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
    def __init__(self, w: World, fast: bool, run_dir: Path | None, p_malformed: float):
        self.fast = fast
        self.p_malformed = p_malformed
        self.provider = MockProvider(w, p_malformed, fast)
        self.log = LLMCallLog(run_dir / "llm_calls.sqlite" if run_dir else None)
        self.so_call = 0
        self.so_fallback = 0
        self.so_nghi = 0
        self.het_ngan_sach = False
        self.ly_do_dung = ""
        # mock: gather TUẦN TỰ theo sorted-id, chia sẻ da_nham (giữ hành vi phân bố thửa
        # công + kinh tế sống + tất định như kiến trúc cũ; mock tức thì nên không cần
        # song song). real override = False: fan-out song song, da_nham rỗng mỗi agent.
        self._tuan_tu = True
        # khoá serial hóa log/bộ đếm khi real fan-out per-agent trong thread pool
        self._lock = threading.Lock()

    def _du_ngan_sach(self, w: World, thinkers: list[str]) -> bool:
        """Mock luôn đủ; MindReal override bằng budget guard thật (per-agent)."""
        return True

    def _dich_intent_la(self, w: World, thung: list, ke_hoach: dict) -> None:
        """Mock: không có LLM dịch — bỏ + log (mỏ ý định mới lạ, điều luật #3)."""
        for aid, d, ly_do in thung:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)

    def __call__(self, w: World) -> dict[str, KeHoach]:
        from minds.rulebot import _BoiCanhTick, bo_sung_ke_hoach_entity

        self.provider.w = w  # sau resume, w là object mới
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

        # --- nén hồi ký mỗi 4 tick (mock nén — heuristic, vẫn log call) ---
        if w.tick % 4 == 0:
            self._nen_hoi_ky(w)
        self.log.flush()
        return ke_hoach

    async def _gather_song_song(self, w: World, thinkers: list[str],
                                triggers: dict[str, list[str]], ctx: dict) -> dict:
        """REAL: fan-out SONG SONG per-agent (I/O-bound). Mỗi agent da_nham RỖNG (bất
        đối xứng thông tin — LLM tự thấy đất công còn trống trong prompt; xung đột thửa
        do engine trọng tài apply-time). Kết quả APPLY theo sorted-id ở caller → thứ tự
        hoàn tất của coroutine KHÔNG ảnh hưởng world-hash (điều luật #4)."""
        sem = asyncio.Semaphore(int(w.cfg.get("minds.concurrency")))

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
        try:
            resp = self.provider.goi(req, attempt=0)  # NGOÀI khoá — I/O chạy song song
        except LoiHetQuota as e:
            with self._lock:
                self._ghi_call_loi(w, req, e)
                self._dung_em(str(e))
            return None
        ok, hong = parse_batch(resp.text, [aid])
        with self._lock:
            self.so_call += 1
            self.log.ghi(w.tick, req, resp, fallback=False)
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
            self.log.ghi(w.tick, req2, resp2, fallback=bool(hong2))
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
        self.log.ghi(w.tick, req, resp_loi, fallback=True)

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
                  p_malformed: float | None = None) -> MindMock:
    if p_malformed is None:
        p_malformed = float(w.cfg.get("models.mock.p_malformed_mac_dinh"))
    return MindMock(w, fast, run_dir, p_malformed)
