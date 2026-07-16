"""Versioned conception → gestation → delivery → postpartum contracts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from engine import demography, household, metrics_demography
from engine.config import load_config
from engine.world import tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "agrarian_transition_v1"
SPATIAL = SCENARIO / "spatial_v1.yaml"
LIVELIHOOD = SCENARIO / "spatial_livelihood_v2.yaml"
REPRODUCTION = SCENARIO / "spatial_livelihood_v6.yaml"
PROVENANCE = SCENARIO / "provenance.csv"


def _world(seed: int = 613, events_path: Path | None = None):
    cfg = load_config(overlays=[SPATIAL, LIVELIHOOD, REPRODUCTION])
    w = tao_the_gioi(cfg, seed, events_path=events_path)
    women = [aid for aid in sorted(w.agents) if w.agents[aid].gioi_tinh == "nu"]
    men = [aid for aid in sorted(w.agents) if w.agents[aid].gioi_tinh == "nam"]
    mother, father = women[0], men[0]
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


def _new_children(w, before: set[str]) -> list[str]:
    return sorted(set(w.agents) - before)


def _events(path: Path, w) -> list[dict]:
    w.events.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_config_gate_only_active_in_versioned_agrarian_overlay():
    base = load_config()
    assert "thai_ky_tick" not in base.get("nhan_khau.sinh_san")

    active = load_config(overlays=[SPATIAL, REPRODUCTION])
    ss = active.get("nhan_khau.sinh_san")
    assert ss["thai_ky_tick"] == 2
    assert ss["khoang_cach_sinh_toi_thieu_tick"] == 3
    assert ss["p_sinh_doi"] == pytest.approx(0.02)

    with PROVENANCE.open(encoding="utf-8", newline="") as handle:
        rows = {row["parameter"]: row for row in csv.DictReader(handle)}
    for key in (
        "nhan_khau.sinh_san.thai_ky_tick",
        "nhan_khau.sinh_san.khoang_cach_sinh_toi_thieu_tick",
        "nhan_khau.sinh_san.p_sinh_doi",
    ):
        assert rows[key]["status"] == "design_assumption"
        assert rows[key]["notes"]


@pytest.mark.parametrize(("key", "value"), [
    ("thai_ky_tick", 0),
    ("thai_ky_tick", 1.5),
    ("khoang_cach_sinh_toi_thieu_tick", -1),
    ("p_sinh_doi", 1.01),
])
def test_invalid_reproduction_config_fails_closed(key, value):
    w, _mother, _father = _world()
    w.cfg.raw()["nhan_khau"]["sinh_san"][key] = value
    with pytest.raises(ValueError):
        demography.sinh_con(w, {})


def test_conception_waits_until_due_tick_then_enters_postpartum(tmp_path):
    event_path = tmp_path / "events.jsonl"
    w, mother, father = _world(events_path=event_path)
    before = set(w.agents)

    w.tick = 1
    demography.sinh_con(w, {})
    assert _new_children(w, before) == []
    assert w.thai_ky[mother] == {
        "cha": father,
        "thu_thai_tick": 1,
        "sinh_tick": 3,
    }

    w.tick = 2
    demography.sinh_con(w, {})
    assert _new_children(w, before) == []

    w.tick = 3
    demography.sinh_con(w, {})
    children = _new_children(w, before)
    assert len(children) == 1
    assert mother not in w.thai_ky
    assert w.hau_san[mother] == 6

    rows = _events(event_path, w)
    assert [row["loai"] for row in rows].count("thu_thai") == 1
    births = [row for row in rows if row["loai"] == "sinh" and row.get("me") == mother]
    assert len(births) == 1
    assert any(
        row["loai"] == "hau_san_bat_dau"
        and row["duoc_thu_thai_lai_tu_tick"] == 6
        for row in rows
    )


def test_postpartum_enforces_five_tick_minimum_between_deliveries():
    w, mother, _father = _world()
    first_population = set(w.agents)

    for tick in (1, 2, 3):
        w.tick = tick
        demography.sinh_con(w, {})
    first_children = _new_children(w, first_population)
    assert len(first_children) == 1

    for tick in (4, 5):
        w.tick = tick
        demography.sinh_con(w, {})
        assert mother not in w.thai_ky

    w.tick = 6
    demography.sinh_con(w, {})
    assert w.thai_ky[mother]["sinh_tick"] == 8

    w.tick = 7
    demography.sinh_con(w, {})
    assert len(_new_children(w, first_population)) == 1

    w.tick = 8
    demography.sinh_con(w, {})
    assert len(_new_children(w, first_population)) == 2

    m = metrics_demography.tinh(w)
    spacing = m["sinh_san"]["khoang_cach_ca_sinh"]
    assert spacing["n_khoang"] == 1
    assert spacing["min_tick"] == 5
    assert spacing["min_nam"] == pytest.approx(5 / 3)


def test_twins_are_two_live_births_one_delivery_and_one_event(tmp_path):
    event_path = tmp_path / "events.jsonl"
    w, mother, _father = _world(events_path=event_path)
    w.cfg.raw()["nhan_khau"]["sinh_san"]["p_sinh_doi"] = 1.0
    before = set(w.agents)

    for tick in (1, 2, 3):
        w.tick = tick
        demography.sinh_con(w, {})

    children = _new_children(w, before)
    assert len(children) == 2
    rows = _events(event_path, w)
    twin = [row for row in rows if row["loai"] == "sinh_doi"]
    assert len(twin) == 1
    assert twin[0]["cac_con"] == children
    assert twin[0]["so_con"] == 2
    births = [row for row in rows if row["loai"] == "sinh" and row.get("me") == mother]
    assert len(births) == 2

    m = metrics_demography.tinh(w)["sinh_san"]
    assert m["tre_sinh_song_tick"] == 2
    assert m["ca_sinh_tick"] == 1
    assert m["ca_sinh_doi_tick"] == 1
    assert m["khoang_cach_ca_sinh"]["n_khoang"] == 0


def test_father_death_during_gestation_does_not_cancel_birth_or_mutate_dead_memory():
    w, mother, father = _world()
    before = set(w.agents)
    w.tick = 1
    demography.sinh_con(w, {})

    w.agents[father].con_song = False
    memory_before = list(w.agents[father].ky_uc_doi)
    w.tick = 3
    demography.sinh_con(w, {})

    children = _new_children(w, before)
    assert len(children) == 1
    assert w.agents[children[0]].cha == father
    assert w.agents[father].ky_uc_doi == memory_before
    assert mother not in w.thai_ky


def test_mother_death_before_due_cancels_pregnancy_and_removes_ghost_state(tmp_path):
    event_path = tmp_path / "events.jsonl"
    w, mother, _father = _world(events_path=event_path)
    before = set(w.agents)
    w.tick = 1
    demography.sinh_con(w, {})

    w.tick = 2
    w.agents[mother].health = 0.0
    assert mother in demography.cai_chet(w)
    assert mother not in w.thai_ky
    assert mother not in w.hau_san
    assert _new_children(w, before) == []

    rows = _events(event_path, w)
    ended = [row for row in rows if row["loai"] == "thai_ky_ket_thuc"]
    assert len(ended) == 1
    assert ended[0]["me"] == mother
    assert ended[0]["ly_do"] == "me_mat"


def test_maternal_death_at_delivery_keeps_newborn_and_assigns_living_parent_residence():
    w, mother, father = _world()
    w.cfg.raw()["nhan_khau"]["sinh_san"]["rui_ro_me"] = 1.0
    before = set(w.agents)
    w.tick = 1
    demography.sinh_con(w, {})

    w.tick = 3
    demography.sinh_con(w, {})
    children = _new_children(w, before)
    assert len(children) == 1
    child = children[0]
    assert w.agents[mother].health == 0.0
    assert mother in demography.cai_chet(w)
    assert w.agents[child].con_song
    mortality = metrics_demography.tinh(w)["chet"]
    assert mortality["theo_nguyen_nhan"] == {"tu_vong_sinh_no": 1}

    household.buoc_cu_tru(w, {})
    assert household.rid_cua(w, child) == household.rid_cua(w, father)
    assert household.rid_cua(w, mother) is None
    assert mother not in w.thai_ky and mother not in w.hau_san
