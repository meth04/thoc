"""Gói realism 3: gà con cần nuôi, trữ lượng cá logistic, nhà cần góp công, ký ức hai tầng."""

from __future__ import annotations

from engine.intents import KeHoach
from engine.world import _ca_suc_chua
from tests.helpers import chay_tick, mind_tinh, the_gioi_test


def test_ga_con_phai_nuoi_moi_thanh_ga():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=3000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    kh = KeHoach(id=aid, bat_ga_cong=120.0)
    chay_tick(w, mind_tinh({w.tick + 1: {aid: kh}}), 1)
    # bắt về là GÀ CON — trong cùng tick chưa thành gà lớn... nhưng buoc_chan_nuoi
    # chạy CUỐI tick nên gà con bắt đầu tick này còn nguyên đến hết tick
    assert w.ledger.so_du(aid, "ga_con") >= 4  # 120 công / 30 = 4 con
    assert w.ledger.so_du(aid, "ga") == 0
    chay_tick(w, mind_tinh({}), 1)
    # sau 1 tick nuôi → trưởng thành
    assert w.ledger.so_du(aid, "ga") >= 3  # trừ hao tử suất tự nhiên
    assert w.ledger.so_du(aid, "ga_con") < 1


def test_giet_ga_non_it_thit():
    from engine.chan_nuoi import giet_ga

    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=1000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    w.ledger.sinh(aid, "ga_con", 2.0, "bat_rung", "fixture", 0)
    giet_ga(w, aid, 2)
    cn = w.cfg.raw()["chan_nuoi"]
    assert abs(w.ledger.so_du(aid, "thit") - 2 * cn["thit_moi_ga_con_kg"]) < 1e-6


def test_ca_tru_luong_rut_khi_danh_va_hoi_khi_nghi():
    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=3000.0)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    suc_chua = _ca_suc_chua(w)
    assert w.ca_ton > 0.7 * suc_chua
    # sông đã kiệt (fixture) → nghỉ đánh thì hồi theo logistic
    w.ca_ton = suc_chua * 0.2
    ton_kiet = w.ca_ton
    chay_tick(w, mind_tinh({}), 16)
    assert w.ca_ton > ton_kiet * 1.5  # hồi rõ rệt nhưng CẦN NHIỀU NĂM
    assert w.ca_ton <= suc_chua + 1e-6
    # đánh bắt rút trữ lượng đúng bằng lượng cá sinh ra trong sổ
    ton_truoc = w.ca_ton
    khs = {a: KeHoach(id=a, danh_ca_cong=180.0) for a in ids}
    chay_tick(w, mind_tinh({w.tick + 1: khs}), 1)
    assert any(w.ledger.so_du(a, "ca") > 0 for a in ids)  # có bắt được cá
    # trữ lượng sau < trước + tái sinh tối đa (đánh bắt đã rút bớt)
    assert w.ca_ton < ton_truoc + 0.15 * suc_chua / 4 + 1e-6


def test_ca_thua_thi_kho_bat():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=3000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    kh = KeHoach(id=aid, danh_ca_cong=90.0)
    chay_tick(w, mind_tinh({w.tick + 1: {aid: kh}}), 1)
    bat_day = w.ledger.so_du(aid, "ca")
    # vét trữ lượng xuống thấp rồi đánh cùng số công
    w.ca_ton = _ca_suc_chua(w) * 0.15
    w.ledger.huy(aid, "ca", w.ledger.so_du(aid, "ca"), "an", "fixture", w.tick)
    chay_tick(w, mind_tinh({w.tick + 1: {aid: KeHoach(id=aid, danh_ca_cong=90.0)}}), 1)
    bat_can = w.ledger.so_du(aid, "ca")
    assert bat_can < bat_day * 0.5  # cá thưa → cùng công bắt được ít hẳn


def test_nha_mot_minh_khong_dung_noi():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=3000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    w.ledger.sinh(aid, "go", 10.0, "khai_thac", "fixture", 0)
    t = w.tick + 1 if (w.tick + 1) % 2 == 0 else w.tick + 2  # mùa khô
    chay_tick(w, mind_tinh({t: {aid: KeHoach(id=aid, xay_nha=1)}}),
              t - w.tick)
    assert w.ledger.so_du(aid, "nha") == 0  # 240 công > 180 một người
    assert any("nha" in sc or "nhà" in sc for sc in w.agents[aid].su_co)


def test_nha_dung_duoc_khi_co_nguoi_gop_cong():
    w = the_gioi_test(seed=7, giu_lai=2, thoc_moi_nguoi=3000.0)
    a1, a2 = sorted(a for a, ag in w.agents.items() if ag.con_song)
    w.ledger.sinh(a1, "go", 10.0, "khai_thac", "fixture", 0)
    t = w.tick + 1 if (w.tick + 1) % 2 == 0 else w.tick + 2
    khs = {a1: KeHoach(id=a1, xay_nha=1), a2: KeHoach(id=a2, gop_cong_cho=a1)}
    chay_tick(w, mind_tinh({t: khs}), t - w.tick)
    assert w.ledger.so_du(a1, "nha") == 1.0  # 180 + 180 công ≥ 240


def test_ky_uc_doi_khong_troi():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=1000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    w.ghi_ky_uc(aid, "tôi kết hôn với X", doi=True)
    for i in range(25):  # 25 chuyện vặt — vượt xa cap rolling 10
        w.ghi_ky_uc(aid, f"chuyện vặt {i}")
    a = w.agents[aid]
    assert any("kết hôn" in m for m in a.ky_uc_doi)  # dấu mốc không trôi
    assert len(a.ky_uc) <= int(w.cfg.get("minds.ky_uc_toi_da"))
    assert not any("kết hôn" in m for m in a.ky_uc)
