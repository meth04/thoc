"""Vật lý chăn nuôi (gà) — nguồn thu nhập phụ cho hộ dư thóc.

Mỗi tick (đầu bước tiêu dùng): gà của mỗi hộ ăn thóc (engine tự trừ); no đủ thì đàn
sinh sôi, thiếu ăn thì chết dần; quá đông thì dịch bệnh kìm đàn. Giết gà lấy thịt —
thịt ăn thay thóc (đậm dinh dưỡng hơn) nhưng mau hỏng. Gà/thịt mua bán trên chợ như
mọi tài sản khác.
"""

from __future__ import annotations

from engine.ledger import LoiSoKep
from engine.world import World


def buoc_chan_nuoi(w: World) -> None:
    cn = w.cfg.raw()["chan_nuoi"]
    an_moi_con = float(cn["ga_an_thoc_moi_tick"])
    sinh_san = float(cn["ga_sinh_san_moi_tick"])
    tran = float(cn["ga_toi_da_moi_ho"])
    g = w.rng.get("chan_nuoi", w.tick)

    chu_ga = sorted(
        (ct, v) for (ct, ts), v in w.ledger._so_du.items() if ts == "ga" and v >= 1
    )
    for chu, so_ga in chu_ga:
        if chu in w.agents and not w.agents[chu].con_song:
            continue
        so_ga = float(so_ga)
        # 1) gà ăn thóc — chủ nghèo thì đàn đói
        can_thoc = so_ga * an_moi_con
        co_thoc = w.ledger.so_du(chu, "thoc")
        cho_an = min(can_thoc, co_thoc)
        if cho_an > 0:
            w.ledger.huy(chu, "thoc", cho_an, "nuoi_ga", "nuôi gà", w.tick)
        ty_le_no = cho_an / can_thoc if can_thoc > 0 else 1.0
        # 2) thiếu ăn → chết dần (nửa phần đói); no đủ → sinh sôi (trừ khi quá đông)
        if ty_le_no < 1.0 - 1e-9:
            chet = min(so_ga, so_ga * (1.0 - ty_le_no) * 0.5 + 0.5)
            w.ledger.huy(chu, "ga", chet, "chet_doi_ga", "gà chết đói", w.tick)
            so_ga = w.ledger.so_du(chu, "ga")
            if chu in w.agents:
                from engine.production import _ghi_su_co

                _ghi_su_co(w, chu, f"đàn gà đói (thiếu {can_thoc - cho_an:.0f}kg thóc), "
                                   f"chết mất {chet:.1f} con")
        # tử suất tự nhiên của đàn (gà già, chồn cáo)
        chet_gia = so_ga * float(cn.get("ga_chet_gia_moi_tick", 0.05))
        if chet_gia > 0:
            nguyen_cg = int(chet_gia)
            if g.random() < chet_gia - nguyen_cg:
                nguyen_cg += 1
            if nguyen_cg > 0:
                w.ledger.huy(chu, "ga", min(float(nguyen_cg), so_ga), "chet_doi_ga",
                             "gà già/chồn bắt", w.tick)
                so_ga = w.ledger.so_du(chu, "ga")
        if ty_le_no >= 1.0 - 1e-9 and so_ga < tran:
            de_them = min(so_ga * sinh_san, tran - so_ga)
            # phần lẻ thành xác suất — đàn nhỏ vẫn lớn dần được
            nguyen = int(de_them)
            if g.random() < de_them - nguyen:
                nguyen += 1
            if nguyen > 0:
                w.ledger.sinh(chu, "ga", float(nguyen), "sinh_san", "gà đẻ", w.tick)


def bat_ga(w: World, aid: str, so_cong: float) -> None:
    """Bắt gà rừng con về nuôi — cần ô rừng trong làng, tốn công."""
    cn = w.cfg.raw()["chan_nuoi"]
    if not any(p.loai == "rung" for p in w.parcels.values()):
        return
    cong_co = min(so_cong, w.ledger.so_du(aid, "cong"))
    so_con = int(cong_co // float(cn["bat_ga_cong_moi_con"]))
    if so_con <= 0:
        return
    try:
        w.ledger.huy(aid, "cong", so_con * float(cn["bat_ga_cong_moi_con"]), "dung",
                     "bắt gà rừng", w.tick)
    except LoiSoKep:
        return
    from engine.production import ghi_cong_dung

    ghi_cong_dung(w, "phi_nong", so_con * float(cn["bat_ga_cong_moi_con"]))
    w.ledger.sinh(aid, "ga", float(so_con), "bat_rung", "bắt gà rừng", w.tick)
    w.events.ghi(w.tick, "bat_ga", id=aid, so_con=so_con)


def giet_ga(w: World, aid: str, so_con: int) -> None:
    """Giết gà lấy thịt (thịt mau hỏng — giết vừa đủ ăn/bán)."""
    cn = w.cfg.raw()["chan_nuoi"]
    so_con = int(min(so_con, w.ledger.so_du(aid, "ga")))
    if so_con <= 0:
        return
    w.ledger.huy(aid, "ga", float(so_con), "giet_thit", "giết gà", w.tick)
    w.ledger.sinh(aid, "thit", so_con * float(cn["thit_moi_ga_kg"]), "giet_thit",
                  "thịt gà", w.tick)
    w.events.ghi(w.tick, "giet_ga", id=aid, so_con=so_con)


def hao_thit(w: World) -> None:
    """Thịt không trữ lâu được."""
    ty_le = float(w.cfg.raw()["chan_nuoi"]["thit_hao_moi_tick"])
    for (ct, ts), v in list(w.ledger._so_du.items()):
        if ts == "thit" and v > 0:
            w.ledger.huy(ct, "thit", v * ty_le, "hao_thit", "thịt ôi", w.tick)
