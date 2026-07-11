"""Pipeline một tick (SPEC mục 6). Phase 2: đủ bước 4 (bảng rao), 6 (chợ), 7 (hợp đồng)."""

from __future__ import annotations

from collections.abc import Callable

from engine import (
    audit,
    board,
    consumption,
    contracts,
    demography,
    education,
    market,
    metrics,
    production,
)
from engine.intents import KeHoach
from engine.market import Lenh, NiemYetDat
from engine.world import World

# Hàm minds: (world) → {agent_id: KeHoach}
MindFn = Callable[[World], dict[str, KeHoach]]


def chay_mot_tick(w: World, mind_fn: MindFn, tong_thua_ban_dau: int) -> dict:
    w.tick += 1

    # 1. bat_dau: tuổi +1 tick; thời tiết năm được rút (lazy)
    for a in w.agents.values():
        if a.con_song:
            a.tuoi_tick += 1
    loai_tt, _ = w.thoi_tiet(w.tick)
    if w.mua_mua():
        w.events.ghi(w.tick, "thoi_tiet", kieu=loai_tt)

    # 2+3. trigger + quyết định
    ke_hoach = mind_fn(w)

    # 3b. lập pháp nhân + di chúc + di cư (trước bảng rao để entity ký được ngay)
    from engine import entities as entities_mod

    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        a = w.agents.get(aid)
        if a is None or not a.con_song:
            continue
        if kh.lap_phap_nhan:
            d = kh.lap_phap_nhan
            entities_mod.lap_phap_nhan(
                w, aid, str(d.get("ten", "")), d.get("co_phan", {}), d.get("von_gop", {})
            )
        if kh.viet_di_chuc:
            a.di_chuc = kh.viet_di_chuc
            w.events.ghi(w.tick, "viet_di_chuc", id=aid)
        if kh.di_cu:
            _di_cu(w, aid)
        # quyết định nhân danh entity (người điều hành >50% cổ phần)
        for eid, kh_con in kh.quyet_dinh_entity:
            if eid in w.entities and entities_mod.nguoi_dieu_hanh(w, eid) == aid:
                kh_con.id = eid
                ke_hoach[eid] = kh_con
            else:
                w.ghi_unrecognized(aid, "quyet_dinh_entity",
                                   f"không điều hành {eid}")

    # 4. bang_rao: đăng đề nghị, trả lời, khớp; đơn phương phá vỡ
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        for hd, den in kh.de_nghi_hop_dong:
            board.dang_de_nghi(w, aid, hd, den)
        for ref, tl in sorted(kh.tra_loi_de_nghi.items()):
            dn = w.bang_rao.get(ref)
            if dn is not None and (dn.den is None or dn.den == aid) and dn.tu != aid:
                dn.tra_loi[aid] = tl
    board.khop_bang_rao(w)
    for aid in sorted(ke_hoach):
        for hd_id in ke_hoach[aid].don_phuong_pha_vo:
            hd = w.hop_dong.get(hd_id)
            if hd is not None and hd.trang_thai == "hieu_luc" and aid in hd.cac_ben:
                contracts.phat_vi_pham(w, hd, aid)

    # 5. san_xuat: sinh công → góp công theo hợp đồng → canh/khai thác/chế tác/xây → R&D
    w.kl_hd_tick = 0.0  # tích lũy giá trị chuyển giao qua hợp đồng trong tick (quy thóc)
    w.gat_tick.clear()
    w.cong_dung_tick = {}
    w.kl_thanh_toan_tick = {}
    production.sinh_cong(w)
    contracts.gop_cong_dau_san_xuat(w)
    production.thi_hanh_san_xuat(w, ke_hoach)
    # chăn nuôi: bắt gà / giết thịt theo kế hoạch
    from engine import chan_nuoi as cn_mod

    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        if kh.bat_ga_cong > 0:
            cn_mod.bat_ga(w, aid, kh.bat_ga_cong)
        if kh.giet_ga > 0:
            cn_mod.giet_ga(w, aid, kh.giet_ga)
    from engine import research as research_mod

    for aid in sorted(ke_hoach):
        nc = ke_hoach[aid].nghien_cuu
        if nc and w.chu_the_hoat_dong(aid):
            linh_vuc, cong, thoc = nc
            research_mod.thi_hanh_nghien_cuu(w, aid, linh_vuc, float(cong), float(thoc))
    research_mod.buoc_nghien_cuu(w)

    # 6. cho: call auction mọi tài sản + sealed bid đất
    lenh_tick: list[Lenh] = []
    tra_gia: list[tuple[str, str, float]] = []
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not w.chu_the_hoat_dong(aid):
            continue
        for le in kh.dat_lenh:
            if isinstance(le, Lenh) and le.ai == aid:
                lenh_tick.append(le)
        for thua, gia_ask in kh.niem_yet_dat:
            p = w.parcels.get(thua)
            if p is not None and p.chu == aid and gia_ask > 0:
                w.niem_yet_dat[thua] = NiemYetDat(thua, aid, float(gia_ask), w.tick)
                w.events.ghi(w.tick, "niem_yet", thua=thua, gia=gia_ask, chu=aid)
        for thua, gia in kh.tra_gia_dat:
            tra_gia.append((aid, thua, float(gia)))
        for hd_id, sl in kh.yeu_cau_rut.items():
            w.yeu_cau_rut_tick[(hd_id, aid)] = float(sl)
    # rao vặt: ai đang rao bán/cần mua gì — tick sau cả làng nghe phong thanh
    w.rao_vat = [
        (le.ai, le.chieu, le.tai_san, le.so_luong, le.gia)
        for le in lenh_tick if le.tai_san != "cong"
    ][:20]
    kl_cho = market.phien_cho(w, lenh_tick)
    market.phien_dat(w, w.niem_yet_dat, tra_gia)

    # 7. thi_hanh_hop_dong: clause định kỳ, đáo hạn, vi phạm, cưỡng chế
    contracts.thi_hanh_hop_dong_tick(w, chet_tick=w.chet_tick_truoc)
    # entity: chia lợi nhuận + kiểm tra mất khả năng thanh toán → thanh lý
    from engine.entities import chia_loi_nhuan_dinh_ky, kiem_tra_pha_san

    chia_loi_nhuan_dinh_ky(w)
    kiem_tra_pha_san(w)
    # hợp đồng kết thúc → chuyển kho lưu trữ (chỉ observatory/analyze đọc)
    xong = [hid for hid, h in w.hop_dong.items() if h.trang_thai != "hieu_luc"]
    for hid in xong:
        w.hop_dong_xong[hid] = w.hop_dong.pop(hid)

    # 8. tieu_dung_suc_khoe (đàn gà ăn/đẻ trước, rồi người ăn — thóc lẫn thịt)
    cn_mod.buoc_chan_nuoi(w)
    cn_mod.hao_thit(w)
    consumption.hao_hut_kho(w)
    consumption.an_va_suc_khoe(w)

    # 9. nhan_khau (ghi lại người chết tick này cho điều kiện sự kiện tick sau)
    truoc = {aid for aid, a in w.agents.items() if not a.con_song}
    demography.buoc_nhan_khau(w, ke_hoach)
    w.chet_tick_truoc = {
        aid for aid, a in w.agents.items() if not a.con_song
    } - truoc

    # 10. giao_duc
    education.buoc_giao_duc(w, ke_hoach)

    # 11. ket_toan: công bốc hơi → AUDIT (assert) → tri thức → metrics → observatory
    production.boc_hoi_cong(w)
    audit.kiem_toan_the_gioi(w, tong_thua_ban_dau)
    research_mod.cap_nhat_san_tier(w)
    m = metrics.buoc_ket_toan(w)
    m["kl_cho"] = round(kl_cho, 3)
    m["kl_giao_dich"] = round(kl_cho + getattr(w, "kl_hd_tick", 0.0), 3)
    hieu_luc = [h for h in w.hop_dong.values() if h.trang_thai == "hieu_luc"]
    m["hd_hieu_luc"] = len(hieu_luc)
    m["so_mo_tip"] = len({board.mo_tip_hop_dong(h) for h in hieu_luc})
    m["tri_thuc"] = round(w.tri_thuc, 3)
    m["san_tier"] = w.san_tri_thuc_tier
    m["so_entity"] = sum(1 for e in w.entities.values() if e.con_hoat_dong)
    m["so_blueprint"] = len(w.blueprints)
    m["so_may"] = round(w.ledger.tong_tai_san("may"), 1)
    cong_4_tam: dict[str, float] = {}
    for d in [*w.cong_dung_4, w.cong_dung_tick][-4:]:
        for k, v in d.items():
            cong_4_tam[k] = cong_4_tam.get(k, 0.0) + v
    tong_cong = sum(cong_4_tam.values())
    m["ty_trong_phi_nong"] = round(
        cong_4_tam.get("phi_nong", 0.0) / tong_cong, 4) if tong_cong else 0.0
    # cửa sổ 4 tick cho cơ cấu công + phương tiện thanh toán (trước khi observatory đọc)
    w.cong_dung_4.append(dict(w.cong_dung_tick))
    if len(w.cong_dung_4) > 4:
        w.cong_dung_4.pop(0)
    w.kl_thanh_toan_4.append(dict(w.kl_thanh_toan_tick))
    if len(w.kl_thanh_toan_4) > 4:
        w.kl_thanh_toan_4.pop(0)
    # observatory: nhãn định chế + giai cấp + milestones (chỉ đọc)
    from observatory.observer import buoc_observatory, viet_chronicle

    obs = buoc_observatory(w)
    m["giai_cap"] = obs["giai_cap"]
    m["nhan_dinh_che"] = obs["nhan_dinh_che"]
    m["cong_nghiep_hoa"] = bool(w.nhan_dinh_che.get("cong_nghiep_hoa"))
    # cửa sổ thu nhập 4 tick (sau khi observatory đã dùng)
    w.thu_nhap_4.append(w.thu_nhap_tick)
    if len(w.thu_nhap_4) > 4:
        w.thu_nhap_4.pop(0)
    w.thu_nhap_tick = {}
    # chronicle mỗi 20 tick
    if w.tick % int(w.cfg.get("minds.chronicle_moi_n_tick")) == 0:
        doan = viet_chronicle(w, m)
        w.events.ghi(w.tick, "chronicle", van=doan)
    # snapshot giai cấp + của cải mỗi 10 tick — tools/analyze dựng ma trận dịch chuyển
    if w.tick % 10 == 0:
        from engine.entities import tai_san_quy_thoc

        snap = {
            aid: [obs["phan_loai"].get(aid, "?"), round(tai_san_quy_thoc(w, aid), 1)]
            for aid, ag in w.agents.items() if ag.con_song
        }
        w.events.ghi(w.tick, "giai_cap_snapshot", du_lieu=snap)
    return m


def _di_cu(w: World, aid: str) -> None:
    """Lập làng mới: cần cụm ≥8 thửa ruộng công cách mọi làng ≥10 ô (chỉ vật lý)."""
    from engine.types import Village

    ung_vien = [
        p for p in w.parcels.values()
        if p.loai == "ruong" and p.chu is None
        and all(abs(p.r - v.r) + abs(p.c - v.c) >= 10 for v in w.villages)
    ]
    if len(ung_vien) < 8:
        w.ghi_unrecognized(aid, "di_cu", "không còn vùng đất công đủ xa/đủ rộng")
        return
    tam = ung_vien[0]
    gan_tam = [p for p in ung_vien if abs(p.r - tam.r) + abs(p.c - tam.c) <= 6]
    if len(gan_tam) < 8:
        w.ghi_unrecognized(aid, "di_cu", "cụm đất quá thưa")
        return
    vid = len(w.villages)
    w.villages.append(Village(id=vid, ten=f"Làng Mới {vid}", r=tam.r, c=tam.c))
    for p in gan_tam:
        p.lang = vid
    w.agents[aid].lang = vid
    w.events.ghi(w.tick, "di_cu", id=aid, lang=vid)
