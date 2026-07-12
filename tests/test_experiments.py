"""Kiểm thử hạ tầng scenario/manifest — không chạy LLM hay subprocess mô phỏng."""

from __future__ import annotations

from pathlib import Path

from engine.config import Config, deep_merge, load_config
from engine.world import tao_the_gioi
from tools.counterfactual import TREATMENTS, _paired_delta, _summary
from tools.experiments import build_manifest, permute_personas, scenario_overlay, validate_scenario


def test_deep_merge_khong_doi_input_va_thay_list():
    base = {"a": {"b": 1, "c": [1, 2]}, "x": 3}
    merged = deep_merge(base, {"a": {"b": 2, "c": [9]}, "y": 4})
    assert merged == {"a": {"b": 2, "c": [9]}, "x": 3, "y": 4}
    assert base == {"a": {"b": 1, "c": [1, 2]}, "x": 3}


def test_config_digest_on_dinh_va_doi_khi_tham_so_doi():
    a = Config({"b": [1, 2], "a": {"x": 3}})
    b = Config({"a": {"x": 3}, "b": [1, 2]})
    c = Config({"a": {"x": 4}, "b": [1, 2]})
    assert a.digest() == b.digest()
    assert a.digest() != c.digest()


def test_scenario_benchmark_hop_le_va_overlay_nap_duoc():
    scope = validate_scenario("preindustrial_closed_v1")
    overlay = scenario_overlay("preindustrial_closed_v1")
    assert scope["validation_tier"] == "mechanism_benchmark"
    assert overlay is not None
    cfg = load_config(overlays=[overlay])
    assert cfg.get("san_xuat.san_luong_goc_kg") > 0


def test_manifest_ghi_scope_hash_va_config_digest():
    overlay = scenario_overlay("preindustrial_closed_v1")
    assert overlay is not None
    manifest = build_manifest(
        run_name="test", mode="rulebot", seed=7, ticks_requested=12,
        config_digest="abc", config_overlays=[Path(overlay)],
        scenario="preindustrial_closed_v1",
    )
    assert manifest["run"]["seed"] == 7
    assert manifest["reproducibility"]["config_sha256"] == "abc"
    assert manifest["reproducibility"]["scenario_scope"]["name"] == "preindustrial_closed_v1"
    assert "scenarios/preindustrial_closed_v1/scope.yaml" in \
        manifest["reproducibility"]["scenario_files_sha256"]


def test_counterfactuals_co_treatment_can_kiem_dinh():
    assert {"c1_no_contract_seeds", "c2_permute_personas", "c3_no_parameter_noise",
            "c4_adverse_weather"} <= set(TREATMENTS)
    weather = TREATMENTS["c4_adverse_weather"].overlay
    assert weather is not None
    assert sum(v["p"] for v in weather["thoi_gian"]["thoi_tiet"].values()) == 1.0


def test_permute_personas_tat_dinh_va_giu_da_tap_persona():
    cfg = load_config()
    a = tao_the_gioi(cfg, 91)
    b = tao_the_gioi(cfg, 91)
    before = sorted(tuple(x.persona.as_dict().values()) for x in a.agents.values())
    permute_personas(a)
    permute_personas(b)
    after = sorted(tuple(x.persona.as_dict().values()) for x in a.agents.values())
    assert before == after
    assert [x.persona.as_dict() for x in a.agents.values()] == \
        [x.persona.as_dict() for x in b.agents.values()]


def test_ensemble_summary_bao_ca_mean_median_phan_vi_va_delta_ghep_cap():
    baseline = [
        {"dan_so": 10, "gini_dat": 0.2},
        {"dan_so": 30, "gini_dat": 0.4},
        {"dan_so": 50, "gini_dat": 0.6},
    ]
    treatment = [
        {"dan_so": 15, "gini_dat": 0.1},
        {"dan_so": 35, "gini_dat": 0.3},
        {"dan_so": 55, "gini_dat": 0.5},
    ]
    summary = _summary(baseline)
    assert summary["dan_so"] == {"n": 3, "mean": 30.0, "median": 30.0,
                                  "p10": 14.0, "p90": 46.0}
    delta = _paired_delta(treatment, baseline)
    assert delta["dan_so"]["mean"] == 5.0
    assert delta["gini_dat"]["mean"] == -0.1
