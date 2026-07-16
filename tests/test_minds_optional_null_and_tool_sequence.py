"""Regressions for optional-null semantics, neutral prices, and tool/final sequencing.

Local-only: worlds are fixtures and provider traffic uses ``httpx.MockTransport``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest

from engine.config import Config, load_config
from minds.capabilities import TU_TEN, chuan_hoa_null_hanh_dong
from minds.gateway import LLMRequest
from minds.keypool import EnvKeys
from minds.prompts import build_agent_prompt, muc_hanh_dong
from minds.providers_real import GatewayReal
from minds.quota import QuotaCounter
from minds.schemas import HanhDong, QuyetDinh
from minds.translate import quyet_dinh_thanh_ke_hoach
from tests.helpers import the_gioi_test

ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
LIVELIHOOD = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"


def _agent_ids(w) -> tuple[str, str]:
    ids = sorted(aid for aid, agent in w.agents.items() if agent.con_song)
    return ids[0], ids[1]


def _translate(w, aid: str, action: dict):
    rejected: list = []
    decision = QuyetDinh(id=aid, hanh_dong=[HanhDong(**action)])
    plan = quyet_dinh_thanh_ke_hoach(w, decision, rejected)
    return plan, rejected


def test_optional_top_level_null_matches_omitted_without_losing_sibling_fields():
    """The real regression shape was ``day_cho:null`` beside valid study/logging fields."""
    w = the_gioi_test(seed=31, giu_lai=3, thoc_moi_nguoi=2_000.0)
    aid, _other = _agent_ids(w)
    common = {"loai": "phan_bo_cong", "hoc": True, "khai_go_cong": 37.5}

    omitted, rejected_omitted = _translate(w, aid, common)
    explicit_null, rejected_null = _translate(w, aid, {**common, "day_cho": None})

    assert rejected_omitted == rejected_null == []
    assert explicit_null == omitted
    assert explicit_null.hoc is True
    assert explicit_null.cong_khai_go == 37.5
    assert explicit_null.day_cho == []


def test_empty_values_are_preserved_and_are_not_treated_as_omitted():
    cap = TU_TEN["phan_bo_cong"]
    raw = {
        "loai": "phan_bo_cong",
        "canh_thua": [],
        "gop_cong_cho": "",
        "day_cho": [],
    }
    assert chuan_hoa_null_hanh_dong(cap, raw) == raw


@pytest.mark.parametrize("required_value", [pytest.param(None, id="null"), pytest.param("omit", id="omitted")])
def test_required_top_level_field_null_or_omitted_is_rejected(required_value):
    w = the_gioi_test(seed=32, giu_lai=3, thoc_moi_nguoi=2_000.0)
    aid, _other = _agent_ids(w)
    action = {
        "loai": "dat_lenh",
        "chieu": "mua",
        "sl": 1.0,
        "gia": 2.0,
        "thanh_toan": "thoc",
    }
    if required_value != "omit":
        action["tai_san"] = required_value

    plan, rejected = _translate(w, aid, action)

    assert plan.dat_lenh == []
    assert len(rejected) == 1
    assert "tham số sai" in rejected[0][2]
    if required_value is None:
        assert "không được null" in rejected[0][2]


def test_nested_required_null_is_not_stripped_and_is_rejected_by_nested_validator():
    w = the_gioi_test(seed=33, giu_lai=3, thoc_moi_nguoi=2_000.0)
    aid, other = _agent_ids(w)
    action = {
        "loai": "de_nghi_hop_dong",
        "den": other,
        "hop_dong": {
            "cac_ben": [aid, other],
            "hinh_thuc": "mieng",
            "thoi_han": 1,
            "dieu_khoan": [{
                "loai": "chuyen_giao_mot_lan",
                "tu": aid,
                "den": other,
                "tai_san": None,
                "so_luong": 1.0,
                "tai": "ky_ket",
            }],
        },
    }

    plan, rejected = _translate(w, aid, action)

    assert plan.de_nghi_hop_dong == []
    assert len(rejected) == 1
    assert "tham số sai" in rejected[0][2]


def _menu_line(w, action: str) -> str:
    matches = [line for line in muc_hanh_dong(w) if f'"loai":"{action}"' in line]
    assert len(matches) == 1
    return matches[0]


def test_price_rendering_has_no_invalid_placeholder_or_static_anchor_without_evidence():
    w = the_gioi_test(seed=34, giu_lai=3, thoc_moi_nguoi=2_000.0)
    market = _menu_line(w, "dat_lenh")
    trip = _menu_line(w, "buon_chuyen")

    rendered = market + "\n" + trip
    assert "<đơn_giá_tự_chọn>" not in rendered
    assert '"gia":<' not in rendered
    assert '"gia":12' not in rendered
    assert '"gia":14' not in rendered
    assert "catalog cố ý không đặt một giá mẫu" in market
    assert "Chưa có giao dịch go khớp" in trip


def test_price_evidence_is_dynamic_and_remains_fact_text_not_an_action_anchor():
    w = Config(copy.deepcopy(load_config(overlays=[SPATIAL, LIVELIHOOD]).raw()))
    from engine.world import tao_the_gioi

    world = tao_the_gioi(w, 35, events_path=None)
    world.tick = 1
    world.gia_lich_su["go"] = [(1, 17.25)]

    trip = _menu_line(world, "buon_chuyen")
    quote = _menu_line(world, "dang_bao_gia")

    assert "Giá go khớp gần nhất là 17.25 thóc" in trip
    assert "Giá go khớp gần nhất là 17.25 thóc" in quote
    assert "không phải giá chuẩn" in trip and "không phải giá chuẩn" in quote
    assert '"gia":17.25' not in trip
    assert '"don_gia":17.25' not in quote


def _env() -> EnvKeys:
    return EnvKeys(gemini_keys=["fixture-key"], nine_key="fixture-nine",
                   nine_base="http://fixture.invalid/v1")


def test_prompt_and_payload_allow_tool_turn_before_json_only_final():
    """First payload permits a function call; only the forced final payload enables JSON mode."""
    w = the_gioi_test(seed=36, giu_lai=3, thoc_moi_nguoi=2_000.0)
    aid, _other = _agent_ids(w)
    prompt = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if payload.get("tools"):
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [{
                    "functionCall": {"name": "xem_thoi_tiet", "args": {}},
                }]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
            })
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{
                "text": json.dumps({"id": aid, "hanh_dong": [], "ly_do": "đủ dữ kiện"}),
            }]}}],
            "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 5},
        })

    raw = copy.deepcopy(load_config().raw())
    raw["minds"]["cong_cu_max_luot"] = 1
    gateway = GatewayReal(Config(raw), _env(), QuotaCounter(None),
                          transport=httpx.MockTransport(handler))
    response = gateway.goi_agentic(
        LLMRequest(prompt=prompt, ctx={}, tier="T0", batch_ids=[aid]), w, aid,
    )

    assert len(payloads) == 2
    first, final = payloads
    prompt_text = first["contents"][0]["parts"][0]["text"]
    assert "function/tool call KHÔNG phải câu trả lời quyết định" in prompt_text
    assert "CÂU TRẢ LỜI CUỐI CÙNG" in prompt_text
    assert first.get("tools")
    assert "responseMimeType" not in first["generationConfig"]
    assert "tools" not in final
    assert "responseMimeType" in final["generationConfig"]
    assert any(
        "functionResponse" in part
        for turn in final["contents"]
        for part in turn.get("parts", [])
    )
    assert json.loads(response.text) == {"id": aid, "hanh_dong": [], "ly_do": "đủ dữ kiện"}
