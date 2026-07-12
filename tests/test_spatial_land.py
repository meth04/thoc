"""ADR 0005 Phase D (khai hoang bờ kia) + endowment food-equivalent (§7).

Bất biến then chốt:
- OFF (mặc định): world_hash + homestead legacy y nguyên; intent ``khai_hoang`` bị BỎ QUA
  (path no-op, không tốn công, không đổi ``loai``).
- ON: agent ĐANG Ở bờ kia (đã qua đò) vỡ được rừng/đồi CÔNG → ruộng (tạo quyền đất HỢP LỆ
  qua homestead, không free-grab); agent CHƯA qua sông KHÔNG vỡ được thửa bờ kia.
- Endowment ON: mỗi thành viên nhận đúng một-năm food-equivalent theo tuổi, audit xanh,
  KHÔNG food-mint sau tick 0. OFF: 200 kg phẳng.
- Tất định: 2 run cùng seed(+overlay) ⇒ cùng world_hash.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import production
from engine.audit import kiem_toan_the_gioi
from engine.config import load_config
from engine.intents import KeHoach
from engine.world import _endowment_t0_kg, tao_the_gioi
from tests.helpers import chay_tick, mind_tinh

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
)
SEED = 41


def _thua_cong(w, bo: str | None = None, loai=("rung", "doi")):
    """Thửa rừng/đồi CÔNG (chu=None) đầu tiên theo id — tất định."""
    return next(
        p for p in sorted(w.parcels.values(), key=lambda x: x.id)
        if p.loai in loai and p.chu is None and (bo is None or p.bo == bo)
    )


def _cap(w, aid, ts, sl, luong):
    cur = w.ledger.so_du(aid, ts)
    if cur < sl:
        w.ledger.sinh(aid, ts, sl - cur, luong, "fixture", w.tick)


# --------------------------------------------------------------------------- #
#  OFF = legacy bất biến                                                         #
# --------------------------------------------------------------------------- #
def test_off_khai_hoang_bi_bo_qua_va_hash_bat_bien():
    """Mặc định: 2 run cùng seed ⇒ cùng hash; intent khai_hoang là no-op (không tốn công,
    không đổi loai) vì cổng ``khong_gian.bat`` TẮT."""
    w1 = tao_the_gioi(load_config(), SEED)
    w2 = tao_the_gioi(load_config(), SEED)
    assert w1.world_hash() == w2.world_hash()
    p = _thua_cong(w2)
    loai0 = p.loai
    aid = sorted(w2.agents)[0]
    _cap(w2, aid, "cong", 500.0, "sinh_cong")
    cong_truoc = w2.ledger.so_du(aid, "cong")
    production.khai_hoang_dat(w2, {aid: KeHoach(id=aid, khai_hoang=[p.id])})
    assert w2.parcels[p.id].loai == loai0                       # KHÔNG đổi loai
    assert w2.ledger.so_du(aid, "cong") == pytest.approx(cong_truoc)  # KHÔNG tốn công


def test_off_homestead_ruong_cong_van_nhu_cu():
    """Chèn ``khai_hoang_dat`` (no-op OFF) KHÔNG phá homestead: canh công-ruộng 2 vụ mưa
    liên tiếp ⇒ thành chủ như cũ."""
    w = tao_the_gioi(load_config(), SEED)
    aid = sorted(w.agents)[0]
    p = _thua_cong(w, loai=("ruong",))
    for t in (1, 3):
        w.tick = t
        _cap(w, aid, "cong", 500.0, "sinh_cong")
        _cap(w, aid, "thoc", 2000.0, "khoi_tao")
        production.thi_hanh_san_xuat(w, {aid: KeHoach(id=aid, canh_thua=[p.id])})
    assert w.parcels[p.id].chu == aid


# --------------------------------------------------------------------------- #
#  ON = khai hoang bờ kia                                                        #
# --------------------------------------------------------------------------- #
def test_on_khai_hoang_bo_kia_can_qua_song():
    """Thửa rừng/đồi bờ ``hoang``: chưa qua sông ⇒ KHÔNG vỡ được (không tốn công); qua đò
    rồi (``ben_kia_tick``) ⇒ vỡ thành ruộng, hạ độ màu về đất mới vỡ."""
    w = tao_the_gioi(load_config(overlays=[OVERLAY]), SEED)
    p = _thua_cong(w, bo="hoang")
    aid = sorted(w.agents)[0]
    _cap(w, aid, "cong", 1000.0, "sinh_cong")
    kh = {aid: KeHoach(id=aid, khai_hoang=[p.id])}
    production.khai_hoang_dat(w, kh)                       # chưa qua sông
    assert w.parcels[p.id].loai in ("rung", "doi")
    assert w.ledger.so_du(aid, "cong") == pytest.approx(1000.0)
    w.ben_kia_tick = {aid}                                # đã qua đò
    production.khai_hoang_dat(w, kh)
    assert w.parcels[p.id].loai == "ruong"
    assert w.parcels[p.id].mau_mo == pytest.approx(0.7)
    assert w.ledger.so_du(aid, "cong") == pytest.approx(1000.0 - 120.0)
    assert w.parcels[p.id].chu is None                    # KHÔNG cấp title free


def test_on_khai_hoang_tao_quyen_dat_qua_homestead():
    """Vỡ hoang rồi canh liên tiếp 2 vụ mưa ⇒ quyền đất HỢP LỆ qua homestead (không tức thì)."""
    w = tao_the_gioi(load_config(overlays=[OVERLAY]), SEED)
    p = _thua_cong(w, bo="hoang")
    aid = sorted(w.agents)[0]
    w.ben_kia_tick = {aid}
    w.tick = 1
    _cap(w, aid, "cong", 1000.0, "sinh_cong")
    _cap(w, aid, "thoc", 2000.0, "khoi_tao")
    production.thi_hanh_san_xuat(w, {aid: KeHoach(id=aid, khai_hoang=[p.id], canh_thua=[p.id])})
    assert w.parcels[p.id].loai == "ruong"
    assert w.parcels[p.id].chu is None                    # mới 1 vụ ⇒ chưa thành chủ
    assert w.parcels[p.id].homestead_ai == aid
    w.tick = 3
    _cap(w, aid, "cong", 1000.0, "sinh_cong")
    _cap(w, aid, "thoc", 2000.0, "khoi_tao")
    production.thi_hanh_san_xuat(w, {aid: KeHoach(id=aid, canh_thua=[p.id])})
    assert w.parcels[p.id].chu == aid


def test_on_khai_hoang_tat_dinh_2run():
    """2 run cùng seed+overlay ⇒ cùng world_hash sau khai hoang (path D tất định)."""
    def chay(seed: int):
        w = tao_the_gioi(load_config(overlays=[OVERLAY]), seed)
        p = _thua_cong(w, bo="hoang")
        aid = sorted(w.agents)[0]
        w.ben_kia_tick = {aid}
        _cap(w, aid, "cong", 500.0, "sinh_cong")
        production.khai_hoang_dat(w, {aid: KeHoach(id=aid, khai_hoang=[p.id])})
        return w.world_hash(), w.parcels[p.id].loai
    a, b = chay(SEED), chay(SEED)
    assert a == b
    assert a[1] == "ruong"


# --------------------------------------------------------------------------- #
#  Determinism ON (chạy tick với static mind) + endowment                       #
# --------------------------------------------------------------------------- #
def test_on_2run_chay_tick_cung_hash():
    """Overlay ON + static mind (không intent) ⇒ 2 world cùng seed vẫn cùng hash sau tick."""
    w1 = tao_the_gioi(load_config(overlays=[OVERLAY]), SEED)
    w2 = tao_the_gioi(load_config(overlays=[OVERLAY]), SEED)
    assert w1.world_hash() == w2.world_hash()
    m = mind_tinh({})
    chay_tick(w1, m, 4)
    chay_tick(w2, m, 4)
    assert w1.world_hash() == w2.world_hash()


def test_endowment_off_giu_200_phang():
    """OFF (mặc định): endowment = ``thoc_moi_nguoi`` 200 kg phẳng."""
    cfg = load_config()
    assert _endowment_t0_kg(cfg, la_nguoi_lon=True) == pytest.approx(200.0)
    assert _endowment_t0_kg(cfg, la_nguoi_lon=False) == pytest.approx(200.0)
    w = tao_the_gioi(cfg, SEED)
    for aid in w.agents:
        assert w.ledger.so_du(aid, "thoc") == pytest.approx(200.0)


def test_endowment_on_food_equiv_theo_tuoi_va_khong_mint_sau_t0():
    """ON: người lớn = nguoi_lon_kg_tick × tick/năm (90×2=180), trẻ = 45×2=90; audit xanh;
    KHÔNG food-mint sau tick 0 (luồng khoi_tao đứng yên khi chạy tiếp)."""
    cfg = load_config(overlays=[OVERLAY])
    cfg.raw()["khong_gian"]["endowment"]["bat"] = True
    assert _endowment_t0_kg(cfg, la_nguoi_lon=True) == pytest.approx(180.0)
    assert _endowment_t0_kg(cfg, la_nguoi_lon=False) == pytest.approx(90.0)
    w = tao_the_gioi(cfg, SEED)
    n = len(w.agents)
    for aid in w.agents:                                  # t0 toàn người lớn (tuổi ≥16)
        assert w.ledger.so_du(aid, "thoc") == pytest.approx(180.0)
    kiem_toan_the_gioi(w, len(w.parcels))                 # audit xanh t0
    khoi0 = w.ledger.flows._tich_luy.get(("thoc", "khoi_tao"), 0.0)
    assert khoi0 == pytest.approx(180.0 * n)
    chay_tick(w, mind_tinh({}), 4)                        # audit chạy trong từng tick
    assert w.ledger.flows._tich_luy.get(("thoc", "khoi_tao"), 0.0) == pytest.approx(khoi0)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
