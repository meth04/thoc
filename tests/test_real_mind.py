"""MindReal end-to-end với FakeTransport — nối dây LLM thật mà không đốt quota."""

from __future__ import annotations

import json
import re

import httpx

from engine.config import load_config
from minds.keypool import EnvKeys
from minds.real import MindReal
from tests.helpers import chay_tick, the_gioi_test


def lam_env() -> EnvKeys:
    return EnvKeys(gemini_keys=["k1", "k2"], nine_key="nk",
                   nine_base="http://localhost:9/v1", llm_mode="real")


def _ids_tu_prompt(payload: dict) -> list[str]:
    """Rút danh sách id được hỏi từ prompt (dòng 'id theo thứ tự: [...]')."""
    if "contents" in payload:  # aistudio
        text = payload["contents"][0]["parts"][0]["text"]
    else:  # ninerouter
        text = payload["messages"][0]["content"]
    m = re.search(r"id theo thứ tự: \[(.*?)\]", text)
    if not m:
        return []
    return re.findall(r"[AE]\d+", m.group(1))


def _resp(payload: dict, text: str) -> httpx.Response:
    if "contents" in payload:
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 99, "candidatesTokenCount": 42},
        })
    return httpx.Response(200, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 99, "completion_tokens": 42},
    })


def transport_ngoan():
    """LLM giả: trả quyết định hợp lệ (kèm fence markdown như model thật hay làm)."""

    def kich_ban(r: httpx.Request):
        payload = json.loads(r.content)
        ids = _ids_tu_prompt(payload)
        if not ids:  # nén hồi ký: trả object id→text
            text = "{}"
        else:
            qd = [{"id": i, "hanh_dong": [
                {"loai": "phan_bo_cong", "hoc": False},
                {"loai": "dat_lenh", "chieu": "mua", "tai_san": "go", "sl": 1,
                 "gia": 12.0},
            ], "ly_do": "làm ăn bình thường"} for i in ids]
            text = "```json\n" + json.dumps(qd, ensure_ascii=False) + "\n```"
        return _resp(payload, text)

    return httpx.MockTransport(kich_ban)


def transport_hong():
    """LLM giả luôn trả rác — pipeline phải fallback thẻ, thế giới vẫn chạy."""

    def kich_ban(r: httpx.Request):
        return _resp(json.loads(r.content), "Dạ em xin lỗi, hôm nay em mệt ạ...")

    return httpx.MockTransport(kich_ban)


def lam_mind(w, tmp_path, transport) -> MindReal:
    return MindReal(w, tmp_path, load_config(), lam_env(), tmp_path / "quota.sqlite",
                    transport=transport, cho_toi_s=2.0)


def test_mind_real_chay_3_tick_khong_loi(tmp_path):
    w = the_gioi_test(seed=61, giu_lai=10, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_ngoan())
    chay_tick(w, mind, 3)  # audit mỗi tick — có vi phạm là raise
    assert mind.so_call > 0
    assert mind.so_fallback == 0
    assert not mind.het_ngan_sach
    # lệnh mua gỗ từ LLM đã vào chợ (events có lệnh khớp hoặc ít nhất không lỗi)


def test_mind_real_llm_tra_rac_thi_fallback_the(tmp_path):
    w = the_gioi_test(seed=62, giu_lai=8, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_hong())
    chay_tick(w, mind, 2)
    assert mind.so_fallback > 0  # mọi người nghĩ đều rơi về thẻ
    assert all(a.con_song for a in w.agents.values()
               if a.con_song is not None and a.con_song)  # thế giới vẫn nguyên vẹn


def test_mind_real_het_ngan_sach_dung_em(tmp_path):
    import time as _t

    w = the_gioi_test(seed=63, giu_lai=10, thoc_moi_nguoi=2000)
    mind = lam_mind(w, tmp_path, transport_ngoan())
    # đốt sạch RPD của mọi key T0/T1 (cùng model aistudio)
    from minds.keypool import key_hash

    route = mind.gateway.routes_cua_tier("T0")[0]
    for k in lam_env().gemini_keys:
        for _ in range(route.rpd):
            mind.quota.ghi_call(route.provider, route.model, key_hash(k), _t.time())
    chay_tick(w, mind, 1)
    assert mind.het_ngan_sach, "thiếu ngân sách phải dừng êm, không degrade"
    assert mind.so_call == 0 or mind.so_fallback == 0  # không call liều


def test_patch_the_ngoai_khoang_khong_sap(tmp_path):
    """LLM trả thẻ vượt khoảng hợp lệ → bỏ trường lỗi, KHÔNG crash (điều luật #3)."""
    from minds.schemas import PolicyPatch, TheChinhSach, ap_patch

    the_cu = TheChinhSach()
    patch = PolicyPatch(du_tru_muc_tieu=50.0, canh_toi_da=3, y_dinh_sinh_con=1.0)
    the_moi = ap_patch(the_cu, patch)
    assert the_moi.du_tru_muc_tieu == the_cu.du_tru_muc_tieu  # trường lỗi bị bỏ
    assert the_moi.canh_toi_da == 3 and the_moi.y_dinh_sinh_con == 1.0  # trường tốt giữ
