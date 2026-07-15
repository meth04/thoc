"""Simultaneous allocation of a season's common-field use requests.

The old production loop consumed common field requests in lexical agent-id order.  In a
full-autonomy tick, independently prompted residents often picked the same visible parcel;
the low-id resident therefore won every time and the remainder starved despite ample land.

This module implements a small, auditable mechanism instead of hiding a rulebot choice:
agents still submit concrete parcel ids, all requests are observed together, and a seeded
lottery resolves only collisions for that tick.  It grants no title (homestead continues to
be earned by cultivation) and creates no food, labour, or land.
"""

from __future__ import annotations

from typing import Any


def _cfg(x: Any) -> Any:
    return getattr(x, "cfg", x)


def _bat(x: Any) -> bool:
    cfg = _cfg(x)
    return bool(cfg.get("khong_gian.bat", False)) and bool(
        cfg.get("khong_gian.phan_bo_ruong_cong.bat", False)
    )


def phan_bo_ruong_cong(w: Any, ke_hoach: dict[str, Any]) -> set[str]:
    """Resolve contested public rice fields for the current sowing season.

    Plans are changed only by removing public parcels an actor did not receive.  Private and
    leased fields retain their existing path through ``engine.production``.  The return value
    is the set of public fields reserved this tick, used by the transparent food fallback to
    select a genuinely unused field.
    """
    if not _bat(w) or not w.mua_mua():
        return set()

    from engine.contracts import quyen_su_dung_thua
    from engine.spatial import co_the_o_bo

    requested: dict[str, list[str]] = {}
    public_requested: dict[str, set[str]] = {}
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid):
            continue
        kh = ke_hoach[aid]
        rows: list[str] = []
        seen: set[str] = set()
        rights = quyen_su_dung_thua(w, aid)
        for raw in getattr(kh, "canh_thua", ()) or ():
            pid = str(raw)
            if pid in seen:
                continue
            seen.add(pid)
            parcel = w.parcels.get(pid)
            # Invalid/private/unreachable targets keep their normal handler result.  Only a
            # valid shared field participates in this simultaneous allocation.
            if (parcel is None or parcel.loai != "ruong" or parcel.chu is not None
                    or parcel.homestead_ai is not None or pid in rights
                    or not co_the_o_bo(w, aid, parcel.bo)):
                continue
            rows.append(pid)
        if rows:
            requested[aid] = rows
            public_requested[aid] = set(rows)

    awarded: dict[str, set[str]] = {aid: set() for aid in requested}
    reserved: set[str] = set()
    max_rank = max((len(rows) for rows in requested.values()), default=0)
    for rank in range(max_rank):
        by_field: dict[str, list[str]] = {}
        for aid, rows in requested.items():
            if rank >= len(rows):
                continue
            pid = rows[rank]
            if pid not in reserved:
                by_field.setdefault(pid, []).append(aid)
        for pid, candidates in sorted(by_field.items()):
            # Equal access gets priority over an actor already awarded a different common
            # field this season; true ties are broken by a separate deterministic lottery.
            min_wins = min(len(awarded[aid]) for aid in candidates)
            pool = sorted(aid for aid in candidates if len(awarded[aid]) == min_wins)
            g = w.rng.get(f"ruong_cong_lottery:{pid}:rank:{rank}", w.tick)
            winner = pool[int(g.integers(0, len(pool)))]
            awarded[winner].add(pid)
            reserved.add(pid)
            w.events.ghi(w.tick, "phan_bo_ruong_cong", thua=pid, nguoi=winner,
                         thu_tu_uu_tien=rank + 1, so_nguoi_xin=len(candidates))

    from engine.action_journal import rejected as journal_rejected

    for aid, public_ids in sorted(public_requested.items()):
        kh = ke_hoach[aid]
        granted = awarded.get(aid, set())
        # Preserve the action's declared ordering; only contention outcomes change it.
        kh.canh_thua = [
            str(pid) for pid in getattr(kh, "canh_thua", ())
            if str(pid) not in public_ids or str(pid) in granted
        ]
        if not granted:
            first = requested[aid][0]
            journal_rejected(w, aid, "phan_bo_cong", "common_land_lottery_lost",
                             target=first,
                             detail="all requested common fields were awarded by seeded lottery")
            w.events.ghi(w.tick, "phan_bo_ruong_cong_tu_choi", nguoi=aid, thua=first,
                         code="common_land_lottery_lost")
        elif len(granted) < len(public_ids):
            w.events.ghi(w.tick, "phan_bo_ruong_cong_mot_phan", nguoi=aid,
                         duoc=sorted(granted), khong_duoc=sorted(public_ids - granted))
    return reserved


__all__ = ["_bat", "phan_bo_ruong_cong"]
