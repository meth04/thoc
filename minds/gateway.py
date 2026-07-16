"""Gateway LLM — interface chung mock | replay (real ở Phase 5). Log MỌI call (điều luật #6)."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LLMRequest:
    prompt: str
    ctx: dict[str, Any]  # máy-đọc-được — mock dùng cái này, KHÔNG parse prompt
    tier: str
    schema: str = "QuyetDinh"
    batch_ids: list[str] = field(default_factory=list)
    # Runtime-only scheduler metadata.  It is deliberately NOT rendered into
    # prompts/transcripts: it governs infrastructure cost, not what an agent
    # knows about the simulated world.
    tick_budget: Any | None = None
    logical_id: str = ""
    logical_kind: str = "decision"
    max_api_calls: int | None = None
    # Stable accounting identity shared by provider retries, JSON repair and a
    # terminal decision record. These fields are runtime metadata only; they are
    # never rendered into the prompt or exposed to the simulated agent.
    tick: int | None = None
    decision_id: str = ""
    attempt_source: str = ""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    tok_in: int = 0
    tok_out: int = 0
    latency_s: float = 0.0
    key_hash: str = ""
    # The successful physical-request identity, if this response came from a
    # guarded real provider. Per-attempt rows retain every failed/retried ID.
    quota_claim_id: str | None = None
    retries: int = 0
    # Explicit counters replace the overloaded legacy ``retries`` field. Keep
    # ``retries`` as a compatibility alias for old readers/artifacts.
    provider_retries: int = 0
    json_repair_retries: int = 0
    # Read-only MCP turns are part of a real agent's evidence trail. They are
    # empty for ordinary/mock calls and are persisted losslessly in transcript.
    tool_turns: list[dict[str, Any]] = field(default_factory=list)
    tool_catalog_hash: str | None = None


class LLMCallLog:
    """llm_calls.sqlite — mọi call kể cả mock: model, key-hash, token, latency, fallback.

    ``segment_id``/``superseded`` (ADR 0006 §C.1 ngoại lệ): row của một đoạn quỹ đạo bị bỏ
    (resume) vẫn là call **đã thực sự xảy ra, đã tiêu token/quota/USD**. Xóa chúng là làm
    đẹp chi phí ⇒ **KHÔNG BAO GIỜ DELETE**, chỉ ``superseded=1``. Telemetry vì thế báo hai
    số: ``call_burned`` (mọi row = chi phí) và ``call_effective`` (superseded=0 = quỹ đạo).

    Migration ``ALTER TABLE`` chỉ chạy ở **write path** (run mới / resume), guard bằng
    ``PRAGMA table_info`` để DB cũ vẫn mở được. Read path (telemetry/verify) KHÔNG BAO GIỜ
    ALTER — nó chỉ dùng ``COALESCE(superseded,0)=0`` khi cột có mặt.
    """

    def __init__(self, duong_dan: Path | None, *, segment_id: int = 0):
        self._conn = None
        self.path = Path(duong_dan) if duong_dan is not None else None
        self.segment_id = int(segment_id)
        self._lock = threading.RLock()
        self._attempt_ordinal: dict[str, int] = {}
        # kiến trúc 1-to-1 real: cả logical-call log lẫn per-HTTP-attempt log bị gọi từ
        # nhiều worker thread. SQLite connection dùng chung nhưng mọi write được khóa ở đây.
        if duong_dan is not None:
            duong_dan.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(duong_dan, check_same_thread=False)
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS llm_calls (
                    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER, tier TEXT, provider TEXT, model TEXT, key_hash TEXT,
                    batch_size INTEGER, tok_in INTEGER, tok_out INTEGER,
                    latency_ms INTEGER, retries INTEGER, fallback INTEGER, raw TEXT,
                    segment_id INTEGER, superseded INTEGER DEFAULT 0,
                    provider_retries INTEGER DEFAULT 0,
                    json_repair_retries INTEGER DEFAULT 0,
                    tool_turns INTEGER DEFAULT 0,
                    call_source TEXT,
                    quota_claim_id TEXT
                )"""
            )
            self._migrate()
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS llm_attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER,
                    parent_logical_id TEXT NOT NULL,
                    parent_decision_id TEXT,
                    logical_kind TEXT,
                    source TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    provider_retry_ordinal INTEGER DEFAULT 0,
                    route_ordinal INTEGER DEFAULT 0,
                    tool_turn_ordinal INTEGER,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    key_hash TEXT,
                    attempt_started INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER,
                    latency_ms INTEGER NOT NULL,
                    error_class TEXT,
                    billability TEXT NOT NULL,
                    quota_claim_id TEXT,
                    segment_id INTEGER,
                    superseded INTEGER DEFAULT 0
                )"""
            )
            attempt_columns = {r[1] for r in self._conn.execute("PRAGMA table_info(llm_attempts)")}
            if "quota_claim_id" not in attempt_columns:
                self._conn.execute("ALTER TABLE llm_attempts ADD COLUMN quota_claim_id TEXT")
            self._conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_llm_attempts_parent
                   ON llm_attempts(parent_decision_id, parent_logical_id, ordinal)"""
            )
            # engine.journal chỉ biết bảng legacy ``llm_calls``. Trigger additive này làm
            # attempt của cùng segment/tick bị supersede cùng logical rows, không xóa lịch sử.
            self._conn.execute(
                """CREATE TRIGGER IF NOT EXISTS trg_llm_calls_supersede_attempts
                   AFTER UPDATE OF superseded ON llm_calls
                   WHEN NEW.superseded = 1 AND COALESCE(OLD.superseded, 0) = 0
                   BEGIN
                     UPDATE llm_attempts SET superseded = 1
                     WHERE COALESCE(superseded, 0) = 0
                       AND tick = OLD.tick
                       AND COALESCE(segment_id, 0) = COALESCE(OLD.segment_id, 0);
                   END"""
            )
            self._conn.commit()

    def _migrate(self) -> None:
        """Migration additive cho DB cũ; không rewrite/delete bất kỳ row lịch sử nào."""
        cot = {r[1] for r in self._conn.execute("PRAGMA table_info(llm_calls)")}
        additions = {
            "segment_id": "INTEGER",
            "superseded": "INTEGER DEFAULT 0",
            "provider_retries": "INTEGER DEFAULT 0",
            "json_repair_retries": "INTEGER DEFAULT 0",
            "tool_turns": "INTEGER DEFAULT 0",
            "call_source": "TEXT",
            "quota_claim_id": "TEXT",
        }
        for ten, ddl in additions.items():
            if ten not in cot:
                self._conn.execute(f"ALTER TABLE llm_calls ADD COLUMN {ten} {ddl}")

    def dat_segment(self, segment_id: int) -> None:
        """Set the segment for subsequent immutable writes.

        Recovery superseding belongs to :class:`engine.journal.RunJournals`: it must happen
        before the ``RecoveryEntry`` is persisted, with an attempt range/count as evidence.
        This method deliberately performs no recovery inference or mutation after the fact.
        """
        with self._lock:
            self.segment_id = int(segment_id)

    def max_call_id(self) -> int:
        if self._conn is None:
            return 0
        with self._lock:
            return int(self._conn.execute(
                "SELECT COALESCE(MAX(call_id),0) FROM llm_calls").fetchone()[0])

    @staticmethod
    def _tick_cua(req: LLMRequest) -> int:
        if req.tick is not None:
            return int(req.tick)
        budget = getattr(req, "tick_budget", None)
        return int(getattr(budget, "tick", 0) or 0)

    def ghi(self, tick: int, req: LLMRequest, resp: LLMResponse, fallback: bool) -> None:
        if self._conn is None:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO llm_calls (tick, tier, provider, model, key_hash, batch_size,"
                " tok_in, tok_out, latency_ms, retries, fallback, raw, segment_id, superseded,"
                " provider_retries, json_repair_retries, tool_turns, call_source, quota_claim_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?)",
                (tick, req.tier, resp.provider, resp.model, resp.key_hash, len(req.batch_ids),
                 resp.tok_in, resp.tok_out, int(resp.latency_s * 1000), resp.retries,
                 int(fallback), resp.text[:4000], self.segment_id,
                 int(resp.provider_retries), int(resp.json_repair_retries),
                 len(resp.tool_turns), req.attempt_source or req.logical_kind,
                 resp.quota_claim_id),
            )

    def ghi_attempt(
        self,
        req: LLMRequest,
        *,
        provider: str,
        model: str,
        key_hash: str,
        attempt_started: bool,
        status: str,
        http_status: int | None,
        latency_s: float,
        error_class: str | None,
        billability: str,
        provider_retry_ordinal: int = 0,
        route_ordinal: int = 0,
        tool_turn_ordinal: int | None = None,
        source: str | None = None,
        quota_claim_id: str | None = None,
    ) -> None:
        """Append one immutable row per attempted HTTP turn or denied-before-start event.

        ``attempt_started=0`` is deliberately distinct from a failed HTTP attempt: no request
        left the process and ``billability`` must be ``not_billable``. All started failures use
        ``unknown`` unless a provider returned a successful, usage-bearing response.
        """
        if self._conn is None:
            return
        statuses = {
            "success", "rate_limited", "http_error", "network_error",
            "response_parse_error", "budget_denied", "quota_denied",
        }
        if status not in statuses:
            raise ValueError(f"unknown HTTP attempt status: {status}")
        if billability not in {"billable", "not_billable", "unknown"}:
            raise ValueError(f"unknown billability: {billability}")
        if not attempt_started and billability != "not_billable":
            raise ValueError("denied-before-start must be not_billable")
        parent = req.decision_id or req.logical_id or f"{req.logical_kind}:anonymous"
        with self._lock:
            if parent not in self._attempt_ordinal:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(ordinal),0) FROM llm_attempts "
                    "WHERE COALESCE(parent_decision_id,'')=?",
                    (req.decision_id or parent,),
                ).fetchone()
                self._attempt_ordinal[parent] = int(row[0] or 0)
            self._attempt_ordinal[parent] += 1
            ordinal = self._attempt_ordinal[parent]
            self._conn.execute(
                "INSERT INTO llm_attempts (tick, parent_logical_id, parent_decision_id,"
                " logical_kind, source, ordinal, provider_retry_ordinal, route_ordinal,"
                " tool_turn_ordinal, provider, model, key_hash, attempt_started, status,"
                " http_status, latency_ms, error_class, billability, quota_claim_id, segment_id, superseded)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    self._tick_cua(req), req.logical_id or parent, req.decision_id or parent,
                    req.logical_kind, source or req.attempt_source or req.logical_kind, ordinal,
                    int(provider_retry_ordinal), int(route_ordinal), tool_turn_ordinal,
                    provider, model, key_hash, int(attempt_started), status, http_status,
                    max(0, int(latency_s * 1000)), error_class, billability, quota_claim_id,
                    self.segment_id,
                ),
            )
            # An HTTP attempt is cost evidence. Commit immediately so a process crash after
            # the request cannot erase the row while the provider may still have billed it.
            self._conn.commit()

    def attempt_summary(
        self, *, effective_only: bool = True, tick: int | None = None
    ) -> dict[str, int]:
        """Stable counters for telemetry owner; no interpretation is hidden in aliases."""
        if self._conn is None:
            return {}
        clauses: list[str] = []
        params: list[int] = []
        if effective_only:
            clauses.append("COALESCE(superseded,0)=0")
        if tick is not None:
            clauses.append("tick=?")
            params.append(int(tick))
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                "SELECT source, status, attempt_started, COUNT(*) FROM llm_attempts "
                f"{where} GROUP BY source, status, attempt_started",  # noqa: S608
                params,
            ).fetchall()
        out: dict[str, int] = {}
        for source, status, started, count in rows:
            out[f"source:{source}"] = out.get(f"source:{source}", 0) + int(count)
            out[f"status:{status}"] = out.get(f"status:{status}", 0) + int(count)
            key = "provider_request_started" if started else "denied_before_start"
            out[key] = out.get(key, 0) + int(count)
        return dict(sorted(out.items()))

    def flush(self) -> None:
        if self._conn is not None:
            with self._lock:
                self._conn.commit()

    def dong(self) -> None:
        if self._conn is not None:
            with self._lock:
                self._conn.commit()
                self._conn.close()
                self._conn = None


class MockProvider:
    """Provider mock: PersonaBot + adversarial, latency giả lập N(1.2,0.3) (tắt --fast)."""

    ten = "mock"

    def __init__(self, w, p_malformed: float, fast: bool):
        self.w = w
        self.p_malformed = p_malformed
        self.fast = fast

    def goi(self, req: LLMRequest, attempt: int = 0) -> LLMResponse:
        from minds.personabot import sinh_quyet_dinh, tra_loi_mock
        from minds.tick_budget import bat_dau_yeu_cau

        # A mock invocation is the offline equivalent of one provider request.
        # This makes the same 1..N scheduler contract testable without any
        # external model call. Transcript replay intentionally bypasses it.
        bat_dau_yeu_cau(req)
        t0 = time.time()
        batch = [
            sinh_quyet_dinh(self.w, aid, req.ctx["bc"], req.ctx["da_nham"],
                            req.ctx["cau_hon_den"], attempt=attempt)
            for aid in req.batch_ids
        ]
        text = tra_loi_mock(self.w, batch, self.p_malformed, attempt=attempt)
        latency = time.time() - t0
        if not self.fast:
            cfg = self.w.cfg.get("models.mock.gia_lap_latency")
            g = self.w.rng.get(f"mock_latency:{req.batch_ids[0]}:{attempt}", self.w.tick)
            time.sleep(max(0.0, float(g.normal(cfg["mean_s"], cfg["std_s"]))))
        return LLMResponse(
            text=text, provider="mock", model=f"personabot-{req.tier}",
            tok_in=len(req.prompt) // 4, tok_out=len(text) // 4, latency_s=latency,
            key_hash=hashlib.sha256(b"mock").hexdigest()[:8],
        )
