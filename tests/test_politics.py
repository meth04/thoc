"""Cơ chế nhà nước TRUNG LẬP (engine/politics.py) — bốn cổng bắt buộc.

(a) bầu cử chọn đúng người NHIỀU PHIẾU NHẤT + tất định (world_hash trùng);
(b) thuế BẢO TOÀN: chuyển CÂN, tổng thóc không đổi, công quỹ chia hết, audit xanh;
(c) bạo động CHỈ kích hoạt khi đủ điều kiện (Gini cao + số đông) + bảo toàn;
(d) hối lộ là chuyển CÂN (không sinh/hủy thóc).

Nguyên tắc tự phát (điều luật #7): mọi ý định do agent phát; engine không thiên vị.
Ledger sanctity (điều luật #1): mọi dịch chuyển qua CONG_QUY, không sửa số dư trực tiếp.
"""

from __future__ import annotations

from engine import audit, politics
from engine.config import load_config
from engine.intents import KeHoach
from engine.world import CONG_QUY, ChinhQuyen, tao_the_gioi
from tests.helpers import cap_ruong, chay_tick, mind_tinh, the_gioi_test

TICK_BAU = 20  # = chinh_tri.bau_cu_moi_n_tick trong config


def _ids_song(w) -> list[str]:
    return sorted(a for a, ag in w.agents.items() if ag.con_song)


# ------------------------------------------------------------------ (a) bầu cử


def _dung_bau_cu(seed: int):
    """Thế giới ở tick bầu cử với 2 ứng viên; dồn 3 phiếu cho ids[1], 1 cho ids[0]."""
    w = tao_the_gioi(load_config(), seed)
    w.tick = TICK_BAU
    ids = _ids_song(w)
    kh = {aid: KeHoach(id=aid) for aid in ids}
    kh[ids[0]].ung_cu = True
    kh[ids[1]].ung_cu = True
    kh[ids[2]].bo_phieu = ids[1]
    kh[ids[3]].bo_phieu = ids[1]
    kh[ids[4]].bo_phieu = ids[1]
    kh[ids[5]].bo_phieu = ids[0]
    return w, kh, ids


def test_bau_cu_chon_nguoi_nhieu_phieu_nhat():
    w, kh, ids = _dung_bau_cu(seed=1)
    politics.buoc_chinh_quyen(w, kh)
    assert w.chinh_quyen.truong_lang == ids[1]
    assert w.chinh_quyen.nhiem_ky_den == TICK_BAU + int(
        w.cfg.get("chinh_tri.nhiem_ky_tick"))


def test_bau_cu_tat_dinh_cung_seed_cung_ke_hoach():
    w1, kh1, ids = _dung_bau_cu(seed=1)
    w2, kh2, _ = _dung_bau_cu(seed=1)
    politics.buoc_chinh_quyen(w1, kh1)
    politics.buoc_chinh_quyen(w2, kh2)
    assert w1.chinh_quyen.truong_lang == w2.chinh_quyen.truong_lang == ids[1]
    assert w1.world_hash() == w2.world_hash()  # cùng thao tác → cùng thế giới (điều luật #4)


def test_bau_cu_hoa_phieu_id_nho_thang():
    """Hòa phiếu → tie-break id nhỏ hơn (tất định, không thiên vị)."""
    w = tao_the_gioi(load_config(), seed=2)
    w.tick = TICK_BAU
    ids = _ids_song(w)
    kh = {aid: KeHoach(id=aid) for aid in ids}
    kh[ids[0]].ung_cu = True
    kh[ids[1]].ung_cu = True
    kh[ids[2]].bo_phieu = ids[0]
    kh[ids[3]].bo_phieu = ids[1]  # hòa 1–1
    politics.buoc_chinh_quyen(w, kh)
    assert w.chinh_quyen.truong_lang == ids[0]


def test_vo_chinh_phu_khi_khong_co_y_dinh():
    """Không hành vi chính trị nào → w.chinh_quyen vẫn None (tự phát, điều luật #7)."""
    w = tao_the_gioi(load_config(), seed=3)
    ids = _ids_song(w)
    politics.buoc_chinh_quyen(w, {aid: KeHoach(id=aid) for aid in ids})
    assert w.chinh_quyen is None


# ------------------------------------------------------------------ (b) thuế


def test_thue_bao_toan_va_chia_het_cong_quy():
    w = the_gioi_test(seed=5, giu_lai=6, thoc_moi_nguoi=1000)
    ids = _ids_song(w)
    farmer = ids[0]
    w.chinh_quyen = ChinhQuyen(truong_lang=farmer, thue_suat=0.2, nhiem_ky_den=999)
    w.gat_tick = {"Pxx": (farmer, 500.0)}  # người này vừa gặt 500kg
    tong_truoc = w.ledger.tong_tai_san("thoc")
    politics.thu_thue_va_chia(w)
    assert abs(w.ledger.tong_tai_san("thoc") - tong_truoc) < 1e-6  # chuyển CÂN
    assert w.ledger.so_du(CONG_QUY, "thoc") < 1e-6  # công quỹ chia hết về 0
    audit.kiem_toan(w.ledger, w.tick)  # raise nếu lệch


def test_thue_qua_mot_tick_that_audit_xanh():
    """Thuế đi qua chay_mot_tick (audit chạy cuối tick) — không lệch bảo toàn."""
    w = the_gioi_test(seed=3, giu_lai=6, thoc_moi_nguoi=2000)
    ids = _ids_song(w)
    thua = cap_ruong(w, ids[0], 2)
    w.chinh_quyen = ChinhQuyen(truong_lang=ids[0], thue_suat=0.3, nhiem_ky_den=999)
    plans = {1: {ids[0]: KeHoach(id=ids[0], canh_thua=thua)}}  # tick 1 = mùa mưa → gặt
    chay_tick(w, mind_tinh(plans), 1)  # audit raise nếu vi phạm bảo toàn
    assert w.ledger.so_du(CONG_QUY, "thoc") < 1e-6


def test_thue_suat_bi_chan_tran():
    """Trưởng làng đặt thuế vượt trần → bị ép về thue_suat_toi_da (engine cưỡng chế)."""
    w = the_gioi_test(seed=6, giu_lai=4, thoc_moi_nguoi=500)
    ids = _ids_song(w)
    truong = ids[0]
    w.chinh_quyen = ChinhQuyen(truong_lang=truong, nhiem_ky_den=999)
    kh = {aid: KeHoach(id=aid) for aid in ids}
    kh[truong].ban_hanh_luat = {"loai": "thue", "suat": 9.9}
    politics.buoc_chinh_quyen(w, kh)
    assert w.chinh_quyen.thue_suat == float(w.cfg.get("chinh_tri.thue_suat_toi_da"))


def test_chi_truong_lang_moi_lap_phap():
    """Người thường ra luật → bị bỏ qua (chỉ trưởng làng đương nhiệm mới đặt được)."""
    w = the_gioi_test(seed=7, giu_lai=4, thoc_moi_nguoi=500)
    ids = _ids_song(w)
    w.chinh_quyen = ChinhQuyen(truong_lang=ids[0], nhiem_ky_den=999)
    kh = {aid: KeHoach(id=aid) for aid in ids}
    kh[ids[1]].ban_hanh_luat = {"loai": "thue", "suat": 0.4}  # không phải trưởng làng
    politics.buoc_chinh_quyen(w, kh)
    assert w.chinh_quyen.thue_suat == 0.0  # luật của người thường vô hiệu


# ------------------------------------------------------------------ (c) bạo động


def _dung_bat_binh_dang(seed: int, n: int = 10):
    """Thế giới n người lớn: 1 người CỰC giàu, còn lại nghèo → Gini rất cao."""
    w = the_gioi_test(seed=seed, giu_lai=n, thoc_moi_nguoi=10)
    ids = _ids_song(w)
    giau = ids[-1]
    w.ledger.sinh(giau, "thoc", 100000.0, "khoi_tao", "test cực giàu", 0)
    return w, ids, giau


def test_bao_dong_kich_hoat_khi_du_dieu_kien():
    w, ids, giau = _dung_bat_binh_dang(seed=9)
    kh = {aid: KeHoach(id=aid, bao_dong=True) for aid in ids}  # cả làng bạo động
    tong_truoc = w.ledger.tong_tai_san("thoc")
    giau_truoc = w.ledger.so_du(giau, "thoc")
    politics.buoc_bao_dong(w, kh)
    assert abs(w.ledger.tong_tai_san("thoc") - tong_truoc) < 1e-6  # sung công CÂN
    assert w.ledger.so_du(giau, "thoc") < giau_truoc  # người giàu bị sung công
    assert w.ledger.so_du(CONG_QUY, "thoc") < 1e-6  # chia lại hết


def test_bao_dong_khong_kich_hoat_khi_thieu_so_dong():
    w, ids, giau = _dung_bat_binh_dang(seed=10)
    kh = {aid: KeHoach(id=aid) for aid in ids}
    kh[ids[0]].bao_dong = True  # chỉ 1 người < 30% → không thành
    giau_truoc = w.ledger.so_du(giau, "thoc")
    tong_truoc = w.ledger.tong_tai_san("thoc")
    politics.buoc_bao_dong(w, kh)
    assert w.ledger.so_du(giau, "thoc") == giau_truoc  # KHÔNG ai bị sung công
    assert abs(w.ledger.tong_tai_san("thoc") - tong_truoc) < 1e-9


def test_bao_dong_khong_kich_hoat_khi_gini_thap():
    """Của cải đều nhau (Gini≈0) dù cả làng bạo động → không sung công."""
    w = the_gioi_test(seed=11, giu_lai=10, thoc_moi_nguoi=1000)
    ids = _ids_song(w)
    kh = {aid: KeHoach(id=aid, bao_dong=True) for aid in ids}
    truoc = {aid: w.ledger.so_du(aid, "thoc") for aid in ids}
    politics.buoc_bao_dong(w, kh)
    for aid in ids:
        assert w.ledger.so_du(aid, "thoc") == truoc[aid]


# ------------------------------------------------------------------ (d) hối lộ


def test_hoi_lo_la_chuyen_can():
    w = the_gioi_test(seed=13, giu_lai=3, thoc_moi_nguoi=500)
    ids = _ids_song(w)
    briber, bribee = ids[0], ids[1]
    kh = {aid: KeHoach(id=aid) for aid in ids}
    kh[briber].hoi_lo = (bribee, 100.0)
    tong_truoc = w.ledger.tong_tai_san("thoc")
    b0 = w.ledger.so_du(briber, "thoc")
    r0 = w.ledger.so_du(bribee, "thoc")
    politics.buoc_chinh_quyen(w, kh)
    assert abs(w.ledger.so_du(briber, "thoc") - (b0 - 100)) < 1e-9
    assert abs(w.ledger.so_du(bribee, "thoc") - (r0 + 100)) < 1e-9
    assert abs(w.ledger.tong_tai_san("thoc") - tong_truoc) < 1e-9  # không sinh/hủy
    assert w.uy_tin(briber, bribee) != 0.0  # có vun quan hệ (không ép ban ơn)


# ------------------------------------------------------------- nghiệp đoàn/đình công


def test_dinh_cong_hoan_gop_cong_khong_vi_pham():
    """Thợ trong nghiệp đoàn đình công → hợp đồng góp công KHÔNG bị giao, KHÔNG vi phạm."""
    from engine import contracts
    from engine.contracts import ClauseGopCong, HopDong

    w = the_gioi_test(seed=15, giu_lai=2, thoc_moi_nguoi=500)
    ids = _ids_song(w)
    tho, chu = ids[0], ids[1]
    hd = HopDong(id="HDT", cac_ben=[tho, chu], tick_ky=0,
                 dieu_khoan=[ClauseGopCong(tu=tho, den=chu, so_cong_moi_tick=30)])
    w.hop_dong["HDT"] = hd
    # thợ đình công tick này
    w.chinh_quyen = ChinhQuyen(nghiep_doan={tho}, dinh_cong_tick={tho})
    # cấp công cho thợ để nếu KHÔNG đình công thì góp được
    w.ledger.sinh(tho, "cong", 60.0, "sinh_cong", "test", w.tick)
    contracts.gop_cong_dau_san_xuat(w)
    assert w.ledger.so_du(chu, "cong") == 0.0  # không giao công (đình công)
    assert hd.trang_thai == "hieu_luc"  # KHÔNG bị dán vi phạm
    # dọn công để boc_hoi/audit không vướng ở test khác (công của thợ vẫn còn)
    w.ledger.huy(tho, "cong", w.ledger.so_du(tho, "cong"), "boc_hoi", "dọn", w.tick)
