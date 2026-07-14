"""P4 demographic metrics: state-derived denominators and honest missing data."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import metrics, metrics_demography
from engine.config import load_config
from engine.world import tao_the_gioi

ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
LIVELIHOOD = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"


def _world(n: int = 4):
    w = tao_the_gioi(load_config(overlays=[SPATIAL, LIVELIHOOD]), 211, events_path=None)
    ids = sorted(w.agents)
    for aid in ids[n:]:
        w.agents[aid].con_song = False
    cfg = w.cfg.raw()["quan_sat"]["nhan_khau"]
    cfg["cua_so_tick"] = 2
    cfg["min_person_tick"] = 1
    cfg["min_woman_tick"] = 1
    cfg["min_n_tu_vong"] = 1
    cfg["bang_song"]["min_person_tick_moi_band"] = 1
    return w, ids[:n]


def _age(w, aid: str, years: float) -> None:
    w.agents[aid].tuoi_tick = years * 2.0


def test_age_at_death_khac_tuoi_nguoi_song_va_khong_tuoi_tho_gia():
    w, ids = _world()
    for aid, age in zip(ids, (10.0, 20.0, 30.0, 40.0), strict=True):
        _age(w, aid, age)
    w.tick = 1
    metrics_demography.bat_dau_tick(w)
    for aid, cause in zip(ids[:3], ("chet_doi", "benh_tat", "tuoi_gia"), strict=True):
        metrics_demography.ghi_chet(w, w.agents[aid].tuoi_nam, cause)
        w.agents[aid].con_song = False

    m = metrics.buoc_ket_toan(w)["demography"]

    assert m["song"] == {"n": 1, "tuoi_tb": 40.0, "tuoi_trung_vi": 40.0}
    assert m["chet"]["n_tick"] == 3
    assert m["chet"]["tuoi_tb_khi_chet"] == pytest.approx(20.0)
    assert m["chet"]["tuoi_trung_vi_khi_chet"] == pytest.approx(20.0)
    assert m["chet"]["theo_nguyen_nhan"] == {
        "benh_tat": 1, "chet_doi": 1, "tuoi_gia": 1,
    }
    assert "life_expectancy" not in m
    assert "tuoi_tho" not in m
    assert "e0_period" in m["bang_song"]
    assert "exposure_person_tick" in m["bang_song"]


def test_mortality_rate_uses_person_ticks_not_final_population():
    w, ids = _world()
    for aid in ids:
        _age(w, aid, 30.0)

    w.tick = 1
    metrics_demography.bat_dau_tick(w)  # four people exposed this tick
    for aid in ids[:2]:
        metrics_demography.ghi_chet(w, 30.0, "chet_doi")
        w.agents[aid].con_song = False
    metrics.buoc_ket_toan(w)

    w.tick = 2
    metrics_demography.bat_dau_tick(w)  # two people exposed in the second tick
    m = metrics.buoc_ket_toan(w)["demography"]

    # spatial_v1 has 3 ticks/year: 2 deaths / (4+2) person-ticks * 3 = 1.
    assert m["exposure_person_tick"] == pytest.approx(6.0)
    assert m["ty_suat_chet_moi_nguoi_moi_nam"] == pytest.approx(1.0)
    assert m["ty_suat_chet_moi_nguoi_moi_nam"] != pytest.approx(3.0)


def test_missing_denominator_and_no_workers_are_none_not_fake_zero():
    w, ids = _world(n=1)
    _age(w, ids[0], 75.0)
    w.tick = 1
    metrics_demography.bat_dau_tick(w)
    m = metrics.buoc_ket_toan(w)["demography"]

    assert m["chet"]["tuoi_tb_khi_chet"] is None
    assert m["chet"]["tuoi_trung_vi_khi_chet"] is None
    assert m["ty_le_phu_thuoc"] is None
    # The final open age band has no observed death, so a period e0 would be
    # infinite/unsupported rather than a made-up longevity claim.
    assert m["bang_song"]["e0_period"] is None


def test_legacy_metrics_surface_stays_unchanged_when_gate_is_absent():
    w = tao_the_gioi(load_config(overlays=[SPATIAL]), 211, events_path=None)
    w.tick = 1
    m = metrics.buoc_ket_toan(w)
    assert "demography" not in m


def test_versioned_p4_surface_reports_project_quote_and_ecology_coverage():
    w, _ids = _world()
    w.tick = 1
    metrics_demography.bat_dau_tick(w)
    m = metrics.buoc_ket_toan(w)

    assert m["projects"]["trang_thai"]["dang_lam"] == 0
    assert m["quotes"]["n_bao_gia_mo"] == 0
    assert m["quotes"]["ty_le_chap_nhan_den_thanh_toan"] is None
    assert m["ecology"]["forest_area_cells"] >= 0
    assert "forest_biomass" in m["ecology"]
