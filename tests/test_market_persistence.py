"""Versioned persistent call-auction book: invariants, negative cases, and replay."""

from __future__ import annotations

import copy
import json
import pickle
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.config import Config, load_config
from engine.entities import Entity
from engine.market import Lenh, phien_cho
from engine.world import World, tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "scenarios" / "agrarian_transition_v1" / "market_persistence_v1.yaml"


def _cfg(ttl: int | None = 3) -> Config:
    raw = copy.deepcopy(load_config().raw())
    if ttl is not None:
        raw["cho"] = {"lenh_ton_tai_tick": ttl}
    return Config(raw)


def _world(seed: int = 71, *, ttl: int | None = 3, events: Path | None = None):
    w = tao_the_gioi(_cfg(ttl), seed, events_path=events)
    return w, sorted(w.agents)


def _mint_go(w, owner: str, quantity: float) -> None:
    w.ledger.sinh(owner, "go", quantity, "khai_thac", "market fixture", w.tick)


def _events(path: Path, w) -> list[dict]:
    w.events.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_cross_tick_match_and_supply_demand_fill_event(tmp_path):
    event_path = tmp_path / "events.jsonl"
    w, (seller, buyer, *_) = _world(events=event_path)
    _mint_go(w, seller, 5.0)

    assert phien_cho(w, [Lenh(seller, "ban", "go", 5.0, 4.0)]) == 0.0
    assert [(order.id, order.so_luong) for order in w.lenh_cho] == [("LC000001", 5.0)]

    w.tick = 1
    assert phien_cho(w, [Lenh(buyer, "mua", "go", 5.0, 4.0)]) == pytest.approx(5.0)
    assert w.lenh_cho == []
    assert w.ledger.so_du(seller, "go") == pytest.approx(0.0)
    assert w.ledger.so_du(buyer, "go") == pytest.approx(5.0)

    summaries = [event for event in _events(event_path, w) if event["loai"] == "tong_hop_cho"]
    metric = summaries[-1]["theo_tai_san"]["go/thoc"]
    assert metric == {
        "lenh_mua": 1,
        "lenh_ban": 1,
        "kl_mua": 5.0,
        "kl_ban": 5.0,
        "cau": 5.0,
        "cung": 5.0,
        "kl_khop": 5.0,
        "fill_rate": 1.0,
        "fill_rate_cau": 1.0,
        "fill_rate_cung": 1.0,
    }


def test_partial_fill_reduces_only_settled_quantity():
    w, (seller, buyer, *_) = _world()
    _mint_go(w, seller, 10.0)
    phien_cho(w, [Lenh(seller, "ban", "go", 10.0, 2.0)])

    w.tick = 1
    assert phien_cho(w, [Lenh(buyer, "mua", "go", 4.0, 2.0)]) == pytest.approx(4.0)
    assert len(w.lenh_cho) == 1
    resting = w.lenh_cho[0]
    assert resting.id == "LC000001"
    assert resting.ai == seller and resting.chieu == "ban"
    assert resting.so_luong == pytest.approx(6.0)


def test_order_expires_after_exactly_configured_sessions(tmp_path):
    event_path = tmp_path / "events.jsonl"
    w, (seller, *_) = _world(events=event_path)
    _mint_go(w, seller, 2.0)

    phien_cho(w, [Lenh(seller, "ban", "go", 2.0, 3.0)])  # session 1: tick 0
    assert w.lenh_cho[0].het_han_tick == 2
    w.tick = 1
    phien_cho(w, [])  # session 2
    assert len(w.lenh_cho) == 1
    w.tick = 2
    phien_cho(w, [])  # session 3, then expiry
    assert w.lenh_cho == []

    expired = [event for event in _events(event_path, w) if event["loai"] == "lenh_het_han"]
    assert len(expired) == 1
    assert expired[0]["id"] == "LC000001"
    assert expired[0]["con_lai"] == pytest.approx(2.0)


@pytest.mark.parametrize("owner_kind", ["dead_agent", "dissolved_entity"])
def test_inactive_owner_order_is_removed_and_cannot_submit_again(tmp_path, owner_kind):
    event_path = tmp_path / f"{owner_kind}.jsonl"
    w, ids = _world(events=event_path)
    buyer = ids[2]
    if owner_kind == "dead_agent":
        owner = ids[0]
    else:
        owner = "E0999"
        w.entities[owner] = Entity(id=owner, ten="fixture", con_hoat_dong=True)
    _mint_go(w, owner, 5.0)
    phien_cho(w, [Lenh(owner, "ban", "go", 5.0, 2.0)])
    assert len(w.lenh_cho) == 1

    if owner_kind == "dead_agent":
        w.agents[owner].con_song = False
    else:
        w.entities[owner].con_hoat_dong = False
    w.tick = 1
    assert phien_cho(w, [
        Lenh(owner, "ban", "go", 1.0, 2.0),
        Lenh(buyer, "mua", "go", 5.0, 2.0),
    ]) == 0.0
    assert all(order.ai != owner for order in w.lenh_cho)
    assert w.ledger.so_du(buyer, "go") == 0.0

    events = _events(event_path, w)
    assert any(event["loai"] == "huy_lenh" and event["ai"] == owner for event in events)
    assert any(event["loai"] == "tu_choi_lenh" and event["ai"] == owner for event in events)


@pytest.mark.parametrize("owner", ["VO_THUA_NHAN", "DI_SAN:A0001"])
def test_void_or_estate_subject_cannot_open_market_order(owner):
    w, _ = _world()
    assert phien_cho(w, [Lenh(owner, "mua", "go", 1.0, 2.0)]) == 0.0
    assert w.lenh_cho == []
    assert w._next_lenh_cho == 0


def test_failed_settlement_does_not_consume_counterparty_or_order_quantity():
    w, (bad_seller, good_seller, buyer, *_) = _world()
    _mint_go(w, good_seller, 5.0)

    # The first seller has no wood. Both orders must remain unchanged after the failed pair.
    assert phien_cho(w, [
        Lenh(bad_seller, "ban", "go", 5.0, 2.0),
        Lenh(buyer, "mua", "go", 5.0, 2.0),
    ]) == 0.0
    assert {order.ai: order.so_luong for order in w.lenh_cho} == {
        bad_seller: 5.0,
        buyer: 5.0,
    }

    # A funded seller arriving next tick can still fill the buyer completely. The bad order
    # remains at 5 rather than stealing allocation or being decremented by a failed transaction.
    w.tick = 1
    assert phien_cho(w, [Lenh(good_seller, "ban", "go", 5.0, 2.0)]) == pytest.approx(5.0)
    assert w.ledger.so_du(buyer, "go") == pytest.approx(5.0)
    assert [(order.ai, order.so_luong) for order in w.lenh_cho] == [(bad_seller, 5.0)]
    assert w.settlement_fail_tick >= 2  # the unfunded resting order was tried once per session


@settings(max_examples=30, deadline=None)
@given(supply=st.integers(min_value=1, max_value=30), demand=st.integers(min_value=1, max_value=30))
def test_property_partial_fill_preserves_both_assets(supply: int, demand: int):
    w, (seller, buyer, *_) = _world(seed=101, ttl=4)
    _mint_go(w, seller, float(supply))
    go_before = w.ledger.tong_tai_san("go")
    thoc_before = w.ledger.tong_tai_san("thoc")

    filled = phien_cho(w, [
        Lenh(seller, "ban", "go", float(supply), 2.0),
        Lenh(buyer, "mua", "go", float(demand), 2.0),
    ])
    expected = float(min(supply, demand))
    assert filled == pytest.approx(expected)
    assert w.ledger.tong_tai_san("go") == pytest.approx(go_before)
    assert w.ledger.tong_tai_san("thoc") == pytest.approx(thoc_before)
    assert w.ledger.so_du(buyer, "go") == pytest.approx(expected)
    assert sum(order.so_luong for order in w.lenh_cho) == pytest.approx(abs(supply - demand))


def test_same_seed_checkpoint_resume_preserves_order_book_hash(tmp_path):
    cfg = _cfg(3)
    continuous = tao_the_gioi(cfg, 211)
    seller, buyer = sorted(continuous.agents)[:2]
    _mint_go(continuous, seller, 6.0)
    phien_cho(continuous, [Lenh(seller, "ban", "go", 6.0, 3.0)])
    continuous.tick = 1

    duplicate = tao_the_gioi(cfg, 211)
    _mint_go(duplicate, seller, 6.0)
    phien_cho(duplicate, [Lenh(seller, "ban", "go", 6.0, 3.0)])
    duplicate.tick = 1
    assert duplicate.world_hash() == continuous.world_hash()

    checkpoint = continuous.luu_checkpoint(tmp_path / "checkpoints")
    resumed = World.nap_checkpoint(checkpoint, cfg=cfg)
    assert resumed.world_hash() == continuous.world_hash()
    assert resumed.lenh_cho[0].id == "LC000001"

    buy = Lenh(buyer, "mua", "go", 4.0, 3.0)
    phien_cho(continuous, [buy])
    phien_cho(resumed, [Lenh(buyer, "mua", "go", 4.0, 3.0)])
    phien_cho(duplicate, [Lenh(buyer, "mua", "go", 4.0, 3.0)])
    assert resumed.world_hash() == continuous.world_hash() == duplicate.world_hash()


def test_ttl_one_or_absent_keeps_legacy_path_and_hash():
    legacy, (seller, *_) = _world(seed=313, ttl=None)
    explicit_one, _ = _world(seed=313, ttl=1)
    assert legacy.world_hash() == explicit_one.world_hash()
    assert "persistent_orders" not in legacy.behavioral_state()["market"]
    assert "persistent_orders" not in explicit_one.behavioral_state()["market"]

    for w in (legacy, explicit_one):
        _mint_go(w, seller, 1.0)
        phien_cho(w, [Lenh(seller, "ban", "go", 1.0, 2.0)])
        assert w.lenh_cho == []
        assert w._next_lenh_cho == 0
    assert legacy.world_hash() == explicit_one.world_hash()


def test_checkpoint_migration_only_materializes_book_when_ttl_active(tmp_path):
    active, _ = _world(seed=401, ttl=3)
    del active.lenh_cho
    del active._next_lenh_cho
    active_path = tmp_path / "active-old.pkl"
    with open(active_path, "wb") as handle:
        pickle.dump(active, handle)
    migrated = World.nap_checkpoint(active_path, cfg=_cfg(3))
    assert migrated.lenh_cho == [] and migrated._next_lenh_cho == 0

    legacy, _ = _world(seed=402, ttl=1)
    legacy_hash = legacy.world_hash()
    del legacy.lenh_cho
    del legacy._next_lenh_cho
    legacy_path = tmp_path / "legacy-old.pkl"
    with open(legacy_path, "wb") as handle:
        pickle.dump(legacy, handle)
    loaded_legacy = World.nap_checkpoint(legacy_path, cfg=_cfg(1))
    assert "lenh_cho" not in vars(loaded_legacy)
    assert "_next_lenh_cho" not in vars(loaded_legacy)
    assert loaded_legacy.world_hash() == legacy_hash


def test_overlay_declares_ttl_without_editing_legacy_artifacts():
    cfg = load_config(overlays=[OVERLAY])
    assert cfg.get("cho.lenh_ton_tai_tick") == 3
