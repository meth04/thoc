"""Nhân khẩu: cưới, sinh, chết (đói/Gompertz/sinh nở), thừa kế mặc định (SPEC 2.7–2.8)."""

from __future__ import annotations

import math

import numpy as np

from engine import household
from engine.intents import KeHoach
from engine.types import Agent, Persona
from engine.world import VO_THUA_NHAN, World

TAI_SAN_ROI = ("nha", "cong_cu", "may")  # chia round-robin nguyên chiếc
TAI_SAN_CHIA_DEU = ("thoc", "go", "quang_dong", "xu")


def can_huyet(w: World, a: str, b: str) -> bool:
    """Chặn cận huyết: cha mẹ–con, anh chị em ruột/nửa, ông bà–cháu."""
    ag, bg = w.agents[a], w.agents[b]
    if b in (ag.cha, ag.me) or a in (bg.cha, bg.me):
        return True
    if ag.cha is not None and ag.cha == bg.cha:
        return True
    if ag.me is not None and ag.me == bg.me:
        return True
    ong_ba_a = {
        p
        for pid in (ag.cha, ag.me)
        if pid and pid in w.agents
        for p in (w.agents[pid].cha, w.agents[pid].me)
        if p
    }
    if b in ong_ba_a:
        return True
    ong_ba_b = {
        p
        for pid in (bg.cha, bg.me)
        if pid and pid in w.agents
        for p in (w.agents[pid].cha, w.agents[pid].me)
        if p
    }
    return a in ong_ba_b


def xu_ly_cau_hon(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    """Cầu hôn là intent; bên kia trả lời TICK SAU (SPEC 2.7)."""
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    from engine.action_journal import executed as journal_executed
    from engine.action_journal import rejected as journal_rejected

    # 1) Trả lời các đề nghị đã chờ từ tick trước
    con_cho: list[tuple[str, str, int]] = []
    for tu, den, tick_gui in w.cau_hon_cho:
        a, b = w.agents.get(tu), w.agents.get(den)
        if not a or not b or not a.con_song or not b.con_song:
            kh = ke_hoach.get(den)
            if kh is not None and tu in kh.tra_loi_cau_hon:
                journal_rejected(w, den, "tra_loi_cau_hon", "proposal_unavailable", target=tu)
            continue
        if a.vo_chong or b.vo_chong:
            kh = ke_hoach.get(den)
            if kh is not None and tu in kh.tra_loi_cau_hon:
                journal_rejected(w, den, "tra_loi_cau_hon", "marriage_unavailable", target=tu)
            continue
        kh = ke_hoach.get(den)
        tra_loi = kh.tra_loi_cau_hon.get(tu) if kh else None
        if tra_loi is None:
            if w.tick - tick_gui < 2:
                con_cho.append((tu, den, tick_gui))
            continue
        if tra_loi:
            a.vo_chong, b.vo_chong = den, tu
            w.cong_quan_he(tu, den, 1.0)
            # ADR 0007 §C: cưới (kể cả TÁI HÔN — không phải code path riêng, chỉ là `cuoi` áp
            # lên người goá) là một trong sáu biến cố ĐƯỢC PHÉP đổi membership. Ở đây chỉ KHAI
            # BÁO; `household.buoc_cu_tru` (bước 9b) là single-writer duy nhất của `w.cu_tru`.
            household.ghi_bien_co(w, "cuoi", a=tu, b=den)
            w.events.ghi(w.tick, "cuoi", vo=den if b.gioi_tinh == "nu" else tu,
                         chong=tu if a.gioi_tinh == "nam" else den)
            w.ghi_ky_uc(tu, f"tôi kết hôn với {b.ten} ({den})", doi=True)
            w.ghi_ky_uc(den, f"tôi kết hôn với {a.ten} ({tu})", doi=True)
            journal_executed(w, den, "tra_loi_cau_hon", target=tu, code="married")
        else:
            w.ghi_ky_uc(tu, f"tôi cầu hôn {b.ten} ({den}) nhưng bị từ chối")
            journal_executed(w, den, "tra_loi_cau_hon", target=tu, code="proposal_declined")
    w.cau_hon_cho = con_cho

    # 2) Nhận đề nghị mới từ kế hoạch tick này
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not kh.cau_hon:
            continue
        a = w.agents.get(aid)
        b = w.agents.get(kh.cau_hon)
        if not a or not b or not a.con_song or not b.con_song:
            journal_rejected(w, aid, "cau_hon", "partner_unavailable", target=kh.cau_hon)
            continue
        if not a.truong_thanh(tt) or not b.truong_thanh(tt):
            journal_rejected(w, aid, "cau_hon", "underage", target=kh.cau_hon)
            continue
        if a.vo_chong or b.vo_chong or a.gioi_tinh == b.gioi_tinh:
            journal_rejected(w, aid, "cau_hon", "marriage_ineligible", target=kh.cau_hon)
            continue
        if can_huyet(w, aid, kh.cau_hon):
            journal_rejected(w, aid, "cau_hon", "kinship_prohibited", target=kh.cau_hon)
            continue  # engine chặn cận huyết
        w.cau_hon_cho.append((aid, kh.cau_hon, w.tick))
        w.events.ghi(w.tick, "cau_hon", tu=aid, den=kh.cau_hon)
        journal_executed(w, aid, "cau_hon", target=kh.cau_hon,
                         code="proposal_sent", pending=True)


def _thai_ky_cfg(ss: dict) -> dict | None:
    """Đọc gate thai kỳ (WP-E, REPORT_REAL15_V5 §9) — bật bằng SỰ HIỆN DIỆN của khóa
    ``nhan_khau.sinh_san.thai_ky_tick``.

    Config legacy KHÔNG có khóa → trả ``None`` → ``sinh_con`` đi ĐÚNG code path cũ
    (giữ nguyên thứ tự rút RNG và các world-hash pin — tests/test_household_estate.py).
    Khóa có mặt nhưng vô nghĩa → raise (fail closed, không có fallback lặng lẽ).
    """
    if "thai_ky_tick" not in ss:
        return None

    def tick_nguyen(ten: str, raw: object, toi_thieu: int) -> int:
        if isinstance(raw, bool):
            raise ValueError(f"{ten} phải là số tick nguyên")
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{ten} phải là số tick nguyên") from exc
        if not math.isfinite(number) or not number.is_integer() or number < toi_thieu:
            raise ValueError(f"{ten} phải là số tick nguyên >= {toi_thieu}")
        return int(number)

    thai = tick_nguyen("nhan_khau.sinh_san.thai_ky_tick", ss["thai_ky_tick"], 1)
    hau_san = tick_nguyen(
        "nhan_khau.sinh_san.khoang_cach_sinh_toi_thieu_tick",
        ss.get("khoang_cach_sinh_toi_thieu_tick", 0),
        0,
    )
    p_doi = float(ss.get("p_sinh_doi", 0.0))
    if not math.isfinite(p_doi) or not 0.0 <= p_doi <= 1.0:
        raise ValueError("nhan_khau.sinh_san.p_sinh_doi phải trong [0, 1]")
    return {"thai_ky_tick": thai, "hau_san_tick": hau_san, "p_sinh_doi": p_doi}


def _trang_thai_sinh_san(w: World) -> tuple[dict[str, dict], dict[str, int]]:
    """Trạng thái thai kỳ + hậu sản. SINGLE-WRITER: chỉ module này mutate.

    ``w.thai_ky`` ánh xạ mẹ sang cha tại lúc thụ thai và tick dự sinh; ``w.hau_san``
    ánh xạ mẹ sang tick sớm nhất được xét thụ thai lại. Thuộc tính được tạo lười để
    checkpoint cũ vẫn nạp được trong work package không được sửa ``engine/world.py``.

    Đây là behavioral state: nó đổi việc một ca sinh có xảy ra ở tick sau hay không.
    Hiện pickle đã serialize nó, nhưng ``World.behavioral_state`` chưa băm nó. Test
    integration strict-xfail và handoff cuối work package giữ blocker này hiển thị.
    """
    if not hasattr(w, "thai_ky"):
        w.thai_ky = {}
    if not hasattr(w, "hau_san"):
        w.hau_san = {}
    return w.thai_ky, w.hau_san


def _xoa_sinh_san_khi_chet(w: World, aid: str) -> None:
    """Dọn thai kỳ/hậu sản ngay khi một agent chết; không để dead ghost trong state."""
    if _thai_ky_cfg(w.cfg.get("nhan_khau.sinh_san")) is None:
        return
    thai_ky, hau_san = _trang_thai_sinh_san(w)
    thai = thai_ky.pop(aid, None)
    hau_san.pop(aid, None)
    if thai is not None:
        w.events.ghi(
            w.tick,
            "thai_ky_ket_thuc",
            me=aid,
            cha=thai.get("cha"),
            thu_thai_tick=thai.get("thu_thai_tick"),
            sinh_du_kien=thai.get("sinh_tick"),
            ly_do="me_mat",
        )


def _an_ninh_luong_thuc(w: World, aid: str, nc: dict, tt: int) -> float:
    """An ninh lương thực của hộ: dự trữ / nhu cầu 2 tick."""
    ho = w.ho_cua(aid)
    du_tru = sum(w.ledger.so_du(m, "thoc") for m in ho)
    nhu_cau = sum(
        nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(tt) else nc["tre_em_kg_tick"]
        for m in ho
    )
    return min(1.0, du_tru / (2 * nhu_cau)) if nhu_cau > 0 else 1.0


def _rui_ro_sinh_no(w: World, g, ss: dict, aid: str) -> None:
    """Rủi ro tử vong sinh nở — CHỈ giảm khi hộ sản phụ CÓ HỢP ĐỒNG hiệu lực với người
    nắm blueprint y_te (giá cả do hai bên tự thỏa thuận trong hợp đồng — engine
    không tự móc túi ai, không tự đặt giá dịch vụ). Luôn rút ĐÚNG MỘT draw RNG."""
    rui_ro = ss["rui_ro_me"]
    ho_me = set(w.ho_cua(aid))
    thay_thuoc = None
    for bid in sorted(w.blueprints):
        bp = w.blueprints[bid]
        if (bp.linh_vuc != "y_te" or not w.chu_the_hoat_dong(bp.chu)
                or bp.chu in ho_me):
            continue
        co_hd = any(
            hd.trang_thai == "hieu_luc" and bp.chu in hd.cac_ben
            and ho_me & set(hd.cac_ben)
            for hd in w.hop_dong.values()
        )
        if co_hd:
            thay_thuoc = bp.chu
            break
    if thay_thuoc is not None:
        from engine.research import duoc_ap_dung

        san = float(ss["y_te_giam_rui_ro_san"])
        rui_ro *= max(san, 1.0 - duoc_ap_dung(w, thay_thuoc, "y_te"))
    if g.random() < rui_ro:
        w.agents[aid].health = 0.0  # tử vong sinh nở — xử lý ở bước chết
        from engine import metrics_demography

        metrics_demography.danh_dau_tu_vong_sinh_no(w, aid)
        w.events.ghi(w.tick, "tu_vong_sinh_no", id=aid)


def _tao_tre(w: World, g, me: Agent, cha: Agent) -> Agent:
    """Sinh MỘT trẻ. persona = trung bình cha mẹ ± đột biến (seeded,
    tham số nhan_khau.dot_bien_persona). Thứ tự rút RNG (k draws persona
    rồi 1 draw giới tính) GIỮ NGUYÊN so với code legacy — đổi là đổi hash pin."""
    cid = w.id_moi()
    pa, pb = cha.persona.as_dict(), me.persona.as_dict()
    db = w.cfg.get("nhan_khau.dot_bien_persona")
    bien_do = int(db["bien_do"])
    gia_tri = {
        k: int(np.clip(round((pa[k] + pb[k]) / 2 + g.integers(-bien_do, bien_do + 1)),
                       int(db["min"]), int(db["max"])))
        for k in pa
    }
    con = Agent(
        id=cid,
        ten=f"Con {cid[1:]}",
        gioi_tinh="nu" if g.random() < w.cfg.get("nhan_khau.ty_le_nu") else "nam",
        tuoi_tick=0,
        persona=Persona(**gia_tri),
        lang=me.lang,
        cha=cha.id,
        me=me.id,
    )
    w.agents[cid] = con
    cha.con.append(cid)
    me.con.append(cid)
    return con


def _ghi_khai_sinh(w: World, con: Agent, me: Agent, cha: Agent) -> None:
    from engine import metrics_demography

    metrics_demography.ghi_sinh(w)
    household.ghi_bien_co(w, "sinh", tre=con.id, me=me.id, cha=cha.id)
    w.events.ghi(w.tick, "sinh", id=con.id, cha=cha.id, me=me.id)
    # Cha có thể đã chết trong thai kỳ. Agent chết không được nhận ký ức mới.
    if cha.con_song:
        w.ghi_ky_uc(cha.id, f"vợ chồng tôi sinh con {con.ten} ({con.id})", doi=True)
    if me.con_song:
        w.ghi_ky_uc(me.id, f"vợ chồng tôi sinh con {con.ten} ({con.id})", doi=True)


def _sinh_con_tuc_thi(w: World, ke_hoach: dict[str, KeHoach], ss: dict, nc: dict,
                      tt: int, g) -> None:
    """Code path LEGACY (không thai kỳ): trúng xúc xắc là sinh NGAY trong tick.

    GIỮ NGUYÊN TỪNG DRAW RNG so với bản trước WP-E — bị pin bởi
    tests/test_household_estate.py::test_hash_legacy_pinned_off và hai hash vàng
    trong tests/test_resume_journal.py. Đổi thứ tự draw ở đây = phá determinism legacy."""
    for aid in sorted(w.agents):
        me = w.agents[aid]
        if not (me.con_song and me.gioi_tinh == "nu" and me.vo_chong):
            continue
        cha = w.agents.get(me.vo_chong)
        if not cha or not cha.con_song:
            continue
        t_min, t_max = ss["tuoi_me"]
        if not (t_min <= me.tuoi_nam <= t_max):
            continue
        kh = ke_hoach.get(aid)
        if kh is not None:
            me.y_dinh_sinh_con = kh.y_dinh_sinh_con
        an_ninh = _an_ninh_luong_thuc(w, aid, nc, tt)
        p = ss["p_goc"] * an_ninh * me.y_dinh_sinh_con
        if g.random() >= p:
            continue
        _rui_ro_sinh_no(w, g, ss, aid)
        con = _tao_tre(w, g, me, cha)
        _ghi_khai_sinh(w, con, me, cha)


def _sinh_con_thai_ky(w: World, ke_hoach: dict[str, KeHoach], ss: dict, nc: dict,
                      tt: int, g, gate: dict) -> None:
    """WP-E: thụ thai → mang thai ``thai_ky_tick`` tick → sinh → hậu sản
    ``khoang_cach_sinh_toi_thieu_tick`` tick không thụ thai lại.

    Khoảng cách tối thiểu giữa hai ca sinh của cùng một mẹ (trừ sinh đôi cùng ca)
    = hau_san_tick + thai_ky_tick. Sinh đôi là draw RNG riêng mỗi ca sinh
    (``p_sinh_doi``), ghi event ``sinh_doi`` bên cạnh hai event ``sinh``."""
    thai_ky, hau_san = _trang_thai_sinh_san(w)
    t_min, t_max = ss["tuoi_me"]
    for aid in sorted(w.agents):
        me = w.agents[aid]
        thai = thai_ky.get(aid)
        if not (me.con_song and me.gioi_tinh == "nu"):
            if not me.con_song:
                _xoa_sinh_san_khi_chet(w, aid)
            continue
        if thai is not None:
            # --- đang mang thai: KHÔNG thụ thai tiếp; đủ tick thì sinh ---
            if w.tick < int(thai["sinh_tick"]):
                continue
            # sinh nở xảy ra dù goá/ly tán — cha ghi theo lúc thụ thai (agent không bị
            # xóa khỏi w.agents kể cả khi đã chết, nên tra cứu trực tiếp là fail-closed)
            cha = w.agents.get(str(thai["cha"]))
            if cha is None:
                raise RuntimeError(f"thai kỳ của {aid} tham chiếu cha không tồn tại")
            _rui_ro_sinh_no(w, g, ss, aid)
            sinh_doi = g.random() < gate["p_sinh_doi"]  # một draw riêng cho mỗi ca sinh
            cac_con: list[str] = []
            for _ in range(2 if sinh_doi else 1):
                con = _tao_tre(w, g, me, cha)
                _ghi_khai_sinh(w, con, me, cha)
                cac_con.append(con.id)
            from engine import metrics_demography

            metrics_demography.ghi_ca_sinh(w, me.id, so_con=len(cac_con))
            if sinh_doi:
                w.events.ghi(
                    w.tick, "sinh_doi", me=aid, cha=cha.id,
                    cac_con=cac_con, so_con=len(cac_con),
                )
            del thai_ky[aid]
            if gate["hau_san_tick"] > 0:
                duoc_lai = int(w.tick + gate["hau_san_tick"])
                hau_san[aid] = duoc_lai
                w.events.ghi(
                    w.tick, "hau_san_bat_dau", me=aid,
                    duoc_thu_thai_lai_tu_tick=duoc_lai,
                )
            continue
        # --- chưa mang thai: hậu sản hết hạn độc lập với hôn nhân/tái hôn ---
        han = hau_san.get(aid)
        if han is not None:
            if w.tick < int(han):
                continue
            del hau_san[aid]
            w.events.ghi(w.tick, "hau_san_ket_thuc", me=aid)

        # --- đủ điều kiện thì xét thụ thai (như legacy, thêm gate sinh học) ---
        if not me.vo_chong:
            continue
        cha = w.agents.get(me.vo_chong)
        if not cha or not cha.con_song:
            continue
        if not (t_min <= me.tuoi_nam <= t_max):
            continue
        kh = ke_hoach.get(aid)
        if kh is not None:
            me.y_dinh_sinh_con = kh.y_dinh_sinh_con
        an_ninh = _an_ninh_luong_thuc(w, aid, nc, tt)
        p = ss["p_goc"] * an_ninh * me.y_dinh_sinh_con
        if g.random() >= p:
            continue
        sinh_du_kien = int(w.tick + gate["thai_ky_tick"])
        thai_ky[aid] = {"cha": cha.id, "thu_thai_tick": int(w.tick),
                        "sinh_tick": sinh_du_kien}
        w.events.ghi(w.tick, "thu_thai", me=aid, cha=cha.id, sinh_du_kien=sinh_du_kien)
        w.ghi_ky_uc(aid, "tôi đang mang thai, sắp đến ngày sinh")


def sinh_con(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    ss = w.cfg.get("nhan_khau.sinh_san")
    nc = w.cfg.raw()["nhu_cau"]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    g = w.rng.get("sinh_con", w.tick)
    gate = _thai_ky_cfg(ss)
    if gate is None:
        _sinh_con_tuc_thi(w, ke_hoach, ss, nc, tt, g)
    else:
        _sinh_con_thai_ky(w, ke_hoach, ss, nc, tt, g, gate)


def _q_nam(tuoi: float, gp: dict[str, float], ns: dict) -> float:
    """Gompertz nội suy log-linear giữa các mốc tuổi (nhan_khau.tu_vong_noi_suy);
    ngoài mốc cuối thì ngoại suy theo độ dốc đoạn cuối, chặn trần q/năm."""
    moc = [float(m) for m in ns["moc_tuoi"]]
    tran = float(ns["tran_q_nam"])
    log_q = [math.log(gp[f"q{int(m)}"]) for m in moc]
    if tuoi <= moc[0]:
        return math.exp(log_q[0])
    for i in range(1, len(moc)):
        if tuoi <= moc[i]:
            t = (tuoi - moc[i - 1]) / (moc[i] - moc[i - 1])
            return math.exp(log_q[i - 1] * (1 - t) + log_q[i] * t)
    do_doc = (log_q[-1] - log_q[-2]) / (moc[-1] - moc[-2])
    return min(tran, math.exp(log_q[-1] + do_doc * (tuoi - moc[-1])))


def _ly_do_suy_kiet(*, vua_doi: bool, vo_gia_cu: bool, co_dich: bool) -> str:
    """Gắn nhãn tử vong sức khỏe thấp theo cơ chế đang hoạt động."""
    # ``benh_tat`` không có cú sốc dịch đã từng làm một chuỗi phơi nhiễm do
    # vô gia cư tất định trông như một dịch bệnh bí ẩn trong real30_v3.
    if vua_doi:
        return "chet_doi"
    if vo_gia_cu:
        return "phoi_nhiem"
    if co_dich:
        return "benh_tat"
    return "kiet_suc"


def cai_chet(w: World) -> list[str]:
    sk = w.cfg.raw()["suc_khoe"]
    gp = w.cfg.get("nhan_khau.tu_vong_gompertz")
    ns = w.cfg.get("nhan_khau.tu_vong_noi_suy")
    nguyen_nhan = w.cfg.get("nhan_khau.tu_vong_nguyen_nhan", {})
    tach_nguyen_nhan = isinstance(nguyen_nhan, dict) and bool(nguyen_nhan.get("bat", False))
    tuoi_gia_tu = float(nguyen_nhan.get("tuoi_gia_tu", float("inf"))) if tach_nguyen_nhan else float("inf")
    g = w.rng.get("tu_vong", w.tick)
    chet: list[str] = []
    for aid in sorted(w.agents):
        a = w.agents[aid]
        if not a.con_song:
            continue
        vua_doi = w.tick - a.doi_tick <= w.tick_moi_nam()  # thiếu ăn trong vòng 1 năm gần đây
        ly_do = None
        ly_do_suy_kiet = _ly_do_suy_kiet(
            vua_doi=vua_doi,
            vo_gia_cu=bool(getattr(a, "vo_gia_cu", False)),
            co_dich=bool(getattr(w, "dich_benh_tick", False)),
        )
        if a.health <= 0:
            # The detailed causal taxonomy is a v3 reporting treatment.  The
            # base/legacy path must retain its old labels exactly, otherwise a
            # read-only diagnosis feature silently changes memories and the
            # pinned behavioural world hash.
            ly_do = ly_do_suy_kiet if tach_nguyen_nhan else (
                "chet_doi" if vua_doi else "kiet_suc"
            )
        elif a.health < sk["nguong_nguy_kich"] and g.random() < sk["p_chet_khi_nguy_kich"]:
            ly_do = ly_do_suy_kiet if tach_nguyen_nhan else (
                "chet_doi" if vua_doi else "benh_tat"
            )
        else:
            # Hazard Gompertz được khai báo theo NĂM. Căn theo độ dài tick để một
            # scenario 3 mùa/năm không lặng lẽ làm xác suất chết thường niên cao hơn.
            q_tick = 1 - (1 - _q_nam(a.tuoi_nam, gp, ns)) ** (1.0 / w.tick_moi_nam())
            if g.random() < q_tick:
                # đói mà chết thì là chết đói, dù trời có gọi đúng số
                yeu = a.health < float(sk["nguong_phan_loai_chet_doi"])
                if vua_doi and yeu:
                    ly_do = "chet_doi"
                elif tach_nguyen_nhan and a.tuoi_nam < tuoi_gia_tu:
                    ly_do = "tu_vong_co_ban"
                else:
                    ly_do = "tuoi_gia"
        if ly_do:
            from engine import metrics_demography, projects, quotes

            ly_do_metric = (
                "tu_vong_sinh_no" if metrics_demography.la_tu_vong_sinh_no(w, aid) else ly_do
            )
            metrics_demography.ghi_chet(w, a.tuoi_nam, ly_do_metric)
            a.con_song = False
            # Thai kỳ/hậu sản là state ảnh hưởng tương lai: người chết phải rời state ngay
            # trong tick chết, không chờ một vòng sinh sản sau và không thành ghost actor.
            _xoa_sinh_san_khi_chet(w, aid)
            # Refund a deceased participant's still-held project materials
            # before the estate path distributes their ledger balance.
            projects.xu_ly_nguoi_chet(w, aid)
            quotes.xu_ly_nguoi_chet(w, aid)
            chet.append(aid)
            w.events.ghi(w.tick, "chet", id=aid, tuoi=round(a.tuoi_nam, 1), ly_do=ly_do)
            # người thân khắc tang vào ký ức
            nhan_xung = [(a.vo_chong, f"vợ/chồng tôi {a.ten} qua đời ({ly_do})")]
            nhan_xung += [(c, f"cha/mẹ tôi {a.ten} qua đời ({ly_do})") for c in a.con]
            nhan_xung += [(p, f"con tôi {a.ten} mất ({ly_do})") for p in (a.cha, a.me)]
            for nid, loi in nhan_xung:
                if nid:
                    w.ghi_ky_uc(nid, loi, doi=True)
    return chet


def thua_ke_mac_dinh(w: World, aid: str) -> None:
    """Thừa kế: theo DI CHÚC nếu có (phần trăm tự do); không di chúc → chia đều con
    → vợ/chồng → đất về công, của rơi vào VO_THUA_NHAN."""
    a = w.agents[aid]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    ty_trong: dict[str, float] | None = None
    if a.di_chuc and a.di_chuc.get("phan_bo"):
        hop_le = {
            nid: max(0.0, float(pct))
            for nid, pct in a.di_chuc["phan_bo"].items()
            if nid in w.agents and w.agents[nid].con_song
        }
        tong = sum(hop_le.values())
        if tong > 0:
            ty_trong = {nid: pct / tong for nid, pct in sorted(hop_le.items())}
        # gia huấn truyền đời cho người nhận
        gia_huan = str(a.di_chuc.get("gia_huan", ""))[:400]
        if gia_huan:
            for nid in hop_le:
                w.agents[nid].gia_huan = gia_huan
        w.events.ghi(w.tick, "di_chuc", nguoi_mat=aid, phan_bo=a.di_chuc.get("phan_bo"))
    con_song = [c for c in a.con if c in w.agents and w.agents[c].con_song]
    if ty_trong:
        nguoi_nhan = list(ty_trong)
    elif con_song:
        nguoi_nhan = sorted(con_song)
    elif a.vo_chong and a.vo_chong in w.agents and w.agents[a.vo_chong].con_song:
        nguoi_nhan = [a.vo_chong]
    else:
        nguoi_nhan = []
    # phòng thủ cuối: KHÔNG bao giờ để tài sản/đất về tay chủ thể không hoạt động —
    # rỗng thì rơi về nhánh vô thừa nhận / đất về công bên dưới
    nguoi_nhan = [n for n in nguoi_nhan if w.chu_the_hoat_dong(n)]
    if ty_trong is not None:
        ty_trong = {n: ty_trong[n] for n in nguoi_nhan}
        tong_tt = sum(ty_trong.values())
        ty_trong = {n: v / tong_tt for n, v in ty_trong.items()} if tong_tt > 0 else None

    # tài sản trong sổ
    tai_san = w.ledger.tai_san_cua(aid)
    for ts, sl in sorted(tai_san.items()):
        if ts == "cong":
            continue  # công bốc hơi, không thừa kế
        if not nguoi_nhan:
            if ts.startswith("co_phan:"):
                # cổ phần vô thừa nhận bị hủy — tỷ trọng cổ đông còn lại tự tăng
                w.ledger.huy(aid, ts, sl, "giai_the", f"cổ phần vô thừa nhận {ts}", w.tick)
            else:
                w.ledger.chuyen(aid, VO_THUA_NHAN, ts, sl, f"vô thừa nhận {ts}", w.tick)
        elif ts in TAI_SAN_ROI or ts.startswith("vi_the:"):
            nguyen = int(sl)
            for i in range(nguyen):
                w.ledger.chuyen(
                    aid, nguoi_nhan[i % len(nguoi_nhan)], ts, 1.0, f"thừa kế {ts}", w.tick
                )
            du = sl - nguyen
            if du > 1e-9:
                w.ledger.chuyen(aid, nguoi_nhan[0], ts, du, f"thừa kế {ts} lẻ", w.tick)
        else:
            for nid in nguoi_nhan:
                phan = sl * (ty_trong[nid] if ty_trong else 1.0 / len(nguoi_nhan))
                if phan > 1e-12:
                    w.ledger.chuyen(aid, nid, ts, phan, f"thừa kế {ts}", w.tick)

    # blueprint (sáng chế) thừa kế như tài sản: round-robin cho người nhận
    bp_cua = sorted(b.id for b in w.blueprints.values() if b.chu == aid)
    for i, bid in enumerate(bp_cua):
        w.blueprints[bid].chu = nguoi_nhan[i % len(nguoi_nhan)] if nguoi_nhan else aid
        # không người nhận: blueprint thành tri thức chung? Không — giữ tên người mất
        # (không ai áp dụng được nữa; khuếch tán vẫn làm nghiên cứu lại rẻ hơn)

    # đất: chia round-robin cho người nhận; không ai → về công
    thua_cua = sorted(p.id for p in w.parcels.values() if p.chu == aid)
    for i, pid in enumerate(thua_cua):
        p = w.parcels[pid]
        if nguoi_nhan:
            nhan = nguoi_nhan[i % len(nguoi_nhan)]
            # trẻ chưa trưởng thành vẫn đứng tên (giám hộ tự nhiên bởi hộ)
            p.chu = nhan
        else:
            p.chu = None
            p.homestead_ai, p.homestead_dem = None, 0
    if thua_cua or tai_san:
        w.events.ghi(
            w.tick, "thua_ke", nguoi_mat=aid,
            nguoi_nhan=nguoi_nhan or ["cong"], so_thua=len(thua_cua),
        )
        for nid in nguoi_nhan:
            w.ghi_ky_uc(nid, f"tôi nhận thừa kế từ {a.ten} ({aid})", doi=True)
    # goá bụa
    if a.vo_chong and a.vo_chong in w.agents:
        w.agents[a.vo_chong].vo_chong = None
    _ = tt  # (giữ chữ ký ổn định — trẻ em vẫn được đứng tên đất)


def buoc_nhan_khau(w: World, ke_hoach: dict[str, KeHoach]) -> None:
    from engine import estate

    xu_ly_cau_hon(w, ke_hoach)
    sinh_con(w, ke_hoach)
    di_san_bat = estate._di_san_bat(w)
    for aid in cai_chet(w):
        if di_san_bat:
            # ADR 0007 §D: tài sản người chết vào chủ thể ledger CÓ HẠN `DI_SAN:<aid>` (bậc 0).
            # Bậc 1–3 (chủ nợ → di chúc → kin) chạy TRỌN VẸN ở bước 9c của CHÍNH tick này —
            # không có tick nào "tạm lệch rồi cân sau" (điều luật #1).
            estate.mo_di_san(w, aid)
        else:
            # LEGACY (đóng băng có ghi chú, ADR §D.8): của rơi vào `VO_THUA_NHAN` — một chủ
            # thể KHÔNG hoạt động, không ai lấy ra được (F-19). Không retcon.
            thua_ke_mac_dinh(w, aid)
