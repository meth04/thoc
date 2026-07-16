"""Homestead information binding for prompts and local read-only tools.

These tests exercise the existing ``phan_bo_cong.canh_thua`` path.  They deliberately do not
add a second action that could bypass common-land allocation or engine title law.
"""

from __future__ import annotations

import re
from pathlib import Path

from engine import production
from engine.config import load_config
from engine.intents import KeHoach
from engine.spatial import co_the_o_bo
from engine.world import tao_the_gioi
from minds.capabilities import ap_dung_hanh_dong, cac_ten_cong_khai
from minds.prompts import _fact_cards_cuc_bo, build_agent_prompt
from minds.world_tools import homestead_fact, thuc_thi

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


def _world_with_homestead(seed: int = 71):
    w = tao_the_gioi(load_config(overlays=OVERLAYS), seed, events_path=None)
    aid = sorted(w.agents)[0]
    field = next(
        parcel for parcel in sorted(w.parcels.values(), key=lambda row: row.id)
        if parcel.loai == "ruong" and parcel.chu is None
        and co_the_o_bo(w, aid, parcel.bo)
    )
    field.homestead_ai = aid
    field.homestead_dem = 2
    w.tick = 3  # winter in spatial_v1; the next required rice season is lua_1
    return w, aid, field


def test_existing_phan_bo_cong_targets_exact_homestead_parcel_without_new_action():
    w, aid, field = _world_with_homestead()
    plan = KeHoach(id=aid)

    ap_dung_hanh_dong(
        w,
        plan,
        {"loai": "phan_bo_cong", "canh_thua": [field.id]},
    )

    assert plan.canh_thua == [field.id]
    assert "tiep_tuc_homestead" not in cac_ten_cong_khai()


def test_homestead_fact_is_correct_private_and_pinned_in_prompt_and_tools():
    w, aid, field = _world_with_homestead()
    other = sorted(row for row in w.agents if row != aid)[0]
    fact = homestead_fact(w, aid, field)
    assert fact is not None
    assert fact == {
        "thua": field.id,
        "tien_do_mua_lua": 2,
        "nguong_title_mua_lua": int(w.cfg.get("san_xuat.homestead_tick_lien_tiep")),
        "do_mau_hien_tai": round(field.mau_mo, 6),
        "san_luong_co_so_theo_do_mau_kg": round(
            float(w.cfg.get("san_xuat.san_luong_goc_kg")) * field.mau_mo, 6
        ),
        "mua_lua_can_tiep_tuc": "lua_1",
        "co_the_tiep_can_hien_tai": True,
        "quyen_hien_tai": "dat_cong_bao_luu_homestead",
        "action_hien_co": "phan_bo_cong.canh_thua",
        "reset_neu_bo_qua_mua_lua": True,
    }

    prompt = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    assert f"FACT CARD — HOMESTEAD BẠN ĐANG TÍCH LŨY: {field.id}" in prompt
    assert "tiến độ 2/4 mùa lúa liên tiếp" in prompt
    assert "mùa lúa cần tiếp tục: lua_1" in prompt
    board = next(
        line for line in prompt.splitlines()
        if line.startswith("FACT CARD — RUỘNG CÔNG CÓ THỂ CANH:")
    )
    assert board.split(": ", 1)[1].startswith(f"{field.id}(")

    other_prompt = build_agent_prompt(w, other, {other: ["dinh_ky"]})
    assert f"HOMESTEAD BẠN ĐANG TÍCH LŨY: {field.id}" not in other_prompt

    opportunities = thuc_thi(w, aid, "xem_co_hoi_san_xuat", {})["co_hoi"]
    assert opportunities[0] == {"hoat_dong": "homestead_dang_tich_luy", **fact}
    crop = next(card for card in opportunities if card["hoat_dong"].startswith("canh_"))
    assert crop["thua_co_the_dung"][0] == field.id
    nearby = thuc_thi(w, aid, "dat_cong_gan", {"toi_da": 6})["thua"]
    assert nearby[0]["id"] == field.id
    assert nearby[0]["homestead_cua_toi"] == fact


def test_only_unheld_common_fields_rotate_behind_pinned_homestead():
    w, aid, field = _world_with_homestead()
    unheld = sorted(
        (
            parcel for parcel in w.parcels.values()
            if parcel.loai == "ruong" and parcel.chu is None
            and parcel.homestead_ai is None and co_the_o_bo(w, aid, parcel.bo)
        ),
        key=lambda row: row.id,
    )
    offset = int(
        w.rng.get(f"ruong_cong_board:{aid}", w.tick).integers(0, len(unheld))
    )
    rotated = unheld[offset:] + unheld[:offset]
    expected = [field.id, *(parcel.id for parcel in rotated[:5])]

    cards = _fact_cards_cuc_bo(w, aid)
    board = next(row for row in cards if row.startswith("FACT CARD — RUỘNG CÔNG"))
    shown = re.findall(r"P\d+_\d+", board.split(". Dùng", 1)[0])

    assert shown == expected


def test_prompt_and_tools_are_replay_stable_and_do_not_mutate_world_hash():
    w, aid, _field = _world_with_homestead()
    # Warm the deterministic weather cache that the full common prompt already owns.
    w.thoi_tiet(w.tick)
    before = w.world_hash()

    prompt_1 = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    tools_1 = {
        "opportunities": thuc_thi(w, aid, "xem_co_hoi_san_xuat", {}),
        "fields": thuc_thi(w, aid, "dat_cong_gan", {"toi_da": 6}),
    }
    prompt_2 = build_agent_prompt(w, aid, {aid: ["dinh_ky"]})
    tools_2 = {
        "opportunities": thuc_thi(w, aid, "xem_co_hoi_san_xuat", {}),
        "fields": thuc_thi(w, aid, "dat_cong_gan", {"toi_da": 6}),
    }

    assert prompt_1 == prompt_2
    assert tools_1 == tools_2
    assert w.world_hash() == before


def test_homestead_card_is_factual_not_a_job_or_guaranteed_outcome():
    w, aid, _field = _world_with_homestead()
    card = next(
        row for row in _fact_cards_cuc_bo(w, aid)
        if row.startswith("FACT CARD — HOMESTEAD")
    ).lower()

    for forbidden in ("nên ", "hãy", "nghề", "phần thưởng", "chắc chắn", "đảm bảo"):
        assert forbidden not in card
    assert "phan_bo_cong.canh_thua" in card
    assert "tiep_tuc_homestead" not in card


def test_missing_one_rice_season_resets_provisional_homestead():
    w, aid, field = _world_with_homestead()
    w.tick = 4  # lua_1 of the next year

    production.thi_hanh_san_xuat(w, {aid: KeHoach(id=aid)})

    assert field.homestead_ai is None
    assert field.homestead_dem == 0
