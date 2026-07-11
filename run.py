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

        return tao_mind_mock(w, fast=args.fast)
    if mode == "real":
        raise SystemExit(
            "Mode real bị khóa trước HUMAN-GATE 1 (cần LLM_MODE=real trong .env VÀ --i-am-sure)."
        )
    raise SystemExit(f"Mode không hỗ trợ: {mode}")


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
    args = ap.parse_args()

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
        if w.tick % ck_moi_n == 0:
            w.luu_checkpoint(ck_dir)
            w.events.flush()
        if w.tick % 50 == 0 or w.tick == tong_tick:
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
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[xong] tick {w.tick} | hash {meta['world_hash'][:16]} | {meta['thoi_gian_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
