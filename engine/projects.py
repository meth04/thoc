"""Versioned generic multi-tick work orders.

Projects are deliberately small accounting state machines, not a special-case
"house builder".  Their kinds, recipes, output assets and ledger flows are read
from the scenario's ``du_an.cong_trinh`` registry.  A project holds contributed
materials in a ledger escrow, records labour already expended, and only creates
its output once both requirements are physically satisfied.

No wage is invented here: a contributor can be paid only through an existing
contract or quote settlement.  Cancelling/expiring a project refunds still-held
materials to the original contributors; already expended labour is not an asset
and cannot be refunded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from engine.ledger import EPSILON, DongSinhHuy, LoiSoKep, Transaction

ESCROW_PREFIX = "DU_AN:"


def _cfg(x: Any) -> Any:
    return getattr(x, "cfg", x)


def _du_an_bat(x: Any) -> bool:
    return bool(_cfg(x).get("du_an.bat", False))


def _holder(project_id: str) -> str:
    return f"{ESCROW_PREFIX}{project_id}"


@dataclass
class DuAn:
    id: str
    chu: str
    loai: str
    tai_san_ra: str
    so_luong_ra: float
    luong_vat_lieu: str
    luong_san_pham: str
    thua: str | None
    bo: str | None
    lang: int
    cong_can: float
    cong_da: float
    vat_lieu_can: dict[str, float]
    vat_lieu_da: dict[str, float]
    dong_gop_vat_lieu: dict[str, dict[str, float]] = field(default_factory=dict)
    dong_gop_cong: dict[str, float] = field(default_factory=dict)
    tick_tao: int = 0
    han_tick: int = 0
    trang_thai: str = "dang_lam"  # dang_lam | hoan_thanh | da_huy | het_han
    tick_dong: int | None = None
    ly_do_dong: str | None = None


def _settings(w: Any) -> dict[str, Any]:
    raw = w.cfg.get("du_an", {})
    if not isinstance(raw, dict):
        raise ValueError("du_an phải là object")
    return raw


def _registry(w: Any) -> dict[str, dict[str, Any]]:
    raw = _settings(w).get("cong_trinh", {})
    if not isinstance(raw, dict):
        raise ValueError("du_an.cong_trinh phải là object")
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}


def _record_failure(w: Any, aid: str, code: str, detail: str) -> None:
    agent = w.agents.get(aid)
    if agent is not None and agent.con_song:
        agent.su_co = [*agent.su_co, f"[{code}] {detail}"][-3:]
    w.events.ghi(w.tick, "du_an_tu_choi", ai=aid, code=code, chi_tiet=detail)


def _new_id(w: Any) -> str:
    w._next_du_an = int(getattr(w, "_next_du_an", 0)) + 1
    return f"DA{w._next_du_an:05d}"


def _recipe_for(w: Any, spec: dict[str, Any]) -> tuple[dict[str, float], float]:
    recipe_name = str(spec.get("recipe", ""))
    raw = w.cfg.get(f"san_xuat.recipe.{recipe_name}", {})
    if not isinstance(raw, dict):
        raise ValueError("recipe công trình không tồn tại")
    labour = float(raw.get("cong", 0.0))
    if not math.isfinite(labour) or labour <= EPSILON:
        raise ValueError("recipe công trình phải có công dương")
    materials: dict[str, float] = {}
    for asset, amount in raw.items():
        if asset in {"cong", "ra"}:
            continue
        value = float(amount)
        if not math.isfinite(value) or value < 0:
            raise ValueError("nguyên liệu công trình không hợp lệ")
        if value > EPSILON:
            materials[str(asset)] = value
    return materials, labour


def _site_for(w: Any, aid: str, spec: dict[str, Any], raw_site: Any) -> tuple[str | None, str | None]:
    """Validate the worksite when the project registry requires a parcel."""
    needs_site = bool(spec.get("can_thua", False))
    if not needs_site:
        return None, None
    site = str(raw_site) if raw_site not in (None, "") else ""
    if not site:
        _record_failure(w, aid, "no_site", "công trình này cần một thửa của chủ dự án")
        return None, "no_site"
    parcel = w.parcels.get(site)
    if parcel is None or parcel.chu != aid:
        _record_failure(w, aid, "no_right", "không có quyền đặt công trình trên thửa này")
        return None, "no_right"
    return site, None


def _active_owned(w: Any, aid: str) -> int:
    return sum(1 for project in getattr(w, "du_an", {}).values()
               if project.chu == aid and project.trang_thai == "dang_lam")


def _create(w: Any, aid: str, raw: Any) -> None:
    if not isinstance(raw, dict):
        _record_failure(w, aid, "bad_params", "dự án phải là object")
        return
    kind = str(raw.get("loai_du_an", raw.get("cong_trinh", raw.get("loai", ""))))
    spec = _registry(w).get(kind)
    if spec is None:
        _record_failure(w, aid, "unknown_project", "loại công trình không có trong scenario")
        return
    capacity = int(_settings(w).get("toi_da_moi_chu", 0))
    if capacity < 1 or _active_owned(w, aid) >= capacity:
        _record_failure(w, aid, "project_capacity", "đã đạt số dự án đang mở tối đa")
        return
    try:
        materials, labour = _recipe_for(w, spec)
        output = str(spec["tai_san_ra"])
        output_qty = float(spec.get("so_luong_ra", 1.0))
        input_flow = str(spec["luong_vat_lieu"])
        output_flow = str(spec["luong_san_pham"])
    except (KeyError, TypeError, ValueError) as exc:
        _record_failure(w, aid, "bad_project_spec", str(exc))
        return
    if not output or not input_flow or not output_flow or output_qty <= EPSILON:
        _record_failure(w, aid, "bad_project_spec", "đầu ra hoặc luồng ledger không hợp lệ")
        return
    site, problem = _site_for(w, aid, spec, raw.get("thua"))
    if problem is not None:
        return
    agent = w.agents[aid]
    parcel = w.parcels.get(site) if site else None
    duration = int(_settings(w).get("han_tick", 0))
    if duration < 1:
        _record_failure(w, aid, "bad_project_spec", "hạn dự án phải là tick dương")
        return
    project_id = _new_id(w)
    project = DuAn(
        id=project_id,
        chu=aid,
        loai=kind,
        tai_san_ra=output,
        so_luong_ra=output_qty,
        luong_vat_lieu=input_flow,
        luong_san_pham=output_flow,
        thua=site,
        bo=parcel.bo if parcel is not None else None,
        lang=int(agent.lang),
        cong_can=labour,
        cong_da=0.0,
        vat_lieu_can=materials,
        vat_lieu_da={asset: 0.0 for asset in materials},
        tick_tao=w.tick,
        han_tick=w.tick + duration,
    )
    w.du_an[project_id] = project
    w.events.ghi(
        w.tick, "du_an_tao", id=project_id, chu=aid, cong_trinh=kind, thua=site,
        cong_can=round(labour, 9), vat_lieu_can=dict(sorted(materials.items())),
        han_tick=project.han_tick,
    )


def dang_ky_du_an(w: Any, ke_hoach: dict[str, Any]) -> None:
    """Register project requests before labour is issued; no asset is moved here."""
    if not _du_an_bat(w):
        return
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid) or aid not in w.agents:
            continue
        for raw in getattr(ke_hoach[aid], "tao_du_an", ()):
            _create(w, aid, raw)


def _get_open(w: Any, aid: str, raw: Any) -> DuAn | None:
    if not isinstance(raw, dict):
        _record_failure(w, aid, "bad_params", "đóng góp dự án phải là object")
        return None
    project_id = str(raw.get("ref", ""))
    project = getattr(w, "du_an", {}).get(project_id)
    if project is None:
        _record_failure(w, aid, "project_not_found", "không có dự án này")
        return None
    if project.trang_thai != "dang_lam":
        _record_failure(w, aid, "project_closed", "dự án đã đóng")
        return None
    return project


def _can_reach(w: Any, aid: str, project: DuAn) -> bool:
    from engine.spatial import co_the_o_bo

    return co_the_o_bo(w, aid, project.bo)


def _contribute_material(w: Any, aid: str, raw: Any) -> None:
    project = _get_open(w, aid, raw)
    if project is None:
        return
    if not _can_reach(w, aid, project):
        _record_failure(w, aid, "no_access", "chưa tới được địa điểm dự án")
        return
    try:
        asset = str(raw.get("tai_san", ""))
        requested = float(raw.get("so_luong", 0.0))
    except (TypeError, ValueError):
        _record_failure(w, aid, "bad_params", "vật liệu hoặc lượng không đọc được")
        return
    if asset not in project.vat_lieu_can or not math.isfinite(requested) or requested <= EPSILON:
        _record_failure(w, aid, "bad_params", "vật liệu không thuộc recipe hoặc lượng không dương")
        return
    remaining = max(0.0, project.vat_lieu_can[asset] - project.vat_lieu_da[asset])
    actual = min(requested, remaining, w.ledger.so_du(aid, asset))
    if actual <= EPSILON:
        code = "no_inventory" if w.ledger.so_du(aid, asset) <= EPSILON else "material_complete"
        _record_failure(w, aid, code, "không còn vật liệu có thể ký quỹ cho dự án")
        return
    try:
        w.ledger.chuyen(aid, _holder(project.id), asset, actual,
                         f"ký quỹ vật liệu dự án {project.id}", w.tick)
    except LoiSoKep:
        _record_failure(w, aid, "no_inventory", "số dư vật liệu không đủ")
        return
    project.vat_lieu_da[asset] += actual
    by_person = project.dong_gop_vat_lieu.setdefault(aid, {})
    by_person[asset] = by_person.get(asset, 0.0) + actual
    code = "du_an_vat_lieu_mot_phan" if actual + EPSILON < requested else "du_an_vat_lieu"
    w.events.ghi(w.tick, code, id=project.id, ai=aid, tai_san=asset,
                 requested=round(requested, 9), executed=round(actual, 9),
                 remaining=round(project.vat_lieu_can[asset] - project.vat_lieu_da[asset], 9))


def _contribute_labour(w: Any, aid: str, raw: Any) -> None:
    project = _get_open(w, aid, raw)
    if project is None:
        return
    if not _can_reach(w, aid, project):
        _record_failure(w, aid, "no_access", "chưa tới được địa điểm dự án")
        return
    try:
        requested = float(raw.get("so_cong", 0.0))
    except (TypeError, ValueError):
        _record_failure(w, aid, "bad_params", "lượng công không đọc được")
        return
    if not math.isfinite(requested) or requested <= EPSILON:
        _record_failure(w, aid, "bad_params", "lượng công phải dương")
        return
    remaining = max(0.0, project.cong_can - project.cong_da)
    actual = min(requested, remaining, w.ledger.so_du(aid, "cong"))
    if actual <= EPSILON:
        code = "insufficient_labor" if w.ledger.so_du(aid, "cong") <= EPSILON else "labor_complete"
        _record_failure(w, aid, code, "không còn công khả dụng để góp dự án")
        return
    try:
        w.ledger.huy(aid, "cong", actual, "dung", f"góp công dự án {project.id}", w.tick)
    except LoiSoKep:
        _record_failure(w, aid, "insufficient_labor", "công khả dụng không đủ")
        return
    from engine.production import ghi_cong_dung

    ghi_cong_dung(w, "phi_nong", actual)
    project.cong_da += actual
    project.dong_gop_cong[aid] = project.dong_gop_cong.get(aid, 0.0) + actual
    code = "du_an_cong_mot_phan" if actual + EPSILON < requested else "du_an_cong"
    w.events.ghi(w.tick, code, id=project.id, ai=aid,
                 requested=round(requested, 9), executed=round(actual, 9),
                 remaining=round(project.cong_can - project.cong_da, 9))


def _ready(project: DuAn) -> bool:
    return (
        project.cong_da + EPSILON >= project.cong_can
        and all(project.vat_lieu_da.get(asset, 0.0) + EPSILON >= need
                for asset, need in project.vat_lieu_can.items())
    )


def _complete(w: Any, project: DuAn) -> None:
    holder = _holder(project.id)
    try:
        transaction = Transaction(
            tick=w.tick,
            ly_do=f"hoàn thành dự án {project.id}",
            sinh_huy=tuple(
                [DongSinhHuy(holder, asset, -amount, project.luong_vat_lieu)
                 for asset, amount in sorted(project.vat_lieu_can.items())]
                + [DongSinhHuy(project.chu, project.tai_san_ra, project.so_luong_ra,
                               project.luong_san_pham)]
            ),
        )
        w.ledger.ap_dung(transaction)
    except LoiSoKep:
        # This should be unreachable because each accepted contribution is escrowed.
        # Fail closed: retain the project/escrow for audit rather than minting output.
        _record_failure(w, project.chu, "project_escrow_failed", "ký quỹ dự án không khớp")
        return
    project.trang_thai = "hoan_thanh"
    project.tick_dong = w.tick
    project.ly_do_dong = "completed"
    if project.thua and project.tai_san_ra == "nha":
        owner = w.agents.get(project.chu)
        if owner is not None and owner.nha_thua is None:
            owner.nha_thua = project.thua
    w.ghi_ky_uc(
        project.chu,
        f"dự án {project.id} hoàn thành: nhận {project.so_luong_ra:g} {project.tai_san_ra}",
    )
    for aid, labour in sorted(project.dong_gop_cong.items()):
        if aid != project.chu:
            w.ghi_ky_uc(aid, f"tôi đã góp {labour:g} công cho dự án {project.id}")
    w.events.ghi(
        w.tick, "du_an_hoan_thanh", id=project.id, chu=project.chu,
        tai_san_ra=project.tai_san_ra, so_luong_ra=round(project.so_luong_ra, 9),
        cong_da=round(project.cong_da, 9), dong_gop_cong=dict(sorted(project.dong_gop_cong.items())),
    )


def _cancel(w: Any, project: DuAn, status: str, reason: str) -> None:
    if project.trang_thai != "dang_lam":
        return
    holder = _holder(project.id)
    refunds: dict[str, dict[str, float]] = {}
    for aid, assets in sorted(project.dong_gop_vat_lieu.items()):
        for asset, declared in sorted(assets.items()):
            actual = min(float(declared), w.ledger.so_du(holder, asset))
            if actual <= EPSILON:
                continue
            try:
                w.ledger.chuyen(holder, aid, asset, actual,
                                 f"hoàn ký quỹ dự án {project.id}", w.tick)
            except LoiSoKep:
                continue
            refunds.setdefault(aid, {})[asset] = actual
    project.trang_thai = status
    project.tick_dong = w.tick
    project.ly_do_dong = reason
    w.ghi_ky_uc(project.chu, f"dự án {project.id} đóng ({reason})")
    w.events.ghi(w.tick, "du_an_huy", id=project.id, chu=project.chu,
                 trang_thai=status, ly_do=reason,
                 hoan={aid: dict(sorted(assets.items())) for aid, assets in sorted(refunds.items())})


def _cancel_request(w: Any, aid: str, project_id: str) -> None:
    project = getattr(w, "du_an", {}).get(project_id)
    if project is None:
        _record_failure(w, aid, "project_not_found", "không có dự án này")
        return
    if project.chu != aid:
        _record_failure(w, aid, "not_authorized", "chỉ chủ dự án được hủy")
        return
    if project.trang_thai != "dang_lam":
        _record_failure(w, aid, "project_closed", "dự án đã đóng")
        return
    _cancel(w, project, "da_huy", "cancelled_by_owner")


def _expire_and_dead(w: Any) -> None:
    for _project_id, project in sorted(getattr(w, "du_an", {}).items()):
        if project.trang_thai != "dang_lam":
            continue
        if not w.chu_the_hoat_dong(project.chu):
            _cancel(w, project, "da_huy", "owner_unavailable")
        elif w.tick > project.han_tick:
            _cancel(w, project, "het_han", "deadline_expired")


def buoc_du_an(w: Any, ke_hoach: dict[str, Any]) -> None:
    """Apply cancellation, material and labour contributions deterministically."""
    if not _du_an_bat(w):
        return
    _expire_and_dead(w)
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid) or aid not in w.agents:
            continue
        for project_id in sorted(str(x) for x in getattr(ke_hoach[aid], "huy_du_an", ())):
            _cancel_request(w, aid, project_id)
    # Materials are locked first, then labour is consumed. This fixed ordering
    # makes competing partial contributions reproducible.
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid) or aid not in w.agents:
            continue
        for raw in getattr(ke_hoach[aid], "gop_vat_lieu_du_an", ()):
            _contribute_material(w, aid, raw)
    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid) or aid not in w.agents:
            continue
        for raw in getattr(ke_hoach[aid], "gop_cong_du_an", ()):
            _contribute_labour(w, aid, raw)
    for _project_id, project in sorted(getattr(w, "du_an", {}).items()):
        if project.trang_thai == "dang_lam" and _ready(project):
            _complete(w, project)


def xu_ly_nguoi_chet(w: Any, aid: str) -> None:
    """Cancel affected projects before estate processing can distribute the refund."""
    if not _du_an_bat(w):
        return
    for _project_id, project in sorted(getattr(w, "du_an", {}).items()):
        if project.trang_thai != "dang_lam":
            continue
        if project.chu == aid:
            _cancel(w, project, "da_huy", "owner_died")
        elif aid in project.dong_gop_vat_lieu or aid in project.dong_gop_cong:
            _cancel(w, project, "da_huy", "contributor_died")


def visible_to(w: Any, aid: str) -> list[DuAn]:
    """Local, read-only work-order view for a participant on the same bank/village."""
    if not _du_an_bat(w) or aid not in w.agents or not w.agents[aid].con_song:
        return []
    return [
        project for _project_id, project in sorted(getattr(w, "du_an", {}).items())
        if project.trang_thai == "dang_lam"
        and (project.chu == aid or (project.lang == w.agents[aid].lang and _can_reach(w, aid, project)))
    ]


def dong_bo_ky_quy(w: Any) -> None:
    """Reconcile declared material escrow to the ledger after physical decay.

    Same reason as ``quotes.dong_bo_ky_quy``: ``hao_hut_kho`` spoils food held by ANY ledger
    subject, escrow holders included. A project escrowing ``thoc`` therefore drifts from its
    declared ``vat_lieu_da`` and fails the world audit. The ledger is the truth; a project
    that loses escrowed grain to rot simply has less material toward completion — which is the
    honest outcome, not an accounting error to be papered over.
    """
    if not _du_an_bat(w):
        return
    for pid, du_an in sorted(getattr(w, "du_an", {}).items()):
        if du_an.trang_thai != "dang_lam":
            continue
        holder = _holder(pid)
        for asset in sorted(du_an.vat_lieu_da):
            thuc = w.ledger.so_du(holder, asset)
            du_an.vat_lieu_da[asset] = thuc if thuc > 1e-9 else 0.0


def kiem_tra_ky_quy(w: Any) -> list[str]:
    """Audit declared material escrow against ledger balances and closed holders."""
    if not _du_an_bat(w):
        return []
    failures: list[str] = []
    for project_id, project in sorted(getattr(w, "du_an", {}).items()):
        holder = _holder(project_id)
        assets = set(project.vat_lieu_can)
        for asset in sorted(assets):
            actual = w.ledger.so_du(holder, asset)
            expected = (project.vat_lieu_da.get(asset, 0.0)
                        if project.trang_thai == "dang_lam" else 0.0)
            if abs(actual - expected) > 1e-7:
                failures.append(
                    f"ký quỹ dự án {project_id}/{asset}: sổ={actual} khai={expected}"
                )
    return failures


def metrics(w: Any) -> dict[str, Any] | None:
    """Executed project state for P4 reporting; never read by the engine."""
    if not _du_an_bat(w):
        return None
    rows = list(getattr(w, "du_an", {}).values())
    status = {name: sum(1 for project in rows if project.trang_thai == name)
              for name in ("dang_lam", "hoan_thanh", "da_huy", "het_han")}
    escrow: dict[str, float] = {}
    for project in rows:
        if project.trang_thai != "dang_lam":
            continue
        for asset, amount in project.vat_lieu_da.items():
            escrow[asset] = escrow.get(asset, 0.0) + float(amount)
    active = [project for project in rows if project.trang_thai == "dang_lam"]
    return {
        "trang_thai": status,
        "cong_da_gop": round(sum(project.cong_da for project in rows), 9),
        "cong_con_lai_dang_mo": round(sum(
            max(0.0, project.cong_can - project.cong_da) for project in active
        ), 9),
        "vat_lieu_ky_quy_dang_mo": {asset: round(amount, 9)
                                      for asset, amount in sorted(escrow.items())},
    }


__all__ = [
    "DuAn", "_du_an_bat", "buoc_du_an", "dang_ky_du_an", "kiem_tra_ky_quy",
    "metrics", "visible_to", "xu_ly_nguoi_chet",
]
