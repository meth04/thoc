"""Provider thật: AI Studio + 9router (OpenAI-compatible) — httpx trực tiếp (SPEC 7.2).

Transport tiêm được (FakeTransport trong test — không call thật nào trước HUMAN-GATE).
RPM của các model đều rất thấp (4–20) nên gọi tuần tự là đủ; không cần asyncio thật.
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass

import httpx

from minds.gateway import LLMRequest, LLMResponse
from minds.keypool import KeyPool, key_hash
from minds.quota import QuotaClaim, QuotaCounter
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


def _json_utf8_chinh_xac(payload: dict) -> bytes:
    """Serialize the exact UTF-8 JSON body that will be passed to ``httpx``.

    Counting this byte sequence is deliberately more conservative than a model
    tokenizer: no external count endpoint is invoked and a token cannot contain
    zero bytes. Callers must transmit this exact ``content``, never ``json=``
    with an independently serialized object.
    """
    return json.dumps(payload, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _token_nguyen(value: object, *, field: str) -> int:
    """Parse one provider usage field without coercing malformed values.

    Usage is quota evidence.  In particular, ``True`` and a fractional string
    must not silently become one/zero tokens through Python's ``int`` coercion.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"provider token field không hợp lệ: {field}")
    if value < 0:
        raise ValueError(f"provider token field âm: {field}")
    return value


def _tong_token_provider(usage: object, *, input_key: str, output_key: str,
                          total_key: str) -> int:
    """Read a self-consistent provider total, failing closed on contradictions."""
    if not isinstance(usage, dict):
        raise ValueError("provider response thiếu usage metadata")
    input_value = usage.get(input_key)
    output_value = usage.get(output_key)
    components_present = input_value is not None or output_value is not None
    if components_present:
        if input_value is None or output_value is None:
            raise ValueError("provider response thiếu một component token usage")
        component_total = (
            _token_nguyen(input_value, field=input_key)
            + _token_nguyen(output_value, field=output_key)
        )
    else:
        component_total = None
    total = usage.get(total_key)
    if total is not None:
        parsed_total = _token_nguyen(total, field=total_key)
        if component_total is not None and parsed_total < component_total:
            raise ValueError("provider total tokens nhỏ hơn input+output")
        return parsed_total
    if component_total is None:
        raise ValueError("provider response thiếu total token usage")
    return component_total


def _bat_dau_request_thuc(req: LLMRequest) -> None:
    """Consume exactly one tick-budget slot immediately before ``client.post``.

    A route retry, a 429 retry and every turn in an agentic tool loop each
    reaches this function independently. It enforces the 1..N cap of the
    *specific agent*, rather than a misleading cap for the whole village.
    """
    bat_dau_yeu_cau(req)


def _ghi_http_attempt(
    sink,
    req: LLMRequest,
    *,
    provider: str,
    model: str,
    key_hash_value: str,
    attempt_started: bool,
    status: str,
    t0: float,
    http_status: int | None = None,
    error: Exception | None = None,
    provider_retry_ordinal: int = 0,
    route_ordinal: int = 0,
    tool_turn_ordinal: int | None = None,
    source: str | None = None,
    quota_claim_id: str | None = None,
) -> None:
    if sink is None:
        return
    billability = (
        "not_billable" if not attempt_started else
        ("billable" if status == "success" else "unknown")
    )
    sink.ghi_attempt(
        req,
        provider=provider,
        model=model,
        key_hash=key_hash_value,
        attempt_started=attempt_started,
        status=status,
        http_status=http_status,
        latency_s=max(0.0, time.time() - t0) if attempt_started else 0.0,
        error_class=type(error).__name__ if error is not None else None,
        billability=billability,
        provider_retry_ordinal=provider_retry_ordinal,
        route_ordinal=route_ordinal,
        tool_turn_ordinal=tool_turn_ordinal,
        source=source,
        quota_claim_id=quota_claim_id,
    )


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


@dataclass(frozen=True)
class Route:
    provider: str  # "aistudio" | "ninerouter"
    model: str
    rpm: int
    rpd: int
    # Effective TPM after quotas.chung.safety_margin. None is a deliberate
    # fail-closed route, not an invitation to guess a provider limit.
    tpm: int | None = None
    tpm_policy: str = "unverified"

    @property
    def co_tpm_da_xac_minh(self) -> bool:
        return self.tpm is not None and self.tpm > 0 and (
            self.provider != "ninerouter" or self.tpm_policy == "verified"
        )


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
        self.attempt_log = None

    def goi(self, req: LLMRequest, model: str, temperature: float,
            max_tokens: int, key: str | None = None, *,
            nhan_slot: Callable[[int, int], QuotaClaim | None], physical_request: Callable[[], object],
            chot_slot_thanh_cong: Callable[[QuotaClaim, int], None],
            huy_slot: Callable[[QuotaClaim], None],
            huy_slot_truoc_khi_gui: Callable[[QuotaClaim], None],
            ghi_429: Callable[[str], None], provider_retry_ordinal: int = 0,
            route_ordinal: int = 0) -> LLMResponse:
        now = time.time()
        if key is None:
            key = self.pool.lay_key(now)
        if key is None:
            raise LoiHetQuota("aistudio: mọi key đang cooldown")
        t0 = time.time()
        kh = key_hash(key)
        payload = {
            "contents": [{"parts": [{"text": req.prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        body = _json_utf8_chinh_xac(payload)
        claim: QuotaClaim | None = None
        try:
            # Admission and the semaphore sit immediately next to ``post``.  The
            # tick slot is consumed only after all provider quotas accept this
            # exact body; a local denial then rolls the claim back before HTTP.
            with physical_request():
                claim = nhan_slot(len(body), max_tokens)
                if claim is None:
                    exc = LoiHetSlot(kh)
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="aistudio", model=model,
                        key_hash_value=kh, attempt_started=False, status="quota_denied", t0=t0,
                        error=exc, provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal,
                    )
                    raise exc
                try:
                    _bat_dau_request_thuc(req)
                except LoiVuotNganSachTick as exc:
                    huy_slot_truoc_khi_gui(claim)
                    claim = None
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="aistudio", model=model,
                        key_hash_value=kh, attempt_started=False, status="budget_denied", t0=t0,
                        error=exc, provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal,
                    )
                    exc.attempt_accounted = True
                    raise
                r = self.client.post(
                    f"{self.base}/v1beta/models/{model}:generateContent",
                    params={"key": key}, headers={"Content-Type": "application/json"}, content=body,
                )
        except httpx.HTTPError as exc:
            _ghi_http_attempt(
                self.attempt_log, req, provider="aistudio", model=model,
                key_hash_value=kh, attempt_started=True, status="network_error", t0=t0,
                error=exc, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal,
                quota_claim_id=claim.claim_id if claim is not None else None,
            )
            if claim is not None:
                huy_slot(claim)
            raise
        if r.status_code == 429:
            self.pool.bao_429(key, time.time())
            ghi_429(kh)
            exc = LoiRateLimit(kh)
            _ghi_http_attempt(
                self.attempt_log, req, provider="aistudio", model=model,
                key_hash_value=kh, attempt_started=True, status="rate_limited", t0=t0,
                http_status=429, error=exc, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal,
                quota_claim_id=claim.claim_id if claim is not None else None,
            )
            if claim is not None:
                huy_slot(claim)
            raise exc  # exception CHỈ mang hash, không mang key
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as raw_exc:
            exc = httpx.HTTPError(che_key(str(raw_exc)))
            _ghi_http_attempt(
                self.attempt_log, req, provider="aistudio", model=model,
                key_hash_value=kh, attempt_started=True, status="http_error", t0=t0,
                http_status=r.status_code, error=raw_exc,
                provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
                quota_claim_id=claim.claim_id if claim is not None else None,
            )
            if claim is not None:
                huy_slot(claim)
            raise exc from None
        self.pool.bao_ok(key)
        try:
            d = r.json()
            text = "".join(
                p.get("text", "")
                for c in d.get("candidates", [])
                for p in c.get("content", {}).get("parts", [])
            )
            usage = d.get("usageMetadata", {})
            tok_in = int(usage.get("promptTokenCount", 0))
            tok_out = int(usage.get("candidatesTokenCount", 0))
            total_tokens = _tong_token_provider(
                usage, input_key="promptTokenCount", output_key="candidatesTokenCount",
                total_key="totalTokenCount",
            )
        except (KeyError, ValueError, IndexError, TypeError, AttributeError) as exc:
            _ghi_http_attempt(
                self.attempt_log, req, provider="aistudio", model=model,
                key_hash_value=kh, attempt_started=True, status="response_parse_error", t0=t0,
                http_status=r.status_code, error=exc,
                provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
                quota_claim_id=claim.claim_id if claim is not None else None,
            )
            if claim is not None:
                huy_slot(claim)
            raise
        if claim is None:
            raise RuntimeError("missing quota claim after started request")
        chot_slot_thanh_cong(claim, total_tokens)
        _ghi_http_attempt(
            self.attempt_log, req, provider="aistudio", model=model,
            key_hash_value=kh, attempt_started=True, status="success", t0=t0,
            http_status=r.status_code, provider_retry_ordinal=provider_retry_ordinal,
            route_ordinal=route_ordinal, quota_claim_id=claim.claim_id,
        )
        return LLMResponse(
            text=text, provider="aistudio", model=model,
            tok_in=tok_in, tok_out=tok_out,
            latency_s=time.time() - t0, key_hash=kh, quota_claim_id=claim.claim_id,
        )

    def goi_agentic(self, req: LLMRequest, model: str, temperature: float,
                    max_tokens: int, w, aid: str, khai_bao: list, thuc_thi,
                    max_luot: int, chon_key, xong_key, *,
                    nhan_slot: Callable[[str, int, int], QuotaClaim | None],
                    physical_request: Callable[[], object],
                    chot_slot_thanh_cong: Callable[[QuotaClaim, int], None],
                    huy_slot: Callable[[QuotaClaim], None],
                    huy_slot_truoc_khi_gui: Callable[[QuotaClaim], None],
                    ghi_429: Callable[[str], None],
                    provider_retry_ordinal: int = 0, route_ordinal: int = 0) -> LLMResponse:
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
            kh = key_hash(key)
            attempt_t0 = time.time()
            # ``chon_key`` only reserves a local in-flight selection.  The tick
            # budget is consumed after durable provider admission, then the exact
            # claim is rolled back if this local gate denies before HTTP.
            claim: QuotaClaim | None = None
            try:
                cfg = {"temperature": temperature, "maxOutputTokens": max_tokens}
                body: dict = {"contents": contents, "generationConfig": cfg}
                if luot < max_luot:
                    body["tools"] = tools
                else:
                    cfg["responseMimeType"] = "application/json"  # lượt cuối: ép JSON quyết
                wire_body = _json_utf8_chinh_xac(body)
                try:
                    with physical_request():
                        claim = nhan_slot(key, len(wire_body), max_tokens)
                        if claim is None:
                            exc = LoiHetSlot(kh)
                            _ghi_http_attempt(
                                self.attempt_log, req, provider="aistudio", model=model,
                                key_hash_value=kh, attempt_started=False, status="quota_denied",
                                t0=attempt_t0, error=exc,
                                provider_retry_ordinal=provider_retry_ordinal,
                                route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                            )
                            raise exc
                        try:
                            _bat_dau_request_thuc(req)
                        except LoiVuotNganSachTick as exc:
                            huy_slot_truoc_khi_gui(claim)
                            claim = None
                            _ghi_http_attempt(
                                self.attempt_log, req, provider="aistudio", model=model,
                                key_hash_value=kh, attempt_started=False, status="budget_denied",
                                t0=attempt_t0, error=exc,
                                provider_retry_ordinal=provider_retry_ordinal,
                                route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                            )
                            exc.attempt_accounted = True
                            exc.tool_turns = list(tool_turns)
                            exc.tool_catalog_hash = tool_catalog
                            raise
                        r = self.client.post(
                            f"{self.base}/v1beta/models/{model}:generateContent",
                            params={"key": key}, headers={"Content-Type": "application/json"},
                            content=wire_body,
                        )
                except httpx.HTTPError as exc:
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="aistudio", model=model,
                        key_hash_value=kh, attempt_started=True, status="network_error",
                        t0=attempt_t0, error=exc,
                        provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                        quota_claim_id=claim.claim_id if claim is not None else None,
                    )
                    if claim is not None:
                        huy_slot(claim)
                    raise
                if r.status_code == 429:
                    self.pool.bao_429(key, time.time())
                    ghi_429(kh)
                    exc = LoiRateLimit(kh)
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="aistudio", model=model,
                        key_hash_value=kh, attempt_started=True, status="rate_limited",
                        t0=attempt_t0, http_status=429, error=exc,
                        provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                        quota_claim_id=claim.claim_id if claim is not None else None,
                    )
                    if claim is not None:
                        huy_slot(claim)
                    raise exc
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as raw_exc:
                    exc = httpx.HTTPError(che_key(str(raw_exc)))
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="aistudio", model=model,
                        key_hash_value=kh, attempt_started=True, status="http_error",
                        t0=attempt_t0, http_status=r.status_code, error=raw_exc,
                        provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                        quota_claim_id=claim.claim_id if claim is not None else None,
                    )
                    if claim is not None:
                        huy_slot(claim)
                    raise exc from None
                self.pool.bao_ok(key)
            finally:
                xong_key(key, False)  # chỉ trả in-flight; settlement claim làm riêng, exact-once
            try:
                d = r.json()
                usage = d.get("usageMetadata", {})
            except (KeyError, ValueError, IndexError, TypeError) as exc:
                _ghi_http_attempt(
                    self.attempt_log, req, provider="aistudio", model=model,
                    key_hash_value=kh, attempt_started=True, status="response_parse_error",
                    t0=attempt_t0, http_status=r.status_code, error=exc,
                    provider_retry_ordinal=provider_retry_ordinal,
                    route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                    quota_claim_id=claim.claim_id if claim is not None else None,
                )
                if claim is not None:
                    huy_slot(claim)
                raise
            try:
                usage_in = int(usage.get("promptTokenCount", 0))
                usage_out = int(usage.get("candidatesTokenCount", 0))
                total_tokens = _tong_token_provider(
                    usage, input_key="promptTokenCount", output_key="candidatesTokenCount",
                    total_key="totalTokenCount",
                )
            except (ValueError, TypeError, AttributeError) as exc:
                _ghi_http_attempt(
                    self.attempt_log, req, provider="aistudio", model=model,
                    key_hash_value=kh, attempt_started=True, status="response_parse_error",
                    t0=attempt_t0, http_status=r.status_code, error=exc,
                    provider_retry_ordinal=provider_retry_ordinal,
                    route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                    quota_claim_id=claim.claim_id if claim is not None else None,
                )
                if claim is not None:
                    huy_slot(claim)
                raise
            tok_in += usage_in
            tok_out += usage_out
            try:
                parts = (d.get("candidates", [{}])[0].get("content", {}).get("parts", []))
                goi_cong_cu = [p["functionCall"] for p in parts if "functionCall" in p]
            except (KeyError, ValueError, IndexError, TypeError) as exc:
                _ghi_http_attempt(
                    self.attempt_log, req, provider="aistudio", model=model,
                    key_hash_value=kh, attempt_started=True, status="response_parse_error",
                    t0=attempt_t0, http_status=r.status_code, error=exc,
                    provider_retry_ordinal=provider_retry_ordinal,
                    route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                    quota_claim_id=claim.claim_id if claim is not None else None,
                )
                if claim is not None:
                    huy_slot(claim)
                raise
            if claim is None:
                raise RuntimeError("missing quota claim after started request")
            chot_slot_thanh_cong(claim, total_tokens)
            _ghi_http_attempt(
                self.attempt_log, req, provider="aistudio", model=model,
                key_hash_value=kh, attempt_started=True, status="success", t0=attempt_t0,
                http_status=r.status_code, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                source="tool_turn" if goi_cong_cu else "decision_final",
                quota_claim_id=claim.claim_id,
            )
            if not goi_cong_cu:
                text = "".join(p.get("text", "") for p in parts)
                return LLMResponse(
                    text=text, provider="aistudio", model=model, tok_in=tok_in,
                    tok_out=tok_out, latency_s=time.time() - t0,
                    key_hash=key_hash(key), quota_claim_id=claim.claim_id, retries=luot,
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
        self.attempt_log = None

    def _post(
        self, req: LLMRequest, model: str, payload: dict, *,
        nhan_slot: Callable[[int, int], QuotaClaim | None],
        physical_request: Callable[[], object],
        chot_slot_thanh_cong: Callable[[QuotaClaim, int], None],
        huy_slot: Callable[[QuotaClaim], None],
        huy_slot_truoc_khi_gui: Callable[[QuotaClaim], None],
        ghi_429: Callable[[str], None],
        provider_retry_ordinal: int, route_ordinal: int, tool_turn_ordinal: int | None,
        source: str | None = None,
    ) -> tuple[dict, QuotaClaim]:
        """Send one exact serialized body under one physical quota claim."""
        kh = key_hash(self.key)
        t0 = time.time()
        wire_body = _json_utf8_chinh_xac(payload)
        claim: QuotaClaim | None = None
        try:
            with physical_request():
                claim = nhan_slot(len(wire_body), int(payload.get("max_tokens", 0)))
                if claim is None:
                    exc = LoiHetSlot(kh)
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="ninerouter", model=model,
                        key_hash_value=kh, attempt_started=False, status="quota_denied", t0=t0,
                        error=exc, provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal, tool_turn_ordinal=tool_turn_ordinal, source=source,
                    )
                    raise exc
                try:
                    _bat_dau_request_thuc(req)
                except LoiVuotNganSachTick as exc:
                    huy_slot_truoc_khi_gui(claim)
                    claim = None
                    _ghi_http_attempt(
                        self.attempt_log, req, provider="ninerouter", model=model,
                        key_hash_value=kh, attempt_started=False, status="budget_denied", t0=t0,
                        error=exc, provider_retry_ordinal=provider_retry_ordinal,
                        route_ordinal=route_ordinal, tool_turn_ordinal=tool_turn_ordinal,
                        source=source,
                    )
                    exc.attempt_accounted = True
                    raise
                response = self.client.post(
                    f"{self.base}/chat/completions",
                    headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
                    content=wire_body,
                )
        except httpx.HTTPError as exc:
            _ghi_http_attempt(
                self.attempt_log, req, provider="ninerouter", model=model,
                key_hash_value=kh, attempt_started=True, status="network_error", t0=t0,
                error=exc, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal, tool_turn_ordinal=tool_turn_ordinal, source=source,
                quota_claim_id=claim.claim_id if claim else None,
            )
            if claim is not None:
                huy_slot(claim)
            raise
        if response.status_code == 429:
            ghi_429(kh)
            exc = LoiRateLimit(kh)
            _ghi_http_attempt(
                self.attempt_log, req, provider="ninerouter", model=model,
                key_hash_value=kh, attempt_started=True, status="rate_limited", t0=t0,
                http_status=429, error=exc, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal, tool_turn_ordinal=tool_turn_ordinal, source=source,
                quota_claim_id=claim.claim_id if claim else None,
            )
            if claim is not None:
                huy_slot(claim)
            raise exc
        try:
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage", {})
            total_tokens = _tong_token_provider(
                usage, input_key="prompt_tokens", output_key="completion_tokens", total_key="total_tokens"
            )
        except (httpx.HTTPStatusError, KeyError, ValueError, IndexError, TypeError, AttributeError) as exc:
            status = "http_error" if isinstance(exc, httpx.HTTPStatusError) else "response_parse_error"
            safe_exc = httpx.HTTPError(che_key(str(exc))) if status == "http_error" else exc
            _ghi_http_attempt(
                self.attempt_log, req, provider="ninerouter", model=model,
                key_hash_value=kh, attempt_started=True, status=status, t0=t0,
                http_status=response.status_code, error=exc,
                provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
                tool_turn_ordinal=tool_turn_ordinal, source=source,
                quota_claim_id=claim.claim_id if claim else None,
            )
            if claim is not None:
                huy_slot(claim)
            if status == "http_error":
                raise safe_exc from None
            raise
        if claim is None:
            raise RuntimeError("missing quota claim after started request")
        chot_slot_thanh_cong(claim, total_tokens)
        return data, claim

    def goi(self, req: LLMRequest, model: str, temperature: float,
            max_tokens: int, *, nhan_slot: Callable[[int, int], QuotaClaim | None],
            physical_request: Callable[[], object],
            chot_slot_thanh_cong: Callable[[QuotaClaim, int], None],
            huy_slot: Callable[[QuotaClaim], None],
            huy_slot_truoc_khi_gui: Callable[[QuotaClaim], None],
            ghi_429: Callable[[str], None],
            provider_retry_ordinal: int = 0, route_ordinal: int = 0) -> LLMResponse:
        t0 = time.time()
        payload = {
            "model": model, "messages": [{"role": "user", "content": req.prompt}],
            "temperature": temperature, "max_tokens": max_tokens, "stream": False,
            "response_format": {"type": "json_object"},
        }
        data, claim = self._post(
            req, model, payload, nhan_slot=nhan_slot, physical_request=physical_request,
            chot_slot_thanh_cong=chot_slot_thanh_cong, huy_slot=huy_slot,
            huy_slot_truoc_khi_gui=huy_slot_truoc_khi_gui, ghi_429=ghi_429,
            provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
            tool_turn_ordinal=None,
        )
        try:
            text = data["choices"][0]["message"]["content"]
            usage = data["usage"]
            tok_in = int(usage["prompt_tokens"])
            tok_out = int(usage["completion_tokens"])
        except (KeyError, ValueError, IndexError, TypeError, AttributeError) as exc:
            _ghi_http_attempt(
                self.attempt_log, req, provider="ninerouter", model=model,
                key_hash_value=key_hash(self.key), attempt_started=True, status="response_parse_error",
                t0=t0, http_status=200, error=exc, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal, quota_claim_id=claim.claim_id,
            )
            raise
        _ghi_http_attempt(
            self.attempt_log, req, provider="ninerouter", model=model,
            key_hash_value=key_hash(self.key), attempt_started=True, status="success", t0=t0,
            http_status=200, provider_retry_ordinal=provider_retry_ordinal,
            route_ordinal=route_ordinal, quota_claim_id=claim.claim_id,
        )
        return LLMResponse(text=text, provider="ninerouter", model=model, tok_in=tok_in,
                           tok_out=tok_out, latency_s=time.time() - t0, key_hash=key_hash(self.key),
                           quota_claim_id=claim.claim_id)

    def goi_agentic(self, req: LLMRequest, model: str, temperature: float,
                    max_tokens: int, w, aid: str, khai_bao: list, thuc_thi,
                    max_luot: int, *, nhan_slot: Callable[[int, int], QuotaClaim | None],
                    physical_request: Callable[[], object],
                    chot_slot_thanh_cong: Callable[[QuotaClaim, int], None],
                    huy_slot: Callable[[QuotaClaim], None],
                    huy_slot_truoc_khi_gui: Callable[[QuotaClaim], None],
                    ghi_429: Callable[[str], None],
                    provider_retry_ordinal: int = 0, route_ordinal: int = 0) -> LLMResponse:
        t0 = time.time()
        tools = [{"type": "function", "function": kb} for kb in khai_bao]
        messages: list[dict] = [{"role": "user", "content": req.prompt}]
        tok_in = tok_out = 0
        from minds.world_tools import catalog_hash, result_hash

        tool_turns: list[dict] = []
        tool_catalog = catalog_hash()
        for luot in range(max_luot + 1):
            payload: dict = {"model": model, "messages": messages, "temperature": temperature,
                             "max_tokens": max_tokens, "stream": False}
            if luot < max_luot:
                payload["tools"] = tools
            else:
                payload["response_format"] = {"type": "json_object"}
            data, claim = self._post(
                req, model, payload, nhan_slot=nhan_slot, physical_request=physical_request,
                chot_slot_thanh_cong=chot_slot_thanh_cong, huy_slot=huy_slot,
                huy_slot_truoc_khi_gui=huy_slot_truoc_khi_gui, ghi_429=ghi_429,
                provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
                tool_turn_ordinal=luot, source="tool_turn" if luot < max_luot else "decision_final",
            )
            try:
                usage = data["usage"]
                tok_in += int(usage["prompt_tokens"])
                tok_out += int(usage["completion_tokens"])
                msg = data["choices"][0]["message"]
            except (KeyError, ValueError, IndexError, TypeError) as exc:
                _ghi_http_attempt(
                    self.attempt_log, req, provider="ninerouter", model=model,
                    key_hash_value=key_hash(self.key), attempt_started=True, status="response_parse_error",
                    t0=t0, http_status=200, error=exc,
                    provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
                    tool_turn_ordinal=luot, quota_claim_id=claim.claim_id,
                )
                raise
            goi_cc = msg.get("tool_calls") or []
            _ghi_http_attempt(
                self.attempt_log, req, provider="ninerouter", model=model,
                key_hash_value=key_hash(self.key), attempt_started=True, status="success", t0=t0,
                http_status=200, provider_retry_ordinal=provider_retry_ordinal,
                route_ordinal=route_ordinal, tool_turn_ordinal=luot,
                source="tool_turn" if goi_cc else "decision_final", quota_claim_id=claim.claim_id,
            )
            if not goi_cc:
                return LLMResponse(
                    text=msg.get("content") or "", provider="ninerouter", model=model,
                    tok_in=tok_in, tok_out=tok_out, latency_s=time.time() - t0,
                    key_hash=key_hash(self.key), quota_claim_id=claim.claim_id, retries=luot,
                    tool_turns=tool_turns, tool_catalog_hash=tool_catalog,
                )
            messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": goi_cc})
            for index, tc in enumerate(goi_cc):
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (ValueError, TypeError):
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                name = str(fn.get("name", ""))
                result = thuc_thi(w, aid, name, args)
                tool_turns.append({"turn": int(luot), "index": int(index), "name": name,
                                   "args": args, "result": result, "result_hash": result_hash(result)})
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                                 "content": json.dumps(result, ensure_ascii=False)})
        return LLMResponse(text="{}", provider="ninerouter", model=model, tok_in=tok_in,
                           tok_out=tok_out, latency_s=time.time() - t0, key_hash=key_hash(self.key),
                           tool_turns=tool_turns, tool_catalog_hash=tool_catalog)


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
                 transport: httpx.BaseTransport | None = None, retry_toi_da: int = 2,
                 attempt_log=None):
        self.cfg = cfg
        self.quota = quota
        self.retry_toi_da = retry_toi_da
        self.attempt_log = attempt_log
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
        # ``minds.concurrency`` limits fan-out work, but the contractual quota
        # setting below limits the physical provider requests themselves.  This
        # matters for retries/tool turns and for several concurrent callers.
        quotas_raw = cfg.raw().get("quotas", {})
        self._provider_gates: dict[str, threading.BoundedSemaphore] = {}
        self.provider_concurrency: dict[str, int] = {}
        for provider in ("aistudio", "ninerouter"):
            limit = int(quotas_raw.get(provider, {}).get("concurrency", 1))
            if limit < 1:
                raise ValueError(f"quotas.{provider}.concurrency phải >= 1")
            self.provider_concurrency[provider] = limit
            self._provider_gates[provider] = threading.BoundedSemaphore(limit)
        self.dat_attempt_log(attempt_log)

    def dat_attempt_log(self, attempt_log) -> None:
        """Attach the append-only attempt sink; safe to call again after resume/rebase."""
        self.attempt_log = attempt_log
        self.aistudio.attempt_log = attempt_log
        self.ninerouter.attempt_log = attempt_log

    @contextmanager
    def _physical_request(self, provider: str):
        """Apply configured provider concurrency immediately around one HTTP ``post``."""
        gate = self._provider_gates[provider]
        gate.acquire()
        try:
            yield
        finally:
            gate.release()

    def _nhan_slot_bat_dau(self, route: Route, kh: str, payload_utf8_bytes: int,
                            max_output_tokens: int) -> QuotaClaim | None:
        """Atomically admit RPM/TPM/RPD immediately before one HTTP body leaves."""
        if not route.co_tpm_da_xac_minh:
            return None
        overhead = self._so_nguyen_cau_hinh(
            self.cfg.get("quotas.chung.token_admission.fixed_overhead_tokens"),
            "quotas.chung.token_admission.fixed_overhead_tokens", cho_phep_zero=True,
        )
        return self.quota.nhan_claim_bat_dau(
            route.provider, route.model, kh, rpm=route.rpm, tpm=int(route.tpm or 0),
            rpd=route.rpd, reserved_tokens=(int(payload_utf8_bytes) + overhead
                                             + self._so_nguyen_cau_hinh(
                                                 max_output_tokens, "max_output_tokens",
                                                 cho_phep_zero=True,
                                             )),
            now=time.time(),
        )

    def _ghi_429_ben_vung(self, route: Route, kh: str) -> None:
        retry = self.cfg.get("quotas.retry")
        self.quota.ghi_429(
            route.provider, kh, time.time(),
            float(retry["cooldown_429_s"]), float(retry["cooldown_toi_da_s"]),
        )

    def _chot_slot_thanh_cong(self, claim: QuotaClaim, provider_total_tokens: int) -> None:
        self.quota.chot_claim(claim, provider_total_tokens)

    def _huy_slot(self, claim: QuotaClaim) -> None:
        """A started request with unknown provider billing remains conservatively claimed."""
        self.quota.giu_claim_khong_ro(claim)

    def _huy_slot_truoc_khi_gui(self, claim: QuotaClaim) -> None:
        """Release a claim rejected locally before its HTTP request starts."""
        self.quota.huy_claim_truoc_khi_gui(claim)

    def ghi_budget_denied_before_start(self, req: LLMRequest) -> None:
        """Account an orchestrator-level denial where no provider route was entered."""
        routes = self.routes_cua_tier(req.tier)
        route = routes[0] if routes else Route("unavailable", "", 0, 0)
        hashes = self._key_hashes(route.provider) if routes else [""]
        _ghi_http_attempt(
            self.attempt_log, req, provider=route.provider, model=route.model,
            key_hash_value=hashes[0] if hashes else "", attempt_started=False,
            status="budget_denied", t0=time.time(),
        )

    def _ghi_route_tpm_chua_xac_minh(
        self, req: LLMRequest, route: Route, *, provider_retry_ordinal: int,
        route_ordinal: int,
    ) -> None:
        """Journal a fail-closed route before a later configured route is considered.

        A route without a verified TPM limit never obtains a claim or emits HTTP.
        Recording the denial makes a configured fallback auditable rather than a
        silent change of real-provider route.
        """
        hashes = self._key_hashes(route.provider)
        exc = LoiHetSlot(f"{route.provider}/{route.model}: TPM policy chưa xác minh")
        _ghi_http_attempt(
            self.attempt_log, req, provider=route.provider, model=route.model,
            key_hash_value=hashes[0] if hashes else "", attempt_started=False,
            status="quota_denied", t0=time.time(), error=exc,
            provider_retry_ordinal=provider_retry_ordinal, route_ordinal=route_ordinal,
        )

    # ---------- cấu hình route ----------
    @staticmethod
    def _so_nguyen_cau_hinh(value: object, path: str, *, cho_phep_zero: bool = False) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{path} phải là số nguyên")
        try:
            parsed = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{path} phải là số nguyên") from exc
        if parsed < 0 or (parsed == 0 and not cho_phep_zero):
            raise ValueError(f"{path} phải {'không âm' if cho_phep_zero else 'dương'}")
        return parsed

    def route_cau_hinh(self, provider: str, model: str) -> Route:
        """Validate published quota policy then derive its one-time effective margin."""
        if provider not in {"aistudio", "ninerouter"}:
            raise ValueError(f"provider không hỗ trợ: {provider}")
        raw = self.cfg.raw().get("quotas", {}).get(provider, {}).get("models", {}).get(model)
        if not isinstance(raw, dict):
            raise ValueError(f"route không có quota khai báo: {provider}/{model}")
        rpm = self._so_nguyen_cau_hinh(raw.get("rpm"), f"quota {provider}/{model}.rpm")
        rpd = self._so_nguyen_cau_hinh(raw.get("rpd"), f"quota {provider}/{model}.rpd")
        policy = str(raw.get("tpm_policy", "unverified"))
        raw_tpm = raw.get("tpm")
        if provider == "ninerouter" and policy != "verified":
            return Route(provider, model, rpm, rpd, None, policy)
        if policy not in {"published", "verified"}:
            raise ValueError(f"quota {provider}/{model}.tpm_policy không hợp lệ: {policy}")
        tpm = self._so_nguyen_cau_hinh(raw_tpm, f"quota {provider}/{model}.tpm")
        margin = float(self.cfg.get("quotas.chung.safety_margin"))
        if not 0.0 < margin <= 1.0:
            raise ValueError("quotas.chung.safety_margin phải thuộc (0,1]")
        return Route(
            provider, model, max(1, math.floor(rpm * margin)),
            max(1, math.floor(rpd * margin)), max(1, math.floor(tpm * margin)), policy,
        )

    def routes_cua_tier(self, tier: str) -> list[Route]:
        if self.strict_treatment:
            route = self.route_cau_hinh(
                str(self.strict_treatment_cfg["provider"]), str(self.strict_treatment_cfg["model"])
            )
            if not route.co_tpm_da_xac_minh:
                raise ValueError(
                    f"route treatment không có TPM policy đã xác minh: {route.provider}/{route.model}"
                )
            return [route]
        routes = []
        for r in self.cfg.get(f"models.tiers.{tier}.routes"):
            routes.append(self.route_cau_hinh(str(r["provider"]), str(r["model"])))
        return routes

    def _key_hashes(self, provider: str) -> list[str]:
        if provider == "aistudio":
            return [key_hash(k) for k in self._env.gemini_keys]
        return [key_hash(self._env.nine_key)]

    def con_lai(self, route: Route, now: float) -> int:
        if not route.co_tpm_da_xac_minh:
            return 0
        return self.quota.con_lai_rpd(route.provider, route.model,
                                      self._key_hashes(route.provider), route.rpd, now)

    def du_tru_token_toi_thieu(self, route: Route, prompt: str, max_output_tokens: int,
                                *, co_cong_cu: bool = False) -> int:
        """Conservative TPM reservation for an exact first-turn payload.

        This mirrors the wire serializers used by both providers.  It is used
        only for preflight; actual admission serializes again immediately before
        HTTP and remains the atomic source of truth.
        """
        max_output = self._so_nguyen_cau_hinh(
            max_output_tokens, "max_output_tokens", cho_phep_zero=True
        )
        if route.provider == "aistudio":
            payload: dict[str, object] = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": max_output},
            }
            if co_cong_cu:
                from minds.world_tools import KHAI_BAO_CONG_CU

                payload["tools"] = [{"functionDeclarations": KHAI_BAO_CONG_CU}]
            else:
                payload["generationConfig"]["responseMimeType"] = "application/json"  # type: ignore[index]
        else:
            payload = {
                "model": route.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": max_output,
                "stream": False,
            }
            if co_cong_cu:
                from minds.world_tools import KHAI_BAO_CONG_CU

                payload["tools"] = [{"type": "function", "function": item}
                                    for item in KHAI_BAO_CONG_CU]
            else:
                payload["response_format"] = {"type": "json_object"}
        overhead = self._so_nguyen_cau_hinh(
            self.cfg.get("quotas.chung.token_admission.fixed_overhead_tokens"),
            "quotas.chung.token_admission.fixed_overhead_tokens", cho_phep_zero=True,
        )
        return len(_json_utf8_chinh_xac(payload)) + overhead + max_output

    def tpm_con_lai(self, route: Route, now: float) -> int:
        """Total verified TPM headroom across usable credentials on this route."""
        if not route.co_tpm_da_xac_minh:
            return 0
        headroom = 0
        for kh in self._key_hashes(route.provider):
            if self.quota.dang_cooldown(route.provider, kh, now):
                continue
            headroom += max(0, int(route.tpm or 0) - self.quota.tpm_hien_tai(
                route.provider, route.model, kh, now
            ))
        return int(headroom)

    def kha_nang_burst(self, route: Route, now: float,
                        *, du_tru_token_moi_request: int = 0) -> int:
        """Số request có thể BẮT ĐẦU ngay trong cửa sổ RPM hiện tại.

        Đây không phải dự báo RPD cả ngày.  Nó là headroom tức thời dùng bởi
        treatment coverage đầy đủ để quyết định trước tick liệu tất cả cư dân
        có thể nhận lượt suy nghĩ bắt buộc hay không.  Cooldown, RPD đã dùng
        và request đang bay đều trừ trực tiếp khỏi năng lực này.
        """
        if not route.co_tpm_da_xac_minh:
            return 0
        if route.provider == "aistudio":
            cong_suat = 0
            for key in self.pool_aistudio.key_kha_dung(now):
                kh = key_hash(key)
                if self.quota.dang_cooldown(route.provider, kh, now):
                    continue
                rpm_con = route.rpm - self.quota.rpm_hien_tai(
                    route.provider, route.model, kh, now
                ) - self._dang_bay.get(kh, 0)
                rpd_con = route.rpd - self.quota.rpd_da_dung(
                    route.provider, route.model, kh, now
                ) - self.quota.rpd_da_du_tru(route.provider, route.model, kh, now)
                tpm_con = max(0, int(route.tpm or 0) - self.quota.tpm_hien_tai(
                    route.provider, route.model, kh, now
                ))
                tpm_request = (tpm_con if du_tru_token_moi_request <= 0
                               else tpm_con // du_tru_token_moi_request)
                cong_suat += max(0, min(rpm_con, rpd_con, tpm_request))
            return int(cong_suat)

        # A missing/placeholder 9router key is not capacity.  Treating it as
        # a usable route would turn a clean preflight failure into a later
        # HTTP failure after some residents have already been processed.
        key = str(self._env.nine_key or "")
        if not key or key.startswith("dien_key"):
            return 0
        kh = key_hash(key)
        if self.quota.dang_cooldown(route.provider, kh, now):
            return 0
        rpm_con = route.rpm - self.quota.rpm_hien_tai(
            route.provider, route.model, kh, now
        ) - self._dang_bay.get(kh, 0)
        rpd_con = route.rpd - self.quota.rpd_da_dung(
            route.provider, route.model, kh, now
        ) - self.quota.rpd_da_du_tru(route.provider, route.model, kh, now)
        tpm_con = max(0, int(route.tpm or 0) - self.quota.tpm_hien_tai(
            route.provider, route.model, kh, now
        ))
        tpm_request = (tpm_con if du_tru_token_moi_request <= 0
                       else tpm_con // du_tru_token_moi_request)
        return int(max(0, min(rpm_con, rpd_con, tpm_request)))

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
        for route_ordinal, route in enumerate(self.routes_cua_tier(req.tier)):
            now = time.time()
            if not route.co_tpm_da_xac_minh:
                self._ghi_route_tpm_chua_xac_minh(
                    req, route, provider_retry_ordinal=so_attempt_hong,
                    route_ordinal=route_ordinal,
                )
                loi_cuoi = LoiHetSlot(
                    f"{route.provider}/{route.model}: TPM policy chưa xác minh"
                )
                continue
            if self.con_lai(route, now) <= 0:
                continue  # route cạn RPD → tràn route sau
            co_route_con_rpd = True
            for _ in range(self.retry_toi_da + 1):
                try:
                    resp = self._goi_route(
                        req, route, tier_cfg,
                        provider_retry_ordinal=so_attempt_hong,
                        route_ordinal=route_ordinal,
                    )
                    resp.retries = so_attempt_hong  # legacy alias
                    resp.provider_retries = so_attempt_hong
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
        for route_ordinal, route in enumerate(self.routes_cua_tier(req.tier)):
            # Re-evaluate after a failed route too: a failed HTTP attempt has
            # already consumed this resident's budget, so the next route may
            # only have room for a direct final JSON answer.
            max_luot = _luot_tool_huu_dung(req, max_luot_cau_hinh)
            now = time.time()
            if not route.co_tpm_da_xac_minh:
                self._ghi_route_tpm_chua_xac_minh(
                    req, route, provider_retry_ordinal=so_attempt_hong,
                    route_ordinal=route_ordinal,
                )
                loi_cuoi = LoiHetSlot(
                    f"{route.provider}/{route.model}: TPM policy chưa xác minh"
                )
                continue
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
                            nhan_slot=lambda body_bytes, out_cap, _route=route, _kh=kh: self._nhan_slot_bat_dau(
                                _route, _kh, body_bytes, out_cap
                            ),
                            physical_request=lambda _route=route: self._physical_request(
                                _route.provider
                            ),
                            chot_slot_thanh_cong=lambda claim, total: self._chot_slot_thanh_cong(
                                claim, total
                            ),
                            huy_slot=lambda claim: self._huy_slot(claim),
                            huy_slot_truoc_khi_gui=lambda claim: self._huy_slot_truoc_khi_gui(claim),
                            ghi_429=lambda key_hash_value, _route=route: self._ghi_429_ben_vung(
                                _route, key_hash_value
                            ),
                            provider_retry_ordinal=so_attempt_hong,
                            route_ordinal=route_ordinal,
                        )
                        resp.provider_retries = so_attempt_hong
                        return resp
                    except (LoiRateLimit, *self._LOI_PHAN_HOI) as e:
                        loi_cuoi = e
                        so_attempt_hong += 1
                continue
            # Mỗi lượt giữ chỗ key đến khi HTTP hoàn tất.  RPD được settle riêng
            # sau khi response đã parse hợp lệ, không trong callback giải phóng key.
            def _chon(_route=route):
                return self._chon_key_aistudio(_route, time.time())

            def _xong(key: str, thanh_cong: bool):
                _ = thanh_cong
                self._giai_phong(key)
            try:
                resp = self.aistudio.goi_agentic(
                    req, route.model, temperature, max_tokens, w, aid,
                    KHAI_BAO_CONG_CU, thuc_thi, max_luot, chon_key=_chon, xong_key=_xong,
                    nhan_slot=lambda key, body_bytes, out_cap, _route=route: self._nhan_slot_bat_dau(
                        _route, key_hash(key), body_bytes, out_cap
                    ),
                    physical_request=lambda _route=route: self._physical_request(
                        _route.provider
                    ),
                    chot_slot_thanh_cong=lambda claim, total: self._chot_slot_thanh_cong(
                        claim, total
                    ),
                    huy_slot=lambda claim: self._huy_slot(claim),
                    huy_slot_truoc_khi_gui=lambda claim: self._huy_slot_truoc_khi_gui(claim),
                    ghi_429=lambda key_hash_value, _route=route: self._ghi_429_ben_vung(
                        _route, key_hash_value
                    ),
                    provider_retry_ordinal=so_attempt_hong,
                    route_ordinal=route_ordinal,
                )
                resp.provider_retries = so_attempt_hong
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
                if self.quota.dang_cooldown(route.provider, kh, now):
                    continue
                da_rpd = (self.quota.rpd_da_dung(route.provider, route.model, kh, now)
                          + self.quota.rpd_da_du_tru(route.provider, route.model, kh, now))
                if da_rpd >= route.rpd:
                    continue  # cạn hoặc đã hứa hết RPD hôm nay
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

    def _goi_route(
        self,
        req: LLMRequest,
        route: Route,
        tier_cfg: dict,
        *,
        provider_retry_ordinal: int = 0,
        route_ordinal: int = 0,
    ) -> LLMResponse:
        now = time.time()
        sample_cfg = self.strict_treatment_cfg if self.strict_treatment else tier_cfg
        temperature = float(sample_cfg.get("temperature", tier_cfg.get("temperature", 0.9)))
        max_tokens = int(sample_cfg.get("max_output_tokens", tier_cfg.get("max_output_tokens", 2000)))
        if not route.co_tpm_da_xac_minh:
            raise LoiHetSlot(f"{route.provider}/{route.model}: TPM policy chưa xác minh")
        if route.provider == "aistudio":
            key = self._chon_key_aistudio(route, now)
            if key is None:  # mọi key cạn RPM/RPD/cooldown → TRÀN route sau (đừng retry)
                raise LoiHetSlot("aistudio-het-slot")
            try:
                return self.aistudio.goi(
                    req, route.model, temperature, max_tokens, key=key,
                    nhan_slot=lambda body_bytes, out_cap, _route=route, _key=key: self._nhan_slot_bat_dau(
                        _route, key_hash(_key), body_bytes, out_cap
                    ),
                    physical_request=lambda _route=route: self._physical_request(
                        _route.provider
                    ),
                    chot_slot_thanh_cong=lambda claim, total: self._chot_slot_thanh_cong(
                        claim, total
                    ),
                    huy_slot=lambda claim: self._huy_slot(claim),
                    huy_slot_truoc_khi_gui=lambda claim: self._huy_slot_truoc_khi_gui(claim),
                    ghi_429=lambda kh, _route=route: self._ghi_429_ben_vung(_route, kh),
                    provider_retry_ordinal=provider_retry_ordinal,
                    route_ordinal=route_ordinal,
                )
            finally:
                self._giai_phong(key)
        kh = key_hash(self._env.nine_key)
        if not self.quota.cho_phep(route.provider, route.model, kh,
                                   route.rpm, route.rpd, now):
            raise LoiHetSlot(kh)  # 9router cạn slot → tràn route sau
        return self.ninerouter.goi(
            req, route.model, temperature, max_tokens,
            nhan_slot=lambda body_bytes, out_cap, _route=route, _kh=kh: self._nhan_slot_bat_dau(
                _route, _kh, body_bytes, out_cap
            ),
            physical_request=lambda: self._physical_request(route.provider),
            chot_slot_thanh_cong=lambda claim, total: self._chot_slot_thanh_cong(claim, total),
            huy_slot=lambda claim: self._huy_slot(claim),
            huy_slot_truoc_khi_gui=lambda claim: self._huy_slot_truoc_khi_gui(claim),
            ghi_429=lambda key_hash_value, _route=route: self._ghi_429_ben_vung(
                _route, key_hash_value
            ),
            provider_retry_ordinal=provider_retry_ordinal,
            route_ordinal=route_ordinal,
        )


def _cohort_guard(
    gw: GatewayReal,
    can_theo_tier: dict[str, int],
    *,
    du_tru_token_theo_tier: dict[str, int] | None,
    burst: bool,
) -> tuple[bool, str]:
    """Allocate one mandatory cohort across shared routes without double-counting.

    A route's request capacity is bounded by RPD and conservative TPM reservation
    in both guards, plus RPM for the immediate-burst guard.  A shared fallback
    route is represented once in the max-flow graph, preventing a partial cohort
    when one tier has already consumed its TPM headroom.
    """
    nhu_cau = {str(tier): int(so) for tier, so in can_theo_tier.items() if int(so) > 0}
    if not nhu_cau:
        return True, ""
    reservations = {str(k): max(0, int(v)) for k, v in (du_tru_token_theo_tier or {}).items()}
    now = time.time()
    routes_tier: dict[str, list[tuple[str, str]]] = {}
    route_obj: dict[tuple[str, str], Route] = {}
    route_reservation: dict[tuple[str, str], int] = {}
    for tier in sorted(nhu_cau):
        keys: list[tuple[str, str]] = []
        for route in gw.routes_cua_tier(tier):
            key = (route.provider, route.model)
            route_obj[key] = route
            route_reservation[key] = max(route_reservation.get(key, 0), reservations.get(tier, 0))
            if key not in keys:
                keys.append(key)
        routes_tier[tier] = keys

    raw_capacity: dict[tuple[str, str], int] = {}
    capacity: dict[tuple[str, str], int] = {}
    for key, route in sorted(route_obj.items()):
        reserve = route_reservation[key]
        rpd_capacity = gw.con_lai(route, now)
        tpm_capacity = (gw.tpm_con_lai(route, now) // reserve if reserve > 0 else rpd_capacity)
        raw_capacity[key] = min(rpd_capacity, tpm_capacity)
        capacity[key] = (
            gw.kha_nang_burst(route, now, du_tru_token_moi_request=reserve)
            if burst else raw_capacity[key]
        )

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
    for (provider, model), cap in sorted(capacity.items()):
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
        f"{provider}/{model}={capacity[(provider, model)]}/{raw_capacity[(provider, model)]}"
        f" (TPM={gw.tpm_con_lai(route_obj[(provider, model)], now)},"
        f" reserve={route_reservation[(provider, model)]})"
        for provider, model in sorted(capacity)
    ) or "không có route khả dụng"
    prefix = "RPM burst không đủ (TPM headroom included)" if burst else "RPD/TPM budget không đủ"
    return False, (
        f"{prefix} cho autonomy tick: cần {tong_can} lượt bắt buộc ({chi_tiet_can}), "
        f"phân bổ được {dong}; headroom an toàn/raw: {chi_tiet_cap}"
    )


def budget_guard(
    gw: GatewayReal, can_theo_tier: dict[str, int],
    du_tru_token_theo_tier: dict[str, int] | None = None,
) -> tuple[bool, str]:
    """Fail closed before a cohort when RPD or TPM cannot cover it."""
    return _cohort_guard(
        gw, can_theo_tier, du_tru_token_theo_tier=du_tru_token_theo_tier, burst=False
    )


def burst_guard(
    gw: GatewayReal, can_theo_tier: dict[str, int],
    du_tru_token_theo_tier: dict[str, int] | None = None,
) -> tuple[bool, str]:
    """Fail closed before an immediate cohort when RPM, RPD, or TPM is insufficient."""
    return _cohort_guard(
        gw, can_theo_tier, du_tru_token_theo_tier=du_tru_token_theo_tier, burst=True
    )
