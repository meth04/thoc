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

    # Tái dựng config ĐÚNG như run: nếu có manifest, áp lại overlay (gồm scenario) để run
    # dùng scenario/counterfactual replay cùng hash. Không manifest (run cũ) → config gốc.
    overlays: list[Path] = []
    manifest_path = run_dir / "experiment_manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("reproducibility", {}).get("config_overlays", []):
            p = Path(item["path"])
            if p.exists():
                overlays.append(p)
    cfg = load_config(overlays=overlays)
    w = tao_the_gioi(cfg, meta["seed"], events_path=None)
    repro = manifest.get("reproducibility", {})
    if "permute_personas" in repro.get("treatments", []):
        from tools.experiments import permute_personas
        permute_personas(w)
    if meta["mode"] == "rulebot":
        # Tái dựng policy Lớp-4 từ manifest (như overlay/treatment) để run có --policy
        # khác rulebot replay đúng world-hash. Không manifest → baseline rulebot.
        from minds.policies import tao_policy

        ten_policy = (repro.get("policy") or {}).get("name") or "rulebot"
        mind_fn = tao_policy(ten_policy)
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
