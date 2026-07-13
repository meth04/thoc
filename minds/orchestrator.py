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
from minds.providers_real import LoiHetQuota, che_key
from minds.repair import parse_batch
from minds.safety import ap_dung_san_an_toi_thieu
from minds.schemas import TheChinhSach, ap_patch
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

    def _du_ngan_sach(self, w: World, thinkers: list[str]) -> bool:
        """Mock luôn đủ; MindReal override bằng budget guard thật (per-agent)."""
        return True

    def _dich_intent_la(self, w: World, thung: list, ke_hoach: dict) -> None:
        """Mock: không có LLM dịch — bỏ + log (mỏ ý định mới lạ, điều luật #3)."""
        for aid, d, ly_do in thung:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)

    def _ghi_log(self, w: World, req: LLMRequest, resp: LLMResponse, fallback: bool) -> None:
        """Ghi llm_calls + gom telemetry (token/latency/lượt công cụ) theo tick. Gọi dưới
        self._lock ở nhánh real fan-out; nhánh nền/mock đơn luồng nên an toàn."""
        self.log.ghi(w.tick, req, resp, fallback)
        # transcript lossless (P1): raw ĐẦY ĐỦ (llm_calls cắt 4000 ký tự nên không dùng
        # replay được). Bỏ qua call LỖI (provider "loi") — chúng là điểm dừng, không có
        # response để replay; miss transcript lúc replay sẽ tự tái hiện dừng-êm.
        if self.transcript is not None and resp.provider != "loi":
            self.transcript.ghi(
                w.tick, req.tier, resp.provider, resp.model,
                w.cfg.get(f"models.tiers.{req.tier}.temperature", None),
                req.prompt, resp.text, resp.tok_in, resp.tok_out,
            )
        self.tok_in += resp.tok_in
        self.tok_out += resp.tok_out
        self.so_luot_cong_cu += max(0, resp.retries)  # với vòng agentic = số lượt công cụ
        st = self.stats_tick
        st["call"] = st.get("call", 0) + 1
        st["tok_in"] = st.get("tok_in", 0) + resp.tok_in
        st["tok_out"] = st.get("tok_out", 0) + resp.tok_out
        st["latency_ms"] = st.get("latency_ms", 0) + int(resp.latency_s * 1000)
        if fallback:
            st["fallback"] = st.get("fallback", 0) + 1

    def __call__(self, w: World) -> dict[str, KeHoach]:
        from minds.rulebot import _BoiCanhTick, bo_sung_ke_hoach_entity

        self.provider.w = w  # sau resume, w là object mới
        self.stats_tick = {}  # reset telemetry của tick này
        bc = _BoiCanhTick(w)
        cau_hon_den: dict[str, list[str]] = {}
        for tu, den, _t in w.cau_hon_cho:
            cau_hon_den.setdefault(den, []).append(tu)
        ctx = {"bc": bc, "cau_hon_den": cau_hon_den}

        triggers = quet_trigger(w)
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

        # hook ngân sách (real: budget guard per-agent; mock: luôn đủ)
        if thinkers and not self._du_ngan_sach(w, thinkers):
            self.het_ngan_sach = True
            for aid in thinkers:
                self.so_fallback += 1
                ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, da_nham)
            thinkers = []

        if thinkers:
            self.so_nghi += len(thinkers)
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
            # PHA APPLY: duyệt SORTED ID — thứ tự ghi Ledger tất định (điều luật #4).
            # xung đột thửa công (nhiều agent cùng nhắm) do engine dedup apply-time
            # (production.da_canh_tick_nay theo sorted id) — không cần da_nham ở mind.
            for aid in sorted(ket):
                qd = ket[aid]
                if qd is None:  # fallback: giữ thẻ cũ, không hành động mới
                    self.so_fallback += 1
                    ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, set())
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

        # --- entity: việc thường nhật chạy MỖI tick (thẻ của pháp nhân) ---
        bo_sung_ke_hoach_entity(w, ke_hoach, bc, da_nham)

        # Survival floor công khai: bổ sung một vụ canh khả thi cho hộ chưa có kế hoạch
        # sinh kế khi kho xuống dưới ngưỡng config. Cần chạy SAU LLM/thẻ để không thay
        # thế lựa chọn tự nguyện, chỉ lấp một ràng buộc vật chất bị bỏ quên.
        ap_dung_san_an_toi_thieu(w, ke_hoach, bc, da_nham)

        # --- nén hồi ký mỗi 4 tick (mock nén — heuristic, vẫn log call) ---
        if w.tick % 4 == 0:
            self._nen_hoi_ky(w)
        # --- tự phản tư mỗi N tick: cô đọng ký ức + ân oán → niềm tin cốt lõi (5.3) ---
        if w.tick % int(w.cfg.get("minds.reflection_moi_n_tick")) == 0:
            self._reflection(w)
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
        # mock: PersonaBot quyết định từ ctx, KHÔNG đọc prompt → khỏi dựng prompt vật lý
        # đắt tiền (chỉ để log tok_in giả). real: dựng prompt thật để LLM đọc + log đúng.
        prompt = (f"[mock 1-to-1] id={aid} tick={w.tick}" if self._tuan_tu
                  else build_agent_prompt(w, aid, triggers))
        tier = tier_cua(w, aid)
        req_ctx = {**ctx, "aid": aid}  # da_nham đã nằm trong ctx (chia sẻ/rỗng tùy chế độ)
        req = LLMRequest(prompt=prompt, ctx=req_ctx, tier=tier, batch_ids=[aid])
        # MCP (PART 5.2): real + cờ bật + provider hỗ trợ → vòng công cụ CHỈ ĐỌC
        dung_cong_cu = (not self._tuan_tu
                        and bool(w.cfg.get("minds.dung_cong_cu_the_gioi"))
                        and hasattr(self.provider, "goi_agentic"))
        try:
            if dung_cong_cu:
                resp = self.provider.goi_agentic(req, w, aid)  # NGOÀI khoá — I/O song song
            else:
                resp = self.provider.goi(req, attempt=0)  # NGOÀI khoá — I/O chạy song song
        except LoiHetQuota as e:
            with self._lock:
                self._ghi_call_loi(w, req, e)
                self._dung_em(str(e))
            return None
        ok, hong = parse_batch(resp.text, [aid])
        with self._lock:
            self.so_call += 1
            self._ghi_log(w, req, resp, False)
        if not hong:
            return ok[aid]
        # retry 1 lần kèm nhắc lỗi (mock: sinh lại với attempt=1)
        req2 = LLMRequest(prompt=prompt + "\n[LỖI JSON — trả lại đúng schema]",
                          ctx=req_ctx, tier=tier, batch_ids=[aid])
        try:
            resp2 = self.provider.goi(req2, attempt=1)
        except LoiHetQuota as e:
            with self._lock:
                self._ghi_call_loi(w, req2, e)
                self._dung_em(str(e))
            return None
        resp2.retries = max(resp2.retries, 1)
        ok2, hong2 = parse_batch(resp2.text, [aid])
        with self._lock:
            self.so_call += 1
            self._ghi_log(w, req2, resp2, bool(hong2))
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
        resp_loi = LLMResponse(
            text=f"[LOI] {che_key(str(e))[:500]}", provider="loi", model="",
            retries=int(getattr(e, "so_attempt_hong", 0)),
        )
        self._ghi_log(w, req, resp_loi, True)

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
                f"Năm {w.tick // 2}: {a.tuoi_nam:.0f} tuổi, {len(a.con)} con, "
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
