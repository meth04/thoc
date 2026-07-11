"""MindReal — orchestrator LLM THẬT: kế thừa trọn pipeline mock (trigger → batch →
prompt → repair → validate → fallback), chỉ thay provider bằng GatewayReal.

Khác mock ở ba điểm:
- RPM pacing: chờ slot thay vì fail (RPD cạn thật thì không chờ vô ích);
- budget guard mỗi tick: thiếu → dừng êm (het_ngan_sach=True), KHÔNG degrade tier;
- nén hồi ký mỗi 4 tick bằng LLM (route nen_hoi_ky), theo lô 8 người, hỏng thì
  rơi về bản nén heuristic.
"""

from __future__ import annotations

import time
from pathlib import Path

from engine.world import World
from minds.gateway import LLMRequest, LLMResponse
from minds.orchestrator import MindMock
from minds.providers_real import GatewayReal, LoiHetQuota, Route, budget_guard, che_key
from minds.quota import QuotaCounter
from minds.repair import sua_va_parse


class GatewayCoPacing:
    """Bọc GatewayReal: LoiHetQuota do nghẽn RPM → chờ rồi thử lại (tối đa cho_toi_s);
    RPD cạn thật → ném tiếp để tầng trên fallback/dừng."""

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
        self.ly_do_dung = ""

    # ---------- budget guard (điều luật #7: không degrade) ----------
    def _du_ngan_sach(self, w: World, cac_batch: list) -> bool:
        can: dict[str, int] = {}
        for tier, _ids in cac_batch:
            can[tier] = can.get(tier, 0) + 1
        # retry + nén hồi ký + chronicle ăn thêm ~40% cùng pool T0/T1
        if "T0" in can or "T1" in can:
            can["T1"] = can.get("T1", 0) + max(1, int(sum(can.values()) * 0.4))
        du, ly_do = budget_guard(self.gateway, can)
        if not du:
            self.ly_do_dung = ly_do
        return du

    # ---------- nén hồi ký bằng LLM (route nen_hoi_ky), lô 8 người ----------
    def _nen_hoi_ky(self, w: World) -> None:
        nen_cfg = self.cfg.get("models.nen_hoi_ky")
        q = self.cfg.raw()["quotas"][nen_cfg["provider"]]["models"].get(nen_cfg["model"], {})
        route = Route(nen_cfg["provider"], nen_cfg["model"],
                      int(q.get("rpm", 4)), int(q.get("rpd", 100)))
        nguoi_lon = [a for a in w.agents.values() if a.con_song and a.tuoi_nam >= 16]
        for i in range(0, len(nguoi_lon), 8):
            lo = nguoi_lon[i:i + 8]
            khoi = []
            for a in lo:
                thoc = w.ledger.so_du(a.id, "thoc")
                dat = sum(1 for p in w.parcels.values() if p.chu == a.id)
                khoi.append(
                    f"- {a.id}: {a.ten}, {a.tuoi_nam:.0f} tuổi, E{a.e_bac}, "
                    f"{len(a.con)} con, {thoc:.0f}kg thóc, {dat} thửa. "
                    f"Hồi ký cũ: {a.hoi_ky or '(trống)'}"
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

    def _goi_nen_co_cho(self, req: LLMRequest, route: Route) -> LLMResponse:
        """Gọi route nền, chờ slot RPM tối đa ~30s (nén rơi về heuristic nếu kẹt)."""
        from minds.providers_real import LoiRateLimit

        han = time.time() + 30.0
        while True:
            try:
                return self.gateway._goi_route(req, route, {"temperature": 0.6,
                                                            "max_output_tokens": 1200})
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
