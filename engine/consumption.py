"""Tiêu dùng & sức khỏe: ăn theo hộ, hao hụt kho, health, vô gia cư (SPEC 2.6)."""

from __future__ import annotations

from engine.world import World


def hao_hut_kho(w: World) -> None:
    from engine.research import duoc_ap_dung

    ty_le_goc = float(w.cfg.get("san_xuat.hao_hut_kho_moi_tick"))
    # hàng lưu kho (blueprint che_bien hiệu ứng luu_kho) người giữ được giảm thêm
    hieu_ung_hang: dict[str, float] = {
        bp.hang_moi: bp.hieu_ung_do_lon
        for bp in w.blueprints.values()
        if bp.hang_moi and bp.hieu_ung == "luu_kho"
    }
    from engine.economy import food_equivalence

    food_assets = food_equivalence(w)
    for (chu_the, ts), v in list(w.ledger._so_du.items()):
        if ts in food_assets and v > 0:
            giam = duoc_ap_dung(w, chu_the, "luu_kho")
            for ma, do_lon in hieu_ung_hang.items():
                if w.ledger.so_du(chu_the, ma) >= 1.0:
                    giam += do_lon
            san = float(w.cfg.get("tieu_dung.san_hao_kho"))
            ty_le = ty_le_goc * max(san, 1.0 - giam)
            w.ledger.huy(chu_the, ts, v * ty_le, "hao_kho", f"hao hụt kho {ts}", w.tick)


def an_va_suc_khoe(w: World) -> None:
    nc = w.cfg.raw()["nhu_cau"]
    sk = w.cfg.raw()["suc_khoe"]
    td = w.cfg.raw()["tieu_dung"]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    from engine.economy import food_equivalence
    from engine.household import _cap_luong_thuc_bat, cap_va_an, rid_cua

    food_assets = food_equivalence(w)
    # ADR 0007 §B: khi BẬT, mỗi kg vượt ranh giới cá nhân đi qua `ledger.chuyen(người-cấp →
    # người-ăn)` + event `cap_luong_thuc` TRƯỚC `huy(người-ăn, "an")`. Hôm nay engine đốt thóc
    # của thành viên khác trong hộ mà KHÔNG để lại bất kỳ dấu vết nào về ai nuôi ai — đó là
    # đúng cái lỗ mà Report_v2 §4.2 nêu. Quy tắc phân bổ giữ NGUYÊN semantics: `nhu_cau_deu`
    # (mỗi người được cấp đúng nhu cầu của mình), nguồn rút vẫn "kho lớn nhất gánh trước",
    # thiếu vẫn chia đều theo tỷ lệ ở mức HỘ (`ty_le_no`). KHÔNG nhân dịp này thêm luật ưu
    # tiên trẻ em/người già — đó là một treatment riêng, phải qua cổng, ngoài P1.
    cap = _cap_luong_thuc_bat(w)
    nha_o = sk.get("nha_o", {})
    nha_o_bat = isinstance(nha_o, dict) and bool(nha_o.get("bat", False))

    # Ăn theo hộ: gom nhu cầu, ăn từ kho các thành viên (chủ hộ trước).
    # Dedup bằng da_xu_ly tại thành viên ĐẦU TIÊN gặp theo thứ tự sorted —
    # điều kiện min(ho) từng làm con riêng nhà tái hôn rơi khỏi mọi hộ (không ăn,
    # không chết đói)
    da_xu_ly: set[str] = set()
    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song or aid in da_xu_ly:
            continue
        ho = [m for m in w.ho_cua(aid) if w.agents[m].con_song]
        da_xu_ly.update(ho)
        co_nha = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
        nhu_cau_tung_nguoi = {
            m: (nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"])
            for m in ho
        }
        tong_nhu_cau = sum(nhu_cau_tung_nguoi.values())
        con_thieu = dict(nhu_cau_tung_nguoi)  # nhu cầu CHƯA được cấp của từng người (quy thóc)
        rid = (rid_cua(w, aid) or ho[0]) if cap else ""
        # Ăn lúa trước rồi ngô/khoai; mỗi thứ có quy đổi dinh dưỡng công khai. Cây vụ
        # đông không bị tự đổi thành thóc, chỉ trực tiếp nuôi hộ khi còn trong kho.
        thieu = tong_nhu_cau
        for ts, quy_doi in food_assets.items():
            if thieu <= 1e-9:
                break
            ton_kho = {m: w.ledger.so_du(m, ts) for m in ho}
            for m in sorted(ho, key=lambda x: -ton_kho[x]):
                if thieu <= 1e-9:
                    break
                tru = min(ton_kho[m], thieu / quy_doi)
                if tru > 0:
                    if cap:
                        cap_va_an(w, ho, m, ts, tru, quy_doi, con_thieu, rid)
                    else:
                        w.ledger.huy(m, ts, tru, "an", f"ăn {ts}", w.tick)
                    thieu -= tru * quy_doi
        an_duoc = tong_nhu_cau - max(0.0, thieu)
        # thiếu lương thực thực vật → ăn THỊT rồi CÁ (đậm dinh dưỡng hơn thóc, mau hỏng)
        if thieu > 1e-9:
            for ts, quy_doi in (
                ("thit", float(w.cfg.raw()["chan_nuoi"]["thit_quy_doi_dinh_duong"])),
                ("ca", float(w.cfg.raw()["danh_ca"]["ca_quy_doi_dinh_duong"])),
            ):
                for m in ho:
                    co = w.ledger.so_du(m, ts)
                    if co <= 0 or thieu <= 1e-9:
                        continue
                    an_them = min(co, thieu / quy_doi)
                    if cap:
                        cap_va_an(w, ho, m, ts, an_them, quy_doi, con_thieu, rid)
                    else:
                        w.ledger.huy(m, ts, an_them, "an", f"ăn {ts}", w.tick)
                    thieu -= an_them * quy_doi
            an_duoc = tong_nhu_cau - max(0.0, thieu)
        ty_le_no = an_duoc / tong_nhu_cau if tong_nhu_cau > 0 else 1.0
        # hàng "tiện nghi": mỗi tick hộ tiêu dùng 1 đơn vị/loại → cộng health nhỏ
        bonus_tien_nghi = 0.0
        for bp in w.blueprints.values():
            if not bp.hang_moi or bp.hieu_ung != "tien_nghi":
                continue
            for m in ho:
                if w.ledger.so_du(m, bp.hang_moi) >= 1.0:
                    w.ledger.huy(m, bp.hang_moi, 1.0, "tieu_dung", "tiện nghi", w.tick)
                    bonus_tien_nghi += (bp.hieu_ung_do_lon
                                        * float(td["he_so_tien_nghi_health"]))
                    break
        ld = w.cfg.raw()["lao_dong_theo_tuoi"]
        hao_gia = float(ld["hao_suc_gia_moi_tick"])
        tuoi_giam = float(ld["tuoi_giam_suc"])
        for m in ho:
            ag = w.agents[m]
            if bonus_tien_nghi > 0:
                ag.health = min(100.0, ag.health + bonus_tien_nghi)
            if ag.tuoi_nam > tuoi_giam:  # tuổi già hao sức — cần được chăm sóc, ăn đủ
                ag.health = max(0.0, ag.health - hao_gia)
            if ty_le_no >= 1.0 - 1e-9:
                hoi = float(sk["hoi_khi_an_du"])
                if nha_o_bat and not co_nha:
                    hoi *= float(nha_o.get("he_so_hoi_khi_vo_gia_cu", 1.0))
                ag.health = min(100.0, ag.health + hoi)
            else:
                mat = sk["mat_toi_da_khi_doi"] * (1.0 - ty_le_no)
                ag.health = max(0.0, ag.health - mat)
                ag.doi_tick = w.tick  # đánh dấu vừa thiếu ăn — phân loại cái chết đúng
                if ty_le_no < float(td["nguong_an_doi_event"]):
                    w.events.ghi(w.tick, "an_doi", id=m, ty_le_no=round(ty_le_no, 2))
            if nha_o_bat:
                ag.vo_gia_cu = not co_nha
                if not co_nha:
                    key = "mat_suc_khoe_mua_mua" if w.mua_mua() else "mat_suc_khoe_mua_kho"
                    ag.health = max(0.0, ag.health - float(nha_o.get(key, 0.0)))

    # Vô gia cư: hộ không sở hữu nhà nào → mùa mưa mất health
    if nha_o_bat:
        return
    da_xu_ly.clear()
    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song or aid in da_xu_ly:
            continue
        ho = [m for m in w.ho_cua(aid) if w.agents[m].con_song]
        da_xu_ly.update(ho)
        co_nha = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
        for m in ho:
            w.agents[m].vo_gia_cu = not co_nha
            if not co_nha and w.mua_mua():
                w.agents[m].health = max(
                    0.0, w.agents[m].health - sk["mat_khi_vo_gia_cu_mua_mua"]
                )


def dich_benh(w: World) -> None:
    """Áp cú sốc dịch bệnh đã được scenario kích hoạt trước bước tử vong.

    Cú sốc tác động sức khỏe chứ không tạo/hủy tài sản, vì vậy không đi qua ledger.
    Event ghi một lần mỗi năm để đối chiếu với dữ liệu dịch bệnh khi scenario có nguồn.
    """
    w.dich_benh_tick = w.co_dich_benh()
    if not w.dich_benh_tick:
        return
    loss = float(w.cfg.get("cu_soc.dich_benh.mat_suc_khoe_moi_tick"))
    for agent in w.agents.values():
        if agent.con_song:
            agent.health = max(0.0, agent.health - loss)
    if w.dau_nam():
        w.events.ghi(w.tick, "dich_benh", mat_suc_khoe=loss)
