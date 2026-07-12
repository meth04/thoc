"""Round-trip KeHoach → QuyetDinh JSON → KeHoach — khóa hồi quy đối xứng translate.

Dựng một KeHoach dùng ĐỦ MỌI trường (kể cả danh_ca, mo_tiec, trom, chan_nuoi, bieu,
buon_chuyen có lang, bao_huy), đi qua đúng pipeline thật (serialize JSON → parse_batch
→ quyet_dinh_thanh_ke_hoach) rồi assert bằng nhau từng trường.
"""

from __future__ import annotations

import dataclasses
import json

from engine.contracts import (
    ClauseChuyenGiaoDinhKy,
    ClauseChuyenGiaoMotLan,
    ClauseGopCong,
    HopDong,
)
from engine.intents import KeHoach
from engine.market import Lenh
from minds.repair import parse_batch
from minds.schemas import LOAI_HANH_DONG, HanhDong, QuyetDinh
from minds.translate import ke_hoach_thanh_quyet_dinh, quyet_dinh_thanh_ke_hoach
from tests.helpers import the_gioi_test


def _hop_dong_lam_cong(tu: str, den: str) -> HopDong:
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


def _ke_hoach_du_truong(w, aid: str) -> KeHoach:
    """KeHoach phủ MỌI trường mà translate serialize được."""
    eid = "E0001"
    kh = KeHoach(id=aid)
    # phan_bo_cong
    kh.canh_thua = ["P01_01", "P01_02"]
    kh.gop_cong_cho = "A0002"
    kh.cong_khai_go = 30.0
    kh.cong_khai_quang = 12.0
    kh.hoc = True
    kh.day_cho = ["A0003"]
    # xây / chế tác / đúc
    kh.che_tao_cong_cu = 2
    kh.xay_nha = 1
    kh.xay_may = 1
    kh.duc_xu = 1
    w.ten_hang["vai_1"] = "Vải thử"  # hàng mới phải có trong thế giới
    kh.che_hang = {"vai_1": 3}
    # R&D + pháp nhân + entity con
    kh.nghien_cuu = ("nong_nghiep", 60.0, 100.0)
    kh.lap_phap_nhan = {
        "ten": "Trại thử",
        "co_phan": {"A0001": 60.0, "A0002": 40.0},
        "von_gop": {"A0001": {"thoc": 200.0}},
    }
    kh_con = KeHoach(id=eid)
    kh_con.canh_thua = ["P05_05"]
    kh_con.dat_lenh = [Lenh(eid, "ban", "cong_cu", 1.0, 100.0)]
    kh.quyet_dinh_entity = [(eid, kh_con)]
    # di chúc + di cư
    kh.viet_di_chuc = {"phan_bo": {"A0003": 100.0}, "gia_huan": "Giữ đất hương hỏa."}
    kh.di_cu = True
    # chăn nuôi + biếu + sinh kế & xã hội (gói realism 2)
    kh.bat_ga_cong = 20.0
    kh.giet_ga = 2
    kh.bieu = [("A0002", "thoc", 50.0)]
    kh.danh_ca_cong = 30.0
    kh.mo_tiec = (100.0, 8.0)
    kh.trom = ("A0009", "thoc", 40.0)
    # hợp đồng: đề nghị + trả lời (chấp nhận & mặc cả) + phá vỡ + BÁO HỦY
    kh.de_nghi_hop_dong = [(_hop_dong_lam_cong(aid, "A0002"), "A0002")]
    kh.tra_loi_de_nghi = {
        "DN0001": "chap_nhan",
        "DN0002": _hop_dong_lam_cong("A0004", aid),  # mặc cả bằng bản sửa đổi
    }
    kh.don_phuong_pha_vo = ["HD00001"]
    # bao_huy: gắn động nếu engine chưa thêm field (translate dùng getattr)
    if getattr(kh, "bao_huy", None) is None:
        kh.bao_huy = []
    kh.bao_huy.append("HD00003")
    # chợ: lệnh làng mình + buôn chuyến (lang=1) + đất
    kh.dat_lenh = [
        Lenh(aid, "mua", "go", 5.0, 12.0),
        Lenh(aid, "ban", "ga", 2.0, 40.0, "thoc", lang=1),
    ]
    kh.niem_yet_dat = [("P02_02", 600.0)]
    kh.tra_gia_dat = [("P03_03", 500.0)]
    kh.yeu_cau_rut = {"HD00002": 20.0}
    # hôn nhân
    kh.cau_hon = "A0005"
    kh.tra_loi_cau_hon = {"A0006": True}
    return kh


def test_roundtrip_du_moi_truong():
    w = the_gioi_test(seed=71, giu_lai=3)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    kh_goc = _ke_hoach_du_truong(w, aid)

    qd_dict = ke_hoach_thanh_quyet_dinh(kh_goc, ly_do="test roundtrip")
    text = json.dumps([qd_dict], ensure_ascii=False)
    ok, hong = parse_batch(text, [aid])
    assert not hong, f"parse_batch hỏng: {hong}"

    thung: list = []
    kh_lai = quyet_dinh_thanh_ke_hoach(w, ok[aid], thung)
    assert thung == [], f"có intent rơi thùng lạ: {thung}"

    for f in dataclasses.fields(KeHoach):
        assert getattr(kh_lai, f.name) == getattr(kh_goc, f.name), (
            f"trường {f.name} lệch sau round-trip:\n"
            f"  gốc: {getattr(kh_goc, f.name)!r}\n"
            f"  lại: {getattr(kh_lai, f.name)!r}"
        )
    # bao_huy có thể là field động (dataclass eq bỏ qua attr động) → so tường minh
    assert list(getattr(kh_lai, "bao_huy", [])) == ["HD00003"]
    # buôn chuyến giữ đúng làng đích
    assert any(le.lang == 1 for le in kh_lai.dat_lenh), "Lenh.lang mất chiều xuôi"


def test_bao_huy_trong_van_pham():
    """bao_huy là nguyên tố hợp lệ: không rơi thùng intent lạ, dịch đúng 2 chiều."""
    assert "bao_huy" in LOAI_HANH_DONG
    w = the_gioi_test(seed=72, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[HanhDong(loai="bao_huy", ref="HD00007")])
    thung: list = []
    kh = quyet_dinh_thanh_ke_hoach(w, qd, thung)
    assert thung == []
    assert list(getattr(kh, "bao_huy", [])) == ["HD00007"]
    # chiều xuôi
    qd_dict = ke_hoach_thanh_quyet_dinh(kh)
    assert {"loai": "bao_huy", "ref": "HD00007"} in qd_dict["hanh_dong"]


def test_dat_lenh_tai_san_trung_thanh_toan_khong_cam():
    """Lệnh 'mua thóc trả bằng thóc' phải có VẾT (thùng intent lạ / unrecognized),
    không được nuốt êm (điều luật #3 + #6)."""
    w = the_gioi_test(seed=73, giu_lai=1)
    aid = sorted(x for x, a in w.agents.items() if a.con_song)[0]
    qd = QuyetDinh(id=aid, hanh_dong=[HanhDong(
        loai="dat_lenh", chieu="mua", tai_san="thoc", sl=10.0, gia=1.0,
        thanh_toan="thoc")])
    thung: list = []
    kh = quyet_dinh_thanh_ke_hoach(w, qd, thung)
    assert not kh.dat_lenh, "lệnh vô nghĩa không được vào chợ"
    assert thung and "vô nghĩa" in thung[0][2]
