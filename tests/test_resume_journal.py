"""P0.2 — Resume-safe journals (ADR 0006 §C; JOURNAL-1..3, INV-J1..J8).

Chứng minh bằng FakeTransport (`httpx.MockTransport`) + rulebot + mock: KHÔNG mạng, KHÔNG
LLM thật, KHÔNG đọc .env (mode real được dựng qua ``mind_factory`` chứ không qua
``lay_mind_fn``).

RANH GIỚI CLAIM (bắt buộc, chống overclaim):
    "resume ⇒ cùng world_hash như run liền một mạch" chỉ đúng khi provider là **hàm THUẦN
    của prompt** (FakeTransport ngoan). LLM thật KHÔNG thuần (temperature>0, batching phía
    server). Với run real, tính chất chứng minh được là **"artifact của run đã resume TỰ
    NHẤT QUÁN và replay ra CHÍNH HASH CỦA NÓ"** — xem
    ``test_resume_real_transport_co_trang_thai_van_tu_nhat_quan``. Test matrix có CẢ HAI.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import yaml

import run as run_mod
from engine.journal import RunJournals, don_quarantine, kiem_lien_tuc

# ---------------------------------------------------------------- T-INV-2: hash vàng
# Đóng băng TRƯỚC khi sửa P0.2 (đo trên working tree sạch, xem docs/reviews/P0.2-engine-surgeon.md).
# Nếu một giá trị dưới đây đổi ⇒ implementation đã phá world_hash struct ⇒ DỪNG, không sửa test.
GOLDEN_RULEBOT_SEED7_20TICK = "8be4915e6ea7a57b7433ad80c23e422f3e96ab15ddf9f3f8372614405d32303c"
GOLDEN_MOCK_SEED11_8TICK = "f9afb0790d920afb7d81c98b8d026f66a693a492b6722faf1100eb4efea9380c"

OVERLAY = {
    "ban_do": {"kich_thuoc": [10, 10]},
    "nhan_khau": {"dan_so_ban_dau": 6},
    "minds": {
        "checkpoint_moi_n_tick": 2,   # tail bẩn 1 tick — đúng hình dạng bệnh của real60
        "dung_cong_cu_the_gioi": False,
        "nghi_dinh_ky_moi_n_tick": 1,  # ai cũng nghĩ mỗi tick ⇒ có call ở mọi tick
        "reflection_moi_n_tick": 4,
        "concurrency": 4,
    },
    # RPM/RPD thật (4/450) làm GatewayCoPacing sleep 3s/slot và làm ROUTE NỀN (nén hồi ký /
    # phản tư) HẾT QUOTA giữa test. Route nền hỏng KHÔNG được ghi transcript
    # (`minds/real.py:171-174,314-317` chỉ ghi event) ⇒ replay sinh `miss` nhân tạo. Đây là
    # FINDING riêng (xem docs/reviews/P0.2-engine-surgeon.md §Findings, owner minds-engineer);
    # test P0.2 nâng quota để đo ĐÚNG cái nó muốn đo (journal), không che khuyết tật đó.
    "quotas": {
        "aistudio": {"models": {"gemini-3.1-flash-lite": {"rpm": 100000, "rpd": 100000}}},
        "ninerouter": {"models": {
            "gc/gemini-3.1-flash-lite-preview": {"rpm": 100000, "rpd": 100000}}},
    },
}
TONG_TICK = 8
KILL_TICK = 7  # checkpoint ở 2/4/6 ⇒ tail bẩn = tick 7 (dở dang)


class _KillRun(Exception):
    """Kill cứng giả lập: run.py KHÔNG chạy checkpoint cuối, journal còn tail bẩn."""


class _NgatTaiTick:
    """Proxy mind: chạy mind của tick K (⇒ llm_calls/transcript CÓ bản ghi tick K, được
    commit/flush cuối `MindMock.__call__`) rồi mới ném ⇒ engine bỏ dở tick K ⇒ events chỉ
    có MỘT PHẦN tick K và KHÔNG có checkpoint. Đúng hình dạng bệnh real60: ba journal dừng ở
    ba chân trời khác nhau. Không dùng subprocess/kill (bất định trên Windows)."""

    def __init__(self, mind, tick: int):
        self._mind = mind
        self._tick = tick

    def __call__(self, w):
        ke_hoach = self._mind(w)
        if w.tick >= self._tick:
            raise _KillRun(f"kill giả lập tại tick {w.tick}")
        return ke_hoach

    def __getattr__(self, name):
        return getattr(self._mind, name)


@pytest.fixture
def overlay(tmp_path: Path) -> Path:
    p = tmp_path / "overlay_test.yaml"
    p.write_text(yaml.safe_dump(OVERLAY, allow_unicode=True), encoding="utf-8")
    return p


def _args(overlay: Path, *, mode: str, run_name: str, ticks: int = TONG_TICK,
          seed: int = 5, resume: bool = False, extra: tuple[str, ...] = ()):
    argv = ["--mode", mode, "--run-name", run_name, "--ticks", str(ticks),
            "--seed", str(seed), "--config-overlay", str(overlay), *extra]
    if resume:
        argv.append("--resume")
    return run_mod._tao_parser().parse_args(argv)


def _dong_handles(giu: dict) -> None:
    """Sau kill: xả buffer xuống đĩa (tail bẩn phải TỒN TẠI trên đĩa để test có nghĩa)."""
    w, mind = giu.get("w"), giu.get("mind")
    if w is not None and getattr(w, "events", None) is not None:
        w.events.flush()
        w.events.dong()
    if mind is not None:
        if getattr(mind, "log", None) is not None:
            mind.log.dong()
        if getattr(mind, "transcript", None) is not None:
            mind.transcript.dong()


def _chay(args, *, base_factory=None, kill_at: int | None = None) -> dict:
    giu: dict = {}
    base = base_factory or run_mod.lay_mind_fn

    def factory(mode, w, a):
        mind = base(mode, w, a)
        giu["w"] = w
        giu["mind"] = mind
        return _NgatTaiTick(mind, kill_at) if kill_at else mind

    try:
        run_mod.chay_run(args, mind_factory=factory)
        giu["killed"] = False
    except _KillRun:
        giu["killed"] = True
        _dong_handles(giu)
    return giu


def _meta(run_dir: Path) -> dict:
    return json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))


def _events(run_dir: Path) -> list[dict]:
    p = run_dir / "events.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _transcript(run_dir: Path) -> list[dict]:
    p = run_dir / "transcript.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _metrics(run_dir: Path) -> list[dict]:
    p = run_dir / "metrics.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _kiem_id_duy_nhat(run_dir: Path) -> None:
    """INV-J2: event seq duy nhất + liên tục 1..E; transcript call_id duy nhất;
    llm_calls.call_id duy nhất; metric tick duy nhất."""
    seqs = [e["seq"] for e in _events(run_dir)]
    assert seqs == list(range(1, len(seqs) + 1)), "event seq phải liên tục 1..E, không gap/dup"
    ids = [t["call_id"] for t in _transcript(run_dir)]
    assert len(ids) == len(set(ids)), f"transcript call_id trùng: {len(ids) - len(set(ids))}"
    ticks = [m["tick"] for m in _metrics(run_dir)]
    assert ticks == list(range(1, len(ticks) + 1)), "metric tick phải duy nhất + liên tục"
    sq = run_dir / "llm_calls.sqlite"
    if sq.exists():
        con = sqlite3.connect(sq)
        n, d = con.execute("SELECT COUNT(*), COUNT(DISTINCT call_id) FROM llm_calls").fetchone()
        con.close()
        assert n == d, "llm_calls.call_id phải duy nhất"


# ================================================================ T-INV-1/2: hash bất biến
def test_t_inv_2_world_hash_vang_khong_doi():
    """P0.2 KHÔNG được đổi world_hash struct. Hash vàng đóng băng TRƯỚC khi sửa code."""
    from engine.config import load_config
    from engine.tick import chay_mot_tick
    from engine.world import tao_the_gioi
    from minds.orchestrator import tao_mind_mock
    from minds.rulebot import quyet_dinh_tat_ca

    cfg = load_config()
    w = tao_the_gioi(cfg, 7, events_path=None)
    n = len(w.parcels)
    for _ in range(20):
        chay_mot_tick(w, quyet_dinh_tat_ca, n)
    assert w.world_hash() == GOLDEN_RULEBOT_SEED7_20TICK

    w2 = tao_the_gioi(cfg, 11, events_path=None)
    m = tao_mind_mock(w2, fast=True, run_dir=None, p_malformed=0.0)
    n2 = len(w2.parcels)
    for _ in range(8):
        chay_mot_tick(w2, m, n2)
    assert w2.world_hash() == GOLDEN_MOCK_SEED11_8TICK


def test_t_inv_1_field_journal_khong_vao_world_hash(tmp_path):
    """INV-J1: seq/segment_id/run_uuid/offset/count không nằm trong behavioral_state."""
    from engine.events import EventLog
    from tests.helpers import the_gioi_test

    w = the_gioi_test(seed=3, giu_lai=3)
    h0 = w.world_hash()
    w.events = EventLog(tmp_path / "events.jsonl", start_seq=1000, segment_id=7)
    for i in range(50):
        w.events.ghi(w.tick, "test_event", i=i)
    w.events.flush()
    assert w.world_hash() == h0, "ghi event / đổi seq-segment KHÔNG được đổi world_hash"
    from engine.world import _canonical_state

    blob = json.dumps(_canonical_state(w.behavioral_state()), default=str)
    for cam in ("run_uuid", "byte_offset", "sha256_prefix", "segment_id"):
        assert cam not in blob, f"{cam} lọt vào behavioral_state"


def test_config_snapshot_khong_doi_quy_dao(tmp_path):
    """`World.nap_checkpoint` KHÔNG cfg (fallback `config_snapshot.json`) phải cho ĐÚNG quỹ
    đạo như khi truyền cfg từ YAML.

    Bệnh đã đo: snapshot ghi `sort_keys=True` ⇒ `khong_gian.vu_dong.cay` đảo thứ tự ⇒
    `economy.food_equivalence` (engine/economy.py:43) trả `[thoc, khoai, ngo]` thay vì
    `[thoc, ngo, khoai]` ⇒ `consumption.an_va_suc_khoe` (engine/consumption.py:60) ăn khoai
    trước ngô ⇒ world LỆCH — dù `config_digest` và `world_hash` (canonical-sort) đều KHỚP.
    Trên `mock60_spatial`: lệch ngay tick 94 sau khi nạp checkpoint tick 90."""
    from engine.config import Config, load_config
    from engine.economy import food_equivalence
    from engine.tick import chay_mot_tick
    from engine.world import World, tao_the_gioi

    spatial = Path("scenarios/agrarian_transition_v1/spatial_v1.yaml").resolve()
    if not spatial.exists():
        pytest.skip("cần overlay spatial_v1 để có vụ đông (nhiều loại lương thực)")
    cfg = load_config(overlays=[spatial])
    assert len(food_equivalence(tao_the_gioi(cfg, 1))) > 2, "cần ≥2 cây để test có nghĩa"

    w = tao_the_gioi(cfg, 9, events_path=None)
    n = len(w.parcels)
    for _ in range(3):
        chay_mot_tick(w, __import__("minds.rulebot", fromlist=["x"]).quyet_dinh_tat_ca, n)
    ck = tmp_path / "ck"
    pkl = w.luu_checkpoint(ck)

    snap = Config(json.loads((ck / "config_snapshot.json").read_text(encoding="utf-8")))
    assert list(food_equivalence(tao_the_gioi(snap, 1))) == \
        list(food_equivalence(tao_the_gioi(cfg, 1))), \
        "config_snapshot đảo thứ tự khóa ⇒ engine ăn lương thực theo thứ tự khác"

    from minds.rulebot import quyet_dinh_tat_ca

    wa = World.nap_checkpoint(pkl, None, cfg=cfg)     # đường của run.py --resume
    wb = World.nap_checkpoint(pkl, None)              # fallback snapshot (API trực tiếp)
    assert wa.world_hash() == wb.world_hash()
    for _ in range(5):
        chay_mot_tick(wa, quyet_dinh_tat_ca, n)
        chay_mot_tick(wb, quyet_dinh_tat_ca, n)
    assert wa.world_hash() == wb.world_hash(), \
        "nạp checkpoint bằng fallback snapshot phải đi CÙNG quỹ đạo với cfg YAML"


# ================================================================ JOURNAL-1: resume ≡ liền
def test_journal_1_rulebot_resume_bang_run_lien(tmp_path, monkeypatch, overlay):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="rulebot", run_name="rb_lien"))
    h_lien = _meta(tmp_path / "rb_lien")["world_hash"]

    g = _chay(_args(overlay, mode="rulebot", run_name="rb_chia"), kill_at=KILL_TICK)
    assert g["killed"]
    rd = tmp_path / "rb_chia"
    truoc = len(_events(rd))
    _chay(_args(overlay, mode="rulebot", run_name="rb_chia", resume=True))

    assert _meta(rd)["world_hash"] == h_lien, "resume phải cho CÙNG world_hash run liền"
    _kiem_id_duy_nhat(rd)
    assert kiem_lien_tuc(rd)["ok"], kiem_lien_tuc(rd)["loi"]
    assert len(_events(rd)) == len(_events(tmp_path / "rb_lien"))
    assert truoc > 0


def test_journal_1_mock_transcript_resume_bang_run_lien(tmp_path, monkeypatch, overlay):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    extra = ("--fast", "--transcript", "--p-malformed", "0.0")
    _chay(_args(overlay, mode="mock", run_name="mk_lien", extra=extra))
    h_lien = _meta(tmp_path / "mk_lien")["world_hash"]

    _chay(_args(overlay, mode="mock", run_name="mk_chia", extra=extra), kill_at=KILL_TICK)
    rd = tmp_path / "mk_chia"
    assert _transcript(rd), "phiên 1 phải có transcript (nếu không thì test vô nghĩa)"
    _chay(_args(overlay, mode="mock", run_name="mk_chia", extra=extra, resume=True))

    assert _meta(rd)["world_hash"] == h_lien
    _kiem_id_duy_nhat(rd)
    assert kiem_lien_tuc(rd)["ok"], kiem_lien_tuc(rd)["loi"]
    assert len(_transcript(rd)) == len(_transcript(tmp_path / "mk_lien"))

    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.misses == 0 and kq.unused == 0, kq
    assert kq.ok, kq.reason


# ---------------------------------------------------------------- FakeTransport (mode real)
def _transport_thuan():
    """Provider THUẦN theo prompt: response chỉ phụ thuộc nội dung prompt."""
    import httpx

    from tests.test_real_mind import _ids_tu_prompt, _resp

    def kich_ban(r: httpx.Request):
        payload = json.loads(r.content)
        ids = _ids_tu_prompt(payload)
        if not ids:
            return _resp(payload, "{}")
        qd = [{"id": i, "hanh_dong": [{"loai": "phan_bo_cong", "hoc": False}],
               "ly_do": "làm ăn"} for i in ids]
        return _resp(payload, json.dumps(qd, ensure_ascii=False))

    return httpx.MockTransport(kich_ban)


def _transport_co_trang_thai():
    """Provider KHÔNG thuần (giống LLM thật): response phụ thuộc SỐ CALL đã đi qua, nên hai
    phiên khác nhau trả khác nhau cho CÙNG một prompt. Đây chính là cơ chế đã chứng minh trên
    real60 (9 prompt_hash trùng, cả 9 có response KHÁC NHAU)."""
    import httpx

    from tests.test_real_mind import _ids_tu_prompt, _resp

    dem = {"n": 0}

    def kich_ban(r: httpx.Request):
        payload = json.loads(r.content)
        ids = _ids_tu_prompt(payload)
        dem["n"] += 1
        if not ids:
            return _resp(payload, "{}")
        gia = 8.0 + float(dem["n"] % 5)
        qd = [{"id": i, "hanh_dong": [
            {"loai": "phan_bo_cong", "hoc": False},
            {"loai": "dat_lenh", "chieu": "mua", "tai_san": "go", "sl": 1, "gia": gia},
        ], "ly_do": "làm ăn"} for i in ids]
        return _resp(payload, json.dumps(qd, ensure_ascii=False))

    return httpx.MockTransport(kich_ban)


def _factory_real(tmp_path: Path, transport):
    """Dựng MindReal với FakeTransport — KHÔNG qua lay_mind_fn (nó đọc .env)."""

    def f(mode, w, a):
        from minds.real import MindReal
        from tests.test_real_mind import lam_env

        rd = tmp_path / (a.run_name or f"{mode}_{a.seed}")
        rd.mkdir(parents=True, exist_ok=True)
        return MindReal(w, rd, w.cfg, lam_env(), rd / "quota.sqlite",
                        transport=transport, cho_toi_s=2.0,
                        transcript_path=rd / "transcript.jsonl")

    return f


def test_journal_1_real_faketransport_thuan_resume_bang_run_lien(tmp_path, monkeypatch, overlay):
    """Provider THUẦN ⇒ resume == run liền (đúng như Report_v2 §5 nói, và CHỈ trong trường
    hợp này)."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="real", run_name="rl_lien"),
          base_factory=_factory_real(tmp_path, _transport_thuan()))
    h_lien = _meta(tmp_path / "rl_lien")["world_hash"]

    _chay(_args(overlay, mode="real", run_name="rl_chia"),
          base_factory=_factory_real(tmp_path, _transport_thuan()), kill_at=KILL_TICK)
    rd = tmp_path / "rl_chia"
    assert _transcript(rd)
    _chay(_args(overlay, mode="real", run_name="rl_chia", resume=True),
          base_factory=_factory_real(tmp_path, _transport_thuan()))

    assert _meta(rd)["world_hash"] == h_lien, "FakeTransport thuần: resume phải bằng run liền"
    _kiem_id_duy_nhat(rd)
    assert kiem_lien_tuc(rd)["ok"], kiem_lien_tuc(rd)["loi"]

    m = _meta(rd)
    # chi phí ĐÃ TRẢ (burned) > số call trên quỹ đạo (effective): row của tick 7 phiên 1 vẫn
    # nằm trong llm_calls (superseded=1), KHÔNG bị xóa (ADR 0006 §C.1 ngoại lệ).
    assert m["so_call_billed"] >= m["so_call"]
    assert m["so_call_superseded"] == m["so_call_billed"] - m["so_call"]
    con = sqlite3.connect(rd / "llm_calls.sqlite")
    sup = con.execute("SELECT COUNT(*) FROM llm_calls WHERE superseded=1").fetchone()[0]
    con.close()
    assert sup == m["so_call_superseded"]

    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.ok, f"{kq.reason} · misses={kq.misses} unused={kq.unused}"


def test_resume_real_transport_co_trang_thai_van_tu_nhat_quan(tmp_path, monkeypatch, overlay):
    """CLAIM BOUNDARY: provider KHÔNG thuần ⇒ hash resume ĐƯỢC PHÉP khác run liền. Cái phải
    chứng minh là artifact của run đã resume **tự nhất quán và replay ra chính hash của nó**."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="real", run_name="st_chia"),
          base_factory=_factory_real(tmp_path, _transport_co_trang_thai()), kill_at=KILL_TICK)
    rd = tmp_path / "st_chia"
    _chay(_args(overlay, mode="real", run_name="st_chia", resume=True),
          base_factory=_factory_real(tmp_path, _transport_co_trang_thai()))

    _kiem_id_duy_nhat(rd)
    assert kiem_lien_tuc(rd)["ok"], kiem_lien_tuc(rd)["loi"]

    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    assert kq.misses == 0, "transcript phải phục vụ đủ mọi prompt"
    assert kq.unused == 0, "mọi response phải được tiêu thụ đúng một lần"
    assert kq.hash_match, f"replay phải ra ĐÚNG hash của chính run đó: {kq}"
    assert kq.ok


# ================================================================ ABLATION (refutation)
def test_ablation_khong_truncate_thi_vo(tmp_path, monkeypatch, overlay):
    """Tắt truncate + tắt rebase counter (= hành vi TRƯỚC P0.2) ⇒ PHẢI tái hiện đúng bệnh:
    call_id trùng, con_lai() > 0, replay LỆCH hash. Nếu test này không đỏ được thì P0.2 là thừa."""
    from minds.transcript import TranscriptWriter

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    tp = _transport_co_trang_thai()
    _chay(_args(overlay, mode="real", run_name="ab"),
          base_factory=_factory_real(tmp_path, tp), kill_at=KILL_TICK)
    rd = tmp_path / "ab"

    # ---- ABLATION: tắt ĐÚNG hai cơ chế của P0.2, giữ nguyên phần còn lại ----
    # (1) không cắt/cách ly tail; (2) không supersede row; (3) call_id đếm lại từ 1 (bệnh cũ).
    monkeypatch.setattr(RunJournals, "_cat_va_cach_ly",
                        lambda self, ten, st, qdir: {"bytes_removed": 0,
                                                     "records_removed": 0,
                                                     "sha256_removed": ""})
    monkeypatch.setattr(RunJournals, "_supersede_llm_calls",
                        lambda self, **kw: {"rows_superseded": 0, "call_id_range": None})
    monkeypatch.setattr(TranscriptWriter, "rebase", lambda self, **kw: None)
    _chay(_args(overlay, mode="real", run_name="ab", resume=True),
          base_factory=_factory_real(tmp_path, _transport_co_trang_thai()))

    ids = [t["call_id"] for t in _transcript(rd)]
    dup = len(ids) - len(set(ids))
    assert dup > 0, "ABLATION phải tái hiện call_id BỊ DÙNG LẠI (real60: 403)"
    jc = kiem_lien_tuc(rd)
    assert not jc["ok"], "journal_continuity phải BẮT được artifact bẩn này"

    from minds.transcript import TranscriptReader
    from tools.replay import replay_from_transcript

    kq = replay_from_transcript(rd)
    reader = TranscriptReader(rd / "transcript.jsonl")
    print(f"\n[ABLATION] dup_call_id={dup} · journal_continuity_loi={jc['loi']} · "
          f"replay: misses={kq.misses} unused={kq.unused} hash_match={kq.hash_match} "
          f"ok={kq.ok}")
    assert reader.tong > len(set(ids)), "transcript chứa bản ghi của quỹ đạo đã bị vứt bỏ"
    assert (kq.unused > 0) or (not kq.hash_match), (
        "ABLATION phải cho con_lai()>0 HOẶC hash lệch — nếu không, truncate là thừa: "
        f"unused={kq.unused} hash_match={kq.hash_match}"
    )
    assert not kq.ok, "ABLATION: cổng replay PHẢI đỏ khi journal không được truncate"


# ================================================================ JOURNAL-2: fail-closed
def _chuan_bi_tail_ban(tmp_path, overlay, ten="fc"):
    _chay(_args(overlay, mode="mock", run_name=ten,
                extra=("--fast", "--transcript", "--p-malformed", "0.0")), kill_at=KILL_TICK)
    return tmp_path / ten


def _snapshot(run_dir: Path) -> dict[str, int]:
    return {p.name: p.stat().st_size for p in sorted(run_dir.glob("*.jsonl"))}


def test_journal_2_thieu_manifest_fail_closed(tmp_path, monkeypatch, overlay):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _chuan_bi_tail_ban(tmp_path, overlay, "fc_missing")
    (rd / "checkpoints" / "journal_manifest.json").unlink()
    truoc = _snapshot(rd)
    with pytest.raises(SystemExit, match="E-JM-01"):
        _chay(_args(overlay, mode="mock", run_name="fc_missing", resume=True,
                    extra=("--fast", "--transcript", "--p-malformed", "0.0")))
    assert _snapshot(rd) == truoc, "fail-closed KHÔNG được ghi/sửa một byte nào"


def test_journal_2_prefix_bi_sua_fail_closed(tmp_path, monkeypatch, overlay):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _chuan_bi_tail_ban(tmp_path, overlay, "fc_prefix")
    ev = rd / "events.jsonl"
    b = bytearray(ev.read_bytes())
    b[10] = b[10] ^ 0x20  # lật một bit BÊN TRONG prefix đã checkpoint
    ev.write_bytes(bytes(b))
    truoc = _snapshot(rd)
    with pytest.raises(SystemExit, match="E-JM-07"):
        _chay(_args(overlay, mode="mock", run_name="fc_prefix", resume=True,
                    extra=("--fast", "--transcript", "--p-malformed", "0.0")))
    assert _snapshot(rd) == truoc


def test_journal_2_file_ngan_hon_offset_fail_closed(tmp_path, monkeypatch, overlay):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _chuan_bi_tail_ban(tmp_path, overlay, "fc_short")
    ev = rd / "events.jsonl"
    ev.write_bytes(ev.read_bytes()[:50])  # ngắn hơn byte_offset của checkpoint
    truoc = _snapshot(rd)
    with pytest.raises(SystemExit, match="E-JM-06"):
        _chay(_args(overlay, mode="mock", run_name="fc_short", resume=True,
                    extra=("--fast", "--transcript", "--p-malformed", "0.0")))
    assert _snapshot(rd) == truoc


def test_journal_2_prompt_template_hash_doi_fail_closed(tmp_path, monkeypatch, overlay):
    """D6: đổi prompt template giữa hai segment ⇒ transcript hai-nửa-hai-luật ⇒ DỪNG."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _chuan_bi_tail_ban(tmp_path, overlay, "fc_prompt")
    mp = rd / "checkpoints" / "journal_manifest.json"
    mf = json.loads(mp.read_text(encoding="utf-8"))
    mf["identity"]["prompt_template_hash"] = "0" * 64
    mp.write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
    truoc = _snapshot(rd)
    with pytest.raises(SystemExit, match="E-JM-04"):
        _chay(_args(overlay, mode="mock", run_name="fc_prompt", resume=True,
                    extra=("--fast", "--transcript", "--p-malformed", "0.0")))
    assert _snapshot(rd) == truoc


# ---------------------------------------------------------------- A-06 / F-P03-1
def test_journal_identity_co_du_4_truong_adr_0006_c2():
    """ADR 0006 §C.2: identity của segment có BỐN trường. `capability_catalog_hash` từng
    THIẾU ⇒ đổi `minds/capabilities.py` (thêm action, đổi menu) giữa hai segment KHÔNG bị
    chặn, vì `prompt_template_hash` = sha256(minds/prompts.py) không đổi theo catalog."""
    from engine.journal import JournalIdentity

    assert set(JournalIdentity.model_fields) == {
        "config_sha256", "prompt_template_hash", "capability_catalog_hash", "git_revision"}


def test_journal_manifest_ghi_capability_catalog_hash(tmp_path, monkeypatch, overlay):
    """Run MỚI phải GHI catalog hash vào journal_manifest.identity — không ghi thì cổng
    resume không có gì để so."""
    from minds.capabilities import catalog_hash

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="rulebot", run_name="cat", ticks=2))
    mf = RunJournals.doc_manifest(tmp_path / "cat")
    assert mf.identity.capability_catalog_hash == catalog_hash()
    assert mf.segments[0].identity.capability_catalog_hash == catalog_hash()


def test_journal_2_capability_catalog_hash_doi_fail_closed(tmp_path, monkeypatch, overlay):
    """A-06 (BLOCKING): đổi capability catalog giữa hai segment ⇒ tập action hợp lệ ĐỔI ⇒
    transcript hai-nửa-hai-luật ⇒ resume phải DỪNG (E-JM-05), 0 byte bị ghi."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = _chuan_bi_tail_ban(tmp_path, overlay, "fc_cat")
    mp = rd / "checkpoints" / "journal_manifest.json"
    mf = json.loads(mp.read_text(encoding="utf-8"))
    assert mf["identity"]["capability_catalog_hash"], "manifest phải ghi catalog hash"
    mf["identity"]["capability_catalog_hash"] = "0" * 64
    mp.write_text(json.dumps(mf, ensure_ascii=False), encoding="utf-8")
    truoc = _snapshot(rd)
    with pytest.raises(SystemExit, match="E-JM-05"):
        _chay(_args(overlay, mode="mock", run_name="fc_cat", resume=True,
                    extra=("--fast", "--transcript", "--p-malformed", "0.0")))
    assert _snapshot(rd) == truoc


def test_recover_journal_ha_cap_artifact_vinh_vien(tmp_path, monkeypatch, overlay):
    """Escape hatch CÓ GIÁ: chạy tiếp được, nhưng KHÔNG BAO GIỜ xanh trở lại."""
    import tools.verify_research_run as vrr

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    rd = _chuan_bi_tail_ban(tmp_path, overlay, "rec")
    (rd / "checkpoints" / "journal_manifest.json").unlink()
    _chay(_args(overlay, mode="mock", run_name="rec", resume=True,
                extra=("--fast", "--transcript", "--p-malformed", "0.0",
                       "--recover-journal")))
    mf = RunJournals.doc_manifest(rd)
    assert mf.replay_complete is False
    assert mf.artifact_status_forced == "diagnostic_only_unreplayable"
    assert mf.recoveries[-1].operator_flag == "--recover-journal"
    assert don_quarantine(rd), "journal cũ phải nằm trong orphans/, KHÔNG bị xóa"
    ket = vrr.verify_run("rec", quick=True)
    assert ket.artifact_status == "diagnostic_only_unreplayable"
    assert ket.failed() is True, ket.render()


# ================================================================ JOURNAL-3: không xóa lịch sử
def test_journal_3_tail_bi_bo_van_ton_tai_trong_orphans(tmp_path, monkeypatch, overlay):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    extra = ("--fast", "--transcript", "--p-malformed", "0.0")
    _chay(_args(overlay, mode="mock", run_name="q", extra=extra), kill_at=KILL_TICK)
    rd = tmp_path / "q"
    ev_truoc, tr_truoc = len(_events(rd)), len(_transcript(rd))
    con = sqlite3.connect(rd / "llm_calls.sqlite")
    sq_truoc = con.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    tail_calls = con.execute("SELECT COUNT(*) FROM llm_calls WHERE tick >= ?",
                             (KILL_TICK,)).fetchone()[0]
    con.close()
    # TIỀN ĐỀ của fixture (nếu hỏng, test vô nghĩa — phải báo rõ chứ không im lặng pass):
    # phiên 1 PHẢI có call ở tick bị kill, nếu không thì không có gì để supersede.
    assert tail_calls > 0, (
        f"fixture hỏng: phiên 1 không có llm_call nào ở tick {KILL_TICK} "
        f"(events={ev_truoc}, transcript={tr_truoc}) ⇒ không tái hiện được bệnh real60")
    assert len([t for t in _transcript(rd) if t["tick"] >= KILL_TICK]) > 0

    _chay(_args(overlay, mode="mock", run_name="q", extra=extra, resume=True))

    assert don_quarantine(rd), "tail bị bỏ PHẢI tồn tại trong checkpoints/orphans/"
    rec_log = rd / "journal_recovery.jsonl"
    dong = [json.loads(x) for x in rec_log.read_text(encoding="utf-8").splitlines() if x.strip()]
    cat = [d for d in dong if d["kind"] == "truncate_on_resume"]
    assert len(cat) == 1, "đúng MỘT dòng journal_recovery cho một lần resume"
    assert cat[0]["from_tick"] == 6
    assert cat[0]["records_truncated"] > 0
    assert cat[0]["files_moved"]

    # KHÔNG MẤT MỘT DÒNG NÀO: prefix (live) + quarantine của CHÍNH lần cắt này == số record
    # trước khi cắt. (Scope theo quarantine_dir của recovery, không theo toàn bộ orphans/.)
    qdir = rd / cat[0]["quarantine_dir"]
    dem = {p.name: len([x for x in p.read_text(encoding="utf-8").splitlines() if x.strip()])
           for p in sorted(qdir.glob("*.jsonl"))}
    assert sum(dem.values()) > 0
    mf = RunJournals.doc_manifest(rd)
    entry = next(e for e in mf.checkpoints if e.tick == 6)
    assert entry.journals["events"].record_count + dem.get("events.jsonl", 0) == ev_truoc
    assert (entry.journals["transcript"].record_count
            + dem.get("transcript.jsonl", 0)) == tr_truoc

    # llm_calls: KHÔNG row nào bị xóa; row của đoạn bị bỏ chỉ bị đánh dấu superseded.
    con = sqlite3.connect(rd / "llm_calls.sqlite")
    sq_sau = con.execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    sup = con.execute("SELECT COUNT(*) FROM llm_calls WHERE superseded=1").fetchone()[0]
    n_rec = con.execute("SELECT COUNT(*) FROM journal_recovery").fetchone()[0]
    con.close()
    assert sq_sau >= sq_truoc, "INV-J5: call_burned đơn điệu tăng — KHÔNG DELETE row nào"
    assert sup > 0, "call của tick 7 phiên 1 phải bị supersede (không xóa)"
    assert n_rec == 1


# ================================================================ verify gate (§C.4)
def test_verify_real_chay_replay_khong_con_skip(tmp_path, monkeypatch, overlay):
    """Nhánh SKIP cho mode real đã bị XÓA HẲN ⇒ artifact real sạch phải PASS bằng replay THẬT."""
    import tools.verify_research_run as vrr

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="real", run_name="vr"),
          base_factory=_factory_real(tmp_path, _transport_thuan()))
    ket = vrr.verify_run("vr", quick=False)
    ten = [n for n, _ok, _d, _h in ket.items]
    assert "replay_from_transcript" in ten
    assert not [d for n, ok, d, _h in ket.items if n == "replay_world_hash" and ok is None], \
        "không được còn item SKIP (mode=real cần transcript)"
    ok, detail, hard = ket.lay("replay_from_transcript")
    assert ok is True, detail
    assert hard is True, "replay-from-transcript của mode real phải là HARD check"
    assert ket.artifact_status == "replay_verified"
    assert ket.failed() is False, ket.render()


def test_verify_bat_artifact_ban_kieu_real60(tmp_path, monkeypatch):
    """Artifact legacy KHÔNG có manifest, có call_id trùng + tick lùi (đúng hình dạng
    real60_spatial) ⇒ journal_continuity FAIL + nhãn diagnostic_only_unreplayable, và
    run dir KHÔNG bị ghi thêm gì."""
    import tools.verify_research_run as vrr
    from engine.config import load_config
    from tools.experiments import build_manifest, write_manifest

    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    rd = tmp_path / "ban"
    rd.mkdir()
    digest = load_config().digest()
    mf = build_manifest(run_name="ban", mode="real", seed=1, ticks_requested=3,
                        config_digest=digest, config_overlays=[], scenario=None)
    mf["outcome"] = {"tick_final": 3, "world_hash": "dead", "elapsed_seconds": 1.0,
                     "stopped_for_budget": False}
    write_manifest(rd, mf)
    (rd / "run_meta.json").write_text(json.dumps({
        "run_name": "ban", "mode": "real", "seed": 1, "tick_cuoi": 3,
        "world_hash": "dead", "thoi_gian_s": 1.0, "config_sha256": digest,
        "scenario": None}), encoding="utf-8")
    (rd / "metrics.jsonl").write_text(
        "".join(json.dumps({"tick": t}) + "\n" for t in (1, 2, 3)), encoding="utf-8")
    # events: tick LÙI (3 → 2) như real60 dòng 4158 (117 → 106)
    (rd / "events.jsonl").write_text(
        "".join(json.dumps({"tick": t, "loai": "x"}) + "\n" for t in (1, 2, 3, 2, 3)),
        encoding="utf-8")
    # transcript: call_id BỊ DÙNG LẠI (real60: 403 lần)
    (rd / "transcript.jsonl").write_text(
        "".join(json.dumps({"call_id": c, "tick": 1, "prompt_hash": f"h{c}"}) + "\n"
                for c in (1, 2, 3, 1, 2)), encoding="utf-8")
    truoc = {p.name: p.stat().st_size for p in sorted(rd.iterdir())}

    ket = vrr.verify_run("ban", quick=False)
    ok, detail, hard = ket.lay("journal_continuity")
    assert ok is False and hard is True, detail
    assert "call_id" in detail and "tick LÙI" in detail
    assert ket.artifact_status == "diagnostic_only_unreplayable"
    assert ket.failed() is True
    assert {p.name: p.stat().st_size for p in sorted(rd.iterdir())} == truoc, \
        "verify là CHỈ ĐỌC — không được ghi gì vào run dir"


def test_verify_json_khong_crash(tmp_path, monkeypatch, overlay, capsys):
    """F-07 regression: Ket.items là 4-tuple; code cũ unpack 3 ⇒ --json luôn ValueError.

    A-03 (SIẾT): bản cũ của test này assert `ma == 0` cho `--quick` — đó chính là hợp đồng
    SAI mà adversarial-reviewer chặn: `--quick` SKIP mọi replay ⇒ `pending_verification` ⇒
    tool KHÔNG được phát tín hiệu xanh. Nay `--quick` ⇒ exit 2 và `ok=False`."""
    import tools.verify_research_run as vrr

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="rulebot", run_name="js"))
    capsys.readouterr()  # bỏ stdout của run
    ma = vrr.main(["js", "--quick", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert ma == vrr.EXIT_CHUA_CHUNG_MINH == 2, "--quick KHÔNG được exit 0"
    assert out["run"] == "js"
    assert out["ok"] is False, "--quick chưa chứng minh gì ⇒ ok phải False"
    assert out["exit_code"] == 2
    assert out["artifact_status"] == "pending_verification"  # --quick: chưa replay
    assert out["hard_failures"] == []  # không phải vì có check hỏng, mà vì CHƯA chạy replay
    assert all({"name", "ok", "detail", "hard"} <= set(c) for c in out["checks"])


# ================================================================ A-03: exit code == nhãn
def test_a03_quick_khong_bao_gio_phat_tin_hieu_du_bang_chung(tmp_path, monkeypatch, overlay,
                                                             capsys):
    """A-03 (BLOCKING, cùng hình dạng F-06): `--quick` bỏ cả `replay_world_hash` lẫn
    `replay_from_transcript` ⇒ SKIP (`ok=None`) ⇒ `Ket.failed()` bỏ qua ⇒ tool CŨ in
    'ĐỦ BẰNG CHỨNG ✅' + exit 0 trên MỌI run. Nó chưa chứng minh gì cả."""
    import tools.verify_research_run as vrr

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _chay(_args(overlay, mode="rulebot", run_name="q0"))
    capsys.readouterr()

    ma = vrr.main(["q0", "--quick"])
    out = capsys.readouterr().out
    assert ma != 0, "--quick PHẢI exit non-zero (pending_verification)"
    assert "ĐỦ BẰNG CHỨNG" not in out, out
    assert "pending_verification" in out

    # cùng run, KHÔNG --quick ⇒ cổng replay chạy thật ⇒ mới được xanh
    ma2 = vrr.main(["q0"])
    out2 = capsys.readouterr().out
    assert ma2 == 0, out2
    assert "ĐỦ BẰNG CHỨNG" in out2 and "replay_verified" in out2


def test_a03_transcript_replay_lech_hash_thi_khong_the_exit_0(tmp_path, monkeypatch, overlay,
                                                              capsys):
    """A-03 (ii): artifact mà transcript replay ra THẾ GIỚI KHÁC không bao giờ được exit 0.

    Dựng bằng cách sửa MỘT response trong transcript của một run mock sạch (prefix vẫn dài
    hơn byte_offset của checkpoint cuối nên journal_continuity vẫn xanh — đúng kịch bản
    'mọi check khác PASS, chỉ replay lệch')."""
    import tools.verify_research_run as vrr

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    extra = ("--fast", "--transcript", "--p-malformed", "0.0")
    _chay(_args(overlay, mode="mock", run_name="tw", extra=extra))
    rd = tmp_path / "tw"
    assert vrr.verify_run("tw", quick=False).artifact_status == "replay_verified"

    dong = [json.loads(x) for x in (rd / "transcript.jsonl").read_text(
        encoding="utf-8").splitlines() if x.strip()]
    # bóp méo response CUỐI ⇒ quyết định khác ⇒ world_hash replay khác hash gốc
    dong[-1]["response_raw"] = json.dumps(
        [{"id": "A0001", "hanh_dong": [{"loai": "phan_bo_cong", "hoc": True}],
          "ly_do": "đổi"}], ensure_ascii=False)
    (rd / "transcript.jsonl").write_text(
        "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong), encoding="utf-8")

    capsys.readouterr()
    ma = vrr.main(["tw"])
    out = capsys.readouterr().out
    ket = vrr.verify_run("tw", quick=False)
    ok, chi_tiet, hard = ket.lay("replay_from_transcript")
    assert ok is False, chi_tiet
    assert hard is True, "cổng transcript phải HARD cho MỌI run có transcript (carve-out đã bỏ)"
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY
    assert ma == 1, out
    assert "ĐỦ BẰNG CHỨNG" not in out, out


# ================================================================ A-11: identity sổ chi phí
def test_a11_xoa_row_llm_calls_bi_bat(tmp_path, monkeypatch, overlay):
    """A-11: check cũ (`burned >= effective`) là TAUTOLOGY — nó vẫn PASS sau khi xóa row.
    Identity mới (`MAX(call_id) == COUNT(*)`, `superseded == Σ recovery`) phải BẮT."""
    import tools.verify_research_run as vrr

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    extra = ("--fast", "--transcript", "--p-malformed", "0.0")
    _chay(_args(overlay, mode="mock", run_name="ke", extra=extra))
    rd = tmp_path / "ke"
    ok, chi_tiet, hard = vrr.verify_run("ke", quick=True).lay("cost_accounting_identity")
    assert ok is True and hard is True, chi_tiet

    con = sqlite3.connect(rd / "llm_calls.sqlite")  # "làm đẹp chi phí": xóa 3 row
    con.execute("DELETE FROM llm_calls WHERE call_id IN (SELECT call_id FROM llm_calls LIMIT 3)")
    con.commit()
    burned, eff = con.execute(
        "SELECT COUNT(*), SUM(CASE WHEN COALESCE(superseded,0)=0 THEN 1 ELSE 0 END)"
        " FROM llm_calls").fetchone()
    con.close()
    assert burned >= eff, "tiền đề A-11: check CŨ vẫn đúng sau khi xóa row ⇒ nó vô dụng"

    ket = vrr.verify_run("ke", quick=True)
    ok, chi_tiet, hard = ket.lay("cost_accounting_identity")
    assert ok is False and hard is True, chi_tiet
    assert "BỊ XÓA" in chi_tiet
    assert ket.failed() is True
    assert ket.ma_thoat() != 0


# ================================================================ A-14: journal thứ 5
def test_a14_unrecognized_tick_lui_bi_bat(tmp_path, monkeypatch, overlay):
    """A-14: `unrecognized_intents.jsonl` (journal thứ 5) trước đây KHÔNG hề có kiểm liên
    tục ⇒ bản ghi của segment đã bị vứt bỏ nằm lại mà không ai thấy."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = tmp_path / "u1"
    rd.mkdir()
    (rd / "events.jsonl").write_text("".join(
        json.dumps({"seq": i + 1, "tick": t, "loai": "unrecognized_intent", "ai": "A1",
                    "intent": "x", "ly_do": "r"}, ensure_ascii=False) + "\n"
        for i, t in enumerate((1, 2, 3))), encoding="utf-8")
    (rd / "unrecognized_intents.jsonl").write_text("".join(
        json.dumps({"tick": t, "ai": "A1", "intent": "x", "ly_do": "r"},
                   ensure_ascii=False) + "\n" for t in (1, 2, 3)), encoding="utf-8")
    assert kiem_lien_tuc(rd)["ok"], "tiền đề: journal sạch phải xanh"

    # tail của segment bị bỏ: tick LÙI 3 → 2 (đúng hình dạng real60 ở events)
    with open(rd / "unrecognized_intents.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"tick": 2, "ai": "A1", "intent": "x", "ly_do": "r"},
                           ensure_ascii=False) + "\n")
    jc = kiem_lien_tuc(rd)
    assert jc["ok"] is False
    assert jc["unrecognized_tick_regressions"] == 1
    assert any("tick LÙI" in x for x in jc["loi"])


def test_a14_unrecognized_lech_so_doi_ung_voi_events(tmp_path, monkeypatch, overlay):
    """`World.ghi_unrecognized` ghi ĐỒNG THỜI 1 event + 1 dòng jsonl ⇒ hai journal là sổ đối
    ứng của nhau. Cắt một bên mà quên bên kia (đúng lớp lỗi F-12) phải bị BẮT."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    rd = tmp_path / "u2"
    rd.mkdir()
    (rd / "events.jsonl").write_text("".join(
        json.dumps({"seq": i + 1, "tick": t, "loai": "unrecognized_intent", "ai": "A1",
                    "intent": "x", "ly_do": "r"}, ensure_ascii=False) + "\n"
        for i, t in enumerate((1, 2))), encoding="utf-8")
    (rd / "unrecognized_intents.jsonl").write_text("".join(
        json.dumps({"tick": t, "ai": "A1", "intent": "x", "ly_do": "r"},
                   ensure_ascii=False) + "\n" for t in (1, 2, 3)), encoding="utf-8")
    jc = kiem_lien_tuc(rd)
    assert jc["ok"] is False
    assert jc["unrecognized_records"] == 3
    assert jc["unrecognized_events"] == 2
    assert any("LỆCH SỔ ĐỐI ỨNG" in x for x in jc["loi"])


class _GhiIntentLa:
    """Ép mỗi tick sinh MỘT intent lạ qua ĐÚNG API thật (`World.ghi_unrecognized`) — nó ghi
    đồng thời 1 event + 1 dòng `unrecognized_intents.jsonl`. Mock/rulebot không tự sinh intent
    lạ nên nếu không ép, test journal thứ 5 sẽ VACUOUS (file không tồn tại)."""

    def __init__(self, mind):
        self._m = mind

    def __call__(self, w):
        w.ghi_unrecognized("A0001", "loai_la_thu_nghiem", f"tick {w.tick}")
        return self._m(w)

    def __getattr__(self, name):
        return getattr(self._m, name)


def test_a14_duong_that_resume_cat_journal_thu_5_cung_nhip(tmp_path, monkeypatch, overlay):
    """Đường THẬT (kill giữa tick + `--resume` qua `run.py`): journal thứ 5 phải được
    truncate/quarantine cùng nhịp với events, nếu không sổ đối ứng lệch ⇒ gate đỏ."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    extra = ("--fast", "--transcript", "--p-malformed", "0.0")

    def base(mode, w, a):
        return _GhiIntentLa(run_mod.lay_mind_fn(mode, w, a))

    g = _chay(_args(overlay, mode="mock", run_name="u3", extra=extra), base_factory=base,
              kill_at=KILL_TICK)
    assert g["killed"]
    rd = tmp_path / "u3"
    un = rd / "unrecognized_intents.jsonl"
    n_truoc = len([x for x in un.read_text(encoding="utf-8").splitlines() if x.strip()])
    assert n_truoc == KILL_TICK, "tiền đề: mỗi tick 1 bản ghi, kill ở tick 7 ⇒ 7 bản ghi"

    _chay(_args(overlay, mode="mock", run_name="u3", extra=extra, resume=True),
          base_factory=base)

    jc = kiem_lien_tuc(rd)
    assert jc["ok"], jc["loi"]
    assert jc["unrecognized_records"] == jc["unrecognized_events"] == TONG_TICK, (
        "journal thứ 5 phải có ĐÚNG 1 bản ghi/tick sau resume (tail của segment cũ đã bị cắt, "
        "không append chồng)")
    assert jc["unrecognized_tick_regressions"] == 0
    # tail bị bỏ KHÔNG bị xóa — nó nằm trong orphans/
    assert any(p.name == "unrecognized_intents.jsonl" for p in don_quarantine(rd))
