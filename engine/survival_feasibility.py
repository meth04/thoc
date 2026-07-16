"""Immutable, read-only survival facts for ADR 0009 v7.

This module deliberately owns no world state.  It does not draw RNG, populate a
cache, allocate an identifier, or call stateful weather helpers.  The models are
an engine-to-interface boundary: ``minds`` may render them, but must not
recalculate food, labour, or reachability.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Set
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.intents import KeHoach

if TYPE_CHECKING:
    from engine.world import World


SCHEMA_VERSION = "survival_feasibility_v7"
_HEALTH_MAX = 100.0
_EPSILON = 1e-9
_V7_SCHEDULE = "signing_tick_half_open_v2"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EdibleAssetSpec(_FrozenModel):
    asset: str
    kg_thoc_equivalent_per_kg: float = Field(gt=0)
    decay_kind: Literal["plant", "meat", "fish"]


class FoodRow(_FrozenModel):
    asset: str
    kg: float = Field(ge=0)
    kg_thoc_equivalent: float = Field(ge=0)
    owner_id: str | None = None
    decay_rate: float | None = Field(default=None, ge=0)


class NeedRow(_FrozenModel):
    kg_thoc_equivalent: float = Field(ge=0)


class FeasibilityPath(_FrozenModel):
    protocol: str
    target_id: str
    path_id: str
    visible: bool
    reachable: bool
    feasible: bool
    conditional: bool = False
    input_owner: str | None = None
    reason_codes: tuple[str, ...] = ()
    earliest_output_tick: int | None = None
    earliest_settlement_tick: int | None = None
    earliest_labor_tick: int | None = None
    counterparty_id: str | None = None
    asset: str | None = None
    quantity: float | None = Field(default=None, ge=0)
    unit_price: float | None = Field(default=None, ge=0)
    payment_asset: str | None = None
    payment_amount: float | None = Field(default=None, ge=0)
    payment_owned: bool | None = None
    delivery: str | None = None
    contract_form: str | None = None
    food_at_signing: bool | None = None
    labor_per_tick: float | None = Field(default=None, ge=0)
    duration_ticks: int | None = Field(default=None, ge=1)
    gross_food: float = Field(ge=0, default=0)
    net_food: float = Field(ge=0, default=0)


class SurvivalFeasibility(_FrozenModel):
    """Facts rendered for one living person at one decision point."""

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    as_of_tick: int
    phase: Literal["decision", "post_common_land"]
    residence_id: str
    members: tuple[str, ...]
    owned_by_person: tuple[FoodRow, ...]
    provisionable_in_residence: tuple[FoodRow, ...]
    food_open: tuple[FoodRow, ...]
    decay_before_consumption: tuple[FoodRow, ...]
    guaranteed_settled_inflow: tuple[FoodRow, ...]
    guaranteed_feasible_output: tuple[FoodRow, ...]
    seed_use: tuple[FoodRow, ...]
    need: NeedRow
    gap: NeedRow
    labor_capacity: float = Field(ge=0)
    childcare_due: float = Field(ge=0)
    outgoing_contract_due: float = Field(ge=0)
    voluntary_requested: float = Field(ge=0)
    residual_conservative: float = Field(ge=0)
    production_paths: tuple[FeasibilityPath, ...]
    quote_paths: tuple[FeasibilityPath, ...]
    contract_paths: tuple[FeasibilityPath, ...]


class LaborProjection(_FrozenModel):
    aid: str
    labor_capacity: float = Field(ge=0)
    childcare_due: float = Field(ge=0)
    outgoing_contract_due: float = Field(ge=0)
    voluntary_requested: float = Field(ge=0)
    residual_conservative: float = Field(ge=0)


class SurvivalProjection(_FrozenModel):
    """One no-mutation post-plan residence projection used by the v7 floor."""

    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    as_of_tick: int
    phase: Literal["post_common_land"] = "post_common_land"
    residence_id: str
    members: tuple[str, ...]
    food_open: tuple[FoodRow, ...]
    decay_before_consumption: tuple[FoodRow, ...]
    guaranteed_settled_inflow: tuple[FoodRow, ...]
    guaranteed_feasible_output: tuple[FoodRow, ...]
    seed_use: tuple[FoodRow, ...]
    need: NeedRow
    gap: NeedRow
    labor: tuple[LaborProjection, ...]
    production_paths: tuple[FeasibilityPath, ...]


def health_max() -> float:
    """The engine-wide clamped health upper bound used by v7 validation."""
    return _HEALTH_MAX


def edible_assets(w: World) -> tuple[EdibleAssetSpec, ...]:
    """Return the complete, deterministic edible asset identity.

    Plant foods retain the existing ``engine.economy.food_equivalence`` factors;
    fresh meat and fish use their own configured nutrition and decay mechanisms.
    The order is a public schema order, not an economic ranking.
    """
    crops = w.cfg.get("khong_gian.vu_dong.cay", {})
    rows = [EdibleAssetSpec(asset="thoc", kg_thoc_equivalent_per_kg=1.0,
                             decay_kind="plant")]
    if isinstance(crops, dict):
        for asset, spec in sorted(crops.items()):
            if isinstance(spec, dict) and "quy_doi_dinh_duong" in spec:
                factor = float(spec["quy_doi_dinh_duong"])
                if not math.isfinite(factor) or factor <= 0:
                    raise ValueError(f"invalid nutritional factor for crop {asset!r}")
                rows.append(EdibleAssetSpec(
                    asset=str(asset), kg_thoc_equivalent_per_kg=factor, decay_kind="plant"
                ))
    rows.extend((
        EdibleAssetSpec(
            asset="thit",
            kg_thoc_equivalent_per_kg=float(w.cfg.get("chan_nuoi.thit_quy_doi_dinh_duong")),
            decay_kind="meat",
        ),
        EdibleAssetSpec(
            asset="ca",
            kg_thoc_equivalent_per_kg=float(w.cfg.get("danh_ca.ca_quy_doi_dinh_duong")),
            decay_kind="fish",
        ),
    ))
    return tuple(rows)


def validate_survival_config(cfg: object) -> None:
    """Reject malformed v7 treatment configs before a world is created.

    Earlier overlays have no ``phien_ban: v7`` marker and deliberately retain
    their historical behaviour.  A partially enabled v7 treatment is rejected
    rather than silently acting like v4/v5.
    """
    shelter = cfg.get("minds.san_cho_o_toi_thieu", {})
    if not isinstance(shelter, dict) or shelter.get("phien_ban") != "v7":
        return
    if not bool(shelter.get("bat", False)):
        raise SystemExit("CẤU HÌNH BỊ CHẶN (ADR 0009): shelter v7 phải bật rõ ràng")
    if not bool(cfg.get("minds.survival_feasibility.bat", False)):
        raise SystemExit("CẤU HÌNH BỊ CHẶN (ADR 0009): shelter v7 cần survival_feasibility.bat=true")
    try:
        threshold = float(shelter["nguong_health_khoi_cong"])
        cap = float(shelter["cong_gop_moi_tick"])
        nominal_labor = float(cfg.get("nhu_cau.ngay_cong_moi_tick"))
    except (KeyError, TypeError, ValueError) as exc:
        raise SystemExit(f"CẤU HÌNH BỊ CHẶN (ADR 0009): giá trị v7 thiếu/sai: {exc}") from exc
    if not all(math.isfinite(value) for value in (threshold, cap, nominal_labor)):
        raise SystemExit("CẤU HÌNH BỊ CHẶN (ADR 0009): số v7 phải hữu hạn")
    if not 0.0 <= threshold < health_max():
        raise SystemExit(
            "CẤU HÌNH BỊ CHẶN (ADR 0009): nguong_health_khoi_cong phải thuộc "
            f"[0, {health_max():g})"
        )
    if not 0.0 <= cap <= nominal_labor:
        raise SystemExit(
            "CẤU HÌNH BỊ CHẶN (ADR 0009): cong_gop_moi_tick phải thuộc "
            f"[0, {nominal_labor:g}]"
        )
    schedule = cfg.get("hop_dong.gop_cong_lich", "")
    if schedule != _V7_SCHEDULE:
        raise SystemExit(
            "CẤU HÌNH BỊ CHẶN (ADR 0009): hop_dong.gop_cong_lich phải là "
            f"{_V7_SCHEDULE!r}"
        )
    if not bool(cfg.get("hop_dong.tiep_can_vat_ly_v2", False)):
        raise SystemExit("CẤU HÌNH BỊ CHẶN (ADR 0009): cần hop_dong.tiep_can_vat_ly_v2=true")


def _residence(w: World, aid: str) -> tuple[str, tuple[str, ...]]:
    if aid not in w.agents or not w.agents[aid].con_song:
        raise ValueError(f"survival feasibility unavailable for inactive agent {aid!r}")
    # Do not use household.rid_cua()/World.ho_cua() on the persistent branch:
    # their derived index cache is harmless to the hash but forbidden to this
    # explicitly cache-free API.  Scan serialized residence state instead.
    for rid, residence in sorted(getattr(w, "cu_tru", {}).items()):
        if aid in residence.thanh_vien:
            members = tuple(sorted(
                member for member in residence.thanh_vien
                if member in w.agents and w.agents[member].con_song
            ))
            if aid not in members:
                raise ValueError(f"active agent {aid!r} is outside residence {rid!r}")
            return str(rid), members
    members = tuple(sorted(
        member for member in w.ho_cua(aid)
        if member in w.agents and w.agents[member].con_song
    ))
    if aid not in members:
        raise ValueError(f"active agent {aid!r} is outside its own legacy household")
    # Legacy household grouping has no serialized residence id.  This explicit
    # label is read-only and cannot be mistaken for a newly created household.
    return f"legacy:{members[0]}", members


def _storage_decay_rate(w: World, owner: str) -> float:
    from engine.research import duoc_ap_dung

    base = float(w.cfg.get("san_xuat.hao_hut_kho_moi_tick"))
    reduction = float(duoc_ap_dung(w, owner, "luu_kho"))
    for blueprint in getattr(w, "blueprints", {}).values():
        if (getattr(blueprint, "hang_moi", None)
                and getattr(blueprint, "hieu_ung", None) == "luu_kho"
                and w.ledger.so_du(owner, blueprint.hang_moi) >= 1.0):
            reduction += float(blueprint.hieu_ung_do_lon)
    floor = float(w.cfg.get("tieu_dung.san_hao_kho"))
    return base * max(floor, 1.0 - reduction)


def _decay_rate(w: World, owner: str, spec: EdibleAssetSpec) -> float:
    if spec.decay_kind == "plant":
        return _storage_decay_rate(w, owner)
    if spec.decay_kind == "meat":
        return float(w.cfg.get("chan_nuoi.thit_hao_moi_tick"))
    return float(w.cfg.get("danh_ca.ca_hao_moi_tick"))


def _food_rows(w: World, owners: tuple[str, ...]) -> tuple[FoodRow, ...]:
    specs = edible_assets(w)
    rows: list[FoodRow] = []
    for owner in owners:
        for spec in specs:
            kg = max(0.0, float(w.ledger.so_du(owner, spec.asset)))
            if kg > _EPSILON:
                rows.append(FoodRow(owner_id=owner, asset=spec.asset, kg=kg,
                                    kg_thoc_equivalent=kg * spec.kg_thoc_equivalent_per_kg))
    return tuple(rows)


def _aggregate_rows(rows: tuple[FoodRow, ...]) -> tuple[FoodRow, ...]:
    by_asset: dict[str, tuple[float, float]] = {}
    for row in rows:
        kg, equiv = by_asset.get(row.asset, (0.0, 0.0))
        by_asset[row.asset] = (kg + row.kg, equiv + row.kg_thoc_equivalent)
    return tuple(
        FoodRow(asset=asset, kg=kg, kg_thoc_equivalent=equiv)
        for asset, (kg, equiv) in sorted(by_asset.items())
    )


def _decay_rows(w: World, rows: tuple[FoodRow, ...]) -> tuple[FoodRow, ...]:
    specs = {spec.asset: spec for spec in edible_assets(w)}
    result: list[FoodRow] = []
    for row in rows:
        if row.owner_id is None:
            continue
        spec = specs[row.asset]
        rate = _decay_rate(w, row.owner_id, spec)
        amount = row.kg * rate
        if amount > _EPSILON:
            result.append(FoodRow(
                owner_id=row.owner_id, asset=row.asset, kg=amount,
                kg_thoc_equivalent=amount * spec.kg_thoc_equivalent_per_kg,
                decay_rate=rate,
            ))
    return tuple(sorted(result, key=lambda row: (row.owner_id or "", row.asset)))


def _need(w: World, members: tuple[str, ...]) -> float:
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    adult = float(w.cfg.get("nhu_cau.nguoi_lon_kg_tick"))
    child = float(w.cfg.get("nhu_cau.tre_em_kg_tick"))
    return sum(adult if w.agents[aid].tuoi_nam >= adult_age else child for aid in members)


def _labor_capacity(w: World, aid: str) -> float:
    agent = w.agents[aid]
    if not agent.con_song:
        return 0.0
    age = agent.tuoi_nam
    cfg = w.cfg.raw()
    nominal = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    child_age = float(w.cfg.get("nhu_cau.tre_em_gop_cong_tu_tuoi"))
    by_age = cfg["lao_dong_theo_tuoi"]
    if age > float(by_age["tuoi_nghi"]):
        factor = float(by_age["he_so_sau_nghi"])
    elif age > float(by_age["tuoi_giam_suc"]):
        factor = float(by_age["he_so_sau_giam"])
    elif age >= adult_age:
        factor = 1.0
    elif age >= child_age:
        factor = float(w.cfg.get("nhu_cau.ty_le_cong_tre_em"))
    else:
        return 0.0
    return max(0.0, nominal * max(0.0, min(health_max(), agent.health)) / health_max() * factor)


def _childcare_due(w: World, members: tuple[str, ...]) -> dict[str, float]:
    """Conservative within-residence mandatory-care allocation, without mutation."""
    due = {aid: 0.0 for aid in members}
    cfg = w.cfg.get("khong_gian.cham_tre", {})
    if not isinstance(cfg, dict) or not bool(cfg.get("bat", False)):
        return due
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    child_age = float(cfg["tuoi_can_cham"])
    labor = float(cfg["cong_cham_moi_tre"])
    adults = sorted(
        (aid for aid in members if w.agents[aid].tuoi_nam >= adult_age),
        key=lambda aid: (-_labor_capacity(w, aid), aid),
    )
    if not adults:
        return due
    for _child in sorted(aid for aid in members if w.agents[aid].tuoi_nam < child_age):
        remaining = labor
        for adult in adults:
            available = max(0.0, _labor_capacity(w, adult) - due[adult])
            used = min(remaining, available)
            due[adult] += used
            remaining -= used
            if remaining <= _EPSILON:
                break
    return due


def _outgoing_contract_due(w: World, aid: str) -> float:
    total = 0.0
    schedule_v7 = w.cfg.get("hop_dong.gop_cong_lich", "") == _V7_SCHEDULE
    for _hid, contract in sorted(getattr(w, "hop_dong", {}).items()):
        if getattr(contract, "trang_thai", None) != "hieu_luc":
            continue
        age = int(w.tick) - int(getattr(contract, "tick_ky", -1))
        duration = getattr(contract, "thoi_han", None)
        for clause in getattr(contract, "dieu_khoan", ()):
            if getattr(clause, "loai", None) != "gop_cong" or getattr(clause, "tu", None) != aid:
                continue
            due = (duration is None or 0 <= age < duration) if schedule_v7 else True
            if due:
                total += max(0.0, float(clause.so_cong_moi_tick))
    return total


def _requested_labor(w: World, aid: str, plan: KeHoach | None) -> float:
    if plan is None:
        return 0.0
    total = max(0.0, float(getattr(plan, "cong_khai_go", 0.0)))
    total += max(0.0, float(getattr(plan, "cong_khai_quang", 0.0)))
    total += max(0.0, float(getattr(plan, "danh_ca_cong", 0.0)))
    total += max(0.0, float(getattr(plan, "bat_ga_cong", 0.0)))
    total += sum(max(0.0, float(row.get("so_cong", 0.0)))
                 for row in getattr(plan, "gop_cong_du_an", ()) if isinstance(row, dict))
    total += float(w.cfg.get("san_xuat.cong_moi_thua")) * len(getattr(plan, "canh_thua", ()))
    crops = w.cfg.get("khong_gian.vu_dong.cay", {})
    if isinstance(crops, dict):
        for _parcel, crop in getattr(plan, "canh_vu_dong", ()):
            spec = crops.get(crop)
            if isinstance(spec, dict):
                total += max(0.0, float(spec.get("cong", 0.0)))
    return total


def _rice_path(w: World, aid: str, parcel_id: str, *, allocated: Set[str],
               selected: bool) -> FeasibilityPath:
    parcel = w.parcels.get(parcel_id)
    reasons: list[str] = []
    reachable = False
    if parcel is None or parcel.loai != "ruong":
        reasons.append("parcel_not_cultivable")
    else:
        from engine.contracts import quyen_su_dung_thua
        from engine.spatial import co_the_o_bo

        rights = quyen_su_dung_thua(w, aid)
        reachable = bool(co_the_o_bo(w, aid, parcel.bo))
        if not w.mua_mua():
            reasons.append("season_not_available")
        if parcel.chu not in (None, aid) and parcel.id not in rights:
            reasons.append("no_land_right")
        if parcel.chu is None and parcel.id not in allocated:
            reasons.append("contested_common_land")
        if parcel.homestead_ai not in (None, aid):
            reasons.append("homestead_reserved")
        if not reachable:
            reasons.append("parcel_unreachable")
    seed = float(w.cfg.get("san_xuat.giong_kg_moi_thua"))
    labor = float(w.cfg.get("san_xuat.cong_moi_thua"))
    if w.ledger.so_du(aid, "thoc") + _EPSILON < seed:
        reasons.append("thieu_giong")
    if _labor_capacity(w, aid) + _EPSILON < labor:
        reasons.append("insufficient_labor")
    # Calling World.thoi_tiet could create a cache entry and consume RNG.  An
    # uncached current weather is therefore a truthful conditional path, not a
    # fabricated guarantee.
    weather = w.thoi_tiet_nam.get(w.nam(w.tick))
    if weather is None:
        reasons.append("weather_unobserved")
    gross = 0.0
    if parcel is not None and weather is not None:
        weather_cfg = w.cfg.get("thoi_gian.thoi_tiet")
        weather_factor = float(weather_cfg[weather]["he_so"])
        from engine.production import _he_so_nong, _health_mult, _tool_mult

        gross = max(0.0, float(w.cfg.get("san_xuat.san_luong_goc_kg"))
                    * parcel.mau_mo * weather_factor * _tool_mult(w, aid)
                    * _health_mult(w.agents[aid].health) * _he_so_nong(w, aid)
                    * w.agents[aid].tay_nghe)
    feasible = not reasons
    return FeasibilityPath(
        protocol="production", target_id=str(parcel_id), path_id="canh_lua",
        visible=parcel is not None, reachable=reachable, feasible=feasible,
        conditional=("contested_common_land" in reasons or "weather_unobserved" in reasons),
        input_owner=aid, reason_codes=tuple(sorted(reasons)),
        earliest_output_tick=w.tick if selected else w.tick,
        gross_food=gross if feasible else 0.0,
        net_food=max(0.0, gross - seed) if feasible else 0.0,
    )


def _production_paths(w: World, aid: str, *, allocated: Set[str],
                      plan: KeHoach | None, all_visible: bool) -> tuple[FeasibilityPath, ...]:
    if all_visible:
        parcels = sorted(
            parcel.id for parcel in w.parcels.values() if parcel.loai == "ruong"
        )
    else:
        parcels = sorted({str(pid) for pid in getattr(plan, "canh_thua", ())})
    return tuple(_rice_path(w, aid, parcel_id, allocated=allocated,
                            selected=not all_visible) for parcel_id in parcels)


def _labor_projection(w: World, members: tuple[str, ...], plans: Mapping[str, KeHoach]) -> tuple[LaborProjection, ...]:
    care = _childcare_due(w, members)
    rows = []
    for aid in members:
        capacity = _labor_capacity(w, aid)
        childcare = care[aid]
        contracts = _outgoing_contract_due(w, aid)
        voluntary = _requested_labor(w, aid, plans.get(aid))
        rows.append(LaborProjection(
            aid=aid, labor_capacity=capacity, childcare_due=childcare,
            outgoing_contract_due=contracts, voluntary_requested=voluntary,
            residual_conservative=max(0.0, capacity - childcare - contracts - voluntary),
        ))
    return tuple(rows)


def _build_projection(w: World, residence_id: str, members: tuple[str, ...],
                      plans: Mapping[str, KeHoach], allocated: Set[str],
                      *, phase: Literal["decision", "post_common_land"]):
    owned = _food_rows(w, members)
    outputs: list[FoodRow] = []
    seed: list[FoodRow] = []
    paths: list[FeasibilityPath] = []
    for aid in members:
        agent_paths = _production_paths(w, aid, allocated=allocated, plan=plans.get(aid),
                                        all_visible=phase == "decision")
        paths.extend(agent_paths)
        if phase == "post_common_land":
            for path in agent_paths:
                if path.feasible and path.path_id == "canh_lua":
                    seed_amount = float(w.cfg.get("san_xuat.giong_kg_moi_thua"))
                    seed.append(FoodRow(owner_id=aid, asset="thoc", kg=seed_amount,
                                        kg_thoc_equivalent=seed_amount))
                    if path.gross_food > _EPSILON:
                        outputs.append(FoodRow(owner_id=aid, asset="thoc", kg=path.gross_food,
                                               kg_thoc_equivalent=path.gross_food))
    # The physical order is seed/output then decay.  Project projected balances
    # by owner before applying owner-specific storage technology/decay rates.
    specs = {spec.asset: spec for spec in edible_assets(w)}
    balances: dict[tuple[str, str], float] = {
        (row.owner_id or "", row.asset): row.kg for row in owned
    }
    for row in seed:
        key = (row.owner_id or "", row.asset)
        balances[key] = max(0.0, balances.get(key, 0.0) - row.kg)
    for row in outputs:
        key = (row.owner_id or "", row.asset)
        balances[key] = balances.get(key, 0.0) + row.kg
    pre_decay = tuple(
        FoodRow(owner_id=owner, asset=asset, kg=kg,
                kg_thoc_equivalent=kg * specs[asset].kg_thoc_equivalent_per_kg)
        for (owner, asset), kg in sorted(balances.items()) if kg > _EPSILON
    )
    decay = _decay_rows(w, pre_decay)
    food_open = _aggregate_rows(owned)
    need = _need(w, members)
    available = sum(row.kg_thoc_equivalent for row in food_open)
    available += sum(row.kg_thoc_equivalent for row in outputs)
    available -= sum(row.kg_thoc_equivalent for row in seed)
    available -= sum(row.kg_thoc_equivalent for row in decay)
    gap = max(0.0, need - max(0.0, available))
    return owned, food_open, tuple(decay), tuple(outputs), tuple(seed), need, gap, tuple(sorted(
        paths, key=lambda row: (row.protocol, row.target_id, row.path_id)
    ))


def _quote_due_tick(w: World, delivery: object) -> int | None:
    """Read a validated quote delivery term without calling a stateful protocol helper."""
    if delivery in (None, "", "ngay"):
        return int(w.tick)
    text = str(delivery)
    if not text.startswith("tick:"):
        return None
    try:
        return int(text.split(":", 1)[1])
    except ValueError:
        return None


def _quote_paths(w: World, aid: str) -> tuple[FeasibilityPath, ...]:
    """Expose only the requester's protocol-visible, still-open quote terms.

    A posted quote has poster escrow but no accepting-party escrow.  It is therefore
    always conditional and never contributes food to a guaranteed balance, even when
    the requester currently owns the quoted payment asset.
    """
    from engine.quotes import quote_visible_to

    food_factor = {spec.asset: spec.kg_thoc_equivalent_per_kg for spec in edible_assets(w)}
    rows: list[FeasibilityPath] = []
    for quote in quote_visible_to(w, aid):
        if int(w.tick) > int(quote.het_han_tick):
            continue
        if not w.chu_the_hoat_dong(quote.nguoi_dang):
            continue
        if quote.doi_tac is not None and not w.chu_the_hoat_dong(quote.doi_tac):
            continue
        if quote.chieu == "ban":
            incoming_asset = quote.tai_san
            payment_asset = quote.thanh_toan
            payment_amount = max(0.0, quote.con_lai * quote.don_gia)
        elif quote.chieu == "mua":
            incoming_asset = quote.thanh_toan
            payment_asset = quote.tai_san
            payment_amount = max(0.0, quote.con_lai)
        else:
            continue  # corrupt quote state is not an observable executable path
        quantity = max(0.0, float(quote.con_lai))
        factor = food_factor.get(incoming_asset, 0.0)
        payment_owned = w.ledger.so_du(aid, payment_asset) + _EPSILON >= payment_amount
        reasons = ["unaccepted_quote"]
        if factor <= 0.0:
            reasons.append("does_not_provide_food")
        if not payment_owned:
            reasons.append("insufficient_payment")
        rows.append(FeasibilityPath(
            protocol="quote", target_id=str(quote.id), path_id=str(quote.id),
            visible=True, reachable=True, feasible=False, conditional=True, input_owner=aid,
            reason_codes=tuple(sorted(reasons)),
            earliest_settlement_tick=_quote_due_tick(w, quote.giao_tai),
            counterparty_id=quote.nguoi_dang, asset=incoming_asset, quantity=quantity,
            unit_price=max(0.0, float(quote.don_gia)), payment_asset=payment_asset,
            payment_amount=payment_amount, payment_owned=payment_owned,
            delivery=str(quote.giao_tai), gross_food=quantity * factor,
            net_food=quantity * factor,
        ))
    return tuple(sorted(rows, key=lambda row: (row.protocol, row.target_id, row.path_id)))


def _resolved_party(party: str, aid: str) -> str:
    """Resolve only the public-board placeholder for this potential acceptor."""
    return aid if party == "?" else party


def _contract_paths(w: World, aid: str, labor: LaborProjection) -> tuple[FeasibilityPath, ...]:
    """Render open board food-at-signing offers, without inspecting payer solvency.

    Board offers do not reserve food and a response has not yet created a contract.
    Thus even a local public offer is only a conditional protocol route: the card can
    disclose its public terms and physical boundary, but cannot promise food or expose
    whether another party has enough private inventory when acceptance is attempted.
    """
    from engine.contracts import delivery_failure_code, validate_hop_dong

    food_factor = {spec.asset: spec.kg_thoc_equivalent_per_kg for spec in edible_assets(w)}
    ttl = int(w.cfg.get("hop_dong.de_nghi_het_han_tick"))
    rows: list[FeasibilityPath] = []
    for offer_id, offer in sorted(getattr(w, "bang_rao", {}).items()):
        contract = getattr(offer, "hd", None)
        recipient = getattr(offer, "den", None)
        proposer = getattr(offer, "tu", None)
        posted_tick = getattr(offer, "tick", None)
        if contract is None or proposer == aid or not isinstance(posted_tick, int):
            continue
        if recipient is not None and recipient != aid:
            continue
        if not isinstance(proposer, str) or not w.chu_the_hoat_dong(proposer):
            continue
        if (
            posted_tick > int(w.tick)
            or int(w.tick) - posted_tick > ttl
            or aid not in contract.cac_ben and "?" not in contract.cac_ben
        ):
            continue
        named_parties = (party for party in contract.cac_ben if party != "?")
        if any(not w.chu_the_hoat_dong(party) for party in named_parties):
            continue
        if validate_hop_dong(contract, w) is not None:
            continue

        food_legs = []
        labor_per_tick = 0.0
        delivery_codes: list[str] = []
        for clause in contract.dieu_khoan:
            source = getattr(clause, "tu", None)
            destination = getattr(clause, "den", None)
            if source is None or destination is None:
                continue
            source = _resolved_party(str(source), aid)
            destination = _resolved_party(str(destination), aid)
            if clause.loai == "gop_cong" and source == aid:
                labor_per_tick += max(0.0, float(clause.so_cong_moi_tick))
            if clause.loai in {"chuyen_giao_mot_lan", "chuyen_giao_dinh_ky", "gop_cong"}:
                code = delivery_failure_code(w, source, destination)
                if code is not None:
                    delivery_codes.append(code)
            if (
                clause.loai == "chuyen_giao_mot_lan"
                and clause.tai == "ky_ket"
                and destination == aid
                and source != aid
                and clause.tai_san in food_factor
            ):
                food_legs.append((source, clause.tai_san, max(0.0, float(clause.so_luong))))
        if not food_legs:
            continue

        assets = {asset for _source, asset, _amount in food_legs}
        providers = {source for source, _asset, _amount in food_legs}
        quantity = sum(amount for _source, _asset, amount in food_legs)
        food = sum(amount * food_factor[asset] for _source, asset, amount in food_legs)
        quantity_fact = quantity if len(assets) == 1 else None
        reachable = not delivery_codes
        reasons = ["unaccepted_contract_offer"]
        reasons.extend(delivery_codes)
        if labor_per_tick > labor.residual_conservative + _EPSILON:
            reasons.append("insufficient_labor")
        earliest = max(int(w.tick), posted_tick + 1)
        rows.append(FeasibilityPath(
            protocol="contract", target_id=str(offer_id), path_id="food_at_signing",
            visible=True, reachable=reachable, feasible=False, conditional=True, input_owner=aid,
            reason_codes=tuple(sorted(set(reasons))), earliest_output_tick=earliest,
            earliest_settlement_tick=earliest, earliest_labor_tick=earliest,
            counterparty_id=next(iter(providers)) if len(providers) == 1 else None,
            asset=next(iter(assets)) if len(assets) == 1 else None, quantity=quantity_fact,
            contract_form=str(contract.hinh_thuc), food_at_signing=True,
            labor_per_tick=labor_per_tick, duration_ticks=contract.thoi_han,
            gross_food=food, net_food=food,
        ))

    if rows:
        return tuple(sorted(rows, key=lambda row: (row.protocol, row.target_id, row.path_id)))
    # This is a protocol prerequisite, not a prospective donor.  It preserves the
    # visible oral/public-board option without claiming that any person will respond.
    return (FeasibilityPath(
        protocol="contract", target_id="public_board", path_id="oral_proposal_prerequisites",
        visible=True, reachable=False, feasible=False, conditional=True,
        reason_codes=("counterparty_required", "response_not_same_tick"),
        earliest_settlement_tick=int(w.tick) + 1, earliest_labor_tick=int(w.tick) + 1,
        contract_form="mieng", food_at_signing=True,
    ),)


def build_survival_feasibility(w: World, aid: str) -> SurvivalFeasibility:
    """Build a facts-only decision card without mutating ``w``.

    Unaccepted quotes and board offers are visible only as conditional protocol
    paths.  They are deliberately excluded from guaranteed inflow/output.
    """
    validate_survival_config(w.cfg)
    residence_id, members = _residence(w, aid)
    empty: dict[str, KeHoach] = {}
    owned, food_open, decay, output, seed, need, gap, paths = _build_projection(
        w, residence_id, members, empty, frozenset(), phase="decision"
    )
    labor = next(row for row in _labor_projection(w, members, empty) if row.aid == aid)
    personal = tuple(row for row in owned if row.owner_id == aid)
    return SurvivalFeasibility(
        as_of_tick=w.tick, phase="decision", residence_id=residence_id, members=members,
        owned_by_person=personal, provisionable_in_residence=owned,
        food_open=food_open, decay_before_consumption=decay,
        guaranteed_settled_inflow=(), guaranteed_feasible_output=output, seed_use=seed,
        need=NeedRow(kg_thoc_equivalent=need), gap=NeedRow(kg_thoc_equivalent=gap),
        labor_capacity=labor.labor_capacity, childcare_due=labor.childcare_due,
        outgoing_contract_due=labor.outgoing_contract_due,
        voluntary_requested=labor.voluntary_requested,
        residual_conservative=labor.residual_conservative,
        production_paths=paths, quote_paths=_quote_paths(w, aid),
        contract_paths=_contract_paths(w, aid, labor),
    )


def project_post_plan_survival(w: World, residence_id: str,
                               plans: Mapping[str, KeHoach],
                               allocated_common_fields: Set[str]) -> SurvivalProjection:
    """Project one residence after common-land allocation, without state mutation."""
    members = None
    for aid in sorted(w.agents):
        if not w.agents[aid].con_song:
            continue
        rid, candidate = _residence(w, aid)
        if rid == residence_id:
            members = candidate
            break
    if members is None:
        raise ValueError(f"unknown active residence {residence_id!r}")
    owned, food_open, decay, output, seed, need, gap, paths = _build_projection(
        w, residence_id, members, plans, frozenset(str(x) for x in allocated_common_fields),
        phase="post_common_land"
    )
    return SurvivalProjection(
        as_of_tick=w.tick, residence_id=residence_id, members=members,
        food_open=food_open, decay_before_consumption=decay,
        guaranteed_settled_inflow=(), guaranteed_feasible_output=output, seed_use=seed,
        need=NeedRow(kg_thoc_equivalent=need), gap=NeedRow(kg_thoc_equivalent=gap),
        labor=_labor_projection(w, members, plans), production_paths=paths,
    )


__all__ = [
    "EdibleAssetSpec", "FeasibilityPath", "FoodRow", "LaborProjection", "NeedRow",
    "SCHEMA_VERSION", "SurvivalFeasibility", "SurvivalProjection", "build_survival_feasibility",
    "edible_assets", "health_max", "project_post_plan_survival", "validate_survival_config",
]
