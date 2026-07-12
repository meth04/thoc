"""Vật lý xã hội: tiệc khao xóm, trộm cắp, cưu mang trẻ mồ côi.

Engine chỉ mô phỏng cái CÓ THỂ xảy ra về mặt vật lý — tục khao vọng, trị an,
luật làng trừng phạt kẻ trộm... phải TỰ PHÁT SINH từ quyết định của agent
(điều luật #7). Ở đây không có "cảnh sát", chỉ có xác suất bị bắt quả tang
và cái giá bằng quan hệ xóm giềng.
"""

from __future__ import annotations

from engine.world import World

# tài sản vật chất trộm được (không trộm được công sức, cổ phần, vị thế hợp đồng)
_TROM_DUOC = {"thoc", "xu", "ga", "thit", "ca", "go", "quang_dong", "cong_cu"}


def mo_tiec(w: World, aid: str, thoc: float, thit: float) -> None:
    """Mở tiệc khao xóm: đốt thóc/thịt thật, đổi lấy quan hệ + sức khỏe cho khách."""
    from engine.production import _ghi_su_co

    tc = w.cfg.raw()["tiec"]
    quy_doi = float(w.cfg.raw()["chan_nuoi"]["thit_quy_doi_dinh_duong"])
    thoc = min(max(0.0, thoc), w.ledger.so_du(aid, "thoc"))
    thit = min(max(0.0, thit), w.ledger.so_du(aid, "thit"))
    if thoc + thit * quy_doi < float(tc["chi_phi_toi_thieu_thoc"]):
        _ghi_su_co(w, aid, "tiệc quá đạm bạc (cỗ mỏng), không ai buồn đến")
        return
    khach = w.hang_xom_cua(aid, ban_kinh=int(tc["ban_kinh_moi"]),
                           toi_da=int(tc["khach_toi_da"]))
    if not khach:
        _ghi_su_co(w, aid, "quanh nhà không có hàng xóm nào để mời tiệc")
        return
    if thoc > 0:
        w.ledger.huy(aid, "thoc", thoc, "tiec", "mở tiệc khao xóm", w.tick)
    if thit > 0:
        w.ledger.huy(aid, "thit", thit, "tiec", "mở tiệc khao xóm", w.tick)
    tang_sk = float(tc["tang_suc_khoe_khach"])
    for k in khach:
        w.agents[k].health = min(100.0, w.agents[k].health + tang_sk)
        w.cong_quan_he(aid, k, float(tc["quan_he_moi_khach"]))
        w.ghi_ky_uc(k, f"{aid} mở tiệc khao xóm, tôi được mời — có đi có lại mới toại lòng nhau")
    w.ghi_ky_uc(aid, f"tôi mở tiệc khao cả xóm ({len(khach)} khách) — nở mày nở mặt")
    w.events.ghi(w.tick, "mo_tiec", id=aid, thoc=round(thoc, 1), thit=round(thit, 1),
                 so_khach=len(khach), khach=list(khach))


def trom(w: World, ke: str, muc_tieu: str, tai_san: str, so_luong: float) -> None:
    """Lấy trộm: được thì kho người ta vơi, thua thì mất sạch thể diện với cả xóm."""
    from engine.production import _ghi_su_co

    tr = w.cfg.raw()["trom"]
    if (tai_san not in _TROM_DUOC or muc_tieu == ke
            or not w.chu_the_hoat_dong(muc_tieu) or so_luong <= 0):
        w.ghi_unrecognized(ke, "trom", f"mục tiêu/tài sản không hợp lệ: {muc_tieu}/{tai_san}")
        return
    lay = min(float(so_luong), w.ledger.so_du(muc_tieu, tai_san) * float(tr["ty_le_lay_toi_da"]))
    if lay <= 1e-9:
        _ghi_su_co(w, ke, f"lẻn vào nhà {muc_tieu} nhưng kho {tai_san} trống trơn")
        return
    # spawn theo (kẻ trộm, tick): mỗi vụ trộm trong tick một roll ĐỘC LẬP —
    # dùng chung một stream thì cả làng cùng thoát/cùng bị bắt (tương quan = 1)
    g = w.rng.get(f"xa_hoi:{ke}", w.tick)
    if g.random() < float(tr["p_thanh_cong"]):
        w.ledger.chuyen(muc_tieu, ke, tai_san, lay, "mất trộm", w.tick)
        if muc_tieu in w.agents:
            nhieu = 1.0 + (g.random() - 0.5) * float(tr["nhieu_uoc_luong"])
            _ghi_su_co(w, muc_tieu,
                       f"kho {tai_san} vơi đi khoảng {lay * nhieu:.0f} — nghi có kẻ trộm")
        w.ghi_ky_uc(ke, f"tôi lẻn lấy {lay:.0f} {tai_san} của {muc_tieu} — trót lọt, "
                        f"nhưng làm lần nữa ắt có ngày bị bắt")
        w.events.ghi(w.tick, "trom", ke=ke, nan_nhan=muc_tieu, tai_san=tai_san,
                     so_luong=round(lay, 1), bi_bat=False)
    else:
        w.cong_quan_he(ke, muc_tieu, float(tr["quan_he_nan_nhan"]))
        for hx in w.hang_xom_cua(muc_tieu, ban_kinh=int(tr["ban_kinh_xom"]),
                                 toi_da=int(tr["xom_toi_da"])):
            if hx != ke:
                w.cong_quan_he(ke, hx, float(tr["quan_he_hang_xom"]))
        if muc_tieu in w.agents:
            w.ghi_ky_uc(muc_tieu, f"bắt quả tang {ke} lẻn vào kho nhà tôi — đồ ăn trộm!", doi=True)
        w.ghi_ky_uc(ke, f"bị bắt quả tang ăn trộm nhà {muc_tieu} — cả xóm coi khinh", doi=True)
        _ghi_su_co(w, ke, f"trộm nhà {muc_tieu} THẤT BẠI: bị bắt quả tang, cả xóm đã biết")
        w.events.ghi(w.tick, "trom", ke=ke, nan_nhan=muc_tieu, tai_san=tai_san,
                     so_luong=0.0, bi_bat=True)


def decay_quan_he(w: World) -> None:
    """Quan hệ không nuôi thì nhạt dần — áp cuối mỗi năm (tick chẵn), tất định.

    Nhân mọi trọng số với (1 - decay); xóa cạnh quá mờ và cạnh dính chủ thể
    không còn hoạt động (đồ thị không phình vô hạn với người chết)."""
    if w.mua_mua():
        return
    decay = float(w.cfg.get("quan_he.decay_moi_nam"))
    nguong = float(w.cfg.get("quan_he.nguong_xoa_canh"))
    moi: dict[tuple[str, str], float] = {}
    for (a, b), v in w.quan_he.items():
        v *= 1.0 - decay
        if abs(v) >= nguong and w.chu_the_hoat_dong(a) and w.chu_the_hoat_dong(b):
            moi[(a, b)] = v
    w.quan_he = moi


def cuu_mang_mo_coi(w: World) -> None:
    """Trẻ mồ côi cả cha lẫn mẹ được thân nhân (rồi hàng xóm) nhận cưu mang.

    Máu mủ trước, láng giềng sau — trật tự tất định: anh chị ruột trưởng thành
    → ông bà → cô dì chú bác → người dưng có quan hệ tốt nhất với cha mẹ quá cố.
    """
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")

    def _song(pid: str | None) -> bool:
        return bool(pid and pid in w.agents and w.agents[pid].con_song)

    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song or a.truong_thanh(tt) or _song(a.cha) or _song(a.me):
            continue
        if _song(a.giam_ho):
            continue
        ung_vien: list[tuple[int, float, str]] = []  # (bậc ưu tiên, -điểm phụ, id)
        # 1) anh chị ruột trưởng thành; 2) ông bà; 3) cô dì chú bác
        for pid in (a.cha, a.me):
            p = w.agents.get(pid) if pid else None
            if p is None:
                continue
            for sib in p.con:
                s = w.agents.get(sib)
                if s and s.con_song and sib != aid and s.truong_thanh(tt):
                    ung_vien.append((1, -s.tuoi_nam, sib))
            for gid in (p.cha, p.me):
                if _song(gid):
                    ung_vien.append((2, -w.agents[gid].tuoi_nam, gid))
                    for co_chu in w.agents[gid].con:
                        c = w.agents.get(co_chu)
                        if (c and c.con_song and co_chu not in (a.cha, a.me)
                                and c.truong_thanh(tt)):
                            ung_vien.append((3, -c.tuoi_nam, co_chu))  # s5: bậc ưu tiên
        if not ung_vien:
            # 4) người dưng: quan hệ tốt nhất với cha/mẹ quá cố
            for b in w.agents.values():
                if b.con_song and b.truong_thanh(tt):
                    diem = sum(w.uy_tin(b.id, pid) for pid in (a.cha, a.me) if pid)
                    ung_vien.append((4, -diem, b.id))  # s5: bậc ưu tiên
        if not ung_vien:
            continue
        ung_vien.sort()
        gid = ung_vien[0][2]
        a.giam_ho = gid
        nguoi_nuoi = w.agents[gid]
        if aid not in nguoi_nuoi.con_nuoi:
            nguoi_nuoi.con_nuoi.append(aid)
        w.cong_quan_he(gid, aid, 1.0)
        w.ghi_ky_uc(gid, f"tôi nhận cưu mang bé {aid} mồ côi — thêm miệng ăn nhưng là phúc đức", doi=True)
        w.ghi_ky_uc(aid, f"cha mẹ mất cả, {gid} đưa tôi về nuôi", doi=True)
        w.events.ghi(w.tick, "cuu_mang", tre=aid, nguoi_nuoi=gid)
