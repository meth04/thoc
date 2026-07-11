"""Nạp cấu hình YAML — mọi tham số nằm trong config/, không hardcode trong code."""

from __future__ import annotations

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


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(config_dir: Path | None = None) -> Config:
    """Nạp world.yaml + models.yaml + quotas.yaml + research.yaml thành một Config."""
    d = config_dir or CONFIG_DIR
    data: dict[str, Any] = {}
    data.update(load_yaml(d / "world.yaml"))
    data["models"] = load_yaml(d / "models.yaml")
    data["quotas"] = load_yaml(d / "quotas.yaml")
    data["research"] = load_yaml(d / "research.yaml")
    return Config(data)
