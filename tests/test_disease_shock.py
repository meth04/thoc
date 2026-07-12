"""Cú sốc dịch bệnh phải tắt mặc định, seeded và chỉ tác động khi scenario bật."""

from __future__ import annotations

from tests.helpers import chay_tick, mind_tinh, the_gioi_test


def test_dich_benh_tat_mac_dinh_khong_anh_huong_world():
    w = the_gioi_test(seed=29, giu_lai=1, thoc_moi_nguoi=5000)
    aid = sorted(w.agents)[0]
    chay_tick(w, mind_tinh({}), 1)
    assert w.dich_benh_tick is False
    # Mùa mưa không nhà vẫn mất 10 health; test chỉ khẳng định không có mất thêm vì dịch.
    assert w.agents[aid].health == 90.0


def test_dich_benh_bat_theo_scenario_giam_suc_khoe_deterministic():
    a = the_gioi_test(seed=31, giu_lai=1, thoc_moi_nguoi=5000)
    b = the_gioi_test(seed=31, giu_lai=1, thoc_moi_nguoi=5000)
    for w in (a, b):
        w.cfg.raw()["cu_soc"]["dich_benh"] = {
            "bat": True, "xac_suat_moi_nam": 1.0, "mat_suc_khoe_moi_tick": 7.0,
        }
    chay_tick(a, mind_tinh({}), 1)
    chay_tick(b, mind_tinh({}), 1)
    aid = sorted(a.agents)[0]
    assert a.dich_benh_tick is True
    assert a.agents[aid].health == 83.0  # 90 baseline mùa mưa − 7 do dịch
    assert a.world_hash() == b.world_hash()
