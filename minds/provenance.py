"""Decision provenance for the non-behavioural observation layer.

The simulation must not collapse a plan supplied by an LLM, a policy card,
the explicit survival floor, or a recovery fallback into the same claim. This
module records that distinction after a mind produces a plan and before the
engine executes it. It never mutates the ledger or participates in
``World.behavioral_state()``, so it is an audit surface rather than another
behavioural rule.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

# Keep the required categories present even when a particular run has zero of
# them. ``mock`` and ``external`` make offline baselines honest rather than
# reporting synthetic decisions as live LLM decisions.
ORIGINS: tuple[str, ...] = (
    "llm",
    "mock",
    "policy_card",
    "survival_floor",
    "fallback",
    "translator",
    "external",
)


def reset_tick(w: Any) -> None:
    """Start a fresh, deterministic provenance record for a simulation tick."""
    w.decision_provenance_tick = {"plans": {}, "actions": []}


def _record(w: Any) -> dict[str, Any]:
    record = getattr(w, "decision_provenance_tick", None)
    if not isinstance(record, dict):
        reset_tick(w)
        record = w.decision_provenance_tick
    record.setdefault("plans", {})
    record.setdefault("actions", [])
    return record


def record_plan(w: Any, aid: str, origin: str, *, detail: str | None = None) -> None:
    """Record who supplied the main plan for one actor in this tick."""
    if origin not in ORIGINS:
        raise ValueError(f"unknown decision origin: {origin}")
    item: dict[str, str] = {"origin": origin}
    if detail:
        item["detail"] = str(detail)
    _record(w)["plans"][str(aid)] = item


def record_action(w: Any, aid: str, action: str, origin: str, *,
                  target: str | None = None, detail: str | None = None) -> None:
    """Record an action added after, or distinguished within, a supplied plan."""
    if origin not in ORIGINS:
        raise ValueError(f"unknown decision origin: {origin}")
    item: dict[str, str] = {
        "aid": str(aid),
        "action": str(action),
        "origin": origin,
    }
    if target not in (None, ""):
        item["target"] = str(target)
    if detail:
        item["detail"] = str(detail)
    _record(w)["actions"].append(item)


def _target(raw: dict[str, Any]) -> str | None:
    for key in ("thua", "ref", "di_san", "tre", "den", "cua", "muc_tieu", "entity"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def record_raw_actions(w: Any, aid: str, actions: list[dict[str, Any]], origin: str) -> None:
    """Record the exact public action objects supplied by a decision source."""
    for raw in actions:
        if isinstance(raw, dict) and raw.get("loai"):
            record_action(w, aid, str(raw["loai"]), origin, target=_target(raw))


def record_plan_actions(w: Any, kh: Any, origin: str) -> None:
    """Render a final KeHoach back to wire actions for policy/fallback provenance."""
    from minds.capabilities import hanh_dong_tu_ke_hoach

    record_raw_actions(w, str(kh.id), hanh_dong_tu_ke_hoach(kh), origin)


def summary(w: Any) -> dict[str, dict[str, int] | int]:
    """Return stable zero-filled counts for metrics and offline audit tooling."""
    record = _record(w)
    plans = record.get("plans", {})
    actions = record.get("actions", [])
    plan_counts = Counter(
        value.get("origin") for _aid, value in plans.items()
        if isinstance(value, dict) and value.get("origin") in ORIGINS
    )
    action_counts = Counter(
        value.get("origin") for value in actions
        if isinstance(value, dict) and value.get("origin") in ORIGINS
    )
    return {
        "plans": {origin: int(plan_counts[origin]) for origin in ORIGINS},
        "actions": {origin: int(action_counts[origin]) for origin in ORIGINS},
        "plan_total": len(plans),
        "action_total": len(actions),
    }
