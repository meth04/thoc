"""ADR 0005 Phase A — nền tảng không gian: Parcel.bo + topology hai bờ + helper thuần đọc.

Bất biến then chốt: overlay TẮT (mặc định) ⇒ bản đồ + world_hash + phân bố hệt legacy
(field `bo` thêm vào KHÔNG đổi hash); overlay BẬT ⇒ hai bờ tất định, sông chặn liên bờ.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.config import load_config
from engine.rng import RngTree
from engine.spatial import cung_bo, qua_song_can_do, reachable
from engine.world import tao_the_gioi
from engine.worldmap import sinh_ban_do

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
)


def _sinh(cfg, seed: int):
    """Sinh bản đồ đúng như tao_the_gioi (cùng nhánh RNG 'khoi_tao')."""
    g = RngTree(seed).get("khoi_tao", 0)
    return sinh_ban_do(cfg, g)


# --------------------------------------------------------------------------- #
#  Legacy invariant (overlay TẮT = mặc định)                                    #
# --------------------------------------------------------------------------- #
def test_off_khong_phan_bo_va_hash_tat_dinh():
    """Config mặc định: 2 run cùng seed ⇒ cùng world_hash; mọi thửa `bo=None`."""
    w1 = tao_the_gioi(load_config(), 42)
    w2 = tao_the_gioi(load_config(), 42)
    assert w1.world_hash() == w2.world_hash()
    assert all(p.bo is None for p in w1.parcels.values())


def test_off_bo_khong_vao_world_hash():
    """Gán `bo` cho thửa KHÔNG đổi world_hash ⇒ chứng minh `bo` nằm ngoài hash-struct."""
    w = tao_the_gioi(load_config(), 7)
    h0 = w.world_hash()
    p = next(p for p in w.parcels.values() if p.loai != "song")
    p.bo = "dan_cu"
    other = next(p for p in w.parcels.values() if p.loai == "song")
    other.bo = "hoang"
    assert w.world_hash() == h0


def test_off_ban_do_tat_dinh_giua_hai_run():
    """Bản đồ (loai/màu mỡ) trùng nhau giữa 2 run cùng seed khi overlay TẮT."""
    p1, _ = _sinh(load_config(), 5)
    p2, _ = _sinh(load_config(), 5)
    m1 = {k: (p.loai, round(p.mau_mo, 6)) for k, p in p1.items()}
    m2 = {k: (p.loai, round(p.mau_mo, 6)) for k, p in p2.items()}
    assert m1 == m2


# --------------------------------------------------------------------------- #
#  Overlay load                                                                 #
# --------------------------------------------------------------------------- #
def test_overlay_merge_sach():
    """`load_config(overlays=[spatial_v1])` bật cờ mà KHÔNG nuốt key base."""
    cfg = load_config(overlays=[OVERLAY])
    assert cfg.get("khong_gian.bat") is True
    assert cfg.get("khong_gian.hai_bo") is True
    # base giữ nguyên (deep_merge không clobber)
    assert cfg.get("ban_do.kich_thuoc") == [30, 30]
    assert cfg.get("san_xuat.recipe.nha.cong") == 240      # recipe cũ còn nguyên
    assert cfg.get("san_xuat.recipe.thuyen.go") == 6       # recipe mới được thêm
    # base config KHÔNG có khong_gian ⇒ mặc định TẮT
    assert load_config().get("khong_gian.bat", False) is False


# --------------------------------------------------------------------------- #
#  Topology (overlay BẬT)                                                       #
# --------------------------------------------------------------------------- #
def test_on_chia_dung_hai_bo():
    """Sông chia map thành đúng 2 bờ không rỗng; làng nằm bờ dân cư; ô sông `bo=None`."""
    cfg = load_config(overlays=[OVERLAY])
    parcels, villages = _sinh(cfg, 3)
    bo_dat = {p.bo for p in parcels.values() if p.loai != "song"}
    assert bo_dat == {"dan_cu", "hoang"}
    assert sum(p.bo == "dan_cu" for p in parcels.values()) > 0
    assert sum(p.bo == "hoang" for p in parcels.values()) > 0
    # ô sông không thuộc bờ nào
    assert all(p.bo is None for p in parcels.values() if p.loai == "song")
    # làng nằm bờ dân cư; ruộng tập trung bờ dân cư; mỏ ở bờ hoang
    v = villages[0]
    assert parcels[f"P{v.r:02d}_{v.c:02d}"].bo == "dan_cu"
    assert all(p.bo == "dan_cu" for p in parcels.values() if p.loai == "ruong")
    assert all(p.bo == "hoang" for p in parcels.values() if p.loai == "mo_dong")


def test_on_cung_bo_va_qua_song():
    """`cung_bo`/`qua_song_can_do` đúng cho cặp cùng bờ và cặp hai bờ."""
    cfg = load_config(overlays=[OVERLAY])
    parcels, _ = _sinh(cfg, 3)
    dan = [p for p in parcels.values() if p.bo == "dan_cu"]
    hoang = [p for p in parcels.values() if p.bo == "hoang"]
    song = next(p for p in parcels.values() if p.loai == "song")
    # cùng bờ
    assert cung_bo(dan[0], dan[1]) is True
    assert qua_song_can_do(dan[0], dan[1]) is False
    # khác bờ ⇒ cần đò
    assert cung_bo(dan[0], hoang[0]) is False
    assert qua_song_can_do(dan[0], hoang[0]) is True
    # ô sông (bo=None) không dựng rào
    assert cung_bo(song, hoang[0]) is True
    assert qua_song_can_do(song, hoang[0]) is False


def test_reachability_can_do_khi_khac_bo():
    """Cùng bờ đi được không cần đò; khác bờ chỉ tới khi có đò."""
    cfg = load_config(overlays=[OVERLAY])
    parcels, _ = _sinh(cfg, 3)
    dan = [p for p in parcels.values() if p.bo == "dan_cu"]
    hoang = [p for p in parcels.values() if p.bo == "hoang"]
    assert reachable(dan[0], dan[1], co_do=False) is True
    assert reachable(dan[0], hoang[0], co_do=False) is False
    assert reachable(dan[0], hoang[0], co_do=True) is True


# --------------------------------------------------------------------------- #
#  Determinism (overlay BẬT)                                                    #
# --------------------------------------------------------------------------- #
def test_on_tat_dinh_phan_bo_bo():
    """2 run cùng seed + overlay ⇒ cùng phân bố `bo`, cùng loại đất, cùng world_hash."""
    cfg = load_config(overlays=[OVERLAY])
    p1, v1 = _sinh(cfg, 11)
    p2, v2 = _sinh(cfg, 11)
    assert {k: p.bo for k, p in p1.items()} == {k: p.bo for k, p in p2.items()}
    assert {k: p.loai for k, p in p1.items()} == {k: p.loai for k, p in p2.items()}
    assert (v1[0].r, v1[0].c) == (v2[0].r, v2[0].c)
    w1 = tao_the_gioi(load_config(overlays=[OVERLAY]), 11)
    w2 = tao_the_gioi(load_config(overlays=[OVERLAY]), 11)
    assert w1.world_hash() == w2.world_hash()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
