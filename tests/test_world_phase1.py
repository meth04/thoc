"""Test Phase 1: thế giới nhỏ chạy nhanh — bảo toàn, tất định, resume."""

from __future__ import annotations

from engine.config import load_config
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from minds.rulebot import quyet_dinh_tat_ca


def chay(seed: int, so_tick: int, w=None):
    cfg = load_config()
    if w is None:
        w = tao_the_gioi(cfg, seed)
    tong_thua = len(w.parcels)
    while w.tick < so_tick:
        chay_mot_tick(w, quyet_dinh_tat_ca, tong_thua)
    return w


def test_40_tick_audit_xanh_va_con_nguoi_song():
    w = chay(seed=7, so_tick=40)  # audit raise nếu vi phạm — chạy trọn là xanh
    song = [a for a in w.agents.values() if a.con_song]
    assert len(song) > 0
    assert w.ledger.tong_tai_san("cong") == 0  # công bốc hơi hết


def test_tat_dinh_cung_seed():
    h1 = chay(seed=11, so_tick=30).world_hash()
    h2 = chay(seed=11, so_tick=30).world_hash()
    assert h1 == h2


def test_khac_seed_khac_the_gioi():
    h1 = chay(seed=11, so_tick=30).world_hash()
    h2 = chay(seed=12, so_tick=30).world_hash()
    assert h1 != h2


def test_resume_giong_chay_lien(tmp_path):
    """Chạy 30 tick, checkpoint, nạp lại chạy tiếp 30 = chạy liền 60 tick."""
    w = chay(seed=5, so_tick=30)
    ck = w.luu_checkpoint(tmp_path)
    from engine.world import World

    w2 = World.nap_checkpoint(ck)
    w2 = chay(seed=5, so_tick=60, w=w2)
    w_lien = chay(seed=5, so_tick=60)
    assert w2.world_hash() == w_lien.world_hash()


def test_homestead_chuyen_chu():
    """Canh đất công 2 mùa mưa liên tiếp → thành chủ."""
    w = chay(seed=7, so_tick=10)
    co_chu = [p for p in w.parcels.values() if p.chu is not None]
    assert len(co_chu) > 0  # sau 5 năm phải có người homestead xong


def test_thua_ke_khong_mat_tai_san():
    """Tổng thóc trước/sau người chết chỉ thay đổi qua luồng đăng ký (audit đã ép)."""
    w = chay(seed=7, so_tick=80)
    da_chet = [a for a in w.agents.values() if not a.con_song]
    assert len(da_chet) > 0
    for a in da_chet:
        assert w.ledger.so_du(a.id, "thoc") < 1e-6  # người chết không ôm tài sản
