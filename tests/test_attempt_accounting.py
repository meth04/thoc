"""Terminal-decision and per-HTTP-attempt accounting, entirely offline.

All provider behavior uses ``httpx.MockTransport``. These tests distinguish a request that
actually left the process from a denied-before-start turn and prove that transcript replay
consumes explicit terminal rows instead of using a miss as a fallback control signal.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from engine.journal import (
    CheckpointEntry,
    JournalIdentity,
    LoiJournal,
    RunJournals,
    SqliteState,
)
from minds.gateway import LLMCallLog, LLMRequest, LLMResponse
from minds.keypool import EnvKeys
from minds.providers_real import GatewayReal
from minds.quota import QuotaCounter
from minds.real import MindReal
from minds.tick_budget import NganSachLLMTick
from minds.transcript import (
    TranscriptProvider,
    TranscriptReader,
    TranscriptTerminalMismatch,
    bam_prompt,
    tao_mind_replay,
)
from tests.helpers import chay_tick, the_gioi_test
from tests.test_real_mind import _ids_tu_prompt, _resp
from tools.experiments import runtime_source_identity


def _env() -> EnvKeys:
    return EnvKeys(
        gemini_keys=["fixture-key-1", "fixture-key-2"],
        nine_key="fixture-nine",
        nine_base="http://fixture.invalid/v1",
        llm_mode="real",
    )


def _world(*, max_calls: int = 2, tools: bool = False, agents: int = 2):
    w = the_gioi_test(seed=811, giu_lai=agents, thoc_moi_nguoi=2000)
    w.cfg.raw()["minds"]["dung_cong_cu_the_gioi"] = tools
    w.cfg.raw()["minds"]["cong_cu_max_luot"] = max_calls
    w.cfg.raw()["minds"]["llm_tick"].update({
        "bat": True,
        "pham_vi": "moi_agent",
        "toi_thieu_call": 1,
        "toi_da_call": max_calls,
        "toi_da_call_moi_quyet_dinh": max_calls,
        "kiem_tra_burst_rpm": False,
    })
    # One route makes failure fixtures deterministic; no hidden model failover.
    w.cfg.raw()["minds"]["nghiem_thuc"].update({
        "bat": True,
        "provider": "aistudio",
        "model": "gemini-3.1-flash-lite",
        "temperature": 0.2,
        "max_output_tokens": 300,
    })
    return w


def _decision(ids: list[str]) -> str:
    return json.dumps([
        {"id": aid, "hanh_dong": [{"loai": "phan_bo_cong", "hoc": False}],
         "ly_do": "fixture"}
        for aid in ids
    ], ensure_ascii=False)


def _transport(handler: Callable[[dict], httpx.Response]) -> httpx.MockTransport:
    def wrapped(request: httpx.Request) -> httpx.Response:
        return handler(json.loads(request.content))

    return httpx.MockTransport(wrapped)


def _mind(w, run_dir: Path, transport: httpx.MockTransport) -> MindReal:
    return MindReal(
        w,
        run_dir,
        w.cfg,
        _env(),
        run_dir / "quota.sqlite",
        transport=transport,
        cho_toi_s=0.01,
        transcript_path=run_dir / "transcript.jsonl",
    )


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _attempts(run_dir: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(run_dir / "llm_calls.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute("SELECT * FROM llm_attempts ORDER BY attempt_id"))
    finally:
        conn.close()


def _replay_one_tick(run_dir: Path, world_factory: Callable[[], object], expected_hash: str):
    reader = TranscriptReader(run_dir / "transcript.jsonl")
    w2 = world_factory()
    mind2 = tao_mind_replay(w2, w2.cfg, "real", reader)
    chay_tick(w2, mind2, 1)
    assert w2.world_hash() == expected_hash
    assert reader.misses == 0
    assert reader.con_lai() == 0


def _terminal_rows(run_dir: Path) -> list[dict]:
    return [row for row in _rows(run_dir / "transcript.jsonl")
            if row.get("record_type") == "decision_terminal"]


def test_success_has_one_terminal_per_scheduled_agent_and_started_attempt(tmp_path):
    w = _world(max_calls=2, agents=2)
    run_dir = tmp_path / "success"

    def handler(payload: dict) -> httpx.Response:
        return _resp(payload, _decision(_ids_tu_prompt(payload)))

    mind = _mind(w, run_dir, _transport(handler))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    terminals = _terminal_rows(run_dir)
    assert len(terminals) == mind.stats_tick["scheduled_agent_decision"] == 2
    assert {row["terminal_reason"] for row in terminals} == {"response"}
    assert len({row["decision_id"] for row in terminals}) == 2
    assert mind.stats_tick["completed_agent_decision_turn"] == 2
    assert mind.stats_tick["parsed_agent_decision"] == 2
    assert mind.stats_tick["exact_one_terminal_decision"] is True

    attempts = _attempts(run_dir)
    assert len(attempts) == 2
    assert {row["status"] for row in attempts} == {"success"}
    assert {row["attempt_started"] for row in attempts} == {1}
    assert {row["billability"] for row in attempts} == {"billable"}
    assert mind.stats_tick["provider_request_started"] == 2
    _replay_one_tick(run_dir, lambda: _world(max_calls=2, agents=2), h)


def test_replay_rejects_tampered_terminal_state(tmp_path):
    """A terminal reason alone cannot turn an accepted replay into a fallback branch."""
    w = _world(max_calls=2, agents=1)
    run_dir = tmp_path / "tampered-terminal-state"
    mind = _mind(
        w,
        run_dir,
        _transport(lambda payload: _resp(payload, _decision(_ids_tu_prompt(payload)))),
    )
    chay_tick(w, mind, 1)
    mind.log.dong()
    mind.transcript.dong()

    transcript_path = run_dir / "transcript.jsonl"
    rows = _rows(transcript_path)
    terminal = next(row for row in rows if row.get("record_type") == "decision_terminal")
    terminal["terminal_state"] = "fallback_selected"  # tampered: reason remains "response"
    transcript_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    reader = TranscriptReader(transcript_path)
    replay_world = _world(max_calls=2, agents=1)
    replay_mind = tao_mind_replay(replay_world, replay_world.cfg, "real", reader)
    with pytest.raises(TranscriptTerminalMismatch, match="terminal state/reason"):
        chay_tick(replay_world, replay_mind, 1)


@pytest.mark.parametrize(("terminal_state", "message"), (
    (None, "missing terminal state"),
    ("not-a-terminal-state", "unknown terminal state"),
    ("fallback_selected", "inconsistent recorded terminal state/reason"),
))
def test_terminal_consume_rejects_missing_unknown_or_inconsistent_state(
    tmp_path, terminal_state, message
):
    """Forged transcript-2 terminal rows fail closed before replay can use them."""
    req = LLMRequest(
        prompt="terminal fixture", ctx={}, tier="T0", tick=1,
        logical_id="agent:A0001", decision_id="decision:1:A0001",
    )
    row = {
        "schema_version": "transcript-2",
        "record_type": "decision_terminal",
        "decision_id": req.decision_id,
        "prompt_hash": bam_prompt(req.prompt),
        "terminal_reason": "response",
        "terminal_state": terminal_state,
    }
    path = tmp_path / "forged-terminal.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    provider = TranscriptProvider(TranscriptReader(path))
    with pytest.raises(TranscriptTerminalMismatch, match=message):
        provider.consume_terminal(req, "response")


def test_terminal_consume_legacy_transcript_without_terminal_schema_is_explicitly_compatible(
    tmp_path,
):
    """Transcript-1 provider rows have no decision-terminal contract to consume."""
    req = LLMRequest(
        prompt="legacy fixture", ctx={}, tier="T0", tick=1,
        logical_id="agent:A0001", decision_id="decision:1:A0001",
    )
    path = tmp_path / "legacy-transcript.jsonl"
    path.write_text(json.dumps({
        "prompt_hash": bam_prompt(req.prompt),
        "response_raw": "{}",
    }) + "\n", encoding="utf-8")

    reader = TranscriptReader(path)
    assert reader.co_terminal_schema is False
    assert TranscriptProvider(reader).consume_terminal(req, "response") is None


def test_429_failover_records_each_route_attempt(tmp_path):
    w = _world(max_calls=3, agents=1)
    # Use normal T1 routes so one failed aistudio attempt can fail over to nine-router.
    w.cfg.raw()["minds"]["nghiem_thuc"]["bat"] = False
    w.cfg.raw()["quotas"]["ninerouter"]["models"][
        "gc/gemini-3.1-flash-lite-preview"
    ].update({"tpm": 1_000_000, "tpm_policy": "verified"})
    log = LLMCallLog(tmp_path / "attempts.sqlite")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        payload = json.loads(request.content)
        if "generativelanguage" in str(request.url):
            return httpx.Response(429, json={"error": "rate"})
        return _resp(payload, _decision(["A0001"]))

    gw = GatewayReal(
        w.cfg,
        _env(),
        QuotaCounter(None),
        transport=httpx.MockTransport(handler),
        retry_toi_da=0,
        attempt_log=log,
    )
    req = LLMRequest(
        prompt="fixture", ctx={}, tier="T1", batch_ids=["A0001"],
        tick=1, logical_id="agent:A0001", decision_id="decision:1:A0001",
        attempt_source="decision_initial",
    )
    response = gw.goi(req)
    log.flush()

    assert response.provider == "ninerouter"
    conn = sqlite3.connect(tmp_path / "attempts.sqlite")
    rows = conn.execute(
        "SELECT provider, route_ordinal, provider_retry_ordinal, status, http_status,"
        " attempt_started, billability FROM llm_attempts ORDER BY attempt_id"
    ).fetchall()
    conn.close()
    assert rows == [
        ("aistudio", 0, 0, "rate_limited", 429, 1, "unknown"),
        ("ninerouter", 1, 1, "success", 200, 1, "billable"),
    ]
    assert len(calls) == 2


def test_disconnect_is_provider_terminal_and_replays_without_miss(tmp_path):
    w = _world(max_calls=4, agents=1)
    run_dir = tmp_path / "disconnect"

    def handler(_payload: dict) -> httpx.Response:
        raise httpx.RemoteProtocolError("fixture disconnect")

    mind = _mind(w, run_dir, _transport(handler))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    terminals = _terminal_rows(run_dir)
    assert [row["terminal_reason"] for row in terminals] == ["provider_error"]
    attempts = _attempts(run_dir)
    assert attempts
    assert {row["status"] for row in attempts} == {"network_error"}
    assert all(row["attempt_started"] == 1 for row in attempts)
    assert all(row["billability"] == "unknown" for row in attempts)
    _replay_one_tick(run_dir, lambda: _world(max_calls=4, agents=1), h)


def test_malformed_then_json_repair_has_separate_sources_and_terminal(tmp_path):
    w = _world(max_calls=2, agents=1)
    run_dir = tmp_path / "repair"

    def handler(payload: dict) -> httpx.Response:
        prompt = payload["contents"][0]["parts"][0]["text"]
        if "[LỖI JSON" in prompt:
            return _resp(payload, _decision(_ids_tu_prompt(payload)))
        return _resp(payload, "không phải json")

    mind = _mind(w, run_dir, _transport(handler))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    attempts = _attempts(run_dir)
    assert [row["source"] for row in attempts] == ["decision_initial", "json_repair"]
    assert [row["status"] for row in attempts] == ["success", "success"]
    assert [row["ordinal"] for row in attempts] == [1, 2]
    assert [row["terminal_reason"] for row in _terminal_rows(run_dir)] == ["response"]

    conn = sqlite3.connect(run_dir / "llm_calls.sqlite")
    calls = conn.execute(
        "SELECT call_source, provider_retries, json_repair_retries, tool_turns, retries "
        "FROM llm_calls ORDER BY call_id"
    ).fetchall()
    conn.close()
    assert calls == [
        ("decision_initial", 0, 0, 0, 0),
        ("json_repair", 0, 1, 0, 1),
    ]
    _replay_one_tick(run_dir, lambda: _world(max_calls=2, agents=1), h)


def test_parse_unusable_terminal_replays_without_missing_control_signal(tmp_path):
    w = _world(max_calls=2, agents=1)
    run_dir = tmp_path / "parse-unusable"

    mind = _mind(w, run_dir, _transport(lambda payload: _resp(payload, "vẫn hỏng")))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    assert [row["terminal_reason"] for row in _terminal_rows(run_dir)] == ["parse_unusable"]
    _replay_one_tick(run_dir, lambda: _world(max_calls=2, agents=1), h)


def test_budget_denial_before_initial_request_is_not_attempt_started(tmp_path, monkeypatch):
    w = _world(max_calls=1, agents=1)
    run_dir = tmp_path / "deny-initial"

    def deny(self, logical_id: str, *, loai: str = "decision", toi_da_task=None) -> bool:
        _ = logical_id, loai, toi_da_task
        self.bi_tu_choi += 1
        return False

    monkeypatch.setattr(NganSachLLMTick, "bat_dau", deny)
    mind = _mind(w, run_dir, _transport(lambda payload: _resp(payload, _decision(["A0001"]))))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    assert [row["terminal_reason"] for row in _terminal_rows(run_dir)] == ["budget_denied"]
    attempts = _attempts(run_dir)
    assert len(attempts) == 1
    assert attempts[0]["status"] == "budget_denied"
    assert attempts[0]["attempt_started"] == 0
    assert attempts[0]["billability"] == "not_billable"
    assert mind.stats_tick["provider_request_started"] == 0
    assert mind.stats_tick["provider_request_denied_before_start"] == 1
    _replay_one_tick(run_dir, lambda: _world(max_calls=1, agents=1), h)


def test_budget_denial_on_json_retry_records_started_and_denied_separately(tmp_path):
    w = _world(max_calls=1, agents=1)
    run_dir = tmp_path / "deny-retry"
    mind = _mind(w, run_dir, _transport(lambda payload: _resp(payload, "hỏng")))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    attempts = _attempts(run_dir)
    assert [(row["source"], row["status"], row["attempt_started"]) for row in attempts] == [
        ("decision_initial", "success", 1),
        ("json_repair", "budget_denied", 0),
    ]
    assert [row["terminal_reason"] for row in _terminal_rows(run_dir)] == ["budget_denied"]
    _replay_one_tick(run_dir, lambda: _world(max_calls=1, agents=1), h)


def test_budget_denial_after_tool_turn_transcripts_partial_evidence_and_replays(
    tmp_path, monkeypatch
):
    w = _world(max_calls=2, tools=True, agents=1)
    run_dir = tmp_path / "deny-tool"

    original_start = NganSachLLMTick.bat_dau

    def allow_one_then_deny(self, logical_id: str, *, loai: str = "decision",
                            toi_da_task=None) -> bool:
        if self.theo_task.get(logical_id, 0) >= 1:
            self.bi_tu_choi += 1
            return False
        return original_start(
            self, logical_id, loai=loai, toi_da_task=toi_da_task
        )

    monkeypatch.setattr(NganSachLLMTick, "bat_dau", allow_one_then_deny)

    def handler(payload: dict) -> httpx.Response:
        assert payload.get("tools"), "first turn must expose read-only tools"
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{
                "functionCall": {"name": "xem_thoi_tiet", "args": {}},
            }]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
        })

    mind = _mind(w, run_dir, _transport(handler))
    chay_tick(w, mind, 1)
    h = w.world_hash()
    mind.log.dong()
    mind.transcript.dong()

    terminals = _terminal_rows(run_dir)
    assert [row["terminal_reason"] for row in terminals] == ["budget_denied"]
    assert len(terminals[0]["tool_turns"]) == 1
    attempts = _attempts(run_dir)
    assert [(row["source"], row["status"], row["attempt_started"]) for row in attempts] == [
        ("tool_turn", "success", 1),
        ("decision_initial", "budget_denied", 0),
    ]
    _replay_one_tick(
        run_dir, lambda: _world(max_calls=2, tools=True, agents=1), h
    )


def test_all_denied_tail_recovery_records_attempt_evidence_before_rebase(tmp_path):
    """A denied-only tail has no logical call, but still needs a RecoveryEntry counterpart."""
    run_dir = tmp_path / "run"
    identity = JournalIdentity(
        config_sha256="cfg", runtime_source_identity=runtime_source_identity()
    )
    journals = RunJournals.moi(run_dir, run_name="run", identity=identity)
    log = LLMCallLog(run_dir / "llm_calls.sqlite", segment_id=0)
    req = LLMRequest(
        prompt="x", ctx={}, tier="T0", batch_ids=["A0001"], tick=2,
        logical_id="agent:A0001", decision_id="decision:2:A0001",
        attempt_source="decision_initial",
    )
    log.ghi_attempt(
        req, provider="aistudio", model="m", key_hash="abcd1234",
        attempt_started=False, status="budget_denied", http_status=None, latency_s=0.0,
        error_class="LoiVuotNganSachTick", billability="not_billable",
    )
    journals.manifest.checkpoints.append(CheckpointEntry(
        tick=1, segment_id=0, world_hash="h", written_at_utc="fixture",
        journals={"llm_calls": SqliteState(
            max_call_id=0, record_count=0, max_attempt_id=0, attempt_record_count=0,
        )},
    ))
    journals.manifest.checkpoint_tick = 1
    journals.manifest.journals = journals.manifest.checkpoints[-1].journals
    journals._ghi_manifest()

    recovery = journals.restore(1, identity=identity)
    ledger = recovery.journals["llm_calls"]
    assert ledger["rows_superseded"] == 0
    assert ledger["attempt_record_count"] == 1
    assert ledger["attempt_rows_superseded"] == 1
    assert ledger["attempt_id_range"] == [1, 1]
    # ``dat_segment`` is now deliberately write-only: recovery already has its evidence.
    log.dat_segment(1)
    conn = sqlite3.connect(run_dir / "llm_calls.sqlite")
    assert conn.execute("SELECT superseded FROM llm_attempts").fetchone()[0] == 1
    conn.close()
    manifest = RunJournals.doc_manifest(run_dir)
    assert manifest is not None
    assert manifest.recoveries[-1].journals["llm_calls"]["attempt_rows_superseded"] == 1
    audit_row = json.loads((run_dir / "journal_recovery.jsonl").read_text(encoding="utf-8"))
    assert audit_row["attempt_record_count"] == audit_row["attempt_rows_superseded"] == 1


def test_resume_rejects_legacy_checkpoint_missing_attempt_prefix(tmp_path):
    run_dir = tmp_path / "legacy-prefix"
    identity = JournalIdentity(
        config_sha256="cfg", runtime_source_identity=runtime_source_identity()
    )
    journals = RunJournals.moi(run_dir, run_name="legacy-prefix", identity=identity)
    log = LLMCallLog(run_dir / "llm_calls.sqlite")
    req = LLMRequest(prompt="x", ctx={}, tier="T0", tick=1, logical_id="agent:A0001")
    log.ghi_attempt(
        req, provider="aistudio", model="m", key_hash="abcd1234",
        attempt_started=False, status="budget_denied", http_status=None, latency_s=0.0,
        error_class="LoiVuotNganSachTick", billability="not_billable",
    )
    # Exact legacy shape: a checkpoint has logical-call metadata but no attempt prefix fields.
    journals.manifest.checkpoints.append(CheckpointEntry(
        tick=1, segment_id=0, world_hash="h", written_at_utc="fixture",
        journals={"llm_calls": SqliteState(max_call_id=0, record_count=0)},
    ))
    with pytest.raises(LoiJournal, match="E-JM-09"):
        journals.restore(1, identity=identity)
    conn = sqlite3.connect(run_dir / "llm_calls.sqlite")
    assert conn.execute("SELECT superseded FROM llm_attempts").fetchone()[0] == 0
    conn.close()


def test_attempt_schema_migrates_old_calls_and_supersedes_by_segment_tick(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE llm_calls (call_id INTEGER PRIMARY KEY AUTOINCREMENT, tick INTEGER,"
        " tier TEXT, provider TEXT, model TEXT, key_hash TEXT, batch_size INTEGER,"
        " tok_in INTEGER, tok_out INTEGER, latency_ms INTEGER, retries INTEGER,"
        " fallback INTEGER, raw TEXT)"
    )
    conn.execute(
        "INSERT INTO llm_calls (tick, tier, provider, model, retries, fallback, raw)"
        " VALUES (2, 'T0', 'mock', 'legacy', 3, 0, 'x')"
    )
    conn.commit()
    conn.close()

    log = LLMCallLog(path, segment_id=0)
    req = LLMRequest(
        prompt="x", ctx={}, tier="T0", batch_ids=["A0001"], tick=2,
        logical_id="agent:A0001", decision_id="decision:2:A0001",
        attempt_source="decision_initial",
    )
    log.ghi_attempt(
        req, provider="aistudio", model="m", key_hash="abcd1234",
        attempt_started=True, status="success", http_status=200, latency_s=0.01,
        error_class=None, billability="billable",
    )
    log.ghi(2, req, LLMResponse(text="{}", provider="aistudio", model="m"), False)
    log.flush()

    conn = sqlite3.connect(path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_calls)")}
    assert {"provider_retries", "json_repair_retries", "tool_turns", "call_source"} <= columns
    assert conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0] == 2
    conn.execute(
        "UPDATE llm_calls SET superseded=1 WHERE tick=2 AND COALESCE(segment_id,0)=0"
    )
    conn.commit()
    assert conn.execute(
        "SELECT COUNT(*) FROM llm_attempts WHERE superseded=1"
    ).fetchone()[0] == 1
    conn.close()
