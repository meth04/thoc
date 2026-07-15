"""MindReal — orchestrator LLM THẬT: kế thừa trọn pipeline mock (trigger → 1-to-1 →
prompt → repair → validate → fallback), chỉ thay provider bằng GatewayReal.

Khác mock ở ba điểm:
- RPM pacing: chờ slot thay vì fail (RPD cạn thật thì không chờ vô ích);
- budget guard mỗi tick: thiếu → dừng êm (het_ngan_sach=True), KHÔNG degrade tier;
- nén hồi ký mỗi 4 tick bằng LLM; khi autonomy treatment bật, mỗi agent có
  request riêng và không bị dồn vào batch.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from engine.world import World
from minds.gateway import LLMRequest, LLMResponse
from minds.orchestrator import MindMock, tier_cua
from minds.provenance import record_action
from minds.providers_real import (
    GatewayReal,
    LoiHetQuota,
    LoiProviderHong,
    Route,
    budget_guard,
    burst_guard,
    che_key,
)
from minds.quota import QuotaCounter
from minds.repair import sua_va_parse
from minds.tick_budget import LoiVuotNganSachTick, cau_hinh_ngan_sach


def _stt_dich_hop_le(row: object) -> int | None:
    """Đọc số thứ tự của một hàng translator mà không tin dữ liệu LLM.

    ``sua_va_parse`` chỉ khôi phục được JSON thành cấu trúc Python; nó không
    biến một giá trị như ``\"một\"`` hay ``null`` thành số nguyên.  Translator là
    nhánh phục hồi lỗi, vì vậy một ``stt`` dị dạng phải đơn giản bị bỏ qua thay
    vì làm chết toàn bộ tick kinh tế.
    """
    if not isinstance(row, dict):
        return None
    value = row.get("stt", -1)
    # ``bool`` là subclass của int trong Python nhưng không phải một chỉ mục
    # người dùng hợp lệ trong protocol JSON này.
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


class GatewayCoPacing:
    """Bọc GatewayReal: LoiHetQuota do nghẽn RPM → chờ rồi thử lại (tối đa cho_toi_s);
    RPD cạn thật / provider hỏng dai dẳng → ném tiếp để tầng trên fallback/dừng êm."""

    def __init__(self, gw: GatewayReal, cho_toi_s: float = 180.0):
        self.gw = gw
        self.cho_toi_s = cho_toi_s

    def _con_rpd(self, tier: str) -> bool:
        now = time.time()
        return any(self.gw.con_lai(r, now) > 0 for r in self.gw.routes_cua_tier(tier))

    def goi(self, req: LLMRequest, attempt: int = 0) -> LLMResponse:
        return self._cho_slot(lambda: self.gw.goi(req), req.tier)

    def goi_agentic(self, req: LLMRequest, w, aid: str) -> LLMResponse:
        """Vòng công cụ MCP với pacing (chờ slot RPM như goi)."""
        return self._cho_slot(lambda: self.gw.goi_agentic(req, w, aid), req.tier)

    def _cho_slot(self, ham, tier: str) -> LLMResponse:
        han = time.time() + self.cho_toi_s
        while True:
            try:
                return ham()
            except LoiProviderHong:
                raise  # lỗi HTTP dai dẳng dù RPD còn — chờ slot RPM là vô ích
            except LoiHetQuota:
                if not self._con_rpd(tier) or time.time() >= han:
                    raise
                time.sleep(3.0)  # nghẽn RPM/cooldown tạm thời — chờ slot


class MindReal(MindMock):
    def __init__(self, w: World, run_dir: Path | None, cfg, env, quota_db: Path | None,
                 transport=None, cho_toi_s: float = 180.0,
                 transcript_path: Path | None = None):
        super().__init__(w, fast=True, run_dir=run_dir, p_malformed=0.0,
                         transcript_path=transcript_path)
        self.cfg = cfg
        self.env = env
        self.quota = QuotaCounter(
            quota_db, reset_hour=int(cfg.get("quotas.chung.reset_hour_local"))
        )
        self.gateway = GatewayReal(cfg, env, self.quota, transport=transport)
        self.provider = GatewayCoPacing(self.gateway, cho_toi_s=cho_toi_s)
        self._tuan_tu = False  # real: fan-out song song per-agent (bất đối xứng thông tin)
        # trần đồng thời TỰ CO GIÃN theo số key (nhiều key → chạy song song nhiều hơn),
        # chặn trên bởi minds.concurrency
        self.concurrency = self.gateway.concurrency_de_xuat(int(cfg.get("minds.concurrency")))
        self.ly_do_dung = ""
        # bộ phiên dịch intent: loại đã hỏi mà LLM cũng bó tay → không hỏi lại (đỡ call)
        self._loai_bo_tay: set[str] = set()

    def kiem_tra_truoc_tick(self, w: World) -> bool:
        """Preflight không-mutation cho run đầy đủ autonomy.

        ``run.py`` gọi hook này trước ``chay_mot_tick``.  Vì vậy một thiếu hụt
        RPM không thể âm thầm biến tick bắt buộc-LLM thành một tick policy-card
        rồi mới dừng.  Người sắp đủ tuổi trong bước tuổi đầu tick cũng được
        tính trước, nên headcount khớp đúng danh sách thinker sau đó.
        """
        self._cfg_ngan_sach_tick = cau_hinh_ngan_sach(w.cfg)
        if not (self._cfg_ngan_sach_tick.get("bat", False)
                and self._cfg_ngan_sach_tick.get("kiem_tra_burst_rpm", False)):
            return True
        tuoi_truong_thanh = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        buoc_tuoi_nam = 1.0 / float(w.tick_moi_nam())
        thinkers = [
            aid for aid in sorted(w.agents)
            if w.agents[aid].con_song
            and w.agents[aid].tuoi_nam + buoc_tuoi_nam >= tuoi_truong_thanh
        ]
        if not thinkers or self._du_ngan_sach(w, thinkers):
            return True
        self.het_ngan_sach = True
        return False

    # ---------- budget guard (điều luật #7: không degrade) ----------
    def _du_ngan_sach(self, w: World, thinkers: list) -> bool:
        # The run must be able to honour the *minimum* independent turn of
        # every autonomous resident. Optional retries/tool turns are bounded
        # per resident later; requiring 10× here would falsely halt a viable
        # expensive run before its first 1-to-1 decision.
        can: dict[str, int] = {}
        # Legacy mode keeps its historic conservative guard (primary response
        # plus one JSON-repair attempt). The new per-agent treatment guards
        # only the contractual minimum turn, then lets optional turns consume
        # each resident's own cap at runtime.
        toi_thieu = (
            int(self._cfg_ngan_sach_tick.get("toi_thieu", 1))
            if self._cfg_ngan_sach_tick.get("bat", False) else 2
        )
        for aid in thinkers:
            tier = tier_cua(w, aid)
            can[tier] = can.get(tier, 0) + toi_thieu
        du, ly_do = budget_guard(self.gateway, can)
        if not du:
            self.ly_do_dung = ly_do
            return False
        if (self._cfg_ngan_sach_tick.get("bat", False)
                and self._cfg_ngan_sach_tick.get("kiem_tra_burst_rpm", False)):
            du_burst, ly_do_burst = burst_guard(self.gateway, can)
            if not du_burst:
                self.ly_do_dung = ly_do_burst
                return False
        if not self._cfg_ngan_sach_tick.get("bat", False):
            # Preserve the legacy treatment's all-or-stop contract, including
            # the old batched background route. The autonomy treatment below
            # deliberately treats these extra per-agent calls as optional.
            tt = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
            so_nguoi_lon = sum(
                1 for a in w.agents.values() if a.con_song and a.tuoi_nam >= tt
            )
            can_nen = 1 if thinkers else 0
            if w.tick % 4 == 0:
                can_nen += math.ceil(so_nguoi_lon / 8)
            if w.tick % int(w.cfg.get("minds.reflection_moi_n_tick")) == 0:
                can_nen += math.ceil(so_nguoi_lon / 8)
            if can_nen > 0:
                route = self._route_nen()
                con = self.gateway.con_lai(route, time.time())
                safety = float(self.cfg.get("quotas.chung.safety_margin"))
                if con * safety < can_nen:
                    self.ly_do_dung = (f"route nền {route.provider}/{route.model}: "
                                        f"cần {can_nen} call, còn {con} (×{safety})")
                    return False
        # Memory, reflection and intent translation are opportunistic.  They
        # share the per-tick cap later and may fall back locally; they must not
        # stop an economic run merely because a non-decision convenience call
        # cannot be afforded.
        return True

    def _route_nen(self) -> Route:
        """Route việc nền (nén hồi ký + dịch intent) — đọc từ models.nen_hoi_ky."""
        if getattr(self.gateway, "strict_treatment", False):
            # Thí nghiệm treatment phải giữ cùng provider/model cho cả call nền; nếu không
            # reflection/memory có thể vô tình dùng một "bộ não" khác với quyết định chính.
            return self.gateway.routes_cua_tier("T0")[0]
        nen_cfg = self.cfg.get("models.nen_hoi_ky")
        q = self.cfg.raw()["quotas"][nen_cfg["provider"]]["models"].get(nen_cfg["model"], {})
        return Route(nen_cfg["provider"], nen_cfg["model"],
                     int(q.get("rpm", 4)), int(q.get("rpd", 100)))

    # ---------- nén hồi ký bằng LLM (route nen_hoi_ky) ----------
    def _nen_hoi_ky(self, w: World) -> None:
        if (self._ngan_sach_tick is not None
                and not bool(self._cfg_ngan_sach_tick.get("goi_ho_tro", False))):
            # Every resident already receives an independent economic decision
            # call this tick. Keep compression local by default so 50 required
            # decisions do not become an accidental 100-call burst merely for
            # background prose. It can be enabled as an explicit treatment.
            super()._nen_hoi_ky(w)
            return
        route = self._route_nen()
        tt = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        nguoi_lon = [a for a in w.agents.values() if a.con_song and a.tuoi_nam >= tt]
        # Legacy/replay treatment keeps the old batch path. The autonomy
        # treatment has one request per resident, so a person's private memory
        # is never folded into another person's LLM call.
        cac_lo = ([[a] for a in nguoi_lon] if self._ngan_sach_tick is not None
                  else [nguoi_lon[i:i + 8] for i in range(0, len(nguoi_lon), 8)])
        for lo in cac_lo:
            khoi = []
            for a in lo:
                thoc = w.ledger.so_du(a.id, "thoc")
                dat = sum(1 for p in w.parcels.values() if p.chu == a.id)
                khoi.append(
                    f"- {a.id}: {a.ten}, {a.tuoi_nam:.0f} tuổi, E{a.e_bac}, "
                    f"{len(a.con)} con, {thoc:.0f}kg thóc, {dat} thửa. "
                    f"Hồi ký cũ: {a.hoi_ky or '(trống)'}. "
                    f"Biến cố gần đây: {a.ky_uc[-4:] or '(không)'}"
                )
            prompt = (
                f"Năm {w.nam()}. Nén hồi ký cho từng người dưới đây thành ≤2 câu "
                f"tiếng Việt (ngôi thứ nhất, giữ chi tiết đắt giá nhất của hồi ký cũ "
                f"+ hiện trạng).\n" + "\n".join(khoi) +
                '\nTrả về DUY NHẤT một JSON object: {"<id>": "<hồi ký mới>", ...}'
            )
            req = LLMRequest(
                prompt=prompt, ctx={}, tier="T1", batch_ids=[a.id for a in lo],
                tick_budget=self._ngan_sach_tick,
                logical_id=(f"agent:{lo[0].id}" if self._ngan_sach_tick is not None
                            else f"memory:{w.tick}:{lo[0].id}"),
                logical_kind="memory",
                max_api_calls=(int(self._cfg_ngan_sach_tick["toi_da"])
                               if self._ngan_sach_tick is not None else 1),
            )
            try:
                resp = self._goi_nen_co_cho(req, route)
                self.gateway.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                            time.time())
                self.so_call += 1
                self._ghi_log(w, req, resp, False)
                du_lieu = sua_va_parse(resp.text)
                d = du_lieu[0] if du_lieu else {}
                gioi_han = int(w.cfg.get("minds.hoi_ky_token_toi_da")) * 4
                for a in lo:
                    if isinstance(d.get(a.id), str) and d[a.id].strip():
                        a.hoi_ky = d[a.id].strip()[:gioi_han]
                    else:
                        self._nen_heuristic(w, a)
            except LoiVuotNganSachTick:
                for a in lo:
                    self._nen_heuristic(w, a)
            except Exception as e:  # noqa: BLE001 — nén hỏng thì dùng heuristic, không chết run
                w.events.ghi(w.tick, "nen_hoi_ky_loi", loi=che_key(str(e))[:200])
                # Call hỏng CŨNG phải vào transcript (ADR 0006 §C.4): replay sẽ gọi lại
                # route nền này và tra transcript; không có row ⇒ miss ⇒ trượt cổng hard
                # `misses == 0` dù artifact hoàn toàn sạch. Lỗi là một NHÁNH ĐIỀU KHIỂN có
                # tác dụng (rơi về heuristic), không phải dữ liệu thiếu.
                self._ghi_call_loi(w, req, e)
                for a in lo:
                    self._nen_heuristic(w, a)

    # ---------- bộ phiên dịch intent lạ: gom cả tick vào MỘT call model rẻ ----------
    def _dich_intent_la(self, w: World, thung: list, ke_hoach: dict) -> None:
        """LLM trả hành động không có trong 15 nguyên tố / sai tham số → thử ÁNH XẠ về
        văn phạm hợp lệ bằng 1 call (model rẻ nhất). Tiết kiệm request:
        (1) gom mọi intent lạ của tick vào một call; (2) loại đã bó tay thì cache,
        không hỏi lại; (3) tick không có intent lạ → 0 call. Kết quả ánh xạ vẫn đi
        qua validator engine như thường — an toàn không đổi."""
        from minds.schemas import HanhDong
        from minds.translate import _mot_hanh_dong

        hoi, bo = [], []
        for aid, d, ly_do in thung:
            loai = str(d.get("loai"))
            if loai in self._loai_bo_tay or aid not in ke_hoach:
                bo.append((aid, d, ly_do))
            else:
                hoi.append((aid, d, ly_do))
        for aid, d, ly_do in bo:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)
        if not hoi:
            return
        if self._ngan_sach_tick is not None:
            # Full-autonomy treatment forbids a convenience batch that puts
            # several residents' intentions in one model request. Each repair
            # is a private continuation of that resident's own 1..N budget.
            for aid, d, ly_do in hoi:
                self._dich_intent_la_mot_nguoi(w, aid, d, ly_do, ke_hoach)
            return
        # trần an toàn cho 1 call — phần bị cắt vẫn phải có vết (điều luật #6)
        for aid, d, ly_do in hoi[40:]:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)
        hoi = hoi[:40]

        from minds.prompts import schema_quyet_dinh_cho

        muc = [
            {"stt": i, "cua": aid, "y_dinh": d, "vi_sao_bi_tu_choi": ly_do}
            for i, (aid, d, ly_do) in enumerate(hoi)
        ]
        prompt = (
            "Các cư dân (agent) đã ra những Ý ĐỊNH dưới đây nhưng engine không nhận diện "
            "được. Hãy DỊCH từng ý định về (các) hành động hợp lệ trong văn phạm — giữ "
            "đúng tinh thần của ý định, dùng đúng id/tham số có trong ý định gốc. Không "
            "dịch nổi thì trả mảng rỗng.\n\n"
            + json.dumps(muc, ensure_ascii=False, indent=1)
            + "\n\n" + schema_quyet_dinh_cho(w)  # menu render từ config/catalog của w
            + '\n\nTrả về DUY NHẤT mảng JSON: [{"stt": 0, "hanh_dong": [...]}, ...] '
              "đủ mọi stt."
        )
        route = self._route_nen()
        req = LLMRequest(
            prompt=prompt, ctx={}, tier="T1",
            batch_ids=[aid for aid, _d, _l in hoi],
            tick_budget=self._ngan_sach_tick,
            logical_id=f"translation:{w.tick}", logical_kind="translation",
            max_api_calls=1,
        )
        try:
            resp = self._goi_nen_co_cho(req, route)
            self.gateway.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                        time.time())
            self.so_call += 1
            self._ghi_log(w, req, resp, False)
            ket_qua = {}
            for x in sua_va_parse(resp.text) or []:
                stt = _stt_dich_hop_le(x)
                if stt is not None:
                    ket_qua[stt] = x.get("hanh_dong", [])
        except LoiVuotNganSachTick:
            ket_qua = {}
        except Exception as e:  # noqa: BLE001 — dịch hỏng thì bỏ như cũ, không chết run
            w.events.ghi(w.tick, "dich_intent_loi", loi=che_key(str(e))[:200])
            # Route nền THỨ BA (cùng bệnh _nen_hoi_ky/_reflection): call hỏng vẫn phải có
            # row transcript (ADR 0006 §C.4). Replay gọi lại ĐÚNG call này qua
            # TranscriptProvider; thiếu row ⇒ miss ⇒ trượt cổng hard `misses == 0` dù
            # artifact hoàn toàn sạch. Lỗi ở đây là NHÁNH ĐIỀU KHIỂN có tác dụng (mọi intent
            # lạ rơi về ghi_unrecognized), không phải dữ liệu thiếu.
            self._ghi_call_loi(w, req, e)
            ket_qua = {}
        for i, (aid, d, ly_do) in enumerate(hoi):
            anh_xa = ket_qua.get(i) or []
            da_ap = 0
            for hd_moi in anh_xa[:3]:
                try:
                    _mot_hanh_dong(w, ke_hoach[aid], HanhDong.model_validate(hd_moi))
                    target = hd_moi.get("thua", hd_moi.get("ref"))
                    record_action(w, aid, str(hd_moi.get("loai", "?")), "translator",
                                  target=str(target) if target not in (None, "") else None,
                                  detail=str(d.get("loai", "unknown")))
                    da_ap += 1
                except Exception:  # noqa: BLE001
                    continue
            if da_ap:
                w.events.ghi(w.tick, "intent_duoc_dich", ai=aid,
                             goc=str(d.get("loai")), so_hanh_dong=da_ap)
            else:
                self._loai_bo_tay.add(str(d.get("loai")))
                w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)

    def _dich_intent_la_mot_nguoi(self, w: World, aid: str, d: dict, ly_do: str,
                                  ke_hoach: dict) -> None:
        """Dịch một intent lạ bằng một request riêng của chính agent đó."""
        from minds.prompts import schema_quyet_dinh_cho
        from minds.schemas import HanhDong
        from minds.translate import _mot_hanh_dong

        loai = str(d.get("loai"))
        if loai in self._loai_bo_tay or aid not in ke_hoach:
            w.ghi_unrecognized(aid, loai, ly_do)
            return
        muc = {"stt": 0, "cua": aid, "y_dinh": d, "vi_sao_bi_tu_choi": ly_do}
        prompt = (
            "Bạn đang giúp DUY NHẤT cư dân này diễn đạt lại ý định của chính họ. "
            "Engine không nhận diện ý định gốc; hãy dịch nó về các hành động hợp lệ, "
            "giữ đúng tinh thần và chỉ dùng id/tham số có trong ý định. Không dịch nổi "
            "thì trả mảng rỗng.\n\n"
            + json.dumps(muc, ensure_ascii=False, indent=1)
            + "\n\n" + schema_quyet_dinh_cho(w)
            + '\n\nTrả về DUY NHẤT mảng JSON: [{"stt": 0, "hanh_dong": [...]}].'
        )
        route = self._route_nen()
        req = LLMRequest(
            prompt=prompt, ctx={}, tier="T1", batch_ids=[aid],
            tick_budget=self._ngan_sach_tick, logical_id=f"agent:{aid}",
            logical_kind="translation",
            max_api_calls=int(self._cfg_ngan_sach_tick["toi_da"]),
        )
        try:
            resp = self._goi_nen_co_cho(req, route)
            self.gateway.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                        time.time())
            self.so_call += 1
            self._ghi_log(w, req, resp, False)
            rows = sua_va_parse(resp.text) or []
            row = next((x for x in rows if _stt_dich_hop_le(x) == 0), {})
            anh_xa = row.get("hanh_dong", []) if isinstance(row, dict) else []
        except LoiVuotNganSachTick:
            anh_xa = []
        except Exception as e:  # noqa: BLE001 — lỗi dịch không được phá tick kinh tế
            w.events.ghi(w.tick, "dich_intent_loi", loi=che_key(str(e))[:200])
            self._ghi_call_loi(w, req, e)
            anh_xa = []

        da_ap = 0
        for hd_moi in (anh_xa if isinstance(anh_xa, list) else [])[:3]:
            try:
                _mot_hanh_dong(w, ke_hoach[aid], HanhDong.model_validate(hd_moi))
                target = hd_moi.get("thua", hd_moi.get("ref"))
                record_action(w, aid, str(hd_moi.get("loai", "?")), "translator",
                              target=str(target) if target not in (None, "") else None,
                              detail=loai)
                da_ap += 1
            except Exception:  # noqa: BLE001 — translator vẫn phải qua validator engine
                continue
        if da_ap:
            w.events.ghi(w.tick, "intent_duoc_dich", ai=aid, goc=loai, so_hanh_dong=da_ap)
        else:
            self._loai_bo_tay.add(loai)
            w.ghi_unrecognized(aid, loai, ly_do)

    def _goi_nen_co_cho(self, req: LLMRequest, route: Route) -> LLMResponse:
        """Gọi route nền, chờ slot RPM tối đa ~30s (nén rơi về heuristic nếu kẹt).
        Tham số sampling đọc từ models.nen_hoi_ky (CLAUDE.md §5 — không hardcode)."""
        from minds.providers_real import LoiRateLimit

        nen_cfg = (
            getattr(self.gateway, "strict_treatment_cfg", {})
            if getattr(self.gateway, "strict_treatment", False)
            else self.cfg.get("models.nen_hoi_ky")
        )
        cau_hinh = {"temperature": float(nen_cfg["temperature"]),
                    "max_output_tokens": int(nen_cfg["max_output_tokens"])}
        han = time.time() + 30.0
        while True:
            try:
                return self.gateway._goi_route(req, route, cau_hinh)
            except LoiRateLimit:
                if time.time() >= han:
                    raise
                time.sleep(3.0)

    def _nen_heuristic(self, w: World, a) -> None:
        thoc = w.ledger.so_du(a.id, "thoc")
        dat = sum(1 for p in w.parcels.values() if p.chu == a.id)
        a.hoi_ky = (f"Năm {w.nam()}: {a.tuoi_nam:.0f} tuổi, {len(a.con)} con, "
                    f"{thoc:.0f}kg thóc, {dat} thửa đất, học vấn E{a.e_bac}.")

    # ---------- tự phản tư bằng LLM (route nền) ----------
    def _reflection(self, w: World) -> None:
        """REAL: LLM cô đọng ký ức + ân oán thành 'niềm tin cốt lõi' (≤2 câu); hỏng thì
        rơi về phản tư heuristic của lớp cha. Uy tín xã hội tự phát từ trí nhớ (5.3)."""
        if (self._ngan_sach_tick is not None
                and not bool(self._cfg_ngan_sach_tick.get("goi_ho_tro", False))):
            super()._reflection(w)
            return
        route = self._route_nen()
        tt = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        nguoi_lon = [a for a in w.agents.values() if a.con_song and a.tuoi_nam >= tt]
        cac_lo = ([[a] for a in nguoi_lon] if self._ngan_sach_tick is not None
                  else [nguoi_lon[i:i + 8] for i in range(0, len(nguoi_lon), 8)])
        for lo in cac_lo:
            khoi = []
            for a in lo:
                than, oan = self._nguoi_than_va_oan(w, a.id)
                khoi.append(
                    f"- {a.id} ({a.ten}): dấu mốc đời={a.ky_uc_doi[-4:] or '(không)'}; "
                    f"chuyện gần đây={a.ky_uc[-4:] or '(không)'}; "
                    f"thân với={[w.agents[n].ten for _v, n in than] or '(không)'}; "
                    f"oán/đề phòng={[w.agents[n].ten for _v, n in oan] or '(không)'}"
                )
            prompt = (
                f"Năm {w.nam()}. Với TỪNG người dưới đây, viết 'niềm tin cốt lõi' của họ "
                f"về người đời (≤2 câu, ngôi thứ nhất): ai đáng tin, ai phải đề phòng và VÌ "
                f"SAO, rút từ ký ức + ân oán của họ.\n" + "\n".join(khoi) +
                '\nTrả về DUY NHẤT một JSON object: {"<id>": "<niềm tin>", ...}'
            )
            req = LLMRequest(
                prompt=prompt, ctx={}, tier="T1", batch_ids=[a.id for a in lo],
                tick_budget=self._ngan_sach_tick,
                logical_id=(f"agent:{lo[0].id}" if self._ngan_sach_tick is not None
                            else f"reflection:{w.tick}:{lo[0].id}"),
                logical_kind="reflection",
                max_api_calls=(int(self._cfg_ngan_sach_tick["toi_da"])
                               if self._ngan_sach_tick is not None else 1),
            )
            try:
                resp = self._goi_nen_co_cho(req, route)
                self.gateway.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                            time.time())
                self.so_call += 1
                self._ghi_log(w, req, resp, False)
                du_lieu = sua_va_parse(resp.text)
                d = du_lieu[0] if du_lieu else {}
                for a in lo:
                    if isinstance(d.get(a.id), str) and d[a.id].strip():
                        a.niem_tin = d[a.id].strip()[:300]
                    else:
                        self._reflection_mot_nguoi(w, a)
            except LoiVuotNganSachTick:
                for a in lo:
                    self._reflection_mot_nguoi(w, a)
            except Exception as e:  # noqa: BLE001 — hỏng thì heuristic, không chết run
                w.events.ghi(w.tick, "reflection_loi", loi=che_key(str(e))[:200])
                # Như _nen_hoi_ky: lỗi route nền phải có row transcript, nếu không replay
                # sẽ miss ở đúng call này (ADR 0006 §C.4).
                self._ghi_call_loi(w, req, e)
                for a in lo:
                    self._reflection_mot_nguoi(w, a)


def tao_mind_real(w: World, run_dir: Path, cfg, env, quota_db: Path,
                  transport=None, transcript_path: Path | None = None) -> MindReal:
    return MindReal(w, run_dir, cfg, env, quota_db, transport=transport,
                    transcript_path=transcript_path)
