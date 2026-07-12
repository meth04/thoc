"""Test gói sửa lỗi engine (wave audit check.md): bảo toàn NaN, chủ thể ma,
engine không tự đặt giá, decay đồ thị quan hệ."""

from __future__ import annotations

import math

import pytest

from engine import demography, market
from engine.audit import LoiBaoToan, kiem_toan_the_gioi
from engine.contracts import ClauseChuyenGiaoDinhKy, HopDong
from engine.entities import lap_phap_nhan
from engine.intents import KeHoach
from engine.ledger import LoiSoKep
from engine.market import Lenh
from engine.research import Blueprint
from engine.world import VO_THUA_NHAN
from engine.xa_hoi import decay_quan_he
from tests.helpers import cap_ruong, the_gioi_test

# ---------------------------------------------------------------- A1: NaN + rollback


def test_lap_phap_nhan_co_phan_am_khong_hong_state():
    """Cổ phần âm bị từ chối TRƯỚC mọi mutation — thóc không kẹt, không entity ma."""
    w = the_gioi_test(giu_lai=2)
    thoc_truoc = w.ledger.so_du("A0001", "thoc")
    eid = lap_phap_nhan(
        w, "A0001", "Xưởng lậu", {"A0001": 150.0, "A0002": -50.0},
        {"A0001": {"thoc": 100.0}},
    )
    assert eid is None
    assert w.ledger.so_du("A0001", "thoc") == pytest.approx(thoc_truoc)
    assert not w.entities
    assert not any(ts.startswith("co_phan:") for _, ts in w.ledger._so_du)


def test_lap_phap_nhan_co_phan_nan_bi_tu_choi():
    """NaN qua mặt mọi so sánh — phải bị chặn tường minh, không lọt vào sổ."""
    w = the_gioi_test(giu_lai=2)
    thoc_truoc = w.ledger.so_du("A0001", "thoc")
    eid = lap_phap_nhan(
        w, "A0001", "X", {"A0001": float("nan"), "A0002": 100.0},
        {"A0001": {"thoc": 50.0}},
    )
    assert eid is None
    assert w.ledger.so_du("A0001", "thoc") == pytest.approx(thoc_truoc)
    assert not w.entities


def test_ledger_tu_choi_nan_va_inf():
    """Guard một chỗ cho mọi luồng: NaN/inf không bao giờ được vào sổ kép."""
    w = the_gioi_test(giu_lai=2)
    for xau in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(LoiSoKep):
            w.ledger.chuyen("A0001", "A0002", "thoc", xau, "test", w.tick)
        with pytest.raises(LoiSoKep):
            w.ledger.sinh("A0001", "thoc", xau, "khoi_tao", "test", w.tick)
    # số dư không đổi, audit vẫn xanh
    kiem_toan_the_gioi(w, len(w.parcels))


# ---------------------------------------------------------------- A2: chợ lọc NaN


def test_phien_cho_loc_lenh_nan_khong_sap():
    """Một lệnh NaN trộn vào KHÔNG làm phiên chợ crash/treo; lệnh lành vẫn khớp."""
    w = the_gioi_test(giu_lai=3)
    w.ledger.sinh("A0001", "go", 20.0, "khai_thac", "fixture", w.tick)
    lenh = [
        Lenh("A0001", "ban", "go", 10.0, 1.0),
        Lenh("A0002", "mua", "go", 10.0, 1.0),
        Lenh("A0003", "mua", "go", float("nan"), 2.0),
        Lenh("A0003", "ban", "go", 5.0, float("inf")),
        Lenh("A0003", "mua", "go", 3.0, float("nan")),
    ]
    khop = market.phien_cho(w, lenh)
    assert khop == pytest.approx(10.0)
    assert w.ledger.so_du("A0002", "go") == pytest.approx(10.0)
    # không giá NaN nào lọt vào lịch sử
    assert all(math.isfinite(x[1]) for x in w.gia_lich_su.get("go", []))


# ---------------------------------------------------------------- A4: thừa kế → về công


def test_thua_ke_toan_nguoi_chet_dat_ve_cong():
    """Người nhận đều đã chết → đất về công, của rơi vào VO_THUA_NHAN; audit xanh."""
    w = the_gioi_test(giu_lai=3)
    a = w.agents["A0001"]
    con = w.agents["A0002"]
    a.con = ["A0002"]
    con.cha = "A0001"
    thua = cap_ruong(w, "A0001", so_thua=2)
    # con chết trước, rồi cha chết — không còn ai nhận
    con.con_song = False
    a.con_song = False
    demography.thua_ke_mac_dinh(w, "A0001")
    for pid in thua:
        assert w.parcels[pid].chu is None  # đất về công, không về tay người chết
    assert w.ledger.so_du(VO_THUA_NHAN, "thoc") > 0
    kiem_toan_the_gioi(w, len(w.parcels))


def test_audit_bat_chu_thua_ma():
    """Chủ thửa là VO_THUA_NHAN / người chết → audit phải fail."""
    w = the_gioi_test(giu_lai=2)
    pid = cap_ruong(w, "A0001", so_thua=1)[0]
    w.parcels[pid].chu = VO_THUA_NHAN
    with pytest.raises(LoiBaoToan):
        kiem_toan_the_gioi(w, len(w.parcels))
    w.parcels[pid].chu = "A0003"  # A0003 đã 'rời cuộc chơi' (chết) trong fixture
    with pytest.raises(LoiBaoToan):
        kiem_toan_the_gioi(w, len(w.parcels))


# ---------------------------------------------------------------- A5: bên chết không nhận


def test_ben_chet_khong_nhan_chuyen_giao():
    """Hợp đồng có bên chết: leg bị SKIP (không chuyển vào túi người chết,
    không dán nhãn vi_pham), hợp đồng bị hủy trong cùng tick."""
    w = the_gioi_test(giu_lai=2)
    w.tick = 3
    hd = HopDong(
        id="HD00001", cac_ben=["A0001", "A0002"], tick_ky=2, trang_thai="hieu_luc",
        dieu_khoan=[ClauseChuyenGiaoDinhKy(tu="A0001", den="A0002",
                                           tai_san="thoc", so_luong=50.0, moi_n_tick=1)],
    )
    w.hop_dong["HD00001"] = hd
    w.agents["A0002"].con_song = False  # người nhận chết (chưa thừa kế vị thế)
    thoc_chet = w.ledger.so_du("A0002", "thoc")
    thoc_song = w.ledger.so_du("A0001", "thoc")

    from engine.contracts import thi_hanh_hop_dong_tick

    thi_hanh_hop_dong_tick(w)
    assert w.ledger.so_du("A0002", "thoc") == pytest.approx(thoc_chet)  # không nhận gì
    assert w.ledger.so_du("A0001", "thoc") == pytest.approx(thoc_song)  # không bị trừ
    assert hd.trang_thai == "huy"  # chấm dứt vì bên chết, KHÔNG phải vi_pham
    assert hd.ke_vi_pham == ""


# ---------------------------------------------------------------- B1: y tế qua hợp đồng


def _dung_san_phu(w):
    """Vợ chồng A0001 (nữ) + A0002 (nam), thầy lang A0003 nắm blueprint y_te mạnh."""
    me, cha, thay = w.agents["A0001"], w.agents["A0002"], w.agents["A0003"]
    me.gioi_tinh, cha.gioi_tinh = "nu", "nam"
    me.tuoi_tick, cha.tuoi_tick = 25 * 2, 27 * 2
    me.vo_chong, cha.vo_chong = "A0002", "A0001"
    thay.con_song = True
    thay.health = 100.0
    w.blueprints["BP0001"] = Blueprint(
        id="BP0001", linh_vuc="y_te", do_lon=1.0, ten="Bí quyết đỡ đẻ", chu="A0003")
    ss = w.cfg.raw()["nhan_khau"]["sinh_san"]
    ss["p_goc"] = 1.0  # ép sinh chắc chắn để test tất định
    ss["rui_ro_me"] = 1.0  # không y tế → tử vong sinh nở chắc chắn
    ss["y_te_giam_rui_ro_san"] = 0.0  # có y tế đủ mạnh → rủi ro về 0
    return me, thay


def test_khong_con_phi_do_de_tu_dong():
    """Engine KHÔNG tự móc túi sản phụ trả thầy lang — không có hợp đồng thì
    không giao dịch nào xảy ra và rủi ro KHÔNG giảm."""
    w = the_gioi_test(giu_lai=3)
    w.tick = 1
    me, thay = _dung_san_phu(w)
    thoc_me = w.ledger.so_du("A0001", "thoc")
    thoc_thay = w.ledger.so_du("A0003", "thoc")
    demography.sinh_con(w, {"A0001": KeHoach(id="A0001", y_dinh_sinh_con=1.0)})
    assert w.ledger.so_du("A0003", "thoc") == pytest.approx(thoc_thay)  # không phí tự động
    assert w.ledger.so_du("A0001", "thoc") == pytest.approx(thoc_me)
    assert me.health == 0.0  # rủi ro nguyên vẹn → tử vong sinh nở


def test_co_hop_dong_y_te_thi_rui_ro_giam():
    """Có hợp đồng hiệu lực giữa sản phụ và chủ blueprint y_te → rủi ro giảm
    (giá cả do hợp đồng tự thỏa thuận, engine không đặt giá)."""
    w = the_gioi_test(giu_lai=3)
    w.tick = 1
    me, thay = _dung_san_phu(w)
    w.hop_dong["HD00001"] = HopDong(
        id="HD00001", cac_ben=["A0001", "A0003"], tick_ky=0, trang_thai="hieu_luc",
        dieu_khoan=[ClauseChuyenGiaoDinhKy(tu="A0001", den="A0003",
                                           tai_san="thoc", so_luong=10.0)],
    )
    thoc_thay = w.ledger.so_du("A0003", "thoc")
    demography.sinh_con(w, {"A0001": KeHoach(id="A0001", y_dinh_sinh_con=1.0)})
    assert me.health > 0.0  # blueprint do_lon=1.0, sàn=0 → rủi ro 0, mẹ sống
    # sinh_con vẫn không chuyển đồng nào — thanh toán là việc của executor hợp đồng
    assert w.ledger.so_du("A0003", "thoc") == pytest.approx(thoc_thay)


# ---------------------------------------------------------------- C1: decay + prune


def test_decay_quan_he_moi_cuoi_nam_va_prune():
    w = the_gioi_test(giu_lai=3)
    w.agents["A0003"].con_song = False
    w.quan_he[("A0001", "A0002")] = 1.0
    w.quan_he[("A0001", "A0003")] = 2.0  # cạnh với người chết
    w.quan_he[("A0002", "A0004")] = 0.01  # cạnh quá mờ (A0004 cũng đã chết)

    w.tick = 1  # mùa mưa (giữa năm) → CHƯA decay
    decay_quan_he(w)
    assert w.quan_he[("A0001", "A0002")] == pytest.approx(1.0)

    w.tick = 2  # cuối năm → decay + prune
    decay_quan_he(w)
    decay = float(w.cfg.get("quan_he.decay_moi_nam"))
    assert w.quan_he[("A0001", "A0002")] == pytest.approx(1.0 * (1 - decay))
    assert ("A0001", "A0003") not in w.quan_he  # cạnh người chết bị dọn
    assert ("A0002", "A0004") not in w.quan_he  # cạnh mờ bị quên
