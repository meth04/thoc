"""World — toàn bộ trạng thái mô phỏng, truyền tường minh, không global."""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.config import Config
from engine.events import EventLog
from engine.ledger import Ledger
from engine.rng import RngTree
from engine.types import Agent, Parcel, Persona, Village
from engine.worldmap import sinh_ban_do

# Chủ thể đặc biệt trong sổ cái
VO_THUA_NHAN = "VO_THUA_NHAN"  # tài sản không người thừa kế

HO_TEN = [
    "An", "Bình", "Cúc", "Dần", "Đào", "Gấm", "Hạnh", "Khang", "Lan", "Mận",
    "Nhài", "Ổi", "Phượng", "Quế", "Rồng", "Sen", "Tùng", "Út", "Vượng", "Xoan",
    "Yến", "Bưởi", "Chanh", "Dừa", "Đước", "Gạo", "Hồng", "Khế", "Lúa", "Mít",
]


@dataclass
class World:
    cfg: Config
    seed: int
    rng: RngTree
    tick: int = 0
    ledger: Ledger = field(default_factory=Ledger)
    agents: dict[str, Agent] = field(default_factory=dict)
    parcels: dict[str, Parcel] = field(default_factory=dict)
    villages: list[Village] = field(default_factory=list)
    thoi_tiet_nam: dict[int, str] = field(default_factory=dict)  # năm → loại
    _next_id: int = 0
    events: EventLog = field(default_factory=lambda: EventLog(None))
    metrics_lich_su: list[dict[str, Any]] = field(default_factory=list)
    # đề nghị cầu hôn chờ trả lời tick sau: (tu, den, tick_gui)
    cau_hon_cho: list[tuple[str, str, int]] = field(default_factory=list)
    # uy tín / quan hệ xã hội: (a,b) → trọng số (âm = ân oán)
    quan_he: dict[tuple[str, str], float] = field(default_factory=dict)
    # ---- Phase 2: hợp đồng, bảng rao, chợ ----
    hop_dong: dict = field(default_factory=dict)  # id → HopDong (đang hiệu lực)
    hop_dong_xong: dict = field(default_factory=dict)  # lưu trữ hợp đồng đã kết thúc
    bang_rao: dict = field(default_factory=dict)  # id → DeNghi
    _next_hd: int = 0
    _next_dn: int = 0
    gia_lich_su: dict[str, list] = field(default_factory=dict)  # tài sản → [(tick, giá, kl)]
    gat_tick: dict[str, tuple[str, float]] = field(default_factory=dict)  # thửa → (ai, kg)
    yeu_cau_rut_tick: dict[tuple[str, str], float] = field(default_factory=dict)
    niem_yet_dat: dict = field(default_factory=dict)  # thua → NiemYetDat
    chet_tick_truoc: set[str] = field(default_factory=set)
    unrecognized_path: Path | None = None
    # kho trạng thái của tầng minds (engine không đọc — chỉ mang theo checkpoint)
    policy_cards: dict[str, dict] = field(default_factory=dict)
    # ---- Phase 4: pháp nhân, R&D, tri thức ----
    entities: dict = field(default_factory=dict)  # id → Entity
    _next_entity: int = 0
    blueprints: dict = field(default_factory=dict)  # id → Blueprint
    _next_bp: int = 0
    diem_nc: dict[tuple[str, str], float] = field(default_factory=dict)
    ten_hang: dict[str, str] = field(default_factory=dict)  # mã hàng mới → tên LLM đặt
    tri_thuc: float = 0.0
    san_tri_thuc_tier: int = 0
    nhan_dinh_che: dict[str, list[str]] = field(default_factory=dict)  # nhãn → chủ thể
    milestones: list[dict] = field(default_factory=list)
    # thu nhập theo nguồn, cửa sổ 4 tick (observatory đọc để phân giai cấp)
    thu_nhap_tick: dict = field(default_factory=dict)  # aid → {nguon: quy thóc}
    thu_nhap_4: list = field(default_factory=list)  # 4 dict gần nhất
    kl_thanh_toan_tick: dict[str, float] = field(default_factory=dict)
    cong_dung_tick: dict[str, float] = field(default_factory=dict)
    cong_dung_4: list = field(default_factory=list)  # cửa sổ 4 tick (mùa mưa+khô)
    kl_thanh_toan_4: list = field(default_factory=list)

    def ghi_thu_nhap(self, aid: str, nguon: str, quy_thoc: float) -> None:
        if quy_thoc <= 0:
            return
        d = self.thu_nhap_tick.setdefault(aid, {})
        d[nguon] = d.get(nguon, 0.0) + quy_thoc

    # ---------- id ----------
    def id_moi(self) -> str:
        self._next_id += 1
        return f"A{self._next_id:04d}"

    # ---------- thời tiết ----------
    def thoi_tiet(self, tick: int) -> tuple[str, float]:
        """Thời tiết của năm chứa tick — ngẫu nhiên ngoại sinh DUY NHẤT, seeded theo năm."""
        nam = tick // 2
        if nam not in self.thoi_tiet_nam:
            tt = self.cfg.get("thoi_gian.thoi_tiet")
            g = self.rng.get("thoi_tiet", nam)
            loai = ["duoc_mua", "binh_thuong", "han_lu"]
            p = [tt[k]["p"] for k in loai]
            self.thoi_tiet_nam[nam] = str(g.choice(loai, p=p))
        loai_tt = self.thoi_tiet_nam[nam]
        return loai_tt, float(self.cfg.get("thoi_gian.thoi_tiet")[loai_tt]["he_so"])

    def mua_mua(self, tick: int | None = None) -> bool:
        t = self.tick if tick is None else tick
        return t % 2 == 1

    def chu_the_hoat_dong(self, cid: str) -> bool:
        """Người còn sống hoặc entity còn hoạt động."""
        a = self.agents.get(cid)
        if a is not None:
            return a.con_song
        e = self.entities.get(cid)
        return e is not None and e.con_hoat_dong

    # ---------- hợp đồng ----------
    def tim_hop_dong(self, hd_id: str):
        return self.hop_dong.get(hd_id) or self.hop_dong_xong.get(hd_id)

    # ---------- giá chợ ----------
    def ghi_gia(self, tai_san: str, gia_quy_thoc: float, khoi_luong: float,
                thanh_toan: str = "thoc") -> None:
        self.gia_lich_su.setdefault(tai_san, []).append(
            (self.tick, round(gia_quy_thoc, 6), round(khoi_luong, 6), thanh_toan)
        )

    def gia_gan_nhat(self, tai_san: str) -> float | None:
        ls = self.gia_lich_su.get(tai_san)
        return ls[-1][1] if ls else None

    def gia_tb_4_tick(self, tai_san: str) -> float | None:
        ls = self.gia_lich_su.get(tai_san)
        if not ls:
            return None
        gan = [x for x in ls if x[0] >= self.tick - 4]
        return sum(x[1] for x in gan) / len(gan) if gan else ls[-1][1]

    def ghi_unrecognized(self, ai: str, loai: str, ly_do: str) -> None:
        """Intent không hợp lệ → bỏ qua + log (điều luật #3) — mỏ 'ý định mới lạ'."""
        self.events.ghi(self.tick, "unrecognized_intent", ai=ai, intent=loai, ly_do=ly_do)
        if self.unrecognized_path is not None:
            with open(self.unrecognized_path, "a", encoding="utf-8") as f:
                json.dump({"tick": self.tick, "ai": ai, "intent": loai, "ly_do": ly_do}, f,
                          ensure_ascii=False)
                f.write("\n")

    # ---------- quan hệ ----------
    def cong_quan_he(self, a: str, b: str, delta: float) -> None:
        if a == b:
            return
        key = (min(a, b), max(a, b))
        self.quan_he[key] = self.quan_he.get(key, 0.0) + delta

    def uy_tin(self, a: str, b: str) -> float:
        return self.quan_he.get((min(a, b), max(a, b)), 0.0)

    # ---------- hộ gia đình ----------
    def ho_cua(self, aid: str) -> list[str]:
        """Hộ = bản thân + vợ/chồng + con chưa trưởng thành còn sống."""
        a = self.agents[aid]
        tt = self.cfg.get("nhan_khau.tuoi_truong_thanh")
        ho = [aid]
        if a.vo_chong and a.vo_chong in self.agents and self.agents[a.vo_chong].con_song:
            ho.append(a.vo_chong)
        for cid in a.con:
            c = self.agents.get(cid)
            if c and c.con_song and not c.truong_thanh(tt):
                ho.append(cid)
        return ho

    # ---------- world hash (điều luật #4) ----------
    def world_hash(self) -> str:
        agents_s = sorted(
            (
                a.id, a.ten, a.gioi_tinh, a.tuoi_tick, a.lang, round(a.health, 6), a.e_bac,
                a.con_song, a.vo_chong or "", a.cha or "", a.me or "", tuple(sorted(a.con)),
                tuple(sorted(a.persona.as_dict().items())),
            )
            for a in self.agents.values()
        )
        parcels_s = sorted(
            (p.id, p.loai, round(p.mau_mo, 6), p.chu or "", p.homestead_dem, p.homestead_ai or "")
            for p in self.parcels.values()
        )
        so_du_s = sorted(
            (ct, ts, round(v, 6)) for (ct, ts), v in self.ledger._so_du.items() if abs(v) > 1e-9
        )
        hd_s = sorted(
            (h.id, h.trang_thai, h.tick_ky, tuple(h.cac_ben),
             tuple(c.loai for c in h.dieu_khoan))
            for h in self.hop_dong.values()
        ) + [len(self.hop_dong_xong)]
        gia_s = sorted(
            (ts, len(ls), round(ls[-1][1], 6)) for ts, ls in self.gia_lich_su.items() if ls
        )
        p4_s = [
            sorted((e.id, e.ten, e.con_hoat_dong) for e in self.entities.values()),
            sorted((b.id, b.linh_vuc, round(b.do_lon, 6), b.chu)
                   for b in self.blueprints.values()),
            sorted((k[0], k[1], round(v, 6)) for k, v in self.diem_nc.items() if v > 1e-9),
            round(self.tri_thuc, 6),
            self.san_tri_thuc_tier,
        ]
        blob = json.dumps(
            [self.tick, self.seed, agents_s, parcels_s, so_du_s, hd_s, gia_s, p4_s],
            ensure_ascii=False, default=str,
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ---------- checkpoint ----------
    def luu_checkpoint(self, thu_muc: Path) -> Path:
        thu_muc.mkdir(parents=True, exist_ok=True)
        duong_dan = thu_muc / f"checkpoint_{self.tick:04d}.pkl"
        events, self.events = self.events, EventLog(None)  # file handle không pickle được
        try:
            with open(duong_dan, "wb") as f:
                pickle.dump(self, f)
        finally:
            self.events = events
        meta = {"tick": self.tick, "world_hash": self.world_hash(), "seed": self.seed}
        with open(thu_muc / "checkpoint_moi_nhat.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return duong_dan

    @staticmethod
    def nap_checkpoint(duong_dan: Path, events_path: Path | None = None) -> World:
        with open(duong_dan, "rb") as f:
            w: World = pickle.load(f)
        w.events = EventLog(events_path)
        return w


def dang_ky_flows(ledger: Ledger) -> None:
    """Đăng ký MỌI luồng sinh/hủy hợp lệ (SPEC 2.4). Ngoài đây ra là luồng lậu."""
    f = ledger.flows
    f.dang_ky("thoc", "khoi_tao", "nguon")
    f.dang_ky("thoc", "gat", "nguon")
    f.dang_ky("thoc", "an", "sink")
    f.dang_ky("thoc", "hao_kho", "sink")
    f.dang_ky("thoc", "giong", "sink")
    f.dang_ky("thoc", "nghien_cuu", "sink")
    f.dang_ky("thoc", "phi_van_chuyen", "sink")
    f.dang_ky("go", "khai_thac", "nguon")
    f.dang_ky("go", "che_tac", "sink")
    f.dang_ky("go", "xay", "sink")
    f.dang_ky("quang_dong", "khai_mo", "nguon")
    f.dang_ky("quang_dong", "che_tac", "sink")
    f.dang_ky("xu", "duc_xu", "nguon")
    f.dang_ky("cong", "sinh_cong", "nguon")
    f.dang_ky("cong", "dung", "sink")
    f.dang_ky("cong", "boc_hoi", "sink")
    f.dang_ky("cong_cu", "che_tac", "nguon")
    f.dang_ky("cong_cu", "hao_mon", "sink")
    f.dang_ky("nha", "xay", "nguon")
    f.dang_ky("may", "che_tac", "nguon")
    f.dang_ky("may", "hao_mon", "sink")


def tao_the_gioi(cfg: Config, seed: int, events_path: Path | None = None) -> World:
    """Khởi tạo thế giới t0: bản đồ + 50 người lớn độc thân, 200kg thóc/người, 0 đất."""
    rng = RngTree(seed)
    w = World(cfg=cfg, seed=seed, rng=rng, events=EventLog(events_path))
    dang_ky_flows(w.ledger)
    g = rng.get("khoi_tao", 0)
    w.parcels, w.villages = sinh_ban_do(cfg, g)

    n = cfg.get("nhan_khau.dan_so_ban_dau")
    tuoi_min, tuoi_max = cfg.get("nhan_khau.tuoi_ban_dau")
    ty_le_nu = cfg.get("nhan_khau.ty_le_nu")
    for i in range(n):
        aid = w.id_moi()
        gioi = "nu" if g.random() < ty_le_nu else "nam"
        persona = Persona(*(int(x) for x in g.integers(1, 10, size=5)))
        # E ban đầu: 80% E0, 16% E1, 4% E2 (xem DECISIONS.md — gieo mầm tri thức tối thiểu)
        r = g.random()
        e0 = 0 if r < 0.80 else (1 if r < 0.96 else 2)
        w.agents[aid] = Agent(
            id=aid,
            ten=f"{HO_TEN[i % len(HO_TEN)]} {i + 1}",
            gioi_tinh=gioi,
            tuoi_tick=int(g.integers(tuoi_min * 2, tuoi_max * 2 + 1)),
            persona=persona,
            lang=0,
            e_bac=e0,
        )
        w.ledger.sinh(aid, "thoc", 200.0, "khoi_tao", "tài sản khởi đầu", tick=0)
        w.events.ghi(0, "sinh", id=aid, ten=w.agents[aid].ten, khoi_tao=True)
    return w
