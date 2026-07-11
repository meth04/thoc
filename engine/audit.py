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


def kiem_toan_the_gioi(w, tong_thua_ban_dau: int) -> None:
    """Audit toàn cục sau mỗi tick: sổ cái + đất + công bốc hơi hết."""
    kiem_toan(w.ledger, w.tick)
    loi: list[str] = []
    if len(w.parcels) != tong_thua_ban_dau:
        loi.append(f"Tổng thửa đổi: {len(w.parcels)} ≠ {tong_thua_ban_dau}")
    for p in w.parcels.values():
        if p.chu is not None and p.chu not in w.agents and not p.chu.startswith("E"):
            loi.append(f"Thửa {p.id} có chủ không tồn tại: {p.chu}")
    tong_cong = w.ledger.tong_tai_san("cong")
    if abs(tong_cong) > DUNG_SAI:
        loi.append(f"Công không bốc hơi hết cuối tick: còn {tong_cong}")
    if loi:
        raise LoiBaoToan(f"[tick {w.tick}] Vi phạm bảo toàn thế giới:\n  " + "\n  ".join(loi))


def kiem_toan(ledger: Ledger, tick: int = -1) -> None:
    """Assert bảo toàn từng tài sản + không âm số dư. Lệch → raise LoiBaoToan."""
    loi: list[str] = []
    tai_san_all = ledger.cac_tai_san() | ledger.flows.cac_tai_san()
    for ts in sorted(tai_san_all):
        thuc_te = ledger.tong_tai_san(ts)
        ky_vong = ledger.flows.tong_ky_vong(ts)
        # dung sai tương đối: float64 trôi ~1e-13/phép tính; luồng lậu thật luôn ≥ gram
        dung_sai = max(DUNG_SAI, abs(ky_vong) * 1e-9)
        if abs(thuc_te - ky_vong) > dung_sai:
            loi.append(
                f"'{ts}': sổ cái có {thuc_te}, FlowRegistry kỳ vọng {ky_vong} "
                f"(lệch {thuc_te - ky_vong})"
            )
    for (chu_the, ts), v in ledger._so_du.items():
        if v < -EPSILON:
            loi.append(f"Âm số dư: {chu_the}/{ts} = {v}")
    if loi:
        raise LoiBaoToan(f"[tick {tick}] Vi phạm bảo toàn:\n  " + "\n  ".join(loi))
