"""Versioned, append-only action preflight and outcome journal.

An LLM may emit a syntactically valid action whose target is impossible in the
current world.  Dropping it with a bare ``continue`` makes a later analysis
mistake an interface defect for an economic choice.  This module therefore
records the request, a deterministic preflight result, and any execution
result reported by an engine handler.

The journal is scenario-gated.  Old scenarios keep their exact transition and
event surfaces; the v3 livelihood scenario enables it and can additionally
filter an action that preflight has already rejected.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _enabled(w: Any) -> bool:
    return bool(w.cfg.get("minds.action_journal.bat", False))


def _enforce(w: Any) -> bool:
    return _enabled(w) and bool(w.cfg.get("minds.action_journal.enforce", False))


def reset_tick(w: Any) -> None:
    """Reset observation state.  It is deliberately outside behavioral hash."""
    if not _enabled(w):
        return
    w.action_journal_tick = []
    w._action_journal_seq = 0


def _records(w: Any) -> list[dict[str, Any]]:
    if not _enabled(w):
        return []
    rows = getattr(w, "action_journal_tick", None)
    if not isinstance(rows, list):
        reset_tick(w)
        rows = w.action_journal_tick
    return rows


def _emit(w: Any, row: dict[str, Any], stage: str) -> None:
    """Emit a compact event while retaining a rich in-memory metric record."""
    w.events.ghi(
        w.tick,
        "action_result",
        action_id=row["id"],
        intent_id=row["intent_id"],
        ai=row["aid"],
        action=row["action"],
        target=row.get("target"),
        origin=row["origin"],
        stage=stage,
        preflight=row["preflight"],
        execution=row["execution"],
        code=row.get("reason_code"),
    )


def _feedback_limit(w: Any) -> int:
    """Bound the behavioural feedback queue exposed to a v3 agent.

    Action-journal rows themselves are observation-only. A small, explicit
    queue is different: the prompt reads it at the next decision point, so it
    belongs to the v3 behavioural state (see ``World.behavioral_state``).
    """
    try:
        return max(1, int(w.cfg.get("minds.action_journal.feedback_toi_da", 8)))
    except (TypeError, ValueError):
        return 8


def _feedback(w: Any, row: dict[str, Any]) -> None:
    """Give an actor a compact engine-confirmed result for its next prompt.

    ``unobserved`` is intentionally not shown: it means the audit layer lacks
    a dedicated handler result, not that the actor learned an economic fact.
    In particular, missing instrumentation must never become a fake rejection.
    """
    status = str(row.get("execution", ""))
    if status not in {"executed", "rejected", "pending"}:
        return
    if row.get("_feedback_execution") == status:
        return
    aid = str(row.get("aid", ""))
    if aid not in getattr(w, "agents", {}):
        return
    agent = w.agents[aid]
    if not agent.con_song:
        return
    queue = getattr(w, "action_feedback", None)
    if not isinstance(queue, dict):
        queue = {}
        w.action_feedback = queue
    item = {
        "tick": int(w.tick),
        "action": str(row.get("action", "?")),
        "target": row.get("target"),
        "status": status,
        "code": str(row.get("reason_code") or ""),
    }
    detail = row.get("detail")
    if detail:
        item["detail"] = str(detail)[:180]
    queue[aid] = [*queue.get(aid, []), item][-_feedback_limit(w):]
    row["_feedback_execution"] = status


def request(w: Any, aid: str, action: str, *, origin: str = "external",
            target: str | None = None, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Record a requested action before any engine state is touched."""
    rows = _records(w)
    if not _enabled(w):
        return None
    w._action_journal_seq = int(getattr(w, "_action_journal_seq", 0)) + 1
    seq = int(w._action_journal_seq)
    row: dict[str, Any] = {
        "id": f"AR{w.tick:06d}_{seq:04d}",
        "intent_id": f"I{w.tick:06d}_{aid}_{seq:04d}",
        "aid": str(aid),
        "action": str(action),
        "target": str(target) if target not in (None, "") else None,
        "origin": str(origin),
        # `preflight=ok` means it was feasible at this snapshot, not that it
        # executed.  Execution is intentionally a separate axis.
        "preflight": "pending",
        "execution": "planned",
        "reason_code": None,
        "params": dict(params or {}),
    }
    rows.append(row)
    _emit(w, row, "request")
    return row


def _find(w: Any, aid: str, action: str, target: str | None = None) -> dict[str, Any] | None:
    """Find the latest unsettled matching request, deterministically."""
    for row in reversed(_records(w)):
        if row.get("aid") != str(aid) or row.get("action") != str(action):
            continue
        if target not in (None, "") and row.get("target") != str(target):
            continue
        if row.get("execution") in {"planned", "pending"}:
            return row
    return None


def preflight_ok(w: Any, row: dict[str, Any] | None) -> None:
    if row is None:
        return
    row["preflight"] = "ok"
    row["reason_code"] = "feasible"
    _emit(w, row, "preflight")


def rejected(w: Any, aid: str, action: str, code: str, *, target: str | None = None,
             detail: str | None = None, preflight: bool = False, feedback: bool = True) -> None:
    """Record a stable rejection; create a row if parsing never produced one."""
    if not _enabled(w):
        return
    row = _find(w, aid, action, target)
    if row is None:
        row = request(w, aid, action, origin="external", target=target)
    if row is None:
        return
    row["reason_code"] = str(code)
    if detail:
        row["detail"] = str(detail)[:300]
    if preflight:
        row["preflight"] = "rejected"
    agent = w.agents.get(str(aid))
    if feedback and agent is not None and agent.con_song:
        target_text = f" {target}" if target not in (None, "") else ""
        agent.su_co = [*agent.su_co, f"[{code}] {action}{target_text}"][-3:]
    previous = row.get("execution")
    row["execution"] = "rejected"
    _emit(w, row, "preflight" if preflight else "execution")
    if previous != "rejected":
        _feedback(w, row)


def executed(w: Any, aid: str, action: str, *, target: str | None = None,
             code: str = "ok", detail: str | None = None, pending: bool = False) -> None:
    """Mark an engine-confirmed effect (or legitimate multi-tick pending state)."""
    if not _enabled(w):
        return
    row = _find(w, aid, action, target)
    if row is None:
        row = request(w, aid, action, origin="external", target=target)
    if row is None:
        return
    row["preflight"] = "ok" if row["preflight"] == "pending" else row["preflight"]
    previous = row.get("execution")
    row["execution"] = "pending" if pending else "executed"
    row["reason_code"] = str(code)
    if detail:
        row["detail"] = str(detail)[:300]
    _emit(w, row, "execution")
    if previous != row["execution"]:
        _feedback(w, row)


def finalize_unresolved(w: Any) -> None:
    """Close requests a legacy handler did not instrument.

    This is an audit safeguard, not a behavioural fallback. ``unobserved``
    says only that the tick finished without an engine-confirmed outcome for
    the request. It must remain distinct from ``rejected``: a valid order can
    be submitted yet unfilled, and an uninstrumented handler may have changed
    state successfully. Updated handlers should still use ``executed`` or
    ``rejected`` whenever they know the outcome.
    """
    if not _enabled(w):
        return
    for row in _records(w):
        if row.get("execution") != "planned":
            continue
        row["execution"] = "unobserved"
        row["reason_code"] = "no_confirmed_effect"
        row["detail"] = "no dedicated engine outcome was recorded in this tick"
        _emit(w, row, "finalize")


def _target(raw: dict[str, Any]) -> str | None:
    for key in ("thua", "ref", "di_san", "tre", "den", "cua", "muc_tieu", "entity"):
        value = raw.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _origin_for(w: Any, aid: str, action: str, target: str | None) -> str:
    provenance = getattr(w, "decision_provenance_tick", {})
    if isinstance(provenance, dict):
        for row in reversed(provenance.get("actions", [])):
            if not isinstance(row, dict):
                continue
            if row.get("aid") == str(aid) and row.get("action") == str(action):
                if target is None or row.get("target") in (None, str(target)):
                    return str(row.get("origin", "external"))
        plan = provenance.get("plans", {}).get(str(aid))
        if isinstance(plan, dict) and plan.get("origin"):
            return str(plan["origin"])
    return "external"


def _preflight(w: Any, aid: str, raw: dict[str, Any]) -> tuple[str | None, str | None]:
    """Pure feasibility check for targets whose engine handlers used to skip silently."""
    action = str(raw.get("loai", ""))
    if not w.chu_the_hoat_dong(aid):
        return "actor_unavailable", "actor is not active"
    from minds.capabilities import TU_TEN

    cap = TU_TEN.get(action)
    if cap is None or not cap.cong_khai:
        return "unknown_action", "action is not in the public capability catalog"
    if not cap.kha_dung(w):
        return "action_unavailable", "scenario gate is off"

    target = _target(raw)
    if action in {"khai_hoang", "canh_vu_dong", "trong_rung"}:
        parcel = w.parcels.get(str(raw.get("thua", "")))
        if parcel is None:
            return "parcel_not_found", "parcel id does not exist"
        from engine.spatial import co_the_o_bo

        if not co_the_o_bo(w, aid, parcel.bo):
            return "parcel_unreachable", "actor has not reached this bank"
        if action == "khai_hoang":
            if parcel.loai not in {"rung", "doi"}:
                return "parcel_not_clearable", "only common forest or hill can be cleared"
            if parcel.chu is not None:
                return "parcel_not_common", "clearing requires a common parcel"
        elif action == "canh_vu_dong":
            if w.mua_mua():
                return "season_not_available", "winter crops can only be cultivated in the dry season"
            if parcel.loai != "ruong":
                return "parcel_not_cultivable", "winter crops require a field"
            from engine.contracts import quyen_su_dung_thua

            rights = quyen_su_dung_thua(w, aid)
            if parcel.chu not in (None, aid) and parcel.id not in rights:
                return "no_land_right", "actor does not own this field"
            crop = str(raw.get("cay", ""))
            crops = w.cfg.get("khong_gian.vu_dong.cay", {})
            if not isinstance(crops, dict) or crop not in crops:
                return "crop_unavailable", "crop is not enabled by this scenario"
        else:
            if parcel.loai != "doi":
                return "parcel_not_reforestable", "reforestation requires a reachable hill parcel"
    elif action == "phan_bo_cong":
        if raw.get("canh_thua") and not w.mua_mua():
            return "season_not_available", "rice cultivation can only be submitted in a rice season"
        from engine.contracts import quyen_su_dung_thua
        from engine.spatial import co_the_o_bo

        rights = quyen_su_dung_thua(w, aid)
        for parcel_id in raw.get("canh_thua", []) or []:
            parcel = w.parcels.get(str(parcel_id))
            if parcel is None:
                return "parcel_not_found", f"field {parcel_id} does not exist"
            if parcel.loai != "ruong":
                return "parcel_not_cultivable", f"{parcel_id} is not a field"
            if parcel.chu not in (None, aid) and parcel.id not in rights:
                return "no_land_right", f"actor has no cultivation right for {parcel_id}"
            if not co_the_o_bo(w, aid, parcel.bo):
                return "parcel_unreachable", f"actor has not reached {parcel_id}'s bank"
    elif action in {"gop_vat_lieu_du_an", "gop_cong_du_an", "huy_du_an"}:
        project = getattr(w, "du_an", {}).get(str(raw.get("ref", "")))
        if project is None:
            return "project_not_found", "project id is not open in world state"
        if project.trang_thai != "dang_lam":
            return "project_closed", "project is not open"
        if action == "huy_du_an" and project.chu != aid:
            return "not_authorized", "only the project owner can cancel it"
        if action != "huy_du_an":
            from engine.spatial import co_the_o_bo

            if not co_the_o_bo(w, aid, project.bo):
                return "project_unreachable", "actor has not reached the project site"
    elif action == "chap_nhan_bao_gia":
        quote = getattr(w, "bao_gia", {}).get(str(raw.get("ref", "")))
        if quote is None:
            return "offer_not_found", "quote id is not open in world state"
        if quote.trang_thai != "dang_treo" or quote.con_lai <= 0:
            return "quote_closed", "quote is no longer open"
        from engine.quotes import _visible

        if not _visible(w, aid, quote):
            return "offer_not_visible", "quote is not visible or cannot be accepted by this actor"
    elif action == "huy_bao_gia":
        quote = getattr(w, "bao_gia", {}).get(str(raw.get("ref", "")))
        if quote is None:
            return "offer_not_found", "quote id is not open in world state"
        if quote.nguoi_dang != aid:
            return "not_authorized", "only the poster can cancel this quote"
        if quote.trang_thai not in {"dang_treo", "da_khop"}:
            return "quote_closed", "quote is already closed"
    elif target and target.startswith("DA") and target not in getattr(w, "du_an", {}):
        return "project_not_found", "project reference does not exist"
    return None, None


def _drop_rejected(kh: Any, raw: dict[str, Any]) -> None:
    """Remove a preflight-rejected primitive only in the v3 enforcement mode."""
    action = str(raw.get("loai", ""))
    if action == "khai_hoang":
        kh.khai_hoang = [p for p in kh.khai_hoang if p != str(raw.get("thua", ""))]
    elif action == "trong_rung":
        kh.trong_rung = [p for p in kh.trong_rung if p != str(raw.get("thua", ""))]
    elif action == "canh_vu_dong":
        pair = (str(raw.get("thua", "")), str(raw.get("cay", "")))
        kh.canh_vu_dong = [p for p in kh.canh_vu_dong if p != pair]
    elif action == "phan_bo_cong":
        rejected_fields = {str(p) for p in raw.get("canh_thua", []) or []}
        if rejected_fields:
            kh.canh_thua = [p for p in kh.canh_thua if p not in rejected_fields]
    elif action in {"gop_vat_lieu_du_an", "gop_cong_du_an"}:
        field = "gop_vat_lieu_du_an" if action == "gop_vat_lieu_du_an" else "gop_cong_du_an"
        ref = str(raw.get("ref", ""))
        setattr(
            kh,
            field,
            [x for x in getattr(kh, field) if str(x.get("ref", "")) != ref],
        )
    elif action == "huy_du_an":
        kh.huy_du_an = [x for x in kh.huy_du_an if x != str(raw.get("ref", ""))]
    elif action == "chap_nhan_bao_gia":
        ref = str(raw.get("ref", ""))
        kh.chap_nhan_bao_gia = [
            item for item in kh.chap_nhan_bao_gia if str(item.get("ref", "")) != ref
        ]
    elif action == "huy_bao_gia":
        kh.huy_bao_gia = [x for x in kh.huy_bao_gia if x != str(raw.get("ref", ""))]


def preflight_plans(w: Any, plans: dict[str, Any]) -> None:
    """Journal every public action and reject impossible land/project/quote refs visibly."""
    if not _enabled(w):
        return
    from minds.capabilities import hanh_dong_tu_ke_hoach

    for aid in sorted(plans):
        kh = plans[aid]
        for raw in hanh_dong_tu_ke_hoach(kh):
            action = str(raw.get("loai", ""))
            target = _target(raw)
            row = request(w, aid, action, origin=_origin_for(w, aid, action, target),
                          target=target, params=raw)
            code, detail = _preflight(w, aid, raw)
            if code is None:
                preflight_ok(w, row)
            else:
                rejected(w, aid, action, code, target=target, detail=detail, preflight=True)
                if _enforce(w):
                    _drop_rejected(kh, raw)


def summary(w: Any) -> dict[str, Any] | None:
    """Counts for planned/preflight/executed/rejected funnel, never read by behaviour."""
    if not _enabled(w):
        return None
    rows = _records(w)
    preflight = Counter(str(row.get("preflight")) for row in rows)
    execution = Counter(str(row.get("execution")) for row in rows)
    reasons = Counter(str(row.get("reason_code")) for row in rows if row.get("reason_code"))
    origins = Counter(str(row.get("origin")) for row in rows)
    execution_rows = [str(row.get("execution")) for row in rows]
    confirmed = sum(status in {"executed", "rejected", "pending"} for status in execution_rows)
    unobserved = sum(status == "unobserved" for status in execution_rows)
    unresolved = sum(status == "planned" for status in execution_rows)
    return {
        "planned": len(rows),
        "preflight": dict(sorted(preflight.items())),
        "execution": dict(sorted(execution.items())),
        "by_origin": dict(sorted(origins.items())),
        "reason_codes": dict(sorted(reasons.items())),
        # ``planned`` is retained as the historical name for number of
        # requests. These fields state whether requests received a handler
        # confirmation instead of inviting readers to infer it from requests.
        "confirmed": confirmed,
        "unobserved": unobserved,
        "unresolved": unresolved,
        "outcome_coverage": round(confirmed / len(rows), 9) if rows else 1.0,
    }
