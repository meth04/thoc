"""Nạp key từ .env bằng regex (SPEC 7.1) + xoay key với cooldown 429 lũy tiến.

Tên biến có gạch ngang (GEMINI-API-KEY-1) không hợp lệ với shell — đọc file trực tiếp.
Key KHÔNG BAO GIỜ xuất hiện trong log: chỉ sha256[:8].
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

RE_GEMINI = re.compile(r"^\s*(GEMINI[-_]API[-_]KEY[-_](\d+))\s*=\s*(.+)$", re.IGNORECASE)
RE_NINE_KEY = re.compile(r"^\s*NINE[-_]?ROUTER[-_]API[-_]KEY\s*=\s*(.+)$", re.IGNORECASE)
RE_NINE_URL = re.compile(r"^\s*NINE[-_]?ROUTER[-_]BASE[-_]URL\s*=\s*(.+)$", re.IGNORECASE)
RE_MODE = re.compile(r"^\s*LLM_MODE\s*=\s*(\w+)", re.IGNORECASE)


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


@dataclass
class EnvKeys:
    gemini_keys: list[str] = field(default_factory=list)
    nine_key: str = ""
    nine_base: str = ""
    llm_mode: str = "mock"

    def co_key_that(self) -> bool:
        hop_le = [k for k in self.gemini_keys if not k.startswith("dien_key")]
        return bool(hop_le)


def nap_env(duong_dan: Path) -> EnvKeys:
    ket_qua = EnvKeys()
    if not duong_dan.exists():
        return ket_qua
    theo_stt: list[tuple[int, str]] = []
    for line in duong_dan.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        m = RE_GEMINI.match(line)
        if m:
            theo_stt.append((int(m.group(2)), m.group(3).strip()))
            continue
        m = RE_NINE_KEY.match(line)
        if m:
            ket_qua.nine_key = m.group(1).strip()
            continue
        m = RE_NINE_URL.match(line)
        if m:
            ket_qua.nine_base = m.group(1).strip().rstrip("/")
            continue
        m = RE_MODE.match(line)
        if m:
            ket_qua.llm_mode = m.group(1).strip().lower()
    ket_qua.gemini_keys = [k for _, k in sorted(theo_stt)]
    return ket_qua


@dataclass
class _TrangThaiKey:
    key: str
    cooldown_den: float = 0.0
    so_lan_429: int = 0


class KeyPool:
    """Bể key AN TOÀN LUỒNG (kiến trúc 1-to-1 gọi từ nhiều thread). 429 → cooldown lũy
    tiến (60s × 2^n). Với NHIỀU key (20-30), chọn key theo TẢI (lay_key_tot_nhat) thay
    vì xoay vòng mù — key rảnh nhất được ưu tiên, key cạn RPM/RPD bị bỏ qua."""

    def __init__(self, keys: list[str], cooldown_goc_s: float = 60.0):
        self._keys = [_TrangThaiKey(k) for k in keys]
        self._i = 0
        self._cooldown_goc = cooldown_goc_s
        self._lock = threading.Lock()

    def so_key(self) -> int:
        return len(self._keys)

    def key_kha_dung(self, now: float) -> list[str]:
        """Danh sách key KHÔNG đang cooldown (thread-safe) — để tầng trên chấm điểm/giữ chỗ."""
        with self._lock:
            return [ts.key for ts in self._keys if ts.cooldown_den <= now]

    def lay_key(self, now: float) -> str | None:
        """Xoay vòng (chỉ tránh cooldown) — cho lối gọi đơn giản/nền một key."""
        with self._lock:
            n = len(self._keys)
            for _ in range(n):
                ts = self._keys[self._i % n]
                self._i += 1
                if ts.cooldown_den <= now:
                    return ts.key
            return None

    def lay_key_tot_nhat(self, now: float,
                         diem_fn: Callable[[str], float | None]) -> str | None:
        """Chọn key KHẢ DỤNG (không cooldown) có ĐIỂM cao nhất. diem_fn(key) trả điểm
        (cao = rảnh hơn, nên chọn) hoặc None (key này không dùng được, vd cạn RPM/RPD).
        Hết key dùng được → None. Tie-break theo key_hash cho ổn định."""
        with self._lock:
            ung_vien: list[tuple[float, str, str]] = []
            for ts in self._keys:
                if ts.cooldown_den > now:
                    continue
                diem = diem_fn(ts.key)
                if diem is None:
                    continue
                ung_vien.append((diem, key_hash(ts.key), ts.key))
            if not ung_vien:
                return None
            ung_vien.sort(key=lambda x: (-x[0], x[1]))
            return ung_vien[0][2]

    def bao_429(self, key: str, now: float) -> None:
        with self._lock:
            for ts in self._keys:
                if ts.key == key:
                    ts.so_lan_429 += 1
                    ts.cooldown_den = now + self._cooldown_goc * (2 ** (ts.so_lan_429 - 1))
                    return

    def bao_ok(self, key: str) -> None:
        with self._lock:
            for ts in self._keys:
                if ts.key == key:
                    ts.so_lan_429 = 0
                    return

    def con_kha_dung(self, now: float) -> int:
        with self._lock:
            return sum(1 for ts in self._keys if ts.cooldown_den <= now)
