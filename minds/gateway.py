"""Gateway LLM — interface chung mock | replay (real ở Phase 5). Log MỌI call (điều luật #6)."""

from __future__ import annotations

import hashlib
import sqlite3
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


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    tok_in: int = 0
    tok_out: int = 0
    latency_s: float = 0.0
    key_hash: str = ""
    retries: int = 0


class LLMCallLog:
    """llm_calls.sqlite — mọi call kể cả mock: model, key-hash, token, latency, fallback."""

    def __init__(self, duong_dan: Path | None):
        self._conn = None
        # kiến trúc 1-to-1 real: log.ghi bị gọi từ nhiều worker thread (fan-out per-agent)
        # → check_same_thread=False; orchestrator serial hóa bằng khoá riêng.
        if duong_dan is not None:
            duong_dan.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(duong_dan, check_same_thread=False)
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS llm_calls (
                    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER, tier TEXT, provider TEXT, model TEXT, key_hash TEXT,
                    batch_size INTEGER, tok_in INTEGER, tok_out INTEGER,
                    latency_ms INTEGER, retries INTEGER, fallback INTEGER, raw TEXT
                )"""
            )

    def ghi(self, tick: int, req: LLMRequest, resp: LLMResponse, fallback: bool) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO llm_calls (tick, tier, provider, model, key_hash, batch_size,"
            " tok_in, tok_out, latency_ms, retries, fallback, raw)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (tick, req.tier, resp.provider, resp.model, resp.key_hash, len(req.batch_ids),
             resp.tok_in, resp.tok_out, int(resp.latency_s * 1000), resp.retries,
             int(fallback), resp.text[:4000]),
        )

    def flush(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def dong(self) -> None:
        if self._conn is not None:
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
