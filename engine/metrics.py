"""Metrics cơ bản mỗi tick (SPEC 9.3 — Phase 1 phần lõi).

PHASE 1 "viện hàn lâm": bổ sung 4 chỉ số kinh tế vĩ mô CHUẨN — GDP thực (giá trị
gia tăng), vòng quay tiền (velocity), Gini thu nhập, và tỷ lệ giao dịch "phi lý"
(bounded rationality). Cả bốn đều THUẦN QUAN SÁT (điều luật #7): tính từ ledger +
lịch sử giá đã có, engine KHÔNG BAO GIỜ đọc lại chúng để rẽ nhánh hành vi. Không một
quy luật kinh tế nào bị "mã hóa" ở đây — ta chỉ ĐO cái đã tự phát xảy ra. Thóc là
numéraire (giá quy về thóc = 1).
"""

from __future__ import annotations

from typing import Any

import numpy as np

from engine.economy import household_snapshot, land_price_productivity
from engine.ledger import EPSILON
from engine.world import World

# ------------------------------------------------------------------ Gini gốc


def gini(gia_tri: list[float]) -> float:
    x = np.sort(np.asarray([max(0.0, v) for v in gia_tri], dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


# --------------------------------------- chỉ số vĩ mô (THUẦN QUAN SÁT, chỉ đo)

# Luồng ledger được coi là "hàng SINH ra" (đầu ra sản xuất) khi so_luong > 0, và
# "nguyên liệu trung gian TIÊU HAO" khi so_luong < 0. Danh sách luồng lấy trực tiếp
# từ engine/production.py — đây KHÔNG phải mã hóa quy luật, chỉ là nhãn kế toán để
# biết bút toán nào là sản xuất (loại trừ ăn/hao kho/bốc hơi công... = tiêu dùng).
_SAN_XUAT_LUONG = frozenset({"gat", "khai_thac", "khai_mo", "che_tac", "xay", "duc_xu"})
# lưu ý: "che_tac"/"xay" xuất hiện ở CẢ đầu ra lẫn đầu vào — phân biệt bằng DẤU của
# so_luong, không bằng tên luồng. "giong" (thóc gieo) chỉ là đầu vào trung gian.
_NGUYEN_LIEU_LUONG = frozenset({"che_tac", "xay", "giong"})


def _gia_quy_thoc(w: World, tai_san: str) -> float:
    """Giá gần nhất của một mặt hàng, quy về thóc (numéraire). Chưa từng khớp chợ →
    0 (không tự bịa giá; giá chỉ đến từ khớp cung–cầu — điều luật #7)."""
    if tai_san == "thoc":
        return 1.0
    g = w.gia_gan_nhat(tai_san)
    return float(g) if g is not None else 0.0


def gdp_thuc(w: World) -> float:
    """GDP THỰC (value-added) của tick hiện tại, quy giá thóc.

    = Σ(giá trị hàng+dịch vụ SINH ra) − Σ(giá trị nguyên liệu trung gian TIÊU HAO).
    Ví dụ: gặt sinh thóc (đầu ra) trừ thóc giống (đầu vào); chế công cụ sinh công cụ
    trừ gỗ tiêu hao. Lao động ("cong") là YẾU TỐ SƠ CẤP (chính là phần giá trị gia
    tăng) nên KHÔNG bị trừ như nguyên liệu.

    QUY LUẬT KHÔNG MÃ HÓA Ở ĐÂU: chỉ cộng/trừ bút toán thật trong ledger của tick
    này. Lịch sử ledger xếp theo tick tăng dần nên duyệt NGƯỢC và dừng ngay khi gặp
    tick cũ — chi phí O(số bút toán của tick này), không phải O(toàn lịch sử)."""
    dau_ra = 0.0
    trung_gian = 0.0
    for tx in reversed(w.ledger.lich_su):
        if tx.tick != w.tick:
            break
        for d in tx.sinh_huy:
            if d.so_luong > 0 and d.luong in _SAN_XUAT_LUONG:
                dau_ra += d.so_luong * _gia_quy_thoc(w, d.tai_san)
            elif d.so_luong < 0 and d.luong in _NGUYEN_LIEU_LUONG:
                trung_gian += (-d.so_luong) * _gia_quy_thoc(w, d.tai_san)
    return dau_ra - trung_gian


def velocity_tien(w: World) -> float:
    """VÒNG QUAY TIỀN V = P·Q / M (phương trình trao đổi).

    M = tổng "xu" đang lưu thông (ledger.tong_tai_san). P·Q = tổng GIÁ TRỊ giao dịch
    trong tick, quy thóc = khớp chợ (mọi phương tiện thanh toán) + chuyển giao qua
    hợp đồng. Chưa có xu (M≈0) → velocity = 0 theo quy ước (chưa tiền tệ hóa).

    QUY LUẬT KHÔNG MÃ HÓA: velocity chỉ là TỶ SỐ đo được; engine không dùng nó để
    điều tiết bất cứ gì."""
    m_xu = w.ledger.tong_tai_san("xu")
    if m_xu <= EPSILON:
        return 0.0
    pq = sum(w.kl_thanh_toan_tick.values()) + float(getattr(w, "kl_hd_tick", 0.0))
    return pq / m_xu


def _thu_nhap_cua_song(w: World) -> dict[str, float]:
    """Tổng thu nhập mỗi người qua cửa sổ thu_nhap_4 (cùng cửa sổ observatory dùng
    để phân giai cấp). Bỏ nguồn 'canh_*' vì đó là BỘ ĐẾM thửa, không phải thóc."""
    tong: dict[str, float] = {}
    for d in w.thu_nhap_4:
        for aid, nguon in d.items():
            tong[aid] = tong.get(aid, 0.0) + sum(
                v for k, v in nguon.items() if not k.startswith("canh_")
            )
    return tong


def gini_thu_nhap(w: World, song: list) -> float:
    """GINI THU NHẬP (dòng chảy) — bổ sung cho gini_thoc/gini_dat (tồn kho). Đo bất
    bình đẳng theo thu nhập cửa sổ 4 tick. THUẦN QUAN SÁT."""
    tn = _thu_nhap_cua_song(w)
    return gini([tn.get(a.id, 0.0) for a in song])


def ty_le_phi_ly(w: World) -> float:
    """BOUNDED RATIONALITY: tỷ lệ giao dịch chợ tick này có giá lệch > k·σ so với
    mặt bằng LỊCH SỬ của chính mặt hàng đó (đọc gia_lich_su).

    Thị trường "lý tính hoàn hảo" hội tụ về một giá → tỷ lệ ≈ 0. Nhiều cú khớp lệch
    xa trung bình → agent đang mặc cả "phi lý" (thiếu thông tin/bị ép). Ngưỡng k·σ và
    số điểm tối thiểu đọc từ config (không magic number). Mặt hàng quá ít lịch sử để
    có σ đáng tin → không xét (không kết tội oan). THUẦN QUAN SÁT — engine không phạt
    ai vì "phi lý"."""
    nguong = float(w.cfg.get("quan_sat.nguong_sigma_phi_ly"))
    min_diem = int(w.cfg.get("quan_sat.min_diem_gia_phi_ly"))
    phi_ly = 0
    tong_gd = 0
    for _ts, ls in sorted(w.gia_lich_su.items()):
        gia_truoc = [g for (t, g, _kl, _tt) in ls if t < w.tick]
        gia_nay = [g for (t, g, _kl, _tt) in ls if t == w.tick]
        if not gia_nay or len(gia_truoc) < min_diem:
            continue
        arr = np.asarray(gia_truoc, dtype=float)
        mu = float(arr.mean())
        sigma = float(arr.std())
        if sigma <= EPSILON:
            continue  # giá đứng yên tuyệt đối → không có "lệch σ" để đo
        tong_gd += len(gia_nay)
        phi_ly += sum(1 for g in gia_nay if abs(g - mu) > nguong * sigma)
    return phi_ly / tong_gd if tong_gd else 0.0


def ecology_metrics(w: World) -> dict[str, Any] | None:
    """P4 physical stock surface; no economic decision reads these numbers."""
    from engine.forest import _rung_bat, sinh_khoi_toi_da

    if not _rung_bat(w):
        return None
    forest = [parcel for parcel in w.parcels.values() if parcel.loai == "rung"]
    biomass = sum(float(getattr(parcel, "sinh_khoi", 0.0)) for parcel in forest)
    canopy = [float(getattr(parcel, "tan_rung", 0.0)) for parcel in forest]
    from engine.world import _ga_rung_suc_chua

    wild_k = _ga_rung_suc_chua(w)
    return {
        "forest_area_cells": len(forest),
        "forest_biomass": round(biomass, 9),
        "forest_biomass_capacity": round(len(forest) * sinh_khoi_toi_da(w), 9),
        "forest_canopy_mean": round(sum(canopy) / len(canopy), 9) if canopy else None,
        "wild_chicken_stock": round(float(getattr(w, "ga_rung_ton", 0.0) or 0.0), 9),
        "wild_chicken_capacity": round(wild_k, 9),
        "domestic_chicken_stock": round(
            w.ledger.tong_tai_san("ga") + w.ledger.tong_tai_san("ga_con"), 9
        ),
    }


# ------------------------------------------------------------------ tổng hợp


def tinh_metrics(w: World) -> dict[str, Any]:
    song = [a for a in w.agents.values() if a.con_song]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    thoc = [w.ledger.so_du(a.id, "thoc") for a in song]
    dat_dem: dict[str, int] = {}
    for p in w.parcels.values():
        if p.chu:
            dat_dem[p.chu] = dat_dem.get(p.chu, 0) + 1
    dat = [dat_dem.get(a.id, 0) for a in song]
    nguoi_lon = [a for a in song if a.truong_thanh(tt)]
    ho = household_snapshot(w)
    thoc_ho = [float(row["grain"]) for row in ho]
    ty_le_ho_thieu_an = (
        sum(1 for row in ho if float(row["food_security"]) < 1.0) / len(ho) if ho else 0.0
    )
    dat_metric = land_price_productivity(w, int(w.cfg.get("quan_sat.cua_so_dat_tick")))
    m = {
        "tick": w.tick,
        "nam": w.nam(),
        "dan_so": len(song),
        "nguoi_lon": len(nguoi_lon),
        "tong_thoc": round(sum(thoc), 1),
        "thoc_moi_nguoi": round(sum(thoc) / len(song), 1) if song else 0.0,
        "gini_thoc": round(gini(thoc), 4),
        "gini_dat": round(gini([float(d) for d in dat]), 4),
        # Gini THU NHẬP (dòng chảy) — đi cùng gini_thoc/gini_dat để tools vẽ quỹ đạo
        # bất bình đẳng (observatory.quy_dao_gini). QUY LUẬT KHÔNG MÃ HÓA — chỉ đo.
        "gini_thu_nhap": round(gini_thu_nhap(w, song), 4),
        "dat_tu_huu": sum(dat),
        "ty_le_biet_chu": round(
            sum(1 for a in nguoi_lon if a.e_bac >= 1) / len(nguoi_lon), 4
        ) if nguoi_lon else 0.0,
        "vo_gia_cu": sum(1 for a in song if a.vo_gia_cu),
        "health_tb": round(sum(a.health for a in song) / len(song), 1) if song else 0.0,
        "dich_benh": bool(getattr(w, "dich_benh_tick", False)),
        # Hộ là đơn vị tiêu dùng thực tế; giữ đồng thời metric cá nhân để hai khái niệm
        # không bị lẫn vào nhau trong phân tích phân phối.
        "so_ho": len(ho),
        "thoc_ho_trung_vi": round(float(np.median(thoc_ho)), 3) if thoc_ho else 0.0,
        "gini_thoc_ho": round(gini(thoc_ho), 4),
        "ty_le_ho_thieu_an": round(ty_le_ho_thieu_an, 4),
        "so_gd_dat_cua_so": int(dat_metric["land_transactions_window"]),
        "gia_dat_tren_san_luong_ky_vong": round(
            dat_metric["land_price_to_expected_output"], 4
        ),
        "so_nha": round(w.ledger.tong_tai_san("nha"), 1),
        "so_cong_cu": round(w.ledger.tong_tai_san("cong_cu"), 2),
        # --- chỉ số vĩ mô viện hàn lâm (THUẦN QUAN SÁT) ---
        "gdp": round(gdp_thuc(w), 3),
        "velocity": round(velocity_tien(w), 4),
        "ty_le_phi_ly": round(ty_le_phi_ly(w), 4),
    }
    return m


def buoc_ket_toan(w: World) -> dict[str, Any]:
    from engine import metrics_demography, projects, quotes
    from minds.provenance import summary as decision_provenance_summary

    # Persist a state-derived exposure snapshot before reading its rolling
    # window. It is a no-op for legacy configurations.
    metrics_demography.chot_tick(w)
    m = tinh_metrics(w)
    m["decision_provenance"] = decision_provenance_summary(w)
    demography = metrics_demography.tinh(w)
    if demography is not None:
        m["demography"] = demography
    project_metrics = projects.metrics(w)
    if project_metrics is not None:
        m["projects"] = project_metrics
    quote_metrics = quotes.metrics(w)
    if quote_metrics is not None:
        m["quotes"] = quote_metrics
    ecology = ecology_metrics(w)
    if ecology is not None:
        m["ecology"] = ecology
    w.metrics_lich_su.append(m)
    return m
