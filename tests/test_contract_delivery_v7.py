"""ADR 0009 §4.3/§6/§9 — v7 contract delivery and signing atomicity."""

from __future__ import annotations

import copy

import pytest

from engine.config import Config, load_config
from engine.contracts import ClauseChuyenGiaoMotLan, ClauseGopCong, HopDong
from engine.world import tao_the_gioi
from tests.helpers import chay_tick, mind_tinh


def _world(*, delivery_v2: bool, seed: int = 811):
    raw = copy.deepcopy(load_config().raw())
    if delivery_v2:
        raw.setdefault("hop_dong", {})["gop_cong_lich"] = "signing_tick_half_open_v2"
        raw["hop_dong"]["tiep_can_vat_ly_v2"] = True
    w = tao_the_gioi(Config(raw), seed, events_path=None)
    ids = sorted(w.agents)
    for aid in ids[2:]:
        agent = w.agents[aid]
        agent.con_song = False
        amount = w.ledger.so_du(aid, "thoc")
        if amount > 0:
            w.ledger.huy(aid, "thoc", amount, "an", "fixture inactive", 0)
    for aid in ids[:2]:
        w.agents[aid].tuoi_tick = 40.0
        w.agents[aid].health = 100.0
    return w, ids[0], ids[1]


def _oral_food_for_labor(requester: str, responder: str) -> HopDong:
    return HopDong(
        cac_ben=[requester, responder], hinh_thuc="mieng", thoi_han=1,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(
                tu=responder, den=requester, tai_san="thoc", so_luong=25.0, tai="ky_ket"
            ),
            ClauseGopCong(tu=requester, den=responder, so_cong_moi_tick=40.0),
        ],
    )


def _sign_after_one_offer_tick(w, requester: str, responder: str) -> None:
    proposal = _oral_food_for_labor(requester, responder)
    plans: dict[int, dict] = {
        1: {requester: __import__("engine.intents", fromlist=["KeHoach"]).KeHoach(
            id=requester, de_nghi_hop_dong=[(proposal, responder)]
        )},
    }
    mind = mind_tinh(plans)
    chay_tick(w, mind, 1)  # proposal at t
    dn_id = next(iter(w.bang_rao))
    plans[2] = {responder: __import__("engine.intents", fromlist=["KeHoach"]).KeHoach(
        id=responder, tra_loi_de_nghi={dn_id: "chap_nhan"}
    )}
    chay_tick(w, mind, 1)  # acceptance and settlement/labor at t+1


def _contract_transactions(w, prefix: str):
    return [tx for tx in w.ledger.lich_su if tx.ly_do.startswith(prefix)]


def test_s4_v7_oral_food_signs_then_contributes_labor_once_and_audits():
    """Food settles at t+1 before phase-5 labor; K=1 has exactly one contribution."""
    w, requester, responder = _world(delivery_v2=True)
    _sign_after_one_offer_tick(w, requester, responder)

    signing = _contract_transactions(w, "ký kết ")
    labor = _contract_transactions(w, "góp công ")
    assert len(signing) == 1
    assert len(signing[0].but_toan) == 2
    assert signing[0].but_toan[0].chu_the == responder
    assert signing[0].but_toan[0].so_luong == pytest.approx(-25.0)
    assert signing[0].but_toan[1].chu_the == requester
    assert signing[0].but_toan[1].so_luong == pytest.approx(25.0)
    assert len(labor) == 1 and labor[0].tick == signing[0].tick == 2
    assert w.ledger.lich_su.index(signing[0]) < w.ledger.lich_su.index(labor[0])

    chay_tick(w, mind_tinh({}), 1)
    assert len(_contract_transactions(w, "góp công ")) == 1
    from engine.audit import kiem_toan

    kiem_toan(w.ledger, w.tick)


def test_s4_legacy_schedule_is_unchanged_without_both_v7_keys():
    """The historical schedule still delivers at signing and once at age == K."""
    w, requester, responder = _world(delivery_v2=False)
    _sign_after_one_offer_tick(w, requester, responder)
    chay_tick(w, mind_tinh({}), 1)
    assert len(_contract_transactions(w, "góp công ")) == 2


def test_s5_v7_directed_offer_cannot_teleport_food_or_labor_between_villages():
    from engine import board
    from engine.contracts import delivery_failure_code

    w, requester, responder = _world(delivery_v2=True)
    w.agents[responder].lang = 1
    before = dict(w.ledger._so_du)
    offer = _oral_food_for_labor(requester, responder)
    assert delivery_failure_code(w, responder, requester) == "delivery_unreachable"

    ref = board.dang_de_nghi(w, requester, offer, responder)
    assert ref is not None, "a directed offer may carry information"
    w.bang_rao[ref].tra_loi[responder] = "chap_nhan"
    board.khop_bang_rao(w)

    assert w.ledger._so_du == before
    assert not w.hop_dong
    assert w._next_hd == 0
    assert not any(ts.startswith("vi_the:") for _owner, ts in w.ledger._so_du)


def test_s10_v7_partial_signing_failure_is_one_transaction_with_no_state_change():
    from engine.board import _ky_hop_dong

    w, a, b = _world(delivery_v2=True)
    # The first leg is solvent, the second is not.  Sequential reversal is forbidden.
    w.ledger.sinh(a, "go", 3.0, "khai_thac", "fixture", w.tick)
    hd = HopDong(
        cac_ben=[a, b], hinh_thuc="mieng", thoi_han=2,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(tu=b, den=a, tai_san="thoc", so_luong=10.0, tai="ky_ket"),
            ClauseChuyenGiaoMotLan(tu=a, den=b, tai_san="go", so_luong=5.0, tai="ky_ket"),
        ],
    )
    before_balances = dict(w.ledger._so_du)
    before_history = list(w.ledger.lich_su)
    assert _ky_hop_dong(w, hd) is False

    assert w.ledger._so_du == before_balances
    assert w.ledger.lich_su == before_history
    assert not w.hop_dong and w._next_hd == 0
    assert hd.id == "" and hd.tick_ky == -1
    assert not any(ts.startswith("vi_the:") for _owner, ts in w.ledger._so_du)


def test_v7_signing_path_is_deterministic_and_ledger_audited():
    worlds = [_world(delivery_v2=True, seed=919)[0] for _ in range(2)]
    for w in worlds:
        requester, responder = sorted(w.agents)[:2]
        _sign_after_one_offer_tick(w, requester, responder)
        chay_tick(w, mind_tinh({}), 1)
        from engine.audit import kiem_toan

        kiem_toan(w.ledger, w.tick)
    assert worlds[0].world_hash() == worlds[1].world_hash()


def test_s5_v7_active_remote_labor_clause_breaches_without_teleporting_labor():
    from engine.board import _ky_hop_dong
    from engine.contracts import gop_cong_dau_san_xuat
    from engine.production import sinh_cong

    w, worker, recipient = _world(delivery_v2=True)
    w.agents[recipient].lang = 1
    hd = HopDong(
        cac_ben=[worker, recipient], hinh_thuc="mieng", thoi_han=2,
        dieu_khoan=[ClauseGopCong(tu=worker, den=recipient, so_cong_moi_tick=40.0)],
    )
    assert _ky_hop_dong(w, hd)
    sinh_cong(w)
    recipient_before = w.ledger.so_du(recipient, "cong")
    gop_cong_dau_san_xuat(w)

    assert w.ledger.so_du(recipient, "cong") == pytest.approx(recipient_before)
    assert w.hop_dong[hd.id].trang_thai == "vi_pham"
    from engine.audit import kiem_toan

    kiem_toan(w.ledger, w.tick)
