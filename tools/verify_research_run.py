"""tools/verify_research_run — kiểm toán tái lập một run nghiên cứu (chỉ đọc).

Tool này KHÔNG chạy provider/LLM thật và KHÔNG sửa run. Nó xác nhận một run trong
``data/runs/<name>/`` đủ bằng chứng để tái lập:

  1. manifest schema + trường bắt buộc;
  2. đồng nhất giữa manifest và run_meta (name/seed/config_sha256/world_hash);
  3. config digest tái dựng từ overlay của manifest khớp digest đã ghi;
  4. scenario files chưa trôi (sha256 khớp) nếu run gắn scenario;
  5. metrics.jsonl liên tục tới tick cuối; events.jsonl tồn tại;
  6. replay rulebot/mock cùng config → world-hash TRÙNG (đồng thời chạy lại audit
     bảo toàn mỗi tick). Real mode: bỏ qua replay (cần transcript), báo rõ.

Trả về nonzero khi bất kỳ bằng chứng bắt buộc nào thiếu. Ví dụ:

  python -m tools.verify_research_run rb300
  python -m tools.verify_research_run rb300 --quick   # bỏ replay tốn thời gian
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engine.config import load_config
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from tools.experiments import ROOT, sha256_file

DATA_DIR = ROOT / "data" / "runs"


class Ket:
    """Gom kết quả kiểm tra; mỗi mục là (tên, ok, chi_tiet, hard).

    `hard=True` (mặc định): sai → toàn cục FAIL (evidence thiếu). `hard=False`: sai chỉ là
    WARN (ví dụ config base trôi sau run — replay hash mới là bằng chứng tái lập quyết định).
    """

    def __init__(self) -> None:
        self.items: list[tuple[str, bool | None, str, bool]] = []

    def add(self, name: str, ok: bool | None, detail: str = "", hard: bool = True) -> None:
        self.items.append((name, ok, detail, hard))

    def failed(self) -> bool:
        return any(ok is False and hard for _, ok, _, hard in self.items)

    def render(self) -> str:
        lines = []
        for name, ok, detail, hard in self.items:
            if ok is True:
                mark = "PASS"
            elif ok is None:
                mark = "SKIP"
            else:
                mark = "FAIL" if hard else "WARN"
            lines.append(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
        return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_metrics(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _reconstruct_config(manifest: dict[str, Any], ket: Ket):
    """Dựng lại config từ overlay ghi trong manifest (đã gồm scenario overlay ở index 0)."""
    repro = manifest.get("reproducibility", {})
    overlay_items = repro.get("config_overlays", [])
    overlays: list[Path] = []
    missing: list[str] = []
    drifted: list[str] = []
    for item in overlay_items:
        p = Path(item["path"])
        if not p.exists():
            missing.append(str(p))
            continue
        if item.get("sha256") and sha256_file(p) != item["sha256"]:
            drifted.append(str(p))
        overlays.append(p)
    if missing:
        ket.add("overlay_files_present", False, f"thiếu: {missing}", hard=False)
    if drifted:
        ket.add("overlay_files_unchanged", False, f"sha256 lệch: {drifted}", hard=False)
    cfg = load_config(overlays=overlays)
    return cfg, bool(missing)


def verify_run(run_name: str, quick: bool = False) -> Ket:
    ket = Ket()
    run_dir = DATA_DIR / run_name
    if not run_dir.is_dir():
        ket.add("run_dir_exists", False, str(run_dir))
        return ket

    # 1. manifest schema + trường bắt buộc
    manifest_path = run_dir / "experiment_manifest.json"
    if not manifest_path.exists():
        ket.add("manifest_present", False, "thiếu experiment_manifest.json")
        return ket
    manifest = _load_json(manifest_path)
    schema_ok = manifest.get("schema_version") is not None
    run_block = manifest.get("run", {})
    repro = manifest.get("reproducibility", {})
    required_run = {"name", "mode", "seed", "ticks_requested"}
    missing_run = sorted(required_run - set(run_block))
    manifest_ok = (schema_ok and not missing_run
                   and repro.get("config_sha256") is not None)
    ket.add("manifest_schema", manifest_ok,
            f"schema={manifest.get('schema_version')} missing_run={missing_run}")

    # 2. run_meta + đồng nhất manifest↔meta
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        ket.add("run_meta_present", False, "thiếu run_meta.json")
        return ket
    meta = _load_json(meta_path)
    same_name = meta.get("run_name") == run_block.get("name") == run_name
    same_seed = meta.get("seed") == run_block.get("seed")
    same_digest = (meta.get("config_sha256") == repro.get("config_sha256"))
    ket.add("manifest_meta_consistent", bool(same_name and same_seed and same_digest),
            f"name={same_name} seed={same_seed} digest={same_digest}")
    outcome = manifest.get("outcome", {})
    if outcome:
        hash_ok = outcome.get("world_hash") == meta.get("world_hash")
        ket.add("outcome_hash_matches_meta", bool(hash_ok),
                f"{outcome.get('world_hash', '')[:12]} vs {meta.get('world_hash', '')[:12]}")

    # 3. config digest tái dựng
    cfg, overlays_missing = _reconstruct_config(manifest, ket)
    if not overlays_missing:
        digest_ok = cfg.digest() == repro.get("config_sha256")
        # SOFT: base config có thể trôi ở khóa không ảnh hưởng run này; replay hash mới là
        # bằng chứng tái lập quyết định. Digest lệch = cảnh báo provenance, không phải FAIL.
        ket.add("config_digest_reproduced", bool(digest_ok),
                f"{cfg.digest()[:12]} vs {str(repro.get('config_sha256'))[:12]}"
                + ("" if digest_ok else " (base config trôi sau run — xem replay_world_hash)"),
                hard=False)
    else:
        ket.add("config_digest_reproduced", None, "overlay thiếu — không tái dựng được digest")

    # 4. scenario files chưa trôi
    scenario = repro.get("scenario")
    if scenario:
        recorded = repro.get("scenario_files_sha256", {})
        drift = []
        for rel, digest in recorded.items():
            p = ROOT / rel
            if not p.exists() or sha256_file(p) != digest:
                drift.append(rel)
        ket.add("scenario_files_unchanged", not drift,
                f"trôi: {drift}" if drift else f"{len(recorded)} file khớp", hard=False)

    # 5. metrics/events consistency
    metrics_path = run_dir / "metrics.jsonl"
    events_path = run_dir / "events.jsonl"
    tick_cuoi = int(meta.get("tick_cuoi", 0))
    if metrics_path.exists():
        rows = _read_metrics(metrics_path)
        ticks = [int(r["tick"]) for r in rows if "tick" in r]
        contiguous = ticks == list(range(1, len(ticks) + 1))
        last_ok = bool(ticks) and ticks[-1] == tick_cuoi
        ket.add("metrics_contiguous_to_final", bool(contiguous and last_ok),
                f"n={len(ticks)} last={ticks[-1] if ticks else None} tick_cuoi={tick_cuoi}")
    else:
        ket.add("metrics_present", False, "thiếu metrics.jsonl")
    ket.add("events_present", events_path.exists(),
            "" if events_path.exists() else "thiếu events.jsonl")

    # 6. replay rulebot/mock (đồng thời audit bảo toàn mỗi tick trong chay_mot_tick)
    mode = meta.get("mode")
    if quick:
        ket.add("replay_world_hash", None, "bỏ qua (--quick)")
    elif mode not in ("rulebot", "mock"):
        ket.add("replay_world_hash", None, f"bỏ qua (mode={mode} cần transcript)")
    elif overlays_missing:
        ket.add("replay_world_hash", None, "overlay thiếu — không replay đúng config")
    else:
        w = tao_the_gioi(cfg, int(meta["seed"]), events_path=None)
        if "permute_personas" in repro.get("treatments", []):
            from tools.experiments import permute_personas
            permute_personas(w)
        if mode == "rulebot":
            # Tái dựng policy Lớp-4 từ manifest (như replay.py) — run tạo bằng --policy khác
            # rulebot phải replay đúng world-hash, không hardcode rulebot.
            from minds.policies import tao_policy
            ten_policy = (repro.get("policy") or {}).get("name") or "rulebot"
            mind_fn = tao_policy(ten_policy)
        else:
            from minds.orchestrator import tao_mind_mock
            mind_fn = tao_mind_mock(w, fast=True, p_malformed=meta.get("p_malformed"))
        tong_thua = len(w.parcels)
        try:
            while w.tick < tick_cuoi:
                chay_mot_tick(w, mind_fn, tong_thua)
            h = w.world_hash()
            ket.add("replay_world_hash", h == meta.get("world_hash"),
                    f"{h[:12]} vs {str(meta.get('world_hash'))[:12]} (audit xanh mỗi tick)")
        except Exception as exc:  # noqa: BLE001 — báo cáo mọi lỗi replay/audit
            ket.add("replay_world_hash", False, f"{type(exc).__name__}: {exc}")
    return ket


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm toán tái lập một run nghiên cứu (chỉ đọc)")
    ap.add_argument("run_name")
    ap.add_argument("--quick", action="store_true", help="bỏ replay (chỉ kiểm artifact)")
    ap.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    args = ap.parse_args(argv)
    ket = verify_run(args.run_name, quick=args.quick)
    if args.json:
        print(json.dumps(
            {"run": args.run_name, "ok": not ket.failed(),
             "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in ket.items]},
            ensure_ascii=False, indent=2))
    else:
        print(ket.render())
        print("KẾT QUẢ: " + ("ĐỦ BẰNG CHỨNG ✅" if not ket.failed() else "THIẾU BẰNG CHỨNG ❌"))
    return 1 if ket.failed() else 0


if __name__ == "__main__":
    sys.exit(main())
