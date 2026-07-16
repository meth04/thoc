"""Engine-owned application of ADR 0009 v7 shelter-floor intent deltas.

``minds.safety`` derives immutable, facts-only deltas.  This module is the sole
owner of applying those deltas to a mutable plan and recording their provenance
and action-journal lifecycle.  It runs after common-land allocation and the
post-lottery food bridge but before residential-lot resolution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine.intents import KeHoach
from minds.provenance import record_action

if TYPE_CHECKING:
    from engine.world import World
    from minds.safety import ShelterFloorDelta


def _raw(delta: ShelterFloorDelta) -> dict[str, Any]:
    """Render one immutable delta as its public action representation."""
    if delta.action == "chon_dat_o":
        choices = tuple(delta.value)
        return {
            "loai": delta.action,
            "thua": choices[0],
            "du_phong": list(choices[1:]),
        }
    if delta.action == "phan_bo_cong":
        return {"loai": delta.action, "khai_go_cong": float(delta.value)}
    if delta.action == "gop_cong_du_an":
        return {"loai": delta.action, "ref": delta.target, "so_cong": float(delta.value)}
    if delta.action == "tao_du_an":
        return {"loai": delta.action, "loai_du_an": "nha", "thua": delta.target}
    raise ValueError(f"unsupported v7 shelter delta action {delta.action!r}")


def _apply_to_plan(plans: dict[str, KeHoach], delta: ShelterFloorDelta) -> dict[str, Any] | None:
    """Apply a preflight-approved delta and return a bindable project entry."""
    plan = plans.setdefault(delta.aid, KeHoach(id=delta.aid))
    if delta.action == "chon_dat_o":
        plan.chon_dat_o = list(delta.value)
        return None
    if delta.action == "phan_bo_cong":
        plan.cong_khai_go = float(delta.value)
        return None
    if delta.action == "gop_cong_du_an":
        entry = {"ref": delta.target, "so_cong": float(delta.value)}
        plan.gop_cong_du_an.append(entry)
        return entry
    if delta.action == "tao_du_an":
        plan.tao_du_an.append({"loai_du_an": "nha", "thua": delta.target})
        return None
    raise ValueError(f"unsupported v7 shelter delta action {delta.action!r}")


def ap_dung_delta_san_cho_o_v7(
    w: World, plans: dict[str, KeHoach], deltas: tuple[ShelterFloorDelta, ...]
) -> int:
    """Preflight, inject, provenance-label and journal v7 shelter deltas.

    A rejected derived intent is never installed in a plan.  Accepted project
    contribution dictionaries receive the exact request id before the projects
    phase, preserving per-entry quantity and provenance attribution when a
    voluntary sibling has the same actor/action/project target.
    """
    from engine.action_journal import (
        _preflight,
        bind_entry_action_id,
        preflight_ok,
        rejected,
        request,
    )

    accepted = 0
    for delta in deltas:
        raw = _raw(delta)
        code, detail = _preflight(w, delta.aid, raw)
        row = request(
            w,
            delta.aid,
            delta.action,
            origin="survival_floor",
            target=delta.target,
            params=raw,
        )
        if code is not None:
            rejected(
                w,
                delta.aid,
                delta.action,
                code,
                target=delta.target,
                detail=detail,
                preflight=True,
            )
            continue
        entry = _apply_to_plan(plans, delta)
        if entry is not None:
            bind_entry_action_id(entry, row)
        record_action(
            w,
            delta.aid,
            delta.action,
            "survival_floor",
            target=delta.target,
            detail=delta.detail,
        )
        preflight_ok(w, row)
        accepted += 1
    return accepted


__all__ = ["ap_dung_delta_san_cho_o_v7"]
