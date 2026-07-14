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
    an_moi_con_non = float(cn["ga_con_an_thoc_moi_tick"])
    sinh_san = float(cn["ga_sinh_san_moi_tick"])
    tran = float(cn["ga_toi_da_moi_ho"])
    g = w.rng.get("chan_nuoi", w.tick)

    chu_dan = sorted({
        ct for (ct, ts), v in w.ledger._so_du.items()
        if ts in ("ga", "ga_con") and v >= 1
    })
    for chu in chu_dan:
        # chủ không hoạt động (chết, VO_THUA_NHAN, entity giải thể) → đàn đứng im,
        # không ăn thóc ma, không sinh sôi, không tiêu RNG
        if not w.chu_the_hoat_dong(chu):
            continue
        so_ga = w.ledger.so_du(chu, "ga")
        # 1) đàn ăn thóc — chủ nghèo thì đàn đói (gà con mới đẻ tick này chưa tính)
        can_thoc = so_ga * an_moi_con + w.ledger.so_du(chu, "ga_con") * an_moi_con_non
        if so_ga < 1e-9 and can_thoc < 1e-9:
            continue
        co_thoc = w.ledger.so_du(chu, "thoc")
        cho_an = min(can_thoc, co_thoc)
        if cho_an > 0:
            w.ledger.huy(chu, "thoc", cho_an, "nuoi_ga", "nuôi gà", w.tick)
        ty_le_no = cho_an / can_thoc if can_thoc > 0 else 1.0
        # 2) thiếu ăn → chết dần (nửa phần đói); no đủ → sinh sôi (trừ khi quá đông)
        if ty_le_no < 1.0 - 1e-9 and so_ga >= 1e-9:
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
        if ty_le_no >= 1.0 - 1e-9 and 1e-9 <= so_ga < tran:
            de_them = min(so_ga * sinh_san, tran - so_ga)
            # phần lẻ thành xác suất — đàn nhỏ vẫn lớn dần được; đẻ ra GÀ CON,
            # tick sau mới trưởng thành (chăn nuôi cần thời gian)
            nguyen = int(de_them)
            if g.random() < de_them - nguyen:
                nguyen += 1
            if nguyen > 0:
                w.ledger.sinh(chu, "ga_con", float(nguyen), "sinh_san", "gà đẻ", w.tick)


def bat_ga(w: World, aid: str, so_cong: float) -> None:
    """Bắt gà rừng con về nuôi.

    Legacy scenario (pool tắt) giữ hành vi cũ. Khi ``khong_gian.ga_rung`` bật, gà là
    commons tái tạo: CPUE giảm theo mật độ, không ai bắt quá stock và người ở bờ dân cư
    chỉ săn được habitat bờ hoang sau khi qua sông.
    """
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected
    from engine.spatial import _ga_rung_bat, co_the_o_bo

    cn = w.cfg.raw()["chan_nuoi"]
    dung_pool = _ga_rung_bat(w)
    rung_toi_duoc = [
        p for p in w.parcels.values()
        if p.loai == "rung" and (not dung_pool or co_the_o_bo(w, aid, p.bo))
    ]
    if not rung_toi_duoc:
        journal_rejected(w, aid, "chan_nuoi", "no_reachable_habitat")
        if dung_pool:
            from engine.production import _ghi_su_co

            _ghi_su_co(w, aid, "bắt gà không thành: không có habitat rừng tới được")
        return
    cong_co = min(so_cong, w.ledger.so_du(aid, "cong"))
    if cong_co <= 0:
        journal_rejected(w, aid, "chan_nuoi", "insufficient_labor")
        return
    if dung_pool:
        from engine.world import _ga_rung_suc_chua

        pool_cfg = w.cfg.get("khong_gian.ga_rung")
        suc_chua = _ga_rung_suc_chua(w)
        ton = max(0.0, float(getattr(w, "ga_rung_ton", 0.0) or 0.0))
        if suc_chua <= 0 or ton <= 1e-9:
            journal_rejected(w, aid, "chan_nuoi", "wild_chicken_depleted")
            from engine.production import _ghi_su_co

            _ghi_su_co(w, aid, "bắt gà không thành: habitat đã cạn")
            return
        dinh_muc = float(pool_cfg["cong_moi_con"])
        mat_do = min(1.0, ton / suc_chua)
        so_con = min((cong_co / dinh_muc) * mat_do, ton)
        cong_dung = cong_co
    else:
        dinh_muc = float(cn["bat_ga_cong_moi_con"])
        so_con = float(int(cong_co // dinh_muc))
        cong_dung = so_con * dinh_muc
        mat_do = None
    if so_con <= 1e-9:
        journal_rejected(w, aid, "chan_nuoi", "no_catch")
        return
    try:
        w.ledger.huy(aid, "cong", cong_dung, "dung",
                      "bắt gà rừng", w.tick)
    except LoiSoKep:
        journal_rejected(w, aid, "chan_nuoi", "insufficient_labor")
        return
    from engine.production import ghi_cong_dung

    ghi_cong_dung(w, "phi_nong", cong_dung)
    # bắt được GÀ CON — phải nuôi 1 tick (6 tháng) mới thành gà đẻ/thịt đầy
    w.ledger.sinh(aid, "ga_con", so_con, "bat_rung", "bắt gà rừng", w.tick)
    if dung_pool:
        w.ga_rung_ton = max(0.0, ton - so_con)
    payload = {"id": aid, "so_con": round(so_con, 4)}
    if mat_do is not None:
        payload["mat_do"] = round(mat_do, 4)
        payload["con_lai"] = round(float(w.ga_rung_ton), 4)
    w.events.ghi(w.tick, "bat_ga", **payload)
    journal_executed(w, aid, "chan_nuoi", code="wild_chicken_caught",
                     detail=f"caught={so_con:g}")


def giet_ga(w: World, aid: str, so_con: int) -> None:
    """Giết gà lấy thịt — gà trưởng thành trước (8kg), túng lắm mới thịt gà con (3kg)."""
    cn = w.cfg.raw()["chan_nuoi"]
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected

    so_con = int(so_con)
    if so_con <= 0:
        return
    lon = int(min(so_con, w.ledger.so_du(aid, "ga")))
    non = int(min(so_con - lon, w.ledger.so_du(aid, "ga_con")))
    thit = lon * float(cn["thit_moi_ga_kg"]) + non * float(cn["thit_moi_ga_con_kg"])
    if lon + non <= 0:
        journal_rejected(w, aid, "chan_nuoi", "no_livestock")
        return
    if lon > 0:
        w.ledger.huy(aid, "ga", float(lon), "giet_thit", "giết gà", w.tick)
    if non > 0:
        w.ledger.huy(aid, "ga_con", float(non), "giet_thit", "giết gà con", w.tick)
    w.ledger.sinh(aid, "thit", thit, "giet_thit", "thịt gà", w.tick)
    w.events.ghi(w.tick, "giet_ga", id=aid, so_con=lon + non)
    journal_executed(w, aid, "chan_nuoi", code="chicken_slaughtered",
                     detail=f"slaughtered={lon + non:g}")


def hao_thit(w: World) -> None:
    """Thịt và cá tươi không trữ lâu được."""
    ty_le_thit = float(w.cfg.raw()["chan_nuoi"]["thit_hao_moi_tick"])
    ty_le_ca = float(w.cfg.raw()["danh_ca"]["ca_hao_moi_tick"])
    for (ct, ts), v in list(w.ledger._so_du.items()):
        if ts == "thit" and v > 0:
            w.ledger.huy(ct, "thit", v * ty_le_thit, "hao_thit", "thịt ôi", w.tick)
        elif ts == "ca" and v > 0:
            w.ledger.huy(ct, "ca", v * ty_le_ca, "hao_thit", "cá ươn", w.tick)


def truong_thanh_ga(w: World) -> None:
    """Đầu tick: gà con bắt/đẻ từ tick TRƯỚC nay đủ 6 tháng, thành gà lớn.

    Chạy trước mọi hành động trong tick — gà bắt/đẻ trong tick này phải đợi
    trọn một tick nuôi (chăn nuôi cần thời gian)."""
    chu_non = sorted(
        ct for (ct, ts), v in w.ledger._so_du.items() if ts == "ga_con" and v > 1e-9
    )
    for chu in chu_non:
        if not w.chu_the_hoat_dong(chu):
            continue
        non = w.ledger.so_du(chu, "ga_con")
        w.ledger.huy(chu, "ga_con", non, "truong_thanh", "gà con lớn", w.tick)
        w.ledger.sinh(chu, "ga", non, "truong_thanh", "gà con lớn", w.tick)


def tai_sinh_ca(w: World) -> None:
    """Trữ lượng cá hồi theo logistic mỗi tick: ΔS = r·S·(1−S/K).

    Đánh vừa phải thì sông nuôi làng mãi (sản lượng bền vững ≈ r·K/4);
    đánh kiệt thì trữ lượng sập và hồi RẤT chậm — bi kịch của cải chung thật.
    """
    from engine.world import _ca_suc_chua

    suc_chua = _ca_suc_chua(w)
    if suc_chua <= 0:
        return
    r = float(w.cfg.get("danh_ca.tai_sinh_moi_tick"))
    s = float(getattr(w, "ca_ton", suc_chua))
    w.ca_ton = min(suc_chua, s + r * s * (1.0 - s / suc_chua))


def tai_sinh_ga_rung(w: World) -> None:
    """Hồi phục logistic của commons gà rừng (chỉ scenario-gated)."""
    from engine.spatial import _ga_rung_bat
    from engine.world import _ga_rung_suc_chua

    if not _ga_rung_bat(w):
        return
    suc_chua = _ga_rung_suc_chua(w)
    ton_cu = max(0.0, float(getattr(w, "ga_rung_ton", 0.0) or 0.0))
    if suc_chua <= 0:
        w.ga_rung_ton = 0.0
        if ton_cu > 1e-9:
            w.events.ghi(w.tick, "ga_rung_suc_chua_giam", ton_truoc=round(ton_cu, 9),
                         suc_chua=0.0, mat=round(ton_cu, 9))
        return
    cfg = w.cfg.get("khong_gian.ga_rung")
    ton = float(getattr(w, "ga_rung_ton", suc_chua * float(cfg["ty_le_ton_ban_dau"])))
    # Logging/clearing can lower K below the surviving stock. This is an ecological loss,
    # not a ledger burn, but it must be explicit in the run journal rather than silently
    # clamping a commons pool.
    if ton > suc_chua + 1e-9:
        w.events.ghi(w.tick, "ga_rung_suc_chua_giam", ton_truoc=round(ton, 9),
                     suc_chua=round(suc_chua, 9), mat=round(ton - suc_chua, 9))
    ton = min(max(0.0, ton), suc_chua)
    r = float(cfg["tai_sinh_moi_tick"])
    w.ga_rung_ton = min(suc_chua, ton + r * ton * (1.0 - ton / suc_chua))


def danh_ca(w: World, aid: str, so_cong: float) -> None:
    """Đánh cá trên sông — trữ lượng CHUNG có hạn; cá càng thưa càng khó bắt.

    Hiệu suất tỷ lệ mật độ đàn cá (CPUE ∝ S/K): cùng một buổi công, sông đầy
    cá bắt được nhiều, sông cạn về tay không — không thể săn bắt mãi.
    """
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected
    from engine.production import _ghi_su_co, ghi_cong_dung
    from engine.world import _ca_suc_chua

    dc = w.cfg.raw()["danh_ca"]
    suc_chua = _ca_suc_chua(w)
    if suc_chua <= 0:
        journal_rejected(w, aid, "danh_ca", "fishery_unavailable")
        _ghi_su_co(w, aid, "vùng này không có sông để đánh cá")
        return
    ton = float(getattr(w, "ca_ton", suc_chua))
    mat_do = max(0.0, ton / suc_chua)
    cong_moi_kg = float(dc["cong_moi_kg_ca"])
    cong_co = min(max(0.0, so_cong), w.ledger.so_du(aid, "cong"))
    # cùng công đó, cá thưa thì bắt được ít — và không bao giờ vét quá phần còn lại
    kg = min((cong_co / cong_moi_kg) * mat_do, ton)
    if kg <= 1e-6:
        journal_rejected(w, aid, "danh_ca", "fishery_depleted")
        _ghi_su_co(w, aid, "ra sông về tay không — cá đã bị đánh gần cạn (hoặc hết công)")
        return
    w.ledger.huy(aid, "cong", cong_co, "dung", "đánh cá", w.tick)
    ghi_cong_dung(w, "nong", cong_co)
    w.ledger.sinh(aid, "ca", kg, "danh_ca", "đánh cá", w.tick)
    w.ca_ton = ton - kg
    w.ghi_thu_nhap(aid, "nong", kg * float(dc["ca_quy_doi_dinh_duong"]))
    w.events.ghi(w.tick, "danh_ca", id=aid, kg=round(kg, 1),
                 mat_do=round(mat_do, 2))
    journal_executed(w, aid, "danh_ca", code="fish_caught", detail=f"kg={kg:g}")
    if mat_do < float(dc["nguong_mat_do_canh_bao"]) and aid in w.agents:
        _ghi_su_co(w, aid, f"sông thưa cá hẳn (chỉ được {kg:.0f}kg) — đánh mãi thì cạn")
