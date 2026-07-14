"""C1 regressions: active-config policy cards and honest decision provenance."""

from __future__ import annotations

import copy
from pathlib import Path

from engine.config import Config, load_config
from engine.intents import KeHoach
from engine.world import tao_the_gioi
from minds.policy_cards import thi_hanh_the
from minds.prompts import schema_quyet_dinh_cho
from minds.provenance import summary
from minds.rulebot import _BoiCanhTick
from minds.safety import ap_dung_san_an_toi_thieu
from minds.schemas import TheChinhSach
from tests.helpers import chay_tick, the_gioi_test

SPATIAL = Path("scenarios/agrarian_transition_v1/spatial_v1.yaml").resolve()


def _spatial_world(*, labor: float) -> tuple[object, str]:
    raw = copy.deepcopy(load_config(overlays=[SPATIAL]).raw())
    raw["nhu_cau"]["ngay_cong_moi_tick"] = labor
    w = tao_the_gioi(Config(raw), 71, events_path=None)
    aid = next(aid for aid in sorted(w.agents) if w.agents[aid].truong_thanh(
        w.cfg.get("nhan_khau.tuoi_truong_thanh")
    ))
    for other, agent in w.agents.items():
        if other != aid:
            agent.con_song = False
    w.agents[aid].vo_chong = None
    w.agents[aid].con = []
    w.agents[aid].health = 100.0
    return w, aid


def _set_grain(w, aid: str, amount: float) -> None:
    current = w.ledger.so_du(aid, "thoc")
    if amount > current:
        w.ledger.sinh(aid, "thoc", amount - current, "khoi_tao", "fixture", 0)
    elif current > amount:
        w.ledger.huy(aid, "thoc", current - amount, "an", "fixture", 0)


def test_policy_card_uses_spatial_120_labor_not_legacy_180():
    """A 4-month spatial policy can fund only 120/50 = 2 parcels, not 3."""
    w, aid = _spatial_world(labor=120)
    w.cfg.raw()["san_xuat"].update({
        "cong_moi_thua": 50,
        "giong_kg_moi_thua": 1,
        "san_luong_goc_kg": 300,
        "thua_toi_da_tu_canh": 10,
    })
    _set_grain(w, aid, 1_000)
    w.tick = 1  # lua_1

    plan = thi_hanh_the(
        w, aid, TheChinhSach(du_tru_muc_tieu=20, canh_toi_da=10),
        _BoiCanhTick(w), set(),
    )

    assert len(plan.canh_thua) == 2


def test_policy_card_uses_active_labor_for_dry_livelihoods():
    """The full-tick wood/fishing allocation follows the running scenario."""
    w, aid = _spatial_world(labor=77)
    _set_grain(w, aid, 100)
    w.tick = 3  # dong

    plan = thi_hanh_the(w, aid, TheChinhSach(), _BoiCanhTick(w), set())

    assert plan.cong_khai_go == 77
    assert plan.danh_ca_cong == 77


def test_policy_patch_prompt_is_delta_not_a_copied_default():
    w, _aid = _spatial_world(labor=120)
    schema = schema_quyet_dinh_cho(w)

    assert "PATCH tùy chọn" in schema
    assert '"du_tru_muc_tieu":2.5,"canh_toi_da":3' not in schema
    assert "an_toan_sinh_ton" in schema


def test_metrics_keep_external_and_survival_floor_origins_separate():
    w = the_gioi_test(seed=29, giu_lai=1, thoc_moi_nguoi=200.0)
    aid = next(aid for aid, agent in sorted(w.agents.items()) if agent.con_song)

    # The floor appends an action to a plan supplied by an outside test mind.
    w.tick = 1
    plans = {aid: KeHoach(id=aid)}
    assert ap_dung_san_an_toi_thieu(w, plans, _BoiCanhTick(w), set()) == 1
    before = summary(w)
    assert before["actions"]["survival_floor"] == 1

    # A normal full tick reports a custom mind as external, never as LLM.
    w = the_gioi_test(seed=31, giu_lai=1, thoc_moi_nguoi=2_000.0)
    aid = next(aid for aid, agent in sorted(w.agents.items()) if agent.con_song)
    chay_tick(w, lambda world: {aid: KeHoach(id=aid)}, 1)
    provenance = w.metrics_lich_su[-1]["decision_provenance"]
    assert provenance["plans"]["external"] == 1
    assert provenance["plans"]["llm"] == 0
    assert set(("policy_card", "survival_floor", "fallback", "translator")) <= set(
        provenance["plans"]
    )
