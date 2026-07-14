"""Cư trú (residence) — state BỀN, engine-owned, scenario-gated (ADR 0007 §A–§C).

Vì sao module này tồn tại: hộ gia đình từng là *derived view* suy từ huyết thống
(``World.ho_cua`` legacy). Hệ quả là **sinh nhật thứ 16** — một biến cố KHÔNG có event,
KHÔNG có quyết định, KHÔNG có bút toán — lại đổi membership của hộ (``engine/world.py``
nhánh ``not c.truong_thanh(tt)``) ⇒ đổi ai được ăn (``engine/consumption.py``) ⇒ đổi ai
sống (F-18). Một biến-cố-không-tồn-tại không được phép có hệ quả vật lý.

Thiết kế (ADR 0007 §A.3 phương án D): residence là ``World.cu_tru`` (KHÔNG phải field của
dataclass ``Agent`` — ``behavioral_state()`` băm mọi field của ``Agent`` nên thêm một field
là đổi hash MỌI run legacy, F-22). Khối ``"residence"`` chỉ được chèn vào ``behavioral_state``
khi cờ BẬT ⇒ gate TẮT cho ra blob JSON y hệt hôm nay ⇒ ba hash pin legacy bất biến.

SINGLE-WRITER (INVARIANT ADR 0007 §C.2): ngoài module này, KHÔNG module nào được gán
``w.cu_tru``/``w._next_cu_tru``. Các module khác chỉ *ghi biến cố* qua ``ghi_bien_co`` rồi
``buoc_cu_tru`` (tick bước 9b) đọc-và-xóa.

Cờ đọc qua ``cfg.get("ho....", False)`` ⇒ KHÔNG cần thêm key vào base ``config/world.yaml``
(giữ ``cfg.digest()`` base bất biến).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Biến cố ĐƯỢC PHÉP đổi membership (ADR 0007 §C.1). "trưởng thành" KHÔNG nằm trong tập này —
# đó chính là invariant R2 của ADR (NO AGE-BASED ORPHANING).
BIEN_CO_HOP_LE = ("sinh", "cuoi", "tach_ho", "cuu_mang", "di_cu", "chet")
QUY_TAC_CAP_HOP_LE = ("nhu_cau_deu",)


@dataclass
class CuTru:
    """Một hộ cư trú: ai sống chung dưới một mái, ăn theo một quy tắc công khai."""

    id: str  # "R0001"
    thanh_vien: list[str]  # SORTED — single source of truth về membership
    lang: int
    nha_thua: str | None  # con trỏ VỊ TRÍ (không phải quyền sở hữu nhà)
    quy_tac_cap: str  # "nhu_cau_deu"
    lap_tick: int


# ---------------------------------------------------------------- cổng scenario


def _ho_bat(x: Any) -> bool:
    """Cờ tổng ``ho.bat`` (mặc định TẮT). Nhận Config hoặc World (đọc ``.cfg``)."""
    cfg = getattr(x, "cfg", x)
    return bool(cfg.get("ho.bat", False))


def _cu_tru_bat(x: Any) -> bool:
    """``ho.cu_tru_ben_vung`` — membership BỀN (ADR §A). TẮT ⇒ ``ho_cua`` legacy y nguyên."""
    cfg = getattr(x, "cfg", x)
    return _ho_bat(x) and bool(cfg.get("ho.cu_tru_ben_vung", False))


def _cap_luong_thuc_bat(x: Any) -> bool:
    """``ho.cap_luong_thuc`` — provisioning có ledger + event (ADR §B). HASH-NEUTRAL (P-1)."""
    cfg = getattr(x, "cfg", x)
    return _ho_bat(x) and bool(cfg.get("ho.cap_luong_thuc", False))


def _tach_ho_bat(x: Any) -> bool:
    """``ho.tach_ho.bat`` — tách hộ tường minh (ADR §C, transition 5)."""
    cfg = getattr(x, "cfg", x)
    return _cu_tru_bat(x) and bool(cfg.get("ho.tach_ho.bat", False))


def quy_tac_cap_cfg(x: Any) -> str:
    cfg = getattr(x, "cfg", x)
    return str(cfg.get("ho.quy_tac_cap", "nhu_cau_deu"))


# ---------------------------------------------------------------- validate config (fail-closed)


def kiem_tra_cau_hinh(cfg: Any) -> None:
    """Fail-closed cho cấu hình hộ/di sản (ADR 0007 §D.6, §G.2).

    Hai lỗi bị chặn NGAY tại ``tao_the_gioi``, không có nhánh "chạy tạm":

    1. ``ho.di_san.het_han == "cong"`` mà ``CONG_QUY`` KHÔNG có drain phủ mọi tài sản.
       ``politics.thu_thue_va_chia`` return sớm khi ``chinh_tri.bat`` false, và ngay cả khi
       bật, ``_chia_deu`` chỉ rebate ``tong_thu`` của tick đó và CHỈ tài sản ``"thoc"``.
       Route di sản về ``CONG_QUY`` ở đó chỉ là **SINK ĐỔI TÊN** (F-36) — nó pass invariant
       "so_du(VO_THUA_NHAN)==0" nhưng vi phạm E1′.
    2. ``ho.quy_tac_cap`` lạ: quy tắc phân bổ khác ``nhu_cau_deu`` là một ĐỊNH CHẾ PHÂN PHỐI
       (charter §5) — chưa qua cổng ⇒ không được chạy im lặng.
    """
    het_han = cfg.get("ho.di_san.het_han", "chia_deu_lang")
    if str(het_han) == "cong" and not _cong_quy_co_drain_day_du(cfg):
        raise SystemExit(
            "CẤU HÌNH BỊ CHẶN (ADR 0007 §D.6): ho.di_san.het_han='cong' nhưng CONG_QUY "
            "KHÔNG có drain phủ mọi loại tài sản (chinh_tri.bat="
            f"{bool(cfg.get('chinh_tri.bat', True))}; politics._chia_deu chỉ rebate 'thoc' "
            "của tick thu thuế). Route di sản về CONG_QUY ở đây là SINK ĐỔI TÊN — vi phạm "
            "INVARIANT E1′ (no absorbing sink / no renamed sink). Dùng 'chia_deu_lang' "
            "(mặc định), 'dau_gia', hoặc 'tan_ra' (null-treatment)."
        )
    qt = quy_tac_cap_cfg(cfg)
    if _ho_bat(cfg) and qt not in QUY_TAC_CAP_HOP_LE:
        raise SystemExit(
            f"CẤU HÌNH BỊ CHẶN: ho.quy_tac_cap='{qt}' chưa qua cổng định chế (charter §5). "
            f"Hợp lệ trong P1: {QUY_TAC_CAP_HOP_LE}"
        )
    che_do = str(cfg.get("ho.di_san.che_do", "kin"))
    if che_do not in ("kin", "chia_deu_lang", "dau_gia", "tan_ra"):
        raise SystemExit(f"CẤU HÌNH BỊ CHẶN: ho.di_san.che_do='{che_do}' không hợp lệ")
    if che_do == "dau_gia":
        raise SystemExit(
            "CẤU HÌNH BỊ CHẶN: ho.di_san.che_do='dau_gia' là PENDING (ADR 0007 §D.6, P2) — "
            "auction không tự nó có đích cuối; nó phải kèm route phân phối tiền thu về. "
            "Chưa cài ⇒ fail-closed thay vì im lặng rơi về chế độ khác."
        )


def _cong_quy_co_drain_day_du(cfg: Any) -> bool:
    """CONG_QUY có drain phủ MỌI loại tài sản không? — hôm nay: KHÔNG, và đó là sự thật (G-2).

    Hàm giữ nguyên hình dạng của điều kiện để nếu sau này có ai khai báo một drain thật
    (hàm có tên + cờ scenario) thì chỗ sửa là ở đây, chứ không phải bằng cách nới invariant.
    """
    return False


# ---------------------------------------------------------------- lookup


def _idx(w: Any) -> dict[str, str]:
    """Chỉ mục aid → rid, dựng lại khi version của ``cu_tru`` đổi (thuần derived, ngoài hash)."""
    ver = getattr(w, "_cu_tru_ver", 0)
    idx = getattr(w, "_cu_tru_idx", None)
    if idx is None or idx.get("__ver__") != ver:
        idx = {"__ver__": ver}
        for rid in sorted(w.cu_tru):
            for m in w.cu_tru[rid].thanh_vien:
                idx[m] = rid
        w._cu_tru_idx = idx
    return idx


def rid_cua(w: Any, aid: str) -> str | None:
    if not getattr(w, "cu_tru", None):
        return None
    return _idx(w).get(aid)


def ho_cua_cu_tru(w: Any, aid: str) -> list[str]:
    """Thành viên hộ của ``aid`` theo state bền (nhánh ON của ``World.ho_cua``).

    KHÔNG đọc tuổi ở bất kỳ đâu — đó là invariant R2. Người chưa có hộ (chưa qua bước 9b của
    tick sinh ra) đứng một mình; caller vốn đã lọc ``con_song``."""
    rid = rid_cua(w, aid)
    if rid is None:
        return [aid]
    return list(w.cu_tru[rid].thanh_vien)


# ---------------------------------------------------------------- biến cố transient


def ghi_bien_co(w: Any, loai: str, **du_lieu: Any) -> None:
    """Module khác (demography/xa_hoi/tick) khai báo một biến cố membership.

    KHÔNG mutate ``w.cu_tru`` — chỉ xếp hàng; ``buoc_cu_tru`` là single-writer. Gate TẮT ⇒
    no-op ⇒ không rò rỉ bộ nhớ vào run legacy."""
    if not _cu_tru_bat(w):
        return
    if loai not in BIEN_CO_HOP_LE:
        raise ValueError(f"biến cố membership không hợp lệ: {loai}")
    if not hasattr(w, "bien_co_ho") or w.bien_co_ho is None:
        w.bien_co_ho = {}
    w.bien_co_ho.setdefault(loai, []).append(du_lieu)


def _lay_bien_co(w: Any, loai: str) -> list[dict[str, Any]]:
    return list(getattr(w, "bien_co_ho", {}).get(loai, []))


# ---------------------------------------------------------------- khởi tạo


def khoi_tao_cu_tru(w: Any) -> None:
    """t0: mỗi agent một hộ riêng (dân số t0 toàn người lớn độc thân)."""
    if not _cu_tru_bat(w):
        return
    qt = quy_tac_cap_cfg(w)
    for aid in sorted(w.agents):
        _lap_ho(w, [aid], w.agents[aid].lang, qt, su_kien=None)


def _lap_ho(w: Any, thanh_vien: list[str], lang: int, quy_tac: str,
            su_kien: str | None) -> str:
    w._next_cu_tru += 1
    rid = f"R{w._next_cu_tru:04d}"
    w.cu_tru[rid] = CuTru(
        id=rid, thanh_vien=sorted(thanh_vien), lang=int(lang),
        nha_thua=None, quy_tac_cap=quy_tac, lap_tick=w.tick,
    )
    _bump(w)
    if su_kien:
        w.events.ghi(w.tick, "lap_ho", ho=rid, thanh_vien=sorted(thanh_vien), ly_do=su_kien)
    return rid


def _bump(w: Any) -> None:
    w._cu_tru_ver = getattr(w, "_cu_tru_ver", 0) + 1


def _roi_ho(w: Any, aid: str) -> str | None:
    rid = rid_cua(w, aid)
    if rid is None:
        return None
    cu = w.cu_tru[rid]
    cu.thanh_vien = [m for m in cu.thanh_vien if m != aid]
    _bump(w)
    return rid


def _vao_ho(w: Any, aid: str, rid: str) -> None:
    cu = w.cu_tru[rid]
    if aid not in cu.thanh_vien:
        cu.thanh_vien = sorted([*cu.thanh_vien, aid])
        _bump(w)


# ---------------------------------------------------------------- phụ thuộc trực hệ


def _song(w: Any, pid: str | None) -> bool:
    return bool(pid and pid in w.agents and w.agents[pid].con_song)


def _phu_thuoc_di_theo(w: Any, nguoi_di: str, rid_nguon: str) -> list[str]:
    """Trẻ chưa trưởng thành trong hộ nguồn mà ``nguoi_di`` là người lớn DUY NHẤT còn sống
    chịu trách nhiệm (cha/mẹ/giám hộ). Con riêng đi theo cha/mẹ ruột — đúng ADR §C.3."""
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    cu = w.cu_tru.get(rid_nguon)
    if cu is None:
        return []
    ra: list[str] = []
    for cid in sorted(cu.thanh_vien):
        c = w.agents.get(cid)
        if c is None or not c.con_song or cid == nguoi_di or c.truong_thanh(tt):
            continue
        nguoi_lo = [p for p in (c.cha, c.me, c.giam_ho) if _song(w, p)]
        if nguoi_di in nguoi_lo and all(p == nguoi_di for p in nguoi_lo):
            ra.append(cid)
    return ra


def _mang_theo_khi_roi_ho(w: Any, nguoi_di: str, rid_nguon: str) -> list[str]:
    """Ai đi theo ``nguoi_di`` khi họ rời hộ vì CƯỚI hoặc DI CƯ.

    Ngoài phụ thuộc trực hệ (§C.3), thêm một luật KHÔNG-BỎ-RƠI: nếu sau khi họ đi, hộ nguồn
    KHÔNG còn một người lớn nào sống, thì mọi người còn lại đi theo (hộ nguồn nhập vào hộ mới).
    Không có luật này, cưới/di cư có thể để lại một hộ toàn trẻ em — tức là tái tạo đúng loại
    orphaning mà ADR 0007 đang xoá, chỉ đổi nguyên nhân từ "tuổi" sang "cha mẹ đi cưới".

    Khác với ``tach_ho``: tách hộ BỊ TỪ CHỐI (`no_adult_left`) thay vì kéo cả nhà đi, vì tách hộ
    là một lựa chọn còn cưới/di cư là hộ nguồn ĐANG TAN.
    """
    mang = set(_phu_thuoc_di_theo(w, nguoi_di, rid_nguon))
    cu = w.cu_tru.get(rid_nguon)
    if cu is None:
        return sorted(mang)
    di_het = {nguoi_di, *mang}
    con_lai = [m for m in cu.thanh_vien if m not in di_het and _song(w, m)]
    if con_lai and not _con_nguoi_lon(w, rid_nguon, di_het):
        mang |= set(con_lai)
    return sorted(mang)


def _con_nguoi_lon(w: Any, rid: str, tru: set[str]) -> bool:
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    cu = w.cu_tru.get(rid)
    if cu is None:
        return False
    return any(
        m not in tru and w.agents[m].con_song and w.agents[m].truong_thanh(tt)
        for m in cu.thanh_vien if m in w.agents
    )


# ---------------------------------------------------------------- bước 9b


def buoc_cu_tru(w: Any, ke_hoach: dict[str, Any]) -> None:
    """SINGLE-WRITER của ``w.cu_tru`` — tick bước 9b (sau ``cuu_mang_mo_coi``, trước audit).

    Thứ tự transition cố định (ADR §C.3): chet → sinh → cuu_mang → cuoi → tach_ho → di_cu →
    tan_ho. Mọi vòng lặp duyệt ``sorted`` ⇒ tất định tuyệt đối, không phụ thuộc dict order.
    **Không transition nào đọc ``truong_thanh()`` để quyết định membership** (INVARIANT R2);
    ``truong_thanh`` chỉ dùng để (a) xét tư cách người TÁCH HỘ và (b) xác định ai là người lớn
    chịu trách nhiệm — không phải để đuổi ai ra khỏi hộ.
    """
    if not _cu_tru_bat(w):
        return
    qt = quy_tac_cap_cfg(w)

    # 1. chet — người chết rời hộ (R4: không có "dead resident")
    for aid in sorted(w.agents):
        if not w.agents[aid].con_song and rid_cua(w, aid) is not None:
            _roi_ho(w, aid)

    # 2. sinh — trẻ mới sinh vào hộ của MẸ; mẹ chết ⇒ cha; cả hai chết ⇒ để cuu_mang xử
    for bc in sorted(_lay_bien_co(w, "sinh"), key=lambda d: str(d.get("tre"))):
        tre = str(bc["tre"])
        a = w.agents.get(tre)
        if a is None or not a.con_song or rid_cua(w, tre) is not None:
            continue
        rid = None
        for pid in (a.me, a.cha, a.giam_ho):
            if _song(w, pid):
                rid = rid_cua(w, pid)
                if rid is not None:
                    break
        if rid is None:
            continue  # không cha không mẹ ⇒ nhánh mồ côi/quét cuối lo
        _vao_ho(w, tre, rid)
        w.events.ghi(w.tick, "vao_ho", tre=tre, ho=rid, ly_do="sinh")

    # 3. cuu_mang — trẻ mồ côi chuyển sang hộ của giám hộ
    for bc in sorted(_lay_bien_co(w, "cuu_mang"), key=lambda d: str(d.get("tre"))):
        tre, nguoi_nuoi = str(bc["tre"]), str(bc["nguoi_nuoi"])
        a = w.agents.get(tre)
        if a is None or not a.con_song or not _song(w, nguoi_nuoi):
            continue
        den = rid_cua(w, nguoi_nuoi)
        if den is None:
            continue
        tu = rid_cua(w, tre)
        if tu == den:
            continue
        if tu is not None:
            _roi_ho(w, tre)
        _vao_ho(w, tre, den)
        w.events.ghi(w.tick, "chuyen_ho", nguoi=tre, tu_ho=tu, den_ho=den, ly_do="cuu_mang")

    # 4. cuoi / tái hôn — spouse-joins: ai có rid LỚN HƠN chuyển sang hộ người kia
    for bc in sorted(_lay_bien_co(w, "cuoi"), key=lambda d: (str(d.get("a")), str(d.get("b")))):
        a_id, b_id = str(bc["a"]), str(bc["b"])
        if not (_song(w, a_id) and _song(w, b_id)):
            continue
        ra, rb = rid_cua(w, a_id), rid_cua(w, b_id)
        if ra is None or rb is None or ra == rb:
            continue  # đã cùng hộ ⇒ no-op (tie-break "rid bằng nhau" của ADR §C.3)
        di, o_lai = (a_id, b_id) if ra > rb else (b_id, a_id)
        tu, den = (ra, rb) if ra > rb else (rb, ra)
        mang_theo = _mang_theo_khi_roi_ho(w, di, tu)
        _roi_ho(w, di)
        _vao_ho(w, di, den)
        for cid in mang_theo:
            _roi_ho(w, cid)
            _vao_ho(w, cid, den)
        w.events.ghi(w.tick, "nhap_ho", nguoi=di, mang_theo=mang_theo, tu_ho=tu,
                     den_ho=den, ly_do="cuoi", ban_doi=o_lai)

    # 5. tach_ho — QUYẾT ĐỊNH của agent, có event, có hệ quả (tự lo ăn, có thể vô gia cư)
    if _tach_ho_bat(w):
        tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
        for aid in sorted(ke_hoach):
            if not getattr(ke_hoach[aid], "tach_ho", False):
                continue
            a = w.agents.get(aid)
            if a is None or not a.con_song:
                w.ghi_unrecognized(aid, "tach_ho", "khong_hoat_dong")
                continue
            if not a.truong_thanh(tt):
                w.ghi_unrecognized(aid, "tach_ho", "chua_truong_thanh")
                continue
            tu = rid_cua(w, aid)
            if tu is None:
                w.ghi_unrecognized(aid, "tach_ho", "khong_hoat_dong")
                continue
            mang_theo = _phu_thuoc_di_theo(w, aid, tu)
            di_het = {aid, *mang_theo}
            con_lai = [m for m in w.cu_tru[tu].thanh_vien
                       if m not in di_het and _song(w, m)]
            if not con_lai:
                w.ghi_unrecognized(aid, "tach_ho", "khong_can_tach")
                continue
            if not _con_nguoi_lon(w, tu, di_het):
                w.ghi_unrecognized(aid, "tach_ho", "no_adult_left")
                continue
            for m in sorted(di_het):
                _roi_ho(w, m)
            den = _lap_ho(w, sorted(di_het), a.lang, qt, su_kien=None)
            w.events.ghi(w.tick, "tach_ho", nguoi=aid, mang_theo=mang_theo, tu_ho=tu,
                         den_ho=den, ly_do="tach_ho")

    # 6. di_cu — người di cư (+ phụ thuộc trực hệ) lập hộ MỚI ở làng mới; hiệu lực CUỐI tick
    # (họ ĐÃ ăn với hộ cũ trong tick này — hành vi khai báo, không phải bug)
    for bc in sorted(_lay_bien_co(w, "di_cu"), key=lambda d: str(d.get("nguoi"))):
        aid = str(bc["nguoi"])
        a = w.agents.get(aid)
        if a is None or not a.con_song:
            continue
        tu = rid_cua(w, aid)
        if tu is None:
            continue
        mang_theo = _mang_theo_khi_roi_ho(w, aid, tu)
        di_het = {aid, *mang_theo}
        for m in sorted(di_het):
            _roi_ho(w, m)
        den = _lap_ho(w, sorted(di_het), a.lang, qt, su_kien=None)
        w.events.ghi(w.tick, "tach_ho", nguoi=aid, mang_theo=mang_theo, tu_ho=tu,
                     den_ho=den, ly_do="di_cu")

    # 6b. quét an toàn — người sống chưa thuộc hộ nào (trẻ mồ côi không ai cưu mang, agent
    # xuất hiện ngoài đường sinh) lập hộ riêng. Nó KHÔNG cứu ai: sống một mình mà không có
    # kho thì vẫn đói thật (ADR §A.8).
    for aid in sorted(w.agents):
        a = w.agents[aid]
        if a.con_song and rid_cua(w, aid) is None:
            _lap_ho(w, [aid], a.lang, qt, su_kien="khong_ho")

    # 7. tan_ho — hộ rỗng thì giải thể
    for rid in sorted(w.cu_tru):
        if not w.cu_tru[rid].thanh_vien:
            del w.cu_tru[rid]
            _bump(w)
            w.events.ghi(w.tick, "tan_ho", ho=rid)

    # đồng bộ thuộc tính suy ra (làng + thửa đặt nhà) — tất định theo id
    for rid in sorted(w.cu_tru):
        cu = w.cu_tru[rid]
        song = [m for m in cu.thanh_vien if _song(w, m)]
        if song:
            cu.lang = int(w.agents[song[0]].lang)
            nha = sorted(
                str(w.agents[m].nha_thua) for m in song if w.agents[m].nha_thua
            )
            cu.nha_thua = nha[0] if nha else None
    _bump(w)

    if getattr(w, "bien_co_ho", None):
        w.bien_co_ho = {}

    _kiem_invariant(w)


def _kiem_invariant(w: Any) -> None:
    """R1 (partition) + R4 (no dead resident) — fail-loud, không "sửa êm" (điều luật #1)."""
    thay: dict[str, str] = {}
    for rid in sorted(w.cu_tru):
        for m in w.cu_tru[rid].thanh_vien:
            if m in thay:
                raise ValueError(
                    f"[tick {w.tick}] R1 vi phạm: {m} thuộc hai hộ {thay[m]} và {rid}"
                )
            thay[m] = rid
            a = w.agents.get(m)
            if a is None or not a.con_song:
                raise ValueError(f"[tick {w.tick}] R4 vi phạm: người chết {m} còn trong {rid}")
    song = {aid for aid, a in w.agents.items() if a.con_song}
    if set(thay) != song:
        thieu = sorted(song - set(thay))
        raise ValueError(f"[tick {w.tick}] R1 vi phạm: người sống không có hộ: {thieu}")


# ---------------------------------------------------------------- provisioning (§B)


def cap_va_an(w: Any, ho: list[str], nguon: str, ts: str, tru: float, quy_doi: float,
              con_thieu: dict[str, float], rid: str) -> None:
    """Cấp lương thực TƯỜNG MINH rồi ăn (ADR §B.4): ``chuyen(người-cấp → người-ăn)`` NGAY
    TRƯỚC ``huy(người-ăn, "an")``, kèm event ``cap_luong_thuc``.

    Quy tắc ``nhu_cau_deu``: mỗi thành viên được cấp đúng ``nhu_cau`` của mình; nguồn rút giữ
    ĐÚNG thứ tự legacy (kho lớn nhất gánh trước) và quy tắc thiếu-đều-theo-tỷ-lệ giữ nguyên —
    nếu đổi là mất tính bookkeeping-only (P-1).

    Bảo toàn: mỗi kg đi qua ĐÚNG một ``chuyen`` (tùy chọn) và ĐÚNG một ``huy`` sink ``"an"``.
    Không mint, không double-consume; ``tru ≤ so_du(nguon)`` nên không bao giờ âm số dư.
    """
    con_lai = tru
    for e in sorted(ho):
        if con_lai <= 1e-12:
            break
        can = con_thieu.get(e, 0.0)
        if can <= 1e-12:
            continue
        phan = min(con_lai, can / quy_doi)
        if phan <= 1e-12:
            continue
        if e != nguon:
            w.ledger.chuyen(nguon, e, ts, phan, f"cấp lương thực {ts}", w.tick)
            w.events.ghi(w.tick, "cap_luong_thuc", tu=nguon, den=e, tai_san=ts,
                         so_luong=round(phan, 6), quy_thoc=round(phan * quy_doi, 6),
                         ho=rid, ly_do="quy_tac_ho")
        w.ledger.huy(e, ts, phan, "an", f"ăn {ts}", w.tick)
        con_thieu[e] = can - phan * quy_doi
        con_lai -= phan
    if con_lai > 1e-12:
        # Nhu cầu cả hộ đã đủ mà vẫn còn phần rút ra (chỉ xảy ra do trôi float): người có kho
        # tự ăn nốt — KHÔNG mint, KHÔNG bỏ rơi kg nào ngoài sổ.
        w.ledger.huy(nguon, ts, con_lai, "an", f"ăn {ts}", w.tick)


__all__ = [
    "BIEN_CO_HOP_LE",
    "CuTru",
    "_cap_luong_thuc_bat",
    "_cu_tru_bat",
    "_ho_bat",
    "_tach_ho_bat",
    "buoc_cu_tru",
    "cap_va_an",
    "ghi_bien_co",
    "ho_cua_cu_tru",
    "khoi_tao_cu_tru",
    "kiem_tra_cau_hinh",
    "rid_cua",
]
