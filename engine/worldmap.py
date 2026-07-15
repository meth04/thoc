"""Sinh bản đồ theo seed: ruộng/rừng/đồi/mỏ/sông + làng đầu tiên."""

from __future__ import annotations

import math

import numpy as np

from engine.config import Config
from engine.forest import khoi_tao_parcel
from engine.spatial import _hai_bo_bat
from engine.types import Parcel, Village


def sinh_ban_do(cfg: Config, rng: np.random.Generator) -> tuple[dict[str, Parcel], list[Village]]:
    h, w = cfg.get("ban_do.kich_thuoc")
    # Overlay không gian BẬT → topology hai bờ (ADR 0005 §2.1). TẮT (mặc định) → path
    # legacy nguyên vẹn: KHÔNG tiêu thêm RNG, KHÔNG gán `bo` ⇒ bản đồ + world_hash y hệt.
    if _hai_bo_bat(cfg):
        return _sinh_ban_do_hai_bo(cfg, rng, h, w)
    n = h * w
    ty_le_ruong = cfg.get("ban_do.ty_le_ruong")
    mm = cfg.get("ban_do.mau_mo")

    # Sông: một dải dọc uốn nhẹ qua giữa bản đồ (biên độ uốn = rộng / song_bien_do_chia)
    bien_do = w // int(cfg.get("ban_do.song_bien_do_chia"))
    song_cot = w // 2 + np.cumsum(rng.integers(-1, 2, size=h)).clip(-bien_do, bien_do)
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
        p = Parcel(id=pid, r=r, c=c, loai=loai, mau_mo=mau_mo, mau_mo_goc=mau_mo)
        # No RNG/no hash-visible state when ecology gate is off; v2 gets its explicit stock.
        khoi_tao_parcel(cfg, p)
        parcels[pid] = p

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
    ban_kinh_lang = int(cfg.get("ban_do.ban_kinh_lang"))
    for v in villages:
        for p in parcels.values():
            if abs(p.r - v.r) + abs(p.c - v.c) <= ban_kinh_lang:
                p.lang = v.id
    _them_lo_dat_o(cfg, parcels, villages)
    return parcels, villages


def khoang_cach(p1: Parcel, p2: Parcel) -> int:
    return abs(p1.r - p2.r) + abs(p1.c - p2.c)


def _sinh_ban_do_hai_bo(
    cfg: Config, rng: np.random.Generator, h: int, w: int
) -> tuple[dict[str, Parcel], list[Village]]:
    """Bản đồ HAI BỜ (overlay ON): sông là dải dọc SẠCH (một ô/hàng, bước ±1) chia map
    liền mạch thành bờ ``dan_cu`` (ruộng đã khai phá + làng) và bờ ``hoang`` (rừng/đồi
    công + mỏ = tài nguyên chưa khai thác). Tất định theo ``rng`` seeded; KHÔNG mutate
    ngoài các thửa trả về. `bo` là STATIC, KHÔNG vào world_hash.
    """
    ty_le_ruong = cfg.get("ban_do.ty_le_ruong")
    mm = cfg.get("ban_do.mau_mo")
    so_mo = int(cfg.get("ban_do.so_o_mo_dong"))
    ban_kinh_lang = int(cfg.get("ban_do.ban_kinh_lang"))
    bien_do = w // int(cfg.get("ban_do.song_bien_do_chia"))

    # Sông: một ô mỗi hàng, đi bộ ngẫu nhiên ±1 quanh trục giữa, KẸP trong [1, w-2] để cả
    # hai bờ luôn không rỗng. Bước ≤1 ⇒ dải sông là RÀO 4-liên-thông giữa hai bờ (không rò).
    lo = max(1, w // 2 - bien_do)
    hi = min(w - 2, w // 2 + bien_do)
    sc = np.empty(h, dtype=int)
    cur = w // 2
    for r in range(h):
        cur = int(min(max(cur + int(rng.integers(-1, 2)), lo), hi))
        sc[r] = cur
    song_o = {(r, int(sc[r])) for r in range(h)}

    def _ben(r: int, c: int) -> str:
        return "dan_cu" if c < sc[r] else "hoang"

    def kc_song(o: tuple[int, int]) -> int:
        return min(abs(o[0] - r) + abs(o[1] - c) for r, c in song_o)

    dan_o = [(r, c) for r in range(h) for c in range(w)
             if (r, c) not in song_o and _ben(r, c) == "dan_cu"]
    hoang_o = [(r, c) for r in range(h) for c in range(w)
               if (r, c) not in song_o and _ben(r, c) == "hoang"]
    rng.shuffle(dan_o)
    rng.shuffle(hoang_o)

    # Ruộng đã khai phá TẬP TRUNG bờ dân cư, ưu tiên gần sông (màu mỡ hơn).
    so_ruong = int(round(h * w * ty_le_ruong))
    dan_sorted = sorted(dan_o, key=lambda o: (kc_song(o), rng.random()))
    o_ruong = dan_sorted[:so_ruong]
    dan_con = dan_sorted[so_ruong:]
    # Bờ hoang: mỏ đồng xa sông nhất + phần còn lại chia rừng/đồi (đất công chưa khai hoang).
    hoang_xa = sorted(hoang_o, key=lambda o: (kc_song(o), rng.random()), reverse=True)
    o_mo = hoang_xa[:so_mo]
    o_rung_doi = sorted(hoang_xa[so_mo:] + dan_con)

    parcels: dict[str, Parcel] = {}

    def them(r: int, c: int, loai: str, mau_mo: float, bo: str | None) -> None:
        pid = f"P{r:02d}_{c:02d}"
        p = Parcel(id=pid, r=r, c=c, loai=loai, mau_mo=mau_mo,
                   mau_mo_goc=mau_mo, bo=bo)
        khoi_tao_parcel(cfg, p)
        parcels[pid] = p

    for r, c in song_o:
        them(r, c, "song", 0.0, None)
    for r, c in o_ruong:
        do_mau = float(rng.uniform(mm["min"], mm["max"]))
        if kc_song((r, c)) <= 1:
            do_mau = min(mm["max"] + mm["bonus_ven_song"], do_mau + mm["bonus_ven_song"])
        them(r, c, "ruong", do_mau, "dan_cu")
    for r, c in o_mo:
        them(r, c, "mo_dong", 1.0, "hoang")
    for i, (r, c) in enumerate(o_rung_doi):
        them(r, c, "rung" if i % 2 == 0 else "doi", 1.0, _ben(r, c))

    # Làng đầu tiên: tâm cụm ruộng ven sông (LUÔN nằm bờ dân cư).
    goc = sorted(o_ruong, key=kc_song)[: max(1, so_ruong // 4)]
    rr = int(np.mean([o[0] for o in goc]))
    cc = int(np.mean([o[1] for o in goc]))
    if (rr, cc) in song_o or _ben(rr, cc) != "dan_cu":
        rr, cc = goc[0]  # làm tròn trung bình lỡ rơi ô sông/bờ kia → về ô ruộng chắc chắn
    villages = [Village(id=0, ten="Làng Gốc Đa", r=rr, c=cc)]
    for v in villages:
        for p in parcels.values():
            if abs(p.r - v.r) + abs(p.c - v.c) <= ban_kinh_lang:
                p.lang = v.id
    _them_lo_dat_o(cfg, parcels, villages)
    return parcels, villages


def _them_lo_dat_o(cfg: Config, parcels: dict[str, Parcel], villages: list[Village]) -> None:
    """Add small public residential lots for the versioned settlement treatment.

    The map's production cells are deliberately much coarser than a household plot.  A
    ``dat_o`` parcel therefore overlays a village-core coordinate rather than converting a
    rice field/forest into a whole housing cell.  It cannot be cultivated or harvested and
    has no owner/title; the dynamic right is kept in ``World.quyen_dat_o``.

    This runs only behind the explicit scenario flag.  No RNG is consumed, so every legacy
    map remains byte-for-byte the same when the flag is absent/off.
    """
    if not (bool(cfg.get("khong_gian.bat", False))
            and bool(cfg.get("khong_gian.dat_o.bat", False))):
        return
    if not villages:
        return
    raw = cfg.get("khong_gian.dat_o", {})
    if not isinstance(raw, dict):
        return
    ratio = max(0.0, float(raw.get("he_so_lo_moi_nguoi", 0.0)))
    minimum = max(0, int(raw.get("so_lo_toi_thieu", 0)))
    population = max(0, int(cfg.get("nhan_khau.dan_so_ban_dau")))
    target = max(minimum, int(math.ceil(population * ratio)))
    if target <= 0:
        return

    # Current treatment has one founding village.  The loop is nevertheless per-village so
    # a later map generator can opt in without silently putting all lots in village zero.
    per_village = int(math.ceil(target / len(villages)))
    next_id = 1
    for village in sorted(villages, key=lambda v: v.id):
        candidates = [
            p for p in parcels.values()
            if p.loai != "song" and p.lang == village.id
            and (p.bo is None or p.bo == "dan_cu")
        ]
        candidates.sort(key=lambda p: (
            abs(p.r - village.r) + abs(p.c - village.c), p.id
        ))
        for base in candidates[:per_village]:
            if next_id > target:
                return
            site = Parcel(
                id=f"O{next_id:04d}", r=base.r, c=base.c, loai="dat_o",
                mau_mo=0.0, mau_mo_goc=0.0, lang=village.id, bo=base.bo,
            )
            # ``dat_o`` has no ecological stock, but calling the common initializer keeps a
            # checkpoint/map invariant: every Parcel exposes the dynamic ecology attributes.
            khoi_tao_parcel(cfg, site)
            parcels[site.id] = site
            next_id += 1
