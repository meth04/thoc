"""Contract engine: hypothesis trên executor + các kịch bản định hướng (a)–(d)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.contracts import (
    ClauseChiaSanLuong,
    ClauseChuyenGiaoDinhKy,
    ClauseChuyenGiaoMotLan,
    ClauseKhiPhaVo,
    ClauseQuyenSuDung,
    HopDong,
)
from engine.intents import KeHoach
from tests.helpers import cap_ruong, chay_tick, mind_tinh, the_gioi_test


def ky_truc_tiep(w, hd: HopDong) -> HopDong:
    """Ký hợp đồng thẳng (bỏ qua bảng rao) cho fixture."""
    from engine.board import _ky_hop_dong

    assert _ky_hop_dong(w, hd), "fixture: hợp đồng phải ký được"
    return w.hop_dong[hd.id]


# ---------------------------------------------------------- hypothesis executor


@st.composite
def hop_dong_ngau_nhien(draw):
    """Hợp đồng gỗ ngẫu nhiên hợp lệ từ văn phạm (định kỳ / một lần / đáo hạn)."""
    n = draw(st.integers(1, 3))
    dieu_khoan = []
    for _ in range(n):
        kieu = draw(st.sampled_from(["dinh_ky", "ky_ket", "dao_han"]))
        tu, den = draw(st.sampled_from([("A", "B"), ("B", "A")]))
        sl = draw(st.floats(1.0, 80.0, allow_nan=False))
        if kieu == "dinh_ky":
            dieu_khoan.append(
                ClauseChuyenGiaoDinhKy(tu=tu, den=den, tai_san="go", so_luong=sl,
                                       moi_n_tick=draw(st.integers(1, 3)))
            )
        else:
            dieu_khoan.append(
                ClauseChuyenGiaoMotLan(tu=tu, den=den, tai_san="go", so_luong=sl, tai=kieu)
            )
    thoi_han = draw(st.integers(1, 5))
    go_a = draw(st.floats(0.0, 150.0, allow_nan=False))
    go_b = draw(st.floats(0.0, 150.0, allow_nan=False))
    return dieu_khoan, thoi_han, go_a, go_b


@settings(max_examples=60, deadline=None)
@given(hop_dong_ngau_nhien())
def test_property_executor_bao_toan_va_phat_hien_vi_pham(bo):
    dieu_khoan, thoi_han, go_a, go_b = bo
    w = the_gioi_test(seed=9, giu_lai=2, thoc_moi_nguoi=5000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    ten = {"A": a, "B": b}
    if go_a > 0:
        w.ledger.sinh(a, "go", go_a, "khai_thac", "fixture", 0)
    if go_b > 0:
        w.ledger.sinh(b, "go", go_b, "khai_thac", "fixture", 0)
    dk = []
    for c in dieu_khoan:
        c2 = c.model_copy()
        c2.tu, c2.den = ten[c.tu], ten[c.den]
        dk.append(c2)
    hd = HopDong(cac_ben=[a, b], hinh_thuc="mieng", thoi_han=thoi_han, dieu_khoan=dk)

    # oracle độc lập: mô phỏng chuyển giao gỗ để dự đoán tick vi phạm đầu tiên
    so_du = {a: go_a, b: go_b}
    tick_ky = w.tick  # ký trước khi chạy tick nào
    # các khoản ky_ket chạy NGAY khi ký — nếu hụt thì không ký được
    ky_duoc = True
    for c in dk:
        if c.loai == "chuyen_giao_mot_lan" and c.tai == "ky_ket":
            if so_du[c.tu] + 1e-9 >= c.so_luong:
                so_du[c.tu] -= c.so_luong
                so_du[c.den] += c.so_luong
            else:
                ky_duoc = False
                break

    from engine.board import _ky_hop_dong

    assert _ky_hop_dong(w, hd) == ky_duoc
    tong_go = w.ledger.tong_tai_san("go")

    tick_vi_pham_du_doan = None
    if ky_duoc:
        for tuoi in range(1, thoi_han + 1):
            if tick_vi_pham_du_doan is not None:
                break
            dao_han = tuoi >= thoi_han
            for c in dk:
                du = (
                    (c.loai == "chuyen_giao_dinh_ky" and tuoi % c.moi_n_tick == 0)
                    or (c.loai == "chuyen_giao_mot_lan" and c.tai == "dao_han" and dao_han)
                )
                if not du:
                    continue
                if so_du[c.tu] + 1e-9 >= c.so_luong:
                    so_du[c.tu] -= c.so_luong
                    so_du[c.den] += c.so_luong
                else:
                    tick_vi_pham_du_doan = tick_ky + tuoi
                    break

    mind = mind_tinh({})
    for _ in range(thoi_han + 1):
        chay_tick(w, mind, 1)  # audit chạy mỗi tick — vi phạm bảo toàn sẽ raise
        if ky_duoc and tick_vi_pham_du_doan == w.tick:
            assert w.tim_hop_dong(hd.id).trang_thai == "vi_pham", "vi phạm phải bị bắt đúng tick"
    assert w.ledger.tong_tai_san("go") == pytest.approx(tong_go)  # gỗ chỉ đổi chủ
    if ky_duoc and tick_vi_pham_du_doan is None:
        assert w.tim_hop_dong(hd.id).trang_thai == "hoan_thanh"


# ---------------------------------------------------------- kịch bản định hướng


def test_a_cay_re_chia_dung_tung_kg():
    """(a) quyền_sử_dụng + chia_sản 40%, 8 tick: chia đúng từng kg, xong đúng hạn."""
    w = the_gioi_test(seed=13, giu_lai=2, thoc_moi_nguoi=4000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    w.agents[a].tuoi_tick = w.agents[b].tuoi_tick = 36  # tre — tranh chet gia giua kich ban
    (pid,) = cap_ruong(w, a, 1)

    hd_mau = HopDong(
        cac_ben=[a, b], hinh_thuc="mieng", thoi_han=8,
        dieu_khoan=[
            ClauseQuyenSuDung(tai_san=f"thua:{pid}", tu=a, den=b),
            ClauseChiaSanLuong(nguon=f"thua:{pid}", ty_le=0.4, den=a),
        ],
    )
    # tick 1: A đề nghị đích danh B; tick 2: B chấp nhận (qua bảng rao thật)
    ke_hoach = {
        1: {a: KeHoach(id=a, de_nghi_hop_dong=[(hd_mau, b)])},
    }
    mind = mind_tinh(ke_hoach)
    chay_tick(w, mind, 1)
    dn_id = next(iter(w.bang_rao))
    ke_hoach[2] = {b: KeHoach(id=b, tra_loi_de_nghi={dn_id: "chap_nhan"})}
    chay_tick(w, mind, 1)
    hd = next(iter(w.hop_dong.values()))
    assert hd.trang_thai == "hieu_luc" and hd.tick_ky == 2

    # B canh thửa của A mỗi mùa mưa; đối chiếu phần chia từng kg
    for t in range(3, 11):
        kh_b = KeHoach(id=b, canh_thua=[pid] if t % 2 == 1 else [])
        ke_hoach[t] = {b: kh_b}
        thoc_a_truoc = w.ledger.so_du(a, "thoc")
        chay_tick(w, mind, 1)
        if t % 2 == 1:  # mùa mưa: B gặt, A nhận đúng 40% rồi mới hao kho + ăn
            nguoi_gat, kg = w.gat_tick[pid]
            assert nguoi_gat == b and kg > 0
            ky_vong = (thoc_a_truoc + 0.4 * kg) * 0.97 - 90.0
            assert w.ledger.so_du(a, "thoc") == pytest.approx(ky_vong, abs=1e-6)
    assert w.tim_hop_dong(hd.id).trang_thai == "hoan_thanh"  # đáo hạn đúng 8 tick


def test_b_vay_van_ban_the_chap_xiet_dung_gia_thua_hoan_lai():
    """(b) vay văn bản thế chấp đất → thiếu khi đáo hạn → xiết theo giá chợ, thừa hoàn."""
    w = the_gioi_test(seed=17, giu_lai=2, thoc_moi_nguoi=2000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    (pid,) = cap_ruong(w, a, 1)
    w.agents[a].e_bac = 1  # người soạn biết chữ
    # A chỉ còn 50 thóc — chắc chắn không trả nổi 390
    w.ledger.huy(a, "thoc", w.ledger.so_du(a, "thoc") - 50.0, "an", "fixture", 0)
    w.ghi_gia("dat", 500.0, 1.0)  # giá chợ gần nhất của đất
    w.thoi_tiet_nam.update({0: "han_lu", 1: "han_lu", 2: "han_lu"})  # mất mùa

    hd = ky_truc_tiep(w, HopDong(
        cac_ben=[a, b], hinh_thuc="van_ban", thoi_han=2, nguoi_soan=a,
        the_chap=[f"thua:{pid}"],
        dieu_khoan=[
            ClauseChuyenGiaoMotLan(tu=b, den=a, tai_san="thoc", so_luong=300, tai="ky_ket"),
            ClauseChuyenGiaoMotLan(tu=a, den=b, tai_san="thoc", so_luong=390, tai="dao_han"),
            ClauseKhiPhaVo(phat="xiet_the_chap"),
        ],
    ))
    assert w.ledger.so_du(a, "thoc") == pytest.approx(350)
    mind = mind_tinh({})
    chay_tick(w, mind, 1)
    thoc_a_truoc = w.ledger.so_du(a, "thoc")
    chay_tick(w, mind, 1)  # tick đáo hạn: vi phạm + xiết tại bước 7
    assert w.tim_hop_dong(hd.id).trang_thai == "vi_pham"
    assert w.parcels[pid].chu == b, "đất thế chấp phải về tay chủ nợ"
    # thừa hoàn lại: đất 500 > nợ 390 → hoàn 110 TRƯỚC hao kho + ăn
    ky_vong = (thoc_a_truoc + 110.0) * 0.97 - 90.0
    assert w.ledger.so_du(a, "thoc") == pytest.approx(ky_vong, abs=1e-6)


def test_c_vi_pham_mieng_chi_mat_uy_tin_va_tin_don():
    """(c) hợp đồng MIỆNG vi phạm → không xiết gì, chỉ uy tín giảm + tin đồn lan."""
    w = the_gioi_test(seed=19, giu_lai=3, thoc_moi_nguoi=2000)
    a, b, c = sorted(x for x, ag in w.agents.items() if ag.con_song)
    (pid,) = cap_ruong(w, a, 1)
    w.cong_quan_he(b, c, 1.0)  # C là chỗ quen của B — tin đồn sẽ lan tới C

    hd = ky_truc_tiep(w, HopDong(
        cac_ben=[a, b], hinh_thuc="mieng", thoi_han=4,
        dieu_khoan=[ClauseChuyenGiaoDinhKy(tu=a, den=b, tai_san="go", so_luong=100,
                                           moi_n_tick=1)],  # A không hề có gỗ
    ))
    uy_tin_ab_truoc = w.uy_tin(a, b)
    thoc_a_truoc = w.ledger.so_du(a, "thoc")
    chay_tick(w, mind_tinh({}), 1)
    assert w.tim_hop_dong(hd.id).trang_thai == "vi_pham"
    assert w.parcels[pid].chu == a, "miệng: KHÔNG xiết đất"
    assert w.ledger.so_du(a, "thoc") == pytest.approx(thoc_a_truoc * 0.97 - 90, abs=1e-6), \
        "miệng: không mất thóc ngoài ăn + hao kho"
    assert w.uy_tin(a, b) == pytest.approx(uy_tin_ab_truoc - 0.5)
    assert w.uy_tin(a, c) == pytest.approx(-0.1), "tin đồn lan tới người quen của nạn nhân"


def test_d_han_han_gia_thoc_tang():
    """(d) hạn hán/đói → giá thóc (đo bằng gỗ) phiên sau tăng ≥20% — rulebot tự phản ứng."""
    from minds.rulebot import quyet_dinh_tat_ca

    w = the_gioi_test(seed=23, giu_lai=2, thoc_moi_nguoi=2000)
    a, b = sorted(x for x, ag in w.agents.items() if ag.con_song)
    # cùng giới để rulebot không cưới nhau (hộ nhập một là hỏng kịch bản)
    w.agents[a].gioi_tinh = w.agents[b].gioi_tinh = "nam"
    w.agents[a].persona.tiet_kiem = 5
    w.agents[b].persona.tiet_kiem = 3  # B sẵn sàng bán thóc lấy gỗ
    w.ledger.sinh(a, "go", 200.0, "khai_thac", "fixture", 0)

    def dat_thoc(aid: str, muc: float) -> None:
        hien = w.ledger.so_du(aid, "thoc")
        if hien > muc:
            w.ledger.huy(aid, "thoc", hien - muc, "an", "fixture", w.tick)
        else:
            w.ledger.sinh(aid, "thoc", muc - hien, "khoi_tao", "fixture", w.tick)

    gia_phien: list[float] = []

    def gia_moi_nhat():
        ls = w.gia_lich_su.get("thoc/go")
        return ls[-1] if ls else None

    # giai đoạn 1: hơi đói (an ninh ~0.5) — chờ phiên khớp đầu tiên
    for _ in range(12):
        dat_thoc(a, 120.0)
        dat_thoc(b, 8000.0)
        truoc = gia_moi_nhat()
        chay_tick(w, quyet_dinh_tat_ca, 1)
        sau = gia_moi_nhat()
        if sau is not None and sau != truoc:
            gia_phien.append(sau[1])
            break
    assert gia_phien, "phải có phiên khớp thóc/gỗ ở giai đoạn hơi đói"

    # giai đoạn 2: hạn hán + kiệt lương (an ninh ~0) — giá phiên sau phải bật ≥20%
    nam_nay = (w.tick + 1) // 2
    for nam in range(nam_nay, nam_nay + 8):
        w.thoi_tiet_nam[nam] = "han_lu"
    for _ in range(12):
        dat_thoc(a, 10.0)
        dat_thoc(b, 8000.0)
        truoc = gia_moi_nhat()
        chay_tick(w, quyet_dinh_tat_ca, 1)
        sau = gia_moi_nhat()
        if sau is not None and sau != truoc:
            gia_phien.append(sau[1])
            break
    assert len(gia_phien) == 2, "phải có phiên khớp trong hạn hán"
    assert gia_phien[1] >= 1.2 * gia_phien[0], f"giá thóc phải tăng ≥20%: {gia_phien}"
