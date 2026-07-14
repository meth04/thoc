"""Ràng buộc sinh kế tối thiểu cho tầng hành vi.

Đây không phải một "bot bí mật": nó là survival floor công khai, bật/tắt trong config
và ghi event mỗi lần áp dụng. Lý do tồn tại là LLM có thể chọn một hành động hợp lệ
nhưng quên hoàn toàn mùa gieo, tạo chết đói nhân tạo dù hộ vẫn có đất, giống và lao
động. Floor chỉ bổ sung một kế hoạch canh tác khả thi khi hộ đang dưới mức dự trữ tối
thiểu và chưa hề có ai trong hộ dự định canh.
"""

from __future__ import annotations

from engine.economy import household_food_equivalent, household_food_need, households
from engine.intents import KeHoach
from engine.world import World
from minds.provenance import record_action


def ap_dung_san_an_toi_thieu(w: World, ke_hoach: dict[str, KeHoach], bc,
                              da_nham: set[str]) -> int:
    """Bổ sung tối đa một thửa/hộ rủi ro trong mùa mưa; trả số hộ được bảo vệ."""
    cfg = w.cfg.get("minds.san_an_toi_thieu")
    if not bool(cfg["bat"]) or not w.mua_mua():
        return 0
    ty_le_du_tru = float(cfg["du_tru_toi_thieu_tick"])
    giong = float(w.cfg.get("san_xuat.giong_kg_moi_thua"))
    cong_can = float(w.cfg.get("san_xuat.cong_moi_thua"))
    ngay_cong = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    da_bao_ve = 0

    # Hộ được chuẩn hóa ở engine.economy để vợ/chồng không bị xét hai lần.
    for members in households(w):
        need = household_food_need(w, members)
        if household_food_equivalent(w, members) >= ty_le_du_tru * need:
            continue
        plans = [ke_hoach.get(aid) for aid in members]
        if any(plan is not None and plan.canh_thua for plan in plans):
            continue
        candidates = []
        for aid in members:
            a = w.agents[aid]
            if not a.con_song or a.tuoi_nam < adult_age:
                continue
            # Hộ không có cơ chế "rút kho chung" tại thời điểm gieo: người canh phải
            # thực sự tự có giống; công ước tính theo cùng công thức sinh công của engine.
            own_grain = w.ledger.so_du(aid, "thoc")
            labor = ngay_cong * (a.health / 100.0)
            if own_grain >= giong and labor >= cong_can:
                candidates.append((-own_grain, aid))
        if not candidates:
            continue
        _negative_grain, farmer = min(candidates)
        from minds.rulebot import _chon_thua_canh

        parcels = _chon_thua_canh(bc, farmer, 1, da_nham)
        if not parcels:
            continue
        plan = ke_hoach.setdefault(farmer, KeHoach(id=farmer))
        plan.canh_thua = [*plan.canh_thua, *parcels]
        record_action(w, farmer, "phan_bo_cong", "survival_floor", target=parcels[0],
                      detail="minimum_food_security")
        da_nham.update(parcels)
        da_bao_ve += 1
        w.events.ghi(w.tick, "san_an_toi_thieu", ho=members[0], nguoi_canh=farmer,
                      thua=parcels[0], du_tru=round(household_food_equivalent(w, members), 1),
                     nhu_cau=round(need, 1))
    return da_bao_ve
