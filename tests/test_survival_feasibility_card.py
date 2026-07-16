"""ADR 0009 — facts-only survival card (minds surface, S2/S3/S6 + FakeTransport).

Phạm vi minds-owner: card/tool chỉ RENDER schema bất biến từ API engine
``engine.survival_feasibility.build_survival_feasibility`` (import lười). Engine module chưa
tồn tại trong tree ⇒ tests dùng stub qua ``sys.modules`` để kiểm chứng đúng seam + boundary,
KHÔNG tự tính lại vật lý food/labor/reachability trong minds. Mọi số fixture là
``design_assumption`` của test, không phải dữ kiện lịch sử. Không mạng: chỉ world fixture +
``httpx.MockTransport``.
"""

from __future__ import annotations

import copy
import json
import sys
import types
from pathlib import Path

import httpx
import pytest

from engine import board
from engine.config import Config, load_config
from engine.contracts import ClauseChuyenGiaoMotLan, ClauseGopCong, HopDong
from engine.world import tao_the_gioi
from minds.gateway import LLMRequest
from minds.keypool import EnvKeys
from minds.prompts import build_agent_prompt, build_user_rieng, render_survival_fact_card
from minds.providers_real import GatewayReal
from minds.quota import QuotaCounter
from minds.world_tools import (
    SURVIVAL_API_MODULE,
    SURVIVAL_SCHEMA_VERSION,
    canonical_json,
    result_hash,
    survival_fact_payload,
    thuc_thi,
)

# ---------------------------------------------------------------- fixtures


def _world_v7(seed: int = 21, giu_lai: int = 3, *, contract_v2: bool = True):
    """World thật với cổng interface v7 bật qua config (không sửa engine/overlay)."""
    raw = copy.deepcopy(load_config().raw())
    raw.setdefault("minds", {})["survival_feasibility"] = {"bat": True}
    if contract_v2:
        raw.setdefault("hop_dong", {})["gop_cong_lich"] = "signing_tick_half_open_v2"
        raw["hop_dong"]["tiep_can_vat_ly_v2"] = True
    w = tao_the_gioi(Config(raw), seed, events_path=None)
    ids = sorted(w.agents)
    for aid in ids[giu_lai:]:
        a = w.agents[aid]
        a.con_song = False
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "rời cuộc chơi (fixture)", 0)
    w.tick = 3
    return w


def _live_ids(w) -> list[str]:
    return sorted(a for a, ag in w.agents.items() if ag.con_song)


def _facts(aid: str, members: list[str], **override):
    """Schema fixture đủ field bắt buộc; chỉ enforce BẤT ĐẲNG THỨC A0021, không số lịch sử."""
    facts = {
        "as_of_tick": 3,
        "phase": "decision",
        "residence_id": "R0001",
        "members": list(members),
        "owned_by_person": [
            {"owner_id": aid, "asset": "ca", "kg": 2.0, "kg_thoc_equivalent": 5.0},
        ],
        "provisionable_in_residence": [
            {"owner_id": members[0], "asset": "thoc", "kg": 10.0,
             "kg_thoc_equivalent": 10.0},
        ],
        "food_open": [{"asset": "thoc", "kg_thoc_equivalent": 10.0},
                      {"asset": "ca", "kg_thoc_equivalent": 5.0}],
        "decay_before_consumption": [
            {"owner_id": aid, "asset": "ca", "kg_thoc_equivalent": 0.75},
        ],
        "guaranteed_settled_inflow": [],
        "guaranteed_feasible_output": [],
        "seed_use": [],
        "need": {"kg_thoc_equivalent": 90.0},
        "gap": {"kg_thoc_equivalent": 75.75},
        "labor_capacity": 180.0,
        "childcare_due": 0.0,
        "outgoing_contract_due": 0.0,
        "voluntary_requested": 0.0,
        "residual_conservative": 180.0,
        # canh_lua infeasible vì KHÔNG có giống; danh_ca conditional, net DƯỚI nhu cầu
        # (đúng bất đẳng thức A0021: catch_food < need, no seed/payment).
        "production_paths": [
            {"protocol": "production", "target_id": "P00_09", "path_id": "canh_lua",
             "visible": True, "reachable": True, "feasible": False,
             "input_owner": aid, "reason_codes": ["thieu_giong"],
             "earliest_output_tick": 3, "gross_food": 0.0, "net_food": 0.0},
            {"protocol": "production", "target_id": "song", "path_id": "danh_ca",
             "visible": True, "reachable": True, "feasible": True,
             "conditional": True, "input_owner": aid,
             "reason_codes": ["cpue_thap"], "earliest_output_tick": 3,
             "gross_food": 20.0, "net_food": 20.0},
        ],
        "quote_paths": [],
        "contract_paths": [],
    }
    facts.update(override)
    return facts


ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "agrarian_transition_v1"
V7_OVERLAYS = [
    SCENARIO / name
    for name in (
        "spatial_v1.yaml",
        "spatial_livelihood_v2.yaml",
        "spatial_livelihood_v3.yaml",
        "spatial_livelihood_v4.yaml",
        "spatial_livelihood_v5.yaml",
        "spatial_livelihood_v6.yaml",
        "spatial_livelihood_v7.yaml",
    )
]


def _real_v7_public_board_fixture(seed: int = 89):
    """A real v7 public offer with two separate residences and no engine stubbing."""
    w = tao_the_gioi(load_config(overlays=V7_OVERLAYS), seed, events_path=None)
    requester, responder = sorted(w.agents)[:2]
    for other, agent in w.agents.items():
        if other not in {requester, responder}:
            agent.con_song = False
    for aid in (requester, responder):
        w.agents[aid].tuoi_tick = 40.0
        w.agents[aid].health = 100.0
        w.agents[aid].lang = 0
        w.agents[aid].nha_thua = None
    offer = HopDong(
        cac_ben=[responder, "?"], hinh_thuc="mieng", thoi_han=1,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(
                tu=responder, den="?", tai_san="thoc", so_luong=25.0, tai="ky_ket",
            ),
            ClauseGopCong(tu="?", den=responder, so_cong_moi_tick=40.0),
        ],
    )
    offer_id = board.dang_de_nghi(w, responder, offer)
    assert offer_id is not None
    w.tick = 1  # A t=0 board offer becomes response-eligible at decision tick t=1.
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    return w, requester, responder, offer_id


def _stub_engine(monkeypatch, facts_by_aid):
    """Cắm module engine.survival_feasibility giả (per-aid) vào sys.modules."""
    mod = types.ModuleType(SURVIVAL_API_MODULE)
    calls = {"n": 0}

    def build_survival_feasibility(w, aid):
        calls["n"] += 1
        return copy.deepcopy(facts_by_aid[aid])

    mod.build_survival_feasibility = build_survival_feasibility
    monkeypatch.setitem(sys.modules, SURVIVAL_API_MODULE, mod)
    return calls


# ---------------------------------------------------------------- seam/gate


def test_gate_off_giu_nguyen_legacy_prompt_va_tool():
    from tests.helpers import the_gioi_test

    w = the_gioi_test(seed=17, giu_lai=3, thoc_moi_nguoi=2_000.0)
    aid = _live_ids(w)[0]
    prompt = build_user_rieng(w, aid, ["dinh_ky"])
    assert "[KHẢ NĂNG THỰC THI SỐNG CÒN]" in prompt
    assert "SURVIVAL FEASIBILITY V7" not in prompt
    tool = thuc_thi(w, aid, "xem_co_hoi_san_xuat", {})
    assert "co_hoi" in tool and "schema_version" not in tool


def test_gate_on_thieu_engine_api_bao_dependency_khong_bia_so(monkeypatch):
    w = _world_v7(seed=23)
    aid = _live_ids(w)[0]
    # Mô phỏng module engine CHƯA tồn tại một cách tất định (kể cả khi engine đã lên cây).
    monkeypatch.setitem(sys.modules, SURVIVAL_API_MODULE, None)
    payload = thuc_thi(w, aid, "xem_co_hoi_san_xuat", {})
    assert payload["schema_version"] == SURVIVAL_SCHEMA_VERSION
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "engine_api_unavailable"
    # Prompt: card bị BỎ, không rơi về con số minds tự tính.
    assert render_survival_fact_card(w, aid) == ""
    rieng = build_user_rieng(w, aid, ["dinh_ky"])
    assert "SURVIVAL FEASIBILITY V7" not in rieng
    assert "[KHẢ NĂNG THỰC THI SỐNG CÒN]" not in rieng
    assert "KIỂM TRA SINH TỒN" not in rieng


def test_gate_on_thieu_contract_v2_fail_closed(monkeypatch):
    w = _world_v7(seed=23, contract_v2=False)
    aid = _live_ids(w)[0]
    _stub_engine(monkeypatch, {aid: _facts(aid, _live_ids(w))})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "contract_protocol_mismatch"
    assert render_survival_fact_card(w, aid) == ""


def test_schema_thieu_field_hoac_sai_kieu_bi_tu_choi(monkeypatch):
    w = _world_v7(seed=29)
    ids = _live_ids(w)
    aid = ids[0]
    thieu = _facts(aid, ids)
    del thieu["residual_conservative"]
    _stub_engine(monkeypatch, {aid: thieu})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "invalid_engine_schema"
    assert "residual_conservative" in payload["missing_fields"]

    mod = types.ModuleType(SURVIVAL_API_MODULE)
    mod.build_survival_feasibility = lambda w, aid: ["not", "a", "mapping"]
    monkeypatch.setitem(sys.modules, SURVIVAL_API_MODULE, mod)
    payload2 = survival_fact_payload(w, aid)
    assert payload2["status"] == "unavailable"
    assert payload2["reason_code"] == "engine_api_error"


# ---------------------------------------------------------------- S2 boundary


def test_s2_khong_dem_tai_san_ngoai_ho_hoac_di_san(monkeypatch):
    w = _world_v7(seed=31)
    ids = _live_ids(w)
    aid, outsider = ids[0], ids[-1]
    members = [aid]  # residence R1 chỉ có requester
    facts = _facts(aid, members)
    # provisionable liệt kê chủ NGOÀI residence (R2/estate) ⇒ leak biên giới ADR §2.3/§2.4
    facts["provisionable_in_residence"] = [
        {"owner_id": outsider, "asset": "thoc", "kg": 500.0, "kg_thoc_equivalent": 500.0},
    ]
    _stub_engine(monkeypatch, {aid: facts})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "privacy_boundary_violation"
    assert render_survival_fact_card(w, aid) == ""


def test_s2_owned_by_person_chi_cua_chinh_nguoi_duoc_hoi(monkeypatch):
    w = _world_v7(seed=31)
    ids = _live_ids(w)
    aid, outsider = ids[0], ids[-1]
    facts = _facts(aid, [aid, ids[1]])
    facts["owned_by_person"].append(
        {"owner_id": outsider, "asset": "thoc", "kg": 999.0, "kg_thoc_equivalent": 999.0}
    )
    _stub_engine(monkeypatch, {aid: facts})
    assert survival_fact_payload(w, aid)["reason_code"] == "privacy_boundary_violation"


@pytest.mark.parametrize("field", (
    "owned_by_person",
    "provisionable_in_residence",
    "food_open",
    "decay_before_consumption",
    "guaranteed_settled_inflow",
    "guaranteed_feasible_output",
    "seed_use",
))
def test_s2_outsider_owner_in_every_food_balance_collection_fails_closed(
    monkeypatch, field
):
    """No food projection component may disclose an external principal's balance."""
    w = _world_v7(seed=33)
    ids = _live_ids(w)
    aid, outsider = ids[0], ids[-1]
    facts = _facts(aid, [aid])
    facts[field].append({
        "owner_id": outsider,
        "asset": "thoc",
        "kg": 123.0,
        "kg_thoc_equivalent": 123.0,
    })
    _stub_engine(monkeypatch, {aid: facts})

    payload = survival_fact_payload(w, aid)

    assert payload["status"] == "unavailable", field
    assert payload["reason_code"] == "privacy_boundary_violation", field


@pytest.mark.parametrize("path_field, principal_field", (
    *( ("production_paths", field) for field in (
        "input_owner", "counterparty_id", "counterparty", "counterparty_owner_id",
        "payment_owner_id",
    )),
    *( (path_field, field) for path_field in ("quote_paths", "contract_paths") for field in (
        "input_owner", "counterparty", "counterparty_owner_id", "payment_owner_id",
    )),
))
def test_s2_external_nonprotocol_principal_in_path_fails_closed(
    monkeypatch, path_field, principal_field
):
    """Only an open offer's exact ``counterparty_id`` may name an outsider."""
    w = _world_v7(seed=35)
    ids = _live_ids(w)
    aid, outsider = ids[0], ids[-1]
    facts = _facts(aid, [aid])
    facts[path_field] = [{
        "protocol": "fixture",
        "target_id": "fixture-target",
        "path_id": "fixture-path",
        principal_field: outsider,
    }]
    _stub_engine(monkeypatch, {aid: facts})

    payload = survival_fact_payload(w, aid)

    assert payload["status"] == "unavailable", (path_field, principal_field)
    assert payload["reason_code"] == "privacy_boundary_violation", (
        path_field, principal_field,
    )


@pytest.mark.parametrize("path_field, protocol", (
    ("quote_paths", "quote"),
    ("contract_paths", "contract"),
))
def test_s2_external_open_offer_counterparty_id_is_protocol_visible_only(
    monkeypatch, path_field, protocol
):
    w = _world_v7(seed=36)
    ids = _live_ids(w)
    aid, outsider = ids[0], ids[-1]
    facts = _facts(aid, [aid])
    facts[path_field] = [{
        "protocol": protocol,
        "target_id": "public-offer-1",
        "path_id": "public-offer-1",
        "visible": True,
        "reachable": True,
        "feasible": False,
        "conditional": True,
        "counterparty_id": outsider,
        "reason_codes": ["unaccepted_offer"],
        "gross_food": 25.0,
        "net_food": 25.0,
    }]
    _stub_engine(monkeypatch, {aid: facts})

    payload = survival_fact_payload(w, aid)

    assert payload["status"] == "available"
    path = payload["facts"][path_field][0]
    assert path["counterparty_id"] == outsider
    assert path["conditional"] is True and path["feasible"] is False
    assert payload["facts"]["guaranteed_settled_inflow"] == []


@pytest.mark.parametrize("override", (
    {"visible": False},
    {"conditional": False},
    {"feasible": True},
    {"protocol": "production"},
    {"target_id": ""},
))
def test_s2_external_counterparty_id_requires_visible_unaccepted_offer(monkeypatch, override):
    w = _world_v7(seed=38)
    ids = _live_ids(w)
    aid, outsider = ids[0], ids[-1]
    facts = _facts(aid, [aid])
    path = {
        "protocol": "quote",
        "target_id": "BG00001",
        "path_id": "BG00001",
        "visible": True,
        "reachable": True,
        "feasible": False,
        "conditional": True,
        "counterparty_id": outsider,
    }
    path.update(override)
    facts["quote_paths"] = [path]
    _stub_engine(monkeypatch, {aid: facts})

    payload = survival_fact_payload(w, aid)

    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "privacy_boundary_violation"


def test_s2_house_ownership_tach_khoi_provisioning(monkeypatch):
    """Chuyển responder vào R1 chỉ kích hoạt provisioning ADR 0007; nhà vẫn field riêng."""
    w = _world_v7(seed=37)
    ids = _live_ids(w)
    aid, responder = ids[0], ids[1]
    facts_ngoai = _facts(aid, [aid])
    _stub_engine(monkeypatch, {aid: facts_ngoai})
    p1 = survival_fact_payload(w, aid)
    assert p1["status"] == "available"
    # responder chưa cùng hộ ⇒ không được xuất hiện trong provisionable
    assert all(_owner(r) != responder
               for r in p1["facts"]["provisionable_in_residence"])

    facts_cung_ho = _facts(aid, [aid, responder])
    facts_cung_ho["provisionable_in_residence"].append(
        {"owner_id": responder, "asset": "thoc", "kg": 30.0, "kg_thoc_equivalent": 30.0}
    )
    facts_cung_ho["house_usable_in_residence"] = {
        "co_nha": True, "owner_id": responder, "chuyen_quyen_so_huu": False,
    }
    _stub_engine(monkeypatch, {aid: facts_cung_ho})
    p2 = survival_fact_payload(w, aid)
    assert p2["status"] == "available"
    rows = p2["facts"]["provisionable_in_residence"]
    assert any(_owner(r) == responder for r in rows)
    assert p2["facts"]["house_usable_in_residence"]["chuyen_quyen_so_huu"] is False


def _owner(row):
    for key in ("owner_id", "owner", "aid", "chu"):
        if row.get(key) not in (None, ""):
            return str(row[key])
    return None


def test_s2_forbidden_keys_bi_chan(monkeypatch):
    w = _world_v7(seed=41)
    ids = _live_ids(w)
    aid = ids[0]
    for leak in (
        {"recommended": "danh_ca"},
        {"ranking": ["danh_ca", "canh_lua"]},
        {"global_stock": {"thoc": 12345.0}},
        {"quote_paths": [{"protocol": "quote", "target_id": "BG1", "path_id": "BG1",
                          "willingness": 0.9}]},
        {"contract_paths": [{"protocol": "contract", "target_id": "DN1",
                              "path_id": "food_at_signing", "counterparty_solvency": 0.9}]},
        {"quote_paths": [{"protocol": "quote", "target_id": "BG1", "path_id": "BG1",
                           "counterparty_balance": 123.0}]},
    ):
        facts = _facts(aid, ids)
        facts.update(copy.deepcopy(leak))
        _stub_engine(monkeypatch, {aid: facts})
        payload = survival_fact_payload(w, aid)
        assert payload["status"] == "unavailable", leak
        assert payload["reason_code"] == "privacy_boundary_violation", leak


# ---------------------------------------------------------------- S3 facts-only/API


def test_s3_facts_only_khong_khuyen_nghi_thu_tu_on_dinh_khong_rng(monkeypatch):
    w = _world_v7(seed=43)
    ids = _live_ids(w)
    aid = ids[0]
    facts = _facts(aid, ids)
    # path rows CỐ Ý đảo thứ tự đầu vào — renderer phải sort (protocol, target_id, path_id)
    facts["production_paths"] = list(reversed(facts["production_paths"]))
    _stub_engine(monkeypatch, {aid: facts})

    h0 = w.world_hash()
    payload_a = survival_fact_payload(w, aid)
    payload_b = survival_fact_payload(w, aid)
    assert payload_a == payload_b  # tất định, không RNG, không state tích lũy
    assert w.world_hash() == h0

    assert payload_a["status"] == "available"
    assert payload_a["card_mode"] == "expanded"  # gap > 0 ⇒ thẻ mở rộng
    rows = payload_a["facts"]["production_paths"]
    assert [r["path_id"] for r in rows] == ["canh_lua", "danh_ca"]
    lua = rows[0]
    assert lua["feasible"] is False and "thieu_giong" in lua["reason_codes"]
    ca = rows[1]
    assert ca.get("conditional") is True
    assert ca["net_food"] < payload_a["facts"]["need"]["kg_thoc_equivalent"]

    text = canonical_json(payload_a).lower()
    for tu in ('"recommended"', '"best"', '"rank"', "nên ", "hãy"):
        assert tu not in text, f"card lộ khuyến nghị/mớm ý: {tu!r}"


def test_s3_prompt_va_tool_cung_mot_schema_json(monkeypatch):
    w = _world_v7(seed=47)
    ids = _live_ids(w)
    aid = ids[0]
    _stub_engine(monkeypatch, {aid: _facts(aid, ids)})

    tool_payload = thuc_thi(w, aid, "xem_co_hoi_san_xuat", {})
    card = render_survival_fact_card(w, aid)
    assert card.startswith("[FACT CARD — SURVIVAL FEASIBILITY V7] ")
    embedded = json.loads(card.split("] ", 1)[1])
    assert embedded == tool_payload  # prompt card và tool JSON là MỘT schema

    rieng = build_user_rieng(w, aid, ["dinh_ky"])
    assert canonical_json(tool_payload) in rieng
    # prose sinh tồn cũ (bốn phần / kiểm tra sinh tồn) bị thay bằng facts
    assert "[KHẢ NĂNG THỰC THI SỐNG CÒN]" not in rieng
    assert "KIỂM TRA SINH TỒN" not in rieng


def test_s3_compact_khi_khong_co_gap(monkeypatch):
    w = _world_v7(seed=53)
    ids = _live_ids(w)
    aid = ids[0]
    du_an = _facts(aid, ids, gap={"kg_thoc_equivalent": 0.0})
    _stub_engine(monkeypatch, {aid: du_an})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "available"
    assert payload["card_mode"] == "compact"


def test_s3_protocol_facts_dung_lich_v7():
    w = _world_v7(seed=59)
    from minds.world_tools import _contract_protocol_facts

    protocol = _contract_protocol_facts(w, int(w.tick))
    assert protocol is not None
    oral = protocol["oral_contract"]
    assert oral["proposal_response_earliest_tick"] == w.tick + 1
    assert oral["thoi_han_1_total_contributions"] == 1
    assert oral["gop_cong_execution_rule"] == "0 <= tick - tick_ky < thoi_han"
    assert oral["unreachable_reason_code"] == "delivery_unreachable"
    assert oral["minimum_tangible_reachability"] == "same_residence_or_same_village_same_bank"
    assert protocol["message"]["settles_assets"] is False


# ---------------------------------------------------------------- S6 quote distinction


def test_s6_quote_khong_phai_phantom_credit(monkeypatch):
    w = _world_v7(seed=61)
    ids = _live_ids(w)
    aid = ids[0]
    facts = _facts(aid, ids)
    facts["quote_paths"] = [{
        "protocol": "quote", "target_id": "BG00001", "path_id": "BG00001",
        "visible": True, "reachable": True, "feasible": False, "conditional": True,
        "chieu": "ban", "tai_san": "thoc",
        "so_luong": 30.0, "don_gia": 1.0, "thanh_toan": "ca",
        "requires_payment_asset": "ca", "requires_payment_amount": 30.0,
        "payment_owned": False, "reason_codes": ["insufficient_payment"],
        "earliest_settlement_tick": int(w.tick),
        "gross_food": 30.0, "net_food": 30.0,
    }]
    _stub_engine(monkeypatch, {aid: facts})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "available"
    quote = payload["facts"]["quote_paths"][0]
    # điều kiện protocol trung thực, không được đổi thành food đã có
    assert quote["payment_owned"] is False
    assert "insufficient_payment" in quote["reason_codes"]
    assert payload["facts"]["guaranteed_settled_inflow"] == []
    q_proto = payload["protocol"]["quote"]
    assert q_proto["requires_two_sided_escrow"] is True
    assert q_proto["unaccepted_quote_is_guaranteed_food"] is False
    assert q_proto["labor_is_not_escrowable"] is True


def test_s6_quote_co_payment_hien_duong_settlement(monkeypatch):
    w = _world_v7(seed=67)
    ids = _live_ids(w)
    aid = ids[0]
    facts = _facts(aid, ids)
    facts["quote_paths"] = [{
        "protocol": "quote", "target_id": "BG00002", "path_id": "BG00002",
        "visible": True, "reachable": True, "feasible": False, "conditional": True,
        "chieu": "ban", "tai_san": "thoc",
        "so_luong": 30.0, "don_gia": 1.0, "thanh_toan": "go",
        "requires_payment_asset": "go", "requires_payment_amount": 30.0,
        "payment_owned": True, "reason_codes": [],
        "earliest_settlement_tick": int(w.tick),
        "gross_food": 30.0, "net_food": 30.0,
    }]
    _stub_engine(monkeypatch, {aid: facts})
    payload = survival_fact_payload(w, aid)
    quote = payload["facts"]["quote_paths"][0]
    assert quote["payment_owned"] is True and quote["reason_codes"] == []
    assert quote["earliest_settlement_tick"] == w.tick


def test_s6_real_public_board_path_is_visible_without_external_food_or_balance():
    """Tool and prompt expose identical public offer facts, not the offerer's account."""
    w, requester, responder, offer_id = _real_v7_public_board_fixture()
    external_balance = 987_654.0
    w.ledger.sinh(
        responder, "thoc", external_balance, "khoi_tao", "fixture private balance", w.tick,
    )
    before = w.world_hash()

    tool_payload = thuc_thi(w, requester, "xem_co_hoi_san_xuat", {})
    card = render_survival_fact_card(w, requester)
    prompt = build_user_rieng(w, requester, ["dinh_ky"])

    assert tool_payload["status"] == "available"
    path = next(
        row for row in tool_payload["facts"]["contract_paths"]
        if row["target_id"] == offer_id
    )
    # Public board identity and terms are actionable protocol metadata, not a residence claim.
    assert path["counterparty_id"] == responder
    assert path["asset"] == "thoc" and path["quantity"] == pytest.approx(25.0)
    assert path["labor_per_tick"] == pytest.approx(40.0)
    assert path["visible"] is True and path["reachable"] is True
    assert path["conditional"] is True and path["feasible"] is False
    assert "unaccepted_contract_offer" in path["reason_codes"]
    # The public promise does not turn either the offerer's stock or its terms into food held now.
    assert tool_payload["facts"]["guaranteed_settled_inflow"] == []
    for field in (
        "owned_by_person", "provisionable_in_residence", "food_open",
        "decay_before_consumption", "guaranteed_settled_inflow",
        "guaranteed_feasible_output", "seed_use",
    ):
        assert all(_owner(row) != responder for row in tool_payload["facts"][field])
    wire = canonical_json(tool_payload)
    assert str(external_balance) not in wire
    assert json.loads(card.split("] ", 1)[1]) == tool_payload
    assert wire in prompt
    assert w.world_hash() == before


# ---------------------------------------------------------------- FakeTransport surface


def _env() -> EnvKeys:
    return EnvKeys(gemini_keys=["fixture-key"], nine_key="fixture-nine",
                   nine_base="http://fixture.invalid/v1")


def test_fake_transport_agent_thay_card_qua_tool_va_prompt(monkeypatch):
    """Vòng agentic thật (MockTransport): tool trả đúng schema v7, world bất biến."""
    w = _world_v7(seed=71)
    ids = _live_ids(w)
    aid = ids[0]
    _stub_engine(monkeypatch, {aid: _facts(aid, ids)})

    prompt = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    assert "[FACT CARD — SURVIVAL FEASIBILITY V7]" in prompt

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        contents = payload.get("contents", [])
        da_co_tool = any("functionResponse" in part
                         for c in contents for part in c.get("parts", []))
        if payload.get("tools") and not da_co_tool:
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{
                    "functionCall": {"name": "xem_co_hoi_san_xuat", "args": {}},
                }]}}],
                "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 4},
            })
        qd = {"id": aid, "hanh_dong": [], "ly_do": "đọc card sinh tồn rồi mới quyết"}
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [
                {"text": json.dumps(qd, ensure_ascii=False)}]}}],
            "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8},
        })

    raw = copy.deepcopy(load_config().raw())
    raw["minds"]["cong_cu_max_luot"] = 1
    gateway = GatewayReal(Config(raw), _env(), QuotaCounter(None),
                          transport=httpx.MockTransport(handler))
    h0 = w.world_hash()
    resp = gateway.goi_agentic(
        LLMRequest(prompt=prompt, ctx={}, tier="T0", batch_ids=[aid]), w, aid,
    )
    assert w.world_hash() == h0
    assert len(resp.tool_turns) == 1
    turn = resp.tool_turns[0]
    assert turn["name"] == "xem_co_hoi_san_xuat"
    assert turn["result"]["schema_version"] == SURVIVAL_SCHEMA_VERSION
    assert turn["result"]["status"] == "available"
    assert turn["result_hash"] == result_hash(turn["result"])
    # tool JSON = prompt card JSON (một schema, một nguồn engine)
    assert canonical_json(turn["result"]) in prompt
    assert json.loads(resp.text)["id"] == aid


def test_agent_chet_khong_duoc_hoi_card():
    w = _world_v7(seed=73)
    ids = _live_ids(w)
    aid = ids[0]
    w.agents[aid].con_song = False
    payload = thuc_thi(w, aid, "xem_co_hoi_san_xuat", {})
    assert payload.get("code") == "agent_unavailable"


@pytest.mark.parametrize("phase", ["decision", "post_common_land"])
def test_phase_hop_le_duoc_giu_nguyen(monkeypatch, phase):
    w = _world_v7(seed=79)
    ids = _live_ids(w)
    aid = ids[0]
    _stub_engine(monkeypatch, {aid: _facts(aid, ids, phase=phase)})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "available"
    assert payload["facts"]["phase"] == phase


def test_phase_la_bi_tu_choi(monkeypatch):
    w = _world_v7(seed=83)
    ids = _live_ids(w)
    aid = ids[0]
    _stub_engine(monkeypatch, {aid: _facts(aid, ids, phase="mid_tick")})
    payload = survival_fact_payload(w, aid)
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "invalid_engine_schema"
