"""Rulebot v0 — heuristic tự cung tự cấp, persona-hóa, tất định theo (seed, agent, tick).

Rulebot là một "mind": chỉ đọc world và trả về KeHoach; engine validate rồi thi hành.
Run đối chứng rule-bot cùng seed là baseline cho run LLM (SPEC quyết định #7).
"""

from __future__ import annotations

import numpy as np

from engine.board import mo_tip_hop_dong
from engine.contracts import (
    ClauseChiaSanLuong,
    ClauseChuyenGiaoDinhKy,
    ClauseChuyenGiaoMotLan,
    ClauseDieuKienSuKien,
    ClauseGopCong,
    ClauseHoanTraTheoYeuCau,
    ClauseKhiPhaVo,
    ClauseQuyenSuDung,
    HopDong,
    ben_hien_tai,
)
from engine.demography import can_huyet
from engine.intents import KeHoach
from engine.market import Lenh
from engine.world import World


class _BoiCanhTick:
    """Cấu trúc dùng chung tính MỘT lần mỗi tick — tránh quét 900 thửa cho từng agent."""

    def __init__(self, w: World):
        self.ruong_cua: dict[str, list] = {}
        self.homestead_cua: dict[str, list] = {}
        dat_cong = []
        for p in w.parcels.values():
            if p.loai != "ruong":
                continue
            if p.chu is not None:
                self.ruong_cua.setdefault(p.chu, []).append(p)
            elif p.homestead_ai is not None:
                self.homestead_cua.setdefault(p.homestead_ai, []).append(p)
            else:
                dat_cong.append(p)
        for ds in self.ruong_cua.values():
            ds.sort(key=lambda p: (-p.mau_mo, p.id))
        for ds in self.homestead_cua.values():
            ds.sort(key=lambda p: (-p.homestead_dem, -p.mau_mo, p.id))
        lang = w.villages[0]
        dat_cong.sort(key=lambda p: (abs(p.r - lang.r) + abs(p.c - lang.c), -p.mau_mo, p.id))
        self.dat_cong = dat_cong
        # đề nghị đang treo của từng người (chống đăng trùng)
        self.dang_treo: set[tuple[str, str]] = set()
        for dn in w.bang_rao.values():
            self.dang_treo.add((dn.tu, "+".join(sorted(c.loai for c in dn.hd.dieu_khoan))))
        # ai điều hành entity nào — MỘT lượt quét sổ (cổ đông lớn nhất còn sống)
        co_phan_cua: dict[str, list[tuple[float, str]]] = {}
        for (ct, ts), v in w.ledger._so_du.items():
            if ts.startswith("co_phan:") and v > 1e-9:
                eid = ts.split(":", 1)[1]
                if ct in w.agents and w.agents[ct].con_song:
                    co_phan_cua.setdefault(eid, []).append((v, ct))
        self.dieu_hanh_cua: dict[str, list[str]] = {}
        for eid, holders in co_phan_cua.items():
            e = w.entities.get(eid)
            if e is None or not e.con_hoat_dong:
                continue
            holders.sort(key=lambda x: (-x[0], x[1]))
            self.dieu_hanh_cua.setdefault(holders[0][1], []).append(eid)
        # hợp đồng đang hiệu lực: mô-típ theo bên + thửa đang cho thuê + công thuê vào
        self.motif_active: set[tuple[str, str]] = set()
        self.thua_dang_thue: set[str] = set()
        self.cong_thue_vao: dict[str, float] = {}
        self.dang_lam_thue: set[str] = set()
        for hd in w.hop_dong.values():
            if hd.trang_thai != "hieu_luc":
                continue
            motif = mo_tip_hop_dong(hd)
            for ben in hd.cac_ben:
                self.motif_active.add((ben_hien_tai(w, hd.id, ben), motif))
            for ck in hd.dieu_khoan:
                if ck.loai == "quyen_su_dung" and ck.tai_san.startswith("thua:"):
                    self.thua_dang_thue.add(ck.tai_san.split(":", 1)[1])
                elif ck.loai == "gop_cong":
                    den = ben_hien_tai(w, hd.id, ck.den)
                    self.cong_thue_vao[den] = (
                        self.cong_thue_vao.get(den, 0.0) + ck.so_cong_moi_tick
                    )
                    self.dang_lam_thue.add(ben_hien_tai(w, hd.id, ck.tu))
        tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
        self.doc_than: dict[str, list[str]] = {"nam": [], "nu": []}
        for b in w.agents.values():
            if b.con_song and b.vo_chong is None and b.truong_thanh(tt):
                self.doc_than[b.gioi_tinh].append(b.id)
        self.doc_than["nam"].sort()
        self.doc_than["nu"].sort()


def _chon_thua_canh(bc: _BoiCanhTick, aid: str, so_thua: int, da_nham: set[str]) -> list[str]:
    """Ưu tiên: thửa mình sở hữu → đất công đang homestead dở → đất công gần làng."""
    ket_qua: list[str] = []
    for nhom in (bc.ruong_cua.get(aid, ()), bc.homestead_cua.get(aid, ()), bc.dat_cong):
        for p in nhom:
            if len(ket_qua) >= so_thua:
                return ket_qua
            if p.id not in da_nham:
                ket_qua.append(p.id)
                da_nham.add(p.id)
    return ket_qua


def quyet_dinh_tat_ca(w: World) -> dict[str, KeHoach]:
    """Kế hoạch cho mọi agent còn sống. Đất công được 'nhắm' tuần tự theo id — tất định."""
    ke_hoach: dict[str, KeHoach] = {}
    da_nham: set[str] = set()
    bc = _BoiCanhTick(w)
    cau_hon_den: dict[str, list[str]] = {}
    for tu, den, _t in w.cau_hon_cho:
        cau_hon_den.setdefault(den, []).append(tu)
    for aid in sorted(w.agents):
        if w.agents[aid].con_song:
            ke_hoach[aid] = ke_hoach_mot_nguoi(w, aid, bc, da_nham, cau_hon_den)
    bo_sung_ke_hoach_entity(w, ke_hoach, bc, da_nham)
    return ke_hoach


def bo_sung_ke_hoach_entity(w: World, ke_hoach: dict[str, KeHoach],
                            bc: _BoiCanhTick, da_nham: set[str]) -> None:
    """Entity chạy việc thường nhật MỖI TICK (canh tác, trả lương, chế tác) —
    như thẻ chính sách; quyết định lớn vẫn qua người điều hành khi họ 'nghĩ'."""
    quan_ly_cua: dict[str, str] = {}
    for mgr, eids in bc.dieu_hanh_cua.items():
        for eid in eids:
            quan_ly_cua[eid] = mgr
    for eid in sorted(quan_ly_cua):
        if eid in ke_hoach:
            continue
        e = w.entities.get(eid)
        if e is None or not e.con_hoat_dong:
            continue
        g = w.rng.get(f"entity_the:{eid}", w.tick)
        kh = _ke_hoach_entity(w, eid, bc, da_nham, g)
        kh.id = eid
        ke_hoach[eid] = kh


def ke_hoach_mot_nguoi(
    w: World, aid: str, bc: _BoiCanhTick, da_nham: set[str],
    cau_hon_den: dict[str, list[str]],
) -> KeHoach:
    """Kế hoạch heuristic đầy đủ cho MỘT agent — lõi chung của rulebot & PersonaBot."""
    cfg = w.cfg
    tt = cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = cfg.raw()["nhu_cau"]
    sx = cfg.raw()["san_xuat"]
    if True:  # giữ thụt lề của thân vòng lặp cũ
        a = w.agents[aid]
        g = w.rng.get(f"rulebot:{aid}", w.tick)
        kh = KeHoach(id=aid)
        p5 = a.persona

        # ---- trẻ em ----
        if not a.truong_thanh(tt):
            cha_me = [p for p in (a.cha, a.me) if p and p in w.agents and w.agents[p].con_song]
            if a.e_bac < 1 and any(w.agents[p].e_bac >= 1 for p in cha_me) and a.tuoi_nam >= 6:
                kh.hoc = True  # học chữ với cha mẹ
            elif a.tuoi_nam >= nc["tre_em_gop_cong_tu_tuoi"] and cha_me:
                kh.gop_cong_cho = cha_me[0]
            return kh

        # ---- hộ & an ninh lương thực ----
        ho = w.ho_cua(aid)
        thoc_ho = sum(w.ledger.so_du(m, "thoc") for m in ho)
        nhu_cau_tick = sum(
            nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"]
            for m in ho
        )
        muc_du_tru = nhu_cau_tick * (1.5 + p5.tiet_kiem / 3.0)
        an_ninh = thoc_ho / muc_du_tru if muc_du_tru > 0 else 1.0

        # ---- mùa mưa: canh tác ----
        if w.mua_mua():
            # vợ canh cùng chồng: người id nhỏ hơn trong cặp canh chính; người kia canh thêm
            thieu = max(0.0, muc_du_tru * 2 - thoc_ho)
            so_thua_can = max(1, min(3, round(thieu / sx["san_luong_goc_kg"] + 0.5)))
            if p5.cham_chi >= 7:
                so_thua_can = 3
            # công thuê vào (hợp đồng góp công đang hiệu lực) → canh thêm được ruộng nhà
            cong_thue_vao = bc.cong_thue_vao.get(aid, 0.0)
            so_ruong_so_huu = len(bc.ruong_cua.get(aid, ()))
            if cong_thue_vao > 0:
                so_thua_can = max(so_thua_can, so_ruong_so_huu)
            toi_da_theo_cong = int(
                (180.0 * (a.health / 100.0) + cong_thue_vao) // sx["cong_moi_thua"]
            )
            # đủ giống + để lại thức ăn 1 tick
            giong = sx["giong_kg_moi_thua"]
            toi_da_theo_giong = int(max(0, (thoc_ho - nhu_cau_tick)) // giong)
            so_thua = min(so_thua_can, toi_da_theo_giong, max(toi_da_theo_cong, 1))
            if so_thua > 0:
                kh.canh_thua = _chon_thua_canh(bc, aid, so_thua, da_nham)
        else:
            # ---- mùa khô: gỗ, chế tác, xây, học ----
            go_co = w.ledger.so_du(aid, "go")
            co_nha_ho = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
            co_cong_cu = w.ledger.so_du(aid, "cong_cu") >= 1.0
            r_nha = sx["recipe"]["nha"]
            r_cu = sx["recipe"]["cong_cu"]
            # chuyên môn hóa theo persona: chăm chỉ tự khai thác/chế; lười thì MUA ở chợ
            tu_lam = p5.cham_chi >= 5
            if not co_nha_ho and an_ninh > 0.4:
                if go_co >= r_nha["go"]:
                    kh.xay_nha = 1
                elif tu_lam:
                    kh.cong_khai_go = 120.0
                # người lười: gỗ sẽ được đặt mua ở khối chợ bên dưới
            elif not co_cong_cu and an_ninh > 0.6 and tu_lam:
                if go_co >= r_cu["go"]:
                    kh.che_tao_cong_cu = 1
                else:
                    kh.cong_khai_go = 80.0
            elif an_ninh > 1.0 and p5.cham_chi >= 6:
                # nghề khai thác chọn theo GIÁ: quặng (20 công/đv) vs gỗ (10 công/đv)
                gia_go_ref = w.gia_gan_nhat("go") or 12.0
                gia_quang_ref = w.gia_gan_nhat("quang_dong") or 40.0
                if gia_quang_ref / 20.0 > gia_go_ref / 10.0 and co_cong_cu:
                    kh.cong_khai_quang = 60.0
                else:
                    kh.cong_khai_go = 60.0  # tích gỗ dư đem bán

            # tự học lên bậc kế tiếp khi no đủ và trọng học
            if a.e_bac < 4 and an_ninh > 0.8 and p5.trong_hoc >= 7:
                kh.hoc = True

        # dạy con học chữ tại nhà
        if a.e_bac >= 1:
            kh.day_cho = [
                c
                for c in a.con
                if c in w.agents
                and w.agents[c].con_song
                and w.agents[c].e_bac < 1
                and w.agents[c].tuoi_nam >= 6
            ]

        # ---- hôn nhân ----
        if a.vo_chong is None and 16 <= a.tuoi_nam <= 45:
            p_cau_hon = 0.15 + 0.04 * p5.hop_tac
            if g.random() < p_cau_hon:
                khac_gioi = "nu" if a.gioi_tinh == "nam" else "nam"
                ung_vien = [
                    bid
                    for bid in bc.doc_than[khac_gioi]
                    if w.agents[bid].lang == a.lang and not can_huyet(w, aid, bid)
                ]
                if ung_vien:
                    kh.cau_hon = ung_vien[int(g.integers(0, len(ung_vien)))]
        # trả lời cầu hôn đang chờ
        for tu in cau_hon_den.get(aid, ()):
            dong_y = a.vo_chong is None and g.random() < (0.35 + 0.06 * p5.hop_tac)
            kh.tra_loi_cau_hon[tu] = bool(dong_y)

        # ---- ý định sinh con ----
        if an_ninh >= 1.2:
            kh.y_dinh_sinh_con = 1.0
        elif an_ninh >= 0.6:
            kh.y_dinh_sinh_con = 0.5
        else:
            kh.y_dinh_sinh_con = 0.0

        # ---- Phase 2: hợp đồng (8 công thức) + chợ ----
        _hop_dong_va_cho(w, a, kh, g, thoc_ho, nhu_cau_tick, an_ninh, bc)

        # ---- Phase 4: R&D, entity, cổ phần, li-xăng, quặng/xu, di chúc, di cư ----
        _phase4_hanh_vi(w, a, kh, g, an_ninh, bc, da_nham)
    return kh


def _phase4_hanh_vi(w: World, a, kh: KeHoach, g, an_ninh: float,
                    bc: _BoiCanhTick, da_nham: set[str]) -> None:
    aid = a.id
    p5 = a.persona
    thoc = w.ledger.so_du(aid, "thoc")
    mua_kho = not w.mua_mua()

    # 1) khai quặng + đúc xu (mùa khô, có công cụ, chăm chỉ)
    if (mua_kho and p5.cham_chi >= 6 and w.ledger.so_du(aid, "cong_cu") >= 1
            and an_ninh > 1.0 and kh.cong_khai_quang == 0 and g.random() < 0.5):
        kh.cong_khai_quang = 60.0
        kh.cong_khai_go = 0.0
    if w.ledger.so_du(aid, "quang_dong") >= 2 and g.random() < 0.4:
        kh.duc_xu = 1

    # 2) đầu tư R&D khi dư dả × trọng học (SPEC 7.5)
    if mua_kho and an_ninh > 1.3 and p5.trong_hoc >= 5 and g.random() < (
            0.1 + 0.05 * p5.trong_hoc):
        cac_lv = ["nong_nghiep", "cong_cu_may_moc", "luu_kho", "che_bien",
                  "y_te", "vat_lieu", "van_chuyen"]
        trong_so = [0.2, 0.3, 0.15, 0.15, 0.08, 0.07, 0.05]
        lv = str(g.choice(cac_lv, p=trong_so))
        kh.nghien_cuu = (lv, 60.0, round(min(thoc * 0.05, 100.0), 0))

    # 3) lập entity: nông dân giàu có MÁY (hoặc nhiều đất + tham vọng) chuyển
    # cơ ngơi thành pháp nhân — góp đất + máy + vốn, thuê người làm quy mô
    dieu_hanh = sorted(bc.dieu_hanh_cua.get(aid, ()))
    ruong_cua_toi = bc.ruong_cua.get(aid, ())
    co_may_rieng = w.ledger.so_du(aid, "may") >= 1
    if (not dieu_hanh and p5.lieu_linh >= 5 and thoc > 3000
            and (co_may_rieng or len(ruong_cua_toi) >= 5) and g.random() < 0.2):
        von_gop: dict[str, float] = {"thoc": round(thoc * 0.5, 0)}
        if co_may_rieng:
            von_gop["may"] = float(int(w.ledger.so_du(aid, "may")))
        # góp các thửa ngoài sức tự canh (giữ lại 3 thửa tốt nhất cho nhà)
        for p in ruong_cua_toi[3:]:
            if p.id not in bc.thua_dang_thue:
                von_gop[f"thua:{p.id}"] = 1.0
        kh.lap_phap_nhan = {
            "ten": f"Hội làm ăn của {a.ten}",
            "co_phan": {aid: 100.0},
            "von_gop": {aid: von_gop},
        }
    # bán bớt cổ phần entity mình lập (hùn hạp qua chợ), mua cổ phần khi liều lĩnh
    for eid in dieu_hanh:
        cp = w.ledger.so_du(aid, f"co_phan:{eid}")
        if cp > 60 and g.random() < 0.3:
            from engine.entities import tai_san_quy_thoc

            gia_mot_cp = max(tai_san_quy_thoc(w, eid) / 100.0, 1.0)
            kh.dat_lenh.append(Lenh(aid, "ban", f"co_phan:{eid}", 20.0,
                                    round(gia_mot_cp * 0.95, 1)))
    if p5.lieu_linh >= 7 and thoc > 2000 and g.random() < 0.15:
        entity_song = [eid for eid, e in w.entities.items() if e.con_hoat_dong]
        if entity_song:
            from engine.entities import tai_san_quy_thoc

            eid = entity_song[int(g.integers(0, len(entity_song)))]
            gia_mot_cp = max(tai_san_quy_thoc(w, eid) / 100.0, 1.0)
            kh.dat_lenh.append(Lenh(aid, "mua", f"co_phan:{eid}", 10.0,
                                    round(gia_mot_cp * 1.05, 1)))

    # 3b) cá nhân có bí quyết máy móc → tự dựng máy (hạt giống xưởng)
    from engine.research import duoc_ap_dung

    if (duoc_ap_dung(w, aid, "cong_cu_may_moc") > 0 and w.ledger.so_du(aid, "may") < 1
            and thoc > 800):
        go, quang, xu = (w.ledger.so_du(aid, ts) for ts in ("go", "quang_dong", "xu"))
        r_may = w.cfg.raw()["research"]["may"]["recipe"]
        if go >= r_may["go"] and (quang >= r_may["quang_hoac_xu"]
                                  or xu >= r_may["quang_hoac_xu"]):
            kh.xay_may = 1
        else:
            gia_go = w.gia_gan_nhat("go") or 12.0
            if go < r_may["go"]:
                kh.dat_lenh.append(Lenh(aid, "mua", "go", round(r_may["go"] - go, 1),
                                        round(gia_go * 1.15, 1)))
            gia_quang = w.gia_gan_nhat("quang_dong") or 40.0
            if quang < r_may["quang_hoac_xu"] and xu < r_may["quang_hoac_xu"]:
                kh.dat_lenh.append(Lenh(aid, "mua", "quang_dong",
                                        round(r_may["quang_hoac_xu"] - quang, 1),
                                        round(gia_quang * 1.15, 1)))

    # 3c) hàng tiện nghi: giàu mua dùng; ai có blueprint che_bien thì chế đem bán
    if w.ten_hang and thoc > 1200 and g.random() < 0.4:
        ma = sorted(w.ten_hang)[int(g.integers(0, len(w.ten_hang)))]
        gia_hang = w.gia_gan_nhat(ma) or 40.0
        kh.dat_lenh.append(Lenh(aid, "mua", ma, 2.0, round(gia_hang * 1.1, 1)))
    bp_che_bien = [bp for bp in w.blueprints.values()
                   if bp.chu == aid and bp.hang_moi]
    for bp in bp_che_bien:
        ton = w.ledger.so_du(aid, bp.hang_moi)
        if ton < 6 and not w.mua_mua():
            kh.che_hang[bp.hang_moi] = kh.che_hang.get(bp.hang_moi, 0) + 4
        if ton >= 1:
            gia_hang = w.gia_gan_nhat(bp.hang_moi) or 40.0
            kh.dat_lenh.append(Lenh(aid, "ban", bp.hang_moi, round(ton, 1),
                                    round(max(gia_hang * 0.9, 15.0), 1)))

    # 4) li-xăng blueprint mình sở hữu (công thức 8)
    bp_cua = [bp for bp in w.blueprints.values()
              if bp.chu == aid and bp.linh_vuc != "che_bien"]
    if bp_cua and g.random() < 0.3:
        bp = bp_cua[int(g.integers(0, len(bp_cua)))]
        _dang_neu_chua_treo(kh, bc, aid, HopDong(
            cac_ben=[aid, "?"], hinh_thuc="mieng", thoi_han=8,
            dieu_khoan=[
                ClauseQuyenSuDung(tai_san=f"blueprint:{bp.id}", tu=aid, den="?"),
                ClauseChuyenGiaoDinhKy(tu="?", den=aid, tai_san="thoc",
                                       so_luong=15.0, moi_n_tick=1),
            ], nguoi_soan=aid))

    # 5) điều hành entity: thuê người, mua đất, dựng máy, canh tác
    for eid in dieu_hanh:
        kh.quyet_dinh_entity.append((eid, _ke_hoach_entity(w, eid, bc, da_nham, g)))

    # 6) di chúc ở mốc tuổi 50 / ốm nặng
    if a.di_chuc is None and (a.tuoi_nam >= 50 or a.health < 30):
        con_song = [c for c in a.con if c in w.agents and w.agents[c].con_song]
        if con_song:
            if p5.tiet_kiem >= 7 and len(con_song) > 1:
                phan_bo = {con_song[0]: 40.0 + 10.0 * (p5.tiet_kiem - 7)}
                con_lai = (100.0 - phan_bo[con_song[0]]) / (len(con_song) - 1)
                for c in con_song[1:]:
                    phan_bo[c] = con_lai
            else:
                phan_bo = {c: 100.0 / len(con_song) for c in con_song}
            cau = ("Cần cù giữ đất, chớ bán ruộng hương hỏa." if p5.tiet_kiem >= 6
                   else "Sống rộng rãi với làng xóm, của cải là phù du.")
            kh.viet_di_chuc = {"phan_bo": phan_bo, "gia_huan": cau}

    # 7) di cư khi đất công quanh làng cạn
    if (len(bc.dat_cong) < 5 and len(bc.ruong_cua.get(aid, ())) == 0
            and p5.lieu_linh >= 8 and g.random() < 0.1):
        kh.di_cu = True


def _dieu_hanh_boi(w: World, eid: str) -> str | None:
    from engine.entities import nguoi_dieu_hanh

    return nguoi_dieu_hanh(w, eid)


def _ke_hoach_entity(w: World, eid: str, bc: _BoiCanhTick, da_nham: set[str], g) -> KeHoach:
    """Kế hoạch nhân danh entity: thuê công, mua đất/vật liệu, dựng máy, canh tác."""
    kh = KeHoach(id=eid)
    thoc = w.ledger.so_du(eid, "thoc")
    ruong = bc.ruong_cua.get(eid, ())
    cong_thue = bc.cong_thue_vao.get(eid, 0.0)

    # thuê người làm: có máy = xưởng, thuê hết cỡ; chưa máy = trại, thuê theo đất
    so_nhan_cong = int(cong_thue // 120)
    co_may = w.ledger.so_du(eid, "may") >= 1
    muc_tieu_nhan_cong = 8 if co_may else min(8, max(2, len(ruong) // 2))
    if thoc > 800 and so_nhan_cong < muc_tieu_nhan_cong:
        # thuê người: TẠM ỨNG khi ký (người đói ăn ngay, giữ sức) + lương mỗi tick
        gia_cong_thue = 2.0 + 0.6 * float(g.random())
        _dang_neu_chua_treo(kh, bc, eid, HopDong(
            cac_ben=[eid, "?"], hinh_thuc="mieng", thoi_han=8,
            dieu_khoan=[
                ClauseChuyenGiaoMotLan(tu=eid, den="?", tai_san="thoc",
                                       so_luong=180.0, tai="ky_ket"),
                ClauseGopCong(tu="?", den=eid, so_cong_moi_tick=100.0),
                ClauseChuyenGiaoDinhKy(tu=eid, den="?", tai_san="thoc",
                                       so_luong=round(100 * gia_cong_thue, 0), moi_n_tick=1),
            ], nguoi_soan=eid))
    # mua đất niêm yết — mở rộng điền sản là ưu tiên số một của entity
    if thoc > 2500 and w.niem_yet_dat:
        re_nhat = min(w.niem_yet_dat.values(), key=lambda ny: (ny.gia_ask, ny.thua))
        if re_nhat.chu != eid and re_nhat.gia_ask <= thoc - 1500:
            kh.tra_gia_dat.append((re_nhat.thua, round(re_nhat.gia_ask * 1.1, 0)))
    # canh tác bằng công thuê: đất entity trước, thiếu thì khai hoang đất công
    if w.mua_mua() and cong_thue > 0:
        so_thua = min(int(cong_thue // 60), int(max(0, thoc - 400) // 60), 10)
        if so_thua > 0:
            kh.canh_thua = _chon_thua_canh(bc, eid, so_thua, da_nham)
    # có máy + công thuê → xưởng: mùa khô chế công cụ/hàng hết công suất
    if co_may and cong_thue >= 60 and not w.mua_mua():
        from engine.production import he_so_may as _hsm

        cong_moi_cu = 60.0 / max(_hsm(w, eid), 1.0)
        suc = max(1, int(cong_thue // cong_moi_cu))
        go_e = w.ledger.so_du(eid, "go")
        kh.che_tao_cong_cu = min(suc, int(go_e // 2))
        if go_e < suc * 2:
            gia_go = w.gia_gan_nhat("go") or 12.0
            kh.dat_lenh.append(Lenh(eid, "mua", "go", round(suc * 2 - go_e, 1),
                                    round(gia_go * 1.1, 1)))
        # chế hàng tiện nghi nếu entity nắm blueprint che_bien
        for bp in w.blueprints.values():
            if bp.chu == eid and bp.hang_moi:
                kh.che_hang[bp.hang_moi] = 4
    ton_cu = w.ledger.so_du(eid, "cong_cu")
    if ton_cu >= 1:
        gia_cu = w.gia_gan_nhat("cong_cu") or 100.0
        kh.dat_lenh.append(Lenh(eid, "ban", "cong_cu", round(ton_cu, 1),
                                round(max(gia_cu * 0.9, 50), 0)))
    # gom vật liệu + dựng MỘT máy khi có blueprint (máy nhân công suất mọi việc)
    from engine.research import duoc_ap_dung

    r_may = w.cfg.raw()["research"]["may"]["recipe"]
    if duoc_ap_dung(w, eid, "cong_cu_may_moc") > 0 and w.ledger.so_du(eid, "may") < 1:
        go, quang, xu = (w.ledger.so_du(eid, ts) for ts in ("go", "quang_dong", "xu"))
        can_kl = float(r_may["quang_hoac_xu"])
        if go >= r_may["go"] and (quang >= can_kl or xu >= can_kl) and cong_thue >= 100:
            kh.xay_may = 1
        elif thoc > 1500:
            gia_go = w.gia_gan_nhat("go") or 12.0
            if go < r_may["go"]:
                kh.dat_lenh.append(Lenh(eid, "mua", "go", round(r_may["go"] - go, 1),
                                        round(gia_go * 1.15, 1)))
            gia_quang = w.gia_gan_nhat("quang_dong") or 40.0
            if quang < can_kl and xu < can_kl:
                kh.dat_lenh.append(Lenh(eid, "mua", "quang_dong", round(can_kl - quang, 1),
                                        round(gia_quang * 1.15, 1)))
    # entity chưa có blueprint máy → R&D chỉ khi đã có điền sản vững (đất ≥4) + vốn dày
    elif len(ruong) >= 4 and thoc > 4000 and g.random() < 0.5:
        kh.nghien_cuu = ("cong_cu_may_moc", min(cong_thue, 120.0), round(thoc * 0.05, 0))
    return kh


# ============================ Phase 2: rulebot v1 ============================


def _so_ruong(w: World, aid: str, bc: _BoiCanhTick) -> int:
    return len(bc.ruong_cua.get(aid, ()))


def _tra_loi_bang_rao(w: World, a, kh: KeHoach, g, thoc: float, an_ninh: float,
                      so_ruong: int, bc: _BoiCanhTick) -> bool:
    """Đánh giá đề nghị trên bảng rao theo mô-típ; trả True nếu đã nhận một cái."""
    p5 = a.persona
    for dn_id in sorted(w.bang_rao):
        dn = w.bang_rao[dn_id]
        if dn.tu == a.id or (dn.den is not None and dn.den != a.id):
            continue
        hd = dn.hd
        motif = dn.motif
        nhan = False
        if "gop_cong" in motif and "chuyen_giao_dinh_ky" in motif:
            gop = next(c for c in hd.dieu_khoan if c.loai == "gop_cong")
            tra = next(c for c in hd.dieu_khoan if c.loai == "chuyen_giao_dinh_ky")
            gia_cong = tra.so_luong / max(gop.so_cong_moi_tick, 1e-9)
            if gop.tu == "?":
                # bên kia TUYỂN người làm: khi đất công cạn, người ít đất sống bằng lương
                dat_con = len(bc.dat_cong)
                gia_cong_moi_cong = tra.so_luong / max(
                    gop.so_cong_moi_tick * tra.moi_n_tick, 1e-9)
                da_co_viec = a.id in bc.dang_lam_thue
                nhan = (
                    not da_co_viec  # 120 công/việc — nhận 2 việc là vỡ nợ công ngay
                    and tra.tai_san == "thoc"
                    and gia_cong_moi_cong >= 1.6 + 0.1 * p5.cham_chi
                    and (
                        # người ít đất tuổi lao động: lương xưởng > canh 1 thửa lẻ
                        (so_ruong <= 1 and a.tuoi_nam <= 35)
                        or (so_ruong <= 1 and (dat_con < 40 or an_ninh < 1.0))
                        or (so_ruong <= 2 and dat_con == 0)
                    )
                )
            else:
                # người khác xin làm công cho "?": tôi thuê nếu nhiều đất + dư thóc
                nhan = (
                    so_ruong >= 4
                    and an_ninh > 1.2
                    and gia_cong <= 3.0 + 0.35 * p5.hop_tac
                    and tra.tai_san == "thoc"
                )
        elif motif == "chia_san_luong+quyen_su_dung":
            chia = next(c for c in hd.dieu_khoan if c.loai == "chia_san_luong")
            nhan = so_ruong == 0 and chia.ty_le <= 0.5
        elif motif == "chuyen_giao_dinh_ky+quyen_su_dung":
            qsd = next(c for c in hd.dieu_khoan if c.loai == "quyen_su_dung")
            to = next(c for c in hd.dieu_khoan if c.loai == "chuyen_giao_dinh_ky")
            if qsd.tai_san.startswith("thua:"):
                # thuê đất tô cố định: nhận nếu không đất và tô < kỳ vọng sản lượng
                to_moi_vu = to.so_luong / max(to.moi_n_tick, 1) * 2
                nhan = so_ruong == 0 and to.tai_san == "thoc" and to_moi_vu <= 350
            elif qsd.tai_san.startswith("blueprint:"):
                # li-xăng sáng chế: nông dân/thợ khấm khá thuê bí quyết
                bp_id = qsd.tai_san.split(":", 1)[1]
                bp = w.blueprints.get(bp_id)
                nhan = (
                    bp is not None
                    and an_ninh > 1.0
                    and to.so_luong <= 25
                    and (bp.linh_vuc != "nong_nghiep" or so_ruong >= 1)
                )
        elif "hoan_tra_theo_yeu_cau" in motif:
            nhan = p5.hop_tac >= 6 and an_ninh > 1.0
        elif motif in ("chuyen_giao_mot_lan+chuyen_giao_mot_lan",
                       "chuyen_giao_mot_lan+chuyen_giao_mot_lan+khi_pha_vo"):
            giai_ngan = next(
                (c for c in hd.dieu_khoan
                 if c.loai == "chuyen_giao_mot_lan" and c.tai == "ky_ket"), None
            )
            hoan = next(
                (c for c in hd.dieu_khoan
                 if c.loai == "chuyen_giao_mot_lan" and c.tai == "dao_han"), None
            )
            if giai_ngan is not None and hoan is not None and giai_ngan.tai_san == "thoc":
                lai = hoan.so_luong / max(giai_ngan.so_luong, 1e-9)
                nhan = (
                    thoc > 5 * giai_ngan.so_luong
                    and lai >= 1.1
                    and (bool(hd.the_chap) or w.uy_tin(a.id, dn.tu) > 0)
                )
        elif "dieu_kien_su_kien" in motif:
            nhan = p5.lieu_linh >= 6 and an_ninh > 1.5  # bán bảo hiểm
        elif motif == "chuyen_giao_dinh_ky+chuyen_giao_mot_lan":
            # nhận niên kim: cầm cục thóc trước, trả dòng nhỏ về sau — dân liều thích
            nhan = p5.lieu_linh >= 5 and an_ninh > 1.0
        if nhan:
            kh.tra_loi_de_nghi[dn_id] = "chap_nhan"
            return True
    return False



def _dang_neu_chua_treo(kh: KeHoach, bc: _BoiCanhTick, aid: str, hd: HopDong,
                        den: str | None = None) -> None:
    """Đăng đề nghị nếu chưa có đề nghị cùng mô-típ đang treo (chống spam bảng rao)."""
    motif = "+".join(sorted(c.loai for c in hd.dieu_khoan))
    if (aid, motif) in bc.dang_treo:
        return
    bc.dang_treo.add((aid, motif))
    kh.de_nghi_hop_dong.append((hd, den))


def _hop_dong_va_cho(w: World, a, kh: KeHoach, g, thoc_ho: float,
                     nhu_cau_tick: float, an_ninh: float, bc: _BoiCanhTick) -> None:
    aid = a.id
    p5 = a.persona
    thoc = w.ledger.so_du(aid, "thoc")
    so_ruong = _so_ruong(w, aid, bc)

    # 0) trả lời bảng rao trước (khớp đầu tiên thắng)
    da_nhan = _tra_loi_bang_rao(w, a, kh, g, thoc, an_ninh, so_ruong, bc)

    # 1) đói → rút tiền gửi / vay / xin làm thuê
    if an_ninh < 0.5:
        for hd in w.hop_dong.values():
            if hd.trang_thai != "hieu_luc":
                continue
            for ck in hd.dieu_khoan:
                if ck.loai == "hoan_tra_theo_yeu_cau" and ben_hien_tai(w, hd.id, ck.den) == aid:
                    kh.yeu_cau_rut[hd.id] = min(ck.tran_rut_moi_tick,
                                                max(nhu_cau_tick * 2 - thoc, 0))
        if not kh.yeu_cau_rut and not da_nhan and g.random() < 0.6:
            khoan_vay = round(max(nhu_cau_tick * 2, 100.0), 0)
            dieu_khoan = [
                ClauseChuyenGiaoMotLan(tu="?", den=aid, tai_san="thoc",
                                       so_luong=khoan_vay, tai="ky_ket"),
                ClauseChuyenGiaoMotLan(tu=aid, den="?", tai_san="thoc",
                                       so_luong=round(khoan_vay * 1.3, 0), tai="dao_han"),
            ]
            the_chap: list[str] = []
            hinh_thuc = "mieng"
            if a.e_bac >= 1 and so_ruong >= 1:
                hinh_thuc = "van_ban"
                the_chap = [f"thua:{bc.ruong_cua[aid][-1].id}"]
                dieu_khoan.append(ClauseKhiPhaVo(phat="xiet_the_chap"))
            _dang_neu_chua_treo(kh, bc, aid, HopDong(
                cac_ben=[aid, "?"], hinh_thuc=hinh_thuc, thoi_han=4,
                the_chap=the_chap, dieu_khoan=dieu_khoan, nguoi_soan=aid))

    # 2) không đất → xin làm thuê (đổi công lấy thóc)
    if so_ruong == 0 and an_ninh < 1.0 and not da_nhan and g.random() < 0.5:
        gia_cong = round(2.5 + 0.2 * p5.cham_chi + float(g.random()), 1)
        _dang_neu_chua_treo(kh, bc, aid, HopDong(
            cac_ben=[aid, "?"], hinh_thuc="mieng", thoi_han=4,
            dieu_khoan=[
                ClauseGopCong(tu=aid, den="?", so_cong_moi_tick=120.0),
                ClauseChuyenGiaoDinhKy(tu="?", den=aid, tai_san="thoc",
                                       so_luong=round(120 * gia_cong, 0), moi_n_tick=1),
            ], nguoi_soan=aid))

    # 3) nhiều đất canh không xuể → mời cấy rẽ / tô cố định (chỉ thửa CHƯA cho thuê)
    thua_ranh = [p for p in bc.ruong_cua.get(aid, ())[3:] if p.id not in bc.thua_dang_thue]
    if thua_ranh and g.random() < 0.5:
        thua_du = thua_ranh[0]
        if p5.tiet_kiem >= 6:
            dieu_khoan = [
                ClauseQuyenSuDung(tai_san=f"thua:{thua_du.id}", tu=aid, den="?"),
                ClauseChuyenGiaoDinhKy(tu="?", den=aid, tai_san="thoc",
                                       so_luong=180.0, moi_n_tick=2),
            ]
        else:
            dieu_khoan = [
                ClauseQuyenSuDung(tai_san=f"thua:{thua_du.id}", tu=aid, den="?"),
                ClauseChiaSanLuong(nguon=f"thua:{thua_du.id}", ty_le=0.4, den=aid),
            ]
        _dang_neu_chua_treo(kh, bc, aid, HopDong(
            cac_ben=[aid, "?"], hinh_thuc="mieng", thoi_han=8,
            dieu_khoan=dieu_khoan, nguoi_soan=aid))

    # 4) giàu + tiết kiệm → gửi có kỳ rút (mô-típ gửi-rút)
    if thoc > 6 * nhu_cau_tick and p5.tiet_kiem >= 7 and g.random() < 0.25:
        khoan_gui = round(thoc * 0.2, 0)
        _dang_neu_chua_treo(kh, bc, aid, HopDong(
            cac_ben=[aid, "?"], hinh_thuc="mieng", thoi_han=None, bao_truoc=2,
            dieu_khoan=[
                ClauseChuyenGiaoMotLan(tu=aid, den="?", tai_san="thoc",
                                       so_luong=khoan_gui, tai="ky_ket"),
                ClauseHoanTraTheoYeuCau(tu="?", den=aid, tai_san="thoc",
                                        tran_rut_moi_tick=round(khoan_gui / 2, 0)),
            ], nguoi_soan=aid))

    # 4b) niên kim dưỡng già: già + của để dành → đổi cục tiền lấy dòng thóc trọn đời
    if (a.tuoi_nam >= 50 and thoc > 2500 and p5.tiet_kiem >= 5
            and (aid, "chuyen_giao_dinh_ky+chuyen_giao_mot_lan") not in bc.motif_active):
        _dang_neu_chua_treo(kh, bc, aid, HopDong(
            cac_ben=[aid, "?"], hinh_thuc="mieng", thoi_han=None, bao_truoc=2,
            dieu_khoan=[
                ClauseChuyenGiaoMotLan(tu=aid, den="?", tai_san="thoc",
                                       so_luong=1000.0, tai="ky_ket"),
                ClauseChuyenGiaoDinhKy(tu="?", den=aid, tai_san="thoc",
                                       so_luong=40.0, moi_n_tick=1),
            ], nguoi_soan=aid))

    # 5) sợ rủi ro + có ruộng → mua bảo hiểm mùa màng (tái tục khi hết hạn)
    if (so_ruong >= 1 and p5.lieu_linh <= 4 and an_ninh > 0.5
            and (aid, "chuyen_giao_dinh_ky+dieu_kien_su_kien") not in bc.motif_active):
        _dang_neu_chua_treo(kh, bc, aid, HopDong(
            cac_ben=[aid, "?"], hinh_thuc="mieng", thoi_han=8,
            dieu_khoan=[
                ClauseChuyenGiaoDinhKy(tu=aid, den="?", tai_san="thoc",
                                       so_luong=10.0, moi_n_tick=1),
                ClauseDieuKienSuKien(
                    neu={"loai": "han_lu"},
                    thi=ClauseChuyenGiaoMotLan(tu="?", den=aid, tai_san="thoc",
                                               so_luong=250.0, tai="ky_ket"),
                ),
            ], nguoi_soan=aid))

    # 6) chợ: gỗ, công cụ, đất — phân công theo persona:
    # người lười tự khai thác thì MUA, người chăm khai thác dư thì BÁN; công cụ hao mòn
    # 5%/tick nên cầu tái diễn liên tục — đây là dòng máu của chợ làng.
    go_co = w.ledger.so_du(aid, "go")
    gia_go = w.gia_gan_nhat("go") or 12.0
    co_nha_ho = any(w.ledger.so_du(m, "nha") >= 1.0 for m in w.ho_cua(aid))
    can_go = (not co_nha_ho) or kh.che_tao_cong_cu or go_co < 2
    if kh.cong_khai_go == 0 and can_go and go_co < 6 and thoc > 400 and p5.cham_chi <= 4:
        kh.dat_lenh.append(Lenh(aid, "mua", "go", 4.0,
                                round(gia_go * (1.0 + 0.05 * p5.lieu_linh), 1)))
    if go_co > 4 and p5.cham_chi >= 5:
        kh.dat_lenh.append(Lenh(aid, "ban", "go", round(go_co - 3, 1),
                                round(max(gia_go * (0.85 + 0.03 * p5.tiet_kiem), 3.0), 1)))
    quang_co = w.ledger.so_du(aid, "quang_dong")
    if quang_co > 3:
        gia_quang = w.gia_gan_nhat("quang_dong") or 40.0
        kh.dat_lenh.append(Lenh(aid, "ban", "quang_dong", round(quang_co - 2, 1),
                                round(gia_quang * 0.9, 1)))
    # chợ nhà: vô gia cư có tiền thì MUA; thợ dựng nhà thừa đem bán
    co_nha = any(w.ledger.so_du(m, "nha") >= 1.0 for m in w.ho_cua(aid))
    gia_nha = w.gia_gan_nhat("nha") or 450.0
    if not co_nha and thoc > gia_nha * 1.3:
        kh.dat_lenh.append(Lenh(aid, "mua", "nha", 1.0, round(gia_nha * 1.1, 0)))
    if co_nha and p5.cham_chi >= 7 and not w.mua_mua():
        so_nha = w.ledger.so_du(aid, "nha")
        if so_nha >= 2:
            kh.dat_lenh.append(Lenh(aid, "ban", "nha", round(so_nha - 1, 1),
                                    round(max(gia_nha * 0.95, 350), 0)))
        elif w.ledger.so_du(aid, "go") >= 6 and an_ninh > 1.2 and g.random() < 0.3:
            kh.xay_nha = max(kh.xay_nha, 1)

    cong_cu_co = w.ledger.so_du(aid, "cong_cu")
    gia_cu = w.gia_gan_nhat("cong_cu") or 100.0
    if cong_cu_co < 1 and thoc > 500:
        kh.dat_lenh.append(Lenh(aid, "mua", "cong_cu", 1.0,
                                round(gia_cu * (1.0 + 0.03 * p5.lieu_linh), 0)))
    if cong_cu_co >= 2:
        kh.dat_lenh.append(Lenh(aid, "ban", "cong_cu", round(cong_cu_co - 1, 2),
                                round(max(gia_cu * 0.9, 40), 0)))
    # thợ chăm chỉ chuyên chế công cụ để bán (nghề thủ công tự phát)
    if not w.mua_mua() and p5.cham_chi >= 6 and cong_cu_co < 3:
        if go_co >= 4:
            kh.che_tao_cong_cu = max(kh.che_tao_cong_cu, 1)
        elif kh.cong_khai_go == 0 and an_ninh > 0.8:
            kh.cong_khai_go = 60.0

    # thóc đổi gỗ hai chiều — giá thóc (theo gỗ) nổi theo đói kém
    gia_thoc_go = w.gia_gan_nhat("thoc/go") or (1.0 / gia_go)
    if an_ninh < 0.8 and go_co >= 1 and thoc < nhu_cau_tick * 2:
        do_doi = min(1.0, 0.8 - an_ninh + 0.2)
        kh.dat_lenh.append(Lenh(aid, "mua", "thoc", round(nhu_cau_tick, 0),
                                round(gia_thoc_go * (1.0 + do_doi), 4), thanh_toan="go"))
    elif an_ninh > 2.5 and p5.tiet_kiem <= 6 and g.random() < 0.3:
        kh.dat_lenh.append(Lenh(aid, "ban", "thoc", round(thoc * 0.05, 0),
                                round(gia_thoc_go * 0.95, 4), thanh_toan="go"))

    # đất: túng quẫn bán thửa; nhiều đất canh không xuể bán bớt giá cao; giàu mua
    gia_dat_ref = w.gia_gan_nhat("dat") or 600.0
    if an_ninh < 0.3 and so_ruong >= 2:
        thua_ban = bc.ruong_cua[aid][-1]
        kh.niem_yet_dat.append((thua_ban.id, round(gia_dat_ref * (0.8 + p5.tiet_kiem * 0.05), 0)))
    elif so_ruong >= 5 and p5.tiet_kiem <= 6 and g.random() < 0.2:
        thua_ban = bc.ruong_cua[aid][-1]
        if thua_ban.id not in bc.thua_dang_thue:
            kh.niem_yet_dat.append((thua_ban.id, round(gia_dat_ref * 1.2, 0)))
    if thoc > 3000 and p5.lieu_linh >= 5 and w.niem_yet_dat:
        re_nhat = min(w.niem_yet_dat.values(), key=lambda ny: (ny.gia_ask, ny.thua))
        if re_nhat.chu != aid and re_nhat.gia_ask <= thoc * 0.4:
            kh.tra_gia_dat.append((re_nhat.thua, float(np.ceil(re_nhat.gia_ask))))
