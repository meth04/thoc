"""Hạ tầng thí nghiệm tái lập cho THÓC.

Module này không chạy mô phỏng và không biết LLM. Nó chỉ đóng gói ngữ cảnh của một
run (scenario, config đã ghép, overlay, code revision) thành manifest bất biến để
kết quả sau này có thể được kiểm tra hoặc tái lập.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = ROOT / "scenarios"
MANIFEST_SCHEMA = 1


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Mọi file chứa CODE RENDER PROMPT. Băm một file là không đủ: sau P0.1, thân hàm render
# (`_gt_xay`, `mo_ta_cong_thuc`, …) sống ở `minds/capabilities.py`, trong khi
# `capability_catalog_hash` chỉ băm *khai báo* + bảng render, KHÔNG băm thân hàm. Sửa một thân
# hàm sẽ đổi prompt của MỌI agent trong khi cả hai hash đứng yên ⇒ resume/replay không phát hiện.
FILE_RENDER_PROMPT = ("prompts.py", "capabilities.py")


def prompt_template_hash() -> str | None:
    """sha256 của TOÀN BỘ code render prompt (một nguồn sự thật cho run.py + tools/replay.py).

    Hai nơi tự tính riêng thì identity check sẽ so hai con số khác nhau và luôn báo lệch.
    """
    goc = ROOT / "minds"
    phan = [sha256_file(goc / ten) for ten in FILE_RENDER_PROMPT if (goc / ten).exists()]
    if not phan:
        return None
    return hashlib.sha256("".join(phan).encode("utf-8")).hexdigest()


def git_revision() -> str | None:
    """Đọc commit hiện tại nếu git khả dụng; không làm run thất bại khi không có git."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _load_yaml_object(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        value = yaml.safe_load(f) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} phải là YAML object")
    return value


def scenario_dir(name: str) -> Path:
    """Trả về scenario nằm trong repo; chặn path traversal từ CLI."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Tên scenario không hợp lệ")
    path = SCENARIOS_DIR / name
    if not path.is_dir():
        raise FileNotFoundError(f"Không tìm thấy scenario: {name}")
    return path


def validate_scenario(name: str) -> dict[str, Any]:
    """Kiểm tra metadata tối thiểu, trả về scope để ghi manifest."""
    directory = scenario_dir(name)
    scope_path = directory / "scope.yaml"
    if not scope_path.exists():
        raise FileNotFoundError(f"Scenario {name} thiếu scope.yaml")
    scope = _load_yaml_object(scope_path)
    required = {"name", "scope", "unit_of_analysis", "boundaries", "exclusions"}
    missing = sorted(required - set(scope))
    if missing:
        raise ValueError(f"Scenario {name} thiếu trường scope: {', '.join(missing)}")
    if str(scope["name"]) != name:
        raise ValueError(f"scope.name phải bằng tên thư mục scenario ({name})")
    return scope


def scenario_overlay(name: str) -> Path | None:
    """Overlay tham số của scenario, nếu scenario có thay config gốc."""
    path = scenario_dir(name) / "parameters.yaml"
    return path if path.exists() else None


def build_manifest(*, run_name: str, mode: str, seed: int, ticks_requested: int,
                   config_digest: str, config_overlays: list[Path],
                   scenario: str | None, treatments: list[str] | None = None,
                   policy: dict | None = None, prompt_template_hash: str | None = None,
                   model_snapshot: list[str] | None = None,
                   temperature: Any = None, calendar: dict[str, Any] | None = None,
                   run_uuid: str | None = None,
                   capability_catalog_hash: str | None = None) -> dict[str, Any]:
    """Tạo metadata đủ để phân biệt hai run có cùng seed nhưng khác giả định.

    ``prompt_template_hash`` (sha256 của minds/prompts.py), ``model_snapshot`` (danh sách
    provider/model dùng) và ``temperature`` biến prompt/model từ hộp đen thành *treatment
    có version* (P1 reproducibility) — kwarg optional, không phá chữ ký cũ.

    ``capability_catalog_hash`` (ADR 0006 §A.2) băm NỘI DUNG KHAI BÁO của catalog (không băm
    file) ⇒ refactor thuần không đổi hash, đổi interface thì đổi. Cùng với
    ``prompt_template_hash`` nó biến "prompt identity" từ niềm tin thành phép so hash: replay
    chỉ hợp lệ khi code hiện tại quảng cáo ĐÚNG tập action mà run gốc đã quảng cáo.

    ``run_uuid`` (ADR 0006 §C.2) nối manifest với ``checkpoints/journal_manifest.json`` và
    với từng dòng transcript. Nó là **metadata thuần**: CẤM đưa vào RNG/prompt/``world_hash``
    (INV-J7) — nếu không, hai run cùng seed sẽ khác hash chỉ vì khác uuid.
    """
    scope: dict[str, Any] | None = None
    scenario_files: dict[str, str] = {}
    if scenario is not None:
        scope = validate_scenario(scenario)
        directory = scenario_dir(scenario)
        scenario_files = {
            str(p.relative_to(ROOT)).replace("\\", "/"): sha256_file(p)
            for p in sorted(directory.glob("*")) if p.is_file()
        }
    overlay_items = []
    for path in config_overlays:
        resolved = path.resolve()
        overlay_items.append({
            "path": str(resolved),
            "sha256": sha256_file(resolved),
        })
    return {
        "schema_version": MANIFEST_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "run": {
            "name": run_name,
            "mode": mode,
            "seed": seed,
            "ticks_requested": ticks_requested,
            "run_uuid": run_uuid,
        },
        "reproducibility": {
            "config_sha256": config_digest,
            "config_overlays": overlay_items,
            "scenario": scenario,
            "treatments": list(treatments or []),
            "policy": policy,
            "scenario_scope": scope,
            "scenario_files_sha256": scenario_files,
            "prompt_template_hash": prompt_template_hash,
            "capability_catalog_hash": capability_catalog_hash,
            "model_snapshot": list(model_snapshot) if model_snapshot is not None else None,
            "temperature": temperature,
            # Calendar thực chạy tách khỏi mô tả scope chung: scenario có thể có overlay
            # seasonal variant nên một tên scenario không đủ để suy ra tick/năm.
            "calendar": calendar,
            "git_revision": git_revision(),
            "python": sys.version,
        },
    }


def write_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "experiment_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def update_manifest_outcome(run_dir: Path, outcome: dict[str, Any]) -> Path:
    path = run_dir / "experiment_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["outcome"] = outcome
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def permute_personas(world) -> None:
    """Hoán đổi persona tất định giữa người sống, giữ nguyên địa lý/tài sản.

    Đây là counterfactual C2, không phải nguồn ngẫu nhiên trong engine. Nó tách tác
    động của dị biệt hành vi khỏi bản đồ và phân bổ ban đầu; treatment luôn được ghi
    trong manifest bởi ``run.py``.
    """
    ids = sorted(aid for aid, a in world.agents.items() if a.con_song)
    if len(ids) < 2:
        return
    personas = [world.agents[aid].persona for aid in ids]
    order = world.rng.get("counterfactual_persona", 0).permutation(len(ids))
    for aid, index in zip(ids, order, strict=True):
        world.agents[aid].persona = personas[int(index)]
