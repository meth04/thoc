"""Regression contracts for artifact identity and non-destructive output admission."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import run as run_mod
import tools.replay as replay_mod
import tools.verify_research_run as verify_mod
from engine.config import load_config
from engine.journal import LoiJournal, RunJournals
from tools.experiments import runtime_source_identity, write_manifest
from tools.replay import _kiem_identity


def _args(run_name: str, *extra: str):
    return run_mod._tao_parser().parse_args([
        "--mode", "rulebot", "--run-name", run_name, "--ticks", "1", "--seed", "17", *extra,
    ])


def _fingerprints(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*")) if path.is_file()
    }


def _item(result: verify_mod.Ket, name: str):
    return result.lay(name)


def test_non_resume_rejects_occupied_directory_without_mutating_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    run_mod.chay_run(_args("occupied"))
    artifact = tmp_path / "occupied"
    before = _fingerprints(artifact)

    with pytest.raises(SystemExit, match="E-RUN-ISO-01"):
        run_mod.chay_run(_args("occupied"))

    assert _fingerprints(artifact) == before


def test_verifier_hard_compares_identity_contract_across_final_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(verify_mod, "DATA_DIR", tmp_path)
    run_mod.chay_run(_args("identity"))
    artifact = tmp_path / "identity"

    clean = verify_mod.verify_run("identity", quick=True)
    assert clean.failed() is False, clean.render()
    assert _item(clean, "artifact_identity_contract")[0] is True
    assert _item(clean, "journal_checkpoint_identity_contract")[0] is True
    assert clean.artifact_status == verify_mod.PENDING

    meta_path = artifact / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["identity_contract"]["execution"]["temperature"] = {"tampered": 1}
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    tampered = verify_mod.verify_run("identity", quick=True)
    check = _item(tampered, "artifact_identity_contract")
    assert check is not None and check[0] is False
    assert tampered.artifact_status == verify_mod.DIAGNOSTIC_ONLY
    assert tampered.ma_thoat() == verify_mod.EXIT_THIEU_BANG_CHUNG


def test_runtime_source_identity_includes_runtime_customizers_but_excludes_artifact_trees(tmp_path):
    """Inventory is Git-independent and includes Python's root runtime customizer hooks only."""
    (tmp_path / "engine").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "run.py").write_text("x = 1\n", encoding="utf-8")
    # Python may import these conventional root modules before application code; they are
    # executable runtime law, unlike arbitrary root-level Python files.
    (tmp_path / "sitecustomize.py").write_text("SITE = 1\n", encoding="utf-8")
    (tmp_path / "usercustomize.py").write_text("USER = 1\n", encoding="utf-8")
    (tmp_path / "engine" / "untracked_runtime.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "tests" / "test_hidden.py").write_text("z = 3\n", encoding="utf-8")
    (tmp_path / "docs" / "example.py").write_text("z = 4\n", encoding="utf-8")
    (tmp_path / "data" / "artifact.py").write_text("z = 5\n", encoding="utf-8")
    # A non-Python secret must be neither traversed as source nor parsed.
    (tmp_path / ".env").write_bytes(b"NOT_A_PYTHON_SECRET=\xff\x00")

    first = runtime_source_identity(tmp_path)
    assert [row["path"] for row in first["files"]] == [
        "engine/untracked_runtime.py", "run.py", "sitecustomize.py", "usercustomize.py",
    ]
    assert first["version"] == 1
    assert len(first["sha256"]) == 64

    # The second file is deliberately untracked: no Git operation is involved in this test.
    (tmp_path / "engine" / "untracked_later.py").write_text("later = True\n", encoding="utf-8")
    second = runtime_source_identity(tmp_path)
    assert second["sha256"] != first["sha256"]
    assert [row["path"] for row in second["files"]][-1] == "usercustomize.py"
    assert "engine/untracked_later.py" in [row["path"] for row in second["files"]]


def test_runtime_source_identity_propagates_and_fails_closed_resume_replay_verify(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(verify_mod, "DATA_DIR", tmp_path)
    run_mod.chay_run(_args("runtime_identity"))
    artifact = tmp_path / "runtime_identity"
    manifest_path = artifact / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = runtime_source_identity()
    assert manifest["reproducibility"]["runtime_source_identity"] == expected
    assert manifest["identity_contract"]["execution"]["runtime_source_identity"] == expected
    assert RunJournals.doc_manifest(artifact).identity.runtime_source_identity == expected

    # Replay and verification reject a self-consistent manifest whose recorded executable source
    # differs from the current tree; no provider or network path is involved.
    forged = json.loads(json.dumps(expected))
    forged["sha256"] = "0" * 64
    manifest["reproducibility"]["runtime_source_identity"] = forged
    write_manifest(artifact, manifest)
    replay_ok, detail = _kiem_identity(manifest, load_config())
    assert replay_ok is False
    assert detail["runtime_source_identity"] == [forged, expected]
    monkeypatch.setattr(replay_mod, "DATA_DIR", tmp_path)
    assert replay_mod.main(["runtime_identity"]) == 1
    verified = verify_mod.verify_run("runtime_identity", quick=True)
    check = _item(verified, "runtime_source_identity_current")
    assert check is not None and check[0] is False
    assert verified.artifact_status == verify_mod.VERSION_MISMATCH

    # Restore the experiment manifest; then corrupt only journal identity.  Resume must stop
    # before journal truncation/mutation because journal and manifest no longer prove one source.
    manifest["reproducibility"]["runtime_source_identity"] = expected
    write_manifest(artifact, manifest)
    journal_path = artifact / "checkpoints" / "journal_manifest.json"
    journal_data = json.loads(journal_path.read_text(encoding="utf-8"))
    journal_data["identity"]["runtime_source_identity"] = forged
    journal_path.write_text(json.dumps(journal_data, ensure_ascii=False), encoding="utf-8")
    before = _fingerprints(artifact)
    resume = _args("runtime_identity")
    resume.resume = True
    with pytest.raises(SystemExit, match="E-JM-12"):
        run_mod.chay_run(resume)
    assert _fingerprints(artifact) == before


def test_verifier_binds_outer_meta_execution_before_selecting_replay_branch(tmp_path, monkeypatch):
    """Mutable run_meta cannot turn a manifest-rulebot artifact into a real replay branch."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(verify_mod, "DATA_DIR", tmp_path)
    run_mod.chay_run(_args("outer_projection"))
    artifact = tmp_path / "outer_projection"
    meta_path = artifact / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update({
        "mode": "real",
        "policy": {"name": "tampered"},
        "model_snapshot": ["tampered/model"],
        "temperature": {"tampered": 1},
    })
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    result = verify_mod.verify_run("outer_projection", quick=False)
    projection = _item(result, "run_meta_execution_projection")
    assert projection is not None and projection[0] is False and projection[2] is True
    assert all(field in projection[1] for field in ("mode", "policy", "model_snapshot", "temperature"))
    # The verifier branches from the bound manifest mode, so it still runs the rulebot seed replay
    # rather than accepting the mutable outer mode as a real/transcript branch.
    replay = _item(result, "replay_world_hash")
    assert replay is not None and replay[0] is True, result.render()
    assert result.artifact_status == verify_mod.DIAGNOSTIC_ONLY
    assert result.ma_thoat() == verify_mod.EXIT_THIEU_BANG_CHUNG


def test_legacy_manifest_missing_schema3_runtime_identity_is_diagnostic_only(tmp_path, monkeypatch):
    """Unknown executable law is legacy evidence, not a current-code version mismatch."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(verify_mod, "DATA_DIR", tmp_path)
    run_mod.chay_run(_args("legacy_manifest"))
    artifact = tmp_path / "legacy_manifest"
    manifest_path = artifact / "experiment_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest["reproducibility"].pop("runtime_source_identity")
    write_manifest(artifact, manifest)

    result = verify_mod.verify_run("legacy_manifest", quick=True)
    legacy = _item(result, "schema3_runtime_identity")
    assert legacy is not None and legacy[0] is False and legacy[2] is True
    assert result.artifact_status == verify_mod.DIAGNOSTIC_ONLY
    assert result.artifact_status != verify_mod.VERSION_MISMATCH


def test_final_checkpoint_rejects_unsupported_journal_schema_and_missing_runtime_identity(
    tmp_path, monkeypatch
):
    """Final checkpoint evidence is invalid without its own supported source provenance."""
    monkeypatch.setattr(run_mod, "DATA_DIR", tmp_path)
    run_mod.chay_run(_args("journal_schema"))
    artifact = tmp_path / "journal_schema"
    meta = json.loads((artifact / "run_meta.json").read_text(encoding="utf-8"))
    journal_path = artifact / "checkpoints" / "journal_manifest.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["schema_version"] = "journal-legacy"
    journal_path.write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")

    kwargs = {
        "expected_run_name": "journal_schema",
        "expected_run_uuid": meta["run_uuid"],
        "expected_tick": meta["tick_cuoi"],
        "expected_world_hash": meta["world_hash"],
    }
    with pytest.raises(LoiJournal, match="E-JM-11.*schema không hỗ trợ"):
        RunJournals.verify_final_checkpoint(artifact, **kwargs)

    journal["schema_version"] = "journal-2"
    journal["identity"]["runtime_source_identity"] = None
    journal_path.write_text(json.dumps(journal, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LoiJournal, match="E-JM-12.*runtime_source_identity"):
        RunJournals.verify_final_checkpoint(artifact, **kwargs)
