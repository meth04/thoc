"""engine/journal.py — run journal manifest + resume an toàn (ADR 0006 §C).

Vấn đề (đã chứng minh trên ``data/runs/real60_spatial/``): resume nạp checkpoint tick N
nhưng KHÔNG đưa journal về trạng thái tick N. Ba journal của cùng một lần kill dừng ở BA
tick khác nhau (events→117, llm_calls→118, transcript→119) ⇒ **không heuristic quét nội
dung nào tìm được điểm cắt an toàn**. Điểm cắt hợp lệ duy nhất là byte-offset được ghi
TẠI checkpoint, sau flush+fsync.

Thiết kế (ADR 0006 §C.1, model-architect D1–D7):

- **Class A** (``events.jsonl``, ``transcript.jsonl``, ``unrecognized_intents.jsonl``):
  stream append-only ⇒ resume = *truncate-with-quarantine*. Tail bị bỏ được **CHUYỂN**
  nguyên bytes sang ``checkpoints/orphans/`` (kèm sha256) rồi mới cắt khỏi file live.
  KHÔNG xóa bằng chứng (điều luật #6).
- **Class B** (``metrics.jsonl``): journal *dẫn xuất*, được ghi đè cuối run từ
  ``World.metrics_lich_su`` (nằm trong pickle) ⇒ KHÔNG cần truncate. Chỉ assert
  tick duy nhất + liên tục.
- **Class C** (``llm_calls.sqlite``): sổ **chi phí đã trả**. Row của đoạn bị bỏ vẫn là call
  đã thực sự xảy ra, đã tiêu token/quota/USD ⇒ **KHÔNG BAO GIỜ DELETE**. Thay vào đó
  ``superseded=1`` + ``segment_id`` của segment cũ. Telemetry báo cả ``call_burned``
  (mọi row — chi phí) lẫn ``call_effective`` (superseded=0 — quỹ đạo).

Ranh giới hash: journal KHÔNG nằm trong ``World.behavioral_state()``
(``engine/world.py:460-570``) ⇒ mọi thay đổi ở đây **không đổi ``world_hash``** (INV-J1).
Counter (event ``seq``, transcript ``call_id``) thuộc về **journal writer**, không thuộc
``World`` — ``World.luu_checkpoint`` hoán ``events`` ra ``EventLog(None)`` lúc pickle nên
counter đặt trong World cũng không sống sót; manifest là bản checkpoint của counter.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "journal-2"

# Duyệt theo thứ tự tên đã sort ở MỌI vòng lặp (flush/capture/truncate/quarantine) để file
# manifest byte-stable với cùng input (deterministic tie-break, INV-J bổ trợ).
TEN_FILE: dict[str, str] = {
    "events": "events.jsonl",
    "llm_calls": "llm_calls.sqlite",
    "metrics": "metrics.jsonl",
    "transcript": "transcript.jsonl",
    "unrecognized": "unrecognized_intents.jsonl",
}
CLASS_A: tuple[str, ...] = ("events", "transcript", "unrecognized")  # truncate + quarantine
SHA_RONG = hashlib.sha256(b"").hexdigest()

# Mã lỗi ổn định cho từng trường identity phải khớp giữa hai segment (ADR 0006 §C.4).
# ``git_revision`` KHÔNG nằm ở đây: một commit chỉ đổi doc/test không đổi luật của thế giới;
# ba hash dưới đây MỚI là luật (config, prompt template, capability catalog).
MA_IDENTITY: dict[str, str] = {
    "config_sha256": "E-JM-03",
    "prompt_template_hash": "E-JM-04",
    "capability_catalog_hash": "E-JM-05",
    "runtime_source_identity": "E-JM-12",
}


def _co_runtime_source_identity(value: object) -> bool:
    """Return whether a journal carries the minimum versioned source evidence.

    The journal module intentionally does not import ``tools.experiments``: journal evidence is
    artifact infrastructure, while source-inventory construction belongs to the experiment tool.
    A final artifact nevertheless needs a nonempty versioned digest to prove which executable
    law produced its checkpoint.
    """
    return (isinstance(value, dict)
            and isinstance(value.get("sha256"), str)
            and bool(value["sha256"]))


class LoiJournal(Exception):
    """Sai lệch journal ⇒ fail-closed. ``ma`` là mã lỗi ổn định (E-JM-xx)."""

    def __init__(self, ma: str, thong_diep: str):
        super().__init__(f"[{ma}] {thong_diep}")
        self.ma = ma
        self.thong_diep = thong_diep


# ---------------------------------------------------------------- schema (pydantic v2)
class JournalIdentity(BaseModel):
    """Định danh code/config của một segment (ADR 0006 §C.2 — BỐN trường).

    Hai hash prompt-liên-quan đo HAI THỨ KHÁC NHAU và cần CẢ HAI:

    - ``prompt_template_hash`` = sha256 **byte** của ``minds/prompts.py`` + ``minds/capabilities.py``
      (`tools.experiments.prompt_template_hash`). Bắt mọi sửa đổi *code render*, kể cả thân hàm
      (``_gt_xay``, ``mo_ta_cong_thuc``…). Băm mình ``prompts.py`` là KHÔNG ĐỦ: sau P0.1 thân hàm
      render sống ở ``capabilities.py``, nên sửa nó sẽ đổi prompt của MỌI agent mà hash đứng yên.
    - ``capability_catalog_hash`` = sha256 **khai báo** của catalog (`minds.capabilities.catalog_hash`).
      Ổn định khi refactor thuần (đổi thứ tự, đổi docstring) và CHỈ đổi khi *interface* đổi (thêm/bớt
      action, đổi tham số, đổi ``ma_ket_qua``) ⇒ nó nói "tập action hợp lệ đã khác", một tín hiệu
      ngữ nghĩa mà hash byte không phân biệt được với việc format lại code.

    Thiếu ``capability_catalog_hash`` ⇒ resume vẫn chạy qua một thay đổi interface và sinh đúng
    artifact "transcript hai-nửa-hai-luật" mà ``E-JM-04`` được đẻ ra để chặn (A-06/F-P03-1).
    """

    config_sha256: str | None = None
    prompt_template_hash: str | None = None
    capability_catalog_hash: str | None = None
    # Full versioned runtime Python inventory from tools.experiments.  It is metadata outside
    # World and therefore never participates in world_hash, but it is mandatory for new-run
    # resume evidence: a changed or missing source inventory is a different executable law.
    runtime_source_identity: dict[str, Any] | None = None
    git_revision: str | None = None


class JsonlState(BaseModel):
    kind: Literal["jsonl"] = "jsonl"
    byte_offset: int
    record_count: int
    sha256_prefix: str


class SqliteState(BaseModel):
    kind: Literal["sqlite"] = "sqlite"
    max_call_id: int
    record_count: int
    # Additive attempt-ledger checkpoint identity. ``None`` is reserved for a
    # pre-attempt-accounting checkpoint; it is never silently equivalent to 0.
    max_attempt_id: int | None = None
    attempt_record_count: int | None = None
    sha256_prefix: None = None


class DerivedState(BaseModel):
    kind: Literal["derived"] = "derived"
    record_count: int
    source: str = "World.metrics_lich_su"


TrangThaiJournal = JsonlState | SqliteState | DerivedState


class CheckpointEntry(BaseModel):
    tick: int
    segment_id: int
    world_hash: str | None = None
    written_at_utc: str
    journals: dict[str, TrangThaiJournal]


class SegmentEntry(BaseModel):
    segment_id: int
    started_at_tick: int
    resumed_from_tick: int | None = None
    ended_at_tick: int | None = None
    status: str = "active"  # active | closed | closed_truncated
    identity: JournalIdentity


class RecoveryEntry(BaseModel):
    at_utc: str
    kind: str  # truncate_on_resume | operator_recover | fresh_run_reset
    resumed_checkpoint_tick: int
    from_segment_id: int
    new_segment_id: int
    quarantine_dir: str
    journals: dict[str, dict[str, Any]] = Field(default_factory=dict)
    operator_flag: str | None = None
    reason_code: str | None = None


class JournalManifest(BaseModel):
    """``checkpoints/journal_manifest.json`` — append-only lịch sử segment + recovery.

    Top-level ``checkpoint_tick``/``identity``/``journals`` phản chiếu checkpoint MỚI NHẤT
    (đúng schema ADR 0006 §C.2); ``checkpoints``/``segments``/``recoveries`` giữ lịch sử
    (model-architect D1) — hai yêu cầu này không loại trừ nhau."""

    schema_version: str = SCHEMA_VERSION
    run_uuid: str
    run_name: str
    created_at_utc: str
    segment_id: int = 0  # segment ĐANG hoạt động
    checkpoint_tick: int = 0
    identity: JournalIdentity = Field(default_factory=JournalIdentity)
    journals: dict[str, TrangThaiJournal] = Field(default_factory=dict)
    segments: list[SegmentEntry] = Field(default_factory=list)
    checkpoints: list[CheckpointEntry] = Field(default_factory=list)
    recoveries: list[RecoveryEntry] = Field(default_factory=list)
    # False sau `--recover-journal`: transcript prefix đã mất ⇒ replay-from-t0 bất khả thi.
    replay_complete: bool = True
    artifact_status_forced: str | None = None


# ---------------------------------------------------------------- tiện ích file
def _bay_gio() -> str:
    return datetime.now(UTC).isoformat()


def _ghi_atomic(path: Path, noi_dung: str) -> None:
    """Ghi tmp + fsync + os.replace: hoặc file cũ, hoặc file mới, không có bản nửa vời."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(noi_dung)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _sha256_prefix(path: Path, byte_offset: int) -> str:
    """sha256 ĐẦY ĐỦ (64 hex) của bytes ``[0, byte_offset)`` — không cắt ngắn digest."""
    h = hashlib.sha256()
    con = byte_offset
    if con <= 0 or not path.exists():
        return h.hexdigest()
    with open(path, "rb") as f:
        while con > 0:
            chunk = f.read(min(1 << 20, con))
            if not chunk:
                break
            h.update(chunk)
            con -= len(chunk)
    return h.hexdigest()


def _dem_dong(path: Path, byte_offset: int) -> int:
    if byte_offset <= 0 or not path.exists():
        return 0
    n, con = 0, byte_offset
    with open(path, "rb") as f:
        while con > 0:
            chunk = f.read(min(1 << 20, con))
            if not chunk:
                break
            n += chunk.count(b"\n")
            con -= len(chunk)
    return n


def _fsync_path(path: Path) -> None:
    """fsync một file không do ta giữ handle (``unrecognized_intents.jsonl`` mở/đóng mỗi ghi)."""
    if not path.exists():
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass  # một số filesystem không fsync được handle chỉ-đọc; nội dung đã qua close()
    finally:
        os.close(fd)


def _cot_llm_calls(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(llm_calls)")}


# ---------------------------------------------------------------- RunJournals
class RunJournals:
    """Điều phối 5 journal của một run: flush → capture → checkpoint → verify → restore.

    Wrapper **additive** ở tầng ``run.py``: ``World.luu_checkpoint`` giữ nguyên chữ ký và
    hành vi (test/tool gọi trực tiếp vẫn chạy, chỉ không có manifest)."""

    def __init__(self, run_dir: Path, manifest: JournalManifest):
        self.run_dir = Path(run_dir)
        self.ck_dir = self.run_dir / "checkpoints"
        self.manifest_path = self.ck_dir / "journal_manifest.json"
        self.manifest = manifest
        # rolling sha256 per journal Class-A: capture() O(bytes mới) thay vì O(file)
        self._hasher: dict[str, Any] = {t: hashlib.sha256() for t in CLASS_A}
        self._offset: dict[str, int] = dict.fromkeys(CLASS_A, 0)
        self._count: dict[str, int] = dict.fromkeys(CLASS_A, 0)
        self._events = None
        self._transcript = None
        self._llm_log = None

    # ---------- khởi tạo / nạp ----------
    @staticmethod
    def duong_dan_manifest(run_dir: Path) -> Path:
        return Path(run_dir) / "checkpoints" / "journal_manifest.json"

    @staticmethod
    def doc_manifest(run_dir: Path) -> JournalManifest | None:
        p = RunJournals.duong_dan_manifest(run_dir)
        if not p.exists():
            return None
        return JournalManifest.model_validate_json(p.read_text(encoding="utf-8"))

    @classmethod
    def moi(cls, run_dir: Path, *, run_name: str, identity: JournalIdentity) -> RunJournals:
        """Run MỚI: segment 0, journal rỗng. Journal cũ cùng tên (nếu có) bị quarantine —
        KHÔNG xóa, KHÔNG append chồng lên quỹ đạo cũ (đó chính là bệnh của real60)."""
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        mf = JournalManifest(
            run_uuid=str(uuid.uuid4()), run_name=run_name, created_at_utc=_bay_gio(),
            segment_id=0, checkpoint_tick=0, identity=identity,
            segments=[SegmentEntry(segment_id=0, started_at_tick=0, resumed_from_tick=None,
                                   identity=identity)],
        )
        self = cls(run_dir, mf)
        self._reset_journal_cu()
        self._ghi_manifest()
        return self

    @classmethod
    def tao_de_recover(cls, run_dir: Path, *, run_name: str, identity: JournalIdentity,
                       tick: int, ly_do: str) -> RunJournals:
        """``--recover-journal`` trên run LEGACY (chưa từng có manifest). Dựng manifest mới,
        segment 0 = "không rõ" (bị quarantine), rồi mở segment 1 với journal rỗng."""
        run_dir = Path(run_dir)
        mf = JournalManifest(
            run_uuid=str(uuid.uuid4()), run_name=run_name, created_at_utc=_bay_gio(),
            segment_id=0, checkpoint_tick=int(tick), identity=JournalIdentity(),
            segments=[SegmentEntry(segment_id=0, started_at_tick=0, resumed_from_tick=None,
                                   ended_at_tick=None, status="active",
                                   identity=JournalIdentity())],
        )
        self = cls(run_dir, mf)
        self.recover_toan_bo(tick, identity=identity, ly_do=ly_do)
        return self

    @classmethod
    def nap(cls, run_dir: Path) -> RunJournals:
        mf = cls.doc_manifest(run_dir)
        if mf is None:
            raise LoiJournal(
                "E-JM-01",
                f"Không có {cls.duong_dan_manifest(run_dir)}. Run này được tạo trước P0.2 nên "
                "không có byte-offset journal tại checkpoint; KHÔNG thể xác định điểm cắt an "
                "toàn (ba journal của một lần kill có thể dừng ở ba tick khác nhau). "
                "Chọn: (1) chạy run mới — khuyến nghị, giữ artifact cũ nguyên vẹn; "
                "(2) --resume --recover-journal ⇒ toàn bộ journal bị QUARANTINE và artifact "
                "bị hạ VĨNH VIỄN xuống diagnostic_only_unreplayable.",
            )
        return cls(run_dir, mf)

    # ---------- writers ----------
    def gan_writers(self, *, events=None, transcript=None, llm_log=None) -> None:
        """Nhận tham chiếu writer để flush+fsync trước khi capture offset."""
        if events is not None:
            self._events = events
        if transcript is not None:
            self._transcript = transcript
        if llm_log is not None:
            self._llm_log = llm_log

    # ---------- counters cho phiên mới ----------
    def counters(self) -> dict[str, int]:
        """record_count tại checkpoint đang nạp → seq/call_id khởi động của segment mới."""
        ra: dict[str, int] = {}
        for ten in CLASS_A:
            st = self.manifest.journals.get(ten)
            ra[ten] = int(getattr(st, "record_count", 0)) if st is not None else 0
        return ra

    # ---------- flush + capture ----------
    def flush_all(self) -> None:
        """flush + fsync MỌI journal TRƯỚC khi đọc offset. Offset không fsync là offset nói dối."""
        if self._events is not None:
            self._events.flush()
            self._events.fsync()
        if self._transcript is not None:
            self._transcript.flush()
            self._transcript.fsync()
        if self._llm_log is not None:
            self._llm_log.flush()  # commit
        _fsync_path(self.run_dir / TEN_FILE["unrecognized"])

    def _tien_hasher(self, ten: str) -> None:
        """Nạp bytes mới (từ ``_offset``) vào rolling hash; chỉ tính tới newline cuối cùng."""
        path = self.run_dir / TEN_FILE[ten]
        if not path.exists():
            return
        size = path.stat().st_size
        if size <= self._offset[ten]:
            return
        with open(path, "rb") as f:
            f.seek(self._offset[ten])
            moi = f.read(size - self._offset[ten])
        cat = moi.rfind(b"\n")
        if cat < 0:  # chưa có dòng hoàn chỉnh nào mới
            return
        phan = moi[: cat + 1]
        self._hasher[ten].update(phan)
        self._offset[ten] += len(phan)
        self._count[ten] += phan.count(b"\n")

    def capture(self, w) -> dict[str, TrangThaiJournal]:
        """Đọc offset/record_count/sha256 SAU khi flush_all(). O(bytes mới)/checkpoint."""
        states: dict[str, TrangThaiJournal] = {}
        for ten in CLASS_A:
            self._tien_hasher(ten)
            states[ten] = JsonlState(
                byte_offset=self._offset[ten], record_count=self._count[ten],
                sha256_prefix=self._hasher[ten].hexdigest(),
            )
        sq = self.run_dir / TEN_FILE["llm_calls"]
        if sq.exists():
            conn = sqlite3.connect(sq)
            try:
                cot = _cot_llm_calls(conn)
                if "call_id" in cot:
                    row = conn.execute(
                        "SELECT COALESCE(MAX(call_id),0), COUNT(*) FROM llm_calls").fetchone()
                    attempt_max: int | None = None
                    attempt_count: int | None = None
                    has_attempts = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' "
                        "AND name='llm_attempts'"
                    ).fetchone()
                    if has_attempts:
                        attempt_row = conn.execute(
                            "SELECT COALESCE(MAX(attempt_id),0), COUNT(*) FROM llm_attempts"
                        ).fetchone()
                        attempt_max, attempt_count = int(attempt_row[0]), int(attempt_row[1])
                    states["llm_calls"] = SqliteState(
                        max_call_id=int(row[0]), record_count=int(row[1]),
                        max_attempt_id=attempt_max, attempt_record_count=attempt_count,
                    )
            finally:
                conn.close()
        states["metrics"] = DerivedState(record_count=len(w.metrics_lich_su))
        return dict(sorted(states.items()))

    # ---------- checkpoint ----------
    def checkpoint(self, w) -> CheckpointEntry:
        """Thứ tự BẮT BUỘC (run.py:259-261 cũ ghi checkpoint TRƯỚC flush ⇒ offset sai):

        flush+fsync → capture → journal_manifest (atomic) → pickle+moi_nhat → con trỏ.

        Con trỏ resume (``checkpoint_moi_nhat.json``) được ghi CUỐI CÙNG: crash giữa chừng
        ⇒ con trỏ vẫn ở checkpoint cũ hơn ⇒ resume nhất quán, không cần rollback thủ công.
        """
        self.flush_all()
        states = self.capture(w)
        entry = CheckpointEntry(
            tick=int(w.tick), segment_id=self.manifest.segment_id,
            world_hash=w.world_hash(), written_at_utc=_bay_gio(), journals=states,
        )
        self.manifest.checkpoints.append(entry)
        self.manifest.checkpoint_tick = entry.tick
        self.manifest.journals = states
        self._ghi_manifest()
        w.luu_checkpoint(self.ck_dir)  # pkl + checkpoint_moi_nhat.json + config_snapshot
        self._gan_con_tro(entry)
        return entry

    def _gan_con_tro(self, entry: CheckpointEntry) -> None:
        """Thêm (additive) con trỏ journal vào ``checkpoint_moi_nhat.json`` — reader cũ không đổi."""
        p = self.ck_dir / "checkpoint_moi_nhat.json"
        if not p.exists():
            return
        meta = json.loads(p.read_text(encoding="utf-8"))
        meta["journal_manifest"] = "journal_manifest.json"
        meta["journal_state_sha256"] = _digest_states(entry.journals)
        meta["segment_id"] = entry.segment_id
        meta["run_uuid"] = self.manifest.run_uuid
        _ghi_atomic(p, json.dumps(meta, ensure_ascii=False, sort_keys=True))

    def _ghi_manifest(self) -> None:
        _ghi_atomic(
            self.manifest_path,
            json.dumps(self.manifest.model_dump(mode="json"), ensure_ascii=False,
                       indent=2, sort_keys=True) + "\n",
        )

    # ---------- verify (fail-closed) ----------
    def entry_cua_tick(self, tick: int) -> CheckpointEntry:
        khop = [e for e in self.manifest.checkpoints if e.tick == int(tick)]
        if not khop:
            raise LoiJournal(
                "E-JM-02",
                f"journal_manifest không có entry cho checkpoint tick {tick} "
                f"(có: {sorted({e.tick for e in self.manifest.checkpoints})}). "
                "Không suy ra được điểm cắt an toàn.",
            )
        return khop[-1]  # append-only: entry cuối là lần ghi gần nhất cho tick đó

    def verify(self, tick: int, identity: JournalIdentity) -> CheckpointEntry:
        """Kích thước ≥ byte_offset AND sha256(prefix) khớp AND identity khớp. Sai lệch bất kỳ
        ⇒ LoiJournal, KHÔNG mutate byte nào (INV-J8)."""
        entry = self.entry_cua_tick(tick)
        self._kiem_identity(identity)
        for ten in CLASS_A:
            st = entry.journals.get(ten)
            if st is None or not isinstance(st, JsonlState):
                continue
            path = self.run_dir / TEN_FILE[ten]
            size = path.stat().st_size if path.exists() else 0
            if size < st.byte_offset:
                raise LoiJournal(
                    "E-JM-06",
                    f"{TEN_FILE[ten]} ngắn hơn offset checkpoint: {size} < {st.byte_offset} "
                    "byte. Journal bị cắt/mất ngoài tầm kiểm soát của run.",
                )
            thuc = _sha256_prefix(path, st.byte_offset)
            if thuc != st.sha256_prefix:
                raise LoiJournal(
                    "E-JM-07",
                    f"{TEN_FILE[ten]} prefix [0,{st.byte_offset}) bị SỬA: "
                    f"sha256 {thuc[:16]} ≠ {st.sha256_prefix[:16]} ghi lúc checkpoint.",
                )
        sq_state = entry.journals.get("llm_calls")
        sq = self.run_dir / TEN_FILE["llm_calls"]
        if isinstance(sq_state, SqliteState):
            if not sq.exists():
                raise LoiJournal("E-JM-08", "llm_calls.sqlite mất sau checkpoint.")
            conn = sqlite3.connect(sq)
            try:
                n, mn, mx = conn.execute(
                    "SELECT COUNT(*), COALESCE(MIN(call_id),0), COALESCE(MAX(call_id),0) "
                    "FROM llm_calls WHERE call_id <= ?",
                    (sq_state.max_call_id,),
                ).fetchone()
                if (int(n) != sq_state.record_count or int(mx) != sq_state.max_call_id
                        or sq_state.max_call_id != sq_state.record_count
                        or (int(n) and int(mn) != 1)):
                    raise LoiJournal(
                        "E-JM-08",
                        f"llm_calls: {n} row/MIN={mn}/MAX={mx} có call_id ≤ "
                        f"{sq_state.max_call_id}, manifest ghi {sq_state.record_count}. "
                        "Sổ chi phí không còn prefix liên tục 1..N.",
                    )
                has_attempts = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='llm_attempts'"
                ).fetchone()
                attempt_rows = int(conn.execute(
                    "SELECT COUNT(*) FROM llm_attempts"
                ).fetchone()[0]) if has_attempts else 0
                attempt_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(llm_attempts)")
                } if has_attempts else set()
                attempt_metadata = (
                    sq_state.max_attempt_id is not None
                    and sq_state.attempt_record_count is not None
                )
                if attempt_rows and not attempt_metadata:
                    raise LoiJournal(
                        "E-JM-09",
                        "llm_attempts có row nhưng checkpoint không ghi max_attempt_id/"
                        "attempt_record_count. Không biết prefix attempt nào thuộc checkpoint; "
                        "resume bị từ chối thay vì xác minh ngầm artifact thiếu bằng chứng.",
                    )
                if attempt_metadata:
                    if "attempt_id" not in attempt_columns or "superseded" not in attempt_columns:
                        raise LoiJournal(
                            "E-JM-10",
                            "llm_attempts checkpoint prefix thiếu attempt_id hoặc superseded; "
                            "không thể xác minh forensic identity.",
                        )
                    n_attempt, mn_attempt, mx_attempt = conn.execute(
                        "SELECT COUNT(*), COALESCE(MIN(attempt_id),0), "
                        "COALESCE(MAX(attempt_id),0) FROM llm_attempts WHERE attempt_id <= ?",
                        (sq_state.max_attempt_id,),
                    ).fetchone()
                    bad_attempt_sup = int(conn.execute(
                        "SELECT COUNT(*) FROM llm_attempts WHERE attempt_id <= ? "
                        "AND (superseded IS NULL OR superseded NOT IN (0,1))",
                        (sq_state.max_attempt_id,),
                    ).fetchone()[0])
                    if (int(n_attempt) != sq_state.attempt_record_count
                            or int(mx_attempt) != sq_state.max_attempt_id
                            or sq_state.max_attempt_id != sq_state.attempt_record_count
                            or (int(n_attempt) and int(mn_attempt) != 1)
                            or bad_attempt_sup):
                        raise LoiJournal(
                            "E-JM-10",
                            f"llm_attempts: {n_attempt} row/MIN={mn_attempt}/MAX={mx_attempt} "
                            f"có attempt_id ≤ {sq_state.max_attempt_id}, manifest ghi "
                            f"{sq_state.attempt_record_count}; superseded invalid={bad_attempt_sup}. "
                            "Sổ attempt không còn prefix liên tục/binary.",
                        )
            finally:
                conn.close()
        return entry

    @classmethod
    def verify_final_checkpoint(
        cls,
        run_dir: Path,
        *,
        expected_run_name: str,
        expected_run_uuid: str | None,
        expected_tick: int,
        expected_world_hash: str | None,
        expected_identity: JournalIdentity | None = None,
    ) -> CheckpointEntry:
        """Validate immutable evidence for a completed run without mutating it.

        Resume verification intentionally accepts a live tail after the selected checkpoint.
        A completed artifact has no such allowance: its current Class-A files and SQLite call
        ledger must be *exactly* the prefix recorded by the final checkpoint.  The pointer,
        manifest, metadata identities, segment history, and recovery log form one evidence
        chain; a valid JSONL stream alone is not sufficient evidence of a verified artifact.
        """
        run_dir = Path(run_dir)
        manifest = cls.doc_manifest(run_dir)
        if manifest is None:
            raise LoiJournal(
                "E-JM-11",
                "thiếu checkpoints/journal_manifest.json; artifact legacy không có bằng chứng "
                "checkpoint-prefix nên chỉ có thể là diagnostic_only_unreplayable.",
            )
        if manifest.schema_version != SCHEMA_VERSION:
            raise LoiJournal(
                "E-JM-11",
                f"journal schema không hỗ trợ: {manifest.schema_version!r}; "
                f"cần {SCHEMA_VERSION!r} để xác minh final checkpoint.",
            )
        if not _co_runtime_source_identity(manifest.identity.runtime_source_identity):
            raise LoiJournal(
                "E-JM-12",
                "journal final checkpoint thiếu runtime_source_identity versioned; "
                "artifact không chứng minh được executable runtime law.",
            )
        if manifest.run_name != expected_run_name:
            raise LoiJournal(
                "E-JM-11",
                f"journal run_name={manifest.run_name!r} ≠ run={expected_run_name!r}",
            )
        if not manifest.run_uuid or not expected_run_uuid or manifest.run_uuid != expected_run_uuid:
            raise LoiJournal(
                "E-JM-11",
                "run_uuid giữa journal manifest và run metadata thiếu hoặc không khớp.",
            )
        if manifest.checkpoint_tick != int(expected_tick):
            raise LoiJournal(
                "E-JM-11",
                f"journal checkpoint_tick={manifest.checkpoint_tick} ≠ tick cuối={expected_tick}",
            )
        journal = cls(run_dir, manifest)
        entry = journal.entry_cua_tick(expected_tick)
        if entry.segment_id != manifest.segment_id:
            raise LoiJournal(
                "E-JM-11",
                f"checkpoint segment={entry.segment_id} ≠ active/final segment={manifest.segment_id}",
            )
        if entry.world_hash != expected_world_hash:
            raise LoiJournal(
                "E-JM-11",
                "world_hash của final checkpoint không khớp run metadata/manifest outcome.",
            )
        if _digest_states(manifest.journals) != _digest_states(entry.journals):
            raise LoiJournal(
                "E-JM-11",
                "top-level journals của manifest không còn đúng state final checkpoint.",
            )
        if expected_identity is not None:
            for field_name, code in sorted(MA_IDENTITY.items()):
                expected = getattr(expected_identity, field_name)
                actual = getattr(manifest.identity, field_name)
                if expected != actual:
                    raise LoiJournal(
                        code,
                        f"final journal identity {field_name}={actual!r} ≠ manifest={expected!r}",
                    )

        pointer_path = run_dir / "checkpoints" / "checkpoint_moi_nhat.json"
        if not pointer_path.exists():
            raise LoiJournal("E-JM-11", "thiếu checkpoint_moi_nhat.json cho checkpoint cuối.")
        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LoiJournal("E-JM-11", f"checkpoint_moi_nhat.json không đọc được: {exc}") from exc
        if (
            int(pointer.get("tick", -1)) != int(expected_tick)
            or pointer.get("world_hash") != expected_world_hash
            or pointer.get("journal_manifest") != "journal_manifest.json"
            or pointer.get("run_uuid") != manifest.run_uuid
            or int(pointer.get("segment_id", -1)) != entry.segment_id
            or pointer.get("journal_state_sha256") != _digest_states(entry.journals)
        ):
            raise LoiJournal(
                "E-JM-11",
                "checkpoint_moi_nhat không trỏ đúng final journal state/run_uuid/segment/hash.",
            )
        if not (run_dir / "checkpoints" / f"checkpoint_{int(expected_tick):04d}.pkl").exists():
            raise LoiJournal("E-JM-11", "thiếu pickle của final checkpoint.")

        cls._verify_final_prefixes(run_dir, entry)
        cls._verify_final_history(run_dir, manifest, entry, expected_tick)
        return entry

    @staticmethod
    def _verify_final_prefixes(run_dir: Path, entry: CheckpointEntry) -> None:
        """Require exact final Class-A/SQLite state, not merely a valid checkpoint prefix."""
        for name in CLASS_A:
            state = entry.journals.get(name)
            if not isinstance(state, JsonlState):
                raise LoiJournal("E-JM-11", f"checkpoint cuối thiếu JsonlState cho {name}.")
            path = Path(run_dir) / TEN_FILE[name]
            size = path.stat().st_size if path.exists() else 0
            count = _dem_dong(path, size)
            digest = _sha256_prefix(path, size)
            if (size != state.byte_offset or count != state.record_count
                    or digest != state.sha256_prefix):
                raise LoiJournal(
                    "E-JM-11",
                    f"{TEN_FILE[name]} không đúng final prefix: size/count/sha256 "
                    f"={size}/{count}/{digest[:16]} nhưng checkpoint ghi "
                    f"{state.byte_offset}/{state.record_count}/{state.sha256_prefix[:16]}.",
                )
        state = entry.journals.get("llm_calls")
        path = Path(run_dir) / TEN_FILE["llm_calls"]
        if state is None and not path.exists():
            return  # rulebot artifact: no provider cost ledger was ever created.
        if not isinstance(state, SqliteState):
            raise LoiJournal("E-JM-11", "checkpoint cuối thiếu SqliteState cho llm_calls.")
        if not path.exists():
            raise LoiJournal("E-JM-08", "llm_calls.sqlite mất sau final checkpoint.")
        conn = sqlite3.connect(path)
        try:
            n, distinct, minimum, maximum = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT call_id), COALESCE(MIN(call_id),0), "
                "COALESCE(MAX(call_id),0) FROM llm_calls"
            ).fetchone()
            if (int(n) != state.record_count or int(maximum) != state.max_call_id
                    or int(distinct) != int(n) or state.max_call_id != state.record_count
                    or (int(n) and int(minimum) != 1)):
                raise LoiJournal(
                    "E-JM-08",
                    "llm_calls không còn đúng final SQLite prefix 1..N của checkpoint.",
                )
            has_attempts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='llm_attempts'"
            ).fetchone()
            if state.max_attempt_id is not None or state.attempt_record_count is not None:
                if not has_attempts:
                    raise LoiJournal(
                        "E-JM-10", "final checkpoint ghi attempt prefix nhưng llm_attempts đã mất."
                    )
                an, ad, amin, amax = conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT attempt_id), COALESCE(MIN(attempt_id),0), "
                    "COALESCE(MAX(attempt_id),0) FROM llm_attempts"
                ).fetchone()
                if (state.max_attempt_id is None or state.attempt_record_count is None
                        or int(an) != state.attempt_record_count
                        or int(amax) != state.max_attempt_id or int(ad) != int(an)
                        or state.max_attempt_id != state.attempt_record_count
                        or (int(an) and int(amin) != 1)):
                    raise LoiJournal(
                        "E-JM-10", "llm_attempts không còn đúng final SQLite prefix 1..N."
                    )
            elif has_attempts and int(conn.execute("SELECT COUNT(*) FROM llm_attempts").fetchone()[0]):
                raise LoiJournal(
                    "E-JM-10", "llm_attempts có row nhưng final checkpoint thiếu attempt prefix."
                )
        finally:
            conn.close()

    @staticmethod
    def _verify_final_history(run_dir: Path, manifest: JournalManifest,
                              entry: CheckpointEntry, expected_tick: int) -> None:
        """Validate segment/recovery lineage and its append-only external evidence."""
        segments = sorted(manifest.segments, key=lambda item: item.segment_id)
        ids = [segment.segment_id for segment in segments]
        if ids != list(range(manifest.segment_id + 1)):
            raise LoiJournal("E-JM-11", "segment_id không liên tục 0..segment cuối.")
        if not segments or segments[-1].status != "closed" or segments[-1].ended_at_tick != expected_tick:
            raise LoiJournal("E-JM-11", "final segment chưa đóng đúng tick cuối.")
        if segments[-1].segment_id != entry.segment_id:
            raise LoiJournal("E-JM-11", "final segment không khớp checkpoint cuối.")
        expected_links = {(segment.segment_id - 1, segment.segment_id)
                          for segment in segments if segment.segment_id > 0}
        actual_links = {(recovery.from_segment_id, recovery.new_segment_id)
                        for recovery in manifest.recoveries if recovery.new_segment_id > 0}
        if actual_links != expected_links:
            raise LoiJournal("E-JM-11", "recoveries không tạo lineage một-đối-một cho segments.")
        recovery_path = Path(run_dir) / "journal_recovery.jsonl"
        if manifest.recoveries and not recovery_path.exists():
            raise LoiJournal("E-JM-11", "manifest có recovery nhưng thiếu journal_recovery.jsonl.")
        logged: set[tuple[int, int, str]] = set()
        if recovery_path.exists():
            try:
                rows = [json.loads(line) for line in recovery_path.read_text(
                    encoding="utf-8").splitlines() if line.strip()]
            except json.JSONDecodeError as exc:
                raise LoiJournal("E-JM-11", f"journal_recovery.jsonl không phải JSON: {exc}") from exc
            for row in rows:
                if row.get("run_uuid") != manifest.run_uuid:
                    raise LoiJournal("E-JM-11", "journal_recovery có run_uuid khác manifest.")
                logged.add((int(row.get("from_segment_id", -99)),
                            int(row.get("new_segment_id", -99)), str(row.get("kind", ""))))
        for recovery in manifest.recoveries:
            key = (recovery.from_segment_id, recovery.new_segment_id, recovery.kind)
            if key not in logged:
                raise LoiJournal("E-JM-11", "một RecoveryEntry không có evidence journal_recovery.")
            for state in recovery.journals.values():
                quarantine = state.get("quarantine_file")
                if quarantine and not (Path(run_dir) / quarantine).is_file():
                    raise LoiJournal(
                        "E-JM-11", f"thiếu quarantine evidence {quarantine} của recovery.")

    def _kiem_identity(self, hien_tai: JournalIdentity) -> None:
        cu = self.manifest.identity
        for truong, ma in sorted(MA_IDENTITY.items()):
            a, b = getattr(cu, truong), getattr(hien_tai, truong)
            # The source inventory is a new non-negotiable provenance field.  Unlike older
            # optional identity fields, a missing value cannot be assumed compatible: it would
            # permit an old/unknown executable tree to append a new trajectory.
            source_missing = truong == "runtime_source_identity" and (a is None or b is None)
            if source_missing or (a is not None and b is not None and a != b):
                a_text = str(a)[:16]
                b_text = str(b)[:16]
                raise LoiJournal(
                    ma,
                    f"{truong} đổi hoặc thiếu giữa hai segment: manifest {a_text} ≠ "
                    f"hiện tại {b_text}. Resume sẽ tạo một artifact hai-nửa-hai-luật, không "
                    "qua nổi cổng replay. Hãy chạy run mới.",
                )

    # ---------- restore: truncate-with-quarantine ----------
    def restore(self, tick: int, *, identity: JournalIdentity,
                operator_flag: str | None = None) -> RecoveryEntry:
        """Đưa MỌI journal Class-A về đúng prefix tại tick N. Tail bị bỏ được **MOVE** sang
        ``checkpoints/orphans/`` (hash + index vào ``recoveries[]``) — KHÔNG XÓA.
        ``llm_calls``: ``superseded=1``, KHÔNG DELETE row."""
        entry = self.verify(tick, identity)
        seg_cu = self.manifest.segment_id
        seg_moi = seg_cu + 1
        qdir = self.ck_dir / "orphans" / f"seg{seg_cu:04d}_after_tick{int(tick):04d}"
        ghi_nhan: dict[str, dict[str, Any]] = {}
        for ten in CLASS_A:
            st = entry.journals.get(ten)
            if not isinstance(st, JsonlState):
                continue
            ghi_nhan[ten] = self._cat_va_cach_ly(ten, st, qdir)
            # rolling hash của segment mới bắt đầu ĐÚNG tại prefix đã verify
            self._offset[ten] = st.byte_offset
            self._count[ten] = st.record_count
            h = hashlib.sha256()
            self._nap_hasher(h, self.run_dir / TEN_FILE[ten], st.byte_offset)
            self._hasher[ten] = h
        sq_state = entry.journals.get("llm_calls")
        max_call = sq_state.max_call_id if isinstance(sq_state, SqliteState) else 0
        max_attempt = sq_state.max_attempt_id if isinstance(sq_state, SqliteState) else None
        ghi_nhan["llm_calls"] = self._supersede_llm_calls(
            max_call_id=max_call, max_attempt_id=max_attempt, checkpoint_tick=int(tick),
            from_segment=seg_cu, new_segment=seg_moi,
        )
        rec = RecoveryEntry(
            at_utc=_bay_gio(),
            kind="operator_recover" if operator_flag else "truncate_on_resume",
            resumed_checkpoint_tick=int(tick), from_segment_id=seg_cu, new_segment_id=seg_moi,
            quarantine_dir=str(qdir.relative_to(self.run_dir)).replace("\\", "/"),
            journals=ghi_nhan, operator_flag=operator_flag,
        )
        self._dong_segment(seg_cu, "closed_truncated")
        self.manifest.recoveries.append(rec)
        self.manifest.segments.append(SegmentEntry(
            segment_id=seg_moi, started_at_tick=int(tick), resumed_from_tick=int(tick),
            identity=identity))
        self.manifest.segment_id = seg_moi
        self.manifest.identity = identity
        self._ghi_manifest()
        self._ghi_recovery_log(rec)
        return rec

    def recover_toan_bo(self, tick: int, *, identity: JournalIdentity,
                        ly_do: str) -> RecoveryEntry:
        """``--recover-journal`` (escape hatch CÓ GIÁ): quarantine TOÀN BỘ journal Class-A
        hiện có (không chỉ tail) vì không biết prefix nào đúng, rồi chạy tiếp với journal
        rỗng từ tick N. Artifact bị hạ **VĨNH VIỄN** xuống ``diagnostic_only_unreplayable``:
        transcript prefix đã mất ⇒ replay-from-t0 là BẤT KHẢ THI (sự thật, không phải hình
        phạt). Flag này KHÔNG BAO GIỜ làm một run xanh trở lại."""
        seg_cu = self.manifest.segment_id
        seg_moi = seg_cu + 1
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        qdir = self.ck_dir / "orphans" / f"legacy_{stamp}"
        ghi_nhan: dict[str, dict[str, Any]] = {}
        for ten in CLASS_A:
            rong = JsonlState(byte_offset=0, record_count=0, sha256_prefix=SHA_RONG)
            ghi_nhan[ten] = self._cat_va_cach_ly(ten, rong, qdir)
            self._offset[ten] = 0
            self._count[ten] = 0
            self._hasher[ten] = hashlib.sha256()
        ghi_nhan["llm_calls"] = self._supersede_llm_calls(
            max_call_id=None, max_attempt_id=None, checkpoint_tick=int(tick),
            from_segment=seg_cu, new_segment=seg_moi,
        )
        rec = RecoveryEntry(
            at_utc=_bay_gio(), kind="operator_recover", resumed_checkpoint_tick=int(tick),
            from_segment_id=seg_cu, new_segment_id=seg_moi,
            quarantine_dir=str(qdir.relative_to(self.run_dir)).replace("\\", "/"),
            journals=ghi_nhan, operator_flag="--recover-journal", reason_code=ly_do,
        )
        self._dong_segment(seg_cu, "closed_quarantined")
        self.manifest.recoveries.append(rec)
        self.manifest.segments.append(SegmentEntry(
            segment_id=seg_moi, started_at_tick=int(tick), resumed_from_tick=int(tick),
            identity=identity))
        self.manifest.segment_id = seg_moi
        self.manifest.identity = identity
        self.manifest.replay_complete = False
        self.manifest.artifact_status_forced = "diagnostic_only_unreplayable"
        self.manifest.journals = {}
        self._ghi_manifest()
        self._ghi_recovery_log(rec)
        return rec

    # ---------- nội bộ ----------
    def _reset_journal_cu(self) -> None:
        """Run MỚI trên run-dir đã có journal (vd tools.verify_local chạy lại cùng run-name):
        quarantine bytes cũ rồi bắt đầu từ 0. Append chồng lên quỹ đạo cũ = đúng bệnh
        real60 (events trùng, call_id lặp) ⇒ không được phép."""
        co_gi = [t for t in CLASS_A
                 if (self.run_dir / TEN_FILE[t]).exists()
                 and (self.run_dir / TEN_FILE[t]).stat().st_size > 0]
        sq = self.run_dir / TEN_FILE["llm_calls"]
        if not co_gi and not sq.exists():
            return
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        qdir = self.ck_dir / "orphans" / f"pre_run_{stamp}"
        ghi_nhan: dict[str, dict[str, Any]] = {}
        for ten in CLASS_A:
            rong = JsonlState(byte_offset=0, record_count=0, sha256_prefix=SHA_RONG)
            ghi_nhan[ten] = self._cat_va_cach_ly(ten, rong, qdir)
        if sq.exists():
            ghi_nhan["llm_calls"] = self._supersede_llm_calls(
                max_call_id=None, max_attempt_id=None, checkpoint_tick=-1,
                from_segment=-1, new_segment=0)
        rec = RecoveryEntry(
            at_utc=_bay_gio(), kind="fresh_run_reset", resumed_checkpoint_tick=0,
            from_segment_id=-1, new_segment_id=0,
            quarantine_dir=str(qdir.relative_to(self.run_dir)).replace("\\", "/"),
            journals=ghi_nhan, reason_code="run mới ghi đè run-dir đã có journal",
        )
        self.manifest.recoveries.append(rec)
        self._ghi_recovery_log(rec)

    def _cat_va_cach_ly(self, ten: str, st: JsonlState, qdir: Path) -> dict[str, Any]:
        """MOVE bytes ``[byte_offset, EOF)`` sang quarantine rồi truncate file live."""
        path = self.run_dir / TEN_FILE[ten]
        if not path.exists():
            return {"bytes_removed": 0, "records_removed": 0, "sha256_removed": SHA_RONG}
        size = path.stat().st_size
        if size <= st.byte_offset:
            return {"bytes_removed": 0, "records_removed": 0, "sha256_removed": SHA_RONG}
        with open(path, "rb") as f:
            f.seek(st.byte_offset)
            tail = f.read()
        qdir.mkdir(parents=True, exist_ok=True)
        dich = qdir / TEN_FILE[ten]
        with open(dich, "wb") as f:
            f.write(tail)
            f.flush()
            os.fsync(f.fileno())
        with open(path, "r+b") as f:
            f.truncate(st.byte_offset)
            f.flush()
            os.fsync(f.fileno())
        return {
            "bytes_removed": len(tail),
            "records_removed": tail.count(b"\n"),
            "sha256_removed": hashlib.sha256(tail).hexdigest(),
            "quarantine_file": str(dich.relative_to(self.run_dir)).replace("\\", "/"),
        }

    def _supersede_llm_calls(self, *, max_call_id: int | None, max_attempt_id: int | None,
                             checkpoint_tick: int, from_segment: int,
                             new_segment: int) -> dict[str, Any]:
        """Supersede the discarded prefix tail in both immutable cost ledgers.

        ``llm_attempts`` is deliberately handled *here*, before ``RecoveryEntry`` is committed.
        A denied-before-start tail has no logical ``llm_calls`` row, so the old gateway-side
        post-recovery mutation had no durable counterpart. This journal-owned transaction records
        the attempt count/range in the same recovery evidence as logical calls.
        """
        sq = self.run_dir / TEN_FILE["llm_calls"]
        empty = {
            "rows_superseded": 0, "call_id_range": None,
            "attempt_record_count": 0, "attempt_id_range": None,
            "attempt_rows_superseded": 0, "deleted": 0,
        }
        if not sq.exists():
            return empty
        conn = sqlite3.connect(sq)
        try:
            cot = _cot_llm_calls(conn)
            if not cot:
                return empty
            if "segment_id" not in cot:  # migration additive (write path duy nhất)
                conn.execute("ALTER TABLE llm_calls ADD COLUMN segment_id INTEGER")
            if "superseded" not in cot:
                conn.execute("ALTER TABLE llm_calls ADD COLUMN superseded INTEGER DEFAULT 0")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS journal_recovery (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, at_utc TEXT,
                    resumed_checkpoint_tick INTEGER, from_segment_id INTEGER,
                    new_segment_id INTEGER, call_id_lo INTEGER, call_id_hi INTEGER,
                    rows_superseded INTEGER)"""
            )
            if max_call_id is None:  # explicit recovery/reset has no trustworthy prefix
                call_where, call_params = "tick > ?", (checkpoint_tick,)
            else:
                call_where, call_params = "call_id > ?", (max_call_id,)
            call_row = conn.execute(
                f"SELECT MIN(call_id), MAX(call_id), COUNT(*) FROM llm_calls "  # noqa: S608
                f"WHERE {call_where} AND COALESCE(superseded,0)=0", call_params,
            ).fetchone()
            call_lo, call_hi, call_count = call_row[0], call_row[1], int(call_row[2])

            has_attempts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='llm_attempts'"
            ).fetchone()
            attempt_lo = attempt_hi = None
            attempt_count = 0
            if has_attempts:
                attempt_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(llm_attempts)")
                }
                if "superseded" not in attempt_columns:
                    conn.execute(
                        "ALTER TABLE llm_attempts ADD COLUMN superseded INTEGER DEFAULT 0"
                    )
                if max_attempt_id is None:
                    attempt_where, attempt_params = "tick > ?", (checkpoint_tick,)
                else:
                    attempt_where, attempt_params = "attempt_id > ?", (max_attempt_id,)
                attempt_row = conn.execute(
                    f"SELECT MIN(attempt_id), MAX(attempt_id), COUNT(*) FROM llm_attempts "  # noqa: S608
                    f"WHERE {attempt_where} AND COALESCE(superseded,0)=0", attempt_params,
                ).fetchone()
                attempt_lo, attempt_hi, attempt_count = (
                    attempt_row[0], attempt_row[1], int(attempt_row[2])
                )

            if call_count:
                conn.execute(
                    f"UPDATE llm_calls SET superseded=1, segment_id=COALESCE(segment_id,?) "  # noqa: S608
                    f"WHERE {call_where} AND COALESCE(superseded,0)=0",
                    (from_segment, *call_params),
                )
                conn.execute(
                    "INSERT INTO journal_recovery (at_utc, resumed_checkpoint_tick,"
                    " from_segment_id, new_segment_id, call_id_lo, call_id_hi, rows_superseded)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (_bay_gio(), checkpoint_tick, from_segment, new_segment,
                     call_lo, call_hi, call_count),
                )
            if attempt_count:
                conn.execute(
                    f"UPDATE llm_attempts SET superseded=1 "  # noqa: S608
                    f"WHERE {attempt_where} AND COALESCE(superseded,0)=0",
                    attempt_params,
                )
            conn.commit()
        finally:
            conn.close()
        return {
            "rows_superseded": call_count,
            "call_id_range": [call_lo, call_hi] if call_count else None,
            "attempt_record_count": attempt_count,
            "attempt_id_range": [attempt_lo, attempt_hi] if attempt_count else None,
            "attempt_rows_superseded": attempt_count,
            "deleted": 0,
        }

    def _dong_segment(self, seg_id: int, trang_thai: str) -> None:
        for s in self.manifest.segments:
            if s.segment_id == seg_id and s.status == "active":
                s.status = trang_thai

    def _ghi_recovery_log(self, rec: RecoveryEntry) -> None:
        """``journal_recovery.jsonl`` append-only ở run-dir (JOURNAL-3)."""
        dong = {
            "at_utc": rec.at_utc, "run_uuid": self.manifest.run_uuid,
            "run_name": self.manifest.run_name, "kind": rec.kind,
            "from_tick": rec.resumed_checkpoint_tick,
            "from_segment_id": rec.from_segment_id, "new_segment_id": rec.new_segment_id,
            "bytes_truncated": sum(int(v.get("bytes_removed", 0))
                                   for v in rec.journals.values()),
            "records_truncated": sum(int(v.get("records_removed", 0))
                                     for v in rec.journals.values()),
            "rows_superseded": int(rec.journals.get("llm_calls", {}).get(
                "rows_superseded", 0)),
            "attempt_record_count": int(rec.journals.get("llm_calls", {}).get(
                "attempt_record_count", 0)),
            "attempt_rows_superseded": int(rec.journals.get("llm_calls", {}).get(
                "attempt_rows_superseded", 0)),
            "attempt_id_range": rec.journals.get("llm_calls", {}).get("attempt_id_range"),
            "files_moved": [v["quarantine_file"] for v in rec.journals.values()
                            if v.get("quarantine_file")],
            "quarantine_dir": rec.quarantine_dir,
            "operator_flag": rec.operator_flag,
            "ly_do": rec.reason_code or (
                "resume: journal về đúng prefix của checkpoint (ADR 0006 §C.1)"),
        }
        p = self.run_dir / "journal_recovery.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(dong, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _nap_hasher(h, path: Path, byte_offset: int) -> None:
        if byte_offset <= 0 or not path.exists():
            return
        con = byte_offset
        with open(path, "rb") as f:
            while con > 0:
                chunk = f.read(min(1 << 20, con))
                if not chunk:
                    break
                h.update(chunk)
                con -= len(chunk)

    # ---------- đóng segment cuối run ----------
    def ket_thuc(self, tick: int) -> None:
        for s in self.manifest.segments:
            if s.segment_id == self.manifest.segment_id:
                s.ended_at_tick = int(tick)
                s.status = "closed"
        self._ghi_manifest()


def _digest_states(states: dict[str, TrangThaiJournal]) -> str:
    blob = json.dumps({k: v.model_dump(mode="json") for k, v in sorted(states.items())},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- kiểm tra liên tục (đọc)
def kiem_lien_tuc(run_dir: Path) -> dict[str, Any]:
    """Tính TỪ NỘI DUNG FILE (không cần manifest) ⇒ bắt được cả artifact legacy.

    Trả về dict các phát hiện; ``ok=False`` khi journal không thể là bằng chứng replay:
    event ``seq`` trùng/gap, tick lùi trong thứ tự file, ``call_id`` transcript trùng,
    metric tick trùng, ``unrecognized_intents`` lệch sổ đối ứng với events.
    Đây là hàm ĐỌC — không sửa một byte nào của run."""
    run_dir = Path(run_dir)
    kq: dict[str, Any] = {"ok": True, "loi": [], "canh_bao": []}
    khoa_ev_un: list[tuple] = []  # đối ứng của unrecognized_intents.jsonl (xem cuối hàm)

    ev = run_dir / TEN_FILE["events"]
    if ev.exists():
        seqs: list[int] = []
        ticks: list[int] = []
        dong_thay: dict[str, int] = {}
        trung_khit = 0
        n = 0
        with open(ev, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                n += 1
                dong_thay[s] = dong_thay.get(s, 0) + 1
                if dong_thay[s] == 2:
                    trung_khit += 1
                try:
                    d = json.loads(s)
                except json.JSONDecodeError:
                    kq["loi"].append(f"events dòng {n} không phải JSON")
                    kq["ok"] = False
                    continue
                if "seq" in d:
                    seqs.append(int(d["seq"]))
                if "tick" in d:
                    ticks.append(int(d["tick"]))
                if d.get("loai") == "unrecognized_intent":
                    khoa_ev_un.append((int(d.get("tick", -1)), d.get("ai"), d.get("intent"),
                                       d.get("ly_do")))
        kq["events_records"] = n
        lui = sum(1 for a, b in zip(ticks, ticks[1:], strict=False) if b < a)
        kq["events_tick_regressions"] = lui
        if lui:
            kq["ok"] = False
            kq["loi"].append(f"events: {lui} lần tick LÙI trong thứ tự file "
                             "(tail của segment bị bỏ còn nằm trong journal)")
        kq["events_dup_lines"] = trung_khit
        if seqs:
            if len(set(seqs)) != len(seqs):
                kq["ok"] = False
                kq["loi"].append(f"events: seq trùng ({len(seqs) - len(set(seqs))} bản)")
            if seqs != list(range(1, len(seqs) + 1)):
                kq["ok"] = False
                kq["loi"].append("events: seq không liên tục 1..E (gap hoặc không tăng)")
            if trung_khit:  # seq duy nhất ⇒ dòng trùng khít là BẤT KHẢ ⇒ file đã bị sửa
                kq["ok"] = False
                kq["loi"].append(f"events: {trung_khit} dòng TRÙNG KHÍT dù có seq")
        else:
            if n:
                kq["canh_bao"].append(
                    "events: legacy (không có seq) — bằng chứng cứng duy nhất là tick LÙI")
            if trung_khit:
                # KHÔNG hard: một agent chế tác cùng món 4 lần trong CÙNG tick sinh 4 dòng
                # byte-identical hợp lệ (mock60_spatial: 46 dòng như vậy, không phải nhiễm bẩn).
                # Trùng khít CHỈ là bằng chứng nhiễm bẩn khi đi kèm tick LÙI (real60: 230 dòng,
                # tất cả ở tick ≥ 106 = vùng resume). Dòng trùng một mình là AMBIGUOUS.
                kq["canh_bao"].append(
                    f"events: {trung_khit} dòng trùng khít (legacy không có seq ⇒ không phân "
                    "biệt được sự kiện lặp hợp lệ với ghi-lại-đoạn-đã-bỏ)")

    tr = run_dir / TEN_FILE["transcript"]
    if tr.exists():
        expected_call_id = 1
        transcript_records = 0
        malformed = missing = non_integer = discontinuous = 0
        with open(tr, encoding="utf-8") as f:
            for physical_line, line in enumerate(f, start=1):
                s = line.strip()
                if not s:
                    continue
                transcript_records += 1
                try:
                    d = json.loads(s)
                except (TypeError, json.JSONDecodeError):
                    malformed += 1
                    kq["loi"].append(
                        f"transcript dòng vật lý {physical_line} không phải JSON hợp lệ")
                    continue
                if not isinstance(d, dict) or "call_id" not in d:
                    missing += 1
                    kq["loi"].append(
                        f"transcript dòng vật lý {physical_line} thiếu call_id")
                    continue
                call_id = d["call_id"]
                if isinstance(call_id, bool) or not isinstance(call_id, int):
                    non_integer += 1
                    kq["loi"].append(
                        f"transcript dòng vật lý {physical_line} call_id không phải int")
                    continue
                if call_id != expected_call_id:
                    discontinuous += 1
                    kq["loi"].append(
                        f"transcript dòng vật lý {physical_line} call_id={call_id}, "
                        f"phải là {expected_call_id} (gap/đảo/lặp/zero)")
                    # Keep the expected physical sequence unchanged: a later valid value cannot
                    # repair a corrupt physical line by merely resynchronizing the counter.
                    continue
                expected_call_id += 1
        kq["transcript_records"] = transcript_records
        kq["transcript_max_call_id"] = expected_call_id - 1
        kq["transcript_malformed"] = malformed
        kq["transcript_missing_call_id"] = missing
        kq["transcript_noninteger_call_id"] = non_integer
        kq["transcript_discontinuous_call_id"] = discontinuous
        kq["transcript_dup_call_id"] = discontinuous  # compatibility counter; continuity is exact.
        if malformed or missing or non_integer or discontinuous:
            kq["ok"] = False

    sq = run_dir / TEN_FILE["llm_calls"]
    if sq.exists():
        conn = sqlite3.connect(sq)
        try:
            cot = _cot_llm_calls(conn)
            if cot:
                tong = int(conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0])
                kq["llm_calls_burned"] = tong
                if "superseded" in cot:
                    bad_call_sup = int(conn.execute(
                        "SELECT COUNT(*) FROM llm_calls WHERE superseded IS NULL "
                        "OR superseded NOT IN (0,1)"
                    ).fetchone()[0])
                    if bad_call_sup:
                        kq["ok"] = False
                        kq["loi"].append(
                            f"llm_calls: {bad_call_sup} superseded không phải binary 0/1")
                    hl, sup = conn.execute(
                        "SELECT SUM(CASE WHEN superseded=0 THEN 1 ELSE 0 END),"
                        " SUM(CASE WHEN superseded=1 THEN 1 ELSE 0 END) FROM llm_calls"
                    ).fetchone()
                    hl, sup = int(hl or 0), int(sup or 0)
                else:
                    hl, sup = tong, 0
                kq["llm_calls_effective"] = hl
                kq["llm_calls_superseded"] = sup
                co_rec = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='journal_recovery'"
                ).fetchone()
                kq["llm_recovery_rows"] = int(conn.execute(
                    "SELECT COALESCE(SUM(rows_superseded),0) FROM journal_recovery"
                ).fetchone()[0]) if co_rec else 0
                n, d, mn, mx = conn.execute(
                    "SELECT COUNT(*), COUNT(DISTINCT call_id), COALESCE(MIN(call_id),0),"
                    " COALESCE(MAX(call_id),0) FROM llm_calls"
                ).fetchone()
                kq["llm_calls_max_id"] = int(mx)
                if int(n) != int(d) or (int(n) and (int(mn) != 1 or int(mx) != int(n))):
                    kq["ok"] = False
                    kq["loi"].append("llm_calls: call_id không liên tục 1..N")

            has_attempts = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='llm_attempts'"
            ).fetchone()
            if not has_attempts:
                kq["llm_attempts_evidence"] = "unavailable"
            else:
                attempt_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(llm_attempts)")
                }
                if "attempt_id" not in attempt_columns:
                    kq["llm_attempts_evidence"] = "unavailable"
                    kq["ok"] = False
                    kq["loi"].append("llm_attempts: thiếu attempt_id")
                elif "superseded" not in attempt_columns:
                    kq["llm_attempts_evidence"] = "unavailable"
                    kq["ok"] = False
                    kq["loi"].append("llm_attempts: thiếu cột superseded")
                else:
                    n, d, mn, mx = conn.execute(
                        "SELECT COUNT(*), COUNT(DISTINCT attempt_id),"
                        " COALESCE(MIN(attempt_id),0), COALESCE(MAX(attempt_id),0) "
                        "FROM llm_attempts"
                    ).fetchone()
                    attempts_burned = int(n)
                    kq["llm_attempts_evidence"] = "available"
                    kq["llm_attempts_burned"] = attempts_burned
                    kq["llm_attempts_max_id"] = int(mx)
                    if (int(n) != int(d)
                            or (attempts_burned and (int(mn) != 1 or int(mx) != attempts_burned))):
                        kq["ok"] = False
                        kq["loi"].append("llm_attempts: attempt_id không liên tục 1..N")
                    bad_attempt_sup = int(conn.execute(
                        "SELECT COUNT(*) FROM llm_attempts WHERE superseded IS NULL "
                        "OR superseded NOT IN (0,1)"
                    ).fetchone()[0])
                    if bad_attempt_sup:
                        kq["ok"] = False
                        kq["loi"].append(
                            f"llm_attempts: {bad_attempt_sup} superseded không phải binary 0/1")
                    eff, sup = conn.execute(
                        "SELECT SUM(CASE WHEN superseded=0 THEN 1 ELSE 0 END),"
                        " SUM(CASE WHEN superseded=1 THEN 1 ELSE 0 END) FROM llm_attempts"
                    ).fetchone()
                    kq["llm_attempts_effective"] = int(eff or 0)
                    kq["llm_attempts_superseded"] = int(sup or 0)
        finally:
            conn.close()

    # journal thứ 5 (F-12/A-14): `unrecognized_intents.jsonl` được truncate+quarantine khi
    # resume nhưng TRƯỚC ĐÂY không hề có kiểm liên tục ⇒ bản ghi của một segment đã bị vứt bỏ
    # nằm lại trong file mà không ai thấy. Hai bằng chứng cứng, tính TỪ NỘI DUNG FILE:
    #   (1) tick KHÔNG được lùi trong thứ tự file (tail của segment cũ xen vào);
    #   (2) SỔ ĐỐI ỨNG: `World.ghi_unrecognized` (engine/world.py:399-406) ghi ĐỒNG THỜI một
    #       event `unrecognized_intent` và một dòng jsonl ⇒ hai journal phải khớp TỪNG BẢN GHI
    #       theo thứ tự. Lệch = một trong hai journal đã bị cắt/ghi lệch nhau.
    un = run_dir / TEN_FILE["unrecognized"]
    if un.exists() and ev.exists():
        khoa_un: list[tuple] = []
        for i, line in enumerate(un.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                kq["ok"] = False
                kq["loi"].append(f"unrecognized_intents dòng {i} không phải JSON")
                continue
            khoa_un.append((int(r.get("tick", -1)), r.get("ai"), r.get("intent"),
                            r.get("ly_do")))
        kq["unrecognized_records"] = len(khoa_un)
        kq["unrecognized_events"] = len(khoa_ev_un)
        ut = [k[0] for k in khoa_un]
        lui_un = sum(1 for a, b in zip(ut, ut[1:], strict=False) if b < a)
        kq["unrecognized_tick_regressions"] = lui_un
        if lui_un:
            kq["ok"] = False
            kq["loi"].append(
                f"unrecognized_intents: {lui_un} lần tick LÙI trong thứ tự file "
                "(tail của segment bị bỏ còn nằm trong journal)")
        if khoa_un != khoa_ev_un:
            kq["ok"] = False
            kq["loi"].append(
                f"unrecognized_intents LỆCH SỔ ĐỐI ỨNG với events ({len(khoa_un)} bản ghi vs "
                f"{len(khoa_ev_un)} event `unrecognized_intent`, so theo thứ tự). Hai journal "
                "do CÙNG một lệnh ghi (World.ghi_unrecognized) ⇒ lệch nghĩa là một trong hai "
                "đã bị cắt/ghi lệch (journal thứ 5 không được truncate cùng nhịp).")

    mt = run_dir / TEN_FILE["metrics"]
    if mt.exists():
        ticks = [json.loads(line)["tick"]
                 for line in mt.read_text(encoding="utf-8").splitlines() if line.strip()]
        kq["metrics_records"] = len(ticks)
        if len(set(ticks)) != len(ticks):
            kq["ok"] = False
            kq["loi"].append("metrics: tick trùng")
        if ticks and ticks != list(range(1, len(ticks) + 1)):
            kq["ok"] = False
            kq["loi"].append("metrics: tick không liên tục 1..M")

    try:
        mf = RunJournals.doc_manifest(run_dir)
    except Exception as exc:  # noqa: BLE001 — malformed evidence is a hard continuity failure
        mf = None
        kq["ok"] = False
        kq["loi"].append(f"journal_manifest không hợp lệ: {type(exc).__name__}: {exc}")
    if mf is not None:
        kq["run_uuid"] = mf.run_uuid
        kq["segment_id"] = mf.segment_id
        kq["replay_complete"] = mf.replay_complete
        kq["artifact_status_forced"] = mf.artifact_status_forced
        attempt_recovery_counts: list[int] = []
        attempt_recovery_incomplete = False
        for recovery in mf.recoveries:
            ledger = recovery.journals.get("llm_calls", {})
            if "attempt_rows_superseded" not in ledger:
                attempt_recovery_incomplete = True
                continue
            attempt_recovery_counts.append(int(ledger["attempt_rows_superseded"]))
        kq["llm_attempt_recovery_rows"] = (
            None if attempt_recovery_incomplete else sum(attempt_recovery_counts)
        )
        metadata_missing = []
        for checkpoint in mf.checkpoints:
            state = checkpoint.journals.get("llm_calls")
            if (isinstance(state, SqliteState)
                    and (state.max_attempt_id is None
                         or state.attempt_record_count is None)):
                metadata_missing.append(checkpoint.tick)
        kq["llm_attempt_checkpoint_metadata_missing"] = metadata_missing
        for ten in CLASS_A:
            st = mf.journals.get(ten)
            if not isinstance(st, JsonlState):
                continue
            path = run_dir / TEN_FILE[ten]
            size = path.stat().st_size if path.exists() else 0
            if size < st.byte_offset:
                kq["ok"] = False
                kq["loi"].append(f"{TEN_FILE[ten]} ngắn hơn byte_offset của checkpoint cuối")
    else:
        kq["canh_bao"].append("không có checkpoints/journal_manifest.json (run legacy)")
    return kq


def don_quarantine(run_dir: Path) -> list[Path]:
    """Liệt kê file quarantine (JOURNAL-3: tail bị bỏ phải TỒN TẠI, không bị xóa)."""
    q = Path(run_dir) / "checkpoints" / "orphans"
    return sorted(q.rglob("*.jsonl")) if q.exists() else []


__all__ = [
    "CLASS_A",
    "TEN_FILE",
    "CheckpointEntry",
    "JournalIdentity",
    "JournalManifest",
    "JsonlState",
    "LoiJournal",
    "RecoveryEntry",
    "RunJournals",
    "SegmentEntry",
    "SqliteState",
    "don_quarantine",
    "kiem_lien_tuc",
]
