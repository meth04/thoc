"""Các metric hộ và đất là quan sát: không được thay đổi số dư hay quyền sở hữu."""

from __future__ import annotations

from engine.economy import (
    expected_land_value,
    expected_parcel_net_output,
    household_snapshot,
    households,
    land_price_productivity,
)
from engine.market import NiemYetDat, phien_dat
from tests.helpers import cap_ruong, the_gioi_test


def test_vo_chong_chi_duoc_dem_mot_ho():
    w = the_gioi_test(seed=5, giu_lai=2, thoc_moi_nguoi=1000)
    a, b = sorted(w.agents)[:2]
    w.agents[a].vo_chong = b
    w.agents[b].vo_chong = a
    assert households(w) == [[a, b]]
    snap = household_snapshot(w)
    assert len(snap) == 1
    assert snap[0]["grain"] == 2000


def test_san_luong_ky_vong_dat_tang_theo_do_mau():
    w = the_gioi_test(seed=5, giu_lai=1, thoc_moi_nguoi=1000)
    ids = cap_ruong(w, sorted(w.agents)[0], 2)
    low, high = ids
    w.parcels[low].mau_mo = 0.7
    w.parcels[high].mau_mo = 1.3
    assert expected_parcel_net_output(w, high) > expected_parcel_net_output(w, low) > 0
    assert expected_land_value(w, high) > expected_land_value(w, low) > 0


def test_neo_dat_pha_gia_cho_nhung_van_phan_biet_do_mau():
    w = the_gioi_test(seed=15, giu_lai=1, thoc_moi_nguoi=1000)
    ids = cap_ruong(w, sorted(w.agents)[0], 2)
    poor, rich = ids
    w.parcels[poor].mau_mo = 0.6
    w.parcels[rich].mau_mo = 1.4
    w.ghi_gia("dat", 1000, 1, "thoc")
    assert expected_land_value(w, rich) > expected_land_value(w, poor)


def test_giao_dich_dat_ghi_metric_von_hoa_ma_khong_dat_gia():
    w = the_gioi_test(seed=5, giu_lai=2, thoc_moi_nguoi=5000)
    seller, buyer = sorted(w.agents)[:2]
    (parcel,) = cap_ruong(w, seller, 1)
    phien_dat(w, {parcel: NiemYetDat(parcel, seller, 400.0, 0)}, [(buyer, parcel, 700.0)])
    assert len(w.giao_dich_dat) == 1
    observation = w.giao_dich_dat[0]
    assert observation["price"] == 700.0
    assert observation["expected_net_output"] > 0
    metric = land_price_productivity(w, window_ticks=8)
    assert metric["land_transactions_window"] == 1
    assert metric["land_price_to_expected_output"] > 0
