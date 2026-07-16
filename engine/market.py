"""Chợ generic (SPEC 3.1): call auction MỌI tài sản + sealed bid đất.

Engine không bao giờ can thiệp giá — giá chỉ từ khớp lệnh cung–cầu.
Mỗi cặp (tài sản, tài sản thanh toán) là một sổ lệnh riêng; mặc định thanh toán bằng thóc,
nhưng agent có thể rao thanh toán bằng xu — xã hội có "tiền tệ hóa" hay không là tự phát.

Sổ lệnh persist (WP-A, ``cho.lenh_ton_tai_tick`` > 1): lệnh chưa khớp nằm trên sổ tối đa
N phiên rồi hết hạn (event ``lenh_het_han``). Config vắng hoặc = 1 ⇒ ĐÚNG NGUYÊN VĂN phiên
trong-tick legacy (lệnh chết cuối tick) — run/replay cũ không đổi một byte hành vi.

GHI CHÚ THIẾT KẾ (escrow): chợ này KHÔNG ký quỹ. Settlement là MỘT transaction nguyên tử
4 chân (hàng + tiền) ngay tại thời điểm khớp; bên thiếu số dư ⇒ ``LoiSoKep`` ⇒ phần khớp đó
bị hủy, không âm sổ, không mint. Lệnh persist vì vậy chỉ là Ý ĐỊNH nằm sổ — hết hạn/hủy
KHÔNG có bút toán hoàn (không có gì bị khóa). Ký quỹ bằng chủ thể ledger riêng
(``KY_QUY_CHO:*``) bị BÁC có chủ đích: audit E1′ (``estate.bang_drain``) fail-closed với mọi
chủ thể không khai báo drain, và hook giải phóng khi chủ lệnh chết nằm ở ``demography`` —
cả hai ngoài module này; escrow "nửa vời" ở đây sẽ làm audit đỏ ngay khi ``ho.di_san.bat``.
Mỗi phiên, lệnh của chủ thể không còn hoạt động (chết/giải thể) bị gỡ trước khi khớp.
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


@dataclass
class LenhCho:
    """Một lệnh trên sổ persist. ``so_luong`` là khối lượng CÒN LẠI (giảm dần theo fill)."""

    id: str  # "LC000001" — tie-break tất định sau (giá, tick đặt)
    ai: str
    chieu: str  # "mua" | "ban"
    tai_san: str
    so_luong: float
    gia: float
    thanh_toan: str
    lang: int | None  # nguyên bản từ intent (None = chợ làng mình lúc đặt)
    lang_so: int  # sổ lệnh (làng) đã resolve lúc đặt — lệnh không đi theo người
    tick_dat: int
    het_han_tick: int  # tick CUỐI CÙNG lệnh còn tham gia khớp


def lenh_ton_tai_tick(w) -> int:
    """Số phiên một lệnh chưa khớp được nằm sổ. Vắng config/không hợp lệ ⇒ 1 (legacy)."""
    try:
        return max(1, int(w.cfg.get("cho.lenh_ton_tai_tick", 1)))
    except (TypeError, ValueError):
        return 1


_LenhBatKy = Lenh | LenhCho
_KetQuaKhop = list[tuple[_LenhBatKy, float]]


def _cong_khop(ket_qua: _KetQuaKhop, le: _LenhBatKy, so_luong: float) -> None:
    """Cộng fill theo identity object mà không biến địa chỉ ``id()`` thành khóa nghiệp vụ."""
    for index, (da_co, tong) in enumerate(ket_qua):
        if da_co is le:
            ket_qua[index] = (da_co, tong + so_luong)
            return
    ket_qua.append((le, so_luong))


def _da_khop(ket_qua: _KetQuaKhop, le: _LenhBatKy) -> float:
    """Đọc tổng fill của đúng object lệnh; hai lệnh bằng giá trị vẫn là hai intent riêng."""
    return sum(so_luong for da_co, so_luong in ket_qua if da_co is le)


def _phi_buon_chuyen(w, le: _LenhBatKy, lang_cho: int, gia_tri_quy_thoc: float) -> None:
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


def _khop_legacy_da_sap(
    w, tai_san: str, thanh_toan: str, mua_khop: list[_LenhBatKy],
    ban_khop: list[_LenhBatKy], p_sao: float, lang: int,
) -> tuple[float, float, _KetQuaKhop]:
    """Settlement loop frozen for TTL absent/=1 so old trajectories remain unchanged."""
    cau = sum(le.so_luong for le in mua_khop)
    cung = sum(le.so_luong for le in ban_khop)
    kl = min(cau, cung)
    he_so_mua = kl / cau if cau > 0 else 0.0
    he_so_ban = kl / cung if cung > 0 else 0.0

    tong_khop = 0.0
    khop_theo_lenh: _KetQuaKhop = []
    i, j = 0, 0
    con_mua = [le.so_luong * he_so_mua for le in mua_khop]
    con_ban = [le.so_luong * he_so_ban for le in ban_khop]
    while i < len(mua_khop) and j < len(ban_khop):
        khop = min(con_mua[i], con_ban[j])
        if khop > 1e-9:
            nguoi_mua, nguoi_ban = mua_khop[i].ai, ban_khop[j].ai
            tien = khop * p_sao
            try:
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
                _cong_khop(khop_theo_lenh, mua_khop[i], khop)
                _cong_khop(khop_theo_lenh, ban_khop[j], khop)
                w.events.ghi(w.tick, "khop_cho", tai_san=tai_san, thanh_toan=thanh_toan,
                             lang=lang, mua=nguoi_mua, ban=nguoi_ban, sl=round(khop, 3),
                             gia=round(p_sao, 3))
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
                if _lang_cua(w, nguoi_mua) == _lang_cua(w, nguoi_ban):
                    w.cong_quan_he_gioi_han(
                        nguoi_mua, nguoi_ban,
                        float(w.cfg.get("quan_he.cong_moi_tuong_tac")))
            except LoiSoKep:
                # Frozen legacy behavior: a failed pair still consumes its intratick allocation.
                w.settlement_fail_tick += 1
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
    return tong_khop, p_sao, khop_theo_lenh


def _khop_mot_so_lenh(
    w, tai_san: str, thanh_toan: str, mua: list[_LenhBatKy], ban: list[_LenhBatKy],
    lang: int = 0, *, phan_bo_lai_khi_that_bai: bool = False,
) -> tuple[float, float | None, _KetQuaKhop]:
    """Call auction một cặp: tìm p* tối đa khối lượng, khớp pro-rata tại biên.

    Khi ``phan_bo_lai_khi_that_bai`` bật cho sổ persist, fill chỉ bị trừ sau khi transaction
    bốn chân commit; phía thiếu hàng/tiền bị loại khỏi phiên rồi volume còn lại được phân bổ
    lại tất định. TTL absent/=1 đi qua loop legacy đóng băng để không đổi trajectory cũ.
    """
    if not mua or not ban:
        return 0.0, None, []
    gia_ung_vien = sorted({le.gia for le in mua} | {le.gia for le in ban})

    def khoi_luong(p: float) -> float:
        cau = sum(le.so_luong for le in mua if le.gia >= p)
        cung = sum(le.so_luong for le in ban if le.gia <= p)
        return min(cau, cung)

    kl_max = max(khoi_luong(p) for p in gia_ung_vien)
    if kl_max <= 1e-9:
        return 0.0, None, []
    ung_vien_tot = [p for p in gia_ung_vien if khoi_luong(p) >= kl_max - 1e-12]
    p_sao = float(ung_vien_tot[len(ung_vien_tot) // 2])  # giữa khoảng max-volume

    # Price-time priority tất định: giá tốt trước, lệnh đặt sớm trước, tie-break bằng id
    # lệnh rồi id người đặt. Lenh legacy không có tick_dat/id ⇒ hai khóa giữa là hằng số
    # ⇒ thứ tự Y HỆT khóa cũ (-gia, ai) / (gia, ai) — hành vi legacy không đổi một bit.
    mua_khop = sorted(
        [le for le in mua if le.gia >= p_sao],
        key=lambda x: (-x.gia, getattr(x, "tick_dat", 0), getattr(x, "id", ""), x.ai),
    )
    ban_khop = sorted(
        [le for le in ban if le.gia <= p_sao],
        key=lambda x: (x.gia, getattr(x, "tick_dat", 0), getattr(x, "id", ""), x.ai),
    )
    if not phan_bo_lai_khi_that_bai:
        return _khop_legacy_da_sap(w, tai_san, thanh_toan, mua_khop, ban_khop, p_sao, lang)

    from engine.ledger import ButToan, Transaction

    tong_khop = 0.0
    khop_theo_lenh: _KetQuaKhop = []
    con_mua = [float(le.so_luong) for le in mua_khop]
    con_ban = [float(le.so_luong) for le in ban_khop]
    khoa_mua: set[int] = set()
    khoa_ban: set[int] = set()

    while True:
        chi_so_mua = [i for i, con in enumerate(con_mua) if con > 1e-9 and i not in khoa_mua]
        chi_so_ban = [j for j, con in enumerate(con_ban) if con > 1e-9 and j not in khoa_ban]
        if not chi_so_mua or not chi_so_ban:
            break
        cau = sum(con_mua[i] for i in chi_so_mua)
        cung = sum(con_ban[j] for j in chi_so_ban)
        kl_vong = min(cau, cung)
        if kl_vong <= 1e-9:
            break
        he_so_mua = kl_vong / cau
        he_so_ban = kl_vong / cung
        muc_mua = [con_mua[i] * he_so_mua for i in chi_so_mua]
        muc_ban = [con_ban[j] * he_so_ban for j in chi_so_ban]
        vi_tri_mua = vi_tri_ban = 0
        co_that_bai = False

        while vi_tri_mua < len(chi_so_mua) and vi_tri_ban < len(chi_so_ban):
            i, j = chi_so_mua[vi_tri_mua], chi_so_ban[vi_tri_ban]
            khop = min(muc_mua[vi_tri_mua], muc_ban[vi_tri_ban])
            if khop <= 1e-9:
                if muc_mua[vi_tri_mua] <= 1e-9:
                    vi_tri_mua += 1
                if muc_ban[vi_tri_ban] <= 1e-9:
                    vi_tri_ban += 1
                continue

            nguoi_mua, nguoi_ban = mua_khop[i].ai, ban_khop[j].ai
            tien = khop * p_sao
            # Cùng một chủ thể tự khớp có delta ròng bằng 0; giữ semantics legacy. Với hai
            # chủ thể khác nhau, xác định chính xác phía thiếu để không tiêu allocation của phía kia.
            thieu_mua = (
                nguoi_mua != nguoi_ban
                and w.ledger.so_du(nguoi_mua, thanh_toan) + 1e-9 < tien
            )
            thieu_ban = (
                nguoi_mua != nguoi_ban
                and w.ledger.so_du(nguoi_ban, tai_san) + 1e-9 < khop
            )
            if thieu_mua or thieu_ban:
                if thieu_mua:
                    khoa_mua.add(i)
                if thieu_ban:
                    khoa_ban.add(j)
                w.settlement_fail_tick += 1
                co_that_bai = True
                break

            try:
                # Nguyên tử: mỗi tài sản có một debit + một credit trong CÙNG transaction.
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
            except LoiSoKep:
                # Hai kiểm tra số dư ở trên đã phủ failure khả kiến. Một lỗi khác là vi phạm
                # accounting thật (không cân/NaN/flow), phải fail closed chứ không nuốt.
                raise

            tong_khop += khop
            con_mua[i] -= khop
            con_ban[j] -= khop
            muc_mua[vi_tri_mua] -= khop
            muc_ban[vi_tri_ban] -= khop
            _cong_khop(khop_theo_lenh, mua_khop[i], khop)
            _cong_khop(khop_theo_lenh, ban_khop[j], khop)
            # `lang` = sổ lệnh (làng) khớp lệnh — cho phép observatory/analysis đo
            # phân tán giá GIỮA LÀNG offline (ADR 0003 §D đường D1). Chỉ thêm field
            # event journal; KHÔNG đụng world_hash/logic khớp/Lenh/gia_lich_su.
            w.events.ghi(w.tick, "khop_cho", tai_san=tai_san, thanh_toan=thanh_toan,
                         lang=lang, mua=nguoi_mua, ban=nguoi_ban, sl=round(khop, 3),
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
            if muc_mua[vi_tri_mua] <= 1e-9:
                vi_tri_mua += 1
            if muc_ban[vi_tri_ban] <= 1e-9:
                vi_tri_ban += 1

        if not co_that_bai:
            # Một phía của vòng pro-rata đã được lấp hết; không còn volume chéo để phân lại.
            break

    if tong_khop > 1e-9:
        if thanh_toan == "thoc":
            w.ghi_gia(tai_san, p_sao, tong_khop, thanh_toan)
        else:
            w.ghi_gia(f"{tai_san}/{thanh_toan}", p_sao, tong_khop, thanh_toan)
            gia_tt = w.gia_gan_nhat(thanh_toan)
            if gia_tt is not None:
                w.ghi_gia(tai_san, p_sao * gia_tt, tong_khop, thanh_toan)
    return tong_khop, p_sao, khop_theo_lenh


def _lang_cua(w, aid: str) -> int:
    a = w.agents.get(aid)
    return a.lang if a is not None else 0  # entity: chợ làng 0 (làng lập entity)


def _toi_duoc_cho(w, aid: str, lang_cho: int) -> bool:
    """Người đặt lệnh có tới được chợ ``lang_cho``? (ADR 0005 §2.2: sông chặn liên bờ.)

    TẮT không_gian ⇒ luôn True (không rào). BẬT ⇒ chợ bờ đối diện chỉ tới được khi đã qua
    đò tick này (``ben_kia_tick``) hoặc tự sở hữu thuyền — nếu không, HÀNG kẹt bờ (bỏ lệnh,
    không âm sổ, không teleport). Đơn-bờ (một làng bờ dân cư) ⇒ inert.
    """
    from engine.spatial import _hai_bo_bat, co_the_o_bo

    if not _hai_bo_bat(w) or not (0 <= lang_cho < len(w.villages)):
        return True
    v = w.villages[lang_cho]
    p = w.parcels.get(f"P{v.r:02d}_{v.c:02d}")
    bo_cho = p.bo if p is not None else None
    return co_the_o_bo(w, aid, bo_cho) or w.ledger.so_du(aid, "thuyen") >= 1.0


def phien_cho(w, lenh_tick: list[Lenh]) -> float:
    """Bước 6: MỖI LÀNG một chợ — gom lệnh theo (làng, tài sản, thanh toán), khớp từng sổ.

    Lệnh gửi sang làng khác = buôn chuyến: chịu phí 2%/khoảng cách trên giá trị khớp.
    ``cho.lenh_ton_tai_tick`` > 1 ⇒ sổ lệnh persist; vắng/= 1 ⇒ phiên trong-tick legacy.
    """
    if lenh_ton_tai_tick(w) <= 1:
        return _phien_trong_tick(w, lenh_tick)
    return _phien_so_lenh(w, lenh_tick)


def _phien_trong_tick(w, lenh_tick: list[Lenh]) -> float:
    """Nhánh legacy NGUYÊN VĂN: lệnh chỉ sống trong tick đặt, không có sổ qua đêm."""
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import order_target
    from engine.action_journal import rejected as journal_rejected

    cap: dict[tuple[int, str, str], tuple[list[Lenh], list[Lenh]]] = {}
    valid: list[Lenh] = []
    for le in lenh_tick:
        action = "buon_chuyen" if le.lang is not None else "dat_lenh"
        target = order_target(le)
        # NaN/inf từ intent hỏng phải bị chặn NGAY — một lệnh NaN treo cả phiên chợ
        if not (math.isfinite(le.so_luong) and math.isfinite(le.gia)):
            journal_rejected(w, le.ai, action, "invalid_order", target=target)
            continue
        if (le.chieu not in {"mua", "ban"} or le.so_luong <= 0 or le.gia <= 0
                or le.tai_san == le.thanh_toan):
            journal_rejected(w, le.ai, action, "invalid_order", target=target)
            continue
        lang = le.lang if le.lang is not None else _lang_cua(w, le.ai)
        if not (0 <= lang < len(w.villages)):
            journal_rejected(w, le.ai, action, "market_not_found", target=target)
            continue
        if not _toi_duoc_cho(w, le.ai, lang):  # chợ bờ kia không đò ⇒ hàng kẹt bờ
            journal_rejected(w, le.ai, action, "market_unreachable", target=target)
            continue
        mua, ban = cap.setdefault((lang, le.tai_san, le.thanh_toan), ([], []))
        (mua if le.chieu == "mua" else ban).append(le)
        valid.append(le)
    tong = 0.0
    khop_theo_lenh: _KetQuaKhop = []
    gia_theo_lenh: list[tuple[Lenh, float]] = []
    for (lang, ts, tt) in sorted(cap):
        mua, ban = cap[(lang, ts, tt)]
        khoi_luong, gia, fills = _khop_mot_so_lenh(w, ts, tt, mua, ban, lang=lang)
        tong += khoi_luong
        for le, so_luong in fills:
            _cong_khop(khop_theo_lenh, le, so_luong)
        if gia is not None:
            gia_theo_lenh.extend((le, gia) for le in [*mua, *ban])
    for le in valid:
        da_khop = _da_khop(khop_theo_lenh, le)
        action = "buon_chuyen" if le.lang is not None else "dat_lenh"
        target = order_target(le)
        if da_khop <= 1e-9:
            journal_executed(w, le.ai, action, target=target, code="unfilled",
                             detail="accepted by the market but matched zero quantity")
            continue
        code = "matched" if da_khop >= le.so_luong - 1e-9 else "partially_matched"
        gia = next((p for da_co, p in gia_theo_lenh if da_co is le), None)
        price_text = f" price={gia:g}" if gia is not None else ""
        journal_executed(
            w, le.ai, action, target=target, code=code,
            detail=f"filled={da_khop:g}/{le.so_luong:g}{price_text}",
        )
    return tong


# ---------------------------------------------------------------- sổ lệnh persist (WP-A)


def _phien_so_lenh(w, lenh_tick: list[Lenh]) -> float:
    """Sổ lệnh persist: gỡ lệnh chủ chết/giải thể → nhận lệnh mới → khớp CẢ SỔ → hết hạn.

    Settlement vẫn nguyên tử trực tiếp owner↔owner (xem ghi chú thiết kế đầu file) nên
    bảo toàn từng tick tự xanh: mọi bút toán chỉ là ``chuyen`` cân, không mint/burn mới.
    """
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import order_target
    from engine.action_journal import rejected as journal_rejected

    ttl = lenh_ton_tai_tick(w)

    # 1) Gỡ lệnh của chủ thể không còn hoạt động (chết/estate/giải thể) TRƯỚC khi khớp —
    #    người chết không được nhận thêm giao dịch mới (điều luật boundary). Không có
    #    escrow nên không có bút toán hoàn; chỉ event.
    con_song: list[LenhCho] = []
    so_huy_khong_hoat_dong = 0
    for lc in w.lenh_cho:
        if w.chu_the_hoat_dong(lc.ai):
            con_song.append(lc)
        else:
            so_huy_khong_hoat_dong += 1
            w.events.ghi(w.tick, "huy_lenh", id=lc.id, ai=lc.ai, chieu=lc.chieu,
                         tai_san=lc.tai_san, thanh_toan=lc.thanh_toan,
                         con_lai=round(lc.so_luong, 6), ly_do="chu_the_khong_hoat_dong")
    w.lenh_cho = con_song

    # 2) Nhận lệnh mới — validate Y HỆT nhánh legacy (mã từ chối giữ nguyên schema).
    moi: list[tuple[LenhCho, Lenh]] = []
    for le in lenh_tick:
        action = "buon_chuyen" if le.lang is not None else "dat_lenh"
        target = order_target(le)
        if not w.chu_the_hoat_dong(le.ai):
            journal_rejected(w, le.ai, action, "actor_inactive", target=target)
            w.events.ghi(w.tick, "tu_choi_lenh", ai=le.ai, ly_do="chu_the_khong_hoat_dong")
            continue
        if not (math.isfinite(le.so_luong) and math.isfinite(le.gia)):
            journal_rejected(w, le.ai, action, "invalid_order", target=target)
            continue
        if (le.chieu not in {"mua", "ban"} or le.so_luong <= 0 or le.gia <= 0
                or le.tai_san == le.thanh_toan):
            journal_rejected(w, le.ai, action, "invalid_order", target=target)
            continue
        lang_so = le.lang if le.lang is not None else _lang_cua(w, le.ai)
        if not (0 <= lang_so < len(w.villages)):
            journal_rejected(w, le.ai, action, "market_not_found", target=target)
            continue
        if not _toi_duoc_cho(w, le.ai, lang_so):
            journal_rejected(w, le.ai, action, "market_unreachable", target=target)
            continue
        w._next_lenh_cho += 1
        # "cong" là flow trong-tick (bốc hơi cuối tick) ⇒ lệnh dính công KHÔNG ngủ qua đêm:
        # để nó treo là treo một lời hứa vật lý không thể giữ.
        song = 1 if "cong" in (le.tai_san, le.thanh_toan) else ttl
        lc = LenhCho(
            id=f"LC{w._next_lenh_cho:06d}", ai=le.ai, chieu=le.chieu, tai_san=le.tai_san,
            so_luong=float(le.so_luong), gia=float(le.gia), thanh_toan=le.thanh_toan,
            lang=le.lang, lang_so=int(lang_so), tick_dat=w.tick,
            het_han_tick=w.tick + song - 1,
        )
        w.lenh_cho.append(lc)
        moi.append((lc, le))

    # 3) Gom CẢ SỔ theo (làng, tài sản, thanh toán). Lệnh treo mà tick này chủ không tới
    #    được chợ (đò/bờ, ADR 0005) đứng ngoài phiên nhưng vẫn nằm sổ chờ tick sau.
    cap: dict[tuple[int, str, str], tuple[list[LenhCho], list[LenhCho]]] = {}
    for lc in w.lenh_cho:
        if not _toi_duoc_cho(w, lc.ai, lc.lang_so):
            continue
        mua, ban = cap.setdefault((lc.lang_so, lc.tai_san, lc.thanh_toan), ([], []))
        (mua if lc.chieu == "mua" else ban).append(lc)

    tong = 0.0
    khop_theo_lenh: dict[str, float] = {}
    gia_theo_lenh: dict[str, float] = {}
    thong_ke: dict[str, dict[str, float]] = {}
    for (lang, ts, tt) in sorted(cap):
        mua, ban = cap[(lang, ts, tt)]
        khoi_luong, gia, fills = _khop_mot_so_lenh(
            w, ts, tt, mua, ban, lang=lang, phan_bo_lai_khi_that_bai=True,
        )
        tong += khoi_luong
        for le_da_khop, so_luong in fills:
            assert isinstance(le_da_khop, LenhCho)
            khop_theo_lenh[le_da_khop.id] = (
                khop_theo_lenh.get(le_da_khop.id, 0.0) + so_luong
            )
        if gia is not None:
            for lc in [*mua, *ban]:
                gia_theo_lenh[lc.id] = gia
        tk = thong_ke.setdefault(f"{ts}/{tt}", {
            "lenh_mua": 0, "lenh_ban": 0, "kl_mua": 0.0, "kl_ban": 0.0, "kl_khop": 0.0,
        })
        tk["lenh_mua"] += len(mua)
        tk["lenh_ban"] += len(ban)
        tk["kl_mua"] += sum(x.so_luong for x in mua)
        tk["kl_ban"] += sum(x.so_luong for x in ban)
        tk["kl_khop"] += khoi_luong

    # 4) Trừ phần ĐÃ SETTLE khỏi khối lượng còn lại. Phần khớp-hụt (LoiSoKep) KHÔNG bị
    #    trừ — lệnh còn nguyên trên sổ thử lại tick sau. Chủ lệnh treo từ tick trước được
    #    báo qua ký ức (journal chỉ dành cho lệnh đặt trong tick — không bịa request mới).
    for lc in w.lenh_cho:
        da = khop_theo_lenh.get(lc.id, 0.0)
        if da <= 1e-9:
            continue
        lc.so_luong = max(0.0, lc.so_luong - da)
        if lc.tick_dat < w.tick:
            gia_k = gia_theo_lenh.get(lc.id)
            gia_text = f" giá {gia_k:g} {lc.thanh_toan}" if gia_k is not None else ""
            w.ghi_ky_uc(lc.ai, f"lệnh {lc.chieu} {lc.tai_san} treo ở chợ của tôi "
                               f"khớp {da:.1f}{gia_text}")

    # 5) Journal cho lệnh đặt TRONG tick (schema code y legacy; unfilled = đã lên sổ).
    for lc, le in moi:
        action = "buon_chuyen" if le.lang is not None else "dat_lenh"
        target = order_target(le)
        da_khop = khop_theo_lenh.get(lc.id, 0.0)
        if da_khop <= 1e-9:
            journal_executed(
                w, le.ai, action, target=target, code="unfilled",
                detail=("accepted by the market but matched zero quantity; "
                        f"resting on the book until tick {lc.het_han_tick}"),
            )
            continue
        code = "matched" if lc.so_luong <= 1e-9 else "partially_matched"
        gia_k = gia_theo_lenh.get(lc.id)
        price_text = f" price={gia_k:g}" if gia_k is not None else ""
        journal_executed(
            w, le.ai, action, target=target, code=code,
            detail=f"filled={da_khop:g}/{le.so_luong:g}{price_text}",
        )

    # 6) Quét sổ cuối phiên: khớp hết → gỡ êm; quá hạn → event ``lenh_het_han``.
    #    Không có escrow ⇒ hết hạn không có bút toán nào (không gì bị khóa để hoàn).
    so_het_han = 0
    giu_lai: list[LenhCho] = []
    for lc in w.lenh_cho:
        if lc.so_luong <= 1e-9:
            continue
        if w.tick >= lc.het_han_tick:
            so_het_han += 1
            w.events.ghi(w.tick, "lenh_het_han", id=lc.id, ai=lc.ai, chieu=lc.chieu,
                         tai_san=lc.tai_san, thanh_toan=lc.thanh_toan, gia=lc.gia,
                         con_lai=round(lc.so_luong, 6), tick_dat=lc.tick_dat)
            if lc.tick_dat < w.tick:
                w.ghi_ky_uc(lc.ai, f"lệnh {lc.chieu} {lc.tai_san} của tôi hết hạn ở chợ, "
                                   f"{lc.so_luong:.1f} chưa khớp")
            continue
        giu_lai.append(lc)
    w.lenh_cho = giu_lai

    # 7) Báo cáo hai phía cung–cầu mỗi tick (CHỈ event/log — không đổi hành vi khớp).
    w.events.ghi(
        w.tick, "tong_hop_cho",
        so_lenh_moi=len(moi), so_lenh_ton=len(w.lenh_cho), so_het_han=so_het_han,
        so_huy_khong_hoat_dong=so_huy_khong_hoat_dong, kl_khop=round(tong, 6),
        theo_tai_san={
            k: {
                "lenh_mua": int(v["lenh_mua"]), "lenh_ban": int(v["lenh_ban"]),
                "kl_mua": round(v["kl_mua"], 6), "kl_ban": round(v["kl_ban"], 6),
                "cau": round(v["kl_mua"], 6), "cung": round(v["kl_ban"], 6),
                "kl_khop": round(v["kl_khop"], 6),
                "fill_rate": round(
                    v["kl_khop"] / min(v["kl_mua"], v["kl_ban"]), 6
                ) if min(v["kl_mua"], v["kl_ban"]) > 1e-9 else 0.0,
                "fill_rate_cau": round(v["kl_khop"] / v["kl_mua"], 6)
                if v["kl_mua"] > 1e-9 else 0.0,
                "fill_rate_cung": round(v["kl_khop"] / v["kl_ban"], 6)
                if v["kl_ban"] > 1e-9 else 0.0,
            }
            for k, v in sorted(thong_ke.items())
        },
    )
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
            # Metric kiểm định vốn hóa đất: ghi năng suất vật chất *trước* khi đổi chủ.
            # Không dùng nó để đặt giá hay chấp nhận bid.
            from engine.economy import expected_parcel_net_output

            w.giao_dich_dat.append({
                "tick": w.tick,
                "parcel": thua,
                "price": float(gia),
                "expected_net_output": expected_parcel_net_output(w, thua),
                "fertility": float(p.mau_mo),
            })
            w.ghi_gia("dat", gia, 1.0, "thoc")
            w.events.ghi(w.tick, "ban_dat", thua=thua, tu=ny.chu, den=ai, gia=gia)
            w.ghi_ky_uc(ny.chu, f"tôi bán thửa {thua} được {gia:.0f}kg thóc", doi=True)
            w.ghi_ky_uc(ai, f"tôi mua thửa {thua} giá {gia:.0f}kg thóc", doi=True)
            w.cong_quan_he(ai, ny.chu, w.cfg.get("quan_he.cong_moi_tuong_tac"))
            break
