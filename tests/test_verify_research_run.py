"""Kiểm thử độc lập cho tools/verify_research_run — kiểm toán tái lập một run.

Test khách quan (không nới để hợp thức hóa): dựng run tối giản trong tmp_path và
monkeypatch DATA_DIR để KHÔNG đụng data/runs thật. Không mạng, không LLM, không API.
Một test replay end-to-end THẬT (rulebot vài tick) chứng minh world-hash tái lập TRÙNG,
cũng chạy hoàn toàn trong tmp_path.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import tools.verify_research_run as vrr
from engine.config import load_config
from engine.journal import kiem_lien_tuc
from tools.experiments import build_manifest, write_manifest


def _item(ket: vrr.Ket, name: str) -> tuple[bool | None, str, bool] | None:
    for n, ok, detail, hard in ket.items:
        if n == name:
            return ok, detail, hard
    return None


def _build_run(
    run_dir: Path,
    *,
    seed: int = 5,
    mode: str = "rulebot",
    tick_cuoi: int = 3,
    world_hash: str = "deadbeef",
    outcome_hash: str | None = None,
    config_digest: str | None = None,
    metrics_ticks: list[int] | None = None,
) -> None:
    """Dựng artifact của một run đủ để verify_run chấm; mọi hard-check pass mặc định."""
    run_dir.mkdir(parents=True, exist_ok=True)
    digest = config_digest if config_digest is not None else load_config().digest()
    manifest = build_manifest(
        run_name=run_dir.name, mode=mode, seed=seed, ticks_requested=tick_cuoi,
        config_digest=digest, config_overlays=[], scenario=None, treatments=[],
    )
    manifest["outcome"] = {
        "tick_final": tick_cuoi,
        "world_hash": outcome_hash if outcome_hash is not None else world_hash,
        "elapsed_seconds": 0.1,
        "stopped_for_budget": False,
    }
    write_manifest(run_dir, manifest)
    meta = {
        "run_name": run_dir.name, "mode": mode, "seed": seed,
        "tick_cuoi": tick_cuoi, "world_hash": world_hash,
        "thoi_gian_s": 0.1, "config_sha256": digest, "scenario": None,
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    ticks = metrics_ticks if metrics_ticks is not None else list(range(1, tick_cuoi + 1))
    with open(run_dir / "metrics.jsonl", "w", encoding="utf-8") as f:
        for t in ticks:
            f.write(json.dumps({"tick": t}, ensure_ascii=False) + "\n")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")


def test_legacy_run_without_journal_schema_is_diagnostic_not_green(tmp_path, monkeypatch):
    """Continuity alone cannot upgrade a legacy run with no checkpoint-prefix evidence."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _build_run(tmp_path / "r_ok")
    before = {p.name: p.read_bytes() for p in (tmp_path / "r_ok").iterdir()}
    ket = vrr.verify_run("r_ok", quick=True)
    assert _item(ket, "metrics_contiguous_to_final")[0] is True
    assert _item(ket, "events_present")[0] is True
    assert _item(ket, "journal_manifest_present")[0] is False
    assert _item(ket, "final_checkpoint_journal_evidence")[0] is False
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY
    assert ket.ma_thoat() == vrr.EXIT_THIEU_BANG_CHUNG
    assert {p.name: p.read_bytes() for p in (tmp_path / "r_ok").iterdir()} == before


def test_thieu_manifest_fail(tmp_path, monkeypatch):
    """Xóa experiment_manifest.json → manifest_present FAIL, failed() True."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _build_run(tmp_path / "r_no_manifest")
    (tmp_path / "r_no_manifest" / "experiment_manifest.json").unlink()
    ket = vrr.verify_run("r_no_manifest", quick=True)
    assert ket.failed() is True
    assert _item(ket, "manifest_present")[0] is False


def test_metrics_khong_lien_tuc_fail(tmp_path, monkeypatch):
    """metrics.jsonl thiếu tick giữa → metrics_contiguous_to_final FAIL."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _build_run(tmp_path / "r_gap", tick_cuoi=4, metrics_ticks=[1, 2, 4])
    ket = vrr.verify_run("r_gap", quick=True)
    ok, detail, hard = _item(ket, "metrics_contiguous_to_final")
    assert ok is False, detail
    assert hard is True
    assert ket.failed() is True


def test_outcome_hash_lech_fail(tmp_path, monkeypatch):
    """manifest.outcome.world_hash ≠ run_meta.world_hash → FAIL (hard)."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _build_run(tmp_path / "r_hash", world_hash="aaaaaaaa", outcome_hash="bbbbbbbb")
    ket = vrr.verify_run("r_hash", quick=True)
    ok, _, hard = _item(ket, "outcome_hash_matches_meta")
    assert ok is False
    assert hard is True
    assert ket.failed() is True


def test_config_digest_drift_is_hard_failure(tmp_path, monkeypatch):
    """Changed recorded configuration law cannot be downgraded to provenance warning."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    # digest cố tình sai (ghi cùng vào manifest+meta để manifest_meta_consistent vẫn pass)
    _build_run(tmp_path / "r_drift", config_digest="0" * 64)
    ket = vrr.verify_run("r_drift", quick=True)
    ok, _, hard = _item(ket, "config_digest_reproduced")
    assert ok is False  # digest tái dựng KHÁC digest đã ghi
    assert hard is True
    assert ket.failed() is True, ket.render()


def test_replay_world_hash_trung_that(tmp_path, monkeypatch):
    """End-to-end THẬT: rulebot vài tick → verify_run (không quick) replay hash TRÙNG."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    from engine.tick import chay_mot_tick
    from engine.world import tao_the_gioi
    from minds.rulebot import quyet_dinh_tat_ca

    seed, tick_cuoi = 5, 3
    cfg = load_config()
    w = tao_the_gioi(cfg, seed, events_path=None)
    tong_thua = len(w.parcels)
    while w.tick < tick_cuoi:
        chay_mot_tick(w, quyet_dinh_tat_ca, tong_thua)
    real_hash = w.world_hash()

    _build_run(tmp_path / "r_replay", seed=seed, mode="rulebot",
               tick_cuoi=tick_cuoi, world_hash=real_hash)
    ket = vrr.verify_run("r_replay", quick=False)
    ok, detail, _ = _item(ket, "replay_world_hash")
    assert ok is True, detail
    # A seed replay is not enough to certify an artifact that lacks final checkpoint evidence.
    assert _item(ket, "final_checkpoint_journal_evidence")[0] is False
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY
    assert ket.failed() is True, ket.render()


def test_replay_tai_dung_policy_tu_manifest(tmp_path, monkeypatch):
    """M1 regression: run tạo bằng policy KHÁC rulebot phải replay đúng world-hash — verify_run
    phải đọc reproducibility.policy trong manifest, KHÔNG hardcode rulebot."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    from engine.tick import chay_mot_tick
    from engine.world import tao_the_gioi
    from minds.policies import tao_policy
    from minds.rulebot import quyet_dinh_tat_ca

    seed, tick_cuoi = 5, 3
    cfg = load_config()
    w = tao_the_gioi(cfg, seed, events_path=None)
    policy = tao_policy("feasible_random")
    tong_thua = len(w.parcels)
    while w.tick < tick_cuoi:
        chay_mot_tick(w, policy, tong_thua)
    real_hash = w.world_hash()

    # Test chỉ có nghĩa nếu feasible_random KHÁC rulebot (nếu trùng, hardcode-rulebot không lộ).
    w_rb = tao_the_gioi(cfg, seed, events_path=None)
    while w_rb.tick < tick_cuoi:
        chay_mot_tick(w_rb, quyet_dinh_tat_ca, tong_thua)
    assert w_rb.world_hash() != real_hash, "feasible_random phải khác rulebot để test có nghĩa"

    run_dir = tmp_path / "r_policy"
    _build_run(run_dir, seed=seed, mode="rulebot", tick_cuoi=tick_cuoi, world_hash=real_hash)
    mpath = run_dir / "experiment_manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["reproducibility"]["policy"] = {
        "name": "feasible_random",
        "version": getattr(policy, "version", "0"),
        "params": getattr(policy, "params", {}),
    }
    write_manifest(run_dir, manifest)

    ket = vrr.verify_run("r_policy", quick=False)
    ok, detail, _ = _item(ket, "replay_world_hash")
    assert ok is True, detail  # trước fix M1: replay bằng rulebot → LỆCH → FAIL
    assert _item(ket, "final_checkpoint_journal_evidence")[0] is False
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY
    assert ket.failed() is True, ket.render()


def test_transcript_call_id_physical_continuity_fails_closed(tmp_path):
    """Every nonblank transcript line must be JSON with the physical 1..N call_id sequence."""
    cases = {
        "gap": [{"call_id": 1}, {"call_id": 3}],
        "reversal": [{"call_id": 1}, {"call_id": 2}, {"call_id": 1}],
        "missing": [{"call_id": 1}, {"tick": 2}],
        "noninteger": [{"call_id": 1}, {"call_id": "2"}],
        "malformed": [{"call_id": 1}, "{not json"],
    }
    for name, rows in cases.items():
        run_dir = tmp_path / name
        run_dir.mkdir()
        (run_dir / "transcript.jsonl").write_text(
            "\n".join(row if isinstance(row, str) else json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        result = kiem_lien_tuc(run_dir)
        assert result["ok"] is False, name
        assert any("transcript dòng vật lý" in error for error in result["loi"]), result["loi"]


def _attempt_db(path: Path, *, ids: list[int], superseded: list[int | None]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE llm_calls (call_id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO llm_calls (call_id) VALUES (1)")
        conn.execute(
            "CREATE TABLE llm_attempts (attempt_id INTEGER PRIMARY KEY, superseded INTEGER)"
        )
        conn.executemany(
            "INSERT INTO llm_attempts (attempt_id, superseded) VALUES (?, ?)",
            list(zip(ids, superseded, strict=True)),
        )
        conn.commit()
    finally:
        conn.close()


def test_attempt_forensics_rejects_deleted_gap_and_invalid_superseded(tmp_path):
    gap = tmp_path / "gap"
    gap.mkdir()
    _attempt_db(gap / "llm_calls.sqlite", ids=[1, 3], superseded=[0, 0])
    gap_result = kiem_lien_tuc(gap)
    assert gap_result["ok"] is False
    assert gap_result["llm_attempts_max_id"] == 3
    assert any("attempt_id không liên tục" in error for error in gap_result["loi"])

    invalid = tmp_path / "invalid"
    invalid.mkdir()
    _attempt_db(invalid / "llm_calls.sqlite", ids=[1], superseded=[2])
    invalid_result = kiem_lien_tuc(invalid)
    assert invalid_result["ok"] is False
    assert any("superseded không phải binary" in error for error in invalid_result["loi"])


def test_real_legacy_without_attempt_table_is_diagnostic_not_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    run_dir = tmp_path / "legacy_real"
    _build_run(run_dir, mode="real")
    conn = sqlite3.connect(run_dir / "llm_calls.sqlite")
    try:
        conn.execute("CREATE TABLE llm_calls (call_id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO llm_calls (call_id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()

    ket = vrr.verify_run("legacy_real", quick=True)
    check = _item(ket, "attempt_forensic_identity")
    assert check is not None and check[0] is False
    assert "unavailable" in check[1]
    assert ket.artifact_status == vrr.DIAGNOSTIC_ONLY
    assert ket.ma_thoat() == vrr.EXIT_THIEU_BANG_CHUNG


def _run_rulebot_artifact(tmp_path: Path, monkeypatch, name: str) -> Path:
    """Create a final checkpoint in tmp_path; no provider/network/LLM is involved."""
    import run as run_mod

    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    args = run_mod._tao_parser().parse_args([
        "--mode", "rulebot", "--run-name", name, "--ticks", "2", "--seed", "17",
    ])
    assert run_mod.chay_run(args) == 0
    return tmp_path / name


@pytest.mark.parametrize("call_ids", ([1, 3], [1, 2, 1]), ids=["gap", "reversal"])
def test_direct_replay_rejects_bad_call_ids_before_transcript_reader(
    tmp_path, monkeypatch, call_ids
):
    """Direct replay has the same physical call-id gate as the post-run verifier."""
    import minds.transcript as transcript_mod
    import tools.replay as replay

    run_dir = tmp_path / "direct"
    run_dir.mkdir()
    (run_dir / "run_meta.json").write_text(json.dumps({
        "run_name": "direct", "mode": "real", "seed": 1, "tick_cuoi": 0,
        "world_hash": "deadbeef",
    }), encoding="utf-8")
    (run_dir / "transcript.jsonl").write_text(
        "".join(json.dumps({"call_id": call_id, "prompt_hash": str(call_id)}) + "\n"
                for call_id in call_ids),
        encoding="utf-8",
    )

    class MustNotConstructReader:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("continuity must fail before TranscriptReader")

    monkeypatch.setattr(transcript_mod, "TranscriptReader", MustNotConstructReader)
    result = replay.replay_from_transcript(run_dir)
    assert result.ok is False
    assert "journal_continuity FAIL trước TranscriptReader" in result.reason
    assert "call_id" in result.reason


def test_final_checkpoint_evidence_detects_one_byte_event_prefix_tamper(tmp_path, monkeypatch):
    """Changing one valid JSON byte without changing file length invalidates checkpoint SHA."""
    run_dir = _run_rulebot_artifact(tmp_path, monkeypatch, "prefix_tamper")
    clean = vrr.verify_run("prefix_tamper", quick=True)
    assert _item(clean, "final_checkpoint_journal_evidence")[0] is True, clean.render()

    events = run_dir / "events.jsonl"
    raw = bytearray(events.read_bytes())
    marker = b'"loai": "'
    index = raw.find(marker)
    assert index >= 0, "fixture needs a serialized event type"
    position = index + len(marker)
    raw[position] = ord("Z") if raw[position] != ord("Z") else ord("Y")
    size = events.stat().st_size
    events.write_bytes(raw)
    assert events.stat().st_size == size, "tamper must preserve byte length"

    tampered = vrr.verify_run("prefix_tamper", quick=True)
    evidence = _item(tampered, "final_checkpoint_journal_evidence")
    assert evidence is not None and evidence[0] is False
    assert evidence[2] is True
    assert "sha256" in evidence[1]
    # The change preserves JSON/seq/tick continuity; only immutable prefix evidence detects it.
    assert _item(tampered, "journal_continuity")[0] is True


def test_scenario_digest_drift_is_hard_failure(tmp_path, monkeypatch):
    """A changed declared scenario file is executable-law drift, not a soft provenance warning."""
    from tools.experiments import sha256_file, write_manifest

    run_dir = _run_rulebot_artifact(tmp_path, monkeypatch, "scenario_drift")
    declared = tmp_path / "scenario_file.txt"
    declared.write_text("before", encoding="utf-8")
    manifest_path = run_dir / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["reproducibility"]["scenario"] = "fixture_scenario"
    manifest["reproducibility"]["scenario_files_sha256"] = {
        "scenario_file.txt": sha256_file(declared),
    }
    write_manifest(run_dir, manifest)
    declared.write_text("after ", encoding="utf-8")
    monkeypatch.setattr(vrr, "ROOT", tmp_path)

    result = vrr.verify_run("scenario_drift", quick=True)
    check = _item(result, "scenario_files_unchanged")
    assert check is not None and check[0] is False and check[2] is True
    assert result.failed() is True
