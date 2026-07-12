"""Metric nghiên cứu THUẦN QUAN SÁT cho T04–T08 (ADR 0003 + ADR 0004) + T13 không gian
(ADR 0005 §10).

Tầng Lớp-5 (MODEL_CHARTER §3): CHỈ ĐỌC world, KHÔNG mutate state, KHÔNG đặt giá,
KHÔNG rẽ nhánh engine, KHÔNG vào world_hash. Mọi đại lượng tái dựng từ state ĐÃ CÓ
(ledger, hợp đồng, cửa sổ thanh toán) — không tạo bút toán mới, không đăng ký luồng.

- Tín dụng (T06): CLAIMS VIEW tái dựng từ clause hợp đồng ĐANG HIỆU LỰC. Hợp đồng là
  single source of truth; nợ KHÔNG là số dư âm mà là NGHĨA VỤ CHUYỂN GIAO tương lai.
- Tiền (T07): tỷ trọng giá trị thanh toán bằng xu đọc từ ``w.kl_thanh_toan_tick`` +
  ledger; engine KHÔNG ép xu (giữ đúng market.py).
- Hộ (T04): thặng dư bán chợ, gini tiêu dùng/thu nhập — TÁCH khỏi gini tồn kho.
- Tài khóa (T08): thuế thu tick này + số dư CONG_QUY (=0 vì rebate chia hết ngay).
- Chợ/đất (T05): phân tán giá quy thóc giữa các sổ lệnh (proxy in-memory).

Đại lượng chưa đủ state để tính TRUNG THỰC → trả ``None`` (KHÔNG bịa 0). Coverage được
báo kèm (``n_claims``/``n_traders``/``n_muc_gia``...) để không suy luận khi mẫu quá thưa.

Invariant (test-enforced — đối xứng claim): với mỗi clause chuyển giao của hợp đồng
hiệu lực, "tài sản đòi nợ của chủ nợ" = "nghĩa vụ của con nợ" theo (đơn vị, khối
lượng). Đối xứng theo CẤU TRÚC vì mỗi claim tái dựng từ đúng một clause (creditor=`den`,
debtor=`tu`) — không có claim mồ côi/thiếu counterpart.
"""

from __future__ import annotations

import math
from statistics import mean, median, pstdev
from typing import Any

from engine.contracts import gia_tri_thi_truong
from engine.economy import households
from engine.ledger import EPSILON
from engine.metrics import gini, gini_thu_nhap, velocity_tien
from engine.spatial import _khong_gian_bat
from engine.world import CONG_QUY, World


def _hhi(gia_tri) -> float | None:
    """Chỉ số tập trung Herfindahl trên tập giá trị dương; None nếu tổng ~0."""
    vals = [float(v) for v in gia_tri if v > EPSILON]
    tong = sum(vals)
    if tong <= EPSILON:
        return None
    return round(sum((v / tong) ** 2 for v in vals), 6)


def _ky_con_lai(tuoi: int, thoi_han: int | None, moi_n: int) -> int:
    """Số kỳ chuyển giao định kỳ CÒN LẠI đến thời hạn (nghĩa vụ tương lai).

    Hợp đồng vô thời hạn (``thoi_han is None``) → không chặn được horizon, trả 0
    (nghĩa vụ tương lai không xác định; báo trung thực thay vì cộng vô hạn)."""
    if thoi_han is None or moi_n <= 0:
        return 0
    return sum(1 for t in range(tuoi + 1, thoi_han + 1) if t % moi_n == 0)


def _thanh_khoan_quy_thoc(w: World, aid: str, xu_gia: float | None) -> float:
    """Tài sản thanh khoản của một chủ thể quy thóc = thóc + xu (theo giá chợ)."""
    thoc = w.ledger.so_du(aid, "thoc")
    xu = w.ledger.so_du(aid, "xu")
    return thoc + (xu * xu_gia if xu_gia else 0.0)


def claims_view(w: World) -> list[dict[str, Any]]:
    """Tái dựng quan hệ chủ nợ→con nợ từ clause chuyển giao của hợp đồng HIỆU LỰC.

    Mỗi claim = một nghĩa vụ chuyển giao còn hiệu lực: ``tu`` là con nợ (bên chuyển),
    ``den`` là chủ nợ (bên nhận). ``outstanding`` quy thóc theo giá chợ gần nhất
    (clause giải ngân ``tai='ky_ket'`` đã thực thi lúc ký → KHÔNG còn nghĩa vụ)."""
    claims: list[dict[str, Any]] = []
    for hd in sorted(w.hop_dong.values(), key=lambda h: h.id):
        if hd.trang_thai != "hieu_luc":
            continue
        tuoi = w.tick - hd.tick_ky
        co_the_chap = bool(hd.the_chap)
        for ck in hd.dieu_khoan:
            if ck.loai == "chuyen_giao_dinh_ky":
                so_ky = _ky_con_lai(tuoi, hd.thoi_han, ck.moi_n_tick)
                if so_ky <= 0:
                    continue
                don_gia = gia_tri_thi_truong(w, ck.tai_san, ck.so_luong)
                claims.append({
                    "hop_dong": hd.id, "creditor": ck.den, "debtor": ck.tu,
                    "unit": ck.tai_san, "qty": ck.so_luong * so_ky,
                    "outstanding": don_gia * so_ky, "debt_service": don_gia,
                    "secured": co_the_chap,
                })
            elif ck.loai == "chuyen_giao_mot_lan":
                den_han_tuoi = (
                    hd.thoi_han if ck.tai == "dao_han"
                    else ck.tick_t if ck.tai == "tick_T" else None
                )
                if den_han_tuoi is None or tuoi >= den_han_tuoi:
                    continue  # giải ngân ký kết (đã xong) hoặc đã tới/qua hạn
                claims.append({
                    "hop_dong": hd.id, "creditor": ck.den, "debtor": ck.tu,
                    "unit": ck.tai_san, "qty": ck.so_luong,
                    "outstanding": gia_tri_thi_truong(w, ck.tai_san, ck.so_luong),
                    "debt_service": 0.0, "secured": co_the_chap,
                })
    return claims


def _quet_tick(w: World) -> tuple[list[tuple], dict[str, float], float, float, float]:
    """Đọc lại các bút toán của TICK HIỆN TẠI từ ledger (read-only, một lượt).

    Trả (khớp chợ, tiêu dùng quy thóc theo chủ thể, thuế thu vào CONG_QUY, chi công thóc,
    hao mòn thủy lợi). Lịch sử ledger tăng dần theo tick nên duyệt NGƯỢC và dừng khi gặp
    tick cũ (O(bút toán của tick này))."""
    trades: list[tuple] = []
    an_per: dict[str, float] = {}
    tax_revenue = 0.0
    fiscal_spending = 0.0  # thóc treasury tiêu xây thủy lợi tick này
    depreciation = 0.0  # đơn vị thủy lợi hao mòn tick này
    for tx in reversed(w.ledger.lich_su):
        if tx.tick != w.tick:
            break
        ly = tx.ly_do
        if ly.startswith("chợ ") and tx.but_toan:
            spec = ly[len("chợ "):].rsplit(" @", 1)[0]
            if "/" in spec:
                tai_san, thanh_toan = spec.rsplit("/", 1)
                good = sum(bt.so_luong for bt in tx.but_toan
                           if bt.tai_san == tai_san and bt.so_luong > 0)
                pay = sum(bt.so_luong for bt in tx.but_toan
                          if bt.tai_san == thanh_toan and bt.so_luong > 0)
                parties = {bt.chu_the for bt in tx.but_toan}
                xu_recv = {bt.chu_the: bt.so_luong for bt in tx.but_toan
                           if bt.tai_san == "xu" and bt.so_luong > 0}
                trades.append((tai_san, thanh_toan, good, pay, parties, xu_recv))
        elif ly == "thu thuế thu hoạch":
            for bt in tx.but_toan:
                if bt.chu_the == CONG_QUY and bt.tai_san == "thoc" and bt.so_luong > 0:
                    tax_revenue += bt.so_luong
        for d in tx.sinh_huy:
            if d.luong == "an" and d.so_luong < 0:
                gia = 1.0 if d.tai_san == "thoc" else (w.gia_gan_nhat(d.tai_san) or 0.0)
                an_per[d.chu_the] = an_per.get(d.chu_the, 0.0) + (-d.so_luong) * gia
            elif d.tai_san == "thoc" and d.luong == "chi_cong" and d.so_luong < 0:
                fiscal_spending += -d.so_luong
            elif d.tai_san == "thuy_loi" and d.luong == "hao_mon" and d.so_luong < 0:
                depreciation += -d.so_luong
    return trades, an_per, tax_revenue, fiscal_spending, depreciation


_SPATIAL_KEYS = (
    "river_crossing_volume", "ferry_fare_median", "ferry_payment_asset_share",
    "ben_kia_population", "land_use_by_bank", "far_bank_cleared",
    "occupation_entropy", "resource_stock_ca",
)


def _phi_do_tick(w: World) -> list[tuple[str, float]]:
    """Phí đò của TICK HIỆN TẠI đọc lại từ ledger (read-only). Mỗi chuyến-trả-phí là một
    ``ledger.chuyen`` khách→chủ với ``ly_do`` mở đầu 'phí đò ' (``spatial.buoc_qua_song``);
    trả (tài_sản, số_lượng) BÊN CHỦ NHẬN. Chuyến MIỄN PHÍ (chủ thuyền tự qua) KHÔNG có bút
    toán ⇒ không nằm ở đây (đúng: 0 phí, không làm loãng trung vị phí thực).

    Ghi chú nguồn: ``EventLog`` chỉ ghi ra file (không giữ in-memory) nên event ``qua_song``
    KHÔNG truy vấn được lúc chạy — số chuyến lấy từ ``w.ben_kia_tick``, phí từ ledger."""
    ra: list[tuple[str, float]] = []
    for tx in reversed(w.ledger.lich_su):
        if tx.tick != w.tick:
            break
        if tx.ly_do.startswith("phí đò "):
            for bt in tx.but_toan:
                if bt.so_luong > 0:
                    ra.append((bt.tai_san, float(bt.so_luong)))
    return ra


def _spatial_metrics(w: World) -> dict[str, Any]:
    """Metric KHÔNG GIAN (ADR 0005 §10, Lớp-5 chỉ đọc). Gated ``khong_gian.bat``.

    TẮT ⇒ MỌI khóa = ``None`` (không suy diễn khi overlay off) ⇒ metric cũ + world_hash bất
    biến. BẬT ⇒ đếm thật; đại lượng KHÔNG đủ mẫu (trung vị/tỷ trọng phí khi 0 chuyến trả phí,
    entropy khi 0 nhãn) → ``None`` (KHÔNG 0 giả); đại lượng ĐẾM (crossing/ben_kia/cleared) = 0
    khi thật sự chưa có (0 là quan sát THẬT, không phải undefined).

    Ghi chú: ``river_crossing_volume`` và ``ben_kia_population`` TRÙNG nhau theo cơ chế hiện
    hành — ``ben_kia_tick`` reset đầu tick rồi chỉ nạp người qua sông tick này, mỗi người tối
    đa một lần; vẫn báo hai nhãn vì ngữ nghĩa (số chuyến vs dân số bờ kia) tách biệt."""
    if not _khong_gian_bat(w):
        return dict.fromkeys(_SPATIAL_KEYS)

    ben_kia = getattr(w, "ben_kia_tick", set())
    river_crossing_volume = len(ben_kia)
    ben_kia_population = len(ben_kia)

    # phí đò quy thóc (thóc=1.0; tài sản khác theo giá gần nhất). Tài sản chưa có giá ⇒ loại
    # khỏi mẫu (coverage guard) — không bịa giá 0.
    vals: list[float] = []
    val_theo_ts: dict[str, float] = {}
    for ts, sl in _phi_do_tick(w):
        gia = 1.0 if ts == "thoc" else w.gia_gan_nhat(ts)
        if gia is None:
            continue
        v = sl * gia
        vals.append(v)
        val_theo_ts[ts] = val_theo_ts.get(ts, 0.0) + v
    ferry_fare_median = round(float(median(vals)), 6) if vals else None
    tong_val = sum(val_theo_ts.values())
    ferry_payment_asset_share = (
        {a: round(v / tong_val, 6) for a, v in sorted(val_theo_ts.items())}
        if tong_val > EPSILON else None
    )

    # đất theo bờ: ruộng CÓ CHỦ / tổng ruộng mỗi bờ (tỷ lệ ruộng đang canh, độc lập mùa);
    # far_bank_cleared: thửa bờ hoang đã thành ruộng HOẶC có chủ (khai hoang thành công).
    ruong_tong: dict[str, int] = {}
    ruong_canh: dict[str, int] = {}
    far_bank_cleared = 0
    for p in sorted(w.parcels.values(), key=lambda x: x.id):
        if p.bo == "hoang" and (p.loai == "ruong" or p.chu is not None):
            far_bank_cleared += 1
        if p.loai != "ruong" or p.bo is None:
            continue
        ruong_tong[p.bo] = ruong_tong.get(p.bo, 0) + 1
        if p.chu is not None:
            ruong_canh[p.bo] = ruong_canh.get(p.bo, 0) + 1
    land_use_by_bank = {
        bo: round(ruong_canh.get(bo, 0) / n, 6) for bo, n in sorted(ruong_tong.items())
    } or None

    # occupation entropy: Shannon (nat) trên phân bố nhãn giai cấp w.phan_loai (lag 1 tick —
    # engine cập nhật SAU metrics; tick 0 rỗng ⇒ None). Đọc thuần, KHÔNG điều khiển engine.
    nhan = list(getattr(w, "phan_loai", {}).values())
    if nhan:
        dem: dict[str, int] = {}
        for lb in nhan:
            dem[lb] = dem.get(lb, 0) + 1
        tong = len(nhan)
        occupation_entropy = round(
            -sum((c / tong) * math.log(c / tong) for c in dem.values()), 6)
    else:
        occupation_entropy = None

    ca_ton = getattr(w, "ca_ton", None)
    resource_stock_ca = round(float(ca_ton), 6) if ca_ton is not None else None

    return {
        "river_crossing_volume": river_crossing_volume,
        "ferry_fare_median": ferry_fare_median,
        "ferry_payment_asset_share": ferry_payment_asset_share,
        "ben_kia_population": ben_kia_population,
        "land_use_by_bank": land_use_by_bank,
        "far_bank_cleared": far_bank_cleared,
        "occupation_entropy": occupation_entropy,
        "resource_stock_ca": resource_stock_ca,
    }


def research_metrics(w: World) -> dict[str, Any]:
    """Gom mọi metric nghiên cứu T04–T08 + T13 không gian. Thuần đọc; chưa tính được → None."""
    trades, an_per, tax_revenue, fiscal_spending, depreciation = _quet_tick(w)
    xu_gia = w.gia_gan_nhat("xu")

    # ---------------------------------------------------------- T06 tín dụng
    claims = claims_view(w)
    credit_outstanding = round(sum(c["outstanding"] for c in claims), 6)
    debt_service = sum(c["debt_service"] for c in claims)
    by_creditor: dict[str, float] = {}
    debtors: set[str] = set()
    secured = 0.0
    unsecured = 0.0
    for c in claims:
        by_creditor[c["creditor"]] = by_creditor.get(c["creditor"], 0.0) + c["outstanding"]
        debtors.add(c["debtor"])
        if c["secured"]:
            secured += c["outstanding"]
        else:
            unsecured += c["outstanding"]
    tong_tk_debtor = sum(_thanh_khoan_quy_thoc(w, d, xu_gia) for d in sorted(debtors))
    debt_service_ratio = (
        round(debt_service / tong_tk_debtor, 6) if tong_tk_debtor > EPSILON else None
    )
    tong_no = secured + unsecured
    secured_vs_unsecured = {
        "secured": round(secured, 6),
        "unsecured": round(unsecured, 6),
        "secured_share": round(secured / tong_no, 6) if tong_no > EPSILON else None,
    }
    # arrears = hợp đồng KẾT THÚC ở trạng thái vi phạm (tích lũy — hợp đồng vi phạm
    # bị dời sang w.hop_dong_xong ngay trong tick vi phạm).
    arrears = sum(
        1 for h in (*w.hop_dong.values(), *w.hop_dong_xong.values())
        if h.trang_thai == "vi_pham"
    )

    # ---------------------------------------------------------- T07 tiền
    kl = w.kl_thanh_toan_tick
    market_total = sum(kl.values())
    xu_value = kl.get("xu", 0.0)
    thoc_value = kl.get("thoc", 0.0)
    monetary_share_by_value = (
        round(xu_value / market_total, 6) if market_total > EPSILON else None
    )
    xu_stock = w.ledger.tong_tai_san("xu")
    if xu_stock <= EPSILON:
        monetary_share_by_stock = 0.0
    elif xu_gia is None:
        monetary_share_by_stock = None  # có xu nhưng chưa có giá → không quy thóc được
    else:
        thoc_stock = w.ledger.tong_tai_san("thoc")
        xu_thoc = xu_stock * xu_gia
        tong_tk = thoc_stock + xu_thoc
        monetary_share_by_stock = round(xu_thoc / tong_tk, 6) if tong_tk > EPSILON else None
    traders: set[str] = set()
    xu_received: dict[str, float] = {}
    for (_ts, _tt, _good, _pay, parties, xu_recv) in trades:
        traders |= parties
        for chu, v in xu_recv.items():
            xu_received[chu] = xu_received.get(chu, 0.0) + v
    acceptance_breadth = round(len(xu_received) / len(traders), 6) if traders else None
    payment_concentration = _hhi(xu_received.values()) if len(xu_received) >= 2 else None
    kl_hd = float(getattr(w, "kl_hd_tick", 0.0))
    tong_settle = market_total + kl_hd
    barter_share = round(thoc_value / tong_settle, 6) if tong_settle > EPSILON else None
    credit_share = round(kl_hd / tong_settle, 6) if tong_settle > EPSILON else None
    velocity = round(velocity_tien(w), 6)
    velocity_coverage_ok = bool(xu_stock > EPSILON and market_total > EPSILON)

    # ---------------------------------------------------------- T04 hộ
    harvest_total = sum(kg for (_a, kg) in w.gat_tick.values())
    grain_sold = sum(good for (ts, _tt, good, _p, _pt, _x) in trades if ts == "thoc")
    marketed_surplus = (
        round(grain_sold / harvest_total, 6) if harvest_total > EPSILON else None
    )
    hos = households(w)
    if len(hos) >= 2:
        tieu_dung_ho = [sum(an_per.get(m, 0.0) for m in mem) for mem in hos]
        consumption_gini = round(gini(tieu_dung_ho), 6)
    else:
        consumption_gini = None
    song = [a for a in w.agents.values() if a.con_song]
    income_gini = round(gini_thu_nhap(w, song), 6) if song else None
    kgs = [kg for (_a, kg) in w.gat_tick.values() if kg > EPSILON]
    yield_per_parcel = round(float(median(kgs)), 6) if kgs else None
    # poverty_duration: median độ dài streak trên các hộ ĐANG nghèo (streak>=1), None nếu
    # không hộ nào nghèo. n_ho_ngheo_keo_dai: số hộ nghèo ít nhất ``cua_so_tick`` tick liên
    # tiếp. State ``w.poverty_streak`` do engine cập nhật ở ket_toan (ADR 0003 §E); đây CHỈ ĐỌC.
    streaks = [s for s in w.poverty_streak.values() if s >= 1]
    poverty_duration = round(float(median(streaks)), 6) if streaks else None
    nguong_keo_dai = int(w.cfg.get("quan_sat.cua_so_tick"))
    n_ho_ngheo_keo_dai = sum(1 for s in w.poverty_streak.values() if s >= nguong_keo_dai)

    # ---------------------------------------------------------- T08 tài khóa
    # fiscal_balance = số dư CONG_QUY (thu − chi). Hiện = 0 vì thu_thue_va_chia CHIA
    # HẾT ngay trong tick (conduit, KHÔNG tích lũy treasury, KHÔNG chi tiêu công). Báo
    # trung thực: không public wealth phantom. Khi fiscal.bat BẬT (ADR 0004 §T08-C):
    # treasury tích lũy thuế; thủy lợi là hàng công của CONG_QUY, xây tốn thóc/gỗ/công +
    # hao mòn mỗi tick. treasury_balance == fiscal_balance (cùng số dư thóc CONG_QUY).
    fiscal_balance = round(w.ledger.so_du(CONG_QUY, "thoc"), 6)
    treasury_balance = fiscal_balance
    public_good_stock = round(w.ledger.tong_tai_san("thuy_loi"), 6)

    # ---------------------------------------------------------- T05 phân tán giá
    # Proxy in-memory: mỗi sổ lệnh (một làng) khớp tại một p*; gom các p* PHÂN BIỆT
    # quy thóc theo tài sản. KHÔNG phân biệt được hai làng tình cờ khớp cùng giá (CV
    # vẫn đúng = 0 khi đó). Trường `lang` đã thêm vào event khop_cho để phân tích
    # OFFLINE chính xác theo làng (ADR 0003 §D đường D1). Chỉ payment=thoc để giá SO
    # SÁNH ĐƯỢC (giá quy xu ở đơn vị khác, không gộp chung).
    gia_theo_ts: dict[str, set[float]] = {}
    for (ts, tt, good, pay, _pt, _x) in trades:
        if tt != "thoc" or good <= EPSILON:
            continue
        gia_theo_ts.setdefault(ts, set()).add(round(pay / good, 6))
    price_dispersion_by_asset: dict[str, dict[str, Any]] = {}
    for ts in sorted(gia_theo_ts):
        muc_gia = sorted(gia_theo_ts[ts])
        if len(muc_gia) < 2:
            continue  # <2 mức giá → không đo phân tán (undefined, coverage guard)
        mu = mean(muc_gia)
        cv = round(pstdev(muc_gia) / mu, 6) if mu > EPSILON else None
        price_dispersion_by_asset[ts] = {"cv": cv, "n_muc_gia": len(muc_gia)}

    return {
        # T06 — tín dụng (claims view)
        "credit_outstanding": credit_outstanding,
        "debt_service": round(debt_service, 6),
        "debt_service_ratio": debt_service_ratio,
        "claims_concentration": _hhi(by_creditor.values()),
        "secured_vs_unsecured": secured_vs_unsecured,
        "arrears": arrears,
        "n_claims": len(claims),
        # T07 — tiền
        "monetary_share_by_value": monetary_share_by_value,
        "monetary_share_by_stock": monetary_share_by_stock,
        "acceptance_breadth": acceptance_breadth,
        "payment_concentration": payment_concentration,
        "barter_share": barter_share,
        "credit_share": credit_share,
        "velocity": velocity,
        "velocity_coverage_ok": velocity_coverage_ok,
        "n_traders": len(traders),
        "failed_settlement": int(w.settlement_fail_tick),
        # T04 — hộ
        "marketed_surplus": marketed_surplus,
        "consumption_gini": consumption_gini,
        "income_gini": income_gini,
        "yield_per_parcel": yield_per_parcel,
        "harvest_total": round(harvest_total, 6),
        "poverty_duration": poverty_duration,
        "n_ho_ngheo_keo_dai": n_ho_ngheo_keo_dai,
        # T08 — tài khóa
        "tax_revenue": round(tax_revenue, 6),
        "fiscal_balance": fiscal_balance,
        "treasury_balance": treasury_balance,
        "public_good_stock": public_good_stock,
        "fiscal_spending": round(fiscal_spending, 6),
        "depreciation": round(depreciation, 6),
        # T05 — phân tán giá giữa sổ lệnh (proxy)
        "price_dispersion_by_asset": price_dispersion_by_asset,
        # T13 — không gian (ADR 0005 §10); MỌI khóa None khi khong_gian.bat TẮT
        **_spatial_metrics(w),
    }
