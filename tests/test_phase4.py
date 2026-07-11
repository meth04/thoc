"""Phase 4 — kịch bản định hướng (a)–(e): exercise cơ chế, không ép kết quả run tự do."""

from __future__ import annotations

import pytest

from engine.contracts import (
    ClauseChuyenGiaoDinhKy,
    ClauseChuyenGiaoMotLan,
    ClauseDieuKienSuKien,
    ClauseGopCong,
    ClauseHoanTraTheoYeuCau,
    HopDong,
)
from engine.entities import co_dong_cua, lap_phap_nhan
from engine.intents import KeHoach
from engine.market import Lenh, phien_cho
from engine.research import Blueprint
from observatory.observer import nhan_dinh_che
from tests.helpers import cap_ruong, chay_tick, mind_tinh, the_gioi_test


def ky(w, hd: HopDong) -> HopDong:
    from engine.board import _ky_hop_dong

    assert _ky_hop_dong(w, hd)
    return w.hop_dong[hd.id]


def test_a_entity_50_30_20_chia_loi_nhuan_va_ban_co_phan():
    """(a) lập entity 50/30/20, 2 hợp đồng góp công, chia lợi nhuận đúng kg, bán 20%."""
    w = the_gioi_test(seed=41, giu_lai=6, thoc_moi_nguoi=3000)
    a, b, c, d, e, f = sorted(x for x, ag in w.agents.items() if ag.con_song)
    # vốn góp người khác phải do CHÍNH HỌ chuyển (đồng thuận) — intent một chiều
    # chỉ được rút túi người lập (chống LLM tiêu tiền người khác, DECISIONS.md)
    eid = lap_phap_nhan(w, a, "Hội Ba Nhà", {a: 50.0, b: 30.0, c: 20.0},
                        {a: {"thoc": 500}})
    assert eid is not None
    w.ledger.chuyen(b, eid, "thoc", 300, "b tự góp vốn (đồng thuận)", w.tick)
    w.ledger.chuyen(c, eid, "thoc", 200, "c tự góp vốn (đồng thuận)", w.tick)
    cd = co_dong_cua(w, eid)
    assert cd[a] == pytest.approx(50) and cd[b] == pytest.approx(30)
    assert cd[c] == pytest.approx(20)
    assert w.ledger.so_du(eid, "thoc") == pytest.approx(1000)

    # 2 hợp đồng góp công vào entity
    for nv in (d, e):
        ky(w, HopDong(cac_ben=[nv, eid], hinh_thuc="mieng", thoi_han=8, dieu_khoan=[
            ClauseGopCong(tu=nv, den=eid, so_cong_moi_tick=100.0),
            ClauseChuyenGiaoDinhKy(tu=eid, den=nv, tai_san="thoc", so_luong=50.0,
                                   moi_n_tick=1),
        ]))
    # bơm "lợi nhuận" (nguồn gặt) để vượt đệm lưu động 4000 → chia đúng cổ phần
    w.ledger.sinh(eid, "thoc", 5000.0, "gat", "fixture lợi nhuận", w.tick)
    truoc = {x: w.ledger.so_du(x, "thoc") for x in (a, b, c)}
    w.tick += 2  # tick chẵn (mùa khô) để chia
    from engine.entities import chia_loi_nhuan_dinh_ky

    chia_loi_nhuan_dinh_ky(w)
    du = 6000 - 4000  # đệm 4000
    assert w.ledger.so_du(a, "thoc") - truoc[a] == pytest.approx(du * 0.5)
    assert w.ledger.so_du(b, "thoc") - truoc[b] == pytest.approx(du * 0.3)
    assert w.ledger.so_du(c, "thoc") - truoc[c] == pytest.approx(du * 0.2)

    # cổ đông b bán 20% trên chợ → sang tên đúng
    kl = phien_cho(w, [
        Lenh(b, "ban", f"co_phan:{eid}", 20.0, 10.0),
        Lenh(f, "mua", f"co_phan:{eid}", 20.0, 12.0),
    ])
    assert kl == pytest.approx(20.0)
    cd2 = co_dong_cua(w, eid)
    assert cd2[b] == pytest.approx(10) and cd2[f] == pytest.approx(20)


def test_b_gui_rut_nhan_ngan_hang_ep_rut_thanh_ly_pro_rata():
    """(b) 5 hợp đồng gửi-rút → nhãn ngân hàng; ép rút vượt dự trữ → thanh lý pro-rata."""
    w = the_gioi_test(seed=43, giu_lai=6, thoc_moi_nguoi=3000)
    ids = sorted(x for x, ag in w.agents.items() if ag.con_song)
    chu, *nguoi_gui = ids
    eid = lap_phap_nhan(w, chu, "Nhà Giữ Thóc", {chu: 100.0}, {chu: {"thoc": 100}})
    hd_ids = []
    for ng in nguoi_gui:
        hd = ky(w, HopDong(cac_ben=[ng, eid], hinh_thuc="mieng", thoi_han=None,
                           bao_truoc=2, dieu_khoan=[
            ClauseChuyenGiaoMotLan(tu=ng, den=eid, tai_san="thoc", so_luong=400,
                                   tai="ky_ket"),
            ClauseHoanTraTheoYeuCau(tu=eid, den=ng, tai_san="thoc",
                                    tran_rut_moi_tick=400.0),
        ]))
        hd_ids.append(hd.id)
    assert w.ledger.so_du(eid, "thoc") == pytest.approx(100 + 5 * 400)
    # observatory dán nhãn ngân hàng (nghĩa vụ ≥1500 từ ≥5 chủ nợ)
    nhan = nhan_dinh_che(w)
    assert eid in nhan["ngan_hang"]

    # entity đem thóc đi "đầu tư" (fixture đốt qua luồng hợp lệ) → dự trữ mỏng
    w.ledger.huy(eid, "thoc", 1900.0, "an", "fixture đầu tư kẹt", w.tick)
    con_lai = w.ledger.so_du(eid, "thoc")  # 200
    # ép rút đồng loạt 400/người — vượt xa dự trữ → vi phạm hàng loạt
    ke_hoach = {w.tick + 1: {
        ng: KeHoach(id=ng, yeu_cau_rut={hid: 400.0})
        for ng, hid in zip(nguoi_gui, hd_ids, strict=True)
    }}
    tong_truoc = {ng: w.ledger.so_du(ng, "thoc") for ng in nguoi_gui}
    chay_tick(w, mind_tinh(ke_hoach), 1)
    # nhận từ entity = đảo ngược hao kho (×0.97) + ăn (−90) trong tick
    da_tra = sum(
        (w.ledger.so_du(ng, "thoc") + 90.0) / 0.97 - tong_truoc[ng] for ng in nguoi_gui
    )
    assert da_tra >= con_lai - 1.0  # toàn bộ dự trữ còn lại về tay người gửi
    assert not w.entities[eid].con_hoat_dong, "entity mất khả năng thanh toán phải bị thanh lý"
    vi_pham = [h for h in w.hop_dong_xong.values() if h.trang_thai == "vi_pham"]
    assert vi_pham, "phải có vi phạm hàng loạt được ghi nhận"
    assert any(m["ten"] == "mo_tip_gui_rut_dau" for m in w.milestones)


def test_c_may_va_entity_nang_suat_hon_ho_tu_canh_nhan_xuong():
    """(c) blueprint máy → entity 5 công nhân có năng suất/đầu người CAO HƠN hộ tự canh."""
    w = the_gioi_test(seed=45, giu_lai=7, thoc_moi_nguoi=3000)
    ids = sorted(x for x, ag in w.agents.items() if ag.con_song)
    chu, doi_chung, *tho = ids  # 5 thợ
    eid = lap_phap_nhan(w, chu, "Xưởng Đồng Tâm", {chu: 100.0}, {chu: {"thoc": 2500}})
    # blueprint máy móc mạnh (fixture đặt độ lớn — bình thường engine rút)
    w._next_bp += 1
    w.blueprints["BPX"] = Blueprint(id="BPX", linh_vuc="cong_cu_may_moc", do_lon=1.5,
                                    ten="Guồng nước", chu=eid, tick_sinh=0)
    w.ledger.sinh(eid, "may", 1.0, "che_tac", "fixture máy", 0)
    # 20 thửa màu mỡ đồng nhất cho entity, 3 thửa cho hộ đối chứng
    thua_e = cap_ruong(w, eid, 20)
    thua_h = cap_ruong(w, doi_chung, 3)
    for pid in thua_e + thua_h:
        w.parcels[pid].mau_mo = 1.0
    for nv in tho:
        ky(w, HopDong(cac_ben=[nv, eid], hinh_thuc="mieng", thoi_han=8, dieu_khoan=[
            ClauseGopCong(tu=nv, den=eid, so_cong_moi_tick=100.0),
            ClauseChuyenGiaoDinhKy(tu=eid, den=nv, tai_san="thoc", so_luong=220.0,
                                   moi_n_tick=1),
        ]))
    # nhãn xưởng: entity ≥3 hợp đồng góp công
    nhan = nhan_dinh_che(w)
    assert eid in nhan["xuong"]

    # một mùa mưa: entity canh 16 thửa bằng 500 công thuê ×2 (máy); hộ canh 3
    w.tick += 0
    tick_mua = w.tick + 1 if (w.tick + 1) % 2 == 1 else w.tick + 2
    ke_hoach = {tick_mua: {
        eid: KeHoach(id=eid, canh_thua=thua_e),
        doi_chung: KeHoach(id=doi_chung, canh_thua=thua_h),
    }}
    mind = mind_tinh(ke_hoach)
    while w.tick < tick_mua:
        chay_tick(w, mind, 1)
    gat_e = sum(kg for pid, (ai, kg) in w.gat_tick.items() if ai == eid)
    gat_h = sum(kg for pid, (ai, kg) in w.gat_tick.items() if ai == doi_chung)
    nang_suat_entity = gat_e / 5  # trên đầu công nhân
    assert gat_h > 0
    assert nang_suat_entity > gat_h, (
        f"xưởng máy {nang_suat_entity:.0f}kg/người phải vượt hộ tự canh {gat_h:.0f}kg"
    )


def test_d_hang_moi_duoc_che_mua_ban_hieu_ung_dung():
    """(d) blueprint che_bien → hàng mới có tên, mua bán được, hiệu ứng tiện nghi đúng."""
    w = the_gioi_test(seed=47, giu_lai=2, thoc_moi_nguoi=3000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    w._next_bp += 1
    bp = Blueprint(id="BPV", linh_vuc="che_bien", do_lon=0.1, ten="Nghề dệt vải",
                   chu=a, tick_sinh=0, hang_moi="vai_tho",
                   recipe={"go": 1.0, "cong": 20.0}, hieu_ung="tien_nghi",
                   hieu_ung_do_lon=0.2)
    w.blueprints["BPV"] = bp
    w.ten_hang["vai_tho"] = "Vải thô Nghề dệt"
    w.ledger.flows.dang_ky("vai_tho", "che_tac", "nguon")
    w.ledger.flows.dang_ky("vai_tho", "tieu_dung", "sink")
    w.ledger.sinh(a, "go", 5.0, "khai_thac", "fixture", 0)

    # a chế 3 tấm vải, bán 1 cho b (b tiêu dùng NGAY trong tick — tiện nghi)
    ke_hoach = {
        w.tick + 1: {a: KeHoach(id=a, che_hang={"vai_tho": 3})},
        w.tick + 2: {
            a: KeHoach(id=a, dat_lenh=[Lenh(a, "ban", "vai_tho", 1.0, 30.0)]),
            b: KeHoach(id=b, dat_lenh=[Lenh(b, "mua", "vai_tho", 1.0, 35.0)]),
        },
    }
    mind = mind_tinh(ke_hoach)
    chay_tick(w, mind, 1)
    assert w.ledger.so_du(a, "vai_tho") >= 2.0  # 3 chế, 1 có thể đã tiêu dùng tiện nghi
    w.agents[b].health = 50.0
    thoc_a_truoc = w.ledger.so_du(a, "thoc")
    chay_tick(w, mind, 1)
    # bán được: a nhận ~32.5 thóc (giá giữa 30-35); b đã tiêu dùng vải ngay
    assert w.ledger.so_du(a, "thoc") > (thoc_a_truoc + 25) * 0.97 - 90
    assert w.ledger.so_du(b, "vai_tho") == pytest.approx(0.0)
    # hiệu ứng tiện nghi đúng: +hieu_ung_do_lon×10 cộng thêm vào +10 ăn no
    assert w.agents[b].health == pytest.approx(50 + 10 + 0.2 * 10, abs=1e-6)


def test_e_bao_hiem_chi_tra_khi_han_va_nhan_bao_hiem():
    """(e) dieu_kien_su_kien hạn lũ → bồi thường đúng; đủ 5 hợp đồng → nhãn bảo hiểm."""
    w = the_gioi_test(seed=49, giu_lai=6, thoc_moi_nguoi=3000)
    ids = sorted(x for x, ag in w.agents.items() if ag.con_song)
    nha_bh, *nong_dan = ids
    for nd in nong_dan:
        ky(w, HopDong(cac_ben=[nd, nha_bh], hinh_thuc="mieng", thoi_han=8, dieu_khoan=[
            ClauseChuyenGiaoDinhKy(tu=nd, den=nha_bh, tai_san="thoc", so_luong=10.0,
                                   moi_n_tick=1),
            ClauseDieuKienSuKien(neu={"loai": "han_lu"},
                                 thi=ClauseChuyenGiaoMotLan(tu=nha_bh, den=nd,
                                                            tai_san="thoc", so_luong=250,
                                                            tai="ky_ket")),
        ]))
    nhan = nhan_dinh_che(w)
    assert nha_bh in nhan["bao_hiem"], "bán ≥5 hợp đồng sự kiện → nhãn bảo hiểm"

    # năm tới hạn lũ — mọi nông dân được bồi thường đúng 250 (trừ phí 10 đã nộp)
    nam_sau = (w.tick + 1) // 2
    w.thoi_tiet_nam[nam_sau] = "han_lu"
    truoc = {nd: w.ledger.so_du(nd, "thoc") for nd in nong_dan}
    chay_tick(w, mind_tinh({}), 1)
    for nd in nong_dan:
        delta_hd = -10.0 + 250.0  # nộp phí kỳ 1 rồi nhận bồi thường
        ky_vong = (truoc[nd] + delta_hd) * 0.97 - 90.0  # hao kho + ăn
        assert w.ledger.so_du(nd, "thoc") == pytest.approx(ky_vong, abs=1e-6)
