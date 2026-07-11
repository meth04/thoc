"""Ý định đã validate mà engine thi hành. Phase 1: KeHoach tự cung tự cấp của rulebot.

LLM/rulebot không bao giờ chạm state (điều luật #3) — chỉ trả về các cấu trúc ở đây;
engine kiểm tra vật lý (đủ công, đủ giống, đúng loại đất...) rồi mới thực thi.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeHoach:
    """Kế hoạch một tick của một agent (Phase 1 — chưa có chợ/hợp đồng)."""

    id: str
    canh_thua: list[str] = field(default_factory=list)  # thửa muốn canh mùa mưa (≤3)
    gop_cong_cho: str | None = None  # trẻ em góp công cho cha/mẹ
    cong_khai_go: float = 0.0
    cong_khai_quang: float = 0.0
    che_tao_cong_cu: int = 0
    xay_nha: int = 0
    hoc: bool = False  # dành 50% công cho việc học (bậc kế tiếp)
    day_cho: list[str] = field(default_factory=list)  # dạy E1 tại nhà cho con
    cau_hon: str | None = None
    tra_loi_cau_hon: dict[str, bool] = field(default_factory=dict)
    y_dinh_sinh_con: float = 0.5
