"""Survival floor phải minh bạch, tối thiểu và không lấn quyết định đã có."""

from __future__ import annotations

from engine.intents import KeHoach
from minds.orchestrator import MindMock
from minds.rulebot import _BoiCanhTick
from minds.safety import ap_dung_san_an_toi_thieu
from minds.schemas import QuyetDinh
from tests.helpers import chay_tick, the_gioi_test


def _world_at_sowing():
    w = the_gioi_test(seed=19, giu_lai=1, thoc_moi_nguoi=200.0)
    w.tick = 1  # mùa mưa
    return w, sorted(w.agents)[0]


def test_san_an_toi_thieu_bo_sung_mot_vu_khi_llm_quen_canhtac():
    w, aid = _world_at_sowing()
    plans = {aid: KeHoach(id=aid)}
    count = ap_dung_san_an_toi_thieu(w, plans, _BoiCanhTick(w), set())
    assert count == 1
    assert len(plans[aid].canh_thua) == 1


def test_san_an_toi_thieu_khong_chen_ke_hoach_canhtac_da_co():
    w, aid = _world_at_sowing()
    planned = [next(p.id for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)]
    plans = {aid: KeHoach(id=aid, canh_thua=planned)}
    assert ap_dung_san_an_toi_thieu(w, plans, _BoiCanhTick(w), set()) == 0
    assert plans[aid].canh_thua == planned


def test_pipeline_khong_de_nguoi_nghi_rong_chet_doi_vi_bo_mua_gieo():
    """Hồi quy từ pilot real: thinker trả JSON hợp lệ nhưng không phân bổ công."""
    w = the_gioi_test(seed=23, giu_lai=1, thoc_moi_nguoi=200.0)
    aid = sorted(w.agents)[0]
    # Tick đầu tăng tuổi lên đúng mốc 16, buộc agent đi qua nhánh "nghĩ".
    w.agents[aid].tuoi_tick = 31
    mind = MindMock(w, fast=True, run_dir=None, p_malformed=0.0)
    mind._nghi_dong_bo = lambda *_args, **_kwargs: QuyetDinh(id=aid)  # type: ignore[method-assign]
    chay_tick(w, mind, 9)
    assert w.agents[aid].con_song
    # Nếu floor không xen vào tick 1, tồn kho 200kg không thể sống qua nhiều tick.
    assert w.ledger.so_du(aid, "thoc") > 200.0
