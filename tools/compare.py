"""So sánh 2 run (mock vs rulebot) vào report của run A.

  python -m tools.compare mock300 rb300
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"


def doc_metrics(run: str) -> list[dict]:
    with open(DATA_DIR / run / "metrics.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def dong(ms: list[dict], key: str, tick: int) -> float:
    for m in ms:
        if m["tick"] == tick:
            return m.get(key, 0)
    return float("nan")


def ticks_chung(ma: list[dict], mb: list[dict], toi_da: int = 6) -> list[int]:
    """Mốc chung trải đều trên horizon thật, không giả định run nào cũng 600 tick."""
    chung = sorted({int(m["tick"]) for m in ma} & {int(m["tick"]) for m in mb})
    if len(chung) <= toi_da:
        return chung
    indices = sorted({round(i * (len(chung) - 1) / (toi_da - 1)) for i in range(toi_da)})
    return [chung[i] for i in indices]


def compare_runs(run_a: str, run_b: str, output: Path) -> Path:
    """So sánh hai run và ghi output đã chỉ định, không ghi đè report global."""
    ma, mb = doc_metrics(run_a), doc_metrics(run_b)
    meta_a = json.loads((DATA_DIR / run_a / "run_meta.json").read_text(encoding="utf-8"))
    meta_b = json.loads((DATA_DIR / run_b / "run_meta.json").read_text(encoding="utf-8"))

    cac_tick = ticks_chung(ma, mb)
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="So sánh hai run THÓC mà không đè report khác")
    parser.add_argument("run_a")
    parser.add_argument("run_b")
    parser.add_argument("--output", type=Path, help="đường dẫn report tùy chọn")
    args = parser.parse_args(argv)
    output = args.output or DATA_DIR / args.run_a / "reports" / f"compare_{args.run_b}.md"
    ra = compare_runs(args.run_a, args.run_b, output)
    print(f"[xong] {ra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
