"""Metric nghiên cứu T04–T08 là QUAN SÁT thuần (ADR 0003 + 0004).

Chứng minh: (a) gọi metric KHÔNG đổi world-hash và có mặt trong m['research'];
(b) claims view đối xứng chủ nợ/con nợ; (c) tài khóa báo 0 trung thực; (d) tỷ trọng
tiền tệ hóa 0 khi không xu, dương khi có xu, và không giảm khi tăng giao dịch xu.
"""

from __future__ import annotations

from engine.contracts import ClauseChuyenGiaoMotLan, HopDong
from engine.market import Lenh, phien_cho
from engine.metrics_research import claims_view, research_metrics
from engine.world import World
from tests.helpers import chay_tick, mind_tinh, the_gioi_test


def test_research_khong_doi_world_hash_va_co_mat_trong_metrics():
    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=1500)
    chay_tick(w, mind_tinh({}), 3)
    # gọi metric quan sát KHÔNG được đổi world-hash (Lớp-5, read-only)
    h_truoc = w.world_hash()
    res = research_metrics(w)
    h_sau = w.world_hash()
    assert h_truoc == h_sau
    assert isinstance(res, dict) and "credit_outstanding" in res
    # tích hợp: tick.py đã gắn research vào metrics_lich_su (ngoài world_hash)
    assert "research" in w.metrics_lich_su[-1]
    assert "monetary_share_by_value" in w.metrics_lich_su[-1]["research"]


def test_claim_symmetry_vay_the_chap():
    w = the_gioi_test(seed=11, giu_lai=2, thoc_moi_nguoi=1000)
    creditor, debtor = sorted(w.agents)[:2]
    hd = HopDong(
        id="H0001",
        cac_ben=[creditor, debtor],
        hinh_thuc="van_ban",
        thoi_han=10,
        the_chap=["thoc:200"],  # có thế chấp → secured
        dieu_khoan=[ClauseChuyenGiaoMotLan(
            tu=debtor, den=creditor, tai_san="thoc", so_luong=250.0, tai="dao_han")],
        trang_thai="hieu_luc",
        tick_ky=w.tick,
    )
    w.hop_dong[hd.id] = hd

    res = research_metrics(w)
    assert res["credit_outstanding"] == 250.0
    assert res["n_claims"] == 1
    assert res["secured_vs_unsecured"]["secured"] == 250.0
    assert res["secured_vs_unsecured"]["unsecured"] == 0.0

    # đối xứng theo cấu trúc: đúng một claim, creditor/debtor đúng chiều, và tổng
    # tài-sản-đòi-nợ của chủ nợ = tổng nghĩa-vụ của con nợ theo (đơn vị, khối lượng)
    claims = claims_view(w)
    assert len(claims) == 1
    c = claims[0]
    assert c["creditor"] == creditor and c["debtor"] == debtor
    assert c["unit"] == "thoc" and c["qty"] == 250.0
    doi_no_chu = sum(k["outstanding"] for k in claims if k["creditor"] == creditor)
    nghia_vu_con = sum(k["outstanding"] for k in claims if k["debtor"] == debtor)
    assert doi_no_chu == nghia_vu_con == 250.0


def test_giai_ngan_ky_ket_khong_tao_nghia_vu():
    # clause giải ngân tại ký kết đã thực thi lúc ký → KHÔNG còn outstanding
    w = the_gioi_test(seed=12, giu_lai=2, thoc_moi_nguoi=1000)
    creditor, debtor = sorted(w.agents)[:2]
    hd = HopDong(
        id="H0002",
        cac_ben=[creditor, debtor],
        hinh_thuc="mieng",
        thoi_han=10,
        dieu_khoan=[ClauseChuyenGiaoMotLan(
            tu=creditor, den=debtor, tai_san="thoc", so_luong=300.0, tai="ky_ket")],
        trang_thai="hieu_luc",
        tick_ky=w.tick,
    )
    w.hop_dong[hd.id] = hd
    res = research_metrics(w)
    assert res["credit_outstanding"] == 0.0
    assert res["n_claims"] == 0


def test_fiscal_honest_khi_chinh_tri_tat():
    w = the_gioi_test(seed=9, giu_lai=3, thoc_moi_nguoi=1200)
    w.cfg.raw()["chinh_tri"]["bat"] = False  # tắt toàn bộ tầng chính trị → không thuế
    chay_tick(w, mind_tinh({}), 2)
    res = w.metrics_lich_su[-1]["research"]
    assert res["tax_revenue"] == 0.0
    assert res["fiscal_balance"] == 0.0  # rebate/không thu → CONG_QUY = 0, không phantom


def test_monetary_share_zero_khi_khong_xu_duong_khi_co_xu():
    w = the_gioi_test(seed=13, giu_lai=2, thoc_moi_nguoi=1000)
    # không khớp lệnh nào → mẫu số 0 → undefined (None), KHÔNG bịa 0
    w.kl_thanh_toan_tick = {}
    assert research_metrics(w)["monetary_share_by_value"] is None
    # chỉ thanh toán bằng thóc → tiền tệ hóa theo giá trị = 0 (định nghĩa được)
    w.kl_thanh_toan_tick = {"thoc": 100.0}
    assert research_metrics(w)["monetary_share_by_value"] == 0.0
    # có thanh toán bằng xu → > 0
    w.kl_thanh_toan_tick = {"thoc": 100.0, "xu": 50.0}
    assert research_metrics(w)["monetary_share_by_value"] > 0.0


def test_monetary_share_khong_giam_khi_tang_giao_dich_xu():
    w = the_gioi_test(seed=14, giu_lai=2, thoc_moi_nguoi=1000)
    w.kl_thanh_toan_tick = {"thoc": 100.0, "xu": 50.0}
    s1 = research_metrics(w)["monetary_share_by_value"]
    w.kl_thanh_toan_tick = {"thoc": 100.0, "xu": 100.0}
    s2 = research_metrics(w)["monetary_share_by_value"]
    assert s2 >= s1 > 0.0


def test_ledger_scan_barter_trade_acceptance_va_traders():
    w = the_gioi_test(seed=3, giu_lai=2, thoc_moi_nguoi=1000)
    buyer, seller = sorted(w.agents)[:2]
    w.ledger.sinh(seller, "cong_cu", 2.0, "che_tac", "fixture", w.tick)
    w.kl_thanh_toan_tick = {}
    phien_cho(w, [
        Lenh(ai=buyer, chieu="mua", tai_san="cong_cu", so_luong=1.0, gia=10.0),
        Lenh(ai=seller, chieu="ban", tai_san="cong_cu", so_luong=1.0, gia=10.0),
    ])
    res = research_metrics(w)
    assert res["n_traders"] == 2  # đọc lại đúng cặp mua–bán từ ledger
    assert res["acceptance_breadth"] == 0.0  # không ai nhận xu (thanh toán bằng thóc)
    assert res["monetary_share_by_value"] == 0.0
    assert isinstance(res["price_dispersion_by_asset"], dict)  # coverage guard: 1 làng → {}


# ------------------------ observation state (ADR 0003 §E + 0004 §T07 C) -----------------

def _ban_cung(w, aids, giu=20.0):
    """Rút gần hết thóc để hộ đói (food_security<1 sau tiêu dùng)."""
    for aid in aids:
        sd = w.ledger.so_du(aid, "thoc")
        if sd > giu:
            w.ledger.huy(aid, "thoc", sd - giu, "an", "fixture bần cùng", w.tick)


def test_poverty_streak_tang_khi_doi_lien_tiep_reset_khi_du_an():
    w = the_gioi_test(seed=21, giu_lai=2, thoc_moi_nguoi=1000)
    kept = sorted(w.agents)[:2]
    _ban_cung(w, kept)
    chay_tick(w, mind_tinh({}), 2)  # đói 2 tick liên tiếp
    assert all(w.poverty_streak.get(h, 0) >= 2 for h in kept)
    for aid in kept:  # cấp thóc dư dả → đủ ăn → streak reset
        w.ledger.sinh(aid, "thoc", 3000.0, "khoi_tao", "fixture no đủ", w.tick)
    chay_tick(w, mind_tinh({}), 1)
    assert all(w.poverty_streak.get(h, 0) == 0 for h in kept)


def test_research_surface_poverty_va_failed_settlement():
    w = the_gioi_test(seed=71, giu_lai=3, thoc_moi_nguoi=800)
    w.poverty_streak = {"A0001": 5, "A0002": 3, "A0003": 0}
    w.settlement_fail_tick = 2
    res = research_metrics(w)
    assert res["poverty_duration"] == 4.0  # median{5,3}; hộ đủ ăn (0) không tính median
    assert res["n_ho_ngheo_keo_dai"] == 1  # cua_so_tick=4 → chỉ streak 5 >= 4
    assert res["failed_settlement"] == 2


def test_failed_settlement_dem_khi_dat_lenh_khong_du_hang():
    w = the_gioi_test(seed=31, giu_lai=2, thoc_moi_nguoi=1000)
    buyer, seller = sorted(w.agents)[:2]
    assert w.ledger.so_du(seller, "cong_cu") == 0.0  # seller rao bán thứ KHÔNG có
    w.settlement_fail_tick = 0
    phien_cho(w, [
        Lenh(ai=buyer, chieu="mua", tai_san="cong_cu", so_luong=1.0, gia=10.0),
        Lenh(ai=seller, chieu="ban", tai_san="cong_cu", so_luong=1.0, gia=10.0),
    ])
    assert w.settlement_fail_tick == 1  # LoiSoKep bị nuốt → đếm 1
    assert research_metrics(w)["failed_settlement"] == 1
    # KHÔNG đổi hành vi khớp: không giá nào được ghi cho cong_cu
    assert w.gia_gan_nhat("cong_cu") is None


def test_settlement_fail_tick_reset_moi_tick():
    w = the_gioi_test(seed=32, giu_lai=2, thoc_moi_nguoi=1000)
    w.settlement_fail_tick = 5  # bẩn từ trước
    chay_tick(w, mind_tinh({}), 1)  # tick không có khớp lỗi → reset về 0
    assert w.settlement_fail_tick == 0


def test_observation_state_khong_vao_world_hash():
    w = the_gioi_test(seed=42, giu_lai=3, thoc_moi_nguoi=800)
    chay_tick(w, mind_tinh({}), 3)
    h0 = w.world_hash()
    w.poverty_streak["A0001"] = 999  # bịa observation state
    w.settlement_fail_tick = 777
    assert w.world_hash() == h0  # observation state KHÔNG đụng hash/determinism


def test_replay_hai_run_cung_seed_trung_hash():
    w1 = the_gioi_test(seed=101, giu_lai=3, thoc_moi_nguoi=700)
    w2 = the_gioi_test(seed=101, giu_lai=3, thoc_moi_nguoi=700)
    chay_tick(w1, mind_tinh({}), 6)
    chay_tick(w2, mind_tinh({}), 6)
    assert w1.world_hash() == w2.world_hash()  # observation state không phá replay
    assert hasattr(w1, "poverty_streak") and hasattr(w1, "settlement_fail_tick")


def test_checkpoint_resume_giu_observation_state(tmp_path):
    w = the_gioi_test(seed=51, giu_lai=2, thoc_moi_nguoi=500)
    w.poverty_streak = {"A0001": 3}
    w.settlement_fail_tick = 7
    duong_dan = w.luu_checkpoint(tmp_path)
    w2 = World.nap_checkpoint(duong_dan)
    assert w2.poverty_streak == {"A0001": 3}
    assert w2.settlement_fail_tick == 7


def test_migration_checkpoint_cu_thieu_observation_state(tmp_path):
    w = the_gioi_test(seed=61, giu_lai=2, thoc_moi_nguoi=500)
    del w.poverty_streak  # giả lập checkpoint cũ (trước khi có field)
    del w.settlement_fail_tick
    duong_dan = w.luu_checkpoint(tmp_path)
    w2 = World.nap_checkpoint(duong_dan)
    assert w2.poverty_streak == {}  # migration default an toàn
    assert w2.settlement_fail_tick == 0
