"""Chợ generic (SPEC 3.1): call auction MỌI tài sản + sealed bid đất.

Engine không bao giờ can thiệp giá — giá chỉ từ khớp lệnh cung–cầu.
Mỗi cặp (tài sản, tài sản thanh toán) là một sổ lệnh riêng; mặc định thanh toán bằng thóc,
nhưng agent có thể rao thanh toán bằng xu — xã hội có "tiền tệ hóa" hay không là tự phát.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.ledger import LoiSoKep


@dataclass(frozen=True)
class Lenh:
    ai: str
    chieu: str  # "mua" | "ban"
    tai_san: str
    so_luong: float
    gia: float  # đơn giá tính bằng tài sản thanh toán
    thanh_toan: str = "thoc"


def _khop_mot_so_lenh(
    w, tai_san: str, thanh_toan: str, mua: list[Lenh], ban: list[Lenh],
    g: np.random.Generator,
) -> float:
    """Call auction một cặp: tìm p* tối đa khối lượng, khớp pro-rata tại biên."""
    if not mua or not ban:
        return 0.0
    gia_ung_vien = sorted({le.gia for le in mua} | {le.gia for le in ban})

    def khoi_luong(p: float) -> float:
        cau = sum(le.so_luong for le in mua if le.gia >= p)
        cung = sum(le.so_luong for le in ban if le.gia <= p)
        return min(cau, cung)

    kl_max = max(khoi_luong(p) for p in gia_ung_vien)
    if kl_max <= 1e-9:
        return 0.0
    ung_vien_tot = [p for p in gia_ung_vien if khoi_luong(p) >= kl_max - 1e-12]
    p_sao = float(ung_vien_tot[len(ung_vien_tot) // 2])  # giữa khoảng max-volume

    mua_khop = sorted([le for le in mua if le.gia >= p_sao], key=lambda x: (-x.gia, x.ai))
    ban_khop = sorted([le for le in ban if le.gia <= p_sao], key=lambda x: (x.gia, x.ai))
    cau = sum(le.so_luong for le in mua_khop)
    cung = sum(le.so_luong for le in ban_khop)
    kl = min(cau, cung)
    # pro-rata bên dư
    he_so_mua = kl / cau if cau > 0 else 0.0
    he_so_ban = kl / cung if cung > 0 else 0.0

    tong_khop = 0.0
    i, j = 0, 0
    con_mua = [le.so_luong * he_so_mua for le in mua_khop]
    con_ban = [le.so_luong * he_so_ban for le in ban_khop]
    while i < len(mua_khop) and j < len(ban_khop):
        khop = min(con_mua[i], con_ban[j])
        if khop > 1e-9:
            nguoi_mua, nguoi_ban = mua_khop[i].ai, ban_khop[j].ai
            tien = khop * p_sao
            try:
                # nguyên tử: hàng + tiền trong một transaction hai chân
                from engine.ledger import ButToan, Transaction

                w.ledger.ap_dung(
                    Transaction(
                        tick=w.tick,
                        ly_do=f"chợ {tai_san}/{thanh_toan} @{p_sao:.2f}",
                        but_toan=(
                            ButToan(nguoi_ban, tai_san, -khop),
                            ButToan(nguoi_mua, tai_san, +khop),
                            ButToan(nguoi_mua, thanh_toan, -tien),
                            ButToan(nguoi_ban, thanh_toan, +tien),
                        ),
                    )
                )
                tong_khop += khop
                w.events.ghi(w.tick, "khop_cho", tai_san=tai_san, thanh_toan=thanh_toan,
                             mua=nguoi_mua, ban=nguoi_ban, sl=round(khop, 3),
                             gia=round(p_sao, 3))
                # thu nhập người bán + khối lượng theo phương tiện thanh toán (quy thóc)
                gia_tt = 1.0 if thanh_toan == "thoc" else (w.gia_gan_nhat(thanh_toan) or 0.0)
                quy_thoc = tien * gia_tt
                nhom = ("che_tac" if tai_san == "cong_cu" or tai_san in w.ten_hang
                        else "khai_thac" if tai_san in ("go", "quang_dong")
                        else "ban_" + tai_san.split(":")[0])
                w.ghi_thu_nhap(nguoi_ban, nhom, quy_thoc)
                w.kl_thanh_toan_tick[thanh_toan] = (
                    w.kl_thanh_toan_tick.get(thanh_toan, 0.0) + quy_thoc
                )
            except LoiSoKep:
                pass  # bên nào thiếu (đặt lệnh quá tay) → phần khớp đó bỏ
        con_mua[i] -= khop
        con_ban[j] -= khop
        if con_mua[i] <= 1e-9:
            i += 1
        if con_ban[j] <= 1e-9:
            j += 1

    if tong_khop > 1e-9:
        if thanh_toan == "thoc":
            w.ghi_gia(tai_san, p_sao, tong_khop, thanh_toan)
        else:
            w.ghi_gia(f"{tai_san}/{thanh_toan}", p_sao, tong_khop, thanh_toan)
            gia_tt = w.gia_gan_nhat(thanh_toan)
            if gia_tt is not None:
                w.ghi_gia(tai_san, p_sao * gia_tt, tong_khop, thanh_toan)
    return tong_khop


def phien_cho(w, lenh_tick: list[Lenh]) -> float:
    """Bước 6 pipeline: gom lệnh theo cặp (tài sản, thanh toán), khớp từng cặp."""
    g = w.rng.get("cho", w.tick)
    cap: dict[tuple[str, str], tuple[list[Lenh], list[Lenh]]] = {}
    for le in lenh_tick:
        if le.so_luong <= 0 or le.gia <= 0 or le.tai_san == le.thanh_toan:
            continue
        mua, ban = cap.setdefault((le.tai_san, le.thanh_toan), ([], []))
        (mua if le.chieu == "mua" else ban).append(le)
    tong = 0.0
    for (ts, tt) in sorted(cap):
        mua, ban = cap[(ts, tt)]
        tong += _khop_mot_so_lenh(w, ts, tt, mua, ban, g)
    return tong


# ---------------------------------------------------------------- đất: sealed bid


@dataclass
class NiemYetDat:
    thua: str
    chu: str
    gia_ask: float
    tick: int


def phien_dat(w, niem_yet: dict[str, NiemYetDat], tra_gia: list[tuple[str, str, float]]) -> None:
    """Sealed bid từng thửa: bid cao nhất ≥ ask thắng, trả giá bid (first-price)."""
    bid_theo_thua: dict[str, list[tuple[float, str]]] = {}
    for ai, thua, gia in tra_gia:
        if thua in niem_yet and gia > 0 and ai != niem_yet[thua].chu:
            bid_theo_thua.setdefault(thua, []).append((gia, ai))
    for thua in sorted(bid_theo_thua):
        ny = niem_yet[thua]
        p = w.parcels.get(thua)
        if p is None or p.chu != ny.chu:
            continue  # chủ đã đổi giữa chừng
        for gia, ai in sorted(bid_theo_thua[thua], reverse=True):
            if gia < ny.gia_ask:
                break
            try:
                w.ledger.chuyen(ai, ny.chu, "thoc", gia, f"mua đất {thua}", w.tick)
            except LoiSoKep:
                continue  # người trả giá không đủ thóc → xét bid kế
            p.chu = ai
            p.homestead_ai, p.homestead_dem = None, 0
            del niem_yet[thua]
            w.ghi_gia("dat", gia, 1.0, "thoc")
            w.events.ghi(w.tick, "ban_dat", thua=thua, tu=ny.chu, den=ai, gia=gia)
            w.cong_quan_he(ai, ny.chu, w.cfg.get("quan_he.cong_moi_tuong_tac"))
            break
