"""Phase 1 "viện hàn lâm": kiểm 4 chỉ số kinh tế vĩ mô CHUẨN trong tinh_metrics.

Cả bốn (gdp, velocity, gini_thu_nhap, ty_le_phi_ly) THUẦN QUAN SÁT — chỉ đo từ
ledger + lịch sử giá, không mã hóa quy luật kinh tế nào. Test dùng thế giới nhỏ.
"""

from __future__ import annotations

from engine.config import load_config
from engine.metrics import (
    gdp_thuc,
    gini_thu_nhap,
    tinh_metrics,
    ty_le_phi_ly,
    velocity_tien,
)
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.rulebot import quyet_dinh_tat_ca
from observatory.observer import quy_dao_gini
from tests.helpers import the_gioi_test

CAC_FIELD_MOI = ("gdp", "velocity", "gini_thu_nhap", "ty_le_phi_ly")


# --------------------------------------------------------------- tích hợp thật


def _chay(seed: int, so_tick: int):
    cfg = load_config()
    w = tao_the_gioi(cfg, seed)
    tong_thua = len(w.parcels)
    while w.tick < so_tick:
        chay_mot_tick(w, quyet_dinh_tat_ca, tong_thua)
    return w


def test_cac_field_xuat_hien_va_hop_ly():
    """Chạy thế giới thật ~30 tick: mọi bản ghi metrics có đủ 4 field, giá trị hợp lý."""
    w = _chay(seed=7, so_tick=30)  # audit raise nếu vi phạm bảo toàn — chạy trọn = xanh
    assert len(w.metrics_lich_su) >= 30
    for m in w.metrics_lich_su:
        for f in CAC_FIELD_MOI:
            assert f in m, f"thiếu field {f}"
        # miền giá trị hợp lệ
        assert 0.0 <= m["gini_thu_nhap"] <= 1.0
        assert 0.0 <= m["ty_le_phi_ly"] <= 1.0
        assert m["velocity"] >= 0.0
        # GDP thực có thể âm (mùa mất/chỉ tiêu hao) nhưng phải là số hữu hạn
        assert isinstance(m["gdp"], float)


def test_gdp_duong_khi_co_thu_hoach():
    """Ít nhất một tick mùa mưa phải có GDP > 0 (giá trị gia tăng từ gặt)."""
    w = _chay(seed=7, so_tick=30)
    assert any(m["gdp"] > 0 for m in w.metrics_lich_su)


def test_quy_dao_gini_khop_metrics():
    """observatory.quy_dao_gini chỉ đọc lại nhật ký metrics đúng bằng số tick."""
    w = _chay(seed=7, so_tick=20)
    qd = quy_dao_gini(w)
    assert len(qd) == len(w.metrics_lich_su)
    tick0, gt0, gd0, gtn0 = qd[0]
    assert tick0 == w.metrics_lich_su[0]["tick"]
    assert gtn0 == w.metrics_lich_su[0]["gini_thu_nhap"]


# --------------------------------------------------------------- GDP value-added


def test_gdp_value_added_gat_tru_giong():
    """GDP = giá trị hàng SINH ra − nguyên liệu trung gian TIÊU HAO; ăn/hao kho KHÔNG
    tính vào (là tiêu dùng, không phải sản xuất)."""
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    aid = sorted(w.agents)[0]
    w.tick = 5
    w.ledger.sinh(aid, "thoc", 100.0, "gat", "gặt (test)", w.tick)      # đầu ra +100
    w.ledger.huy(aid, "thoc", 10.0, "giong", "gieo (test)", w.tick)     # trung gian -10
    w.ledger.huy(aid, "thoc", 20.0, "an", "ăn (test)", w.tick)          # tiêu dùng: bỏ qua
    assert abs(gdp_thuc(w) - 90.0) < 1e-6


def test_gdp_chi_dem_tick_hien_tai():
    """Sản xuất ở tick TRƯỚC không được tính vào GDP tick hiện tại."""
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    aid = sorted(w.agents)[0]
    w.tick = 4
    w.ledger.sinh(aid, "thoc", 50.0, "gat", "gặt cũ", w.tick)
    w.tick = 5  # sang tick mới, chưa sản xuất gì
    assert abs(gdp_thuc(w) - 0.0) < 1e-6


# --------------------------------------------------------------- velocity


def test_velocity_0_khi_chua_co_xu():
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    assert w.ledger.tong_tai_san("xu") == 0.0
    assert velocity_tien(w) == 0.0


def test_velocity_bang_pq_chia_m():
    """V = P·Q / M với P·Q = khớp chợ (quy thóc) + chuyển giao hợp đồng."""
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    aid = sorted(w.agents)[0]
    w.ledger.sinh(aid, "xu", 50.0, "duc_xu", "đúc xu (test)", w.tick)   # M = 50
    w.kl_thanh_toan_tick = {"thoc": 30.0, "xu": 0.0}                    # khớp chợ 30
    w.kl_hd_tick = 20.0                                                 # hợp đồng 20
    assert abs(velocity_tien(w) - (50.0 / 50.0)) < 1e-6                 # P·Q=50, M=50 → 1.0


# --------------------------------------------------------------- gini thu nhập


def test_gini_thu_nhap_bat_binh_dang():
    """Thu nhập lệch nhau → Gini > 0; bộ đếm 'canh_*' KHÔNG tính là thu nhập."""
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    a, b = sorted(w.agents)[:2]
    song = [w.agents[a], w.agents[b]]
    w.thu_nhap_4 = [
        {a: {"nong": 100.0, "canh_thua_tong": 5.0}, b: {"nong": 0.0}},
    ]
    g = gini_thu_nhap(w, song)
    assert 0.0 < g <= 1.0
    # cân bằng tuyệt đối → Gini = 0
    w.thu_nhap_4 = [{a: {"nong": 50.0}, b: {"nong": 50.0}}]
    assert gini_thu_nhap(w, song) == 0.0


# --------------------------------------------------------------- bounded rationality


def test_ty_le_phi_ly_phat_hien_gia_lech():
    """Một cú khớp lệch xa (>3σ) mặt bằng lịch sử → bị đếm là 'phi lý'."""
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    w.tick = 10
    lich_su = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0]  # 6 điểm, σ nhỏ
    w.gia_lich_su["go"] = [(t, p, 1.0, "thoc") for t, p in enumerate(lich_su)]
    w.gia_lich_su["go"] += [(10, 20.0, 1.0, "thoc"), (10, 10.0, 1.0, "thoc")]
    # 1 cú @20 (phi lý) + 1 cú @10 (bình thường) → 1/2
    assert abs(ty_le_phi_ly(w) - 0.5) < 1e-9


def test_ty_le_phi_ly_thi_truong_on_dinh():
    """Mọi cú khớp sát trung bình → tỷ lệ phi lý = 0."""
    w = the_gioi_test(seed=1, giu_lai=2, thoc_moi_nguoi=2000.0)
    w.tick = 10
    lich_su = [10.0, 10.2, 9.8, 10.1, 9.9, 10.0]
    w.gia_lich_su["go"] = [(t, p, 1.0, "thoc") for t, p in enumerate(lich_su)]
    w.gia_lich_su["go"] += [(10, 10.05, 1.0, "thoc"), (10, 9.95, 1.0, "thoc")]
    assert ty_le_phi_ly(w) == 0.0


def test_tinh_metrics_tra_du_field():
    """tinh_metrics (không chạy tick) vẫn trả đủ 4 field trên thế giới mới."""
    w = tao_the_gioi(load_config(), seed=3)
    m = tinh_metrics(w)
    for f in CAC_FIELD_MOI:
        assert f in m
