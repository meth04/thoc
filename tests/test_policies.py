"""BehaviorPolicy Lớp-4 (ADR 0002): feasible, no-mutation, swap, determinism, ordering.

Kiểm chứng contract hành vi thay thế được — baseline không-mạng phải khả thi, tất định,
không chạm state; đổi policy có tác động (world-hash khác) nhưng audit luôn xanh.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.config import load_config
from engine.spatial import _bo_cua
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.policies import (
    REGISTRY,
    AdaptivePolicy,
    BehaviorPolicy,
    FeasibleRandomPolicy,
    SpatialSurvivalPolicy,
    tao_policy,
)
from minds.rulebot import quyet_dinh_tat_ca
from tests.helpers import chay_tick, the_gioi_test


def _the_gioi(seed: int = 7, thoc: float = 300.0):
    return the_gioi_test(seed=seed, giu_lai=10, thoc_moi_nguoi=thoc)


def _hash_sau_k_tick(name: str, seed: int, k: int) -> str:
    w = _the_gioi(seed=seed)
    chay_tick(w, tao_policy(name), k)  # audit raise trong chay_mot_tick nếu bảo toàn hỏng
    return w.world_hash()


@pytest.mark.parametrize("name", ["feasible_random", "subsistence"])
def test_intent_phan_lon_kha_thi(name: str) -> None:
    """Engine không được bỏ >50% canh_thua đã phát (baseline chủ yếu khả thi)."""
    w = _the_gioi()
    pol = tao_policy(name)
    captured: dict = {}

    def wrap(world, _p=pol, _c=captured):
        plans = _p(world)
        _c.clear()
        _c.update(plans)
        return plans

    chay_mot_tick(w, wrap, len(w.parcels))  # tick 1 = mùa mưa
    assert w.mua_mua()
    issued = {(aid, pid) for aid, kh in captured.items() for pid in kh.canh_thua}
    assert issued, "baseline phải phát canh_thua ở mùa gieo"
    farmed = {(aid, pid) for pid, (aid, _kg) in w.gat_tick.items()}
    lot = issued - farmed
    assert len(lot) <= 0.5 * len(issued), f"{name}: {len(lot)}/{len(issued)} intent bị lọc"


@pytest.mark.parametrize("name", ["rulebot", "feasible_random", "subsistence"])
def test_khong_mutate_world_khi_goi_policy(name: str) -> None:
    """Gọi policy chỉ ĐỌC world: world-hash trước == sau (điều luật #3, ADR 0002 §A.1)."""
    w = _the_gioi(seed=5)
    w.tick = 1  # mùa mưa, buộc nhánh canh tác chạy
    pol = tao_policy(name)
    truoc = w.world_hash()
    pol(w)
    assert w.world_hash() == truoc


def test_policy_swap_khac_hash_nhung_audit_xanh() -> None:
    """Cùng seed, đổi policy → world-hash KHÁC (có tác động); cả hai audit xanh."""
    h_rulebot = _hash_sau_k_tick("rulebot", seed=7, k=8)
    h_random = _hash_sau_k_tick("feasible_random", seed=7, k=8)
    h_subs = _hash_sau_k_tick("subsistence", seed=7, k=8)
    assert len({h_rulebot, h_random, h_subs}) == 3


@pytest.mark.parametrize("name", ["rulebot", "feasible_random", "subsistence"])
def test_tat_dinh_cung_seed_cung_policy(name: str) -> None:
    """Cùng seed + cùng policy chạy 2 lần → world-hash trùng (điều luật #4)."""
    assert _hash_sau_k_tick(name, seed=11, k=6) == _hash_sau_k_tick(name, seed=11, k=6)


def test_ordering_invariance_theo_sorted_id() -> None:
    """Xáo thứ tự chèn agent không đổi kết quả policy (apply theo sorted-id)."""
    w1 = _the_gioi(seed=3)
    w2 = _the_gioi(seed=3)
    w1.tick = w2.tick = 1
    w2.agents = {aid: w2.agents[aid] for aid in reversed(list(w2.agents))}
    pol = FeasibleRandomPolicy()
    r1 = {aid: kh.canh_thua for aid, kh in pol(w1).items()}
    r2 = {aid: kh.canh_thua for aid, kh in pol(w2).items()}
    assert r1 == r2 and any(r1.values())


def test_registry_va_factory() -> None:
    assert set(REGISTRY) == {"rulebot", "feasible_random", "subsistence", "adaptive"}
    for name in REGISTRY:
        pol = tao_policy(name)
        assert isinstance(pol, BehaviorPolicy)
        assert pol.name == name and isinstance(pol.version, str) and isinstance(pol.params, dict)
    with pytest.raises(SystemExit):
        tao_policy("khong_ton_tai")


def test_adaptive_params_vao_manifest() -> None:
    """adaptive (đã cài, ADR 0002 §C.3) khai báo alpha + hệ số phòng ngừa → manifest."""
    pol = AdaptivePolicy()
    assert isinstance(pol, BehaviorPolicy)
    assert {"alpha", "he_so_phong_ngua", "buffer_ticks"} <= set(pol.params)
    assert pol.name == "adaptive" and pol.version == "1.0.0"


def test_adaptive_chay_that_feasible_va_audit_xanh() -> None:
    """adaptive canh khả thi ở mùa gieo (không bị lọc >50%); chạy nhiều tick audit xanh."""
    w = _the_gioi()
    pol = tao_policy("adaptive")
    captured: dict = {}

    def wrap(world, _p=pol, _c=captured):
        plans = _p(world)
        _c.clear()
        _c.update(plans)
        return plans

    chay_mot_tick(w, wrap, len(w.parcels))  # tick 1 = mùa mưa
    assert w.mua_mua()
    issued = {(aid, pid) for aid, kh in captured.items() for pid in kh.canh_thua}
    assert issued, "adaptive phải phát canh_thua ở mùa gieo"
    farmed = {(aid, pid) for pid, (aid, _kg) in w.gat_tick.items()}
    lot = issued - farmed
    assert len(lot) <= 0.5 * len(issued), f"adaptive: {len(lot)}/{len(issued)} intent bị lọc"
    chay_tick(w, pol, 5)  # audit raise trong chay_mot_tick nếu bảo toàn hỏng


def test_adaptive_tat_dinh_cung_seed() -> None:
    """Cùng seed + adaptive chạy 2 lần → world-hash trùng (điều luật #4, state kỳ vọng nội bộ)."""
    assert _hash_sau_k_tick("adaptive", seed=11, k=6) == _hash_sau_k_tick("adaptive", seed=11, k=6)


def test_adaptive_khong_mutate_world() -> None:
    """Gọi adaptive chỉ ĐỌC world: world-hash trước == sau (state kỳ vọng KHÔNG vào world)."""
    w = _the_gioi(seed=5)
    w.tick = 1  # mùa mưa, buộc nhánh canh tác chạy
    pol = tao_policy("adaptive")
    truoc = w.world_hash()
    pol(w)
    assert w.world_hash() == truoc


def test_adaptive_swap_khac_rulebot() -> None:
    """Cùng seed, adaptive vs rulebot → world-hash KHÁC (có tác động); cả hai audit xanh."""
    assert _hash_sau_k_tick("adaptive", seed=7, k=8) != _hash_sau_k_tick("rulebot", seed=7, k=8)


# ===================== T13 — sinh kế KHÔNG GIAN (ADR 0005 §9) =====================
# Cơ chế mới scenario-gated OFF: OFF ⇒ hành vi + world-hash legacy y nguyên; ON (overlay hai
# bờ) ⇒ policy phát rao_do/qua_song/dong_thuyen khi có động cơ (đất/tài nguyên bờ kia), audit
# xanh, feasible, tất định, no-mutation. KHÔNG ép mọi agent qua sông.

_OVERLAY_SPATIAL = (
    Path(__file__).resolve().parents[1]
    / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
)


def _the_gioi_2bo(seed: int = 41, giu_lai: int = 10, thoc: float = 600.0):
    """Thế giới nhỏ HAI BỜ (overlay spatial_v1 BẬT): trim còn ``giu_lai`` agent + nạp thóc,
    tương tự ``the_gioi_test`` nhưng dùng config có ``khong_gian.hai_bo``."""
    w = tao_the_gioi(load_config(overlays=[_OVERLAY_SPATIAL]), seed)
    ids = sorted(w.agents)
    for aid in ids[giu_lai:]:
        w.agents[aid].con_song = False
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "rời cuộc chơi (fixture)", 0)
    for aid in ids[:giu_lai]:
        hien = w.ledger.so_du(aid, "thoc")
        if thoc > hien:
            w.ledger.sinh(aid, "thoc", thoc - hien, "khoi_tao", "fixture", 0)
        w.agents[aid].health = 100.0
    return w


def _cap_thuyen(w, so_agent: int = 2) -> list[str]:
    """Cấp thuyền cho vài agent NGƯỜI LỚN đầu tiên qua luồng nguồn ``dong_thuyen`` (audit-safe)."""
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    cap: list[str] = []
    for aid in sorted(w.agents):
        if len(cap) >= so_agent:
            break
        a = w.agents[aid]
        if a.con_song and a.truong_thanh(tt):
            w.ledger.sinh(aid, "thuyen", 1.0, "dong_thuyen", "fixture thuyền", 0)
            cap.append(aid)
    return cap


def _capture(pol):
    """Bọc policy để bắt kế hoạch tick cuối (kiểm intent phát ra)."""
    box: dict = {}

    def wrap(world, _p=pol, _b=box):
        plans = _p(world)
        _b.clear()
        _b.update(plans)
        return plans

    return wrap, box


def test_khong_gian_OFF_rulebot_khong_phat_intent() -> None:
    """OFF (base config): rulebot KHÔNG phát rao_do/qua_song/dong_thuyen ⇒ nhánh không-gian
    ngủ hoàn toàn ⇒ hành vi + world-hash legacy y nguyên (ADR 0005 §11.4)."""
    w = _the_gioi(seed=7)
    wrap, box = _capture(tao_policy("rulebot"))
    for _ in range(4):
        chay_mot_tick(w, wrap, len(w.parcels))
        assert not any(kh.rao_do or kh.qua_song or kh.dong_thuyen for kh in box.values())


def test_spatial_survival_OFF_bang_adaptive() -> None:
    """OFF ⇒ SpatialSurvivalPolicy trả Y HỆT AdaptivePolicy (world-hash trùng = legacy)."""
    h_adaptive = _hash_sau_k_tick("adaptive", seed=11, k=6)
    w = _the_gioi(seed=11)
    chay_tick(w, SpatialSurvivalPolicy(), 6)
    assert w.world_hash() == h_adaptive


def test_khong_gian_ON_rulebot_phat_intent_va_qua_song() -> None:
    """ON: chủ thuyền rao đò + tự qua sông (thiếu đất) ⇒ phát rao_do/qua_song, chuyến THÀNH
    (ben_kia_tick không rỗng = feasible); audit xanh mỗi tick."""
    w = _the_gioi_2bo(seed=13)
    _cap_thuyen(w, 2)
    wrap, box = _capture(tao_policy("rulebot"))
    saw_rao = saw_qua = saw_cross = False
    for _ in range(4):
        chay_mot_tick(w, wrap, len(w.parcels))  # audit raise nếu bảo toàn hỏng
        saw_rao = saw_rao or any(kh.rao_do for kh in box.values())
        saw_qua = saw_qua or any(kh.qua_song for kh in box.values())
        saw_cross = saw_cross or bool(w.ben_kia_tick)
    assert saw_rao and saw_qua, "rulebot ON phải phát rao_do + qua_song khi có động cơ bờ kia"
    assert saw_cross, "ít nhất một chuyến qua sông THÀNH CÔNG (feasible, không lọc hàng loạt)"


def test_khong_gian_ON_dong_thuyen_kha_thi() -> None:
    """ON: agent THIẾU đất + đủ gỗ + persona tiên phong ⇒ đóng thuyền ở MÙA KHÔ; thuyền THÀNH
    (feasible). Chạy đúng MỘT tick khô để gỗ chưa bị bán trước khi đóng."""
    w = _the_gioi_2bo(seed=21, thoc=1200.0)
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    aid = next(x for x in sorted(w.agents)
               if w.agents[x].con_song and w.agents[x].truong_thanh(tt)
               and _bo_cua(w, x) == "dan_cu")
    a = w.agents[aid]
    a.persona.lieu_linh, a.persona.cham_chi = 8, 7
    w.ledger.sinh(aid, "go", 12.0, "khai_thac", "fixture gỗ", 0)
    w.tick = 2  # sau chay_mot_tick → tick 3 (mùa đông của calendar 3-mùa)
    wrap, box = _capture(quyet_dinh_tat_ca)
    chay_mot_tick(w, wrap, len(w.parcels))
    assert box[aid].dong_thuyen > 0, "agent tiên phong đủ gỗ phải phát dong_thuyen mùa khô"
    assert w.ledger.so_du(aid, "thuyen") >= 1.0, "thuyền phải được đóng THÀNH (feasible)"


def _hash_2bo(pol_factory, seed: int, k: int) -> str:
    w = _the_gioi_2bo(seed=seed)
    _cap_thuyen(w, 2)
    chay_tick(w, pol_factory(), k)
    return w.world_hash()


@pytest.mark.parametrize("pol_factory", [lambda: tao_policy("rulebot"), SpatialSurvivalPolicy])
def test_khong_gian_ON_tat_dinh(pol_factory) -> None:
    """ON: cùng seed + cùng policy chạy 2 lần → world-hash trùng (điều luật #4, kể cả
    ``ben_kia_tick``/``thuyen`` tái lập được)."""
    assert _hash_2bo(pol_factory, seed=13, k=6) == _hash_2bo(pol_factory, seed=13, k=6)


@pytest.mark.parametrize("pol_factory", [lambda: tao_policy("rulebot"), SpatialSurvivalPolicy])
def test_khong_gian_ON_khong_mutate(pol_factory) -> None:
    """ON: gọi policy chỉ ĐỌC world — world-hash trước == sau (điều luật #3); ``ben_kia_tick``
    do engine nạp ở tick, KHÔNG do policy ghi."""
    w = _the_gioi_2bo(seed=5)
    _cap_thuyen(w, 2)
    w.tick = 1
    pol = pol_factory()
    truoc = w.world_hash()
    pol(w)
    assert w.world_hash() == truoc


def test_spatial_survival_ON_phat_intent_va_audit_xanh() -> None:
    """ON: SpatialSurvivalPolicy (nền adaptive) phủ thêm intent không-gian — chủ thuyền rao
    đò/qua sông; chạy nhiều tick audit xanh."""
    w = _the_gioi_2bo(seed=13)
    _cap_thuyen(w, 2)
    wrap, box = _capture(SpatialSurvivalPolicy())
    saw = False
    for _ in range(4):
        chay_mot_tick(w, wrap, len(w.parcels))  # audit raise nếu bảo toàn hỏng
        saw = saw or any(kh.rao_do or kh.qua_song for kh in box.values())
    assert saw, "SpatialSurvivalPolicy ON phải phát intent không-gian (rao đò / qua sông)"
