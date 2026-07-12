"""Sensitivity runner cho THÓC — đo importance/identifiability của tham số scenario.

Công cụ này CHỈ rút giá trị tham số TỪ ``plausible_range`` đã khai báo trong
``scenarios/<scenario>/priors.yaml`` (một-tham-số-một-lần / grid đều, tất định). Với
mỗi điểm lưới nó viết overlay YAML (deep-merge như ``tools.counterfactual``), chạy
``run.py --config-overlay`` ở chế độ rulebot (KHÔNG mạng, KHÔNG LLM) qua subprocess rồi
đọc dòng cuối ``metrics.jsonl``. Báo cáo độ nhạy của các outcome chính, TÁCH biến thiên
do tham số khỏi nhiễu giữa seed (cần ≥2 seed mỗi điểm).

Nguyên tắc cứng:
- KHÔNG lấy giá trị NGOÀI ``plausible_range``; KHÔNG dùng random toàn cục (grid tất định).
- KHÔNG tune, KHÔNG chọn "param tốt nhất" — chỉ báo importance/identifiability.
- Nếu một param không đổi được outcome (non-identified) → BÁO rõ, không bịa hiệu ứng.
- Thư mục thí nghiệm isolated, refuse overwrite; không đọc dữ liệu ngoài.

Ví dụ:
  python -m tools.sensitivity --scenario agrarian_transition_v1 \
      --params san_xuat.san_luong_goc_kg --samples 3 --seeds 41 42 --ticks 60
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from tools.counterfactual import _read_final_metrics

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "data" / "runs"
EXPERIMENTS = ROOT / "data" / "experiments"
SCENARIOS = ROOT / "scenarios"
EPSILON = 1e-9


def _num(value: Any) -> float | None:
    """Ép về float; trả None nếu thiếu/không phải số (không bịa 0)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(row: dict[str, Any], key: str) -> Any:
    """Lấy metric ở cấp cao nhất, rồi tới nhánh nested ``research`` nếu có."""
    if key in row:
        return row[key]
    research = row.get("research")
    if isinstance(research, dict) and key in research:
        return research[key]
    return None


def _food_security_rate(row: dict[str, Any]) -> float | None:
    """Tỷ lệ hộ đủ ăn = 1 − tỷ lệ hộ thiếu ăn (dẫn xuất minh bạch từ metric có sẵn)."""
    v = _num(_get(row, "ty_le_ho_thieu_an"))
    return None if v is None else round(1.0 - v, 6)


# Outcome chính = read-only từ metrics.jsonl. Tên → hàm rút giá trị (None = không đo được).
OUTCOMES: dict[str, Callable[[dict[str, Any]], float | None]] = {
    "dan_so": lambda r: _num(_get(r, "dan_so")),
    "gini_dat": lambda r: _num(_get(r, "gini_dat")),
    "gini_thoc": lambda r: _num(_get(r, "gini_thoc")),
    "gdp": lambda r: _num(_get(r, "gdp")),
    "food_security_rate": _food_security_rate,
}


def grid_from_range(lo: float, hi: float, n: int) -> list[float]:
    """Lưới đều tất định trên [lo, hi]; n≥2 gồm cả hai đầu mút, LUÔN nằm trong range.

    Đây là cách rút giá trị duy nhất: không random toàn cục, tái lập tuyệt đối. Kẹp
    ``min(hi, max(lo, .))`` để làm tròn float không bao giờ đẩy giá trị ra ngoài range.
    """
    if hi < lo:
        raise ValueError(f"plausible_range không hợp lệ: [{lo}, {hi}]")
    if n < 1:
        raise ValueError("samples phải >= 1")
    if n == 1:
        return [min(hi, max(lo, round((lo + hi) / 2.0, 9)))]
    step = (hi - lo) / (n - 1)
    return [min(hi, max(lo, round(lo + i * step, 9))) for i in range(n)]


def _nested_overlay(path: str, value: Any) -> dict[str, Any]:
    """Dựng dict lồng theo đường dẫn chấm (ví dụ ``a.b.c`` → {a:{b:{c: value}}})."""
    root: dict[str, Any] = {}
    cursor = root
    parts = path.split(".")
    for key in parts[:-1]:
        nxt: dict[str, Any] = {}
        cursor[key] = nxt
        cursor = nxt
    cursor[parts[-1]] = value
    return root


def _load_priors(scenario: str) -> dict[str, dict[str, Any]]:
    """Đọc priors.yaml, chỉ giữ key có ``plausible_range`` (param đo được độ nhạy)."""
    path = SCENARIOS / scenario / "priors.yaml"
    if not path.exists():
        raise SystemExit(f"Scenario {scenario} thiếu priors.yaml: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        k: v for k, v in data.items()
        if isinstance(v, dict) and isinstance(v.get("plausible_range"), list)
        and len(v["plausible_range"]) == 2
    }


def _run_point(*, param: str, idx: int, seed: int, ticks: int, scenario: str,
               overlay: Path, prefix: str) -> tuple[str, dict[str, Any]]:
    """Chạy một điểm (param×seed) qua run.py rulebot; refuse overwrite run cũ."""
    run_name = f"{prefix}_{param.replace('.', '_')}_i{idx}_s{seed}"
    run_dir = RUNS / run_name
    if run_dir.exists():
        raise FileExistsError(f"Run đã tồn tại, không ghi đè: {run_dir}")
    cmd = [sys.executable, str(ROOT / "run.py"), "--mode", "rulebot",
           "--ticks", str(ticks), "--seed", str(seed), "--run-name", run_name,
           "--scenario", scenario, "--config-overlay", str(overlay)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, encoding="utf-8",
                            errors="replace", capture_output=True)
    if result.returncode != 0:
        tail = (result.stderr or "")[-600:]
        raise RuntimeError(f"Run {run_name} thất bại (exit {result.returncode}): {tail}")
    return run_name, _read_final_metrics(run_name)


def _point_stats(seed_rows: dict[int, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Gộp outcome qua seed tại MỘT điểm: median (điểm ước lượng) + spread=max−min (nhiễu seed)."""
    out: dict[str, dict[str, Any]] = {}
    for name, extract in OUTCOMES.items():
        vals = [v for v in (extract(r) for r in seed_rows.values()) if v is not None]
        if not vals:
            out[name] = {"median": None, "spread": None, "n": 0}
        else:
            out[name] = {
                "median": round(median(vals), 6),
                "spread": round(max(vals) - min(vals), 6),
                "n": len(vals),
            }
    return out


def _sensitivity(points: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Độ nhạy mỗi outcome: biến thiên-do-param (range của seed-median) vs nhiễu-seed.

    ``identifiable`` = biến thiên do param vượt hẳn nhiễu giữa seed. Nếu param không đổi
    được outcome hoặc hiệu ứng chìm trong nhiễu seed → non-identified, ghi ``note`` rõ.
    """
    result: dict[str, dict[str, Any]] = {}
    for name in OUTCOMES:
        valued = [
            (p["value"], p["agg"][name]["median"], p["agg"][name]["spread"])
            for p in points if p["agg"][name]["median"] is not None
        ]
        if len(valued) < 2:
            result[name] = {
                "available": False,
                "note": "không đủ điểm có dữ liệu (>=2) để ước lượng độ nhạy",
            }
            continue
        pvals = [v for v, _, _ in valued]
        medians = [m for _, m, _ in valued]
        spreads = [s for _, _, s in valued if s is not None]
        param_span = round(max(pvals) - min(pvals), 9)
        outcome_range = round(max(medians) - min(medians), 6)
        seed_noise = round(median(spreads), 6) if spreads else 0.0
        slope = round(outcome_range / param_span, 6) if param_span > EPSILON else None
        center_o = median(medians)
        center_p = (min(pvals) + max(pvals)) / 2.0
        if param_span > EPSILON and abs(center_o) > EPSILON and abs(center_p) > EPSILON:
            elasticity = round(
                (outcome_range / abs(center_o)) / (param_span / abs(center_p)), 6
            )
        else:
            elasticity = None
        identifiable = bool(outcome_range > EPSILON and outcome_range > seed_noise + EPSILON)
        entry: dict[str, Any] = {
            "available": True,
            "outcome_range": outcome_range,
            "seed_noise_median": seed_noise,
            "param_span": param_span,
            "sensitivity_per_unit": slope,
            "elasticity": elasticity,
            "identifiable": identifiable,
        }
        if not identifiable:
            entry["note"] = (
                "non-identified: param KHÔNG đổi outcome trên plausible_range"
                if outcome_range <= EPSILON
                else "non-identified: biến thiên do param <= nhiễu giữa seed"
            )
        result[name] = entry
    return result


def _write_markdown(directory: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# Độ nhạy tham số — `{payload['scenario']}`",
        "",
        f"- Mode: `{payload['mode']}` (rulebot, KHÔNG mạng/LLM)",
        f"- ticks: {payload['ticks']}; seeds: {payload['seeds']} (n_seed={len(payload['seeds'])}); "
        f"samples/param: {payload['samples']}",
        f"- Outcome: {', '.join(payload['outcomes'])}",
        f"- Phương pháp: {payload['method']}",
        "",
        "Cột: outcome_range = biến thiên seed-median trên lưới param; seed_noise = trung vị "
        "spread giữa seed; identifiable = param vượt nhiễu seed.",
    ]
    for param, info in payload["params"].items():
        lines += [
            "",
            f"## `{param}`  range {info['plausible_range']} ({info.get('unit', '?')})",
            f"- grid: {info['grid']}; n_failed_runs: {info['n_failed_runs']}",
            "",
            "| outcome | outcome_range | seed_noise | sens/unit | elasticity | identifiable |",
            "|---|---:|---:|---:|---:|:--:|",
        ]
        for name in payload["outcomes"]:
            s = info["sensitivity"][name]
            if not s.get("available"):
                lines.append(f"| {name} | — | — | — | — | n/a ({s.get('note', '')}) |")
                continue
            flag = "yes" if s["identifiable"] else f"no ({s.get('note', '')})"
            lines.append(
                f"| {name} | {s['outcome_range']} | {s['seed_noise_median']} | "
                f"{s['sensitivity_per_unit']} | {s['elasticity']} | {flag} |"
            )
    (directory / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sensitivity runner (rút CHỈ từ plausible_range) cho THÓC")
    parser.add_argument("--scenario", required=True,
                        help="tên scenario trong scenarios/ (phải có priors.yaml)")
    parser.add_argument("--params", nargs="+", default=None,
                        help="param cần đo; mặc định: tất cả key có plausible_range trong priors")
    parser.add_argument("--samples", type=int, default=3,
                        help="số điểm lưới mỗi param (one-at-a-time, >=2)")
    parser.add_argument("--seeds", nargs="+", type=int, default=[41, 42],
                        help="seed mô phỏng (>=2 để tách nhiễu seed khỏi biến thiên param)")
    parser.add_argument("--ticks", type=int, default=60)
    parser.add_argument("--mode", choices=["rulebot"], default="rulebot",
                        help="chỉ rulebot — KHÔNG mạng/LLM")
    parser.add_argument("--prefix", default="sens")
    args = parser.parse_args(argv)

    if args.ticks <= 0:
        parser.error("--ticks phải dương")
    if args.samples < 2:
        parser.error("--samples phải >= 2 (cần biến thiên để đo độ nhạy)")
    seeds = sorted(dict.fromkeys(args.seeds))
    if len(seeds) < 2:
        parser.error("--seeds cần >= 2 seed phân biệt (tách nhiễu seed khỏi biến thiên param)")

    priors = _load_priors(args.scenario)
    if not priors:
        raise SystemExit(f"Scenario {args.scenario} không có param nào có plausible_range.")
    params = args.params if args.params else sorted(priors)
    unknown = [p for p in params if p not in priors]
    if unknown:
        raise SystemExit(
            f"Param không có plausible_range trong priors: {unknown}. "
            f"Có sẵn: {sorted(priors)}")

    directory = EXPERIMENTS / f"{args.prefix}_sens"
    if directory.exists():
        raise SystemExit(
            f"Thư mục thí nghiệm đã tồn tại: {directory}; đổi --prefix để không ghi đè.")
    directory.mkdir(parents=True)

    per_param: dict[str, Any] = {}
    for param in params:
        spec = priors[param]
        lo, hi = float(spec["plausible_range"][0]), float(spec["plausible_range"][1])
        grid = grid_from_range(lo, hi, args.samples)
        points: list[dict[str, Any]] = []
        n_failed = 0
        for idx, value in enumerate(grid):
            overlay = directory / f"{param.replace('.', '_')}_i{idx}.yaml"
            overlay.write_text(
                yaml.safe_dump(_nested_overlay(param, value), allow_unicode=True,
                               sort_keys=True), encoding="utf-8")
            seed_rows: dict[int, dict[str, Any]] = {}
            for seed in seeds:
                try:
                    run_name, metrics = _run_point(
                        param=param, idx=idx, seed=seed, ticks=args.ticks,
                        scenario=args.scenario, overlay=overlay, prefix=args.prefix)
                except (RuntimeError, FileExistsError, FileNotFoundError, ValueError) as exc:
                    n_failed += 1
                    print(f"[{param} i{idx}={value}] seed={seed} FAILED: {exc}")
                    continue
                seed_rows[seed] = metrics
                print(f"[{param} i{idx}={value}] seed={seed} -> {run_name}")
            points.append({
                "value": value,
                "n_seed_success": len(seed_rows),
                "by_seed": {str(s): {n: OUTCOMES[n](r) for n in OUTCOMES}
                            for s, r in sorted(seed_rows.items())},
                "agg": _point_stats(seed_rows),
            })
        per_param[param] = {
            "plausible_range": [lo, hi],
            "central": spec.get("central"),
            "unit": spec.get("unit"),
            "status": spec.get("status"),
            "grid": grid,
            "n_points": len(grid),
            "n_seed": len(seeds),
            "n_failed_runs": n_failed,
            "points": points,
            "sensitivity": _sensitivity(points),
        }

    payload = {
        "scenario": args.scenario,
        "mode": args.mode,
        "ticks": args.ticks,
        "seeds": seeds,
        "samples": args.samples,
        "outcomes": list(OUTCOMES),
        "method": ("one-at-a-time grid trên plausible_range (tất định); độ nhạy = range của "
                   "seed-median; nhiễu seed = spread giữa seed; KHÔNG tune, KHÔNG chọn param tốt nhất"),
        "params": per_param,
    }
    (directory / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(directory, payload)
    print(f"[xong] {directory.relative_to(ROOT) / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
