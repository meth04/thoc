"""Thi hành thẻ chính sách cho agent KHÔNG nghĩ trong tick (SPEC 4.2).

Thẻ chỉ làm việc thường nhật: canh tác, ăn, mua bán theo ngưỡng, tự động trả lời
hợp đồng quen thuộc. Thẻ KHÔNG đề nghị hợp đồng mới, không cầu hôn, không mặc cả.
"""

from __future__ import annotations

from engine.economy import household_food_equivalent
from engine.intents import KeHoach
from engine.market import Lenh
from engine.pricing import gia_ky_vong
from engine.world import World
from minds.schemas import TheChinhSach


def chon_vu_dong_theo_rang_buoc(w: World, parcels: list, cong_san_sang: float,
                                 thieu_luong_thuc: float) -> list[tuple[str, str]]:
    """Choose winter crops from current physical trade-offs, never a fixed crop rule.

    A crop that meets the remaining per-field food need with less labour is
    preferred.  When no feasible crop can meet that need, the higher food per
    scarce field is preferred.  Therefore a labour-constrained household can
    rationally choose potato, while a land-constrained hungry household can
    choose maize under the very same scenario configuration.
    """
    crops = w.cfg.get("khong_gian.vu_dong.cay", {})
    if not isinstance(crops, dict) or cong_san_sang <= 0 or not parcels:
        return []
    _weather, weather_multiplier = w.thoi_tiet(w.tick)
    remaining_labor = max(0.0, float(cong_san_sang))
    remaining_food = max(0.0, float(thieu_luong_thuc))
    selected: list[tuple[str, str]] = []
    for index, parcel in enumerate(parcels):
        fields_left = len(parcels) - index
        need_here = remaining_food / fields_left if fields_left else 0.0
        options: list[tuple[bool, float, float, str]] = []
        for crop, spec in sorted(crops.items()):
            if not isinstance(spec, dict):
                continue
            labor = float(spec.get("cong", 0.0))
            nutrition = float(spec.get("san_luong_kg", 0.0)) * float(
                spec.get("quy_doi_dinh_duong", 0.0)
            )
            expected_food = max(0.0, nutrition * float(parcel.mau_mo) * weather_multiplier)
            if labor > 0 and expected_food > 0 and labor <= remaining_labor + 1e-9:
                options.append((expected_food >= need_here, labor, expected_food, str(crop)))
        if not options:
            continue
        sufficient = [item for item in options if item[0]]
        # enough food: economise scarce labour; otherwise economise scarce land
        chosen = (min(sufficient, key=lambda row: (row[1], -row[2], row[3])) if sufficient
                  else max(options, key=lambda row: (row[2], -row[1], row[3])))
        _enough, labor, food, crop = chosen
        selected.append((parcel.id, crop))
        remaining_labor -= labor
        remaining_food = max(0.0, remaining_food - food)
    return selected


def thi_hanh_the(w: World, aid: str, the: TheChinhSach, bc, da_nham: set[str]) -> KeHoach:
    from minds.rulebot import _chon_thua_canh

    a = w.agents[aid]
    cfg = w.cfg
    tt = cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = cfg.raw()["nhu_cau"]
    sx = cfg.raw()["san_xuat"]
    # The historical one-bank baseline has a pinned mock trajectory. Its
    # legacy card was intentionally a separate treatment surface, so retain
    # it byte-for-byte in effect. Spatial (and V3) treatments instead read
    # every physical labour constraint from the active config; this is the
    # C1 parity repair without retconning old base artifacts.
    config_parity = bool(cfg.get("khong_gian.bat", False)) or bool(
        cfg.get("minds.action_journal.bat", False)
    )
    cong_moi_tick = float(nc["ngay_cong_moi_tick"]) if config_parity else 180.0
    kh = KeHoach(id=aid)
    kh.y_dinh_sinh_con = the.y_dinh_sinh_con

    # trẻ em: tuổi đi học thì học; 15+ biết chữ rồi thì phụ việc nhà
    if not a.truong_thanh(tt):
        cha_me = [p for p in (a.cha, a.me) if p and p in w.agents and w.agents[p].con_song]
        if a.tuoi_nam >= nc["tre_em_gop_cong_tu_tuoi"] and cha_me and a.e_bac >= 1:
            kh.gop_cong_cho = cha_me[0]
        elif a.tuoi_nam >= 6 and a.e_bac < 4:
            kh.hoc = True
        return kh

    ho = w.ho_cua(aid)
    thoc_ho = sum(w.ledger.so_du(m, "thoc") for m in ho)
    food_ho = household_food_equivalent(w, ho)
    nhu_cau_tick = sum(
        nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"]
        for m in ho
    )
    muc_du_tru = nhu_cau_tick * the.du_tru_muc_tieu
    an_ninh = food_ho / muc_du_tru if muc_du_tru > 0 else 1.0

    if w.mua_mua():
        thieu = max(0.0, muc_du_tru * 2 - thoc_ho)
        so_thua_can = max(
            1,
            min(the.canh_toi_da,
                int(sx["thua_toi_da_tu_canh"]) if config_parity else the.canh_toi_da,
                round(thieu / sx["san_luong_goc_kg"] + 0.5)),
        )
        cong_thue_vao = bc.cong_thue_vao.get(aid, 0.0)
        if cong_thue_vao > 0:
            so_thua_can = max(so_thua_can, len(bc.ruong_cua.get(aid, ())))
        toi_da_cong = int(
            (cong_moi_tick * (a.health / 100.0) + cong_thue_vao) // sx["cong_moi_thua"]
        )
        toi_da_giong = int(max(0, thoc_ho - nhu_cau_tick) // sx["giong_kg_moi_thua"])
        so_thua = min(
            so_thua_can, toi_da_giong,
            toi_da_cong if config_parity else max(toi_da_cong, 1),
        )
        if so_thua > 0:
            kh.canh_thua = _chon_thua_canh(bc, aid, so_thua, da_nham)
    else:
        winter_labor = 0.0
        from engine.spatial import _vu_dong_bat, co_the_o_bo

        if config_parity and _vu_dong_bat(w) and food_ho < muc_du_tru:
            from engine.contracts import quyen_su_dung_thua

            leased = quyen_su_dung_thua(w, aid)
            fields = list(bc.ruong_cua.get(aid, ()))
            known_ids = {field.id for field in fields}
            for pid in sorted(leased):
                parcel = w.parcels.get(pid)
                if parcel is not None and parcel.id not in known_ids:
                    fields.append(parcel)
                    known_ids.add(parcel.id)
            fields = [
                p for p in fields
                if p.id not in da_nham and p.loai == "ruong" and co_the_o_bo(w, aid, p.bo)
            ][:max(0, int(the.canh_toi_da))]
            cong_du_kien = (cong_moi_tick * (a.health / 100.0)
                             + float(bc.cong_thue_vao.get(aid, 0.0)))
            kh.canh_vu_dong = chon_vu_dong_theo_rang_buoc(
                w, fields, cong_du_kien, max(0.0, muc_du_tru - food_ho)
            )
            da_nham.update(pid for pid, _crop in kh.canh_vu_dong)
            crop_specs = w.cfg.get("khong_gian.vu_dong.cay", {})
            winter_labor = sum(float(crop_specs[crop]["cong"])
                                for _pid, crop in kh.canh_vu_dong)
        go_co = w.ledger.so_du(aid, "go")
        co_nha = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
        # nhà 240 công: một người không đủ — cần vợ/chồng góp công hoặc công thuê vào
        vc = w.agents.get(a.vo_chong) if a.vo_chong else None
        vc_lon = vc is not None and vc.con_song and vc.truong_thanh(tt)
        cong_du_kien = (cong_moi_tick * (a.health / 100.0) + bc.cong_thue_vao.get(aid, 0.0)
                        + (cong_moi_tick * (vc.health / 100.0) if vc_lon else 0.0))
        if not co_nha and go_co >= sx["recipe"]["nha"]["go"]:
            if cong_du_kien >= float(sx["recipe"]["nha"]["cong"]):
                kh.xay_nha = 1
        elif not co_nha and the.khai_go_khi_ranh and an_ninh > 0.4:
            kh.cong_khai_go = (
                max(0.0, cong_moi_tick - winter_labor) if config_parity else 120.0
            )
        # vợ/chồng (id lớn hơn) góp công cho người dựng nhà cùng hộ
        if (not co_nha and a.vo_chong and aid > a.vo_chong and vc is not None
                and vc.con_song and w.ledger.so_du(a.vo_chong, "go")
                >= sx["recipe"]["nha"]["go"]):
            kh.gop_cong_cho = a.vo_chong
        if the.hoc_khi_du_an and a.e_bac < 4 and an_ninh > 0.8:
            kh.hoc = True

    if the.day_con and a.e_bac >= 1:
        kh.day_cho = [
            c for c in a.con
            if c in w.agents and w.agents[c].con_song
            and w.agents[c].e_bac < 1 and w.agents[c].tuoi_nam >= 6
        ]

    # mua bán theo ngưỡng thẻ
    if the.mua_cong_cu_khi_hong and w.ledger.so_du(aid, "cong_cu") < 1:
        gia_cu = gia_ky_vong(w, aid, "cong_cu")
        if ((config_parity and thoc_ho > muc_du_tru + gia_cu * 1.05)
                or (not config_parity and thoc_ho > 500.0)):
            kh.dat_lenh.append(Lenh(aid, "mua", "cong_cu", 1.0, round(gia_cu * 1.05, 0)))
    if the.ban_go_nguong is not None:
        go_co = w.ledger.so_du(aid, "go")
        if go_co > the.ban_go_nguong:
            gia_go = gia_ky_vong(w, aid, "go")
            kh.dat_lenh.append(
                Lenh(aid, "ban", "go", round(go_co - the.ban_go_nguong, 1),
                     round(gia_go * 0.9, 1))
            )
    if the.nguong_rao_dat is not None and an_ninh < the.nguong_rao_dat:
        ruong = bc.ruong_cua.get(aid, ())
        if len(ruong) >= 2:
            from engine.economy import expected_land_value

            gia_dat = expected_land_value(w, ruong[-1].id)
            kh.niem_yet_dat.append((ruong[-1].id, round(gia_dat, 0)))

    # phụng dưỡng cha mẹ già thiếu ăn (thẻ mặc định bật)
    if the.phung_duong_cha_me and an_ninh > 1.2:
        for pid in (a.cha, a.me):
            if pid and pid in w.agents:
                cu = w.agents[pid]
                tuoi_gia = (
                    float(cfg.get("lao_dong_theo_tuoi.tuoi_giam_suc"))
                    if config_parity else 60.0
                )
                nguong_thieu = float(nc["nguoi_lon_kg_tick"]) if config_parity else 120.0
                if cu.con_song and cu.tuoi_nam > tuoi_gia and w.ledger.so_du(pid, "thoc") < nguong_thieu:
                    kh.bieu.append((pid, "thoc", nguong_thieu))
    # heuristic sinh tồn tự động — chỉ chạy khi thẻ BẬT an_toan_sinh_ton
    # (LLM tắt được bằng patch: giữ nguyên tắc "thẻ do agent tự đặt", check.md D5)
    if the.an_toan_sinh_ton:
        # đàn gà của thẻ: đói giết ăn, đông bán bớt (việc thường nhật)
        so_ga = w.ledger.so_du(aid, "ga")
        if an_ninh < 0.6 and so_ga >= 2:
            kh.giet_ga = max(kh.giet_ga, 2)
        # túng mà không ruộng → ra sông đánh cá (sinh kế không cần vốn)
        if an_ninh < 0.9 and not bc.ruong_cua.get(aid) and not kh.canh_thua:
            kh.danh_ca_cong = max(
                kh.danh_ca_cong, cong_moi_tick if config_parity else 120.0
            )
        if so_ga > 12:
            gia_ga = gia_ky_vong(w, aid, "ga")
            kh.dat_lenh.append(Lenh(aid, "ban", "ga", round(so_ga - 8, 0),
                                    round(gia_ga * 0.95, 1)))

    # tự động trả lời hợp đồng quen thuộc theo thẻ
    if the.nhan_lam_cong_gia_toi_thieu is not None or the.nhan_gui_thoc:
        for dn_id in sorted(w.bang_rao):
            dn = w.bang_rao[dn_id]
            if dn.tu == aid or (dn.den is not None and dn.den != aid):
                continue
            if (the.nhan_lam_cong_gia_toi_thieu is not None
                    and "gop_cong" in dn.motif and "chuyen_giao_dinh_ky" in dn.motif):
                gop = next(c for c in dn.hd.dieu_khoan if c.loai == "gop_cong")
                tra = next(c for c in dn.hd.dieu_khoan if c.loai == "chuyen_giao_dinh_ky")
                gia_cong = tra.so_luong / max(gop.so_cong_moi_tick, 1e-9)
                if (tra.tai_san == "thoc" and gia_cong >= the.nhan_lam_cong_gia_toi_thieu
                        and len(bc.ruong_cua.get(aid, ())) >= 4 and an_ninh > 1.2):
                    kh.tra_loi_de_nghi[dn_id] = "chap_nhan"
                    break
            elif the.nhan_gui_thoc and dn.motif == "chuyen_giao_mot_lan+hoan_tra_theo_yeu_cau":
                if an_ninh > 1.0:
                    kh.tra_loi_de_nghi[dn_id] = "chap_nhan"
                    break
    return kh
