"""CAP-1..5 — capability registry parity (ADR 0006 §A.3, test matrix §6).

Bộ test ĐỘC LẬP (test-engineer), viết sau khi đọc `minds/capabilities.py` nhưng KHÔNG tái
dùng helper của người implement. Mục tiêu là tìm chỗ interface SAI/THIẾU, không hợp thức hóa
implementation.

Năm bất biến bị cưỡng chế ở đây:

- **CAP-1 (bốn chân đủ):** descriptor `cong_khai` ⇒ có tên trong `LOAI_HANH_DONG`,
  `engine_handler` import được, `mau_prompt(w)` render được, và dịch được HAI CHIỀU
  (`to_kehoach`/`from_kehoach`) trên một `KeHoach` phủ MỌI field action.
- **CAP-2 (không field mồ côi):** mọi field của `engine.intents.KeHoach` hoặc được khai báo
  bởi một descriptor, hoặc nằm trong `FIELD_KHONG_PHAI_ACTION`. Test *chống rỗng*
  (`test_cap2_them_field_gia_thi_test_phai_do`) chứng minh assertion này KHÔNG vacuous.
- **CAP-3 (không quảng cáo hàng không có):** menu ⟺ `kha_dung(w)`, HAI CHIỀU, đo trên base
  VÀ overlay spatial.
- **CAP-4 (anti-teleology):** mọi text render từ catalog qua bộ chặn từ-mớm + tên-định-chế +
  nhãn-giai-cấp. Kèm guard chống NỚI bộ chặn của `tests/test_prompt_ky_luat.py`.
- **CAP-5 (không quảng cáo mà giấu kinh tế học):** xem khối CAP-5 ở cuối file. Đây là lưới
  cho LỚP defect `duc_xu` (menu chào `mon:"xu"` mà prompt chưa bao giờ nói đúc xu tốn gì /
  ra bao nhiêu ⇒ mọi kết luận "agent không đúc tiền" từ những run đó đều interface-confounded).

Không mạng, không LLM: chỉ dựng World từ config và render text.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import pytest

from engine.config import Config, load_config
from engine.contracts import (
    ClauseChuyenGiaoDinhKy,
    ClauseChuyenGiaoMotLan,
    ClauseGopCong,
    HopDong,
)
from engine.intents import KeHoach
from engine.market import Lenh
from engine.world import tao_the_gioi
from minds import capabilities as cap
from minds.capabilities import (
    CATALOG,
    FIELD_KHONG_PHAI_ACTION,
    cac_ten_cong_khai,
    catalog_hash,
    handler_ton_tai,
    hanh_dong_tu_ke_hoach,
    kha_dung_trong,
    mon_recipe_khong_co_duong_che,
    tai_san_giao_dich,
)
from minds.prompts import (
    build_agent_prompt,
    build_user_chung,
    luat_vat_ly,
    muc_hanh_dong,
    schema_quyet_dinh_cho,
)
from minds.repair import parse_batch
from minds.schemas import LOAI_HANH_DONG
from minds.translate import ke_hoach_thanh_quyet_dinh, quyet_dinh_thanh_ke_hoach

SPATIAL = Path("scenarios/agrarian_transition_v1/spatial_v1.yaml").resolve()
LIVELIHOOD = Path("scenarios/agrarian_transition_v1/spatial_livelihood_v2.yaml").resolve()

# Sáu action chỉ tồn tại khi overlay không-gian BẬT (F-02/F-03: ba cái đầu từng MỒ CÔI —
# engine chạy được, LLM không gọi nổi tên).
ACTION_CHI_CO_O_SPATIAL = ("dong_thuyen", "rao_do", "qua_song", "khai_hoang",
                           "canh_vu_dong", "cham_tre")

# Bộ chặn CAP-4 — bản SAO ĐỘC LẬP (nới bộ chặn ở test_prompt_ky_luat.py KHÔNG nới cái này).
TU_MOM = ("nên ", "hãy", "khôn ngoan", "đáng")
TU_XEP_HANG = ("tốt hơn", "tốt nhất", "lợi nhất", "có lợi", "khuyến nghị", "ưu tiên",
               "hiệu quả nhất", "sinh lời", "nên chọn", "đáng làm", "tối đa hóa")
TEN_DINH_CHE_CAM = ("ngân hàng", "công ty", "bảo hiểm", "xưởng")
# Nhãn giai cấp là sản phẩm của observatory (Lớp-5). Chúng KHÔNG được rò vào interface Lớp-4.
NHAN_GIAI_CAP_CAM = ("địa chủ", "tá điền", "phú nông", "cố nông", "trung nông",
                     "thương nhân", "thợ thủ công", "công nhân", "vô gia cư")


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def w_base():
    return tao_the_gioi(load_config(), 11, events_path=None)


@pytest.fixture(scope="module")
def w_spatial():
    assert SPATIAL.exists(), f"thiếu overlay spatial: {SPATIAL}"
    return tao_the_gioi(load_config(overlays=[SPATIAL]), 11, events_path=None)


@pytest.fixture(scope="module")
def w_livelihood():
    """Scenario versioned P1/P2: spatial base plus household/ecology overlay."""
    assert LIVELIHOOD.exists(), f"thiếu overlay livelihood: {LIVELIHOOD}"
    return tao_the_gioi(load_config(overlays=[SPATIAL, LIVELIHOOD]), 11, events_path=None)


# --------------------------------------------------------------------------- CAP-2
def _field_mo_coi(cac_field: list[str]) -> list[str]:
    """Field KeHoach không được descriptor nào khai báo và cũng không ở allowlist."""
    da_khai_bao: set[str] = set()
    for c in CATALOG:
        da_khai_bao.update(c.kehoach_field)
    return sorted(f for f in cac_field
                  if f not in da_khai_bao and f not in FIELD_KHONG_PHAI_ACTION)


def test_cap2_khong_co_field_kehoach_mo_coi():
    """Mọi field của KeHoach phải được khai báo — đây chính là test lẽ ra đã bắt F-02."""
    ten = [f.name for f in dataclasses.fields(KeHoach)]
    assert _field_mo_coi(ten) == [], (
        "field KeHoach không có đường LLM và cũng không ở FIELD_KHONG_PHAI_ACTION: "
        f"{_field_mo_coi(ten)}"
    )


def test_cap2_them_field_gia_thi_test_phai_do():
    """CHỐNG VACUOUS: thêm một field vào KeHoach mà quên khai báo ⇒ CAP-2 phải ĐỎ.

    Nếu test này pass (tức `_field_mo_coi` KHÔNG bắt được field giả), thì
    `test_cap2_khong_co_field_kehoach_mo_coi` là một assertion rỗng.
    """

    @dataclasses.dataclass
    class _KeHoachCoFieldMoi(KeHoach):
        thue_may_bay: int = 0  # field mới, không descriptor nào khai báo

    ten = [f.name for f in dataclasses.fields(_KeHoachCoFieldMoi)]
    assert _field_mo_coi(ten) == ["thue_may_bay"], (
        "CAP-2 KHÔNG phát hiện được field mồ côi ⇒ test CAP-2 là vacuous"
    )


def test_cap2_khong_khai_bao_field_khong_ton_tai():
    """Chiều ngược: descriptor không được trỏ tới field KeHoach không tồn tại."""
    co_that = {f.name for f in dataclasses.fields(KeHoach)}
    # `bao_huy` là field thật (engine/intents.py:35) — nếu ai đó xóa nó, test phải đỏ.
    thieu = sorted({f for c in CATALOG for f in c.kehoach_field} - co_that)
    assert thieu == [], f"descriptor khai báo field KeHoach không tồn tại: {thieu}"


def test_cap2_allowlist_co_ly_do():
    """Mỗi mục FIELD_KHONG_PHAI_ACTION phải kèm LÝ DO (không phải cửa sau im lặng)."""
    for ten, ly_do in FIELD_KHONG_PHAI_ACTION.items():
        assert isinstance(ly_do, str) and len(ly_do.strip()) >= 20, (
            f"allowlist '{ten}' thiếu lý do tường minh"
        )


# --------------------------------------------------------------------------- CAP-1
def test_cap1_ten_cong_khai_khop_loai_hanh_dong():
    assert LOAI_HANH_DONG == frozenset(c.ten for c in CATALOG if c.cong_khai)
    assert len({c.ten for c in CATALOG}) == len(CATALOG), "tên action trùng trong CATALOG"


def test_cap1_engine_handler_import_duoc():
    """Mọi handler engine phải tồn tại BẰNG TÊN (không import ngược minds)."""
    thieu = [(c.ten, h) for c in CATALOG if c.cong_khai
             for h in c.engine_handler if not handler_ton_tai(h)]
    assert thieu == [], f"engine_handler không import được: {thieu}"


def test_cap1_mau_prompt_render_duoc(w_base, w_spatial, w_livelihood):
    """`mau_prompt(w)` render được ở CHÍNH thế giới action đó khả dụng."""
    loi: list[str] = []
    for c in CATALOG:
        for ten_w, w in (("base", w_base), ("spatial", w_spatial),
                         ("livelihood", w_livelihood)):
            if not c.kha_dung(w):
                continue
            try:
                s = c.mau_prompt(w)
            except Exception as e:  # noqa: BLE001 — báo cáo mọi lỗi render
                loi.append(f"{c.ten}@{ten_w}: {type(e).__name__}: {e}")
                continue
            if not s.strip():
                loi.append(f"{c.ten}@{ten_w}: dòng menu RỖNG")
            if f'"{c.ten}"' not in s:
                loi.append(f"{c.ten}@{ten_w}: dòng menu không nêu tên action")
    assert loi == [], f"mau_prompt hỏng: {loi}"


def test_cap1_ma_ket_qua_khong_rong():
    """Mỗi action phải khai báo tập outcome code (engine/metrics/feedback dùng)."""
    thieu = [c.ten for c in CATALOG if c.cong_khai and not c.ma_ket_qua]
    assert thieu == [], f"action thiếu ma_ket_qua: {thieu}"
    khong_ok = [c.ten for c in CATALOG if c.cong_khai and "ok" not in c.ma_ket_qua]
    assert khong_ok == [], f"ma_ket_qua thiếu 'ok': {khong_ok}"


# --------------------------------------------------------------------------- CAP-1 roundtrip
def _hop_dong_mau(tu: str, den: str) -> HopDong:
    return HopDong(
        cac_ben=[tu, den], hinh_thuc="mieng", thoi_han=8,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(tu=tu, den=den, tai_san="thoc",
                                   so_luong=100.0, tai="ky_ket"),
            ClauseGopCong(tu=den, den=tu, so_cong_moi_tick=60.0),
            ClauseChuyenGiaoDinhKy(tu=tu, den=den, tai_san="thoc",
                                   so_luong=120.0, moi_n_tick=1),
        ], nguoi_soan=tu,
    )


def _ke_hoach_phu_moi_action(w, aid: str) -> KeHoach:
    """KeHoach set MỌI field action — kể cả `dong_thuyen`/`rao_do`/`qua_song`/`khai_hoang`/
    `canh_vu_dong`/`cham_tre_cho` và 8 field chính trị.

    `tests/test_translate_roundtrip.py::_ke_hoach_du_truong` KHÔNG set 14 field này ⇒ nó
    pass GIẢ cho chúng (mọi field default rỗng thì roundtrip luôn bằng nhau). Đây là lý do
    F-02 sống sót suốt: bộ test cũ không exercise field mồ côi.
    """
    eid = "E0001"
    kh = KeHoach(id=aid)
    # phan_bo_cong
    kh.canh_thua = ["P01_01", "P01_02"]
    kh.gop_cong_cho = "A0002"
    kh.cong_khai_go = 30.0
    kh.cong_khai_quang = 12.0
    kh.hoc = True
    kh.day_cho = ["A0003"]
    # xay
    kh.che_tao_cong_cu = 2
    kh.xay_nha = 1
    kh.xay_may = 1
    kh.duc_xu = 1
    w.ten_hang["vai_1"] = "Vải thử"
    kh.che_hang = {"vai_1": 3}
    # nghien_cuu / lap_phap_nhan / quyet_dinh_entity
    kh.nghien_cuu = ("nong_nghiep", 60.0, 100.0)
    kh.lap_phap_nhan = {"ten": "Trại thử",
                        "co_phan": {"A0001": 60.0, "A0002": 40.0},
                        "von_gop": {"A0001": {"thoc": 200.0}}}
    kh_con = KeHoach(id=eid)
    kh_con.canh_thua = ["P05_05"]
    kh_con.dat_lenh = [Lenh(eid, "ban", "cong_cu", 1.0, 100.0)]
    kh.quyet_dinh_entity = [(eid, kh_con)]
    # di chúc / di cư
    kh.viet_di_chuc = {"phan_bo": {"A0003": 100.0}, "gia_huan": "Giữ đất hương hỏa."}
    kh.di_cu = True
    # household / estate: action phải có roundtrip giống mọi intent khác; engine có handler
    # nhưng không có đường schema/catalog sẽ làm CAP-1 đỏ ngay tại đây.
    kh.tach_ho = True
    kh.yeu_cau_di_san = ["DI_SAN:A0001"]
    # v5 settlement entry: ranked public residential-lot request
    kh.chon_dat_o = ["O0001", "O0002", "O0003"]
    # ---- KHÔNG GIAN: 3 action từng mồ côi (F-02) + khai hoang (F-03) + vụ đông + chăm trẻ
    kh.dong_thuyen = 2
    kh.rao_do = (5.0, "thoc")
    kh.qua_song = ("hoang", "thoc", 6.5)
    kh.khai_hoang = ["P05_06"]
    kh.trong_rung = ["P05_08"]
    kh.canh_vu_dong = [("P05_07", "ngo")]
    kh.cham_tre_cho = ["A0004"]
    # chăn nuôi / biếu / sinh kế
    kh.bat_ga_cong = 20.0
    kh.giet_ga = 2
    kh.bieu = [("A0002", "thoc", 50.0)]
    kh.danh_ca_cong = 30.0
    kh.mo_tiec = (100.0, 8.0)
    kh.trom = ("A0009", "thoc", 40.0)
    kh.nhan_tin = [("A0002", "để lại cho tôi ít gỗ nhé")]
    # hợp đồng
    kh.de_nghi_hop_dong = [(_hop_dong_mau(aid, "A0002"), "A0002")]
    kh.tra_loi_de_nghi = {"DN0001": "chap_nhan",
                          "DN0002": _hop_dong_mau("A0004", aid)}
    kh.don_phuong_pha_vo = ["HD00001"]
    kh.bao_huy = ["HD00003"]
    # chợ + đất
    kh.dat_lenh = [Lenh(aid, "mua", "go", 5.0, 12.0),
                   Lenh(aid, "ban", "ga", 2.0, 40.0, "thoc", lang=1)]
    kh.niem_yet_dat = [("P02_02", 600.0)]
    kh.tra_gia_dat = [("P03_03", 500.0)]
    kh.yeu_cau_rut = {"HD00002": 20.0}
    # versioned quote/escrow commerce
    kh.dang_bao_gia = [{"chieu": "ban", "tai_san": "go", "so_luong": 4.0,
                         "don_gia": 12.0, "thanh_toan": "thoc", "doi_tac": None,
                         "het_han_tick": None, "giao_tai": "ngay"}]
    kh.chap_nhan_bao_gia = [{"ref": "BG00001", "so_luong": 2.0}]
    kh.huy_bao_gia = ["BG00002"]
    # generic work order: all four public routes must survive JSON round-trip
    kh.tao_du_an = [{"loai_du_an": "nha", "thua": "P02_02"}]
    kh.gop_vat_lieu_du_an = [{"ref": "DA00001", "tai_san": "go", "so_luong": 10.0}]
    kh.gop_cong_du_an = [{"ref": "DA00001", "so_cong": 20.0}]
    kh.huy_du_an = ["DA00002"]
    # hôn nhân
    kh.cau_hon = "A0005"
    kh.tra_loi_cau_hon = {"A0006": True}
    # ---- CHÍNH TRỊ (8 ý định) ----
    kh.ung_cu = True
    kh.bo_phieu = "A0002"
    kh.ban_hanh_luat = {"loai": "thue", "suat": 0.1}
    kh.hoi_lo = ("A0003", 100.0)
    kh.gia_nhap_nghiep_doan = True
    kh.dinh_cong = True
    kh.bao_dong = True
    kh.keu_goi = "Cùng nhau giữ đất công."
    return kh


def test_cap1_roundtrip_phu_MOI_action_cong_khai(w_spatial):
    """MỌI action `cong_khai` phải được EXERCISE trong một roundtrip thật, không chỉ default.

    Đây là test lẽ ra đã bắt F-02 ngay từ đầu: `dong_thuyen`/`rao_do`/`qua_song` có field
    engine + executor nhưng không có đường schema/translate ⇒ roundtrip sẽ mất chúng.
    """
    w = w_spatial
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    kh_goc = _ke_hoach_phu_moi_action(w, aid)

    qd_dict = ke_hoach_thanh_quyet_dinh(kh_goc, ly_do="roundtrip đủ action")
    phat_ra = {hd["loai"] for hd in qd_dict["hanh_dong"]}
    thieu = sorted(frozenset(c.ten for c in CATALOG if c.cong_khai) - phat_ra)
    assert thieu == [], (
        "action KHÔNG được exercise trong roundtrip (from_kehoach im lặng nuốt field, "
        f"hoặc field chưa được set trong fixture): {thieu}"
    )

    ok, hong = parse_batch(json.dumps([qd_dict], ensure_ascii=False), [aid])
    assert not hong, f"schema từ chối JSON do chính catalog phát ra: {hong}"
    thung: list = []
    kh_lai = quyet_dinh_thanh_ke_hoach(w, ok[aid], thung)
    assert thung == [], f"intent rơi thùng lạ trên đường về: {thung}"

    for f in dataclasses.fields(KeHoach):
        if f.name in FIELD_KHONG_PHAI_ACTION:
            continue
        assert getattr(kh_lai, f.name) == getattr(kh_goc, f.name), (
            f"field {f.name} LỆCH sau roundtrip:\n"
            f"  gốc: {getattr(kh_goc, f.name)!r}\n  lại: {getattr(kh_lai, f.name)!r}"
        )
    # buôn chuyến giữ đúng làng đích (wire contract của chợ)
    assert any(le.lang == 1 for le in kh_lai.dat_lenh), "Lenh.lang mất chiều xuôi"


def test_ba_action_mo_coi_co_shape_dung_engine(w_spatial):
    """Shape tham số phải khớp ĐÚNG cái `engine/spatial.py::buoc_qua_song` đọc."""
    w = w_spatial
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    kh = KeHoach(id=aid)
    kh.dong_thuyen = 1
    kh.rao_do = (5.0, "thoc")
    kh.qua_song = ("hoang", "thoc", 6.5)
    hd = {h["loai"]: h for h in hanh_dong_tu_ke_hoach(kh)}
    assert hd["dong_thuyen"] == {"loai": "dong_thuyen", "so_luong": 1}
    assert hd["rao_do"] == {"loai": "rao_do", "phi": 5.0, "tai_san": "thoc"}
    assert hd["qua_song"] == {"loai": "qua_song", "den_bo": "hoang", "tai_san": "thoc",
                              "phi_chap_nhan": 6.5}


def test_qua_song_bo_la_roi_thung_khong_raise(w_spatial):
    """Điều luật #3: tham số LLM sai (bờ không tồn tại) → thùng intent lạ, KHÔNG raise."""
    from minds.schemas import HanhDong, QuyetDinh

    w = w_spatial
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[
        HanhDong(loai="qua_song", den_bo="mat_trang", tai_san="thoc", phi_chap_nhan=1)])
    thung: list = []
    kh = quyet_dinh_thanh_ke_hoach(w, qd, thung)
    assert kh.qua_song is None
    assert thung and "mat_trang" in thung[0][2]


# --------------------------------------------------------------------------- CAP-3
def _menu_ten(w) -> set[str]:
    """Tên action THẬT SỰ xuất hiện trong menu render (parse từ text, không tin cấu trúc)."""
    ten: set[str] = set()
    text = "\n".join(muc_hanh_dong(w))
    for c in CATALOG:
        if f'"loai":"{c.ten}"' in text:
            ten.add(c.ten)
    return ten


@pytest.mark.parametrize("ten_cfg", ["base", "spatial", "livelihood"])
def test_cap3_menu_bang_kha_dung_hai_chieu(ten_cfg, w_base, w_spatial, w_livelihood):
    w = {"base": w_base, "spatial": w_spatial, "livelihood": w_livelihood}[ten_cfg]
    kha_dung = {c.ten for c in kha_dung_trong(w)}
    menu = _menu_ten(w)
    assert menu - kha_dung == set(), (
        f"[{ten_cfg}] menu QUẢNG CÁO action không khả dụng: {sorted(menu - kha_dung)}")
    assert kha_dung - menu == set(), (
        f"[{ten_cfg}] action khả dụng nhưng KHÔNG có trong menu (agent không biết nó tồn "
        f"tại): {sorted(kha_dung - menu)}")
    assert len(menu) == len(muc_hanh_dong(w)), "menu có dòng không nêu tên action nào"


def test_cap3_action_khong_gian_chi_hien_khi_overlay_bat(w_base, w_spatial):
    menu_base, menu_spatial = _menu_ten(w_base), _menu_ten(w_spatial)
    for ten in ACTION_CHI_CO_O_SPATIAL:
        assert ten in menu_spatial, f"overlay spatial BẬT nhưng menu thiếu '{ten}'"
        assert ten not in menu_base, f"base KHÔNG có cơ chế '{ten}' mà menu vẫn quảng cáo"
    # phần còn lại phải giống nhau — overlay chỉ THÊM, không âm thầm bớt action
    assert menu_spatial - menu_base == set(ACTION_CHI_CO_O_SPATIAL)
    assert menu_base - menu_spatial == set(), (
        f"overlay spatial làm MẤT action: {sorted(menu_base - menu_spatial)}")


def test_cap3_trong_rung_chi_hien_o_scenario_ecology_v2(w_spatial, w_livelihood):
    """Không quảng cáo tái sinh rừng trong control spatial_v1 chưa có stock rừng."""
    assert "trong_rung" not in _menu_ten(w_spatial)
    assert "trong_rung" in _menu_ten(w_livelihood)


def test_cap3_kha_dung_khong_phu_thuoc_trang_thai_agent(w_spatial):
    """`kha_dung` là cổng SCENARIO, không phải cổng năng lực cá nhân: nó không được đọc
    trạng thái một agent cụ thể (nếu không, menu sẽ tiết lộ 'bạn không đủ điều kiện' =
    mớm ý). Chứng minh: menu bất biến khi thế giới đổi tick."""
    truoc = _menu_ten(w_spatial)
    w_spatial.tick += 3
    try:
        assert _menu_ten(w_spatial) == truoc
    finally:
        w_spatial.tick -= 3


# --------------------------------------------------------------------------- CAP-4
def _moi_text_catalog(w) -> str:
    phan = [c.mau_prompt(w) for c in kha_dung_trong(w)]
    phan += [c.ten for c in CATALOG]
    phan += [m for c in CATALOG for m in c.ma_ket_qua]
    phan.append(luat_vat_ly(w))
    return "\n".join(phan)


@pytest.mark.parametrize("ten_cfg", ["base", "spatial"])
def test_cap4_text_catalog_khong_mom_khong_xep_hang(ten_cfg, w_base, w_spatial):
    w = w_base if ten_cfg == "base" else w_spatial
    thap = _moi_text_catalog(w).lower()
    for tu in TU_MOM:
        assert tu not in thap, f"[{ten_cfg}] catalog lộ từ mớm ý: {tu!r}"
    for tu in TU_XEP_HANG:
        assert tu not in thap, f"[{ten_cfg}] catalog XẾP HẠNG sinh kế: {tu!r}"
    for ten in TEN_DINH_CHE_CAM:
        assert ten not in thap, f"[{ten_cfg}] catalog lộ tên định chế: {ten!r}"
    for nhan in NHAN_GIAI_CAP_CAM:
        assert nhan not in thap, (
            f"[{ten_cfg}] nhãn giai cấp (Lớp-5) rò vào interface Lớp-4: {nhan!r}")


def test_cap4_prompt_that_cung_sach(w_spatial):
    """Prompt 1-to-1 THẬT (đã ghép menu + xáo) cũng phải qua bộ chặn."""
    aid = sorted(a for a, ag in w_spatial.agents.items() if ag.con_song)[0]
    thap = build_agent_prompt(w_spatial, aid, {aid: ["dinh_ky"]}).lower()
    for tu in (*TU_MOM, *TU_XEP_HANG, *TEN_DINH_CHE_CAM):
        assert tu not in thap, f"prompt spatial lộ: {tu!r}"


def test_bo_chan_prompt_ky_luat_khong_bi_noi_long():
    """GUARD chống nới test: `tests/test_prompt_ky_luat.py` phải giữ nguyên bộ chặn gốc
    (git HEAD). Nới nó = làm rỗng cổng anti-teleology ⇒ test này đỏ."""
    from tests import test_prompt_ky_luat as pkl

    assert tuple(pkl.TU_MOM) == ("nên ", "hãy", "khôn ngoan", "đáng")
    assert tuple(pkl.TEN_DINH_CHE_CAM) == ("ngân hàng", "công ty", "bảo hiểm", "xưởng")
    assert tuple(pkl.Y_DINH_CHINH_TRI) == (
        "ung_cu", "bo_phieu", "ban_hanh_luat", "hoi_lo",
        "nghiep_doan", "dinh_cong", "bao_dong", "keu_goi")


# --------------------------------------------------------------------------- catalog_hash
def test_catalog_hash_bat_bien_khi_reorder(monkeypatch):
    goc = catalog_hash()
    monkeypatch.setattr(cap, "CATALOG", tuple(reversed(CATALOG)))
    assert catalog_hash() == goc, "reorder file KHÔNG được đổi catalog_hash (refactor thuần)"


def test_catalog_hash_bat_bien_khi_doi_ham(monkeypatch):
    """Đổi implementation `to_kehoach` (không đổi interface) ⇒ hash GIỮ NGUYÊN."""
    goc = catalog_hash()
    moi = tuple(
        dataclasses.replace(c, to_kehoach=lambda w, kh, d, t: None) if c.ten == "di_cu" else c
        for c in CATALOG
    )
    monkeypatch.setattr(cap, "CATALOG", moi)
    assert catalog_hash() == goc


@pytest.mark.parametrize("cach", ["mau_prompt", "schema_fields", "bot_action",
                                  "kha_dung_key", "ma_ket_qua", "thu_tu_phat"])
def test_catalog_hash_doi_khi_doi_interface(cach, monkeypatch):
    goc = catalog_hash()
    if cach == "bot_action":
        moi = tuple(c for c in CATALOG if c.ten != "qua_song")
    else:
        def _sua(c):
            if c.ten != "qua_song":
                return c
            if cach == "mau_prompt":
                return dataclasses.replace(c, mau_prompt_template=c.mau_prompt_template + " .")
            if cach == "schema_fields":
                return dataclasses.replace(
                    c, schema_fields=(*c.schema_fields, ("moi", "int")))
            if cach == "kha_dung_key":
                return dataclasses.replace(c, kha_dung_key=c.kha_dung_key + "+x")
            if cach == "ma_ket_qua":
                return dataclasses.replace(c, ma_ket_qua=(*c.ma_ket_qua, "ma_moi"))
            return dataclasses.replace(c, thu_tu_phat=c.thu_tu_phat + 1)

        moi = tuple(_sua(c) for c in CATALOG)
    monkeypatch.setattr(cap, "CATALOG", moi)
    assert catalog_hash() != goc, f"đổi interface ({cach}) mà catalog_hash KHÔNG đổi"


def test_catalog_hash_khong_bam_file():
    """Hash băm NỘI DUNG KHAI BÁO — không phải sha256 file (đổi docstring không đổi hash)."""
    import hashlib

    blob = Path(cap.__file__).read_bytes()
    assert catalog_hash() != hashlib.sha256(blob).hexdigest()
    assert len(catalog_hash()) == 64


# --------------------------------------------------------------------------- no-mutation
@pytest.mark.parametrize("ten_cfg", ["base", "spatial"])
def test_render_catalog_khong_mutate_world_hash(ten_cfg, w_base, w_spatial):
    """ADR 0006 §A.2: render/serialize catalog + prompt là CHỈ ĐỌC (khuôn ADR 0002 §A.1)."""
    w = w_base if ten_cfg == "base" else w_spatial
    h0 = w.world_hash()
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    muc_hanh_dong(w)
    luat_vat_ly(w)
    tai_san_giao_dich(w)
    catalog_hash()
    build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    assert w.world_hash() == h0, "render prompt/catalog ĐÃ MUTATE world state"


# ============================================================================= CAP-5
# "Không quảng cáo mà giấu kinh tế học" (minds/capabilities.py:21-30).
#
# BỐI CẢNH (N-02, adversarial-reviewer vòng 2): `mon_recipe_khong_co_duong_che()` được viết
# làm "hook cho test CAP-5" nhưng KHÔNG có caller nào — lớp defect `duc_xu` vẫn không có lưới.
# Khối dưới đây là lưới đó, gồm ba tầng:
#
#   (a) MÓN của `xay` — mọi `mon` menu chào phải kèm chi phí đầu vào + sản phẩm đầu ra, số
#       đọc từ CONFIG ĐANG CHẠY (đổi config ⇒ menu đổi). Có test CHỐNG VACUOUS ở cả hai
#       hướng: thêm món giả vào config ⇒ đỏ; giấu kinh tế học của `xu` ⇒ đỏ.
#   (b) MỌI action `cong_khai` — tham số kinh tế học của action (chi phí đầu vào / lượng sản
#       phẩm đầu ra / cổng khả thi định lượng mà ENGINE cưỡng chế) phải hiện trên BỀ MẶT
#       LUẬT mà mọi agent đọc (`schema_quyet_dinh_cho` + `luat_vat_ly` + `build_user_chung`).
#       Đo bằng ĐỘT BIẾN, không bằng so chuỗi: đổi giá trị config ⇒ bề mặt PHẢI đổi. Cách này
#       không phụ thuộc câu chữ và không thể vacuous (số nhỏ như "8" xuất hiện khắp nơi nên
#       kiểm `"8" in prompt` là rỗng nghĩa).
#   (c) CAP-4 trùm CAP-5 — text kinh tế học mới thuần dữ kiện, không xếp hạng/mớm ý.
#
# GIỚI HẠN ĐÃ BIẾT (không tự tổng quát hóa được, ghi rõ theo yêu cầu):
#   1. Bảng `THAM_SO_KINH_TE` là bảng CỦA TEST, không suy ra tự động được từ code: production
#      không khai báo cạnh action→khóa-config (mỗi `mau_prompt_gia_tri` là một closure đục).
#      ⇒ THÊM MỘT KHÓA CONFIG MỚI cho action CŨ vẫn lọt lưới. Lưới chỉ tự đóng cho (i) action
#      mới (test `..._bang_tham_so_phu_moi_action_cong_khai` bắt buộc phân loại) và (ii) món
#      `xay`/recipe mới (hook + parse menu).
#   2. Tham số PHÂN PHỐI kết quả (research `xac_suat_thanh_cong.k0`/`.d`, độ lớn blueprint,
#      thời tiết) KHÔNG bị khẳng định ở đây: prompt cố ý nói "kết quả rút từ phân phối". Cả hai
#      đều KHÔNG hiện trên bề mặt luật (đã đo) — nhưng có công bố hay không là quyết định của
#      spec-governor, không phải của test. Ghi lại ở `THAM_SO_PHAN_PHOI_KHONG_KHANG_DINH`.
#   3. Ngưỡng ">50% cổ phần" của `quyet_dinh_entity` nằm TRONG CODE (không phải config) nên
#      ngoài tầm CAP-5 ("đọc từ config đang chạy"); nó là vi phạm "không magic number" khác.

# --- bảng ĐỘC LẬP của test (KHÔNG import MON_XAY/MON_NGOAI_XAY/NHAN_NGUYEN_LIEU) ---------
# món `xay` → đường dẫn config chứa công thức của nó
DUONG_DAN_RECIPE: dict[str, str] = {
    "cong_cu": "san_xuat.recipe.cong_cu",
    "nha": "san_xuat.recipe.nha",
    "xu": "san_xuat.recipe.xu",
    "may": "research.may.recipe",
}
# món CÓ recipe trong `san_xuat.recipe` nhưng đi qua action RIÊNG (không phải `xay`)
MON_QUA_ACTION_KHAC: dict[str, str] = {"thuyen": "dong_thuyen"}
# khóa recipe không phải nguyên liệu đầu vào
KHOA_KHONG_PHAI_NGUYEN_LIEU = frozenset({"ra", "tang_nang_suat", "hao_mon_moi_tick_dung"})
PLACEHOLDER_HANG_MOI = "<mã hàng mới>"
# nơi agent đọc được công thức của hàng do blueprint đẻ ra (minds/prompts.build_user_rieng)
KHOI_BI_QUYET = "BÍ QUYẾT BẠN NẮM"


def _so(x: Any) -> str:
    """Bản sao ĐỘC LẬP của `capabilities.so` — test không mượn formatter của production."""
    return f"{float(x):g}"


def _lay(raw: dict, path: str) -> Any:
    node: Any = raw
    for k in path.split("."):
        if not isinstance(node, dict) or k not in node:
            return None
        node = node[k]
    return node


def _dat(raw: dict, path: str, val: Any) -> None:
    node = raw
    khoa = path.split(".")
    for k in khoa[:-1]:
        node = node[k]
    node[khoa[-1]] = val


def _the_gioi(sua=None, spatial: bool = False, livelihood: bool = False):
    """World MỚI từ config (đã sửa) — mỗi test đột biến dựng thế giới riêng, không đụng fixture."""
    overlays = [SPATIAL] if spatial or livelihood else None
    if livelihood:
        assert LIVELIHOOD.exists(), f"thiếu overlay livelihood: {LIVELIHOOD}"
        overlays = [SPATIAL, LIVELIHOOD]
    cfg = load_config(overlays=overlays)
    raw = copy.deepcopy(cfg.raw())
    if sua is not None:
        sua(raw)
    return tao_the_gioi(Config(raw), 11, events_path=None)


def _be_mat_luat(w) -> str:
    """BỀ MẶT LUẬT: đúng những gì MỌI agent đọc được về luật chơi (không gồm khối riêng tư,
    vốn là TRẠNG THÁI chứ không phải công bố luật)."""
    return schema_quyet_dinh_cho(w) + "\n" + luat_vat_ly(w) + "\n" + build_user_chung(w)


def _dong_menu(w, ten: str) -> str:
    dong = [d for d in muc_hanh_dong(w) if f'"loai":"{ten}"' in d]
    assert len(dong) == 1, f"menu phải có ĐÚNG một dòng cho '{ten}', thấy {len(dong)}"
    return dong[0]


def _mon_quang_cao(dong_xay: str) -> list[str]:
    """Các `mon` menu CHÀO — parse từ chính text, không hỏi production."""
    m = re.search(r'"mon":(.+?),"so_luong"', dong_xay)
    assert m, f"dòng `xay` không có trường mon: {dong_xay!r}"
    return [t.strip().strip('"') for t in m.group(1).split("|")]


def _recipe_mo_coi(w) -> tuple[str, ...]:
    """Món có công thức trong config mà KHÔNG action nào chế được (bảng của TEST)."""
    r = _lay(w.cfg.raw(), "san_xuat.recipe") or {}
    return tuple(sorted(m for m in r
                        if m not in DUONG_DAN_RECIPE and m not in MON_QUA_ACTION_KHAC))


def _vi_pham_cap5_xay(w) -> list[str]:
    """Món `xay` bị quảng cáo mà KHÔNG công bố (chi phí đầu vào → sản phẩm đầu ra)."""
    dong = _dong_menu(w, "xay")
    quang_cao = _mon_quang_cao(dong)
    loi: list[str] = []
    for mon in quang_cao:
        if mon == PLACEHOLDER_HANG_MOI:
            if KHOI_BI_QUYET not in dong:
                loi.append(f"{mon}: chào hàng-mới mà không chỉ nơi agent đọc được công thức")
            continue
        if mon in DUONG_DAN_RECIPE:
            r = _lay(w.cfg.raw(), DUONG_DAN_RECIPE[mon])
            if not isinstance(r, dict) or not r:
                loi.append(f"{mon}: menu chào nhưng config không có công thức")
                continue
            m = re.search(rf"(?<![\w<]){re.escape(mon)}: ([^;]+?) → ([\d.]+) "
                          rf"{re.escape(mon)}\b", dong)
            if m is None:
                loi.append(f"{mon}: menu KHÔNG nêu 'chi phí đầu vào → sản phẩm đầu ra'")
                continue
            ra_cfg = _so(r.get("ra", 1))
            if m.group(2) != ra_cfg:
                loi.append(f"{mon}: sản phẩm đầu ra nêu {m.group(2)}, config nói {ra_cfg}")
            nl = {k: v for k, v in r.items() if k not in KHOA_KHONG_PHAI_NGUYEN_LIEU}
            hang = [t.strip() for t in m.group(1).split(" + ") if t.strip()]
            if len(hang) != len(nl):
                loi.append(f"{mon}: nêu {len(hang)} nguyên liệu, config có {len(nl)} "
                           f"({sorted(nl)}) — có thứ bị nuốt")
                continue
            neu = sorted(t.split(" ", 1)[0] for t in hang)
            cfg_so = sorted(_so(v) for v in nl.values())
            if neu != cfg_so:
                loi.append(f"{mon}: số lượng nguyên liệu nêu {neu} ≠ config {cfg_so}")
            continue
        # còn lại: phải là BÍ DANH và phải dẫn chiếu về một món đã công bố
        m = re.search(rf"(?<![\w<]){re.escape(mon)}: ([^;]+)", dong)
        if m is None or not any(g in m.group(1) for g in DUONG_DAN_RECIPE):
            loi.append(f"{mon}: món được chào mà KHÔNG có kinh tế học lẫn dẫn chiếu")
    # chiều ngược: chế được trong thế giới này ⇒ phải được chào (CAP-3 ở cấp MÓN)
    for mon, dd in DUONG_DAN_RECIPE.items():
        r = _lay(w.cfg.raw(), dd)
        if isinstance(r, dict) and r and mon not in quang_cao:
            loi.append(f"{mon}: config có công thức nhưng menu KHÔNG chào (agent không biết)")
    return loi


def _vi_pham_cap5(w) -> list[str]:
    """CỔNG CAP-5 tổng: recipe mồ côi + món chào mà giấu kinh tế học."""
    return ([f"recipe mồ côi (không action nào chế được): {m}" for m in _recipe_mo_coi(w)]
            + _vi_pham_cap5_xay(w))


# --------------------------------------------------------------------------- CAP-5 (a) món
@pytest.mark.parametrize("ten_cfg", ["base", "spatial"])
def test_cap5_khong_co_recipe_mo_coi(ten_cfg, w_base, w_spatial):
    """Hook `mon_recipe_khong_co_duong_che` phải RỖNG — và bảng của TEST phải đồng ý với nó.

    Lệch nhau ⇒ registry và test đang nói về hai tập món khác nhau (một trong hai đã mục).
    """
    w = w_base if ten_cfg == "base" else w_spatial
    assert mon_recipe_khong_co_duong_che(w) == (), (
        f"[{ten_cfg}] config khai công thức mà KHÔNG action nào gọi được: "
        f"{mon_recipe_khong_co_duong_che(w)}")
    assert _recipe_mo_coi(w) == mon_recipe_khong_co_duong_che(w), (
        f"[{ten_cfg}] bảng món của test ({_recipe_mo_coi(w)}) lệch registry "
        f"({mon_recipe_khong_co_duong_che(w)})")


@pytest.mark.parametrize("ten_cfg", ["base", "spatial"])
def test_cap5_moi_mon_quang_cao_deu_cong_bo_kinh_te_hoc(ten_cfg, w_base, w_spatial):
    """MỌI `mon` trong dòng menu `xay` phải kèm chi phí đầu vào + sản phẩm đầu ra, số KHỚP
    config đang chạy. Đây là test lẽ ra đã bắt `duc_xu` (menu chào "xu" suốt nhiều run mà
    prompt chưa bao giờ nói đúc xu tốn gì / ra bao nhiêu)."""
    w = w_base if ten_cfg == "base" else w_spatial
    assert _vi_pham_cap5(w) == [], f"[{ten_cfg}] CAP-5 vi phạm: {_vi_pham_cap5(w)}"


def test_cap5_mon_gia_trong_config_thi_hook_va_cong_phai_do():
    """CHỐNG VACUOUS #1: thêm một món có công thức mà KHÔNG có đường chế ⇒ CAP-5 phải ĐỎ.

    Nếu thế giới này vẫn xanh thì `mon_recipe_khong_co_duong_che` là hook chết và cả khối
    CAP-5 là assertion rỗng.
    """
    def them_vang(raw):
        raw["san_xuat"]["recipe"]["vang"] = {"cong": 9, "quang_dong": 3, "ra": 2}

    w = _the_gioi(them_vang)
    assert mon_recipe_khong_co_duong_che(w) == ("vang",), (
        "hook KHÔNG phát hiện món 'vang' có công thức mà không action nào chế được ⇒ "
        "CAP-5 vẫn không cưỡng chế được")
    assert _recipe_mo_coi(w) == ("vang",)
    vp = _vi_pham_cap5(w)
    assert any("vang" in v for v in vp), f"cổng CAP-5 KHÔNG bắt được món giả: {vp}"


def test_cap5_giau_kinh_te_hoc_cua_mot_mon_thi_phai_do(monkeypatch, w_base):
    """CHỐNG VACUOUS #2: dựng lại ĐÚNG bug lịch sử — menu vẫn chào `mon:"xu"` nhưng dòng menu
    không công bố công thức đúc xu ⇒ cổng CAP-5 PHẢI chỉ mặt "xu".

    (Trước bản vá, `_gt_xay` liệt kê "xu" ở trường `mon` trong khi phần công thức chỉ nói về
    cong_cu và nha — đúc xu, KÊNH DUY NHẤT sinh ra tiền xu, bị chào mà giấu kinh tế học.)
    """
    goc = cap.mo_ta_cong_thuc

    def giau_xu(mon: str, r: dict) -> str:
        return "" if mon == "xu" else goc(mon, r)

    monkeypatch.setattr(cap, "mo_ta_cong_thuc", giau_xu)
    dong = _dong_menu(w_base, "xay")
    assert '"xu"' in dong, "tiền đề của test hỏng: menu không còn chào món 'xu'"
    vp = _vi_pham_cap5_xay(w_base)
    assert any(v.startswith("xu:") for v in vp), (
        f"cổng CAP-5 KHÔNG bắt được món bị giấu kinh tế học ⇒ nó là assertion rỗng: {vp}")


@pytest.mark.parametrize(
    ("khoa", "spatial"),
    [
        ("san_xuat.recipe.cong_cu.go", False),
        ("san_xuat.recipe.nha.cong", False),
        ("san_xuat.recipe.xu.quang_dong", False),
        ("san_xuat.recipe.xu.ra", False),
        ("research.may.recipe.cong", False),
        ("san_xuat.recipe.thuyen.go", True),
    ],
)
def test_cap5_so_trong_menu_doc_tu_config_song(khoa, spatial):
    """Số trong menu phải ĐỌC TỪ CONFIG ĐANG CHẠY: đổi một khóa recipe ⇒ menu PHẢI đổi và
    phải nêu ĐÚNG giá trị mới (không hardcode trong template, không cache chéo scenario)."""
    w0 = _the_gioi(spatial=spatial)
    cu = _lay(w0.cfg.raw(), khoa)
    assert cu is not None, f"khóa {khoa} không có trong config — tiền đề test sai"
    moi = float(cu) * 3.0 + 7.0
    w1 = _the_gioi(lambda raw: _dat(raw, khoa, moi), spatial=spatial)

    menu0, menu1 = "\n".join(muc_hanh_dong(w0)), "\n".join(muc_hanh_dong(w1))
    assert menu0 != menu1, (
        f"đổi {khoa} ({cu} → {moi}) mà MENU KHÔNG ĐỔI ⇒ số trong prompt không đọc từ config")
    assert _so(moi) in menu1, f"menu không nêu giá trị mới của {khoa} (={_so(moi)})"
    assert _vi_pham_cap5(w1) == [], f"CAP-5 vỡ sau khi đổi {khoa}: {_vi_pham_cap5(w1)}"


def test_cap5_moi_mon_quang_cao_deu_duoc_engine_nhan(w_base):
    """Món được CHÀO ⇒ engine nhận (không rơi thùng "món lạ"). Chiều còn lại của CAP-5:
    quảng cáo mà engine không thi hành được cũng là quảng cáo dối."""
    from minds.schemas import HanhDong, QuyetDinh

    aid = sorted(a for a, ag in w_base.agents.items() if ag.con_song)[0]
    rong = KeHoach(id=aid)
    for mon in _mon_quang_cao(_dong_menu(w_base, "xay")):
        if mon == PLACEHOLDER_HANG_MOI:
            continue
        thung: list = []
        kh = quyet_dinh_thanh_ke_hoach(
            w_base,
            QuyetDinh(id=aid, hanh_dong=[HanhDong(loai="xay", mon=mon, so_luong=1)]),
            thung,
        )
        assert thung == [], f"món '{mon}' được menu chào nhưng engine coi là lạ: {thung}"
        doi = [f.name for f in dataclasses.fields(KeHoach)
               if getattr(kh, f.name) != getattr(rong, f.name) and f.name != "id"]
        assert doi, f"món '{mon}' được chào nhưng KHÔNG ghi vào field KeHoach nào"


def test_cap5_hang_moi_tu_blueprint_co_duong_che_va_duong_doc_cong_thuc():
    """`<mã hàng mới>`: menu chỉ được chào nếu (a) chỉ rõ nơi đọc công thức và (b) engine
    thật sự nhận mã hàng đó (che_hang)."""
    from minds.schemas import HanhDong, QuyetDinh

    w = _the_gioi()
    dong = _dong_menu(w, "xay")
    assert PLACEHOLDER_HANG_MOI in dong
    assert KHOI_BI_QUYET in dong, (
        "menu chào hàng mới mà không nói agent đọc công thức ở đâu ⇒ giấu kinh tế học")
    w.ten_hang["vai_1"] = "Vải thử"
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    thung: list = []
    kh = quyet_dinh_thanh_ke_hoach(
        w, QuyetDinh(id=aid, hanh_dong=[HanhDong(loai="xay", mon="vai_1", so_luong=2)]), thung)
    assert thung == [] and kh.che_hang == {"vai_1": 2}


# --------------------------------------------------------------------------- CAP-5 (c) CAP-4
@pytest.mark.parametrize("ten_cfg", ["base", "spatial"])
def test_cap5_text_kinh_te_hoc_thuan_du_kien(ten_cfg, w_base, w_spatial):
    """CAP-4 TRÙM CAP-5: text công bố kinh tế học chỉ nêu DỮ KIỆN (chi phí + sản phẩm) —
    không xếp hạng, không khuyến nghị, không tên định chế, không nhãn giai cấp."""
    w = w_base if ten_cfg == "base" else w_spatial
    thap = "\n".join(muc_hanh_dong(w)).lower()
    for tu in (*TU_MOM, *TU_XEP_HANG, *TEN_DINH_CHE_CAM, *NHAN_GIAI_CAP_CAM):
        assert tu not in thap, f"[{ten_cfg}] text kinh tế học lộ từ cấm: {tu!r}"


# --------------------------------------------------------------------------- CAP-5 (b) action
# Tham số kinh tế học mà ENGINE cưỡng chế cho từng action: chi phí đầu vào / lượng sản phẩm
# đầu ra / cổng khả thi ĐỊNH LƯỢNG. Bảng của TEST (xem GIỚI HẠN #1 ở đầu khối).
THAM_SO_KINH_TE: dict[str, tuple[str, ...]] = {
    "phan_bo_cong": ("san_xuat.cong_moi_thua", "san_xuat.giong_kg_moi_thua",
                     "san_xuat.thua_toi_da_tu_canh", "san_xuat.san_luong_goc_kg",
                     "san_xuat.khai_thac.cong_moi_go", "san_xuat.khai_thac.cong_moi_quang",
                     "san_xuat.khai_thac.hieu_suat_khong_cong_cu"),
    "xay": ("san_xuat.recipe.cong_cu.cong", "san_xuat.recipe.cong_cu.go",
            "san_xuat.recipe.nha.cong", "san_xuat.recipe.nha.go",
            "san_xuat.recipe.xu.cong", "san_xuat.recipe.xu.quang_dong",
            "san_xuat.recipe.xu.ra", "research.may.recipe.cong", "research.may.recipe.go",
            "research.may.recipe.quang_hoac_xu"),
    # giá MỘT điểm nghiên cứu (engine/research.py:37) — đầu vào quy đổi ra đầu ra
    "nghien_cuu": ("research.diem_nghien_cuu.cong_moi_diem",
                   "research.diem_nghien_cuu.thoc_moi_diem"),
    # engine/chan_nuoi.py:96-106 — CÓ pool gà rừng (spatial) thì định mức công là
    # `khong_gian.ga_rung.cong_moi_con`, KHÔNG phải `chan_nuoi.bat_ga_cong_moi_con`
    "chan_nuoi": ("chan_nuoi.bat_ga_cong_moi_con", "chan_nuoi.thit_moi_ga_kg",
                  "chan_nuoi.thit_moi_ga_con_kg", "chan_nuoi.ga_toi_da_moi_ho",
                  "khong_gian.ga_rung.cong_moi_con"),
    "danh_ca": ("danh_ca.cong_moi_kg_ca",),
    "mo_tiec": ("tiec.chi_phi_toi_thieu_thoc", "tiec.khach_toi_da"),
    "trom": ("trom.ty_le_lay_toi_da", "trom.p_thanh_cong"),
    "nhan_tin": ("minds.p2p_gui_toi_da", "minds.p2p_hom_thu_toi_da"),
    "de_nghi_hop_dong": ("hop_dong.van_ban_can_E_nguoi_soan", "hop_dong.de_nghi_het_han_tick"),
    "tra_loi_hop_dong": ("hop_dong.mac_ca_toi_da_vong",),
    "don_phuong_pha_vo": ("hop_dong.uy_tin.phat_vi_pham_mieng",),
    "buon_chuyen": ("thuong_mai.phi_van_chuyen_moi_khoang_cach",),
    "niem_yet": ("thuong_mai.niem_yet_het_han_tick",),
    "di_cu": ("di_cu.so_thua_toi_thieu", "di_cu.cach_lang_toi_thieu", "di_cu.ban_kinh_cum"),
    "cau_hon": ("nhan_khau.tuoi_truong_thanh",),
    "ung_cu": ("chinh_tri.bau_cu_moi_n_tick",),
    "ban_hanh_luat": ("chinh_tri.thue_suat_toi_da",),
    "bao_dong": ("chinh_tri.gini_nguong_bao_dong", "chinh_tri.ty_le_so_dong_bao_dong",
                 "chinh_tri.ty_le_sung_cong_bao_dong"),
    "dong_thuyen": ("san_xuat.recipe.thuyen.cong", "san_xuat.recipe.thuyen.go"),
    "rao_do": ("khong_gian.do.khach_toi_da_moi_tick", "khong_gian.do.hao_mon_moi_tick_dung"),
    "khai_hoang": ("khong_gian.khai_hoang.cong_moi_thua",
                   "khong_gian.khai_hoang.mau_mo_khai_hoang",
                   "san_xuat.homestead_tick_lien_tiep"),
    "trong_rung": ("khong_gian.rung.trong_rung.cong_moi_thua",
                    "khong_gian.rung.trong_rung.ty_le_sinh_khoi_khoi_dau",
                    "khong_gian.rung.sinh_khoi_toi_da_moi_o"),
    "dang_bao_gia": ("thuong_mai.bao_gia.het_han_tick",),
    "tao_du_an": ("du_an.toi_da_moi_chu", "du_an.han_tick"),
    "cham_tre": ("khong_gian.cham_tre.tuoi_can_cham", "khong_gian.cham_tre.cong_cham_moi_tre"),
    "canh_vu_dong": ("khong_gian.vu_dong.cay.ngo.cong",
                     "khong_gian.vu_dong.cay.ngo.san_luong_kg",
                     "khong_gian.vu_dong.cay.khoai.cong",
                     "khong_gian.vu_dong.cay.khoai.san_luong_kg"),
}

# Action KHÔNG có tham số kinh tế học nào trong config — mỗi mục PHẢI có lý do.
LY_DO_KHONG_THAM_SO: dict[str, str] = {
    "lap_phap_nhan": "vốn góp + tỷ lệ cổ phần do agent tự đặt; engine không áp số nào từ config",
    "quyet_dinh_entity": "ngưỡng điều hành nằm trong code (không phải config) — ngoài tầm CAP-5",
    "viet_di_chuc": "phân bổ do agent tự đặt; engine chỉ chuẩn hóa tỷ lệ",
    "bieu": "biếu là chuyển giao thuần, không chi phí/điều kiện định lượng nào từ config",
    "qua_song": "phí do chủ đò rao + agent chấp nhận; sức chở là tham số của rao_do",
    "dat_lenh": "giá do khớp lệnh cung-cầu; không tham số chi phí nào từ config",
    "tra_gia_dat": "đấu giá kín; không tham số chi phí nào từ config",
    "yeu_cau_hoan_tra": "trần rút ghi trong CHÍNH hợp đồng hai bên ký, không ở config",
    "bao_huy": "báo hủy đúng luật: không phí, không phạt, không ngưỡng config",
    "tra_loi_cau_hon": "trả lời thuần; điều kiện tuổi thuộc về cau_hon",
    "bo_phieu": "một người một phiếu; không tham số config",
    "hoi_lo": "số thóc do agent tự đặt; engine không áp trần từ config",
    "nghiep_doan": "gia nhập/rời nhóm: không phí, không ngưỡng config",
    "dinh_cong": "đình công: không phí, không ngưỡng config (điều kiện là 'ở trong nghiệp đoàn')",
    "keu_goi": "lời nói thuần, tự nó không dịch chuyển của cải",
    "tach_ho": (
        "tách hộ là transition cư trú tường minh; engine không ấn định chi phí, phần tài sản "
        "hay kết quả kinh tế nào"
    ),
    "yeu_cau_di_san": (
        "yêu cầu chỉ ghi tư cách claim vào lifecycle di sản; không tự chuyển tài sản hoặc áp "
        "một mức giá nào"
    ),
    "chon_dat_o": (
        "quyền lô chỉ là một yêu cầu đồng thời; không có chi phí, tài sản hay title ruộng được "
        "engine áp đặt (trần danh sách là interface của treatment v5)"
    ),
    "chap_nhan_bao_gia": (
        "chấp nhận chỉ dùng giá/lượng đã ghi trên chính báo giá; không có tham số engine áp đặt"
    ),
    "huy_bao_gia": (
        "hủy chỉ trả phần ký quỹ chưa khớp; không có mức phí hoặc ngưỡng config"
    ),
    "gop_vat_lieu_du_an": (
        "lượng và loại vật liệu do recipe của chính dự án đang mở công bố; action chỉ ký quỹ "
        "phần người góp tự nêu, engine không áp giá hoặc mức đóng góp"
    ),
    "gop_cong_du_an": (
        "lượng công do người góp tự nêu và bị chặn bởi số công còn lại; recipe của dự án ghi "
        "mức còn thiếu, action không áp mức lương hay quota riêng"
    ),
    "huy_du_an": (
        "hủy chỉ hoàn vật liệu còn trong ký quỹ theo sổ góp; không có phí hoặc ngưỡng kinh tế "
        "được engine áp đặt ngoài lifecycle dự án"
    ),
}

# Tham số PHÂN PHỐI kết quả — KHÔNG khẳng định ở đây (xem GIỚI HẠN #2). Đã ĐO: cả hai đều
# KHÔNG hiện trên bề mặt luật. Công bố hay không là quyết định của spec-governor.
THAM_SO_PHAN_PHOI_KHONG_KHANG_DINH: dict[str, tuple[str, ...]] = {
    "nghien_cuu": ("research.xac_suat_thanh_cong.k0", "research.xac_suat_thanh_cong.d",
                   "research.xac_suat_thanh_cong.he_so_roll_moi_tick"),
}


def _tham_so_cap5() -> list[tuple[str, str]]:
    return [(act, p) for act, paths in sorted(THAM_SO_KINH_TE.items()) for p in paths]


def test_cap5_bang_tham_so_phu_moi_action_cong_khai():
    """LƯỚI CHO ACTION MỚI: mọi action `cong_khai` phải được PHÂN LOẠI — hoặc có tham số kinh
    tế học phải công bố, hoặc có lý do tường minh vì sao không có. Thêm một action mới mà quên
    khai kinh tế học của nó ⇒ test này ĐỎ ngay (đó là lớp defect `duc_xu` ở cấp action)."""
    ten = cac_ten_cong_khai()
    phan_loai = set(THAM_SO_KINH_TE) | set(LY_DO_KHONG_THAM_SO)
    assert set(THAM_SO_KINH_TE) & set(LY_DO_KHONG_THAM_SO) == set(), (
        "một action vừa 'có tham số' vừa 'không có tham số'")
    assert sorted(ten - phan_loai) == [], (
        f"action công khai CHƯA được phân loại kinh tế học: {sorted(ten - phan_loai)}")
    assert sorted(phan_loai - ten) == [], (
        f"bảng CAP-5 nhắc action không còn trong catalog: {sorted(phan_loai - ten)}")
    for act, ly_do in LY_DO_KHONG_THAM_SO.items():
        assert len(ly_do.strip()) >= 20, f"'{act}' thiếu lý do tường minh"


@pytest.mark.parametrize(("act", "khoa"), _tham_so_cap5(),
                         ids=[f"{a}:{p}" for a, p in _tham_so_cap5()])
def test_cap5_tham_so_kinh_te_hien_tren_be_mat_luat(act, khoa):
    """ĐỘT BIẾN: đổi một tham số kinh tế học mà ENGINE cưỡng chế ⇒ BỀ MẶT LUẬT agent đọc PHẢI
    đổi theo. Bề mặt KHÔNG đổi ⇒ agent đang chơi một trò chơi mà nó không được cho biết luật:
    tần suất nó không dùng cơ chế đó nói về INTERFACE, không nói về hành vi agent (đúng lớp
    confound `duc_xu`).

    Đo bằng đột biến chứ không so chuỗi: số nhỏ ("8", "10") xuất hiện khắp prompt nên kiểm
    `"8" in prompt` là rỗng nghĩa; đột biến thì không thể vacuous.
    """
    # Chọn scenario NHỎ NHẤT chứa cả khóa config lẫn action. P2/P1 overlay là thí nghiệm
    # khác, không được ép chúng vào base/spatial_v1 chỉ để test xanh.
    candidates = (("base", False, False), ("spatial", True, False),
                  ("livelihood", True, True))
    ten_cfg, spatial, livelihood = next(
        (ten, sp, lv) for ten, sp, lv in candidates
        if _lay(_the_gioi(spatial=sp, livelihood=lv).cfg.raw(), khoa) is not None
        and act in {c.ten for c in kha_dung_trong(_the_gioi(spatial=sp, livelihood=lv))}
    )
    w0 = _the_gioi(spatial=spatial, livelihood=livelihood)
    cu = _lay(w0.cfg.raw(), khoa)
    assert cu is not None, f"{khoa} không có trong config — bảng CAP-5 đã mục"
    assert act in {c.ten for c in kha_dung_trong(w0)}, (
        f"{act} không khả dụng ở scenario {ten_cfg}")

    moi = int(cu) * 3 + 7 if isinstance(cu, int) else float(cu) * 3.0 + 7.0
    w1 = _the_gioi(lambda raw: _dat(raw, khoa, moi), spatial=spatial, livelihood=livelihood)
    assert _be_mat_luat(w1) != _be_mat_luat(w0), (
        f"[{ten_cfg}] '{act}': đổi {khoa} ({cu} → {moi}) mà BỀ MẶT "
        f"LUẬT của agent KHÔNG ĐỔI ⇒ engine cưỡng chế một con số mà prompt chưa bao giờ công "
        f"bố (CAP-5, minds/capabilities.py:21-30)")
