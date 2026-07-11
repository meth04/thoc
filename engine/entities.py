"""PHÁP NHÂN + cổ phần (SPEC 3.3) — nguyên tố thứ hai, không phải 'công ty' có tên.

Entity có sổ riêng (chủ thể trong ledger chung), sở hữu đất/máy/blueprint, ký hợp đồng,
bị xiết như người. Cổ phần = token `co_phan:{entity}` (100 đơn vị) — bán trên chợ,
thế chấp, thừa kế. Trách nhiệm hữu hạn trong vốn góp (lựa chọn thiết kế, ghi README).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.contracts import ben_hien_tai, gia_tri_thi_truong
from engine.ledger import LoiSoKep
from engine.world import World

TONG_CO_PHAN = 100.0


@dataclass
class Entity:
    id: str
    ten: str
    dieu_le: str = ""
    con_hoat_dong: bool = True
    tick_lap: int = 0
    nguoi_lap: list[str] = field(default_factory=list)


def lap_phap_nhan(w: World, nguoi_lap: str, ten: str, co_phan: dict[str, float],
                  von_gop: dict[str, dict[str, float]]) -> str | None:
    """Lập pháp nhân: mint cổ phần theo %, chuyển vốn góp vào sổ entity.

    co_phan: {agent_id: phần trăm}; von_gop: {agent_id: {tài sản: số lượng}}.
    Trả entity id, hoặc None nếu không hợp lệ (bỏ + log).
    """
    tong = sum(co_phan.values())
    if abs(tong - 100.0) > 1.0 and abs(tong - 1.0) > 0.02:
        w.ghi_unrecognized(nguoi_lap, "lap_phap_nhan", f"cổ phần cộng {tong} ≠ 100%")
        return None
    # vốn góp CHỈ được rút từ túi người ra quyết định — không tiêu tiền người khác
    for aid in von_gop:
        if aid != nguoi_lap:
            w.ghi_unrecognized(nguoi_lap, "lap_phap_nhan",
                               f"vốn góp từ {aid} không phải người lập")
            return None
    he_so = 100.0 / tong
    for aid in co_phan:
        if aid not in w.agents or not w.agents[aid].con_song:
            w.ghi_unrecognized(nguoi_lap, "lap_phap_nhan", f"cổ đông không tồn tại: {aid}")
            return None
    w._next_entity += 1
    eid = f"E{w._next_entity:04d}"
    ts_cp = f"co_phan:{eid}"
    w.ledger.flows.dang_ky(ts_cp, "lap_entity", "nguon")
    w.ledger.flows.dang_ky(ts_cp, "giai_the", "sink")
    # chuyển vốn góp TRƯỚC — ai thiếu thì hủy cả giao dịch. Đất góp bằng "thua:PID".
    da_gop: list[tuple[str, str, float]] = []
    da_gop_dat: list[str] = []
    for aid, gop in sorted(von_gop.items()):
        for ts, sl in sorted(gop.items()):
            if ts.startswith("thua:"):
                pid = ts.split(":", 1)[1]
                p = w.parcels.get(pid)
                if p is None or p.chu != aid:
                    for pid2 in da_gop_dat:
                        w.parcels[pid2].chu = aid
                    for a2, t2, s2 in da_gop:
                        w.ledger.chuyen(eid, a2, t2, s2, "hoàn vốn góp hụt", w.tick)
                    w.ghi_unrecognized(nguoi_lap, "lap_phap_nhan", f"{aid} không có {pid}")
                    return None
                p.chu = eid
                da_gop_dat.append(pid)
                continue
            try:
                w.ledger.chuyen(aid, eid, ts, float(sl), f"vốn góp {eid}", w.tick)
                da_gop.append((aid, ts, float(sl)))
            except LoiSoKep:
                for pid2 in da_gop_dat:
                    w.parcels[pid2].chu = aid
                for a2, t2, s2 in da_gop:
                    w.ledger.chuyen(eid, a2, t2, s2, "hoàn vốn góp hụt", w.tick)
                w.ghi_unrecognized(nguoi_lap, "lap_phap_nhan", f"{aid} thiếu {ts}")
                return None
    for aid, pct in sorted(co_phan.items()):
        w.ledger.sinh(aid, ts_cp, pct * he_so, "lap_entity", f"cổ phần {eid}", w.tick)
    w.entities[eid] = Entity(id=eid, ten=ten or eid, tick_lap=w.tick,
                             nguoi_lap=sorted(co_phan))
    w.events.ghi(w.tick, "lap_entity", entity=eid, ten=ten, co_phan=co_phan)
    return eid


def co_dong_cua(w: World, eid: str) -> dict[str, float]:
    ts_cp = f"co_phan:{eid}"
    return {
        ct: v for (ct, ts), v in w.ledger._so_du.items() if ts == ts_cp and v > 1e-9
    }


def nguoi_dieu_hanh(w: World, eid: str) -> str | None:
    """Cổ đông (còn sống) giữ nhiều cổ phần nhất điều hành entity (tie-break theo id)."""
    ung_vien = [
        (v, ct) for ct, v in co_dong_cua(w, eid).items()
        if ct in w.agents and w.agents[ct].con_song
    ]
    if not ung_vien:
        return None
    ung_vien.sort(key=lambda x: (-x[0], x[1]))
    return ung_vien[0][1]


def tai_san_quy_thoc(w: World, chu_the: str) -> float:
    tong = 0.0
    for ts, sl in w.ledger.tai_san_cua(chu_the).items():
        if ts == "cong" or ts.startswith("vi_the:") or ts.startswith("co_phan:"):
            continue
        tong += gia_tri_thi_truong(w, ts, sl)
    for p in w.parcels.values():
        if p.chu == chu_the:
            tong += w.gia_gan_nhat("dat") or 300.0
    return tong


def nghia_vu_quy_thoc(w: World, eid: str) -> float:
    """Tổng nghĩa vụ chưa thực hiện của entity trong các hợp đồng hiệu lực."""
    tong = 0.0
    for hd in w.hop_dong.values():
        # gồm cả hợp đồng vừa VI PHẠM trong tick (nghĩa vụ chưa đền chưa biến mất)
        if hd.trang_thai not in ("hieu_luc", "vi_pham"):
            continue
        for ck in hd.dieu_khoan:
            tu = getattr(ck, "tu", None)
            if tu is None or ben_hien_tai(w, hd.id, tu) != eid:
                continue
            if ck.loai == "chuyen_giao_mot_lan" and ck.tai != "ky_ket":
                tong += gia_tri_thi_truong(w, ck.tai_san, ck.so_luong)
            elif ck.loai == "hoan_tra_theo_yeu_cau":
                # nghĩa vụ tiềm tàng = tổng đã nhận chưa hoàn (ước lượng bằng trần rút)
                tong += gia_tri_thi_truong(w, ck.tai_san, ck.tran_rut_moi_tick)
    return tong


def kiem_tra_pha_san(w: World) -> None:
    """Entity mất khả năng thanh toán → thanh lý: bán tài sản trả nợ, dư về cổ đông."""
    for eid in sorted(w.entities):
        e = w.entities[eid]
        if not e.con_hoat_dong:
            continue
        nghia_vu = nghia_vu_quy_thoc(w, eid)
        tai_san = tai_san_quy_thoc(w, eid)
        # phá sản CHỈ khi mất khả năng thanh toán (nghĩa vụ > tài sản khả thi) —
        # hụt một kỳ lương lẻ thì chỉ hợp đồng đó vi phạm, xưởng không sập cả dàn
        if nghia_vu > tai_san + 1e-9:
            thanh_ly(w, eid)
            continue
        # entity cạn vốn kéo dài, không đất → tự giải thể (máy trả về cổ đông)
        if (w.tick - e.tick_lap > 24 and w.ledger.so_du(eid, "thoc") < 50.0
                and not any(p.chu == eid for p in w.parcels.values())):
            thanh_ly(w, eid)


def thanh_ly(w: World, eid: str) -> None:
    """Thanh lý: chủ nợ nhận pro-rata theo giá trị; cổ đông nhận phần còn; đóng entity."""
    e = w.entities[eid]
    # 1) hủy mọi hợp đồng của entity, lập danh sách chủ nợ theo giá trị nghĩa vụ
    chu_no: dict[str, float] = {}
    for hd in sorted(w.hop_dong.values(), key=lambda h: h.id):
        # gồm cả hợp đồng VỪA vi phạm trong tick (bank-run): chủ nợ đó vẫn được chia
        if hd.trang_thai not in ("hieu_luc", "vi_pham") or eid not in [
            ben_hien_tai(w, hd.id, b) for b in hd.cac_ben
        ]:
            continue
        for ck in hd.dieu_khoan:
            tu = getattr(ck, "tu", None)
            den = getattr(ck, "den", None)
            if tu and ben_hien_tai(w, hd.id, tu) == eid and den:
                den_r = ben_hien_tai(w, hd.id, den)
                if ck.loai == "chuyen_giao_mot_lan" and ck.tai != "ky_ket":
                    chu_no[den_r] = chu_no.get(den_r, 0.0) + gia_tri_thi_truong(
                        w, ck.tai_san, ck.so_luong)
                elif ck.loai == "hoan_tra_theo_yeu_cau":
                    chu_no[den_r] = chu_no.get(den_r, 0.0) + gia_tri_thi_truong(
                        w, ck.tai_san, ck.tran_rut_moi_tick)
        if hd.trang_thai == "hieu_luc":
            hd.trang_thai = "huy"  # giữ nguyên dấu "vi_pham" cho sổ sách
        from engine.contracts import dot_vi_the

        dot_vi_the(w, hd)
        w.events.ghi(w.tick, "huy_hd", hd=hd.id, ly_do="thanh_ly_entity")

    tong_no = sum(chu_no.values())
    # 2) chia TÀI SẢN THẬT pro-rata cho chủ nợ theo tỷ trọng nợ (trả bằng hiện vật)
    tai_san = {
        ts: sl for ts, sl in w.ledger.tai_san_cua(eid).items()
        if ts != "cong" and not ts.startswith("vi_the:") and not ts.startswith("co_phan:")
    }
    co_dong = co_dong_cua(w, eid)
    for ts, sl in sorted(tai_san.items()):
        if tong_no > 0:
            for nid, no in sorted(chu_no.items()):
                phan = sl * (no / tong_no)
                if phan > 1e-9:
                    w.ledger.chuyen(eid, nid, ts, phan, f"thanh lý {eid}", w.tick)
        con = w.ledger.so_du(eid, ts)
        if con > 1e-9 and co_dong:
            tong_cp = sum(co_dong.values())
            for cid, cp in sorted(co_dong.items()):
                w.ledger.chuyen(eid, cid, ts, con * cp / tong_cp,
                                f"chia tài sản dư {eid}", w.tick)
    # đất của entity: chủ nợ lớn nhất trước, còn lại cổ đông lớn nhất, hết thì về công
    thua_cua = sorted(p.id for p in w.parcels.values() if p.chu == eid)
    thu_tu = [nid for nid, _ in sorted(chu_no.items(), key=lambda x: -x[1])] + [
        cid for cid, _ in sorted(co_dong.items(), key=lambda x: -x[1])
    ]
    for i, pid in enumerate(thua_cua):
        w.parcels[pid].chu = thu_tu[i % len(thu_tu)] if thu_tu else None
    # 3) đốt cổ phần, đóng entity
    ts_cp = f"co_phan:{eid}"
    for cid, cp in sorted(co_dong.items()):
        w.ledger.huy(cid, ts_cp, cp, "giai_the", f"giải thể {eid}", w.tick)
    e.con_hoat_dong = False
    w.events.ghi(w.tick, "pha_san_entity", entity=eid, tong_no=round(tong_no, 1),
                 chu_no=list(chu_no))


def chia_loi_nhuan_dinh_ky(w: World) -> None:
    """Điều lệ mặc định: cuối mỗi năm (tick chẵn), entity chia thóc VƯỢT vốn lưu động
    tối thiểu cho cổ đông theo cổ phần."""
    if w.mua_mua():
        return
    for eid in sorted(w.entities):
        e = w.entities[eid]
        if not e.con_hoat_dong:
            continue
        thoc = w.ledger.so_du(eid, "thoc")
        nghia_vu = nghia_vu_quy_thoc(w, eid)
        # giữ lại vốn hoạt động (trả lương/mua vật liệu) — chỉ chia phần thực sự dư
        dem_luu_dong = max(4000.0, nghia_vu * 2.0)
        du = thoc - dem_luu_dong
        if du <= 1e-9:
            continue
        co_dong = co_dong_cua(w, eid)
        tong_cp = sum(co_dong.values())
        if tong_cp <= 0:
            continue
        for cid, cp in sorted(co_dong.items()):
            w.ledger.chuyen(eid, cid, "thoc", du * cp / tong_cp,
                            f"chia lợi nhuận {eid}", w.tick)
        w.events.ghi(w.tick, "chia_loi_nhuan", entity=eid, tong=round(du, 1))
