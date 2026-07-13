"""Regression tests for seasonal livelihoods, commons, care labor and state integrity.

All tests are local/deterministic. They deliberately exercise engine primitives directly,
not a real provider, so a passing suite does not spend an LLM request.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import care, chan_nuoi, consumption, contracts
from engine.config import load_config
from engine.contracts import ClauseGopCong, HopDong
from engine.intents import KeHoach
from engine.pricing import cap_nhat_gia_ky_vong, gia_ky_vong
from engine.tick import chay_mot_tick
from engine.world import World, _ga_rung_suc_chua, tao_the_gioi

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
)


def _world(seed: int = 17):
    return tao_the_gioi(load_config(overlays=[OVERLAY]), seed)


def _empty_plans(w):
    return {aid: KeHoach(id=aid) for aid, a in w.agents.items() if a.con_song}


def test_vu_dong_tao_tai_san_an_duoc_va_khong_mint_thoc():
    w = _world()
    aid = sorted(w.agents)[0]
    parcel = next(p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    parcel.chu = aid
    w.ledger.sinh(aid, "thoc", 5_000.0, "khoi_tao", "fixture", w.tick)

    def mind(world):
        plans = _empty_plans(world)
        if world.mua_mua():  # hai mùa lúa đầu năm, cùng dùng thửa theo các tick khác nhau
            plans[aid].canh_thua = [parcel.id]
        if world.mua() == "dong":  # tick thứ ba: vụ đông sau hai vụ lúa
            plans[aid].canh_vu_dong = [(parcel.id, "ngo")]
        return plans

    chay_mot_tick(w, mind, len(w.parcels))
    chay_mot_tick(w, mind, len(w.parcels))
    thoc_before = w.ledger.so_du(aid, "thoc")
    chay_mot_tick(w, mind, len(w.parcels))

    ngo = w.ledger.so_du(aid, "ngo")
    assert ngo > 0.0
    assert any(item["cay"] == "ngo" for item in w.thu_hoach_cay_tick)
    # Vụ đông dùng công và mint NGO, không được lén tạo thêm thóc.
    assert w.ledger.so_du(aid, "thoc") <= thoc_before

    # Khi hết lúa, ngô thực sự nuôi hộ (không chỉ là một commodity để hiển thị).
    con_thoc = w.ledger.so_du(aid, "thoc")
    if con_thoc > 0:
        w.ledger.huy(aid, "thoc", con_thoc, "an", "fixture bỏ lúa", w.tick)
    ngo_before = w.ledger.so_du(aid, "ngo")
    consumption.an_va_suc_khoe(w)
    assert w.ledger.so_du(aid, "ngo") < ngo_before


def test_calendar_spatial_co_hai_vu_lua_mot_vu_dong_va_tuoi_dung_nam():
    """Calendar spatial là 3 mùa 4 tháng; legacy không bị đổi ngầm sang đơn vị mới."""
    w = _world(19)
    aid = sorted(w.agents)[0]
    tuoi_truoc = w.agents[aid].tuoi_nam
    assert w.tick_moi_nam() == 3
    assert [w.mua(t) for t in (1, 2, 3)] == ["lua_1", "lua_2", "dong"]
    assert w.thoi_tiet(1) == w.thoi_tiet(2) == w.thoi_tiet(3)

    for _ in range(3):
        chay_mot_tick(w, _empty_plans, len(w.parcels))
    assert w.agents[aid].tuoi_nam == pytest.approx(tuoi_truoc + 1.0)
    assert w.nam() == 1

    legacy = tao_the_gioi(load_config(), 19)
    assert legacy.tick_moi_nam() == 2
    assert [legacy.mua(t) for t in (1, 2)] == ["lua", "kho"]


def test_ga_rung_pool_gioi_han_va_hoi_phuc():
    w = _world(23)
    aid = sorted(w.agents)[0]
    # Thu nhỏ K để test chạm trần stock trong thế giới test nhanh.
    w.cfg.raw()["khong_gian"]["ga_rung"]["suc_chua_moi_o"] = 0.01
    k = _ga_rung_suc_chua(w)
    assert k > 0
    w.ga_rung_ton = min(0.5, k)
    w.ben_kia_tick = {aid}  # habitat rừng ở bờ hoang, agent đã trả đò thành công
    w.ledger.sinh(aid, "cong", 180.0, "sinh_cong", "fixture", w.tick)

    before = float(w.ga_rung_ton)
    chan_nuoi.bat_ga(w, aid, 10_000.0)
    assert 0.0 <= float(w.ga_rung_ton) <= before
    assert w.ledger.so_du(aid, "ga_con") <= before + 1e-9

    w.ga_rung_ton = min(k * 0.2, k - 1e-6)
    depleted = float(w.ga_rung_ton)
    chan_nuoi.tai_sinh_ga_rung(w)
    assert depleted < float(w.ga_rung_ton) <= k


def test_cham_tre_chuyen_cong_thuc_su_va_credit_hop_dong():
    w = _world(29)
    parent, child, carer = sorted(w.agents)[:3]
    w.agents[child].tuoi_tick = 4  # 2 tuổi, cần được chăm
    w.agents[child].cha = parent
    w.agents[parent].con = [child]
    w.ledger.sinh(parent, "cong", 100.0, "sinh_cong", "fixture", w.tick)

    # Không có người ngoài: phụ huynh tự chăm, công giảm đúng config.
    care.buoc_cham_tre(w, {parent: KeHoach(id=parent)})
    cong_can = float(w.cfg.get("khong_gian.cham_tre.cong_cham_moi_tre"))
    assert w.ledger.so_du(parent, "cong") == pytest.approx(100.0 - cong_can)

    # Worker có giao kèo gop_cong với parent và tự nguyện chăm: công worker bị đốt,
    # phần đó được credit nên executor không giao công lần hai cho parent.
    w.ledger.sinh(carer, "cong", 100.0, "sinh_cong", "fixture", w.tick)
    hd = HopDong(
        id="HDCARE", cac_ben=[carer, parent], hinh_thuc="mieng", thoi_han=2,
        dieu_khoan=[ClauseGopCong(tu=carer, den=parent, so_cong_moi_tick=cong_can)],
        tick_ky=w.tick,
    )
    w.hop_dong[hd.id] = hd
    w.cong_cham_tre_theo_cap = {}
    care.buoc_cham_tre(w, {
        parent: KeHoach(id=parent), carer: KeHoach(id=carer, cham_tre_cho=[child]),
    })
    assert w.cong_cham_tre_theo_cap[(carer, parent)] == pytest.approx(cong_can)
    carer_after_care = w.ledger.so_du(carer, "cong")
    contracts.gop_cong_dau_san_xuat(w)
    assert w.ledger.so_du(carer, "cong") == pytest.approx(carer_after_care)


def test_price_belief_hoc_tu_phien_cho_va_hash_nhan_biet_state_hanh_vi():
    w = _world(31)
    aid = sorted(w.agents)[0]
    prior = w.agents[aid].gia_ky_vong["go"]
    assert gia_ky_vong(w, aid, "go") == pytest.approx(prior)
    h0 = w.world_hash()
    w.ghi_gia("go", 30.0, 1.0)
    cap_nhat_gia_ky_vong(w)
    assert w.agents[aid].gia_ky_vong["go"] > prior
    assert w.world_hash() != h0


def test_hash_phu_state_prompt_va_commons():
    w = _world(37)
    aid = sorted(w.agents)[0]
    h0 = w.world_hash()
    w.agents[aid].nha_thua = next(iter(w.parcels))
    assert w.world_hash() != h0

    h1 = w.world_hash()
    w.policy_cards[aid] = {"du_dinh": "tích lũy để thuê đất"}
    assert w.world_hash() != h1

    h2 = w.world_hash()
    w.agents[aid].di_chuc = {"phan_bo": {aid: 100.0}, "gia_huan": "giữ lời hứa"}
    assert w.world_hash() != h2

    h3 = w.world_hash()
    w.ca_ton = float(w.ca_ton) * 0.9
    assert w.world_hash() != h3


def test_checkpoint_tu_du_overlay_giu_config_va_hash(tmp_path):
    w = _world(41)
    path = w.luu_checkpoint(tmp_path)
    loaded = World.nap_checkpoint(path)
    assert loaded.cfg.digest() == w.cfg.digest()
    assert loaded.world_hash() == w.world_hash()
    assert loaded.ledger.lich_su == []  # journal cũ ở artifact, không lặp trong every snapshot


def test_rulebot_overlay_da_dang_tat_dinh_va_audit_xanh():
    """Smoke integration không-mạng: nhiều mùa, commons + crop cùng chạy vẫn tái lập."""
    from minds.policies import tao_policy

    def run(seed):
        world = _world(seed)
        policy = tao_policy("rulebot")
        for _ in range(12):
            chay_mot_tick(world, policy, len(world.parcels))
        return world

    a, b = run(53), run(53)
    assert a.world_hash() == b.world_hash()
    assert a.ledger.tong_tai_san("ngo") + a.ledger.tong_tai_san("khoai") > 0.0
    assert a.ga_rung_ton is not None and a.ga_rung_ton >= 0.0
