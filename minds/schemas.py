"""Schema quyết định v3 (SPEC 5) + thẻ chính sách (SPEC 4.2) — pydantic v2.

LLM chỉ trả JSON theo schema này; engine validate whitelist rồi mới thi hành.
Trường lạ / loại lạ → bỏ qua + ghi unrecognized (điều luật #3).

`LOAI_HANH_DONG` KHÔNG còn là danh sách chép tay ("15 nguyên tố" của SPEC 5 đã lỗi thời —
catalog hiện có 38 action): nó được DERIVED từ `minds/capabilities.py` (ADR 0006 §A.1).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from minds.capabilities import cac_ten_cong_khai

# Whitelist nguyên tố hành động — DERIVED từ capability registry (ADR 0006 §A.1), không
# còn là danh sách chép tay. Thêm/bớt action = sửa `minds/capabilities.py`; mọi chỗ khác
# (schema, translate, menu prompt, test) tự theo. Giữ nguyên TÊN PUBLIC `LOAI_HANH_DONG`
# để không phá import hiện có (minds/translate.py).
LOAI_HANH_DONG: frozenset[str] = cac_ten_cong_khai()


class TheChinhSach(BaseModel):
    """Thẻ chính sách — engine thi hành mỗi tick tới khi agent thay thẻ.

    Thẻ KHÔNG được tự ký hợp đồng mới phức tạp — cái đó cần LLM (trigger).
    """

    model_config = ConfigDict(extra="ignore")

    du_tru_muc_tieu: float = Field(default=2.5, ge=0, le=20)  # × nhu cầu hộ / tick
    canh_toi_da: int = Field(default=3, ge=0, le=10)
    khai_go_khi_ranh: bool = True
    hoc_khi_du_an: bool = False
    day_con: bool = True
    y_dinh_sinh_con: float = Field(default=0.5, ge=0, le=1)
    # tự động trả lời hợp đồng quen thuộc: mô-típ → điều kiện
    nhan_lam_cong_gia_toi_thieu: float | None = None  # kg thóc/công
    nhan_gui_thoc: bool = False
    ban_go_nguong: float | None = None  # bán gỗ khi vượt ngưỡng
    mua_cong_cu_khi_hong: bool = True
    nguong_rao_dat: float | None = None  # an ninh dưới ngưỡng → rao bớt đất
    phung_duong_cha_me: bool = True  # tự chuyển thóc cho cha mẹ già thiếu ăn
    # heuristic sinh tồn tự động (giết gà khi đói, đánh cá khi túng, bán gà đàn đông)
    # — LLM TẮT được bằng patch (tính "thẻ do agent tự đặt", check.md D5)
    an_toan_sinh_ton: bool = True
    du_dinh: str = ""  # dự định dài hạn TỰ GHI — hiện lại trong prompt lần nghĩ sau


class PolicyPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    # mọi trường của thẻ đều patch được; chỉ trường xuất hiện mới bị thay
    du_tru_muc_tieu: float | None = None
    canh_toi_da: int | None = None
    khai_go_khi_ranh: bool | None = None
    hoc_khi_du_an: bool | None = None
    day_con: bool | None = None
    y_dinh_sinh_con: float | None = None
    nhan_lam_cong_gia_toi_thieu: float | None = None
    nhan_gui_thoc: bool | None = None
    ban_go_nguong: float | None = None
    mua_cong_cu_khi_hong: bool | None = None
    nguong_rao_dat: float | None = None
    phung_duong_cha_me: bool | None = None
    an_toan_sinh_ton: bool | None = None
    du_dinh: str | None = None
    # UNSET ngưỡng None-able (patch None nghĩa là "không đổi" nên cần kênh riêng):
    # vd {"bo_nguong": ["ban_go_nguong"]} → ngừng bán gỗ theo ngưỡng
    bo_nguong: list[str] | None = None


class HanhDong(BaseModel):
    """Hành động thô — validate chi tiết theo `loai` khi ánh xạ sang KeHoach."""

    model_config = ConfigDict(extra="allow")
    loai: str


class QuyetDinh(BaseModel):
    id: str
    the_chinh_sach: PolicyPatch | None = None
    hanh_dong: list[HanhDong] = Field(default_factory=list)
    ly_do: str = ""
    model_config = ConfigDict(extra="allow")  # trường lạ → unrecognized log


def ap_patch(the_cu: TheChinhSach, patch: PolicyPatch) -> TheChinhSach:
    """Áp patch AN TOÀN: trường nào ngoài khoảng hợp lệ thì bỏ TRƯỜNG ĐÓ (điều luật #3
    — dữ liệu LLM là input không tin được; giá trị lạ không được làm sập run)."""
    from pydantic import ValidationError

    du_lieu: dict[str, Any] = the_cu.model_dump()
    moi = patch.model_dump(exclude_none=True)
    # bo_nguong: unset tường minh các trường None-able (exclude_none nuốt None thường)
    bo = moi.pop("bo_nguong", None) or []
    truong_none_able = {
        ten for ten, f in TheChinhSach.model_fields.items() if f.default is None
    }
    for ten in bo:
        if str(ten) in truong_none_able:
            moi[str(ten)] = None
    for _ in range(len(moi) + 1):
        try:
            return TheChinhSach(**{**du_lieu, **moi})
        except ValidationError as e:
            truong_loi = {loi["loc"][0] for loi in e.errors() if loi["loc"]}
            if not truong_loi:
                break
            for k in truong_loi:
                moi.pop(k, None)
    return the_cu  # không cứu nổi → giữ thẻ cũ
