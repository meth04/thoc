"""Audit bảo toàn (điều luật #1) — chạy SAU MỖI TICK, lệch là raise, không đi tiếp.

Đối chiếu tổng tồn tại từng tài sản trong sổ cái với tổng kỳ vọng của FlowRegistry
(Σ sinh − Σ hủy đã đăng ký). Mọi luồng "lậu" — tài sản xuất hiện/biến mất ngoài sổ —
đều làm hai con số này lệch nhau và bị bắt tại đây.
"""

from __future__ import annotations

from engine.ledger import EPSILON, Ledger

# 1e-6 → 1e-5 (mock300r2 tick 494): tài sản chia lẻ vô hạn (4.5 công/kg cá, hao 15%/tick)
# trôi float ~1e-6 sau ~500 tick × hàng trăm nghìn bút toán; luồng lậu thật luôn ≥ gram.
DUNG_SAI = 1e-5


class LoiBaoToan(Exception):
    """Phương trình bảo toàn tài nguyên bị vi phạm."""


def kiem_toan_the_gioi(w, tong_thua_ban_dau: int) -> None:
    """Audit toàn cục sau mỗi tick: sổ cái + đất + công bốc hơi hết."""
    kiem_toan(w.ledger, w.tick)
    loi: list[str] = []
    if len(w.parcels) != tong_thua_ban_dau:
        loi.append(f"Tổng thửa đổi: {len(w.parcels)} ≠ {tong_thua_ban_dau}")
    for p in w.parcels.values():
        # chủ thửa phải là agent CÒN SỐNG hoặc entity CÒN HOẠT ĐỘNG — người chết
        # chưa thừa kế xong, VO_THUA_NHAN, entity giải thể đứng tên đất = chủ thể ma
        if p.chu is not None and not w.chu_the_hoat_dong(p.chu):
            loi.append(f"Thửa {p.id} có chủ không hoạt động: {p.chu}")
    tong_cong = w.ledger.tong_tai_san("cong")
    if abs(tong_cong) > DUNG_SAI:
        loi.append(f"Công không bốc hơi hết cuối tick: còn {tong_cong}")
    if loi:
        raise LoiBaoToan(f"[tick {w.tick}] Vi phạm bảo toàn thế giới:\n  " + "\n  ".join(loi))


def kiem_toan(ledger: Ledger, tick: int = -1) -> None:
    """Assert bảo toàn từng tài sản + không âm số dư. Lệch → raise LoiBaoToan."""
    loi: list[str] = []
    # một lượt qua sổ + một lượt qua registry — O(n), không O(n×tài sản)
    tong_thuc_te: dict[str, float] = {}
    for (chu_the, ts), v in ledger._so_du.items():
        tong_thuc_te[ts] = tong_thuc_te.get(ts, 0.0) + v
        if v < -EPSILON:
            loi.append(f"Âm số dư: {chu_the}/{ts} = {v}")
    tong_ky_vong: dict[str, float] = {}
    for (ts, _), v in ledger.flows._tich_luy.items():
        tong_ky_vong[ts] = tong_ky_vong.get(ts, 0.0) + v
    for ts in sorted(tong_thuc_te.keys() | tong_ky_vong.keys()):
        thuc_te = tong_thuc_te.get(ts, 0.0)
        ky_vong = tong_ky_vong.get(ts, 0.0)
        # dung sai tương đối: float64 trôi ~1e-13/phép tính; luồng lậu thật luôn ≥ gram
        dung_sai = max(DUNG_SAI, abs(ky_vong) * 1e-9)
        if abs(thuc_te - ky_vong) > dung_sai:
            loi.append(
                f"'{ts}': sổ cái có {thuc_te}, FlowRegistry kỳ vọng {ky_vong} "
                f"(lệch {thuc_te - ky_vong})"
            )
    if loi:
        raise LoiBaoToan(f"[tick {tick}] Vi phạm bảo toàn:\n  " + "\n  ".join(loi))
