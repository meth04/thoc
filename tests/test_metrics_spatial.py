"""Metric KHÔNG GIAN T13 (ADR 0005 §10) là QUAN SÁT thuần trong ``research_metrics``.

Chứng minh: (a) khong_gian.bat TẮT ⇒ MỌI khóa spatial = None, metric cũ + world_hash bất
biến (metric read-only, không vào hash); (b) BẬT + chuyến đò giả lập ⇒ số chuyến/dân-số-bờ-kia
đúng, phí trung vị + tỷ trọng tài sản đúng, entropy nghề ∈ [0,∞); (c) BẬT nhưng 0 dữ liệu ⇒
trung vị/tỷ trọng phí → None còn số đếm = 0 (0 THẬT, không undefined); (d) 2-run cùng seed
(OFF và ON) ⇒ cùng world_hash — thêm khóa read-only KHÔNG phá determinism/replay.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import spatial
from engine.config import load_config
from engine.intents import KeHoach
from engine.metrics_research import _SPATIAL_KEYS, research_metrics
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from tests.helpers import mind_tinh, the_gioi_test

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
)


def _on(seed: int = 3):
    return tao_the_gioi(load_config(overlays=[OVERLAY]), seed)


def _bo_khac(w, aid: str) -> str:
    return "hoang" if spatial._bo_cua(w, aid) == "dan_cu" else "dan_cu"


# --------------------------------------------------------------------------- #
#  OFF: mọi khóa spatial = None; metric cũ + world_hash bất biến                #
# --------------------------------------------------------------------------- #
def test_off_spatial_keys_deu_none_va_read_only():
    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=1500)
    h_truoc = w.world_hash()
    res = research_metrics(w)
    h_sau = w.world_hash()
    assert h_truoc == h_sau                       # gọi metric KHÔNG đổi hash (Lớp-5)
    assert "credit_outstanding" in res            # metric cũ còn nguyên
    for k in _SPATIAL_KEYS:
        assert res[k] is None, f"OFF: {k} phải None, nhận {res[k]!r}"


# --------------------------------------------------------------------------- #
#  ON + chuyến đò giả lập: số chuyến/phí/entropy có giá trị đúng                 #
# --------------------------------------------------------------------------- #
def test_on_co_chuyen_do_metric_dung():
    w = _on()
    op, kh = sorted(w.agents)[:2]
    w.ledger.sinh(op, "thuyen", 1.0, "dong_thuyen", "test", w.tick)
    den = _bo_khac(w, kh)
    ke = {op: KeHoach(id=op, rao_do=(5.0, "thoc")),
          kh: KeHoach(id=kh, qua_song=(den, "thoc", 5.0))}
    spatial.buoc_qua_song(w, ke)
    assert kh in w.ben_kia_tick                   # tiền đề: đã qua sông + trả phí thóc
    # nhãn giai cấp (lag 1 tick) — set thủ công để kiểm entropy đọc-thuần
    w.phan_loai = {"A": "nong", "B": "tho", "C": "nong"}
    res = research_metrics(w)

    assert res["river_crossing_volume"] == 1
    assert res["ben_kia_population"] == 1
    assert res["ferry_fare_median"] == 5.0
    assert res["ferry_payment_asset_share"] == {"thoc": 1.0}
    assert 0.0 < res["occupation_entropy"] < 1.0  # 2 nhãn (2:1) ⇒ entropy dương, < log(3)
    assert res["resource_stock_ca"] is not None and res["resource_stock_ca"] > 0.0
    assert isinstance(res["far_bank_cleared"], int) and res["far_bank_cleared"] >= 0
    assert res["land_use_by_bank"] is None or isinstance(res["land_use_by_bank"], dict)


def test_on_khong_do_thi_count_0_va_undefined_none():
    """ON nhưng 0 chuyến + chưa phân loại ⇒ số đếm = 0 (THẬT), phí/entropy = None."""
    w = _on()
    res = research_metrics(w)  # chưa ai qua sông, w.phan_loai rỗng ở tick 0
    assert res["river_crossing_volume"] == 0      # 0 chuyến là quan sát THẬT (không None)
    assert res["ben_kia_population"] == 0
    assert res["ferry_fare_median"] is None        # 0 phí ⇒ trung vị undefined
    assert res["ferry_payment_asset_share"] is None
    assert res["occupation_entropy"] is None       # phan_loai rỗng ⇒ undefined
    assert res["resource_stock_ca"] is not None     # ca_ton có sẵn dù chưa ai đánh cá


# --------------------------------------------------------------------------- #
#  Replay-same-hash: thêm metric read-only KHÔNG đổi world_hash                  #
# --------------------------------------------------------------------------- #
def test_off_2run_cung_hash_metric_khong_pha_determinism():
    def _run():
        w = the_gioi_test(seed=41, giu_lai=4, thoc_moi_nguoi=1500)
        for _ in range(5):
            chay_mot_tick(w, mind_tinh({}), len(w.parcels))
        return w.world_hash()

    assert _run() == _run()


def test_on_2run_cung_hash():
    from minds.policies import tao_policy

    def _run():
        w = _on(41)
        mind = tao_policy("rulebot")
        for _ in range(4):
            chay_mot_tick(w, mind, len(w.parcels))
        return w.world_hash()

    assert _run() == _run()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
