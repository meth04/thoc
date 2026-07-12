"""PART 5 MCP — công cụ thế giới CHỈ ĐỌC + vòng agentic (function-calling).

Hai bất biến phải chứng minh: (1) công cụ không đổi state (world_hash bất biến);
(2) vòng agentic gọi công cụ rồi trả quyết định, engine vẫn nhận kế hoạch.
"""

from __future__ import annotations

import json

import httpx

from engine.config import load_config
from minds.keypool import EnvKeys
from minds.providers_real import GatewayReal
from minds.quota import QuotaCounter
from minds.world_tools import CONG_CU, thuc_thi
from tests.helpers import the_gioi_test


def _env() -> EnvKeys:
    return EnvKeys(gemini_keys=["k1", "k2"], nine_key="nk", nine_base="http://x/v1")


def test_moi_cong_cu_chi_doc_khong_doi_the_gioi():
    """Gọi MỌI công cụ cho MỌI agent → world_hash bất biến (điều luật #1)."""
    w = the_gioi_test(seed=7, giu_lai=6, thoc_moi_nguoi=2000.0)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    h0 = w.world_hash()
    for ten in CONG_CU:
        for aid in ids:
            args: dict = {}
            if ten == "gia_cho":
                args = {"tai_san": "go"}
            elif ten in ("uy_tin_voi", "nghe_ve"):
                args = {"nguoi": ids[-1]}
            elif ten == "dat_cong_gan":
                args = {"toi_da": 3}
            kq = thuc_thi(w, aid, ten, args)
            assert isinstance(kq, dict)  # luôn trả JSON-được
    assert w.world_hash() == h0  # KHÔNG một công cụ nào chạm state


def test_cong_cu_ten_la_khong_raise():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=1000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    kq = thuc_thi(w, aid, "hack_ledger", {})  # tên bịa → lỗi mềm, không sập
    assert "loi" in kq


def _fake_transport_vong_cong_cu(dem: dict):
    """Gemini giả: lượt 1 gọi công cụ xem_thoi_tiet; lượt 2 trả quyết định."""

    def kich_ban(r: httpx.Request):
        payload = json.loads(r.content)
        contents = payload.get("contents", [])
        co_ket_qua = any("functionResponse" in p
                         for c in contents for p in c.get("parts", []))
        if payload.get("tools") and not co_ket_qua:
            dem["goi_tool"] = dem.get("goi_tool", 0) + 1
            return httpx.Response(200, json={
                "candidates": [{"content": {"parts": [
                    {"functionCall": {"name": "xem_thoi_tiet", "args": {}}}]}}],
                "usageMetadata": {"promptTokenCount": 40, "candidatesTokenCount": 6},
            })
        # đã có kết quả công cụ → ra quyết định
        text = contents[0]["parts"][0]["text"]
        import re
        m = re.search(r'\(id "([AE]\d+)"\)', text)
        aid = m.group(1) if m else "A0001"
        qd = {"id": aid, "hanh_dong": [{"loai": "phan_bo_cong", "hoc": False}],
              "ly_do": "đã hỏi thời tiết rồi mới quyết"}
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [
                {"text": json.dumps(qd, ensure_ascii=False)}]}}],
            "usageMetadata": {"promptTokenCount": 70, "candidatesTokenCount": 18},
        })

    return httpx.MockTransport(kich_ban)


def test_vong_agentic_goi_cong_cu_roi_quyet_dinh():
    """LLM gọi công cụ (đọc thời tiết) rồi trả quyết định; world_hash bất biến."""
    from minds.gateway import LLMRequest

    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=2000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    from minds.prompts import build_agent_prompt

    prompt = build_agent_prompt(w, aid, {})
    dem: dict = {}
    gw = GatewayReal(load_config(), _env(), QuotaCounter(None),
                     transport=_fake_transport_vong_cong_cu(dem))
    h0 = w.world_hash()
    req = LLMRequest(prompt=prompt, ctx={}, tier="T0", batch_ids=[aid])
    resp = gw.goi_agentic(req, w, aid)
    # đã gọi công cụ ≥1 lần, rồi ra JSON quyết định hợp lệ
    assert dem.get("goi_tool", 0) >= 1
    assert resp.retries >= 1  # số lượt gọi công cụ
    du_lieu = json.loads(resp.text)
    assert du_lieu["id"] == aid and du_lieu["hanh_dong"]
    # công cụ CHỈ ĐỌC — thế giới không đổi sau cả vòng agentic
    assert w.world_hash() == h0
