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
        blob = json.dumps(
            [self.tick, self.seed, agents_s, parcels_s, so_du_s], ensure_ascii=False, default=str
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
