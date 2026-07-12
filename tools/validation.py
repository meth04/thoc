"""Kiểm tra package scenario và đánh giá moment ngoài/in-sample.

THÓC không được gọi một run là "khớp dữ liệu" chỉ vì biểu đồ trông hợp lý. Tool này
ép target có thời điểm, đơn vị, nguồn và dải chấp nhận; đồng thời phân biệt rõ
benchmark cơ chế (không có target) với scenario thực chứng.

Ví dụ:
  python -m tools.validation preindustrial_closed_v1
  python -m tools.validation my_historical_scenario --run ten_run
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from engine.config import load_config
from tools.experiments import ROOT, scenario_dir, validate_scenario

RUNS = ROOT / "data" / "runs"
REQUIRED_SCENARIO_FILES = (
    "scope.yaml", "parameters.yaml", "priors.yaml", "data_dictionary.md",
    "targets_in_sample.yaml", "targets_holdout.yaml", "policy_experiments.yaml",
    "provenance.csv",
)


@dataclass(frozen=True)
class Target:
    id: str
    metric: str
    tick: int
    unit: str
    source: str
    expected: float | None = None
    lower: float | None = None
    upper: float | None = None
    weight: float = 1.0


def _yaml_object(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} phải là YAML object")
    return value


def load_targets(scenario: str, split: str) -> list[Target]:
    if split not in {"in_sample", "holdout"}:
        raise ValueError("split phải là in_sample hoặc holdout")
    path = scenario_dir(scenario) / f"targets_{split}.yaml"
    raw = _yaml_object(path).get("targets", [])
    if not isinstance(raw, list):
        raise ValueError(f"{path}: targets phải là list")
    targets: list[Target] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{path}: mỗi target phải là object")
        missing = {"id", "metric", "unit", "source"} - set(item)
        if missing:
            raise ValueError(f"{path}: target thiếu {sorted(missing)}")
        if "tick" not in item and "year" not in item:
            raise ValueError(f"{path}: target {item['id']} thiếu tick hoặc year")
        tick = int(item.get("tick", int(item["year"]) * 2))
        expected = float(item["expected"]) if item.get("expected") is not None else None
        lower = float(item["lower"]) if item.get("lower") is not None else None
        upper = float(item["upper"]) if item.get("upper") is not None else None
        if expected is None and (lower is None or upper is None):
            raise ValueError(f"{path}: target {item['id']} cần expected hoặc [lower, upper]")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"{path}: target {item['id']} có lower > upper")
        target_id = str(item["id"])
        if target_id in seen:
            raise ValueError(f"{path}: target id trùng {target_id}")
        seen.add(target_id)
        targets.append(Target(
            id=target_id, metric=str(item["metric"]), tick=tick, unit=str(item["unit"]),
            source=str(item["source"]), expected=expected, lower=lower, upper=upper,
            weight=float(item.get("weight", 1.0)),
        ))
    return targets


# Status provenance KHÔNG được coi là "có nguồn thật": chuỗi rỗng (chưa điền) và
# design_assumption (số do người thiết kế đặt, chưa có evidence). So khớp sau .strip().lower().
NON_SOURCED_STATUS = {"", "design_assumption"}


def _empirical_ready(package: dict[str, Any]) -> bool:
    """Cổng thực chứng thuần, đọc từ các khóa package đã tính — tách để test độc lập.

    Một scenario CHỈ empirical_ready khi tier thuộc họ thực chứng VÀ đủ bằng chứng: không
    thiếu file/prior, không lỗi target, không rò rỉ holdout, có target in-sample + holdout,
    provenance đúng cột, source của target khác rỗng, và MỌI dòng provenance đã có nguồn
    thật (status ∉ {design_assumption, ""}) — siết W2 (ADR 0001 §Compliance).
    """
    return (
        str(package.get("validation_tier", "")).strip().lower() in EMPIRICAL_TIERS
        and not package.get("missing_files")
        and not package.get("invalid_priors")
        and not package.get("target_error")
        and not package.get("target_split_error")
        and bool(package.get("in_sample_targets"))
        and bool(package.get("holdout_targets"))
        and bool(package.get("provenance_ok"))
        and bool(package.get("targets_sourced"))
        and bool(package.get("provenance_all_sourced"))
    )


def validate_package(scenario: str) -> dict[str, Any]:
    """Xác nhận cấu trúc, prior và target trước khi chạy hiệu chuẩn."""
    scope = validate_scenario(scenario)
    directory = scenario_dir(scenario)
    missing_files = [name for name in REQUIRED_SCENARIO_FILES if not (directory / name).exists()]
    cfg = load_config(overlays=[directory / "parameters.yaml"])
    priors = _yaml_object(directory / "priors.yaml")
    invalid_priors = []
    for path, prior in priors.items():
        if not isinstance(prior, dict):
            invalid_priors.append(f"{path}: không phải object")
            continue
        try:
            cfg.get(str(path))
        except KeyError:
            invalid_priors.append(f"{path}: không có trong config")
        if not prior.get("unit") or not prior.get("status"):
            invalid_priors.append(f"{path}: thiếu unit/status")
    try:
        inputs = load_targets(scenario, "in_sample")
        holdout = load_targets(scenario, "holdout")
        target_error = None
    except ValueError as exc:
        inputs, holdout, target_error = [], [], str(exc)
    # Target split phải rời nhau: một id không được vừa ở in-sample vừa ở holdout (rò rỉ
    # calibration). Benchmark targets rỗng ⇒ không giao ⇒ None.
    overlap = sorted({t.id for t in inputs} & {t.id for t in holdout})
    target_split_error = (
        f"id target trùng giữa in_sample và holdout: {overlap}" if overlap else None
    )
    with open(directory / "provenance.csv", encoding="utf-8", newline="") as f:
        provenance = list(csv.DictReader(f))
    required_columns = {"parameter", "unit", "status", "source", "notes"}
    provenance_ok = bool(provenance) and required_columns <= set(provenance[0])
    # Mỗi dòng provenance phải có unit khác rỗng; thiếu thì BÁO (không raise) để package vẫn dùng được.
    missing_units = [
        str(row.get("parameter") or f"dòng {index}")
        for index, row in enumerate(provenance, start=1)
        if not str(row.get("unit") or "").strip()
    ]
    # W2: có nguồn thật khi MỌI dòng provenance có status ∉ {design_assumption, ""}.
    provenance_all_sourced = bool(provenance) and all(
        str(row.get("status") or "").strip().lower() not in NON_SOURCED_STATUS
        for row in provenance
    )
    tier = str(scope.get("validation_tier", ""))
    package = {
        "scenario": scenario,
        "validation_tier": tier,
        "missing_files": missing_files,
        "invalid_priors": invalid_priors,
        "target_error": target_error,
        "target_split_error": target_split_error,
        "in_sample_targets": len(inputs),
        "holdout_targets": len(holdout),
        "provenance_ok": provenance_ok,
        "missing_units": missing_units,
        "targets_sourced": all(target.source.strip() for target in [*inputs, *holdout]),
        "provenance_all_sourced": provenance_all_sourced,
    }
    package["empirical_ready"] = _empirical_ready(package)
    return package


# Nhãn hàm ý bằng chứng thực chứng — không được gán khi metadata chưa đủ (ADR 0001 §Compliance).
# Bao gồm mọi từ charter §2 cấm dùng khi thiếu evidence: empirical/calibrated/validated + các
# từ hàm ý nhân quả/dự báo/tầm-cỡ. So khớp sau khi .strip().lower().
EMPIRICAL_TIERS = {
    "empirical", "calibrated", "validated", "empirically_validated",
    "causal", "predictive", "world_class",
}


def claim_tier_label(package: dict[str, Any]) -> str:
    """Nhãn claim AN TOÀN NHẤT mà bằng chứng cho phép.

    Không bao giờ trả 'empirical' khi `empirical_ready` False. Dùng cho report/export để
    một benchmark cơ chế không thể vô tình in nhãn thực chứng.
    """
    return "empirical" if package.get("empirical_ready") else "mechanism_benchmark"


def assert_no_overclaim(package: dict[str, Any]) -> None:
    """Chặn scenario tự nhận empirical/calibrated/validated khi target/provenance chưa đủ.

    Raise `ValueError` mô tả nếu `validation_tier` thuộc họ thực chứng nhưng `empirical_ready`
    là False. Đây là documentation/test gate của T01 (ADR 0001): benchmark không có target
    không phải fail, nhưng KHÔNG được đội nhãn thực chứng.
    """
    tier = str(package.get("validation_tier", "")).strip().lower()
    if tier in EMPIRICAL_TIERS and not package.get("empirical_ready"):
        raise ValueError(
            f"Scenario '{package.get('scenario')}' khai báo validation_tier='{tier}' nhưng "
            f"thiếu bằng chứng (empirical_ready=False: missing_files={package.get('missing_files')}, "
            f"target_error={package.get('target_error')}, target_split_error={package.get('target_split_error')}, "
            f"in_sample={package.get('in_sample_targets')}, holdout={package.get('holdout_targets')}, "
            f"provenance_ok={package.get('provenance_ok')}, "
            f"provenance_all_sourced={package.get('provenance_all_sourced')}). "
            "Không được export nhãn empirical/validated khi target/provenance rỗng hoặc chỉ là design_assumption."
        )


def evaluate_targets(metrics: list[dict[str, Any]], targets: list[Target]) -> list[dict[str, Any]]:
    """So moment mô phỏng với target đã khóa trước; không thay đổi world/config."""
    by_tick = {int(row["tick"]): row for row in metrics if "tick" in row}
    results: list[dict[str, Any]] = []
    for target in targets:
        row = by_tick.get(target.tick)
        if row is None or target.metric not in row:
            results.append({"id": target.id, "status": "missing", "metric": target.metric,
                            "tick": target.tick, "unit": target.unit})
            continue
        actual = float(row[target.metric])
        lower = target.lower
        upper = target.upper
        if lower is None and upper is None and target.expected is not None:
            lower = upper = target.expected
        within = (lower is None or actual >= lower) and (upper is None or actual <= upper)
        centre = target.expected if target.expected is not None else (lower + upper) / 2
        scale = max(abs(centre), abs((upper or centre) - (lower or centre)), 1e-9)
        results.append({
            "id": target.id, "status": "pass" if within else "fail", "metric": target.metric,
            "tick": target.tick, "unit": target.unit, "actual": actual,
            "expected": target.expected, "lower": lower, "upper": upper,
            "normalized_error": abs(actual - centre) / scale,
            "weight": target.weight, "source": target.source,
        })
    return results


def _metrics_from_run(run: str) -> list[dict[str, Any]]:
    path = RUNS / run / "metrics.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Không có metrics của run: {run}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra scenario và target thực chứng")
    parser.add_argument("scenario")
    parser.add_argument("--run", help="đánh giá target trên data/runs/<name>")
    args = parser.parse_args(argv)
    package = validate_package(args.scenario)
    package["safe_claim_label"] = claim_tier_label(package)
    print(json.dumps(package, ensure_ascii=False, indent=2))
    # Gate chống overclaim (ADR 0001): scenario tự nhận empirical mà thiếu bằng chứng → fail.
    try:
        assert_no_overclaim(package)
    except ValueError as exc:
        print(f"OVERCLAIM: {exc}")
        return 2
    if not args.run:
        return 0 if not package["missing_files"] and not package["invalid_priors"] else 1
    metrics = _metrics_from_run(args.run)
    try:
        results = {
            split: evaluate_targets(metrics, load_targets(args.scenario, split))
            for split in ("in_sample", "holdout")
        }
    except ValueError as exc:
        print(f"TARGET_ERROR: {exc}")
        return 1
    output = RUNS / args.run / "scenario_validation.json"
    output.write_text(json.dumps({"package": package, "results": results}, ensure_ascii=False,
                                 indent=2), encoding="utf-8")
    print(f"Đã ghi {output.relative_to(ROOT)}")
    # Benchmark không có target không phải fail kỹ thuật; chỉ không được gọi empirical_ready.
    failures = [r for rows in results.values() for r in rows if r["status"] != "pass"]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
