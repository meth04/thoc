"""Cây RNG tất định — một seed gốc, spawn Generator theo (subsystem, tick).

Điều luật #4: cùng seed → cùng thế giới. Mọi ngẫu nhiên trong engine phải đi qua đây;
không module nào được tự tạo Generator riêng.
"""

from __future__ import annotations

import hashlib

import numpy as np


def _ten_thanh_so(ten: str) -> int:
    """Băm tên subsystem thành số nguyên ổn định (không phụ thuộc hash() của Python)."""
    return int.from_bytes(hashlib.sha256(ten.encode("utf-8")).digest()[:8], "big")


class RngTree:
    """Cây RNG: root seed → Generator con theo (subsystem, tick), tất định tuyệt đối."""

    def __init__(self, seed: int):
        self.seed = int(seed)

    def get(self, subsystem: str, tick: int = 0) -> np.random.Generator:
        """Generator tất định cho (subsystem, tick). Gọi lại cùng cặp → cùng chuỗi số."""
        ss = np.random.SeedSequence(
            entropy=self.seed, spawn_key=(_ten_thanh_so(subsystem), int(tick))
        )
        return np.random.default_rng(ss)
