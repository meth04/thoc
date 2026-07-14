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
