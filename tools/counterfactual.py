"""Chạy phản chứng tái lập (C1–C5) mà không sửa config gốc.

Mặc định dùng rulebot để ensemble không tốn request LLM. Có thể truyền ``--mode
mock`` để kiểm tra toàn pipeline mock; mock vẫn chạy cục bộ, không gọi provider thật.

Ví dụ:
  python -m tools.counterfactual --suite c1_no_contract_seeds c4_adverse_weather \
      --seeds 41 42 43 --ticks 80
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
EXPERIMENTS = ROOT / "data" / "experiments"


@dataclass(frozen=True)
class Treatment:
    id: str
    description: str
    overlay: dict[str, Any] | None = None
    permute_personas: bool = False


TREATMENTS: dict[str, Treatment] = {
    "baseline": Treatment("baseline", "Cấu hình không treatment."),
    "c1_no_contract_seeds": Treatment(
        "c1_no_contract_seeds", "Bỏ toàn bộ mẫu hợp đồng khởi đầu.",
        {"hop_dong": {"mau_khoi_dau": []}},
    ),
    "c2_permute_personas": Treatment(
        "c2_permute_personas", "Hoán đổi persona, giữ bản đồ/tài sản ban đầu.",
        permute_personas=True,
    ),
    "c3_no_parameter_noise": Treatment(
        "c3_no_parameter_noise", "Tắt nhiễu tham số ở tầng minds.",
        {"minds": {"nhieu_tham_so_so": 0.0}},
    ),
    "c4_adverse_weather": Treatment(
        "c4_adverse_weather", "Tăng xác suất hạn/lũ, bảo toàn tổng xác suất bằng 1.",
        {"thoi_gian": {"thoi_tiet": {
            "duoc_mua": {"p": 0.10, "he_so": 1.25},
            "binh_thuong": {"p": 0.45, "he_so": 1.0},
            "han_lu": {"p": 0.45, "he_so": 0.55},
        }}},
    ),
}

SUMMARY_FIELDS = (
    "dan_so", "thoc_moi_nguoi", "gini_dat", "gini_thoc", "gini_thu_nhap",
    "ty_le_biet_chu", "gdp", "ty_le_phi_nong",
)


def _write_overlay(directory: Path, treatment: Treatment) -> Path | None:
    if treatment.overlay is None:
        return None
    path = directory / f"{treatment.id}.yaml"
    path.write_text(yaml.safe_dump(treatment.overlay, allow_unicode=True, sort_keys=True),
                    encoding="utf-8")
    return path


def _read_final_metrics(run_name: str) -> dict[str, Any]:
    path = RUNS / run_name / "metrics.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError(f"Run {run_name} không có metrics")
    return rows[-1]


def _run_one(*, treatment: Treatment, seed: int, ticks: int, mode: str,
             scenario: str | None, overlay: Path | None, prefix: str) -> tuple[str, dict[str, Any]]:
    run_name = f"{prefix}_{treatment.id}_s{seed}"
    run_dir = RUNS / run_name
    if run_dir.exists():
        raise FileExistsError(f"Run đã tồn tại, không ghi đè: {run_dir}")
    cmd = [sys.executable, str(ROOT / "run.py"), "--mode", mode, "--ticks", str(ticks),
           "--seed", str(seed), "--run-name", run_name]
    if mode == "mock":
        cmd.append("--fast")
    if scenario:
        cmd += ["--scenario", scenario]
    if overlay:
        cmd += ["--config-overlay", str(overlay)]
    if treatment.permute_personas:
        cmd.append("--permute-personas")
    result = subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"Run {run_name} thất bại (exit {result.returncode})")
    return run_name, _read_final_metrics(run_name)


def _percentile(values: list[float], q: float) -> float:
    """Phân vị nội suy tuyến tính, không thêm dependency cho tool ensemble."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Tóm tắt bất định giữa seed; không che phân phối bằng một mean duy nhất."""
    out: dict[str, dict[str, float]] = {}
    for key in SUMMARY_FIELDS:
        values = [float(row.get(key, 0.0)) for row in rows]
        out[key] = {
            "n": len(values),
            "mean": round(mean(values), 6) if values else 0.0,
            "median": round(median(values), 6) if values else 0.0,
            "p10": round(_percentile(values, 0.10), 6),
            "p90": round(_percentile(values, 0.90), 6),
        }
    return out


def _paired_delta(treatment: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Chênh treatment−baseline theo cùng seed, tránh lẫn nhiễu stochastic."""
    if len(treatment) != len(baseline):
        raise ValueError("Treatment và baseline phải có cùng số seed để so ghép cặp")
    rows = [
        {key: float(t.get(key, 0.0)) - float(b.get(key, 0.0)) for key in SUMMARY_FIELDS}
        for t, b in zip(treatment, baseline, strict=True)
    ]
    return _summary(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ensemble phản chứng tái lập cho THÓC")
    parser.add_argument("--suite", nargs="+", default=["baseline", *TREATMENTS.keys()],
                        choices=sorted(TREATMENTS), help="treatment cần chạy")
    parser.add_argument("--seeds", nargs="+", type=int, default=[41, 42, 43])
    parser.add_argument("--ticks", type=int, default=100)
    parser.add_argument("--mode", choices=["rulebot", "mock"], default="rulebot")
    parser.add_argument("--scenario", default="preindustrial_closed_v1")
    parser.add_argument("--prefix", default="cf")
    args = parser.parse_args(argv)
    if args.ticks <= 0:
        parser.error("--ticks phải dương")

    selected = list(dict.fromkeys(args.suite))
    directory = EXPERIMENTS / f"{args.prefix}_{args.mode}_{args.ticks}t"
    if directory.exists():
        raise SystemExit(f"Thư mục thí nghiệm đã tồn tại: {directory}; đổi --prefix để không ghi đè.")
    directory.mkdir(parents=True)

    all_rows: dict[str, list[dict[str, Any]]] = {t: [] for t in selected}
    rows_by_seed: dict[str, dict[int, dict[str, Any]]] = {t: {} for t in selected}
    run_names: dict[str, list[str]] = {t: [] for t in selected}
    failed: dict[str, list[int]] = {t: [] for t in selected}
    for treatment_id in selected:
        treatment = TREATMENTS[treatment_id]
        overlay = _write_overlay(directory, treatment)
        for seed in args.seeds:
            # Run fail (tuyệt chủng/crash/exit≠0) được ĐẾM là failed, KHÔNG abort cả ensemble.
            try:
                run_name, metrics = _run_one(
                    treatment=treatment, seed=seed, ticks=args.ticks, mode=args.mode,
                    scenario=args.scenario, overlay=overlay, prefix=args.prefix,
                )
            except (RuntimeError, FileExistsError, FileNotFoundError) as exc:
                failed[treatment_id].append(seed)
                print(f"[{treatment_id}] seed={seed} FAILED: {exc}")
                continue
            run_names[treatment_id].append(run_name)
            all_rows[treatment_id].append(metrics)
            rows_by_seed[treatment_id][seed] = metrics
            print(f"[{treatment_id}] seed={seed} -> {run_name}")

    payload = {
        "mode": args.mode,
        "ticks": args.ticks,
        "seeds": args.seeds,
        "scenario": args.scenario,
        "treatments": {
            tid: {
                "description": TREATMENTS[tid].description,
                "runs": run_names[tid],
                "n_success": len(all_rows[tid]),
                "n_failed": len(failed[tid]),
                "failed_seeds": failed[tid],
                "final_metrics": _summary(all_rows[tid]),
            }
            for tid in selected
        },
    }
    if "baseline" in selected:
        base = rows_by_seed["baseline"]
        for tid in selected:
            if tid == "baseline":
                continue
            # Paired delta chỉ trên seed thành công Ở CẢ HAI (align theo seed, không theo vị trí).
            common = sorted(set(rows_by_seed[tid]) & set(base))
            if common:
                payload["treatments"][tid]["paired_delta_vs_baseline"] = _paired_delta(
                    [rows_by_seed[tid][s] for s in common], [base[s] for s in common]
                )
                payload["treatments"][tid]["paired_delta_seeds"] = common
            else:
                payload["treatments"][tid]["paired_delta_vs_baseline"] = {
                    "note": "không có seed thành công chung với baseline"
                }
    (directory / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    lines = ["# Ensemble phản chứng", "", f"- Mode: `{args.mode}` (không gọi LLM thật)",
             f"- Tick: {args.ticks}; seeds: {args.seeds}; scenario: `{args.scenario}`", "",
             "- Mỗi ô: mean [p10, p90] giữa các seed; treatment có baseline kèm delta trong JSON.",
             "", "| treatment | dân số | thóc/người | Gini đất | Gini thóc | GDP | phi nông |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for tid in selected:
        s = payload["treatments"][tid]["final_metrics"]
        def fmt(key: str, decimals: int = 1, percent: bool = False, metrics=s) -> str:
            item = metrics[key]
            factor = 100 if percent else 1
            suffix = "%" if percent else ""
            return (f"{item['mean'] * factor:.{decimals}f}{suffix} "
                    f"[{item['p10'] * factor:.{decimals}f}, {item['p90'] * factor:.{decimals}f}]")
        lines.append(
            f"| {tid} | {fmt('dan_so')} | {fmt('thoc_moi_nguoi')} | {fmt('gini_dat', 3)} "
            f"| {fmt('gini_thoc', 3)} | {fmt('gdp')} | {fmt('ty_le_phi_nong', 1, True)} |"
        )
    (directory / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[xong] {directory.relative_to(ROOT) / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
