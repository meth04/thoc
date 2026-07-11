"""Test cây RNG — tất định & tái lập (điều luật #4)."""

from __future__ import annotations

import numpy as np

from engine.rng import RngTree


def test_cung_seed_cung_chuoi():
    a = RngTree(42).get("thoi_tiet", 7)
    b = RngTree(42).get("thoi_tiet", 7)
    assert np.array_equal(a.random(100), b.random(100))


def test_khac_subsystem_khac_chuoi():
    t = RngTree(42)
    a = t.get("thoi_tiet", 7).random(50)
    b = t.get("nhan_khau", 7).random(50)
    assert not np.array_equal(a, b)


def test_khac_tick_khac_chuoi():
    t = RngTree(42)
    a = t.get("thoi_tiet", 7).random(50)
    b = t.get("thoi_tiet", 8).random(50)
    assert not np.array_equal(a, b)


def test_khac_seed_khac_chuoi():
    a = RngTree(41).get("thoi_tiet", 0).random(50)
    b = RngTree(42).get("thoi_tiet", 0).random(50)
    assert not np.array_equal(a, b)


def test_goi_lai_khong_phu_thuoc_thu_tu():
    """Lấy generator theo thứ tự khác nhau → cùng (subsystem, tick) vẫn cùng chuỗi."""
    t1 = RngTree(42)
    x1 = t1.get("a", 1).random(10)
    _ = t1.get("b", 2).random(10)
    y1 = t1.get("c", 3).random(10)

    t2 = RngTree(42)
    y2 = t2.get("c", 3).random(10)
    x2 = t2.get("a", 1).random(10)
    assert np.array_equal(x1, x2)
    assert np.array_equal(y1, y2)


def test_ten_bam_on_dinh():
    """Băm tên không dùng hash() Python (đổi theo process) — chuỗi phải ổn định."""
    v = RngTree(123).get("san_xuat", 0).integers(0, 1_000_000, size=5)
    v2 = RngTree(123).get("san_xuat", 0).integers(0, 1_000_000, size=5)
    assert np.array_equal(v, v2)
