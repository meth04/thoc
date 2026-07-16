"""Tối ưu gọi model với NHIỀU key (20-30): chọn key rảnh nhất, an toàn luồng, co giãn."""

from __future__ import annotations

import threading
import time

from engine.config import load_config
from minds.keypool import EnvKeys, KeyPool, key_hash
from minds.providers_real import GatewayReal
from minds.quota import QuotaCounter


def test_lay_key_tot_nhat_chon_ranh_nhat():
    pool = KeyPool([f"k{i}" for i in range(5)])
    tai = {"k0": 3.0, "k1": 1.0, "k2": 0.0, "k3": 5.0, "k4": 2.0}  # k2 rảnh nhất
    # điểm = headroom (rảnh) = -tải; chọn điểm cao nhất
    chon = pool.lay_key_tot_nhat(time.time(), lambda k: -tai[k])
    assert chon == "k2"


def test_lay_key_bo_qua_key_khong_dung_duoc():
    pool = KeyPool(["k0", "k1", "k2"])
    # k0,k1 cạn (None), chỉ k2 dùng được
    chon = pool.lay_key_tot_nhat(time.time(),
                                 lambda k: None if k in ("k0", "k1") else 1.0)
    assert chon == "k2"
    # tất cả cạn → None
    assert pool.lay_key_tot_nhat(time.time(), lambda k: None) is None


def test_key_cooldown_bi_loai():
    pool = KeyPool(["k0", "k1"], cooldown_goc_s=60.0)
    now = time.time()
    pool.bao_429("k0", now)  # k0 vào cooldown
    chon = pool.lay_key_tot_nhat(now, lambda k: 1.0)
    assert chon == "k1"  # k0 đang cooldown → bỏ


def test_cooldown_chan_tran_hoi_nhanh():
    """429 liên tiếp KHÔNG đẩy cooldown lên vô hạn — chặn trần để key hồi nhanh, không
    bị loại khỏi vòng quay hàng phút (nguyên nhân lệch tải trong run15 thật)."""
    pool = KeyPool(["k0"], cooldown_goc_s=45.0, cooldown_toi_da_s=90.0)
    now = 1000.0
    for _ in range(6):  # 6 lần 429 liên tiếp
        pool.bao_429("k0", now)
    ts = pool._keys[0]
    # lũy tiến 45,90,180,... nhưng chặn ở 90 → cooldown ≤ now+90 (không phải now+1440)
    assert ts.cooldown_den <= now + 90.0 + 1e-6
    assert pool.lay_key_tot_nhat(now + 91.0, lambda k: 1.0) == "k0"  # hồi sau 91s


def _env(n: int) -> EnvKeys:
    return EnvKeys(gemini_keys=[f"gkey_{i}" for i in range(n)],
                   nine_key="nk", nine_base="http://x/v1")


def test_gateway_chon_key_ranh_hon_khi_mot_key_da_dung():
    gw = GatewayReal(load_config(), _env(4), QuotaCounter(None))
    route = gw.routes_cua_tier("T0")[0]  # aistudio
    now = time.time()
    # Dồn physical starts lên gkey_0: RPM tính admission, không phải response thành công.
    for _ in range(3):
        assert gw.quota.nhan_slot_bat_dau(
            route.provider, route.model, key_hash("gkey_0"), route.rpm, route.rpd, now
        )
    chon = gw._chon_key_aistudio(route, now)
    assert chon is not None and chon != "gkey_0"  # chọn key rảnh hơn


def test_giu_cho_trai_deu_khi_chon_song_song():
    """30 lần chọn LIÊN TIẾP không release (mô phỏng 30 call ĐANG BAY cùng lúc) phải
    TRẢI ĐỀU nhờ giữ chỗ đang-bay — không dội 1 key (chống thundering-herd)."""
    from collections import Counter

    gw = GatewayReal(load_config(), _env(15), QuotaCounter(None))
    route = gw.routes_cua_tier("T0")[0]  # aistudio gemini-3.1-flash-lite, rpm=4/key
    now = time.time()
    chon = [gw._chon_key_aistudio(route, now) for _ in range(30)]
    chon = [key_hash(k) for k in chon if k]
    dem = Counter(chon)
    assert len(chon) == 30                 # 15 key × rpm 4 = 60 slot ≥ 30
    assert max(dem.values()) <= route.rpm  # KHÔNG key nào vượt RPM (trước đây 1 key ăn 28)
    assert len(dem) >= 8                    # trải ra ≥ 8 key thay vì dồn 1


def test_giai_phong_tra_slot():
    gw = GatewayReal(load_config(), _env(3), QuotaCounter(None))
    route = gw.routes_cua_tier("T0")[0]
    now = time.time()
    k = gw._chon_key_aistudio(route, now)
    assert gw._dang_bay[key_hash(k)] == 1
    gw._giai_phong(k)
    assert gw._dang_bay[key_hash(k)] == 0


def test_concurrency_co_gian_theo_so_key():
    cap = 48
    assert GatewayReal(load_config(), _env(2), QuotaCounter(None)).concurrency_de_xuat(cap) == 8
    assert GatewayReal(load_config(), _env(20), QuotaCounter(None)).concurrency_de_xuat(cap) == 44
    assert GatewayReal(load_config(), _env(30), QuotaCounter(None)).concurrency_de_xuat(cap) == cap


def test_keypool_an_toan_luong():
    """Nhiều thread cùng lấy key + báo 429 + báo ok — không crash, không hỏng trạng thái."""
    pool = KeyPool([f"k{i}" for i in range(8)])
    loi: list = []

    def chay():
        try:
            for _ in range(500):
                now = time.time()
                k = pool.lay_key_tot_nhat(now, lambda key: 1.0)
                if k:
                    pool.bao_429(k, now)
                    pool.bao_ok(k)
        except Exception as e:  # noqa: BLE001
            loi.append(e)

    ts = [threading.Thread(target=chay) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not loi
    assert pool.so_key() == 8
