"""CLI chạy mô phỏng THÓC.

Ví dụ:
  python run.py --mode rulebot --years 300 --seed 42 --run-name rb300
  python run.py --mode rulebot --ticks 100 --seed 42 --run-name t100 --resume
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

from engine.config import load_config
from engine.tick import chay_mot_tick
from engine.world import World, tao_the_gioi

DATA_DIR = Path(__file__).resolve().parent / "data" / "runs"


def lay_mind_fn(mode: str, w: World, args: argparse.Namespace):
    if mode == "rulebot":
        from minds.rulebot import quyet_dinh_tat_ca

        return quyet_dinh_tat_ca
    if mode == "mock":
        from minds.orchestrator import tao_mind_mock

        run_dir = DATA_DIR / (args.run_name or f"mock_{args.seed}")
        return tao_mind_mock(w, fast=args.fast, run_dir=run_dir,
                             p_malformed=args.p_malformed)
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
        return tao_mind_real(w, run_dir, w.cfg, env,
                             quota_db=DATA_DIR / "quota_counters.sqlite")
    raise SystemExit(f"Mode không hỗ trợ: {mode}")


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
    if env.nine_key and not env.nine_key.startswith("dien_key"):
        print(f"9router health-check: {'OK' if gw.ninerouter.health_check() else 'FAIL'}")
    routes: list[tuple[str, Route]] = []
    for tier in ("T0", "T1", "T2", "T3", "T4"):
        for r in gw.routes_cua_tier(tier):
            routes.append((tier, r))
    for ten_nen in ("nen_hoi_ky", "chronicle"):
        nen = cfg.get(f"models.{ten_nen}")
        q = cfg.raw()["quotas"][nen["provider"]]["models"].get(nen["model"], {})
        routes.append((ten_nen, Route(nen["provider"], nen["model"],
                                      int(q.get("rpm", 5)), int(q.get("rpd", 100)))))
    print(f"{'route':<14} {'model':<36} {'ok':<4} {'tok i/o':<10} latency")
    so_call = 0
    for tier, route in routes[:12]:
        # JSON mode (PART 5.2): OpenAI json_object cần TOP-LEVEL OBJECT (không phải mảng)
        req = LLMRequest(prompt='Trả về đúng một JSON object: {"ok": true}', ctx={},
                         tier=tier if tier.startswith("T") else "T0", batch_ids=["smoke"])
        try:
            resp = gw._goi_route(req, route, cfg.get("models.tiers.T0"))
            gw.quota.ghi_call(route.provider, route.model, resp.key_hash, __import__("time").time())
            so_call += 1
            print(f"{tier:<14} {route.model:<36} ok   {resp.tok_in}/{resp.tok_out:<7}"
                  f" {resp.latency_s:.2f}s")
        except Exception as e:  # noqa: BLE001 — smoke báo cáo mọi lỗi (đã che key)
            from minds.providers_real import che_key

            print(f"{tier:<14} {route.model:<36} LỖI  {type(e).__name__}: "
                  f"{che_key(str(e))[:160]}")
    print(f"[smoke] {so_call} call — xong.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="THÓC — mô phỏng 300 năm kinh tế tự phát")
    ap.add_argument("--mode", choices=["rulebot", "mock", "real"], default="rulebot")
    ap.add_argument("--years", type=int, default=None)
    ap.add_argument("--ticks", type=int, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--fast", action="store_true", help="tắt giả lập latency của mock")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--i-am-sure", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--until-budget", action="store_true")
    ap.add_argument("--p-malformed", type=float, default=None,
                    help="tỷ lệ mock cố tình trả JSON hỏng (mặc định theo models.yaml)")
    args = ap.parse_args()

    if args.smoke:
        return chay_smoke(args)
    tong_tick = args.ticks if args.ticks is not None else (args.years or 300) * 2
    run_name = args.run_name or f"{args.mode}_{args.seed}"
    run_dir = DATA_DIR / run_name
    ck_dir = run_dir / "checkpoints"
    events_path = run_dir / "events.jsonl"

    cfg = load_config()
    ck_moi_nhat = ck_dir / "checkpoint_moi_nhat.json"
    if args.resume and ck_moi_nhat.exists():
        meta = json.loads(ck_moi_nhat.read_text(encoding="utf-8"))
        w = World.nap_checkpoint(ck_dir / f"checkpoint_{meta['tick']:04d}.pkl", events_path)
        print(f"[resume] từ tick {w.tick} (hash {meta['world_hash'][:12]})")
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
        w = tao_the_gioi(cfg, args.seed, events_path)
    w.unrecognized_path = run_dir / "unrecognized_intents.jsonl"

    mind_fn = lay_mind_fn(args.mode, w, args)
    tong_thua = len(w.parcels)
    ck_moi_n = int(cfg.get("minds.checkpoint_moi_n_tick"))

    ngat = {"flag": False}

    def bat_sigint(_sig, _frm):
        ngat["flag"] = True
        print("\n[SIGINT] sẽ checkpoint sạch rồi dừng...")

    signal.signal(signal.SIGINT, bat_sigint)

    t0 = time.time()
    while w.tick < tong_tick and not ngat["flag"]:
        m = chay_mot_tick(w, mind_fn, tong_thua)
        if getattr(mind_fn, "het_ngan_sach", False):
            print(f"[budget] hết ngân sách: {getattr(mind_fn, 'ly_do_dung', '')} "
                  f"— checkpoint và dừng êm (không degrade).")
            break
        if w.tick % ck_moi_n == 0:
            w.luu_checkpoint(ck_dir)
            w.events.flush()
        buoc_in = 5 if args.mode == "real" else 50
        if w.tick % buoc_in == 0 or w.tick == tong_tick:
            print(
                f"tick {w.tick:4d} (năm {m['nam']:3d}) | dân {m['dan_so']:4d} | "
                f"thóc/người {m['thoc_moi_nguoi']:7.1f} | gini đất {m['gini_dat']:.2f} | "
                f"biết chữ {m['ty_le_biet_chu']:.0%} | {time.time() - t0:6.1f}s"
            )

    w.luu_checkpoint(ck_dir)
    w.events.flush()
    w.events.dong()
    # metrics ra file
    with open(run_dir / "metrics.jsonl", "w", encoding="utf-8") as f:
        for m in w.metrics_lich_su:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    meta = {
        "run_name": run_name,
        "mode": args.mode,
        "seed": args.seed,
        "tick_cuoi": w.tick,
        "world_hash": w.world_hash(),
        "thoi_gian_s": round(time.time() - t0, 1),
    }
    if args.mode in ("mock", "real"):
        meta["p_malformed"] = mind_fn.p_malformed
        meta["so_call"] = mind_fn.so_call
        meta["so_luot_nghi"] = mind_fn.so_nghi
        meta["so_fallback"] = mind_fn.so_fallback
        meta["fallback_rate"] = round(mind_fn.fallback_rate, 4)
        meta["het_ngan_sach"] = bool(getattr(mind_fn, "het_ngan_sach", False))
        mind_fn.log.dong()
        print(f"[{args.mode}] call={meta['so_call']} nghĩ={meta['so_luot_nghi']} "
              f"fallback={meta['so_fallback']} ({meta['fallback_rate']:.2%})")
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
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
    dong = [
        f"# Phiên {n} — run `{meta['run_name']}` (mode {meta['mode']}, seed {meta['seed']})",
        "",
        f"- Tick cuối: {meta['tick_cuoi']} (năm {meta['tick_cuoi'] // 2}); "
        f"thời gian chạy {meta['thoi_gian_s']}s; world-hash `{meta['world_hash'][:16]}`",
        f"- Dân số {m.get('dan_so', '?')} · biết chữ {m.get('ty_le_biet_chu', 0):.0%} · "
        f"gini đất {m.get('gini_dat', '?')} · tri thức {m.get('tri_thuc', 0)}",
        f"- Entity {m.get('so_entity', 0)} · máy {m.get('so_may', 0)} · "
        f"blueprint {m.get('so_blueprint', 0)} · hợp đồng hiệu lực {m.get('hd_hieu_luc', 0)}",
        f"- Nhãn định chế: {m.get('nhan_dinh_che', {})} · "
        f"công nghiệp hóa: {m.get('cong_nghiep_hoa', False)}",
    ]
    if "fallback_rate" in meta:
        dong.append(f"- LLM: {meta['so_call']} call, {meta['so_luot_nghi']} lượt nghĩ, "
                    f"fallback {meta['fallback_rate']:.2%} (p_malformed={meta['p_malformed']})")
    dong.append(f"- Milestones: {[x['ten'] for x in w.milestones]}")
    (rp_dir / f"session_{n}.md").write_text("\n".join(dong), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
