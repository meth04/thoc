"""Audit bảo toàn (điều luật #1) — chạy SAU MỖI TICK, lệch là raise, không đi tiếp.

Đối chiếu tổng tồn tại từng tài sản trong sổ cái với tổng kỳ vọng của FlowRegistry
(Σ sinh − Σ hủy đã đăng ký). Mọi luồng "lậu" — tài sản xuất hiện/biến mất ngoài sổ —
đều làm hai con số này lệch nhau và bị bắt tại đây.
"""

from __future__ import annotations

from engine.ledger import EPSILON, Ledger

DUNG_SAI = 1e-6


class LoiBaoToan(Exception):
    """Phương trình bảo toàn tài nguyên bị vi phạm."""


def kiem_toan(ledger: Ledger, tick: int = -1) -> None:
    """Assert bảo toàn từng tài sản + không âm số dư. Lệch → raise LoiBaoToan."""
    loi: list[str] = []
    tai_san_all = ledger.cac_tai_san() | ledger.flows.cac_tai_san()
    for ts in sorted(tai_san_all):
        thuc_te = ledger.tong_tai_san(ts)
        ky_vong = ledger.flows.tong_ky_vong(ts)
        if abs(thuc_te - ky_vong) > DUNG_SAI:
            loi.append(
                f"'{ts}': sổ cái có {thuc_te}, FlowRegistry kỳ vọng {ky_vong} "
                f"(lệch {thuc_te - ky_vong})"
            )
    for (chu_the, ts), v in ledger._so_du.items():
        if v < -EPSILON:
            loi.append(f"Âm số dư: {chu_the}/{ts} = {v}")
    if loi:
        raise LoiBaoToan(f"[tick {tick}] Vi phạm bảo toàn:\n  " + "\n  ".join(loi))
