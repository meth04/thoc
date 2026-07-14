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

SCHEMA_VERSION = "journal-1"

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
}


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
                    states["llm_calls"] = SqliteState(max_call_id=int(row[0]),
                                                      record_count=int(row[1]))
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
        if isinstance(sq_state, SqliteState) and sq.exists():
            conn = sqlite3.connect(sq)
            try:
                n = conn.execute("SELECT COUNT(*) FROM llm_calls WHERE call_id <= ?",
                                 (sq_state.max_call_id,)).fetchone()[0]
            finally:
                conn.close()
            if int(n) != sq_state.record_count:
                raise LoiJournal(
                    "E-JM-08",
                    f"llm_calls: {n} row có call_id ≤ {sq_state.max_call_id}, manifest ghi "
                    f"{sq_state.record_count}. Sổ chi phí đã bị sửa (row bị xóa?).",
                )
        return entry

    def _kiem_identity(self, hien_tai: JournalIdentity) -> None:
        cu = self.manifest.identity
        for truong, ma in sorted(MA_IDENTITY.items()):
            a, b = getattr(cu, truong), getattr(hien_tai, truong)
            if a is not None and b is not None and a != b:
                raise LoiJournal(
                    ma,
                    f"{truong} đổi giữa hai segment: manifest {a[:16]} ≠ hiện tại {b[:16]}. "
                    "Resume sẽ tạo một artifact hai-nửa-hai-luật, không qua nổi cổng replay "
                    "(transcript khóa theo prompt_hash; tập action hợp lệ khóa theo catalog). "
                    "Hãy chạy run mới.",
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
        ghi_nhan["llm_calls"] = self._supersede_llm_calls(
            max_call_id=max_call, checkpoint_tick=int(tick),
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
            max_call_id=None, checkpoint_tick=int(tick),
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
                max_call_id=None, checkpoint_tick=-1, from_segment=-1, new_segment=0)
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

    def _supersede_llm_calls(self, *, max_call_id: int | None, checkpoint_tick: int,
                             from_segment: int, new_segment: int) -> dict[str, Any]:
        """KHÔNG BAO GIỜ DELETE. Row của đoạn bị bỏ đã tiêu token/quota/USD thật; xóa chúng
        là làm đẹp chi phí (vi phạm điều luật #6). Chỉ đánh dấu ``superseded=1``."""
        sq = self.run_dir / TEN_FILE["llm_calls"]
        if not sq.exists():
            return {"rows_superseded": 0, "call_id_range": None}
        conn = sqlite3.connect(sq)
        try:
            cot = _cot_llm_calls(conn)
            if not cot:
                return {"rows_superseded": 0, "call_id_range": None}
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
            if max_call_id is None:  # không biết prefix ⇒ cắt theo tick (recover/reset)
                dk, tham = "tick > ?", (checkpoint_tick,)
            else:
                dk, tham = "call_id > ?", (max_call_id,)
            row = conn.execute(
                f"SELECT MIN(call_id), MAX(call_id), COUNT(*) FROM llm_calls "  # noqa: S608
                f"WHERE {dk} AND COALESCE(superseded,0)=0", tham).fetchone()
            lo, hi, n = row[0], row[1], int(row[2])
            if n:
                conn.execute(
                    f"UPDATE llm_calls SET superseded=1, segment_id=COALESCE(segment_id,?) "  # noqa: S608
                    f"WHERE {dk} AND COALESCE(superseded,0)=0", (from_segment, *tham))
                conn.execute(
                    "INSERT INTO journal_recovery (at_utc, resumed_checkpoint_tick,"
                    " from_segment_id, new_segment_id, call_id_lo, call_id_hi, rows_superseded)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (_bay_gio(), checkpoint_tick, from_segment, new_segment, lo, hi, n),
                )
            conn.commit()
        finally:
            conn.close()
        return {"rows_superseded": n, "call_id_range": [lo, hi] if n else None,
                "deleted": 0}

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
        ids: list[int] = []
        with open(tr, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                d = json.loads(s)
                if "call_id" in d:
                    ids.append(int(d["call_id"]))
        kq["transcript_records"] = len(ids)
        dup = len(ids) - len(set(ids))
        kq["transcript_dup_call_id"] = dup
        if dup:
            kq["ok"] = False
            kq["loi"].append(
                f"transcript: {dup} call_id BỊ DÙNG LẠI ⇒ TranscriptReader FIFO trả response "
                "của phiên trước ⇒ replay lệch hash")

    sq = run_dir / TEN_FILE["llm_calls"]
    if sq.exists():
        conn = sqlite3.connect(sq)
        try:
            cot = _cot_llm_calls(conn)
            if cot:
                tong = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
                kq["llm_calls_burned"] = int(tong)
                if "superseded" in cot:
                    hl, sup = conn.execute(
                        "SELECT SUM(CASE WHEN COALESCE(superseded,0)=0 THEN 1 ELSE 0 END),"
                        " SUM(CASE WHEN COALESCE(superseded,0)=1 THEN 1 ELSE 0 END)"
                        " FROM llm_calls").fetchone()
                    hl, sup = int(hl or 0), int(sup or 0)
                else:
                    hl, sup = tong, 0
                kq["llm_calls_effective"] = hl
                kq["llm_calls_superseded"] = sup
                # `journal_recovery` là sổ ĐỐI ỨNG của cột `superseded`: mỗi lần resume ghi
                # số row nó vừa đánh dấu. Tổng hai bên phải bằng nhau — nếu ai đó DELETE row
                # (làm đẹp chi phí) thì cột `superseded` tụt xuống dưới con số sổ đã tuyên bố.
                co_rec = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='journal_recovery'"
                ).fetchone()
                kq["llm_recovery_rows"] = int(conn.execute(
                    "SELECT COALESCE(SUM(rows_superseded),0) FROM journal_recovery"
                ).fetchone()[0]) if co_rec else 0
                if "call_id" in cot:
                    n, d, mx = conn.execute(
                        "SELECT COUNT(*), COUNT(DISTINCT call_id), COALESCE(MAX(call_id),0)"
                        " FROM llm_calls").fetchone()
                    kq["llm_calls_max_id"] = int(mx)
                    if int(n) != int(d):
                        kq["ok"] = False
                        kq["loi"].append("llm_calls: call_id trùng")
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

    mf = RunJournals.doc_manifest(run_dir)
    if mf is not None:
        kq["run_uuid"] = mf.run_uuid
        kq["segment_id"] = mf.segment_id
        kq["replay_complete"] = mf.replay_complete
        kq["artifact_status_forced"] = mf.artifact_status_forced
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
