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


def ap_dung_san_an_sau_phan_bo_ruong_cong(w: World, ke_hoach: dict[str, KeHoach],
                                           da_duoc_phan: set[str]) -> int:
    """Bridge a lottery loser to one feasible public field in the same sowing tick.

    This is intentionally narrower than a hidden planner: it runs only for a food-insecure
    household after its own submitted common-field requests lost the public lottery, chooses
    one still-unclaimed field, and still requires that actor's seed grain and labour.  The
    action is visible as ``survival_floor`` in provenance/journal/event records.
    """
    from engine.common_land import _bat as common_land_enabled

    cfg = w.cfg.get("minds.san_an_toi_thieu")
    if (not common_land_enabled(w) or not bool(cfg["bat"]) or not w.mua_mua()):
        return 0
    from engine.action_journal import preflight_ok, request
    from engine.spatial import co_the_o_bo

    ty_le_du_tru = float(cfg["du_tru_toi_thieu_tick"])
    giong = float(w.cfg.get("san_xuat.giong_kg_moi_thua"))
    cong_can = float(w.cfg.get("san_xuat.cong_moi_thua"))
    ngay_cong = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
    adult_age = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    used = set(da_duoc_phan)
    for kh in ke_hoach.values():
        for pid in getattr(kh, "canh_thua", ()) or ():
            parcel = w.parcels.get(str(pid))
            if parcel is not None and parcel.loai == "ruong" and parcel.chu is None:
                used.add(parcel.id)

    # Sorting by a keyed random rank avoids replacing ID priority with an equally hidden
    # household-id priority.  The stream is isolated and deterministic for replay.
    households_rows = [sorted(members) for members in households(w)]
    households_rows.sort(key=lambda members: (
        float(w.rng.get(f"food_floor_household:{'|'.join(members)}", w.tick).random()),
        members,
    ))
    protected = 0
    for members in households_rows:
        need = household_food_need(w, members)
        if household_food_equivalent(w, members) >= ty_le_du_tru * need:
            continue
        if any(getattr(ke_hoach.get(aid), "canh_thua", ()) for aid in members):
            continue
        builders = []
        for aid in members:
            agent = w.agents.get(aid)
            if agent is None or not agent.con_song or agent.tuoi_nam < adult_age:
                continue
            if w.ledger.so_du(aid, "thoc") < giong:
                continue
            labour = ngay_cong * (agent.health / 100.0)
            if labour >= cong_can:
                builders.append(aid)
        if not builders:
            continue
        # Grain-rich candidates can actually pay seed; ties use a private keyed draw.
        best_grain = max(w.ledger.so_du(aid, "thoc") for aid in builders)
        tied = [aid for aid in builders if abs(w.ledger.so_du(aid, "thoc") - best_grain) < 1e-9]
        builder = sorted(tied)[int(w.rng.get(
            f"food_floor_builder:{'|'.join(members)}", w.tick
        ).integers(0, len(tied)))]
        fields = [
            parcel for parcel in w.parcels.values()
            if (parcel.loai == "ruong" and parcel.chu is None
                and parcel.homestead_ai is None and parcel.id not in used)
            and co_the_o_bo(w, builder, parcel.bo)
        ]
        if not fields:
            continue
        fields.sort(key=lambda parcel: parcel.id)
        # A random rotation, not lexical "first field", leaves the allocation observable and
        # prevents the fallback itself from creating a persistent geographic/id advantage.
        g = w.rng.get(f"food_floor_field:{builder}", w.tick)
        field = fields[int(g.integers(0, len(fields)))]
        plan = ke_hoach.setdefault(builder, KeHoach(id=builder))
        plan.canh_thua.append(field.id)
        used.add(field.id)
        da_duoc_phan.add(field.id)
        record_action(w, builder, "phan_bo_cong", "survival_floor", target=field.id,
                      detail="common_land_lottery_feasibility_bridge")
        row = request(w, builder, "phan_bo_cong", origin="survival_floor", target=field.id,
                      params={"canh_thua": [field.id]})
        preflight_ok(w, row)
        w.events.ghi(w.tick, "san_an_toi_thieu", ho=members[0], nguoi_canh=builder,
                     thua=field.id,
                     du_tru=round(household_food_equivalent(w, members), 1),
                     nhu_cau=round(need, 1), che_do="sau_lottery_ruong_cong")
        protected += 1
    return protected


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
    from engine.settlement import _dat_o_bat, lo_cong_kha_dung, lo_cua, lo_uu_tien

    da_bao_ve = 0

    for members in households(w):
        song = [aid for aid in members if aid in w.agents and w.agents[aid].con_song]
        nguoi_lon = [aid for aid in song if w.agents[aid].tuoi_nam >= adult_age]
        if not nguoi_lon:
            continue
        if any(w.ledger.so_du(aid, "nha") >= 1.0 for aid in song):
            continue

        # A house cannot be started without a legal site.  In the settlement treatment this
        # is a public, non-productive lot chosen by the resident, not a gifted house or farm
        # title.  The floor only supplies a ranked *request* when the LLM omitted every legal
        # entry action; the engine lottery still decides the result after all plans arrive.
        holders = [(w.agents[aid].health, aid, lo_cua(w, aid)) for aid in nguoi_lon]
        holders = [row for row in holders if row[2]]
        if not holders and _dat_o_bat(w):
            # A syntactically nonempty hallucinated id is not a legal entry response.  Respect
            # an LLM's viable public request, but replace only an empty/invalid list with the
            # transparent board slice so one bad string cannot strand a household indefinitely.
            pending = any(
                set(getattr(ke_hoach.get(aid), "chon_dat_o", ()) or ())
                & set(lo_cong_kha_dung(w, aid))
                for aid in nguoi_lon
            )
            if not pending:
                _health, builder = min(
                    (w.agents[aid].health, aid) for aid in nguoi_lon
                )
                options = lo_uu_tien(w, builder)
                if options:
                    plan = ke_hoach.setdefault(builder, KeHoach(id=builder))
                    plan.chon_dat_o = options
                    record_action(w, builder, "chon_dat_o", "survival_floor",
                                  target=options[0], detail="minimum_shelter_entry_right")
                    w.events.ghi(w.tick, "san_cho_o_toi_thieu", ho=song[0],
                                 nguoi_xay=builder, thua=options[0],
                                 health_min=round(min(w.agents[x].health for x in song), 3),
                                 che_do="xin_lo_cu_tru")
                    da_bao_ve += 1
            # The current tick's claim is resolved after the mind phase.  A project is opened
            # next tick only once a concrete lot is known, never by inventing a site id.
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
            con_thieu_vat_lieu: dict[str, float] = {}
            for asset, need in sorted(project.vat_lieu_can.items()):
                remaining = max(0.0, float(need) - float(project.vat_lieu_da.get(asset, 0.0)))
                held = max(0.0, w.ledger.so_du(builder, asset))
                if remaining > 1e-9 and held > 1e-9:
                    plan.gop_vat_lieu_du_an.append({
                        "ref": project.id, "tai_san": asset,
                        "so_luong": min(remaining, held),
                    })
                shortfall = max(0.0, remaining - held)
                if shortfall > 1e-9:
                    con_thieu_vat_lieu[asset] = shortfall
            remaining_labor = max(0.0, float(project.cong_can) - float(project.cong_da))
            # Spending the last labour hours on a half-built house while missing all of its
            # wood is a deterministic trap: projects consume labour before extraction in the
            # tick pipeline.  First acquire the missing build material; only then add work.
            go_thieu = con_thieu_vat_lieu.get("go", 0.0)
            if go_thieu > 1e-9:
                khai = w.cfg.get("san_xuat.khai_thac", {})
                cong_moi_go = max(1e-9, float(khai.get("cong_moi_go", 1.0)))
                hieu = 1.0 if w.ledger.so_du(builder, "cong_cu") >= 1.0 else float(
                    khai.get("hieu_suat_khong_cong_cu", 1.0)
                )
                cong_can_go = go_thieu * cong_moi_go / max(hieu, 1e-9)
                plan.cong_khai_go = max(
                    float(plan.cong_khai_go), min(cong_moi_tick, cong_can_go)
                )
                record_action(w, builder, "phan_bo_cong", "survival_floor",
                              detail="minimum_shelter_materials")
            elif remaining_labor > 1e-9 and cong_moi_tick > 0:
                plan.gop_cong_du_an.append({
                    "ref": project.id,
                    "so_cong": min(remaining_labor, cong_moi_tick),
                })
                record_action(w, builder, "gop_cong_du_an", "survival_floor",
                              target=project.id, detail="minimum_shelter_continuation")
            w.events.ghi(w.tick, "san_cho_o_toi_thieu", ho=song[0], nguoi_xay=builder,
                         du_an=project.id, health_min=round(min(
                             w.agents[aid].health for aid in song
                         ), 3), che_do="tiep_dien")
            da_bao_ve += 1
            continue

        # A project accepts either an owned parcel (legacy path) or the narrow public
        # residential permit.  Neither route creates wood, labour, a house, or farm title.
        candidates = []
        for aid in nguoi_lon:
            sites = sorted(p.id for p in w.parcels.values() if p.chu == aid)
            residence_site = lo_cua(w, aid)
            if residence_site:
                sites = [residence_site, *sites]
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
