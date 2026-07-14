"""C2: feasible targets and explicit action results, entirely offline."""

from __future__ import annotations

import copy
from pathlib import Path

from engine.config import Config, load_config
from engine.intents import KeHoach
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.prompts import build_agent_prompt
from minds.world_tools import thuc_thi

SPATIAL = Path("scenarios/agrarian_transition_v1/spatial_v1.yaml").resolve()
LIVELIHOOD = Path("scenarios/agrarian_transition_v1/spatial_livelihood_v2.yaml").resolve()


def _world():
    raw = copy.deepcopy(load_config(overlays=[SPATIAL, LIVELIHOOD]).raw())
    raw.setdefault("minds", {})["action_journal"] = {"bat": True, "enforce": True}
    w = tao_the_gioi(Config(raw), 103, events_path=None)
    aid = next(aid for aid in sorted(w.agents) if w.agents[aid].truong_thanh(
        w.cfg.get("nhan_khau.tuoi_truong_thanh")
    ))
    w.agents[aid].health = 100.0
    return w, aid


def _run_one(w, aid: str, plan: KeHoach) -> None:
    chay_mot_tick(w, lambda _world: {aid: plan}, len(w.parcels))


def test_common_field_is_rejected_for_clearing_with_a_stable_code():
    w, aid = _world()
    field = next(p.id for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    plan = KeHoach(id=aid, khai_hoang=[field])

    _run_one(w, aid, plan)

    assert plan.khai_hoang == []  # v3-style enforcement prevents a silent engine skip
    journal = w.metrics_lich_su[-1]["action_journal"]
    assert journal["execution"]["rejected"] == 1
    assert journal["reason_codes"]["parcel_not_clearable"] == 1
    row = w.action_journal_tick[0]
    assert row["intent_id"].startswith("I") and row["target"] == field
    assert row["preflight"] == "rejected"
    assert "parcel_not_clearable" in w.agents[aid].su_co[-1]


def test_stale_project_reference_is_visible_not_silently_ignored():
    w, aid = _world()
    plan = KeHoach(id=aid, gop_cong_du_an=[{"ref": "DA99999", "so_cong": 12.0}])

    _run_one(w, aid, plan)

    assert plan.gop_cong_du_an == []
    journal = w.metrics_lich_su[-1]["action_journal"]
    assert journal["reason_codes"]["project_not_found"] == 1


def test_runtime_quote_failure_is_journaled_as_a_rejection():
    """Preflight cannot know stock locked earlier in the same tick; execution must still speak."""
    w, aid = _world()
    plan = KeHoach(id=aid, dang_bao_gia=[{
        "chieu": "ban", "tai_san": "go", "so_luong": 1_000_000.0,
        "don_gia": 4.0, "thanh_toan": "thoc", "doi_tac": None, "giao_tai": "ngay",
    }])

    _run_one(w, aid, plan)

    row = next(item for item in w.action_journal_tick if item["action"] == "dang_bao_gia")
    assert row["preflight"] == "ok"
    assert row["execution"] == "rejected"
    assert row["reason_code"] == "insufficient_inventory"
    assert "insufficient_inventory" in w.agents[aid].su_co[-1]
    cumulative = w.metrics_lich_su[-1]["action_journal"]["cumulative"]
    assert cumulative["execution"]["rejected"] == 1
    assert cumulative["reason_codes"]["insufficient_inventory"] == 1


def test_reforestation_requires_a_hill_not_an_existing_forest():
    w, aid = _world()
    # Make a locally reachable factual counterexample; it remains a forest, so
    # planting it again is not a permissible reforestation target.
    from engine.spatial import _bo_cua

    current_bank = _bo_cua(w, aid)
    parcel = next(p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    parcel.loai = "rung"
    parcel.bo = current_bank
    plan = KeHoach(id=aid, trong_rung=[parcel.id])

    _run_one(w, aid, plan)

    assert plan.trong_rung == []
    row = next(item for item in w.action_journal_tick if item["action"] == "trong_rung")
    assert row["preflight"] == "rejected"
    assert row["reason_code"] == "parcel_not_reforestable"


def test_fact_cards_separate_cultivable_common_fields_from_clearable_land():
    w, aid = _world()
    # The tool/prompt must see both banks only after a valid crossing state.
    w.ben_kia_tick = {aid}
    prompt = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    opportunities = thuc_thi(w, aid, "xem_co_hoi_san_xuat", {})["co_hoi"]

    assert "RUỘNG CÔNG CÓ THỂ CANH" in prompt
    assert "KHÔNG phải mục tiêu khai_hoang" in prompt
    clearing = next(card for card in opportunities if card["hoat_dong"] == "khai_hoang")
    assert clearing["loai_thua_hop_le"] == ["rung", "doi"]
    assert all(w.parcels[pid].loai in {"rung", "doi"} for pid in clearing["thua_co_the_dung"])
    common = thuc_thi(w, aid, "dat_cong_gan", {})["thua"]
    assert common and all(w.parcels[row["id"]].loai == "ruong" for row in common)
