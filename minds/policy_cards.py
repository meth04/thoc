"""Thi hành thẻ chính sách cho agent KHÔNG nghĩ trong tick (SPEC 4.2).

Thẻ chỉ làm việc thường nhật: canh tác, ăn, mua bán theo ngưỡng, tự động trả lời
hợp đồng quen thuộc. Thẻ KHÔNG đề nghị hợp đồng mới, không cầu hôn, không mặc cả.
"""

from __future__ import annotations

from engine.intents import KeHoach
from engine.market import Lenh
from engine.world import World
from minds.schemas import TheChinhSach


def thi_hanh_the(w: World, aid: str, the: TheChinhSach, bc, da_nham: set[str]) -> KeHoach:
    from minds.rulebot import _chon_thua_canh

    a = w.agents[aid]
    cfg = w.cfg
    tt = cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = cfg.raw()["nhu_cau"]
    sx = cfg.raw()["san_xuat"]
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
    nhu_cau_tick = sum(
        nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"]
        for m in ho
    )
    muc_du_tru = nhu_cau_tick * the.du_tru_muc_tieu
    an_ninh = thoc_ho / muc_du_tru if muc_du_tru > 0 else 1.0

    if w.mua_mua():
        thieu = max(0.0, muc_du_tru * 2 - thoc_ho)
        so_thua_can = max(1, min(the.canh_toi_da, round(thieu / sx["san_luong_goc_kg"] + 0.5)))
        cong_thue_vao = bc.cong_thue_vao.get(aid, 0.0)
        if cong_thue_vao > 0:
            so_thua_can = max(so_thua_can, len(bc.ruong_cua.get(aid, ())))
        toi_da_cong = int((180.0 * (a.health / 100.0) + cong_thue_vao) // sx["cong_moi_thua"])
        toi_da_giong = int(max(0, thoc_ho - nhu_cau_tick) // sx["giong_kg_moi_thua"])
        so_thua = min(so_thua_can, toi_da_giong, max(toi_da_cong, 1))
        if so_thua > 0:
            kh.canh_thua = _chon_thua_canh(bc, aid, so_thua, da_nham)
    else:
        go_co = w.ledger.so_du(aid, "go")
        co_nha = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
        if not co_nha and go_co >= sx["recipe"]["nha"]["go"]:
            kh.xay_nha = 1
        elif not co_nha and the.khai_go_khi_ranh and an_ninh > 0.4:
            kh.cong_khai_go = 120.0
        if the.hoc_khi_du_an and a.e_bac < 4 and an_ninh > 0.8:
            kh.hoc = True

    if the.day_con and a.e_bac >= 1:
        kh.day_cho = [
            c for c in a.con
            if c in w.agents and w.agents[c].con_song
            and w.agents[c].e_bac < 1 and w.agents[c].tuoi_nam >= 6
        ]

    # mua bán theo ngưỡng thẻ
    if the.mua_cong_cu_khi_hong and w.ledger.so_du(aid, "cong_cu") < 1 and thoc_ho > 500:
        gia_cu = w.gia_gan_nhat("cong_cu") or 100.0
        kh.dat_lenh.append(Lenh(aid, "mua", "cong_cu", 1.0, round(gia_cu * 1.05, 0)))
    if the.ban_go_nguong is not None:
        go_co = w.ledger.so_du(aid, "go")
        if go_co > the.ban_go_nguong:
            gia_go = w.gia_gan_nhat("go") or 12.0
            kh.dat_lenh.append(
                Lenh(aid, "ban", "go", round(go_co - the.ban_go_nguong, 1),
                     round(gia_go * 0.9, 1))
            )
    if the.nguong_rao_dat is not None and an_ninh < the.nguong_rao_dat:
        ruong = bc.ruong_cua.get(aid, ())
        if len(ruong) >= 2:
            gia_dat = w.gia_gan_nhat("dat") or 600.0
            kh.niem_yet_dat.append((ruong[-1].id, round(gia_dat, 0)))

    # phụng dưỡng cha mẹ già thiếu ăn (thẻ mặc định bật)
    if the.phung_duong_cha_me and an_ninh > 1.2:
        for pid in (a.cha, a.me):
            if pid and pid in w.agents:
                cu = w.agents[pid]
                if cu.con_song and cu.tuoi_nam > 60 and w.ledger.so_du(pid, "thoc") < 120:
                    kh.bieu.append((pid, "thoc", 120.0))
    # heuristic sinh tồn tự động — chỉ chạy khi thẻ BẬT an_toan_sinh_ton
    # (LLM tắt được bằng patch: giữ nguyên tắc "thẻ do agent tự đặt", check.md D5)
    if the.an_toan_sinh_ton:
        # đàn gà của thẻ: đói giết ăn, đông bán bớt (việc thường nhật)
        so_ga = w.ledger.so_du(aid, "ga")
        if an_ninh < 0.6 and so_ga >= 2:
            kh.giet_ga = max(kh.giet_ga, 2)
        # túng mà không ruộng → ra sông đánh cá (sinh kế không cần vốn)
        if an_ninh < 0.9 and not bc.ruong_cua.get(aid) and not kh.canh_thua:
            kh.danh_ca_cong = max(kh.danh_ca_cong, 120.0)
        if so_ga > 12:
            gia_ga = w.gia_gan_nhat("ga") or 40.0
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
