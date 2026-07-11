"""Kiểu dữ liệu lõi của thế giới: Persona, Agent, Parcel, Village."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Persona:
    """5 trục tính cách 1–9, bất biến trọn đời (SPEC 4.5)."""

    lieu_linh: int = 5  # chấp nhận rủi ro
    cham_chi: int = 5  # cường độ lao động
    trong_hoc: int = 5  # coi trọng học hành / R&D
    hop_tac: int = 5  # thiên hướng hợp tác, giữ chữ tín
    tiet_kiem: int = 5  # tích trữ vs tiêu dùng

    def as_dict(self) -> dict[str, int]:
        return {
            "lieu_linh": self.lieu_linh,
            "cham_chi": self.cham_chi,
            "trong_hoc": self.trong_hoc,
            "hop_tac": self.hop_tac,
            "tiet_kiem": self.tiet_kiem,
        }


@dataclass
class Agent:
    id: str
    ten: str
    gioi_tinh: str  # "nam" | "nu"
    tuoi_tick: int  # tuổi tính bằng tick (6 tháng); tuổi năm = tuoi_tick / 2
    persona: Persona
    lang: int = 0
    health: float = 100.0
    e_bac: int = 0  # bậc giáo dục E0..E4
    con_song: bool = True
    vo_chong: str | None = None
    cha: str | None = None
    me: str | None = None
    con: list[str] = field(default_factory=list)
    # học hành: đang học lên bậc nào, còn bao nhiêu tick
    hoc_muc_tieu: int | None = None
    hoc_tick_con: int = 0
    hoc_tu_hoc: bool = False
    # trạng thái tạm theo tick
    vo_gia_cu: bool = False
    y_dinh_sinh_con: float = 0.5  # 0 | 0.5 | 1 — mind cập nhật
    # hồi ký / gia huấn / di chúc (Phase 3+)
    hoi_ky: str = ""
    gia_huan: str = ""
    di_chuc: dict | None = None  # {"phan_bo": {id: %}, "gia_huan": str}
    # theo dõi sinh tồn + phản hồi hành động (LLM đọc trong prompt)
    doi_tick: int = -99  # tick gần nhất bị thiếu ăn
    su_co: list = field(default_factory=list)  # việc không thành gần đây (≤3 mục)
    # ký ức đời người — engine tự ghi các biến cố (cưới, sinh con, tang, giao kèo,
    # đất đai...); LLM đọc trong prompt để sống TIẾP một cuộc đời, không phải mỗi
    # lần được hỏi lại là một người xa lạ
    ky_uc: list = field(default_factory=list)  # ≤10 mục gần nhất

    @property
    def tuoi_nam(self) -> float:
        return self.tuoi_tick / 2.0

    def truong_thanh(self, tuoi_truong_thanh: int) -> bool:
        return self.tuoi_nam >= tuoi_truong_thanh


@dataclass
class Parcel:
    id: str
    r: int
    c: int
    loai: str  # ruong | rung | doi | mo_dong | song
    mau_mo: float = 1.0
    chu: str | None = None  # None = đất công; id người hoặc pháp nhân
    lang: int | None = None
    # trạng thái canh tác trong tick hiện tại
    nguoi_canh: str | None = None
    homestead_dem: int = 0  # số mùa mưa liên tiếp cùng một người canh đất công
    homestead_ai: str | None = None


@dataclass
class Village:
    id: int
    ten: str
    r: int
    c: int
