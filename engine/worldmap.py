"""Sinh bản đồ theo seed: ruộng/rừng/đồi/mỏ/sông + làng đầu tiên."""

from __future__ import annotations

import numpy as np

from engine.config import Config
from engine.types import Parcel, Village


def sinh_ban_do(cfg: Config, rng: np.random.Generator) -> tuple[dict[str, Parcel], list[Village]]:
    h, w = cfg.get("ban_do.kich_thuoc")
    n = h * w
    ty_le_ruong = cfg.get("ban_do.ty_le_ruong")
    mm = cfg.get("ban_do.mau_mo")

    # Sông: một dải dọc uốn nhẹ qua giữa bản đồ
    song_cot = w // 2 + np.cumsum(rng.integers(-1, 2, size=h)).clip(-w // 4, w // 4)
    song_o: set[tuple[int, int]] = {(r, int(w // 2 + dc) % w) for r, dc in enumerate(song_cot)}

    o_con_lai = [(r, c) for r in range(h) for c in range(w) if (r, c) not in song_o]
    rng.shuffle(o_con_lai)

    so_ruong = int(round(n * ty_le_ruong))
    # Ruộng ưu tiên gần sông (ven sông màu mỡ hơn)
    def kc_song(o: tuple[int, int]) -> int:
        return min(abs(o[0] - r) + abs(o[1] - c) for r, c in song_o)

    o_sorted = sorted(o_con_lai, key=lambda o: (kc_song(o), rng.random()))
    o_ruong = o_sorted[:so_ruong]
    o_khac = o_sorted[so_ruong:]

    so_mo = cfg.get("ban_do.so_o_mo_dong")
    # Mỏ đồng nằm trên đồi xa sông nhất
    o_khac_xa = sorted(o_khac, key=kc_song, reverse=True)
    o_mo = o_khac_xa[:so_mo]
    # Nửa còn lại chia rừng/đồi
    o_thuong = o_khac_xa[so_mo:]
    parcels: dict[str, Parcel] = {}

    def them(r: int, c: int, loai: str, mau_mo: float = 1.0) -> None:
        pid = f"P{r:02d}_{c:02d}"
        parcels[pid] = Parcel(id=pid, r=r, c=c, loai=loai, mau_mo=mau_mo)

    for r, c in song_o:
        them(r, c, "song", 0.0)
    for r, c in o_ruong:
        do_mau = float(rng.uniform(mm["min"], mm["max"]))
        if kc_song((r, c)) <= 1:
            do_mau = min(mm["max"] + mm["bonus_ven_song"], do_mau + mm["bonus_ven_song"])
        them(r, c, "ruong", do_mau)
    for r, c in o_mo:
        them(r, c, "mo_dong")
    for i, (r, c) in enumerate(o_thuong):
        them(r, c, "rung" if i % 2 == 0 else "doi")

    # Làng đầu tiên: tâm vùng ruộng ven sông
    rr = int(np.mean([o[0] for o in o_ruong[: max(1, so_ruong // 4)]]))
    cc = int(np.mean([o[1] for o in o_ruong[: max(1, so_ruong // 4)]]))
    villages = [Village(id=0, ten="Làng Gốc Đa", r=rr, c=cc)]
    for v in villages:
        for p in parcels.values():
            if abs(p.r - v.r) + abs(p.c - v.c) <= 8:
                p.lang = v.id
    return parcels, villages


def khoang_cach(p1: Parcel, p2: Parcel) -> int:
    return abs(p1.r - p2.r) + abs(p1.c - p2.c)
