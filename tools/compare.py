"""So sánh 2 run (mock vs rulebot) → reports/compare_baseline.md.

  python -m tools.compare mock300 rb300
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def doc_metrics(run: str) -> list[dict]:
    with open(DATA_DIR / run / "metrics.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def dong(ms: list[dict], key: str, tick: int) -> float:
    for m in ms:
        if m["tick"] == tick:
            return m.get(key, 0)
    return float("nan")


def main() -> int:
    run_a, run_b = sys.argv[1], sys.argv[2]
    ma, mb = doc_metrics(run_a), doc_metrics(run_b)
    meta_a = json.loads((DATA_DIR / run_a / "run_meta.json").read_text(encoding="utf-8"))
    meta_b = json.loads((DATA_DIR / run_b / "run_meta.json").read_text(encoding="utf-8"))
    REPORT_DIR.mkdir(exist_ok=True)

    cac_tick = [100, 200, 300, 400, 500, 600]
    chi_so = ["dan_so", "thoc_moi_nguoi", "gini_dat", "gini_thoc", "ty_le_biet_chu",
              "hd_hieu_luc", "so_mo_tip", "kl_giao_dich", "vo_gia_cu"]
    lines = [
        f"# So sánh baseline: `{run_a}` (mode {meta_a['mode']}) vs `{run_b}` (mode {meta_b['mode']})",
        "",
        f"- Seed: {meta_a['seed']} / {meta_b['seed']}; tick cuối: {meta_a['tick_cuoi']} / {meta_b['tick_cuoi']}",
        f"- Thời gian chạy: {meta_a['thoi_gian_s']}s / {meta_b['thoi_gian_s']}s",
    ]
    if "fallback_rate" in meta_a:
        lines.append(
            f"- `{run_a}`: {meta_a['so_call']} call, fallback {meta_a['fallback_rate']:.2%} "
            f"(p_malformed={meta_a['p_malformed']})"
        )
    lines += ["", "| chỉ số | tick | " + run_a + " | " + run_b + " |", "|---|---|---|---|"]
    for cs in chi_so:
        for t in cac_tick:
            va, vb = dong(ma, cs, t), dong(mb, cs, t)
            lines.append(f"| {cs} | {t} | {va} | {vb} |")
    ra = REPORT_DIR / "compare_baseline.md"
    ra.write_text("\n".join(lines), encoding="utf-8")
    print(f"[xong] {ra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
