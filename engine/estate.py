"""Di sản (estate) — chủ thể ledger CÓ HẠN, không phải một cái ví vĩnh viễn (ADR 0007 §D).

Bệnh đang chữa (F-19): tài sản không người thừa kế rơi vào ``VO_THUA_NHAN``. Đó KHÔNG phải
chủ thể hoạt động (``World.chu_the_hoat_dong``) ⇒ không ai giao dịch/trộm/ký hợp đồng/nhận đất
với nó ⇒ của cải **kẹt vĩnh viễn**. Checkpoint tick 180 của ``real60_spatial``: 92.5% thóc,
100% gà và **căn nhà DUY NHẤT** của thế giới nằm trong đó.

Bệnh thứ hai (F-20): ``contracts.thi_hanh_hop_dong_tick`` hủy hợp đồng khi một bên chết
(``trang_thai="huy"`` + ``dot_vi_the``) **KHÔNG settlement** ⇒ nợ chết theo con nợ, chủ nợ mất
trắng. Module này trả nợ TỪ di sản TRƯỚC khi heir nhận.

Bệnh thứ ba (F-36): route di sản hết hạn về ``CONG_QUY`` chỉ là **SINK ĐỔI TÊN** trong
scenario đích (``chinh_tri.bat: false``). ``household.kiem_tra_cau_hinh`` chặn nó fail-closed.

Vòng đời: mở ở tick người chết (bậc 0), chạy TRỌN VẸN bậc 1–3 trong CHÍNH tick đó (nguyên tử —
không có tick nào "tạm lệch rồi cân sau"), giữ trạng thái ``"mo"`` chỉ khi bậc 3 không tìm được
ai nhận; hết ``claim_han_tick`` ⇒ bậc 4 ⇒ đóng.

**Đất KHÔNG vào estate**: ``audit.py`` cấm thửa có chủ không hoạt động. Đất đi thẳng từ người
chết sang heir NGAY trong tick chết, hoặc về công (``p.chu = None``) khi thật sự không có heir.
Không có cơ chế "cấp lại đất" — đó sẽ là một định chế cấp đất mới.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.household import _ho_bat
from engine.ledger import EPSILON

TIEN_TO = "DI_SAN:"
# Tài sản nguyên chiếc — chia round-robin, không cắt lẻ (khuôn demography.TAI_SAN_ROI)
TAI_SAN_ROI = ("nha", "cong_cu", "may")


@dataclass
class DiSan:
    id: str  # "DI_SAN:A0051" — cũng là chủ thể ledger
    nguoi_mat: str
    lang: int
    ho_id: str | None  # hộ cư trú lúc chết (bậc 3: "sống chung thì thừa kế")
    mo_tick: int
    han_tick: int
    trang_thai: str = "mo"  # "mo" | "dong"
    yeu_cau: list[tuple[str, str]] = field(default_factory=list)  # (claimant, ly_do) SORTED


# ---------------------------------------------------------------- cổng scenario


def _di_san_bat(x: Any) -> bool:
    cfg = getattr(x, "cfg", x)
    return _ho_bat(x) and bool(cfg.get("ho.di_san.bat", False))


def _che_do(w: Any) -> str:
    return str(w.cfg.get("ho.di_san.che_do", "kin"))


def _het_han(w: Any) -> str:
    return str(w.cfg.get("ho.di_san.het_han", "chia_deu_lang"))


# ---------------------------------------------------------------- E1′ terminal subjects


def bang_drain(w: Any) -> dict[str, set[str] | None]:
    """BẢNG TƯỜNG MINH terminal-subject → tập tài sản có DRAIN ĐANG BẬT (``None`` = mọi tài sản).

    INVARIANT E1′ (ADR 0007 §D.6): mọi terminal subject S và mọi tài sản ``ts``: **hoặc**
    ``so_du(S, ts) == 0``, **hoặc** S có một drain ĐÃ KHAI BÁO (hàm có tên + cờ scenario đang
    BẬT) rút được ĐÚNG loại tài sản đó về tay chủ thể hoạt động.

    Thêm một chủ thể ledger mới mà quên khai báo drain ⇒ ``kiem_e1_prime`` FAIL (T-16). Đó
    chính là cái bẫy "đổi tên sink" (F-36) mà E1 gốc (``so_du(VO_THUA_NHAN)==0``) không bắt được.
    """
    drains: dict[str, set[str] | None] = {
        # KHÔNG có drain nào. Không policy nào lấy được của cải ra khỏi đây.
        "VO_THUA_NHAN": set(),
    }
    # CONG_QUY: drain = politics.thu_thue_va_chia/_chia_deu (rebate đầu người) —
    # CHỈ chạy khi chinh_tri.bat, và CHỈ rút "thoc". politics.thi_hanh_chi_cong thêm go/cong
    # khi fiscal.bat. Mọi tài sản khác vào CONG_QUY là kẹt.
    cq: set[str] = set()
    if bool(w.cfg.get("chinh_tri.bat", True)):
        cq.add("thoc")
        if bool(w.cfg.get("fiscal.bat", False)):
            cq |= {"go", "cong"}
    drains["CONG_QUY"] = cq

    # Ký quỹ báo giá (`KY_QUY:*`) và ký quỹ vật liệu dự án (`DU_AN:*`) KHÔNG phải sink: chúng
    # CÓ drain thật — settlement giao hàng cho bên mua, còn expiry/cancel trả lại bên bán (xem
    # `quotes._settle_fill`, `quotes._release_unallocated`, `projects` hoàn/huỷ). Trước đây
    # chúng chỉ chưa được KHAI BÁO, nên E1′ đúng khi chặn: một chủ thể giữ của cải phải nói
    # được của cải thoát ra bằng đường nào.
    #
    # CHỈ khai cho thread/dự án CÒN MỞ. Một báo giá đã `hoan_thanh`/`het_han`/`da_huy` mà vẫn
    # còn số dư là bug thật (escrow không được giải phóng) và E1′ PHẢI bắt — nên không khai.
    if bool(w.cfg.get("thuong_mai.bao_gia.bat", False)):
        from engine.quotes import ESCROW_PREFIX as _BG

        for qid, q in getattr(w, "bao_gia", {}).items():
            if q.trang_thai in {"hoan_thanh", "het_han", "da_huy"}:
                continue
            drains[f"{_BG}{qid}"] = None  # settlement/expiry rút được MỌI tài sản đã ký quỹ
            for fill in q.fills:
                if fill.status == "pending":
                    drains[fill.counterparty_holder] = None
    if bool(w.cfg.get("du_an.bat", False)):
        from engine.projects import ESCROW_PREFIX as _DA

        for pid, du_an in getattr(w, "du_an", {}).items():
            if du_an.trang_thai == "dang_lam":
                drains[f"{_DA}{pid}"] = None  # hoàn thành tiêu vật liệu / huỷ hoàn lại
    return drains


def kiem_e1_prime(w: Any) -> list[str]:
    """Liệt kê vi phạm E1′ (dùng trong nhánh gated của ``audit.kiem_toan_the_gioi``)."""
    if not _di_san_bat(w):
        return []
    drains = bang_drain(w)
    loi: list[str] = []
    for (ct, ts), v in sorted(w.ledger._so_du.items()):
        if v <= EPSILON or ts == "cong":
            continue
        if w.chu_the_hoat_dong(ct):
            continue
        if ct.startswith(TIEN_TO):
            ds = w.di_san.get(ct)
            if ds is None or ds.trang_thai != "mo":
                loi.append(f"E1′: estate ĐÃ ĐÓNG/không tồn tại {ct} còn {ts}={v}")
            elif w.tick > ds.han_tick:
                loi.append(f"E1′: {ct} quá hạn (han={ds.han_tick}) mà còn {ts}={v}")
            continue  # estate đang mở, còn hạn: drain = buoc_di_san (mọi tài sản)
        phu = drains.get(ct)
        if phu is None and ct in drains:
            continue  # drain phủ mọi tài sản
        if phu is None:
            loi.append(f"E1′: chủ thể ledger KHÔNG khai báo drain: {ct} giữ {ts}={v}")
        elif ts not in phu:
            loi.append(f"E1′: {ct} giữ {ts}={v} — không có drain đang bật phủ '{ts}'")
    return loi


# ---------------------------------------------------------------- bậc 0: mở di sản


def mo_di_san(w: Any, aid: str) -> None:
    """Bậc 0 — gọi NGAY trong bước 9 (thay ``demography.thua_ke_mac_dinh`` khi gate ON).

    Toàn bộ tài sản của người chết (TRỪ ``"cong"`` — công bốc hơi cuối tick) chuyển sang chủ
    thể ``DI_SAN:<aid>``, KỂ CẢ ``vi_the:*`` và ``co_phan:*`` ⇒ người chết có số dư 0 ngay
    trong tick chết. **Đất KHÔNG vào estate** (audit cấm chủ không hoạt động) — xử ở bậc 3/4.
    """
    from engine.household import rid_cua

    a = w.agents[aid]
    han = int(w.cfg.get("ho.di_san.claim_han_tick", 3))
    ds_id = f"{TIEN_TO}{aid}"
    w._next_di_san += 1
    ds = DiSan(
        id=ds_id, nguoi_mat=aid, lang=int(a.lang), ho_id=rid_cua(w, aid),
        mo_tick=w.tick, han_tick=w.tick + max(0, han),
    )
    w.di_san[ds_id] = ds
    tai_san = w.ledger.tai_san_cua(aid)
    for ts, sl in sorted(tai_san.items()):
        if ts == "cong":
            continue
        w.ledger.chuyen(aid, ds_id, ts, sl, f"mở di sản {aid}", w.tick)
    w.events.ghi(w.tick, "mo_di_san", id=ds_id, nguoi_mat=aid, han_tick=ds.han_tick,
                 tai_san={k: round(v, 3) for k, v in sorted(tai_san.items()) if k != "cong"})
    # goá bụa — GIỮ nguyên semantics legacy (demography.thua_ke_mac_dinh): xóa vo_chong của
    # người CÒN SỐNG; người chết vẫn trỏ về bạn đời để bậc 3 đọc được thứ tự thừa kế.
    if a.vo_chong and a.vo_chong in w.agents:
        w.agents[a.vo_chong].vo_chong = None


# ---------------------------------------------------------------- bước 9c


def buoc_di_san(w: Any) -> None:
    """Bậc 1→5 cho mọi estate đang mở. Tất định: ``sorted(w.di_san)``."""
    if not _di_san_bat(w):
        return
    from engine.contracts import xay_vi_the_chu

    for ds_id in sorted(w.di_san):
        ds = w.di_san[ds_id]
        if ds.trang_thai != "mo":
            continue
        if ds.mo_tick == w.tick:
            xay_vi_the_chu(w)  # vị thế đã nằm ở DI_SAN sau bậc 0 → resolve đúng chủ hiện tại
            _bac1_chu_no(w, ds)
            _bac2_3_thua_ke(w, ds)
        elif ds.yeu_cau and _con_so_du(w, ds_id):
            # Claim window: bậc 3 không tìm được ai lúc chết ⇒ estate ở "mo" để người có tư
            # cách `yeu_cau_di_san`. Đòi hợp lệ, còn hạn ⇒ chia đều cho người đòi.
            doi = sorted({c for c, _ly in ds.yeu_cau if w.chu_the_hoat_dong(c)})
            if doi:
                _chia_cho(w, ds, doi, None, "thua_ke")
                _chia_dat(w, ds, doi)
        if w.tick >= ds.han_tick and _con_so_du(w, ds_id):
            _bac4_het_han(w, ds)
        if not _con_so_du(w, ds_id):
            _dong(w, ds)
        elif w.tick >= ds.han_tick:
            # Bậc 4 đã chạy mà vẫn còn số dư ⇒ có một loại tài sản KHÔNG có đích ⇒ bug thật,
            # không được im lặng để nó thành absorbing sink mới (điều luật #1).
            con = w.ledger.tai_san_cua(ds_id)
            raise ValueError(
                f"[tick {w.tick}] {ds_id} hết hạn mà còn số dư sau bậc 4: {con} — "
                "vi phạm E1′/E2 (tài sản không có đích hợp pháp)"
            )


def _con_so_du(w: Any, ds_id: str) -> bool:
    return any(v > EPSILON for v in w.ledger.tai_san_cua(ds_id).values())


def _dong(w: Any, ds: DiSan) -> None:
    ds.trang_thai = "dong"
    w.di_san_xong[ds.id] = ds
    del w.di_san[ds.id]
    w.events.ghi(w.tick, "dong_di_san", id=ds.id, nguoi_mat=ds.nguoi_mat, tick_dong=w.tick)


# ---------------------------------------------------------------- bậc 1: chủ nợ / hợp đồng


def _hop_dong_cua(w: Any, ds_id: str) -> list[Any]:
    from engine.contracts import ben_hien_tai

    return [
        hd for hd in sorted(w.hop_dong.values(), key=lambda h: h.id)
        if hd.trang_thai in ("hieu_luc", "vi_pham")
        and ds_id in [ben_hien_tai(w, hd.id, b) for b in hd.cac_ben]
    ]


def _bac1_chu_no(w: Any, ds: DiSan) -> None:
    """Chủ nợ / hợp đồng — TÁI DÙNG khuôn ``entities.thanh_ly``, không phát minh đại số nợ mới.

    Thiếu ⇒ chủ nợ nhận pro-rata, phần thiếu **mất THẬT** (event ``khong_thu_du``): không mint
    bù, không số dư âm, KHÔNG cho nợ "sống tiếp" sang heir (nợ truyền đời là định chế mới —
    cần ADR riêng, ngoài P1).
    """
    from engine.contracts import (
        ben_hien_tai,
        dot_vi_the,
        gia_tri_thi_truong,
        xay_vi_the_chu,
        xiet_the_chap,
    )
    from engine.entities import _mot_lan_chua_tra

    chu_no: dict[str, float] = {}
    hds = _hop_dong_cua(w, ds.id)
    for hd in hds:
        for ck in hd.dieu_khoan:
            tu = getattr(ck, "tu", None)
            den = getattr(ck, "den", None)
            if not (tu and den and ben_hien_tai(w, hd.id, tu) == ds.id):
                continue
            den_r = ben_hien_tai(w, hd.id, den)
            if not w.chu_the_hoat_dong(den_r):
                continue
            if ck.loai == "chuyen_giao_mot_lan" and _mot_lan_chua_tra(w, hd, ck):
                chu_no[den_r] = chu_no.get(den_r, 0.0) + gia_tri_thi_truong(
                    w, ck.tai_san, ck.so_luong)
            elif ck.loai == "hoan_tra_theo_yeu_cau":
                chu_no[den_r] = chu_no.get(den_r, 0.0) + gia_tri_thi_truong(
                    w, ck.tai_san, ck.tran_rut_moi_tick)
            elif ck.loai == "chuyen_giao_dinh_ky" and hd.thoi_han is None:
                # Annuity vô hạn: KHÔNG có nghĩa vụ tồn đọng xác định. Định giá nó cần một
                # discount rate — tham số KHÔNG có provenance ⇒ ta không bịa. Dòng thu chấm dứt.
                w.events.ghi(w.tick, "nghia_vu_cham_dut", hd=hd.id, di_san=ds.id,
                             loai="dinh_ky_khong_thoi_han", chu_no=den_r)

    # thế chấp: xiết TRƯỚC pro-rata ⇒ chủ nợ có bảo đảm được ưu tiên ĐÚNG như khi con nợ còn
    # sống. Không tạo thứ tự ưu tiên mới.
    for hd in hds:
        if not hd.the_chap:
            continue
        no_hd = sum(
            gia_tri_thi_truong(w, c.tai_san, c.so_luong)
            for c in hd.dieu_khoan
            if c.loai in ("chuyen_giao_mot_lan", "chuyen_giao_dinh_ky")
            and getattr(c, "tu", None) and ben_hien_tai(w, hd.id, c.tu) == ds.id
        )
        nan_nhan = [
            ben_hien_tai(w, hd.id, b) for b in hd.cac_ben
        ]
        nguoi_doi = next(
            (n for n in nan_nhan if n != ds.id and w.chu_the_hoat_dong(n)), None)
        if nguoi_doi and no_hd > 1e-9:
            truoc = _gia_tri_quy_thoc(w, nguoi_doi)
            xiet_the_chap(w, hd, nguoi_doi, ds.id, no_hd, chu_dat=ds.nguoi_mat)
            thu = max(0.0, _gia_tri_quy_thoc(w, nguoi_doi) - truoc)
            if nguoi_doi in chu_no:
                chu_no[nguoi_doi] = max(0.0, chu_no[nguoi_doi] - thu)

    tong_no = sum(chu_no.values())
    if tong_no > 1e-9:
        tai_san = {
            ts: sl for ts, sl in w.ledger.tai_san_cua(ds.id).items()
            if ts != "cong" and not ts.startswith("vi_the:")
        }
        # Mẫu số = max(tổng nghĩa vụ, giá trị estate). `entities.thanh_ly` dùng `tong_no` làm
        # mẫu số VÔ ĐIỀU KIỆN ⇒ một chủ nợ duy nhất nuốt 100% tài sản dù nợ nhỏ hơn nhiều
        # (over-payment). Ở đây KHÔNG lặp lại lỗi đó (ADR §D.3 E2: "đúng một đích", T-21:
        # "nợ X, tài sản X+Y ⇒ chủ nợ nhận X, heir nhận Y"):
        #   • tài sản ≤ nợ  ⇒ mẫu = tong_no      ⇒ chủ nợ nhận TOÀN BỘ pro-rata, thiếu là thiếu THẬT
        #   • tài sản >  nợ ⇒ mẫu = giá trị estate ⇒ chủ nợ i nhận đúng giá trị `no_i`, dư về heir
        gia_tri = sum(_quy_thoc(w, ts, sl) for ts, sl in tai_san.items())
        mau = max(tong_no, gia_tri)
        tra: dict[str, float] = dict.fromkeys(chu_no, 0.0)
        for ts, sl in sorted(tai_san.items()):
            for nid in sorted(chu_no):
                phan = sl * (chu_no[nid] / mau)
                if phan > 1e-9:
                    w.ledger.chuyen(ds.id, nid, ts, phan, f"thanh toán di sản {ds.id}", w.tick)
                    tra[nid] += _quy_thoc(w, ts, phan)
        for nid in sorted(chu_no):
            w.events.ghi(w.tick, "thanh_toan_di_san", di_san=ds.id, chu_no=nid,
                         nghia_vu=round(chu_no[nid], 3), da_tra=round(tra[nid], 3))
            thieu = chu_no[nid] - tra[nid]
            if thieu > 1e-6:
                w.events.ghi(w.tick, "khong_thu_du", di_san=ds.id, chu_no=nid,
                             thieu=round(thieu, 3))

    xay_vi_the_chu(w)  # refresh sau xiết/pro-rata trước khi đốt token vị thế
    for hd in hds:
        hd.trang_thai = "huy" if hd.trang_thai == "hieu_luc" else hd.trang_thai
        dot_vi_the(w, hd)
        w.events.ghi(w.tick, "huy_hd", hd=hd.id, ly_do="di_san")


def _quy_thoc(w: Any, ts: str, sl: float) -> float:
    from engine.contracts import gia_tri_thi_truong

    return gia_tri_thi_truong(w, ts, sl)


def _gia_tri_quy_thoc(w: Any, cid: str) -> float:
    from engine.entities import tai_san_quy_thoc

    return tai_san_quy_thoc(w, cid)


# ---------------------------------------------------------------- bậc 2+3: di chúc → kin


def _nguoi_nhan(w: Any, ds: DiSan) -> tuple[list[str], dict[str, float] | None]:
    """Di chúc → con → vợ/chồng → **(MỚI) người đồng cư trú lúc chết**.

    Bậc đồng-cư-trú là chỗ residence "trả tiền" cho chính nó: sống chung thì thừa kế. Nó chỉ
    tồn tại khi ``ho.cu_tru_ben_vung`` bật (không có residence thì không có bậc này).
    """
    a = w.agents[ds.nguoi_mat]
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
        gia_huan = str(a.di_chuc.get("gia_huan", ""))[:400]
        if gia_huan:
            for nid in hop_le:
                w.agents[nid].gia_huan = gia_huan
        w.events.ghi(w.tick, "di_chuc", nguoi_mat=ds.nguoi_mat,
                     phan_bo=a.di_chuc.get("phan_bo"))
    con_song = [c for c in a.con if c in w.agents and w.agents[c].con_song]
    if ty_trong:
        nguoi_nhan = list(ty_trong)
    elif con_song:
        nguoi_nhan = sorted(con_song)
    elif a.vo_chong and a.vo_chong in w.agents and w.agents[a.vo_chong].con_song:
        nguoi_nhan = [a.vo_chong]
    else:
        nguoi_nhan = _dong_cu_tru(w, ds)
    nguoi_nhan = [n for n in nguoi_nhan if w.chu_the_hoat_dong(n)]
    if ty_trong is not None:
        ty_trong = {n: ty_trong[n] for n in nguoi_nhan}
        tong_tt = sum(ty_trong.values())
        ty_trong = {n: v / tong_tt for n, v in ty_trong.items()} if tong_tt > 0 else None
    return nguoi_nhan, ty_trong


def _dong_cu_tru(w: Any, ds: DiSan) -> list[str]:
    if ds.ho_id is None or ds.ho_id not in getattr(w, "cu_tru", {}):
        return []
    return sorted(
        m for m in w.cu_tru[ds.ho_id].thanh_vien
        if m != ds.nguoi_mat and m in w.agents and w.agents[m].con_song
    )


def _bac2_3_thua_ke(w: Any, ds: DiSan) -> None:
    if _che_do(w) == "tan_ra":
        # null-treatment: không truyền thừa; bậc 4 phân hủy tài sản động. ĐẤT vẫn phải rời
        # tay người chết NGAY tick này (audit cấm chủ thửa không hoạt động) ⇒ về công.
        _chia_dat(w, ds, [])
        return
    nguoi_nhan, ty_trong = _nguoi_nhan(w, ds)
    _chia_cho(w, ds, nguoi_nhan, ty_trong, "thua_ke")
    _chia_dat(w, ds, nguoi_nhan)
    if nguoi_nhan:
        for nid in nguoi_nhan:
            w.ghi_ky_uc(nid, f"tôi nhận thừa kế từ {w.agents[ds.nguoi_mat].ten} "
                             f"({ds.nguoi_mat})", doi=True)


def _chia_cho(w: Any, ds: DiSan, nguoi_nhan: list[str],
              ty_trong: dict[str, float] | None, ly_do: str) -> None:
    """Chuyển tài sản còn lại của estate cho ``nguoi_nhan`` (giữ semantics legacy từng loại)."""
    if not nguoi_nhan:
        return
    da_chuyen = False
    for ts, sl in sorted(w.ledger.tai_san_cua(ds.id).items()):
        if ts == "cong" or sl <= EPSILON:
            continue
        if ts.startswith("vi_the:"):
            continue  # vị thế đã bị đốt ở bậc 1; còn sót thì bậc 4 xử
        da_chuyen = True
        if ts in TAI_SAN_ROI:
            nguyen = int(sl)
            for i in range(nguyen):
                w.ledger.chuyen(ds.id, nguoi_nhan[i % len(nguoi_nhan)], ts, 1.0,
                                f"{ly_do} {ts}", w.tick)
            du = sl - nguyen
            if du > 1e-9:
                w.ledger.chuyen(ds.id, nguoi_nhan[0], ts, du, f"{ly_do} {ts} lẻ", w.tick)
        else:
            con = sl
            for i, nid in enumerate(nguoi_nhan):
                phan = (con if i == len(nguoi_nhan) - 1
                        else sl * (ty_trong[nid] if ty_trong else 1.0 / len(nguoi_nhan)))
                phan = min(phan, con)
                if phan > 1e-12:
                    w.ledger.chuyen(ds.id, nid, ts, phan, f"{ly_do} {ts}", w.tick)
                    con -= phan
    if da_chuyen:
        # Chỉ ghi khi THẬT SỰ có gì chuyển: chủ nợ nuốt hết estate ⇒ heir nhận 0 ⇒ KHÔNG có
        # event `thua_ke` giả để về sau ai đó đếm nhầm "đã có thừa kế".
        w.events.ghi(w.tick, ly_do, nguoi_mat=ds.nguoi_mat, di_san=ds.id,
                     nguoi_nhan=list(nguoi_nhan))


def _chia_dat(w: Any, ds: DiSan, nguoi_nhan: list[str]) -> None:
    """Đất: round-robin cho người nhận; KHÔNG ai → về công NGAY trong tick chết.

    Đất không bao giờ đứng tên estate (``audit`` cấm chủ không hoạt động) và KHÔNG có cơ chế
    "cấp lại đất" cho claim muộn — lấy lại đất công đã có đường hợp lệ sẵn (khai hoang / mua).
    """
    thua_cua = sorted(p.id for p in w.parcels.values() if p.chu == ds.nguoi_mat)
    if not thua_cua:
        return
    ve_cong: list[str] = []
    for i, pid in enumerate(thua_cua):
        p = w.parcels[pid]
        if nguoi_nhan:
            p.chu = nguoi_nhan[i % len(nguoi_nhan)]
        else:
            p.chu = None
            p.homestead_ai, p.homestead_dem = None, 0
            ve_cong.append(pid)
    w.events.ghi(w.tick, "thua_ke_dat", nguoi_mat=ds.nguoi_mat, di_san=ds.id,
                 nguoi_nhan=list(nguoi_nhan) or ["cong"], so_thua=len(thua_cua),
                 ve_cong=ve_cong)


# ---------------------------------------------------------------- bậc 4: hết hạn


def _bac4_het_han(w: Any, ds: DiSan) -> None:
    """Hết hạn mà không ai nhận. ``cong`` đã bị chặn ở config-validation (§D.6)."""
    che_do = _het_han(w) if _che_do(w) != "tan_ra" else "tan_ra"
    if che_do == "tan_ra":
        _tan_ra(w, ds)
        return
    nguoi_nhan = _nguoi_lon_lang(w, ds.lang) or _nguoi_lon_lang(w, None)
    if not nguoi_nhan:
        _tan_ra(w, ds)  # không còn ai sống để chia — bảo toàn qua sink đã đăng ký
        return
    _chia_deu_lang(w, ds, nguoi_nhan)


def _nguoi_lon_lang(w: Any, lang: int | None) -> list[str]:
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    return sorted(
        a.id for a in w.agents.values()
        if a.con_song and a.truong_thanh(tt) and (lang is None or a.lang == lang)
    )


def _chia_deu_lang(w: Any, ds: DiSan, nguoi_nhan: list[str]) -> None:
    """Escheat-to-commons per-capita: người cuối nhận phần dư ⇒ số dư estate về ĐÚNG 0."""
    n = len(nguoi_nhan)
    for ts, sl in sorted(w.ledger.tai_san_cua(ds.id).items()):
        if ts == "cong" or sl <= EPSILON:
            continue
        if ts.startswith("co_phan:"):
            # cổ phần vô thừa nhận: GIỮ hành vi hiện tại — hủy qua sink "giai_the" đã đăng ký;
            # tỷ trọng cổ đông còn lại tự tăng. Có đối ứng ⇒ không phải sink lậu.
            w.ledger.huy(ds.id, ts, sl, "giai_the", f"cổ phần vô thừa nhận {ts}", w.tick)
            continue
        if ts.startswith("vi_the:"):
            w.ledger.flows.dang_ky(ts, "het_hd", "sink")
            w.ledger.huy(ds.id, ts, sl, "het_hd", f"vị thế vô thừa nhận {ts}", w.tick)
            continue
        if ts in TAI_SAN_ROI:
            nguyen = int(sl)
            for i in range(nguyen):
                w.ledger.chuyen(ds.id, nguoi_nhan[i % n], ts, 1.0,
                                f"chia đều làng {ts}", w.tick)
            du = w.ledger.so_du(ds.id, ts)
            if du > EPSILON:
                w.ledger.chuyen(ds.id, nguoi_nhan[0], ts, du,
                                f"chia đều làng {ts} lẻ", w.tick)
            continue
        phan_deu = sl / n
        for i, nid in enumerate(nguoi_nhan):
            phan = sl - phan_deu * (n - 1) if i == n - 1 else phan_deu
            if phan > EPSILON:
                w.ledger.chuyen(ds.id, nid, ts, phan, f"chia đều làng {ts}", w.tick)
        du = w.ledger.so_du(ds.id, ts)
        if du > EPSILON:
            w.ledger.chuyen(ds.id, nguoi_nhan[-1], ts, du, f"chia đều làng {ts} dư", w.tick)
    w.events.ghi(w.tick, "chia_deu_lang", di_san=ds.id, nguoi_mat=ds.nguoi_mat,
                 lang=ds.lang, so_nguoi=n)


def _tan_ra(w: Any, ds: DiSan) -> None:
    """Null-treatment: không ai nhận thì của cải MẤT — qua sink ĐĂNG KÝ, có đối ứng, audit xanh.

    Đây là baseline để đo xem chế độ truyền thừa (``kin``) có tác dụng gì. Nhà không người ở
    thì sập; đó là một mệnh đề vật lý, không phải một cách giấu tài sản."""
    for ts, sl in sorted(w.ledger.tai_san_cua(ds.id).items()):
        if ts == "cong" or sl <= EPSILON:
            continue
        w.ledger.flows.dang_ky(ts, "tan_ra", "sink")
        w.ledger.huy(ds.id, ts, sl, "tan_ra", f"tan rã di sản {ts}", w.tick)
    w.events.ghi(w.tick, "tan_ra_di_san", di_san=ds.id, nguoi_mat=ds.nguoi_mat)


# ---------------------------------------------------------------- claim (intent)


def yeu_cau_di_san(w: Any, aid: str, ds_id: str) -> None:
    """Intent ``yeu_cau_di_san``: người có tư cách xin nhận di sản đang mở (LLM chỉ trả ý định).

    Từ chối ⇒ ``ghi_unrecognized`` + bỏ qua ÊM, không raise (điều luật #3)."""
    if not _di_san_bat(w):
        w.ghi_unrecognized(aid, "yeu_cau_di_san", "tinh_nang_tat")
        return
    ds = w.di_san.get(ds_id)
    if ds is None or ds.trang_thai != "mo":
        w.ghi_unrecognized(aid, "yeu_cau_di_san", "khong_ton_tai")
        return
    if w.tick > ds.han_tick:
        w.ghi_unrecognized(aid, "yeu_cau_di_san", "het_han")
        return
    if not w.chu_the_hoat_dong(aid) or aid not in w.agents:
        w.ghi_unrecognized(aid, "yeu_cau_di_san", "khong_hoat_dong")
        return
    a = w.agents[ds.nguoi_mat]
    hop_le = (
        aid in a.con or aid == a.vo_chong or aid in _dong_cu_tru(w, ds)
        or (a.di_chuc or {}).get("phan_bo", {}).get(aid) is not None
    )
    if not hop_le:
        w.ghi_unrecognized(aid, "yeu_cau_di_san", "no_right")
        return
    if (aid, "kin") not in ds.yeu_cau:
        ds.yeu_cau = sorted([*ds.yeu_cau, (aid, "kin")])
    w.events.ghi(w.tick, "yeu_cau_di_san", di_san=ds_id, ai=aid)


__all__ = [
    "DiSan",
    "TIEN_TO",
    "_di_san_bat",
    "bang_drain",
    "buoc_di_san",
    "kiem_e1_prime",
    "mo_di_san",
    "yeu_cau_di_san",
]
