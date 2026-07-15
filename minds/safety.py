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


def ap_dung_san_cho_o_toi_thieu(w: World, ke_hoach: dict[str, KeHoach]) -> int:
    """Keep a feasible shelter project moving when exposure is life-threatening.

    This is the housing analogue of the public food floor above.  It never
    creates wood, labour, land or a house; it only turns an already feasible
    survival response into auditable project intents.  A resident can still
    choose a different livelihood while healthy.  The guard activates only
    after the transparent health threshold in the active scenario has been
    crossed.
    """
    cfg = w.cfg.get("minds.san_cho_o_toi_thieu", {})
    nha_cfg = w.cfg.get("suc_khoe.nha_o", {})
    if (not isinstance(cfg, dict) or not bool(cfg.get("bat", False))
            or not isinstance(nha_cfg, dict) or not bool(nha_cfg.get("bat", False))):
        return 0
    from engine.projects import _du_an_bat

    if not _du_an_bat(w):
        return 0
    registry = w.cfg.get("du_an.cong_trinh", {})
    if not isinstance(registry, dict) or "nha" not in registry:
        return 0
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    nguong = float(cfg.get("nguong_health_khoi_cong", 50.0))
    cong_moi_tick = max(0.0, float(cfg.get("cong_gop_moi_tick", 0.0)))
    da_bao_ve = 0

    for members in households(w):
        song = [aid for aid in members if aid in w.agents and w.agents[aid].con_song]
        nguoi_lon = [aid for aid in song if w.agents[aid].tuoi_nam >= adult_age]
        if not nguoi_lon:
            continue
        if any(w.ledger.so_du(aid, "nha") >= 1.0 for aid in song):
            continue
        if min(w.agents[aid].health for aid in song) > nguong:
            continue

        projects = [
            project for project in getattr(w, "du_an", {}).values()
            if project.trang_thai == "dang_lam" and project.loai == "nha"
            and project.chu in song
        ]
        if projects:
            project = min(projects, key=lambda p: (p.tick_tao, p.id))
            builder = project.chu
            plan = ke_hoach.setdefault(builder, KeHoach(id=builder))
            # Escrow only recipe material already held by the builder.  The
            # engine independently caps the amount and records the outcome.
            for asset, need in sorted(project.vat_lieu_can.items()):
                remaining = max(0.0, float(need) - float(project.vat_lieu_da.get(asset, 0.0)))
                held = max(0.0, w.ledger.so_du(builder, asset))
                if remaining > 1e-9 and held > 1e-9:
                    plan.gop_vat_lieu_du_an.append({
                        "ref": project.id, "tai_san": asset,
                        "so_luong": min(remaining, held),
                    })
            remaining_labor = max(0.0, float(project.cong_can) - float(project.cong_da))
            if remaining_labor > 1e-9 and cong_moi_tick > 0:
                plan.gop_cong_du_an.append({
                    "ref": project.id,
                    "so_cong": min(remaining_labor, cong_moi_tick),
                })
            record_action(w, builder, "gop_cong_du_an", "survival_floor", target=project.id,
                          detail="minimum_shelter_continuation")
            w.events.ghi(w.tick, "san_cho_o_toi_thieu", ho=song[0], nguoi_xay=builder,
                         du_an=project.id, health_min=round(min(
                             w.agents[aid].health for aid in song
                         ), 3), che_do="tiep_dien")
            da_bao_ve += 1
            continue

        # A project needs a site owned by its builder.  No special land right
        # is invented: residents without a parcel must still acquire/lease one
        # or seek another valid response through the ordinary economy.
        candidates = []
        for aid in nguoi_lon:
            sites = sorted(p.id for p in w.parcels.values() if p.chu == aid)
            if sites:
                candidates.append((w.agents[aid].health, aid, sites[0]))
        if not candidates:
            continue
        _health, builder, site = min(candidates, key=lambda row: (row[0], row[1], row[2]))
        plan = ke_hoach.setdefault(builder, KeHoach(id=builder))
        if not any(str(row.get("loai_du_an", "")) == "nha"
                   for row in plan.tao_du_an if isinstance(row, dict)):
            plan.tao_du_an.append({"loai_du_an": "nha", "thua": site})
            record_action(w, builder, "tao_du_an", "survival_floor", target=site,
                          detail="minimum_shelter_project")
            w.events.ghi(w.tick, "san_cho_o_toi_thieu", ho=song[0], nguoi_xay=builder,
                         thua=site, health_min=round(min(
                             w.agents[aid].health for aid in song
                         ), 3), che_do="mo_du_an")
            da_bao_ve += 1
    return da_bao_ve
