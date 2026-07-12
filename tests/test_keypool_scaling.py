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


def _env(n: int) -> EnvKeys:
    return EnvKeys(gemini_keys=[f"gkey_{i}" for i in range(n)],
                   nine_key="nk", nine_base="http://x/v1")


def test_gateway_chon_key_ranh_hon_khi_mot_key_da_dung():
    gw = GatewayReal(load_config(), _env(4), QuotaCounter(None))
    route = gw.routes_cua_tier("T0")[0]  # aistudio
    now = time.time()
    # dồn tải lên gkey_0: ghi vài call → RPM cao → phải tránh nó
    for _ in range(3):
        gw.quota.ghi_call(route.provider, route.model, key_hash("gkey_0"), now)
    chon = gw._chon_key_aistudio(route, now)
    assert chon is not None and chon != "gkey_0"  # chọn key rảnh hơn


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
