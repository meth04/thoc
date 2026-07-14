"""Sản xuất: sinh công, gieo–gặt, khai thác, chế tác, xây, homestead (SPEC 2.5)."""

from __future__ import annotations

from engine.intents import KeHoach
from engine.ledger import LoiSoKep
from engine.world import World


def sinh_cong(w: World) -> None:
    """Công sinh mỗi tick theo health & TUỔI: trẻ ≥15 phụ giúp 30%; già >60 giảm sức,
    >70 gần như nghỉ hẳn (con cháu phụng dưỡng); không tích trữ qua tick."""
    ngay_cong = w.cfg.get("nhu_cau.ngay_cong_moi_tick")
    tuoi_gop = w.cfg.get("nhu_cau.tre_em_gop_cong_tu_tuoi")
    ty_le_tre = w.cfg.get("nhu_cau.ty_le_cong_tre_em")
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    ld = w.cfg.raw()["lao_dong_theo_tuoi"]
    tuoi_giam = float(ld["tuoi_giam_suc"])
    tuoi_nghi = float(ld["tuoi_nghi"])
    for a in w.agents.values():
        if not a.con_song:
            continue
        if a.tuoi_nam > tuoi_nghi:
            he_so = float(ld["he_so_sau_nghi"])
        elif a.tuoi_nam > tuoi_giam:
            he_so = float(ld["he_so_sau_giam"])
        elif a.truong_thanh(tt):
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


def he_so_may(w: World, aid: str) -> float:
    """Máy nhân năng suất CÔNG của người làm cho chủ máy (SPEC 2.5)."""
    if w.ledger.so_du(aid, "may") < 1.0:
        return 1.0
    from engine.research import duoc_ap_dung

    return 1.0 + duoc_ap_dung(w, aid, "cong_cu_may_moc")


def _he_so_nong(w: World, aid: str) -> float:
    from engine.research import duoc_ap_dung

    return 1.0 + duoc_ap_dung(w, aid, "nong_nghiep")


def _giam_chi_phi_vat_lieu(w: World, aid: str) -> float:
    from engine.research import duoc_ap_dung

    return max(0.5, 1.0 - duoc_ap_dung(w, aid, "vat_lieu"))


def ghi_cong_dung(w: World, muc_dich: str, so_cong: float) -> None:
    """Theo dõi công dùng nông/phi nông — observatory đọc để đo cơ cấu lao động."""
    d = getattr(w, "cong_dung_tick", None)
    if d is None:
        w.cong_dung_tick = d = {}
    d[muc_dich] = d.get(muc_dich, 0.0) + so_cong


def _lam_nguyen_tu(w: World, aid: str, ly_do: str,
                   tieu: list[tuple[str, float, str]],
                   ra: list[tuple[str, float, str]]) -> bool:
    """Recipe NGUYÊN TỬ: thiếu bất kỳ nguyên liệu nào → không trừ gì cả (không mất
    công oan). Trả False khi thiếu."""
    from engine.ledger import DongSinhHuy, Transaction

    try:
        w.ledger.ap_dung(Transaction(
            tick=w.tick, ly_do=ly_do,
            sinh_huy=tuple(
                [DongSinhHuy(aid, ts, -sl, luong) for ts, sl, luong in tieu]
                + [DongSinhHuy(aid, ts, +sl, luong) for ts, sl, luong in ra]
            ),
        ))
        return True
    except LoiSoKep:
        return False


def _ghi_su_co(w: World, aid: str, noi_dung: str) -> None:
    """Việc không thành (thiếu nguyên liệu...) — agent sẽ thấy trong prompt tick sau."""
    a = w.agents.get(aid)
    if a is not None:
        a.su_co = [*a.su_co, noi_dung][-3:]


def _thieu_gi(w: World, aid: str, can: list[tuple[str, float, str]]) -> str:
    thieu = []
    for ts, sl, _l in can:
        co = w.ledger.so_du(aid, ts)
        if co + 1e-9 < sl:
            thieu.append(f"{ts} cần {sl:.0f} chỉ có {co:.0f}")
    return "; ".join(thieu) or "thiếu nguyên liệu"


def _hao_mon_cong_cu(w: World, aid: str) -> None:
    sl = w.ledger.so_du(aid, "cong_cu")
    if sl >= 1.0:
        hm = float(w.cfg.get("san_xuat.recipe.cong_cu.hao_mon_moi_tick_dung"))
        w.ledger.huy(aid, "cong_cu", min(sl, hm), "hao_mon", "hao mòn công cụ", w.tick)


def khai_hoang_dat(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    """ADR 0005 §4.1 — vỡ hoang rừng/đồi CÔNG thành ruộng.

    Tốn công ``khong_gian.khai_hoang.cong_moi_thua`` (NGUYÊN TỬ: thiếu ⇒ skip, không mất
    công); đổi ``loai`` rừng/đồi → ``ruong`` + hạ độ màu về đất mới vỡ. KHÔNG cấp title
    miễn phí: quyền đất vẫn tích qua ĐƯỜNG HOMESTEAD sẵn có (agent phải canh liên tiếp).
    Thửa bờ ``hoang``: agent phải ĐANG Ở bờ kia (đã qua đò — ``co_the_o_bo``) mới vỡ được.
    Gated ``khong_gian.bat``+``khai_hoang.bat``: TẮT (mặc định) ⇒ no-op ⇒ ``p.loai`` bất
    biến ⇒ world_hash legacy y nguyên. Chạy TRƯỚC canh nên đất vỡ canh ngay được tick này.
    """
    from engine.spatial import _khong_gian_bat, co_the_o_bo

    if not _khong_gian_bat(w) or not bool(w.cfg.get("khong_gian.khai_hoang.bat", False)):
        return
    cong_moi = float(w.cfg.get("khong_gian.khai_hoang.cong_moi_thua"))
    mau_mo = float(w.cfg.get("khong_gian.khai_hoang.mau_mo_khai_hoang"))
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not kh.khai_hoang or not w.chu_the_hoat_dong(aid):
            continue
        for pid in sorted(kh.khai_hoang):
            p = w.parcels.get(pid)
            if p is None or p.loai not in ("rung", "doi") or p.chu is not None:
                continue
            if not co_the_o_bo(w, aid, p.bo):
                _ghi_su_co(w, aid, f"khai hoang {pid} bất thành: chưa qua sông tới bờ kia")
                continue
            tieu = [("cong", cong_moi, "dung")]
            if not _lam_nguyen_tu(w, aid, f"khai hoang {pid}", tieu, []):
                _ghi_su_co(w, aid, f"khai hoang {pid} không thành: {_thieu_gi(w, aid, tieu)}")
                continue
            ghi_cong_dung(w, "phi_nong", cong_moi)
            tu_loai = p.loai
            # Only the versioned ecology treatment turns residual forest biomass into wood.
            # Keep legacy event layout byte-for-byte when the P2 gate is off.
            from engine.forest import _rung_bat, thu_hoi_go_khai_hoang

            ecology = _rung_bat(w)
            go_thu_hoi = thu_hoi_go_khai_hoang(w, aid, p) if ecology else 0.0
            p.loai = "ruong"
            p.mau_mo = p.mau_mo_goc = mau_mo
            if ecology:
                w.events.ghi(w.tick, "khai_hoang", id=aid, thua=pid, tu_loai=tu_loai,
                             go_thu_hoi=round(go_thu_hoi, 9))
            else:
                w.events.ghi(w.tick, "khai_hoang", id=aid, thua=pid, tu_loai=tu_loai)
            w.ghi_ky_uc(aid, f"tôi vỡ hoang thửa {pid} ({tu_loai}) thành ruộng", doi=True)


def thi_hanh_san_xuat(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    """Thi hành kế hoạch sản xuất theo thứ tự id tất định."""
    sx = w.cfg.raw()["san_xuat"]
    _, he_so_tt = w.thoi_tiet(w.tick)
    # thủy lợi công (fiscal.bat) giảm thiệt hại hạn/lũ qua ĐƯỜNG TƯỜNG MINH này; TẮT →
    # trả nguyên he_so_tt nên sản lượng + world-hash legacy KHÔNG đổi (ADR 0004 §T08-C)
    from engine import politics

    he_so_tt = politics.he_so_thoi_tiet_thuy_loi(w, he_so_tt)
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

    # 0) Trẻ em góp công cho cha mẹ + biếu tặng (phụng dưỡng, quà cáp)
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        # nhận công phải CÒN HOẠT ĐỘNG — không góp cả tick lao động lên xác cha mẹ
        if kh.gop_cong_cho and w.chu_the_hoat_dong(kh.gop_cong_cho):
            sl = w.ledger.so_du(aid, "cong")
            if sl > 0:
                w.ledger.chuyen(aid, kh.gop_cong_cho, "cong", sl, "con góp công", w.tick)
        for den, ts, sl in kh.bieu:
            if ts == "cong" or not w.chu_the_hoat_dong(den) or den == aid:
                continue
            sl = min(float(sl), w.ledger.so_du(aid, ts))
            if sl > 0:
                w.ledger.chuyen(aid, den, ts, sl, f"biếu {den}", w.tick)
                w.cong_quan_he(aid, den, w.cfg.get("quan_he.cong_moi_tuong_tac"))
                w.events.ghi(w.tick, "bieu", tu=aid, den=den, tai_san=ts,
                             so_luong=round(sl, 1))
                w.ghi_ky_uc(den, f"{aid} biếu tôi {sl:.0f} {ts} — ơn nghĩa phải nhớ")

    # 0.5) Khai hoang rừng/đồi CÔNG bờ kia → ruộng (ADR 0005 §4.1) TRƯỚC canh: đất mới vỡ
    # canh ngay tick này để khởi động homestead. TẮT overlay ⇒ no-op ⇒ hash legacy bất biến.
    khai_hoang_dat(w, ke_hoach)

    da_canh_tick_nay: dict[str, str] = {}  # parcel id → người canh

    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        a = w.agents.get(aid)
        if a is None and not (aid in w.entities and w.entities[aid].con_hoat_dong):
            continue  # entity dùng công góp vào để sản xuất như người
        if a is not None and not a.con_song:
            continue
        health = a.health if a is not None else 100.0

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
                from engine.spatial import co_the_o_bo

                if not co_the_o_bo(w, aid, p.bo):
                    _ghi_su_co(w, aid, f"canh {pid} bất thành: chưa qua sông tới thửa")
                    continue
                # máy nhân năng suất công → cùng một thửa tốn ít công hơn
                cong_can = float(sx["cong_moi_thua"]) / he_so_may(w, aid)
                giong = float(sx["giong_kg_moi_thua"])
                tieu = [("cong", cong_can, "dung"), ("thoc", giong, "giong")]
                if not _lam_nguyen_tu(w, aid, f"canh {pid}", tieu, []):
                    _ghi_su_co(w, aid, f"gieo {pid} không thành: {_thieu_gi(w, aid, tieu)}")
                    continue  # thiếu công/giống → thửa này bỏ, KHÔNG mất gì
                ghi_cong_dung(w, "nong", cong_can)
                da_canh_tick_nay[pid] = aid
                w.canh_tick.add(pid)
                hs = hieu_suat[min(so_thua_canh, len(hieu_suat) - 1)]
                so_thua_canh += 1
                dung_cong_cu = dung_cong_cu or w.ledger.so_du(aid, "cong_cu") >= 1.0
                san_luong = (
                    float(sx["san_luong_goc_kg"])
                    * p.mau_mo
                    * he_so_tt
                    * hs
                    * _tool_mult(w, aid)
                    * _health_mult(health)
                    * _he_so_nong(w, aid)  # blueprint nông nghiệp áp dụng được
                    * (a.tay_nghe if a is not None else 1.0)  # kinh nghiệm đồng áng
                )
                w.ledger.sinh(aid, "thoc", san_luong, "gat", f"gặt {pid}", w.tick)
                # đất canh liên tục bạc màu dần — muốn giữ độ màu phải cho nghỉ
                dd = w.cfg.raw()["dat_dai"]
                goc = p.mau_mo_goc if p.mau_mo_goc > 0 else p.mau_mo
                p.mau_mo = max(goc * float(dd["san_ty_le_mau_mo"]),
                               p.mau_mo * (1.0 - float(dd["thoai_hoa_moi_vu"])))
                w.gat_tick[pid] = (aid, san_luong)
                w.ghi_thu_nhap(aid, "nong", san_luong)
                w.ghi_thu_nhap(aid, "canh_thua_tong", 1.0)  # đếm thửa (đơn vị: thửa)
                if p.chu is not None and p.chu != aid:
                    w.ghi_thu_nhap(aid, "canh_thue_thua", 1.0)
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
                        w.ghi_ky_uc(aid, f"tôi khai hoang xong thửa {pid} — đất của tôi", doi=True)
            if dung_cong_cu:
                _hao_mon_cong_cu(w, aid)
            if so_thua_canh > 0 and a is not None:
                tn = w.cfg.raw()["tay_nghe"]
                a.tay_nghe = min(float(tn["tran"]), a.tay_nghe + float(tn["tang_moi_vu"]))

        # 1b) Vụ đông: mỗi thửa ruộng chỉ một cây khô (ngô HOẶC khoai). Giữ calendar 2
        # tick/năm; không thêm hạt giống/nước/dinh dưỡng chi tiết, nhưng output là tài sản
        # riêng và công/fertility/weather vẫn là ràng buộc vật lý thật.
        if not mua_mua and kh.canh_vu_dong:
            from engine.spatial import _vu_dong_bat, co_the_o_bo

            if _vu_dong_bat(w):
                cay_cfg = w.cfg.get("khong_gian.vu_dong.cay")
                dung_cong_cu = False
                so_thua_canh = 0
                for pid, cay in sorted(kh.canh_vu_dong):
                    p = w.parcels.get(pid)
                    spec = cay_cfg.get(cay)
                    if p is None or p.loai != "ruong" or not isinstance(spec, dict):
                        continue
                    if p.chu is not None and p.chu != aid and pid not in qsd_map.get(aid, set()):
                        continue
                    if pid in da_canh_tick_nay or not co_the_o_bo(w, aid, p.bo):
                        continue
                    cong_can = float(spec["cong"]) / he_so_may(w, aid)
                    if not _lam_nguyen_tu(w, aid, f"canh {cay} {pid}",
                                           [("cong", cong_can, "dung")], []):
                        _ghi_su_co(w, aid, f"canh {cay} {pid} không thành: thiếu công")
                        continue
                    ghi_cong_dung(w, "nong", cong_can)
                    da_canh_tick_nay[pid] = aid
                    w.canh_tick.add(pid)
                    san_luong = (
                        float(spec["san_luong_kg"])
                        * p.mau_mo
                        * he_so_tt
                        * _tool_mult(w, aid)
                        * _health_mult(health)
                        * _he_so_nong(w, aid)
                        * (a.tay_nghe if a is not None else 1.0)
                    )
                    w.ledger.sinh(aid, cay, san_luong, "gat", f"gặt {cay} {pid}", w.tick)
                    dd = w.cfg.raw()["dat_dai"]
                    goc = p.mau_mo_goc if p.mau_mo_goc > 0 else p.mau_mo
                    p.mau_mo = max(
                        goc * float(dd["san_ty_le_mau_mo"]),
                        p.mau_mo * (1.0 - float(dd["thoai_hoa_moi_vu"])),
                    )
                    dung_cong_cu = dung_cong_cu or w.ledger.so_du(aid, "cong_cu") >= 1.0
                    so_thua_canh += 1
                    quy_doi = float(spec["quy_doi_dinh_duong"])
                    w.ghi_thu_nhap(aid, "nong", san_luong * quy_doi)
                    w.thu_hoach_cay_tick.append({
                        "thua": pid, "ai": aid, "cay": cay, "kg": round(san_luong, 6),
                    })
                    w.events.ghi(w.tick, "gat_cay", id=aid, thua=pid, cay=cay,
                                 kg=round(san_luong, 1))
                if dung_cong_cu:
                    _hao_mon_cong_cu(w, aid)
                if so_thua_canh > 0 and a is not None:
                    tn = w.cfg.raw()["tay_nghe"]
                    a.tay_nghe = min(float(tn["tran"]),
                                      a.tay_nghe + float(tn["tang_moi_vu"]))

        # 2) Khai thác gỗ/quặng
        kt = sx["khai_thac"]
        for tai_san, cong_xin, dinh_muc, luong in (
            ("go", kh.cong_khai_go, 1.0 / float(kt["cong_moi_go"]), "khai_thac"),
            ("quang_dong", kh.cong_khai_quang, 1.0 / float(kt["cong_moi_quang"]), "khai_mo"),
        ):
            if cong_xin <= 0:
                continue
            # Quặng cần mỏ, gỗ cần rừng. P2 versioned ecology also makes far-bank access a
            # physical constraint; spatial_v1 remains a legacy control with its old path.
            loai_o = "mo_dong" if tai_san == "quang_dong" else "rung"
            from engine.forest import _rung_bat, khai_thac_go
            from engine.spatial import co_the_o_bo

            ecology = _rung_bat(w)
            if ecology:
                co_nguon = any(
                    p.loai == loai_o and co_the_o_bo(w, aid, p.bo)
                    for p in w.parcels.values()
                )
            else:
                co_nguon = any(p.loai == loai_o for p in w.parcels.values())
            if not co_nguon:
                if ecology:
                    _ghi_su_co(w, aid, f"khai thác {tai_san} không thành: chưa tới nguồn")
                continue
            cong_co = min(cong_xin, w.ledger.so_du(aid, "cong"))
            if cong_co <= 0:
                continue
            hieu_suat_kt = 1.0 if w.ledger.so_du(aid, "cong_cu") >= 1.0 else float(
                kt["hieu_suat_khong_cong_cu"]
            )
            if tai_san == "go" and ecology:
                thu_duoc, cong_dung = khai_thac_go(
                    w,
                    aid,
                    cong_co,
                    dinh_muc * hieu_suat_kt * he_so_may(w, aid),
                )
                if thu_duoc <= 1e-9:
                    _ghi_su_co(w, aid, "khai thác gỗ không thành: rừng tới được đã cạn")
                    continue
                ghi_cong_dung(w, "phi_nong", cong_dung)
            else:
                w.ledger.huy(aid, "cong", cong_co, "dung", f"khai thác {tai_san}", w.tick)
                ghi_cong_dung(w, "phi_nong", cong_co)
                thu_duoc = cong_co * dinh_muc * hieu_suat_kt * he_so_may(w, aid)
                w.ledger.sinh(aid, tai_san, thu_duoc, luong, f"khai thác {tai_san}", w.tick)
            if w.ledger.so_du(aid, "cong_cu") >= 1.0:
                _hao_mon_cong_cu(w, aid)

        # 3) Chế tác công cụ, xây nhà, đúc xu, dựng máy, hàng mới — recipe NGUYÊN TỬ
        giam_vl = _giam_chi_phi_vat_lieu(w, aid)
        he_may = he_so_may(w, aid)
        for _ in range(int(kh.che_tao_cong_cu)):
            r = sx["recipe"]["cong_cu"]
            cong_can = float(r["cong"]) * giam_vl / he_may
            tieu = [("cong", cong_can, "dung"), ("go", float(r["go"]), "che_tac")]
            if not _lam_nguyen_tu(w, aid, "chế công cụ", tieu,
                                  [("cong_cu", 1.0, "che_tac")]):
                _ghi_su_co(w, aid, f"chế công cụ không thành: {_thieu_gi(w, aid, tieu)}")
                break
            ghi_cong_dung(w, "phi_nong", cong_can)
            w.events.ghi(w.tick, "che_tac", id=aid, mon="cong_cu")
        for _ in range(int(kh.xay_nha)):
            r = sx["recipe"]["nha"]
            cong_can = float(r["cong"]) * giam_vl / he_may
            tieu = [("cong", cong_can, "dung"), ("go", float(r["go"]), "xay")]
            if not _lam_nguyen_tu(w, aid, "xây nhà", tieu, [("nha", 1.0, "xay")]):
                _ghi_su_co(w, aid, f"xây nhà không thành: {_thieu_gi(w, aid, tieu)}")
                break
            ghi_cong_dung(w, "phi_nong", cong_can)
            # nhà dựng TRÊN thửa của mình (làng xóm 2D) — ưu tiên thửa gần làng
            ag = w.agents.get(aid)
            if ag is not None and ag.nha_thua is None:
                lang = w.villages[ag.lang if ag.lang < len(w.villages) else 0]
                thua_minh = sorted(
                    (p for p in w.parcels.values() if p.chu == aid),
                    key=lambda p: (abs(p.r - lang.r) + abs(p.c - lang.c), p.id),
                )
                if thua_minh:
                    ag.nha_thua = thua_minh[0].id
            w.events.ghi(w.tick, "xay_nha", id=aid,
                         thua=(ag.nha_thua if ag is not None else None))
        for _ in range(int(kh.duc_xu)):
            r = sx["recipe"]["xu"]
            cong_can = float(r["cong"]) * giam_vl
            tieu = [("cong", cong_can, "dung"),
                    ("quang_dong", float(r["quang_dong"]), "che_tac")]
            if not _lam_nguyen_tu(w, aid, "đúc xu", tieu,
                                  [("xu", float(r["ra"]), "duc_xu")]):
                _ghi_su_co(w, aid, f"đúc xu không thành: {_thieu_gi(w, aid, tieu)}")
                break
            ghi_cong_dung(w, "phi_nong", cong_can)
            w.events.ghi(w.tick, "duc_xu", id=aid, ra=r["ra"])
        # máy: cần blueprint cong_cu_may_moc áp dụng được (SPEC 2.5 + research.yaml)
        for _ in range(int(kh.xay_may)):
            from engine.research import duoc_ap_dung

            if duoc_ap_dung(w, aid, "cong_cu_may_moc") <= 0:
                w.ghi_unrecognized(aid, "xay_may", "chưa có blueprint cong_cu_may_moc")
                _ghi_su_co(w, aid, "dựng máy không thành: chưa nắm bí quyết máy móc "
                                   "(cần blueprint cong_cu_may_moc hoặc li-xăng)")
                break
            r_may = w.cfg.raw()["research"]["may"]["recipe"]
            can_kim_loai = float(r_may["quang_hoac_xu"])
            kim_loai = ("quang_dong"
                        if w.ledger.so_du(aid, "quang_dong") >= can_kim_loai else "xu")
            cong_can = float(r_may["cong"]) * giam_vl
            tieu = [("cong", cong_can, "dung"), ("go", float(r_may["go"]), "che_tac"),
                    (kim_loai, can_kim_loai, "che_tac")]
            if not _lam_nguyen_tu(w, aid, "dựng máy", tieu, [("may", 1.0, "che_tac")]):
                _ghi_su_co(w, aid, f"dựng máy không thành: {_thieu_gi(w, aid, tieu)}")
                break
            ghi_cong_dung(w, "phi_nong", cong_can)
            w.events.ghi(w.tick, "may_moi", id=aid)
        # hàng mới từ blueprint che_bien
        for ma_hang, so_luong in sorted(kh.che_hang.items()):
            bp = next((b for b in w.blueprints.values() if b.hang_moi == ma_hang), None)
            if bp is None:
                w.ghi_unrecognized(aid, "che_hang", f"không có blueprint cho {ma_hang}")
                continue
            from engine.research import duoc_ap_dung

            if bp.chu != aid and duoc_ap_dung(w, aid, "che_bien") <= 0:
                # cần sở hữu hoặc li-xăng blueprint che_bien
                quyen = False
                from engine.contracts import ben_hien_tai

                for hd in w.hop_dong.values():
                    if hd.trang_thai != "hieu_luc":
                        continue
                    for ck in hd.dieu_khoan:
                        if (ck.loai == "quyen_su_dung"
                                and ck.tai_san == f"blueprint:{bp.id}"
                                and ben_hien_tai(w, hd.id, ck.den) == aid):
                            quyen = True
                if not quyen:
                    w.ghi_unrecognized(aid, "che_hang", f"không có quyền {bp.id}")
                    continue
            cong_mac_dinh = float(w.cfg.raw()["research"]["hang_moi"]["cong_mac_dinh"])
            for _ in range(int(so_luong)):
                cong_can = float(bp.recipe.get("cong", cong_mac_dinh)) * giam_vl / he_may
                tieu = [("cong", cong_can, "dung")] + [
                    (ts, float(sl), "che_tac")
                    for ts, sl in sorted(bp.recipe.items()) if ts != "cong"
                ]
                if not _lam_nguyen_tu(w, aid, f"chế {ma_hang}", tieu,
                                      [(ma_hang, 1.0, "che_tac")]):
                    _ghi_su_co(w, aid,
                               f"chế {ma_hang} không thành: {_thieu_gi(w, aid, tieu)}")
                    break
                ghi_cong_dung(w, "phi_nong", cong_can)
                w.events.ghi(w.tick, "che_tac", id=aid, mon=ma_hang)

    # 4) Reset homestead cho thửa công KHÔNG được canh mùa mưa này
    if mua_mua:
        for p in w.parcels.values():
            if p.chu is None and p.homestead_ai is not None and p.id not in da_canh_tick_nay:
                p.homestead_ai, p.homestead_dem = None, 0
        for pid, aid in da_canh_tick_nay.items():
            w.parcels[pid].nguoi_canh = aid
    else:
        for pid, aid in da_canh_tick_nay.items():
            w.parcels[pid].nguoi_canh = aid


def boc_hoi_cong(w: World) -> None:
    """Công không tích trữ — bốc hơi cuối tick, bất kể ai đang giữ."""
    giu_cong = [(ct, v) for (ct, ts), v in w.ledger._so_du.items() if ts == "cong" and v > 0]
    for ct, v in giu_cong:
        w.ledger.huy(ct, "cong", v, "boc_hoi", "công bốc hơi cuối tick", w.tick)


def phuc_hoi_dat(w: World) -> None:
    """Ruộng bỏ hoang (không gặt tick này) hồi độ màu dần về mức nguyên thủy."""
    dd = w.cfg.raw()["dat_dai"]
    hoi = float(dd["phuc_hoi_moi_tick_bo_hoang"])
    for p in w.parcels.values():
        if p.loai != "ruong" or p.id in w.canh_tick:
            continue
        goc = p.mau_mo_goc if p.mau_mo_goc > 0 else p.mau_mo
        if p.mau_mo < goc:
            p.mau_mo = min(goc, p.mau_mo + hoi)
