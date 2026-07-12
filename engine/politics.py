"""Cơ chế nhà nước TRUNG LẬP — bầu cử, lập pháp, hối lộ, nghiệp đoàn, thuế, bạo động.

Engine ở đây CHỈ cung cấp VẬT LÝ chính trị: đếm phiếu, thu thuế theo suất, tái phân
phối, và vật lý sung công khi bất bình đẳng vượt ngưỡng + đủ số đông. MỌI ý định
(ứng cử, bỏ phiếu, thuế suất bao nhiêu, có bạo động hay không) đều do agent tự phát —
KHÔNG hardcode "địa chủ thì bị bạo động", KHÔNG thiên vị ứng viên (điều luật #7).

Mọi dịch chuyển tài sản đi QUA w.ledger.chuyen với chủ thể công quỹ CONG_QUY; thuế và
tái phân phối là chuyển-giao CÂN nên phương trình bảo toàn tự xanh (điều luật #1).
"""

from __future__ import annotations

from engine.ledger import EPSILON
from engine.metrics import gini
from engine.world import CONG_QUY, ChinhQuyen, World


def _chinh_tri_bat(w: World) -> bool:
    """Cờ scenario bật/tắt TOÀN BỘ tầng chính trị (ADR 0001 §C, MODEL_CHARTER §5–6).

    Mặc định TRUE để `preindustrial_closed_v1` + mọi run cũ giữ nguyên hành vi và
    world-hash. Khi FALSE (vd `agrarian_transition_v1`): tầng chính trị coi như không
    tồn tại — không tạo w.chinh_quyen, không thu thuế, không sung công; intent chính trị
    của agent bị bỏ qua ÊM (không lỗi, đúng điều luật #3)."""
    return bool(w.cfg.get("chinh_tri.bat", True))


def _fiscal_bat(w: World) -> bool:
    """Cờ scenario bật/tắt tầng TÀI KHÓA (treasury tích lũy + thủy lợi) — ADR 0004 §T08-C.

    Mặc định FALSE để preindustrial_closed_v1 + mọi run cũ giữ nguyên hành vi rebate và
    world-hash (không treasury stock, không thủy lợi). Xây trên tầng chính trị: chỉ có ý
    nghĩa khi chinh_tri.bat cũng TRUE (không có t* → không thu thuế → không có treasury)."""
    return bool(w.cfg.get("fiscal.bat", False))


def _bao_dam_chinh_quyen(w: World) -> ChinhQuyen:
    """Sinh nhà nước lần đầu có hành vi chính trị (trước đó làng vô chính phủ)."""
    if w.chinh_quyen is None:
        w.chinh_quyen = ChinhQuyen()
    return w.chinh_quyen


def _la_nguoi_lon_song(w: World, aid: str) -> bool:
    a = w.agents.get(aid)
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    return a is not None and a.con_song and a.truong_thanh(tt)


# ------------------------------------------------------------- bước đầu tick


def buoc_chinh_quyen(w: World, ke_hoach: dict) -> None:
    """Bước chính trị ĐẦU tick (trước sản xuất): bầu cử, lập pháp, hối lộ, nghiệp đoàn,
    đình công, kêu gọi. Chỉ tạo w.chinh_quyen khi thực sự có ý định chính trị."""
    if not _chinh_tri_bat(w):
        return  # tầng chính trị TẮT theo scenario — intent chính trị bị bỏ qua êm
    co_y_dinh = any(
        getattr(kh, "ung_cu", False) or getattr(kh, "bo_phieu", None)
        or getattr(kh, "ban_hanh_luat", None) or getattr(kh, "hoi_lo", None)
        or getattr(kh, "gia_nhap_nghiep_doan", False) or getattr(kh, "dinh_cong", False)
        or getattr(kh, "keu_goi", None)
        for kh in ke_hoach.values()
    )
    cq = w.chinh_quyen
    # tick bầu cử phải chạy kể cả không ai ứng cử (để hết nhiệm kỳ có thể khuyết)
    tick_bau = cq is not None and w.tick % int(w.cfg.get("chinh_tri.bau_cu_moi_n_tick")) == 0
    if not (co_y_dinh or tick_bau):
        return
    cq = _bao_dam_chinh_quyen(w)

    # đình công tick này dựng lại từ đầu (thành viên nghiệp đoàn chọn đình công)
    cq.dinh_cong_tick = set()

    _bau_cu(w, ke_hoach, cq)
    _lap_phap(w, ke_hoach, cq)
    _hoi_lo(w, ke_hoach)
    _nghiep_doan_dinh_cong(w, ke_hoach, cq)
    _keu_goi(w, ke_hoach)


def _bau_cu(w: World, ke_hoach: dict, cq: ChinhQuyen) -> None:
    """Bầu cử TRUNG LẬP: ứng viên tích lũy trong nhiệm kỳ (dân thấy trong prompt); tới
    tick bầu cử đếm phiếu (mỗi người 1 phiếu cho ứng viên hợp lệ), hết nhiệm kỳ thì
    người NHIỀU PHIẾU NHẤT (tie-break id nhỏ) nhậm chức. Không thiên vị ai."""
    # đăng ký ứng cử (mọi tick) — ứng viên hiện trong danh sách để dân bỏ phiếu
    for aid in sorted(ke_hoach):
        if getattr(ke_hoach[aid], "ung_cu", False) and _la_nguoi_lon_song(w, aid):
            cq.phieu.setdefault(aid, 0)

    if w.tick % int(w.cfg.get("chinh_tri.bau_cu_moi_n_tick")) != 0:
        return

    # đếm phiếu: mỗi người lớn còn sống 1 phiếu, chỉ cho ứng viên đã đăng ký
    tally = {cid: 0 for cid in cq.phieu if _la_nguoi_lon_song(w, cid)}
    for aid in sorted(ke_hoach):
        cho = getattr(ke_hoach[aid], "bo_phieu", None)
        if cho in tally and _la_nguoi_lon_song(w, aid):
            tally[cho] += 1
    cq.phieu = tally

    truong_song = cq.truong_lang is not None and _la_nguoi_lon_song(w, cq.truong_lang)
    het_nhiem_ky = not truong_song or w.tick >= cq.nhiem_ky_den
    if het_nhiem_ky and tally and max(tally.values()) > 0:
        # nhiều phiếu nhất; hòa thì id nhỏ hơn (tất định, không thiên vị)
        thang = sorted(tally, key=lambda c: (-tally[c], c))[0]
        cq.truong_lang = thang
        cq.nhiem_ky_den = w.tick + int(w.cfg.get("chinh_tri.nhiem_ky_tick"))
        w.events.ghi(w.tick, "bau_cu", truong_lang=thang, phieu=tally[thang],
                     nhiem_ky_den=cq.nhiem_ky_den)
        w.ghi_ky_uc(thang, f"tôi được làng bầu làm trưởng làng ({tally[thang]} phiếu)",
                    doi=True)
        cq.phieu = {}  # nhiệm kỳ mới — ứng viên đăng ký lại cho kỳ sau


def _lap_phap(w: World, ke_hoach: dict, cq: ChinhQuyen) -> None:
    """CHỈ trưởng làng đương nhiệm (còn sống) mới đặt được thuế suất / lương tối thiểu."""
    truong = cq.truong_lang
    if truong is None or not _la_nguoi_lon_song(w, truong):
        return
    luat = getattr(ke_hoach.get(truong), "ban_hanh_luat", None)
    if not isinstance(luat, dict):
        return
    loai = luat.get("loai")
    if loai == "thue":
        try:
            suat = float(luat.get("suat", 0.0))
        except (TypeError, ValueError):
            return
        tran = float(w.cfg.get("chinh_tri.thue_suat_toi_da"))
        cq.thue_suat = min(max(suat, 0.0), tran)
        w.events.ghi(w.tick, "ban_hanh_luat", boi=truong, loai_luat="thue",
                     suat=round(cq.thue_suat, 4))
    elif loai == "luong_toi_thieu":
        try:
            muc = float(luat.get("muc", 0.0))
        except (TypeError, ValueError):
            return
        cq.luong_toi_thieu = max(muc, 0.0)
        w.events.ghi(w.tick, "ban_hanh_luat", boi=truong, loai_luat="luong_toi_thieu",
                     muc=round(cq.luong_toi_thieu, 4))


def _hoi_lo(w: World, ke_hoach: dict) -> None:
    """Đút lót: chuyển thóc briber→den QUA LEDGER + cộng quan hệ. KHÔNG ép ban ơn —
    người nhận có chịu tác động hay không là tự phát (điều luật #7)."""
    cong_qh = float(w.cfg.get("quan_he.cong_moi_tuong_tac"))
    for aid in sorted(ke_hoach):
        hoi_lo = getattr(ke_hoach[aid], "hoi_lo", None)
        if not hoi_lo or not _la_nguoi_lon_song(w, aid):
            continue
        den, thoc = hoi_lo
        if den == aid or not w.chu_the_hoat_dong(den):
            continue
        so = min(float(thoc), w.ledger.so_du(aid, "thoc"))
        if so <= EPSILON:
            continue
        w.ledger.chuyen(aid, den, "thoc", so, f"hối lộ {den}", w.tick)
        w.cong_quan_he(aid, den, cong_qh)
        w.events.ghi(w.tick, "hoi_lo", tu=aid, den=den, thoc=round(so, 1))
        w.ghi_ky_uc(den, f"{aid} đút lót tôi {so:.0f} thóc")


def _nghiep_doan_dinh_cong(w: World, ke_hoach: dict, cq: ChinhQuyen) -> None:
    """Gia nhập nghiệp đoàn (bền); đình công (chỉ thành viên, theo tick)."""
    for aid in sorted(ke_hoach):
        kh = ke_hoach[aid]
        if not _la_nguoi_lon_song(w, aid):
            continue
        if getattr(kh, "gia_nhap_nghiep_doan", False) and aid not in cq.nghiep_doan:
            cq.nghiep_doan.add(aid)
            w.events.ghi(w.tick, "gia_nhap_nghiep_doan", ai=aid)
        if getattr(kh, "dinh_cong", False) and aid in cq.nghiep_doan:
            cq.dinh_cong_tick.add(aid)
    if cq.dinh_cong_tick:
        w.events.ghi(w.tick, "dinh_cong", so_nguoi=len(cq.dinh_cong_tick))


def _keu_goi(w: World, ke_hoach: dict) -> None:
    """Vận động townhall — thông tin THUẦN, phát tới cả làng qua event (không chạm ledger)."""
    for aid in sorted(ke_hoach):
        noi_dung = getattr(ke_hoach[aid], "keu_goi", None)
        if noi_dung and _la_nguoi_lon_song(w, aid):
            w.events.ghi(w.tick, "keu_goi", tu=aid, noi_dung=str(noi_dung)[:300])


# ------------------------------------------------------------- thuế (sau thu hoạch)


def thu_thue_va_chia(w: World) -> None:
    """Thu thuế = thue_suat × sản lượng gặt mỗi người → CONG_QUY; rồi CONG_QUY chia đều
    đầu người lớn còn sống. Mọi bước là chuyen CÂN nên bảo toàn tự xanh (điều luật #1)."""
    if not _chinh_tri_bat(w):
        return  # tầng chính trị TẮT theo scenario — không thu thuế
    cq = w.chinh_quyen
    if cq is None or cq.thue_suat <= EPSILON:
        return
    suat = cq.thue_suat
    # sản lượng gặt của MỖI NGƯỜI (entity đứng ngoài — thuế đánh trên "người")
    thu_theo_nguoi: dict[str, float] = {}
    for pid in sorted(w.gat_tick):
        aid, kg = w.gat_tick[pid]
        if aid in w.agents and w.agents[aid].con_song:
            thu_theo_nguoi[aid] = thu_theo_nguoi.get(aid, 0.0) + kg
    tong_thu = 0.0
    for aid in sorted(thu_theo_nguoi):
        thue = min(suat * thu_theo_nguoi[aid], w.ledger.so_du(aid, "thoc"))
        if thue > EPSILON:
            w.ledger.chuyen(aid, CONG_QUY, "thoc", thue, "thu thuế thu hoạch", w.tick)
            tong_thu += thue
    if tong_thu <= EPSILON:
        return
    if _fiscal_bat(w):
        # tài khóa BẬT: GIỮ thuế trong CONG_QUY (treasury stock) — KHÔNG rebate ngay.
        # Thóc vẫn nằm trong sổ (chuyen CÂN) nên bảo toàn xanh; treasury do trưởng làng chi.
        w.events.ghi(w.tick, "thue", tong_thu=round(tong_thu, 1),
                     suat=round(suat, 4), giu_treasury=True)
        return
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    nguoi_lon = sorted(a.id for a in w.agents.values()
                       if a.con_song and a.truong_thanh(tt))
    if not nguoi_lon:  # không ai để chia → thóc ở lại công quỹ (bảo toàn vẫn xanh)
        return
    _chia_deu(w, CONG_QUY, nguoi_lon, tong_thu, "trợ cấp công quỹ")
    w.events.ghi(w.tick, "thue", tong_thu=round(tong_thu, 1), so_nguoi=len(nguoi_lon),
                 suat=round(suat, 4))


def _chia_deu(w: World, tu: str, nguoi_nhan: list[str], tong: float, ly_do: str) -> None:
    """Chia `tong` thóc đều cho nguoi_nhan; người cuối nhận phần dư để CONG_QUY về 0
    (tránh trôi float — chuyển CÂN tuyệt đối)."""
    n = len(nguoi_nhan)
    phan_deu = tong / n
    for i, aid in enumerate(nguoi_nhan):
        phan = tong - phan_deu * (n - 1) if i == n - 1 else phan_deu
        if phan > EPSILON:
            w.ledger.chuyen(tu, aid, "thoc", phan, ly_do, w.tick)


# ------------------------------------------------------ tài khóa (fiscal.bat, ADR 0004 §T08-C)


def _xay_mot_don_vi(w: World, truong: str, ct: float, cg: float, cc: float) -> bool:
    """Xây 1 đơn vị thủy lợi NGUYÊN TỬ: treasury (CONG_QUY) trả thóc, trưởng làng góp gỗ +
    công; đối ứng là 1 đơn vị thủy lợi của CONG_QUY. Thiếu bất kỳ đầu vào nào → không đổi gì
    (LoiSoKep, kiểm đủ TRƯỚC — không trừ nửa vời). Mọi đơn vị có nguồn + counterpart."""
    from engine.ledger import DongSinhHuy, LoiSoKep, Transaction

    dong = []
    if ct > EPSILON:
        dong.append(DongSinhHuy(CONG_QUY, "thoc", -ct, "chi_cong"))
    if cg > EPSILON:
        dong.append(DongSinhHuy(truong, "go", -cg, "chi_cong"))
    if cc > EPSILON:
        dong.append(DongSinhHuy(truong, "cong", -cc, "chi_cong"))
    dong.append(DongSinhHuy(CONG_QUY, "thuy_loi", 1.0, "chi_cong"))
    try:
        w.ledger.ap_dung(Transaction(tick=w.tick, ly_do="chi công thủy lợi",
                                     sinh_huy=tuple(dong)))
        return True
    except LoiSoKep:
        return False


def thi_hanh_chi_cong(w: World, ke_hoach: dict) -> None:
    """Trưởng làng đương nhiệm chi CÔNG QUỸ xây thủy lợi (intent ban_hanh_luat loại
    'chi_cong'). Governance (ai được chi) TÁCH khỏi capacity (đủ treasury hay không):
    chỉ incumbent còn sống mới chi; xây được bao nhiêu tuỳ treasury + gỗ/công của trưởng.
    Gọi trong pha sản xuất (trưởng đã có công). Gated fiscal.bat + chinh_tri.bat."""
    if not (_chinh_tri_bat(w) and _fiscal_bat(w)):
        return
    cq = w.chinh_quyen
    if cq is None:
        return
    truong = cq.truong_lang
    if truong is None or not _la_nguoi_lon_song(w, truong):
        return  # office vacancy / trưởng chết → KHÔNG chi được (treasury không mất)
    luat = getattr(ke_hoach.get(truong), "ban_hanh_luat", None)
    if not isinstance(luat, dict) or luat.get("loai") != "chi_cong":
        return
    try:
        so_dv = int(luat.get("so_don_vi", 1))
    except (TypeError, ValueError):
        return
    tran = int(w.cfg.get("fiscal.chi_cong_toi_da_moi_tick"))
    so_dv = max(0, min(so_dv, tran))
    ct = float(w.cfg.get("fiscal.chi_phi_thoc_moi_don_vi"))
    cg = float(w.cfg.get("fiscal.chi_phi_go_moi_don_vi"))
    cc = float(w.cfg.get("fiscal.chi_phi_cong_moi_don_vi"))
    xay = 0
    for _ in range(so_dv):
        if not _xay_mot_don_vi(w, truong, ct, cg, cc):
            break  # cạn treasury/gỗ/công → dừng, phần đã xây giữ nguyên
        xay += 1
    if xay > 0:
        w.events.ghi(w.tick, "chi_cong", boi=truong, so_don_vi=xay,
                     thoc=round(ct * xay, 1), go=round(cg * xay, 1),
                     cong=round(cc * xay, 1))
        w.ghi_ky_uc(truong, f"tôi cho xây {xay} đơn vị thủy lợi từ công quỹ", doi=True)


def hao_mon_thuy_loi(w: World) -> None:
    """Thủy lợi hao mòn ty_le mỗi tick (SINK đã đăng ký). Không duy trì thì mất dần —
    lợi ích công có chi phí giữ. Gated fiscal.bat + chinh_tri.bat."""
    if not (_chinh_tri_bat(w) and _fiscal_bat(w)):
        return
    ton = w.ledger.so_du(CONG_QUY, "thuy_loi")
    if ton <= EPSILON:
        return
    ty_le = float(w.cfg.get("fiscal.hao_mon_ty_le_moi_tick"))
    mat = min(ton, ton * ty_le)
    if mat > EPSILON:
        w.ledger.huy(CONG_QUY, "thuy_loi", mat, "hao_mon", "hao mòn thủy lợi", w.tick)
        w.events.ghi(w.tick, "hao_mon_thuy_loi", mat=round(mat, 4), con=round(ton - mat, 4))


def he_so_thoi_tiet_thuy_loi(w: World, he_so_tt: float) -> float:
    """Lợi ích ĐO ĐƯỢC của thủy lợi: khi tồn ≥ ngưỡng, giảm thiệt hại hạn/lũ (he_so_tt<1)
    theo he_so_loi_ich. CHỈ giảm THIỆT HẠI (không thưởng mùa tốt). he_so_loi_ich=0 → placebo
    (thủy lợi không cải thiện gì → lợi ích đến từ cơ chế đã khai báo, không phải magic).
    Cộng đồng dùng chung một treasury/nhà nước nên áp cho cả cộng đồng (một làng: là per-làng).
    Gated fiscal.bat + chinh_tri.bat; TẮT → trả nguyên he_so_tt (hash legacy bất biến)."""
    if not (_chinh_tri_bat(w) and _fiscal_bat(w)) or he_so_tt >= 1.0:
        return he_so_tt
    nguong = float(w.cfg.get("fiscal.nguong_duy_tri_don_vi"))
    if w.ledger.so_du(CONG_QUY, "thuy_loi") < nguong:
        return he_so_tt
    loi = min(max(float(w.cfg.get("fiscal.he_so_loi_ich_han_lu")), 0.0), 1.0)
    return he_so_tt + loi * (1.0 - he_so_tt)


# ------------------------------------------------------------- bạo động (trước audit)


def buoc_bao_dong(w: World, ke_hoach: dict) -> None:
    """Bạo động = CƠ CHẾ TRUNG LẬP: chỉ kích hoạt khi Gini thóc > ngưỡng VÀ số người
    bạo động ≥ tỷ lệ số đông. Khi đó sung công ty_le_sung_cong thóc của nhóm giàu nhất
    (top decile) chia đều nhóm nghèo nhất, QUA LEDGER. Ngưỡng là HẰNG VẬT LÝ trong
    config (như thời tiết) — KHÔNG thiên vị giai cấp nào (điều luật #7)."""
    if not _chinh_tri_bat(w):
        return  # tầng chính trị TẮT theo scenario — không sung công
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    song = sorted((a for a in w.agents.values() if a.con_song and a.truong_thanh(tt)),
                  key=lambda a: a.id)
    n_lon = len(song)
    so_bao_dong = sum(
        1 for a in song if getattr(ke_hoach.get(a.id), "bao_dong", False)
    )
    w.so_bao_dong_tick = so_bao_dong
    if n_lon < 2:
        return
    nguong = float(w.cfg.get("chinh_tri.gini_nguong_bao_dong"))
    ty_so_dong = float(w.cfg.get("chinh_tri.ty_le_so_dong_bao_dong"))
    thoc = [w.ledger.so_du(a.id, "thoc") for a in song]
    if gini(thoc) <= nguong or so_bao_dong < ty_so_dong * n_lon:
        return  # thiếu điều kiện → KHÔNG có bạo động

    order = sorted(song, key=lambda a: (w.ledger.so_du(a.id, "thoc"), a.id))
    phan_vi = int(w.cfg.get("chinh_tri.phan_vi_giau_ngheo"))
    k = max(1, n_lon // phan_vi)  # top/bottom group (mặc định decile trong config)
    ngheo = order[:k]
    giau = order[-k:]
    ids_ngheo = {a.id for a in ngheo}
    ids_giau = {a.id for a in giau}
    if ids_giau & ids_ngheo:  # dân quá ít, không tách bạch giàu–nghèo → không sung công
        return
    ty_sung = float(w.cfg.get("chinh_tri.ty_le_sung_cong_bao_dong"))
    pool = 0.0
    for a in sorted(giau, key=lambda a: a.id):
        lay = ty_sung * w.ledger.so_du(a.id, "thoc")
        if lay > EPSILON:
            w.ledger.chuyen(a.id, CONG_QUY, "thoc", lay, "sung công bạo động", w.tick)
            pool += lay
    if pool <= EPSILON:
        return
    _chia_deu(w, CONG_QUY, sorted(ids_ngheo), pool, "chia lại bạo động")
    w.events.ghi(w.tick, "bao_dong", so_nguoi=so_bao_dong, sung_cong=round(pool, 1),
                 gini=round(gini(thoc), 4), so_giau=k, so_ngheo=len(ngheo))
