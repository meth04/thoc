"""Transcript-replay cho LLM THẬT (P1 — reports/publication_roadmap.md §2).

Một run ghi MỌI call vào ``data/runs/<run>/transcript.jsonl`` (append-only); replay nạp
lại response theo ``prompt_hash`` thay vì gọi API → chạy lại nguyên pipeline
(repair → validate → intent → apply) → CÙNG world-hash. Đây là cổng REPRODUCIBILITY
reviewer đòi: "kết luận real tái lập được từ artifact".

Vì sao tất định (điều luật #4):
- Prompt là hàm THUẦN của trạng thái thế giới; ``RngTree.get`` spawn Generator riêng theo
  (subsystem × tick) — KHÔNG có stream chia sẻ — nên bỏ qua call sinh-quyết-định lúc
  replay không hề động vào RNG engine. Cùng transcript ⇒ cùng chuỗi prompt ⇒ cùng
  response ⇒ cùng world-hash (quy nạp theo tick).
- Tra cứu bằng ``prompt_hash`` (không bằng call_id): fan-out song song real ghi call theo
  thứ tự HOÀN TẤT không tất định, nhưng prompt mỗi agent là duy nhất (chứa id) nên khóa
  theo nội dung prompt loại bỏ phụ thuộc thứ tự. Trùng prompt hiếm (nén hồi ký) xử lý FIFO.

Che key: prompt/response đi qua ``che_key`` trước khi ghi (điều luật #4 mục 4 — key không
bao giờ lộ). ``prompt_hash`` băm prompt GỐC nên replay (băm ``req.prompt`` gốc) vẫn khớp.

GIỚI HẠN (không overclaim):
- Vòng công cụ MCP (``goi_agentic``) ghi 1 entry/agent: prompt khởi đầu, từng tool-call /
  result (kèm hash), và QUYẾT ĐỊNH cuối. Khi replay, các tool CHỈ ĐỌC được chạy lại trên đúng
  snapshot rồi so với transcript; điều này chứng minh information set, không biến tool thành
  một transition hay bằng chứng rằng lựa chọn là tối ưu.
- Hồi ký/niềm tin (``a.hoi_ky``, ``a.niem_tin``) KHÔNG vào world_hash nhưng CÓ trong prompt
  tick sau; nên mọi call (kể cả nén/phản tư) đều được ghi + phục vụ từ transcript để prompt
  các tick sau trùng khít.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from pathlib import Path

from minds.gateway import LLMRequest, LLMResponse
from minds.providers_real import LoiHetQuota, LoiProviderHong, che_key
from minds.tick_budget import LoiVuotNganSachTick

TERMINAL_REASONS = frozenset({
    "response", "budget_denied", "parse_unusable", "provider_error",
})
TERMINAL_STATES = frozenset({"decision_accepted", "fallback_selected"})
TERMINAL_SCHEMA_VERSIONS = frozenset({"transcript-2"})


def terminal_state_for_reason(reason: str) -> str:
    """The only terminal state compatible with one replayed decision reason."""
    if reason not in TERMINAL_REASONS:
        raise ValueError(f"unknown terminal reason: {reason}")
    return "decision_accepted" if reason == "response" else "fallback_selected"


def bam_prompt(prompt: str) -> str:
    """sha256 hex của prompt — khóa tra cứu transcript, tất định (điều luật #4)."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class TranscriptWriter:
    """Ghi transcript.jsonl append-only: mỗi call một dòng JSON đã che key.

    ``call_id`` phải DUY NHẤT TOÀN RUN. Trước P0.2, writer mở ``"a"`` nhưng đặt ``_n = 0``
    ⇒ mỗi process mới đếm lại từ 1 ⇒ ``real60_spatial`` có **403 call_id bị dùng lại**
    (`docs/reviews/Report_v2-ledger.md` F-05). ``start_call_id`` được gieo lại từ
    ``record_count`` của checkpoint đang nạp (``engine/journal.py``).

    ``run_uuid``/``segment_id`` là metadata forensic (phân biệt bản ghi giữa file live và
    file quarantine). **Khóa replay VẪN là ``prompt_hash``** — không đổi.
    """

    def __init__(self, path: Path, *, start_call_id: int = 0,
                 run_uuid: str | None = None, segment_id: int = 0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a", encoding="utf-8")  # noqa: SIM115 — giữ mở suốt run
        self._n = int(start_call_id)
        self.run_uuid = run_uuid
        self.segment_id = int(segment_id)

    def rebase(self, *, start_call_id: int, run_uuid: str | None = None,
               segment_id: int = 0) -> None:
        """Gieo lại counter/identity sau khi run.py nạp journal manifest (mind được dựng
        trước khi biết segment). Chỉ hợp lệ trước call đầu tiên của phiên."""
        self._n = int(start_call_id)
        self.run_uuid = run_uuid
        self.segment_id = int(segment_id)

    @property
    def so_ghi(self) -> int:
        """call_id cao nhất đã ghi (toàn run)."""
        return self._n

    def ghi(self, tick: int, tier: str, provider: str, model: str, temperature,
            prompt: str, response_raw: str, tok_in: int, tok_out: int,
            *, error_type: str | None = None, error_message: str | None = None,
            tool_turns: list[dict] | None = None,
            tool_catalog_hash: str | None = None,
            logical_id: str = "", logical_kind: str = "decision",
            decision_id: str = "", source: str = "") -> None:
        """Ghi cả response thành công lẫn lỗi terminal.

        Một lỗi provider là một nhánh điều khiển có tác dụng lên run (fallback/dừng êm),
        không phải ``missing data``. Ghi nó vào transcript để replay tái hiện đúng nhánh
        thay vì cố ý tạo một miss giả ở lần chạy sau.
        """
        self._n += 1
        is_error = error_type is not None or provider == "loi"
        self._f.write(json.dumps({
            "schema_version": "transcript-2",
            "record_type": "provider_call",
            "call_id": self._n,
            "run_uuid": self.run_uuid,
            "segment_id": self.segment_id,
            "tick": int(tick),
            "tier": tier,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "logical_id": logical_id,
            "logical_kind": logical_kind,
            "decision_id": decision_id,
            "source": source or logical_kind,
            "prompt_hash": bam_prompt(prompt),  # băm prompt GỐC (khớp lúc replay)
            "request": che_key(prompt),         # lưu bản đã che để người đọc/kiểm tra
            "response_raw": che_key(response_raw or ""),
            "outcome": "error" if is_error else "response",
            "error_type": error_type,
            "error_message": che_key(error_message or "") if is_error else "",
            "tok_in": int(tok_in),
            "tok_out": int(tok_out),
            "tool_turns": tool_turns or [],
            "tool_catalog_hash": tool_catalog_hash,
        }, ensure_ascii=False) + "\n")

    def ghi_terminal(
        self,
        *,
        tick: int,
        req: LLMRequest,
        terminal_reason: str,
        terminal_state: str,
        error_type: str | None = None,
        error_message: str | None = None,
        tool_turns: list[dict] | None = None,
        tool_catalog_hash: str | None = None,
    ) -> None:
        """Append the one terminal state of a scheduled agent decision.

        Provider responses and decision terminals are separate record types. Replay therefore
        never has to manufacture a transcript miss to select fallback: it consumes this row and
        validates the same terminal branch explicitly.
        """
        expected_state = terminal_state_for_reason(terminal_reason)
        if terminal_state not in TERMINAL_STATES:
            raise ValueError(f"unknown terminal state: {terminal_state}")
        if terminal_state != expected_state:
            raise ValueError(
                "inconsistent terminal state/reason: "
                f"reason={terminal_reason!r} state={terminal_state!r}"
            )
        self._n += 1
        self._f.write(json.dumps({
            "schema_version": "transcript-2",
            "record_type": "decision_terminal",
            "call_id": self._n,
            "run_uuid": self.run_uuid,
            "segment_id": self.segment_id,
            "tick": int(tick),
            "tier": req.tier,
            "provider": "decision",
            "model": "",
            "logical_id": req.logical_id,
            "logical_kind": req.logical_kind,
            "decision_id": req.decision_id,
            "source": req.attempt_source or req.logical_kind,
            "prompt_hash": bam_prompt(req.prompt),
            "request": che_key(req.prompt),
            "response_raw": "",
            "outcome": "terminal",
            "terminal_reason": terminal_reason,
            "terminal_state": terminal_state,
            "error_type": error_type,
            "error_message": che_key(error_message or "") if error_message else "",
            "tok_in": 0,
            "tok_out": 0,
            "tool_turns": tool_turns or [],
            "tool_catalog_hash": tool_catalog_hash,
        }, ensure_ascii=False) + "\n")

    # ``flush``/``fsync``/``dong`` là IDEMPOTENT (như ``EventLog`` và ``LLMCallLog``): trên
    # đường crash, ``run.chay_run`` đóng writer để không có handle mồ côi nào flush buffer ĐÈ
    # vào journal vừa bị truncate lúc resume; caller (test seam, driver) có thể đóng lần nữa.
    # Đóng hai lần phải là no-op, không phải ``ValueError: I/O operation on closed file``.
    def flush(self) -> None:
        if not self._f.closed:
            self._f.flush()

    def fsync(self) -> None:
        if not self._f.closed:
            self._f.flush()
            os.fsync(self._f.fileno())

    def dong(self) -> None:
        if not self._f.closed:
            self._f.flush()
            self._f.close()


class TranscriptReader:
    """Nạp transcript.jsonl → hàng đợi FIFO response theo prompt_hash (tiêu thụ 1 lần)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._theo_hash: dict[str, deque] = {}
        self._terminal_theo_decision: dict[str, deque] = {}
        self._terminal_theo_hash: dict[str, deque] = {}
        self.tong = 0
        self.misses = 0
        self.terminal_total = 0
        self.terminal_consumed = 0
        # A transcript without an explicitly declared terminal schema predates decision-terminal
        # records and is replayed through the legacy path.  Once transcript-2 is declared, a
        # missing terminal is an artifact failure rather than a fallback control signal.
        self.co_terminal_schema = False
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("schema_version") in TERMINAL_SCHEMA_VERSIONS:
                    self.co_terminal_schema = True
                if d.get("record_type") == "decision_terminal":
                    self.co_terminal_schema = True
                    self.terminal_total += 1
                    decision_id = str(d.get("decision_id") or "")
                    if decision_id:
                        self._terminal_theo_decision.setdefault(decision_id, deque()).append(d)
                    else:
                        self._terminal_theo_hash.setdefault(d["prompt_hash"], deque()).append(d)
                else:
                    # Rows before transcript-2 have no record_type and remain provider calls.
                    self._theo_hash.setdefault(d["prompt_hash"], deque()).append(d)
                self.tong += 1

    def lay(self, prompt: str, *, dem_miss: bool = True) -> dict | None:
        """Pop one provider-call row. Terminal rows never share this queue."""
        dq = self._theo_hash.get(bam_prompt(prompt))
        if not dq:
            if dem_miss:
                self.misses += 1
                raise KeyError("transcript miss")
            return None
        return dq.popleft()

    def xem_terminal(self, req: LLMRequest) -> dict | None:
        """Peek the recorded terminal without consuming it (used before a denied request)."""
        dq = (self._terminal_theo_decision.get(req.decision_id)
              if req.decision_id else self._terminal_theo_hash.get(bam_prompt(req.prompt)))
        return dq[0] if dq else None

    def lay_terminal(self, req: LLMRequest) -> dict | None:
        """Consume one terminal row, retaining only pre-terminal-schema compatibility.

        Legacy rows have no terminal schema at all, so they return ``None`` explicitly.  A
        transcript-2 artifact declares the schema and must contain a matching terminal row.
        """
        if not self.co_terminal_schema:
            return None
        dq = (self._terminal_theo_decision.get(req.decision_id)
              if req.decision_id else self._terminal_theo_hash.get(bam_prompt(req.prompt)))
        if not dq:
            self.misses += 1
            raise KeyError("decision terminal transcript miss")
        self.terminal_consumed += 1
        return dq.popleft()

    def con_lai(self) -> int:
        """Số provider rows + terminal rows chưa được tiêu thụ (replay đúng ⇒ 0)."""
        return (
            sum(len(dq) for dq in self._theo_hash.values())
            + sum(len(dq) for dq in self._terminal_theo_decision.values())
            + sum(len(dq) for dq in self._terminal_theo_hash.values())
        )


class TranscriptProvider:
    """Provider thay mạng: trả response đã ghi theo prompt_hash (không call API).

    Transcript-2 dùng ``decision_terminal`` để tái tạo budget denial/provider error/parse
    unusable. Chỉ một prompt thật sự không có cả provider row lẫn terminal row mới là miss và
    làm cổng replay fail; miss không còn là control signal cho fallback."""

    ten = "transcript"

    def __init__(self, reader: TranscriptReader):
        self.reader = reader

    def goi(self, req: LLMRequest, attempt: int = 0) -> LLMResponse:
        return self._tra(req)

    def goi_agentic(self, req: LLMRequest, w, aid: str) -> LLMResponse:
        try:
            d = self._lay(req)
        except LoiVuotNganSachTick as exc:
            terminal = getattr(exc, "transcript_terminal", None)
            if isinstance(terminal, dict):
                self._kiem_tool_turns(terminal, w, aid)
            raise
        self._kiem_tool_turns(d, w, aid)
        return self._phan_hoi(d)

    def _tra(self, req: LLMRequest) -> LLMResponse:
        return self._phan_hoi(self._lay(req))

    def _lay(self, req: LLMRequest) -> dict:
        d = self.reader.lay(req.prompt, dem_miss=False)
        if d is not None:
            return d
        terminal = self.reader.xem_terminal(req)
        if terminal and terminal.get("terminal_reason") == "budget_denied":
            exc = LoiVuotNganSachTick(
                str(terminal.get("error_message") or "budget denied recorded in transcript")
            )
            exc.transcript_terminal = terminal
            raise exc
        try:
            self.reader.lay(req.prompt, dem_miss=True)
        except KeyError:
            raise LoiHetQuota("transcript thiếu response cho prompt") from None
        raise AssertionError("unreachable")

    def consume_terminal(
        self,
        req: LLMRequest,
        expected_reason: str,
        expected_state: str | None = None,
    ) -> dict | None:
        """Consume and validate the reason and exact terminal state selected by replay.

        ``expected_state`` is optional solely for the existing orchestrator call seam: its
        canonical value is derived from ``expected_reason``.  Callers that supply it must agree
        with that canonical mapping, so neither a caller nor a tampered transcript can turn a
        fallback into an accepted decision (or the reverse).
        """
        try:
            canonical_state = terminal_state_for_reason(expected_reason)
        except ValueError as exc:
            raise TranscriptTerminalMismatch(str(exc)) from None
        if expected_state is None:
            expected_state = canonical_state
        elif expected_state not in TERMINAL_STATES:
            raise TranscriptTerminalMismatch(
                f"unknown expected terminal state: {expected_state!r}"
            )
        elif expected_state != canonical_state:
            raise TranscriptTerminalMismatch(
                "inconsistent expected terminal state/reason: "
                f"reason={expected_reason!r} state={expected_state!r}"
            )
        try:
            row = self.reader.lay_terminal(req)
        except KeyError as exc:
            raise TranscriptTerminalMismatch(str(exc)) from None
        if row is None:
            return None  # explicitly legacy: transcript contains no terminal schema
        actual_reason = row.get("terminal_reason")
        if actual_reason not in TERMINAL_REASONS:
            raise TranscriptTerminalMismatch(
                f"unknown terminal reason for {req.decision_id or req.logical_id}: "
                f"recorded={actual_reason!r}"
            )
        actual_state = row.get("terminal_state")
        if actual_state is None or actual_state == "":
            raise TranscriptTerminalMismatch(
                f"missing terminal state for {req.decision_id or req.logical_id}"
            )
        if actual_state not in TERMINAL_STATES:
            raise TranscriptTerminalMismatch(
                f"unknown terminal state for {req.decision_id or req.logical_id}: "
                f"recorded={actual_state!r}"
            )
        recorded_canonical_state = terminal_state_for_reason(actual_reason)
        if actual_state != recorded_canonical_state:
            raise TranscriptTerminalMismatch(
                "inconsistent recorded terminal state/reason for "
                f"{req.decision_id or req.logical_id}: reason={actual_reason!r} "
                f"state={actual_state!r}"
            )
        if actual_reason != expected_reason:
            raise TranscriptTerminalMismatch(
                f"terminal reason mismatch for {req.decision_id or req.logical_id}: "
                f"recorded={actual_reason!r} replay={expected_reason!r}"
            )
        if actual_state != expected_state:
            raise TranscriptTerminalMismatch(
                f"terminal state mismatch for {req.decision_id or req.logical_id}: "
                f"recorded={actual_state!r} replay={expected_state!r}"
            )
        return row

    @staticmethod
    def _phan_hoi(d: dict) -> LLMResponse:
        if d.get("outcome") == "error" or d.get("provider") == "loi":
            message = str(d.get("error_message") or d.get("response_raw")
                          or "provider error recorded in transcript")
            error_type = str(d.get("error_type") or "")
            exc_type = LoiProviderHong if error_type == "LoiProviderHong" else LoiHetQuota
            raise exc_type(message)
        return LLMResponse(
            text=d.get("response_raw", ""), provider=d.get("provider", "transcript"),
            model=d.get("model", ""), tok_in=int(d.get("tok_in", 0)),
            tok_out=int(d.get("tok_out", 0)), key_hash="transcript",
            tool_turns=list(d.get("tool_turns") or []),
            tool_catalog_hash=d.get("tool_catalog_hash"),
        )

    @staticmethod
    def _kiem_tool_turns(d: dict, w, aid: str) -> None:
        """Replay each recorded read-only query and fail closed on evidence drift."""
        turns = d.get("tool_turns") or []
        if not turns:
            return  # Legacy transcripts predate the tool-turn evidence contract.
        from minds.world_tools import catalog_hash, result_hash, thuc_thi

        recorded_catalog = d.get("tool_catalog_hash")
        current_catalog = catalog_hash()
        if recorded_catalog and recorded_catalog != current_catalog:
            raise TranscriptToolMismatch(
                "tool_catalog_hash mismatch: transcript tool interface differs from current code"
            )
        for position, turn in enumerate(turns):
            if not isinstance(turn, dict):
                raise TranscriptToolMismatch(f"tool turn {position} is not an object")
            name = str(turn.get("name", ""))
            args = turn.get("args")
            if not isinstance(args, dict):
                raise TranscriptToolMismatch(f"tool turn {position} has non-object arguments")
            actual = thuc_thi(w, aid, name, dict(args))
            expected_hash = str(turn.get("result_hash", ""))
            actual_hash = result_hash(actual)
            if not expected_hash or expected_hash != actual_hash:
                raise TranscriptToolMismatch(
                    f"tool turn {position} result mismatch for {name}: "
                    f"recorded={expected_hash or '<missing>'} actual={actual_hash}"
                )


class TranscriptToolMismatch(RuntimeError):
    """A recorded MCP information set cannot be reproduced on the replay snapshot."""


class TranscriptTerminalMismatch(RuntimeError):
    """Replay selected a different or missing terminal decision branch."""


def tao_mind_replay(w, cfg, mode: str, reader: TranscriptReader, p_malformed=None):
    """Dựng mind replay-from-transcript cho mock/real: pipeline y hệt run gốc nhưng provider
    = TranscriptProvider (không mạng, không quota, không kiểm ngân sách). KHÔNG ghi file
    (run_dir/quota_db = None) nên không đụng artifact của run gốc."""
    prov = TranscriptProvider(reader)
    if mode == "mock":
        from minds.orchestrator import tao_mind_mock

        mind = tao_mind_mock(w, fast=True, run_dir=None, p_malformed=p_malformed)
        mind.provider = prov  # nén/phản tư mock là heuristic → không cần transcript
        return mind
    if mode == "real":
        from minds.keypool import EnvKeys
        from minds.real import MindReal

        env = EnvKeys(gemini_keys=[], nine_key="", nine_base="", llm_mode="real")
        mind = MindReal(w, None, cfg, env, None, transport=None)  # run_dir/quota_db=None
        # đóng client httpx của gateway thật (bị vứt bỏ) để khỏi rò tài nguyên
        for p in (mind.gateway.aistudio, mind.gateway.ninerouter):
            try:
                p.client.close()
            except Exception:  # noqa: BLE001
                pass
        mind.provider = prov  # quyết định agent: từ transcript (thay GatewayCoPacing)
        mind.gateway = _GatewayReplay()  # route nền: ghi_call no-op, không mạng
        mind._goi_nen_co_cho = lambda req, route: prov.goi(req)  # nén/phản tư/dịch intent
        # Infrastructure budget is not re-spent during replay. Explicit terminal rows recreate
        # denial/fallback branches; a miss is always artifact failure, never a control signal.
        mind._du_ngan_sach = lambda w, thinkers, triggers=None: True
        return mind
    raise ValueError(f"mode replay không hỗ trợ: {mode}")


class _GatewayReplay:
    """Gateway giả cho replay real: route chỉ là metadata, quota không được dùng.

    ``MindReal`` vẫn hỏi route nền khi nén hồi ký/phản tư. Trong replay, request đó
    đi thẳng vào :class:`TranscriptProvider`, nên route chỉ cần giữ identity để call
    path giống live; nó không được admission, đọc quota, hay tạo HTTP client.
    """

    class _Quota:
        def ghi_call(self, *a, **k) -> None:  # noqa: ANN002, ANN003
            pass

    def __init__(self):
        self.quota = _GatewayReplay._Quota()

    @staticmethod
    def route_cau_hinh(provider: str, model: str):
        """Return inert background-route metadata for an already-recorded request.

        Zero limits and an absent TPM policy make accidental use for admission fail
        closed. Replay only passes this identity to its transcript-backed background
        call seam; it never invokes a provider or touches quota state.
        """
        from minds.providers_real import Route

        return Route(provider=str(provider), model=str(model), rpm=0, rpd=0)
