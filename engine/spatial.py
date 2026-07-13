"""Helper KHÔNG GIAN (ADR 0005, Phase A): cờ overlay + hình học hai bờ sông.

THUẦN đọc — không mutate World/Parcel, không chạm ledger, không tiêu RNG. Khi overlay
TẮT (mặc định), mọi helper trả giá trị trung tính (không phân bờ, không cần đò) ⇒ hành
vi + world_hash legacy y nguyên. Cờ đọc qua ``cfg.get("khong_gian.bat", False)`` nên KHÔNG
cần thêm key vào base ``config/world.yaml`` (giữ config-digest base bất biến).
"""

from __future__ import annotations

from typing import Any

from engine.ledger import LoiSoKep
from engine.types import Parcel


def _khong_gian_bat(x: Any) -> bool:
    """Cờ tổng ``khong_gian.bat`` (mặc định TẮT). Nhận Config hoặc World (đọc ``.cfg``)."""
    cfg = getattr(x, "cfg", x)
    return bool(cfg.get("khong_gian.bat", False))


def _hai_bo_bat(x: Any) -> bool:
    """Sub-flag ``hai_bo``: chỉ chia hai bờ khi CẢ ``khong_gian.bat`` và ``.hai_bo`` bật."""
    cfg = getattr(x, "cfg", x)
    return _khong_gian_bat(x) and bool(cfg.get("khong_gian.hai_bo", False))


def _vu_dong_bat(x: Any) -> bool:
    """Cờ vụ khô ngô/khoai; tắt độc lập để làm ablation calendar."""
    cfg = getattr(x, "cfg", x)
    return _khong_gian_bat(x) and bool(cfg.get("khong_gian.vu_dong.bat", False))


def _ga_rung_bat(x: Any) -> bool:
    """Cờ pool gà rừng tái tạo; tắt giữ semantics bắt gà legacy."""
    cfg = getattr(x, "cfg", x)
    return _khong_gian_bat(x) and bool(cfg.get("khong_gian.ga_rung.bat", False))


def _cham_tre_bat(x: Any) -> bool:
    """Cờ time-cost chăm trẻ; tắt không trừ công của run legacy."""
    cfg = getattr(x, "cfg", x)
    return _khong_gian_bat(x) and bool(cfg.get("khong_gian.cham_tre.bat", False))


def cung_bo(a: Parcel, b: Parcel) -> bool:
    """Hai thửa CÙNG bờ? Bờ ``None`` (chưa phân bờ / ô sông) coi như không rào ⇒ True.

    Nhờ vậy khi overlay TẮT (mọi thửa ``bo=None``) hàm luôn trả True ⇒ không ràng buộc
    di chuyển, giữ nguyên ngữ nghĩa legacy (sông KHÔNG chặn).
    """
    if a.bo is None or b.bo is None:
        return True
    return a.bo == b.bo


def qua_song_can_do(tu: Parcel, den: Parcel) -> bool:
    """Đi từ ``tu`` sang ``den`` có phải vượt sông (cần đò)? = khác bờ."""
    return not cung_bo(tu, den)


def reachable(tu: Parcel, den: Parcel, co_do: bool = False) -> bool:
    """Tới được ``den`` từ ``tu``? Cùng bờ luôn tới; khác bờ chỉ khi có đò (``co_do``)."""
    if cung_bo(tu, den):
        return True
    return bool(co_do)


# --------------------------------------------------------------------------- #
#  Phase B/C: vị trí người theo bờ + đò-dịch-vụ (thuyền + rao phí + qua_song)   #
# --------------------------------------------------------------------------- #
def _bo_cua(w: Any, aid: str) -> str | None:
    """Bờ nơi ``aid`` cư trú. TẮT (mọi thửa ``bo=None``) hoặc ô sông ⇒ None (không rào)."""
    if not _hai_bo_bat(w):
        return None
    r, c = w.vi_tri_cua(aid)
    p = w.parcels.get(f"P{r:02d}_{c:02d}")
    return p.bo if p is not None else None


def co_the_o_bo(w: Any, aid: str, bo: str | None) -> bool:
    """``aid`` được hoạt động trên bờ ``bo`` tick này? Cùng bờ cư trú, hoặc đã qua đò.

    TẮT / ``bo`` None ⇒ luôn True (không rào) ⇒ hành vi legacy y nguyên. Đây là điểm
    kiểm DUY NHẤT cho "sông chặn liên bờ": chợ/khai hoang/khai thác bờ kia đều hỏi hàm này.
    """
    if not _hai_bo_bat(w) or bo is None:
        return True
    if _bo_cua(w, aid) == bo:
        return True
    return aid in getattr(w, "ben_kia_tick", set())


def _dong_thuyen(w: Any, aid: str, so_luong: int) -> None:
    """Đóng thuyền: recipe công+gỗ NGUYÊN TỬ (thiếu ⇒ skip, không mất công) — như xay_nha."""
    from engine.production import _lam_nguyen_tu, ghi_cong_dung

    r = w.cfg.get("san_xuat.recipe.thuyen", {})
    if not r:
        return
    cong, go = float(r["cong"]), float(r["go"])
    for _ in range(int(so_luong)):
        tieu = [("cong", cong, "dung"), ("go", go, "xay")]
        if not _lam_nguyen_tu(w, aid, "đóng thuyền", tieu,
                              [("thuyen", 1.0, "dong_thuyen")]):
            break
        ghi_cong_dung(w, "phi_nong", cong)
        w.events.ghi(w.tick, "dong_thuyen", id=aid)


def buoc_qua_song(w: Any, ke_hoach: dict) -> None:
    """Đò là DỊCH VỤ (ADR 0005 §2.3): đóng thuyền + niêm yết phí + chở khách qua sông.

    Gated ``_hai_bo_bat`` (TẮT ⇒ no-op ⇒ hash legacy bất biến). KHÔNG teleport: chỉ khách
    trả phí THÀNH CÔNG (hoặc tự sở hữu thuyền) mới vào ``w.ben_kia_tick``. Phí = ``chuyen``
    khách→chủ đò (cân, không mint tiền công); thuyền hao mòn mỗi chuyến vận hành. Tất định:
    sắp theo id + khách theo (phí giảm dần, id); capacity cắt phần dư — không dùng RNG.
    """
    if not _hai_bo_bat(w):
        return
    # 1) Đóng thuyền TRƯỚC vận hành (công đã sinh ở bước sinh_cong).
    for aid in sorted(ke_hoach):
        n = int(getattr(ke_hoach[aid], "dong_thuyen", 0) or 0)
        if n > 0 and aid in w.agents and w.agents[aid].con_song:
            _dong_thuyen(w, aid, n)

    ben_kia: set[str] = w.ben_kia_tick
    hao_mon = float(w.cfg.get("khong_gian.do.hao_mon_moi_tick_dung", 0.0))
    cap = int(w.cfg.get("khong_gian.do.khach_toi_da_moi_tick", 0))
    dung_thuyen: set[str] = set()  # chủ thuyền vận hành tick này ⇒ hao mòn

    def _di_duoc(kid: str, den_bo: str) -> bool:
        a = w.agents.get(kid)
        if a is None or not a.con_song or kid in ben_kia:
            return False
        bo = _bo_cua(w, kid)  # phải cư trú bờ ĐỐI DIỆN đích (không tự "qua" về bờ mình)
        return bo is not None and den_bo in ("dan_cu", "hoang") and den_bo != bo

    def _qua(operator: str, kid: str) -> None:
        ben_kia.add(kid)
        dung_thuyen.add(operator)
        w.events.ghi(w.tick, "qua_song", operator=operator, khach=kid)

    # 2) Chủ thuyền TỰ qua (sở hữu phương tiện) — không phí, chỉ hao mòn thuyền của mình.
    for kid in sorted(ke_hoach):
        req = getattr(ke_hoach[kid], "qua_song", None)
        if req is None or w.ledger.so_du(kid, "thuyen") < 1.0:
            continue
        if _di_duoc(kid, str(req[0])):
            _qua(kid, kid)

    # 3) Khớp khách ↔ chủ đò: chủ niêm yết (phi, tài sản); khách chấp nhận (≥ phí, đúng tài
    #    sản, đúng bờ). Khách trả THÓC được ngay (chủ chấp nhận) — tiền tệ chưa cần.
    for op in sorted(ke_hoach):
        offer = getattr(ke_hoach[op], "rao_do", None)
        if offer is None or op not in w.agents or not w.agents[op].con_song:
            continue
        if w.ledger.so_du(op, "thuyen") < 1.0:
            continue
        phi, ts = float(offer[0]), str(offer[1])
        ung_vien: list[tuple[float, str]] = []
        for kid in sorted(ke_hoach):
            if kid == op or kid in ben_kia:
                continue
            req = getattr(ke_hoach[kid], "qua_song", None)
            if req is None:
                continue
            den_bo, ts_tra, phi_tra = str(req[0]), str(req[1]), float(req[2])
            if ts_tra != ts or phi_tra + 1e-9 < phi or not _di_duoc(kid, den_bo):
                continue
            ung_vien.append((phi_tra, kid))
        ung_vien.sort(key=lambda x: (-x[0], x[1]))  # sẵn lòng trả cao trước, tie-break id
        cho = 0
        for _phi_tra, kid in ung_vien:
            if cho >= cap:
                break  # vượt capacity chuyến này ⇒ khách còn lại kẹt bờ
            try:
                w.ledger.chuyen(kid, op, ts, phi, f"phí đò {op}", w.tick)
            except LoiSoKep:
                continue  # khách không đủ phí ⇒ không qua, không âm sổ (kẹt/suy kiệt hợp lệ)
            _qua(op, kid)
            cho += 1

    # 4) Hao mòn thuyền của mọi chủ vận hành tick này (SINK đã đăng ký, audit tự cân).
    for op in sorted(dung_thuyen):
        bal = w.ledger.so_du(op, "thuyen")
        if bal > 1e-9 and hao_mon > 0:
            w.ledger.huy(op, "thuyen", min(bal, hao_mon), "hao_mon_thuyen",
                         "hao mòn thuyền", w.tick)
