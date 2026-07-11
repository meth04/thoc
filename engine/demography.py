"""Nhân khẩu: cưới, sinh, chết (đói/Gompertz/sinh nở), thừa kế mặc định (SPEC 2.7–2.8)."""

from __future__ import annotations

import math

import numpy as np

from engine.intents import KeHoach
from engine.types import Agent, Persona
from engine.world import VO_THUA_NHAN, World

TAI_SAN_ROI = ("nha", "cong_cu", "may")  # chia round-robin nguyên chiếc
TAI_SAN_CHIA_DEU = ("thoc", "go", "quang_dong", "xu")


def can_huyet(w: World, a: str, b: str) -> bool:
    """Chặn cận huyết: cha mẹ–con, anh chị em ruột/nửa, ông bà–cháu."""
    ag, bg = w.agents[a], w.agents[b]
    if b in (ag.cha, ag.me) or a in (bg.cha, bg.me):
        return True
    if ag.cha is not None and ag.cha == bg.cha:
        return True
    if ag.me is not None and ag.me == bg.me:
        return True
    ong_ba_a = {
        p
        for pid in (ag.cha, ag.me)
        if pid and pid in w.agents
        for p in (w.agents[pid].cha, w.agents[pid].me)
        if p
    }
    if b in ong_ba_a:
        return True
    ong_ba_b = {
        p
        for pid in (bg.cha, bg.me)
        if pid and pid in w.agents
        for p in (w.agents[pid].cha, w.agents[pid].me)
        if p
    }
    return a in ong_ba_b


def xu_ly_cau_hon(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    """Cầu hôn là intent; bên kia trả lời TICK SAU (SPEC 2.7)."""
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")

    # 1) Trả lời các đề nghị đã chờ từ tick trước
    con_cho: list[tuple[str, str, int]] = []
    for tu, den, tick_gui in w.cau_hon_cho:
        a, b = w.agents.get(tu), w.agents.get(den)
        if not a or not b or not a.con_song or not b.con_song:
            continue
        if a.vo_chong or b.vo_chong:
            continue
        kh = ke_hoach.get(den)
        tra_loi = kh.tra_loi_cau_hon.get(tu) if kh else None
        if tra_loi is None:
            if w.tick - tick_gui < 2:
                con_cho.append((tu, den, tick_gui))
            continue
        if tra_loi:
            a.vo_chong, b.vo_chong = den, tu
            w.cong_quan_he(tu, den, 1.0)
            w.events.ghi(w.tick, "cuoi", vo=den if b.gioi_tinh == "nu" else tu,
                         chong=tu if a.gioi_tinh == "nam" else den)
    w.cau_hon_cho = con_cho

    # 2) Nhận đề nghị mới từ kế hoạch tick này
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not kh.cau_hon:
            continue
        a = w.agents.get(aid)
        b = w.agents.get(kh.cau_hon)
        if not a or not b or not a.con_song or not b.con_song:
            continue
        if not a.truong_thanh(tt) or not b.truong_thanh(tt):
            continue
        if a.vo_chong or b.vo_chong or a.gioi_tinh == b.gioi_tinh:
            continue
        if can_huyet(w, aid, kh.cau_hon):
            continue  # engine chặn cận huyết
        w.cau_hon_cho.append((aid, kh.cau_hon, w.tick))
        w.events.ghi(w.tick, "cau_hon", tu=aid, den=kh.cau_hon)


def sinh_con(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    ss = w.cfg.get("nhan_khau.sinh_san")
    nc = w.cfg.raw()["nhu_cau"]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    g = w.rng.get("sinh_con", w.tick)
    for aid in sorted(w.agents):
        me = w.agents[aid]
        if not (me.con_song and me.gioi_tinh == "nu" and me.vo_chong):
            continue
        cha = w.agents.get(me.vo_chong)
        if not cha or not cha.con_song:
            continue
        t_min, t_max = ss["tuoi_me"]
        if not (t_min <= me.tuoi_nam <= t_max):
            continue
        kh = ke_hoach.get(aid)
        if kh is not None:
            me.y_dinh_sinh_con = kh.y_dinh_sinh_con
        # an ninh lương thực của hộ: dự trữ / nhu cầu 2 tick
        ho = w.ho_cua(aid)
        du_tru = sum(w.ledger.so_du(m, "thoc") for m in ho)
        nhu_cau = sum(
            nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"]
            for m in ho
        )
        an_ninh = min(1.0, du_tru / (2 * nhu_cau)) if nhu_cau > 0 else 1.0
        p = ss["p_goc"] * an_ninh * me.y_dinh_sinh_con
        if g.random() >= p:
            continue
        # sinh nở — rủi ro giảm nếu mua được dịch vụ y tế (blueprint y_te trong làng)
        rui_ro = ss["rui_ro_me"]
        thay_thuoc = next(
            (bp.chu for bp in w.blueprints.values()
             if bp.linh_vuc == "y_te" and bp.chu in w.agents
             and w.agents[bp.chu].con_song),
            None,
        )
        if thay_thuoc and thay_thuoc != aid and w.ledger.so_du(aid, "thoc") >= 20:
            from engine.research import duoc_ap_dung

            w.ledger.chuyen(aid, thay_thuoc, "thoc", 20.0, "dịch vụ đỡ đẻ", w.tick)
            w.ghi_thu_nhap(thay_thuoc, "dich_vu", 20.0)
            rui_ro *= max(0.2, 1.0 - duoc_ap_dung(w, thay_thuoc, "y_te"))
        if g.random() < rui_ro:
            me.health = 0.0  # tử vong sinh nở — xử lý ở bước chết
            w.events.ghi(w.tick, "tu_vong_sinh_no", id=aid)
        cid = w.id_moi()
        pa, pb = cha.persona.as_dict(), me.persona.as_dict()
        # persona = trung bình cha mẹ ± đột biến 2 (seeded)
        gia_tri = {
            k: int(np.clip(round((pa[k] + pb[k]) / 2 + g.integers(-2, 3)), 1, 9)) for k in pa
        }
        con = Agent(
            id=cid,
            ten=f"Con {cid[1:]}",
            gioi_tinh="nu" if g.random() < w.cfg.get("nhan_khau.ty_le_nu") else "nam",
            tuoi_tick=0,
            persona=Persona(**gia_tri),
            lang=me.lang,
            cha=cha.id,
            me=me.id,
        )
        w.agents[cid] = con
        cha.con.append(cid)
        me.con.append(cid)
        w.events.ghi(w.tick, "sinh", id=cid, cha=cha.id, me=me.id)


def _q_nam(tuoi: float, gp: dict[str, float]) -> float:
    """Gompertz nội suy log-linear giữa các mốc q20/q60/q75; ngoài 75 ngoại suy."""
    q20, q60, q75 = gp["q20"], gp["q60"], gp["q75"]
    if tuoi <= 20:
        return q20
    if tuoi <= 60:
        t = (tuoi - 20) / 40
        return math.exp(math.log(q20) * (1 - t) + math.log(q60) * t)
    if tuoi <= 75:
        t = (tuoi - 60) / 15
        return math.exp(math.log(q60) * (1 - t) + math.log(q75) * t)
    do_doc = (math.log(q75) - math.log(q60)) / 15
    return min(0.8, math.exp(math.log(q75) + do_doc * (tuoi - 75)))


def cai_chet(w: World) -> list[str]:
    sk = w.cfg.raw()["suc_khoe"]
    gp = w.cfg.get("nhan_khau.tu_vong_gompertz")
    g = w.rng.get("tu_vong", w.tick)
    chet: list[str] = []
    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song:
            continue
        ly_do = None
        if a.health <= 0:
            ly_do = "kiet_suc"
        elif a.health < sk["nguong_nguy_kich"] and g.random() < sk["p_chet_khi_nguy_kich"]:
            ly_do = "doi_benh"
        else:
            q_tick = 1 - (1 - _q_nam(a.tuoi_nam, gp)) ** 0.5
            if g.random() < q_tick:
                ly_do = "tuoi_gia"
        if ly_do:
            a.con_song = False
            chet.append(aid)
            w.events.ghi(w.tick, "chet", id=aid, tuoi=round(a.tuoi_nam, 1), ly_do=ly_do)
    return chet


def thua_ke_mac_dinh(w: World, aid: str) -> None:
    """Thừa kế: theo DI CHÚC nếu có (phần trăm tự do); không di chúc → chia đều con
    → vợ/chồng → đất về công, của rơi vào VO_THUA_NHAN."""
    a = w.agents[aid]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    ty_trong: dict[str, float] | None = None
    if a.di_chuc and a.di_chuc.get("phan_bo"):
        hop_le = {
            nid: max(0.0, float(pct))
            for nid, pct in a.di_chuc["phan_bo"].items()
            if nid in w.agents and w.agents[nid].con_song
        }
        tong = sum(hop_le.values())
        if tong > 0:
            ty_trong = {nid: pct / tong for nid, pct in sorted(hop_le.items())}
        # gia huấn truyền đời cho người nhận
        gia_huan = str(a.di_chuc.get("gia_huan", ""))[:400]
        if gia_huan:
            for nid in hop_le:
                w.agents[nid].gia_huan = gia_huan
        w.events.ghi(w.tick, "di_chuc", nguoi_mat=aid, phan_bo=a.di_chuc.get("phan_bo"))
    con_song = [c for c in a.con if c in w.agents and w.agents[c].con_song]
    if ty_trong:
        nguoi_nhan = list(ty_trong)
    elif con_song:
        nguoi_nhan = sorted(con_song)
    elif a.vo_chong and a.vo_chong in w.agents and w.agents[a.vo_chong].con_song:
        nguoi_nhan = [a.vo_chong]
    else:
        nguoi_nhan = []

    # tài sản trong sổ
    tai_san = w.ledger.tai_san_cua(aid)
    for ts, sl in sorted(tai_san.items()):
        if ts == "cong":
            continue  # công bốc hơi, không thừa kế
        if not nguoi_nhan:
            w.ledger.chuyen(aid, VO_THUA_NHAN, ts, sl, f"vô thừa nhận {ts}", w.tick)
        elif ts in TAI_SAN_ROI or ts.startswith("vi_the:"):
            nguyen = int(sl)
            for i in range(nguyen):
                w.ledger.chuyen(
                    aid, nguoi_nhan[i % len(nguoi_nhan)], ts, 1.0, f"thừa kế {ts}", w.tick
                )
            du = sl - nguyen
            if du > 1e-9:
                w.ledger.chuyen(aid, nguoi_nhan[0], ts, du, f"thừa kế {ts} lẻ", w.tick)
        else:
            for nid in nguoi_nhan:
                phan = sl * (ty_trong[nid] if ty_trong else 1.0 / len(nguoi_nhan))
                if phan > 1e-12:
                    w.ledger.chuyen(aid, nid, ts, phan, f"thừa kế {ts}", w.tick)

    # đất: chia round-robin cho người nhận; không ai → về công
    thua_cua = sorted(p.id for p in w.parcels.values() if p.chu == aid)
    for i, pid in enumerate(thua_cua):
        p = w.parcels[pid]
        if nguoi_nhan:
            nhan = nguoi_nhan[i % len(nguoi_nhan)]
            # trẻ chưa trưởng thành vẫn đứng tên (giám hộ tự nhiên bởi hộ)
            p.chu = nhan
        else:
            p.chu = None
            p.homestead_ai, p.homestead_dem = None, 0
    if thua_cua or tai_san:
        w.events.ghi(
            w.tick, "thua_ke", nguoi_mat=aid,
            nguoi_nhan=nguoi_nhan or ["cong"], so_thua=len(thua_cua),
        )
    # goá bụa
    if a.vo_chong and a.vo_chong in w.agents:
        w.agents[a.vo_chong].vo_chong = None
    _ = tt  # (giữ chữ ký ổn định — trẻ em vẫn được đứng tên đất)


def buoc_nhan_khau(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    xu_ly_cau_hon(w, ke_hoach)
    sinh_con(w, ke_hoach)
    for aid in cai_chet(w):
        thua_ke_mac_dinh(w, aid)
