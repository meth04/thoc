"""Khóa hồi quy schema ý định CHÍNH TRỊ (bầu cử, lập pháp, nghiệp đoàn, bạo động)
+ công cụ RAG lập pháp CHỈ ĐỌC get_phan_bo_cua_cai.

Hai bất biến sắt kiểm ở đây:
1. Round-trip 2 chiều ĐỐI XỨNG cho cả 8 ý định chính trị qua ĐÚNG pipeline thật
   (serialize JSON → parse_batch → quyet_dinh_thanh_ke_hoach), không rơi thùng lạ.
2. Tham số sai (luật không phải dict, thiếu id...) → bỏ + ghi vết, KHÔNG raise (điều luật #3).
3. Công cụ get_phan_bo_cua_cai THUẦN ĐỌC: world_hash bất biến sau khi gọi (điều luật #1).
"""

from __future__ import annotations

import json

from engine.intents import KeHoach
from minds.repair import parse_batch
from minds.schemas import LOAI_HANH_DONG, HanhDong, QuyetDinh
from minds.translate import ke_hoach_thanh_quyet_dinh, quyet_dinh_thanh_ke_hoach
from minds.world_tools import thuc_thi
from tests.helpers import the_gioi_test

_TAM_Y_DINH = {
    "ung_cu", "bo_phieu", "ban_hanh_luat", "hoi_lo", "nghiep_doan",
    "dinh_cong", "bao_dong", "keu_goi",
}


def test_tam_loai_co_trong_van_pham():
    """8 loại chính trị đều là nguyên tố hợp lệ của schema."""
    assert _TAM_Y_DINH <= LOAI_HANH_DONG


def _ke_hoach_chinh_tri(aid: str) -> KeHoach:
    kh = KeHoach(id=aid)
    kh.ung_cu = True
    kh.bo_phieu = "A0002"
    kh.ban_hanh_luat = {"loai": "thue", "suat": 0.1}
    kh.hoi_lo = ("A0003", 100.0)
    kh.gia_nhap_nghiep_doan = True
    kh.dinh_cong = True
    kh.bao_dong = True
    kh.keu_goi = "Xin bà con dồn phiếu cho người nghèo."
    return kh


def test_roundtrip_tam_y_dinh_chinh_tri():
    """KeHoach chính trị → JSON → parse_batch → KeHoach: khớp từng trường, không rơi thùng."""
    w = the_gioi_test(seed=81, giu_lai=3)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    kh_goc = _ke_hoach_chinh_tri(aid)

    qd_dict = ke_hoach_thanh_quyet_dinh(kh_goc, ly_do="test chính trị")
    ok, hong = parse_batch(json.dumps([qd_dict], ensure_ascii=False), [aid])
    assert not hong, f"parse_batch hỏng: {hong}"

    thung: list = []
    kh_lai = quyet_dinh_thanh_ke_hoach(w, ok[aid], thung)
    assert thung == [], f"có intent chính trị rơi thùng lạ: {thung}"

    assert kh_lai.ung_cu is True
    assert kh_lai.bo_phieu == "A0002"
    assert kh_lai.ban_hanh_luat == {"loai": "thue", "suat": 0.1}
    assert kh_lai.hoi_lo == ("A0003", 100.0)
    assert kh_lai.gia_nhap_nghiep_doan is True
    assert kh_lai.dinh_cong is True
    assert kh_lai.bao_dong is True
    assert kh_lai.keu_goi == "Xin bà con dồn phiếu cho người nghèo."


def test_luat_luong_toi_thieu_roundtrip():
    """Đạo luật lương tối thiểu (dạng luật thứ hai) cũng đi qua nguyên vẹn."""
    w = the_gioi_test(seed=82, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    kh = KeHoach(id=aid)
    kh.ban_hanh_luat = {"loai": "luong_toi_thieu", "muc": 2.0}
    qd_dict = ke_hoach_thanh_quyet_dinh(kh)
    ok, hong = parse_batch(json.dumps([qd_dict], ensure_ascii=False), [aid])
    assert not hong
    kh_lai = quyet_dinh_thanh_ke_hoach(w, ok[aid], [])
    assert kh_lai.ban_hanh_luat == {"loai": "luong_toi_thieu", "muc": 2.0}


def test_luat_khong_phai_dict_roi_thung_khong_raise():
    """luật là chuỗi/số bậy → bỏ + ghi vết, KHÔNG raise (điều luật #3)."""
    w = the_gioi_test(seed=83, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[HanhDong(loai="ban_hanh_luat", luat="đánh thuế đi")])
    thung: list = []
    kh = quyet_dinh_thanh_ke_hoach(w, qd, thung)
    assert kh.ban_hanh_luat is None
    assert thung and thung[0][0] == aid  # có vết trong thùng intent lạ


def test_suat_am_bi_ep_ve_khong_am():
    """Thuế suất âm do LLM bịa bị ép về ≥0 (không tin dữ liệu LLM)."""
    w = the_gioi_test(seed=84, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[HanhDong(
        loai="ban_hanh_luat", luat={"loai": "thue", "suat": -0.5})])
    kh = quyet_dinh_thanh_ke_hoach(w, qd, [])
    assert kh.ban_hanh_luat == {"loai": "thue", "suat": 0.0}


def test_hoi_lo_thieu_den_roi_thung():
    """hối lộ thiếu người nhận → KeyError bị bắt, rơi thùng, không sập."""
    w = the_gioi_test(seed=85, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[HanhDong(loai="hoi_lo", thoc=50.0)])
    thung: list = []
    kh = quyet_dinh_thanh_ke_hoach(w, qd, thung)
    assert kh.hoi_lo is None
    assert thung  # có vết


def test_nghiep_doan_mac_dinh_gia_nhap():
    """{"loai":"nghiep_doan"} không kèm cờ → hiểu là gia nhập."""
    w = the_gioi_test(seed=86, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[HanhDong(loai="nghiep_doan")])
    kh = quyet_dinh_thanh_ke_hoach(w, qd, [])
    assert kh.gia_nhap_nghiep_doan is True


# ---- công cụ RAG lập pháp CHỈ ĐỌC ----

def test_get_phan_bo_cua_cai_chi_doc():
    """get_phan_bo_cua_cai KHÔNG đổi world_hash (điều luật #1) và trả đủ khóa."""
    w = the_gioi_test(seed=87, giu_lai=5, thoc_moi_nguoi=1500.0)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    h0 = w.world_hash()
    kq = thuc_thi(w, ids[0], "get_phan_bo_cua_cai", {})
    assert w.world_hash() == h0  # thuần đọc
    for k in ("so_dan", "so_ho", "thoc_p10", "thoc_p50", "thoc_p90",
              "gini_thoc", "so_ho_ngheo"):
        assert k in kq, f"thiếu khóa {k}"
    # phân vị đơn điệu không giảm
    assert kq["thoc_p10"] <= kq["thoc_p50"] <= kq["thoc_p90"]
    assert 0.0 <= kq["gini_thoc"] <= 1.0
    assert 0 <= kq["so_ho_ngheo"] <= kq["so_ho"]


def test_get_phan_bo_bat_bien_qua_nhieu_lan_goi():
    """Gọi nhiều lần trả CÙNG kết quả (tất định) và không đổi thế giới."""
    w = the_gioi_test(seed=88, giu_lai=4, thoc_moi_nguoi=800.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    h0 = w.world_hash()
    kq1 = thuc_thi(w, aid, "get_phan_bo_cua_cai", {})
    kq2 = thuc_thi(w, aid, "get_phan_bo_cua_cai", {})
    assert kq1 == kq2
    assert w.world_hash() == h0
