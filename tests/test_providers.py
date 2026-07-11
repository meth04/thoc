"""Phase 5 — FakeTransport unit: 429/xoay key, RPD khóa, persist, budget guard, tràn route."""

from __future__ import annotations

import httpx
import pytest

from engine.config import load_config
from minds.gateway import LLMRequest
from minds.keypool import EnvKeys, key_hash, nap_env
from minds.providers_real import GatewayReal, LoiHetQuota, budget_guard
from minds.quota import QuotaCounter


def lam_env(so_key: int = 3) -> EnvKeys:
    return EnvKeys(gemini_keys=[f"key_that_{i}" for i in range(1, so_key + 1)],
                   nine_key="nine_key_x", nine_base="http://localhost:8000/v1",
                   llm_mode="real")


def fake_transport(kich_ban):
    """kich_ban(request) → httpx.Response; đếm call qua closure."""
    return httpx.MockTransport(kich_ban)


def resp_aistudio(text="[]", status=200):
    return httpx.Response(status, json={
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }) if status == 200 else httpx.Response(status, json={"error": "quota"})


def resp_nine(text="[]", status=200):
    return httpx.Response(status, json={
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }) if status == 200 else httpx.Response(status, json={"error": "quota"})


def req(tier="T1"):
    return LLMRequest(prompt="xin chào", ctx={}, tier=tier, batch_ids=["A0001"])


def test_a_429_xen_ke_cooldown_va_xoay_key():
    """(a) key đầu dính 429 → cooldown + tự xoay sang key khác, call vẫn thành công."""
    thay = []

    def kich_ban(r: httpx.Request):
        key = r.url.params.get("key", "")
        thay.append(key)
        if key == "key_that_1":
            return resp_aistudio(status=429)
        return resp_aistudio("[]")

    env = lam_env(3)
    gw = GatewayReal(load_config(), env, QuotaCounter(None), transport=fake_transport(kich_ban))
    resp = gw.goi(req("T0"))  # T0 chỉ có route aistudio
    assert resp.provider == "aistudio"
    assert "key_that_1" in thay and thay[-1] != "key_that_1", "phải xoay sang key khác"
    # key_1 đang cooldown → call sau không đụng key_1 nữa
    thay.clear()
    gw.goi(req("T0"))
    assert "key_that_1" not in thay


def test_b_cham_rpd_khoa_model_toi_reset():
    """(b) chạm RPD → model coi như cạn (LoiHetQuota) tới kỳ reset."""
    def kich_ban(r):
        return resp_aistudio("[]")

    env = lam_env(1)
    cfg = load_config()
    quota = QuotaCounter(None)
    gw = GatewayReal(cfg, env, quota, transport=fake_transport(kich_ban))
    rpd = gw.routes_cua_tier("T0")[0].rpd
    kh = key_hash(env.gemini_keys[0])
    # nạp đầy bộ đếm RPD (ghi thẳng, khỏi gọi rpd lần)
    import time

    for _ in range(rpd):
        quota.ghi_call("aistudio", "gemma-4-31b-it", kh, time.time())
    quota._rpm.clear()  # chỉ test RPD, bỏ giới hạn RPM
    with pytest.raises(LoiHetQuota):
        gw.goi(req("T0"))


def test_c_restart_khong_mat_bo_dem(tmp_path):
    """(c) bộ đếm RPD persist SQLite — restart đọc lại đúng."""
    import time

    db = tmp_path / "quota.sqlite"
    q1 = QuotaCounter(db)
    for _ in range(7):
        q1.ghi_call("aistudio", "gemma-4-31b-it", "abcd1234", time.time())
    q2 = QuotaCounter(db)  # "restart"
    assert q2.rpd_da_dung("aistudio", "gemma-4-31b-it", "abcd1234", time.time()) == 7


def test_d_budget_thieu_dung_em_khong_degrade():
    """(d) budget guard: thiếu → (False, lý do); KHÔNG tự hạ tier."""
    import time

    env = lam_env(1)
    cfg = load_config()
    quota = QuotaCounter(None)
    gw = GatewayReal(cfg, env, quota, transport=fake_transport(lambda r: resp_aistudio()))
    # đốt gần hết RPD của T0
    route = gw.routes_cua_tier("T0")[0]
    kh = key_hash(env.gemini_keys[0])
    for _ in range(route.rpd - 3):
        quota.ghi_call(route.provider, route.model, kh, time.time())
    du, ly_do = budget_guard(gw, {"T0": 100})
    assert not du and "T0" in ly_do
    du2, _ = budget_guard(gw, {"T0": 2})
    assert du2  # cần ít thì vẫn đi tiếp — không degrade, không chết oan


def test_e_t1_can_key_tran_sang_9router():
    """(e) T1 cạn route aistudio → tự tràn sang 9router, log đúng provider."""
    import time

    goi_den = []

    def kich_ban(r: httpx.Request):
        goi_den.append(str(r.url))
        if "generativelanguage" in str(r.url):
            return resp_aistudio(status=429)
        return resp_nine("[]")

    env = lam_env(2)
    cfg = load_config()
    quota = QuotaCounter(None)
    gw = GatewayReal(cfg, env, quota, transport=fake_transport(kich_ban))
    # đốt sạch RPD route aistudio của T1
    route1 = gw.routes_cua_tier("T1")[0]
    for k in env.gemini_keys:
        for _ in range(route1.rpd):
            quota.ghi_call(route1.provider, route1.model, key_hash(k), time.time())
    resp = gw.goi(req("T1"))
    assert resp.provider == "ninerouter"
    assert resp.model.startswith("gc/"), "giữ nguyên tiền tố gc/ trong model id"
    assert all("generativelanguage" not in u for u in goi_den), "không gọi route đã cạn"


def test_nap_env_regex_gach_ngang(tmp_path):
    """Loader đọc tên biến có gạch ngang + LLM_MODE; key chỉ hiện dạng hash."""
    f = tmp_path / ".env"
    f.write_text(
        "LLM_MODE=mock\nGEMINI-API-KEY-2=abc2\nGEMINI-API-KEY-1=abc1\n"
        "GEMINI_API_KEY_3=abc3\nNINE_ROUTER_BASE_URL=http://x:8000/v1\n"
        "NINE_ROUTER_API_KEY=nk\n# GEMINI-API-KEY-9=comment\n",
        encoding="utf-8",
    )
    env = nap_env(f)
    assert env.gemini_keys == ["abc1", "abc2", "abc3"]  # theo số thứ tự
    assert env.nine_key == "nk" and env.nine_base == "http://x:8000/v1"
    assert env.llm_mode == "mock"
    assert len(key_hash("abc1")) == 8
