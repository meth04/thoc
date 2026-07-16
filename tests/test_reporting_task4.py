"""Task #4 telemetry/reporting contracts; all fixtures are local and offline."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import engine.metrics as metrics_module
from engine.config import Config, load_config
from engine.metrics import tinh_metrics
from run import _treatments_tu_config, viet_session_report
from tools.reality_check import kiem_d1
from tools.telemetry import sinh_bao_cao


def _attempt_db(run_dir):
    db = run_dir / "llm_calls.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE llm_calls (tick INTEGER, tier TEXT, provider TEXT, model TEXT, "
        "key_hash TEXT, tok_in INTEGER, tok_out INTEGER, latency_ms INTEGER, retries INTEGER, "
        "fallback INTEGER, superseded INTEGER, provider_retries INTEGER, "
        "json_repair_retries INTEGER, tool_turns INTEGER)"
    )
    conn.executemany(
        "INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "T0", "provider", "model", "key", 10, 5, 20, 99, 0, 0, 2, 3, 4),
            (1, "T0", "loi", "", "", 0, 0, 10, 0, 1, 0, 0, 0, 0),
        ],
    )
    conn.execute(
        "CREATE TABLE llm_attempts (attempt_started INTEGER, billability TEXT, status TEXT, "
        "source TEXT, superseded INTEGER)"
    )
    conn.executemany(
        "INSERT INTO llm_attempts VALUES (?,?,?,?,?)",
        [
            (1, "billable", "success", "decision_initial", 0),
            (1, "unknown", "rate_limited", "decision_initial", 0),
            (0, "not_billable", "budget_denied", "json_repair", 0),
            (1, "billable", "success", "tool_turn", 1),
        ],
    )
    conn.commit()
    conn.close()


def _metrics_world():
    """Minimal read-only world surface for metrics, independent of unrelated WIP imports."""
    class Ledger:
        def __init__(self):
            self.lich_su = []

        def so_du(self, _aid, _asset):
            return 0.0

        def tong_tai_san(self, _asset):
            return 0.0

    class Agent:
        def __init__(self, aid):
            self.id = aid
            self.con_song = True
            self.e_bac = 0
            self.vo_gia_cu = False
            self.health = 100.0

        def truong_thanh(self, _threshold):
            return True

    cfg = Config({
        "nhan_khau": {"tuoi_truong_thanh": 16},
        "quan_sat": {
            "cua_so_dat_tick": 4,
            "nguong_sigma_phi_ly": 3.0,
            "min_diem_gia_phi_ly": 6,
        },
    })
    return SimpleNamespace(
        tick=1,
        nam=lambda: 0,
        cfg=cfg,
        agents={"A0001": Agent("A0001"), "A0002": Agent("A0002")},
        parcels={}, ledger=Ledger(), thu_nhap_4=[], gia_lich_su={},
        kl_thanh_toan_tick={}, kl_hd_tick=0.0,
        gia_gan_nhat=lambda asset: (3.0 if asset == "go" else None),
    )


def _metric_line(*, fallback: int, llm: int, mock: int = 0) -> dict:
    return {
        "tick": 1,
        "decision_provenance": {
            "plans": {"llm": llm, "mock": mock, "fallback": fallback, "policy_card": 3},
            "plan_total": llm + mock + fallback + 3,
        },
        "llm": {
            "scheduled_agent_decision": llm + mock + fallback,
            "completed_agent_decision_turn": llm + mock + fallback,
            "parsed_agent_decision": llm + mock,
            "terminal_reason_counts": {"response": llm + mock, "provider_error": fallback},
            "exact_one_terminal_decision": True,
        },
    }


def test_telemetry_separates_attempt_billability_counters_and_decisions(tmp_path):
    _attempt_db(tmp_path)
    (tmp_path / "metrics.jsonl").write_text(
        json.dumps(_metric_line(fallback=2, llm=8)) + "\n", encoding="utf-8"
    )

    report = sinh_bao_cao(tmp_path)

    assert report["provider_retries"] == 2
    assert report["json_repair_retries"] == 3
    assert report["tool_turns"] == 4
    assert report["call_loi_provider"] == 1
    assert "?" not in report["theo_model"]
    assert report["attempts"]["burned"]["by_billability"] == {
        "billable": 2, "not_billable": 1, "unknown": 1,
    }
    assert report["attempts"]["effective"]["total"] == 3
    assert report["fallback_call_level"]["rate"] == 0.5
    assert report["fallback_decision_level"]["rate"] == 0.2
    assert report["terminal_decision_coverage"]["terminal_coverage"] == 1.0
    assert report["terminal_decision_coverage"]["parsed_decision_coverage"] == 0.8
    text = (tmp_path / "reports" / "telemetry.md").read_text(encoding="utf-8")
    assert "provider_retries 2" in text
    assert "HTTP attempts / billability" in text
    assert "fallback_decision_level" in text


def test_d1_fails_decision_fallback_even_when_call_fallback_is_low(tmp_path):
    _attempt_db(tmp_path)
    conn = sqlite3.connect(tmp_path / "llm_calls.sqlite")
    conn.execute("UPDATE llm_calls SET fallback=0")
    conn.commit()
    conn.close()
    (tmp_path / "metrics.jsonl").write_text(
        json.dumps(_metric_line(fallback=2, llm=8)) + "\n", encoding="utf-8"
    )
    (tmp_path / "run_meta.json").write_text(json.dumps({"mode": "real"}), encoding="utf-8")

    result = kiem_d1(tmp_path)

    assert result["ket_luan"] == "fail"
    assert "decision fallback=2/10=20.00%" in result["bang_chung"]
    assert "call-level fallback=0.00%" in result["bang_chung"]


def test_metrics_mark_empty_land_distribution_undefined_and_report_gdp_coverage(monkeypatch):
    w = _metrics_world()
    w.gia_gan_nhat = lambda _asset: None
    w.ledger.lich_su = [SimpleNamespace(
        tick=w.tick,
        sinh_huy=[SimpleNamespace(so_luong=2.0, luong="khai_thac", tai_san="go")],
    )]
    monkeypatch.setattr(metrics_module, "household_snapshot", lambda _w: [])
    monkeypatch.setattr(
        metrics_module, "land_price_productivity",
        lambda _w, _window: {"land_transactions_window": 0, "land_price_to_expected_output": 0.0},
    )

    missing_price = tinh_metrics(w)

    assert missing_price["gini_dat"] is None
    assert missing_price["n_thua_tu_huu"] == 0
    assert missing_price["n_nguoi_mau_gini_dat"] == 2
    assert missing_price["gdp_price_coverage"] == {
        "components": 1,
        "priced_components": 0,
        "unpriced_components": 1,
        "priced_output_components": 0,
        "unpriced_output_components": 1,
        "priced_intermediate_components": 0,
        "unpriced_intermediate_components": 0,
        "coverage": 0.0,
        "complete": False,
    }

    w.gia_gan_nhat = lambda asset: 3.0 if asset == "go" else None
    priced = tinh_metrics(w)
    assert priced["gdp"] == 6.0
    assert priced["gdp_price_coverage"]["coverage"] == 1.0
    assert priced["gdp_price_coverage"]["complete"] is True


def test_complete_v7_stack_manifest_has_distinct_active_treatment_labels():
    scenario = Path(__file__).resolve().parents[1] / "scenarios" / "agrarian_transition_v1"
    overlays = [
        scenario / name
        for name in (
            "spatial_v1.yaml",
            "spatial_livelihood_v2.yaml",
            "spatial_livelihood_v3.yaml",
            "spatial_livelihood_v4.yaml",
            "spatial_livelihood_v5.yaml",
            "spatial_livelihood_v6.yaml",
            "spatial_livelihood_v7.yaml",
        )
    ]
    cfg = load_config(overlays=overlays)

    from tools.experiments import build_manifest

    manifest = build_manifest(
        run_name="v7-manifest-fixture", mode="rulebot", seed=17, ticks_requested=1,
        config_digest=cfg.digest(), config_overlays=overlays,
        scenario="agrarian_transition_v1",
        treatments=_treatments_tu_config(cfg, permute_personas=False),
    )

    assert manifest["reproducibility"]["treatments"] == [
        "survival_floor_food", "survival_floor_shelter", "settlement_entry_v5",
        "llm_autonomy_v4", "common_land_lottery", "reproductive_timing_v6",
        "survival_feasibility_v7", "shelter_floor_v7", "contract_schedule_v2",
        "physical_contract_delivery_v2",
    ]

    legacy_cfg = load_config(overlays=overlays[:5])
    v6_v7_labels = {
        "reproductive_timing_v6", "survival_feasibility_v7", "shelter_floor_v7",
        "contract_schedule_v2", "physical_contract_delivery_v2",
    }
    assert not (set(_treatments_tu_config(legacy_cfg, permute_personas=False)) & v6_v7_labels)


def test_manifest_treatments_come_from_merged_config_and_real_report_omits_mock_rate(tmp_path):
    cfg = Config({
        "minds": {
            "san_an_toi_thieu": {"bat": True},
            "san_cho_o_toi_thieu": {"bat": True},
            "llm_tick": {"bat": True},
        },
        "khong_gian": {
            "dat_o": {"bat": True},
            "phan_bo_ruong_cong": {"bat": True, "co_che": "lottery_seeded"},
        },
    })
    assert _treatments_tu_config(cfg, permute_personas=True) == [
        "permute_personas", "survival_floor_food", "survival_floor_shelter",
        "settlement_entry_v5", "llm_autonomy_v4", "common_land_lottery",
    ]

    w = SimpleNamespace(nam=lambda: 0, metrics_lich_su=[], milestones=[])
    meta = {
        "run_name": "real-fixture", "mode": "real", "seed": 902, "tick_cuoi": 0,
        "thoi_gian_s": 0.0, "world_hash": "fixture-world-hash", "fallback_rate": 0.0,
        "so_call": 1, "so_luot_nghi_phien": 1,
    }
    viet_session_report(tmp_path, w, meta)
    text = next((tmp_path / "reports").glob("session_*.md")).read_text(encoding="utf-8")
    assert "p_malformed" not in text
    assert "gini đất không xác định (n=0 thửa tư hữu)" in text
