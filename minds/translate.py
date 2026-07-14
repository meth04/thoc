"""Ánh xạ hai chiều KeHoach ↔ QuyetDinh — dispatch qua capability registry (ADR 0006 §A).

- PersonaBot nghĩ bằng KeHoach → xuất QuyetDinh JSON (như một LLM thật sẽ trả).
- Validator nhận QuyetDinh (đã sửa JSON) → dựng lại KeHoach cho engine.
Tham số sai / loại lạ → bỏ + ghi unrecognized, KHÔNG lỗi (điều luật #3).

Module này KHÔNG còn chứa bảng elif: mọi hành động được khai báo MỘT LẦN ở
`minds/capabilities.py` (`to_kehoach` / `from_kehoach` / `thu_tu_phat`). Thứ tự phát JSON
là WIRE CONTRACT (chợ khớp theo thứ tự danh sách lệnh khi giá bằng nhau) nên do
`thu_tu_phat` quyết định, không do thứ tự khai báo trong file.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from engine.intents import KeHoach
from minds.capabilities import ap_dung_hanh_dong, hanh_dong_tu_ke_hoach
from minds.schemas import LOAI_HANH_DONG, HanhDong, QuyetDinh

__all__ = [
    "LOAI_HANH_DONG",
    "ke_hoach_thanh_quyet_dinh",
    "quyet_dinh_thanh_ke_hoach",
]


def ke_hoach_thanh_quyet_dinh(kh: KeHoach, patch: dict | None = None,
                              ly_do: str = "") -> dict[str, Any]:
    """KeHoach → dict QuyetDinh (sẵn sàng serialize JSON)."""
    qd: dict[str, Any] = {"id": kh.id, "hanh_dong": hanh_dong_tu_ke_hoach(kh), "ly_do": ly_do}
    if patch:
        qd["the_chinh_sach"] = patch
    return qd


def quyet_dinh_thanh_ke_hoach(w, qd: QuyetDinh,
                              thung_intent_la: list | None = None) -> KeHoach:
    """QuyetDinh (đã validate schema) → KeHoach.

    Hành động lạ/sai tham số: có `thung_intent_la` → gom vào thùng cho bộ phiên dịch
    intent (LLM) thử ánh xạ; không có thùng → bỏ + log như cũ (điều luật #3).
    """
    kh = KeHoach(id=qd.id)
    for hd in qd.hanh_dong:
        try:
            _mot_hanh_dong(w, kh, hd, thung_intent_la)
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as e:
            if thung_intent_la is not None:
                thung_intent_la.append((qd.id, hd.model_dump(), f"tham số sai: {e}"))
            else:
                w.ghi_unrecognized(qd.id, hd.loai, f"tham số sai: {e}")
    # ý định sinh con nằm trong thẻ (patch xử lý ở orchestrator)
    return kh


def _mot_hanh_dong(w, kh: KeHoach, hd: HanhDong, thung: list | None = None) -> None:
    """Một hành động đã validate schema → mutate KeHoach (qua descriptor trong catalog).

    Giữ nguyên chữ ký cũ (minds/real.py bộ phiên dịch intent lạ gọi trực tiếp).
    """
    ap_dung_hanh_dong(w, kh, hd.model_dump(), thung)
