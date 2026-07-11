"""Tiện ích test: thế giới nhỏ có kiểm soát."""

from __future__ import annotations

from engine.config import load_config
from engine.intents import KeHoach
from engine.tick import chay_mot_tick
from engine.world import World, tao_the_gioi


def the_gioi_test(seed: int = 1, giu_lai: int = 2, thoc_moi_nguoi: float = 2000.0) -> World:
    """Thế giới thật nhưng chỉ giữ `giu_lai` agent đầu (còn lại cho 'rời cuộc chơi').

    Agent giữ lại được cấp thóc qua luồng khoi_tao để fixture chủ động điều khiển.
    """
    w = tao_the_gioi(load_config(), seed)
    ids = sorted(w.agents)
    for aid in ids[giu_lai:]:
        a = w.agents[aid]
        a.con_song = False
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "rời cuộc chơi (fixture)", 0)
    for aid in ids[:giu_lai]:
        hien_co = w.ledger.so_du(aid, "thoc")
        if thoc_moi_nguoi > hien_co:
            w.ledger.sinh(aid, "thoc", thoc_moi_nguoi - hien_co, "khoi_tao", "fixture", 0)
        w.agents[aid].health = 100.0
    return w


def mind_tinh(ke_hoach_theo_tick: dict[int, dict[str, KeHoach]]):
    """Mind fn phát kế hoạch soạn sẵn theo tick; tick không có → kế hoạch rỗng."""

    def fn(w: World) -> dict[str, KeHoach]:
        kh = ke_hoach_theo_tick.get(w.tick, {})
        # luôn bảo đảm mọi agent sống có KeHoach rỗng (không hành động)
        ra = {aid: KeHoach(id=aid) for aid, a in w.agents.items() if a.con_song}
        ra.update(kh)
        return ra

    return fn


def chay_tick(w: World, mind_fn, n: int = 1) -> None:
    tong_thua = len(w.parcels)
    for _ in range(n):
        chay_mot_tick(w, mind_fn, tong_thua)


def cap_ruong(w: World, aid: str, so_thua: int = 1) -> list[str]:
    """Gán quyền sở hữu vài thửa ruộng tốt gần làng cho agent (fixture)."""
    lang = w.villages[0]
    ruong = sorted(
        (p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None),
        key=lambda p: (abs(p.r - lang.r) + abs(p.c - lang.c), -p.mau_mo, p.id),
    )
    cap = []
    for p in ruong[:so_thua]:
        p.chu = aid
        cap.append(p.id)
    return cap
