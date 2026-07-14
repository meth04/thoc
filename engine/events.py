"""events.jsonl — append-only, mọi sự kiện thế giới (điều luật #6).

``seq`` là số thứ tự **đơn điệu, duy nhất TOÀN RUN** (không reset khi resume): nó được gieo
lại từ ``record_count`` của checkpoint đang nạp (``engine/journal.py`` — manifest là bản
checkpoint của counter). INVARIANT (JOURNAL-1/INV-J2): ``seq`` tăng nghiêm ngặt, không gap,
không lặp trong file live.

Counter KHÔNG thuộc ``World``: ``World.luu_checkpoint`` hoán ``events`` ra ``EventLog(None)``
trước khi pickle (``engine/world.py:590``) nên counter đặt trong World cũng không sống sót
checkpoint; và một field của World nằm ngoài ``behavioral_state()`` là một hash-boundary
hazard thường trực. Journal writer tự sở hữu counter của nó (model-architect D4).

``seq``/``seg`` là metadata journal — KHÔNG vào ``behavioral_state()``/``world_hash``
(``engine/world.py:460-570`` không chứa event journal) ⇒ thêm field ở đây **không đổi hash**.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, duong_dan: Path | None, *, start_seq: int = 0,
                 segment_id: int = 0):
        self._path = duong_dan
        self._f = None
        self._seq = int(start_seq)
        self._segment_id = int(segment_id)
        if duong_dan is not None:
            duong_dan.parent.mkdir(parents=True, exist_ok=True)
            self._f = open(duong_dan, "a", encoding="utf-8")  # noqa: SIM115

    @property
    def seq(self) -> int:
        """Số record đã ghi (toàn run, gồm cả các segment trước)."""
        return self._seq

    def ghi(self, tick: int, loai: str, **du_lieu: Any) -> None:
        if self._f is None:
            return
        self._seq += 1
        rec = {"seq": self._seq, "seg": self._segment_id, "tick": tick, "loai": loai,
               **du_lieu}
        self._f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def flush(self) -> None:
        if self._f is not None:
            self._f.flush()

    def fsync(self) -> None:
        """Đẩy xuống đĩa TRƯỚC khi capture byte_offset: offset không fsync là offset nói dối."""
        if self._f is not None:
            self._f.flush()
            os.fsync(self._f.fileno())

    def dong(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None
