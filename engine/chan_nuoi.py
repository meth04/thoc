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
        # chủ không hoạt động (chết, VO_THUA_NHAN, entity giải thể) → đàn đứng im,
        # không ăn thóc ma, không sinh sôi, không tiêu RNG
        if not w.chu_the_hoat_dong(chu):
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
        chet_gia = so_ga * float(cn["ga_chet_gia_moi_tick"])
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
    """Thịt và cá tươi không trữ lâu được."""
    ty_le_thit = float(w.cfg.raw()["chan_nuoi"]["thit_hao_moi_tick"])
    ty_le_ca = float(w.cfg.raw()["danh_ca"]["ca_hao_moi_tick"])
    for (ct, ts), v in list(w.ledger._so_du.items()):
        if ts == "thit" and v > 0:
            w.ledger.huy(ct, "thit", v * ty_le_thit, "hao_thit", "thịt ôi", w.tick)
        elif ts == "ca" and v > 0:
            w.ledger.huy(ct, "ca", v * ty_le_ca, "hao_thit", "cá ươn", w.tick)


def danh_ca(w: World, aid: str, so_cong: float) -> None:
    """Đánh cá trên sông — trữ lượng là CỦA CHUNG cả làng, đánh nhiều thì cạn.

    Không cần đất: đây là sinh kế của người không ruộng (văn liệu kinh tế nông thôn).
    """
    from engine.production import _ghi_su_co, ghi_cong_dung

    dc = w.cfg.raw()["danh_ca"]
    so_o_song = sum(1 for p in w.parcels.values() if p.loai == "song")
    if so_o_song == 0:
        _ghi_su_co(w, aid, "vùng này không có sông để đánh cá")
        return
    # trữ lượng chung tái sinh mỗi tick — ai đánh trước được trước (thứ tự id tất định)
    if getattr(w, "_ca_pool_tick", None) != w.tick:
        w._ca_pool_tick = w.tick
        w._ca_pool = so_o_song * float(dc["ca_moi_o_song_kg"])
    cong_moi_kg = float(dc["cong_moi_kg_ca"])
    cong_co = min(max(0.0, so_cong), w.ledger.so_du(aid, "cong"))
    kg = min(cong_co / cong_moi_kg, w._ca_pool)
    if kg <= 1e-9:
        _ghi_su_co(w, aid, "ra sông nhưng cá đã bị đánh cạn mùa này (hoặc hết công)")
        return
    w.ledger.huy(aid, "cong", kg * cong_moi_kg, "dung", "đánh cá", w.tick)
    ghi_cong_dung(w, "nong", kg * cong_moi_kg)
    w.ledger.sinh(aid, "ca", kg, "danh_ca", "đánh cá", w.tick)
    w._ca_pool -= kg
    w.ghi_thu_nhap(aid, "nong", kg * float(dc["ca_quy_doi_dinh_duong"]))
    w.events.ghi(w.tick, "danh_ca", id=aid, kg=round(kg, 1))
