"""PART 5.4 — P2P nhắn tin 1-1: giao tick sau, thuần thông tin, không chạm Ledger."""

from __future__ import annotations

from engine.intents import KeHoach
from tests.helpers import chay_tick, mind_tinh, the_gioi_test


def test_tin_nhan_giao_tick_sau_va_hien_trong_prompt():
    from minds.prompts import build_user_rieng

    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=2000.0)
    a1, a2, _a3 = sorted(a for a, ag in w.agents.items() if ag.con_song)
    h0 = w.world_hash()
    kh = KeHoach(id=a1, nhan_tin=[(a2, "Bán cho tôi 5 gỗ giá 60 thóc nhé?")])
    chay_tick(w, mind_tinh({w.tick + 1: {a1: kh}}), 1)
    # tin đã vào hòm thư người nhận (giao ở prompt tick này/kế)
    thu = w.hom_thu.get(a2, [])
    assert any(tu == a1 and "gỗ" in noi for tu, noi, _t in thu)
    # người nhận THẤY tin trong prompt riêng của mình
    p = build_user_rieng(w, a2, [])
    assert "TIN NHẮN" in p and a1 in p
    # thuần thông tin: không tài sản nào dịch chuyển (audit vẫn xanh ở chay_tick trên)
    # — kho thóc/gỗ hai bên không đổi vì nhắn tin
    assert w.ledger.so_du(a1, "thoc") > 0 and w.ledger.so_du(a2, "thoc") > 0
    _ = h0


def test_tin_nhan_song_dung_mot_tick():
    w = the_gioi_test(seed=7, giu_lai=2, thoc_moi_nguoi=2000.0)
    a1, a2 = sorted(a for a, ag in w.agents.items() if ag.con_song)
    kh = KeHoach(id=a1, nhan_tin=[(a2, "chào bác")])
    chay_tick(w, mind_tinh({w.tick + 1: {a1: kh}}), 1)
    assert w.hom_thu.get(a2)
    # tick sau không ai gửi → hòm thư được thay mới (rỗng), tin cũ tan
    chay_tick(w, mind_tinh({}), 1)
    assert not w.hom_thu.get(a2)


def test_khong_gui_cho_nguoi_chet_hay_chinh_minh():
    w = the_gioi_test(seed=7, giu_lai=2, thoc_moi_nguoi=2000.0)
    a1, a2 = sorted(a for a, ag in w.agents.items() if ag.con_song)
    w.agents[a2].con_song = False  # a2 vừa mất
    kh = KeHoach(id=a1, nhan_tin=[(a2, "gửi người đã khuất"), (a1, "gửi chính mình")])
    chay_tick(w, mind_tinh({w.tick + 1: {a1: kh}}), 1)
    assert not w.hom_thu.get(a2) and not w.hom_thu.get(a1)


def test_p2p_khong_pha_tat_dinh_va_bao_toan():
    """Mock ngắn (rulebot có gửi tin) — audit xanh + cùng seed cùng hash."""
    from minds.orchestrator import tao_mind_mock

    def chay():
        w = the_gioi_test(seed=17, giu_lai=10, thoc_moi_nguoi=1500.0)
        mind = tao_mind_mock(w, fast=True)
        chay_tick(w, mind, 20)  # audit assert bên trong mỗi tick
        return w.world_hash()

    assert chay() == chay()
