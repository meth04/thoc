"""Pipeline một tick (SPEC mục 6) — Phase 1: bỏ bước 4 (bảng rao), 6 (chợ), 7 (hợp đồng)."""

from __future__ import annotations

from collections.abc import Callable

from engine import audit, consumption, demography, education, metrics, production
from engine.intents import KeHoach
from engine.world import World

# Hàm minds: (world) → {agent_id: KeHoach}
MindFn = Callable[[World], dict[str, KeHoach]]


def chay_mot_tick(w: World, mind_fn: MindFn, tong_thua_ban_dau: int) -> dict:
    w.tick += 1

    # 1. bat_dau: tuổi +1 tick; thời tiết của năm được rút (lazy trong w.thoi_tiet)
    for a in w.agents.values():
        if a.con_song:
            a.tuoi_tick += 1
    loai_tt, _ = w.thoi_tiet(w.tick)
    if w.mua_mua():
        w.events.ghi(w.tick, "thoi_tiet", kieu=loai_tt)

    # 2+3. trigger/quyết định (Phase 1: rulebot quyết cho mọi người mỗi tick)
    ke_hoach = mind_fn(w)

    # 5. san_xuat: sinh công, canh tác, khai thác, chế tác, xây
    production.sinh_cong(w)
    production.thi_hanh_san_xuat(w, ke_hoach)

    # 8. tieu_dung_suc_khoe: hao kho, ăn, health, vô gia cư
    consumption.hao_hut_kho(w)
    consumption.an_va_suc_khoe(w)

    # 9. nhan_khau: cưới, sinh, chết, thừa kế
    demography.buoc_nhan_khau(w, ke_hoach)

    # 10. giao_duc
    education.buoc_giao_duc(w, ke_hoach)

    # 11. ket_toan: công bốc hơi → AUDIT (assert) → metrics
    production.boc_hoi_cong(w)
    audit.kiem_toan_the_gioi(w, tong_thua_ban_dau)
    m = metrics.buoc_ket_toan(w)
    return m
