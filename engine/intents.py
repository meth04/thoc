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
    # ---- Phase 2: hợp đồng + chợ ----
    # đề nghị hợp đồng: list (HopDong, den | None)
    de_nghi_hop_dong: list = field(default_factory=list)
    # trả lời đề nghị trên bảng rao: ref → "chap_nhan" | "tu_choi" | HopDong (mặc cả)
    tra_loi_de_nghi: dict = field(default_factory=dict)
    don_phuong_pha_vo: list[str] = field(default_factory=list)  # hd ids
    # báo hủy hợp đồng vô hạn ĐÚNG LUẬT (điều khoản bao_truoc) — không phạt uy tín
    bao_huy: list[str] = field(default_factory=list)  # hd ids
    dat_lenh: list = field(default_factory=list)  # list[Lenh]
    niem_yet_dat: list = field(default_factory=list)  # [(thua, gia_ask)]
    tra_gia_dat: list = field(default_factory=list)  # [(thua, gia)]
    yeu_cau_rut: dict[str, float] = field(default_factory=dict)  # hd_id → số lượng
    # ---- Phase 4: pháp nhân, R&D, máy, xu, di chúc, di cư ----
    xay_may: int = 0
    duc_xu: int = 0  # số mẻ đúc (1 quặng + 5 công → 10 xu)
    che_hang: dict[str, int] = field(default_factory=dict)  # mã hàng mới → số lượng
    nghien_cuu: tuple[str, float, float] | None = None  # (lĩnh vực, công, thóc)
    lap_phap_nhan: dict | None = None  # {ten, co_phan, von_gop, dieu_le}
    quyet_dinh_entity: list = field(default_factory=list)  # [(entity_id, KeHoach con)]
    viet_di_chuc: dict | None = None  # {phan_bo: {id: %}, gia_huan}
    di_cu: bool = False
    # ---- Không gian (ADR 0005 §2.3): đò là DỊCH VỤ, không class định chế ----
    dong_thuyen: int = 0  # đóng N thuyền (recipe công+gỗ, nguyên tử)
    rao_do: tuple | None = None  # chủ thuyền niêm yết: (phi, tai_san_tra) mỗi chuyến
    qua_song: tuple | None = None  # khách xin qua: (den_bo, tai_san_tra, phi_chap_nhan)
    # khai hoang (ADR 0005 §4.1): vỡ rừng/đồi CÔNG thành ruộng (tốn công, homestead qua canh)
    khai_hoang: list[str] = field(default_factory=list)  # thửa rừng/đồi công muốn vỡ hoang
    # chăn nuôi
    bat_ga_cong: float = 0.0  # công dành đi bắt gà rừng về nuôi
    giet_ga: int = 0  # giết bao nhiêu con lấy thịt
    # biếu tặng (phụng dưỡng cha mẹ già, quà cưới, cứu đói hàng xóm...)
    bieu: list = field(default_factory=list)  # [(den, tai_san, so_luong)]
    # sinh kế & xã hội (gói realism 2)
    danh_ca_cong: float = 0.0  # công dành ra sông đánh cá (trữ lượng chung của làng)
    mo_tiec: tuple | None = None  # (thoc, thit) — tiệc khao xóm
    trom: tuple | None = None  # (muc_tieu, tai_san, so_luong) — làm liều, rủi ro thể diện
    # P2P (PART 5.4): nhắn tin 1-1 mặc cả/vận động — [(người nhận, nội dung)]; giao tick sau
    nhan_tin: list = field(default_factory=list)
    # ---- Chính trị (bầu cử, lập pháp, nghiệp đoàn, bạo động) ----
    # engine chỉ cung cấp cơ chế trung lập; MỌI ý định dưới đây do agent tự phát
    ung_cu: bool = False  # ra ứng cử chức trưởng làng kỳ này
    bo_phieu: str | None = None  # id ứng viên mình bầu
    ban_hanh_luat: dict | None = None  # trưởng làng ra luật, vd {"loai":"thue","suat":0.1}
    hoi_lo: tuple | None = None  # (den, thoc) — đút lót một người
    gia_nhap_nghiep_doan: bool = False  # gia nhập nghiệp đoàn (thương lượng tập thể)
    dinh_cong: bool = False  # đình công tick này
    bao_dong: bool = False  # tham gia bạo động (vật lý sung công khi đủ số đông + Gini cao)
    keu_goi: str | None = None  # vận động townhall — thông tin thuần, không dịch chuyển tài sản
