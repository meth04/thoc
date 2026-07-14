"""Kỷ luật prompt chính trị (REPORTS PHẦN 4 §4.1 + check.md P1/P4).

Chứng minh prompt render THẬT:
- có câu CĂN TÍNH GIAI CẤP đầu khối riêng (thuần dữ kiện: giai cấp + tuổi + biến cố đời),
- có đủ ý định chính trị tự phát trong danh mục hành động (mô tả TRUNG LẬP nêu cơ chế),
- có SỰ KIỆN nhà nước làng trong luật vật lý,
- KHÔNG mớm chiến lược (không "nên/hãy/khôn ngoan/đáng") và không lộ tên định chế (P1).
"""

from __future__ import annotations

from minds.prompts import (
    build_agent_prompt,
    build_user_chung,
    build_user_rieng,
    luat_vat_ly,
    muc_hanh_dong,
)
from tests.helpers import the_gioi_test

# Từ mớm chiến lược bị check.md P4 cấm; tên định chế bị P1 cấm.
TU_MOM = ("nên ", "hãy", "khôn ngoan", "đáng")
TEN_DINH_CHE_CAM = ("ngân hàng", "công ty", "bảo hiểm", "xưởng")
Y_DINH_CHINH_TRI = ("ung_cu", "bo_phieu", "ban_hanh_luat", "hoi_lo",
                    "nghiep_doan", "dinh_cong", "bao_dong", "keu_goi")


def _prompt_that(seed: int = 42, aid: str | None = None) -> str:
    w = the_gioi_test(seed=seed, giu_lai=6, thoc_moi_nguoi=2000)
    aid = aid or sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    return build_agent_prompt(w, aid, {aid: ["dinh_ky"]})


def test_prompt_khong_mom_chien_luoc():
    """Toàn bộ prompt 1-to-1 KHÔNG chứa từ mớm ý (check.md P4)."""
    p = _prompt_that().lower()
    for tu in TU_MOM:
        assert tu not in p, f"prompt lộ từ mớm ý: {tu!r}"


def test_prompt_khong_lo_ten_dinh_che():
    """Menu là ngữ pháp + cơ chế trung lập, không nêu tên định chế (check.md P1)."""
    p = _prompt_that().lower()
    for ten in TEN_DINH_CHE_CAM:
        assert ten not in p, f"prompt lộ tên định chế: {ten!r}"


def test_prompt_co_du_y_dinh_chinh_tri():
    """Danh mục hành động phải có đủ 8 ý định chính trị tự phát."""
    p = _prompt_that()
    for loai in Y_DINH_CHINH_TRI:
        assert loai in p, f"thiếu ý định chính trị: {loai}"


def test_menu_chinh_tri_trung_lap_va_dung_hop_dong_schema():
    """Menu chính trị dùng đúng tên schema chốt và mô tả trung lập (không xúi)."""
    # ADR 0006 §B: menu render từ catalog + World.cfg ⇒ cần một world thật (base config).
    menu = "\n".join(muc_hanh_dong(the_gioi_test(seed=42, giu_lai=6, thoc_moi_nguoi=2000)))
    # đúng hợp đồng giao diện
    assert '"loai":"bo_phieu","cho":' in menu
    assert '"loai":"ban_hanh_luat","luat":{"loai":"thue","suat"' in menu
    assert '"loai":"ban_hanh_luat","luat":{"loai":"luong_toi_thieu","muc"' in menu
    assert '"loai":"hoi_lo","den":' in menu and '"thoc":' in menu
    assert '"loai":"nghiep_doan","gia_nhap":' in menu
    assert '"loai":"keu_goi","noi_dung":' in menu
    # trung lập: không có từ mớm trong mô tả menu
    for tu in TU_MOM:
        assert tu not in menu.lower(), f"menu lộ từ mớm ý: {tu!r}"


def test_luat_vat_ly_co_su_kien_nha_nuoc():
    """Luật vật lý nêu SỰ KIỆN nhà nước làng — thuần vật lý, không định hướng."""
    # ADR 0006 §B: luật vật lý render TỪ World.cfg ⇒ cần một world thật (base config).
    van_ban = luat_vat_ly(the_gioi_test(seed=42, giu_lai=6, thoc_moi_nguoi=2000))
    thap = van_ban.lower()
    for cot_moc in ("trưởng làng", "công quỹ", "gini", "sung công",
                    "nghiệp đoàn", "đình công"):
        assert cot_moc in thap, f"luật vật lý thiếu sự kiện: {cot_moc}"
    for tu in TU_MOM:
        assert tu not in thap, f"luật vật lý lộ từ mớm ý: {tu!r}"


def test_can_tinh_giai_cap_dau_khoi_rieng():
    """Câu CĂN TÍNH GIAI CẤP mở đầu khối riêng, rút từ SỰ KIỆN (giai cấp + tuổi + biến cố)."""
    w = the_gioi_test(seed=42, giu_lai=6, thoc_moi_nguoi=2000)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    a = w.agents[aid]
    a.ky_uc_doi = ["đã 2 lần suýt chết đói", "bị A0007 quỵt nợ 200kg thóc"]
    # observatory nạp nhãn giai cấp vào w (getattr an toàn nếu chưa có)
    w.phan_loai = {aid: "ta_dien"}

    rieng = build_user_rieng(w, aid, ["dinh_ky"])
    dong_dau = rieng.split("\n", 1)[0]
    assert dong_dau.startswith("Bạn là "), "câu căn tính phải ở ĐẦU khối riêng"
    assert "tá điền" in dong_dau, "phải mang nhãn giai cấp (dữ kiện thân phận)"
    assert f"{a.tuoi_nam:.0f} tuổi" in dong_dau, "phải nêu tuổi"
    assert "quỵt nợ" in dong_dau, "phải rút biến cố nặng từ ky_uc_doi"
    # thuần dữ kiện — không lời khuyên
    for tu in TU_MOM:
        assert tu not in dong_dau.lower()


def test_can_tinh_khong_co_phan_loai_van_chay():
    """Chưa có observatory phân loại (w.phan_loai vắng) → vẫn ra câu căn tính, không nổ."""
    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=2000)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    assert not getattr(w, "phan_loai", None)  # chưa phân loại (vắng hoặc rỗng {})
    dong_dau = build_user_rieng(w, aid, []).split("\n", 1)[0]
    assert dong_dau.startswith("Bạn là dân làng "), "fallback trung lập khi chưa phân loại"


def test_tinh_hinh_viec_lang_hien_khi_co_chinh_quyen():
    """w.chinh_quyen tồn tại → build_user_chung nêu Trưởng làng/thuế/lương/ứng viên."""
    w = the_gioi_test(seed=42, giu_lai=6, thoc_moi_nguoi=2000)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]

    class _CQ:  # cấu trúc tối thiểu theo hợp đồng ChinhQuyen
        truong_lang = None
        thue_suat = 0.1
        luong_toi_thieu = 2.0
        phieu = {aid: 3}

    w.chinh_quyen = _CQ()
    chung = build_user_chung(w)
    assert "[VIỆC LÀNG]" in chung
    assert "công quỹ" in chung
    assert "10%" in chung and "2.0 thóc/công" in chung
    assert aid in chung.split("[VIỆC LÀNG]", 1)[1]  # ứng viên hiện tên


def test_tinh_hinh_viec_lang_vang_khi_chua_co_nha_nuoc():
    """Chưa có định chế chính trị (w.chinh_quyen vắng) → không chèn [VIỆC LÀNG]."""
    w = the_gioi_test(seed=42, giu_lai=6, thoc_moi_nguoi=2000)
    assert "[VIỆC LÀNG]" not in build_user_chung(w)
