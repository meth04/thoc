"""P3 bilateral quote/escrow state machine (local deterministic tests)."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import quotes
from engine.config import load_config
from engine.intents import KeHoach
from engine.world import tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
LIVELIHOOD = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"


def _world(seed: int = 73):
    w = tao_the_gioi(load_config(overlays=[SPATIAL, LIVELIHOOD]), seed, events_path=None)
    seller, buyer = sorted(w.agents)[:2]
    w.ledger.sinh(seller, "go", 20.0, "khai_thac", "fixture", 0)
    w.ledger.sinh(buyer, "thoc", 1_000.0, "khoi_tao", "fixture", 0)
    w.tick = 1
    return w, seller, buyer


def _ask(qty: float = 4.0, price: float = 10.0, delivery: str = "ngay") -> dict:
    return {
        "chieu": "ban", "tai_san": "go", "so_luong": qty, "don_gia": price,
        "thanh_toan": "thoc", "doi_tac": None, "giao_tai": delivery,
    }


def test_spot_quote_settles_exactly_once_va_ky_quy_bang_0():
    w, seller, buyer = _world()
    go_ban, thoc_mua = w.ledger.so_du(seller, "go"), w.ledger.so_du(buyer, "thoc")
    plans = {
        seller: KeHoach(id=seller, dang_bao_gia=[_ask()]),
        buyer: KeHoach(id=buyer, chap_nhan_bao_gia=[{"ref": "BG00001", "so_luong": 4.0}]),
    }

    quotes.buoc_bao_gia(w, plans)

    q = w.bao_gia["BG00001"]
    assert q.trang_thai == "hoan_thanh"
    assert w.ledger.so_du(seller, "go") == pytest.approx(go_ban - 4.0)
    assert w.ledger.so_du(buyer, "go") == pytest.approx(4.0)
    assert w.ledger.so_du(buyer, "thoc") == pytest.approx(thoc_mua - 40.0)
    assert w.ledger.so_du(seller, "thoc") >= 40.0
    assert quotes.kiem_tra_ky_quy(w) == []

    h0 = w.world_hash()
    quotes.giao_hang_den_han(w)  # a second call cannot settle a spot fill twice
    assert w.world_hash() == h0


def test_double_spend_bi_chan_tai_luc_dang_bao_gia():
    w, seller, buyer = _world()
    w.ledger.chuyen(seller, buyer, "go", w.ledger.so_du(seller, "go") - 4.0,
                     "fixture transfer", w.tick)
    quotes.buoc_bao_gia(w, {
        seller: KeHoach(id=seller, dang_bao_gia=[_ask(), _ask()]),
    })
    assert len(w.bao_gia) == 1
    assert w.ledger.so_du(seller, "go") == pytest.approx(0.0)
    assert quotes.kiem_tra_ky_quy(w) == []


def test_quote_expiry_hoan_ky_quy_chua_khop():
    w, seller, _buyer = _world()
    go0 = w.ledger.so_du(seller, "go")
    w.cfg.raw()["thuong_mai"]["bao_gia"]["het_han_tick"] = 1
    quotes.buoc_bao_gia(w, {seller: KeHoach(id=seller, dang_bao_gia=[_ask()])})
    assert w.ledger.so_du(seller, "go") == pytest.approx(go0 - 4.0)

    w.tick = 3
    quotes.buoc_bao_gia(w, {})
    q = w.bao_gia["BG00001"]
    assert q.trang_thai == "het_han"
    assert w.ledger.so_du(seller, "go") == pytest.approx(go0)
    assert quotes.kiem_tra_ky_quy(w) == []


def test_forward_quote_giu_hai_ben_trong_ky_quy_toi_ngay_giao():
    w, seller, buyer = _world()
    seller_go, buyer_thoc = w.ledger.so_du(seller, "go"), w.ledger.so_du(buyer, "thoc")
    quotes.buoc_bao_gia(w, {
        seller: KeHoach(id=seller, dang_bao_gia=[_ask(delivery="tick:3")]),
        buyer: KeHoach(id=buyer, chap_nhan_bao_gia=[{"ref": "BG00001", "so_luong": 4.0}]),
    })
    q = w.bao_gia["BG00001"]
    assert q.trang_thai == "da_khop"
    assert w.ledger.so_du(buyer, "go") == 0.0
    assert w.ledger.so_du(seller, "go") == pytest.approx(seller_go - 4.0)
    assert w.ledger.so_du(buyer, "thoc") == pytest.approx(buyer_thoc - 40.0)
    assert quotes.kiem_tra_ky_quy(w) == []

    w.tick = 2
    quotes.giao_hang_den_han(w)
    assert w.ledger.so_du(buyer, "go") == 0.0
    w.tick = 3
    quotes.giao_hang_den_han(w)
    assert q.trang_thai == "hoan_thanh"
    assert w.ledger.so_du(buyer, "go") == pytest.approx(4.0)
    assert quotes.kiem_tra_ky_quy(w) == []


def test_settlement_failure_refunds_counterparty_escrow_instead_of_stranding_it():
    w, seller, buyer = _world()
    buyer_thoc = w.ledger.so_du(buyer, "thoc")
    quotes.buoc_bao_gia(w, {
        seller: KeHoach(id=seller, dang_bao_gia=[_ask(delivery="tick:3")]),
        buyer: KeHoach(id=buyer, chap_nhan_bao_gia=[{"ref": "BG00001", "so_luong": 4.0}]),
    })
    q = w.bao_gia["BG00001"]
    # Fixture a stale/corrupt escrow *without* breaking ledger conservation.
    # The recovery path must return the buyer's payment rather than leaving it
    # in a non-active holder.
    w.ledger.chuyen("KY_QUY:BG00001", seller, "go", 4.0, "fixture stale escrow", w.tick)
    w.tick = 3
    quotes.giao_hang_den_han(w)

    assert q.fills[0].status == "failed"
    assert q.trang_thai == "da_huy"
    assert w.ledger.so_du(buyer, "thoc") == pytest.approx(buyer_thoc)
    assert w.ledger.so_du(q.fills[0].counterparty_holder, "thoc") == pytest.approx(0.0)
    assert quotes.kiem_tra_ky_quy(w) == []


def test_death_before_forward_delivery_releases_both_escrows_for_estate_path():
    w, seller, buyer = _world()
    seller_go, buyer_thoc = w.ledger.so_du(seller, "go"), w.ledger.so_du(buyer, "thoc")
    quotes.buoc_bao_gia(w, {
        seller: KeHoach(id=seller, dang_bao_gia=[_ask(delivery="tick:3")]),
        buyer: KeHoach(id=buyer, chap_nhan_bao_gia=[{"ref": "BG00001", "so_luong": 4.0}]),
    })
    q = w.bao_gia["BG00001"]
    w.agents[seller].con_song = False
    quotes.xu_ly_nguoi_chet(w, seller)

    assert q.trang_thai == "da_huy"
    assert q.fills[0].status == "failed"
    assert w.ledger.so_du(seller, "go") == pytest.approx(seller_go)
    assert w.ledger.so_du(buyer, "thoc") == pytest.approx(buyer_thoc)
    assert quotes.kiem_tra_ky_quy(w) == []


def test_chi_nguoi_dang_moi_huy_duoc_quote_va_legacy_hash_khong_doi():
    w, seller, buyer = _world()
    quotes.buoc_bao_gia(w, {seller: KeHoach(id=seller, dang_bao_gia=[_ask()])})
    quotes.buoc_bao_gia(w, {buyer: KeHoach(id=buyer, huy_bao_gia=["BG00001"])})
    assert w.bao_gia["BG00001"].trang_thai == "dang_treo"
    quotes.buoc_bao_gia(w, {seller: KeHoach(id=seller, huy_bao_gia=["BG00001"])})
    assert w.bao_gia["BG00001"].trang_thai == "da_huy"
    assert quotes.kiem_tra_ky_quy(w) == []

    legacy = tao_the_gioi(load_config(overlays=[SPATIAL]), 73, events_path=None)
    h0 = legacy.world_hash()
    legacy.bao_gia["BG00001"] = object()
    legacy._next_bao_gia = 99
    assert legacy.world_hash() == h0
