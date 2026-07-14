"""V3 economics: explicit trade-offs, durable shelter, honest mortality labels."""

from __future__ import annotations

from pathlib import Path

from engine import consumption, demography, metrics_demography
from engine.config import load_config
from engine.world import tao_the_gioi


ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
V2 = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"
V3 = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v3.yaml"


def _world(seed: int = 401):
    w = tao_the_gioi(load_config(overlays=[SPATIAL, V2, V3]), seed, events_path=None)
    aid = next(aid for aid in sorted(w.agents) if w.agents[aid].truong_thanh(
        w.cfg.get("nhan_khau.tuoi_truong_thanh")
    ))
    for other, agent in w.agents.items():
        if other != aid:
            agent.con_song = False
    w.agents[aid].vo_chong = None
    w.agents[aid].con = []
    w.agents[aid].health = 80.0
    return w, aid


def _set_grain(w, aid: str, amount: float) -> None:
    current = w.ledger.so_du(aid, "thoc")
    if amount > current:
        w.ledger.sinh(aid, "thoc", amount - current, "khoi_tao", "fixture", 0)
    elif current > amount:
        w.ledger.huy(aid, "thoc", current - amount, "an", "fixture", 0)


def test_v3_winter_crop_config_has_land_labor_tradeoff_not_strict_dominance():
    cfg = load_config(overlays=[SPATIAL, V2, V3])
    maize = cfg.get("khong_gian.vu_dong.cay.ngo")
    potato = cfg.get("khong_gian.vu_dong.cay.khoai")
    maize_food = float(maize["san_luong_kg"]) * float(maize["quy_doi_dinh_duong"])
    potato_food = float(potato["san_luong_kg"]) * float(potato["quy_doi_dinh_duong"])

    assert maize_food > potato_food  # scarce land favors maize's larger total output
    assert float(maize["cong"]) > float(potato["cong"])
    assert maize_food / float(maize["cong"]) < potato_food / float(potato["cong"])


def test_v3_homeless_full_meal_does_not_erase_shelter_exposure():
    homeless, aid = _world(409)
    housed, aid_housed = _world(409)
    _set_grain(homeless, aid, 1_000)
    _set_grain(housed, aid_housed, 1_000)
    housed.ledger.sinh(aid_housed, "nha", 1.0, "xay", "fixture", 0)
    homeless.tick = housed.tick = 1  # lua_1 / rain season

    consumption.an_va_suc_khoe(homeless)
    consumption.an_va_suc_khoe(housed)
    assert homeless.agents[aid].vo_gia_cu
    assert homeless.agents[aid].health < housed.agents[aid_housed].health

    homeless.tick = housed.tick = 3  # dry season still has exposure + slower recovery
    consumption.an_va_suc_khoe(homeless)
    consumption.an_va_suc_khoe(housed)
    assert homeless.agents[aid].health < housed.agents[aid_housed].health


def test_v3_young_baseline_death_is_not_mislabeled_old_age(monkeypatch):
    w, aid = _world(419)
    w.tick = 1
    w.agents[aid].tuoi_tick = 60.0  # 30 years in the 3-tick calendar
    metrics_demography.bat_dau_tick(w)
    monkeypatch.setattr(demography, "_q_nam", lambda *_args: 1.0)

    assert demography.cai_chet(w) == [aid]
    assert w.nhan_khau_tick["deaths"] == [{"tuoi": 30.0, "ly_do": "tu_vong_co_ban"}]
