"""Giáo dục — vật lý của việc học (SPEC 2.9). Phase 1: dạy E1 tại nhà + tự học."""

from __future__ import annotations

from engine.intents import KeHoach
from engine.ledger import LoiSoKep
from engine.world import World


def _so_tick_bac(w: World, bac: int) -> int:
    return int(w.cfg.raw()["giao_duc"][f"E{bac}"][1])


def _phan_cong_mat(w: World, bac: int) -> float:
    return float(w.cfg.raw()["giao_duc"][f"E{bac}"][2])


def buoc_giao_duc(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    """Tiến độ học: cần thầy (Phase 1: cha mẹ dạy E1) hoặc tự học (gấp đôi tick)."""
    ngay_cong = w.cfg.get("nhu_cau.ngay_cong_moi_tick")

    # danh sách con được cha mẹ (E≥1) dạy tick này
    duoc_day_e1: set[str] = set()
    if w.cfg.get("giao_duc.cha_me_day_E1_tai_nha"):
        for aid in sorted(ke_hoach):
            day_cho = ke_hoach[aid].day_cho
            thay = w.agents.get(aid)
            if not day_cho or not thay or not thay.con_song or thay.e_bac < 1:
                continue
            for hid in day_cho:
                if hid in w.agents and hid in thay.con:
                    duoc_day_e1.add(hid)

    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song:
            continue
        kh = ke_hoach.get(aid)
        muon_hoc = (kh is not None and kh.hoc) or aid in duoc_day_e1
        if not muon_hoc:
            continue
        muc_tieu = a.e_bac + 1
        if muc_tieu > 4:
            continue
        # bắt đầu khoá mới nếu chưa học
        if a.hoc_muc_tieu != muc_tieu:
            co_thay = aid in duoc_day_e1 and muc_tieu == 1
            a.hoc_muc_tieu = muc_tieu
            a.hoc_tu_hoc = not co_thay
            so_tick = _so_tick_bac(w, muc_tieu)
            a.hoc_tick_con = so_tick * (2 if a.hoc_tu_hoc else 1)
        # trả chi phí công (50% công sinh trong tick)
        cong_mat = ngay_cong * (a.health / 100.0) * _phan_cong_mat(w, muc_tieu)
        try:
            if cong_mat > 0:
                w.ledger.huy(aid, "cong", min(cong_mat, w.ledger.so_du(aid, "cong")),
                             "dung", "học", w.tick)
        except LoiSoKep:
            continue
        a.hoc_tick_con -= 1
        if a.hoc_tick_con <= 0:
            a.e_bac = muc_tieu
            a.hoc_muc_tieu = None
            w.events.ghi(w.tick, "thang_E", id=aid, e=muc_tieu, tu_hoc=a.hoc_tu_hoc)
