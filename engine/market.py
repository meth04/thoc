"""Chợ generic (SPEC 3.1): call auction MỌI tài sản + sealed bid đất.

Engine không bao giờ can thiệp giá — giá chỉ từ khớp lệnh cung–cầu.
Mỗi cặp (tài sản, tài sản thanh toán) là một sổ lệnh riêng; mặc định thanh toán bằng thóc,
nhưng agent có thể rao thanh toán bằng xu — xã hội có "tiền tệ hóa" hay không là tự phát.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.ledger import LoiSoKep


@dataclass(frozen=True)
class Lenh:
    ai: str
    chieu: str  # "mua" | "ban"
    tai_san: str
    so_luong: float
    gia: float  # đơn giá tính bằng tài sản thanh toán
    thanh_toan: str = "thoc"
    lang: int | None = None  # None = chợ làng mình; khác làng = buôn chuyến (chịu phí)


def _phi_buon_chuyen(w, le: Lenh, lang_cho: int, gia_tri_quy_thoc: float) -> None:
    """Phí buôn chuyến 2%/khoảng cách giữa làng mình và làng chợ (SPEC 3.1)."""
    lang_nha = _lang_cua(w, le.ai)
    if lang_nha == lang_cho:
        return
    v1, v2 = w.villages[lang_nha], w.villages[lang_cho]
    kc = abs(v1.r - v2.r) + abs(v1.c - v2.c)
    chuan_hoa = float(w.cfg.get("thuong_mai.chuan_hoa_khoang_cach"))
    phi = gia_tri_quy_thoc * float(
        w.cfg.get("thuong_mai.phi_van_chuyen_moi_khoang_cach")) * (kc / chuan_hoa)
    phi = min(phi, w.ledger.so_du(le.ai, "thoc"))
    if phi > 0:
        w.ledger.huy(le.ai, "thoc", phi, "phi_van_chuyen", "phí buôn chuyến", w.tick)


def _khop_mot_so_lenh(
    w, tai_san: str, thanh_toan: str, mua: list[Lenh], ban: list[Lenh], lang: int = 0,
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
                _phi_buon_chuyen(w, mua_khop[i], lang, quy_thoc)
                _phi_buon_chuyen(w, ban_khop[j], lang, quy_thoc)
                # chợ làng là mặt-đối-mặt: cặp mua–bán CÙNG LÀNG thành bạn hàng dần
                if _lang_cua(w, nguoi_mua) == _lang_cua(w, nguoi_ban):
                    w.cong_quan_he_gioi_han(
                        nguoi_mua, nguoi_ban,
                        float(w.cfg.get("quan_he.cong_moi_tuong_tac")))
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


def _lang_cua(w, aid: str) -> int:
    a = w.agents.get(aid)
    return a.lang if a is not None else 0  # entity: chợ làng 0 (làng lập entity)


def phien_cho(w, lenh_tick: list[Lenh]) -> float:
    """Bước 6: MỖI LÀNG một chợ — gom lệnh theo (làng, tài sản, thanh toán), khớp từng sổ.

    Lệnh gửi sang làng khác = buôn chuyến: chịu phí 2%/khoảng cách trên giá trị khớp.
    """
    cap: dict[tuple[int, str, str], tuple[list[Lenh], list[Lenh]]] = {}
    for le in lenh_tick:
        # NaN/inf từ intent hỏng phải bị chặn NGAY — một lệnh NaN treo cả phiên chợ
        if not (math.isfinite(le.so_luong) and math.isfinite(le.gia)):
            continue
        if le.so_luong <= 0 or le.gia <= 0 or le.tai_san == le.thanh_toan:
            continue
        lang = le.lang if le.lang is not None else _lang_cua(w, le.ai)
        if not (0 <= lang < len(w.villages)):
            continue
        mua, ban = cap.setdefault((lang, le.tai_san, le.thanh_toan), ([], []))
        (mua if le.chieu == "mua" else ban).append(le)
    tong = 0.0
    for (lang, ts, tt) in sorted(cap):
        mua, ban = cap[(lang, ts, tt)]
        tong += _khop_mot_so_lenh(w, ts, tt, mua, ban, lang=lang)
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
    # niêm yết hết hạn hoặc chủ đã đổi (thừa kế, xiết nợ...) → gỡ khỏi bảng,
    # không bán cưỡng bức theo giá ask cũ từ hàng chục tick trước
    het_han = int(w.cfg.get("thuong_mai.niem_yet_het_han_tick"))
    for thua in sorted(niem_yet):
        ny = niem_yet[thua]
        p = w.parcels.get(thua)
        if p is None or p.chu != ny.chu or w.tick - ny.tick > het_han:
            del niem_yet[thua]
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
            w.ghi_ky_uc(ny.chu, f"tôi bán thửa {thua} được {gia:.0f}kg thóc")
            w.ghi_ky_uc(ai, f"tôi mua thửa {thua} giá {gia:.0f}kg thóc")
            w.cong_quan_he(ai, ny.chu, w.cfg.get("quan_he.cong_moi_tuong_tac"))
            break
