"""V5 settlement entry and simultaneous common-land allocation regressions.

All paths are deterministic/local; no provider or LLM request is made here.
"""

from __future__ import annotations

from pathlib import Path

from engine import common_land, production, projects, settlement
from engine.config import load_config
from engine.intents import KeHoach
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.orchestrator import MindMock
from minds.prompts import build_agent_prompt
from minds.safety import ap_dung_san_an_sau_phan_bo_ruong_cong, ap_dung_san_cho_o_toi_thieu

ROOT = Path(__file__).resolve().parents[1]
OVERLAYS = [
    ROOT / "scenarios" / "agrarian_transition_v1" / name
    for name in (
        "spatial_v1.yaml",
        "spatial_livelihood_v2.yaml",
        "spatial_livelihood_v3.yaml",
        "spatial_livelihood_v4.yaml",
        "spatial_livelihood_v5.yaml",
    )
]


def _world(seed: int = 17):
    return tao_the_gioi(load_config(overlays=OVERLAYS), seed)


def _three_living(w):
    ids = sorted(w.agents)[:3]
    for aid, agent in w.agents.items():
        if aid not in ids:
            agent.con_song = False
            stock = w.ledger.so_du(aid, "thoc")
            if stock:
                w.ledger.huy(aid, "thoc", stock, "an", "fixture removal", 0)
    return ids


def test_lot_claim_is_ranked_fair_and_creates_no_resource():
    w = _world(23)
    ids = _three_living(w)
    lots = sorted(p.id for p in w.parcels.values() if p.loai == "dat_o")
    assert len(lots) >= 2 * len(w.agents)
    before = {aid: dict(w.ledger.tai_san_cua(aid)) for aid in ids}
    w.tick = 1
    plans = {
        aid: KeHoach(id=aid, chon_dat_o=lots[:3])
        for aid in ids
    }

    assert settlement.giai_quyet_chon_dat_o(w, plans) == 3
    assigned = {aid: settlement.lo_cua(w, aid) for aid in ids}
    assert len(set(assigned.values())) == 3
    assert all(site in lots[:3] for site in assigned.values())
    assert {aid: dict(w.ledger.tai_san_cua(aid)) for aid in ids} == before
    assert all(w.parcels[site].chu is None for site in assigned.values())


def test_completed_home_lot_is_not_reissued_after_builder_dies():
    w = _world(29)
    deceased, claimant, _other = _three_living(w)
    site = next(p.id for p in w.parcels.values() if p.loai == "dat_o")
    w.quyen_dat_o[site] = deceased
    w.agents[deceased].nha_thua = site
    w.agents[deceased].con_song = False
    w.tick = 1

    assert settlement.giai_quyet_chon_dat_o(
        w, {claimant: KeHoach(id=claimant, chon_dat_o=[site])}
    ) == 0
    assert w.quyen_dat_o[site] == deceased


def test_common_field_collision_is_not_lexical_id_priority_and_floor_has_feasible_bridge():
    winners = set()
    for seed in range(11, 23):
        w = _world(seed)
        ids = _three_living(w)
        for aid in ids:
            stock = w.ledger.so_du(aid, "thoc")
            if stock > 100.0:
                w.ledger.huy(aid, "thoc", stock - 100.0, "an", "fixture low reserve", 0)
        field = next(p.id for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
        w.tick = 1
        plans = {aid: KeHoach(id=aid, canh_thua=[field]) for aid in ids}
        allocated = common_land.phan_bo_ruong_cong(w, plans)
        assert allocated == {field}
        winner = next(aid for aid in ids if plans[aid].canh_thua == [field])
        winners.add(winner)
        # The two losing households have enough seed/labour but no remaining field.  The
        # post-lottery floor supplies one unused public field without creating any resource.
        before = {aid: w.ledger.so_du(aid, "thoc") for aid in ids}
        ap_dung_san_an_sau_phan_bo_ruong_cong(w, plans, allocated)
        assert all(plans[aid].canh_thua for aid in ids)
        assert {aid: w.ledger.so_du(aid, "thoc") for aid in ids} == before
    assert len(winners) > 1, "winner must vary by seed, not stay at smallest agent id"


def test_post_lottery_food_floor_never_selects_another_residents_homestead():
    w = _world(27)
    claimant, owner, _other = _three_living(w)
    stock = w.ledger.so_du(claimant, "thoc")
    if stock > 100.0:
        w.ledger.huy(claimant, "thoc", stock - 100.0, "an", "fixture low reserve", 0)
    reserved = next(p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    reserved.homestead_ai = owner
    reserved.homestead_dem = 1
    w.tick = 1
    plans = {claimant: KeHoach(id=claimant)}
    # All genuinely public fields are already reserved by an earlier allocation; the only
    # otherwise visible field is another resident's provisional homestead.
    allocated = {
        p.id for p in w.parcels.values()
        if p.loai == "ruong" and p.chu is None and p.id != reserved.id
    }
    assert ap_dung_san_an_sau_phan_bo_ruong_cong(w, plans, allocated) == 0
    assert not plans[claimant].canh_thua


def test_provisional_homestead_cannot_be_reset_by_another_common_field_request():
    w = _world(31)
    intruder, owner, _other = _three_living(w)
    field = next(p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    field.homestead_ai = owner
    field.homestead_dem = 1
    w.tick = 1
    production.sinh_cong(w)
    production.thi_hanh_san_xuat(w, {
        # The intruder has the lower lexical id and is applied first.  The owner
        # nevertheless keeps the field and its continuous-cultivation progress.
        intruder: KeHoach(id=intruder, canh_thua=[field.id]),
        owner: KeHoach(id=owner, canh_thua=[field.id]),
    })
    assert field.homestead_ai == owner and field.homestead_dem == 2
    assert w.gat_tick[field.id][0] == owner


def test_shelter_floor_opens_legal_lot_then_house_project_without_gifting_inputs():
    w = _world(41)
    ids = _three_living(w)
    aid = ids[0]
    for other in ids[1:]:
        w.agents[other].con_song = False
    w.tick = 1
    plans = {aid: KeHoach(id=aid)}
    # At the first decision the floor can request a legal entry lot but cannot invent a site.
    assert ap_dung_san_cho_o_toi_thieu(w, plans) == 1
    assert plans[aid].chon_dat_o
    thoc_before = w.ledger.so_du(aid, "thoc")
    assert settlement.giai_quyet_chon_dat_o(w, plans) == 1
    site = settlement.lo_cua(w, aid)
    assert site and w.parcels[site].chu is None
    assert w.ledger.so_du(aid, "thoc") == thoc_before

    w.tick = 2
    plans = {aid: KeHoach(id=aid)}
    assert ap_dung_san_cho_o_toi_thieu(w, plans) == 1
    assert plans[aid].tao_du_an == [{"loai_du_an": "nha", "thua": site}]
    projects.dang_ky_du_an(w, plans)
    project = next(project for project in w.du_an.values() if project.chu == aid)
    assert project.thua == site and project.trang_thai == "dang_lam"
    assert w.ledger.so_du(aid, "go") == 0.0
    assert w.ledger.so_du(aid, "nha") == 0.0


def test_v5_prompt_exposes_survival_feasibility_and_agentic_information_paths():
    w = _world(47)
    aid = _three_living(w)[0]
    prompt = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    assert "[KHẢ NĂNG THỰC THI SỐNG CÒN]" in prompt
    assert "Công cụ chỉ-đọc" in prompt
    assert "nhan_tin" in prompt
    assert "quyền đất hay nhà" in prompt


def test_v5_mock_autonomy_reaches_houses_without_network_calls():
    """A short full-cohort mock smoke catches the old no-site/no-house death spiral."""
    w = _world(59)
    mind = MindMock(w, fast=True, run_dir=None, p_malformed=0.0)
    initial_parcels = len(w.parcels)
    for _ in range(12):
        chay_mot_tick(w, mind, initial_parcels)
    living = [aid for aid, agent in w.agents.items() if agent.con_song]
    adults = [aid for aid in living if w.agents[aid].truong_thanh(
        int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    )]
    homes = [aid for aid in living if w.ledger.so_du(aid, "nha") >= 1.0]
    assert living, "entry mechanism must not reproduce early population extinction"
    assert homes, "at least one legal house project must complete in the mock smoke"
    assert all(settlement.lo_cua(w, aid) or w.ledger.so_du(aid, "nha") >= 1.0 for aid in adults)
