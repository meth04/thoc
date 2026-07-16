"""JOURNAL-1..3 — resume/replay khép kín, kiểm ĐỘC LẬP qua ĐƯỜNG THẬT `run.py` (ADR 0006 §C).

Bộ test này KHÔNG tái dùng fixture của `tests/test_resume_journal.py` (người implement viết).
Nó dựng lại overlay, cơ chế kill, và assertion riêng, rồi kiểm cùng một hợp đồng:

- **JOURNAL-1**: chạy liền N tick  ==  chia hai phiên có `--resume`  ⇒ **cùng `world_hash`**,
  cùng số event, `seq` duy nhất + liên tục, `call_id` duy nhất, metric tick duy nhất,
  transcript tiêu thụ khép kín (`misses == 0 && unused == 0`).
  Ba đường: rulebot · mock(`--transcript`) · real(FakeTransport THUẦN).
- **JOURNAL-2**: byte_offset hỏng / sha256_prefix hỏng / thiếu manifest / `prompt_template_hash`
  đổi ⇒ resume **DỪNG** và **0 byte bị ghi** (so sha256 TỪNG FILE trước/sau).
- **JOURNAL-3**: tail bị bỏ tồn tại trong `checkpoints/orphans/` + dòng `journal_recovery.jsonl`;
  **0 row `llm_calls` bị DELETE**; `call_burned == call_effective + rows_superseded`.
- **ABLATION**: tắt truncate ⇒ PHẢI tái hiện đúng bệnh `real60_spatial` (dup `call_id`,
  `unused > 0`, hash lệch). Không đỏ được ⇒ P0.2 là thừa.
- **F-P02-1**: route NỀN hỏng (500) ⇒ transcript phải có row `outcome == "error"` ⇒ replay
  vẫn `misses == 0`.

KHÔNG mạng, KHÔNG `.env`, KHÔNG LLM thật: mode `real` được dựng qua ``mind_factory`` với
``httpx.MockTransport``.

RANH GIỚI CLAIM: "resume ⇒ cùng world_hash như chạy liền" chỉ đúng khi provider là HÀM THUẦN
của prompt. LLM thật không thuần ⇒ với run real, thứ chứng minh được là "artifact tự nhất quán
và replay ra CHÍNH hash của nó".
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
import yaml

import run as run_mod
from engine.journal import JournalIdentity, RunJournals, don_quarantine, kiem_lien_tuc

# ---- thế giới nhỏ, checkpoint dày để tail bẩn chắc chắn tồn tại ----
OVERLAY_TE = {
    "ban_do": {"kich_thuoc": [12, 12]},
    "nhan_khau": {"dan_so_ban_dau": 7},
    "minds": {
        "checkpoint_moi_n_tick": 3,      # checkpoint ở 3, 6 ⇒ kill ở 8 để lại tail 2 tick
        "dung_cong_cu_the_gioi": False,  # vòng công cụ MCP nằm ngoài scope P0.2
        "nghi_dinh_ky_moi_n_tick": 1,    # ai cũng nghĩ mỗi tick ⇒ có call ở MỌI tick
        "reflection_moi_n_tick": 2,      # route nền phản tư chạy nhiều lần trong 9 tick
        "concurrency": 4,
    },
    # Quota THẬT (rpm 4) làm GatewayCoPacing sleep 3s/slot ⇒ test dài vô ích và biến lỗi
    # quota thành nhiễu. Nâng quota để đo ĐÚNG cái đang đo (journal), không phải rate-limit.
    "quotas": {
        "aistudio": {"models": {"gemini-3.1-flash-lite": {"rpm": 100000, "rpd": 100000}}},
        # FakeTransport-only policy: production 9router remains unverified and
        # fail-closed; this independent journal fixture admits only its local routes.
        "ninerouter": {"models": {
            "gc/gemini-3.1-flash-lite-preview": {
                "rpm": 100000, "rpd": 100000, "tpm": 1000000, "tpm_policy": "verified",
            },
            "gc/gemini-2.5-flash-lite": {
                "rpm": 100000, "rpd": 100000, "tpm": 1000000, "tpm_policy": "verified",
            },
            "gc/gemini-2.5-flash": {
                "rpm": 100000, "rpd": 100000, "tpm": 1000000, "tpm_policy": "verified",
            },
            "gc/gemini-2.5-pro": {
                "rpm": 100000, "rpd": 100000, "tpm": 1000000, "tpm_policy": "verified",
            },
        }},
    },
}
TONG_TICK = 9
KILL = 8  # checkpoint gần nhất = 6 ⇒ tail bẩn = tick 7 (trọn) + tick 8 (dở dang)
CK_RESUME = 6


class _Kill(Exception):
    """Kill cứng giả lập: run.py không kịp checkpoint ⇒ journal còn tail bẩn trên đĩa."""


class _MindNgat:
    """Chạy XONG mind của tick K (⇒ llm_calls/transcript đã có bản ghi tick K) rồi mới ném
    ⇒ engine bỏ dở tick K ⇒ events chỉ có MỘT PHẦN tick K. Đúng hình dạng real60: ba journal
    dừng ở ba chân trời khác nhau."""

    def __init__(self, mind, tick: int):
        self._m = mind
        self._t = tick

    def __call__(self, w):
        kh = self._m(w)
        if w.tick >= self._t:
            raise _Kill(f"kill tại tick {w.tick}")
        return kh

    def __getattr__(self, ten):
        return getattr(self._m, ten)


@pytest.fixture
def ov(tmp_path: Path) -> Path:
    p = tmp_path / "ov_te.yaml"
    p.write_text(yaml.safe_dump(OVERLAY_TE, allow_unicode=True), encoding="utf-8")
    return p


def _args(ov: Path, *, mode: str, ten: str, ticks: int = TONG_TICK, seed: int = 3,
          resume: bool = False, them: tuple[str, ...] = ()):
    argv = ["--mode", mode, "--run-name", ten, "--ticks", str(ticks), "--seed", str(seed),
            "--config-overlay", str(ov), *them]
    if resume:
        argv.append("--resume")
    return run_mod._tao_parser().parse_args(argv)  # đi qua ĐÚNG hợp đồng CLI


def _xa_buffer(giu: dict) -> None:
    w, mind = giu.get("w"), giu.get("mind")
    if w is not None and getattr(w, "events", None) is not None:
        w.events.flush()
        w.events.dong()
    if mind is not None:
        if getattr(mind, "log", None) is not None:
            mind.log.dong()
        if getattr(mind, "transcript", None) is not None:
            mind.transcript.dong()


def _chay(args, *, factory=None, kill_at: int | None = None) -> dict:
    giu: dict = {}
    goc = factory or run_mod.lay_mind_fn

    def f(mode, w, a):
        mind = goc(mode, w, a)
        giu["w"], giu["mind"] = w, mind
        return _MindNgat(mind, kill_at) if kill_at else mind

    try:
        run_mod.chay_run(args, mind_factory=f)
        giu["killed"] = False
    except _Kill:
        giu["killed"] = True
        _xa_buffer(giu)
    return giu


# ---------------------------------------------------------------- đọc artifact
def _jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _meta(rd: Path) -> dict:
    return json.loads((rd / "run_meta.json").read_text(encoding="utf-8"))


def _sq(rd: Path, sql: str, *tham):
    con = sqlite3.connect(rd / "llm_calls.sqlite")
    try:
        return con.execute(sql, tham).fetchone()
    finally:
        con.close()


def _dau_van_tay(rd: Path) -> dict[str, str]:
    """sha256 TỪNG FILE trong run-dir — bằng chứng 'không một byte nào bị ghi'."""
    ra: dict[str, str] = {}
    for p in sorted(rd.rglob("*")):
        if p.is_file():
            ra[str(p.relative_to(rd)).replace("\\", "/")] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return ra


def _kiem_id(rd: Path) -> None:
    """INV-J2: seq liên tục 1..E; call_id transcript/llm_calls duy nhất; metric tick duy nhất."""
    seqs = [e["seq"] for e in _jsonl(rd / "events.jsonl")]
    assert seqs, "events rỗng — test vô nghĩa"
    assert seqs == list(range(1, len(seqs) + 1)), "event seq phải liên tục 1..E"
    ids = [t["call_id"] for t in _jsonl(rd / "transcript.jsonl")]
    assert len(ids) == len(set(ids)), f"transcript call_id trùng {len(ids) - len(set(ids))} bản"
    ticks = [m["tick"] for m in _jsonl(rd / "metrics.jsonl")]
    assert ticks == list(range(1, len(ticks) + 1)), "metric tick phải duy nhất + liên tục"
    if (rd / "llm_calls.sqlite").exists():
        n, d = _sq(rd, "SELECT COUNT(*), COUNT(DISTINCT call_id) FROM llm_calls")
        assert n == d, "llm_calls.call_id phải duy nhất"
    jc = kiem_lien_tuc(rd)
    assert jc["ok"], f"journal_continuity FAIL: {jc['loi']}"


def _kiem_ke_toan_chi_phi(rd: Path) -> None:
    """ADR 0006 §C.1: call_burned = call_effective + rows_superseded; KHÔNG DELETE row nào."""
    m = _meta(rd)
    burned = int(m["so_call_billed"])
    eff = int(m["so_call"])
    sup = int(m["so_call_superseded"])
    assert burned == eff + sup, f"lệch sổ chi phí: burned={burned} eff={eff} sup={sup}"
    tong, = _sq(rd, "SELECT COUNT(*) FROM llm_calls")
    n_sup, = _sq(rd, "SELECT COUNT(*) FROM llm_calls WHERE COALESCE(superseded,0)=1")
    assert tong == burned, "call_burned phải là MỌI row (không xóa row nào)"
    assert n_sup == sup


# ---------------------------------------------------------------- FakeTransport (mode real)
def _text(payload: dict) -> str:
    if "contents" in payload:
        return payload["contents"][0]["parts"][0]["text"]
    return payload["messages"][0]["content"]


def _tra_loi(payload: dict, text: str) -> httpx.Response:
    if "contents" in payload:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20}})
    return httpx.Response(200, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 20}})


def _ids(payload: dict) -> list[str]:
    import re

    t = _text(payload)
    m = re.search(r'\(id "([AE]\d+)"\)', t)
    return [m.group(1)] if m else []


def _transport(quyet_dinh, *, loi_nen: tuple[str, ...] = ()) -> httpx.MockTransport:
    """`quyet_dinh(ids, n) -> list[dict]`. `loi_nen`: prompt route NỀN chứa các chuỗi này
    ⇒ trả HTTP 500 (mô phỏng provider hỏng dai dẳng ở route nền)."""
    dem = {"n": 0}

    def kb(r: httpx.Request):
        payload = json.loads(r.content)
        t = _text(payload)
        for dau in loi_nen:
            if dau in t:
                return httpx.Response(500, json={"error": "loi nen gia lap"})
        ids = _ids(payload)
        if not ids:
            return _tra_loi(payload, "{}")  # route nền ngoan (nếu không bị ép lỗi)
        dem["n"] += 1
        return _tra_loi(payload, json.dumps(quyet_dinh(ids, dem["n"]), ensure_ascii=False))

    return httpx.MockTransport(kb)


def _qd_thuan(ids, _n):
    """Provider THUẦN theo prompt (response chỉ phụ thuộc id trong prompt)."""
    return [{"id": i, "hanh_dong": [{"loai": "phan_bo_cong", "hoc": False}],
             "ly_do": "làm ăn"} for i in ids]


def _qd_co_trang_thai(ids, n):
    """Provider KHÔNG thuần: response phụ thuộc SỐ CALL đã đi qua ⇒ hai phiên trả khác nhau
    cho CÙNG một prompt. Đây chính là cơ chế đã đo trên real60 (9 prompt_hash trùng, cả 9 có
    response KHÁC NHAU)."""
    return [{"id": i, "hanh_dong": [
        {"loai": "phan_bo_cong", "hoc": False},
        {"loai": "dat_lenh", "chieu": "mua", "tai_san": "go", "sl": 1,
         "gia": 8.0 + float(n % 5)},
    ], "ly_do": "làm ăn"} for i in ids]


def _factory_real(tmp: Path, transport):
    def f(mode, w, a):
        from minds.real import MindReal
        from tests.test_real_mind import lam_env

        rd = tmp / (a.run_name or f"{mode}_{a.seed}")
        rd.mkdir(parents=True, exist_ok=True)
        return MindReal(w, rd, w.cfg, lam_env(), rd / "quota.sqlite",
                        transport=transport, cho_toi_s=2.0,
                        transcript_path=rd / "transcript.jsonl")

    return f


# ================================================================ JOURNAL-1
def test_journal1_rulebot_resume_bang_chay_lien(tmp_path, monkeypatch, ov):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(ov, mode="rulebot", ten="rb_lien"))
    h = _meta(tmp_path / "rb_lien")["world_hash"]

    g = _chay(_args(ov, mode="rulebot", ten="rb_chia"), kill_at=KILL)
    assert g["killed"], "fixture hỏng: kill không xảy ra"
    rd = tmp_path / "rb_chia"
    ev_ban = len(_jsonl(rd / "events.jsonl"))
    assert ev_ban > 0
    _chay(_args(ov, mode="rulebot", ten="rb_chia", resume=True))

    assert _meta(rd)["world_hash"] == h, "resume phải cho CÙNG world_hash run liền"
    _kiem_id(rd)
    assert len(_jsonl(rd / "events.jsonl")) == len(
        _jsonl(tmp_path / "rb_lien" / "events.jsonl")), "số event phải bằng run liền"
    assert _meta(rd)["segment_id"] == 1


@pytest.mark.parametrize("p_mal", ["0.0", "0.05"])
def test_journal1_mock_transcript_resume_bang_chay_lien(p_mal, tmp_path, monkeypatch, ov):
    """Có cả p_malformed>0 (adversarial mock): resume vẫn phải bằng chạy liền."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    them = ("--fast", "--transcript", "--p-malformed", p_mal)
    _chay(_args(ov, mode="mock", ten="mk_lien", them=them))
    h = _meta(tmp_path / "mk_lien")["world_hash"]

    _chay(_args(ov, mode="mock", ten="mk_chia", them=them), kill_at=KILL)
    rd = tmp_path / "mk_chia"
    assert _jsonl(rd / "transcript.jsonl"), "phiên 1 phải có transcript, nếu không test rỗng"
    _chay(_args(ov, mode="mock", ten="mk_chia", them=them, resume=True))

    assert _meta(rd)["world_hash"] == h
    _kiem_id(rd)
    _kiem_ke_toan_chi_phi(rd)
    assert len(_jsonl(rd / "transcript.jsonl")) == len(
        _jsonl(tmp_path / "mk_lien" / "transcript.jsonl"))

    if p_mal == "0.0":
        # p_malformed>0: PersonaBot nhắm thửa (da_nham) TRƯỚC khi text hỏng ⇒ side-effect đó
        # không tái dựng được từ transcript (giới hạn ĐÃ BIẾT, tests/test_transcript.py).
        # Với p=0 thì cổng phải khép kín tuyệt đối.
        from tools.replay import replay_from_transcript

        kq = replay_from_transcript(rd)
        assert kq.misses == 0 and kq.unused == 0, kq
        assert kq.hash_match and kq.ok, kq.reason


def test_journal1_real_faketransport_thuan_resume_bang_chay_lien(tmp_path, monkeypatch, ov):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(ov, mode="real", ten="rl_lien"),
          factory=_factory_real(tmp_path, _transport(_qd_thuan)))
    h = _meta(tmp_path / "rl_lien")["world_hash"]

    _chay(_args(ov, mode="real", ten="rl_chia"),
          factory=_factory_real(tmp_path, _transport(_qd_thuan)), kill_at=KILL)
    rd = tmp_path / "rl_chia"
    assert _jsonl(rd / "transcript.jsonl")
    _chay(_args(ov, mode="real", ten="rl_chia", resume=True),
          factory=_factory_real(tmp_path, _transport(_qd_thuan)))

    assert _meta(rd)["world_hash"] == h, "FakeTransport THUẦN: resume phải bằng chạy liền"
    _kiem_id(rd)
    _kiem_ke_toan_chi_phi(rd)
    assert _meta(rd)["so_call_superseded"] > 0, (
        "tail của phiên 1 phải có call bị supersede — nếu không, test không chạm bệnh")

    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.misses == 0 and kq.unused == 0, kq
    assert kq.ok, kq.reason


def test_journal1_real_provider_khong_thuan_van_tu_nhat_quan(tmp_path, monkeypatch, ov):
    """CLAIM BOUNDARY: provider không thuần ⇒ hash resume ĐƯỢC PHÉP khác chạy liền. Thứ phải
    chứng minh là artifact TỰ NHẤT QUÁN: replay ra CHÍNH hash của nó, tiêu thụ khép kín."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(ov, mode="real", ten="st"),
          factory=_factory_real(tmp_path, _transport(_qd_co_trang_thai)), kill_at=KILL)
    rd = tmp_path / "st"
    _chay(_args(ov, mode="real", ten="st", resume=True),
          factory=_factory_real(tmp_path, _transport(_qd_co_trang_thai)))

    _kiem_id(rd)
    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.misses == 0, "transcript phải phục vụ đủ MỌI prompt"
    assert kq.unused == 0, "mọi response phải được tiêu thụ đúng một lần"
    assert kq.hash_match, f"replay phải ra ĐÚNG hash của chính run đó: {kq}"


# ================================================================ ABLATION (refutation)
def test_ablation_tat_truncate_thi_tai_hien_benh_real60(tmp_path, monkeypatch, ov):
    """Tắt ĐÚNG hai cơ chế của P0.2 (truncate+quarantine, supersede, rebase call_id), giữ
    nguyên phần còn lại ⇒ PHẢI tái hiện: dup `call_id`, `unused > 0`, hash LỆCH.

    Không đỏ được ⇒ P0.2 là thừa ⇒ báo cáo NGAY."""
    from minds.transcript import TranscriptReader, TranscriptWriter
    from tools.replay import replay_from_transcript

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(ov, mode="real", ten="ab"),
          factory=_factory_real(tmp_path, _transport(_qd_co_trang_thai)), kill_at=KILL)
    rd = tmp_path / "ab"

    monkeypatch.setattr(RunJournals, "_cat_va_cach_ly",
                        lambda self, ten, st, q: {"bytes_removed": 0, "records_removed": 0,
                                                  "sha256_removed": ""})
    monkeypatch.setattr(RunJournals, "_supersede_llm_calls",
                        lambda self, **kw: {"rows_superseded": 0, "call_id_range": None})
    monkeypatch.setattr(TranscriptWriter, "rebase", lambda self, **kw: None)
    _chay(_args(ov, mode="real", ten="ab", resume=True),
          factory=_factory_real(tmp_path, _transport(_qd_co_trang_thai)))

    ids = [t["call_id"] for t in _jsonl(rd / "transcript.jsonl")]
    dup = len(ids) - len(set(ids))
    jc = kiem_lien_tuc(rd)
    kq = replay_from_transcript(rd)
    reader = TranscriptReader(rd / "transcript.jsonl")
    print(f"\n[ABLATION] dup_call_id={dup} · continuity_loi={jc['loi']} · "
          f"misses={kq.misses} unused={kq.unused} hash_match={kq.hash_match} ok={kq.ok}")

    assert dup > 0, "ABLATION phải tái hiện call_id BỊ DÙNG LẠI (real60: 403)"
    assert not jc["ok"], "journal_continuity phải BẮT được artifact bẩn này"
    assert reader.tong > len(set(ids)), "transcript chứa bản ghi của quỹ đạo đã bị vứt bỏ"
    assert kq.unused > 0 or not kq.hash_match, (
        f"ABLATION phải cho unused>0 HOẶC hash lệch: unused={kq.unused} "
        f"hash_match={kq.hash_match} — nếu không, truncate là THỪA")
    assert not kq.ok, "cổng replay PHẢI đỏ khi journal không được truncate"


# ================================================================ JOURNAL-2 (fail-closed)
def _tail_ban(tmp_path, ov, ten: str) -> Path:
    _chay(_args(ov, mode="mock", ten=ten,
                them=("--fast", "--transcript", "--p-malformed", "0.0")), kill_at=KILL)
    return tmp_path / ten


def _resume_phai_dung(ov, ten: str, ma_loi: str) -> None:
    with pytest.raises(SystemExit, match=ma_loi):
        _chay(_args(ov, mode="mock", ten=ten, resume=True,
                    them=("--fast", "--transcript", "--p-malformed", "0.0")))


def _sua_manifest(rd: Path, sua) -> None:
    p = rd / "checkpoints" / "journal_manifest.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    sua(d)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def test_journal2_thieu_manifest_fail_closed(tmp_path, monkeypatch, ov):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _tail_ban(tmp_path, ov, "fc_missing")
    (rd / "checkpoints" / "journal_manifest.json").unlink()
    truoc = _dau_van_tay(rd)
    _resume_phai_dung(ov, "fc_missing", "E-JM-01")
    assert _dau_van_tay(rd) == truoc, "fail-closed KHÔNG được ghi/sửa một byte nào"


def test_journal2_byte_offset_hong_fail_closed(tmp_path, monkeypatch, ov):
    """byte_offset của checkpoint bị sửa LỚN HƠN kích thước file ⇒ E-JM-06, 0 byte bị ghi."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _tail_ban(tmp_path, ov, "fc_offset")

    def sua(d):
        for e in d["checkpoints"]:
            if e["tick"] == CK_RESUME:
                e["journals"]["events"]["byte_offset"] = 10**9

    _sua_manifest(rd, sua)
    truoc = _dau_van_tay(rd)
    _resume_phai_dung(ov, "fc_offset", "E-JM-06")
    assert _dau_van_tay(rd) == truoc


def test_journal2_sha256_prefix_hong_fail_closed(tmp_path, monkeypatch, ov):
    """byte_offset LÙI vài byte ⇒ prefix hash không khớp ⇒ E-JM-07 (không âm thầm cắt sai chỗ)."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _tail_ban(tmp_path, ov, "fc_sha")

    def sua(d):
        for e in d["checkpoints"]:
            if e["tick"] == CK_RESUME:
                e["journals"]["events"]["sha256_prefix"] = "0" * 64

    _sua_manifest(rd, sua)
    truoc = _dau_van_tay(rd)
    _resume_phai_dung(ov, "fc_sha", "E-JM-07")
    assert _dau_van_tay(rd) == truoc


def test_journal2_prefix_file_bi_sua_fail_closed(tmp_path, monkeypatch, ov):
    """Ai đó sửa NỘI DUNG prefix đã checkpoint (không phải manifest) ⇒ vẫn phải bắt."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _tail_ban(tmp_path, ov, "fc_prefix")
    ev = rd / "events.jsonl"
    b = bytearray(ev.read_bytes())
    b[20] ^= 0x20
    ev.write_bytes(bytes(b))
    truoc = _dau_van_tay(rd)
    _resume_phai_dung(ov, "fc_prefix", "E-JM-07")
    assert _dau_van_tay(rd) == truoc


def test_journal2_prompt_template_hash_doi_fail_closed(tmp_path, monkeypatch, ov):
    """Đổi prompt template giữa hai segment ⇒ transcript hai-nửa-hai-luật ⇒ DỪNG (E-JM-04)."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _tail_ban(tmp_path, ov, "fc_prompt")
    _sua_manifest(rd, lambda d: d["identity"].__setitem__("prompt_template_hash", "0" * 64))
    truoc = _dau_van_tay(rd)
    _resume_phai_dung(ov, "fc_prompt", "E-JM-04")
    assert _dau_van_tay(rd) == truoc


def test_journal_identity_phai_co_capability_catalog_hash():
    """ADR 0006 §C.2 (schema `RunJournalManifest.identity`) liệt kê BỐN trường:
    `config_sha256`, `prompt_template_hash`, **`capability_catalog_hash`**, `git_revision`.
    §C.4 bắt resume verify identity.

    `minds/capabilities.py::catalog_hash()` ĐÃ tồn tại và ĐÃ được `run.py` ghi vào
    `experiment_manifest.reproducibility.capability_catalog_hash`. Nhưng
    `engine/journal.py::JournalIdentity` KHÔNG có trường đó ⇒ **thêm/bớt action giữa hai
    segment KHÔNG bị fail-closed**: một run resume có thể có nửa đầu chạy trên interface cũ
    (không `qua_song`) và nửa sau trên interface mới, mà cổng resume vẫn xanh. Đó đúng là
    lớp lỗi mà §C.4 sinh ra để chặn."""
    assert "capability_catalog_hash" in JournalIdentity.model_fields, (
        "JournalIdentity thiếu capability_catalog_hash ⇒ resume không phát hiện được thay đổi "
        "capability catalog giữa hai segment (ADR 0006 §C.2/§C.4). P0.3 chưa wire."
    )


def test_journal2_identity_catalog_doi_fail_closed(tmp_path, monkeypatch, ov):
    """Hệ quả hành vi của test trên: đổi `capability_catalog_hash` giữa hai segment PHẢI làm
    resume dừng với ĐÚNG mã `E-JM-05`.

    (N-05, adversarial-reviewer vòng 2: `match="E-JM-0"` cũ khớp cả `E-JM-03`/`E-JM-04` ⇒ test
    vẫn xanh dù resume dừng vì lý do KHÁC — nó không kiểm cái nó tuyên bố. `engine/journal.py:
    61-63` gán mỗi trường identity một mã riêng: config_sha256→E-JM-03, prompt_template_hash→
    E-JM-04, capability_catalog_hash→E-JM-05.)
    """
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _tail_ban(tmp_path, ov, "fc_cat")
    mf = RunJournals.doc_manifest(rd)
    assert mf is not None
    idn = mf.identity.model_dump()
    assert idn.get("capability_catalog_hash"), (
        "manifest journal KHÔNG ghi capability_catalog_hash ⇒ không có gì để so ⇒ resume "
        "qua được cả khi tập action đã đổi (ADR 0006 §C.2)")

    _sua_manifest(rd, lambda d: d["identity"].__setitem__(
        "capability_catalog_hash", "0" * 64))
    truoc = _dau_van_tay(rd)
    with pytest.raises(SystemExit, match=r"E-JM-05\b"):
        _chay(_args(ov, mode="mock", ten="fc_cat", resume=True,
                    them=("--fast", "--transcript", "--p-malformed", "0.0")))
    assert _dau_van_tay(rd) == truoc


# ================================================================ JOURNAL-3 (không xóa lịch sử)
def test_journal3_tail_bi_bo_ton_tai_va_khong_xoa_row_nao(tmp_path, monkeypatch, ov):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    them = ("--fast", "--transcript", "--p-malformed", "0.0")
    _chay(_args(ov, mode="mock", ten="q", them=them), kill_at=KILL)
    rd = tmp_path / "q"

    ev_truoc = len(_jsonl(rd / "events.jsonl"))
    tr_truoc = len(_jsonl(rd / "transcript.jsonl"))
    sq_truoc, = _sq(rd, "SELECT COUNT(*) FROM llm_calls")
    tail_calls, = _sq(rd, "SELECT COUNT(*) FROM llm_calls WHERE tick > ?", CK_RESUME)
    # TIỀN ĐỀ (nếu hỏng thì test vô nghĩa — phải báo rõ, không im lặng pass)
    assert tail_calls > 0, f"fixture hỏng: không có llm_call nào sau tick {CK_RESUME}"
    assert len([t for t in _jsonl(rd / "transcript.jsonl")
                if t["tick"] > CK_RESUME]) > 0

    _chay(_args(ov, mode="mock", ten="q", them=them, resume=True))

    # (a) tail bị bỏ TỒN TẠI trong orphans/
    orphans = don_quarantine(rd)
    assert orphans, "tail bị bỏ PHẢI nằm trong checkpoints/orphans/, không được xóa"

    # (b) đúng MỘT dòng journal_recovery.jsonl cho một lần resume
    dong = _jsonl(rd / "journal_recovery.jsonl")
    cat = [d for d in dong if d["kind"] == "truncate_on_resume"]
    assert len(cat) == 1, f"phải có đúng 1 recovery record, có {len(cat)}"
    assert cat[0]["from_tick"] == CK_RESUME
    assert cat[0]["records_truncated"] > 0
    assert cat[0]["files_moved"], "recovery record phải liệt kê file đã chuyển"

    # (c) KHÔNG MẤT DÒNG NÀO: prefix (live) + quarantine == số record trước khi cắt
    qdir = rd / cat[0]["quarantine_dir"]
    dem = {p.name: len(_jsonl(p)) for p in sorted(qdir.glob("*.jsonl"))}
    mf = RunJournals.doc_manifest(rd)
    entry = next(e for e in mf.checkpoints if e.tick == CK_RESUME)
    assert entry.journals["events"].record_count + dem.get("events.jsonl", 0) == ev_truoc
    assert (entry.journals["transcript"].record_count
            + dem.get("transcript.jsonl", 0)) == tr_truoc

    # (d) llm_calls: KHÔNG row nào bị DELETE; đoạn bị bỏ chỉ bị đánh dấu superseded
    sq_sau, = _sq(rd, "SELECT COUNT(*) FROM llm_calls")
    sup, = _sq(rd, "SELECT COUNT(*) FROM llm_calls WHERE superseded=1")
    n_rec, = _sq(rd, "SELECT COUNT(*) FROM journal_recovery")
    assert sq_sau >= sq_truoc, "call_burned phải ĐƠN ĐIỆU TĂNG — không DELETE row nào"
    assert sup > 0, "call của tail phải bị supersede (không xóa)"
    assert n_rec == 1

    # (e) sổ chi phí cân
    _kiem_ke_toan_chi_phi(rd)
    _kiem_id(rd)


# ================================================================ F-P02-1 (route nền hỏng)
NEN_HOI_KY = "Nén hồi ký"
REFLECTION = "niềm tin cốt lõi"
DICH_INTENT = "engine không nhận diện"


def _row_loi(rd: Path, dau: str) -> list[dict]:
    return [t for t in _jsonl(rd / "transcript.jsonl")
            if t.get("outcome") == "error" and dau in (t.get("request") or "")]


def test_fp02_1_route_nen_hong_van_co_row_transcript(tmp_path, monkeypatch, ov):
    """F-P02-1 regression: call route NỀN (`_nen_hoi_ky`, `_reflection`) hỏng phải ghi
    transcript row `outcome="error"`. Không có row ⇒ replay gọi lại route đó → MISS → trượt
    cổng hard `misses == 0` dù artifact hoàn toàn sạch."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    tp = _transport(_qd_thuan, loi_nen=(NEN_HOI_KY, REFLECTION))
    _chay(_args(ov, mode="real", ten="nen"), factory=_factory_real(tmp_path, tp))
    rd = tmp_path / "nen"

    # TIỀN ĐỀ: route nền THẬT SỰ đã hỏng (nếu không, test vacuous)
    r_nen = _row_loi(rd, NEN_HOI_KY)
    r_ref = _row_loi(rd, REFLECTION)
    assert r_nen, "tiền đề hỏng: không có call _nen_hoi_ky nào lỗi ⇒ test không đo gì"
    assert r_ref, "tiền đề hỏng: không có call _reflection nào lỗi ⇒ test không đo gì"
    assert all(t["provider"] == "loi" for t in r_nen + r_ref)

    _kiem_id(rd)
    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.misses == 0, (
        f"route nền hỏng KHÔNG được ghi transcript ⇒ replay MISS ({kq.misses}). "
        "Lỗi provider là một NHÁNH ĐIỀU KHIỂN có tác dụng (rơi về heuristic), không phải "
        "dữ liệu thiếu — nó phải nằm trong artifact.")
    assert kq.unused == 0, kq
    assert kq.hash_match and kq.ok, kq.reason


def test_fp02_1b_route_dich_intent_hong_van_co_row_transcript(tmp_path, monkeypatch, ov):
    """CÙNG hợp đồng, route nền THỨ BA: `MindReal._dich_intent_la` (`minds/real.py:234-236`).

    LLM trả một `loai` lạ ⇒ engine gom vào thùng intent ⇒ MindReal gọi route nền để DỊCH.
    Nếu call đó hỏng, nhánh `except` chỉ ghi event `dich_intent_loi` — KHÔNG ghi transcript
    row. Replay sẽ gọi lại đúng call đó ⇒ `misses > 0` ⇒ trượt cổng hard.
    """
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)

    def qd_co_intent_la(ids, _n):
        return [{"id": i, "hanh_dong": [
            {"loai": "phan_bo_cong", "hoc": False},
            {"loai": "trong_ca_phe", "thua": "P01_01"},  # loại LẠ ⇒ vào thùng intent
        ], "ly_do": "làm ăn"} for i in ids]

    tp = _transport(qd_co_intent_la, loi_nen=(DICH_INTENT,))
    _chay(_args(ov, mode="real", ten="dich"), factory=_factory_real(tmp_path, tp))
    rd = tmp_path / "dich"

    # TIỀN ĐỀ: bộ dịch intent THẬT SỰ được gọi và THẬT SỰ hỏng
    ev = _jsonl(rd / "events.jsonl")
    assert [e for e in ev if e.get("loai") == "dich_intent_loi"], (
        "tiền đề hỏng: route dịch-intent không được gọi hoặc không lỗi ⇒ test không đo gì")

    assert _row_loi(rd, DICH_INTENT), (
        "F-P02-1 CHƯA ĐÓNG HẾT: `minds/real.py::_dich_intent_la` nhánh `except` ghi event "
        "`dich_intent_loi` nhưng KHÔNG gọi `_ghi_call_loi` ⇒ transcript thiếu row ⇒ replay "
        "MISS. Hai route nền kia (`_nen_hoi_ky`, `_reflection`) đã được vá; route này thì "
        "chưa.")

    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.misses == 0, f"replay MISS {kq.misses} vì transcript thiếu call route nền"
