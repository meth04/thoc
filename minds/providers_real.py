"""Provider thật: AI Studio + 9router (OpenAI-compatible) — httpx trực tiếp (SPEC 7.2).

Transport tiêm được (FakeTransport trong test — không call thật nào trước HUMAN-GATE).
RPM của các model đều rất thấp (4–20) nên gọi tuần tự là đủ; không cần asyncio thật.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from minds.gateway import LLMRequest, LLMResponse
from minds.keypool import KeyPool, key_hash
from minds.quota import QuotaCounter


def che_key(text: str) -> str:
    """Che API key trong mọi chuỗi lỗi/URL — key không bao giờ được lộ ra log."""
    text = re.sub(r"key=[^&\s'\"]+", "key=***", text)
    return re.sub(r"Bearer [^\s'\"]+", "Bearer ***", text)


@dataclass
class Route:
    provider: str  # "aistudio" | "ninerouter"
    model: str
    rpm: int
    rpd: int


class LoiHetQuota(Exception):
    """Model/route cạn ngân sách trong chu kỳ hiện hành."""


class AIStudioProvider:
    ten = "aistudio"

    def __init__(self, pool: KeyPool, transport: httpx.BaseTransport | None = None,
                 base_url: str = "https://generativelanguage.googleapis.com"):
        self.pool = pool
        self.base = base_url
        self.client = httpx.Client(transport=transport, timeout=60.0)

    def goi(self, req: LLMRequest, model: str, temperature: float,
            max_tokens: int, key: str | None = None) -> LLMResponse:
        now = time.time()
        if key is None:
            key = self.pool.lay_key(now)
        if key is None:
            raise LoiHetQuota("aistudio: mọi key đang cooldown")
        t0 = time.time()
        r = self.client.post(
            f"{self.base}/v1beta/models/{model}:generateContent",
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": req.prompt}]}],
                "generationConfig": {"temperature": temperature,
                                     "maxOutputTokens": max_tokens},
            },
        )
        if r.status_code == 429:
            self.pool.bao_429(key, time.time())
            raise LoiRateLimit(key)
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPError(che_key(str(e))) from None  # không lộ key trong URL
        self.pool.bao_ok(key)
        d = r.json()
        text = "".join(
            p.get("text", "")
            for c in d.get("candidates", [])
            for p in c.get("content", {}).get("parts", [])
        )
        usage = d.get("usageMetadata", {})
        return LLMResponse(
            text=text, provider="aistudio", model=model,
            tok_in=int(usage.get("promptTokenCount", 0)),
            tok_out=int(usage.get("candidatesTokenCount", 0)),
            latency_s=time.time() - t0, key_hash=key_hash(key),
        )


class NineRouterProvider:
    ten = "ninerouter"

    def __init__(self, api_key: str, base_url: str,
                 transport: httpx.BaseTransport | None = None):
        self.key = api_key
        self.base = base_url.rstrip("/")
        self.client = httpx.Client(transport=transport, timeout=120.0)

    def health_check(self) -> bool:
        try:
            r = self.client.get(f"{self.base}/models",
                                headers={"Authorization": f"Bearer {self.key}"})
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def goi(self, req: LLMRequest, model: str, temperature: float,
            max_tokens: int) -> LLMResponse:
        t0 = time.time()
        r = self.client.post(
            f"{self.base}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": model,  # GIỮ NGUYÊN tiền tố gc/
                "messages": [{"role": "user", "content": req.prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if r.status_code == 429:
            raise LoiRateLimit("ninerouter")
        r.raise_for_status()
        d = r.json()
        text = d["choices"][0]["message"]["content"]
        usage = d.get("usage", {})
        return LLMResponse(
            text=text, provider="ninerouter", model=model,
            tok_in=int(usage.get("prompt_tokens", 0)),
            tok_out=int(usage.get("completion_tokens", 0)),
            latency_s=time.time() - t0, key_hash=key_hash(self.key),
        )


class LoiRateLimit(Exception):
    def __init__(self, key: str):
        self.key = key
        super().__init__("429")


class GatewayReal:
    """Routes/tier có tràn: thử route đầu còn ngân sách → tràn route sau (SPEC 7.2)."""

    def __init__(self, cfg, env, quota: QuotaCounter,
                 transport: httpx.BaseTransport | None = None, retry_toi_da: int = 2):
        self.cfg = cfg
        self.quota = quota
        self.retry_toi_da = retry_toi_da
        self.pool_aistudio = KeyPool(
            env.gemini_keys,
            cooldown_goc_s=float(cfg.get("quotas.retry.cooldown_429_s")),
        )
        self.aistudio = AIStudioProvider(self.pool_aistudio, transport=transport)
        self.ninerouter = NineRouterProvider(env.nine_key, env.nine_base or "http://localhost",
                                             transport=transport)
        self._env = env

    # ---------- cấu hình route ----------
    def routes_cua_tier(self, tier: str) -> list[Route]:
        routes = []
        for r in self.cfg.get(f"models.tiers.{tier}.routes"):
            q = self.cfg.raw()["quotas"][r["provider"]]["models"].get(r["model"], {})
            routes.append(Route(r["provider"], r["model"],
                                int(q.get("rpm", 5)), int(q.get("rpd", 100))))
        return routes

    def _key_hashes(self, provider: str) -> list[str]:
        if provider == "aistudio":
            return [key_hash(k) for k in self._env.gemini_keys]
        return [key_hash(self._env.nine_key)]

    def con_lai(self, route: Route, now: float) -> int:
        return self.quota.con_lai_rpd(route.provider, route.model,
                                      self._key_hashes(route.provider), route.rpd, now)

    # ---------- gọi ----------
    def goi(self, req: LLMRequest) -> LLMResponse:
        tier_cfg = self.cfg.get(f"models.tiers.{req.tier}")
        loi_cuoi: Exception | None = None
        for route in self.routes_cua_tier(req.tier):
            now = time.time()
            if self.con_lai(route, now) <= 0:
                continue  # route cạn RPD → tràn route sau
            for _ in range(self.retry_toi_da + 1):
                try:
                    resp = self._goi_route(req, route, tier_cfg)
                    self.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                        time.time())
                    return resp
                except LoiRateLimit as e:
                    loi_cuoi = e
                    continue  # xoay key / thử lại
                except (httpx.HTTPError, KeyError) as e:
                    loi_cuoi = e
                    continue
        raise LoiHetQuota(f"tier {req.tier}: mọi route cạn/lỗi ({loi_cuoi})")

    def _goi_route(self, req: LLMRequest, route: Route, tier_cfg: dict) -> LLMResponse:
        now = time.time()
        temperature = float(tier_cfg.get("temperature", 0.9))
        max_tokens = int(tier_cfg.get("max_output_tokens", 2000))
        if route.provider == "aistudio":
            key = self.pool_aistudio.lay_key(now)
            if key is None:
                raise LoiRateLimit("aistudio-cooldown")
            kh = key_hash(key)
            if not self.quota.cho_phep(route.provider, route.model, kh,
                                       route.rpm, route.rpd, now):
                raise LoiRateLimit(kh)
            return self.aistudio.goi(req, route.model, temperature, max_tokens, key=key)
        kh = key_hash(self._env.nine_key)
        if not self.quota.cho_phep(route.provider, route.model, kh,
                                   route.rpm, route.rpd, now):
            raise LoiRateLimit(kh)
        return self.ninerouter.goi(req, route.model, temperature, max_tokens)


def budget_guard(gw: GatewayReal, can_theo_tier: dict[str, int]) -> tuple[bool, str]:
    """Trước bước 3: ước lượng call cần; thiếu → (False, lý do) để checkpoint + dừng êm."""
    safety = float(gw.cfg.get("quotas.chung.safety_margin"))
    now = time.time()
    for tier, can in sorted(can_theo_tier.items()):
        if can <= 0:
            continue
        tong_con = sum(gw.con_lai(r, now) for r in gw.routes_cua_tier(tier))
        if tong_con * safety < can:
            return False, f"tier {tier}: cần {can} call, còn {tong_con} (×{safety})"
    return True, ""
