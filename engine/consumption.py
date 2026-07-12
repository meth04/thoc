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
    for (chu_the, ts), v in list(w.ledger._so_du.items()):
        if ts == "thoc" and v > 0:
            giam = duoc_ap_dung(w, chu_the, "luu_kho")
            for ma, do_lon in hieu_ung_hang.items():
                if w.ledger.so_du(chu_the, ma) >= 1.0:
                    giam += do_lon
            san = float(w.cfg.get("tieu_dung.san_hao_kho"))
            ty_le = ty_le_goc * max(san, 1.0 - giam)
            w.ledger.huy(chu_the, "thoc", v * ty_le, "hao_kho", "hao hụt kho", w.tick)


def an_va_suc_khoe(w: World) -> None:
    nc = w.cfg.raw()["nhu_cau"]
    sk = w.cfg.raw()["suc_khoe"]
    td = w.cfg.raw()["tieu_dung"]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")

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
        nhu_cau_tung_nguoi = {
            m: (nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"])
            for m in ho
        }
        tong_nhu_cau = sum(nhu_cau_tung_nguoi.values())
        ton_kho = {m: w.ledger.so_du(m, "thoc") for m in ho}
        tong_ton = sum(ton_kho.values())
        an_duoc = min(tong_nhu_cau, tong_ton)
        # trừ kho: người nhiều thóc trước
        con_phai_tru = an_duoc
        for m in sorted(ho, key=lambda x: -ton_kho[x]):
            tru = min(ton_kho[m], con_phai_tru)
            if tru > 0:
                w.ledger.huy(m, "thoc", tru, "an", "ăn", w.tick)
                con_phai_tru -= tru
        # thiếu thóc → ăn THỊT rồi CÁ (đậm dinh dưỡng hơn thóc, nhưng mau hỏng)
        if an_duoc < tong_nhu_cau - 1e-9:
            thieu = tong_nhu_cau - an_duoc
            for ts, quy_doi in (
                ("thit", float(w.cfg.raw()["chan_nuoi"]["thit_quy_doi_dinh_duong"])),
                ("ca", float(w.cfg.raw()["danh_ca"]["ca_quy_doi_dinh_duong"])),
            ):
                for m in ho:
                    co = w.ledger.so_du(m, ts)
                    if co <= 0 or thieu <= 1e-9:
                        continue
                    an_them = min(co, thieu / quy_doi)
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
                ag.health = min(100.0, ag.health + sk["hoi_khi_an_du"])
            else:
                mat = sk["mat_toi_da_khi_doi"] * (1.0 - ty_le_no)
                ag.health = max(0.0, ag.health - mat)
                ag.doi_tick = w.tick  # đánh dấu vừa thiếu ăn — phân loại cái chết đúng
                if ty_le_no < float(td["nguong_an_doi_event"]):
                    w.events.ghi(w.tick, "an_doi", id=m, ty_le_no=round(ty_le_no, 2))

    # Vô gia cư: hộ không sở hữu nhà nào → mùa mưa mất health
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
