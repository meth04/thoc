"""Test sổ kép + FlowRegistry + audit — viết TRƯỚC engine theo kỷ luật kiểm thử."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine.audit import LoiBaoToan, kiem_toan
from engine.ledger import ButToan, Ledger, LoiSoKep, Transaction


def lam_ledger() -> Ledger:
    led = Ledger()
    led.flows.dang_ky("thoc", "gat", "nguon")
    led.flows.dang_ky("thoc", "an", "sink")
    led.flows.dang_ky("thoc", "hao_kho", "sink")
    led.flows.dang_ky("thoc", "giong", "sink")
    led.flows.dang_ky("go", "khai_thac", "nguon")
    return led


# ---------- đơn vị cơ bản ----------


def test_chuyen_can_no_co():
    led = lam_ledger()
    led.sinh("A1", "thoc", 100, "gat", "gặt vụ 1")
    led.chuyen("A1", "A2", "thoc", 40, "bán thóc")
    assert led.so_du("A1", "thoc") == pytest.approx(60)
    assert led.so_du("A2", "thoc") == pytest.approx(40)
    assert led.tong_tai_san("thoc") == pytest.approx(100)
    kiem_toan(led)


def test_khong_am_so_du():
    led = lam_ledger()
    led.sinh("A1", "thoc", 10, "gat", "gặt")
    with pytest.raises(LoiSoKep):
        led.chuyen("A1", "A2", "thoc", 11, "bán quá tay")
    # thất bại nguyên tử — không thay đổi gì
    assert led.so_du("A1", "thoc") == pytest.approx(10)
    assert led.so_du("A2", "thoc") == pytest.approx(0)


def test_transaction_khong_can_bi_tu_choi():
    led = lam_ledger()
    led.sinh("A1", "thoc", 100, "gat", "gặt")
    with pytest.raises(LoiSoKep):
        led.ap_dung(
            Transaction(
                tick=0,
                ly_do="lệch sổ",
                but_toan=(ButToan("A1", "thoc", -30), ButToan("A2", "thoc", +29)),
            )
        )


def test_luong_chua_dang_ky_bi_chan():
    led = lam_ledger()
    with pytest.raises(LoiSoKep):
        led.sinh("A1", "thoc", 50, "in_tien", "luồng lậu")
    with pytest.raises(LoiSoKep):
        led.sinh("A1", "vang", 50, "gat", "tài sản lạ")
    led.sinh("A1", "thoc", 50, "gat", "gặt")
    with pytest.raises(LoiSoKep):
        led.huy("A1", "thoc", 10, "dot_choi", "sink lậu")


def test_no_la_object_rieng_khong_phai_so_am():
    """Điều luật #2: không thể biểu diễn nợ bằng số dư âm."""
    led = lam_ledger()
    with pytest.raises(LoiSoKep):
        led.ap_dung(
            Transaction(
                tick=0,
                ly_do="cho vay bằng số âm",
                but_toan=(ButToan("A1", "thoc", -50), ButToan("A2", "thoc", +50)),
            )
        )


def test_transaction_nhieu_chan_nguyen_tu():
    """Đổi thóc lấy gỗ trong MỘT transaction — cân từng tài sản độc lập."""
    led = lam_ledger()
    led.sinh("A1", "thoc", 100, "gat", "gặt")
    led.sinh("A2", "go", 5, "khai_thac", "đốn gỗ")
    led.ap_dung(
        Transaction(
            tick=1,
            ly_do="đổi 60 thóc lấy 3 gỗ",
            but_toan=(
                ButToan("A1", "thoc", -60),
                ButToan("A2", "thoc", +60),
                ButToan("A2", "go", -3),
                ButToan("A1", "go", +3),
            ),
        )
    )
    assert led.so_du("A1", "go") == pytest.approx(3)
    assert led.so_du("A2", "thoc") == pytest.approx(60)
    kiem_toan(led)


# ---------- audit bắt luồng lậu ----------


def test_audit_bat_luong_lau_co_tinh():
    """Cố tình bơm tài sản NGOÀI sổ (mutate trực tiếp) → audit phải bắt được."""
    led = lam_ledger()
    led.sinh("A1", "thoc", 100, "gat", "gặt")
    kiem_toan(led)  # sạch trước khi cài lậu
    led._so_du[("A1", "thoc")] += 7.0  # luồng lậu: thóc từ hư không
    with pytest.raises(LoiBaoToan):
        kiem_toan(led)


def test_audit_bat_sinh_huy_ghi_thieu():
    """Hủy tài sản ngoài sổ (mutate trực tiếp) cũng bị bắt."""
    led = lam_ledger()
    led.sinh("A1", "thoc", 100, "gat", "gặt")
    led._so_du[("A1", "thoc")] -= 30.0  # ăn vụng không ghi sổ
    with pytest.raises(LoiBaoToan):
        kiem_toan(led)


# ---------- property-based: chuỗi transaction ngẫu nhiên ----------


@st.composite
def kich_ban(draw):
    """Chuỗi thao tác ngẫu nhiên: sinh/chuyển/hủy giữa 4 chủ thể, 2 tài sản."""
    n = draw(st.integers(min_value=1, max_value=60))
    ops = []
    for _ in range(n):
        loai = draw(st.sampled_from(["sinh", "chuyen", "huy"]))
        tai_san = draw(st.sampled_from(["thoc", "go"]))
        a = draw(st.sampled_from(["A1", "A2", "A3", "A4"]))
        b = draw(st.sampled_from(["A1", "A2", "A3", "A4"]))
        q = draw(st.floats(min_value=0.0, max_value=500.0, allow_nan=False))
        ops.append((loai, tai_san, a, b, q))
    return ops


@settings(max_examples=200, deadline=None)
@given(kich_ban())
def test_property_khong_bao_gio_am_va_luon_can(ops):
    led = lam_ledger()
    for loai, tai_san, a, b, q in ops:
        try:
            if loai == "sinh":
                luong = "gat" if tai_san == "thoc" else "khai_thac"
                led.sinh(a, tai_san, q, luong, "sinh ngẫu nhiên")
            elif loai == "chuyen":
                led.chuyen(a, b, tai_san, q, "chuyển ngẫu nhiên")
            else:
                if tai_san == "thoc":
                    led.huy(a, tai_san, q, "an", "hủy ngẫu nhiên")
                else:
                    raise LoiSoKep("gỗ chưa có sink")
        except LoiSoKep:
            pass  # từ chối hợp lệ (thiếu số dư / luồng chưa đăng ký) — không được đổi state
        # BẤT BIẾN sau mỗi bước: không âm, tổng khớp registry
        for (_, _ts), v in led._so_du.items():
            assert v >= 0
        kiem_toan(led)


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["A1", "A2", "A3"]),
            st.sampled_from(["A1", "A2", "A3"]),
            st.floats(min_value=0, max_value=100, allow_nan=False),
        ),
        max_size=30,
    )
)
def test_property_tong_bat_bien_qua_chuyen(cap):
    """Chuyển nội bộ thuần túy không bao giờ đổi tổng tài sản."""
    led = lam_ledger()
    led.sinh("A1", "thoc", 1000, "gat", "vốn đầu")
    for tu, den, q in cap:
        try:
            led.chuyen(tu, den, "thoc", q, "chuyển")
        except LoiSoKep:
            pass
    assert led.tong_tai_san("thoc") == pytest.approx(1000)
    kiem_toan(led)
