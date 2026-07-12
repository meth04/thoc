"""Sổ kép đa tài sản, đa chủ thể (điều luật #2).

Mọi dịch chuyển tài sản là một Transaction có bên nợ + bên có. Tài sản chỉ được
sinh/hủy qua mint/burn gắn với một luồng đã đăng ký trong FlowRegistry (điều luật #1).
Không có số dư âm — nợ là object riêng ở tầng hợp đồng, không phải số âm trong sổ.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EPSILON = 1e-9


class LoiSoKep(Exception):
    """Vi phạm quy tắc sổ kép: âm số dư, không cân, luồng chưa đăng ký."""


@dataclass(frozen=True)
class ButToan:
    """Một dòng bút toán: thay đổi `so_luong` (±) tài sản của một chủ thể."""

    chu_the: str
    tai_san: str
    so_luong: float


@dataclass(frozen=True)
class DongSinhHuy:
    """Sinh (+) hoặc hủy (−) tài sản, gắn với luồng đã đăng ký trong FlowRegistry."""

    chu_the: str
    tai_san: str
    so_luong: float  # dương = sinh (mint), âm = hủy (burn)
    luong: str


@dataclass(frozen=True)
class Transaction:
    tick: int
    ly_do: str
    but_toan: tuple[ButToan, ...] = ()
    sinh_huy: tuple[DongSinhHuy, ...] = ()


class FlowRegistry:
    """Đăng ký mọi luồng sinh/hủy hợp lệ của từng tài sản; tích lũy để audit đối chiếu."""

    def __init__(self) -> None:
        self._nguon: set[tuple[str, str]] = set()  # (tai_san, luong) được phép sinh
        self._sink: set[tuple[str, str]] = set()  # (tai_san, luong) được phép hủy
        self._tich_luy: dict[tuple[str, str], float] = {}  # net sinh−hủy theo (tai_san, luong)

    def dang_ky(self, tai_san: str, luong: str, loai: str) -> None:
        """loai: 'nguon' (sinh) hoặc 'sink' (hủy)."""
        if loai == "nguon":
            self._nguon.add((tai_san, luong))
        elif loai == "sink":
            self._sink.add((tai_san, luong))
        else:
            raise ValueError(f"loai phải là 'nguon' hoặc 'sink', nhận: {loai}")

    def cho_phep(self, tai_san: str, luong: str, so_luong: float) -> bool:
        key = (tai_san, luong)
        return key in self._nguon if so_luong > 0 else key in self._sink

    def ghi(self, tai_san: str, luong: str, so_luong: float) -> None:
        key = (tai_san, luong)
        self._tich_luy[key] = self._tich_luy.get(key, 0.0) + so_luong

    def tong_ky_vong(self, tai_san: str) -> float:
        """Tổng tồn tại kỳ vọng của tài sản = Σ sinh − Σ hủy đã ghi."""
        return sum(v for (ts, _), v in self._tich_luy.items() if ts == tai_san)

    def cac_tai_san(self) -> set[str]:
        return {ts for ts, _ in self._tich_luy}


@dataclass
class Ledger:
    """Sổ cái: số dư theo (chủ thể, tài sản) ≥ 0; lịch sử transaction append-only."""

    flows: FlowRegistry = field(default_factory=FlowRegistry)
    _so_du: dict[tuple[str, str], float] = field(default_factory=dict)
    _lich_su: list[Transaction] = field(default_factory=list)

    # ---------- đọc ----------
    def so_du(self, chu_the: str, tai_san: str) -> float:
        return self._so_du.get((chu_the, tai_san), 0.0)

    def tong_tai_san(self, tai_san: str) -> float:
        return sum(v for (_, ts), v in self._so_du.items() if ts == tai_san)

    def tai_san_cua(self, chu_the: str) -> dict[str, float]:
        return {ts: v for (ct, ts), v in self._so_du.items() if ct == chu_the and v > EPSILON}

    def cac_tai_san(self) -> set[str]:
        return {ts for _, ts in self._so_du}

    @property
    def lich_su(self) -> list[Transaction]:
        return self._lich_su

    # ---------- ghi ----------
    def ap_dung(self, tx: Transaction) -> None:
        """Áp dụng transaction NGUYÊN TỬ: kiểm tra hết trước, có lỗi thì không đổi gì."""
        # 0) NaN/inf không bao giờ được vào sổ — mọi so sánh với NaN đều False,
        # một số dư NaN sẽ qua mặt audit vĩnh viễn (điều luật #1)
        for dong in (*tx.but_toan, *tx.sinh_huy):
            if not math.isfinite(dong.so_luong):
                raise LoiSoKep(
                    f"Số lượng không hữu hạn: {dong.chu_the}/{dong.tai_san} = "
                    f"{dong.so_luong} ({tx.ly_do})"
                )
        delta_tai_san: dict[str, float] = {}
        for bt in tx.but_toan:
            if abs(bt.so_luong) <= EPSILON:
                continue
            delta_tai_san[bt.tai_san] = delta_tai_san.get(bt.tai_san, 0.0) + bt.so_luong
        # 1) Bút toán thường phải cân từng tài sản (nợ = có)
        for ts, tong in delta_tai_san.items():
            if abs(tong) > 1e-6:
                raise LoiSoKep(f"Transaction không cân cho '{ts}': lệch {tong} ({tx.ly_do})")
        # 2) Sinh/hủy phải qua luồng đã đăng ký
        for sh in tx.sinh_huy:
            if abs(sh.so_luong) <= EPSILON:
                continue
            if not self.flows.cho_phep(sh.tai_san, sh.luong, sh.so_luong):
                loai = "nguon" if sh.so_luong > 0 else "sink"
                raise LoiSoKep(
                    f"Luồng chưa đăng ký ({loai}): {sh.tai_san}/{sh.luong} ({tx.ly_do})"
                )
        # 3) Không chủ thể nào bị âm số dư sau transaction
        thay_doi: dict[tuple[str, str], float] = {}
        for bt in tx.but_toan:
            key = (bt.chu_the, bt.tai_san)
            thay_doi[key] = thay_doi.get(key, 0.0) + bt.so_luong
        for sh in tx.sinh_huy:
            key = (sh.chu_the, sh.tai_san)
            thay_doi[key] = thay_doi.get(key, 0.0) + sh.so_luong
        for key, delta in thay_doi.items():
            moi = self._so_du.get(key, 0.0) + delta
            if moi < -EPSILON:
                raise LoiSoKep(
                    f"Âm số dư: {key[0]} thiếu {key[1]} (còn {self._so_du.get(key, 0.0)}, "
                    f"cần {-delta}) ({tx.ly_do})"
                )
        # --- cam kết ---
        for key, delta in thay_doi.items():
            moi = self._so_du.get(key, 0.0) + delta
            if abs(moi) <= EPSILON:
                self._so_du.pop(key, None)  # dọn key 0 — sổ không phình vô hạn
            else:
                self._so_du[key] = moi
        for sh in tx.sinh_huy:
            if abs(sh.so_luong) > EPSILON:
                self.flows.ghi(sh.tai_san, sh.luong, sh.so_luong)
        self._lich_su.append(tx)

    # ---------- tiện ích ----------
    def chuyen(
        self, tu: str, den: str, tai_san: str, so_luong: float, ly_do: str, tick: int = 0
    ) -> None:
        if so_luong < -EPSILON:
            raise LoiSoKep(f"Số lượng chuyển phải ≥ 0, nhận {so_luong} ({ly_do})")
        self.ap_dung(
            Transaction(
                tick=tick,
                ly_do=ly_do,
                but_toan=(
                    ButToan(tu, tai_san, -so_luong),
                    ButToan(den, tai_san, +so_luong),
                ),
            )
        )

    def sinh(
        self, den: str, tai_san: str, so_luong: float, luong: str, ly_do: str, tick: int = 0
    ) -> None:
        if so_luong < -EPSILON:
            raise LoiSoKep(f"Số lượng sinh phải ≥ 0 ({ly_do})")
        self.ap_dung(
            Transaction(
                tick=tick, ly_do=ly_do, sinh_huy=(DongSinhHuy(den, tai_san, +so_luong, luong),)
            )
        )

    def huy(
        self, tu: str, tai_san: str, so_luong: float, luong: str, ly_do: str, tick: int = 0
    ) -> None:
        if so_luong < -EPSILON:
            raise LoiSoKep(f"Số lượng hủy phải ≥ 0 ({ly_do})")
        self.ap_dung(
            Transaction(
                tick=tick, ly_do=ly_do, sinh_huy=(DongSinhHuy(tu, tai_san, -so_luong, luong),)
            )
        )
