"""Cổng bằng chứng — `tools.verify_research_run` (ADR 0006 §C.4, test matrix §6).

Regression cứng cho **F-06** (cổng phát false-green: `verify_research_run real60_spatial`
từng in "ĐỦ BẰNG CHỨNG ✅" + **exit 0** trên một artifact KHÔNG replay được) và **F-07**
(`--json` luôn `ValueError` ⇒ output máy-đọc-được của gate đã chết).

Kèm ba `world_hash` pin legacy (ADR 0007 §0.1): P0 phải là **hash-neutral**. Một pin đổi ⇒
implementation đã phá `world_hash` struct ⇒ DỪNG, KHÔNG sửa test.

Tất cả CHỈ ĐỌC với artifact người dùng: `data/runs/real60_spatial/` được so sha256 từng file
trước/sau khi chạy gate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

import run as run_mod
import tools.verify_research_run as vrr
from engine.config import load_config
from engine.journal import kiem_lien_tuc
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.rulebot import quyet_dinh_tat_ca

ROOT = Path(__file__).resolve().parent.parent
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
REAL60 = ROOT / "data" / "runs" / "real60_spatial"

# ADR 0007 §0.1 — ba chuỗi này là GATE CỨNG của P0/P1.
PIN_RULEBOT_S11_T20 = "4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b"
PIN_RULEBOT_S42_T20 = "f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153"
PIN_SPATIAL_S11_T20 = "afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745"

OVERLAY_G = {
    "ban_do": {"kich_thuoc": [12, 12]},
    "nhan_khau": {"dan_so_ban_dau": 7},
    "minds": {"checkpoint_moi_n_tick": 3, "dung_cong_cu_the_gioi": False,
              "nghi_dinh_ky_moi_n_tick": 1, "concurrency": 4},
}


@pytest.fixture
def ov(tmp_path: Path) -> Path:
    p = tmp_path / "ov_gate.yaml"
    p.write_text(yaml.safe_dump(OVERLAY_G, allow_unicode=True), encoding="utf-8")
    return p


def _chay(ov: Path, *, mode: str, ten: str, ticks: int = 6, seed: int = 4,
          them: tuple[str, ...] = ()) -> None:
    argv = ["--mode", mode, "--run-name", ten, "--ticks", str(ticks), "--seed", str(seed),
            "--config-overlay", str(ov), *them]
    run_mod.chay_run(run_mod._tao_parser().parse_args(argv))


def _van_tay(d: Path) -> dict[str, str]:
    return {str(p.relative_to(d)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(d.rglob("*")) if p.is_file()}


# ================================================================ hash pin (P0 hash-neutral)
@pytest.mark.parametrize(("ten", "overlays", "seed", "pin"), [
    ("legacy_off_s11", [], 11, PIN_RULEBOT_S11_T20),
    ("legacy_off_s42", [], 42, PIN_RULEBOT_S42_T20),
    ("spatial_on_s11", [SPATIAL], 11, PIN_SPATIAL_S11_T20),
])
def test_world_hash_legacy_bat_bien(ten, overlays, seed, pin):
    """P0 (catalog + prompt renderer + journal seq/segment) KHÔNG được đổi `world_hash`."""
    cfg = load_config(overlays=[p.resolve() for p in overlays])
    w = tao_the_gioi(cfg, seed, events_path=None)
    n = len(w.parcels)
    for _ in range(20):
        chay_mot_tick(w, quyet_dinh_tat_ca, n)
    assert w.world_hash() == pin, (
        f"[{ten}] world_hash ĐÃ ĐỔI ⇒ P0 không còn hash-neutral (ADR 0006 §C.6). "
        "KHÔNG sửa pin — đi tìm thay đổi đã lọt vào behavioral_state().")


# ================================================================ F-06 regression (real60)
@pytest.mark.skipif(
    not REAL60.is_dir(),
    reason="artifact người dùng (data/ nằm trong .gitignore) — không có trên clone sạch")
def test_f06_real60_spatial_khong_bao_gio_xanh_lai():
    """F-06 REGRESSION (CRITICAL). Cổng cũ SKIP replay cho mode real, SKIP lưu `ok=None`,
    `Ket.failed()` chỉ fail khi `ok is False` ⇒ in `ĐỦ BẰNG CHỨNG ✅` + **exit 0** trên một
    artifact có 403 `call_id` lặp và 1 tick LÙI. Cấm nó xanh lại bằng BẤT KỲ đường nào."""
    truoc = _van_tay(REAL60)

    ket = vrr.verify_run("real60_spatial", quick=False)
    assert ket.failed() is True, "artifact không replay được PHẢI trượt cổng\n" + ket.render()
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY, ket.artifact_status

    # đúng CÁI SAI, không phải sai vì lý do khác
    ok_jc, chi_tiet, hard_jc = ket.lay("journal_continuity")
    assert ok_jc is False and hard_jc is True
    assert "call_id" in chi_tiet and "tick LÙI" in chi_tiet

    # và không còn item SKIP nào có thể nuốt FAIL
    skip = [n for n, ok, _d, hard in ket.items if ok is None and hard]
    assert skip == [], f"còn item SKIP hard (đường phát false-green): {skip}"

    assert vrr.main(["real60_spatial"]) == 1, "exit code phải != 0"
    assert _van_tay(REAL60) == truoc, "verify là CHỈ ĐỌC — artifact bị SỬA"


@pytest.mark.skipif(not REAL60.is_dir(), reason="artifact người dùng")
def test_f07_json_khong_crash_tren_real60(capsys):
    """F-07: `Ket.items` là 4-tuple; code cũ unpack 3 ⇒ `--json` LUÔN ValueError."""
    ma = vrr.main(["real60_spatial", "--quick", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert ma == 1
    assert out["run"] == "real60_spatial"
    assert out["ok"] is False
    assert out["artifact_status"] == vrr.DIAGNOSTIC_ONLY
    assert all({"name", "ok", "detail", "hard"} <= set(c) for c in out["checks"])


@pytest.mark.skipif(not REAL60.is_dir(), reason="artifact người dùng")
def test_journal_continuity_tinh_tu_NOI_DUNG_FILE_khong_can_manifest():
    """`journal_continuity` phải tính TỪ NỘI DUNG FILE, không từ `journal_manifest.json` —
    nếu không, artifact legacy (không có manifest) sẽ lọt cổng."""
    from engine.journal import RunJournals

    assert RunJournals.doc_manifest(REAL60) is None, "real60 legacy: KHÔNG có manifest"
    jc = kiem_lien_tuc(REAL60)
    assert jc["ok"] is False, "phải bắt được bẩn dù KHÔNG có manifest"
    assert jc["transcript_dup_call_id"] == 403
    assert jc["events_tick_regressions"] == 1


# ================================================================ run sạch ⇒ replay_verified
def test_run_sach_moi_thi_replay_verified(tmp_path, monkeypatch, ov):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _chay(ov, mode="rulebot", ten="sach")
    ket = vrr.verify_run("sach", quick=False)
    assert ket.failed() is False, ket.render()
    assert ket.artifact_status == vrr.REPLAY_VERIFIED
    ok, _d, hard = ket.lay("replay_world_hash")
    assert ok is True and hard is True
    ok_jc, _d, _h = ket.lay("journal_continuity")
    assert ok_jc is True


def test_run_mock_co_transcript_chay_cong_replay_that(tmp_path, monkeypatch, ov):
    """mock + transcript + p_malformed=0 ⇒ cổng replay-from-transcript là HARD và phải PASS."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _chay(ov, mode="mock", ten="mk",
          them=("--fast", "--transcript", "--p-malformed", "0.0"))
    ket = vrr.verify_run("mk", quick=False)
    ok, chi_tiet, hard = ket.lay("replay_from_transcript")
    assert ok is True, chi_tiet
    assert hard is True, "mock p_malformed=0 ⇒ cổng transcript phải HARD"
    assert "0 miss, 0 chưa dùng" in chi_tiet
    assert ket.artifact_status == vrr.REPLAY_VERIFIED
    assert ket.failed() is False


# ================================================================ identity mismatch = FAIL
def _sua_manifest(rd: Path, khoa: str, gia_tri: str) -> None:
    p = rd / "experiment_manifest.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["reproducibility"][khoa] = gia_tri
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.parametrize("khoa", ["prompt_template_hash", "capability_catalog_hash"])
def test_identity_mismatch_la_skipped_version_mismatch_va_FAIL(khoa, tmp_path, monkeypatch, ov):
    """ADR 0006 §C.4: identity lệch ⇒ `skipped_version_mismatch` = **FAIL**, KHÔNG im lặng
    PASS và cũng KHÔNG phải một hash-FAIL trần (người đọc sẽ kết luận nhầm 'mô phỏng mất
    tất định' trong khi sự thật là 'artifact cũ hơn interface')."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _chay(ov, mode="mock", ten="idm",
          them=("--fast", "--transcript", "--p-malformed", "0.0"))
    rd = tmp_path / "idm"
    assert vrr.verify_run("idm", quick=False).artifact_status == vrr.REPLAY_VERIFIED

    _sua_manifest(rd, khoa, "0" * 64)
    ket = vrr.verify_run("idm", quick=False)
    assert ket.artifact_status == vrr.VERSION_MISMATCH, ket.render()
    assert ket.failed() is True, "identity mismatch phải là FAIL, không phải SKIP/PASS"
    ok, chi_tiet, _h = ket.lay("replay_from_transcript")
    assert ok is False
    assert "identity LỆCH" in chi_tiet or "version_mismatch" in chi_tiet


def test_manifest_moi_co_capability_catalog_hash(tmp_path, monkeypatch, ov):
    """P0.3: `capability_catalog_hash` phải nằm trong manifest của MỌI mode (rulebot cũng
    phát intent qua cùng bộ action ⇒ tập action là một phần identity của run)."""
    from minds.capabilities import catalog_hash

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    _chay(ov, mode="rulebot", ten="cat")
    mf = json.loads((tmp_path / "cat" / "experiment_manifest.json").read_text("utf-8"))
    assert mf["reproducibility"]["capability_catalog_hash"] == catalog_hash()
    assert mf["run"]["run_uuid"], "manifest thiếu run_uuid (ADR 0006 §C.2)"


# ================================================================ artifact bẩn tổng hợp
def test_gate_bat_artifact_ban_kieu_real60_tren_du_lieu_tong_hop(tmp_path, monkeypatch):
    """Bản tổng hợp của F-06 (chạy được cả trên clone sạch không có data/): artifact legacy
    KHÔNG manifest, có `call_id` lặp + tick lùi ⇒ FAIL + `diagnostic_only_unreplayable`,
    và run-dir KHÔNG bị ghi thêm gì."""
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
        "run_name": "ban", "mode": "real", "seed": 1, "tick_cuoi": 3, "world_hash": "dead",
        "thoi_gian_s": 1.0, "config_sha256": digest, "scenario": None}), encoding="utf-8")
    (rd / "metrics.jsonl").write_text(
        "".join(json.dumps({"tick": t}) + "\n" for t in (1, 2, 3)), encoding="utf-8")
    (rd / "events.jsonl").write_text(  # tick LÙI 3 → 2 (real60: dòng 4158, 117 → 106)
        "".join(json.dumps({"tick": t, "loai": "x"}) + "\n" for t in (1, 2, 3, 2, 3)),
        encoding="utf-8")
    (rd / "transcript.jsonl").write_text(  # call_id BỊ DÙNG LẠI (real60: 403 lần)
        "".join(json.dumps({"call_id": c, "tick": 1, "prompt_hash": f"h{c}"}) + "\n"
                for c in (1, 2, 3, 1, 2)), encoding="utf-8")
    truoc = _van_tay(rd)

    ket = vrr.verify_run("ban", quick=False)
    assert ket.failed() is True
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY
    ok, chi_tiet, hard = ket.lay("journal_continuity")
    assert ok is False and hard is True and "call_id" in chi_tiet
    # replay KHÔNG được chạy trên artifact bẩn (transcript là bản ghi của quỹ đạo đã bị bỏ)
    ok_r, ly_do, hard_r = ket.lay("replay_from_transcript")
    assert ok_r is False and hard_r is True
    assert "điều kiện tiên quyết" in ly_do
    assert _van_tay(rd) == truoc, "verify là CHỈ ĐỌC — không được ghi vào run dir"
