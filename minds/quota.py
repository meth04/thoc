"""Quota RPM/RPD theo ``(provider, model, key_hash)`` với SQLite bền vững.

RPM và một *reservation* RPD được ghi nhận nguyên tử tại admission, ngay trước HTTP.
RPM vẫn bị tiêu thụ bởi request đã bắt đầu dù lỗi/429.  Reservation RPD không phải call
thành công: nó được nhả khi request không thành công, hoặc được settle vào bộ đếm RPD khi
response hợp lệ được trả về.  Vì vậy hai process không thể cùng nhận "slot RPD cuối".
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class QuotaClaim:
    """Durable identity for one physical provider request admitted before HTTP."""

    claim_id: str
    provider: str
    model: str
    key_hash: str
    reserved_tokens: int


def _ky_rpd(now_ts: float, reset_hour: int) -> str:
    """Chu kỳ ngày hiện hành: nhãn ngày bắt đầu (lùi 1 ngày nếu chưa tới giờ reset)."""
    dt = datetime.fromtimestamp(now_ts)
    if dt.hour < reset_hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


class QuotaCounter:
    """Nguồn chân lý SQLite cho admission RPM, RPD và cooldown 429.

    ``nhan_slot_bat_dau`` dùng ``BEGIN IMMEDIATE`` để hai Gateway/process cùng database
    không thể cùng nhìn thấy một RPM slot cuối rồi cùng gửi request.  Mọi tham số thời gian
    được truyền rõ để kiểm thử clock giả không phụ thuộc mạng hay thời gian thật.
    """

    def __init__(self, duong_dan: Path | None, reset_hour: int = 8):
        self.reset_hour = reset_hour
        # Giữ tên thuộc tính cũ cho code/test legacy chỉ dọn cache nội bộ; RPM authoritative
        # nằm trong ``quota_rpm_starts`` nên restart hay process khác không làm mất admission.
        self._rpm: dict = {}
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            duong_dan if duong_dan else ":memory:", check_same_thread=False, timeout=30.0
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_counters (
                provider TEXT, model TEXT, key_hash TEXT, ky TEXT, so_call INTEGER,
                PRIMARY KEY (provider, model, key_hash, ky)
            )"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_rpm_starts (
                provider TEXT NOT NULL, model TEXT NOT NULL, key_hash TEXT NOT NULL,
                started_at REAL NOT NULL,
                claim_id TEXT
            )"""
        )
        # Additive migration: only claims created by the current implementation
        # need a durable RPM-row identity for a pre-HTTP rollback. Historic rows
        # retain NULL and continue to count normally in the sliding window.
        rpm_columns = {row[1] for row in self._conn.execute("PRAGMA table_info(quota_rpm_starts)")}
        if "claim_id" not in rpm_columns:
            self._conn.execute("ALTER TABLE quota_rpm_starts ADD COLUMN claim_id TEXT")
        # A row is created in the same transaction as RPM admission.  It is a
        # durable in-flight claim, not a successful/billable call, and must be
        # explicitly settled or released by the guarded provider path.
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_rpd_reservations (
                provider TEXT NOT NULL, model TEXT NOT NULL, key_hash TEXT NOT NULL,
                ky TEXT NOT NULL, so_slot INTEGER NOT NULL CHECK (so_slot >= 0),
                PRIMARY KEY (provider, model, key_hash, ky)
            )"""
        )
        # One durable claim per physical request. ``reserved_tokens`` is charged
        # conservatively at admission; only provider-reported total tokens may
        # replace it. A started request with unknown billability deliberately
        # retains this row/reservation until its natural TPM/RPD window expires.
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_token_claims (
                claim_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL, model TEXT NOT NULL, key_hash TEXT NOT NULL,
                ky TEXT NOT NULL, admitted_at REAL NOT NULL,
                reserved_tokens INTEGER NOT NULL CHECK (reserved_tokens >= 0),
                settled_tokens INTEGER CHECK (settled_tokens >= 0),
                status TEXT NOT NULL CHECK (status IN ('admitted','settled','unknown'))
            )"""
        )
        self._conn.execute(
            """CREATE INDEX IF NOT EXISTS quota_rpm_starts_window
               ON quota_rpm_starts (provider, model, key_hash, started_at)"""
        )
        self._conn.execute(
            """CREATE INDEX IF NOT EXISTS quota_token_claims_window
               ON quota_token_claims (provider, model, key_hash, admitted_at)"""
        )
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS quota_cooldowns (
                provider TEXT NOT NULL, key_hash TEXT NOT NULL,
                cooldown_den REAL NOT NULL, so_lan_429 INTEGER NOT NULL,
                PRIMARY KEY (provider, key_hash)
            )"""
        )
        self._conn.commit()

    def _bat_dau_giao_dich(self) -> None:
        """Mở write transaction serializable giữa các Counter/process cùng SQLite."""
        self._conn.execute("BEGIN IMMEDIATE")

    def _rollback_an_toan(self) -> None:
        if self._conn.in_transaction:
            self._conn.rollback()

    # ---------- đọc ----------
    def rpd_da_dung(self, provider: str, model: str, key_hash: str, now: float) -> int:
        ky = _ky_rpd(now, self.reset_hour)
        with self._lock:
            row = self._conn.execute(
                "SELECT so_call FROM quota_counters WHERE provider=? AND model=? AND"
                " key_hash=? AND ky=?", (provider, model, key_hash, ky)
            ).fetchone()
        return int(row[0]) if row else 0

    def rpm_hien_tai(self, provider: str, model: str, key_hash: str, now: float) -> int:
        """Số HTTP request đã *bắt đầu* trong 60 giây gần nhất, bền vững qua restart."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM quota_rpm_starts WHERE provider=? AND model=?"
                " AND key_hash=? AND started_at>?",
                (provider, model, key_hash, now - 60.0),
            ).fetchone()
        return int(row[0]) if row else 0

    def tpm_hien_tai(self, provider: str, model: str, key_hash: str, now: float) -> int:
        """Token đã hứa/dùng trong cửa sổ TPM 60 giây hiện tại.

        Claim chưa settle (kể cả started failure không rõ billing) giữ nguyên reservation;
        claim settle dùng đúng ``settled_tokens`` provider trả về, không dùng estimate nội bộ.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(COALESCE(settled_tokens,reserved_tokens)),0) "
                "FROM quota_token_claims WHERE provider=? AND model=? AND key_hash=? "
                "AND admitted_at>?",
                (provider, model, key_hash, now - 60.0),
            ).fetchone()
        return int(row[0]) if row else 0

    def rpd_da_du_tru(self, provider: str, model: str, key_hash: str, now: float) -> int:
        """Số RPD in-flight đã được admission trong chu kỳ hiện hành.

        Khác ``rpd_da_dung`` (success-only), giá trị này là phần sức chứa đã hứa
        cho request đang bay và phải được trừ khỏi mọi admission/preflight mới.
        """
        ky = _ky_rpd(now, self.reset_hour)
        with self._lock:
            row = self._conn.execute(
                "SELECT so_slot FROM quota_rpd_reservations WHERE provider=? AND model=?"
                " AND key_hash=? AND ky=?", (provider, model, key_hash, ky)
            ).fetchone()
        return int(row[0]) if row else 0

    def cooldown_den(self, provider: str, key_hash: str) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT cooldown_den FROM quota_cooldowns WHERE provider=? AND key_hash=?",
                (provider, key_hash),
            ).fetchone()
        return float(row[0]) if row else 0.0

    def dang_cooldown(self, provider: str, key_hash: str, now: float) -> bool:
        return self.cooldown_den(provider, key_hash) > now

    def cho_phep(self, provider: str, model: str, key_hash: str,
                 rpm: int, rpd: int, now: float) -> bool:
        """Kiểm tra đọc nhanh để chọn route; admission thực phải gọi hàm nguyên tử bên dưới."""
        if self.dang_cooldown(provider, key_hash, now):
            return False
        if self.rpm_hien_tai(provider, model, key_hash, now) >= rpm:
            return False
        return (self.rpd_da_dung(provider, model, key_hash, now)
                + self.rpd_da_du_tru(provider, model, key_hash, now)) < rpd

    def con_lai_rpd(self, provider: str, model: str, key_hashes: list[str],
                    rpd_moi_key: int, now: float) -> int:
        return sum(
            max(0, rpd_moi_key - self.rpd_da_dung(provider, model, kh, now)
                - self.rpd_da_du_tru(provider, model, kh, now))
            for kh in key_hashes
        )

    # ---------- admission/ghi bền vững ----------
    def nhan_slot_bat_dau(self, provider: str, model: str, key_hash: str,
                           rpm: int, rpd: int, now: float) -> bool:
        """Atomically reserve one RPM and one provisional RPD slot before HTTP.

        ``False`` means no request may leave the process.  The RPD reservation is
        success-neutral until :meth:`chot_call_du_tru` or :meth:`huy_call_du_tru`.
        """
        ky = _ky_rpd(now, self.reset_hour)
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                # Bounded retention: rows outside every possible current RPM window are
                # irrelevant.  The strict ``<=`` matches the window predicate below.
                self._conn.execute("DELETE FROM quota_rpm_starts WHERE started_at<=?", (now - 60.0,))
                cd = self._conn.execute(
                    "SELECT cooldown_den FROM quota_cooldowns WHERE provider=? AND key_hash=?",
                    (provider, key_hash),
                ).fetchone()
                if cd is not None and float(cd[0]) > now:
                    self._conn.rollback()
                    return False
                used_rpm = self._conn.execute(
                    "SELECT COUNT(*) FROM quota_rpm_starts WHERE provider=? AND model=?"
                    " AND key_hash=? AND started_at>?",
                    (provider, model, key_hash, now - 60.0),
                ).fetchone()[0]
                used_rpd_row = self._conn.execute(
                    "SELECT so_call FROM quota_counters WHERE provider=? AND model=?"
                    " AND key_hash=? AND ky=?",
                    (provider, model, key_hash, ky),
                ).fetchone()
                used_rpd = int(used_rpd_row[0]) if used_rpd_row else 0
                reserved_row = self._conn.execute(
                    "SELECT so_slot FROM quota_rpd_reservations WHERE provider=? AND model=?"
                    " AND key_hash=? AND ky=?", (provider, model, key_hash, ky)
                ).fetchone()
                reserved_rpd = int(reserved_row[0]) if reserved_row else 0
                if int(used_rpm) >= rpm or used_rpd + reserved_rpd >= rpd:
                    self._conn.rollback()
                    return False
                self._conn.execute(
                    "INSERT INTO quota_rpm_starts (provider, model, key_hash, started_at)"
                    " VALUES (?,?,?,?)",
                    (provider, model, key_hash, now),
                )
                self._conn.execute(
                    "INSERT INTO quota_rpd_reservations (provider, model, key_hash, ky, so_slot)"
                    " VALUES (?,?,?,?,1) ON CONFLICT (provider, model, key_hash, ky)"
                    " DO UPDATE SET so_slot = so_slot + 1",
                    (provider, model, key_hash, ky),
                )
                self._conn.commit()
                return True
            except Exception:
                self._rollback_an_toan()
                raise

    def nhan_claim_bat_dau(
        self, provider: str, model: str, key_hash: str, *, rpm: int, tpm: int,
        rpd: int, reserved_tokens: int, now: float, claim_id: str | None = None,
    ) -> QuotaClaim | None:
        """Atomically admit one physical request against RPM, TPM and RPD.

        ``reserved_tokens`` must already be a conservative request-specific upper
        bound. No HTTP may leave until this returns a claim. The opaque ID is then
        required for exact-once settlement; it prevents concurrent same-key calls
        from releasing or settling one another's provisional capacity.
        """
        if min(int(rpm), int(tpm), int(rpd)) < 1:
            raise ValueError("RPM/TPM/RPD phải là số nguyên dương")
        if int(reserved_tokens) < 0:
            raise ValueError("reserved_tokens không được âm")
        ky = _ky_rpd(now, self.reset_hour)
        claim = QuotaClaim(
            claim_id=claim_id or uuid4().hex,
            provider=provider,
            model=model,
            key_hash=key_hash,
            reserved_tokens=int(reserved_tokens),
        )
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                self._conn.execute("DELETE FROM quota_rpm_starts WHERE started_at<=?", (now - 60.0,))
                cd = self._conn.execute(
                    "SELECT cooldown_den FROM quota_cooldowns WHERE provider=? AND key_hash=?",
                    (provider, key_hash),
                ).fetchone()
                if cd is not None and float(cd[0]) > now:
                    self._conn.rollback()
                    return None
                used_rpm = int(self._conn.execute(
                    "SELECT COUNT(*) FROM quota_rpm_starts WHERE provider=? AND model=? "
                    "AND key_hash=? AND started_at>?",
                    (provider, model, key_hash, now - 60.0),
                ).fetchone()[0])
                used_tpm = int(self._conn.execute(
                    "SELECT COALESCE(SUM(COALESCE(settled_tokens,reserved_tokens)),0) "
                    "FROM quota_token_claims WHERE provider=? AND model=? AND key_hash=? "
                    "AND admitted_at>?",
                    (provider, model, key_hash, now - 60.0),
                ).fetchone()[0])
                used_rpd_row = self._conn.execute(
                    "SELECT so_call FROM quota_counters WHERE provider=? AND model=? "
                    "AND key_hash=? AND ky=?", (provider, model, key_hash, ky),
                ).fetchone()
                reserved_rpd_row = self._conn.execute(
                    "SELECT so_slot FROM quota_rpd_reservations WHERE provider=? AND model=? "
                    "AND key_hash=? AND ky=?", (provider, model, key_hash, ky),
                ).fetchone()
                used_rpd = int(used_rpd_row[0]) if used_rpd_row else 0
                reserved_rpd = int(reserved_rpd_row[0]) if reserved_rpd_row else 0
                if (used_rpm >= int(rpm) or used_tpm + claim.reserved_tokens > int(tpm)
                        or used_rpd + reserved_rpd >= int(rpd)):
                    self._conn.rollback()
                    return None
                self._conn.execute(
                    "INSERT INTO quota_rpm_starts (provider, model, key_hash, started_at, claim_id) "
                    "VALUES (?,?,?,?,?)", (provider, model, key_hash, now, claim.claim_id),
                )
                self._conn.execute(
                    "INSERT INTO quota_rpd_reservations (provider, model, key_hash, ky, so_slot) "
                    "VALUES (?,?,?,?,1) ON CONFLICT (provider, model, key_hash, ky) "
                    "DO UPDATE SET so_slot=so_slot+1", (provider, model, key_hash, ky),
                )
                self._conn.execute(
                    "INSERT INTO quota_token_claims "
                    "(claim_id,provider,model,key_hash,ky,admitted_at,reserved_tokens,status) "
                    "VALUES (?,?,?,?,?,?,?, 'admitted')",
                    (claim.claim_id, provider, model, key_hash, ky, now, claim.reserved_tokens),
                )
                self._conn.commit()
                return claim
            except Exception:
                self._rollback_an_toan()
                raise

    def _lay_du_tru_ky(self, provider: str, model: str, key_hash: str, ky: str) -> None:
        row = self._conn.execute(
            "SELECT so_slot FROM quota_rpd_reservations WHERE provider=? AND model=? "
            "AND key_hash=? AND ky=?", (provider, model, key_hash, ky),
        ).fetchone()
        if row is None or int(row[0]) < 1:
            raise RuntimeError("RPD reservation missing at provider claim settlement")
        if int(row[0]) == 1:
            self._conn.execute(
                "DELETE FROM quota_rpd_reservations WHERE provider=? AND model=? "
                "AND key_hash=? AND ky=?", (provider, model, key_hash, ky),
            )
        else:
            self._conn.execute(
                "UPDATE quota_rpd_reservations SET so_slot=so_slot-1 WHERE provider=? "
                "AND model=? AND key_hash=? AND ky=?", (provider, model, key_hash, ky),
            )

    def chot_claim(self, claim: QuotaClaim, provider_total_tokens: int) -> None:
        """Settle exactly this physical claim using provider-reported total tokens."""
        if int(provider_total_tokens) < 0:
            raise ValueError("provider_total_tokens không được âm")
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                row = self._conn.execute(
                    "SELECT ky,status FROM quota_token_claims WHERE claim_id=?", (claim.claim_id,)
                ).fetchone()
                if row is None or str(row[1]) != "admitted":
                    raise RuntimeError("quota claim missing or already settled")
                ky = str(row[0])
                self._lay_du_tru_ky(claim.provider, claim.model, claim.key_hash, ky)
                self._conn.execute(
                    "INSERT INTO quota_counters (provider,model,key_hash,ky,so_call) VALUES (?,?,?,?,1) "
                    "ON CONFLICT (provider,model,key_hash,ky) DO UPDATE SET so_call=so_call+1",
                    (claim.provider, claim.model, claim.key_hash, ky),
                )
                self._conn.execute(
                    "UPDATE quota_token_claims SET settled_tokens=?, status='settled' "
                    "WHERE claim_id=?", (int(provider_total_tokens), claim.claim_id),
                )
                self._conn.execute(
                    "UPDATE quota_cooldowns SET so_lan_429=0, cooldown_den=0 "
                    "WHERE provider=? AND key_hash=?", (claim.provider, claim.key_hash),
                )
                self._conn.commit()
            except Exception:
                self._rollback_an_toan()
                raise

    def huy_claim_truoc_khi_gui(self, claim: QuotaClaim) -> None:
        """Undo an admitted claim when no HTTP request left this process.

        Admission happens immediately before a send so RPM/TPM/RPD decisions are
        race-safe.  A subsequent local tick-budget denial is nevertheless not a
        provider request.  This exact rollback removes only the named claim and
        its RPM row; it must never be used once ``post`` has been invoked.
        """
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                row = self._conn.execute(
                    "SELECT ky,status FROM quota_token_claims WHERE claim_id=?", (claim.claim_id,)
                ).fetchone()
                if row is None or str(row[1]) != "admitted":
                    raise RuntimeError("quota claim missing or already started/settled")
                ky = str(row[0])
                self._lay_du_tru_ky(claim.provider, claim.model, claim.key_hash, ky)
                deleted = self._conn.execute(
                    "DELETE FROM quota_rpm_starts WHERE claim_id=?", (claim.claim_id,)
                ).rowcount
                if deleted != 1:
                    raise RuntimeError("RPM claim row missing at pre-send rollback")
                self._conn.execute(
                    "DELETE FROM quota_token_claims WHERE claim_id=?", (claim.claim_id,)
                )
                self._conn.commit()
            except Exception:
                self._rollback_an_toan()
                raise

    def giu_claim_khong_ro(self, claim: QuotaClaim) -> None:
        """Keep an admitted physical request reserved when provider billing is unknown."""
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                row = self._conn.execute(
                    "SELECT status FROM quota_token_claims WHERE claim_id=?", (claim.claim_id,)
                ).fetchone()
                if row is None:
                    raise RuntimeError("quota claim missing at unknown outcome")
                if str(row[0]) == "admitted":
                    self._conn.execute(
                        "UPDATE quota_token_claims SET status='unknown' WHERE claim_id=?",
                        (claim.claim_id,),
                    )
                elif str(row[0]) != "unknown":
                    raise RuntimeError("cannot retain an already settled quota claim")
                self._conn.commit()
            except Exception:
                self._rollback_an_toan()
                raise

    def _lay_mot_du_tru(self, provider: str, model: str, key_hash: str) -> str:
        """Consume one oldest provisional RPD slot inside an active transaction.

        Admission owns the accounting cycle even if a response straddles the
        provider's reset hour.  This prevents a pre-reset in-flight request
        from becoming an unreserved extra success in the new cycle.
        """
        row = self._conn.execute(
            "SELECT ky, so_slot FROM quota_rpd_reservations WHERE provider=? AND model=?"
            " AND key_hash=? AND so_slot>0 ORDER BY ky LIMIT 1",
            (provider, model, key_hash),
        ).fetchone()
        if row is None:
            raise RuntimeError("RPD reservation missing at provider settlement")
        ky, so_slot = str(row[0]), int(row[1])
        if so_slot == 1:
            self._conn.execute(
                "DELETE FROM quota_rpd_reservations WHERE provider=? AND model=?"
                " AND key_hash=? AND ky=?", (provider, model, key_hash, ky)
            )
        else:
            self._conn.execute(
                "UPDATE quota_rpd_reservations SET so_slot=so_slot-1 WHERE provider=?"
                " AND model=? AND key_hash=? AND ky=?", (provider, model, key_hash, ky)
            )
        return ky

    def huy_call_du_tru(self, provider: str, model: str, key_hash: str) -> None:
        """Release one admitted RPD reservation after a non-success outcome."""
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                self._lay_mot_du_tru(provider, model, key_hash)
                self._conn.commit()
            except Exception:
                self._rollback_an_toan()
                raise

    def chot_call_du_tru(self, provider: str, model: str, key_hash: str) -> None:
        """Settle one admitted reservation as a successful RPD call exactly once."""
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                ky = self._lay_mot_du_tru(provider, model, key_hash)
                self._conn.execute(
                    "INSERT INTO quota_counters (provider, model, key_hash, ky, so_call)"
                    " VALUES (?,?,?,?,1) ON CONFLICT (provider, model, key_hash, ky)"
                    " DO UPDATE SET so_call = so_call + 1",
                    (provider, model, key_hash, ky),
                )
                # A valid provider response proves the credential is usable again.
                self._conn.execute(
                    "UPDATE quota_cooldowns SET so_lan_429=0, cooldown_den=0"
                    " WHERE provider=? AND key_hash=?", (provider, key_hash)
                )
                self._conn.commit()
            except Exception:
                self._rollback_an_toan()
                raise

    def ghi_429(self, provider: str, key_hash: str, now: float,
                cooldown_goc_s: float, cooldown_toi_da_s: float) -> float:
        """Persist exponential 429 cooldown and return its expiry timestamp.

        Cooldown is scoped to provider/key (as in ``KeyPool``), not a model, because a
        provider normally rate-limits the credential itself.  A successful call resets the
        accumulated strike count in :meth:`ghi_call`.
        """
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                row = self._conn.execute(
                    "SELECT cooldown_den, so_lan_429 FROM quota_cooldowns"
                    " WHERE provider=? AND key_hash=?", (provider, key_hash)
                ).fetchone()
                failures = (int(row[1]) if row else 0) + 1
                duration = min(float(cooldown_goc_s) * (2 ** (failures - 1)),
                               float(cooldown_toi_da_s))
                expiry = max(float(row[0]) if row else 0.0, now + duration)
                self._conn.execute(
                    "INSERT INTO quota_cooldowns (provider, key_hash, cooldown_den, so_lan_429)"
                    " VALUES (?,?,?,?) ON CONFLICT(provider, key_hash) DO UPDATE SET"
                    " cooldown_den=excluded.cooldown_den, so_lan_429=excluded.so_lan_429",
                    (provider, key_hash, expiry, failures),
                )
                self._conn.commit()
                return expiry
            except Exception:
                self._rollback_an_toan()
                raise

    def ghi_call(self, provider: str, model: str, key_hash: str, now: float) -> None:
        """Record one successful response for RPD; never creates an RPM admission row."""
        ky = _ky_rpd(now, self.reset_hour)
        with self._lock:
            try:
                self._bat_dau_giao_dich()
                self._conn.execute(
                    "INSERT INTO quota_counters (provider, model, key_hash, ky, so_call)"
                    " VALUES (?,?,?,?,1) ON CONFLICT (provider, model, key_hash, ky)"
                    " DO UPDATE SET so_call = so_call + 1",
                    (provider, model, key_hash, ky),
                )
                # A successful provider response proves the credential is usable again.
                self._conn.execute(
                    "UPDATE quota_cooldowns SET so_lan_429=0, cooldown_den=0"
                    " WHERE provider=? AND key_hash=?",
                    (provider, key_hash),
                )
                self._conn.commit()
            except Exception:
                self._rollback_an_toan()
                raise


def cho_toi_rpm(quota: QuotaCounter, provider: str, model: str, key_hash: str,
                rpm: int, rpd: int, timeout_s: float = 90.0) -> bool:
    """Đợi tới khi một slot *có thể* mở; caller vẫn phải admission nguyên tử trước HTTP."""
    han = time.time() + timeout_s
    while time.time() < han:
        now = time.time()
        if quota.cho_phep(provider, model, key_hash, rpm, rpd, now):
            return True
        if (quota.rpd_da_dung(provider, model, key_hash, now)
                + quota.rpd_da_du_tru(provider, model, key_hash, now) >= rpd):
            return False  # RPD cạn/đã hứa hết — chờ vô ích trong phiên này
        time.sleep(1.0)
    return False
