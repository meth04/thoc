"""Sản xuất: sinh công, gieo–gặt, khai thác, chế tác, xây, homestead (SPEC 2.5)."""

from __future__ import annotations

from engine.intents import KeHoach
from engine.ledger import LoiSoKep
from engine.world import World


def sinh_cong(w: World) -> None:
    """Công sinh mỗi tick theo health; trẻ ≥10 tuổi góp 30%; không tích trữ qua tick."""
    ngay_cong = w.cfg.get("nhu_cau.ngay_cong_moi_tick")
    tuoi_gop = w.cfg.get("nhu_cau.tre_em_gop_cong_tu_tuoi")
    ty_le_tre = w.cfg.get("nhu_cau.ty_le_cong_tre_em")
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    for a in w.agents.values():
        if not a.con_song:
            continue
        if a.truong_thanh(tt):
            he_so = 1.0
        elif a.tuoi_nam >= tuoi_gop:
            he_so = ty_le_tre
        else:
            continue
        cong = ngay_cong * (a.health / 100.0) * he_so
        if cong > 0:
            w.ledger.sinh(a.id, "cong", cong, "sinh_cong", "công sinh đầu tick", w.tick)


def cong_kha_dung(w: World, aid: str) -> float:
    return w.ledger.so_du(aid, "cong")


def _health_mult(health: float) -> float:
    # Công đã scale theo health; hệ số này chỉ phạt nhẹ thêm (xem DECISIONS.md)
    return 0.5 + 0.5 * (health / 100.0)


def _tool_mult(w: World, aid: str) -> float:
    """Có công cụ → nhân năng suất; công cụ hao mòn 5% mỗi tick DÙNG."""
    if w.ledger.so_du(aid, "cong_cu") >= 1.0:
        return float(w.cfg.get("san_xuat.recipe.cong_cu.tang_nang_suat"))
    return 1.0


def _hao_mon_cong_cu(w: World, aid: str) -> None:
    sl = w.ledger.so_du(aid, "cong_cu")
    if sl >= 1.0:
        hm = float(w.cfg.get("san_xuat.recipe.cong_cu.hao_mon_moi_tick_dung"))
        w.ledger.huy(aid, "cong_cu", min(sl, hm), "hao_mon", "hao mòn công cụ", w.tick)


def thi_hanh_san_xuat(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    """Thi hành kế hoạch sản xuất theo thứ tự id tất định."""
    sx = w.cfg.raw()["san_xuat"]
    _, he_so_tt = w.thoi_tiet(w.tick)
    mua_mua = w.mua_mua()

    # quyền sử dụng thửa theo hợp đồng — tính MỘT lần cho cả tick
    from engine.contracts import ben_hien_tai

    qsd_map: dict[str, set[str]] = {}
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if ck.loai == "quyen_su_dung" and ck.tai_san.startswith("thua:"):
                den = ben_hien_tai(w, hd.id, ck.den)
                qsd_map.setdefault(den, set()).add(ck.tai_san.split(":", 1)[1])

    # 0) Trẻ em góp công cho cha mẹ
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if kh.gop_cong_cho and kh.gop_cong_cho in w.agents:
            sl = w.ledger.so_du(aid, "cong")
            if sl > 0:
                w.ledger.chuyen(aid, kh.gop_cong_cho, "cong", sl, "con góp công", w.tick)

    da_canh_tick_nay: dict[str, str] = {}  # parcel id → người canh

    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        a = w.agents.get(aid)
        if a is None or not a.con_song:
            continue

        # 1) Canh tác (chỉ mùa mưa): gieo + gặt trong cùng tick.
        # Quá 3 thửa: cần công đi thuê (gop_cong); hiệu suất thửa 4+ giữ sàn 0.7.
        if mua_mua and kh.canh_thua:
            duoc_dung = qsd_map.get(aid, set())
            hieu_suat = [1.0, *sx["hieu_suat_thua_2_3"]]
            dung_cong_cu = False
            so_thua_canh = 0
            for pid in kh.canh_thua:
                p = w.parcels.get(pid)
                if p is None or p.loai != "ruong":
                    continue
                if p.chu is not None and p.chu != aid and pid not in duoc_dung:
                    continue  # đất người khác, không có quyền sử dụng
                if pid in da_canh_tick_nay:
                    continue
                try:
                    cong_can = float(sx["cong_moi_thua"])
                    giong = float(sx["giong_kg_moi_thua"])
                    w.ledger.huy(aid, "cong", cong_can, "dung", f"canh {pid}", w.tick)
                    w.ledger.huy(aid, "thoc", giong, "giong", f"gieo {pid}", w.tick)
                except LoiSoKep:
                    continue  # thiếu công/giống → thửa này bỏ
                da_canh_tick_nay[pid] = aid
                hs = hieu_suat[min(so_thua_canh, len(hieu_suat) - 1)]
                so_thua_canh += 1
                dung_cong_cu = dung_cong_cu or w.ledger.so_du(aid, "cong_cu") >= 1.0
                san_luong = (
                    float(sx["san_luong_goc_kg"])
                    * p.mau_mo
                    * he_so_tt
                    * hs
                    * _tool_mult(w, aid)
                    * _health_mult(a.health)
                )
                w.ledger.sinh(aid, "thoc", san_luong, "gat", f"gặt {pid}", w.tick)
                w.gat_tick[pid] = (aid, san_luong)
                w.events.ghi(w.tick, "gat", id=aid, thua=pid, kg=round(san_luong, 1))
                # homestead trên đất công
                if p.chu is None:
                    if p.homestead_ai == aid:
                        p.homestead_dem += 1
                    else:
                        p.homestead_ai, p.homestead_dem = aid, 1
                    if p.homestead_dem >= int(sx["homestead_tick_lien_tiep"]):
                        p.chu = aid
                        p.homestead_ai, p.homestead_dem = None, 0
                        w.events.ghi(w.tick, "homestead", id=aid, thua=pid)
            if dung_cong_cu:
                _hao_mon_cong_cu(w, aid)

        # 2) Khai thác gỗ/quặng
        kt = sx["khai_thac"]
        for tai_san, cong_xin, dinh_muc, luong in (
            ("go", kh.cong_khai_go, float(kt["go_moi_10_cong"]) / 10.0, "khai_thac"),
            ("quang_dong", kh.cong_khai_quang, float(kt["quang_moi_20_cong"]) / 20.0, "khai_mo"),
        ):
            if cong_xin <= 0:
                continue
            # quặng chỉ khai thác được nếu làng có ô mỏ; gỗ cần ô rừng
            loai_o = "mo_dong" if tai_san == "quang_dong" else "rung"
            if not any(p.loai == loai_o for p in w.parcels.values()):
                continue
            cong_co = min(cong_xin, w.ledger.so_du(aid, "cong"))
            if cong_co <= 0:
                continue
            hieu_suat_kt = 1.0 if w.ledger.so_du(aid, "cong_cu") >= 1.0 else float(
                kt["hieu_suat_khong_cong_cu"]
            )
            w.ledger.huy(aid, "cong", cong_co, "dung", f"khai thác {tai_san}", w.tick)
            thu_duoc = cong_co * dinh_muc * hieu_suat_kt
            w.ledger.sinh(aid, tai_san, thu_duoc, luong, f"khai thác {tai_san}", w.tick)
            if w.ledger.so_du(aid, "cong_cu") >= 1.0:
                _hao_mon_cong_cu(w, aid)

        # 3) Chế tác công cụ, xây nhà (recipe vật lý cố định)
        for _ in range(int(kh.che_tao_cong_cu)):
            r = sx["recipe"]["cong_cu"]
            try:
                w.ledger.huy(aid, "cong", float(r["cong"]), "dung", "chế công cụ", w.tick)
                w.ledger.huy(aid, "go", float(r["go"]), "che_tac", "chế công cụ", w.tick)
            except LoiSoKep:
                break
            w.ledger.sinh(aid, "cong_cu", 1.0, "che_tac", "công cụ mới", w.tick)
            w.events.ghi(w.tick, "che_tac", id=aid, mon="cong_cu")
        for _ in range(int(kh.xay_nha)):
            r = sx["recipe"]["nha"]
            try:
                w.ledger.huy(aid, "cong", float(r["cong"]), "dung", "xây nhà", w.tick)
                w.ledger.huy(aid, "go", float(r["go"]), "xay", "xây nhà", w.tick)
            except LoiSoKep:
                break
            w.ledger.sinh(aid, "nha", 1.0, "xay", "nhà mới", w.tick)
            w.events.ghi(w.tick, "xay_nha", id=aid)

    # 4) Reset homestead cho thửa công KHÔNG được canh mùa mưa này
    if mua_mua:
        for p in w.parcels.values():
            if p.chu is None and p.homestead_ai is not None and p.id not in da_canh_tick_nay:
                p.homestead_ai, p.homestead_dem = None, 0
        for pid, aid in da_canh_tick_nay.items():
            w.parcels[pid].nguoi_canh = aid


def boc_hoi_cong(w: World) -> None:
    """Công không tích trữ — bốc hơi cuối tick, bất kể ai đang giữ."""
    giu_cong = [(ct, v) for (ct, ts), v in w.ledger._so_du.items() if ts == "cong" and v > 0]
    for ct, v in giu_cong:
        w.ledger.huy(ct, "cong", v, "boc_hoi", "công bốc hơi cuối tick", w.tick)
