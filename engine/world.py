"""World — toàn bộ trạng thái mô phỏng, truyền tường minh, không global."""

from __future__ import annotations

import copy
import hashlib
import json
import pickle
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from engine.config import Config
from engine.events import EventLog
from engine.ledger import Ledger
from engine.rng import RngTree
from engine.types import Agent, Parcel, Persona, Village
from engine.worldmap import sinh_ban_do

# Chủ thể đặc biệt trong sổ cái
VO_THUA_NHAN = "VO_THUA_NHAN"  # tài sản không người thừa kế
CONG_QUY = "CONG_QUY"  # công quỹ làng — một CHỦ THỂ ledger như VO_THUA_NHAN; thu thuế/
# tái phân phối/sung công đều là chuyen CÂN giữa dân và chủ thể này (bảo toàn tự xanh)


def _canonical_state(value: Any) -> Any:
    """Đưa state có thể ảnh hưởng hành vi về JSON ổn định để băm.

    ``world_hash`` không được dựa vào ``repr`` của dataclass/Pydantic, vì thứ tự dict,
    set và kiểu key tuple có thể làm cùng một state cho hash khác nhau. Hàm này cũng
    giữ nguyên độ chính xác float thay vì làm tròn tùy tiện: một thay đổi nhỏ nhưng có
    thể đổi quyết định ở tick sau phải được phát hiện.
    """
    if isinstance(value, BaseModel):
        return _canonical_state(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _canonical_state(getattr(value, f.name))
            for f in fields(value)
        }
    if isinstance(value, dict):
        items = [(_canonical_state(k), _canonical_state(v)) for k, v in value.items()]
        items.sort(key=lambda pair: json.dumps(pair[0], ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":"), default=str))
        return {"__dict__": items}
    if isinstance(value, tuple):
        return {"__tuple__": [_canonical_state(v) for v in value]}
    if isinstance(value, list):
        return [_canonical_state(v) for v in value]
    if isinstance(value, set | frozenset):
        vals = [_canonical_state(v) for v in value]
        vals.sort(key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":"), default=str))
        return {"__set__": vals}
    if isinstance(value, Path):
        return str(value)
    # `float.hex` là biểu diễn đầy đủ và tất định; chuẩn hóa -0.0 để cùng số học
    # không bị xem là hai state khác nhau chỉ vì dấu của zero.
    if isinstance(value, float):
        return {"__float__": (0.0 if value == 0.0 else value).hex()}
    if isinstance(value, str | int | bool) or value is None:
        return value
    # NumPy scalar / enum / loại nhỏ khác: str ổn định hơn repr có địa chỉ bộ nhớ.
    return str(value)


def _behavioral_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Lược bỏ nhánh config bị scenario-gate tắt khỏi hash.

    ``Config.digest`` vẫn ghi toàn bộ YAML để provenance, nhưng world hash phải biểu diễn
    *quỹ đạo có thể xảy ra*. Một block fiscal hoàn toàn tắt và một config cũ chưa có block
    đó có cùng transition function, nên không được tạo false-negative replay/hash.
    """
    cfg = copy.deepcopy(raw)
    fiscal = cfg.get("fiscal")
    if not isinstance(fiscal, dict) or not bool(fiscal.get("bat", False)):
        cfg.pop("fiscal", None)

    politics = cfg.get("chinh_tri")
    if isinstance(politics, dict) and not bool(politics.get("bat", True)):
        cfg["chinh_tri"] = {"bat": False}

    space = cfg.get("khong_gian")
    if not isinstance(space, dict) or not bool(space.get("bat", False)):
        cfg.pop("khong_gian", None)
    else:
        # Subsystems tắt độc lập không thể ảnh hưởng tick; giữ flag để khác với bật.
        for name in ("do", "khai_hoang", "vu_dong", "ga_rung", "rung", "cham_tre", "endowment"):
            block = space.get(name)
            if isinstance(block, dict) and not bool(block.get("bat", False)):
                space[name] = {"bat": False}
        if not bool(space.get("hai_bo", False)):
            space["hai_bo"] = False
            space.pop("do", None)

    disease = cfg.get("cu_soc", {}).get("dich_benh") if isinstance(cfg.get("cu_soc"), dict) else None
    if isinstance(disease, dict) and not bool(disease.get("bat", False)):
        cfg["cu_soc"]["dich_benh"] = {"bat": False}

    strict = cfg.get("minds", {}).get("nghiem_thuc") if isinstance(cfg.get("minds"), dict) else None
    if isinstance(strict, dict) and not bool(strict.get("bat", False)):
        cfg["minds"]["nghiem_thuc"] = {"bat": False}

    # Quote/escrow is a versioned commerce treatment. A disabled overlay has the same
    # transition function as an old config with no ``bao_gia`` block, so omit it from the
    # behavioral identity rather than creating a false replay distinction.
    trade = cfg.get("thuong_mai")
    if isinstance(trade, dict):
        quotes = trade.get("bao_gia")
        if not isinstance(quotes, dict) or not bool(quotes.get("bat", False)):
            trade.pop("bao_gia", None)

    # Generic work orders are another versioned treatment. A disabled registry
    # has the same transition function as an old configuration with no project
    # block, so it must not create a false legacy hash distinction.
    projects = cfg.get("du_an")
    if not isinstance(projects, dict) or not bool(projects.get("bat", False)):
        cfg.pop("du_an", None)

    # Hộ/di sản (ADR 0007 §A.6): giữ ĐÚNG các cờ có thể đổi quỹ đạo; sub-flag TẮT được chuẩn hóa
    # để config cũ (thiếu block `ho`) và config mới `bat:false` có CÙNG behavioral hash.
    #
    # ⚠️ `cap_luong_thuc` ĐƯỢC GIỮ trong behavioral config — KHÔNG strip. ADR 0007 §B.3 tuyên bố
    # INVARIANT P-1 ("bật riêng provisioning ⇒ world_hash TRÙNG HỆT run OFF"). Chứng minh của ADR
    # đúng ở MỨC GIÁ TRỊ nhưng SAI ở mức BIT: `world_hash` băm `float.hex()` (chính xác tuyệt
    # đối), còn cộng dồn IEEE-754 KHÔNG kết hợp. Legacy áp MỘT delta `-tru` cho người có kho;
    # provisioning áp `-x₁, -x₂, …` (mỗi người ăn một bút toán) ⇒ `(bal-x₁)-x₂ ≠ bal-(x₁+x₂)`.
    # Đo được: base seed 11, tick 4, `('A0042','thoc')` OFF=977.4906109560651 vs
    # PROV=977.4906109560652 (lệch 1 ULP = 1.14e-13); dân số/health/flow_totals y hệt.
    # ⇒ Cờ này CÓ đổi quỹ đạo số học ⇒ nó THUỘC transition function ⇒ để nó ngoài hash là tạo
    # false-equivalence cho replay. Fail-closed: giữ lại. (Xem F-P1-1 trong
    # docs/reviews/P1-engine-surgeon.md — ADR §B.3 và ma trận ablation §G.4 cần sửa.)
    ho = cfg.get("ho")
    if isinstance(ho, dict) and bool(ho.get("bat", False)):
        hieu_luc: dict[str, Any] = {}
        if bool(ho.get("cu_tru_ben_vung", False)):
            hieu_luc["cu_tru_ben_vung"] = True
            hieu_luc["quy_tac_cap"] = ho.get("quy_tac_cap", "nhu_cau_deu")
            tach = ho.get("tach_ho")
            if isinstance(tach, dict) and bool(tach.get("bat", False)):
                hieu_luc["tach_ho"] = {"bat": True}
        if bool(ho.get("cap_luong_thuc", False)):
            hieu_luc["cap_luong_thuc"] = True
        di_san = ho.get("di_san")
        if isinstance(di_san, dict) and bool(di_san.get("bat", False)):
            hieu_luc["di_san"] = di_san
        if hieu_luc:
            hieu_luc["bat"] = True
            cfg["ho"] = hieu_luc
        else:
            cfg.pop("ho", None)
    else:
        cfg.pop("ho", None)
    return cfg


@dataclass
class ChinhQuyen:
    """Nhà nước làng — TỰ PHÁT SINH từ ý định agent (bầu cử, lập pháp, nghiệp đoàn).

    Engine chỉ giữ TRẠNG THÁI trung lập; không chủ thể nào được thiên vị. Struct này
    chỉ tồn tại (w.chinh_quyen ≠ None) SAU khi có hành vi chính trị đầu tiên — trước
    đó làng vô chính phủ, đúng nguyên tắc tự phát (điều luật #7)."""

    truong_lang: str | None = None  # id người đang giữ chức; None = khuyết
    nhiem_ky_den: int = 0  # tick hết nhiệm kỳ đương nhiệm
    thue_suat: float = 0.0  # suất thuế thu hoạch (0..thue_suat_toi_da)
    luong_toi_thieu: float = 0.0  # sàn lương (thóc/công) — chỉ là dữ kiện dân đọc
    phieu: dict[str, int] = field(default_factory=dict)  # ứng viên id → số phiếu kỳ này
    nghiep_doan: set[str] = field(default_factory=set)  # thành viên nghiệp đoàn
    dinh_cong_tick: set[str] = field(default_factory=set)  # ai đình công tick hiện tại

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
    dich_benh_nam: dict[int, bool] = field(default_factory=dict)  # năm → có dịch hay không
    dich_benh_tick: bool = False
    _next_id: int = 0
    events: EventLog = field(default_factory=lambda: EventLog(None))
    metrics_lich_su: list[dict[str, Any]] = field(default_factory=list)
    # đề nghị cầu hôn chờ trả lời tick sau: (tu, den, tick_gui)
    cau_hon_cho: list[tuple[str, str, int]] = field(default_factory=list)
    # hòm thư P2P (PART 5.4): người nhận → [(người gửi, nội dung, tick)] — giao ở prompt
    # tick SAU (mặc cả/vận động qua nhiều tick), thuần THÔNG TIN, không chạm Ledger
    hom_thu: dict[str, list] = field(default_factory=dict)
    # uy tín / quan hệ xã hội: (a,b) → trọng số (âm = ân oán)
    quan_he: dict[tuple[str, str], float] = field(default_factory=dict)
    # ---- Phase 2: hợp đồng, bảng rao, chợ ----
    hop_dong: dict = field(default_factory=dict)  # id → HopDong (đang hiệu lực)
    hop_dong_xong: dict = field(default_factory=dict)  # lưu trữ hợp đồng đã kết thúc
    bang_rao: dict = field(default_factory=dict)  # id → DeNghi
    _next_hd: int = 0
    _next_dn: int = 0
    # Versioned A2A quote threads. Explicitly omitted from behavioral_state when gate off so
    # adding this field cannot alter legacy/spatial_v1 world hashes.
    bao_gia: dict[str, Any] = field(default_factory=dict)
    _next_bao_gia: int = 0
    # Versioned generic work orders. These fields are hashed only when their
    # scenario gate is enabled.
    du_an: dict[str, Any] = field(default_factory=dict)
    _next_du_an: int = 0
    gia_lich_su: dict[str, list] = field(default_factory=dict)  # tài sản → [(tick, giá, kl)]
    gat_tick: dict[str, tuple[str, float]] = field(default_factory=dict)  # thửa → (ai, kg)
    # Mọi thửa đã canh (lúa hoặc vụ đông) trong tick — dùng cho hồi màu; `gat_tick` giữ
    # riêng lúa/thóc để các clause chia_san_luong cũ không vô tình chuyển thóc cho ngô/khoai.
    canh_tick: set[str] = field(default_factory=set)
    thu_hoach_cay_tick: list[dict[str, Any]] = field(default_factory=list)
    yeu_cau_rut_tick: dict[tuple[str, str], float] = field(default_factory=dict)
    niem_yet_dat: dict = field(default_factory=dict)  # thua → NiemYetDat
    # giao dịch đất đã khớp kèm năng suất kỳ vọng lúc bán; chỉ metric/analysis đọc.
    giao_dich_dat: list[dict] = field(default_factory=list)
    chet_tick_truoc: set[str] = field(default_factory=set)
    unrecognized_path: Path | None = None
    # kho trạng thái của tầng minds (engine không đọc — chỉ mang theo checkpoint)
    policy_cards: dict[str, dict] = field(default_factory=dict)
    # nhà nước làng — None cho tới khi có hành vi chính trị đầu tiên (tự phát, điều luật #7)
    chinh_quyen: ChinhQuyen | None = None
    so_bao_dong_tick: int = 0  # số người bạo động tick này (metric, đặt trong buoc_bao_dong)
    # ---- Phase 4: pháp nhân, R&D, tri thức ----
    entities: dict = field(default_factory=dict)  # id → Entity
    _next_entity: int = 0
    blueprints: dict = field(default_factory=dict)  # id → Blueprint
    _next_bp: int = 0
    diem_nc: dict[tuple[str, str], float] = field(default_factory=dict)
    ten_hang: dict[str, str] = field(default_factory=dict)  # mã hàng mới → tên LLM đặt
    tri_thuc: float = 0.0
    san_tri_thuc_tier: int = 0
    # nhãn → chủ thể: kênh MỘT CHIỀU observatory→metrics — engine chỉ ghi lại vào
    # metrics/events, không bao giờ rẽ nhánh hành vi theo nhãn này
    nhan_dinh_che: dict[str, list[str]] = field(default_factory=dict)
    # nhãn giai cấp aid→nhãn (observatory→prompt persona; engine không rẽ nhánh theo nó)
    phan_loai: dict[str, str] = field(default_factory=dict)
    milestones: list[dict] = field(default_factory=list)
    # thu nhập theo nguồn, cửa sổ 4 tick (observatory đọc để phân giai cấp)
    thu_nhap_tick: dict = field(default_factory=dict)  # aid → {nguon: quy thóc}
    thu_nhap_4: list = field(default_factory=list)  # 4 dict gần nhất
    kl_thanh_toan_tick: dict[str, float] = field(default_factory=dict)
    cong_dung_tick: dict[str, float] = field(default_factory=dict)
    cong_dung_4: list = field(default_factory=list)  # cửa sổ 4 tick (mùa mưa+khô)
    kl_thanh_toan_4: list = field(default_factory=list)
    # ---- observation state (Lớp-5, ADR 0003 §E + 0004 §T07 C): KHÔNG vào world_hash ----
    # poverty_streak: số tick LIÊN TIẾP food_security<1 per hộ-head (T04). settlement_fail_tick:
    # số lần LoiSoKep bị nuốt ở khớp chợ trong tick (T07). Engine KHÔNG đọc lại hai field này
    # ⇒ không ảnh hưởng hành vi ⇒ NGOÀI hash; nhưng vào pickle checkpoint + migration.
    poverty_streak: dict[str, int] = field(default_factory=dict)
    settlement_fail_tick: int = 0
    # Provenance of plans/actions for the current tick. It is an observation
    # record owned by minds/metrics, deliberately absent from behavioral_state:
    # recording an origin must never change a world transition or legacy hash.
    decision_provenance_tick: dict[str, Any] = field(default_factory=dict)
    # Versioned action-result journal (v3). This is observation state only;
    # engine.action_journal is the single writer and it never enters
    # behavioral_state().
    action_journal_tick: list[dict[str, Any]] = field(default_factory=list)
    _action_journal_seq: int = 0
    # Engine-confirmed v3 outcomes waiting for the next prompt. Unlike the
    # raw action journal this affects a future decision, so it is inserted in
    # behavioral_state only behind the versioned action-journal gate.
    action_feedback: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    # P4 demographic observation state. It is intentionally excluded from
    # behavioral_state: it records completed facts but never controls a future
    # transition. engine.metrics_demography owns its contents.
    nhan_khau_tick: dict[str, Any] = field(default_factory=dict)
    nhan_khau_lich_su: list[dict[str, Any]] = field(default_factory=list)
    tu_vong_sinh_no_tick: set[str] = field(default_factory=set)
    # ben_kia_tick (ADR 0005 §2.3): tập agent ĐÃ QUA SÔNG tick này (trả phí đò thành công
    # hoặc tự chèo thuyền). Transient — reset đầu pha sản xuất, KHÔNG vào world_hash (như
    # settlement_fail_tick); các pha sau đọc để biết ai được hoạt động bờ đối diện. Không
    # teleport: không có chuyến ⇒ không vào set ⇒ kẹt bờ cư trú.
    ben_kia_tick: set[str] = field(default_factory=set)
    # accounting chăm trẻ: credit công của carer theo (carer, parent) để clause gop_cong
    # trả lương cho đúng dịch vụ thay vì buộc carer giao hai lần cùng một ngày công.
    cong_cham_tre_theo_cap: dict[tuple[str, str], float] = field(default_factory=dict)
    cham_tre_tick: dict[str, float] = field(default_factory=dict)
    # ---- ADR 0007: cư trú (state BỀN) + di sản ----
    # `cu_tru` KHÔNG phải field của dataclass `Agent`: `behavioral_state()` băm "population":
    # self.agents và `_canonical_state` duyệt `dataclasses.fields()` ⇒ thêm MỘT field vào
    # `Agent` là đổi hash của MỌI run legacy (F-22). Ở World thì không: `behavioral_state`
    # dựng dict tường minh nên field mới CHỈ vào hash khi ta chèn khối, và ta chỉ chèn khi
    # cờ scenario BẬT. SINGLE-WRITER: chỉ `engine/household.py` được gán `cu_tru`/`_next_cu_tru`,
    # chỉ `engine/estate.py` được gán `di_san*`.
    cu_tru: dict[str, Any] = field(default_factory=dict)  # rid → household.CuTru
    _next_cu_tru: int = 0
    # biến cố membership transient trong tick (đọc-và-xóa bởi household.buoc_cu_tru)
    bien_co_ho: dict[str, list] = field(default_factory=dict)
    di_san: dict[str, Any] = field(default_factory=dict)  # "DI_SAN:<aid>" → estate.DiSan (mở)
    di_san_xong: dict[str, Any] = field(default_factory=dict)  # đã đóng (observatory đọc)
    _next_di_san: int = 0

    def ghi_thu_nhap(self, aid: str, nguon: str, quy_thoc: float) -> None:
        if quy_thoc <= 0:
            return
        d = self.thu_nhap_tick.setdefault(aid, {})
        d[nguon] = d.get(nguon, 0.0) + quy_thoc

    # ---------- id ----------
    def id_moi(self) -> str:
        self._next_id += 1
        return f"A{self._next_id:04d}"

    # ---------- calendar / thời tiết ----------
    def tick_moi_nam(self) -> int:
        """Số tick trong một năm lịch, suy từ đơn vị thời gian của config.

        Calendar legacy giữ ``6 tháng/tick`` = 2 tick/năm. Scenario có thể dùng 4
        tháng/tick (3 mùa) nhưng phải chia tròn một năm; từ chối cấu hình mơ hồ thay vì
        âm thầm đổi tuổi, hazard hay báo cáo.
        """
        thang = float(self.cfg.get("thoi_gian.thang_moi_tick"))
        if thang <= 0:
            raise ValueError("thoi_gian.thang_moi_tick phải dương")
        so_tick = int(round(12.0 / thang))
        if so_tick < 1 or abs(so_tick * thang - 12.0) > 1e-9:
            raise ValueError(
                "thoi_gian.thang_moi_tick phải chia tròn 12 để calendar có đơn vị năm rõ ràng"
            )
        return so_tick

    def nam(self, tick: int | None = None) -> int:
        """Năm lịch chứa ``tick``.

        Legacy không khai báo calendar nên giữ nguyên index ``tick // 2`` (một phần của
        replay contract cũ). Calendar khai báo tường minh bắt đầu tại tick 1 và gán đủ N
        mùa đầu tiên vào cùng năm 1, tránh việc mùa cuối vô tình rơi sang năm thời tiết kế.
        """
        t = self.tick if tick is None else tick
        lich = self.cfg.raw().get("thoi_gian", {}).get("lich_mua")
        if lich is None:
            return t // self.tick_moi_nam()
        if t <= 0:
            return 0
        return (t - 1) // self.tick_moi_nam() + 1

    def mua(self, tick: int | None = None) -> str:
        """Nhãn mùa của tick hiện tại, đọc từ calendar scenario nếu được khai báo.

        Một lịch có N tick phải chứa đúng N nhãn. Không có ``lich_mua`` giữ nguyên
        quy ước legacy: tick lẻ=mưa/lúa, tick chẵn=khô.
        """
        t = self.tick if tick is None else tick
        lich = self.cfg.raw().get("thoi_gian", {}).get("lich_mua")
        if lich is None:
            return "lua" if t % 2 == 1 else "kho"
        if not isinstance(lich, list) or len(lich) != self.tick_moi_nam():
            raise ValueError("thoi_gian.lich_mua phải là list có đúng tick_moi_nam phần tử")
        # Tick 1 là mùa đầu tiên; tick 0 (khởi tạo) vòng về mùa cuối để không tạo một
        # mùa hư cấu trước khi thế giới bắt đầu chạy.
        return str(lich[(t - 1) % len(lich)])

    def dau_nam(self, tick: int | None = None) -> bool:
        t = self.tick if tick is None else tick
        return t % self.tick_moi_nam() == 1

    def cuoi_nam(self, tick: int | None = None) -> bool:
        t = self.tick if tick is None else tick
        return t % self.tick_moi_nam() == 0

    def thoi_tiet(self, tick: int) -> tuple[str, float]:
        """Thời tiết của năm chứa tick — ngẫu nhiên ngoại sinh DUY NHẤT, seeded theo năm."""
        nam = self.nam(tick)
        if nam not in self.thoi_tiet_nam:
            tt = self.cfg.get("thoi_gian.thoi_tiet")
            g = self.rng.get("thoi_tiet", nam)
            loai = ["duoc_mua", "binh_thuong", "han_lu"]
            p = [tt[k]["p"] for k in loai]
            self.thoi_tiet_nam[nam] = str(g.choice(loai, p=p))
        loai_tt = self.thoi_tiet_nam[nam]
        return loai_tt, float(self.cfg.get("thoi_gian.thoi_tiet")[loai_tt]["he_so"])

    def mua_mua(self, tick: int | None = None) -> bool:
        return self.mua(tick).startswith("lua")

    def co_dich_benh(self, tick: int | None = None) -> bool:
        """Cú sốc dịch bệnh theo năm, tắt mặc định và tất định theo seed.

        Cấu hình scenario quyết định có bật, xác suất và cường độ; engine không suy
        luận dịch từ kết quả kinh tế. Trạng thái cache vào world để checkpoint/replay
        không phụ thuộc thứ tự gọi RNG.
        """
        t = self.tick if tick is None else tick
        disease = self.cfg.get("cu_soc.dich_benh")
        if not bool(disease["bat"]):
            return False
        year = self.nam(t)
        if year not in self.dich_benh_nam:
            g = self.rng.get("dich_benh", year)
            self.dich_benh_nam[year] = bool(g.random() < float(disease["xac_suat_moi_nam"]))
        return self.dich_benh_nam[year]

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
        gan = [x for x in ls if x[0] >= self.tick - int(self.cfg.get("thuong_mai.cua_so_gia_tick"))]
        return sum(x[1] for x in gan) / len(gan) if gan else ls[-1][1]

    def vi_tri_cua(self, aid: str) -> tuple[int, int]:
        """Vị trí cư trú: thửa đặt nhà → thửa sở hữu đầu tiên → trung tâm làng."""
        a = self.agents.get(aid)
        if a is None:
            v = self.villages[0]
            return (v.r, v.c)
        if a.nha_thua and a.nha_thua in self.parcels:
            p = self.parcels[a.nha_thua]
            return (p.r, p.c)
        for p in self.parcels.values():
            if p.chu == aid:
                return (p.r, p.c)
        v = self.villages[a.lang if a.lang < len(self.villages) else 0]
        return (v.r, v.c)

    def hang_xom_cua(self, aid: str, ban_kinh: int | None = None,
                     toi_da: int | None = None) -> list[str]:
        """Hàng xóm theo khoảng cách cư trú thật (làng xóm 2D)."""
        if ban_kinh is None:
            ban_kinh = int(self.cfg.get("quan_he.ban_kinh_lang_gieng"))
        if toi_da is None:
            toi_da = int(self.cfg.get("quan_he.lang_gieng_toi_da"))
        r0, c0 = self.vi_tri_cua(aid)
        tuoi_tt = float(self.cfg.get("nhan_khau.tuoi_truong_thanh"))
        ung_vien = []
        for b in self.agents.values():
            if not b.con_song or b.id == aid or b.tuoi_nam < tuoi_tt:
                continue
            r, c = self.vi_tri_cua(b.id)
            kc = abs(r - r0) + abs(c - c0)
            if kc <= ban_kinh:
                ung_vien.append((kc, b.id))
        ung_vien.sort()
        return [bid for _kc, bid in ung_vien[:toi_da]]

    def ghi_ky_uc(self, aid: str, noi_dung: str, doi: bool = False) -> None:
        """Khắc một biến cố vào ký ức agent (kèm mốc năm).

        doi=True → DẤU MỐC ĐỜI (cưới, sinh, tang, đất đai, nhà cửa, ân oán lớn):
        không bị trôi theo thời gian. Mặc định → chuyện gần đây (rolling)."""
        a = self.agents.get(aid)
        if a is None or not a.con_song:
            return
        dong = f"Năm {self.nam()}: {noi_dung}"
        if doi:
            toi_da = int(self.cfg.get("minds.ky_uc_doi_toi_da"))
            if len(a.ky_uc_doi) < toi_da:
                a.ky_uc_doi = [*a.ky_uc_doi, dong]
            else:  # đầy thì vẫn không quên — dồn vào chuyện gần đây
                a.ky_uc = [*a.ky_uc, dong][-int(self.cfg.get("minds.ky_uc_toi_da")):]
        else:
            toi_da = int(self.cfg.get("minds.ky_uc_toi_da"))
            a.ky_uc = [*a.ky_uc, dong][-toi_da:]

    def ghi_unrecognized(self, ai: str, loai: str, ly_do: str) -> None:
        """Intent không hợp lệ → bỏ qua + log (điều luật #3) — mỏ 'ý định mới lạ'."""
        from engine.action_journal import rejected as journal_rejected

        journal_rejected(self, ai, loai, "unrecognized_intent", detail=ly_do)
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

    def cong_quan_he_gioi_han(self, a: str, b: str, delta: float) -> None:
        """Cộng quan hệ từ tương tác kinh tế lặp lại — tối đa 1 lần/cặp/tick
        (bạn hàng tích lũy, nhưng 100 lệnh khớp một phiên không thành tri kỷ)."""
        if a == b:
            return
        key = (min(a, b), max(a, b))
        if getattr(self, "_qh_cap_tick", None) != self.tick:
            self._qh_cap_tick = self.tick
            self._qh_cap: set[tuple[str, str]] = set()
        if key in self._qh_cap:
            return
        self._qh_cap.add(key)
        self.cong_quan_he(a, b, delta)

    # ---------- hộ gia đình ----------
    def ho_cua(self, aid: str) -> list[str]:
        """Hộ = chủ hộ + vợ/chồng + con (đẻ lẫn nuôi) chưa trưởng thành còn sống.

        Trẻ chưa trưởng thành quy về hộ của cha/mẹ còn sống, hoặc người giám hộ
        (trẻ mồ côi được cưu mang ăn chung nồi cơm nhà người nuôi).

        ⚠️ NHÁNH LEGACY (gate TẮT) GIỮ NGUYÊN TỪNG DÒNG — kể cả defect F-18: ``not
        c.truong_thanh(tt)`` đẩy người vừa tròn 16 tuổi ra khỏi hộ cha mẹ CÒN SỐNG, trong khi
        ``consumption.an_va_suc_khoe`` ăn theo đúng hộ này ⇒ họ ăn 0 kg dù cha mẹ đầy thóc.
        Semantics lỗi được ĐÓNG BĂNG CÓ GHI CHÚ cho regression legacy, không retcon (ADR 0007
        §A.6). Nhánh ON (``ho.cu_tru_ben_vung``) đọc state bền và KHÔNG đọc tuổi (INVARIANT R2).
        """
        from engine.household import _cu_tru_bat, ho_cua_cu_tru

        if _cu_tru_bat(self):
            return ho_cua_cu_tru(self, aid)
        a = self.agents[aid]
        tt = self.cfg.get("nhan_khau.tuoi_truong_thanh")
        if not a.truong_thanh(tt):
            for pid in (a.cha, a.me, a.giam_ho):
                p = self.agents.get(pid) if pid else None
                if p is not None and p.con_song:
                    a = p
                    break
        ho = [a.id]
        nguoi_lon = [a]
        if a.vo_chong and a.vo_chong in self.agents and self.agents[a.vo_chong].con_song:
            ho.append(a.vo_chong)
            nguoi_lon.append(self.agents[a.vo_chong])
        # con (đẻ lẫn nuôi) của CẢ HAI vợ chồng — con riêng nhà tái hôn không bị bỏ rơi
        for nl in nguoi_lon:
            for cid in [*nl.con, *nl.con_nuoi]:
                c = self.agents.get(cid)
                if c and c.con_song and not c.truong_thanh(tt) and cid not in ho:
                    ho.append(cid)
        return ho

    # ---------- world hash (điều luật #4) ----------
    def behavioral_state(self) -> dict[str, Any]:
        """Toàn bộ state có thể làm tick/prompt/replay tiếp theo rẽ nhánh.

        Không đưa event journal, metric history, transaction journal, cache thuần đọc và
        observation state vào đây: chúng không được engine/minds dùng để quyết định. Ngược
        lại, mọi thứ agent thấy ở prompt, mọi cache RNG/weather, hợp đồng đầy đủ, lịch sử giá,
        pool tài nguyên, tin nhắn và state chính trị đều phải có mặt. Đây là ranh giới công
        khai cho reproducibility; thêm field state mới phải hoặc vào đây, hoặc được ghi rõ là
        read-only tại nơi khai báo.
        """
        two_bank = bool(self.cfg.get("khong_gian.hai_bo", False))
        # Off must retain the exact pre-P2 canonical layout. In the two-bank legacy branch a
        # Parcel dataclass went directly through `_canonical_state`; replacing it with a dict
        # adds the canonical ``__dict__`` wrapper even if all visible fields are identical.
        # Ecology state is deliberately dynamic (not a Parcel dataclass field), so the legacy
        # branch also naturally excludes it.
        from engine.forest import _rung_bat

        if not _rung_bat(self):
            parcels: dict[str, Any] = {pid: p for pid, p in self.parcels.items()}
            if not two_bank:
                parcels = {
                    pid: {
                        "id": p.id,
                        "r": p.r,
                        "c": p.c,
                        "loai": p.loai,
                        "mau_mo": p.mau_mo,
                        "mau_mo_goc": p.mau_mo_goc,
                        "chu": p.chu,
                        "lang": p.lang,
                        "nguoi_canh": p.nguoi_canh,
                        "homestead_dem": p.homestead_dem,
                        "homestead_ai": p.homestead_ai,
                    }
                    for pid, p in self.parcels.items()
                }
        else:
            # Versioned ecology treatment: these fields alter future logging yield and chicken
            # habitat, therefore must participate in the replay/world hash.
            parcels = {}
            for pid, p in self.parcels.items():
                view: dict[str, Any] = {
                    "id": p.id,
                    "r": p.r,
                    "c": p.c,
                    "loai": p.loai,
                    "mau_mo": p.mau_mo,
                    "mau_mo_goc": p.mau_mo_goc,
                    "chu": p.chu,
                    "lang": p.lang,
                    "nguoi_canh": p.nguoi_canh,
                    "homestead_dem": p.homestead_dem,
                    "homestead_ai": p.homestead_ai,
                    "sinh_khoi": float(getattr(p, "sinh_khoi", 0.0)),
                    "tan_rung": float(getattr(p, "tan_rung", 0.0)),
                }
                if two_bank:
                    view["bo"] = p.bo
                parcels[pid] = view
        ledger = self.ledger
        state: dict[str, Any] = {
            "hash_schema": "behavioral-state-v2",
            # Config là một phần của state chuyển tiếp; normalize các block scenario tắt để
            # config cũ thiếu block và config mới `bat:false` vẫn có cùng behavioral hash.
            "config": _behavioral_config(self.cfg.raw()),
            "seed": self.seed,
            "tick": self.tick,
            "ids": {
                "agent": self._next_id,
                "contract": self._next_hd,
                "proposal": self._next_dn,
                "entity": self._next_entity,
                "blueprint": self._next_bp,
            },
            "ledger": {
                "balances": ledger._so_du,
                "flow_sources": ledger.flows._nguon,
                "flow_sinks": ledger.flows._sink,
                "flow_totals": ledger.flows._tich_luy,
            },
            "population": self.agents,
            "parcels": parcels,
            "villages": self.villages,
            # thoi_tiet_nam/dich_benh_nam là cache lười thuần xác định từ
            # (seed, config, year); đưa cache vào hash sẽ khiến một policy chỉ ĐỌC thời tiết
            # thay hash. Giá trị vật lý tương lai vẫn được băm gián tiếp qua seed/config/tick.
            "family_queue": self.cau_hon_cho,
            "messages": self.hom_thu,
            "relationships": self.quan_he,
            "contracts": {"active": self.hop_dong, "closed": self.hop_dong_xong},
            "board": self.bang_rao,
            "market": {
                "price_history": self.gia_lich_su,
                "land_listings": self.niem_yet_dat,
                "withdraw_requests": self.yeu_cau_rut_tick,
                "classified_ads": getattr(self, "rao_vat", []),
            },
            "production": {
                "harvests_this_tick": self.gat_tick,
                "cultivated_this_tick": self.canh_tick,
                "crop_harvests_this_tick": self.thu_hoach_cay_tick,
                "previous_deaths": self.chet_tick_truoc,
                "crossed_river": self.ben_kia_tick if two_bank else set(),
                "care_labor_credit": self.cong_cham_tre_theo_cap,
                "care_this_tick": self.cham_tre_tick,
            },
            "minds": {"policy_cards": self.policy_cards},
            "politics": {"government": self.chinh_quyen, "riot_count": self.so_bao_dong_tick},
            "research": {
                "entities": self.entities,
                "blueprints": self.blueprints,
                "points": self.diem_nc,
                "product_names": self.ten_hang,
                "knowledge": self.tri_thuc,
                "knowledge_floor": self.san_tri_thuc_tier,
            },
            # Các cửa sổ sau được observatory dùng để cập nhật phan_loai; phan_loai lại nằm
            # trong prompt của agent, nên chúng không phải metric vô hại.
            "observatory_inputs": {
                "labels": self.nhan_dinh_che,
                "classifications": self.phan_loai,
                "income_this_tick": self.thu_nhap_tick,
                "income_window": self.thu_nhap_4,
                "payment_this_tick": self.kl_thanh_toan_tick,
                "payment_window": self.kl_thanh_toan_4,
                "labor_this_tick": self.cong_dung_tick,
                "labor_window": self.cong_dung_4,
            },
            # commons là state vật lý: nếu khác đi, lợi ích biên của cá/gà và hành vi tick
            # sau khác ngay. `getattr` giúp đọc checkpoint cũ trước migration.
            "commons": {
                "fish_stock": getattr(self, "ca_ton", None),
                "wild_chicken_stock": getattr(self, "ga_rung_ton", None),
            },
        }
        # ADR 0007 §A.5: HAI khối CÓ ĐIỀU KIỆN. Gate TẮT ⇒ KHÔNG có key ⇒ blob JSON không đổi
        # MỘT BYTE ⇒ ba hash pin legacy bất biến. KHÔNG bump `hash_schema`, KHÔNG thêm key rỗng
        # "cho đẹp" (key rỗng cũng đổi hash). Gate BẬT ⇒ hash khác — đúng và mong muốn: đó là
        # một THÍ NGHIỆM KHÁC.
        from engine.estate import _di_san_bat
        from engine.household import _cu_tru_bat

        if _cu_tru_bat(self):
            # Đổi ai được ăn ⇒ đổi quỹ đạo ⇒ PHẢI vào hash. `_next_cu_tru` quyết định id tương
            # lai (tie-break) nên cũng vào, nhưng đặt TRONG khối này chứ KHÔNG nhét vào
            # state["ids"] (nhét vào `ids` là đổi layout ngay cả khi gate TẮT).
            state["residence"] = {"cu_tru": self.cu_tru, "next_id": self._next_cu_tru}
        if _di_san_bat(self):
            # `di_san_xong` KHÔNG vào hash: estate ĐÃ ĐÓNG không ảnh hưởng quỹ đạo (kho lưu
            # trữ chỉ observatory đọc). Ta cố ý KHÔNG bắt chước `hop_dong_xong` — nó đang nằm
            # trong hash ở trên; ghi rõ ra đây để reviewer bắt bẻ được, không giấu.
            state["estate"] = {"mo": self.di_san, "next_id": self._next_di_san}
        from engine.quotes import _bao_gia_bat

        if bool(self.cfg.get("minds.action_journal.bat", False)):
            # An empty field would alter legacy hashes. The v3 queue is
            # intentionally a behavioural input because the prompt reads it.
            state["minds"]["action_feedback"] = getattr(self, "action_feedback", {})

        if _bao_gia_bat(self):
            state["commerce"] = {
                "quotes": self.bao_gia,
                "next_quote_id": self._next_bao_gia,
            }
        from engine.projects import _du_an_bat

        if _du_an_bat(self):
            state["projects"] = {
                "active_and_closed": self.du_an,
                "next_project_id": self._next_du_an,
            }
        return state

    def world_hash(self) -> str:
        """SHA-256 của toàn bộ behavioral state, không phải snapshot rút gọn.

        Được dùng cho checkpoint/replay/kiểm chứng thuần đọc. Nếu state liên quan đến
        quyết định đổi mà hash không đổi, đó là lỗi nghiêm trọng chứ không phải tối ưu hóa.
        """
        blob = json.dumps(
            _canonical_state(self.behavioral_state()),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    # ---------- checkpoint ----------
    def luu_checkpoint(self, thu_muc: Path) -> Path:
        thu_muc.mkdir(parents=True, exist_ok=True)
        duong_dan = thu_muc / f"checkpoint_{self.tick:04d}.pkl"
        events, self.events = self.events, EventLog(None)  # file handle không pickle được
        # Transaction journal cũ không điều khiển future state: metrics chỉ quét transaction
        # của TICK HIỆN TẠI và checkpoint được ghi cuối tick. Giữ nó trong mọi checkpoint làm
        # artifact tăng theo O(tick²) (mỗi snapshot lặp toàn bộ ledger history). Flow totals,
        # balances và metrics history vẫn được giữ nên audit/replay/resume không mất dữ liệu
        # hành vi; event/metrics đã có artifact append-only riêng ở run directory.
        lich_su, self.ledger._lich_su = self.ledger._lich_su, []
        try:
            with open(duong_dan, "wb") as f:
                pickle.dump(self, f)
        finally:
            self.ledger._lich_su = lich_su
            self.events = events
        meta = {
            "tick": self.tick,
            "world_hash": self.world_hash(),
            "seed": self.seed,
            "config_digest": self.cfg.digest(),
        }
        with open(thu_muc / "checkpoint_moi_nhat.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)
        # Checkpoint phải tự đủ để tiếp tục đúng scenario cả khi caller không còn nhớ overlay.
        # run.py vẫn kiểm manifest/digest trước resume; snapshot này chủ yếu bảo vệ API trực tiếp
        # và test/review khỏi vô tình nạp base world.yaml cho một run spatial.
        #
        # KHÔNG `sort_keys`: engine CÓ chỗ duyệt dict config theo THỨ TỰ CHÈN — `economy.
        # food_equivalence` (`engine/economy.py:43`) đọc `khong_gian.vu_dong.cay` rồi
        # `consumption.an_va_suc_khoe` (`engine/consumption.py:60`) ăn theo đúng thứ tự đó.
        # Snapshot sắp xếp khóa ⇒ ăn `khoai` trước `ngo` thay vì `ngo` trước `khoai` ⇒ world
        # nạp bằng fallback snapshot đi một QUỸ ĐẠO KHÁC world của chính run đó, dù
        # `config_digest` và `world_hash` (đã canonical-sort) đều KHỚP. Đo được trên
        # `mock60_spatial`: liên tục vs nạp-ck90-bằng-snapshot lệch hash ngay tick 94.
        # `world_hash` KHÔNG đổi vì `_canonical_state` vốn sort — đây chỉ là sửa artifact.
        # (Hazard gốc — engine phụ thuộc thứ tự khóa config — vẫn OPEN, xem
        #  docs/reviews/P0.2-engine-surgeon.md §Findings F-P02-2.)
        with open(thu_muc / "config_snapshot.json", "w", encoding="utf-8") as f:
            json.dump(self.cfg.raw(), f, ensure_ascii=False, sort_keys=False)
        return duong_dan

    @staticmethod
    def nap_checkpoint(duong_dan: Path, events_path: Path | None = None,
                       cfg: Config | None = None) -> World:
        from engine.config import load_config

        with open(duong_dan, "rb") as f:
            w: World = pickle.load(f)
        w.events = EventLog(events_path)
        # Ưu tiên config caller (run.py đã kiểm manifest); nếu dùng API trực tiếp thì nạp
        # snapshot cạnh checkpoint. Checkpoint cũ chưa có snapshot mới rơi về YAML base.
        if cfg is not None:
            w.cfg = cfg
        else:
            snapshot = Path(duong_dan).parent / "config_snapshot.json"
            if snapshot.exists():
                w.cfg = Config(json.loads(snapshot.read_text(encoding="utf-8")))
            else:
                w.cfg = load_config()
        # migration: checkpoint trước khi có mau_mo_goc → đất không bao giờ hồi màu
        for p in w.parcels.values():
            p.mau_mo_goc = p.mau_mo_goc or p.mau_mo
        # P2 migration: only a checkpoint predating the stock fields is initialized from the
        # versioned scenario. An existing zero is a real depleted forest and MUST NOT regrow
        # magically on load.
        from engine.forest import khoi_tao_parcel

        for p in w.parcels.values():
            if not hasattr(p, "sinh_khoi") or not hasattr(p, "tan_rung"):
                khoi_tao_parcel(w, p)
        # migration: checkpoint trước khi có trữ lượng cá / ký ức đời
        if not hasattr(w, "ca_ton"):
            w.ca_ton = _ca_suc_chua(w) * float(w.cfg.get("danh_ca.ty_le_ton_ban_dau"))
        if not hasattr(w, "ga_rung_ton"):
            ga_k = _ga_rung_suc_chua(w)
            w.ga_rung_ton = (
                ga_k * float(w.cfg.get("khong_gian.ga_rung.ty_le_ton_ban_dau", 0.0))
                if ga_k > 0 else None
            )
        for a in w.agents.values():
            if not hasattr(a, "ky_uc_doi"):
                a.ky_uc_doi = []
            if not hasattr(a, "gia_ky_vong"):
                from engine.pricing import khoi_tao_gia_ky_vong

                a.gia_ky_vong = khoi_tao_gia_ky_vong(
                    w, a.id, w.rng.get(f"gia_ky_vong:{a.id}", 0)
                )
        # migration: checkpoint trước khi có định chế chính trị
        if not hasattr(w, "chinh_quyen"):
            w.chinh_quyen = None
        if not hasattr(w, "so_bao_dong_tick"):
            w.so_bao_dong_tick = 0
        if not hasattr(w, "giao_dich_dat"):
            w.giao_dich_dat = []
        if not hasattr(w, "dich_benh_nam"):
            w.dich_benh_nam = {}
        if not hasattr(w, "dich_benh_tick"):
            w.dich_benh_tick = False
        # migration: observation state (ngoài hash) — checkpoint cũ thiếu → default an toàn
        if not hasattr(w, "poverty_streak"):
            w.poverty_streak = {}
        if not hasattr(w, "settlement_fail_tick"):
            w.settlement_fail_tick = 0
        # P4 observation migration. Old checkpoints do not have an invented
        # exposure history; their first resumed tick starts a fresh window.
        if not hasattr(w, "nhan_khau_tick"):
            w.nhan_khau_tick = {}
        if not hasattr(w, "nhan_khau_lich_su"):
            w.nhan_khau_lich_su = []
        if not hasattr(w, "tu_vong_sinh_no_tick"):
            w.tu_vong_sinh_no_tick = set()
        if not hasattr(w, "canh_tick"):
            w.canh_tick = set()
        if not hasattr(w, "thu_hoach_cay_tick"):
            w.thu_hoach_cay_tick = []
        if not hasattr(w, "cong_cham_tre_theo_cap"):
            w.cong_cham_tre_theo_cap = {}
        if not hasattr(w, "cham_tre_tick"):
            w.cham_tre_tick = {}
        # migration ADR 0005: bờ sông (static) + qua-sông transient — checkpoint cũ (OFF)
        # nạp lại ⇒ field trung tính ⇒ replay + world_hash bất biến (§11.3)
        if not hasattr(w, "ben_kia_tick"):
            w.ben_kia_tick = set()
        for p in w.parcels.values():
            if not hasattr(p, "bo"):
                p.bo = None
        # migration ADR 0007: cư trú + di sản. Checkpoint cũ (gate OFF) nạp lại ⇒ dict RỖNG ⇒
        # key "residence"/"estate" VẪN không xuất hiện trong behavioral_state (gate vẫn OFF)
        # ⇒ world_hash y nguyên ⇒ resume run cũ không gãy. `_cu_tru_idx`/`_cu_tru_ver` là chỉ
        # mục derived (ngoài hash), dựng lại từ `cu_tru`.
        if not hasattr(w, "cu_tru"):
            w.cu_tru = {}
        if not hasattr(w, "_next_cu_tru"):
            w._next_cu_tru = 0
        if not hasattr(w, "bien_co_ho"):
            w.bien_co_ho = {}
        if not hasattr(w, "di_san"):
            w.di_san = {}
        if not hasattr(w, "di_san_xong"):
            w.di_san_xong = {}
        if not hasattr(w, "_next_di_san"):
            w._next_di_san = 0
        # Quote/escrow migration. OFF checkpoint stays hash-neutral because the commerce key is
        # omitted; ON legacy checkpoint gets an empty book, not an invented trade history.
        if not hasattr(w, "bao_gia"):
            w.bao_gia = {}
        if not hasattr(w, "_next_bao_gia"):
            w._next_bao_gia = 0
        # Generic project/work-order migration. Old checkpoints get an empty
        # registry; no past material or labour is inferred.
        if not hasattr(w, "du_an"):
            w.du_an = {}
        if not hasattr(w, "_next_du_an"):
            w._next_du_an = 0
        w._cu_tru_ver = getattr(w, "_cu_tru_ver", 0) + 1  # ép dựng lại chỉ mục
        w._cu_tru_idx = None
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
    f.dang_ky("thoc", "che_tac", "sink")  # recipe hàng mới có thể ăn thóc làm nguyên liệu
    f.dang_ky("xu", "duc_xu", "nguon")
    f.dang_ky("xu", "che_tac", "sink")  # dựng máy trả bằng xu
    f.dang_ky("cong", "sinh_cong", "nguon")
    f.dang_ky("cong", "dung", "sink")
    f.dang_ky("cong", "boc_hoi", "sink")
    f.dang_ky("cong_cu", "che_tac", "nguon")
    f.dang_ky("cong_cu", "hao_mon", "sink")
    # chăn nuôi: gà bắt từ rừng, sinh sản; giết lấy thịt; thịt ăn được, mau hỏng
    f.dang_ky("ga", "truong_thanh", "nguon")
    f.dang_ky("ga", "chet_doi_ga", "sink")
    f.dang_ky("ga", "giet_thit", "sink")
    f.dang_ky("ga_con", "bat_rung", "nguon")
    f.dang_ky("ga_con", "sinh_san", "nguon")
    f.dang_ky("ga_con", "truong_thanh", "sink")
    f.dang_ky("ga_con", "chet_doi_ga", "sink")
    f.dang_ky("ga_con", "giet_thit", "sink")
    f.dang_ky("thoc", "nuoi_ga", "sink")
    f.dang_ky("thit", "giet_thit", "nguon")
    f.dang_ky("thit", "an", "sink")
    f.dang_ky("thit", "hao_thit", "sink")
    f.dang_ky("thit", "tiec", "sink")
    f.dang_ky("thoc", "tiec", "sink")
    f.dang_ky("ca", "danh_ca", "nguon")
    f.dang_ky("ca", "an", "sink")
    f.dang_ky("ca", "hao_thit", "sink")
    # Vụ đông (scenario-gated): ngô/khoai là tài sản ăn được riêng, không đổi thóc
    # ngầm. Đăng ký vô điều kiện an toàn vì chưa dùng thì không có entry audit nào.
    for cay in ("ngo", "khoai"):
        f.dang_ky(cay, "gat", "nguon")
        f.dang_ky(cay, "an", "sink")
        f.dang_ky(cay, "hao_kho", "sink")
    f.dang_ky("cong", "cham_tre", "sink")
    f.dang_ky("nha", "xay", "nguon")
    f.dang_ky("may", "che_tac", "nguon")
    f.dang_ky("may", "hao_mon", "sink")
    # tài khóa (fiscal.bat) — thủy lợi là TÀI SẢN của CONG_QUY, chỉ dùng khi bật; đăng ký
    # vô điều kiện KHÔNG đổi hash (registry không vào world_hash; luồng không dùng → không tích lũy)
    f.dang_ky("thoc", "chi_cong", "sink")        # thóc treasury tiêu để xây thủy lợi
    f.dang_ky("go", "chi_cong", "sink")          # gỗ trưởng làng góp vào công trình
    f.dang_ky("cong", "chi_cong", "sink")        # công trưởng làng góp vào công trình
    f.dang_ky("thuy_loi", "chi_cong", "nguon")   # thủy lợi được xây (đối ứng thóc/gỗ/công)
    f.dang_ky("thuy_loi", "hao_mon", "sink")     # thủy lợi hao mòn mỗi tick
    # đò (khong_gian.bat) — thuyền là TÀI SẢN (recipe công+gỗ), phí đò = chuyen CÂN (không
    # mint tiền công). Đăng ký vô điều kiện KHÔNG đổi hash (không dùng → không tích lũy)
    f.dang_ky("thuyen", "dong_thuyen", "nguon")  # đóng thuyền (đối ứng công/gỗ)
    f.dang_ky("thuyen", "hao_mon_thuyen", "sink")  # thuyền hao mòn mỗi tick vận hành


def _ca_suc_chua(w: World) -> float:
    """Sức chứa trữ lượng cá của sông (K) = số ô sông × sức chứa mỗi ô."""
    so_o = sum(1 for p in w.parcels.values() if p.loai == "song")
    return so_o * float(w.cfg.get("danh_ca.suc_chua_moi_o_kg"))


def _ga_rung_suc_chua(w: World) -> float:
    """Sức chứa gà rừng = habitat rừng còn lại × K/ô (chỉ khi scenario bật)."""
    from engine.spatial import _ga_rung_bat

    if not _ga_rung_bat(w):
        return 0.0
    k_o = float(w.cfg.get("khong_gian.ga_rung.suc_chua_moi_o"))
    from engine.forest import _rung_bat

    if _rung_bat(w) and bool(w.cfg.get("khong_gian.ga_rung.k_theo_tan_che", True)):
        # Canopy-weighted habitat: logging can reduce K without changing the discrete parcel
        # label, which is the causal feedback required by spatial_livelihood_v2.
        return sum(
            max(0.0, min(1.0, float(getattr(p, "tan_rung", 0.0))))
            for p in w.parcels.values() if p.loai == "rung"
        ) * k_o
    so_o = sum(1 for p in w.parcels.values() if p.loai == "rung")
    return so_o * k_o


def _endowment_t0_kg(cfg: Config, la_nguoi_lon: bool) -> float:
    """Tồn kho thóc t0 mỗi thành viên. OFF (mặc định) ⇒ ``thoc_moi_nguoi`` PHẲNG (200 kg
    legacy). ON (``khong_gian.endowment.bat``, ADR 0005 §7) ⇒ một-NĂM khẩu phần
    food-equivalent quy từ ``nhu_cau``×(tick/năm) theo tuổi (design_assumption) — là tồn kho
    THẬT (giữ/tiêu/bán/vay được), KHÔNG food-mint sau tick 0 (chỉ luồng ``khoi_tao`` t0)."""
    kt = cfg.raw()["khoi_tao"]
    if not bool(cfg.get("khong_gian.endowment.bat", False)):
        return float(kt["thoc_moi_nguoi"])
    tick_moi_nam = 12.0 / float(cfg.get("thoi_gian.thang_moi_tick"))
    theo_tuoi = bool(cfg.get("khong_gian.endowment.food_equiv_theo_tuoi", True))
    kg_tick = (float(cfg.get("nhu_cau.nguoi_lon_kg_tick"))
               if (la_nguoi_lon or not theo_tuoi)
               else float(cfg.get("nhu_cau.tre_em_kg_tick")))
    return kg_tick * tick_moi_nam


def tao_the_gioi(cfg: Config, seed: int, events_path: Path | None = None) -> World:
    """Khởi tạo thế giới t0: bản đồ + người lớn độc thân (tham số mục khoi_tao), 0 đất."""
    from engine.household import khoi_tao_cu_tru, kiem_tra_cau_hinh

    # Fail-closed TRƯỚC khi có world nào tồn tại (ADR 0007 §D.6/§G.2): cấu hình route di sản
    # về một sink không có drain thì DỪNG, không có nhánh "chạy tạm rồi tính sau".
    kiem_tra_cau_hinh(cfg)
    rng = RngTree(seed)
    w = World(cfg=cfg, seed=seed, rng=rng, events=EventLog(events_path))
    dang_ky_flows(w.ledger)
    g = rng.get("khoi_tao", 0)
    w.parcels, w.villages = sinh_ban_do(cfg, g)
    w.ca_ton = _ca_suc_chua(w) * float(cfg.get("danh_ca.ty_le_ton_ban_dau"))
    ga_k = _ga_rung_suc_chua(w)
    w.ga_rung_ton = (
        ga_k * float(cfg.get("khong_gian.ga_rung.ty_le_ton_ban_dau", 0.0))
        if ga_k > 0 else None
    )

    n = cfg.get("nhan_khau.dan_so_ban_dau")
    tuoi_min, tuoi_max = cfg.get("nhan_khau.tuoi_ban_dau")
    ty_le_nu = cfg.get("nhan_khau.ty_le_nu")
    kt = cfg.raw()["khoi_tao"]
    p_min, p_max = int(kt["persona_min"]), int(kt["persona_max"])
    nguong_e1, nguong_e2 = (float(x) for x in kt["phan_bo_e"])
    tuoi_tt = int(cfg.get("nhan_khau.tuoi_truong_thanh"))
    for i in range(n):
        aid = w.id_moi()
        gioi = "nu" if g.random() < ty_le_nu else "nam"
        persona = Persona(*(int(x) for x in g.integers(p_min, p_max + 1, size=5)))  # s5: 5 trục persona
        # phân bố E ban đầu (xem DECISIONS.md — gieo mầm tri thức tối thiểu)
        r = g.random()
        e0 = 0 if r < nguong_e1 else (1 if r < nguong_e2 else 2)
        w.agents[aid] = Agent(
            id=aid,
            ten=f"{HO_TEN[i % len(HO_TEN)]} {i + 1}",
            gioi_tinh=gioi,
            tuoi_tick=int(g.integers(tuoi_min * 2, tuoi_max * 2 + 1)),
            persona=persona,
            lang=0,
            e_bac=e0,
        )
        # Neo giá thuộc về tác nhân, được rút từ stream RNG riêng để thêm cơ chế này không
        # làm trôi giới/persona/học vấn của các agent còn lại.
        from engine.pricing import khoi_tao_gia_ky_vong

        w.agents[aid].gia_ky_vong = khoi_tao_gia_ky_vong(
            w, aid, rng.get(f"gia_ky_vong:{aid}", 0)
        )
        endow = _endowment_t0_kg(cfg, w.agents[aid].truong_thanh(tuoi_tt))
        w.ledger.sinh(aid, "thoc", endow, "khoi_tao", "tài sản khởi đầu", tick=0)
        w.events.ghi(0, "sinh", id=aid, ten=w.agents[aid].ten, khoi_tao=True)
    # Cư trú t0 (no-op khi gate TẮT): mỗi agent một hộ riêng — dân số t0 toàn người lớn độc
    # thân; id cấp theo sorted(w.agents) ⇒ tất định.
    khoi_tao_cu_tru(w)
    return w
