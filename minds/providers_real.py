"""Provider thật: AI Studio + 9router (OpenAI-compatible) — httpx trực tiếp (SPEC 7.2).

Transport tiêm được (FakeTransport trong test — không call thật nào trước HUMAN-GATE).
RPM của các model đều rất thấp (4–20) nên gọi tuần tự là đủ; không cần asyncio thật.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass

import httpx

from minds.gateway import LLMRequest, LLMResponse
from minds.keypool import KeyPool, key_hash
from minds.quota import QuotaCounter
from minds.tick_budget import (
    LoiVuotNganSachTick,
    bat_dau_yeu_cau,
    logical_id_cua,
    slot_con_lai_cho_yeu_cau,
)


def che_key(text: str) -> str:
    """Che API key trong mọi chuỗi lỗi/URL — key không bao giờ được lộ ra log."""
    text = re.sub(r"key=[^&\s'\"]+", "key=***", text)
    return re.sub(r"Bearer [^\s'\"]+", "Bearer ***", text)


def _bat_dau_request_thuc(req: LLMRequest) -> None:
    """Consume exactly one tick-budget slot immediately before ``client.post``.

    A route retry, a 429 retry and every turn in an agentic tool loop each
    reaches this function independently. It enforces the 1..N cap of the
    *specific agent*, rather than a misleading cap for the whole village.
    """
    bat_dau_yeu_cau(req)


def _luot_tool_huu_dung(req: LLMRequest, cau_hinh_max_luot: int) -> int:
    """Cap tool turns so one agent always retains a final JSON call.

    A tool turn is itself an LLM request.  With a per-agent cap of 10, the
    most an agent can do is 9 tool requests plus one final decision—not 10
    tools *and* a hidden eleventh model request.
    """
    con_lai = slot_con_lai_cho_yeu_cau(req)
    if con_lai is None:
        return max(0, int(cau_hinh_max_luot))
    if con_lai < 1:
        raise LoiVuotNganSachTick(
            f"tick {getattr(getattr(req, 'tick_budget', None), 'tick', '?')}: "
            f"hết slot LLM cho {logical_id_cua(req)}"
        )
    return min(max(0, int(cau_hinh_max_luot)), max(0, con_lai - 1))


@dataclass
class Route:
    provider: str  # "aistudio" | "ninerouter"
    model: str
    rpm: int
    rpd: int


class LoiHetQuota(Exception):
    """Model/route cạn ngân sách trong chu kỳ hiện hành.

    Thuộc tính `so_attempt_hong`: số attempt đã thất bại trước khi bó tay
    (điều luật #6 — orchestrator ghi vết vào llm_calls kể cả call thất bại).
    """

    so_attempt_hong: int = 0


class LoiProviderHong(LoiHetQuota):
    """Lỗi HTTP/parse dai dẳng dù ngân sách RPD còn — KHÔNG nên chờ slot RPM
    (phân biệt với LoiHetQuota-vì-cạn-RPD để tầng pacing không đợi vô ích)."""


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
        _bat_dau_request_thuc(req)
        r = self.client.post(
            f"{self.base}/v1beta/models/{model}:generateContent",
            params={"key": key},
            json={
                "contents": [{"parts": [{"text": req.prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                    # JSON mode (Structured Output, PART 5.2): buộc trả JSON hợp lệ →
                    # json_repair chỉ còn là lưới an toàn hiếm dùng, hết lỗi cú pháp
                    "responseMimeType": "application/json",
                },
            },
        )
        if r.status_code == 429:
            self.pool.bao_429(key, time.time())
            raise LoiRateLimit(key_hash(key))  # exception CHỈ mang hash, không mang key
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

    def goi_agentic(self, req: LLMRequest, model: str, temperature: float,
                    max_tokens: int, w, aid: str, khai_bao: list, thuc_thi,
                    max_luot: int, chon_key, xong_key) -> LLMResponse:
        """Vòng agentic Gemini function-calling (PART 5 MCP): LLM gọi công cụ CHỈ ĐỌC
        nhiều lượt trước khi quyết. MỖI LƯỢT lấy KEY MỚI (chon_key) rồi trả (xong_key có
        ghi quota nếu thành công) — một agent nghĩ 10 lượt = 10 request trải trên 10 key,
        tôn trọng RPM 4/key thay vì dội 1 key. Hội thoại nằm trong `contents` (không phụ
        thuộc key). Công cụ không chạm state (điều luật #1); tất định qua replay transcript."""
        t0 = time.time()
        contents: list[dict] = [{"role": "user", "parts": [{"text": req.prompt}]}]
        tools = [{"functionDeclarations": khai_bao}]
        tok_in = tok_out = 0
        # A function call is evidence, not merely an implementation detail:
        # persist the exact effective arguments and read-only response so a
        # later replay can attest the information set that preceded a choice.
        from minds.world_tools import catalog_hash, result_hash

        tool_turns: list[dict] = []
        tool_catalog = catalog_hash()
        for luot in range(max_luot + 1):
            key = chon_key()
            if key is None:
                raise LoiHetSlot("aistudio-het-slot")  # tràn cả vòng sang 9router
            # ``chon_key`` already reserved an in-flight key.  A rejected
            # tick-budget slot must release it without creating a quota row.
            try:
                _bat_dau_request_thuc(req)
            except LoiVuotNganSachTick:
                xong_key(key, False)
                raise
            thanh_cong = False
            try:
                cfg = {"temperature": temperature, "maxOutputTokens": max_tokens}
                body: dict = {"contents": contents, "generationConfig": cfg}
                if luot < max_luot:
                    body["tools"] = tools
                else:
                    cfg["responseMimeType"] = "application/json"  # lượt cuối: ép JSON quyết
                r = self.client.post(
                    f"{self.base}/v1beta/models/{model}:generateContent",
                    params={"key": key}, json=body,
                )
                if r.status_code == 429:
                    self.pool.bao_429(key, time.time())
                    raise LoiRateLimit(key_hash(key))
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise httpx.HTTPError(che_key(str(e))) from None
                self.pool.bao_ok(key)
                thanh_cong = True
            finally:
                xong_key(key, thanh_cong)  # trả in-flight + ghi quota (RPM/RPD) nếu thành
            d = r.json()
            usage = d.get("usageMetadata", {})
            tok_in += int(usage.get("promptTokenCount", 0))
            tok_out += int(usage.get("candidatesTokenCount", 0))
            parts = (d.get("candidates", [{}])[0].get("content", {}).get("parts", []))
            goi_cong_cu = [p["functionCall"] for p in parts if "functionCall" in p]
            if not goi_cong_cu:
                text = "".join(p.get("text", "") for p in parts)
                return LLMResponse(
                    text=text, provider="aistudio", model=model, tok_in=tok_in,
                    tok_out=tok_out, latency_s=time.time() - t0,
                    key_hash=key_hash(key), retries=luot,
                    tool_turns=tool_turns, tool_catalog_hash=tool_catalog,
                )  # retries = số lượt (độ sâu nghĩ)
            # LLM gọi công cụ → thực thi CHỈ ĐỌC, đưa kết quả vào hội thoại rồi lặp
            contents.append({"role": "model", "parts": [
                {"functionCall": fc} for fc in goi_cong_cu]})
            responses: list[dict] = []
            for index, fc in enumerate(goi_cong_cu):
                name = str(fc.get("name", ""))
                raw_args = fc.get("args")
                args = dict(raw_args) if isinstance(raw_args, dict) else {}
                result = thuc_thi(w, aid, name, args)
                tool_turns.append({
                    "turn": int(luot),
                    "index": int(index),
                    "name": name,
                    "args": args,
                    "result": result,
                    "result_hash": result_hash(result),
                })
                responses.append({"functionResponse": {"name": name, "response": result}})
            contents.append({"role": "user", "parts": [
                *responses]})
        # lượt cuối ép JSON nên luôn return ở trên — nhánh này chỉ để an toàn kiểu
        return LLMResponse(text="{}", provider="aistudio", model=model, tok_in=tok_in,
                           tok_out=tok_out, latency_s=time.time() - t0, key_hash="",
                           tool_turns=tool_turns, tool_catalog_hash=tool_catalog)


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

    def goi_agentic(self, req: LLMRequest, model: str, temperature: float,
                    max_tokens: int, w, aid: str, khai_bao: list, thuc_thi,
                    max_luot: int, ghi_thanh_cong=None) -> LLMResponse:
        """Vòng agentic OpenAI-compatible (MCP trên 9router): LLM gọi công cụ CHỈ ĐỌC
        nhiều lượt trước khi quyết. Công cụ = KHAI_BAO_CONG_CU bọc dạng OpenAI tools."""
        t0 = time.time()
        tools = [{"type": "function", "function": kb} for kb in khai_bao]
        messages: list[dict] = [{"role": "user", "content": req.prompt}]
        tok_in = tok_out = 0
        from minds.world_tools import catalog_hash, result_hash

        tool_turns: list[dict] = []
        tool_catalog = catalog_hash()
        for luot in range(max_luot + 1):
            body: dict = {"model": model, "messages": messages, "temperature": temperature,
                          "max_tokens": max_tokens, "stream": False}
            if luot < max_luot:
                body["tools"] = tools  # còn lượt → cho gọi công cụ
            else:
                body["response_format"] = {"type": "json_object"}  # lượt cuối: ép quyết
            _bat_dau_request_thuc(req)
            r = self.client.post(f"{self.base}/chat/completions",
                                 headers={"Authorization": f"Bearer {self.key}"}, json=body)
            if r.status_code == 429:
                raise LoiRateLimit("ninerouter")
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise httpx.HTTPError(che_key(str(e))) from None
            # One agentic response may contain many HTTP turns.  Count each
            # successful turn now—not once when the entire conversation ends—
            # so RPM/RPD state and the auditable scheduler describe the same
            # physical requests.  This also preserves calls already spent if
            # a later tool turn returns malformed JSON.
            if ghi_thanh_cong is not None:
                ghi_thanh_cong()
            d = r.json()
            usage = d.get("usage", {})
            tok_in += int(usage.get("prompt_tokens", 0))
            tok_out += int(usage.get("completion_tokens", 0))
            msg = d["choices"][0]["message"]
            goi_cc = msg.get("tool_calls") or []
            if not goi_cc:
                return LLMResponse(
                    text=msg.get("content") or "", provider="ninerouter", model=model,
                    tok_in=tok_in, tok_out=tok_out, latency_s=time.time() - t0,
                    key_hash=key_hash(self.key), retries=luot,
                    tool_turns=tool_turns, tool_catalog_hash=tool_catalog)
            messages.append({"role": "assistant", "content": msg.get("content"),
                             "tool_calls": goi_cc})
            import json as _json
            for index, tc in enumerate(goi_cc):
                fn = tc.get("function", {})
                try:
                    args = _json.loads(fn.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                name = str(fn.get("name", ""))
                kq = thuc_thi(w, aid, name, args)
                tool_turns.append({
                    "turn": int(luot),
                    "index": int(index),
                    "name": name,
                    "args": args,
                    "result": kq,
                    "result_hash": result_hash(kq),
                })
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                  "content": _json.dumps(kq, ensure_ascii=False)})
        return LLMResponse(text="{}", provider="ninerouter", model=model, tok_in=tok_in,
                           tok_out=tok_out, latency_s=time.time() - t0,
                           key_hash=key_hash(self.key), tool_turns=tool_turns,
                           tool_catalog_hash=tool_catalog)

    def goi(self, req: LLMRequest, model: str, temperature: float,
            max_tokens: int) -> LLMResponse:
        t0 = time.time()
        _bat_dau_request_thuc(req)
        r = self.client.post(
            f"{self.base}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "model": model,  # GIỮ NGUYÊN tiền tố gc/
                "messages": [{"role": "user", "content": req.prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                # 9router mặc định trả SSE stream kể cả khi không xin — phải tắt tường minh
                "stream": False,
                # JSON mode (Structured Output, PART 5.2) — OpenAI-compatible
                "response_format": {"type": "json_object"},
            },
        )
        if r.status_code == 429:
            raise LoiRateLimit("ninerouter")
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise httpx.HTTPError(che_key(str(e))) from None  # không lộ key/header
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
    """429/nghẽn slot — chỉ mang key_hash (không bao giờ giữ key thô, điều luật #4 mục 4)."""

    def __init__(self, key_hash: str):
        self.key_hash = key_hash
        super().__init__("429")


class LoiHetSlot(LoiRateLimit):
    """Route CẠN SLOT cục bộ (mọi key RPM đầy / cooldown / RPD cạn) — retry cùng route
    vô ích, phải TRÀN sang route sau. Khác 429 server (retry cùng route bằng key khác)."""


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
            cooldown_toi_da_s=float(cfg.get("quotas.retry.cooldown_toi_da_s")),
        )
        self.aistudio = AIStudioProvider(self.pool_aistudio, transport=transport)
        self.ninerouter = NineRouterProvider(env.nine_key, env.nine_base or "http://localhost",
                                             transport=transport)
        self._env = env
        self.strict_treatment_cfg = dict(cfg.get("minds.nghiem_thuc", {}))
        self.strict_treatment = bool(self.strict_treatment_cfg.get("bat", False))
        if self.strict_treatment:
            provider = str(self.strict_treatment_cfg.get("provider", ""))
            model = str(self.strict_treatment_cfg.get("model", ""))
            if not provider or not model:
                raise ValueError(
                    "minds.nghiem_thuc bật nhưng thiếu provider/model — không được âm thầm "
                    "rơi về route tier"
                )
        # GIỮ CHỖ NGUYÊN TỬ khi chọn key (chống thundering-herd lúc fan-out song song):
        # đếm call ĐANG BAY mỗi key; chọn key thì +1, xong (thành/bại) thì -1. Worker sau
        # thấy key đã đầy slot → chọn key khác → trải đều 15-30 key thay vì dội 1 key.
        self._sel_lock = threading.Lock()
        self._dang_bay: dict[str, int] = {}

    # ---------- cấu hình route ----------
    def routes_cua_tier(self, tier: str) -> list[Route]:
        if self.strict_treatment:
            provider = str(self.strict_treatment_cfg["provider"])
            model = str(self.strict_treatment_cfg["model"])
            q = self.cfg.raw()["quotas"].get(provider, {}).get("models", {}).get(model)
            if not isinstance(q, dict):
                raise ValueError(
                    f"route treatment không có quota khai báo: {provider}/{model}"
                )
            return [Route(provider, model, int(q.get("rpm", 5)), int(q.get("rpd", 100)))]
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

    def kha_nang_burst(self, route: Route, now: float) -> int:
        """Số request có thể BẮT ĐẦU ngay trong cửa sổ RPM hiện tại.

        Đây không phải dự báo RPD cả ngày.  Nó là headroom tức thời dùng bởi
        treatment coverage đầy đủ để quyết định trước tick liệu tất cả cư dân
        có thể nhận lượt suy nghĩ bắt buộc hay không.  Cooldown, RPD đã dùng
        và request đang bay đều trừ trực tiếp khỏi năng lực này.
        """
        if route.provider == "aistudio":
            cong_suat = 0
            for key in self.pool_aistudio.key_kha_dung(now):
                kh = key_hash(key)
                rpm_con = route.rpm - self.quota.rpm_hien_tai(
                    route.provider, route.model, kh, now
                ) - self._dang_bay.get(kh, 0)
                rpd_con = route.rpd - self.quota.rpd_da_dung(
                    route.provider, route.model, kh, now
                )
                cong_suat += max(0, min(rpm_con, rpd_con))
            return int(cong_suat)

        # A missing/placeholder 9router key is not capacity.  Treating it as
        # a usable route would turn a clean preflight failure into a later
        # HTTP failure after some residents have already been processed.
        key = str(self._env.nine_key or "")
        if not key or key.startswith("dien_key"):
            return 0
        kh = key_hash(key)
        rpm_con = route.rpm - self.quota.rpm_hien_tai(
            route.provider, route.model, kh, now
        ) - self._dang_bay.get(kh, 0)
        rpd_con = route.rpd - self.quota.rpd_da_dung(
            route.provider, route.model, kh, now
        )
        return int(max(0, min(rpm_con, rpd_con)))

    def concurrency_de_xuat(self, cap: int) -> int:
        """Số call LLM song song NÊN chạy mỗi tick, TỰ CO GIÃN theo số key: mỗi key
        aistudio gánh được ~vài call/phút → càng nhiều key càng chạy song song được.
        Công thức: 2×số_key + dự phòng, chặn trên bởi cap (chống cạn socket/thread)."""
        so_key = max(1, self.pool_aistudio.so_key())
        return max(1, min(cap, so_key * 2 + 4))

    # ---------- gọi ----------
    #: lỗi phản hồi provider bắt được khi gọi route — gồm cả body JSON hỏng
    #: (ValueError từ r.json()), thiếu choices (IndexError), cấu trúc lạ (TypeError)
    _LOI_PHAN_HOI = (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError)

    def goi(self, req: LLMRequest) -> LLMResponse:
        tier_cfg = self.cfg.get(f"models.tiers.{req.tier}")
        loi_cuoi: Exception | None = None
        so_attempt_hong = 0
        co_route_con_rpd = False
        for route in self.routes_cua_tier(req.tier):
            now = time.time()
            if self.con_lai(route, now) <= 0:
                continue  # route cạn RPD → tràn route sau
            co_route_con_rpd = True
            for _ in range(self.retry_toi_da + 1):
                try:
                    resp = self._goi_route(req, route, tier_cfg)
                    self.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                        time.time())
                    resp.retries = so_attempt_hong  # đếm retry THẬT (điều luật #6)
                    return resp
                except LoiHetSlot as e:
                    loi_cuoi = e  # route này cạn slot cục bộ → TRÀN route sau, khỏi retry
                    break
                except LoiRateLimit as e:
                    loi_cuoi = e
                    so_attempt_hong += 1
                    continue  # 429 server → xoay key / thử lại cùng route
                except self._LOI_PHAN_HOI as e:
                    loi_cuoi = e
                    so_attempt_hong += 1
                    continue
        thong_bao = che_key(str(loi_cuoi)) if loi_cuoi is not None else "không còn route"
        if co_route_con_rpd and isinstance(loi_cuoi, self._LOI_PHAN_HOI):
            # RPD còn mà mọi attempt đều lỗi phản hồi → provider hỏng, đừng chờ slot
            loi: LoiHetQuota = LoiProviderHong(
                f"tier {req.tier}: lỗi provider dai dẳng ({thong_bao})")
        else:
            loi = LoiHetQuota(f"tier {req.tier}: mọi route cạn/lỗi ({thong_bao})")
        loi.so_attempt_hong = so_attempt_hong
        raise loi

    def goi_agentic(self, req: LLMRequest, w, aid: str) -> LLMResponse:
        """Vòng công cụ CHỈ ĐỌC (MCP): ưu tiên route aistudio (Gemini function-calling);
        tier không có route aistudio → single-turn không công cụ (9router bản này chưa hỗ
        trợ vòng công cụ). Cùng xử lý tràn route / lỗi như goi()."""
        from minds.world_tools import KHAI_BAO_CONG_CU, thuc_thi

        tier_cfg = self.cfg.get(f"models.tiers.{req.tier}")
        sample_cfg = self.strict_treatment_cfg if self.strict_treatment else tier_cfg
        temperature = float(sample_cfg.get("temperature", tier_cfg.get("temperature", 0.9)))
        max_tokens = int(sample_cfg.get("max_output_tokens", tier_cfg.get("max_output_tokens", 2000)))
        max_luot_cau_hinh = int(self.cfg.get("minds.cong_cu_max_luot"))
        loi_cuoi: Exception | None = None
        so_attempt_hong = 0
        co_route_con_rpd = False
        for route in self.routes_cua_tier(req.tier):
            # Re-evaluate after a failed route too: a failed HTTP attempt has
            # already consumed this resident's budget, so the next route may
            # only have room for a direct final JSON answer.
            max_luot = _luot_tool_huu_dung(req, max_luot_cau_hinh)
            now = time.time()
            if self.con_lai(route, now) <= 0:
                continue
            co_route_con_rpd = True
            if route.provider != "aistudio":
                # 9router: vòng công cụ OpenAI-compatible (MCP cũng chạy trên call tràn)
                kh = key_hash(self._env.nine_key)
                if not self.quota.cho_phep(route.provider, route.model, kh,
                                           route.rpm, route.rpd, now):
                    loi_cuoi = LoiHetSlot(kh)
                    continue  # cạn slot → tràn route sau
                for _ in range(self.retry_toi_da + 1):
                    try:
                        resp = self.ninerouter.goi_agentic(
                            req, route.model, temperature, max_tokens, w, aid,
                            KHAI_BAO_CONG_CU, thuc_thi, max_luot,
                            ghi_thanh_cong=lambda _route=route, _kh=kh: self.quota.ghi_call(
                                _route.provider, _route.model, _kh, time.time()
                            ),
                        )
                        return resp
                    except (LoiRateLimit, *self._LOI_PHAN_HOI) as e:
                        loi_cuoi = e
                        so_attempt_hong += 1
                continue
            # MỖI LƯỢT trong vòng agentic lấy 1 key aistudio riêng (rải RPM 4/key) rồi
            # trả + ghi quota — chon_key giữ chỗ, xong_key nhả + ghi call nếu thành công.
            def _chon(_route=route):
                return self._chon_key_aistudio(_route, time.time())

            def _xong(key: str, thanh_cong: bool, _route=route):
                self._giai_phong(key)
                if thanh_cong:
                    self.quota.ghi_call(_route.provider, _route.model, key_hash(key),
                                        time.time())
            try:
                resp = self.aistudio.goi_agentic(
                    req, route.model, temperature, max_tokens, w, aid,
                    KHAI_BAO_CONG_CU, thuc_thi, max_luot, chon_key=_chon, xong_key=_xong)
                return resp
            except LoiHetSlot as e:
                loi_cuoi = e  # cạn slot giữa vòng → tràn route sau (9router)
                continue
            except (LoiRateLimit, *self._LOI_PHAN_HOI) as e:
                loi_cuoi = e
                so_attempt_hong += 1
                continue
        thong_bao = che_key(str(loi_cuoi)) if loi_cuoi is not None else "không còn route"
        if co_route_con_rpd and isinstance(loi_cuoi, self._LOI_PHAN_HOI):
            loi: LoiHetQuota = LoiProviderHong(f"tier {req.tier}: lỗi dai dẳng ({thong_bao})")
        else:
            loi = LoiHetQuota(f"tier {req.tier}: mọi route cạn/lỗi ({thong_bao})")
        loi.so_attempt_hong = so_attempt_hong
        raise loi

    def _chon_key_aistudio(self, route: Route, now: float) -> str | None:
        """Chọn key aistudio RẢNH NHẤT + GIỮ CHỖ nguyên tử. headroom = RPM − đã_dùng −
        đang_bay: worker song song thấy slot giảm dần nên trải đều thay vì dội 1 key.
        Trả None nếu mọi key cạn RPM/RPD/cooldown. Nhớ gọi _giai_phong sau khi call xong."""
        with self._sel_lock:
            tot_nhat: str | None = None
            diem_tot = -1.0
            for key in self.pool_aistudio.key_kha_dung(now):
                kh = key_hash(key)
                da_rpd = self.quota.rpd_da_dung(route.provider, route.model, kh, now)
                if da_rpd >= route.rpd:
                    continue  # cạn RPD hôm nay
                dung_rpm = (self.quota.rpm_hien_tai(route.provider, route.model, kh, now)
                            + self._dang_bay.get(kh, 0))
                if dung_rpm >= route.rpm:
                    continue  # đầy RPM (kể cả call đang bay)
                diem = (route.rpm - dung_rpm) + (route.rpd - da_rpd) / (route.rpd + 1.0)
                if diem > diem_tot or (diem == diem_tot and (tot_nhat is None
                                                             or kh < key_hash(tot_nhat))):
                    tot_nhat, diem_tot = key, diem
            if tot_nhat is not None:
                self._dang_bay[key_hash(tot_nhat)] = \
                    self._dang_bay.get(key_hash(tot_nhat), 0) + 1
            return tot_nhat

    def _giai_phong(self, key: str) -> None:
        """Trả slot đang-bay của key sau khi call xong (thành công hay lỗi)."""
        kh = key_hash(key)
        with self._sel_lock:
            if self._dang_bay.get(kh, 0) > 0:
                self._dang_bay[kh] -= 1

    def _goi_route(self, req: LLMRequest, route: Route, tier_cfg: dict) -> LLMResponse:
        now = time.time()
        sample_cfg = self.strict_treatment_cfg if self.strict_treatment else tier_cfg
        temperature = float(sample_cfg.get("temperature", tier_cfg.get("temperature", 0.9)))
        max_tokens = int(sample_cfg.get("max_output_tokens", tier_cfg.get("max_output_tokens", 2000)))
        if route.provider == "aistudio":
            key = self._chon_key_aistudio(route, now)
            if key is None:  # mọi key cạn RPM/RPD/cooldown → TRÀN route sau (đừng retry)
                raise LoiHetSlot("aistudio-het-slot")
            try:
                return self.aistudio.goi(req, route.model, temperature, max_tokens, key=key)
            finally:
                self._giai_phong(key)
        kh = key_hash(self._env.nine_key)
        if not self.quota.cho_phep(route.provider, route.model, kh,
                                   route.rpm, route.rpd, now):
            raise LoiHetSlot(kh)  # 9router cạn slot → tràn route sau
        return self.ninerouter.goi(req, route.model, temperature, max_tokens)


def budget_guard(gw: GatewayReal, can_theo_tier: dict[str, int]) -> tuple[bool, str]:
    """Trước bước 3: ước lượng call cần; thiếu → (False, lý do) để checkpoint + dừng êm."""
    safety = float(gw.cfg.get("quotas.chung.safety_margin"))
    now = time.time()
    if gw.strict_treatment:
        route = gw.routes_cua_tier("T0")[0]
        can = sum(int(v) for v in can_theo_tier.values())
        con = gw.con_lai(route, now)
        if con * safety < can:
            return False, (f"treatment {route.provider}/{route.model}: cần {can} call, "
                           f"còn {con} (×{safety})")
        return True, ""
    for tier, can in sorted(can_theo_tier.items()):
        if can <= 0:
            continue
        tong_con = sum(gw.con_lai(r, now) for r in gw.routes_cua_tier(tier))
        if tong_con * safety < can:
            return False, f"tier {tier}: cần {can} call, còn {tong_con} (×{safety})"
    return True, ""


def burst_guard(gw: GatewayReal, can_theo_tier: dict[str, int]) -> tuple[bool, str]:
    """Fail closed when an autonomy tick cannot cover all adults immediately.

    The graph is a small max-flow allocation: a tier can consume any of its
    declared fallback routes, while a shared route (T0/T1 often share one)
    is counted only once.  A naive per-tier sum would double-count that shared
    provider capacity and allow exactly the partial cohort this guard exists
    to prevent.
    """
    nhu_cau = {str(tier): int(so) for tier, so in can_theo_tier.items() if int(so) > 0}
    if not nhu_cau:
        return True, ""
    now = time.time()
    safety = float(gw.cfg.get("quotas.chung.safety_margin"))
    routes_tier: dict[str, list[tuple[str, str]]] = {}
    cong_suat: dict[tuple[str, str], int] = {}
    raw_cong_suat: dict[tuple[str, str], int] = {}
    for tier in sorted(nhu_cau):
        keys: list[tuple[str, str]] = []
        for route in gw.routes_cua_tier(tier):
            key = (route.provider, route.model)
            if key not in raw_cong_suat:
                raw = gw.kha_nang_burst(route, now)
                raw_cong_suat[key] = raw
                # Quotas are already conservative configuration, but preserve
                # the project's global headroom rule.  Do not round one
                # genuinely available slot down to zero for a small scenario.
                cong_suat[key] = max(1, int(raw * safety)) if raw > 0 else 0
            if key not in keys:
                keys.append(key)
        routes_tier[tier] = keys

    # Edmonds–Karp over source -> tier -> route -> sink.  Inputs are small
    # (five tiers and a handful of routes), so clarity beats a clever shortcut.
    graph: dict[str, dict[str, int]] = {}

    def them_canh(u: str, v: str, cap: int) -> None:
        graph.setdefault(u, {})
        graph.setdefault(v, {})
        graph[u][v] = graph[u].get(v, 0) + max(0, int(cap))
        graph[v].setdefault(u, 0)

    source, sink = "__source__", "__sink__"
    tong_can = sum(nhu_cau.values())
    for tier, so in sorted(nhu_cau.items()):
        node_tier = f"tier:{tier}"
        them_canh(source, node_tier, so)
        for provider, model in routes_tier[tier]:
            them_canh(node_tier, f"route:{provider}/{model}", so)
    for (provider, model), cap in sorted(cong_suat.items()):
        them_canh(f"route:{provider}/{model}", sink, cap)

    dong = 0
    while True:
        truoc: dict[str, str | None] = {source: None}
        queue = [source]
        for u in queue:
            for v, cap in graph.get(u, {}).items():
                if cap > 0 and v not in truoc:
                    truoc[v] = u
                    queue.append(v)
                    if v == sink:
                        break
            if sink in truoc:
                break
        if sink not in truoc:
            break
        # Rebuild the actual source→sink path; the compact BFS queue above is
        # not necessarily that path.
        path: list[tuple[str, str]] = []
        v = sink
        while truoc[v] is not None:
            u = truoc[v]
            path.append((u, v))
            v = u
        day = min(graph[u][v] for u, v in path)
        for u, v in path:
            graph[u][v] -= day
            graph[v][u] = graph[v].get(u, 0) + day
        dong += day

    if dong >= tong_can:
        return True, ""
    chi_tiet_can = ", ".join(f"{tier}={so}" for tier, so in sorted(nhu_cau.items()))
    chi_tiet_cap = ", ".join(
        f"{provider}/{model}={cong_suat[(provider, model)]}/{raw_cong_suat[(provider, model)]}"
        for provider, model in sorted(cong_suat)
    ) or "không có route khả dụng"
    return False, (
        "RPM burst không đủ cho autonomy tick: "
        f"cần {tong_can} lượt bắt buộc ({chi_tiet_can}), "
        f"phân bổ được {dong}; headroom an toàn/raw: {chi_tiet_cap}"
    )
