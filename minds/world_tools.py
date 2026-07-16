"""Công cụ thế giới CHỈ ĐỌC cho vòng agentic (PART 5.2/5.3, REPORTS.md — MCP active).

LLM chủ động "hỏi" thế giới trước khi quyết định: check_weather, get_market_price...
thay vì bị nhồi mọi thứ vào prompt. Hai bất biến sắt:

1. TUYỆT ĐỐI CHỈ ĐỌC (điều luật #1): không hàm nào chạm w.ledger/w.agents/... — chỉ
   đọc và trả JSON. Có test snapshot world_hash trước/sau khi gọi mọi công cụ để chứng minh.
2. TẤT ĐỊNH (điều luật #4): công cụ đọc w tại thời điểm GATHER (trước mọi apply); vòng
   nhiều lượt chỉ ảnh hưởng pha gather, quyết định vẫn apply sorted-id. Replay lại đúng
   transcript nhiều lượt → cùng world-hash.

Tên hàm/tham số bằng tiếng Việt không dấu (LLM gọi được), mô tả tiếng Việt.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from engine.metrics import gini
from engine.world import World

# Khai báo công cụ theo lược đồ functionDeclarations của Gemini (OpenAI tools tương tự).
# Mỗi mục: {name, description, parameters(JSON Schema)}.
KHAI_BAO_CONG_CU: list[dict[str, Any]] = [
    {
        "name": "xem_thoi_tiet",
        "description": "Xem mùa và thời tiết tick hiện tại (ảnh hưởng năng suất mùa màng).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "gia_cho",
        "description": "Giá khớp gần nhất của một mặt hàng trên chợ làng (kg thóc/đơn vị). "
                       "Trả null nếu chưa từng có phiên chợ cho mặt hàng đó.",
        "parameters": {
            "type": "object",
            "properties": {"tai_san": {"type": "string",
                                       "description": "vd: go, cong_cu, quang_dong, ga, ca, dat"}},
            "required": ["tai_san"],
        },
    },
    {
        "name": "xem_thi_truong_local",
        "description": "Xem rao vặt và báo giá đang nhìn thấy ở làng/bờ bạn tới được, cùng niềm tin giá riêng của bạn. Không có giá nào được coi là giá đúng.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_bao_gia",
        "description": "Xem các báo giá song phương còn mở mà bạn có quyền nhìn và có thể chấp nhận.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_du_an",
        "description": "Xem tiến độ các dự án đang mở tại địa điểm bạn tới được: đầu ra, vật liệu/công còn thiếu và hạn.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_cho_o",
        "description": "Xem tình trạng chỗ ở của chính bạn: nhà, quyền lô cư trú công, dự án nhà và các lô công đang mở. Chỉ trả dữ kiện, không tạo quyền hay tài sản.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_co_hoi_san_xuat",
        "description": "Xem fact card vật lý cục bộ. Khi survival-feasibility v7 bật, tool trả cùng schema với thẻ prompt: sở hữu/quyền cấp lương thực, cân bằng food, công còn lại và các đường production/quote/contract; không xếp hạng hay tiết lộ ví người ngoài.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_tai_nguyen_gan_day",
        "description": "Xem tối đa một số nguồn tự nhiên và thửa đất có thể tiếp cận quanh nơi ở hiện tại.",
        "parameters": {
            "type": "object",
            "properties": {"toi_da": {"type": "integer", "description": "số mục tối đa trả về"}},
        },
    },
    {
        "name": "tai_san_cua_toi",
        "description": "Kho tài sản của chính bạn (thóc, gỗ, gà, số thửa ruộng...).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "dat_cong_gan",
        "description": "Danh sách thửa ruộng công CHƯA ai sở hữu gần làng (id + độ màu mỡ) "
                       "— có thể canh tác; KHÔNG phải mục tiêu khai hoang.",
        "parameters": {
            "type": "object",
            "properties": {"toi_da": {"type": "integer", "description": "số thửa tối đa trả về"}},
        },
    },
    {
        "name": "uy_tin_voi",
        "description": "Mức độ thân/oán giữa bạn và một người (số dương = thân, âm = oán).",
        "parameters": {
            "type": "object",
            "properties": {"nguoi": {"type": "string", "description": "id người cần hỏi"}},
            "required": ["nguoi"],
        },
    },
    {
        "name": "nghe_ve",
        "description": "Nghe ngóng ƯỚC LƯỢNG (không chính xác) về của cải/nghề của một người "
                       "khác qua tai nghe mắt thấy — như dân làng đồn đoán nhau.",
        "parameters": {
            "type": "object",
            "properties": {"nguoi": {"type": "string", "description": "id người cần nghe ngóng"}},
            "required": ["nguoi"],
        },
    },
    {
        "name": "get_phan_bo_cua_cai",
        "description": "Phổ tài sản của cả làng để cân nhắc TRƯỚC KHI đánh thuế / trợ cấp "
                       "(Agentic RAG lập pháp): phân vị 10/50/90 của kho thóc dân làng, hệ số "
                       "Gini bất bình đẳng (0=đều, 1=lệch cực đoan), và số hộ thiếu ăn "
                       "(kho thóc dưới nhu cầu một tick). Chỉ tham khảo, không thay đổi gì.",
        "parameters": {"type": "object", "properties": {}},
    },
]


SURVIVAL_SCHEMA_VERSION = "survival_feasibility_v7"
SURVIVAL_API_MODULE = "engine.survival_feasibility"
SURVIVAL_REQUIRED_FIELDS: tuple[str, ...] = (
    "as_of_tick",
    "phase",
    "residence_id",
    "members",
    "owned_by_person",
    "provisionable_in_residence",
    "food_open",
    "decay_before_consumption",
    "guaranteed_settled_inflow",
    "guaranteed_feasible_output",
    "seed_use",
    "need",
    "gap",
    "labor_capacity",
    "childcare_due",
    "outgoing_contract_due",
    "voluntary_requested",
    "residual_conservative",
    "production_paths",
    "quote_paths",
    "contract_paths",
)
_SURVIVAL_FOOD_COLLECTION_FIELDS = (
    "owned_by_person",
    "provisionable_in_residence",
    "food_open",
    "decay_before_consumption",
    "guaranteed_settled_inflow",
    "guaranteed_feasible_output",
    "seed_use",
)
_SURVIVAL_ROW_FIELDS = (*_SURVIVAL_FOOD_COLLECTION_FIELDS, "need", "gap")
_SURVIVAL_PATH_FIELDS = ("production_paths", "quote_paths", "contract_paths")
# The engine schema currently uses ``owner_id`` and ``input_owner``.  These aliases are
# intentionally checked at the minds boundary too: an engine/API regression must not expose a
# residence-external principal merely because it introduced a more descriptive wire field.
_SURVIVAL_PRINCIPAL_KEYS = frozenset({
    "owner_id", "owner", "aid", "chu", "input_owner",
    "counterparty_id", "counterparty", "counterparty_owner_id", "counterparty_owner",
    "counterparty_aid", "doi_tac", "doi_tac_id", "ben_kia", "ben_kia_id",
})
_FORBIDDEN_SURVIVAL_KEYS = frozenset({
    "best",
    "global_balance",
    "global_stock",
    "outsider_balance",
    "private_balance",
    "rank",
    "ranking",
    "recommendation",
    "recommended",
    "willingness",
})


def _is_forbidden_survival_key(normalized: str) -> bool:
    """Reject private economic assessments, including future descriptive aliases.

    A public offer may disclose its named counterparty and its posted terms.  It may not
    disclose any party's balance, solvency, or willingness, regardless of where an engine
    schema nests that fact.
    """
    return (
        normalized in _FORBIDDEN_SURVIVAL_KEYS
        or normalized == "balance"
        or normalized == "solvency"
        or normalized.endswith(("_balance", "_solvency", "_willingness"))
    )


def survival_feasibility_enabled(w: World) -> bool:
    """Cổng interface v7; thiếu khóa giữ nguyên prompt/tool legacy."""
    return bool(w.cfg.get("minds.survival_feasibility.bat", False))


def _survival_unavailable(reason_code: str, **detail: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SURVIVAL_SCHEMA_VERSION,
        "status": "unavailable",
        "reason_code": reason_code,
    }
    payload.update(detail)
    return payload


def _json_value(value: Any) -> Any:
    """Copy a frozen dataclass/Pydantic/mapping engine view into deterministic JSON data."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    elif not isinstance(value, Mapping):
        raise TypeError("survival feasibility API must return a mapping or schema object")
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _contains_forbidden_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if _is_forbidden_survival_key(normalized):
                return normalized
            found = _contains_forbidden_key(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _contains_forbidden_key(child)
            if found is not None:
                return found
    return None


def _is_survival_principal_key(normalized: str) -> bool:
    """Recognize owner/counterparty identity aliases added by future engine schemas."""
    return (
        normalized in _SURVIVAL_PRINCIPAL_KEYS
        or normalized.startswith(("owner_", "counterparty_", "doi_tac_", "ben_kia_"))
        or normalized.endswith(("_owner", "_owner_id", "_counterparty", "_doi_tac", "_ben_kia"))
    )


def _outsider_principal_path(
    value: Any, allowed_principals: set[str], *, path: str,
    allowed_external_paths: frozenset[str] = frozenset(),
) -> str | None:
    """Return the first serialized owner/counterparty outside a private fact boundary.

    The builder is an engine-owned interface, but it can be upgraded independently from minds.
    Walk each food/path object rather than trusting today's flat Pydantic rows: an identity in a
    nested payment/input object is as private as a top-level ``owner_id``.  Null owner fields are
    valid for common/unassigned facts; malformed non-string identities fail closed.  The sole
    exception is an exact top-level path admitted by ``_public_offer_counterparty_path`` below.
    """
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            normalized = str(key).strip().lower().replace("-", "_")
            if _is_survival_principal_key(normalized) and child not in (None, ""):
                if (
                    child_path not in allowed_external_paths
                    and (not isinstance(child, str) or child not in allowed_principals)
                ):
                    return child_path
            found = _outsider_principal_path(
                child, allowed_principals, path=child_path,
                allowed_external_paths=allowed_external_paths,
            )
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _outsider_principal_path(
                child, allowed_principals, path=f"{path}[{index}]",
                allowed_external_paths=allowed_external_paths,
            )
            if found is not None:
                return found
    return None


def _public_offer_counterparty_path(
    row: Any, *, field: str, row_path: str, allowed_principals: set[str],
) -> frozenset[str]:
    """Permit only a posted offer's named external counterparty identity.

    ``counterparty_id`` is protocol-visible public/directed offer metadata, unlike an owner,
    payment owner, nested identity, balance, willingness, or solvency fact.  An unaccepted
    quote/contract cannot become food already available to the requester, so it must remain a
    visible, conditional, infeasible path.  This exact-path allowlist prevents future aliases or
    nested data from widening the disclosure boundary.
    """
    expected_protocol = {
        "quote_paths": "quote",
        "contract_paths": "contract",
    }.get(field)
    if not isinstance(row, dict) or expected_protocol is None:
        return frozenset()
    counterparty = row.get("counterparty_id")
    if counterparty in (None, "") or counterparty in allowed_principals:
        return frozenset()
    if not isinstance(counterparty, str):
        return frozenset()
    if (
        row.get("protocol") != expected_protocol
        or row.get("visible") is not True
        or row.get("conditional") is not True
        or row.get("feasible") is not False
        or not isinstance(row.get("target_id"), str)
        or not row["target_id"]
        or not isinstance(row.get("path_id"), str)
        or not row["path_id"]
    ):
        return frozenset()
    return frozenset({f"{row_path}.counterparty_id"})


def _path_principal_boundary_violation(
    paths: list[Any], allowed_principals: set[str], *, field: str,
) -> str | None:
    """Check path identities, narrowly allowing a real open-offer counterparty."""
    for index, row in enumerate(paths):
        row_path = f"{field}[{index}]"
        allowed_external_paths = _public_offer_counterparty_path(
            row, field=field, row_path=row_path, allowed_principals=allowed_principals,
        )
        leak_path = _outsider_principal_path(
            row, allowed_principals, path=row_path,
            allowed_external_paths=allowed_external_paths,
        )
        if leak_path is not None:
            return leak_path
    return None


def _stable_rows(value: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(value, list):
        return value

    def row_key(row: Any) -> tuple[str, ...]:
        if not isinstance(row, dict):
            return (canonical_json(row),)
        selected = tuple(str(row.get(key, "")) for key in keys)
        return (*selected, canonical_json(row))

    return sorted(value, key=row_key)


def _gap_is_positive(value: Any) -> bool:
    """Read the engine's gap fact without recalculating food physics in minds."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value) > 1e-9
    if isinstance(value, dict):
        for key in ("kg_thoc_equivalent", "food_equivalent", "total", "value"):
            if key in value and isinstance(value[key], int | float):
                return float(value[key]) > 1e-9
        return any(_gap_is_positive(child) for child in value.values())
    if isinstance(value, list):
        return any(_gap_is_positive(child) for child in value)
    return False


def _contract_protocol_facts(w: World, as_of_tick: int) -> dict[str, Any] | None:
    """Exact semantics of the two v7 enums, rendered only when both gates match."""
    # Config.get raise khi default là None ⇒ dùng sentinel chuỗi rỗng cho khóa vắng (legacy).
    schedule = w.cfg.get("hop_dong.gop_cong_lich", "")
    physical = bool(w.cfg.get("hop_dong.tiep_can_vat_ly_v2", False))
    if schedule != "signing_tick_half_open_v2" or not physical:
        return None
    return {
        "oral_contract": {
            "proposal_response_earliest_tick": int(as_of_tick) + 1,
            "food_at_signing_before_phase_5_labor": True,
            "gop_cong_schedule": schedule,
            "gop_cong_execution_rule": "0 <= tick - tick_ky < thoi_han",
            "thoi_han_1_total_contributions": 1,
            "unbounded_duration": "thoi_han=null until valid cancellation/default",
            "physical_reachability_v2": True,
            "minimum_tangible_reachability": (
                "same_residence_or_same_village_same_bank"
            ),
            "unreachable_reason_code": "delivery_unreachable",
            "signing_is_atomic": True,
        },
        "quote": {
            "purpose": "spot_exchange_with_owned_payment_asset",
            "requires_two_sided_escrow": True,
            "labor_is_not_escrowable": True,
            "unaccepted_quote_is_guaranteed_food": False,
            "missing_payment_reason_code": "insufficient_payment",
        },
        "message": {
            "information_only": True,
            "settles_assets": False,
            "earliest_response_tick": int(as_of_tick) + 1,
        },
    }


def _gioi_han_path_card(w: World, facts: dict[str, Any]) -> None:
    """Trần số path trong card (prompt VÀ tool cùng nguồn ⇒ invariant "một schema" giữ nguyên).

    v7 sinh 1 production path cho MỖI thửa công (~252 ở t0, gần hết ``feasible=false`` cùng một
    lý do như ``season_not_available``) → ~75KB/agent. Vì token≈byte (bảo thủ), mỗi lượt LLM
    giữ chỗ TPM gần bằng nguyên hạn mức/phút của một key, trần cả pool ở 16/50 agent full-
    autonomy. Giữ MỌI path khả thi (actionable) nguyên vẹn; phần bất khả thi chỉ giữ ``N`` mẫu
    rồi thay phần còn lại bằng ``{so_luot_bo, ly_do_pho_bien}`` — KHÔNG truncate im lặng. ``N``
    đọc từ config (design_assumption ở overlay v7); vắng khóa ⇒ không cap (giữ hành vi legacy).
    """
    raw = w.cfg.raw().get("minds", {})
    sf = raw.get("survival_feasibility", {}) if isinstance(raw, dict) else {}
    n_raw = sf.get("max_path_moi_loai") if isinstance(sf, dict) else None
    if n_raw is None:
        return
    n = int(n_raw)
    for field in _SURVIVAL_PATH_FIELDS:
        paths = facts.get(field)
        if not isinstance(paths, list):
            continue
        bat_kha = [p for p in paths if not (isinstance(p, dict) and p.get("feasible"))]
        if len(bat_kha) <= n:
            continue
        kha_thi = [p for p in paths if isinstance(p, dict) and p.get("feasible")]
        bo = bat_kha[n:]
        ly_do: dict[str, int] = {}
        for p in bo:
            for r in (p.get("reason_codes") or []):
                ly_do[r] = ly_do.get(r, 0) + 1
        facts[field] = kha_thi + bat_kha[:n]
        facts[f"{field}_luoc"] = {
            "so_luot_bo": len(bo),
            "ly_do_pho_bien": sorted(ly_do, key=lambda k: -ly_do[k])[:3],
        }


def survival_fact_payload(w: World, aid: str) -> dict[str, Any]:
    """Validated, privacy-bounded v7 payload shared by prompt and local tool.

    The engine owns every physical calculation. Minds only loads the immutable API lazily,
    checks its declared boundary, sorts rows, and adds versioned protocol semantics from config.
    No fallback recomputes food, labor, reachability, price, or outsider solvency.
    """
    if not survival_feasibility_enabled(w):
        return _survival_unavailable("feature_disabled")
    try:
        module = importlib.import_module(SURVIVAL_API_MODULE)
        builder = module.build_survival_feasibility
    except (ImportError, AttributeError):
        return _survival_unavailable("engine_api_unavailable")
    try:
        facts = _json_value(builder(w, aid))
    except Exception:  # noqa: BLE001 - interface failure is data, never a world mutation
        return _survival_unavailable("engine_api_error")
    if not isinstance(facts, dict):
        return _survival_unavailable("invalid_engine_schema")
    missing = [field for field in SURVIVAL_REQUIRED_FIELDS if field not in facts]
    if missing:
        return _survival_unavailable("invalid_engine_schema", missing_fields=missing)
    if facts.get("phase") not in {"decision", "post_common_land"}:
        return _survival_unavailable("invalid_engine_schema", invalid_field="phase")
    members = sorted({str(member) for member in facts.get("members", [])})
    facts["members"] = members
    residence_id = str(facts.get("residence_id", ""))
    if not residence_id:
        return _survival_unavailable("invalid_engine_schema", invalid_field="residence_id")
    # Every serialized food-balance collection is private to this residence.  Do not limit this
    # check to the two inventory lists: a malformed projection could otherwise disclose an
    # outsider via decay, seed/reserve, a settled inflow, or a feasible output.
    for field in _SURVIVAL_FOOD_COLLECTION_FIELDS:
        rows = facts.get(field)
        if not isinstance(rows, list):
            return _survival_unavailable("invalid_engine_schema", invalid_field=field)
        allowed = {aid} if field == "owned_by_person" else set(members)
        leak_path = _outsider_principal_path(rows, allowed, path=field)
        if leak_path is not None:
            return _survival_unavailable(
                "privacy_boundary_violation", invalid_field=leak_path
            )
    # A target/quote identifier is not a principal.  An external ``counterparty_id`` is visible
    # only on a real open quote/contract offer (public or directed): it is the identity needed to
    # address that protocol, not a private account fact.  Every other declared principal remains
    # inside the residence boundary, including aliases nested under payment/input data.
    external_offer_visible = False
    for field in _SURVIVAL_PATH_FIELDS:
        paths = facts.get(field)
        if not isinstance(paths, list):
            return _survival_unavailable("invalid_engine_schema", invalid_field=field)
        for index, row in enumerate(paths):
            if _public_offer_counterparty_path(
                row, field=field, row_path=f"{field}[{index}]",
                allowed_principals=set(members),
            ):
                external_offer_visible = True
        leak_path = _path_principal_boundary_violation(
            paths, set(members), field=field
        )
        if leak_path is not None:
            return _survival_unavailable(
                "privacy_boundary_violation", invalid_field=leak_path
            )
    # Public/directed terms before acceptance are conditional routes, never a settled inflow.
    # The engine's v7 view intentionally has no such row; fail closed if a future projection
    # attempts to pair an external offer identity with guaranteed food.
    if external_offer_visible and facts["guaranteed_settled_inflow"]:
        return _survival_unavailable(
            "invalid_engine_schema", invalid_field="guaranteed_settled_inflow"
        )
    forbidden = _contains_forbidden_key(facts)
    if forbidden is not None:
        return _survival_unavailable(
            "privacy_boundary_violation", forbidden_field=forbidden
        )
    for field in _SURVIVAL_ROW_FIELDS:
        facts[field] = _stable_rows(
            facts[field], ("owner_id", "owner", "asset", "tai_san")
        )
    for field in _SURVIVAL_PATH_FIELDS:
        facts[field] = _stable_rows(
            facts[field], ("protocol", "target_id", "path_id")
        )
    _gioi_han_path_card(w, facts)
    protocol = _contract_protocol_facts(w, int(facts["as_of_tick"]))
    if protocol is None:
        return _survival_unavailable("contract_protocol_mismatch")
    return {
        "schema_version": SURVIVAL_SCHEMA_VERSION,
        "status": "available",
        "card_mode": "expanded" if _gap_is_positive(facts["gap"]) else "compact",
        "facts": facts,
        "protocol": protocol,
    }


def _xem_thoi_tiet(w: World, aid: str, args: dict) -> dict:
    loai, he_so = w.thoi_tiet(w.tick)
    return {"mua": w.mua(), "thoi_tiet": loai, "he_so_nang_suat": he_so}


def _gia_cho(w: World, aid: str, args: dict) -> dict:
    ts = str(args.get("tai_san", ""))
    return {"tai_san": ts, "gia_gan_nhat": w.gia_gan_nhat(ts)}


def _xem_bao_gia(w: World, aid: str, args: dict) -> dict:
    from engine.quotes import quote_visible_to

    return {
        "bao_gia": [
            {
                "id": quote.id,
                "chieu": quote.chieu,
                "tai_san": quote.tai_san,
                "con_lai": round(quote.con_lai, 6),
                "don_gia": round(quote.don_gia, 6),
                "thanh_toan": quote.thanh_toan,
                "giao_tai": quote.giao_tai,
                "het_han_tick": quote.het_han_tick,
            }
            for quote in quote_visible_to(w, aid)
        ],
        "pham_vi": "chỉ báo giá đang mở và có thể tiếp cận",
    }


def _xem_thi_truong_local(w: World, aid: str, args: dict) -> dict:
    """Expose observed local offers, never a global planner's price vector."""
    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người hỏi không còn hoạt động", "code": "agent_unavailable"}
    ads = []
    for seller, direction, asset, amount, price in getattr(w, "rao_vat", []):
        other = w.agents.get(seller)
        if seller == aid or (other is not None and other.lang != agent.lang):
            continue
        ads.append({
            "ai": seller,
            "chieu": direction,
            "tai_san": asset,
            "so_luong": round(float(amount), 6),
            "gia_rao": round(float(price), 6),
        })
    return {
        "rao_vat_cung_lang": ads,
        "bao_gia_co_the_xem": _xem_bao_gia(w, aid, args)["bao_gia"],
        "gia_ky_vong_rieng": {
            asset: round(float(price), 6)
            for asset, price in sorted(agent.gia_ky_vong.items())
        },
        "canh_bao": "rao/niềm tin không phải giao dịch đã settlement",
    }


def _xem_du_an(w: World, aid: str, args: dict) -> dict:
    from engine.projects import visible_to

    projects = []
    for project in visible_to(w, aid):
        materials_left = {
            asset: round(max(0.0, need - project.vat_lieu_da.get(asset, 0.0)), 6)
            for asset, need in sorted(project.vat_lieu_can.items())
        }
        projects.append({
            "id": project.id,
            "chu": project.chu,
            "loai": project.loai,
            "thua": project.thua,
            "tai_san_ra": project.tai_san_ra,
            "so_luong_ra": round(project.so_luong_ra, 6),
            "cong_can": round(project.cong_can, 6),
            "cong_da": round(project.cong_da, 6),
            "cong_con_lai": round(max(0.0, project.cong_can - project.cong_da), 6),
            "vat_lieu_con_lai": materials_left,
            "han_tick": project.han_tick,
        })
    return {"du_an": projects, "pham_vi": "dự án của bạn hoặc công trường cùng làng/bờ tới được"}


def _xem_cho_o(w: World, aid: str, args: dict) -> dict:
    """Private, read-only housing/entry-right card for an autonomous resident."""
    from engine.settlement import _dat_o_bat, lo_cua, lo_uu_tien

    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người hỏi không còn hoạt động", "code": "agent_unavailable"}
    household = [member for member in w.ho_cua(aid)
                 if member in w.agents and w.agents[member].con_song]
    homes = {
        member: w.ledger.so_du(member, "nha")
        for member in household if w.ledger.so_du(member, "nha") > 0
    }
    site = lo_cua(w, aid)
    projects = [
        project for project in getattr(w, "du_an", {}).values()
        if project.trang_thai == "dang_lam" and project.loai == "nha"
        and project.chu in household
    ]
    project_rows = [
        {
            "id": project.id,
            "thua": project.thua,
            "cong_con_lai": round(max(0.0, project.cong_can - project.cong_da), 6),
            "vat_lieu_con_lai": {
                asset: round(max(0.0, need - project.vat_lieu_da.get(asset, 0.0)), 6)
                for asset, need in sorted(project.vat_lieu_can.items())
            },
            "han_tick": project.han_tick,
        }
        for project in sorted(projects, key=lambda row: (row.tick_tao, row.id))
    ]
    return {
        "co_nha_trong_ho": bool(homes),
        "nha_cua_ho": homes,
        "lo_cu_tru_cua_toi": site,
        "lo_cong_uu_tien": lo_uu_tien(w, aid) if _dat_o_bat(w) and site is None else [],
        "du_an_nha_dang_mo": project_rows,
        "pham_vi": "quyền lô chỉ cho phép đặt dự án nhà; không phải title ruộng",
    }


def _reachable_parcels(w: World, aid: str):
    from engine.spatial import co_the_o_bo

    r0, c0 = w.vi_tri_cua(aid)
    return sorted(
        (parcel for parcel in w.parcels.values() if co_the_o_bo(w, aid, parcel.bo)),
        key=lambda parcel: (abs(parcel.r - r0) + abs(parcel.c - c0), parcel.id),
    )


def _mua_lua_can_tiep_tuc(w: World) -> str:
    """Current sowing season, or the next one after a non-rice tick."""
    for delta in range(w.tick_moi_nam() + 1):
        tick = w.tick + delta
        if w.mua_mua(tick):
            return w.mua(tick)
    raise ValueError("calendar không có mùa lúa")


def homestead_fact(w: World, aid: str, parcel: Any) -> dict[str, Any] | None:
    """Private engine fact for one provisional common-field tenure.

    The yield figure is deliberately a physical base at the parcel's current fertility.  It
    excludes weather, tool, health, skill and multi-field efficiency, so it is not a forecast
    or a livelihood ranking.
    """
    if (parcel.loai != "ruong" or parcel.chu is not None
            or parcel.homestead_ai != aid):
        return None
    sx = w.cfg.raw()["san_xuat"]
    from engine.spatial import co_the_o_bo

    threshold = int(sx["homestead_tick_lien_tiep"])
    fertility = float(parcel.mau_mo)
    return {
        "thua": parcel.id,
        "tien_do_mua_lua": int(parcel.homestead_dem),
        "nguong_title_mua_lua": threshold,
        "do_mau_hien_tai": round(fertility, 6),
        "san_luong_co_so_theo_do_mau_kg": round(
            float(sx["san_luong_goc_kg"]) * fertility, 6
        ),
        "mua_lua_can_tiep_tuc": _mua_lua_can_tiep_tuc(w),
        "co_the_tiep_can_hien_tai": bool(co_the_o_bo(w, aid, parcel.bo)),
        "quyen_hien_tai": "dat_cong_bao_luu_homestead",
        "action_hien_co": "phan_bo_cong.canh_thua",
        "reset_neu_bo_qua_mua_lua": True,
    }


def _ruong_cong_pin_homestead(reachable: list[Any], aid: str) -> list[Any]:
    """Own provisional fields first; only genuinely unheld commons follow."""
    held = [
        parcel for parcel in reachable
        if parcel.loai == "ruong" and parcel.chu is None and parcel.homestead_ai == aid
    ]
    unheld = [
        parcel for parcel in reachable
        if parcel.loai == "ruong" and parcel.chu is None and parcel.homestead_ai is None
    ]
    return [*held, *unheld]


def _xem_tai_nguyen_gan_day(w: World, aid: str, args: dict) -> dict:
    limit = max(0, min(20, int(args.get("toi_da", 8) or 8)))
    rows = []
    for parcel in _reachable_parcels(w, aid):
        if parcel.loai not in {"rung", "doi", "mo_dong", "ruong", "song"}:
            continue
        row: dict[str, Any] = {"thua": parcel.id, "loai": parcel.loai}
        if parcel.loai == "ruong":
            row.update({"chu": parcel.chu, "mau_mo": round(parcel.mau_mo, 4)})
            fact = homestead_fact(w, aid, parcel)
            if fact is not None:
                row["homestead_cua_toi"] = fact
        if parcel.loai == "rung":
            row.update({
                "sinh_khoi": round(float(getattr(parcel, "sinh_khoi", 0.0)), 6),
                "tan_rung": round(float(getattr(parcel, "tan_rung", 0.0)), 6),
            })
        rows.append(row)
        if len(rows) >= limit:
            break
    return {"tai_nguyen": rows, "pham_vi": "chỉ ô có thể tiếp cận ở tick hiện tại"}


def _xem_co_hoi_san_xuat(w: World, aid: str, args: dict) -> dict:
    """Physical fact cards. They disclose constraints without choosing a livelihood.

    Under the v7 treatment this tool returns the exact same validated survival schema used by
    the prompt. The legacy implementation remains untouched when the gate is absent/off.
    """
    if survival_feasibility_enabled(w):
        return survival_fact_payload(w, aid)
    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người hỏi không còn hoạt động", "code": "agent_unavailable"}
    cfg = w.cfg.raw()
    labour = round(w.ledger.so_du(aid, "cong"), 6)
    cards: list[dict[str, Any]] = []
    reachable = _reachable_parcels(w, aid)
    owned_fields = [p for p in reachable if p.loai == "ruong" and p.chu == aid]
    common_fields = _ruong_cong_pin_homestead(reachable, aid)
    held_fields = [p for p in common_fields if p.homestead_ai == aid]
    all_held_fields = sorted(
        (p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None
         and p.homestead_ai == aid),
        key=lambda p: p.id,
    )
    for parcel in all_held_fields:
        fact = homestead_fact(w, aid, parcel)
        if fact is not None:
            cards.append({"hoat_dong": "homestead_dang_tich_luy", **fact})
    # A reachable provisional homestead is pinned before private and unheld fields.  This only
    # preserves the observed ID; the action and engine still decide whether cultivation works.
    unheld_fields = [p for p in common_fields if p.homestead_ai is None]
    usable_fields = [*held_fields, *owned_fields, *unheld_fields]
    if w.mua_mua():
        sx = cfg["san_xuat"]
        cards.append({
            "hoat_dong": "canh_lua",
            "thua_co_the_dung": [p.id for p in usable_fields[:6]],
            "cong_moi_thua": float(sx["cong_moi_thua"]),
            "giong_thoc_moi_thua": float(sx["giong_kg_moi_thua"]),
            "san_luong_co_so_kg_moi_thua": float(sx["san_luong_goc_kg"]),
            "cong_hien_co": labour,
        })
    else:
        crops = w.cfg.get("khong_gian.vu_dong.cay", {})
        if isinstance(crops, dict):
            for crop, spec in sorted(crops.items()):
                if isinstance(spec, dict):
                    cards.append({
                        "hoat_dong": f"canh_{crop}",
                        "thua_co_the_dung": [p.id for p in usable_fields[:6]],
                        "cong_moi_thua": float(spec.get("cong", 0.0)),
                        "san_luong_co_so_kg_moi_thua": float(spec.get("san_luong_kg", 0.0)),
                        "quy_doi_luong_thuc": float(spec.get("quy_doi_dinh_duong", 0.0)),
                        "cong_hien_co": labour,
                    })
    forests = [p for p in reachable if p.loai == "rung"]
    clearable = [p for p in reachable if p.loai in {"rung", "doi"} and p.chu is None]
    if bool(w.cfg.get("khong_gian.khai_hoang.bat", False)) and clearable:
        cards.append({
            "hoat_dong": "khai_hoang",
            "thua_co_the_dung": [p.id for p in clearable[:6]],
            "loai_thua_hop_le": ["rung", "doi"],
            "cong_moi_thua": float(w.cfg.get("khong_gian.khai_hoang.cong_moi_thua")),
            "cong_hien_co": labour,
        })
    if forests:
        cards.append({
            "hoat_dong": "khai_go",
            "cong_moi_go": float(cfg["san_xuat"]["khai_thac"]["cong_moi_go"]),
            "sinh_khoi_tiep_can": round(sum(float(getattr(p, "sinh_khoi", 0.0)) for p in forests), 6),
            "cong_hien_co": labour,
        })
    if any(p.loai == "song" for p in reachable):
        cards.append({
            "hoat_dong": "danh_ca",
            "cong_moi_kg": float(cfg["danh_ca"]["cong_moi_kg_ca"]),
            "ton_ca_chung": round(float(getattr(w, "ca_ton", 0.0)), 6),
            "cong_hien_co": labour,
        })
    from engine.settlement import _dat_o_bat, lo_cua, lo_uu_tien

    if _dat_o_bat(w) and lo_cua(w, aid) is None:
        cards.append({
            "hoat_dong": "chon_dat_o",
            "lo_uu_tien": lo_uu_tien(w, aid),
            "tai_san_tao_ra": "quyen_dat_nha",
            "khong_tao_ra": ["ruong", "go", "cong", "nha"],
        })
    return {"co_hoi": cards, "pham_vi": "thông số vật lý/nguồn lực, không phải khuyến nghị"}


def _tai_san_cua_toi(w: World, aid: str, args: dict) -> dict:
    ts = {k: round(v, 1) for k, v in w.ledger.tai_san_cua(aid).items()
          if not k.startswith("vi_the:") and abs(v) > 1e-9}
    so_thua = sum(1 for p in w.parcels.values() if p.chu == aid)
    return {"tai_san": ts, "so_thua_ruong": so_thua}


def _dat_cong_gan(w: World, aid: str, args: dict) -> dict:
    toi_da = int(args.get("toi_da", 5) or 5)
    cong = _ruong_cong_pin_homestead(_reachable_parcels(w, aid), aid)[:max(0, toi_da)]
    rows = []
    for parcel in cong:
        row: dict[str, Any] = {"id": parcel.id, "mau_mo": round(parcel.mau_mo, 2)}
        fact = homestead_fact(w, aid, parcel)
        if fact is not None:
            row["homestead_cua_toi"] = fact
        rows.append(row)
    return {"thua": rows}


def _uy_tin_voi(w: World, aid: str, args: dict) -> dict:
    nguoi = str(args.get("nguoi", ""))
    return {"nguoi": nguoi, "uy_tin": round(w.uy_tin(aid, nguoi), 2)}


def _nghe_ve(w: World, aid: str, args: dict) -> dict:
    """Ước lượng MỜ (nhiễu seeded theo (người hỏi, người bị hỏi, năm)) — không chính xác."""
    nguoi = str(args.get("nguoi", ""))
    b = w.agents.get(nguoi)
    if b is None or not b.con_song:
        return {"nguoi": nguoi, "biet": "không rõ người này"}
    if nguoi != aid and nguoi not in w.hang_xom_cua(aid):
        return {"loi": "người này không ở trong phạm vi hàng xóm quan sát", "code": "outside_local"}
    g = w.rng.get(f"nghe_ve:{aid}:{nguoi}", w.nam())  # ổn định trong năm
    thoc = w.ledger.so_du(nguoi, "thoc")
    ruong = sum(1 for p in w.parcels.values() if p.chu == nguoi)
    ga = w.ledger.so_du(nguoi, "ga") + w.ledger.so_du(nguoi, "ga_con")
    muc = ("khá giả" if thoc > 2000 else "tạm đủ ăn" if thoc > 500 else "nghèo túng")
    chi_tiet = [f"nhà cửa {muc}"]
    if ruong:
        chi_tiet.append(f"~{max(1, round(ruong * float(g.uniform(0.6, 1.4))))} thửa ruộng")
    if ga >= 1:
        chi_tiet.append(f"có nuôi gà (~{max(1, round(ga * float(g.uniform(0.5, 1.5))))} con)")
    return {"nguoi": nguoi, "ten": b.ten, "tuoi": round(b.tuoi_nam),
            "nghe_ngong": "; ".join(chi_tiet)}


def _phan_vi(x_sap_xep: list[float], q: float) -> float:
    """Phân vị nearest-rank TẤT ĐỊNH trên danh sách ĐÃ sắp xếp tăng dần (không cần numpy).

    q là tỷ lệ trong [0,1]. Không nội suy → độc lập nền tảng, replay ổn định.
    """
    import math
    n = len(x_sap_xep)
    if n == 0:
        return 0.0
    k = min(n, max(1, math.ceil(q * n)))
    return x_sap_xep[k - 1]


def _get_phan_bo_cua_cai(w: World, aid: str, args: dict) -> dict:
    """Phổ tài sản làng cho Trưởng làng RAG trước khi lập pháp (REPORTS.md §4.3).

    THUẦN ĐỌC (điều luật #1): chỉ đọc ledger/agents, không chuyển/sinh/hủy gì.
    Gini dùng CHUNG công thức với engine.metrics để nhất quán với ngưỡng bạo động.
    """
    asker = w.agents.get(aid)
    if asker is None or not asker.con_song:
        return {"loi": "người gọi không còn hoạt động", "code": "agent_unavailable"}
    # Aggregate village facts are observable in a small settlement; individual
    # inventory remains private. This deliberately excludes other villages.
    lang_hoi = asker.lang
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = w.cfg.raw()["nhu_cau"]
    nguoi_lon_kg = float(nc["nguoi_lon_kg_tick"])
    tre_em_kg = float(nc["tre_em_kg_tick"])
    song = [a for a in w.agents.values() if a.con_song and a.lang == lang_hoi]
    thoc = sorted(w.ledger.so_du(a.id, "thoc") for a in song)
    # hộ nghèo: kho thóc cả hộ dưới nhu cầu ăn MỘT tick của hộ (dedup theo hộ)
    da_xu_ly: set[str] = set()
    so_ho = 0
    so_ho_ngheo = 0
    for aid2 in sorted(w.agents):
        a = w.agents[aid2]
        if not a.con_song or a.lang != lang_hoi or aid2 in da_xu_ly:
            continue
        ho = [m for m in w.ho_cua(aid2) if w.agents[m].con_song]
        da_xu_ly.update(ho)
        if not ho:
            continue
        so_ho += 1
        ton = sum(w.ledger.so_du(m, "thoc") for m in ho)
        nhu = sum(nguoi_lon_kg if w.agents[m].truong_thanh(tt) else tre_em_kg for m in ho)
        if ton < nhu:
            so_ho_ngheo += 1
    return {
        "so_dan": len(song),
        "so_ho": so_ho,
        "thoc_p10": round(_phan_vi(thoc, 0.1), 1),
        "thoc_p50": round(_phan_vi(thoc, 0.5), 1),
        "thoc_p90": round(_phan_vi(thoc, 0.9), 1),
        "gini_thoc": round(gini(thoc), 4),
        "so_ho_ngheo": so_ho_ngheo,
    }


CONG_CU: dict[str, Callable[[World, str, dict], dict]] = {
    "xem_thoi_tiet": _xem_thoi_tiet,
    "gia_cho": _gia_cho,
    "xem_thi_truong_local": _xem_thi_truong_local,
    "xem_bao_gia": _xem_bao_gia,
    "xem_du_an": _xem_du_an,
    "xem_cho_o": _xem_cho_o,
    "xem_co_hoi_san_xuat": _xem_co_hoi_san_xuat,
    "xem_tai_nguyen_gan_day": _xem_tai_nguyen_gan_day,
    "tai_san_cua_toi": _tai_san_cua_toi,
    "dat_cong_gan": _dat_cong_gan,
    "uy_tin_voi": _uy_tin_voi,
    "nghe_ve": _nghe_ve,
    "get_phan_bo_cua_cai": _get_phan_bo_cua_cai,
}


def canonical_json(value: Any) -> str:
    """Stable serialization used to attest a read-only tool response."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def result_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def catalog_hash() -> str:
    """Hash both tool declarations and implementation bytes for replay integrity."""
    declarations = canonical_json(KHAI_BAO_CONG_CU).encode("utf-8")
    source = Path(__file__).read_bytes()
    return hashlib.sha256(declarations + b"\0" + source).hexdigest()


def thuc_thi(w: World, aid: str, ten: str, args: dict | None) -> dict:
    """Thực thi một công cụ CHỈ ĐỌC. Tên lạ → trả lỗi (không raise, không chạm state)."""
    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người gọi không còn hoạt động", "code": "agent_unavailable"}
    ham = CONG_CU.get(ten)
    if ham is None:
        return {"loi": f"không có công cụ tên '{ten}'", "code": "unknown_tool"}
    try:
        return ham(w, aid, args or {})
    except Exception as e:  # noqa: BLE001 — công cụ hỏng thì báo lỗi, KHÔNG làm chết vòng
        return {"loi": f"công cụ '{ten}' lỗi: {type(e).__name__}", "code": "tool_error"}
