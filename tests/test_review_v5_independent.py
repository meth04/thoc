"""Independent v5-review acceptance contracts.

This suite deliberately exercises module boundaries not trusted to implementation-owned
coverage: a denied budget slot is not an HTTP request, D1 is decision-level, the
v7 survival interface cannot expose an outsider balance, v7 signing is atomic and
local, and an explicitly OFF card gate preserves the legacy trajectory.

Every provider path uses ``httpx.MockTransport``; no test reads environment keys or
uses the network.
"""

from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import httpx

from engine.config import Config, load_config
from engine.contracts import (
    ClauseChuyenGiaoMotLan,
    ClauseGopCong,
    HopDong,
    delivery_failure_code,
    gop_cong_dau_san_xuat,
)
from engine.production import sinh_cong
from engine.world import World, tao_the_gioi
from minds.gateway import LLMCallLog, LLMRequest, LLMResponse
from minds.keypool import EnvKeys
from minds.prompts import build_user_rieng, render_survival_fact_card
from minds.real import MindReal
from minds.tick_budget import NganSachLLMTick
from minds.world_tools import canonical_json, survival_fact_payload, thuc_thi
from tests.helpers import chay_tick, the_gioi_test
from tools.reality_check import kiem_d1

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "agrarian_transition_v1"
V7_OVERLAYS = [
    SCENARIO / name
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


def _env() -> EnvKeys:
    return EnvKeys(
        gemini_keys=["independent-fixture-key"],
        nine_key="independent-fixture-nine-key",
        nine_base="http://fixture.invalid/v1",
        llm_mode="real",
    )


def _contract_world(*, seed: int = 901):
    raw = copy.deepcopy(load_config().raw())
    raw.setdefault("hop_dong", {}).update({
        "gop_cong_lich": "signing_tick_half_open_v2",
        "tiep_can_vat_ly_v2": True,
    })
    w = tao_the_gioi(Config(raw), seed, events_path=None)
    ids = sorted(w.agents)
    for aid in ids[2:]:
        w.agents[aid].con_song = False
    for aid in ids[:2]:
        w.agents[aid].tuoi_tick = 40.0
        w.agents[aid].health = 100.0
    return w, ids[0], ids[1]


def _v7_world(*, seed: int = 907):
    w = tao_the_gioi(load_config(overlays=V7_OVERLAYS), seed, events_path=None)
    ids = sorted(w.agents)
    for aid in ids[2:]:
        w.agents[aid].con_song = False
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    return w, ids[0], ids[1]


def test_budget_denial_is_terminal_telemetry_not_a_fake_http_attempt(tmp_path, monkeypatch):
    """A slot denial is recorded, but the MockTransport must never receive a request."""
    w = the_gioi_test(seed=911, giu_lai=1, thoc_moi_nguoi=2_000.0)
    w.cfg.raw()["minds"]["llm_tick"].update({
        "bat": True,
        "pham_vi": "moi_agent",
        "toi_thieu_call": 1,
        "toi_da_call": 1,
        "toi_da_call_moi_quyet_dinh": 1,
        "kiem_tra_burst_rpm": False,
    })
    w.cfg.raw()["minds"]["nghiem_thuc"].update({
        "bat": True,
        "provider": "aistudio",
        "model": "gemini-3.1-flash-lite",
    })

    def deny(self, _logical_id, *, loai="decision", toi_da_task=None):
        _ = loai, toi_da_task
        self.bi_tu_choi += 1
        return False

    seen_http: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_http.append(request)
        return httpx.Response(200, json={"candidates": []})

    monkeypatch.setattr(NganSachLLMTick, "bat_dau", deny)
    run_dir = tmp_path / "denied"
    mind = MindReal(
        w,
        run_dir,
        w.cfg,
        _env(),
        run_dir / "quota.sqlite",
        transport=httpx.MockTransport(handler),
        cho_toi_s=0.01,
        transcript_path=run_dir / "transcript.jsonl",
    )
    chay_tick(w, mind, 1)
    mind.log.dong()
    mind.transcript.dong()

    assert seen_http == []
    conn = sqlite3.connect(run_dir / "llm_calls.sqlite")
    attempt_rows = conn.execute(
        "SELECT attempt_started, status, billability FROM llm_attempts"
    ).fetchall()
    conn.close()
    assert attempt_rows == [(0, "budget_denied", "not_billable")]
    terminals = [
        json.loads(line)
        for line in (run_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["terminal_reason"] for row in terminals if row["record_type"] == "decision_terminal"] == [
        "budget_denied"
    ]
    assert mind.stats_tick["provider_request_started"] == 0
    assert mind.stats_tick["provider_request_denied_before_start"] == 1


def test_d1_rejects_high_decision_fallback_when_calls_report_zero_fallback(tmp_path):
    """Call-level success cannot mask a cohort that fell back at decision level."""
    log = LLMCallLog(tmp_path / "llm_calls.sqlite")
    request = LLMRequest(prompt="fixture", ctx={}, tier="T0", tick=1)
    log.ghi(1, request, LLMResponse(text="{}", provider="mock", model="fixture"), False)
    log.dong()
    metric = {
        "tick": 1,
        "decision_provenance": {
            "plans": {"llm": 8, "mock": 0, "fallback": 2, "policy_card": 0},
            "plan_total": 10,
        },
        "llm": {
            "scheduled_agent_decision": 10,
            "completed_agent_decision_turn": 10,
            "parsed_agent_decision": 8,
            "terminal_reason_counts": {"response": 8, "budget_denied": 2},
            "exact_one_terminal_decision": True,
        },
    }
    (tmp_path / "metrics.jsonl").write_text(json.dumps(metric) + "\n", encoding="utf-8")
    (tmp_path / "run_meta.json").write_text(json.dumps({"mode": "real"}), encoding="utf-8")

    result = kiem_d1(tmp_path)

    assert result["ket_luan"] == "fail"
    assert "decision fallback=2/10=20.00%" in result["bang_chung"]
    assert "call-level fallback=0.00%" in result["bang_chung"]


def test_v7_survival_tool_is_read_only_and_omits_outsider_balance():
    """The real engine view exposes only the requester's residence, never R2 stock."""
    w, requester, outsider = _v7_world()
    outsider_balance = 987_654.0
    w.ledger.sinh(outsider, "thoc", outsider_balance, "khoi_tao", "independent fixture", w.tick)
    before = w.world_hash()

    payload = thuc_thi(w, requester, "xem_co_hoi_san_xuat", {})
    card = render_survival_fact_card(w, requester)
    prompt = build_user_rieng(w, requester, ["dinh_ky"])

    assert payload["status"] == "available"
    wire = canonical_json(payload)
    assert str(outsider_balance) not in wire
    assert outsider not in payload["facts"]["members"]
    assert canonical_json(payload) in card
    assert canonical_json(payload) in prompt
    assert "[KHẢ NĂNG THỰC THI SỐNG CÒN]" not in prompt
    assert w.world_hash() == before


def test_v7_tool_rejects_external_owner_in_any_food_balance_row(monkeypatch):
    """A malformed engine projection must fail closed rather than leak an R2 balance."""
    import engine.survival_feasibility as feasibility

    w, requester, outsider = _v7_world(seed=919)
    original = feasibility.build_survival_feasibility

    def leaking_builder(world, aid):
        facts = original(world, aid).model_dump(mode="json")
        facts["decay_before_consumption"].append({
            "owner_id": outsider,
            "asset": "thoc",
            "kg": 123.0,
            "kg_thoc_equivalent": 123.0,
            "decay_rate": 0.01,
        })
        return facts

    monkeypatch.setattr(feasibility, "build_survival_feasibility", leaking_builder)

    payload = survival_fact_payload(w, requester)

    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "privacy_boundary_violation"


def test_gate_off_card_uses_legacy_surface_and_preserves_checkpoint_trajectory(tmp_path):
    """Adding an explicit OFF card gate must be hash-neutral before and after resume."""
    base_raw = copy.deepcopy(load_config().raw())
    off_raw = copy.deepcopy(base_raw)
    off_raw.setdefault("minds", {})["survival_feasibility"] = {"bat": False}
    base_cfg, off_cfg = Config(base_raw), Config(off_raw)
    w_base = tao_the_gioi(base_cfg, 929, events_path=None)
    w_off = tao_the_gioi(off_cfg, 929, events_path=None)
    assert w_base.world_hash() == w_off.world_hash()

    from minds.rulebot import quyet_dinh_tat_ca

    chay_tick(w_base, quyet_dinh_tat_ca, 2)
    chay_tick(w_off, quyet_dinh_tat_ca, 2)
    assert w_base.world_hash() == w_off.world_hash()
    aid = sorted(w_off.agents)[0]
    assert "schema_version" not in thuc_thi(w_off, aid, "xem_co_hoi_san_xuat", {})
    assert "[KHẢ NĂNG THỰC THI SỐNG CÒN]" in build_user_rieng(w_off, aid, ["dinh_ky"])

    checkpoint = w_off.luu_checkpoint(tmp_path / "checkpoint")
    resumed = World.nap_checkpoint(checkpoint, None, cfg=off_cfg)
    assert resumed.world_hash() == w_off.world_hash()
    chay_tick(w_off, quyet_dinh_tat_ca, 1)
    chay_tick(resumed, quyet_dinh_tat_ca, 1)
    assert resumed.world_hash() == w_off.world_hash()


def test_v7_contract_is_local_atomic_and_one_tick_labor():
    """Reachability rejects without mutation; K=1 transfers food and labor exactly once."""
    from engine.board import _ky_hop_dong

    w, worker, responder = _contract_world()
    w.agents[responder].lang = 1
    unreachable = HopDong(
        cac_ben=[worker, responder],
        hinh_thuc="mieng",
        thoi_han=1,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(
                tu=responder, den=worker, tai_san="thoc", so_luong=25.0, tai="ky_ket"
            ),
            ClauseGopCong(tu=worker, den=responder, so_cong_moi_tick=40.0),
        ],
    )
    before = w.world_hash()
    assert delivery_failure_code(w, responder, worker) == "delivery_unreachable"
    assert _ky_hop_dong(w, unreachable) is False
    assert w.world_hash() == before
    assert w.hop_dong == {} and w._next_hd == 0

    w.agents[responder].lang = w.agents[worker].lang
    w.ledger.sinh(worker, "go", 3.0, "khai_thac", "independent fixture", w.tick)
    impossible = HopDong(
        cac_ben=[worker, responder],
        hinh_thuc="mieng",
        thoi_han=2,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(
                tu=responder, den=worker, tai_san="thoc", so_luong=10.0, tai="ky_ket"
            ),
            ClauseChuyenGiaoMotLan(
                tu=worker, den=responder, tai_san="go", so_luong=5.0, tai="ky_ket"
            ),
        ],
    )
    balances, history, next_hd = dict(w.ledger._so_du), list(w.ledger.lich_su), w._next_hd
    assert _ky_hop_dong(w, impossible) is False
    assert dict(w.ledger._so_du) == balances
    assert w.ledger.lich_su == history
    assert w._next_hd == next_hd and w.hop_dong == {}

    one_tick = HopDong(
        cac_ben=[worker, responder],
        hinh_thuc="mieng",
        thoi_han=1,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(
                tu=responder, den=worker, tai_san="thoc", so_luong=25.0, tai="ky_ket"
            ),
            ClauseGopCong(tu=worker, den=responder, so_cong_moi_tick=40.0),
        ],
    )
    assert _ky_hop_dong(w, one_tick) is True
    signed_tick = w.tick
    sinh_cong(w)
    gop_cong_dau_san_xuat(w)
    w.tick += 1
    sinh_cong(w)
    gop_cong_dau_san_xuat(w)
    labor = [tx for tx in w.ledger.lich_su if tx.ly_do.startswith("góp công ")]
    assert len(labor) == 1
    assert labor[0].tick == signed_tick
