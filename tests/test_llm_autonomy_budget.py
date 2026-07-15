"""Autonomy treatment: 1..10 independent LLM requests for every adult agent.

These tests use PersonaBot or ``httpx.MockTransport`` only.  They are an
offline proof that the expensive full-coverage treatment does not silently
collapse back into a village-wide cap or an agent batch.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

import httpx

from engine.config import load_config
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.gateway import LLMRequest
from minds.keypool import EnvKeys, key_hash
from minds.orchestrator import tao_mind_mock
from minds.providers_real import GatewayReal, burst_guard
from minds.quota import QuotaCounter
from minds.real import MindReal, _stt_dich_hop_le
from minds.tick_budget import NganSachLLMTick

ROOT = Path(__file__).resolve().parents[1]
OVERLAYS = [
    ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml",
    ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml",
    ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v3.yaml",
    ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v4.yaml",
]


def _cfg():
    return load_config(overlays=OVERLAYS)


def _env_15_keys() -> EnvKeys:
    # 15 × 4 RPM gives an immediate 60-request burst, enough for the
    # 50-resident first tick without touching a real provider.
    return EnvKeys(
        gemini_keys=[f"fixture-key-{i}" for i in range(15)],
        nine_key="fixture-nine-key",
        nine_base="http://fixture.invalid/v1",
        llm_mode="real",
    )


def _agent_id_from_payload(payload: dict) -> str:
    text = (payload.get("contents", [{}])[0].get("parts", [{}])[0].get("text", "")
            if "contents" in payload
            else payload.get("messages", [{}])[0].get("content", ""))
    match = re.search(r'\(id "([AE]\d+)"\)', text)
    return match.group(1) if match else "A0001"


def _decision_response(payload: dict) -> httpx.Response:
    aid = _agent_id_from_payload(payload)
    text = json.dumps({
        "id": aid,
        "hanh_dong": [{"loai": "phan_bo_cong", "hoc": False}],
        "ly_do": "quyết định độc lập trong fixture",
    }, ensure_ascii=False)
    if "contents" in payload:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10},
        })
    return httpx.Response(200, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    })


def test_v4_mock_tick_1_gives_each_of_50_adults_one_unbatched_call(tmp_path):
    cfg = _cfg()
    w = tao_the_gioi(cfg, seed=42, events_path=None)
    mind = tao_mind_mock(w, fast=True, run_dir=tmp_path, p_malformed=0.0)

    chay_mot_tick(w, mind, len(w.parcels))

    stats = mind.stats_tick
    assert stats["logical_task"] == 50
    assert stats["api_call"] == 50
    assert stats["api_call_cap"] == 500
    assert stats["api_call_min_required"] == 50
    assert stats["api_call_min_met"] is True
    assert len(stats["api_call_by_agent"]) == 50
    assert set(stats["api_call_by_agent"].values()) == {1}

    conn = sqlite3.connect(tmp_path / "llm_calls.sqlite")
    try:
        rows = conn.execute("SELECT batch_size, COUNT(*) FROM llm_calls GROUP BY batch_size").fetchall()
    finally:
        conn.close()
    assert rows == [(1, 50)], "mỗi agent phải có call riêng, không được batch"


def test_per_agent_cap_is_ten_even_when_another_agent_has_unused_capacity():
    budget = NganSachLLMTick(tick=1, toi_thieu=1, toi_da=20, default_toi_da_moi_task=10)
    budget.dat_yeu_cau_cho_tasks(["agent:A", "agent:B"])

    assert all(budget.bat_dau("agent:A", toi_da_task=10) for _ in range(10))
    assert not budget.bat_dau("agent:A", toi_da_task=10)
    assert budget.bat_dau("agent:B", toi_da_task=10)

    stats = budget.thong_ke()
    assert stats["api_call"] == 11
    assert stats["api_call_by_task"] == {"agent:A": 10, "agent:B": 1}
    assert stats["api_call_min_met"] is True


def test_v4_real_fake_provider_makes_50_independent_http_requests(tmp_path):
    cfg = _cfg()
    w = tao_the_gioi(cfg, seed=42, events_path=None)
    w.cfg.raw()["minds"]["dung_cong_cu_the_gioi"] = False
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _decision_response(json.loads(request.content))

    mind = MindReal(
        w, tmp_path, cfg, _env_15_keys(), tmp_path / "quota.sqlite",
        transport=httpx.MockTransport(handler), cho_toi_s=1.0,
    )
    chay_mot_tick(w, mind, len(w.parcels))

    assert len(requests) == 50
    assert mind.stats_tick["api_call"] == 50
    assert mind.stats_tick["api_call_min_met"] is True
    assert not mind.het_ngan_sach
    asked = {_agent_id_from_payload(json.loads(request.content)) for request in requests}
    assert len(asked) == 50


def test_v4_rpm_preflight_stops_before_spending_a_partial_cohort(tmp_path):
    """Two 4-RPM keys cannot honestly start the required 50-person burst."""
    cfg = _cfg()
    # The production v4 treatment may wait for a recoverable RPM window.  This
    # regression exercises the explicit no-wait/fail-closed branch instead.
    cfg.raw()["minds"]["llm_tick"]["cho_burst_rpm_toi_s"] = 0
    strict = cfg.raw()["minds"]["nghiem_thuc"]
    strict.update({
        "bat": True,
        "provider": "aistudio",
        "model": "gemini-3.1-flash-lite",
        "temperature": 0.7,
        "max_output_tokens": 200,
    })
    w = tao_the_gioi(cfg, seed=42, events_path=None)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _decision_response(json.loads(request.content))

    env = EnvKeys(gemini_keys=["fixture-key-0", "fixture-key-1"],
                  nine_key="fixture-nine-key", nine_base="http://fixture.invalid/v1",
                  llm_mode="real")
    mind = MindReal(w, tmp_path, cfg, env, tmp_path / "quota.sqlite",
                    transport=httpx.MockTransport(handler), cho_toi_s=1.0)

    assert not mind.kiem_tra_truoc_tick(w)
    assert mind.het_ngan_sach
    assert "RPM burst" in mind.ly_do_dung
    assert requests == [], "preflight phải dừng trước HTTP đầu tiên, không xử lý nửa làng"
    assert w.tick == 0, "preflight không được làm già đi hay cho nền kinh tế tiến một tick"


def test_rpm_preflight_does_not_double_count_a_route_shared_by_t0_and_t1():
    cfg = _cfg()
    env = EnvKeys(gemini_keys=[f"fixture-key-{i}" for i in range(15)], nine_key="",
                  nine_base="", llm_mode="real")
    gateway = GatewayReal(cfg, env, QuotaCounter(None))

    # 15×4 = 60 raw slots but the global safety headroom makes 51 available.
    # T0 and T1 share that one aistudio route; treating each tier independently
    # would incorrectly claim 102 slots and permit a partial 60-person cohort.
    ok, _reason = burst_guard(gateway, {"T0": 25, "T1": 25})
    assert ok
    ok, reason = burst_guard(gateway, {"T0": 30, "T1": 30})
    assert not ok
    assert "phân bổ được 51" in reason


def test_run_driver_keeps_world_at_tick_zero_when_autonomy_preflight_fails(
        tmp_path, monkeypatch):
    """The public runner, not only MindReal, must honour the no-half-tick contract."""
    import run as run_mod

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    args = run_mod._tao_parser().parse_args([
        "--mode", "real", "--ticks", "1", "--seed", "42", "--run-name", "rpm_preflight",
        "--scenario", "agrarian_transition_v1",
        "--config-overlay", str(OVERLAYS[0]),
        "--config-overlay", str(OVERLAYS[1]),
        "--config-overlay", str(OVERLAYS[2]),
        "--config-overlay", str(OVERLAYS[3]),
    ])
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _decision_response(json.loads(request.content))

    def factory(_mode, w, _args):
        w.cfg.raw()["minds"]["llm_tick"]["cho_burst_rpm_toi_s"] = 0
        env = EnvKeys(gemini_keys=["fixture-key-0", "fixture-key-1"],
                      nine_key="fixture-nine-key", nine_base="http://fixture.invalid/v1",
                      llm_mode="real")
        return MindReal(w, tmp_path / "rpm_preflight", w.cfg, env,
                        tmp_path / "quota.sqlite", transport=httpx.MockTransport(handler),
                        cho_toi_s=1.0)

    assert run_mod.chay_run(args, mind_factory=factory) == 0
    meta = json.loads((tmp_path / "rpm_preflight" / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["tick_cuoi"] == 0
    assert meta["terminal_reason"] == "llm_provider_budget_exhausted"
    assert "RPM burst" in meta["llm_preflight_ly_do"]
    assert requests == []


def test_mcp_never_uses_an_eleventh_request_for_one_agent():
    cfg = _cfg()
    w = tao_the_gioi(cfg, seed=71, events_path=None)
    aid = sorted(w.agents)[0]
    budget = NganSachLLMTick(tick=1, toi_thieu=1, toi_da=10, default_toi_da_moi_task=10)
    budget.dat_yeu_cau_cho_tasks([f"agent:{aid}"])
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if payload.get("tools"):
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{
                    "functionCall": {"name": "xem_thoi_tiet", "args": {}},
                }]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
            })
        return _decision_response(payload)

    gateway = GatewayReal(cfg, _env_15_keys(), QuotaCounter(None),
                          transport=httpx.MockTransport(handler))
    response = gateway.goi_agentic(
        LLMRequest(
            prompt=f'(id "{aid}") fixture MCP', ctx={}, tier="T0", batch_ids=[aid],
            tick_budget=budget, logical_id=f"agent:{aid}", logical_kind="decision",
            max_api_calls=10,
        ),
        w, aid,
    )

    assert len(calls) == 10
    assert len(response.tool_turns) == 9
    assert budget.thong_ke()["api_call"] == 10
    assert json.loads(response.text)["id"] == aid


def test_malformed_translator_sequence_number_is_ignored_not_raised():
    """Translator is recovery code: arbitrary LLM JSON must not kill a tick."""
    assert _stt_dich_hop_le({"stt": "0"}) == 0
    assert _stt_dich_hop_le({"stt": "khong-phai-so"}) is None
    assert _stt_dich_hop_le({"stt": None}) is None
    assert _stt_dich_hop_le({"stt": True}) is None
    assert _stt_dich_hop_le([]) is None


def test_ninerouter_mcp_records_every_physical_request_in_quota():
    """Nine-router tool turns must not look like one cheap quota call."""
    cfg = _cfg()
    w = tao_the_gioi(cfg, seed=72, events_path=None)
    aid = sorted(w.agents)[0]
    budget = NganSachLLMTick(tick=1, toi_thieu=1, toi_da=10, default_toi_da_moi_task=10)
    budget.dat_yeu_cau_cho_tasks([f"agent:{aid}"])
    quota = QuotaCounter(None)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        payload = json.loads(request.content)
        if payload.get("tools"):
            return httpx.Response(200, json={
                "choices": [{"message": {
                    "content": None,
                    "tool_calls": [{
                        "id": f"call-{len(requests)}",
                        "type": "function",
                        "function": {"name": "xem_thoi_tiet", "arguments": "{}"},
                    }],
                }}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            })
        return _decision_response(payload)

    env = EnvKeys(gemini_keys=[], nine_key="fixture-nine-key",
                  nine_base="http://fixture.invalid/v1", llm_mode="real")
    gateway = GatewayReal(cfg, env, quota, transport=httpx.MockTransport(handler))
    response = gateway.goi_agentic(
        LLMRequest(
            prompt=f'(id "{aid}") fixture MCP via 9router', ctx={}, tier="T0", batch_ids=[aid],
            tick_budget=budget, logical_id=f"agent:{aid}", logical_kind="decision",
            max_api_calls=10,
        ),
        w, aid,
    )

    assert len(requests) == 10
    assert len(response.tool_turns) == 9
    assert quota.rpd_da_dung("ninerouter", "gc/gemini-3.1-flash-lite-preview",
                             key_hash(env.nine_key), time.time()) == 10
