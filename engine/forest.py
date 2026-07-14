"""Rừng tái tạo cho ``spatial_livelihood_v2``.

Rừng là một stock vật lý theo thửa: ``sinh_khoi`` quyết định lượng gỗ còn có thể lấy,
``tan_rung`` (canopy) quyết định habitat gà rừng. Module này tuyệt đối không chọn nghề,
giá hay hành vi cho tác nhân. Khi cổng ecology tắt, tất cả entry point là no-op để giữ
transition function và hash legacy nguyên vẹn.
"""

from __future__ import annotations

from typing import Any

from engine.ledger import EPSILON, LoiSoKep


def _cfg(x: Any) -> Any:
    return getattr(x, "cfg", x)


def _rung_bat(x: Any) -> bool:
    """Cổng duy nhất của stock rừng versioned (không áp ngầm cho spatial_v1)."""
    cfg = _cfg(x)
    return bool(cfg.get("khong_gian.bat", False)) and bool(
        cfg.get("khong_gian.rung.bat", False)
    )


def _trong_rung_bat(x: Any) -> bool:
    cfg = _cfg(x)
    return _rung_bat(x) and bool(cfg.get("khong_gian.rung.trong_rung.bat", False))


def sinh_khoi_toi_da(w: Any) -> float:
    return max(0.0, float(w.cfg.get("khong_gian.rung.sinh_khoi_toi_da_moi_o", 0.0)))


def _dat_stock(p: Any, k: float, stock: float) -> None:
    """Đặt stock/canopy cùng lúc; canopy là derived state được checkpoint/hash cùng stock."""
    p.sinh_khoi = min(max(0.0, float(stock)), k)
    p.tan_rung = p.sinh_khoi / k if k > EPSILON else 0.0


def khoi_tao_parcel(w_or_cfg: Any, p: Any) -> None:
    """Khởi tạo attribute động cho thửa tại map-gen/migration.

    ``Parcel`` không thêm dataclass field có chủ ý: thêm field sẽ đổi canonical layout của
    mọi artifact cũ. Attribute động chỉ được đưa vào behavioral hash khi ecology bật.
    """
    cfg = _cfg(w_or_cfg)
    if not _rung_bat(cfg) or p.loai != "rung":
        p.sinh_khoi = 0.0
        p.tan_rung = 0.0
        return
    k = max(0.0, float(cfg.get("khong_gian.rung.sinh_khoi_toi_da_moi_o", 0.0)))
    ty_le = min(1.0, max(0.0, float(cfg.get("khong_gian.rung.ty_le_ton_ban_dau", 0.0))))
    _dat_stock(p, k, k * ty_le)


def tai_sinh_rung(w: Any) -> None:
    """Hồi phục logistic trước khai thác trong tick, không sinh asset ledger.

    Biomass là stock tự nhiên chứ không phải hàng hóa trong ví; tăng tự nhiên được journal
    riêng, không mint ``go``. Chỉ gỗ đã chặt mới đi qua FlowRegistry.
    """
    if not _rung_bat(w):
        return
    k = sinh_khoi_toi_da(w)
    if k <= EPSILON:
        return
    rate = max(0.0, float(w.cfg.get("khong_gian.rung.tai_sinh_moi_tick", 0.0)))
    tang = 0.0
    for p in sorted(w.parcels.values(), key=lambda q: q.id):
        if p.loai != "rung":
            continue
        truoc = min(max(0.0, float(getattr(p, "sinh_khoi", 0.0))), k)
        sau = min(k, truoc + rate * truoc * (1.0 - truoc / k))
        _dat_stock(p, k, sau)
        tang += sau - truoc
    if tang > EPSILON:
        w.events.ghi(w.tick, "tai_sinh_rung", sinh_khoi_tang=round(tang, 9))


def _rung_toi_duoc(w: Any, aid: str) -> list[Any]:
    from engine.spatial import co_the_o_bo

    return [
        p
        for p in sorted(w.parcels.values(), key=lambda q: q.id)
        if p.loai == "rung"
        and float(getattr(p, "sinh_khoi", 0.0)) > EPSILON
        and co_the_o_bo(w, aid, p.bo)
    ]


def khai_thac_go(w: Any, aid: str, cong_xin: float, go_moi_cong: float) -> tuple[float, float]:
    """Chặt gỗ bounded bởi biomass thửa rừng có thể tiếp cận.

    Trả ``(go_thu_duoc, cong_da_dung)``. Không còn stock/hết quyền sang bờ kia => cả hai
    bằng 0; caller phát rejection code cho action-result card. Transaction ledger tiêu công
    và sinh gỗ là một operation nguyên tử; stock chỉ mutate sau operation thành công.
    """
    if not _rung_bat(w) or cong_xin <= EPSILON or go_moi_cong <= EPSILON:
        return 0.0, 0.0
    parcels = _rung_toi_duoc(w, aid)
    ton = sum(float(getattr(p, "sinh_khoi", 0.0)) for p in parcels)
    if ton <= EPSILON:
        return 0.0, 0.0
    cong = max(0.0, min(float(cong_xin), float(w.ledger.so_du(aid, "cong"))))
    go = min(ton, cong * float(go_moi_cong))
    cong_dung = go / float(go_moi_cong)
    if go <= EPSILON or cong_dung <= EPSILON:
        return 0.0, 0.0
    try:
        from engine.ledger import DongSinhHuy, Transaction

        w.ledger.ap_dung(Transaction(
            tick=w.tick,
            ly_do="khai thác gỗ",
            sinh_huy=(
                DongSinhHuy(aid, "cong", -cong_dung, "dung"),
                DongSinhHuy(aid, "go", go, "khai_thac"),
            ),
        ))
    except LoiSoKep:
        return 0.0, 0.0

    con_lay = go
    k = sinh_khoi_toi_da(w)
    for p in parcels:
        lay = min(con_lay, float(getattr(p, "sinh_khoi", 0.0)))
        if lay <= EPSILON:
            continue
        truoc = float(p.sinh_khoi)
        canopy_truoc = float(getattr(p, "tan_rung", 0.0))
        _dat_stock(p, k, truoc - lay)
        con_lay -= lay
        w.events.ghi(
            w.tick,
            "khai_go",
            id=aid,
            thua=p.id,
            go=round(lay, 9),
            sinh_khoi_truoc=round(truoc, 9),
            sinh_khoi_sau=round(float(p.sinh_khoi), 9),
            tan_truoc=round(canopy_truoc, 9),
            tan_sau=round(float(p.tan_rung), 9),
        )
        if con_lay <= EPSILON:
            break
    return go, cong_dung


def thu_hoi_go_khai_hoang(w: Any, aid: str, p: Any) -> float:
    """Đổi rừng thành ruộng: thu hồi tỷ lệ cấu hình của biomass còn lại, rồi xóa canopy."""
    if not _rung_bat(w) or p.loai != "rung":
        return 0.0
    ty_le = min(1.0, max(0.0, float(
        w.cfg.get("khong_gian.rung.ty_le_go_thu_hoi_khai_hoang", 0.0)
    )))
    truoc = max(0.0, float(getattr(p, "sinh_khoi", 0.0)))
    canopy_truoc = float(getattr(p, "tan_rung", 0.0))
    go = truoc * ty_le
    if go > EPSILON:
        w.ledger.sinh(aid, "go", go, "khai_thac", "thu hồi gỗ khai hoang", w.tick)
    _dat_stock(p, sinh_khoi_toi_da(w), 0.0)
    w.events.ghi(
        w.tick,
        "pha_rung",
        id=aid,
        thua=p.id,
        go_thu_hoi=round(go, 9),
        sinh_khoi_mat=round(truoc, 9),
        tan_truoc=round(canopy_truoc, 9),
        tan_sau=0.0,
    )
    return go


def trong_rung_dat(w: Any, ke_hoach: dict[str, Any]) -> None:
    """Trồng lại rừng trên đồi reachable; công thật, không mint gỗ hay cây trưởng thành."""
    if not _trong_rung_bat(w):
        return
    from engine.production import _ghi_su_co, _lam_nguyen_tu, ghi_cong_dung
    from engine.spatial import co_the_o_bo

    cong = max(0.0, float(w.cfg.get("khong_gian.rung.trong_rung.cong_moi_thua", 0.0)))
    ty_le = min(1.0, max(0.0, float(
        w.cfg.get("khong_gian.rung.trong_rung.ty_le_sinh_khoi_khoi_dau", 0.0)
    )))
    k = sinh_khoi_toi_da(w)
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        for pid in sorted(getattr(kh, "trong_rung", ())):
            p = w.parcels.get(pid)
            if p is None or p.loai != "doi":
                from engine.action_journal import rejected as journal_rejected

                journal_rejected(w, aid, "trong_rung", "parcel_not_reforestable", target=pid)
                _ghi_su_co(w, aid, f"trồng rừng {pid} không thành: phải là thửa đồi")
                continue
            if not co_the_o_bo(w, aid, p.bo):
                from engine.action_journal import rejected as journal_rejected

                journal_rejected(w, aid, "trong_rung", "parcel_unreachable", target=pid)
                _ghi_su_co(w, aid, f"trồng rừng {pid} không thành: không có quyền tiếp cận đồi")
                continue
            if not _lam_nguyen_tu(w, aid, f"trồng rừng {pid}", [("cong", cong, "dung")], []):
                from engine.action_journal import rejected as journal_rejected

                journal_rejected(w, aid, "trong_rung", "insufficient_labor", target=pid)
                _ghi_su_co(w, aid, f"trồng rừng {pid} không thành: thiếu công")
                continue
            p.loai = "rung"
            _dat_stock(p, k, k * ty_le)
            ghi_cong_dung(w, "phi_nong", cong)
            w.events.ghi(
                w.tick,
                "trong_rung",
                id=aid,
                thua=pid,
                sinh_khoi=round(float(p.sinh_khoi), 9),
                tan=round(float(p.tan_rung), 9),
            )
            from engine.action_journal import executed as journal_executed

            journal_executed(w, aid, "trong_rung", target=pid, code="reforested")


__all__ = [
    "_rung_bat",
    "_trong_rung_bat",
    "khai_thac_go",
    "khoi_tao_parcel",
    "sinh_khoi_toi_da",
    "tai_sinh_rung",
    "thu_hoi_go_khai_hoang",
    "trong_rung_dat",
]
