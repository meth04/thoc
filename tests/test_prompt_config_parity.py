"""PROMPT-1 — prompt render TỪ CONFIG ĐANG CHẠY (ADR 0006 §B.2, test matrix §6).

Hai cưỡng chế:

1. **Parity table**: prompt base nói đúng luật base; prompt overlay `spatial_v1` nói đúng
   luật spatial. Cụ thể sản lượng base = **600kg** (`config/world.yaml:23`
   `san_luong_goc_kg: 600`), KHÔNG phải `~650kg` — `650` là **hằng số CHẾT đã trôi** trong
   `LUAT_VAT_LY` cũ (F-34). Bảng trong ADR 0006 §B.2 ghi `650` là SAI; code (600) đúng, ADR
   cần sửa một dòng. Test này chốt 600 và cấm 650 quay lại.
2. **Property chống hardcode tái phát**: với MỖI khóa vật lý trong bảng ADR 0006 §B.1, đổi
   giá trị ⇒ text prompt PHẢI đổi. Khóa nào đổi mà prompt đứng yên = còn hằng số chết
   (hoặc prompt không hề nói về luật đó — cả hai đều là lỗ hổng PROMPT-1).

   NGOẠI LỆ CÓ GHI CHÚ (F-15): hệ số tự-học ×2 (`engine/education.py:65`
   `so_tick * (2 if a.hoc_tu_hoc else 1)`) là **hằng số trong engine, KHÔNG có khóa config**.
   Prompt nói "gấp đôi" là đúng engine hôm nay nhưng không config-driven ⇒ property test
   không phủ được nó. Đây là finding riêng, không phải lỗi của renderer.

Không mạng, không LLM: chỉ dựng World từ Config và render text.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from engine.config import Config, load_config
from engine.world import tao_the_gioi
from minds.capabilities import lich_mua, tai_san_giao_dich
from minds.prompts import build_agent_prompt, luat_vat_ly, muc_hanh_dong

SPATIAL = Path("scenarios/agrarian_transition_v1/spatial_v1.yaml").resolve()
SEED = 11


def _the_gioi(cfg: Config):
    return tao_the_gioi(cfg, SEED, events_path=None)


def _van_ban(w) -> str:
    """Bề mặt text mà PROMPT-1 nói tới: luật vật lý + danh mục hành động (tất định)."""
    return luat_vat_ly(w) + "\n" + "\n".join(muc_hanh_dong(w))


@pytest.fixture(scope="module")
def cfg_base() -> Config:
    return load_config()


@pytest.fixture(scope="module")
def cfg_spatial() -> Config:
    assert SPATIAL.exists(), f"thiếu overlay: {SPATIAL}"
    return load_config(overlays=[SPATIAL])


@pytest.fixture(scope="module")
def w_base(cfg_base):
    return _the_gioi(cfg_base)


@pytest.fixture(scope="module")
def w_spatial(cfg_spatial):
    return _the_gioi(cfg_spatial)


# ============================================================ 1. Parity table (base)
def test_parity_base_dung_luat_base(w_base):
    t = _van_ban(w_base)
    assert "Mỗi tick = 6 tháng; một năm = 2 tick" in t
    assert "Vòng mùa trong năm: lua → kho." in t
    assert "Người lớn PHẢI ăn 90kg thóc/tick (trẻ em 45kg)" in t
    assert "bạn có 180 ngày công" in t
    assert "Mỗi thửa cần 60kg thóc giống + 60 công" in t
    assert "Kho thóc hao 3%/tick" in t
    assert "Canh CÙNG MỘT thửa đất công 2 mùa lúa liên tiếp" in t
    assert "Nhà = 8 gỗ + 240 CÔNG" in t
    assert "Tự canh tối đa 3 thửa" in t


def test_f34_base_noi_600kg_khong_phai_650(w_base):
    """F-34 regression: `config/world.yaml:23` = 600. `~650kg` trong prompt cũ là hằng số
    CHẾT đã trôi ⇒ prompt nói dối agent 8% sản lượng ngay ở base. Cấm nó quay lại.

    Bề mặt kiểm là KHỐI LUẬT VẬT LÝ (nơi phát biểu hằng số vật lý). `650` trong ví dụ JSON
    `tra_gia_dat` ("gia":650) là một GIÁ MINH HỌA của định dạng, không phải phát biểu về
    luật — không tính.
    """
    luat = luat_vat_ly(w_base)
    assert "thu ~600kg × màu mỡ × thời tiết" in luat
    assert "650" not in luat, "hằng số chết 650kg quay lại — prompt lại nói sai sản lượng"
    # và số đó phải THẬT SỰ đến từ config, không phải một hằng 600 mới
    d = copy.deepcopy(load_config().raw())
    d["san_xuat"]["san_luong_goc_kg"] = 777
    assert "thu ~777kg" in luat_vat_ly(_the_gioi(Config(d)))


# ============================================================ 1b. Parity table (spatial)
def test_parity_spatial_dung_luat_overlay(w_spatial):
    t = _van_ban(w_spatial)
    assert "Mỗi tick = 4 tháng; một năm = 3 tick" in t
    assert "Vòng mùa trong năm: lua_1 → lua_2 → dong." in t
    assert "Người lớn PHẢI ăn 60kg thóc/tick (trẻ em 30kg)" in t
    assert "bạn có 120 ngày công" in t
    assert "Mỗi thửa cần 40kg thóc giống + 40 công" in t
    assert "thu ~300kg × màu mỡ × thời tiết" in t
    assert "Kho thóc hao 2.01%/tick" in t
    assert "Canh CÙNG MỘT thửa đất công 4 mùa lúa liên tiếp" in t
    # ba mùa: hai vụ lúa + một vụ đông
    assert lich_mua(w_spatial) == ("lua_1", "lua_2", "dong")
    assert "MÙA LÚA (lua_1, lua_2)" in t
    assert "MÙA KHÔ (dong)" in t
    # cơ chế không-gian phải được NÊU trong luật, không chỉ trong menu
    assert "SÔNG CHIA HAI BỜ" in t
    assert "KHAI HOANG" in t
    assert "CHĂM TRẺ" in t


def test_parity_spatial_khong_con_hang_so_base(w_spatial):
    """Không một hằng số VẬT LÝ của thế giới BASE nào được rò vào prompt spatial."""
    luat = luat_vat_ly(w_spatial)
    for so_sai in ("6 tháng", "90kg thóc/tick", "180 ngày công",
                   "60kg thóc giống + 60 công", "~600kg", "~650kg", "3%/tick",
                   "2 mùa lúa liên tiếp"):
        assert so_sai not in luat, f"luật vật lý spatial còn hằng số của base: {so_sai!r}"


def test_menu_spatial_co_du_sau_action_khong_gian(w_spatial, w_base):
    menu_s = "\n".join(muc_hanh_dong(w_spatial))
    menu_b = "\n".join(muc_hanh_dong(w_base))
    for ten in ("dong_thuyen", "rao_do", "qua_song", "khai_hoang",
                "canh_vu_dong", "cham_tre"):
        assert f'"loai":"{ten}"' in menu_s, f"menu spatial thiếu {ten}"
        assert f'"loai":"{ten}"' not in menu_b, f"menu base quảng cáo {ten} không có thật"
    # F-03: khai_hoang phải có VÍ DỤ JSON (trước đây chỉ có văn xuôi ⇒ LLM phải đoán tên
    # trường `thua`)
    assert '"loai":"khai_hoang","thua"' in menu_s


# ============================================================ 2. Asset list (F-04)
def _asset_menu(w) -> set[str]:
    """Tài sản THẬT SỰ được rao trong dòng menu `dat_lenh` (parse chuỗi pipe từ text)."""
    dong = next(m for m in muc_hanh_dong(w) if '"loai":"dat_lenh"' in m)
    phan = dong.split('"tai_san":"', 1)[1].split('","sl"', 1)[0]
    return {t.strip() for t in phan.split("|")
            if t.strip() and not t.strip().startswith(("co_phan:", "<"))}


def test_asset_list_dat_lenh_render_tu_the_gioi(w_base, w_spatial):
    """`dat_lenh` menu KHÔNG được hardcode `go|cong_cu|quang_dong|xu|nha|thoc` (F-04)."""
    ts_base = tai_san_giao_dich(w_base)
    ts_spatial = tai_san_giao_dich(w_spatial)
    for x in ("thoc", "go", "cong_cu", "quang_dong", "xu", "nha", "ga", "ga_con",
              "thit", "ca", "may"):
        assert x in ts_base, f"base thiếu tài sản giao dịch được: {x}"
    for x in ("ngo", "khoai", "thuyen"):
        assert x in ts_spatial, f"spatial thiếu tài sản: {x}"
        assert x not in ts_base, f"base KHÔNG sinh ra được {x} mà menu vẫn rao"
    # và danh sách đó phải THẬT SỰ nằm trong dòng menu dat_lenh (chuỗi nối bằng '|')
    tok_b, tok_s = _asset_menu(w_base), _asset_menu(w_spatial)
    assert tok_b == set(ts_base), f"menu base lệch tai_san_giao_dich: {tok_b ^ set(ts_base)}"
    assert tok_s == set(ts_spatial), f"menu spatial lệch: {tok_s ^ set(ts_spatial)}"
    for x in ("ngo", "khoai", "thuyen"):
        assert x in tok_s and x not in tok_b
    for x in ("ga_con", "thit", "ca", "may"):
        assert x in tok_b, f"menu base thiếu tài sản có thật: {x} (F-04)"


# ============================================================ 3. Property: đổi config ⇒ đổi prompt
def _dat(d: dict, path: str, val: Any) -> None:
    node = d
    parts = path.split(".")
    for k in parts[:-1]:
        node = node[k]
    assert parts[-1] in node, f"khóa config không tồn tại: {path}"
    node[parts[-1]] = val


# Bảng khóa vật lý — ADR 0006 §B.1. Mỗi hàng của bảng được nở thành khóa cụ thể.
KHOA_BASE: list[tuple[str, Any]] = [
    # tháng/tick, tick/năm, tên mùa
    ("thoi_gian.thang_moi_tick", 4),
    # khẩu phần + ngày công
    ("nhu_cau.nguoi_lon_kg_tick", 91),
    ("nhu_cau.tre_em_kg_tick", 46),
    ("nhu_cau.ngay_cong_moi_tick", 181),
    ("nhu_cau.tre_em_gop_cong_tu_tuoi", 14),
    ("nhu_cau.ty_le_cong_tre_em", 0.31),
    # giống / công / sản lượng mỗi thửa
    ("san_xuat.giong_kg_moi_thua", 61),
    ("san_xuat.cong_moi_thua", 61),
    ("san_xuat.san_luong_goc_kg", 601),
    ("san_xuat.thua_toi_da_tu_canh", 4),
    ("san_xuat.hieu_suat_thua_2_3", [0.8, 0.6]),
    # hao kho + homestead
    ("san_xuat.hao_hut_kho_moi_tick", 0.031),
    ("san_xuat.homestead_tick_lien_tiep", 3),
    # recipe nhà / công cụ / XU
    ("san_xuat.recipe.nha.cong", 241),
    ("san_xuat.recipe.nha.go", 9),
    ("san_xuat.recipe.cong_cu.cong", 61),
    ("san_xuat.recipe.cong_cu.go", 3),
    ("san_xuat.recipe.cong_cu.tang_nang_suat", 1.31),
    ("san_xuat.recipe.cong_cu.hao_mon_moi_tick_dung", 0.051),
    ("san_xuat.recipe.xu.cong", 6),
    ("san_xuat.recipe.xu.ra", 11),
    # khai thác
    ("san_xuat.khai_thac.cong_moi_go", 11),
    ("san_xuat.khai_thac.cong_moi_quang", 21),
    ("san_xuat.khai_thac.hieu_suat_khong_cong_cu", 0.51),
    # tuổi lao động / nghỉ
    ("lao_dong_theo_tuoi.tuoi_giam_suc", 61),
    ("lao_dong_theo_tuoi.he_so_sau_giam", 0.51),
    ("lao_dong_theo_tuoi.tuoi_nghi", 71),
    ("lao_dong_theo_tuoi.he_so_sau_nghi", 0.16),
    # đất bạc màu
    ("dat_dai.thoai_hoa_moi_vu", 0.021),
    ("dat_dai.san_ty_le_mau_mo", 0.51),
    ("dat_dai.phuc_hoi_moi_tick_bo_hoang", 0.009),
    # tay nghề
    ("tay_nghe.tang_moi_vu", 0.005),
    ("tay_nghe.tran", 1.21),
    # cá
    ("danh_ca.cong_moi_kg_ca", 4.6),
    ("danh_ca.tai_sinh_moi_tick", 0.16),
    ("danh_ca.ca_quy_doi_dinh_duong", 2.6),
    ("danh_ca.ca_hao_moi_tick", 0.16),
    # gà
    ("chan_nuoi.bat_ga_cong_moi_con", 31),
    ("chan_nuoi.thit_moi_ga_kg", 9),
    ("chan_nuoi.thit_moi_ga_con_kg", 4),
    ("chan_nuoi.ga_an_thoc_moi_tick", 3),
    ("chan_nuoi.ga_con_an_thoc_moi_tick", 2),
    ("chan_nuoi.ga_sinh_san_moi_tick", 0.16),
    ("chan_nuoi.ga_toi_da_moi_ho", 26),
    ("chan_nuoi.thit_quy_doi_dinh_duong", 3.1),
    ("chan_nuoi.thit_hao_moi_tick", 0.21),
    # giáo dục / hợp đồng văn bản
    ("giao_duc.E1", [40, 3, 0.5]),
    ("giao_duc.E4", [320, 9, 0.5]),
    ("hop_dong.van_ban_can_E_nguoi_soan", 2),
    ("hop_dong.mac_ca_toi_da_vong", 4),
    # sinh nở
    ("nhan_khau.sinh_san.rui_ro_me", 0.03),
    # tiệc / trộm
    ("tiec.chi_phi_toi_thieu_thoc", 61),
    ("tiec.khach_toi_da", 9),
    ("trom.ty_le_lay_toi_da", 0.26),
    ("trom.p_thanh_cong", 0.46),
    # thương mại / p2p
    ("thuong_mai.phi_van_chuyen_moi_khoang_cach", 0.03),
    ("thuong_mai.niem_yet_het_han_tick", 5),
    ("minds.p2p_gui_toi_da", 99),
    # việc làng
    ("chinh_tri.bau_cu_moi_n_tick", 11),
    ("chinh_tri.thue_suat_toi_da", 0.51),
    ("chinh_tri.gini_nguong_bao_dong", 0.86),
    ("chinh_tri.ty_le_so_dong_bao_dong", 0.31),
    ("chinh_tri.ty_le_sung_cong_bao_dong", 0.31),
]

KHOA_SPATIAL: list[tuple[str, Any]] = [
    ("thoi_gian.lich_mua", ["lua_1", "lua_2", "kho_moi"]),
    ("san_xuat.recipe.thuyen.cong", 81),
    ("san_xuat.recipe.thuyen.go", 7),
    ("khong_gian.do.khach_toi_da_moi_tick", 5),
    ("khong_gian.do.hao_mon_moi_tick_dung", 0.04),
    ("khong_gian.khai_hoang.cong_moi_thua", 81),
    ("khong_gian.khai_hoang.mau_mo_khai_hoang", 0.71),
    ("khong_gian.vu_dong.cay.ngo.cong", 41),
    ("khong_gian.vu_dong.cay.ngo.san_luong_kg", 281),
    ("khong_gian.vu_dong.cay.ngo.quy_doi_dinh_duong", 0.91),
    ("khong_gian.vu_dong.cay.khoai.cong", 31),
    ("khong_gian.cham_tre.tuoi_can_cham", 7),
    ("khong_gian.cham_tre.cong_cham_moi_tre", 21),
    ("khong_gian.ga_rung.tai_sinh_moi_tick", 0.15),
]


@pytest.mark.parametrize(("khoa", "gia_tri"), KHOA_BASE, ids=[k for k, _ in KHOA_BASE])
def test_prompt1_doi_khoa_config_base_thi_prompt_doi(khoa, gia_tri, cfg_base, w_base):
    goc = _van_ban(w_base)
    d = copy.deepcopy(cfg_base.raw())
    _dat(d, khoa, gia_tri)
    assert _van_ban(_the_gioi(Config(d))) != goc, (
        f"PROMPT-1: đổi `{khoa}` mà prompt KHÔNG đổi ⇒ luật đó hoặc là hằng số chết trong "
        f"renderer, hoặc KHÔNG BAO GIỜ được nói cho agent (agent phải đoán chi phí/năng "
        f"suất của một hành động menu vẫn quảng cáo)."
    )


@pytest.mark.parametrize(("khoa", "gia_tri"), KHOA_SPATIAL,
                         ids=[k for k, _ in KHOA_SPATIAL])
def test_prompt1_doi_khoa_config_spatial_thi_prompt_doi(khoa, gia_tri, cfg_spatial,
                                                        w_spatial):
    goc = _van_ban(w_spatial)
    d = copy.deepcopy(cfg_spatial.raw())
    _dat(d, khoa, gia_tri)
    assert _van_ban(_the_gioi(Config(d))) != goc, (
        f"PROMPT-1 (spatial): đổi `{khoa}` mà prompt KHÔNG đổi")


def test_f15_he_so_tu_hoc_khong_co_khoa_config():
    """F-15 (ghi chú, không phải lỗi renderer): prompt nói "tự học mất gấp đôi số tick"
    nhưng ×2 là HẰNG TRONG ENGINE (`engine/education.py`), không có khóa config ⇒ property
    test ở trên KHÔNG thể phủ nó. Test này ghi nhận sự thật đó để nó không bị quên."""
    src = Path("engine/education.py").read_text(encoding="utf-8")
    assert "if a.hoc_tu_hoc else 1" in src, (
        "hệ số tự-học đã đổi hình dạng — kiểm tra lại xem nó đã thành config chưa "
        "(nếu rồi: thêm khóa đó vào KHOA_BASE và xóa test này)")
    cfg = load_config()
    with pytest.raises(KeyError):
        cfg.get("giao_duc.he_so_tu_hoc")


# ============================================================ 4. Prompt thật (đầu-cuối)
def test_build_agent_prompt_dung_calendar_cua_config(w_base, w_spatial):
    """Câu mở đầu prompt 1-to-1 cũng phải đọc config (không hardcode '6 tháng')."""
    ab = sorted(a for a, ag in w_base.agents.items() if ag.con_song)[0]
    as_ = sorted(a for a, ag in w_spatial.agents.items() if ag.con_song)[0]
    pb = build_agent_prompt(w_base, ab, {ab: ["dinh_ky"]})
    ps = build_agent_prompt(w_spatial, as_, {as_: ["dinh_ky"]})
    assert "(1 tick = 6 tháng)" in pb
    assert "(1 tick = 4 tháng)" in ps
    assert "(1 tick = 6 tháng)" not in ps
