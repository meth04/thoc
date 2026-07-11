"""tools/replay — chạy lại run từ seed và so world-hash (điều luật #4).

  python -m tools.replay rb300 --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.config import load_config
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    run_dir = DATA_DIR / args.run_name
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    if meta["mode"] not in ("rulebot", "mock"):
        raise SystemExit("replay chỉ hỗ trợ rulebot/mock (real cần transcript — Phase 7)")

    cfg = load_config()
    w = tao_the_gioi(cfg, meta["seed"], events_path=None)
    if meta["mode"] == "rulebot":
        from minds.rulebot import quyet_dinh_tat_ca as mind_fn
    else:
        from minds.orchestrator import tao_mind_mock

        mind_fn = tao_mind_mock(w, fast=True, p_malformed=meta.get("p_malformed"))
    tong_thua = len(w.parcels)
    while w.tick < meta["tick_cuoi"]:
        chay_mot_tick(w, mind_fn, tong_thua)
    h = w.world_hash()
    trung = h == meta["world_hash"]
    print(f"hash replay : {h}")
    print(f"hash gốc    : {meta['world_hash']}")
    print("KẾT QUẢ     : " + ("TRÙNG ✅" if trung else "LỆCH ❌"))
    if args.verify and not trung:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
