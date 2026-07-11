"""Unit test call auction: giá & khối lượng đúng đáp án tay; không khớp quá cung/cầu."""

from __future__ import annotations

import pytest

from engine.market import Lenh, NiemYetDat, phien_cho, phien_dat
from tests.helpers import the_gioi_test


def lam_the_gioi_go():
    w = the_gioi_test(seed=3, giu_lai=4, thoc_moi_nguoi=2000)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    for aid in ids:
        w.ledger.sinh(aid, "go", 20.0, "khai_thac", "fixture gỗ", 0)
    return w, ids


def test_auction_dap_an_tay():
    """B1 mua 6@15, B2 mua 6@9; A1 bán 10@8 → p*=9, khớp 10, pro-rata 5/5."""
    w, (a1, b1, b2, _) = lam_the_gioi_go()
    thoc_b1 = w.ledger.so_du(b1, "thoc")
    lenh = [
        Lenh(b1, "mua", "go", 6, 15.0),
        Lenh(b2, "mua", "go", 6, 9.0),
        Lenh(a1, "ban", "go", 10, 8.0),
    ]
    kl = phien_cho(w, lenh)
    assert kl == pytest.approx(10.0)
    assert w.gia_gan_nhat("go") == pytest.approx(9.0)
    # pro-rata bên cầu (12 muốn, 10 có): mỗi bên 5/6 phần
    assert w.ledger.so_du(b1, "go") == pytest.approx(20 + 5.0)
    assert w.ledger.so_du(b2, "go") == pytest.approx(20 + 5.0)
    assert w.ledger.so_du(a1, "go") == pytest.approx(10.0)
    assert w.ledger.so_du(b1, "thoc") == pytest.approx(thoc_b1 - 45.0)
    assert w.ledger.so_du(a1, "thoc") == pytest.approx(2000 + 90.0)


def test_khong_khop_qua_cung_cau():
    w, (a1, a2, b1, _) = lam_the_gioi_go()
    lenh = [
        Lenh(b1, "mua", "go", 100, 20.0),  # cầu 100 nhưng cung chỉ 7
        Lenh(a1, "ban", "go", 4, 10.0),
        Lenh(a2, "ban", "go", 3, 12.0),
    ]
    kl = phien_cho(w, lenh)
    assert kl <= 7.0 + 1e-9
    assert w.ledger.so_du(a1, "go") >= 20 - 4 - 1e-9
    assert w.ledger.so_du(a2, "go") >= 20 - 3 - 1e-9


def test_khong_giao_giá_thi_khong_khop():
    w, (a1, b1, _, _) = lam_the_gioi_go()
    kl = phien_cho(w, [Lenh(b1, "mua", "go", 5, 5.0), Lenh(a1, "ban", "go", 5, 9.0)])
    assert kl == 0.0
    assert w.gia_gan_nhat("go") is None


def test_nguoi_mua_thieu_thoc_khong_pha_bao_toan():
    w, (a1, b1, _, _) = lam_the_gioi_go()
    # b1 chỉ còn 10 thóc nhưng dám bid 50 gỗ × 9
    du = w.ledger.so_du(b1, "thoc") - 10
    w.ledger.huy(b1, "thoc", du, "an", "fixture nghèo", 0)
    phien_cho(w, [Lenh(b1, "mua", "go", 50, 9.0), Lenh(a1, "ban", "go", 20, 9.0)])
    assert w.ledger.so_du(b1, "thoc") >= -1e-9  # không âm — phần thiếu bị hủy khớp


def test_sealed_bid_dat_3_bid_thang_cao_nhat():
    """(e) một thửa 3 bid → bán đúng bid cao nhất ≥ ask."""
    w = the_gioi_test(seed=3, giu_lai=4, thoc_moi_nguoi=5000)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    chu, b1, b2, b3 = ids
    thua = next(p for p in w.parcels.values() if p.loai == "ruong")
    thua.chu = chu
    ny = {thua.id: NiemYetDat(thua.id, chu, 400.0, 0)}
    phien_dat(w, ny, [(b1, thua.id, 450.0), (b2, thua.id, 900.0), (b3, thua.id, 600.0)])
    assert w.parcels[thua.id].chu == b2  # bid cao nhất thắng
    assert w.ledger.so_du(b2, "thoc") == pytest.approx(5000 - 900)
    assert w.ledger.so_du(chu, "thoc") == pytest.approx(5000 + 900)
    assert thua.id not in ny


def test_sealed_bid_duoi_ask_khong_ban():
    w = the_gioi_test(seed=3, giu_lai=2, thoc_moi_nguoi=5000)
    chu, b1 = sorted(a for a, ag in w.agents.items() if ag.con_song)
    thua = next(p for p in w.parcels.values() if p.loai == "ruong")
    thua.chu = chu
    ny = {thua.id: NiemYetDat(thua.id, chu, 1000.0, 0)}
    phien_dat(w, ny, [(b1, thua.id, 800.0)])
    assert w.parcels[thua.id].chu == chu
    assert thua.id in ny  # còn niêm yết chờ chủ hạ giá/rút
