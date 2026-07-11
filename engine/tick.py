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

    # 4. bang_rao: đăng đề nghị, trả lời, khớp; đơn phương phá vỡ
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        a = w.agents.get(aid)
        if a is None or not a.con_song:
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

    # 5. san_xuat: sinh công → góp công theo hợp đồng → canh/khai thác/chế tác/xây
    w.kl_hd_tick = 0.0  # tích lũy giá trị chuyển giao qua hợp đồng trong tick (quy thóc)
    w.gat_tick.clear()
    production.sinh_cong(w)
    contracts.gop_cong_dau_san_xuat(w)
    production.thi_hanh_san_xuat(w, ke_hoach)

    # 6. cho: call auction mọi tài sản + sealed bid đất
    lenh_tick: list[Lenh] = []
    tra_gia: list[tuple[str, str, float]] = []
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        a = w.agents.get(aid)
        if a is None or not a.con_song:
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
    kl_cho = market.phien_cho(w, lenh_tick)
    market.phien_dat(w, w.niem_yet_dat, tra_gia)

    # 7. thi_hanh_hop_dong: clause định kỳ, đáo hạn, vi phạm, cưỡng chế
    contracts.thi_hanh_hop_dong_tick(w, chet_tick=w.chet_tick_truoc)
    # hợp đồng kết thúc → chuyển kho lưu trữ (chỉ observatory/analyze đọc)
    xong = [hid for hid, h in w.hop_dong.items() if h.trang_thai != "hieu_luc"]
    for hid in xong:
        w.hop_dong_xong[hid] = w.hop_dong.pop(hid)

    # 8. tieu_dung_suc_khoe
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

    # 11. ket_toan: công bốc hơi → AUDIT (assert) → metrics
    production.boc_hoi_cong(w)
    audit.kiem_toan_the_gioi(w, tong_thua_ban_dau)
    m = metrics.buoc_ket_toan(w)
    m["kl_cho"] = round(kl_cho, 3)
    m["kl_giao_dich"] = round(kl_cho + getattr(w, "kl_hd_tick", 0.0), 3)
    hieu_luc = [h for h in w.hop_dong.values() if h.trang_thai == "hieu_luc"]
    m["hd_hieu_luc"] = len(hieu_luc)
    m["so_mo_tip"] = len({board.mo_tip_hop_dong(h) for h in hieu_luc})
    return m
