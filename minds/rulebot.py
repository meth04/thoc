"""Rulebot v0 — heuristic tự cung tự cấp, persona-hóa, tất định theo (seed, agent, tick).

Rulebot là một "mind": chỉ đọc world và trả về KeHoach; engine validate rồi thi hành.
Run đối chứng rule-bot cùng seed là baseline cho run LLM (SPEC quyết định #7).
"""

from __future__ import annotations

from engine.demography import can_huyet
from engine.intents import KeHoach
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
            # đủ giống + để lại thức ăn 1 tick
            giong = sx["giong_kg_moi_thua"]
            toi_da_theo_giong = int(max(0, (thoc_ho - nhu_cau_tick)) // giong)
            so_thua = min(so_thua_can, toi_da_theo_giong, 3)
            if so_thua > 0:
                kh.canh_thua = _chon_thua_canh(bc, aid, so_thua, da_nham)
        else:
            # ---- mùa khô: gỗ, chế tác, xây, học ----
            go_co = w.ledger.so_du(aid, "go")
            co_nha_ho = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
            co_cong_cu = w.ledger.so_du(aid, "cong_cu") >= 1.0
            r_nha = sx["recipe"]["nha"]
            r_cu = sx["recipe"]["cong_cu"]
            if not co_nha_ho and an_ninh > 0.4:
                if go_co >= r_nha["go"]:
                    kh.xay_nha = 1
                else:
                    kh.cong_khai_go = 120.0
            elif not co_cong_cu and an_ninh > 0.6 and p5.cham_chi >= 3:
                if go_co >= r_cu["go"]:
                    kh.che_tao_cong_cu = 1
                else:
                    kh.cong_khai_go = 80.0
            elif an_ninh > 1.0 and p5.cham_chi >= 6:
                kh.cong_khai_go = 60.0  # tích gỗ dư

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

    return ke_hoach
