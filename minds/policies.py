"""Tầng hành vi thay thế được (MODEL_CHARTER §3 Lớp-4, ADR 0002).

Một ``BehaviorPolicy`` là hàm thuần `(World) -> {aid: KeHoach}`: CHỈ ĐỌC world và trả
ý định; engine validate + thi hành (điều luật #3). Không policy nào được chạm state,
đặt giá, hay tạo tài nguyên. Mọi ngẫu nhiên đi qua ``w.rng`` để cùng seed + cùng policy
→ cùng world-hash (điều luật #4).

Kết luận cơ chế chính của benchmark KHÔNG được phụ thuộc LLM: các baseline không-mạng ở
đây (rulebot / feasible_random / subsistence) là nền để đo tác động của cơ chế tách khỏi
"policy thông minh". LLM (mock/real) chỉ là treatment sau cùng (ADR 0002 §D).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from engine.intents import KeHoach
from engine.market import Lenh
from engine.spatial import _hai_bo_bat
from engine.world import World
from minds.rulebot import (
    _BoiCanhTick,
    _chon_thua_canh,
    hanh_vi_khong_gian,
    quyet_dinh_tat_ca,
)

# Version bump khi logic policy đổi (vào manifest để phân biệt run cùng seed khác hành vi).
RULEBOT_VERSION = "1.0.0"
FEASIBLE_RANDOM_VERSION = "0.1.0"
SUBSISTENCE_VERSION = "0.1.0"
ADAPTIVE_VERSION = "1.0.0"
SPATIAL_SURVIVAL_VERSION = "1.0.0"


@runtime_checkable
class BehaviorPolicy(Protocol):
    """Contract Lớp-4: định danh ổn định + version + params khai báo, gọi được như hàm."""

    name: str
    version: str
    params: dict

    def __call__(self, w: World) -> dict[str, KeHoach]: ...


def _he_so_cong(w: World, a) -> float:
    """Hệ số sức lao động theo tuổi — KHỚP ``production.sinh_cong`` để ước lượng công."""
    ld = w.cfg.raw()["lao_dong_theo_tuoi"]
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    tuoi_gop = float(w.cfg.get("nhu_cau.tre_em_gop_cong_tu_tuoi"))
    if a.tuoi_nam > float(ld["tuoi_nghi"]):
        return float(ld["he_so_sau_nghi"])
    if a.tuoi_nam > float(ld["tuoi_giam_suc"]):
        return float(ld["he_so_sau_giam"])
    if a.truong_thanh(tt):
        return 1.0
    if a.tuoi_nam >= tuoi_gop:
        return float(w.cfg.get("nhu_cau.ty_le_cong_tre_em"))
    return 0.0


def _cap_thua_kha_thi(w: World, aid: str, a, chua_giong: float = 0.0) -> int:
    """Số thửa TỰ CANH khả thi tối đa cho agent: rào giống (thóc riêng) ∩ rào công.

    Ước lượng công theo đúng công thức sinh công của engine (không đọc số dư 'cong' vì
    công chưa sinh ở thời điểm quyết định). ``chua_giong`` = thóc phải chừa lại (lương ăn).
    Không tính máy (giữ ước lượng bảo thủ → intent luôn khả thi, không bị lọc).
    """
    giong = float(w.cfg.get("san_xuat.giong_kg_moi_thua"))
    cong_moi_thua = float(w.cfg.get("san_xuat.cong_moi_thua"))
    ngay_cong = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
    thua_toi_da = int(w.cfg.get("san_xuat.thua_toi_da_tu_canh"))
    thoc = w.ledger.so_du(aid, "thoc")
    cap_giong = int(max(0.0, thoc - chua_giong) // giong)
    cong_uoc = ngay_cong * (a.health / 100.0) * _he_so_cong(w, a)
    cap_cong = int(cong_uoc // cong_moi_thua)
    return max(0, min(thua_toi_da, cap_giong, cap_cong))


class RulebotPolicy:
    """Baseline hợp lệ: bọc nguyên rulebot heuristic (KHÔNG chẻ nhỏ — named-strategy split
    là future work). Tất định theo (seed, agent, tick)."""

    name = "rulebot"
    version = RULEBOT_VERSION

    def __init__(self) -> None:
        self.params: dict = {}

    def __call__(self, w: World) -> dict[str, KeHoach]:
        return quyet_dinh_tat_ca(w)


class FeasibleRandomPolicy:
    """NEGATIVE baseline: mỗi người lớn (sorted id) chọn NGẪU NHIÊN (seeded) trong tập
    hành động KHẢ THI tối thiểu — canh 0..cap thửa sở hữu/công trống trong mùa mưa, hoặc
    khai thác gỗ trong mùa khô, hoặc nghỉ. Không hợp đồng/đầu tư. Dùng để chứng minh kết
    quả đến từ CƠ CHẾ, không phải "policy thông minh"."""

    name = "feasible_random"
    version = FEASIBLE_RANDOM_VERSION

    def __init__(self) -> None:
        self.params: dict = {"p_lam_mua_kho": 0.5}

    def __call__(self, w: World) -> dict[str, KeHoach]:
        tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        ngay_cong = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
        p_kho = float(self.params["p_lam_mua_kho"])
        bc = _BoiCanhTick(w)
        da_nham: set[str] = set()
        g = w.rng.get("policy_random", w.tick)  # 1 generator/tick, tiêu theo sorted-id
        ke_hoach: dict[str, KeHoach] = {}
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song:
                continue
            kh = KeHoach(id=aid)
            if a.truong_thanh(tt):
                if w.mua_mua():
                    cap = _cap_thua_kha_thi(w, aid, a)
                    so_thua = int(g.integers(0, cap + 1)) if cap >= 1 else 0
                    if so_thua > 0:
                        kh.canh_thua = _chon_thua_canh(bc, aid, so_thua, da_nham)
                elif g.random() < p_kho:
                    # khai thác gỗ chỉ tốn công (engine cap theo công có sẵn) → luôn khả thi
                    he_so = 0.5 if g.random() < 0.5 else 1.0
                    kh.cong_khai_go = round(ngay_cong * he_so * (a.health / 100.0), 1)
            ke_hoach[aid] = kh
        return ke_hoach


class SubsistencePolicy:
    """Luôn ưu tiên canh đủ ăn: mùa mưa canh TỐI ĐA thửa khả thi (chừa lại một tick lương
    ăn của hộ), không hợp đồng/đầu tư. Tất định (không dùng rng)."""

    name = "subsistence"
    version = SUBSISTENCE_VERSION

    def __init__(self) -> None:
        self.params: dict = {}

    def __call__(self, w: World) -> dict[str, KeHoach]:
        tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        an_nguoi_lon = float(w.cfg.get("nhu_cau.nguoi_lon_kg_tick"))
        bc = _BoiCanhTick(w)
        da_nham: set[str] = set()
        ke_hoach: dict[str, KeHoach] = {}
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song:
                continue
            kh = KeHoach(id=aid)
            if w.mua_mua() and a.truong_thanh(tt):
                # chừa một tick lương ăn của bản thân trước khi lấy thóc làm giống
                cap = _cap_thua_kha_thi(w, aid, a, chua_giong=an_nguoi_lon)
                if cap >= 1:
                    kh.canh_thua = _chon_thua_canh(bc, aid, cap, da_nham)
            ke_hoach[aid] = kh
        return ke_hoach


class AdaptivePolicy:
    """Kỳ vọng giá thích nghi (EWMA) + tiết kiệm phòng ngừa trên nền tự cung tự cấp
    (ADR 0002 §C.3, REVIEW §4.4).

    Nền hành vi = subsistence (mùa mưa canh TỐI ĐA thửa khả thi để đủ ăn) nhưng mức
    dự trữ MỤC TIÊU co giãn theo kỳ vọng giá và thời tiết:

    - Kỳ vọng giá thóc thích nghi ``E_t = α·p_t + (1-α)·E_{t-1}`` với ``p_t`` là giá
      thóc quan sát (``w.gia_tb_4_tick`` → ``gia_gan_nhat`` → 1.0 bản vị). Biên độ lệch
      ``|p_t - E_{t-1}|`` được làm trơn thành ``_vol`` (đo biến động kỳ vọng).
    - Tiết kiệm phòng ngừa: dự trữ mục tiêu = lương ăn·``buffer_ticks``·(1 + κ·(biến động
      giá chuẩn hóa + thời tiết xấu)). Biến động cao / hạn-lụt ⇒ giữ nhiều thóc hơn.
    - Khi NO ĐỦ (thóc ≥ dự trữ mục tiêu): mùa khô ĐẦU TƯ công dư đi khai thác gỗ (tài
      sản trữ được), và BÁN phần thóc VƯỢT dự trữ — bán mạnh hơn khi giá hiện ≥ kỳ vọng
      (thời điểm thuận). Khi dưới mục tiêu: thu mình, không bán, không đầu tư.

    Trạng thái kỳ vọng (``_E``, ``_vol``, ``_E_tick``) là NỘI BỘ policy — KHÔNG ghi vào
    world, KHÔNG vào world-hash. Nó là hàm TẤT ĐỊNH của chuỗi giá (world theo seed) nên
    replay (dựng lại policy từ manifest rồi chạy lại cùng chuỗi tick) tái lập y hệt
    (ADR 0002 §A.2). Cập nhật kỳ vọng idempotent trong một tick (gọi lại cùng tick không
    trôi state) để no-mutation/gọi lặp vẫn tất định. Không dùng ``w.rng`` (thuần tất định).
    """

    name = "adaptive"
    version = ADAPTIVE_VERSION

    def __init__(self) -> None:
        self.params: dict = {
            "alpha": 0.5,             # trọng số giá mới trong EWMA kỳ vọng
            "he_so_phong_ngua": 0.6,  # κ: khuếch đại dự trữ khi biến động/thời tiết xấu
            "buffer_ticks": 3.0,      # số tick lương ăn làm dự trữ nền
        }
        self._E: float | None = None  # kỳ vọng giá thóc hiện thời (nội bộ)
        self._vol: float = 0.0        # EWMA biên độ lệch |p - E| (biến động kỳ vọng)
        self._E_tick: int = -1        # tick đã cập nhật kỳ vọng gần nhất (idempotent/tick)

    def _gia_thoc(self, w: World) -> float:
        """Tín hiệu giá thóc p_t: trung bình cửa sổ → giá gần nhất → 1.0 (thóc là bản vị)."""
        p = w.gia_tb_4_tick("thoc")
        if p is None:
            p = w.gia_gan_nhat("thoc")
        return float(p) if p is not None and p > 0 else 1.0

    def _cap_nhat_ky_vong(self, w: World) -> None:
        """EWMA E_t = α·p_t + (1-α)·E_{t-1}; idempotent trong cùng tick (an toàn replay)."""
        if w.tick <= self._E_tick:
            return
        alpha = float(self.params["alpha"])
        p_t = self._gia_thoc(w)
        if self._E is None:
            self._E = p_t
        else:
            self._vol = alpha * abs(p_t - self._E) + (1.0 - alpha) * self._vol
            self._E = alpha * p_t + (1.0 - alpha) * self._E
        self._E_tick = w.tick

    def _du_tru_muc_tieu(self, w: World, an_nguoi_lon: float) -> float:
        """Dự trữ mục tiêu = lương ăn·buffer·(1 + κ·(biến động giá + thời tiết xấu))."""
        kappa = float(self.params["he_so_phong_ngua"])
        buffer_ticks = float(self.params["buffer_ticks"])
        vol_ratio = self._vol / max(self._E or 1.0, 1e-9)
        loai_tt, _ = w.thoi_tiet(w.tick)  # thời tiết năm hiện tại (công khai, đã hiện thực)
        xau = 1.0 if loai_tt == "han_lu" else 0.0
        m_pn = 1.0 + kappa * (min(vol_ratio, 1.0) + xau)
        return an_nguoi_lon * buffer_ticks * m_pn

    def __call__(self, w: World) -> dict[str, KeHoach]:
        self._cap_nhat_ky_vong(w)
        tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        an_nguoi_lon = float(w.cfg.get("nhu_cau.nguoi_lon_kg_tick"))
        ngay_cong = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
        du_tru = self._du_tru_muc_tieu(w, an_nguoi_lon)
        p_t = self._gia_thoc(w)
        gia_go = w.gia_gan_nhat("go") or 12.0
        gia_thoc_go = w.gia_gan_nhat("thoc/go") or (1.0 / gia_go)
        bc = _BoiCanhTick(w)
        da_nham: set[str] = set()
        ke_hoach: dict[str, KeHoach] = {}
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song:
                continue
            kh = KeHoach(id=aid)
            if a.truong_thanh(tt):
                thoc = w.ledger.so_du(aid, "thoc")
                no_du = thoc >= du_tru
                if w.mua_mua():
                    # nền tự cung: canh tối đa thửa khả thi, chừa một tick lương ăn
                    cap = _cap_thua_kha_thi(w, aid, a, chua_giong=an_nguoi_lon)
                    if cap >= 1:
                        kh.canh_thua = _chon_thua_canh(bc, aid, cap, da_nham)
                elif no_du:
                    # mùa khô + no đủ: đầu tư công dư khai thác gỗ (tài sản trữ/bán được)
                    kh.cong_khai_go = round(ngay_cong * 0.5 * (a.health / 100.0), 1)
                # điều chỉnh: bán phần thóc VƯỢT dự trữ phòng ngừa theo kỳ vọng giá
                if thoc > du_tru and gia_thoc_go > 0:
                    surplus = thoc - du_tru
                    thuan = self._E is not None and p_t >= self._E
                    ty_le_ban = 0.5 if thuan else 0.25
                    so_ban = round(min(surplus * ty_le_ban, thoc), 0)
                    if so_ban >= 1:
                        kh.dat_lenh.append(
                            Lenh(aid, "ban", "thoc", so_ban,
                                 round(gia_thoc_go * 0.97, 4), thanh_toan="go")
                        )
            ke_hoach[aid] = kh
        return ke_hoach


class SpatialSurvivalPolicy(AdaptivePolicy):
    """Sinh kế KHÔNG GIAN trên NỀN adaptive (ADR 0005 §9): dự trữ hộ → canh → chợ/đò.

    OFF (``khong_gian.hai_bo`` tắt, mặc định) ⇒ trả Y HỆT ``AdaptivePolicy`` (legacy): không
    dựng ``_BoiCanhTick``, không phát intent không-gian ⇒ world-hash trùng adaptive. ON ⇒ phủ
    thêm rao đò / qua sông / đóng thuyền (``rulebot.hanh_vi_khong_gian``) cho người THIẾU đất
    khi bờ kia còn tài nguyên công. Chỉ ĐỌC world + mutate KeHoach; tất định qua ``w.rng``
    (điều luật #3, #4).

    KHÔNG vào ``REGISTRY`` (giữ nguyên contract 4-policy đã có + run.py dùng rulebot+overlay
    làm phương tiện spatial chính); dựng trực tiếp khi cần benchmark policy thuần adaptive+đò.
    """

    name = "spatial_survival"
    version = SPATIAL_SURVIVAL_VERSION

    def __call__(self, w: World) -> dict[str, KeHoach]:
        ke_hoach = super().__call__(w)  # nền adaptive (cập nhật kỳ vọng + canh/bán)
        if not _hai_bo_bat(w):
            return ke_hoach  # OFF ⇒ nền adaptive nguyên vẹn (legacy)
        tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        an_lon = float(w.cfg.get("nhu_cau.nguoi_lon_kg_tick"))
        du_tru = self._du_tru_muc_tieu(w, an_lon)  # kỳ vọng đã cập nhật trong super()
        bc = _BoiCanhTick(w)
        for aid in sorted(w.agents):
            a = w.agents[aid]
            if not a.con_song or not a.truong_thanh(tt):
                continue
            kh = ke_hoach.get(aid)
            if kh is None:
                continue
            an_ninh = w.ledger.so_du(aid, "thoc") / du_tru if du_tru > 0 else 1.0
            hanh_vi_khong_gian(w, a, kh, bc, an_ninh)
        return ke_hoach


REGISTRY: dict[str, type[BehaviorPolicy]] = {
    "rulebot": RulebotPolicy,
    "feasible_random": FeasibleRandomPolicy,
    "subsistence": SubsistencePolicy,
    "adaptive": AdaptivePolicy,
}


def tao_policy(name: str) -> BehaviorPolicy:
    """Dựng policy theo tên từ REGISTRY (dùng bởi run.py --policy và replay)."""
    lop = REGISTRY.get(name)
    if lop is None:
        ten = ", ".join(sorted(REGISTRY))
        raise SystemExit(f"Policy không hỗ trợ: {name!r}. Có: {ten}.")
    return lop()
