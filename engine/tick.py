"""Pipeline một tick (SPEC mục 6). Phase 2: đủ bước 4 (bảng rao), 6 (chợ), 7 (hợp đồng)."""

from __future__ import annotations

from collections.abc import Callable

from engine import (
    audit,
    board,
    consumption,
    contracts,
    demography,
    economy,
    education,
    market,
    metrics,
    metrics_demography,
    metrics_research,
    production,
    projects,
)
from engine.intents import KeHoach
from engine.market import Lenh, NiemYetDat
from engine.world import World

# Hàm minds: (world) → {agent_id: KeHoach}
MindFn = Callable[[World], dict[str, KeHoach]]


def chay_mot_tick(w: World, mind_fn: MindFn, tong_thua_ban_dau: int) -> dict:
    w.tick += 1

    # Observation-only provenance is reset before the mind runs. A custom
    # mind that does not record an origin is reported as `external` below,
    # rather than silently counted as an LLM decision.
    from engine.action_journal import reset_tick as reset_action_journal
    from minds.provenance import reset_tick as reset_decision_provenance

    reset_decision_provenance(w)
    reset_action_journal(w)

    # 1. bat_dau: tuổi tiến đúng một khoảng lịch; ``tuoi_tick`` được lưu theo nửa-năm
    # để legacy 2-tick/năm không đổi, còn calendar 3 mùa/năm tăng 2/3 mỗi mùa.
    buoc_tuoi = 2.0 / w.tick_moi_nam()
    if buoc_tuoi.is_integer():
        buoc_tuoi = int(buoc_tuoi)
    for a in w.agents.values():
        if a.con_song:
            a.tuoi_tick += buoc_tuoi
    # P4: capture person-time before any birth/death this tick. The metric is
    # derived from engine state, never reconstructed from an event journal.
    metrics_demography.bat_dau_tick(w)
    loai_tt, _ = w.thoi_tiet(w.tick)
    if w.dau_nam():
        w.events.ghi(w.tick, "thoi_tiet", kieu=loai_tt)

    # 2+3. trigger + quyết định
    ke_hoach = mind_fn(w)
    from minds.provenance import record_plan

    for aid in sorted(ke_hoach):
        if aid not in w.decision_provenance_tick.get("plans", {}):
            record_plan(w, aid, "external")
    from engine.action_journal import preflight_plans

    preflight_plans(w, ke_hoach)

    # V4-v6 retain the historical lot-before-common ordering.  ADR 0009 v7 is
    # deliberately different: it must first resolve common-field uncertainty,
    # then derive the food projection, then add a bounded shelter delta, and
    # only then resolve all lot requests together.
    from engine import common_land, settlement
    from minds.safety import (
        _shelter_v7_enabled,
        ap_dung_san_an_sau_phan_bo_ruong_cong,
        de_xuat_san_cho_o_toi_thieu_v7,
    )

    shelter_v7 = _shelter_v7_enabled(w)
    if not shelter_v7:
        settlement.giai_quyet_chon_dat_o(w, ke_hoach)
    da_phan_ruong_cong = common_land.phan_bo_ruong_cong(w, ke_hoach)
    ap_dung_san_an_sau_phan_bo_ruong_cong(w, ke_hoach, da_phan_ruong_cong)
    if shelter_v7:
        # Minds derive immutable, facts-only shelter deltas.  The engine alone
        # mutates the plan and emits provenance/request/preflight observations.
        from engine.shelter_floor import ap_dung_delta_san_cho_o_v7

        shelter_deltas = de_xuat_san_cho_o_toi_thieu_v7(w, ke_hoach, da_phan_ruong_cong)
        ap_dung_delta_san_cho_o_v7(w, ke_hoach, shelter_deltas)
        settlement.giai_quyet_chon_dat_o(w, ke_hoach)

    # 3b. lập pháp nhân + di chúc + di cư (trước bảng rao để entity ký được ngay)
    from engine import entities as entities_mod
    from engine.action_journal import executed as journal_executed

    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        a = w.agents.get(aid)
        if a is None or not a.con_song:
            continue
        if kh.lap_phap_nhan:
            d = kh.lap_phap_nhan
            entities_mod.lap_phap_nhan(
                w, aid, str(d.get("ten", "")), d.get("co_phan", {}), d.get("von_gop", {})
            )
        if kh.viet_di_chuc:
            a.di_chuc = kh.viet_di_chuc
            w.events.ghi(w.tick, "viet_di_chuc", id=aid)
            journal_executed(w, aid, "viet_di_chuc", code="will_recorded")
        if kh.di_cu:
            _di_cu(w, aid)
        # quyết định nhân danh entity (người điều hành >50% cổ phần)
        for eid, kh_con in kh.quyet_dinh_entity:
            if eid in w.entities and entities_mod.nguoi_dieu_hanh(w, eid) == aid:
                kh_con.id = eid
                ke_hoach[eid] = kh_con
            else:
                w.ghi_unrecognized(aid, "quyet_dinh_entity",
                                   f"không điều hành {eid}")

    # 3c. P2P (PART 5.4): thư gửi tick này → hòm thư, GIAO Ở PROMPT TICK SAU. Thuần thông
    # tin (mặc cả/vận động), KHÔNG chạm Ledger. Cap chống spam; cộng nhẹ quan hệ (đã liên lạc).
    hom_thu_moi: dict[str, list] = {}
    cong_lien_lac = float(w.cfg.get("quan_he.cong_moi_tuong_tac"))
    gui_toi_da = int(w.cfg.get("minds.p2p_gui_toi_da"))
    nhan_toi_da = int(w.cfg.get("minds.p2p_hom_thu_toi_da"))
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected

    for aid in sorted(ke_hoach):
        if not w.chu_the_hoat_dong(aid):
            continue
        for den, noi_dung in ke_hoach[aid].nhan_tin[:gui_toi_da]:
            if not w.chu_the_hoat_dong(den) or den == aid:
                journal_rejected(w, aid, "nhan_tin", "recipient_unavailable", target=den)
                continue
            if len(hom_thu_moi.get(den, ())) >= nhan_toi_da:  # hòm thư đầy → bỏ (chống spam)
                journal_rejected(w, aid, "nhan_tin", "mailbox_full", target=den)
                continue
            hom_thu_moi.setdefault(den, []).append((aid, str(noi_dung)[:300], w.tick))
            w.cong_quan_he(aid, den, cong_lien_lac)
            w.events.ghi(w.tick, "nhan_tin", tu=aid, den=den)
            journal_executed(w, aid, "nhan_tin", target=den, code="message_delivered")

    # 4. bang_rao: đăng đề nghị, trả lời, khớp; đơn phương phá vỡ
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected

    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        for hd, den in kh.de_nghi_hop_dong:
            ref = board.dang_de_nghi(w, aid, hd, den)
            if ref is None:
                journal_rejected(w, aid, "de_nghi_hop_dong", "offer_rejected", target=den)
            else:
                journal_executed(w, aid, "de_nghi_hop_dong", target=den,
                                 code="offer_listed", detail=f"ref={ref}")
        for ref, tl in sorted(kh.tra_loi_de_nghi.items()):
            dn = w.bang_rao.get(ref)
            if dn is not None and (dn.den is None or dn.den == aid) and dn.tu != aid:
                dn.tra_loi[aid] = tl
                journal_executed(w, aid, "tra_loi_hop_dong", target=ref,
                                 code="response_submitted", pending=True)
            else:
                journal_rejected(w, aid, "tra_loi_hop_dong", "offer_not_available", target=ref)
    board.khop_bang_rao(w)
    # Versioned P3 commerce: escrow is locked before production/market can spend the same
    # inventory. Gate OFF is a no-op, preserving all legacy tick ordering.
    from engine import quotes

    quotes.buoc_bao_gia(w, ke_hoach)
    # A work order is only registered here. Its inputs/labour are handled after
    # the current tick has issued labour and any ferry crossing has occurred.
    projects.dang_ky_du_an(w, ke_hoach)
    for aid in sorted(ke_hoach):
        for hd_id in ke_hoach[aid].don_phuong_pha_vo:
            hd = w.hop_dong.get(hd_id)
            if hd is not None and hd.trang_thai == "hieu_luc" and aid in hd.cac_ben:
                contracts.phat_vi_pham(w, hd, aid)
        # báo hủy đúng luật: hợp đồng chấm dứt sau bao_truoc tick, không mất uy tín
        for hd_id in ke_hoach[aid].bao_huy:
            hd = w.hop_dong.get(hd_id)
            if (hd is not None and hd.trang_thai == "hieu_luc" and aid in hd.cac_ben
                    and hd.huy_bao_truoc_tu is None):
                hd.huy_bao_truoc_tu = w.tick
                w.events.ghi(w.tick, "bao_huy_hd", hd=hd_id, ai=aid)

    # 4b. chính quyền (TRƯỚC sản xuất): bầu cử, lập pháp, hối lộ, nghiệp đoàn, đình công,
    # kêu gọi. Đánh dấu đình công tick này để hook góp công (bước 5) hoãn giao công.
    from engine import politics

    politics.buoc_chinh_quyen(w, ke_hoach)

    # 5. san_xuat: sinh công → góp công theo hợp đồng → canh/khai thác/chế tác/xây → R&D
    w.kl_hd_tick = 0.0  # tích lũy giá trị chuyển giao qua hợp đồng trong tick (quy thóc)
    w.gat_tick.clear()
    w.canh_tick.clear()
    w.thu_hoach_cay_tick = []
    w.cong_dung_tick = {}
    w.kl_thanh_toan_tick = {}
    w.settlement_fail_tick = 0  # reset đếm thất bại thanh toán mỗi tick (observation, T07)
    w.ben_kia_tick = set()  # reset ai-qua-sông (ADR 0005) — ferry bên dưới nạp lại
    w.cong_cham_tre_theo_cap = {}
    w.cham_tre_tick = {}
    production.sinh_cong(w)
    # Chăm trẻ là trade-off công thật: người chăm dùng công của chính mình trước mọi sản
    # xuất; worker có hợp đồng gop_cong được credit đúng phần công đã chăm thay cha/mẹ.
    from engine import care

    care.buoc_cham_tre(w, ke_hoach)
    contracts.gop_cong_dau_san_xuat(w)
    # chi công (fiscal.bat): trưởng làng chi treasury xây thủy lợi TRƯỚC canh tác (trưởng đã
    # có công; treasury từ các tick trước) — thủy lợi xây tick này giúp ngay vụ tick này.
    politics.thi_hanh_chi_cong(w, ke_hoach)
    # đò (khong_gian.bat): đóng thuyền + chở khách qua sông SAU khi công đã sinh/góp, TRƯỚC
    # canh tác/khai thác bờ kia (khách qua rồi mới hoạt động bờ đối diện). TẮT → no-op.
    from engine import spatial

    spatial.buoc_qua_song(w, ke_hoach)
    projects.buoc_du_an(w, ke_hoach)
    # P2 ecology: biomass regenerates before extraction; optional reforestation uses actual
    # labor before all other production. Both functions are strict no-ops outside v2.
    from engine import forest

    forest.tai_sinh_rung(w)
    forest.trong_rung_dat(w, ke_hoach)
    production.thi_hanh_san_xuat(w, ke_hoach)
    # thuế SAU thu hoạch: thu theo suất trên sản lượng gặt → công quỹ → chia đều đầu người
    politics.thu_thue_va_chia(w)
    # chăn nuôi: bắt gà / giết thịt theo kế hoạch
    from engine import chan_nuoi as cn_mod
    from engine import xa_hoi

    cn_mod.tai_sinh_ca(w)  # đàn cá sông hồi trước, người đánh sau (trong 6 tháng đó)
    cn_mod.tai_sinh_ga_rung(w)
    cn_mod.truong_thanh_ga(w)  # gà con của tick trước nay đủ 6 tháng nuôi
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        if kh.bat_ga_cong > 0:
            cn_mod.bat_ga(w, aid, kh.bat_ga_cong)
        if kh.giet_ga > 0:
            cn_mod.giet_ga(w, aid, kh.giet_ga)
        if kh.danh_ca_cong > 0:
            cn_mod.danh_ca(w, aid, kh.danh_ca_cong)
        if aid in w.agents:  # tiệc/trộm là chuyện người với người, entity đứng ngoài
            if kh.mo_tiec:
                xa_hoi.mo_tiec(w, aid, *kh.mo_tiec)
            if kh.trom:
                xa_hoi.trom(w, aid, *kh.trom)
    from engine import research as research_mod

    for aid in sorted(ke_hoach):
        nc = ke_hoach[aid].nghien_cuu
        if nc and w.chu_the_hoat_dong(aid):
            linh_vuc, cong, thoc = nc
            research_mod.thi_hanh_nghien_cuu(w, aid, linh_vuc, float(cong), float(thoc))
    research_mod.buoc_nghien_cuu(w)

    # 6. cho: call auction mọi tài sản + sealed bid đất
    lenh_tick: list[Lenh] = []
    tra_gia: list[tuple[str, str, float]] = []
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        for le in kh.dat_lenh:
            if isinstance(le, Lenh) and le.ai == aid:
                lenh_tick.append(le)
        for thua, gia_ask in kh.niem_yet_dat:
            p = w.parcels.get(thua)
            if p is not None and p.chu == aid and gia_ask > 0:
                w.niem_yet_dat[thua] = NiemYetDat(thua, aid, float(gia_ask), w.tick)
                w.events.ghi(w.tick, "niem_yet", thua=thua, gia=gia_ask, chu=aid)
        for thua, gia in kh.tra_gia_dat:
            tra_gia.append((aid, thua, float(gia)))
        for hd_id, sl in kh.yeu_cau_rut.items():
            w.yeu_cau_rut_tick[(hd_id, aid)] = float(sl)
    # rao vặt: ai đang rao bán/cần mua gì — tick sau cả làng nghe phong thanh.
    # Quá đông thì LẤY MẪU seeded (không cắt đầu — id lớn cũng được thành tin đồn)
    rao_ca = [
        (le.ai, le.chieu, le.tai_san, le.so_luong, le.gia)
        for le in lenh_tick if le.tai_san != "cong"
    ]
    rao_toi_da = int(w.cfg.get("thuong_mai.rao_vat_toi_da"))
    if len(rao_ca) > rao_toi_da:
        g_rao = w.rng.get("rao_vat", w.tick)
        chon = sorted(g_rao.choice(len(rao_ca), size=rao_toi_da, replace=False))
        rao_ca = [rao_ca[int(i)] for i in chon]
    w.rao_vat = rao_ca
    kl_cho = market.phien_cho(w, lenh_tick)
    market.phien_dat(w, w.niem_yet_dat, tra_gia)
    # Giá chỉ do chợ tạo. Sau phiên, mỗi agent cập nhật reservation value của chính mình
    # từ giao dịch vừa quan sát để tick sau không lặp mãi prior ban đầu.
    from engine.pricing import cap_nhat_gia_ky_vong

    cap_nhat_gia_ky_vong(w)

    # 7. thi_hanh_hop_dong: clause định kỳ, đáo hạn, vi phạm, cưỡng chế
    contracts.thi_hanh_hop_dong_tick(w, chet_tick=w.chet_tick_truoc)
    # Future-dated quote fills settle only at their declared due tick, after other contractual
    # obligations but before consumption/demography. Spot fills already settled in phase 4.
    quotes.giao_hang_den_han(w)
    # entity: chia lợi nhuận + kiểm tra mất khả năng thanh toán → thanh lý
    from engine.entities import chia_loi_nhuan_dinh_ky, kiem_tra_pha_san

    chia_loi_nhuan_dinh_ky(w)
    kiem_tra_pha_san(w)
    # hợp đồng kết thúc → chuyển kho lưu trữ (chỉ observatory/analyze đọc)
    xong = [hid for hid, h in w.hop_dong.items() if h.trang_thai != "hieu_luc"]
    for hid in xong:
        w.hop_dong_xong[hid] = w.hop_dong.pop(hid)

    # 8. tieu_dung_suc_khoe (đàn gà ăn/đẻ trước, rồi người ăn — thóc lẫn thịt)
    cn_mod.buoc_chan_nuoi(w)
    cn_mod.hao_thit(w)
    consumption.hao_hut_kho(w)
    # Hao kho tác động lên MỌI chủ thể ledger — kể cả chủ thể ký quỹ (`KY_QUY:*`, `DU_AN:*`).
    # Sổ khai báo của báo giá/dự án phải bám theo sổ cái, nếu không audit E1′ thấy
    # `sổ=23.5176 khai=24.0` và dừng run. Ký quỹ KHÔNG được miễn hao: miễn hao là tặng agent
    # một kho lưu trữ miễn phí (gửi thóc vào một báo giá không ai nhận để né hao mòn) — đúng
    # loại exploit sẽ bóp méo chính câu hỏi mô hình đang đo.
    quotes.dong_bo_ky_quy(w)
    projects.dong_bo_ky_quy(w)
    consumption.an_va_suc_khoe(w)
    consumption.dich_benh(w)

    # 9. nhan_khau (ghi lại người chết tick này cho điều kiện sự kiện tick sau)
    truoc = {aid for aid, a in w.agents.items() if not a.con_song}
    demography.buoc_nhan_khau(w, ke_hoach)
    w.chet_tick_truoc = {
        aid for aid, a in w.agents.items() if not a.con_song
    } - truoc
    xa_hoi.cuu_mang_mo_coi(w)  # trẻ mồ côi cả cha lẫn mẹ được cưu mang ngay tick này

    # 9b/9c (ADR 0007 §C.2). Vị trí này thỏa hai ràng buộc CỨNG: (a) TRƯỚC
    # `audit.kiem_toan_the_gioi` ⇒ không có tick nào "tạm lệch rồi cân sau"; (b) SAU
    # `cuu_mang_mo_coi` ⇒ trẻ mồ côi đã có giám hộ trước khi tính hộ. ADR KHÔNG hoán vị thứ tự
    # bước tick (đảo demography lên trước contracts sẽ đổi quỹ đạo của MỌI run, kể cả gate
    # TẮT) — F-20 được sửa bằng cách THÊM 9c, không phải hoán vị 7/9. Cả hai no-op khi TẮT.
    from engine import estate, household

    for aid in sorted(ke_hoach):
        for ds_id in getattr(ke_hoach[aid], "yeu_cau_di_san", ()):
            estate.yeu_cau_di_san(w, aid, str(ds_id))
    household.buoc_cu_tru(w, ke_hoach)  # 9b — MỌI mutation membership ở đây, và CHỈ ở đây
    estate.buoc_di_san(w)  # 9c — chủ nợ → di chúc → kin → hết hạn → đóng

    # 10. giao_duc
    education.buoc_giao_duc(w, ke_hoach)

    # 11. ket_toan: đất bỏ hoang hồi màu → quan hệ nhạt dần → công bốc hơi → AUDIT
    production.phuc_hoi_dat(w)
    xa_hoi.decay_quan_he(w)
    production.boc_hoi_cong(w)
    # thủy lợi công hao mòn cuối tick (fiscal.bat) — SINK đã đăng ký, có event; TẮT → no-op
    politics.hao_mon_thuy_loi(w)
    # bạo động: cơ chế trung lập — sung công + chia lại QUA LEDGER khi Gini quá ngưỡng
    # VÀ đủ số đông bạo động (chuyển CÂN nên audit vẫn xanh)
    politics.buoc_bao_dong(w, ke_hoach)
    # Every v3 request has a terminal audit label before metrics are written.
    # Handlers that know the result have already marked it; legacy paths are
    # honestly marked ``unobserved`` instead of silently inflating "planned".
    from engine.action_journal import finalize_unresolved

    finalize_unresolved(w)
    audit.kiem_toan_the_gioi(w, tong_thua_ban_dau)
    research_mod.cap_nhat_san_tier(w)
    m = metrics.buoc_ket_toan(w)
    # Metric nghiên cứu T04–T08 (Lớp-5 quan sát): CHỈ ĐỌC world SAU audit, KHÔNG vào
    # world_hash (chỉ nằm trong m/metrics_lich_su) — không đổi determinism/replay.
    m["research"] = metrics_research.research_metrics(w)
    # poverty_streak (observation state, T04 ADR 0003 §E): cập nhật SAU audit + SAU
    # metrics_research. Streak = số tick LIÊN TIẾP food_security<1 per hộ-head; reset 0 khi
    # đủ ăn. KHÔNG vào world_hash (engine không đọc lại → không đụng determinism). Head mới
    # → bắt đầu 0; head biến mất (hộ tan/chết) → dọn khỏi dict. Giá trị research surface phản
    # ánh streak tới HẾT tick TRƯỚC (lag 1 tick — đúng bản chất state đóng sổ cuối ket_toan).
    # ADR 0007 §F.3: khi cư trú bền BẬT, streak được re-key theo `rid` thay vì head-id ⇒ sửa
    # luôn giới hạn ADR 0003 §E ("head đổi ⇒ streak gãy"). Vẫn NGOÀI world_hash.
    heads_song: set[str] = set()
    for row in sorted(economy.household_snapshot(w), key=lambda r: r["head"]):
        head = str(row.get("rid") or row["head"])
        heads_song.add(head)
        if float(row["food_security"]) < 1.0:
            w.poverty_streak[head] = w.poverty_streak.get(head, 0) + 1
        else:
            w.poverty_streak[head] = 0
    for head in [h for h in w.poverty_streak if h not in heads_song]:
        del w.poverty_streak[head]
    m["kl_cho"] = round(kl_cho, 3)
    m["kl_giao_dich"] = round(kl_cho + getattr(w, "kl_hd_tick", 0.0), 3)
    m["trade_flows"] = metrics.giao_dich_theo_kenh(w, kl_cho, w.metrics_lich_su)
    hieu_luc = [h for h in w.hop_dong.values() if h.trang_thai == "hieu_luc"]
    m["hd_hieu_luc"] = len(hieu_luc)
    m["so_mo_tip"] = len({board.mo_tip_hop_dong(h) for h in hieu_luc})
    m["tri_thuc"] = round(w.tri_thuc, 3)
    m["san_tier"] = w.san_tri_thuc_tier
    m["so_entity"] = sum(1 for e in w.entities.values() if e.con_hoat_dong)
    m["so_blueprint"] = len(w.blueprints)
    m["so_may"] = round(w.ledger.tong_tai_san("may"), 1)
    # chính trị (đặt tại đây — KHÔNG đụng engine/metrics.py; getattr an toàn khi vô chính phủ)
    cq = w.chinh_quyen
    m["truong_lang"] = cq.truong_lang if cq else None
    m["thue_suat"] = round(cq.thue_suat, 4) if cq else 0.0
    m["luong_toi_thieu"] = round(cq.luong_toi_thieu, 4) if cq else 0.0
    m["so_nghiep_doan"] = len(cq.nghiep_doan) if cq else 0
    m["so_dinh_cong"] = len(cq.dinh_cong_tick) if cq else 0
    m["so_bao_dong"] = w.so_bao_dong_tick
    cua_so = int(w.cfg.get("quan_sat.cua_so_tick"))
    cong_4_tam: dict[str, float] = {}
    for d in [*w.cong_dung_4, w.cong_dung_tick][-cua_so:]:
        for k, v in d.items():
            cong_4_tam[k] = cong_4_tam.get(k, 0.0) + v
    tong_cong = sum(cong_4_tam.values())
    m["ty_trong_phi_nong"] = round(
        cong_4_tam.get("phi_nong", 0.0) / tong_cong, 4) if tong_cong else 0.0
    # cửa sổ 4 tick cho cơ cấu công + phương tiện thanh toán (trước khi observatory đọc)
    w.cong_dung_4.append(dict(w.cong_dung_tick))
    if len(w.cong_dung_4) > cua_so:
        w.cong_dung_4.pop(0)
    w.kl_thanh_toan_4.append(dict(w.kl_thanh_toan_tick))
    if len(w.kl_thanh_toan_4) > cua_so:
        w.kl_thanh_toan_4.pop(0)
    # observatory: nhãn định chế + giai cấp + milestones (chỉ đọc)
    from observatory.observer import buoc_observatory, viet_chronicle

    obs = buoc_observatory(w)
    m["giai_cap"] = obs["giai_cap"]
    m["nhan_dinh_che"] = obs["nhan_dinh_che"]
    # cache nhãn giai cấp lên w (kênh MỘT CHIỀU observatory→prompt): persona đọc
    # w.phan_loai để nói "Bạn là [giai cấp]..." — engine KHÔNG rẽ nhánh theo nhãn này
    w.phan_loai = obs["phan_loai"]
    m["cong_nghiep_hoa"] = bool(w.nhan_dinh_che.get("cong_nghiep_hoa"))
    # cửa sổ thu nhập 4 tick (sau khi observatory đã dùng)
    w.thu_nhap_4.append(w.thu_nhap_tick)
    if len(w.thu_nhap_4) > cua_so:
        w.thu_nhap_4.pop(0)
    w.thu_nhap_tick = {}
    # chronicle mỗi 20 tick
    if w.tick % int(w.cfg.get("minds.chronicle_moi_n_tick")) == 0:
        doan = viet_chronicle(w, m)
        w.events.ghi(w.tick, "chronicle", van=doan)
    # snapshot giai cấp + của cải định kỳ — tools/analyze dựng ma trận dịch chuyển
    if w.tick % int(w.cfg.get("quan_sat.snapshot_moi_n_tick")) == 0:
        from engine.entities import tai_san_quy_thoc

        snap = {
            aid: [obs["phan_loai"].get(aid, "?"), round(tai_san_quy_thoc(w, aid), 1)]
            for aid, ag in w.agents.items() if ag.con_song
        }
        w.events.ghi(w.tick, "giai_cap_snapshot", du_lieu=snap)
    # P2P: thư gửi tick này thay hòm thư cũ (đã đọc ở prompt tick này) → giao tick sau
    w.hom_thu = hom_thu_moi
    return m


def _di_cu(w: World, aid: str) -> None:
    """Lập làng mới: cần cụm ruộng công đủ rộng, đủ xa mọi làng (tham số di_cu, chỉ vật lý)."""
    from engine.types import Village

    dc = w.cfg.raw()["di_cu"]
    so_thua_min = int(dc["so_thua_toi_thieu"])
    cach_min = int(dc["cach_lang_toi_thieu"])
    ban_kinh_cum = int(dc["ban_kinh_cum"])
    ung_vien = [
        p for p in w.parcels.values()
        if p.loai == "ruong" and p.chu is None
        and all(abs(p.r - v.r) + abs(p.c - v.c) >= cach_min for v in w.villages)
    ]
    if len(ung_vien) < so_thua_min:
        w.ghi_unrecognized(aid, "di_cu", "không còn vùng đất công đủ xa/đủ rộng")
        return
    tam = ung_vien[0]
    gan_tam = [p for p in ung_vien if abs(p.r - tam.r) + abs(p.c - tam.c) <= ban_kinh_cum]
    if len(gan_tam) < so_thua_min:
        w.ghi_unrecognized(aid, "di_cu", "cụm đất quá thưa")
        return
    vid = len(w.villages)
    w.villages.append(Village(id=vid, ten=f"Làng Mới {vid}", r=tam.r, c=tam.c))
    for p in gan_tam:
        p.lang = vid
    w.agents[aid].lang = vid
    # ADR 0007 §C.3 transition 6: hộ mới ở làng mới có hiệu lực CUỐI tick (bước 9b) — người di
    # cư ĐÃ ăn với hộ cũ trong tick này. Đó là hành vi KHAI BÁO, không phải bug.
    from engine import household

    household.ghi_bien_co(w, "di_cu", nguoi=aid, lang=vid)
    w.events.ghi(w.tick, "di_cu", id=aid, lang=vid)
