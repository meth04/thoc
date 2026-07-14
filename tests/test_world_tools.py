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


def test_fact_cards_local_include_visible_quote_and_project_without_mutating_state():
    from pathlib import Path

    from engine import projects, quotes
    from engine.intents import KeHoach
    from engine.world import tao_the_gioi

    root = Path(__file__).resolve().parents[1]
    spatial = root / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
    livelihood = root / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"
    w = tao_the_gioi(load_config(overlays=[spatial, livelihood]), 91, events_path=None)
    owner, buyer = sorted(w.agents)[:2]
    site = next(p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    site.chu = owner
    w.tick = 1
    w.ledger.sinh(owner, "go", 20.0, "khai_thac", "fixture", w.tick)
    w.ledger.sinh(buyer, "thoc", 100.0, "khoi_tao", "fixture", w.tick)
    projects.dang_ky_du_an(w, {
        owner: KeHoach(id=owner, tao_du_an=[{"loai_du_an": "nha", "thua": site.id}]),
    })
    quotes.buoc_bao_gia(w, {
        owner: KeHoach(id=owner, dang_bao_gia=[{
            "chieu": "ban", "tai_san": "go", "so_luong": 4.0, "don_gia": 10.0,
            "thanh_toan": "thoc", "doi_tac": None, "giao_tai": "ngay",
        }]),
    })

    h0 = w.world_hash()
    du_an = thuc_thi(w, owner, "xem_du_an", {})
    bao_gia = thuc_thi(w, buyer, "xem_bao_gia", {})
    co_hoi = thuc_thi(w, owner, "xem_co_hoi_san_xuat", {})
    aggregate = thuc_thi(w, buyer, "get_phan_bo_cua_cai", {})

    assert du_an["du_an"][0]["id"] == "DA00001"
    assert bao_gia["bao_gia"][0]["id"] == "BG00001"
    assert isinstance(co_hoi["co_hoi"], list)
    assert aggregate["so_dan"] >= 1
    assert w.world_hash() == h0


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
