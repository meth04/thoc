"""Kiểm thử sensitivity runner — rút CHỈ từ plausible_range, tách nhiễu seed.

Test tích hợp chạy run.py rulebot (không mạng/LLM) qua subprocess với horizon rất ngắn,
dùng prefix riêng + cleanup nên KHÔNG đụng run/thí nghiệm thật.
"""

from __future__ import annotations

import json
import shutil

import pytest

from tools import sensitivity
from tools.sensitivity import EXPERIMENTS, RUNS, grid_from_range

SCENARIO = "agrarian_transition_v1"
PARAM = "san_xuat.san_luong_goc_kg"
PREFIX = "t_sens_ut"


def _cleanup(prefix: str) -> None:
    exp = EXPERIMENTS / f"{prefix}_sens"
    if exp.exists():
        shutil.rmtree(exp)
    for d in RUNS.glob(f"{prefix}_*"):
        if d.is_dir():
            shutil.rmtree(d)


@pytest.fixture
def prefix() -> str:
    _cleanup(PREFIX)
    try:
        yield PREFIX
    finally:
        _cleanup(PREFIX)


# ----------------------------------------------------------------- đơn vị (nhanh)

def test_grid_from_range_in_range_va_tat_dinh():
    g = grid_from_range(450.0, 750.0, 3)
    assert g == [450.0, 600.0, 750.0]
    assert grid_from_range(450.0, 750.0, 3) == g  # tất định, không random toàn cục
    for n in (2, 4, 5, 7):
        vals = grid_from_range(0.10, 0.35, n)
        assert len(vals) == n
        assert all(0.10 <= v <= 0.35 for v in vals)  # KHÔNG ra ngoài plausible_range
        assert vals[0] == 0.10 and vals[-1] == 0.35


def test_grid_n1_la_trung_diem_trong_range():
    assert grid_from_range(0.0, 1.0, 1) == [0.5]
    assert grid_from_range(40.0, 90.0, 1) == [65.0]


def test_grid_range_khong_hop_le_raise():
    with pytest.raises(ValueError):
        grid_from_range(10.0, 5.0, 3)


def test_sensitivity_phat_hien_non_identified():
    # outcome không đổi trên lưới param → non-identified, phải BÁO rõ.
    points = [
        {"value": 1.0, "agg": {n: {"median": 5.0, "spread": 0.0} for n in sensitivity.OUTCOMES}},
        {"value": 2.0, "agg": {n: {"median": 5.0, "spread": 0.0} for n in sensitivity.OUTCOMES}},
    ]
    sens = sensitivity._sensitivity(points)
    for n in sensitivity.OUTCOMES:
        assert sens[n]["available"] is True
        assert sens[n]["identifiable"] is False
        assert "non-identified" in sens[n]["note"]


def test_sensitivity_tach_bien_thien_param_khoi_nhieu_seed():
    # param đổi outcome 4.0 vượt hẳn nhiễu seed 0.1 → identifiable.
    points = [
        {"value": 1.0, "agg": {n: {"median": 5.0, "spread": 0.1} for n in sensitivity.OUTCOMES}},
        {"value": 2.0, "agg": {n: {"median": 9.0, "spread": 0.1} for n in sensitivity.OUTCOMES}},
    ]
    sens = sensitivity._sensitivity(points)
    for n in sensitivity.OUTCOMES:
        assert sens[n]["identifiable"] is True
        assert sens[n]["outcome_range"] == 4.0
        assert sens[n]["seed_noise_median"] == 0.1
        assert sens[n]["param_span"] == 1.0


def test_sensitivity_hieu_ung_chim_trong_nhieu_seed_la_non_identified():
    # outcome đổi 0.05 nhưng nhiễu seed 0.5 → không tách được → non-identified.
    points = [
        {"value": 1.0, "agg": {n: {"median": 5.00, "spread": 0.5} for n in sensitivity.OUTCOMES}},
        {"value": 2.0, "agg": {n: {"median": 5.05, "spread": 0.5} for n in sensitivity.OUTCOMES}},
    ]
    sens = sensitivity._sensitivity(points)
    for n in sensitivity.OUTCOMES:
        assert sens[n]["identifiable"] is False
        assert "nhiễu" in sens[n]["note"]


def test_refuse_overwrite(prefix):
    (EXPERIMENTS / f"{prefix}_sens").mkdir(parents=True)
    with pytest.raises(SystemExit):
        sensitivity.main(["--scenario", SCENARIO, "--params", PARAM,
                          "--samples", "2", "--seeds", "41", "42", "--ticks", "8",
                          "--prefix", prefix])


def test_seeds_phai_it_nhat_hai():
    with pytest.raises(SystemExit):
        sensitivity.main(["--scenario", SCENARIO, "--params", PARAM,
                          "--samples", "2", "--seeds", "41", "--ticks", "8",
                          "--prefix", "t_sens_never"])


# ----------------------------------------------------- tích hợp (chạy run.py rulebot)

def test_summary_cau_truc_va_gia_tri_trong_range(prefix):
    rc = sensitivity.main([
        "--scenario", SCENARIO, "--params", PARAM,
        "--samples", "2", "--seeds", "41", "42", "--ticks", "8", "--prefix", prefix,
    ])
    assert rc == 0
    exp = EXPERIMENTS / f"{prefix}_sens"
    assert (exp / "summary.md").exists()
    data = json.loads((exp / "summary.json").read_text(encoding="utf-8"))

    assert data["scenario"] == SCENARIO
    assert data["mode"] == "rulebot"
    assert data["seeds"] == [41, 42]
    assert PARAM in data["params"]

    info = data["params"][PARAM]
    assert info["n_seed"] == 2                      # param → ... + n_seed
    lo, hi = info["plausible_range"]
    assert len(info["grid"]) == 2
    assert all(lo <= v <= hi for v in info["grid"])  # rút NẰM trong plausible_range
    for p in info["points"]:
        assert lo <= p["value"] <= hi
        assert p["n_seed_success"] <= 2

    sens = info["sensitivity"]                       # param → outcome sensitivity
    for outcome in sensitivity.OUTCOMES:
        assert outcome in sens
        entry = sens[outcome]
        assert "available" in entry
        if entry["available"]:
            assert isinstance(entry["identifiable"], bool)
            assert "outcome_range" in entry and "seed_noise_median" in entry
