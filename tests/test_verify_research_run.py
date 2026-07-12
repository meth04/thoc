"""Kiểm thử độc lập cho tools/verify_research_run — kiểm toán tái lập một run.

Test khách quan (không nới để hợp thức hóa): dựng run tối giản trong tmp_path và
monkeypatch DATA_DIR để KHÔNG đụng data/runs thật. Không mạng, không LLM, không API.
Một test replay end-to-end THẬT (rulebot vài tick) chứng minh world-hash tái lập TRÙNG,
cũng chạy hoàn toàn trong tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import tools.verify_research_run as vrr
from engine.config import load_config
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


def test_run_hop_le_du_bang_chung(tmp_path, monkeypatch):
    """Run có đầy đủ bằng chứng + quick → không FAIL, mọi hard-check PASS."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    _build_run(tmp_path / "r_ok")
    ket = vrr.verify_run("r_ok", quick=True)
    assert ket.failed() is False, ket.render()
    # không có hard-check nào FALSE
    assert not [n for n, ok, _, hard in ket.items if ok is False and hard]
    assert _item(ket, "metrics_contiguous_to_final")[0] is True
    assert _item(ket, "events_present")[0] is True


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


def test_config_digest_troi_chi_la_warn(tmp_path, monkeypatch):
    """Digest tái dựng lệch nhưng mọi hard-check khác pass → không FAIL (config_digest soft)."""
    monkeypatch.setattr(vrr, "DATA_DIR", tmp_path)
    # digest cố tình sai (ghi cùng vào manifest+meta để manifest_meta_consistent vẫn pass)
    _build_run(tmp_path / "r_drift", config_digest="0" * 64)
    ket = vrr.verify_run("r_drift", quick=True)
    ok, _, hard = _item(ket, "config_digest_reproduced")
    assert ok is False  # digest tái dựng KHÁC digest đã ghi
    assert hard is False  # nhưng đây chỉ là WARN provenance
    assert ket.failed() is False, ket.render()


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
    assert ket.failed() is False, ket.render()


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
    assert ket.failed() is False, ket.render()
