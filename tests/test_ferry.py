"""ADR 0005 Phase B/C — topology-movement + đò-dịch-vụ (thuyền + phí + qua_song).

Bất biến then chốt (điều luật #1/#4):
- OFF (mặc định): mọi code-path đò no-op ⇒ world_hash + hành vi legacy y nguyên.
- ON: không đò ⇒ KHÔNG qua sông (kẹt bờ); có đò + trả thóc ⇒ qua được, phí vào ledger
  chủ đò (cân, không mint), capacity giới hạn, thuyền hao mòn; audit xanh; tất định.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine import audit, spatial
from engine.config import load_config
from engine.intents import KeHoach
from engine.market import Lenh, phien_cho
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi

OVERLAY = (
    Path(__file__).resolve().parents[1]
    / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
)


def _on(seed: int = 3):
    return tao_the_gioi(load_config(overlays=[OVERLAY]), seed)


def _off(seed: int = 3):
    return tao_the_gioi(load_config(), seed)


def _bo_khac(w, aid: str) -> str:
    """Bờ đối diện nơi ``aid`` cư trú (đích qua sông hợp lệ)."""
    return "hoang" if spatial._bo_cua(w, aid) == "dan_cu" else "dan_cu"


def _cap_thuyen(w, aid: str) -> None:
    """Cấp 1 thuyền qua flow đã đăng ký (kế toán như đóng thật, audit cân)."""
    w.ledger.sinh(aid, "thuyen", 1.0, "dong_thuyen", "test", w.tick)


# --------------------------------------------------------------------------- #
#  OFF = legacy: đò no-op, hash bất biến                                         #
# --------------------------------------------------------------------------- #
def test_off_ferry_hoan_toan_no_op():
    """OFF: dù có thuyền + rao_do + qua_song, buoc_qua_song KHÔNG làm gì (gated)."""
    w = _off()
    a, b = sorted(w.agents)[:2]
    _cap_thuyen(w, a)  # OFF vẫn cho giữ tài sản, nhưng đò không chạy
    thoc_b0 = w.ledger.so_du(b, "thoc")
    ke = {a: KeHoach(id=a, rao_do=(5.0, "thoc")),
          b: KeHoach(id=b, qua_song=("hoang", "thoc", 5.0))}
    spatial.buoc_qua_song(w, ke)
    assert w.ben_kia_tick == set()
    assert w.ledger.so_du(b, "thoc") == thoc_b0  # không thu phí
    assert spatial._bo_cua(w, b) is None          # OFF ⇒ không phân bờ
    assert spatial.co_the_o_bo(w, b, "hoang") is True  # OFF ⇒ không rào


def test_off_hash_tat_dinh_qua_nhieu_tick():
    """OFF: 2 run rulebot cùng seed vẫn cùng world_hash sau nhiều tick (đò không phá)."""
    from minds.policies import tao_policy

    def _run():
        w = _off(41)
        mind = tao_policy("rulebot")
        tong = len(w.parcels)
        for _ in range(6):
            chay_mot_tick(w, mind, tong)
        return w.world_hash()

    assert _run() == _run()


# --------------------------------------------------------------------------- #
#  ON: không đò ⇒ kẹt bờ                                                         #
# --------------------------------------------------------------------------- #
def test_on_khong_do_khong_qua_song():
    """ON: khách xin qua nhưng KHÔNG chủ đò nào ⇒ không ai qua; kẹt bờ cư trú."""
    w = _on()
    b = sorted(w.agents)[1]
    den = _bo_khac(w, b)
    ke = {b: KeHoach(id=b, qua_song=(den, "thoc", 5.0))}
    spatial.buoc_qua_song(w, ke)
    assert b not in w.ben_kia_tick
    assert spatial.co_the_o_bo(w, b, den) is False  # vẫn không tới được bờ kia


# --------------------------------------------------------------------------- #
#  ON: có đò + trả thóc ⇒ qua được, phí vào ledger chủ đò, audit xanh            #
# --------------------------------------------------------------------------- #
def test_on_co_do_tra_thoc_qua_duoc():
    w = _on()
    op, kh = sorted(w.agents)[:2]
    _cap_thuyen(w, op)
    den = _bo_khac(w, kh)
    thoc_op0, thoc_k0 = w.ledger.so_du(op, "thoc"), w.ledger.so_du(kh, "thoc")
    ke = {op: KeHoach(id=op, rao_do=(5.0, "thoc")),
          kh: KeHoach(id=kh, qua_song=(den, "thoc", 5.0))}
    spatial.buoc_qua_song(w, ke)
    assert kh in w.ben_kia_tick
    assert spatial.co_the_o_bo(w, kh, den) is True
    assert w.ledger.so_du(op, "thoc") == thoc_op0 + 5.0   # phí vào chủ đò
    assert w.ledger.so_du(kh, "thoc") == thoc_k0 - 5.0     # khách trả, cân
    hao_mon = float(w.cfg.get("khong_gian.do.hao_mon_moi_tick_dung"))
    assert w.ledger.so_du(op, "thuyen") == pytest.approx(1.0 - hao_mon)
    audit.kiem_toan_the_gioi(w, len(w.parcels))            # bảo toàn xanh


def test_on_fare_thoc_truoc_khi_co_tien_te():
    """Phí trả bằng THÓC chạy dù nền kinh tế CHƯA có xu (M(xu)=0)."""
    w = _on()
    assert w.ledger.tong_tai_san("xu") == 0.0
    op, kh = sorted(w.agents)[:2]
    _cap_thuyen(w, op)
    den = _bo_khac(w, kh)
    ke = {op: KeHoach(id=op, rao_do=(3.0, "thoc")),
          kh: KeHoach(id=kh, qua_song=(den, "thoc", 3.0))}
    spatial.buoc_qua_song(w, ke)
    assert kh in w.ben_kia_tick


def test_on_thieu_phi_thi_ket_bo_khong_am_so():
    """Khách không đủ phí ⇒ không qua, sổ KHÔNG âm (suy kiệt hợp lệ)."""
    w = _on()
    op, kh = sorted(w.agents)[:2]
    _cap_thuyen(w, op)
    w.ledger.huy(kh, "thoc", w.ledger.so_du(kh, "thoc") - 2.0, "an", "làm nghèo", w.tick)
    den = _bo_khac(w, kh)
    ke = {op: KeHoach(id=op, rao_do=(5.0, "thoc")),
          kh: KeHoach(id=kh, qua_song=(den, "thoc", 5.0))}
    spatial.buoc_qua_song(w, ke)
    assert kh not in w.ben_kia_tick
    assert w.ledger.so_du(kh, "thoc") == pytest.approx(2.0)  # không bị trừ, không âm
    audit.kiem_toan_the_gioi(w, len(w.parcels))


def test_on_capacity_gioi_han_dung():
    """Chuyến chở ≤ capacity (config=4); khách dư kẹt bờ, chọn theo (phí, id) tất định."""
    w = _on()
    cap = int(w.cfg.get("khong_gian.do.khach_toi_da_moi_tick"))
    aids = sorted(w.agents)
    op = aids[0]
    khach = aids[1:1 + cap + 2]  # nhiều hơn capacity 2 người
    _cap_thuyen(w, op)
    den = _bo_khac(w, khach[0])
    ke = {op: KeHoach(id=op, rao_do=(4.0, "thoc"))}
    for k in khach:
        ke[k] = KeHoach(id=k, qua_song=(den, "thoc", 4.0))
    spatial.buoc_qua_song(w, ke)
    qua = [k for k in khach if k in w.ben_kia_tick]
    assert len(qua) == cap                       # đúng capacity
    assert qua == sorted(khach)[:cap]            # tất định: id nhỏ (đồng phí) qua trước
    audit.kiem_toan_the_gioi(w, len(w.parcels))


def test_on_chu_thuyen_tu_qua_mien_phi():
    """Chủ thuyền TỰ qua sông (sở hữu phương tiện) — không phí, thuyền hao mòn."""
    w = _on()
    a = sorted(w.agents)[0]
    _cap_thuyen(w, a)
    thoc0 = w.ledger.so_du(a, "thoc")
    den = _bo_khac(w, a)
    ke = {a: KeHoach(id=a, qua_song=(den, "thoc", 0.0))}
    spatial.buoc_qua_song(w, ke)
    assert a in w.ben_kia_tick
    assert w.ledger.so_du(a, "thoc") == thoc0          # miễn phí
    hao_mon = float(w.cfg.get("khong_gian.do.hao_mon_moi_tick_dung"))
    assert w.ledger.so_du(a, "thuyen") == pytest.approx(1.0 - hao_mon)


# --------------------------------------------------------------------------- #
#  ON: đóng thuyền (recipe công+gỗ nguyên tử)                                    #
# --------------------------------------------------------------------------- #
def test_on_dong_thuyen_recipe_nguyen_tu():
    w = _on()
    a = sorted(w.agents)[0]
    r = w.cfg.get("san_xuat.recipe.thuyen")
    w.ledger.sinh(a, "cong", float(r["cong"]) + 20, "sinh_cong", "test", w.tick)
    w.ledger.sinh(a, "go", float(r["go"]) + 3, "khai_thac", "test", w.tick)
    ke = {a: KeHoach(id=a, dong_thuyen=1)}
    spatial.buoc_qua_song(w, ke)
    assert w.ledger.so_du(a, "thuyen") == pytest.approx(1.0)
    assert w.ledger.so_du(a, "cong") == pytest.approx(20.0)  # trừ đúng recipe
    assert w.ledger.so_du(a, "go") == pytest.approx(3.0)
    audit.kiem_toan(w.ledger, w.tick)                        # flow thuyền cân


def test_on_dong_thuyen_thieu_thi_skip_nguyen_tu():
    """Thiếu gỗ ⇒ không đóng, KHÔNG mất công (nguyên tử)."""
    w = _on()
    a = sorted(w.agents)[0]
    r = w.cfg.get("san_xuat.recipe.thuyen")
    w.ledger.sinh(a, "cong", float(r["cong"]), "sinh_cong", "test", w.tick)  # đủ công, 0 gỗ
    ke = {a: KeHoach(id=a, dong_thuyen=1)}
    spatial.buoc_qua_song(w, ke)
    assert w.ledger.so_du(a, "thuyen") == 0.0
    assert w.ledger.so_du(a, "cong") == pytest.approx(float(r["cong"]))  # công còn nguyên


# --------------------------------------------------------------------------- #
#  ON: determinism (2 run cùng seed + overlay ⇒ cùng world_hash)                #
# --------------------------------------------------------------------------- #
def test_on_ferry_tat_dinh_hash():
    def _run():
        w = _on(11)
        op, kh = sorted(w.agents)[:2]
        _cap_thuyen(w, op)
        den = _bo_khac(w, kh)
        ke = {op: KeHoach(id=op, rao_do=(5.0, "thoc")),
              kh: KeHoach(id=kh, qua_song=(den, "thoc", 5.0))}
        spatial.buoc_qua_song(w, ke)
        return w.world_hash()

    assert _run() == _run()


def test_on_rulebot_tat_dinh():
    """ON scenario chạy rulebot 2 lần cùng seed ⇒ cùng hash (overlay không phá determinism)."""
    from minds.policies import tao_policy

    def _run():
        w = _on(41)
        mind = tao_policy("rulebot")
        tong = len(w.parcels)
        for _ in range(5):
            chay_mot_tick(w, mind, tong)
        return w.world_hash()

    assert _run() == _run()


# --------------------------------------------------------------------------- #
#  Phase B: chợ liên bờ bị chặn khi không đò (hàng kẹt bờ)                       #
# --------------------------------------------------------------------------- #
def _cu_tru_bo_hoang(w) -> str:
    """Cho agent đầu tiên cư trú bờ hoang: gán 1 thửa hoang làm nhà (chủ = agent)."""
    a = sorted(w.agents)[0]
    thua = next(p for p in w.parcels.values() if p.bo == "hoang" and p.loai != "song")
    thua.chu = a
    w.agents[a].nha_thua = thua.id
    assert spatial._bo_cua(w, a) == "hoang"
    return a


def test_on_cho_lien_bo_can_do():
    """Người bờ hoang bán ở chợ làng (bờ dân cư): không đò ⇒ hàng kẹt (lệnh bị bỏ)."""
    w = _on()
    ban = _cu_tru_bo_hoang(w)            # cư trú bờ hoang, làng 0 ở bờ dân cư
    mua = sorted(w.agents)[1]            # người bờ dân cư
    w.ledger.sinh(ban, "go", 10, "khai_thac", "test", w.tick)
    lenh = [Lenh(ban, "ban", "go", 5, 2.0), Lenh(mua, "mua", "go", 5, 2.0)]
    assert phien_cho(w, lenh) == 0.0                  # không khớp — hàng kẹt bờ hoang
    assert w.ledger.so_du(ban, "go") == pytest.approx(10.0)
    # cấp thuyền ⇒ tới được chợ bờ kia ⇒ khớp
    _cap_thuyen(w, ban)
    assert phien_cho(w, lenh) > 0.0
    assert w.ledger.so_du(ban, "go") == pytest.approx(5.0)


def test_on_cho_cung_bo_khong_bi_chan():
    """Hai người CÙNG bờ dân cư giao thương bình thường (không rào)."""
    w = _on()
    ban, mua = sorted(w.agents)[:2]      # cả hai cư trú bờ dân cư
    w.ledger.sinh(ban, "go", 10, "khai_thac", "test", w.tick)
    lenh = [Lenh(ban, "ban", "go", 5, 2.0), Lenh(mua, "mua", "go", 5, 2.0)]
    assert phien_cho(w, lenh) > 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
