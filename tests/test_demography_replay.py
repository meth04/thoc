"""Checkpoint/replay contracts for active reproductive state."""

from __future__ import annotations

from pathlib import Path

from engine import demography, household
from engine.config import load_config
from engine.world import World, tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "agrarian_transition_v1"
SPATIAL = SCENARIO / "spatial_v1.yaml"
LIVELIHOOD = SCENARIO / "spatial_livelihood_v2.yaml"
REPRODUCTION = SCENARIO / "spatial_livelihood_v6.yaml"


def _world(seed: int):
    cfg = load_config(overlays=[SPATIAL, LIVELIHOOD, REPRODUCTION])
    w = tao_the_gioi(cfg, seed, events_path=None)
    mother = next(
        aid for aid in sorted(w.agents) if w.agents[aid].gioi_tinh == "nu"
    )
    father = next(
        aid for aid in sorted(w.agents) if w.agents[aid].gioi_tinh == "nam"
    )
    w.agents[mother].vo_chong = father
    w.agents[father].vo_chong = mother
    w.agents[mother].y_dinh_sinh_con = 1.0
    household.ghi_bien_co(w, "cuoi", a=mother, b=father)
    household.buoc_cu_tru(w, {})
    ss = w.cfg.raw()["nhan_khau"]["sinh_san"]
    ss["p_goc"] = 1.0
    ss["rui_ro_me"] = 0.0
    ss["p_sinh_doi"] = 0.0
    return w, mother, father


def test_checkpoint_pickle_carries_active_pregnancy_and_resumes_same_delivery(tmp_path):
    w, mother, _father = _world(seed=617)
    w.tick = 1
    demography.sinh_con(w, {})
    checkpoint = w.luu_checkpoint(tmp_path)

    uninterrupted_before = set(w.agents)
    for tick in (2, 3):
        w.tick = tick
        demography.sinh_con(w, {})

    resumed = World.nap_checkpoint(checkpoint, events_path=None, cfg=w.cfg)
    assert resumed.thai_ky == {
        mother: {
            "cha": w.agents[mother].vo_chong,
            "thu_thai_tick": 1,
            "sinh_tick": 3,
        }
    }
    resumed_before = set(resumed.agents)
    for tick in (2, 3):
        resumed.tick = tick
        demography.sinh_con(resumed, {})

    uninterrupted_children = sorted(set(w.agents) - uninterrupted_before)
    resumed_children = sorted(set(resumed.agents) - resumed_before)
    assert uninterrupted_children == resumed_children
    for child in uninterrupted_children:
        assert resumed.agents[child] == w.agents[child]
    assert resumed.thai_ky == w.thai_ky == {}
    assert resumed.hau_san == w.hau_san
    assert resumed.world_hash() == w.world_hash()


def test_active_reproductive_state_changes_world_hash():
    left, mother, father = _world(seed=619)
    right, _mother2, _father2 = _world(seed=619)
    left.thai_ky = {
        mother: {"cha": father, "thu_thai_tick": 1, "sinh_tick": 3},
    }
    left.hau_san = {}
    right.thai_ky = {}
    right.hau_san = {}
    assert left.world_hash() != right.world_hash()
