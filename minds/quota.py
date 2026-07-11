"""Bộ đếm quota RPM/RPD theo (provider, model, key) — persist SQLite, restart không quên.

RPD reset theo reset_hour_local (quotas.yaml). Budget guard: thiếu → dừng êm,
KHÔNG degrade tier (điều luật #7: không đánh tráo trí thông minh).
"""

from __future__ import annotations

import sqlite3
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path


def _ky_rpd(now_ts: float, reset_hour: int) -> str:
    """Chu kỳ ngày hiện hành: nhãn ngày bắt đầu (lùi 1 ngày nếu chưa tới giờ reset)."""
    dt = datetime.fromtimestamp(now_ts)
    if dt.hour < reset_hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


class QuotaCounter:
    def __init__(self, duong_dan: Path | None, reset_hour: int = 8):
        self.reset_hour = reset_hour
        self._rpm: dict[tuple[str, str, str], deque] = {}
        self._conn = sqlite3.connect(duong_dan) if duong_dan else sqlite3.connect(":memory:")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_counters (
                provider TEXT, model TEXT, key_hash TEXT, ky TEXT, so_call INTEGER,
                PRIMARY KEY (provider, model, key_hash, ky)
            )"""
        )
        self._conn.commit()

    # ---------- đọc ----------
    def rpd_da_dung(self, provider: str, model: str, key_hash: str, now: float) -> int:
        ky = _ky_rpd(now, self.reset_hour)
        row = self._conn.execute(
            "SELECT so_call FROM quota_counters WHERE provider=? AND model=? AND key_hash=?"
            " AND ky=?", (provider, model, key_hash, ky)
        ).fetchone()
        return row[0] if row else 0

    def rpm_hien_tai(self, provider: str, model: str, key_hash: str, now: float) -> int:
        dq = self._rpm.get((provider, model, key_hash))
        if not dq:
            return 0
        while dq and dq[0] <= now - 60.0:
            dq.popleft()
        return len(dq)

    def cho_phep(self, provider: str, model: str, key_hash: str,
                 rpm: int, rpd: int, now: float) -> bool:
        if self.rpm_hien_tai(provider, model, key_hash, now) >= rpm:
            return False
        return self.rpd_da_dung(provider, model, key_hash, now) < rpd

    def con_lai_rpd(self, provider: str, model: str, key_hashes: list[str],
                    rpd_moi_key: int, now: float) -> int:
        return sum(
            max(0, rpd_moi_key - self.rpd_da_dung(provider, model, kh, now))
            for kh in key_hashes
        )

    # ---------- ghi ----------
    def ghi_call(self, provider: str, model: str, key_hash: str, now: float) -> None:
        self._rpm.setdefault((provider, model, key_hash), deque()).append(now)
        ky = _ky_rpd(now, self.reset_hour)
        self._conn.execute(
            "INSERT INTO quota_counters (provider, model, key_hash, ky, so_call)"
            " VALUES (?,?,?,?,1) ON CONFLICT (provider, model, key_hash, ky)"
            " DO UPDATE SET so_call = so_call + 1",
            (provider, model, key_hash, ky),
        )
        self._conn.commit()


def cho_toi_rpm(quota: QuotaCounter, provider: str, model: str, key_hash: str,
                rpm: int, rpd: int, timeout_s: float = 90.0) -> bool:
    """Đợi tới khi slot RPM mở (token-bucket kiểu cửa sổ trượt 60s)."""
    han = time.time() + timeout_s
    while time.time() < han:
        now = time.time()
        if quota.cho_phep(provider, model, key_hash, rpm, rpd, now):
            return True
        if quota.rpd_da_dung(provider, model, key_hash, now) >= rpd:
            return False  # RPD cạn — chờ vô ích trong phiên này
        time.sleep(1.0)
    return False
