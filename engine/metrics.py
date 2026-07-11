"""Metrics cơ bản mỗi tick (SPEC 9.3 — Phase 1 phần lõi)."""

from __future__ import annotations

from typing import Any

import numpy as np

from engine.world import World


def gini(gia_tri: list[float]) -> float:
    x = np.sort(np.asarray([max(0.0, v) for v in gia_tri], dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return 0.0
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))


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
    m = {
        "tick": w.tick,
        "nam": w.tick // 2,
        "dan_so": len(song),
        "nguoi_lon": len(nguoi_lon),
        "tong_thoc": round(sum(thoc), 1),
        "thoc_moi_nguoi": round(sum(thoc) / len(song), 1) if song else 0.0,
        "gini_thoc": round(gini(thoc), 4),
        "gini_dat": round(gini([float(d) for d in dat]), 4),
        "dat_tu_huu": sum(dat),
        "ty_le_biet_chu": round(
            sum(1 for a in nguoi_lon if a.e_bac >= 1) / len(nguoi_lon), 4
        ) if nguoi_lon else 0.0,
        "vo_gia_cu": sum(1 for a in song if a.vo_gia_cu),
        "health_tb": round(sum(a.health for a in song) / len(song), 1) if song else 0.0,
        "so_nha": round(w.ledger.tong_tai_san("nha"), 1),
        "so_cong_cu": round(w.ledger.tong_tai_san("cong_cu"), 2),
    }
    return m


def buoc_ket_toan(w: World) -> dict[str, Any]:
    m = tinh_metrics(w)
    w.metrics_lich_su.append(m)
    return m
