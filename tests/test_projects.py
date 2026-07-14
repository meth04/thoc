"""P1 generic project/work-order accounting, without any LLM call."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import projects
from engine.audit import kiem_toan_the_gioi
from engine.config import load_config
from engine.intents import KeHoach
from engine.world import tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
LIVELIHOOD = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"


def _world():
    w = tao_the_gioi(load_config(overlays=[SPATIAL, LIVELIHOOD]), 307, events_path=None)
    owner, contributor = sorted(w.agents)[:2]
    parcel = next(p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    parcel.chu = owner
    recipe = w.cfg.raw()["san_xuat"]["recipe"]["nha"]
    return w, owner, contributor, parcel.id, float(recipe["go"]), float(recipe["cong"])


def _create_house(w, owner: str, site: str) -> str:
    projects.dang_ky_du_an(w, {
        owner: KeHoach(id=owner, tao_du_an=[{"loai_du_an": "nha", "thua": site}]),
    })
    assert set(w.du_an) == {"DA00001"}
    return "DA00001"


def _issue(w, aid: str, asset: str, amount: float) -> None:
    flow = "khai_thac" if asset == "go" else "sinh_cong"
    w.ledger.sinh(aid, asset, amount, flow, "fixture", w.tick)


def test_house_completes_only_after_multi_tick_material_and_labor_contributions():
    w, owner, worker, site, wood, labour = _world()
    w.tick = 1
    ref = _create_house(w, owner, site)
    _issue(w, worker, "go", wood)
    _issue(w, worker, "cong", labour)

    projects.buoc_du_an(w, {
        worker: KeHoach(
            id=worker,
            gop_vat_lieu_du_an=[{"ref": ref, "tai_san": "go", "so_luong": wood / 2}],
            gop_cong_du_an=[{"ref": ref, "so_cong": labour / 2}],
        ),
    })
    project = w.du_an[ref]
    assert project.trang_thai == "dang_lam"
    assert project.vat_lieu_da["go"] == pytest.approx(wood / 2)
    assert project.cong_da == pytest.approx(labour / 2)
    assert w.ledger.so_du(owner, "nha") == 0.0

    w.tick = 2
    projects.buoc_du_an(w, {
        worker: KeHoach(
            id=worker,
            gop_vat_lieu_du_an=[{"ref": ref, "tai_san": "go", "so_luong": wood}],
            gop_cong_du_an=[{"ref": ref, "so_cong": labour}],
        ),
    })

    assert project.trang_thai == "hoan_thanh"
    assert w.ledger.so_du(owner, "nha") == pytest.approx(1.0)
    assert w.agents[owner].nha_thua == site
    assert w.ledger.so_du(f"DU_AN:{ref}", "go") == pytest.approx(0.0)
    assert projects.kiem_tra_ky_quy(w) == []
    kiem_toan_the_gioi(w, len(w.parcels))


def test_partial_labor_never_overworks_and_keeps_progress_deterministic():
    w, owner, worker, site, _wood, labour = _world()
    w.tick = 1
    ref = _create_house(w, owner, site)
    _issue(w, worker, "cong", labour / 3)

    projects.buoc_du_an(w, {
        worker: KeHoach(id=worker, gop_cong_du_an=[{"ref": ref, "so_cong": labour}]),
    })

    project = w.du_an[ref]
    assert project.cong_da == pytest.approx(labour / 3)
    assert w.ledger.so_du(worker, "cong") == pytest.approx(0.0)
    assert any(tx.ly_do == f"góp công dự án {ref}" for tx in w.ledger.lich_su)


def test_cancel_and_expiry_refund_only_material_escrow_exactly_once():
    w, owner, worker, site, wood, _labour = _world()
    w.tick = 1
    ref = _create_house(w, owner, site)
    _issue(w, worker, "go", wood)
    before = w.ledger.so_du(worker, "go")
    projects.buoc_du_an(w, {
        worker: KeHoach(id=worker, gop_vat_lieu_du_an=[{
            "ref": ref, "tai_san": "go", "so_luong": wood / 2,
        }]),
    })
    assert w.ledger.so_du(worker, "go") == pytest.approx(before - wood / 2)

    projects.buoc_du_an(w, {owner: KeHoach(id=owner, huy_du_an=[ref])})
    assert w.du_an[ref].trang_thai == "da_huy"
    assert w.ledger.so_du(worker, "go") == pytest.approx(before)
    assert projects.kiem_tra_ky_quy(w) == []
    # A second cancellation cannot create a second refund.
    projects.buoc_du_an(w, {owner: KeHoach(id=owner, huy_du_an=[ref])})
    assert w.ledger.so_du(worker, "go") == pytest.approx(before)

    w2, owner2, worker2, site2, wood2, _ = _world()
    w2.cfg.raw()["du_an"]["han_tick"] = 1
    w2.tick = 1
    ref2 = _create_house(w2, owner2, site2)
    _issue(w2, worker2, "go", wood2)
    before2 = w2.ledger.so_du(worker2, "go")
    projects.buoc_du_an(w2, {worker2: KeHoach(id=worker2, gop_vat_lieu_du_an=[{
        "ref": ref2, "tai_san": "go", "so_luong": wood2 / 2,
    }])})
    w2.tick = 3
    projects.buoc_du_an(w2, {})
    assert w2.du_an[ref2].trang_thai == "het_han"
    assert w2.ledger.so_du(worker2, "go") == pytest.approx(before2)
    assert projects.kiem_tra_ky_quy(w2) == []


def test_contributor_death_cancels_and_returns_material_before_estate_path():
    w, owner, worker, site, wood, _labour = _world()
    w.tick = 1
    ref = _create_house(w, owner, site)
    _issue(w, worker, "go", wood)
    projects.buoc_du_an(w, {worker: KeHoach(id=worker, gop_vat_lieu_du_an=[{
        "ref": ref, "tai_san": "go", "so_luong": wood / 2,
    }])})
    assert w.ledger.so_du(f"DU_AN:{ref}", "go") == pytest.approx(wood / 2)

    w.agents[worker].con_song = False
    projects.xu_ly_nguoi_chet(w, worker)

    assert w.du_an[ref].trang_thai == "da_huy"
    assert w.ledger.so_du(f"DU_AN:{ref}", "go") == pytest.approx(0.0)
    assert w.ledger.so_du(worker, "go") == pytest.approx(wood)


def test_disabled_project_state_does_not_change_legacy_hash():
    w = tao_the_gioi(load_config(overlays=[SPATIAL]), 307, events_path=None)
    h0 = w.world_hash()
    w.du_an["DA00001"] = object()
    w._next_du_an = 99
    assert w.world_hash() == h0
