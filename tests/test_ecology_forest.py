"""P2 ecology regression tests for ``spatial_livelihood_v2``.

The tests assert physical/accounting mechanisms, not that an agent will choose a forestry
occupation. All worlds are local deterministic fixtures; no provider or network is involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import forest, production
from engine.config import load_config
from engine.intents import KeHoach
from engine.spatial import co_the_o_bo
from engine.world import _ga_rung_suc_chua, tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
LIVELIHOOD = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"


def _world(seed: int = 17):
    return tao_the_gioi(load_config(overlays=[SPATIAL, LIVELIHOOD]), seed, events_path=None)


def _agent(w) -> str:
    return next(aid for aid in sorted(w.agents) if w.agents[aid].con_song)


def _forest_reachable(w, aid: str):
    return next(
        p for p in sorted(w.parcels.values(), key=lambda q: q.id)
        if p.loai == "rung" and p.chu is None and co_the_o_bo(w, aid, p.bo)
    )


def _hill_reachable(w, aid: str):
    return next(
        p for p in sorted(w.parcels.values(), key=lambda q: q.id)
        if p.loai == "doi" and p.chu is None and co_the_o_bo(w, aid, p.bo)
    )


def _biomass(w) -> float:
    return sum(float(getattr(p, "sinh_khoi", 0.0)) for p in w.parcels.values())


def test_off_rung_dynamic_fields_khong_anh_huong_hash_legacy():
    """P2 fields are excluded from pre-v2 behavior/hash, including spatial_v1 control."""
    w = tao_the_gioi(load_config(overlays=[SPATIAL]), 17, events_path=None)
    h0 = w.world_hash()
    for p in w.parcels.values():
        p.sinh_khoi = 999.0
        p.tan_rung = 0.123
    assert w.world_hash() == h0


def test_v2_biomass_va_canopy_duoc_hash():
    w = _world()
    p = _forest_reachable(w, _agent(w))
    h0 = w.world_hash()
    p.sinh_khoi -= 1.0
    p.tan_rung = p.sinh_khoi / forest.sinh_khoi_toi_da(w)
    assert w.world_hash() != h0


def test_logging_chuyen_biomass_thanh_go_va_khong_doi_loai():
    w = _world()
    aid = _agent(w)
    p = _forest_reachable(w, aid)
    w.ledger.sinh(aid, "cong", 40.0, "sinh_cong", "fixture", w.tick)
    biomass_truoc = _biomass(w)
    go_truoc = w.ledger.so_du(aid, "go")

    go, cong = forest.khai_thac_go(w, aid, 20.0, 1.0)

    assert go == pytest.approx(cong)
    assert go > 0.0
    assert _biomass(w) == pytest.approx(biomass_truoc - go)
    assert w.ledger.so_du(aid, "go") == pytest.approx(go_truoc + go)
    assert p.loai == "rung", "logging does not turn a forest parcel into farmland"
    assert 0.0 <= p.tan_rung <= 1.0


def test_rung_can_kiet_khong_mint_go_hoac_tieu_cong():
    w = _world()
    aid = _agent(w)
    for p in w.parcels.values():
        if p.loai == "rung":
            p.sinh_khoi = p.tan_rung = 0.0
    w.ledger.sinh(aid, "cong", 25.0, "sinh_cong", "fixture", w.tick)
    cong_truoc, go_truoc = w.ledger.so_du(aid, "cong"), w.ledger.so_du(aid, "go")

    go, cong = forest.khai_thac_go(w, aid, 25.0, 1.0)

    assert (go, cong) == (0.0, 0.0)
    assert w.ledger.so_du(aid, "cong") == pytest.approx(cong_truoc)
    assert w.ledger.so_du(aid, "go") == pytest.approx(go_truoc)


def test_canopy_quyet_dinh_suc_chua_ga_rung_khong_phai_nhan_o():
    w = _world()
    k0 = _ga_rung_suc_chua(w)
    assert k0 > 0.0
    for p in w.parcels.values():
        if p.loai == "rung":
            p.sinh_khoi *= 0.5
            p.tan_rung *= 0.5
    assert _ga_rung_suc_chua(w) == pytest.approx(k0 * 0.5)


def test_khai_hoang_thu_hoi_go_va_xoa_canopy():
    w = _world()
    aid = _agent(w)
    p = _forest_reachable(w, aid)
    stock_truoc = p.sinh_khoi
    w.ledger.sinh(aid, "cong", 1_000.0, "sinh_cong", "fixture", w.tick)
    go_truoc = w.ledger.so_du(aid, "go")

    production.khai_hoang_dat(w, {aid: KeHoach(id=aid, khai_hoang=[p.id])})

    assert p.loai == "ruong"
    assert p.sinh_khoi == 0.0 and p.tan_rung == 0.0
    ty_le = w.cfg.get("khong_gian.rung.ty_le_go_thu_hoi_khai_hoang")
    assert w.ledger.so_du(aid, "go") == pytest.approx(go_truoc + stock_truoc * ty_le)


def test_tai_sinh_va_trong_rung_co_stock_that():
    w = _world()
    aid = _agent(w)
    p = _forest_reachable(w, aid)
    p.sinh_khoi = forest.sinh_khoi_toi_da(w) * 0.2
    p.tan_rung = 0.2
    forest.tai_sinh_rung(w)
    assert 0.2 < p.tan_rung <= 1.0

    hill = _hill_reachable(w, aid)
    w.ledger.sinh(aid, "cong", 1_000.0, "sinh_cong", "fixture", w.tick)
    forest.trong_rung_dat(w, {aid: KeHoach(id=aid, trong_rung=[hill.id])})
    assert hill.loai == "rung"
    assert hill.sinh_khoi == pytest.approx(
        forest.sinh_khoi_toi_da(w)
        * w.cfg.get("khong_gian.rung.trong_rung.ty_le_sinh_khoi_khoi_dau")
    )
    assert hill.tan_rung > 0.0


def test_cung_seed_cung_ecology_hash():
    a, b = _world(31), _world(31)
    for w in (a, b):
        aid = _agent(w)
        w.ledger.sinh(aid, "cong", 100.0, "sinh_cong", "fixture", w.tick)
        forest.tai_sinh_rung(w)
        forest.khai_thac_go(w, aid, 25.0, 1.0)
    assert a.world_hash() == b.world_hash()
