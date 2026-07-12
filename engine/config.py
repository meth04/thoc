"""Nạp cấu hình YAML — mọi tham số nằm trong config/, không hardcode trong code."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class Config:
    """Bọc dict cấu hình, truy cập bằng đường dẫn chấm: cfg.get("san_xuat.recipe.nha.cong")."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self._data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                if default is not None:
                    return default
                raise KeyError(f"Thiếu khóa cấu hình: {path}")
            node = node[key]
        return node

    def raw(self) -> dict[str, Any]:
        return self._data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def digest(self) -> str:
        """Dấu vân tay ổn định của cấu hình thực sự đã nạp.

        Mọi run khoa học phải ghi dấu này thay vì chỉ ghi tên file YAML: cùng tên
        scenario nhưng khác một tham số cũng là một thí nghiệm khác.
        """
        blob = json.dumps(self._data, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Ghép đệ quy overlay vào cấu hình.

    Dict được ghép theo khóa; list/scalar được thay trọn vẹn. Hàm không đổi input
    để cùng một config gốc có thể dùng an toàn cho nhiều scenario/phản chứng.
    """
    out = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(config_dir: Path | None = None,
                overlays: list[Path] | None = None) -> Config:
    """Nạp config gốc và các overlay scenario/phản chứng theo thứ tự.

    Overlay là YAML chứa đúng các nhánh cần thay đổi. Đây là cách duy nhất được
    hỗ trợ để chạy phản chứng, tránh sửa tạm ``config/world.yaml`` rồi quên hoàn
    nguyên — một nguồn làm mất tái lập rất thường gặp ở ABM.
    """
    d = config_dir or CONFIG_DIR
    data: dict[str, Any] = {}
    data.update(load_yaml(d / "world.yaml"))
    data["models"] = load_yaml(d / "models.yaml")
    data["quotas"] = load_yaml(d / "quotas.yaml")
    data["research"] = load_yaml(d / "research.yaml")
    for overlay in overlays or []:
        if not overlay.exists():
            raise FileNotFoundError(f"Không tìm thấy config overlay: {overlay}")
        raw = load_yaml(overlay)
        if not isinstance(raw, dict):
            raise ValueError(f"Overlay phải là YAML object: {overlay}")
        data = deep_merge(data, raw)
    return Config(data)
