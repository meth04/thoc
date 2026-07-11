"""Orchestrator minds: trigger → batching → prompt → gateway → repair → validate → intents.

Ai có trigger thì "nghĩ" (gọi LLM/mock); còn lại thẻ chính sách chạy thường nhật.
Fallback (JSON không cứu nổi sau retry): giữ thẻ cũ, không hành động mới.
"""

from __future__ import annotations

from pathlib import Path

from engine.intents import KeHoach
from engine.world import World
from minds.gateway import LLMCallLog, LLMRequest, MockProvider
from minds.policy_cards import thi_hanh_the
from minds.prompts import build_batch_prompt
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

    def _du_ngan_sach(self, w: World, cac_batch: list) -> bool:
        """Mock luôn đủ; MindReal override bằng budget guard thật."""
        return True

    def _dich_intent_la(self, w: World, thung: list, ke_hoach: dict) -> None:
        """Mock: không có LLM dịch — bỏ + log (mỏ ý định mới lạ, điều luật #3)."""
        for aid, d, ly_do in thung:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)

    def __call__(self, w: World) -> dict[str, KeHoach]:
        from minds.rulebot import _BoiCanhTick

        self.provider.w = w  # sau resume, w là object mới
        bc = _BoiCanhTick(w)
        da_nham: set[str] = set()
        cau_hon_den: dict[str, list[str]] = {}
        for tu, den, _t in w.cau_hon_cho:
            cau_hon_den.setdefault(den, []).append(tu)
        ctx = {"bc": bc, "da_nham": da_nham, "cau_hon_den": cau_hon_den}

        triggers = quet_trigger(w)
        ke_hoach: dict[str, KeHoach] = {}
        thung_intent_la: list = []  # (aid, hành động thô, lý do) — bộ dịch intent xử lý sau

        # --- người nghĩ: batch theo (tier, làng), ≤8, xáo trộn seeded ---
        theo_nhom: dict[tuple[str, int], list[str]] = {}
        for aid in sorted(triggers):
            a = w.agents.get(aid)
            if a is None or not a.con_song:
                continue
            theo_nhom.setdefault((tier_cua(w, aid), a.lang), []).append(aid)
        batch_max = int(w.cfg.get("minds.batch_toi_da"))
        g_xao = w.rng.get("batch_xao", w.tick)
        cac_batch: list[tuple[str, list[str]]] = []
        for (tier, _lang), ids in sorted(theo_nhom.items()):
            ids = list(ids)
            g_xao.shuffle(ids)
            for i in range(0, len(ids), batch_max):
                cac_batch.append((tier, ids[i:i + batch_max]))

        # hook ngân sách (real: budget guard; mock: luôn đủ)
        if not self._du_ngan_sach(w, cac_batch):
            self.het_ngan_sach = True
            for aid in sorted(triggers):
                if w.chu_the_hoat_dong(aid) and aid not in ke_hoach:
                    ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, da_nham)
            cac_batch = []

        for tier, ids in cac_batch:
            self.so_nghi += len(ids)
            prompt = build_batch_prompt(w, ids, triggers)
            req = LLMRequest(prompt=prompt, ctx=ctx, tier=tier, batch_ids=ids)
            resp = self.provider.goi(req, attempt=0)
            self.so_call += 1
            ok, hong = parse_batch(resp.text, ids)
            self.log.ghi(w.tick, req, resp, fallback=False)
            if hong:
                # retry 1 lần kèm lỗi validator (mock: sinh lại với attempt=1)
                req2 = LLMRequest(prompt=prompt + "\n[LỖI JSON — trả lại đúng schema]",
                                  ctx=ctx, tier=tier, batch_ids=hong)
                resp2 = self.provider.goi(req2, attempt=1)
                resp2.retries = 1
                self.so_call += 1
                ok2, hong2 = parse_batch(resp2.text, hong)
                ok.update(ok2)
                self.log.ghi(w.tick, req2, resp2, fallback=bool(hong2))
                for aid in hong2:  # fallback: giữ thẻ cũ, không hành động mới
                    self.so_fallback += 1
                    ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, da_nham)
            for aid, qd in ok.items():
                kh = quyet_dinh_thanh_ke_hoach(w, qd, thung_intent_la)
                if qd.the_chinh_sach is not None:
                    try:
                        the_moi = ap_patch(_the_cua(w, aid), qd.the_chinh_sach)
                        w.policy_cards[aid] = the_moi.model_dump()
                        kh.y_dinh_sinh_con = the_moi.y_dinh_sinh_con
                    except Exception as e:  # noqa: BLE001 — thẻ hỏng thì giữ thẻ cũ
                        w.ghi_unrecognized(aid, "the_chinh_sach", f"patch hỏng: {e}")
                ke_hoach[aid] = kh

        # --- bộ phiên dịch intent lạ (real: 1 call LLM; mock: log như cũ) ---
        if thung_intent_la:
            self._dich_intent_la(w, thung_intent_la, ke_hoach)

        # --- người không nghĩ: thẻ chính sách ---
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song or aid in ke_hoach:
                continue
            ke_hoach[aid] = thi_hanh_the(w, aid, _the_cua(w, aid), bc, da_nham)

        # --- entity: việc thường nhật chạy MỖI tick (thẻ của pháp nhân) ---
        from minds.rulebot import bo_sung_ke_hoach_entity

        bo_sung_ke_hoach_entity(w, ke_hoach, bc, da_nham)

        # --- nén hồi ký mỗi 4 tick (mock nén — heuristic, vẫn log call) ---
        if w.tick % 4 == 0:
            self._nen_hoi_ky(w)
        self.log.flush()
        return ke_hoach

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
