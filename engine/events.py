"""events.jsonl — append-only, mọi sự kiện thế giới (điều luật #6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, duong_dan: Path | None):
        self._path = duong_dan
        self._f = None
        if duong_dan is not None:
            duong_dan.parent.mkdir(parents=True, exist_ok=True)
            self._f = open(duong_dan, "a", encoding="utf-8")  # noqa: SIM115

    def ghi(self, tick: int, loai: str, **du_lieu: Any) -> None:
        if self._f is None:
            return
        rec = {"tick": tick, "loai": loai, **du_lieu}
        self._f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def flush(self) -> None:
        if self._f is not None:
            self._f.flush()

    def dong(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None
