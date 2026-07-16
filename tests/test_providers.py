"""Phase 5 — FakeTransport unit: 429/xoay key, RPD khóa, persist, budget guard, tràn route."""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from engine.config import load_config
from minds.gateway import LLMCallLog, LLMRequest
from minds.keypool import EnvKeys, KeyPool, key_hash, nap_env
from minds.providers_real import (
    AIStudioProvider,
    GatewayReal,
    LoiHetQuota,
    NineRouterProvider,
    budget_guard,
    burst_guard,
)
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
    route0 = gw.routes_cua_tier("T0")[0]
    rpd = route0.rpd
    kh = key_hash(env.gemini_keys[0])
    # nạp đầy bộ đếm RPD (ghi thẳng, khỏi gọi rpd lần)
    import time

    for _ in range(rpd):
        quota.ghi_call(route0.provider, route0.model, kh, time.time())
    quota._rpm.clear()  # chỉ test RPD, bỏ giới hạn RPM
    with pytest.raises(LoiHetQuota):
        gw.goi(req("T0"))


def test_c_restart_khong_mat_bo_dem(tmp_path):
    """(c) bộ đếm RPD persist SQLite — restart đọc lại đúng."""
    import time

    db = tmp_path / "quota.sqlite"
    q1 = QuotaCounter(db)
    for _ in range(7):
        q1.ghi_call("aistudio", "model-x", "abcd1234", time.time())
    q2 = QuotaCounter(db)  # "restart"
    assert q2.rpd_da_dung("aistudio", "model-x", "abcd1234", time.time()) == 7


def test_started_rpm_admission_is_atomic_durable_and_not_an_rpd_call(tmp_path):
    """Only three simultaneous physical starts enter a three-RPM window, across restart."""
    db = tmp_path / "quota.sqlite"
    counters = [QuotaCounter(db), QuotaCounter(db)]
    now = 1_000.0
    barrier = threading.Barrier(8)
    accepted: list[bool] = []
    accepted_lock = threading.Lock()

    def admit(index: int) -> None:
        barrier.wait()
        result = counters[index % len(counters)].nhan_slot_bat_dau(
            "aistudio", "model-x", "hash-only", rpm=3, rpd=20, now=now
        )
        with accepted_lock:
            accepted.append(result)

    workers = [threading.Thread(target=admit, args=(i,)) for i in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    restarted = QuotaCounter(db)
    assert sum(accepted) == 3
    assert restarted.rpm_hien_tai("aistudio", "model-x", "hash-only", now) == 3
    assert restarted.rpd_da_dung("aistudio", "model-x", "hash-only", now) == 0
    assert not restarted.nhan_slot_bat_dau(
        "aistudio", "model-x", "hash-only", rpm=3, rpd=20, now=now
    )
    assert restarted.nhan_slot_bat_dau(
        "aistudio", "model-x", "hash-only", rpm=3, rpd=20, now=now + 60.1
    )


def test_rpd_reservation_is_atomic_across_counters_and_settles_or_releases(tmp_path):
    """Two processes cannot both admit the last success-only RPD slot."""
    db = tmp_path / "quota.sqlite"
    counters = [QuotaCounter(db), QuotaCounter(db)]
    now = 4_000.0
    barrier = threading.Barrier(2)
    accepted: list[bool] = []
    lock = threading.Lock()

    def admit(counter: QuotaCounter) -> None:
        barrier.wait()
        value = counter.nhan_slot_bat_dau(
            "aistudio", "model-x", "hash-only", rpm=10, rpd=1, now=now
        )
        with lock:
            accepted.append(value)

    workers = [threading.Thread(target=admit, args=(counter,)) for counter in counters]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    verifier = QuotaCounter(db)
    assert accepted.count(True) == 1
    assert verifier.rpd_da_dung("aistudio", "model-x", "hash-only", now) == 0
    assert verifier.rpd_da_du_tru("aistudio", "model-x", "hash-only", now) == 1

    # A failed started request returns the provisional slot, rather than burning RPD.
    verifier.huy_call_du_tru("aistudio", "model-x", "hash-only")
    assert verifier.rpd_da_du_tru("aistudio", "model-x", "hash-only", now) == 0
    assert verifier.nhan_slot_bat_dau(
        "aistudio", "model-x", "hash-only", rpm=10, rpd=1, now=now
    )
    verifier.chot_call_du_tru("aistudio", "model-x", "hash-only")
    assert verifier.rpd_da_dung("aistudio", "model-x", "hash-only", now) == 1
    assert verifier.rpd_da_du_tru("aistudio", "model-x", "hash-only", now) == 0
    assert not verifier.nhan_slot_bat_dau(
        "aistudio", "model-x", "hash-only", rpm=10, rpd=1, now=now
    )


def test_429_cooldown_is_durable_and_does_not_increment_rpd(tmp_path):
    db = tmp_path / "quota.sqlite"
    q1 = QuotaCounter(db)
    now = 2_000.0
    assert q1.nhan_slot_bat_dau("aistudio", "model-x", "hash-only", 4, 20, now)
    expiry = q1.ghi_429("aistudio", "hash-only", now, 10.0, 20.0)

    q2 = QuotaCounter(db)  # a new process/gateway sees the same cooldown
    assert expiry == now + 10.0
    assert q2.dang_cooldown("aistudio", "hash-only", now + 9.9)
    assert not q2.nhan_slot_bat_dau(
        "aistudio", "model-x", "hash-only", 4, 20, now + 9.9
    )
    assert q2.rpd_da_dung("aistudio", "model-x", "hash-only", now + 9.9) == 0


def test_started_failure_retains_physical_claim_and_blocks_rpd_until_reset(tmp_path):
    """Unknown started billing fails closed; a retry must not reuse the same RPD slot."""
    cfg = load_config()
    cfg.raw()["quotas"]["aistudio"]["models"]["gemini-3.1-flash-lite"].update({
        "rpm": 10, "rpd": 1,
    })
    cfg.raw()["minds"]["nghiem_thuc"] = {
        "bat": True,
        "provider": "aistudio",
        "model": "gemini-3.1-flash-lite",
        "temperature": 0.2,
        "max_output_tokens": 100,
    }
    quota = QuotaCounter(None)
    attempts = LLMCallLog(tmp_path / "llm_calls.sqlite")
    replies = [resp_aistudio(status=500), resp_aistudio("[]")]
    gateway = GatewayReal(
        cfg, lam_env(1), quota,
        transport=fake_transport(lambda _request: replies.pop(0)), retry_toi_da=0,
        attempt_log=attempts,
    )
    route = gateway.routes_cua_tier("T0")[0]
    kh = key_hash(lam_env(1).gemini_keys[0])

    with pytest.raises(LoiHetQuota):
        gateway.goi(req("T0"))
    assert quota.rpd_da_dung(route.provider, route.model, kh, time.time()) == 0
    assert quota.rpd_da_du_tru(route.provider, route.model, kh, time.time()) == 1
    claim_id, status = quota._conn.execute(  # noqa: SLF001 - durable quota evidence
        "SELECT claim_id, status FROM quota_token_claims"
    ).fetchone()
    attempt = attempts._conn.execute(  # noqa: SLF001 - durable attempt evidence
        "SELECT quota_claim_id, attempt_started, status, billability FROM llm_attempts"
    ).fetchone()
    assert status == "unknown"
    assert attempt == (claim_id, 1, "http_error", "unknown")
    # The second fixture response must not be sent: the started unknown claim owns
    # the only RPD slot until the provider reset rather than being guessed free.
    with pytest.raises(LoiHetQuota):
        gateway.goi(req("T0"))
    assert len(replies) == 1


def test_provider_concurrency_caps_physical_http_requests():
    """The configured aistudio gate surrounds MockTransport.post, not just fan-out."""
    cfg = load_config()
    cfg.raw()["quotas"]["aistudio"]["concurrency"] = 2
    active = 0
    peak = 0
    active_lock = threading.Lock()
    two_inside = threading.Event()
    release = threading.Event()

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with active_lock:
            active += 1
            peak = max(peak, active)
            if active == 2:
                two_inside.set()
        assert release.wait(timeout=3.0)
        with active_lock:
            active -= 1
        return resp_aistudio("[]")

    gateway = GatewayReal(
        cfg, lam_env(3), QuotaCounter(None), transport=fake_transport(handler), retry_toi_da=0
    )
    errors: list[Exception] = []

    def call() -> None:
        try:
            gateway.goi(req("T0"))
        except Exception as exc:  # noqa: BLE001 - fixture reports unexpected provider failure
            errors.append(exc)

    workers = [threading.Thread(target=call) for _ in range(3)]
    for worker in workers:
        worker.start()
    assert two_inside.wait(timeout=3.0)
    release.set()
    for worker in workers:
        worker.join()

    assert not errors
    assert peak == 2


def test_ninerouter_burst_preflight_subtracts_durable_rpd_reservation():
    """Burst guard fail-closes when the only NineRouter RPD slot is in flight."""
    cfg = load_config()
    model = "gc/gemini-2.5-flash-lite"
    cfg.raw()["quotas"]["ninerouter"]["models"][model].update({"rpm": 10, "rpd": 1})
    quota = QuotaCounter(None)
    seen_http: list[httpx.Request] = []

    def no_http(request: httpx.Request) -> httpx.Response:
        seen_http.append(request)
        pytest.fail("burst preflight must not issue HTTP")

    gateway = GatewayReal(
        cfg, lam_env(1), quota, transport=fake_transport(no_http), retry_toi_da=0
    )
    route = next(route for route in gateway.routes_cua_tier("T2")
                 if route.provider == "ninerouter")
    kh = key_hash(lam_env(1).nine_key)
    now = time.time()
    assert quota.nhan_slot_bat_dau(
        route.provider, route.model, kh, route.rpm, route.rpd, now
    )
    assert quota.rpd_da_du_tru(route.provider, route.model, kh, now) == 1

    assert gateway.kha_nang_burst(route, now) == 0
    allowed, _reason = burst_guard(gateway, {"T2": 1})
    assert not allowed
    assert seen_http == []


def test_d_budget_thieu_dung_em_khong_degrade():
    """(d) budget guard: thiếu → (False, lý do); KHÔNG tự hạ tier."""
    import time

    env = lam_env(1)
    cfg = load_config()
    quota = QuotaCounter(None)
    gw = GatewayReal(cfg, env, quota, transport=fake_transport(lambda r: resp_aistudio()))
    # đốt gần hết RPD MỌI route của T0 (T0 nay có route aistudio + tràn 9router) — chừa 3
    now = time.time()
    con_tong = sum(gw.con_lai(r, now) for r in gw.routes_cua_tier("T0"))
    for route in gw.routes_cua_tier("T0"):
        kh = key_hash(env.gemini_keys[0]) if route.provider == "aistudio" \
            else key_hash(env.nine_key)
        for _ in range(route.rpd):  # đốt cạn từng route
            quota.ghi_call(route.provider, route.model, kh, now)
    # chừa lại 3 slot ở route đầu
    route0 = gw.routes_cua_tier("T0")[0]
    quota._conn.execute("UPDATE quota_counters SET so_call = so_call - 3 "
                        "WHERE provider=? AND model=?", (route0.provider, route0.model))
    quota._conn.commit()
    assert sum(gw.con_lai(r, now) for r in gw.routes_cua_tier("T0")) == 3 < con_tong
    du, ly_do = budget_guard(gw, {"T0": 100})
    assert not du and "T0" in ly_do
    du2, _ = budget_guard(gw, {"T0": 2})
    assert du2  # cần ít thì vẫn đi tiếp — không degrade, không chết oan


def test_strict_treatment_dung_mot_route_cho_moi_tier():
    """Research treatment không được lẫn model/provider theo học vấn hay failover."""
    cfg = load_config()
    cfg.raw()["minds"]["nghiem_thuc"] = {
        "bat": True,
        "provider": "aistudio",
        "model": "gemini-3.1-flash-lite",
        "temperature": 0.2,
        "max_output_tokens": 321,
    }
    gw = GatewayReal(cfg, lam_env(1), QuotaCounter(None),
                     transport=fake_transport(lambda _r: resp_aistudio("[]")))
    routes = [gw.routes_cua_tier(t)[0] for t in ("T0", "T1", "T2", "T3", "T4")]
    assert {(r.provider, r.model) for r in routes} == {
        ("aistudio", "gemini-3.1-flash-lite")
    }
    assert gw.goi(req("T4")).model == "gemini-3.1-flash-lite"


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
    # Default 9router policy is deliberately unverified. This fixture enables it
    # explicitly because it tests the separate fail-over path.
    cfg.raw()["quotas"]["ninerouter"]["models"][
        "gc/gemini-3.1-flash-lite-preview"
    ].update({"tpm": 1_000_000, "tpm_policy": "verified"})
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


def test_generation_methods_require_guarded_admission_and_no_health_probe_exists():
    """A provider instance cannot emit a generation POST through default callbacks."""
    aistudio = AIStudioProvider(
        KeyPool(["fixture-key"]),
        transport=httpx.MockTransport(lambda _request: pytest.fail("POST must not run")),
    )
    nine = NineRouterProvider(
        "fixture-nine", "http://fixture.invalid/v1",
        transport=httpx.MockTransport(lambda _request: pytest.fail("POST must not run")),
    )
    with pytest.raises(TypeError):
        aistudio.goi(req(), "model-x", 0.1, 10, key="fixture-key")
    with pytest.raises(TypeError):
        nine.goi(req(), "model-x", 0.1, 10)
    with pytest.raises(TypeError):
        aistudio.goi_agentic(
            req(), "model-x", 0.1, 10, None, "A0001", [], lambda *_args: {}, 0,
            lambda: "fixture-key", lambda *_args: None,
        )
    with pytest.raises(TypeError):
        nine.goi_agentic(
            req(), "model-x", 0.1, 10, None, "A0001", [], lambda *_args: {}, 0,
        )
    # Smoke must not make an unadmitted, unlogged /models request in addition to its cap.
    assert not hasattr(NineRouterProvider, "health_check")


def test_tpm_claim_uses_exact_utf8_body_overhead_output_cap_and_provider_total():
    """MockTransport sees exactly the UTF-8 bytes reserved before the HTTP request."""
    cfg = load_config()
    model_cfg = cfg.raw()["quotas"]["aistudio"]["models"]["gemini-3.1-flash-lite"]
    model_cfg.update({"rpm": 100, "rpd": 100, "tpm": 100_000})
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "[]"}]}}],
            "usageMetadata": {
                "promptTokenCount": 7, "candidatesTokenCount": 5, "totalTokenCount": 19,
            },
        })

    quota = QuotaCounter(None)
    gateway = GatewayReal(cfg, lam_env(1), quota, transport=fake_transport(handler), retry_toi_da=0)
    response = gateway.goi(LLMRequest(prompt="lúa và thuyền", ctx={}, tier="T0"))
    route = gateway.routes_cua_tier("T0")[0]
    kh = key_hash(lam_env(1).gemini_keys[0])
    row = quota._conn.execute(
        "SELECT reserved_tokens, settled_tokens, status FROM quota_token_claims"
    ).fetchone()

    assert response.tok_in == 7 and response.tok_out == 5
    assert seen and b"l\xc3\xbaa" in seen[0]
    assert row == (
        len(seen[0]) + cfg.get("quotas.chung.token_admission.fixed_overhead_tokens") + 4096,
        19,
        "settled",
    )
    assert quota.tpm_hien_tai(route.provider, route.model, kh, time.time()) == 19


def test_aistudio_physical_attempt_journals_the_durable_claim_id(tmp_path):
    """The attempt row identifies exactly the same physical claim that TPM settles."""
    cfg = load_config()
    quota = QuotaCounter(tmp_path / "quota.sqlite")
    attempts = LLMCallLog(tmp_path / "llm_calls.sqlite")
    gateway = GatewayReal(
        cfg, lam_env(1), quota, transport=fake_transport(lambda _request: resp_aistudio("[]")),
        retry_toi_da=0, attempt_log=attempts,
    )

    request = req("T0")
    response = gateway.goi(request)
    attempts.ghi(0, request, response, fallback=False)
    attempt_claim = attempts._conn.execute(  # noqa: SLF001 - durable attempt evidence
        "SELECT quota_claim_id FROM llm_attempts WHERE status='success'"
    ).fetchone()[0]
    logical_claim = attempts._conn.execute(  # noqa: SLF001 - logical-call evidence
        "SELECT quota_claim_id FROM llm_calls"
    ).fetchone()[0]
    quota_claim = quota._conn.execute(  # noqa: SLF001 - durable quota evidence
        "SELECT claim_id, status, settled_tokens FROM quota_token_claims"
    ).fetchone()

    assert attempt_claim
    assert logical_claim == attempt_claim
    assert quota_claim == (attempt_claim, "settled", 15)


def test_tpm_denial_before_start_never_posts_or_creates_a_claim(tmp_path):
    cfg = load_config()
    model = "gemini-3.1-flash-lite"
    cfg.raw()["quotas"]["aistudio"]["models"][model].update({"tpm": 100})
    cfg.raw()["minds"]["nghiem_thuc"] = {
        "bat": True, "provider": "aistudio", "model": model,
        "temperature": 0.2, "max_output_tokens": 1,
    }
    calls: list[httpx.Request] = []
    quota = QuotaCounter(None)
    attempts = LLMCallLog(tmp_path / "llm_calls.sqlite")
    gateway = GatewayReal(
        cfg, lam_env(1), quota,
        transport=fake_transport(lambda request: calls.append(request) or resp_aistudio("[]")),
        retry_toi_da=0, attempt_log=attempts,
    )

    with pytest.raises(LoiHetQuota):
        gateway.goi(req("T0"))

    assert calls == []
    assert quota._conn.execute("SELECT COUNT(*) FROM quota_token_claims").fetchone()[0] == 0
    assert attempts._conn.execute(  # noqa: SLF001 - no physical request started
        "SELECT attempt_started, status, billability, quota_claim_id FROM llm_attempts"
    ).fetchone() == (0, "quota_denied", "not_billable", None)


@pytest.mark.parametrize(
    ("case", "http_status", "tpm", "max_output_tokens", "attempt", "claim_status",
     "rpd_used", "rpd_reserved"),
    [
        ("success", 200, 100_000, 100, (1, "success", "billable"), "settled", 1, 0),
        ("http_error", 500, 100_000, 100, (1, "http_error", "unknown"), "unknown", 0, 1),
        ("rate_limited", 429, 100_000, 100, (1, "rate_limited", "unknown"), "unknown", 0, 1),
        ("denied_before_start", None, 100, 1, (0, "quota_denied", "not_billable"), None, 0, 0),
    ],
)
def test_tpm_claim_lifecycle_is_auditable_for_all_terminal_paths(
    tmp_path, case, http_status, tpm, max_output_tokens, attempt, claim_status,
    rpd_used, rpd_reserved,
):
    """Each physical path has one durable TPM outcome; denied work has no claim.

    This is deliberately a FakeTransport fixture. It exercises provider admission/audit
    behavior without loosening the production 9router verified-TPM requirement.
    """
    cfg = load_config()
    model = "gemini-3.1-flash-lite"
    cfg.raw()["quotas"]["aistudio"]["models"][model].update({
        "rpm": 100, "rpd": 100, "tpm": tpm,
    })
    cfg.raw()["minds"]["nghiem_thuc"] = {
        "bat": True, "provider": "aistudio", "model": model,
        "temperature": 0.2, "max_output_tokens": max_output_tokens,
    }
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return resp_aistudio("[]", status=http_status)

    quota = QuotaCounter(None)
    attempts = LLMCallLog(tmp_path / f"{case}.sqlite")
    gateway = GatewayReal(
        cfg, lam_env(1), quota, transport=fake_transport(handler), retry_toi_da=0,
        attempt_log=attempts,
    )
    request = req("T0")
    if claim_status == "settled":
        gateway.goi(request)
    else:
        with pytest.raises(LoiHetQuota):
            gateway.goi(request)

    started, attempt_status, billability, attempt_claim_id = attempts._conn.execute(  # noqa: SLF001
        "SELECT attempt_started, status, billability, quota_claim_id FROM llm_attempts"
    ).fetchone()
    assert (started, attempt_status, billability) == attempt
    assert len(calls) == int(attempt[0])

    claims = quota._conn.execute(  # noqa: SLF001 - durable TPM lifecycle evidence
        "SELECT claim_id, status FROM quota_token_claims"
    ).fetchall()
    if claim_status is None:
        assert claims == []
        assert attempt_claim_id is None
    else:
        assert len(claims) == 1
        assert claims[0] == (attempt_claim_id, claim_status)

    route = gateway.routes_cua_tier("T0")[0]
    kh = key_hash(lam_env(1).gemini_keys[0])
    now = time.time()
    assert quota.rpd_da_dung(route.provider, route.model, kh, now) == rpd_used
    assert quota.rpd_da_du_tru(route.provider, route.model, kh, now) == rpd_reserved


def test_tpm_admission_is_atomic_and_unknown_started_claim_retains_reservation(tmp_path):
    db = tmp_path / "quota.sqlite"
    counters = [QuotaCounter(db), QuotaCounter(db)]
    now = 12_000.0
    barrier = threading.Barrier(2)
    accepted = []

    def admit(counter: QuotaCounter) -> None:
        barrier.wait()
        accepted.append(counter.nhan_claim_bat_dau(
            "aistudio", "model-x", "hash-only", rpm=10, tpm=100, rpd=10,
            reserved_tokens=60, now=now,
        ))

    workers = [threading.Thread(target=admit, args=(counter,)) for counter in counters]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    claim = next(value for value in accepted if value is not None)
    verifier = QuotaCounter(db)
    assert sum(value is not None for value in accepted) == 1
    verifier.giu_claim_khong_ro(claim)
    assert verifier.tpm_hien_tai("aistudio", "model-x", "hash-only", now) == 60
    assert verifier.rpd_da_du_tru("aistudio", "model-x", "hash-only", now) == 1
    assert verifier.nhan_claim_bat_dau(
        "aistudio", "model-x", "hash-only", rpm=10, tpm=100, rpd=10,
        reserved_tokens=41, now=now,
    ) is None


def test_missing_aistudio_tpm_policy_is_configuration_error():
    cfg = load_config()
    del cfg.raw()["quotas"]["aistudio"]["models"]["gemini-3.1-flash-lite"]["tpm"]
    gateway = GatewayReal(cfg, lam_env(1), QuotaCounter(None))

    with pytest.raises(ValueError, match=r"\.tpm"):
        gateway.routes_cua_tier("T0")


def test_unverified_ninerouter_tpm_policy_fails_closed_without_http(tmp_path):
    """An unverified TPM route is a journaled denial, never a silent HTTP fallback."""
    cfg = load_config()
    calls: list[httpx.Request] = []
    attempts = LLMCallLog(tmp_path / "llm_calls.sqlite")
    gateway = GatewayReal(
        cfg, lam_env(1), QuotaCounter(None),
        transport=fake_transport(lambda request: calls.append(request) or resp_nine("[]")),
        retry_toi_da=0, attempt_log=attempts,
    )

    with pytest.raises(LoiHetQuota):
        gateway.goi(req("T2"))
    assert calls == []
    row = attempts._conn.execute(  # noqa: SLF001 - validate durable journal payload
        "SELECT attempt_started, status, billability, quota_claim_id FROM llm_attempts"
    ).fetchone()
    assert row == (0, "quota_denied", "not_billable", None)


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
