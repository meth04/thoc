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
        # hợp đồng đang hiệu lực: mô-típ theo bên + thửa đang cho thuê + công thuê vào
        self.motif_active: set[tuple[str, str]] = set()
        self.thua_dang_thue: set[str] = set()
        self.cong_thue_vao: dict[str, float] = {}
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
    cfg = w.cfg
    tt = cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = cfg.raw()["nhu_cau"]
    sx = cfg.raw()["san_xuat"]
    ke_hoach: dict[str, KeHoach] = {}
    da_nham: set[str] = set()
    bc = _BoiCanhTick(w)
    cau_hon_den: dict[str, list[str]] = {}
    for tu, den, _t in w.cau_hon_cho:
        cau_hon_den.setdefault(den, []).append(tu)

    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song:
            continue
        g = w.rng.get(f"rulebot:{aid}", w.tick)
        kh = KeHoach(id=aid)
        ke_hoach[aid] = kh
        p5 = a.persona

        # ---- trẻ em ----
        if not a.truong_thanh(tt):
            cha_me = [p for p in (a.cha, a.me) if p and p in w.agents and w.agents[p].con_song]
            if a.e_bac < 1 and any(w.agents[p].e_bac >= 1 for p in cha_me) and a.tuoi_nam >= 6:
                kh.hoc = True  # học chữ với cha mẹ
            elif a.tuoi_nam >= nc["tre_em_gop_cong_tu_tuoi"] and cha_me:
                kh.gop_cong_cho = cha_me[0]
            continue

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

    return ke_hoach


# ============================ Phase 2: rulebot v1 ============================


def _so_ruong(w: World, aid: str, bc: _BoiCanhTick) -> int:
    return len(bc.ruong_cua.get(aid, ()))


def _tra_loi_bang_rao(w: World, a, kh: KeHoach, g, thoc: float, an_ninh: float,
                      so_ruong: int) -> bool:
    """Đánh giá đề nghị trên bảng rao theo mô-típ; trả True nếu đã nhận một cái."""
    p5 = a.persona
    for dn_id in sorted(w.bang_rao):
        dn = w.bang_rao[dn_id]
        if dn.tu == a.id or (dn.den is not None and dn.den != a.id):
            continue
        hd = dn.hd
        motif = dn.motif
        nhan = False
        if motif == "chuyen_giao_dinh_ky+gop_cong":
            # người khác xin làm công cho "?": tôi thuê nếu nhiều đất + dư thóc + giá ổn
            gop = next(c for c in hd.dieu_khoan if c.loai == "gop_cong")
            tra = next(c for c in hd.dieu_khoan if c.loai == "chuyen_giao_dinh_ky")
            gia_cong = tra.so_luong / max(gop.so_cong_moi_tick, 1e-9)
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
            # thuê đất tô cố định: nhận nếu không đất và tô < kỳ vọng sản lượng
            to = next(c for c in hd.dieu_khoan if c.loai == "chuyen_giao_dinh_ky")
            to_moi_vu = to.so_luong / max(to.moi_n_tick, 1) * 2
            nhan = so_ruong == 0 and to.tai_san == "thoc" and to_moi_vu <= 350
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
    da_nhan = _tra_loi_bang_rao(w, a, kh, g, thoc, an_ninh, so_ruong)

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

    # đất: túng quẫn bán thửa; giàu mua
    if an_ninh < 0.3 and so_ruong >= 2:
        thua_ban = bc.ruong_cua[aid][-1]
        gia_dat = w.gia_gan_nhat("dat") or 600.0
        kh.niem_yet_dat.append((thua_ban.id, round(gia_dat * (0.8 + p5.tiet_kiem * 0.05), 0)))
    if thoc > 3000 and p5.lieu_linh >= 5 and w.niem_yet_dat:
        re_nhat = min(w.niem_yet_dat.values(), key=lambda ny: (ny.gia_ask, ny.thua))
        if re_nhat.chu != aid and re_nhat.gia_ask <= thoc * 0.4:
            kh.tra_gia_dat.append((re_nhat.thua, float(np.ceil(re_nhat.gia_ask))))
