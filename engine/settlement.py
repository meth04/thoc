"""Quyền lô cư trú công cho treatment định cư ban đầu.

Một ``dat_o`` là lô nhỏ trong lõi làng, tách khỏi ruộng sản xuất ở độ phân giải của
bản đồ.  Nó không phải title ruộng, không sinh tài nguyên và không phải một căn nhà
miễn phí.  Quyền duy nhất của người giữ lô là đặt dự án ``nha`` lên đó; gỗ và công vẫn
đi qua sổ cái/dự án như mọi công trình khác.

Các yêu cầu chọn lô được giải quyết đồng thời sau khi mọi quyết định đã tới engine.
Vì vậy hai người chọn cùng lô không còn bị ưu tiên theo thứ tự id: lottery seeded,
audit được, và người thua có thể dùng các lô dự phòng trong cùng tick.

Toàn bộ module là no-op khi ``khong_gian.dat_o.bat`` tắt.  Những treatment lịch sử vì
thế giữ nguyên transition function và world hash.
"""

from __future__ import annotations

from typing import Any


def _cfg(x: Any) -> Any:
    return getattr(x, "cfg", x)


def _dat_o_bat(x: Any) -> bool:
    """Cổng duy nhất của lô cư trú versioned."""
    cfg = _cfg(x)
    return bool(cfg.get("khong_gian.bat", False)) and bool(
        cfg.get("khong_gian.dat_o.bat", False)
    )


def _rights(w: Any) -> dict[str, str]:
    """Return the mutable site→holder registry, repairing old checkpoints lazily."""
    rights = getattr(w, "quyen_dat_o", None)
    if not isinstance(rights, dict):
        rights = {}
        w.quyen_dat_o = rights
    return rights


def lo_cua(w: Any, aid: str) -> str | None:
    """Residential lot currently held by ``aid`` (one person, at most one lot)."""
    if not _dat_o_bat(w):
        return None
    for site, holder in sorted(_rights(w).items()):
        if holder == aid:
            return site
    return None


def co_quyen_xay_nha(w: Any, aid: str, site: str | None) -> bool:
    """Does an actor hold the narrow right to build a house on this site?"""
    if not _dat_o_bat(w) or not site:
        return False
    parcel = w.parcels.get(str(site))
    return bool(
        parcel is not None
        and parcel.loai == "dat_o"
        and _rights(w).get(str(site)) == aid
    )


def lo_cong_kha_dung(w: Any, aid: str) -> list[str]:
    """All unheld lots in the actor's village/bank, ordered only for presentation.

    The list deliberately does not claim that the first lot is economically better.  It
    is an inventory board; the caller can rotate it for a compact private fact card.
    """
    if not _dat_o_bat(w) or aid not in w.agents or not w.agents[aid].con_song:
        return []
    rights = _rights(w)
    actor = w.agents[aid]
    rows = [
        p for p in w.parcels.values()
        if p.loai == "dat_o" and p.id not in rights and p.lang == actor.lang
    ]
    r0, c0 = w.vi_tri_cua(aid)
    rows.sort(key=lambda p: (abs(p.r - r0) + abs(p.c - c0), p.id))
    return [p.id for p in rows]


def lo_uu_tien(w: Any, aid: str, limit: int | None = None) -> list[str]:
    """A deterministic rotated slice of the public lot board for one agent.

    Showing every resident the same first five ids caused a cold-start coordination
    failure analogous to the old common-field collision.  Rotation is an information
    presentation device only: every listed lot is public, requests still compete through
    the same seeded lottery, and callers may submit ranked fallbacks.
    """
    sites = lo_cong_kha_dung(w, aid)
    if not sites:
        return []
    cfg_limit = int(w.cfg.get("khong_gian.dat_o.toi_da_uu_tien", 3))
    n = max(1, min(len(sites), int(limit if limit is not None else cfg_limit)))
    # ``RngTree.get`` is a pure, keyed stream; this does not consume global randomness.
    offset = int(w.rng.get(f"dat_o_board:{aid}", w.tick).integers(0, len(sites)))
    rotated = sites[offset:] + sites[:offset]
    return rotated[:n]


def _eligible(w: Any, aid: str) -> bool:
    if aid not in w.agents or not w.agents[aid].con_song:
        return False
    adult = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    if w.agents[aid].tuoi_nam < adult:
        return False
    if lo_cua(w, aid) is not None:
        return False
    # A completed house is already a residence; taking another common site would turn
    # this narrow entry bridge into a speculative land-grab.
    return w.ledger.so_du(aid, "nha") < 1.0


def _clean_dead_holders(w: Any) -> None:
    """Release a *pre-construction* right when its holder has died.

    A completed house keeps its physical site occupied even after its builder dies.  Estate
    handling of the house asset is deliberately not overwritten here; this small registry
    only prevents a second house project from being placed on the same coordinates.  An empty
    pre-construction permit, in contrast, must not leave a dead name blocking a common lot
    forever.
    """
    rights = _rights(w)
    for site, holder in list(sorted(rights.items())):
        agent = w.agents.get(holder)
        if agent is not None and agent.con_song:
            continue
        # ``nha_thua`` is the canonical physical location after project completion.  It is
        # intentionally checked across living and dead residents: a house may be in estate,
        # but the lot beneath it is still not a vacant building site.
        if any(getattr(resident, "nha_thua", None) == site
               for resident in w.agents.values()):
            continue
        del rights[site]
        w.events.ghi(w.tick, "quyen_dat_o_het_han", thua=site, nguoi=holder,
                     ly_do="holder_unavailable")


def giai_quyet_chon_dat_o(w: Any, ke_hoach: dict[str, Any]) -> int:
    """Resolve ranked residential-lot claims atomically and fairly.

    Returns the number of granted claims.  A claimant progresses through at most the
    configured ranked alternatives during this tick.  Per-lot winner selection uses a
    separate seed keyed by (lot, tick, preference rank), never lexical agent id.
    """
    if not _dat_o_bat(w):
        return 0
    _clean_dead_holders(w)
    rights = _rights(w)
    max_pref = max(1, int(w.cfg.get("khong_gian.dat_o.toi_da_uu_tien", 3)))

    choices: dict[str, list[str]] = {}
    rejected: dict[str, tuple[str, str]] = {}
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        requested = getattr(kh, "chon_dat_o", ()) or ()
        if not requested:
            continue
        if not isinstance(requested, list | tuple):
            rejected[aid] = ("invalid_residential_site", str(requested))
            continue
        if not _eligible(w, aid):
            code = "already_has_residence" if lo_cua(w, aid) is not None else "actor_ineligible"
            rejected[aid] = (code, str(next(iter(requested), "")))
            continue
        seen: set[str] = set()
        ranked: list[str] = []
        for raw_site in requested:
            site = str(raw_site)
            if site in seen:
                continue
            seen.add(site)
            parcel = w.parcels.get(site)
            if parcel is None or parcel.loai != "dat_o":
                continue
            if parcel.lang != w.agents[aid].lang:
                continue
            ranked.append(site)
            if len(ranked) >= max_pref:
                break
        if ranked:
            choices[aid] = ranked
        else:
            rejected[aid] = ("invalid_residential_site", str(next(iter(requested), "")))

    assigned: dict[str, str] = {}
    max_rank = max((len(rows) for rows in choices.values()), default=0)
    for rank in range(max_rank):
        by_site: dict[str, list[str]] = {}
        for aid, ranked in choices.items():
            if aid in assigned or rank >= len(ranked):
                continue
            site = ranked[rank]
            if site in rights:
                continue
            by_site.setdefault(site, []).append(aid)
        for site, candidates in sorted(by_site.items()):
            # Stable candidate ordering makes the sampled index reproducible while the
            # actual winner remains independent of the lexical order.
            candidates = sorted(candidates)
            g = w.rng.get(f"dat_o_lottery:{site}:rank:{rank}", w.tick)
            winner = candidates[int(g.integers(0, len(candidates)))]
            rights[site] = winner
            assigned[winner] = site

    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected

    for aid, site in sorted(assigned.items()):
        requested = choices[aid]
        journal_executed(
            w, aid, "chon_dat_o", target=requested[0], code="residential_site_claimed",
            detail=f"site={site}; preference_rank={requested.index(site) + 1}",
        )
        w.events.ghi(w.tick, "chon_dat_o", nguoi=aid, thua=site,
                     thu_tu_uu_tien=requested.index(site) + 1)
        w.ghi_ky_uc(aid, f"tôi giữ quyền dựng nhà trên lô {site}", doi=True)

    for aid, (code, target) in sorted(rejected.items()):
        journal_rejected(w, aid, "chon_dat_o", code, target=target or None)
        w.events.ghi(w.tick, "chon_dat_o_tu_choi", nguoi=aid, thua=target or None,
                     code=code)
    for aid, requested in sorted(choices.items()):
        if aid in assigned or aid in rejected:
            continue
        journal_rejected(w, aid, "chon_dat_o", "residential_sites_unavailable",
                         target=requested[0],
                         detail="all ranked public lots were claimed in this allocation")
        w.events.ghi(w.tick, "chon_dat_o_tu_choi", nguoi=aid, thua=requested[0],
                     code="residential_sites_unavailable")
    return len(assigned)


__all__ = [
    "_dat_o_bat", "co_quyen_xay_nha", "giai_quyet_chon_dat_o", "lo_cong_kha_dung",
    "lo_cua", "lo_uu_tien",
]
