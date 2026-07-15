"""Trigger (SPEC 4.3): ai cần "nghĩ" (gọi LLM) trong tick này; còn lại chạy thẻ."""

from __future__ import annotations

from engine.world import World

# Higher numbers mean that a scarce LLM decision slot is economically more
# urgent.  This is a scheduler priority, never an action recommendation: the
# selected person can still choose any valid action or do nothing.
UU_TIEN_TRIGGER = {
    "sap_doi": 100,
    "cho_o_nguy_kich": 95,
    "dao_han": 85,
    "nhan_de_nghi": 80,
    "duoc_cau_hon": 70,
    "moc_tuoi": 55,
    "gia_lech": 45,
    "nghe_tin_bang_rao": 35,
    "dinh_ky": 10,
    "dieu_phoi_toi_thieu": 0,
}


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

    # đề nghị CÔNG KHAI mới đăng → lan tới người quen của người đăng trước
    # (SPEC 2.1: thứ tự tiếp cận bảng rao theo đồ thị quan hệ)
    nghe_tin_rao: set[str] = set()
    for dn in w.bang_rao.values():
        if dn.den is None and w.tick - dn.tick <= 1:
            quen = sorted(
                (b.id for b in w.agents.values()
                 if b.con_song and b.id != dn.tu and b.truong_thanh(16)),
                key=lambda bid: (-w.uy_tin(dn.tu, bid), bid),
            )[:4]
            nghe_tin_rao.update(quen)

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
        # Exposure is a physical threat distinct from hunger.  The config
        # gate keeps legacy treatments byte-for-byte unchanged.
        nha_o = cfg.get("suc_khoe.nha_o", {})
        san_cho = cfg.get("minds.san_cho_o_toi_thieu", {})
        if (isinstance(nha_o, dict) and bool(nha_o.get("bat", False))
                and isinstance(san_cho, dict) and bool(san_cho.get("bat", False))):
            co_nha = any(w.ledger.so_du(m, "nha") >= 1.0 for m in ho)
            nguong_cho = float(san_cho.get("nguong_health_khoi_cong", 50.0))
            if not co_nha and a.health <= nguong_cho:
                them(aid, "cho_o_nguy_kich")
        if gia_lech:
            them(aid, "gia_lech")
        if de_nghi_den.get(aid):
            them(aid, "nhan_de_nghi")
        if aid in nghe_tin_rao:
            them(aid, "nghe_tin_bang_rao")
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


def chon_nguoi_nghi(w: World, triggers: dict[str, list[str]], *,
                     toi_da: int, toi_thieu: int = 1) -> dict[str, list[str]]:
    """Choose a bounded, deterministic and fair set of LLM decision makers.

    The old orchestrator sent every triggered resident to the provider.  A
    periodic trigger could therefore create dozens of calls, while a quiet
    tick made zero calls.  This selector first serves material urgency, then
    uses a tick-rotating tie break so equal residents do not permanently lose
    to a low lexical id.  If living adults exist but no trigger fires, one is
    deliberately scheduled for a normal review.
    """
    cap = max(0, int(toi_da))
    floor = max(0, int(toi_thieu))
    adult_age = int(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    eligible = [
        aid for aid in sorted(w.agents)
        if w.agents[aid].con_song and w.agents[aid].truong_thanh(adult_age)
    ]
    if cap == 0 or not eligible:
        return {}

    index = {aid: i for i, aid in enumerate(eligible)}
    rotation = w.tick % len(eligible)

    def priority(aid: str) -> int:
        return max((UU_TIEN_TRIGGER.get(reason, 20)
                    for reason in triggers.get(aid, [])), default=-1)

    candidates = [aid for aid in eligible if aid in triggers]
    if not candidates and floor:
        # A quiet village still has ordinary decisions (saving, an intended
        # investment, a reply next tick).  This is a review opportunity, not
        # fabricated information or an engine action.
        candidates = eligible[:]
        triggers = {**triggers}
        for aid in candidates:
            triggers.setdefault(aid, ["dieu_phoi_toi_thieu"])

    candidates.sort(
        key=lambda aid: (-priority(aid), (index[aid] - rotation) % len(eligible), aid)
    )
    chosen = candidates[:cap]
    # ``floor`` is normally one and cap is validated positive.  The guard
    # documents the intentional exception: a world with no adult has nobody
    # who can make an economic decision, so an empty call is not manufactured.
    if len(chosen) < floor and eligible:
        for aid in eligible:
            if aid not in chosen:
                chosen.append(aid)
            if len(chosen) >= min(cap, floor):
                break
    return {aid: list(triggers.get(aid, ("dieu_phoi_toi_thieu",))) for aid in chosen}
