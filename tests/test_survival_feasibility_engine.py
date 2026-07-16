"""ADR 0009 engine-only survival feasibility invariants (S1/S2/S3/S7 slice)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from engine import board, quotes
from engine.action_journal import preflight_plans
from engine.action_journal import reset_tick as reset_action_journal
from engine.config import Config, load_config
from engine.contracts import ClauseChuyenGiaoMotLan, ClauseGopCong, HopDong
from engine.intents import KeHoach
from engine.projects import DuAn
from engine.shelter_floor import ap_dung_delta_san_cho_o_v7
from engine.survival_feasibility import (
    build_survival_feasibility,
    edible_assets,
    project_post_plan_survival,
)
from engine.world import tao_the_gioi
from minds.provenance import record_plan
from minds.provenance import reset_tick as reset_decision_provenance
from minds.safety import de_xuat_san_cho_o_toi_thieu_v7

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "scenarios" / "agrarian_transition_v1"
OVERLAYS = [
    SCENARIO / name
    for name in (
        "spatial_v1.yaml",
        "spatial_livelihood_v2.yaml",
        "spatial_livelihood_v3.yaml",
        "spatial_livelihood_v4.yaml",
        "spatial_livelihood_v5.yaml",
        "spatial_livelihood_v6.yaml",
        "spatial_livelihood_v7.yaml",
    )
]


def _world(seed: int = 311):
    return tao_the_gioi(load_config(overlays=OVERLAYS), seed, events_path=None)


def _apply_v7_shelter_floor(w, plans, allocated_common_fields: set[str]) -> int:
    deltas = de_xuat_san_cho_o_toi_thieu_v7(w, plans, allocated_common_fields)
    return ap_dung_delta_san_cho_o_v7(w, plans, deltas)


def _single_live(w):
    aid = sorted(w.agents)[0]
    for other, agent in w.agents.items():
        if other != aid:
            agent.con_song = False
    return aid


def test_s1_complete_edible_identity_and_owner_decay_are_pure():
    w = _world()
    aid = _single_live(w)
    w.tick = 1
    # Weather is a known engine fact for this test.  The builder must never call
    # the stateful World.thoi_tiet cache/RNG path itself.
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    w.ledger.sinh(aid, "ngo", 7.0, "gat", "fixture crop", w.tick)
    w.ledger.sinh(aid, "thit", 3.0, "giet_thit", "fixture meat", w.tick)
    w.ledger.sinh(aid, "ca", 4.0, "danh_ca", "fixture fish", w.tick)

    before = w.world_hash()
    facts = build_survival_feasibility(w, aid)
    assert w.world_hash() == before
    assert [row.asset for row in edible_assets(w)] == ["thoc", "khoai", "ngo", "thit", "ca"]

    by_asset = {row.asset: row for row in facts.provisionable_in_residence}
    assert by_asset["ngo"].kg_thoc_equivalent == pytest.approx(7.0 * 0.9)
    assert by_asset["thit"].kg_thoc_equivalent == pytest.approx(3.0 * 3.0)
    assert by_asset["ca"].kg_thoc_equivalent == pytest.approx(4.0 * 2.5)
    decay = {row.asset: row for row in facts.decay_before_consumption}
    assert decay["thit"].kg == pytest.approx(3.0 * w.cfg.get("chan_nuoi.thit_hao_moi_tick"))
    assert decay["ca"].kg == pytest.approx(4.0 * w.cfg.get("danh_ca.ca_hao_moi_tick"))
    # Meat/fish are not additionally subjected to the plant-store rate.
    assert decay["thit"].decay_rate == pytest.approx(w.cfg.get("chan_nuoi.thit_hao_moi_tick"))
    assert decay["ca"].decay_rate == pytest.approx(w.cfg.get("danh_ca.ca_hao_moi_tick"))


def test_s2_residence_boundary_excludes_dead_outsider_food():
    w = _world(313)
    aid, outsider = sorted(w.agents)[:2]
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    # Initial persistent residences are separate.  The outsider's large fish
    # balance is neither personal nor legally provisionable to the requester.
    w.ledger.sinh(outsider, "ca", 99.0, "danh_ca", "fixture outsider fish", w.tick)
    facts = build_survival_feasibility(w, aid)
    assert all(row.owner_id == aid for row in facts.owned_by_person)
    assert all(row.owner_id != outsider for row in facts.provisionable_in_residence)


def _two_live_local(w):
    requester, responder = sorted(w.agents)[:2]
    for aid, agent in w.agents.items():
        if aid not in {requester, responder}:
            agent.con_song = False
    for aid in (requester, responder):
        w.agents[aid].tuoi_tick = 40.0
        w.agents[aid].health = 100.0
        w.agents[aid].lang = 0
        w.agents[aid].nha_thua = None
    return requester, responder


def _public_oral_food_for_labor(responder: str) -> HopDong:
    return HopDong(
        cac_ben=[responder, "?"], hinh_thuc="mieng", thoi_han=1,
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(
                tu=responder, den="?", tai_san="thoc", so_luong=25.0, tai="ky_ket"
            ),
            ClauseGopCong(tu="?", den=responder, so_cong_moi_tick=40.0),
        ],
    )


def _post_public_oral_food_offer(w, responder: str) -> str:
    ref = board.dang_de_nghi(w, responder, _public_oral_food_for_labor(responder))
    assert ref is not None
    return ref


def test_s6_live_v7_no_seed_no_payment_card_exposes_local_oral_food_labor_offer():
    """An actual public board offer is visible, conditional, local and non-mutating."""
    w = _world(315)
    requester, responder = _two_live_local(w)
    # No thóc means no rice seed; no wood means no quoted-payment asset in this fixture.
    thoc = w.ledger.so_du(requester, "thoc")
    if thoc:
        w.ledger.huy(requester, "thoc", thoc, "an", "fixture no seed/payment", w.tick)
    wood = w.ledger.so_du(requester, "go")
    if wood:
        w.ledger.huy(requester, "go", wood, "dung", "fixture no payment", w.tick)
    ref = _post_public_oral_food_offer(w, responder)
    # A public offer posted at t=0 is first available for acceptance at decision t=1.
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"

    before = w.world_hash()
    facts = build_survival_feasibility(w, requester)
    assert w.world_hash() == before
    assert w.ledger.so_du(requester, "thoc") == 0.0
    assert w.ledger.so_du(requester, "go") == 0.0
    path = next(row for row in facts.contract_paths if row.target_id == ref)
    assert path.counterparty_id == responder
    assert path.visible and path.reachable
    assert path.feasible is False and path.conditional is True
    assert path.asset == "thoc" and path.quantity == pytest.approx(25.0)
    assert path.gross_food == path.net_food == pytest.approx(25.0)
    assert path.food_at_signing is True
    assert path.earliest_settlement_tick == path.earliest_labor_tick == w.tick
    assert path.labor_per_tick == pytest.approx(40.0) and path.duration_ticks == 1
    assert "unaccepted_contract_offer" in path.reason_codes
    assert facts.guaranteed_settled_inflow == ()
    assert all(row.owner_id != responder for row in facts.provisionable_in_residence)


def test_s6_no_responder_exposes_only_counterparty_free_oral_prerequisites():
    w = _world(316)
    requester, _responder = _two_live_local(w)
    facts = build_survival_feasibility(w, requester)

    assert len(facts.contract_paths) == 1
    path = facts.contract_paths[0]
    assert path.target_id == "public_board"
    assert path.counterparty_id is None
    assert path.reachable is False and path.feasible is False and path.conditional is True
    assert path.gross_food == path.net_food == 0.0
    assert set(path.reason_codes) == {"counterparty_required", "response_not_same_tick"}
    assert facts.guaranteed_settled_inflow == ()


def test_s6_unreachable_oral_offer_is_shown_as_unreachable_not_food():
    w = _world(318)
    requester, responder = _two_live_local(w)
    ref = _post_public_oral_food_offer(w, responder)
    # Public information may be visible across villages, but the tangible legs may not teleport.
    w.agents[responder].lang = 1
    w.tick = 1
    facts = build_survival_feasibility(w, requester)

    path = next(row for row in facts.contract_paths if row.target_id == ref)
    assert path.visible and path.reachable is False and path.feasible is False
    assert "delivery_unreachable" in path.reason_codes
    assert facts.guaranteed_settled_inflow == ()


def test_s6_insolvent_offer_does_not_leak_balance_or_become_guaranteed_food():
    w = _world(319)
    requester, responder = _two_live_local(w)
    amount = w.ledger.so_du(responder, "thoc")
    if amount:
        w.ledger.huy(responder, "thoc", amount, "an", "fixture insolvent offer", w.tick)
    ref = _post_public_oral_food_offer(w, responder)
    w.tick = 1
    facts = build_survival_feasibility(w, requester)

    path = next(row for row in facts.contract_paths if row.target_id == ref)
    assert path.reachable and path.feasible is False and path.conditional is True
    assert "unaccepted_contract_offer" in path.reason_codes
    assert all("insufficient" not in code for code in path.reason_codes)
    assert "solv" not in str(path.model_dump()).lower()
    assert facts.guaranteed_settled_inflow == ()


def test_s6_visible_food_quote_reports_own_payment_requirement_without_phantom_food():
    w = _world(320)
    requester, responder = _two_live_local(w)
    quotes.buoc_bao_gia(w, {
        responder: KeHoach(id=responder, dang_bao_gia=[{
            "chieu": "ban", "tai_san": "thoc", "so_luong": 25.0, "don_gia": 2.0,
            "thanh_toan": "go", "doi_tac": requester, "giao_tai": "ngay",
        }]),
    })
    facts = build_survival_feasibility(w, requester)

    path = next(row for row in facts.quote_paths if row.target_id == "BG00001")
    assert path.counterparty_id == responder
    assert path.visible and path.reachable and path.conditional and path.feasible is False
    assert path.asset == "thoc" and path.gross_food == pytest.approx(25.0)
    assert path.payment_asset == "go" and path.payment_amount == pytest.approx(50.0)
    assert path.payment_owned is False and "insufficient_payment" in path.reason_codes
    assert "unaccepted_quote" in path.reason_codes
    assert facts.guaranteed_settled_inflow == ()


def test_post_plan_projection_is_pure_and_only_allocated_common_rice_is_guaranteed():
    w = _world(317)
    aid = _single_live(w)
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    field = next(parcel.id for parcel in w.parcels.values()
                 if parcel.loai == "ruong" and parcel.chu is None)
    residence_id = build_survival_feasibility(w, aid).residence_id
    plans = {aid: KeHoach(id=aid, canh_thua=[field])}
    before = w.world_hash()
    blocked = project_post_plan_survival(w, residence_id, plans, set())
    allocated = project_post_plan_survival(w, residence_id, plans, {field})
    assert w.world_hash() == before
    assert blocked.guaranteed_feasible_output == ()
    assert any("contested_common_land" in row.reason_codes for row in blocked.production_paths)
    assert allocated.guaranteed_feasible_output
    assert allocated.seed_use[0].asset == "thoc"
    assert allocated.gap.kg_thoc_equivalent <= blocked.gap.kg_thoc_equivalent


def test_v7_config_rejects_invalid_threshold_before_world_exists():
    raw = copy.deepcopy(load_config(overlays=OVERLAYS).raw())
    raw["minds"]["san_cho_o_toi_thieu"]["nguong_health_khoi_cong"] = 100
    with pytest.raises(SystemExit, match="nguong_health_khoi_cong"):
        tao_the_gioi(Config(raw), 331, events_path=None)


def test_s7_minds_shelter_proposal_is_pure_and_engine_phase_journals_it():
    """The v7 minds proposal cannot create an observational engine side effect."""
    w = _world(333)
    aid = _single_live(w)
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    w.agents[aid].health = 10.0
    w.ledger.sinh(aid, "thoc", 180.0, "khoi_tao", "fixture food", w.tick)
    plans = {aid: KeHoach(id=aid)}
    reset_decision_provenance(w)
    reset_action_journal(w)
    record_plan(w, aid, "llm")
    before_state = copy.deepcopy(w.behavioral_state())
    before_plans = copy.deepcopy(plans)
    before_journal = copy.deepcopy(w.action_journal_tick)
    before_provenance = copy.deepcopy(w.decision_provenance_tick)

    deltas = de_xuat_san_cho_o_toi_thieu_v7(w, plans, set())

    assert len(deltas) == 1 and deltas[0].action == "chon_dat_o"
    assert plans == before_plans
    assert w.behavioral_state() == before_state
    assert w.action_journal_tick == before_journal
    assert w.decision_provenance_tick == before_provenance

    assert ap_dung_delta_san_cho_o_v7(w, plans, deltas) == 1
    row = w.action_journal_tick[-1]
    assert row["action"] == "chon_dat_o"
    assert row["origin"] == "survival_floor"
    assert row["preflight"] == "ok"
    assert row["execution"] == "planned"
    assert plans[aid].chon_dat_o == list(deltas[0].value)
    assert w.decision_provenance_tick["actions"][-1]["origin"] == "survival_floor"


def test_s7_v7_shelter_is_food_first_and_never_exceeds_residual_labor():
    w = _world(337)
    aid = _single_live(w)
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    w.agents[aid].health = 10.0
    # Current-tick deficit forbids even a floor residential-lot request.
    all_grain = w.ledger.so_du(aid, "thoc")
    w.ledger.huy(aid, "thoc", all_grain, "an", "fixture deficit", w.tick)
    deficit_plan = {aid: KeHoach(id=aid)}
    assert _apply_v7_shelter_floor(w, deficit_plan, set()) == 0
    assert deficit_plan[aid].chon_dat_o == []

    # A food-secure, exposed resident receives a newly journalled/preflighted
    # floor lot request only after the food gate has passed.
    w.ledger.sinh(aid, "thoc", 180.0, "khoi_tao", "fixture food", w.tick)
    lot_plan = {aid: KeHoach(id=aid)}
    assert _apply_v7_shelter_floor(w, lot_plan, set()) == 1
    rows = [row for row in w.action_journal_tick if row["origin"] == "survival_floor"]
    assert rows[-1]["action"] == "chon_dat_o" and rows[-1]["preflight"] == "ok"

    # Create an open home project and consume all available labour with a
    # voluntary request.  The v7 floor may not add logging or project labour
    # because residual_conservative is exactly zero.
    site = next(parcel.id for parcel in w.parcels.values() if parcel.loai == "dat_o")
    w.quyen_dat_o[site] = aid
    w.agents[aid].nha_thua = site
    w.du_an["DAFIX"] = DuAn(
        id="DAFIX", chu=aid, loai="nha", tai_san_ra="nha", so_luong_ra=1.0,
        luong_vat_lieu="xay", luong_san_pham="xay", thua=site, bo=None, lang=0,
        cong_can=240.0, cong_da=0.0, vat_lieu_can={"go": 6.0}, vat_lieu_da={},
        tick_tao=0, han_tick=20,
    )
    plan = KeHoach(id=aid, cong_khai_go=float(w.cfg.get("nhu_cau.ngay_cong_moi_tick")))
    plans = {aid: plan}
    assert _apply_v7_shelter_floor(w, plans, set()) == 0
    assert plans[aid].cong_khai_go == pytest.approx(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
    assert plans[aid].gop_cong_du_an == []


def test_s7_voluntary_scalar_logging_is_never_relabelled_as_floor():
    """A scalar logging field cannot carry mixed voluntary/floor provenance."""
    w = _world(347)
    aid = _single_live(w)
    w.tick = 1
    w.thoi_tiet_nam[w.nam(w.tick)] = "binh_thuong"
    w.agents[aid].health = 10.0
    w.ledger.sinh(aid, "thoc", 180.0, "khoi_tao", "fixture food", w.tick)
    site = next(parcel.id for parcel in w.parcels.values() if parcel.loai == "dat_o")
    w.quyen_dat_o[site] = aid
    w.agents[aid].nha_thua = site
    w.du_an["DA_VOLUNTARY"] = DuAn(
        id="DA_VOLUNTARY", chu=aid, loai="nha", tai_san_ra="nha", so_luong_ra=1.0,
        luong_vat_lieu="xay", luong_san_pham="xay", thua=site, bo=None, lang=0,
        cong_can=240.0, cong_da=0.0, vat_lieu_can={"go": 6.0}, vat_lieu_da={},
        tick_tao=0, han_tick=20,
    )
    # Capacity at this health is 12; this voluntary 8 leaves a floor cap of 4.
    # The voluntary scalar therefore exceeds the calculated floor delta.
    plan = KeHoach(id=aid, cong_khai_go=8.0)
    plans = {aid: plan}
    reset_decision_provenance(w)
    reset_action_journal(w)
    record_plan(w, aid, "llm")
    preflight_plans(w, plans)

    projection = project_post_plan_survival(
        w, build_survival_feasibility(w, aid).residence_id, plans, set()
    )
    assert projection.labor[0].residual_conservative == pytest.approx(4.0)
    assert _apply_v7_shelter_floor(w, plans, set()) == 0

    # Fail closed: no scalar mutation, no floor count/provenance, and the
    # original voluntary request retains its LLM origin.
    assert plan.cong_khai_go == pytest.approx(8.0)
    logging_rows = [
        row for row in w.action_journal_tick if row["action"] == "phan_bo_cong"
    ]
    assert len(logging_rows) == 1
    assert logging_rows[0]["origin"] == "llm"
    assert logging_rows[0]["params"]["khai_go_cong"] == pytest.approx(8.0)
    assert not any(row["origin"] == "survival_floor" for row in logging_rows)
