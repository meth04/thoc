"""Ngân sách request LLM theo tick.

Budget của treatment hiện hành có phạm vi **mỗi agent**: một cư dân trưởng
thành có ít nhất một và nhiều nhất N request provider trong một tick.  Vì thế
50 người ở tick đầu có dải 50..(50×N) request, thay vì một trần 10 cho cả
làng.  ``cong_cu_max_luot`` chỉ giới hạn vòng tool; retry, fail-over và mỗi
vòng agentic vẫn phải được đếm như request độc lập.

Lớp này là semaphore thread-safe dùng chung trong một tick.  Mỗi agent có một
``logical_id`` bền (``agent:<id>``); trần task của ID đó chính là trần *tổng*
cho mọi quyết định, tool, dịch intent, hồi ký và reflection của agent ấy.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


class LoiVuotNganSachTick(Exception):
    """Không còn slot LLM của tick hiện tại.

    Khác với :class:`LoiHetQuota`: đây không phải RPD/RPM cạn và không được
    kích hoạt cơ chế chờ hay dừng cả run.  Caller phải dùng policy/fallback
    cục bộ cho phần việc chưa bắt đầu.
    """


@dataclass
class NganSachLLMTick:
    """Bộ đếm thread-safe cho một tick.

    ``logical_id`` ghép tất cả retry/vòng tool/call phụ của cùng một agent.
    ``toi_da`` là tổng trần của cả tick (= số agent × trần mỗi agent); trần
    task áp cho ``agent:<id>`` bảo đảm không một agent nào vượt quota riêng.
    """

    tick: int
    toi_thieu: int
    toi_da: int
    default_toi_da_moi_task: int = 1
    da_bat_dau: int = 0
    bi_tu_choi: int = 0
    theo_task: dict[str, int] = field(default_factory=dict)
    theo_loai: dict[str, int] = field(default_factory=dict)
    toi_thieu_theo_task: dict[str, int] = field(default_factory=dict)
    # The lower bound is meaningful only while the world still has someone who
    # can make an economic decision.  We record that applicability explicitly:
    # an extinct/no-adult world must not burn a synthetic request just to make
    # a chart look compliant.
    toi_thieu_ap_dung: bool = False
    ngoai_le_toi_thieu: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.tick = int(self.tick)
        self.toi_thieu = max(0, int(self.toi_thieu))
        self.toi_da = max(0, int(self.toi_da))
        self.default_toi_da_moi_task = max(1, int(self.default_toi_da_moi_task))
        if self.toi_thieu > self.toi_da:
            raise ValueError("ngân sách LLM tick: tối thiểu không được lớn hơn tối đa")

    def con_lai(self) -> int:
        with self._lock:
            return max(0, self.toi_da - self.da_bat_dau)

    def con_lai_cho_task(self, logical_id: str, *, toi_da_task: int | None = None) -> int:
        """Số slot còn có thể dùng ngay cho một task logic.

        Đây là ảnh chụp để vòng tool biết khi nào phải ép lượt cuối trả JSON.
        ``bat_dau`` vẫn là hàng rào nguyên tử cuối cùng, vì các agent real có
        thể cùng xin slot song song.
        """
        cap = self.default_toi_da_moi_task if toi_da_task is None else int(toi_da_task)
        cap = max(1, cap)
        key = str(logical_id or "anonymous")
        with self._lock:
            con_task = max(0, cap - self.theo_task.get(key, 0))
            con_tick = max(0, self.toi_da - self.da_bat_dau)
            return min(con_task, con_tick)

    def dat_yeu_cau_toi_thieu(self, ap_dung: bool, *, ly_do_ngoai_le: str | None = None) -> None:
        """Khai báo xem sàn call có áp dụng ở tick này hay không.

        Chỉ orchestrator biết có người trưởng thành còn sống để suy nghĩ. Bộ
        đếm không được tự suy từ số request, vì chính điều đó sẽ che mất bug
        ``0 call`` mà ta đang cần quan sát.
        """
        with self._lock:
            self.toi_thieu_ap_dung = bool(ap_dung and self.toi_thieu > 0)
            self.ngoai_le_toi_thieu = (
                None if self.toi_thieu_ap_dung else (ly_do_ngoai_le or "not_applicable")
            )

    def dat_yeu_cau_cho_tasks(self, logical_ids: list[str] | tuple[str, ...] | set[str],
                              *, toi_thieu_moi_task: int | None = None) -> None:
        """Buộc mỗi agent/task trong danh sách có tối thiểu một request.

        Đây là chỗ biến cam kết "mỗi agent ít nhất một call" thành một bất
        biến có thể kiểm tra, thay vì chỉ suy từ tổng call toàn làng (một agent
        có thể đã dùng hết call của người khác mà tổng vẫn nhìn có vẻ đủ).
        """
        muc = self.toi_thieu if toi_thieu_moi_task is None else int(toi_thieu_moi_task)
        if muc < 1:
            raise ValueError("mỗi agent được yêu cầu phải có ít nhất một request")
        with self._lock:
            self.toi_thieu_theo_task = {
                str(logical_id): muc for logical_id in sorted(set(logical_ids))
            }
            self.toi_thieu_ap_dung = bool(self.toi_thieu_theo_task)
            self.ngoai_le_toi_thieu = None if self.toi_thieu_ap_dung else "no_autonomous_agent"

    def dat_cho(self, logical_id: str, *, loai: str = "decision",
                toi_da_task: int | None = None) -> None:
        """Reserve metadata only, without consuming a network call.

        Chủ yếu để task nền có một per-task cap rõ ràng.  Slot thật chỉ bị
        tiêu ở :meth:`bat_dau`, ngay trước ``client.post``.
        """
        _ = loai
        cap = self.default_toi_da_moi_task if toi_da_task is None else int(toi_da_task)
        if cap < 1:
            raise ValueError("mỗi task LLM phải được phép ít nhất một request")
        # Không cần lưu cap ở đây: request mang cap tường minh, giữ method này
        # cho API đọc dễ hiểu và tương thích với các caller tương lai.
        _ = logical_id

    def bat_dau(self, logical_id: str, *, loai: str = "decision",
                 toi_da_task: int | None = None) -> bool:
        """Xin một slot cho *một request HTTP thật*.

        Trả ``False`` thay vì raise để provider có thể giải phóng key/slot đã
        giữ trước đó.  Không rollback slot nếu request HTTP sau đó lỗi: request
        đã rời process nên quota/chi phí vẫn có thể đã phát sinh.
        """
        cap = self.default_toi_da_moi_task if toi_da_task is None else int(toi_da_task)
        cap = max(1, cap)
        key = str(logical_id or "anonymous")
        kind = str(loai or "decision")
        with self._lock:
            if self.da_bat_dau >= self.toi_da or self.theo_task.get(key, 0) >= cap:
                self.bi_tu_choi += 1
                return False
            self.da_bat_dau += 1
            self.theo_task[key] = self.theo_task.get(key, 0) + 1
            self.theo_loai[kind] = self.theo_loai.get(kind, 0) + 1
            return True

    def thong_ke(self) -> dict[str, Any]:
        with self._lock:
            if self.toi_thieu_theo_task:
                min_required = sum(self.toi_thieu_theo_task.values())
                vi_pham = sorted(
                    task for task, muc in self.toi_thieu_theo_task.items()
                    if self.theo_task.get(task, 0) < muc
                )
                min_met: bool | None = not vi_pham
            else:
                min_required = self.toi_thieu if self.toi_thieu_ap_dung else 0
                vi_pham = []
                min_met = (bool(self.da_bat_dau >= min_required)
                           if self.toi_thieu_ap_dung else None)
            return {
                "api_call": int(self.da_bat_dau),
                "api_call_cap": int(self.toi_da),
                "api_call_denied": int(self.bi_tu_choi),
                "api_call_by_kind": dict(sorted(self.theo_loai.items())),
                "api_call_by_task": dict(sorted(self.theo_task.items())),
                "api_call_min_required": int(min_required),
                "api_call_min_met": min_met,
                "api_call_min_exception": self.ngoai_le_toi_thieu,
                "api_call_min_violations": vi_pham,
            }


def logical_id_cua(req: Any) -> str:
    """Khóa ổn định dùng chung cho provider real và mock."""
    return str(getattr(req, "logical_id", "") or
               f"{getattr(req, 'logical_kind', 'decision')}:{','.join(req.batch_ids)}")


def bat_dau_yeu_cau(req: Any) -> None:
    """Lấy một slot trước đúng một lần gọi provider.

    Với provider real đây là ngay trước HTTP ``post``; với PersonaBot đây là
    một call mô phỏng tương đương. Transcript replay không gọi hàm này vì nó
    không gọi model và phải tái tạo nguyên trạng artifact cũ.
    """
    budget = getattr(req, "tick_budget", None)
    if budget is None:
        return
    logical_id = logical_id_cua(req)
    if not budget.bat_dau(
        logical_id,
        loai=str(getattr(req, "logical_kind", "decision") or "decision"),
        toi_da_task=getattr(req, "max_api_calls", None),
    ):
        raise LoiVuotNganSachTick(
            f"tick {getattr(budget, 'tick', '?')}: hết slot LLM cho {logical_id}"
        )


def slot_con_lai_cho_yeu_cau(req: Any) -> int | None:
    """Trả số lượt provider còn lại cho task; ``None`` = không bật budget."""
    budget = getattr(req, "tick_budget", None)
    if budget is None:
        return None
    return budget.con_lai_cho_task(
        logical_id_cua(req), toi_da_task=getattr(req, "max_api_calls", None)
    )


def cau_hinh_ngan_sach(cfg: Any) -> dict[str, int | float | bool | str]:
    """Đọc + kiểm tra cấu hình scheduler một lần ở rìa minds.

    Giữ fallback cho checkpoint/config cũ: mode mới là opt-in, còn các tham
    số legacy giữ nguyên hành vi nếu không có block mới. Khi bật, ``1..10``
    là giới hạn **mỗi agent**, không phải tổng làng.
    """
    raw = cfg.get("minds.llm_tick", {})
    if not isinstance(raw, dict):
        raise ValueError("minds.llm_tick phải là object")
    bat = bool(raw.get("bat", False))
    pham_vi = str(raw.get("pham_vi", "moi_agent"))
    toi_thieu = int(raw.get("toi_thieu_call", 1))
    toi_da = int(raw.get("toi_da_call", 10))
    # All auxiliary calls of an agent share its own cap.  A smaller explicit
    # value is accepted for ablations, but can never exceed the agent cap.
    moi_task = int(raw.get("toi_da_call_moi_quyet_dinh", toi_da))
    goi_ho_tro = bool(raw.get("goi_ho_tro", False))
    kiem_tra_burst_rpm = bool(raw.get("kiem_tra_burst_rpm", False))
    cho_burst_rpm_toi_s = float(raw.get("cho_burst_rpm_toi_s", 0))
    cho_burst_rpm_poll_s = float(raw.get("cho_burst_rpm_poll_s", 3))
    if toi_thieu < 0 or toi_da < 1 or toi_thieu > toi_da:
        raise ValueError("minds.llm_tick phải có 0 <= toi_thieu_call <= toi_da_call")
    if pham_vi != "moi_agent":
        raise ValueError("minds.llm_tick.pham_vi hiện chỉ hỗ trợ 'moi_agent'")
    if moi_task < 1 or moi_task > toi_da:
        raise ValueError("minds.llm_tick: trần mỗi agent/task phải thuộc [1, toi_da_call]")
    if cho_burst_rpm_toi_s < 0 or cho_burst_rpm_poll_s <= 0:
        raise ValueError("minds.llm_tick: thời gian chờ burst phải >= 0 và poll phải > 0")
    return {
        "bat": bat,
        "pham_vi": pham_vi,
        "toi_thieu": toi_thieu,
        "toi_da": toi_da,
        "toi_da_moi_task": moi_task,
        "goi_ho_tro": goi_ho_tro,
        "kiem_tra_burst_rpm": kiem_tra_burst_rpm,
        "cho_burst_rpm_toi_s": cho_burst_rpm_toi_s,
        "cho_burst_rpm_poll_s": cho_burst_rpm_poll_s,
    }
