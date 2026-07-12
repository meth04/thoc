"""MindReal — orchestrator LLM THẬT: kế thừa trọn pipeline mock (trigger → batch →
prompt → repair → validate → fallback), chỉ thay provider bằng GatewayReal.

Khác mock ở ba điểm:
- RPM pacing: chờ slot thay vì fail (RPD cạn thật thì không chờ vô ích);
- budget guard mỗi tick: thiếu → dừng êm (het_ngan_sach=True), KHÔNG degrade tier;
- nén hồi ký mỗi 4 tick bằng LLM (route nen_hoi_ky), theo lô 8 người, hỏng thì
  rơi về bản nén heuristic.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from engine.world import World
from minds.gateway import LLMRequest, LLMResponse
from minds.orchestrator import MindMock, tier_cua
from minds.providers_real import (
    GatewayReal,
    LoiHetQuota,
    LoiProviderHong,
    Route,
    budget_guard,
    che_key,
)
from minds.quota import QuotaCounter
from minds.repair import sua_va_parse


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
        han = time.time() + self.cho_toi_s
        while True:
            try:
                return self.gw.goi(req)
            except LoiProviderHong:
                raise  # lỗi HTTP dai dẳng dù RPD còn — chờ slot RPM là vô ích
            except LoiHetQuota:
                if not self._con_rpd(req.tier) or time.time() >= han:
                    raise
                time.sleep(3.0)  # nghẽn RPM/cooldown tạm thời — chờ slot


class MindReal(MindMock):
    def __init__(self, w: World, run_dir: Path, cfg, env, quota_db: Path,
                 transport=None, cho_toi_s: float = 180.0):
        super().__init__(w, fast=True, run_dir=run_dir, p_malformed=0.0)
        self.cfg = cfg
        self.env = env
        self.quota = QuotaCounter(
            quota_db, reset_hour=int(cfg.get("quotas.chung.reset_hour_local"))
        )
        self.gateway = GatewayReal(cfg, env, self.quota, transport=transport)
        self.provider = GatewayCoPacing(self.gateway, cho_toi_s=cho_toi_s)
        self._tuan_tu = False  # real: fan-out song song per-agent (bất đối xứng thông tin)
        self.ly_do_dung = ""
        # bộ phiên dịch intent: loại đã hỏi mà LLM cũng bó tay → không hỏi lại (đỡ call)
        self._loai_bo_tay: set[str] = set()

    # ---------- budget guard (điều luật #7: không degrade) ----------
    def _du_ngan_sach(self, w: World, thinkers: list) -> bool:
        # 1-to-1: MỖI người nghĩ = 1 call (theo tier của họ)
        can: dict[str, int] = {}
        for aid in thinkers:
            tier = tier_cua(w, aid)
            can[tier] = can.get(tier, 0) + 1
        # mỗi call có thể phải retry-parse đúng 1 lần → nhu cầu tối đa ×2 (cấu trúc
        # pipeline: 1 call chính + 1 call retry, không phải tham số chỉnh được)
        for tier in list(can):
            can[tier] *= 2
        du, ly_do = budget_guard(self.gateway, can)
        if not du:
            self.ly_do_dung = ly_do
            return False
        # route NỀN (nen_hoi_ky) kiểm riêng theo đúng (provider, model), không gộp T1:
        # +1 call dịch intent lạ (chỉ khi có người nghĩ) + ceil(người_lớn/8) call nén
        # hồi ký đúng chu kỳ 4 tick (khớp orchestrator `w.tick % 4 == 0`)
        tt = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        can_nen = 1 if thinkers else 0
        if w.tick % 4 == 0:
            so_nguoi_lon = sum(
                1 for a in w.agents.values() if a.con_song and a.tuoi_nam >= tt
            )
            can_nen += math.ceil(so_nguoi_lon / 8)
        if can_nen > 0:
            route = self._route_nen()
            con = self.gateway.con_lai(route, time.time())
            safety = float(self.cfg.get("quotas.chung.safety_margin"))
            if con * safety < can_nen:
                self.ly_do_dung = (f"route nền {route.provider}/{route.model}: "
                                   f"cần {can_nen} call, còn {con} (×{safety})")
                return False
        return True

    def _route_nen(self) -> Route:
        """Route việc nền (nén hồi ký + dịch intent) — đọc từ models.nen_hoi_ky."""
        nen_cfg = self.cfg.get("models.nen_hoi_ky")
        q = self.cfg.raw()["quotas"][nen_cfg["provider"]]["models"].get(nen_cfg["model"], {})
        return Route(nen_cfg["provider"], nen_cfg["model"],
                     int(q.get("rpm", 4)), int(q.get("rpd", 100)))

    # ---------- nén hồi ký bằng LLM (route nen_hoi_ky), lô 8 người ----------
    def _nen_hoi_ky(self, w: World) -> None:
        route = self._route_nen()
        tt = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        nguoi_lon = [a for a in w.agents.values() if a.con_song and a.tuoi_nam >= tt]
        for i in range(0, len(nguoi_lon), 8):
            lo = nguoi_lon[i:i + 8]
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
                f"Năm {w.tick // 2}. Nén hồi ký cho từng người dưới đây thành ≤2 câu "
                f"tiếng Việt (ngôi thứ nhất, giữ chi tiết đắt giá nhất của hồi ký cũ "
                f"+ hiện trạng).\n" + "\n".join(khoi) +
                '\nTrả về DUY NHẤT một JSON object: {"<id>": "<hồi ký mới>", ...}'
            )
            req = LLMRequest(prompt=prompt, ctx={}, tier="T1",
                             batch_ids=[a.id for a in lo])
            try:
                resp = self._goi_nen_co_cho(req, route)
                self.gateway.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                            time.time())
                self.so_call += 1
                self.log.ghi(w.tick, req, resp, fallback=False)
                du_lieu = sua_va_parse(resp.text)
                d = du_lieu[0] if du_lieu else {}
                gioi_han = int(w.cfg.get("minds.hoi_ky_token_toi_da")) * 4
                for a in lo:
                    if isinstance(d.get(a.id), str) and d[a.id].strip():
                        a.hoi_ky = d[a.id].strip()[:gioi_han]
                    else:
                        self._nen_heuristic(w, a)
            except Exception as e:  # noqa: BLE001 — nén hỏng thì dùng heuristic, không chết run
                w.events.ghi(w.tick, "nen_hoi_ky_loi", loi=che_key(str(e))[:200])
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
        # trần an toàn cho 1 call — phần bị cắt vẫn phải có vết (điều luật #6)
        for aid, d, ly_do in hoi[40:]:
            w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)
        hoi = hoi[:40]

        from minds.prompts import SCHEMA_QUYET_DINH

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
            + "\n\n" + SCHEMA_QUYET_DINH
            + '\n\nTrả về DUY NHẤT mảng JSON: [{"stt": 0, "hanh_dong": [...]}, ...] '
              "đủ mọi stt."
        )
        route = self._route_nen()
        req = LLMRequest(prompt=prompt, ctx={}, tier="T1",
                         batch_ids=[aid for aid, _d, _l in hoi])
        try:
            resp = self._goi_nen_co_cho(req, route)
            self.gateway.quota.ghi_call(route.provider, route.model, resp.key_hash,
                                        time.time())
            self.so_call += 1
            self.log.ghi(w.tick, req, resp, fallback=False)
            ket_qua = {int(x.get("stt", -1)): x.get("hanh_dong", [])
                       for x in sua_va_parse(resp.text) if isinstance(x, dict)}
        except Exception as e:  # noqa: BLE001 — dịch hỏng thì bỏ như cũ, không chết run
            w.events.ghi(w.tick, "dich_intent_loi", loi=che_key(str(e))[:200])
            ket_qua = {}
        for i, (aid, d, ly_do) in enumerate(hoi):
            anh_xa = ket_qua.get(i) or []
            da_ap = 0
            for hd_moi in anh_xa[:3]:
                try:
                    _mot_hanh_dong(w, ke_hoach[aid], HanhDong.model_validate(hd_moi))
                    da_ap += 1
                except Exception:  # noqa: BLE001
                    continue
            if da_ap:
                w.events.ghi(w.tick, "intent_duoc_dich", ai=aid,
                             goc=str(d.get("loai")), so_hanh_dong=da_ap)
            else:
                self._loai_bo_tay.add(str(d.get("loai")))
                w.ghi_unrecognized(aid, str(d.get("loai")), ly_do)

    def _goi_nen_co_cho(self, req: LLMRequest, route: Route) -> LLMResponse:
        """Gọi route nền, chờ slot RPM tối đa ~30s (nén rơi về heuristic nếu kẹt).
        Tham số sampling đọc từ models.nen_hoi_ky (CLAUDE.md §5 — không hardcode)."""
        from minds.providers_real import LoiRateLimit

        nen_cfg = self.cfg.get("models.nen_hoi_ky")
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
        a.hoi_ky = (f"Năm {w.tick // 2}: {a.tuoi_nam:.0f} tuổi, {len(a.con)} con, "
                    f"{thoc:.0f}kg thóc, {dat} thửa đất, học vấn E{a.e_bac}.")


def tao_mind_real(w: World, run_dir: Path, cfg, env, quota_db: Path,
                  transport=None) -> MindReal:
    return MindReal(w, run_dir, cfg, env, quota_db, transport=transport)
