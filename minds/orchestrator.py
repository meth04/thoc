"""Orchestrator minds: trigger → 1-to-1 gather (async) → apply (sorted) → intents.

Kiến trúc PART 5 (1 agent = 1 LLM call): ai có trigger thì "nghĩ" bằng MỘT call riêng
(bất đối xứng thông tin — call của A không chứa ví của B). Pha GATHER fan-out song song
(asyncio), pha APPLY duyệt theo sorted-id nên tất định tuyệt đối bất kể thứ tự hoàn tất
(điều luật #4: cùng transcript → cùng world-hash). Người không trigger chạy thẻ chính
sách. Fallback (JSON không cứu nổi sau retry): giữ thẻ cũ, không hành động mới.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from engine.intents import KeHoach
from engine.world import World
from minds.gateway import LLMCallLog, LLMRequest, LLMResponse, MockProvider
from minds.policy_cards import thi_hanh_the
from minds.prompts import build_agent_prompt
from minds.provenance import record_plan, record_plan_actions, record_raw_actions
from minds.providers_real import LoiHetQuota, che_key
from minds.repair import parse_batch
from minds.safety import ap_dung_san_an_toi_thieu, ap_dung_san_cho_o_toi_thieu
from minds.schemas import TheChinhSach, ap_patch
from minds.tick_budget import LoiVuotNganSachTick, NganSachLLMTick, cau_hinh_ngan_sach
from minds.translate import quyet_dinh_thanh_ke_hoach
from minds.triggers import quet_trigger


def tier_cua(w: World, aid: str) -> str:
    """tier(agent) = max(sàn tri thức, tier theo E). Sàn nội sinh mở ở Phase 4."""
    e = w.agents[aid].e_bac
    san = int(getattr(w, "san_tri_thuc_tier", 0))
    return f"T{max(min(e, 4), san)}"


def _the_cua(w: World, aid: str) -> TheChinhSach:
    du_lieu = w.policy_cards.get(aid)
    return TheChinhSach(**du_lieu) if du_lieu else TheChinhSach()


def _agent_tu_chu(w: World) -> list[str]:
    """Cư dân có năng lực tự quyết kinh tế trong tick hiện tại.

    Trẻ nhỏ vẫn được hộ bảo trợ qua engine; ép một LLM trưởng thành đưa lệnh
    thị trường thay cho trẻ nhỏ sẽ làm mô hình *kém* thực tế hơn. Tất cả người
    trưởng thành còn sống, không chỉ người có trigger, đều phải có call riêng
    khi treatment autonomy được bật.
    """
    tuoi_truong_thanh = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    return [
        aid for aid in sorted(w.agents)
        if w.agents[aid].con_song and w.agents[aid].truong_thanh(tuoi_truong_thanh)
    ]


class MindMock:
    def __init__(self, w: World, fast: bool, run_dir: Path | None, p_malformed: float,
                 transcript_path: Path | None = None):
        self.fast = fast
        self.p_malformed = p_malformed
        self.provider = MockProvider(w, p_malformed, fast)
        self.log = LLMCallLog(run_dir / "llm_calls.sqlite" if run_dir else None)
        # transcript.jsonl append-only (P1 reproducibility): ghi mọi call → replay không
        # mạng. None = tắt (giữ hành vi cũ). Lấy lười để tránh phụ thuộc vòng import.
        self.transcript = None
        if transcript_path is not None:
            from minds.transcript import TranscriptWriter

            self.transcript = TranscriptWriter(transcript_path)
        self.so_call = 0
        self.so_fallback = 0
        self.so_nghi = 0
        # telemetry tích lũy + theo tick (metrics.jsonl đọc stats_tick sau mỗi tick)
        self.tok_in = 0
        self.tok_out = 0
        self.so_luot_cong_cu = 0  # tổng lượt gọi công cụ MCP
        self.stats_tick: dict = {}
        # Created afresh for each world tick. It aggregates independent
        # per-agent budgets: 50 autonomous residents imply 50..500 provider
        # requests, never a hidden village-wide cap of ten.
        self._ngan_sach_tick: NganSachLLMTick | None = None
        self._cfg_ngan_sach_tick: dict = {}
        self.so_api_call = 0
        self.so_api_call_bi_tu_choi = 0
        self._agent_bi_chan_tick: set[str] = set()
        # Exactly-one terminal decision state for every scheduled agent/tick. This is an
        # accounting invariant independent of whether a provider request ever started.
        self._scheduled_decisions_tick: set[str] = set()
        self._terminal_decisions_tick: dict[str, str] = {}
        self.het_ngan_sach = False
        self.ly_do_dung = ""
        # mock: gather TUẦN TỰ theo sorted-id, chia sẻ da_nham (giữ hành vi phân bố thửa
        # công + kinh tế sống + tất định như kiến trúc cũ; mock tức thì nên không cần
        # song song). real override = False: fan-out song song, da_nham rỗng mỗi agent.
        self._tuan_tu = True
        # khoá serial hóa log/bộ đếm khi real fan-out per-agent trong thread pool
        self._lock = threading.Lock()
        # trần đồng thời (real tự co giãn theo số key ở MindReal.__init__)
        self.concurrency = int(w.cfg.get("minds.concurrency"))

    def _du_ngan_sach(self, w: World, thinkers: list[str],
                       triggers: dict[str, list[str]] | None = None) -> bool:
        """Mock luôn đủ; MindReal override bằng budget guard thật (per-agent)."""
        _ = triggers
        return True

    def _dich_intent_la(self, w: World, thung: list, ke_hoach: dict) -> None:
        """Mock: không có LLM dịch — bỏ + log (mỏ ý định mới lạ, điều luật #3)."""
        for aid, d, ly_do in thung:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)

    def _ghi_log(self, w: World, req: LLMRequest, resp: LLMResponse, fallback: bool,
                 error: Exception | None = None) -> None:
        """Ghi llm_calls + gom telemetry (token/latency/lượt công cụ) theo tick. Gọi dưới
        self._lock ở nhánh real fan-out; nhánh nền/mock đơn luồng nên an toàn."""
        self.log.ghi(w.tick, req, resp, fallback)
        # transcript lossless (P1): raw ĐẦY ĐỦ (llm_calls cắt 4000 ký tự nên không dùng
        # replay được). Call lỗi cũng là outcome cần replay: nếu bỏ qua nó, replay có một
        # ``miss`` nhân tạo và không còn là artifact đủ để tái lập đường dừng-êm.
        if self.transcript is not None:
            self.transcript.ghi(
                w.tick, req.tier, resp.provider, resp.model,
                w.cfg.get(f"models.tiers.{req.tier}.temperature", None),
                req.prompt, resp.text, resp.tok_in, resp.tok_out,
                error_type=type(error).__name__ if error is not None else (
                    "ProviderError" if resp.provider == "loi" else None
                ),
                error_message=str(error) if error is not None else resp.text,
                tool_turns=resp.tool_turns,
                tool_catalog_hash=resp.tool_catalog_hash,
                logical_id=req.logical_id,
                logical_kind=req.logical_kind,
                decision_id=req.decision_id,
                source=req.attempt_source or req.logical_kind,
            )
        self.tok_in += resp.tok_in
        self.tok_out += resp.tok_out
        # `retries` also represents JSON repair in ordinary calls. Tool usage
        # must be counted from the attested calls themselves, never inferred.
        tool_calls = len(resp.tool_turns)
        self.so_luot_cong_cu += tool_calls
        st = self.stats_tick
        st["call"] = st.get("call", 0) + 1
        st["tok_in"] = st.get("tok_in", 0) + resp.tok_in
        st["tok_out"] = st.get("tok_out", 0) + resp.tok_out
        st["latency_ms"] = st.get("latency_ms", 0) + int(resp.latency_s * 1000)
        st["tool_call"] = st.get("tool_call", 0) + tool_calls
        if fallback:
            st["fallback"] = st.get("fallback", 0) + 1

    def _bind_attempt_log(self) -> None:
        """Wire the per-HTTP-attempt sink without changing ``MindReal``'s public constructor."""
        gateway = getattr(self, "gateway", None)
        if gateway is not None and hasattr(gateway, "dat_attempt_log"):
            gateway.dat_attempt_log(self.log)
        provider_gateway = getattr(getattr(self, "provider", None), "gw", None)
        if provider_gateway is not None and hasattr(provider_gateway, "dat_attempt_log"):
            provider_gateway.dat_attempt_log(self.log)

    @staticmethod
    def _decision_id(w: World, aid: str) -> str:
        return f"decision:{w.tick}:{aid}"

    def _tao_request_quyet_dinh(
        self,
        w: World,
        aid: str,
        triggers: dict[str, list[str]],
        ctx: dict,
        *,
        json_repair: bool = False,
    ) -> LLMRequest:
        prompt = (f"[mock 1-to-1] id={aid} tick={w.tick}" if self._tuan_tu
                  else build_agent_prompt(w, aid, triggers))
        if json_repair:
            prompt += "\n[LỖI JSON — trả lại đúng schema]"
        max_api = (int(self._cfg_ngan_sach_tick["toi_da_moi_task"])
                   if self._ngan_sach_tick is not None else None)
        return LLMRequest(
            prompt=prompt,
            ctx={**ctx, "aid": aid},
            tier=tier_cua(w, aid),
            batch_ids=[aid],
            tick_budget=self._ngan_sach_tick,
            logical_id=f"agent:{aid}",
            logical_kind="decision",
            max_api_calls=max_api,
            tick=w.tick,
            decision_id=self._decision_id(w, aid),
            attempt_source="json_repair" if json_repair else "decision_initial",
        )

    def _ghi_terminal_decision(
        self,
        w: World,
        aid: str,
        req: LLMRequest,
        reason: str,
        *,
        error: Exception | None = None,
    ) -> None:
        """Record/consume exactly one terminal state for a scheduled decision."""
        if aid in self._terminal_decisions_tick:
            raise RuntimeError(
                f"duplicate terminal decision for {aid} at tick {w.tick}: "
                f"{self._terminal_decisions_tick[aid]} then {reason}"
            )
        self._terminal_decisions_tick[aid] = reason
        if (reason == "budget_denied" and error is not None
                and not bool(getattr(error, "attempt_accounted", False))):
            gateway = getattr(self, "gateway", None)
            if gateway is not None and hasattr(gateway, "ghi_budget_denied_before_start"):
                gateway.ghi_budget_denied_before_start(req)
                error.attempt_accounted = True
        consume = getattr(self.provider, "consume_terminal", None)
        if callable(consume):
            consume(req, reason)
        if self.transcript is not None:
            self.transcript.ghi_terminal(
                tick=w.tick,
                req=req,
                terminal_reason=reason,
                terminal_state=("decision_accepted" if reason == "response"
                                else "fallback_selected"),
                error_type=type(error).__name__ if error is not None else None,
                error_message=str(error) if error is not None else None,
                tool_turns=list(getattr(error, "tool_turns", []) or []),
                tool_catalog_hash=getattr(error, "tool_catalog_hash", None),
            )

    def __call__(self, w: World) -> dict[str, KeHoach]:
        from minds.rulebot import _BoiCanhTick, bo_sung_ke_hoach_entity

        self.provider.w = w  # sau resume, w là object mới
        self.stats_tick = {}  # reset telemetry của tick này
        self._scheduled_decisions_tick = set()
        self._terminal_decisions_tick = {}
        self._bind_attempt_log()
        self._cfg_ngan_sach_tick = cau_hinh_ngan_sach(w.cfg)
        self._ngan_sach_tick = None
        self._agent_bi_chan_tick = set()
        bc = _BoiCanhTick(w)
        cau_hon_den: dict[str, list[str]] = {}
        for tu, den, _t in w.cau_hon_cho:
            cau_hon_den.setdefault(den, []).append(tu)
        ctx = {"bc": bc, "cau_hon_den": cau_hon_den}

        triggers = quet_trigger(w)
        if self._cfg_ngan_sach_tick["bat"]:
            tu_chu = _agent_tu_chu(w)
            toi_thieu = int(self._cfg_ngan_sach_tick["toi_thieu"])
            toi_da = int(self._cfg_ngan_sach_tick["toi_da"])
            # One aggregate semaphore still gives provider code a simple,
            # thread-safe interface; its hard total is exactly the sum of all
            # independent agent maxima, and each ``agent:<id>`` has its own
            # cap. Thus A cannot spend B's ten calls.
            self._ngan_sach_tick = NganSachLLMTick(
                tick=w.tick,
                toi_thieu=toi_thieu if tu_chu else 0,
                toi_da=len(tu_chu) * toi_da,
                default_toi_da_moi_task=toi_da,
            )
            if tu_chu:
                self._ngan_sach_tick.dat_yeu_cau_cho_tasks(
                    [f"agent:{aid}" for aid in tu_chu], toi_thieu_moi_task=toi_thieu
                )
                # The trigger remains context/priority information, never a
                # gate which suppresses a resident's independent LLM turn.
                triggers = {
                    aid: list(triggers.get(aid, ("dieu_phoi_toi_thieu",)))
                    for aid in tu_chu
                }
            else:
                self._ngan_sach_tick.dat_yeu_cau_toi_thieu(
                    False, ly_do_ngoai_le="no_autonomous_adult"
                )
        ke_hoach: dict[str, KeHoach] = {}
        thung_intent_la: list = []  # (aid, hành động thô, lý do) — bộ dịch intent xử lý sau
        # một da_nham cho CẢ tick: người nghĩ (mock) → người-thẻ → entity đều tránh
        # nhắm trùng thửa công (kinh tế sống). real: người nghĩ chạy song song không
        # dùng nó (engine trọng tài apply-time), nhưng người-thẻ/entity tuần tự vẫn dùng.
        da_nham: set[str] = set()

        # người nghĩ = có trigger + còn sống, DUYỆT THEO SORTED ID (nền tảng tất định)
        thinkers = [
            aid for aid in sorted(triggers)
            if (a := w.agents.get(aid)) is not None and a.con_song
        ]
        # Preserve the intended cohort in telemetry even if the real-provider guard rejects
        # the tick. A scheduled turn always receives one explicit terminal state.
        so_task_logic = len(thinkers)
        self._scheduled_decisions_tick = set(thinkers)
        self.so_nghi += len(thinkers)

        # hook ngân sách (real: budget guard per-agent; mock: luôn đủ)
        if thinkers and not self._du_ngan_sach(w, thinkers, triggers):
            self.het_ngan_sach = True
            for aid in thinkers:
                req_denied = self._tao_request_quyet_dinh(
                    w, aid, triggers, {**ctx, "da_nham": set()}
                )
                exc = LoiVuotNganSachTick("budget guard denied before provider start")
                self._ghi_terminal_decision(w, aid, req_denied, "budget_denied", error=exc)
                self.so_fallback += 1
                ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, da_nham)
                record_plan(w, aid, "fallback", detail="budget_guard")
                record_plan_actions(w, ke_hoach[aid], "fallback")
            thinkers = []

        if thinkers:
            # PHA GATHER: mock chạy ĐỒNG BỘ (CPU thuần — asyncio/thread chỉ tổ tốn); real
            # override _gather_song_song bằng asyncio fan-out (I/O). Cả hai trả {aid: QĐ|None}.
            if self._tuan_tu:
                ket: dict[str, object] = {}
                for aid in thinkers:  # sorted, chia sẻ da_nham → phân bố thửa, kinh tế sống
                    ket[aid] = self._nghi_dong_bo(w, aid, triggers,
                                                  {**ctx, "da_nham": da_nham})
            else:
                ket = asyncio.run(self._gather_song_song(w, thinkers, triggers, ctx))
            # sự cố đã vào prompt tick này → xóa sau khi gather (builder chỉ đọc)
            for aid in thinkers:
                a = w.agents.get(aid)
                if a is not None:
                    a.su_co = []
                # Unlike raw journal rows, this is a prompt-facing
                # behavioural input. Once the actor has been asked, its next
                # engine-confirmed result will replace it; unselected agents
                # retain feedback until they get a decision opportunity.
                feedback = getattr(w, "action_feedback", None)
                if isinstance(feedback, dict):
                    feedback.pop(aid, None)
            # PHA APPLY: duyệt SORTED ID — thứ tự ghi Ledger tất định (điều luật #4).
            # xung đột thửa công (nhiều agent cùng nhắm) do engine dedup apply-time
            # (production.da_canh_tick_nay theo sorted id) — không cần da_nham ở mind.
            decider_injected = (
                getattr(self._nghi_dong_bo, "__func__", None) is not MindMock._nghi_dong_bo
            )
            for aid in sorted(ket):
                qd = ket[aid]
                if aid not in self._terminal_decisions_tick:
                    if not decider_injected:
                        raise RuntimeError(
                            f"production decision path returned without terminal state: "
                            f"{aid} tick {w.tick}"
                        )
                    # Explicit test seam: a fixture replaced the whole provider/parse method,
                    # so no lower layer exists to record a terminal. Account its returned value
                    # at the orchestrator boundary without weakening the production invariant.
                    req_injected = self._tao_request_quyet_dinh(
                        w, aid, triggers, {**ctx, "da_nham": set()}
                    )
                    self._ghi_terminal_decision(
                        w, aid, req_injected,
                        "response" if qd is not None else "parse_unusable",
                    )
                if qd is None:  # fallback: giữ thẻ cũ, không hành động mới
                    self.so_fallback += 1
                    ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, set())
                    detail = ("llm_tick_cap" if aid in self._agent_bi_chan_tick
                              else "llm_response_unusable")
                    record_plan(w, aid, "fallback", detail=detail)
                    record_plan_actions(w, ke_hoach[aid], "fallback")
                    continue
                kh = quyet_dinh_thanh_ke_hoach(w, qd, thung_intent_la)
                the_hien_tai = _the_cua(w, aid)
                # không kèm patch thẻ → ý định sinh con GIỮ theo thẻ hiện tại
                kh.y_dinh_sinh_con = the_hien_tai.y_dinh_sinh_con
                if qd.the_chinh_sach is not None:
                    try:
                        the_moi = ap_patch(the_hien_tai, qd.the_chinh_sach)
                        w.policy_cards[aid] = the_moi.model_dump()
                        kh.y_dinh_sinh_con = the_moi.y_dinh_sinh_con
                    except Exception as e:  # noqa: BLE001 — thẻ hỏng thì giữ thẻ cũ
                        w.ghi_unrecognized(aid, "the_chinh_sach", f"patch hỏng: {e}")
                ke_hoach[aid] = kh
                origin = "mock" if self._tuan_tu else "llm"
                record_plan(w, aid, origin)
                record_raw_actions(
                    w, aid, [action.model_dump() for action in qd.hanh_dong], origin
                )
                # mock (_tuan_tu) chia sẻ da_nham giữa người nghĩ để người-thẻ/entity không
                # nhắm trùng thửa công. Lúc GATHER, PersonaBot đã nạp da_nham; nhưng
                # replay-from-transcript KHÔNG chạy PersonaBot nên tái dựng phần đã nhắm từ
                # chính kế hoạch — idempotent với run gốc (canh_thua đã nằm sẵn trong tập).
                # real (_tuan_tu=False): thinker dùng da_nham RỖNG riêng → KHÔNG đụng ở đây.
                if self._tuan_tu:
                    da_nham.update(kh.canh_thua)

        # --- bộ phiên dịch intent lạ (real: 1 call LLM; mock: log như cũ) ---
        if thung_intent_la:
            self._dich_intent_la(w, thung_intent_la, ke_hoach)

        # --- người không nghĩ: thẻ chính sách (tuần tự sorted, chia sẻ da_nham) ---
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song or aid in ke_hoach:
                continue
            ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, da_nham)
            record_plan(w, aid, "policy_card")
            record_plan_actions(w, ke_hoach[aid], "policy_card")

        # --- entity: việc thường nhật chạy MỖI tick (thẻ của pháp nhân) ---
        bo_sung_ke_hoach_entity(w, ke_hoach, bc, da_nham)

        # Survival floor công khai: bổ sung một vụ canh khả thi cho hộ chưa có kế hoạch
        # sinh kế khi kho xuống dưới ngưỡng config. Cần chạy SAU LLM/thẻ để không thay
        # thế lựa chọn tự nguyện, chỉ lấp một ràng buộc vật chất bị bỏ quên.
        ap_dung_san_an_toi_thieu(w, ke_hoach, bc, da_nham)
        ap_dung_san_cho_o_toi_thieu(w, ke_hoach)

        # --- nén hồi ký mỗi 4 tick (mock nén — heuristic, vẫn log call) ---
        if w.tick % 4 == 0:
            self._nen_hoi_ky(w)
        # --- tự phản tư mỗi N tick: cô đọng ký ức + ân oán → niềm tin cốt lõi (5.3) ---
        if w.tick % int(w.cfg.get("minds.reflection_moi_n_tick")) == 0:
            self._reflection(w)
        self.stats_tick["logical_task"] = so_task_logic
        missing_terminal = sorted(
            self._scheduled_decisions_tick - set(self._terminal_decisions_tick)
        )
        extra_terminal = sorted(
            set(self._terminal_decisions_tick) - self._scheduled_decisions_tick
        )
        if missing_terminal or extra_terminal:
            raise RuntimeError(
                "decision terminal accounting violation: "
                f"missing={missing_terminal} extra={extra_terminal}"
            )
        reason_counts: dict[str, int] = {}
        for reason in self._terminal_decisions_tick.values():
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        self.stats_tick.update({
            "scheduled_agent_decision": so_task_logic,
            "completed_agent_decision_turn": len(self._terminal_decisions_tick),
            "parsed_agent_decision": int(reason_counts.get("response", 0)),
            "terminal_reason_by_agent": dict(sorted(self._terminal_decisions_tick.items())),
            "terminal_reason_counts": dict(sorted(reason_counts.items())),
            "exact_one_terminal_decision": True,
        })
        if self._ngan_sach_tick is not None:
            tick_stats = self._ngan_sach_tick.thong_ke()
            tick_stats["api_call_by_agent"] = {
                task.removeprefix("agent:"): count
                for task, count in tick_stats.get("api_call_by_task", {}).items()
                if task.startswith("agent:")
            }
            tick_stats["api_call_scope"] = "moi_agent"
            tick_stats["api_call_min_moi_agent"] = int(self._cfg_ngan_sach_tick["toi_thieu"])
            tick_stats["api_call_cap_moi_agent"] = int(self._cfg_ngan_sach_tick["toi_da"])
            self.stats_tick.update(tick_stats)
            self.so_api_call += int(tick_stats["api_call"])
            self.so_api_call_bi_tu_choi += int(tick_stats["api_call_denied"])
        # Explicit source/status counters are additive API for telemetry owner. Legacy
        # ``api_call``/``retries`` aliases remain unchanged.
        attempt_summary = self.log.attempt_summary(effective_only=True, tick=w.tick)
        if attempt_summary:
            self.stats_tick["http_attempt_accounting"] = attempt_summary
        self.log.flush()
        if self.transcript is not None:
            self.transcript.flush()
        return ke_hoach

    def _nguoi_than_va_oan(self, w: World, aid: str, k: int = 3):
        """Top-k người thân nhất và k người bị oán nhất (từ đồ thị quan hệ) — CÒN SỐNG."""
        than: list[tuple[float, str]] = []
        oan: list[tuple[float, str]] = []
        for (a, b), v in w.quan_he.items():
            nguoi = b if a == aid else (a if b == aid else None)
            if nguoi is None or nguoi not in w.agents or not w.agents[nguoi].con_song:
                continue
            (than if v > 0 else oan).append((v, nguoi))
        than.sort(reverse=True)
        oan.sort()
        return than[:k], oan[:k]

    def _reflection(self, w: World) -> None:
        """MOCK: phản tư HEURISTIC (tất định). MindReal override bằng LLM. Uy tín xã hội
        TỰ PHÁT: kẻ bội tín nhiều người → nhiều agent ghi 'đề phòng X' trong niềm tin."""
        tt = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if a.con_song and a.tuoi_nam >= tt:
                self._reflection_mot_nguoi(w, a)

    def _reflection_mot_nguoi(self, w: World, a) -> None:
        """Niềm tin cô đọng từ ân/oán mạnh nhất (heuristic tất định — cũng là fallback real)."""
        than, oan = self._nguoi_than_va_oan(w, a.id)
        ve = []
        if than:
            ve.append("tin cậy " + ", ".join(w.agents[n].ten for _v, n in than))
        if oan:
            ve.append("đề phòng " + ", ".join(w.agents[n].ten for _v, n in oan))
        a.niem_tin = "; ".join(ve) if ve else "chưa có ai để bụng thương hay ghét"

    async def _gather_song_song(self, w: World, thinkers: list[str],
                                triggers: dict[str, list[str]], ctx: dict) -> dict:
        """REAL: fan-out SONG SONG per-agent (I/O-bound). Mỗi agent da_nham RỖNG (bất
        đối xứng thông tin — LLM tự thấy đất công còn trống trong prompt; xung đột thửa
        do engine trọng tài apply-time). Kết quả APPLY theo sorted-id ở caller → thứ tự
        hoàn tất của coroutine KHÔNG ảnh hưởng world-hash (điều luật #4)."""
        sem = asyncio.Semaphore(self.concurrency)

        async def mot(aid: str):
            async with sem:
                # provider.goi đồng bộ (HTTP) → to_thread để fan-out thật sự song song
                return aid, await asyncio.to_thread(
                    self._nghi_dong_bo, w, aid, triggers, {**ctx, "da_nham": set()})

        return dict(await asyncio.gather(*(mot(aid) for aid in thinkers)))

    def _nghi_dong_bo(self, w: World, aid: str,
                      triggers: dict[str, list[str]], ctx: dict):
        """Một agent = một call (đồng bộ). Parse + retry 1 lần; trả QuyetDinh hoặc None.
        Dùng trực tiếp cho mock (CPU) và trong thread pool cho real (HTTP)."""
        # mock: PersonaBot quyết định từ ctx, KHÔNG đọc prompt; real: prompt thật. Cả hai
        # dùng cùng decision_id để nối provider attempts, JSON repair và terminal outcome.
        req = self._tao_request_quyet_dinh(w, aid, triggers, ctx)
        # MCP (PART 5.2): real + cờ bật + provider hỗ trợ → vòng công cụ CHỈ ĐỌC
        dung_cong_cu = (not self._tuan_tu
                        and bool(w.cfg.get("minds.dung_cong_cu_the_gioi"))
                        and hasattr(self.provider, "goi_agentic"))
        try:
            if dung_cong_cu:
                resp = self.provider.goi_agentic(req, w, aid)  # NGOÀI khoá — I/O song song
            else:
                resp = self.provider.goi(req, attempt=0)  # NGOÀI khoá — I/O chạy song song
        except LoiVuotNganSachTick as e:
            with self._lock:
                self._agent_bi_chan_tick.add(aid)
                self._ghi_terminal_decision(w, aid, req, "budget_denied", error=e)
            return None
        except LoiHetQuota as e:
            with self._lock:
                self._ghi_call_loi(w, req, e)
                self._ghi_terminal_decision(w, aid, req, "provider_error", error=e)
                self._dung_em(str(e))
            return None
        ok, hong = parse_batch(resp.text, [aid])
        with self._lock:
            self.so_call += 1
            self._ghi_log(w, req, resp, False)
        if not hong:
            with self._lock:
                self._ghi_terminal_decision(w, aid, req, "response")
            return ok[aid]
        # retry 1 lần kèm nhắc lỗi (mock: sinh lại với attempt=1)
        req2 = self._tao_request_quyet_dinh(w, aid, triggers, ctx, json_repair=True)
        try:
            resp2 = self.provider.goi(req2, attempt=1)
        except LoiVuotNganSachTick as e:
            with self._lock:
                self._agent_bi_chan_tick.add(aid)
                self._ghi_terminal_decision(w, aid, req2, "budget_denied", error=e)
            return None
        except LoiHetQuota as e:
            with self._lock:
                self._ghi_call_loi(w, req2, e)
                self._ghi_terminal_decision(w, aid, req2, "provider_error", error=e)
                self._dung_em(str(e))
            return None
        resp2.retries = max(resp2.retries, 1)  # legacy alias
        resp2.json_repair_retries = max(resp2.json_repair_retries, 1)
        ok2, hong2 = parse_batch(resp2.text, [aid])
        with self._lock:
            self.so_call += 1
            self._ghi_log(w, req2, resp2, bool(hong2))
            self._ghi_terminal_decision(
                w, aid, req2, "parse_unusable" if hong2 else "response"
            )
        return ok2.get(aid)  # None → fallback thẻ cũ ở pha apply

    def _dung_em(self, ly_do: str) -> None:
        """Provider cạn quota / hỏng dai dẳng giữa tick: đánh dấu dừng êm để run.py
        checkpoint (điều luật #7 — không degrade, không cố). Agent gặp lỗi rơi về
        thẻ cũ ở pha apply (QuyetDinh None)."""
        self.het_ngan_sach = True
        self.ly_do_dung = ly_do

    def _ghi_call_loi(self, w: World, req: LLMRequest, e: Exception) -> None:
        """Call thất bại hẳn (hết quota / lỗi HTTP dai dẳng) cũng phải có vết trong
        llm_calls (điều luật #6) — raw là thông báo lỗi đã che key, tok=0."""
        so_hong = int(getattr(e, "so_attempt_hong", 0))
        resp_loi = LLMResponse(
            text=f"[LOI] {che_key(str(e))[:500]}", provider="loi", model="",
            retries=so_hong, provider_retries=so_hong,
        )
        self._ghi_log(w, req, resp_loi, True, error=e)

    def _nen_hoi_ky(self, w: World) -> None:
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song or not a.truong_thanh(16):
                continue
            tai_san = w.ledger.so_du(aid, "thoc")
            dat = sum(1 for p in w.parcels.values() if p.chu == aid)
            hd = sum(1 for h in w.hop_dong.values()
                     if h.trang_thai == "hieu_luc" and aid in h.cac_ben)
            a.hoi_ky = (
                f"Năm {w.nam()}: {a.tuoi_nam:.0f} tuổi, {len(a.con)} con, "
                f"{tai_san:.0f}kg thóc, {dat} thửa đất, {hd} giao kèo, học vấn E{a.e_bac}."
            )[: int(w.cfg.get("minds.hoi_ky_token_toi_da")) * 4]

    @property
    def fallback_rate(self) -> float:
        return self.so_fallback / self.so_nghi if self.so_nghi else 0.0


def tao_mind_mock(w: World, fast: bool = False, run_dir: Path | None = None,
                  p_malformed: float | None = None,
                  transcript_path: Path | None = None) -> MindMock:
    if p_malformed is None:
        p_malformed = float(w.cfg.get("models.mock.p_malformed_mac_dinh"))
    return MindMock(w, fast, run_dir, p_malformed, transcript_path=transcript_path)
