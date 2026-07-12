"""Scenario validation phải ngăn tuyên bố thực chứng khi target/provenance thiếu."""

from __future__ import annotations

import pytest

from tools.validation import (
    Target,
    _empirical_ready,
    assert_no_overclaim,
    claim_tier_label,
    evaluate_targets,
    load_targets,
    validate_package,
)


def test_benchmark_duoc_nhan_dien_la_khong_phai_empirical():
    package = validate_package("preindustrial_closed_v1")
    assert package["missing_files"] == []
    assert package["invalid_priors"] == []
    assert package["empirical_ready"] is False
    assert load_targets("preindustrial_closed_v1", "in_sample") == []


def test_nhan_claim_an_toan_khong_bao_gio_la_empirical_khi_thieu_bang_chung():
    package = validate_package("preindustrial_closed_v1")
    # Benchmark cơ chế: nhãn an toàn phải là mechanism_benchmark, không đội nhãn thực chứng.
    assert claim_tier_label(package) == "mechanism_benchmark"
    # Khai báo tier=mechanism_benchmark + thiếu target → KHÔNG bị coi là overclaim.
    assert_no_overclaim(package)


def test_gate_chan_scenario_tu_nhan_empirical_khi_target_rong():
    # Giả lập scenario tự nhận empirical nhưng metadata rỗng.
    fake = {
        "scenario": "fake_empirical",
        "validation_tier": "empirical",
        "missing_files": [],
        "invalid_priors": [],
        "target_error": None,
        "in_sample_targets": 0,
        "holdout_targets": 0,
        "provenance_ok": False,
        "empirical_ready": False,
    }
    with pytest.raises(ValueError, match="empirical"):
        assert_no_overclaim(fake)
    assert claim_tier_label(fake) == "mechanism_benchmark"


def test_gate_cho_qua_khi_du_bang_chung():
    ready = {"scenario": "ok", "validation_tier": "empirical", "empirical_ready": True}
    assert_no_overclaim(ready)  # đủ bằng chứng → không raise
    assert claim_tier_label(ready) == "empirical"


def test_provenance_design_assumption_khong_the_empirical():
    # W2: tier=empirical + targets đầy đủ + target source khác rỗng NHƯNG provenance chỉ là
    # design_assumption ⇒ chưa có nguồn thật ⇒ KHÔNG được empirical_ready, gate phải raise.
    fake = {
        "scenario": "fake_sourced_targets",
        "validation_tier": "empirical",
        "missing_files": [],
        "invalid_priors": [],
        "target_error": None,
        "target_split_error": None,
        "in_sample_targets": 2,
        "holdout_targets": 1,
        "provenance_ok": True,
        "targets_sourced": True,
        "provenance_all_sourced": False,  # mọi dòng vẫn là design_assumption
    }
    assert _empirical_ready(fake) is False
    fake["empirical_ready"] = _empirical_ready(fake)
    with pytest.raises(ValueError, match="provenance"):
        assert_no_overclaim(fake)
    # Ngược lại: khi provenance đã có nguồn thật (và mọi điều kiện khác đủ) thì mới ready.
    assert _empirical_ready({**fake, "provenance_all_sourced": True}) is True


def test_target_split_disjoint_bi_bat():
    # Hai file targets có cùng id ⇒ in_sample ∩ holdout ≠ ∅ ⇒ target_split_error khác None.
    in_ids = {t.id for t in [Target("shared", "m", 4, "u", "s", expected=1.0)]}
    hold_ids = {t.id for t in [Target("shared", "m", 8, "u", "s", expected=2.0)]}
    overlap = sorted(in_ids & hold_ids)
    target_split_error = (
        f"id target trùng giữa in_sample và holdout: {overlap}" if overlap else None
    )
    assert target_split_error is not None
    assert "shared" in target_split_error
    # Có rò rỉ split ⇒ dù các điều kiện khác đủ, empirical_ready vẫn False.
    assert _empirical_ready({
        "validation_tier": "empirical", "missing_files": [], "invalid_priors": [],
        "target_error": None, "target_split_error": target_split_error,
        "in_sample_targets": 1, "holdout_targets": 1, "provenance_ok": True,
        "targets_sourced": True, "provenance_all_sourced": True,
    }) is False


def test_benchmark_van_khong_doi():
    for name in ("preindustrial_closed_v1", "agrarian_transition_v1"):
        package = validate_package(name)
        assert package["empirical_ready"] is False
        assert package["missing_files"] == []
        assert package["invalid_priors"] == []
        # Report units/provenance mới phải có mặt cho người ngoài kiểm.
        assert "missing_units" in package
        assert "provenance_all_sourced" in package
        assert package["provenance_all_sourced"] is False  # toàn design_assumption
        assert package["target_split_error"] is None  # targets rỗng ⇒ không giao
        assert claim_tier_label(package) == "mechanism_benchmark"
        assert_no_overclaim(package)  # benchmark không target ⇒ KHÔNG overclaim


def test_evaluate_targets_dung_dai_va_bao_missing():
    targets = [
        Target("population", "dan_so", 10, "người", "source", lower=90, upper=110),
        Target("absent", "gdp", 20, "kg thóc", "source", expected=10),
    ]
    result = evaluate_targets([{"tick": 10, "dan_so": 100}], targets)
    assert result[0]["status"] == "pass"
    assert result[1]["status"] == "missing"
