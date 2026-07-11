"""Trigger (SPEC 4.3): ai cần "nghĩ" (gọi LLM) trong tick này; còn lại chạy thẻ."""

from __future__ import annotations

from engine.world import World


def quet_trigger(w: World) -> dict[str, list[str]]:
    """Trả {agent_id: [lý do trigger]} — kỳ vọng 30–40% dân/tick."""
    cfg = w.cfg
    tt = cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = cfg.raw()["nhu_cau"]
    dinh_ky_n = int(cfg.get("minds.nghi_dinh_ky_moi_n_tick"))
    nguong_gia = float(cfg.get("minds.nguong_trigger_gia"))
    ket_qua: dict[str, list[str]] = {}

    def them(aid: str, ly_do: str) -> None:
        ket_qua.setdefault(aid, []).append(ly_do)

    # giá thóc/gỗ lệch >±30% trung bình 4 tick → cả làng để ý
    gia_lech = False
    for ts in ("go", "cong_cu"):
        gia = w.gia_gan_nhat(ts)
        tb = w.gia_tb_4_tick(ts)
        if gia and tb and abs(gia - tb) / tb > nguong_gia:
            gia_lech = True

    # đề nghị đích danh / mặc cả đến ai
    de_nghi_den: dict[str, int] = {}
    for dn in w.bang_rao.values():
        if dn.den is not None:
            de_nghi_den[dn.den] = de_nghi_den.get(dn.den, 0) + 1

    # nghĩa vụ đáo hạn tick này + đối tác vi phạm (tick trước ghi trong quan_he? dùng events
    # không tiện — dùng hợp đồng trạng thái) — đáo hạn:
    dao_han_cua: set[str] = set()
    for hd in w.hop_dong.values():
        if hd.trang_thai == "hieu_luc" and hd.thoi_han is not None:
            if w.tick + 1 - hd.tick_ky >= hd.thoi_han:
                for b in hd.cac_ben:
                    dao_han_cua.add(b)

    cau_hon_den = {den for _, den, _t in w.cau_hon_cho}

    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song or not a.truong_thanh(tt):
            continue
        # sắp đói: dự trữ hộ < 1 tick nhu cầu
        ho = w.ho_cua(aid)
        du_tru = sum(w.ledger.so_du(m, "thoc") for m in ho)
        nhu_cau = sum(
            nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"]
            for m in ho
        )
        if du_tru < nhu_cau:
            them(aid, "sap_doi")
        if gia_lech:
            them(aid, "gia_lech")
        if de_nghi_den.get(aid):
            them(aid, "nhan_de_nghi")
        if aid in dao_han_cua:
            them(aid, "dao_han")
        if aid in cau_hon_den:
            them(aid, "duoc_cau_hon")
        if a.tuoi_tick in (32, 60, 100):  # tuổi 16 / 30 / 50
            them(aid, "moc_tuoi")
        # định kỳ 1 lần / 4 tick, so le theo id (hash ổn định — không dùng hash() Python)
        so_le = int(aid[1:]) if aid[1:].isdigit() else len(aid)
        if (w.tick + so_le) % dinh_ky_n == 0:
            them(aid, "dinh_ky")
    return ket_qua
