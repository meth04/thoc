"""CLI chạy mô phỏng THÓC.

Ví dụ:
  python run.py --mode rulebot --years 300 --seed 42 --run-name rb300
  python run.py --mode rulebot --ticks 100 --seed 42 --run-name t100 --resume

Resume (ADR 0006 §C): checkpoint tick N chỉ hợp lệ khi MỌI journal cũng được đưa về đúng
trạng thái tick N. Điểm cắt duy nhất hợp lệ là byte-offset ghi TẠI checkpoint (sau
flush+fsync) — xem ``engine/journal.py``. Sai lệch bất kỳ ⇒ **fail-closed**, không có nhánh
"bỏ qua cho chạy".
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from typing import Any

from engine.config import load_config
from engine.events import EventLog
from engine.journal import JournalIdentity, LoiJournal, RunJournals
from engine.tick import chay_mot_tick
from engine.world import World, tao_the_gioi

DATA_DIR = Path(__file__).resolve().parent / "data" / "runs"


def lay_mind_fn(mode: str, w: World, args: argparse.Namespace):
    if mode == "rulebot":
        from minds.policies import tao_policy

        # policy Lớp-4 thay thế được (ADR 0002); mặc định "rulebot" = baseline cũ.
        return tao_policy(getattr(args, "policy", "rulebot"))
    if mode == "mock":
        from minds.orchestrator import tao_mind_mock

        run_dir = DATA_DIR / (args.run_name or f"mock_{args.seed}")
        # transcript mock chỉ bật khi --transcript (dùng để test replay-from-transcript)
        tp = run_dir / "transcript.jsonl" if args.transcript else None
        return tao_mind_mock(w, fast=args.fast, run_dir=run_dir,
                             p_malformed=args.p_malformed, transcript_path=tp)
    if mode == "real":
        from minds.keypool import nap_env
        from minds.real import tao_mind_real

        env = nap_env(Path(__file__).resolve().parent / ".env")
        if env.llm_mode != "real" or not args.i_am_sure:
            raise SystemExit(
                "Mode real yêu cầu ĐỒNG THỜI LLM_MODE=real trong .env VÀ cờ --i-am-sure."
            )
        if not env.co_key_that():
            raise SystemExit("PENDING KEYS — chưa có key thật trong .env.")
        run_dir = DATA_DIR / (args.run_name or f"real_{args.seed}")
        run_dir.mkdir(parents=True, exist_ok=True)
        # real LUÔN ghi transcript (cổng reproducibility: replay real không mạng)
        return tao_mind_real(w, run_dir, w.cfg, env,
                             quota_db=DATA_DIR / "quota_counters.sqlite",
                             transcript_path=run_dir / "transcript.jsonl")
    raise SystemExit(f"Mode không hỗ trợ: {mode}")


def _treatments_tu_config(cfg, permute_personas: bool) -> list[str]:
    """Suy danh sách treatment ĐANG BẬT từ config đã merge — không hardcode theo scenario.

    Manifest cũ ghi ``treatments: []`` dù 3 survival floor + settlement đang bật (review
    v5 C4). Nhãn ở đây nghĩa là "cờ config của lớp treatment đó đang bật trong run này".
    Gate v6/v7 được kiểm tra theo đúng contract thực thi; absence phải giữ manifest legacy.
    """
    bang = (
        ("minds.san_an_toi_thieu.bat", "survival_floor_food"),
        ("minds.san_cho_o_toi_thieu.bat", "survival_floor_shelter"),
        ("khong_gian.dat_o.bat", "settlement_entry_v5"),
        ("minds.llm_tick.bat", "llm_autonomy_v4"),
    )
    ket = ["permute_personas"] if permute_personas else []
    for khoa, nhan in bang:
        if bool(cfg.get(khoa, False)):
            ket.append(nhan)
    if bool(cfg.get("khong_gian.phan_bo_ruong_cong.bat", False)):
        # nhãn mang cơ chế thật đang cấu hình (lottery_seeded → common_land_lottery)
        co_che = str(cfg.get("khong_gian.phan_bo_ruong_cong.co_che", "lottery_seeded"))
        ket.append("common_land_lottery" if co_che == "lottery_seeded"
                   else f"common_land_{co_che}")

    # v6 changes demography only when this key is present; absent deliberately preserves
    # the legacy code path, RNG draw order, and pinned world hashes.
    sinh_san = cfg.get("nhan_khau.sinh_san", {})
    if isinstance(sinh_san, dict) and "thai_ky_tick" in sinh_san:
        ket.append("reproductive_timing_v6")
    if bool(cfg.get("minds.survival_feasibility.bat", False)):
        ket.append("survival_feasibility_v7")

    shelter = cfg.get("minds.san_cho_o_toi_thieu", {})
    if isinstance(shelter, dict) and bool(shelter.get("bat", False)) and shelter.get("phien_ban") == "v7":
        ket.append("shelter_floor_v7")

    schedule_v2 = cfg.get("hop_dong.gop_cong_lich", "") == "signing_tick_half_open_v2"
    if schedule_v2:
        ket.append("contract_schedule_v2")
    # Physical delivery is active only as the inseparable ADR 0009 schedule+delivery pair.
    if schedule_v2 and bool(cfg.get("hop_dong.tiep_can_vat_ly_v2", False)):
        ket.append("physical_contract_delivery_v2")
    return ket


def _repro_llm_meta(cfg, mode: str):
    """(prompt_template_hash, model_snapshot, temperature) cho manifest (P1)."""
    from tools.experiments import prompt_template_hash

    ph = prompt_template_hash()
    if mode == "mock":
        return ph, ["mock/personabot"], {"mock": None}
    models: list[str] = []
    temps: dict[str, Any] = {}
    for tier in ("T0", "T1", "T2", "T3", "T4"):
        for r in cfg.get(f"models.tiers.{tier}.routes") or []:
            m = f"{r['provider']}/{r['model']}"
            if m not in models:
                models.append(m)
        temps[tier] = cfg.get(f"models.tiers.{tier}.temperature", None)
    for nen in ("nen_hoi_ky", "chronicle"):
        c = cfg.get(f"models.{nen}") or {}
        if c:
            m = f"{c['provider']}/{c['model']}"
            if m not in models:
                models.append(m)
    return ph, models, temps


def chay_smoke(args) -> int:
    """--smoke: 1 call mỗi route (≤12 call) — bảng model | ok | tok | latency."""
    from minds.gateway import LLMRequest
    from minds.keypool import nap_env
    from minds.providers_real import GatewayReal, Route
    from minds.quota import QuotaCounter

    env = nap_env(Path(__file__).resolve().parent / ".env")
    # smoke (≤12 call) được PHASES.md Phase 5 cho phép khi có key thật + --i-am-sure;
    # run real ĐẦY ĐỦ (Phase 7+) vẫn yêu cầu thêm LLM_MODE=real trong .env.
    if not args.i_am_sure:
        raise SystemExit("Smoke cần cờ --i-am-sure.")
    if not env.co_key_that():
        print("PENDING KEYS — chưa có key thật trong .env; bỏ qua smoke, đi tiếp.")
        return 0
    cfg = load_config()
    quota = QuotaCounter(DATA_DIR / "quota_counters.sqlite",
                         reset_hour=int(cfg.get("quotas.chung.reset_hour_local")))
    gw = GatewayReal(cfg, env, quota)
    # Smoke sends only admitted generation requests below.  A separate /models
    # health probe would be an unlogged extra provider call and make the stated
    # ≤12 budget false, so reachability is reported by the generation rows.
    routes: list[tuple[str, Route]] = []
    for tier in ("T0", "T1", "T2", "T3", "T4"):
        for r in gw.routes_cua_tier(tier):
            routes.append((tier, r))
    for ten_nen in ("nen_hoi_ky", "chronicle"):
        nen = cfg.get(f"models.{ten_nen}")
        routes.append((ten_nen, gw.route_cau_hinh(nen["provider"], nen["model"])))
    print(f"{'route':<14} {'model':<36} {'ok':<4} {'tok i/o':<10} latency")
    so_call = 0
    for tier, route in routes[:12]:
        # JSON mode (PART 5.2): OpenAI json_object cần TOP-LEVEL OBJECT (không phải mảng)
        req = LLMRequest(prompt='Trả về đúng một JSON object: {"ok": true}', ctx={},
                         tier=tier if tier.startswith("T") else "T0", batch_ids=["smoke"])
        try:
            resp = gw._goi_route(req, route, cfg.get("models.tiers.T0"))
            so_call += 1
            print(f"{tier:<14} {route.model:<36} ok   {resp.tok_in}/{resp.tok_out:<7}"
                  f" {resp.latency_s:.2f}s")
        except Exception as e:  # noqa: BLE001 — smoke báo cáo mọi lỗi (đã che key)
            from minds.providers_real import che_key

            print(f"{tier:<14} {route.model:<36} LỖI  {type(e).__name__}: "
                  f"{che_key(str(e))[:160]}")
    print(f"[smoke] {so_call} call — xong.")
    return 0


def _nap_journal_resume(run_dir: Path, run_name: str, identity: JournalIdentity,
                        tick_ck: int, args) -> RunJournals:
    """Resume protocol (ADR 0006 §C.4) — FAIL-CLOSED, không mutate byte nào khi sai lệch.

    (i) đọc journal_manifest; (ii) verify prefix/offset/identity tại tick N;
    (iii) restore = truncate-with-quarantine; (iv) segment_id += 1.

    Thiếu manifest / prefix hash lệch / file ngắn hơn offset / prompt_template_hash khác ⇒
    ``SystemExit`` có mã lỗi. **Không có nhánh "bỏ qua cho chạy".** Escape hatch duy nhất là
    ``--recover-journal``, và nó hạ artifact xuống ``diagnostic_only_unreplayable`` VĨNH VIỄN.
    """
    try:
        journals = RunJournals.nap(run_dir)
        journals.restore(tick_ck, identity=identity)
        rec = journals.manifest.recoveries[-1]
        print(f"[recovery] cắt {rec.journals.get('events', {}).get('records_removed', 0)} event / "
              f"{rec.journals.get('transcript', {}).get('records_removed', 0)} transcript / "
              f"supersede {rec.journals.get('llm_calls', {}).get('rows_superseded', 0)} llm_call "
              f"sau tick {tick_ck}; bằng chứng giữ ở {rec.quarantine_dir}/")
        return journals
    except LoiJournal as e:
        if not args.recover_journal:
            raise SystemExit(
                f"{e}\n\nRUN DỪNG (fail-closed). Không byte nào bị sửa.\n"
                f"  1) chạy run mới (khuyến nghị — giữ artifact cũ nguyên vẹn); hoặc\n"
                f"  2) python run.py ... --resume --recover-journal  ⇒ QUARANTINE toàn bộ "
                f"journal, chạy tiếp từ tick {tick_ck}, artifact bị đánh dấu "
                f"diagnostic_only_unreplayable VĨNH VIỄN (không bao giờ qua cổng replay)."
            ) from e
        journals = RunJournals.doc_manifest(run_dir)
        if journals is None:
            js = RunJournals.tao_de_recover(run_dir, run_name=run_name, identity=identity,
                                            tick=tick_ck, ly_do=e.ma)
        else:
            js = RunJournals.nap(run_dir)
            js.recover_toan_bo(tick_ck, identity=identity, ly_do=e.ma)
        rec = js.manifest.recoveries[-1]
        print(f"[--recover-journal] {e.ma}: toàn bộ journal đã QUARANTINE vào "
              f"{rec.quarantine_dir}/. Artifact này VĨNH VIỄN là "
              f"diagnostic_only_unreplayable — nó KHÔNG qua được cổng replay.")
        return js


def _ghi_metrics(run_dir: Path, w) -> None:
    ticks = [int(m["tick"]) for m in w.metrics_lich_su]
    if ticks != list(range(1, len(ticks) + 1)):
        raise SystemExit(
            "[E-JM-10] World.metrics_lich_su không liên tục/duy nhất "
            f"(n={len(ticks)}, đầu={ticks[:3]}, cuối={ticks[-3:]}). Checkpoint hoặc resume "
            "đã làm hỏng lịch sử metric — KHÔNG ghi metrics.jsonl nửa vời."
        )
    with open(run_dir / "metrics.jsonl", "w", encoding="utf-8") as f:
        for m in w.metrics_lich_su:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")


def _tao_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="THÓC — mô phỏng 300 năm kinh tế tự phát")
    ap.add_argument("--mode", choices=["rulebot", "mock", "real"], default="rulebot")
    ap.add_argument("--years", type=int, default=None)
    ap.add_argument("--ticks", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--fast", action="store_true", help="tắt giả lập latency của mock")
    ap.add_argument("--transcript", action="store_true",
                    help="mock: ghi transcript.jsonl để replay-from-transcript (real luôn ghi)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--i-am-sure", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--until-budget", action="store_true")
    ap.add_argument("--p-malformed", type=float, default=None,
                    help="tỷ lệ mock cố tình trả JSON hỏng (mặc định theo models.yaml)")
    ap.add_argument("--scenario", default=None,
                    help="tên scenario trong scenarios/ (ghi scope + provenance vào manifest)")
    ap.add_argument("--config-overlay", action="append", default=[], metavar="YAML",
                    help="YAML ghi đè config; dùng cho scenario/phản chứng, không sửa config gốc")
    ap.add_argument("--permute-personas", action="store_true",
                    help="treatment phản chứng: hoán đổi persona giữa agent, giữ nguyên bản đồ/tài sản")
    ap.add_argument("--policy", default="rulebot",
                    help="tên BehaviorPolicy Lớp-4 (mode rulebot): rulebot | feasible_random | "
                         "subsistence | adaptive (ADR 0002)")
    ap.add_argument("--recover-journal", action="store_true",
                    help="escape hatch CÓ GIÁ (ADR 0006 §C.4): resume một run không có "
                         "journal_manifest hợp lệ. Toàn bộ journal hiện có bị QUARANTINE và "
                         "artifact bị hạ VĨNH VIỄN xuống diagnostic_only_unreplayable. "
                         "Nó KHÔNG BAO GIỜ làm một run xanh trở lại.")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _tao_parser().parse_args(argv)
    if args.smoke:
        return chay_smoke(args)
    return chay_run(args)


def _dong_journals(w, mind_fn) -> None:
    """Đóng MỌI writer journal (best-effort) — dùng trên đường crash.

    Không được raise: nó chạy trong ``except`` và không được che lỗi gốc.
    """
    for dong in (
        lambda: w.events.dong(),
        lambda: mind_fn.transcript.dong(),
        lambda: mind_fn.log.dong(),
    ):
        try:
            dong()
        except Exception:  # noqa: BLE001, S110 — best-effort; lỗi gốc quan trọng hơn
            pass


def _run_dir_occupied(run_dir: Path) -> bool:
    """A directory with any entry is an existing artifact, not a disposable output path."""
    return run_dir.exists() and any(run_dir.iterdir())


def _contract_run_execution(contract: dict[str, Any]) -> dict[str, Any]:
    """The fields that must agree before an interrupted artifact may resume."""
    return {
        "run": {key: contract.get("run", {}).get(key)
                for key in ("name", "mode", "seed", "ticks_requested")},
        "execution": contract.get("execution"),
    }


def _resume_manifest_or_stop(run_dir: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate a v2 artifact before any resume path is allowed to mutate its journals.

    A legacy/malformed directory remains a diagnostic artifact.  It is not upgraded by a
    resume attempt because no matching UUID can be proven.
    """
    from tools.experiments import (
        IDENTITY_CONTRACT_VERSION,
        MANIFEST_SCHEMA,
        manifest_identity_contract,
    )

    manifest_path = run_dir / "experiment_manifest.json"
    checkpoint_path = run_dir / "checkpoints" / "checkpoint_moi_nhat.json"
    if not manifest_path.exists() or not checkpoint_path.exists():
        raise SystemExit(
            "[E-RUN-ISO-02] --resume chỉ hợp lệ cho artifact có manifest và checkpoint. "
            "Directory hiện có được giữ nguyên như diagnostic artifact; hãy dùng run-name mới."
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        journals = RunJournals.doc_manifest(run_dir)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(
            "[E-RUN-ISO-03] Không đọc được identity của artifact hiện có; không resume và "
            "không sửa byte nào. Hãy dùng run-name mới."
        ) from exc

    if journals is None:
        raise SystemExit(
            "[E-JM-01] thiếu checkpoints/journal_manifest.json; không resume và không mutate "
            "artifact legacy/không chứng minh được UUID."
        )
    stored = manifest.get("identity_contract")
    expected = manifest_identity_contract(manifest)
    schema_ok = manifest.get("schema_version") == MANIFEST_SCHEMA
    contract_ok = (isinstance(stored, dict)
                   and stored.get("contract_version") == IDENTITY_CONTRACT_VERSION
                   and stored == expected)
    candidate_contract = manifest_identity_contract(candidate)
    candidate_ok = _contract_run_execution(stored if isinstance(stored, dict) else {}) == \
        _contract_run_execution(candidate_contract)
    run_uuid = expected.get("run", {}).get("run_uuid")
    execution = expected.get("execution", {})
    journal_ok = (
        journals.run_uuid == run_uuid
        and journals.identity.config_sha256 == execution.get("config_sha256")
        and journals.identity.prompt_template_hash == execution.get("prompt_template_hash")
        and journals.identity.capability_catalog_hash == execution.get("capability_catalog_hash")
        and journals.identity.runtime_source_identity == execution.get("runtime_source_identity")
        and journals.identity.git_revision == execution.get("git_revision")
    )
    if journals.identity.config_sha256 != execution.get("config_sha256"):
        raise SystemExit("[E-JM-03] config_sha256 của journal không khớp manifest identity.")
    if journals.identity.prompt_template_hash != execution.get("prompt_template_hash"):
        raise SystemExit("[E-JM-04] prompt_template_hash của journal không khớp manifest identity.")
    if journals.identity.capability_catalog_hash != execution.get("capability_catalog_hash"):
        raise SystemExit(
            "[E-JM-05] capability_catalog_hash của journal không khớp manifest identity."
        )
    if journals.identity.runtime_source_identity != execution.get("runtime_source_identity"):
        raise SystemExit(
            "[E-JM-12] runtime_source_identity của journal không khớp manifest identity."
        )
    checkpoint_contract = checkpoint.get("identity_contract")
    checkpoint_ok = (
        isinstance(checkpoint_contract, dict)
        and checkpoint_contract.get("run") == expected.get("run")
        and checkpoint_contract.get("execution") == execution
        and checkpoint.get("run_uuid") == run_uuid
        and checkpoint.get("segment_id") == journals.segment_id
    )
    if not (schema_ok and contract_ok and candidate_ok and run_uuid and journal_ok and checkpoint_ok):
        raise SystemExit(
            "[E-RUN-ISO-04] Resume identity không chứng minh được cùng run UUID/configuration/"
            "segment. Artifact hiện có giữ nguyên diagnostic/non-green; hãy dùng run-name mới."
        )
    return manifest


def _checkpoint_with_identity(journals: RunJournals, w: World, manifest: dict[str, Any],
                              terminal_reason: str | None = None) -> None:
    """Checkpoint journal first, then atomically attach its matching artifact contract."""
    from tools.experiments import manifest_identity_contract, write_checkpoint_identity

    outcome = {
        "tick_final": w.tick,
        "world_hash": w.world_hash(),
        "segment_id": journals.manifest.segment_id,
        "terminal_reason": terminal_reason,
    }
    checkpoint_manifest = dict(manifest)
    checkpoint_manifest["outcome"] = outcome
    contract = manifest_identity_contract(checkpoint_manifest)
    journals.checkpoint(w)
    write_checkpoint_identity(journals.ck_dir / "checkpoint_moi_nhat.json", contract)


def chay_run(args, *, mind_factory=None) -> int:
    """Thân run — seam để test resume trong-process (không subprocess/kill, bất định trên
    Windows). ``mind_factory(mode, w, args) -> mind_fn``; mặc định ``lay_mind_fn``."""
    mind_factory = mind_factory or lay_mind_fn
    run_name = args.run_name or f"{args.mode}_{args.seed}"
    run_dir = DATA_DIR / run_name
    occupied = _run_dir_occupied(run_dir)
    if occupied and not args.resume:
        raise SystemExit(
            "[E-RUN-ISO-01] Run directory đã có artifact; non-resume bị từ chối để không ghi đè "
            "manifest/meta/metrics/reports. Dùng --run-name mới, hoặc --resume chỉ khi cùng run UUID."
        )
    if occupied and args.resume and not (run_dir / "checkpoints" / "checkpoint_moi_nhat.json").exists():
        raise SystemExit(
            "[E-RUN-ISO-02] --resume không có checkpoint hợp lệ trong directory đã có artifact; "
            "không tạo run mới chồng lên artifact cũ."
        )
    ck_dir = run_dir / "checkpoints"
    events_path = run_dir / "events.jsonl"

    overlays = [Path(p).resolve() for p in args.config_overlay]
    if args.scenario:
        from tools.experiments import scenario_overlay

        scenario_params = scenario_overlay(args.scenario)
        if scenario_params is not None:
            overlays.insert(0, scenario_params.resolve())
    cfg = load_config(overlays=overlays)
    tick_moi_nam = int(round(12.0 / float(cfg.get("thoi_gian.thang_moi_tick"))))
    if tick_moi_nam < 1 or abs(tick_moi_nam * float(cfg.get("thoi_gian.thang_moi_tick")) - 12.0) > 1e-9:
        raise SystemExit("thoi_gian.thang_moi_tick phải chia tròn 12")
    tong_tick = args.ticks if args.ticks is not None else (args.years or 300) * tick_moi_nam
    from tools.experiments import (
        build_manifest,
        manifest_identity_contract,
        refresh_manifest_identity_contract,
        update_manifest_outcome,
        write_manifest,
    )

    # policy Lớp-4 chỉ áp cho mode rulebot; mock/real dùng LLM làm hành vi (ghi None).
    policy_meta = None
    if args.mode == "rulebot":
        from minds.policies import tao_policy

        pol = tao_policy(args.policy)
        policy_meta = {"name": pol.name, "version": pol.version, "params": dict(pol.params)}
    prompt_template_hash = model_snapshot = temperature = None
    if args.mode in ("mock", "real"):
        prompt_template_hash, model_snapshot, temperature = _repro_llm_meta(cfg, args.mode)
    # Catalog hash (ADR 0006 §A.2) ghi cho MỌI mode: rulebot cũng phát intent qua cùng bộ
    # action, nên tập action hợp lệ là một phần của identity run, không riêng của nhánh LLM.
    from minds.capabilities import catalog_hash

    manifest = build_manifest(
        run_name=run_name, mode=args.mode, seed=args.seed, ticks_requested=tong_tick,
        config_digest=cfg.digest(), config_overlays=overlays, scenario=args.scenario,
        treatments=_treatments_tu_config(cfg, args.permute_personas),
        policy=policy_meta, prompt_template_hash=prompt_template_hash,
        capability_catalog_hash=catalog_hash(),
        model_snapshot=model_snapshot, temperature=temperature,
        calendar={
            "months_per_tick": float(cfg.get("thoi_gian.thang_moi_tick")),
            "ticks_per_year": tick_moi_nam,
            "seasons": cfg.raw().get("thoi_gian", {}).get("lich_mua"),
        },
    )
    from tools.experiments import git_revision

    # ADR 0006 §C.2: identity của segment có BỐN trường. `capability_catalog_hash` là trường
    # THỨ BA và nó KHÔNG suy ra được từ `prompt_template_hash`: menu hành động/asset/
    # LOAI_HANH_DONG sống ở `minds/capabilities.py`, còn prompt hash băm `minds/prompts.py`.
    # Thiếu nó ⇒ đổi tập action giữa hai segment mà resume vẫn xanh (A-06/F-P03-1).
    runtime_identity = manifest["reproducibility"]["runtime_source_identity"]
    identity = JournalIdentity(config_sha256=cfg.digest(),
                               prompt_template_hash=prompt_template_hash,
                               capability_catalog_hash=catalog_hash(),
                               runtime_source_identity=runtime_identity,
                               git_revision=git_revision())

    ck_moi_nhat = ck_dir / "checkpoint_moi_nhat.json"
    if args.recover_journal:
        # Recovery intentionally changes bytes and cannot prove the original UUID/prefix.  It is
        # not an output-isolation exception; legacy artifacts remain readable diagnostic evidence.
        raise SystemExit(
            "--recover-journal không được phép trong artifact contract v2: nó không chứng minh "
            "matching run UUID và sẽ mutate artifact cũ. Dùng run-name mới."
        )
    if args.resume and ck_moi_nhat.exists():
        manifest = _resume_manifest_or_stop(run_dir, manifest)
        meta = json.loads(ck_moi_nhat.read_text(encoding="utf-8"))
        tick_ck = int(meta["tick"])
        journals = _nap_journal_resume(run_dir, run_name, identity, tick_ck, args)
        counters = journals.counters()
        # events phải được truncate XONG rồi mới mở handle "a" (offset đúng của segment mới)
        w = World.nap_checkpoint(ck_dir / f"checkpoint_{tick_ck:04d}.pkl", None, cfg=cfg)
        w.events = EventLog(events_path, start_seq=counters["events"],
                            segment_id=journals.manifest.segment_id)
        print(f"[resume] từ tick {w.tick} (hash {meta['world_hash'][:12]}) "
              f"segment {journals.manifest.segment_id} · event seq tiếp {counters['events'] + 1}")
    else:
        if args.resume:
            print("[resume] directory trống — chạy mới từ tick 0.")
        journals = RunJournals.moi(run_dir, run_name=run_name, identity=identity)
        counters = journals.counters()
        manifest["run"]["run_uuid"] = journals.manifest.run_uuid
        refresh_manifest_identity_contract(manifest)
        write_manifest(run_dir, manifest)
        w = tao_the_gioi(cfg, args.seed, events_path)
        if args.permute_personas:
            from tools.experiments import permute_personas

            permute_personas(w)
    w.unrecognized_path = run_dir / "unrecognized_intents.jsonl"

    mind_fn = mind_factory(args.mode, w, args)
    seg = journals.manifest.segment_id
    tr = getattr(mind_fn, "transcript", None)
    if tr is not None:
        tr.rebase(start_call_id=counters["transcript"],
                  run_uuid=journals.manifest.run_uuid, segment_id=seg)
    log = getattr(mind_fn, "log", None)
    if log is not None and hasattr(log, "dat_segment"):
        log.dat_segment(seg)
    journals.gan_writers(events=w.events, transcript=tr, llm_log=log)
    tong_thua = len(w.parcels)
    ck_moi_n = int(cfg.get("minds.checkpoint_moi_n_tick"))

    ngat = {"flag": False}

    def bat_sigint(_sig, _frm):
        ngat["flag"] = True
        print("\n[SIGINT] sẽ checkpoint sạch rồi dừng...")

    signal.signal(signal.SIGINT, bat_sigint)

    t0 = time.time()
    ly_do_ket_thuc: str | None = None
    try:
        while w.tick < tong_tick and not ngat["flag"]:
            # Full-autonomy treatment may require all living adults to receive
            # a mandatory first LLM request.  Check its RPM feasibility before
            # advancing world time: a failed check must not leave behind a
            # policy-card half-tick masquerading as an LLM experiment.
            kiem_tra_truoc_tick = getattr(mind_fn, "kiem_tra_truoc_tick", None)
            if callable(kiem_tra_truoc_tick) and not kiem_tra_truoc_tick(w):
                ly_do_ket_thuc = "llm_provider_budget_exhausted"
                print(f"[budget] preflight không đủ: {getattr(mind_fn, 'ly_do_dung', '')} "
                      "— chưa tiến world tick, checkpoint và dừng êm (không degrade).")
                break
            m = chay_mot_tick(w, mind_fn, tong_thua)
            # telemetry LLM theo tick vào metrics.jsonl (m là chính dict đã lưu lịch sử)
            st = getattr(mind_fn, "stats_tick", None)
            if st:
                m["llm"] = {k: st.get(k, 0) for k in
                            ("call", "logical_task", "api_call", "api_call_cap",
                             "api_call_denied", "api_call_by_kind", "api_call_by_agent",
                             "api_call_min_required", "api_call_min_met",
                             "api_call_min_exception", "api_call_min_violations",
                             "api_call_scope", "api_call_min_moi_agent",
                             "api_call_cap_moi_agent", "tok_in", "tok_out", "fallback",
                             "latency_ms", "scheduled_agent_decision",
                             "completed_agent_decision_turn", "parsed_agent_decision",
                             "terminal_reason_counts", "exact_one_terminal_decision",
                             "http_attempt_accounting")}
            if getattr(mind_fn, "het_ngan_sach", False):
                ly_do_ket_thuc = "llm_provider_budget_exhausted"
                print(f"[budget] hết ngân sách: {getattr(mind_fn, 'ly_do_dung', '')} "
                      f"— checkpoint và dừng êm (không degrade).")
                break
            if not any(agent.con_song for agent in w.agents.values()):
                # An empty world has no economic actor.  Continuing to emit
                # zero-valued ticks (and trying to satisfy a synthetic minimum
                # LLM call) turns extinction into misleading pseudo-data.
                ly_do_ket_thuc = "population_extinct"
                print("[terminal] không còn người sống — kết thúc run tại tick hiện tại.")
                break
            if w.tick % ck_moi_n == 0:
                # THỨ TỰ BẮT BUỘC (cũ: luu_checkpoint RỒI MỚI flush ⇒ offset ghi trước flush
                # ⇒ SAI): flush+fsync journal → capture offset → pickle → manifest → con trỏ.
                _checkpoint_with_identity(journals, w, manifest)
            buoc_in = 5 if args.mode == "real" else 50
            if w.tick % buoc_in == 0 or w.tick == tong_tick:
                gini_dat = m.get("gini_dat")
                gini_dat_text = f"{gini_dat:.2f}" if gini_dat is not None else "N/A"
                print(
                    f"tick {w.tick:4d} (năm {m['nam']:3d}) | dân {m['dan_so']:4d} | "
                    f"thóc/người {m['thoc_moi_nguoi']:7.1f} | gini đất {gini_dat_text} | "
                    f"biết chữ {m['ty_le_biet_chu']:.0%} | {time.time() - t0:6.1f}s"
                )
    except BaseException:
        # Crash giữa run: ĐÓNG writer trước khi thoát. Một process bị kill thật thì OS đóng fd
        # hộ, nhưng một exception bắt được ở tầng trên (driver script, test seam, notebook) để
        # writer SỐNG SÓT với buffer chưa flush. Nếu sau đó `--resume` truncate journal về
        # checkpoint, writer cũ vẫn có thể flush buffer của nó vào file VỪA BỊ CẮT ⇒ **hồi sinh
        # bản ghi mồ côi SAU dữ liệu của segment mới** (đo được: 60 seq trùng + 1 tick lùi).
        # Đóng ở đây làm ngữ nghĩa in-process khớp ngữ nghĩa process-chết.
        _dong_journals(w, mind_fn)
        raise

    _checkpoint_with_identity(journals, w, manifest, terminal_reason=ly_do_ket_thuc)
    journals.ket_thuc(w.tick)
    w.events.dong()
    # metrics.jsonl là journal DẪN XUẤT (Class B): ghi đè cuối run từ World.metrics_lich_su
    # (nằm trong pickle) ⇒ resume KHÔNG tạo dup, không cần truncate. Nhưng phải kiểm chứng
    # chứ không tin: tick duy nhất + liên tục 1..M, nếu không thì fail-closed.
    _ghi_metrics(run_dir, w)
    meta = {
        "run_name": run_name,
        "mode": args.mode,
        "seed": args.seed,
        "tick_cuoi": w.tick,
        "world_hash": w.world_hash(),
        "thoi_gian_s": round(time.time() - t0, 1),
        "config_sha256": cfg.digest(),
        "scenario": args.scenario,
        "policy": policy_meta,
        "run_uuid": journals.manifest.run_uuid,
        "segment_id": journals.manifest.segment_id,
        "replay_complete": journals.manifest.replay_complete,
        "terminal_reason": ly_do_ket_thuc,
    }
    if args.mode in ("mock", "real"):
        # ``p_malformed`` là treatment adversarial riêng của Mock; real không có tỷ lệ
        # JSON hỏng ngoại sinh nên không được in một số 0 gây hiểu sai.
        if args.mode == "mock":
            meta["p_malformed"] = mind_fn.p_malformed
        # Các bộ đếm trên mind chỉ thuộc *phiên process hiện tại*. Run có thể resume
        # nhiều lần, nên số liệu công bố phải lấy từ llm_calls.sqlite append-only.
        meta["so_call_phien"] = mind_fn.so_call
        meta["so_luot_nghi_phien"] = mind_fn.so_nghi
        meta["so_fallback_phien"] = mind_fn.so_fallback
        meta["het_ngan_sach"] = bool(getattr(mind_fn, "het_ngan_sach", False))
        meta["tok_in_phien"] = int(getattr(mind_fn, "tok_in", 0))
        meta["tok_out_phien"] = int(getattr(mind_fn, "tok_out", 0))
        meta["tool_turns_phien"] = int(getattr(mind_fn, "so_luot_cong_cu", 0))
        meta["so_api_call_phien"] = int(getattr(mind_fn, "so_api_call", 0))
        meta["so_api_call_bi_tu_choi_phien"] = int(
            getattr(mind_fn, "so_api_call_bi_tu_choi", 0)
        )
        meta["cho_burst_preflight_s_phien"] = round(
            float(getattr(mind_fn, "so_cho_burst_preflight_s", 0.0)), 3
        )
        if ly_do_ket_thuc == "llm_provider_budget_exhausted":
            meta["llm_preflight_ly_do"] = str(getattr(mind_fn, "ly_do_dung", ""))
        meta["concurrency"] = int(getattr(mind_fn, "concurrency", 0))
        mind_fn.log.dong()
        if getattr(mind_fn, "transcript", None) is not None:
            mind_fn.transcript.dong()
        # telemetry LLM chi tiết từ llm_calls.sqlite → reports/telemetry.{md,json}
        from tools.telemetry import sinh_bao_cao
        tele = sinh_bao_cao(run_dir, cfg.get("models.gia_token"))
        # ADR 0006 §C.1: hai đại lượng KHÁC NHAU. `so_call` (quỹ đạo) là số đi vào bảng kết
        # quả; `so_call_billed` (mọi row, gồm cả segment bị bỏ) là chi phí ĐÃ TRẢ THẬT — không
        # được làm đẹp bằng cách xóa row.
        meta["so_call"] = int(tele.get("call_effective", tele.get("tong_call", 0)))
        meta["so_call_billed"] = int(tele.get("call_burned", tele.get("tong_call", 0)))
        meta["so_call_superseded"] = int(tele.get("call_superseded", 0))
        meta["so_fallback"] = int(tele.get("fallback_effective", tele.get("fallback", 0)))
        meta["fallback_rate"] = float(
            tele.get("fallback_rate_effective", tele.get("fallback_rate", 0.0)))
        meta["tok_in"] = int(tele.get("tok_in", 0))
        meta["tok_out"] = int(tele.get("tok_out", 0))
        meta["provider_retries"] = int(tele.get("provider_retries", 0))
        meta["json_repair_retries"] = int(tele.get("json_repair_retries", 0))
        meta["tool_turns"] = int(tele.get("tool_turns", 0))
        meta["chi_phi_usd_uoc_tinh"] = tele.get("chi_phi_usd", 0.0)
        decision_fallback = tele.get("fallback_decision_level", {})
        if isinstance(decision_fallback, dict) and decision_fallback.get("ap_dung"):
            meta["fallback_decision_level"] = decision_fallback
        terminal = tele.get("terminal_decision_coverage", {})
        if isinstance(terminal, dict) and terminal.get("ap_dung"):
            meta["terminal_decision_coverage"] = terminal
        attempts = tele.get("attempts", {})
        if isinstance(attempts, dict) and attempts.get("ap_dung"):
            meta["http_attempts"] = attempts
        autonomy = tele.get("ngan_sach_tick", {})
        if isinstance(autonomy, dict) and autonomy.get("ap_dung"):
            meta["llm_request_total"] = int(autonomy.get("request_total", 0))
            meta["llm_autonomy_budget"] = {
                "scope": autonomy.get("scope"),
                "agent_tick": int(autonomy.get("agent_tick", 0)),
                "request_moi_tick": autonomy.get("request_moi_tick", {}),
                "dat": bool(autonomy.get("dat", False)),
                "vi_pham_san": len(autonomy.get("vi_pham_san", [])),
                "vi_pham_tran": len(autonomy.get("vi_pham_tran", [])),
                "vi_pham_batch": len(autonomy.get("vi_pham_batch", [])),
            }
        print(f"[{args.mode}] call tổng={meta['so_call']} (phiên này {meta['so_call_phien']}) "
              f"nghĩ phiên={meta['so_luot_nghi_phien']} "
              f"fallback={meta['so_fallback']} ({meta['fallback_rate']:.2%}) | "
              f"token {meta['tok_in'] + meta['tok_out']:,} ~${tele.get('chi_phi_usd', 0):.4f}")
    outcome = {
        "tick_final": w.tick,
        "world_hash": meta["world_hash"],
        "elapsed_seconds": meta["thoi_gian_s"],
        "stopped_for_budget": bool(getattr(mind_fn, "het_ngan_sach", False)),
        "segment_id": journals.manifest.segment_id,
        "terminal_reason": ly_do_ket_thuc,
    }
    manifest = update_manifest_outcome(run_dir, outcome)
    contract = manifest_identity_contract(manifest)
    execution = contract["execution"]
    meta.update({
        "ticks_requested": contract["run"]["ticks_requested"],
        "prompt_template_hash": execution["prompt_template_hash"],
        "capability_catalog_hash": execution["capability_catalog_hash"],
        "runtime_source_identity": execution["runtime_source_identity"],
        "model_snapshot": execution["model_snapshot"],
        "temperature": execution["temperature"],
        "git_revision": execution["git_revision"],
        "identity_contract": contract,
    })
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    viet_session_report(run_dir, w, meta)
    print(f"[xong] tick {w.tick} | hash {meta['world_hash'][:16]} | {meta['thoi_gian_s']}s")
    return 0


def viet_session_report(run_dir: Path, w, meta: dict) -> None:
    """reports/session_<n>.md — tóm tắt phiên (SPEC 11)."""
    rp_dir = run_dir / "reports"
    rp_dir.mkdir(exist_ok=True)
    n = len(list(rp_dir.glob("session_*.md"))) + 1
    m = w.metrics_lich_su[-1] if w.metrics_lich_su else {}
    gini_dat = m.get("gini_dat")
    n_dat = m.get("n_thua_tu_huu", 0)
    gini_dat_text = (
        f"{gini_dat} (n={n_dat} thửa tư hữu)" if gini_dat is not None
        else f"không xác định (n={n_dat} thửa tư hữu)"
    )
    gdp_coverage = m.get("gdp_price_coverage", {})
    gdp_text = f"GDP {m.get('gdp', '?')}"
    if isinstance(gdp_coverage, dict):
        gdp_text += (f"; price coverage {gdp_coverage.get('priced_components', 0)}/"
                     f"{gdp_coverage.get('components', 0)} components")
    dong = [
        f"# Phiên {n} — run `{meta['run_name']}` (mode {meta['mode']}, seed {meta['seed']})",
        "",
        f"- Tick cuối: {meta['tick_cuoi']} (năm {w.nam()}); "
        f"thời gian chạy {meta['thoi_gian_s']}s; world-hash `{meta['world_hash'][:16]}`",
        f"- Dân số {m.get('dan_so', '?')} · biết chữ {m.get('ty_le_biet_chu', 0):.0%} · "
        f"gini đất {gini_dat_text} · tri thức {m.get('tri_thuc', 0)}",
        f"- {gdp_text} (đầu ra/đầu vào chưa có giá không được diễn giải là giá trị 0).",
        f"- Entity {m.get('so_entity', 0)} · máy {m.get('so_may', 0)} · "
        f"blueprint {m.get('so_blueprint', 0)} · hợp đồng hiệu lực {m.get('hd_hieu_luc', 0)}",
        f"- Nhãn định chế: {m.get('nhan_dinh_che', {})} · "
        f"công nghiệp hóa: {m.get('cong_nghiep_hoa', False)}",
    ]
    if "fallback_rate" in meta:
        malformed = (
            f"; mock p_malformed={meta['p_malformed']}" if meta.get("mode") == "mock"
            and "p_malformed" in meta else ""
        )
        dong.append(
            f"- LLM call-level: {meta['so_call']} call tích lũy trong log; "
            f"phiên này {meta.get('so_luot_nghi_phien', meta.get('so_luot_nghi', 0))} lượt nghĩ; "
            f"fallback {meta['fallback_rate']:.2%}{malformed}"
        )
    decision_fallback = meta.get("fallback_decision_level")
    if isinstance(decision_fallback, dict):
        dong.append(
            f"- LLM decision-level fallback: {decision_fallback.get('rate', 0.0):.2%} "
            f"({decision_fallback.get('fallback_plans', 0)}/"
            f"{decision_fallback.get('agent_tick_nghi', 0)} agent-tick nghĩ)."
        )
    terminal = meta.get("terminal_decision_coverage")
    if isinstance(terminal, dict):
        terminal_rate = terminal.get("terminal_coverage")
        parsed_rate = terminal.get("parsed_decision_coverage")
        dong.append(
            "- Terminal decision coverage: "
            f"{terminal_rate:.2%}" if terminal_rate is not None
            else "- Terminal decision coverage: không xác định (0 scheduled)."
        )
        if terminal_rate is not None:
            dong[-1] += (
                f" ({terminal.get('completed_agent_decision_turn', 0)}/"
                f"{terminal.get('scheduled_agent_decision', 0)}); parsed "
                f"{parsed_rate:.2%}" if parsed_rate is not None else "; parsed không xác định"
            )
    autonomy = meta.get("llm_autonomy_budget")
    if isinstance(autonomy, dict):
        rng = autonomy.get("request_moi_tick", {})
        dong.append(
            f"- Autonomy LLM mỗi agent: {'PASS' if autonomy.get('dat') else 'FAIL'} · "
            f"{autonomy.get('agent_tick', 0)} agent-tick · {meta.get('llm_request_total', 0)} "
            f"request · {rng.get('min', 0)}–{rng.get('max', 0)} request/tick · "
            f"vi phạm sàn/trần/batch "
            f"{autonomy.get('vi_pham_san', 0)}/{autonomy.get('vi_pham_tran', 0)}/"
            f"{autonomy.get('vi_pham_batch', 0)}"
        )
    dong.append(f"- Milestones: {[x['ten'] for x in w.milestones]}")
    (rp_dir / f"session_{n}.md").write_text("\n".join(dong), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
