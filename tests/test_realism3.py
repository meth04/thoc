"""Gói realism 2: đất bạc màu, đánh cá, tiệc khao, trộm cắp, tay nghề, cưu mang mồ côi."""

from __future__ import annotations

from engine.intents import KeHoach
from engine.types import Agent, Persona
from tests.helpers import cap_ruong, chay_tick, mind_tinh, the_gioi_test


def _tick_mua_mua(w) -> int:
    """Tick mùa mưa kế tiếp (tick lẻ)."""
    return w.tick + 1 if (w.tick + 1) % 2 == 1 else w.tick + 2


def test_dat_bac_mau_va_phuc_hoi():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=8000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    (pid,) = cap_ruong(w, aid, 1)
    p = w.parcels[pid]
    goc = p.mau_mo_goc
    assert goc > 0
    # canh liên tục nhiều vụ → bạc màu dần, không tụt dưới sàn
    for _ in range(30):
        kh = KeHoach(id=aid, canh_thua=[pid])
        chay_tick(w, mind_tinh({w.tick + 1: {aid: kh}, w.tick + 2: {aid: kh}}), 2)
    san = goc * w.cfg.raw()["dat_dai"]["san_ty_le_mau_mo"]
    assert p.mau_mo < goc * 0.75
    assert p.mau_mo >= san - 1e-9
    # bỏ hoang → hồi dần về mức gốc
    truoc = p.mau_mo
    chay_tick(w, mind_tinh({}), 20)
    assert p.mau_mo > truoc
    assert p.mau_mo <= goc + 1e-9


def test_tay_nghe_tang_va_co_tran():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=9000.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    (pid,) = cap_ruong(w, aid, 1)
    a = w.agents[aid]
    assert a.tay_nghe == 1.0
    kh = KeHoach(id=aid, canh_thua=[pid])
    chay_tick(w, mind_tinh({w.tick + 1: {aid: kh}, w.tick + 2: {aid: kh}}), 2)
    assert a.tay_nghe > 1.0
    tran = w.cfg.raw()["tay_nghe"]["tran"]
    a.tay_nghe = tran
    chay_tick(w, mind_tinh({w.tick + 1: {aid: kh}, w.tick + 2: {aid: kh}}), 2)
    assert a.tay_nghe <= tran + 1e-9


def test_danh_ca_bat_duoc_ca_va_pool_co_han():
    w = the_gioi_test(seed=7, giu_lai=2, thoc_moi_nguoi=2000.0)
    a1, a2 = sorted(a for a, ag in w.agents.items() if ag.con_song)
    t = w.tick + 1
    kh1 = KeHoach(id=a1, danh_ca_cong=120.0)
    kh2 = KeHoach(id=a2, danh_ca_cong=120.0)
    chay_tick(w, mind_tinh({t: {a1: kh1, a2: kh2}}), 1)
    ca1 = w.ledger.so_du(a1, "ca")
    assert ca1 > 0
    # 120 công / 6 công/kg = 20kg trước hao hụt; hao 15% cuối tick
    dc = w.cfg.raw()["danh_ca"]
    ky_vong = (120.0 / dc["cong_moi_kg_ca"]) * (1 - dc["ca_hao_moi_tick"])
    assert abs(ca1 - ky_vong) < 1.0 or ca1 < ky_vong  # có thể chạm trần pool
    # pool giới hạn: tổng cá 2 người không vượt trữ lượng sông một tick
    so_o_song = sum(1 for p in w.parcels.values() if p.loai == "song")
    assert ca1 + w.ledger.so_du(a2, "ca") <= so_o_song * dc["ca_moi_o_song_kg"]


def test_an_ca_khi_het_thoc():
    w = the_gioi_test(seed=7, giu_lai=1, thoc_moi_nguoi=0.0)
    aid = sorted(a for a, ag in w.agents.items() if ag.con_song)[0]
    thoc_du = w.ledger.so_du(aid, "thoc")
    if thoc_du > 0:
        w.ledger.huy(aid, "thoc", thoc_du, "an", "fixture: dốc sạch kho thóc", 0)
    w.ledger.sinh(aid, "ca", 50.0, "danh_ca", "fixture", 0)
    chay_tick(w, mind_tinh({}), 1)
    # 50kg cá → hao 15% còn 42.5 × 2.5 = 106kg quy thóc ≥ 90kg nhu cầu → KHÔNG đói
    assert w.agents[aid].doi_tick == -99  # không bị đánh dấu thiếu ăn
    assert w.ledger.so_du(aid, "ca") < 42.5


def test_mo_tiec_doi_thoc_lay_quan_he():
    w = the_gioi_test(seed=7, giu_lai=4, thoc_moi_nguoi=3000.0)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    chu_tiec = ids[0]
    thoc_truoc = w.ledger.so_du(chu_tiec, "thoc")
    kh = KeHoach(id=chu_tiec, mo_tiec=(200.0, 0.0))
    chay_tick(w, mind_tinh({w.tick + 1: {chu_tiec: kh}}), 1)
    # thóc tiệc bị đốt thật (cùng các khoản ăn/hao khác)
    assert w.ledger.so_du(chu_tiec, "thoc") < thoc_truoc - 200.0 + 1e-9
    # ít nhất một khách được cộng quan hệ + ký ức
    khach_co_qh = [b for b in ids[1:] if w.uy_tin(chu_tiec, b) > 0]
    assert khach_co_qh
    assert any("tiệc" in ku for b in khach_co_qh for ku in w.agents[b].ky_uc)
    assert any("tiệc" in ku for ku in w.agents[chu_tiec].ky_uc)


def test_trom_thanh_cong_va_bi_bat():
    """Chạy trộm nhiều tick — phải thấy CẢ hai nhánh (trót lọt lẫn bị bắt)."""
    w = the_gioi_test(seed=7, giu_lai=2, thoc_moi_nguoi=5000.0)
    ke, nan_nhan = sorted(a for a, ag in w.agents.items() if ag.con_song)
    for _ in range(14):
        kh = KeHoach(id=ke, trom=(nan_nhan, "thoc", 100.0))
        chay_tick(w, mind_tinh({w.tick + 1: {ke: kh}}), 1)
    # đọc từ quan hệ + ký ức thay vì file log (fixture không ghi file)
    thay_bi_bat = any("bắt quả tang" in ku for ku in w.agents[ke].ky_uc)
    thay_thanh_cong = any("trót lọt" in ku for ku in w.agents[ke].ky_uc)
    assert thay_thanh_cong and thay_bi_bat
    # bị bắt → quan hệ với nạn nhân âm nặng
    assert w.uy_tin(ke, nan_nhan) < 0


def test_cuu_mang_mo_coi_va_an_chung_noi_com():
    w = the_gioi_test(seed=7, giu_lai=3, thoc_moi_nguoi=2000.0)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    cha, chu_ho, _ = ids
    # dựng đứa trẻ mồ côi: cha chết ngay tick tới, mẹ không tồn tại
    tre = Agent(id="A9001", ten="Bé Mồ Côi", gioi_tinh="nam", tuoi_tick=10,
                persona=Persona(), cha=cha, me=None)
    w.agents[tre.id] = tre
    w.agents[cha].con.append(tre.id)
    w.agents[cha].con_song = False
    chay_tick(w, mind_tinh({}), 1)
    assert tre.giam_ho is not None and w.agents[tre.giam_ho].con_song
    # ăn chung nồi cơm hộ người nuôi
    ho = w.ho_cua(tre.id)
    assert tre.giam_ho in ho and tre.id in ho
    assert any("cưu mang" in ku or "nhận nuôi" in ku or "nuôi" in ku
               for ku in w.agents[tre.giam_ho].ky_uc)


def test_xiet_the_chap_khong_gan_dat_cho_vo_thua_nhan():
    """Chủ nợ chết không người kế → vị thế VO_THUA_NHAN; xiết thế chấp KHÔNG được
    gán đất cho chủ ma (hồi quy: audit tick 170 seed 42 mock 200)."""
    from engine.contracts import (
        ClauseChuyenGiaoMotLan,
        ClauseKhiPhaVo,
        HopDong,
        phat_vi_pham,
    )
    from engine.world import VO_THUA_NHAN

    w = the_gioi_test(seed=7, giu_lai=2, thoc_moi_nguoi=3000.0)
    con_no, chu_no = sorted(a for a, ag in w.agents.items() if ag.con_song)
    (pid,) = cap_ruong(w, con_no, 1)
    hd = HopDong(cac_ben=[con_no, chu_no], hinh_thuc="van_ban", thoi_han=4,
                 the_chap=[f"thua:{pid}"],
                 dieu_khoan=[
                     ClauseChuyenGiaoMotLan(tu=con_no, den=chu_no, tai_san="thoc",
                                            so_luong=500.0, tai="dao_han"),
                     ClauseKhiPhaVo(phat="xiet_the_chap"),
                 ], nguoi_soan=chu_no)
    hd.id, hd.trang_thai, hd.tick_ky = "HD_TEST", "hieu_luc", w.tick
    w.hop_dong[hd.id] = hd
    # vị thế chủ nợ rơi vào vô thừa nhận (chết không người kế)
    w.ledger.flows.dang_ky(f"vi_the:{hd.id}:{chu_no}", "ky_hd", "nguon")
    w.ledger.sinh(chu_no, f"vi_the:{hd.id}:{chu_no}", 1.0, "ky_hd", "fixture", w.tick)
    w.ledger.chuyen(chu_no, VO_THUA_NHAN, f"vi_the:{hd.id}:{chu_no}", 1.0,
                    "vô thừa nhận", w.tick)
    from engine.contracts import xay_vi_the_chu

    xay_vi_the_chu(w)
    phat_vi_pham(w, hd, con_no)
    assert w.parcels[pid].chu == con_no  # đất KHÔNG về tay chủ ma


def test_bao_toan_voi_ca_va_tiec_100_tick():
    """Audit bảo toàn phải xanh khi có đủ cả cá, tiệc, trộm, gà trong 100 tick rulebot."""
    from minds.rulebot import quyet_dinh_tat_ca

    w = the_gioi_test(seed=11, giu_lai=10, thoc_moi_nguoi=1500.0)
    for i, aid in enumerate(sorted(a for a, ag in w.agents.items() if ag.con_song)):
        if i % 3 == 0:
            cap_ruong(w, aid, 2)
    chay_tick(w, quyet_dinh_tat_ca, 100)  # audit assert chạy bên trong mỗi tick
