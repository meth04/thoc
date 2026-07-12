"""HỢP ĐỒNG — văn phạm 9 clause + executor + cưỡng chế (SPEC 3.2).

Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp
clause hợp lệ. Định chế là nhãn do observatory dán lên sau, từ log.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------- văn phạm


class ClauseChuyenGiaoDinhKy(BaseModel):
    loai: Literal["chuyen_giao_dinh_ky"] = "chuyen_giao_dinh_ky"
    tu: str
    den: str
    tai_san: str
    so_luong: float = Field(gt=0)
    moi_n_tick: int = Field(ge=1, default=1)


class ClauseChuyenGiaoMotLan(BaseModel):
    loai: Literal["chuyen_giao_mot_lan"] = "chuyen_giao_mot_lan"
    tu: str
    den: str
    tai_san: str
    so_luong: float = Field(gt=0)
    tai: str = "ky_ket"  # "ky_ket" | "dao_han" | "tick_T" (T = số tick sau ký)
    tick_t: int | None = None


class ClauseQuyenSuDung(BaseModel):
    loai: Literal["quyen_su_dung"] = "quyen_su_dung"
    tai_san: str  # "thua:P01_02" | "nha" | "cong_cu" | "may:M1" | "blueprint:B1"
    tu: str
    den: str


class ClauseGopCong(BaseModel):
    loai: Literal["gop_cong"] = "gop_cong"
    tu: str
    den: str
    so_cong_moi_tick: float = Field(gt=0)


class ClauseChiaSanLuong(BaseModel):
    loai: Literal["chia_san_luong"] = "chia_san_luong"
    nguon: str  # "thua:P01_02" | "hoat_dong_cua_ben:A0003"
    ty_le: float = Field(gt=0, le=1)
    den: str


class ClauseChiaLoiNhuan(BaseModel):
    loai: Literal["chia_loi_nhuan"] = "chia_loi_nhuan"
    entity: str
    theo_co_phan: bool = True
    ty_le: dict[str, float] | None = None


class ClauseDieuKienSuKien(BaseModel):
    loai: Literal["dieu_kien_su_kien"] = "dieu_kien_su_kien"
    neu: dict  # {loai: han_lu | chet | vo_no | gia, ...tham số}
    thi: ClauseChuyenGiaoDinhKy | ClauseChuyenGiaoMotLan


class ClauseHoanTraTheoYeuCau(BaseModel):
    loai: Literal["hoan_tra_theo_yeu_cau"] = "hoan_tra_theo_yeu_cau"
    tu: str
    den: str
    tai_san: str
    tran_rut_moi_tick: float = Field(gt=0)


class ClauseKhiPhaVo(BaseModel):
    loai: Literal["khi_pha_vo"] = "khi_pha_vo"
    phat: str = "khong"  # "xiet_the_chap" | "khong" | "phat_chuyen_giao"
    phat_chuyen_giao: ClauseChuyenGiaoMotLan | None = None


Clause = Annotated[
    ClauseChuyenGiaoDinhKy | ClauseChuyenGiaoMotLan | ClauseQuyenSuDung | ClauseGopCong | ClauseChiaSanLuong | ClauseChiaLoiNhuan | ClauseDieuKienSuKien | ClauseHoanTraTheoYeuCau | ClauseKhiPhaVo,
    Field(discriminator="loai"),
]


class HopDong(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = ""
    cac_ben: list[str] = Field(min_length=2)
    hinh_thuc: Literal["mieng", "van_ban"] = "mieng"
    thoi_han: int | None = None  # K tick; None = đến khi hủy
    bao_truoc: int = 1  # số tick báo trước khi hủy (hợp đồng vô hạn)
    the_chap: list[str] = Field(default_factory=list)  # ["thoc:200", "thua:P01_02", "nha:1"]
    dieu_khoan: list[Clause] = Field(min_length=1)
    # trạng thái runtime (engine quản lý)
    trang_thai: str = "hieu_luc"  # hieu_luc | hoan_thanh | vi_pham | huy
    tick_ky: int = -1
    nguoi_soan: str = ""
    huy_bao_truoc_tu: int | None = None  # tick bắt đầu báo hủy
    ke_vi_pham: str = ""  # ai phá vỡ (engine ghi khi cưỡng chế)


# ---------------------------------------------------------------- validate


def validate_hop_dong(hd: HopDong, w) -> str | None:
    """Trả None nếu hợp lệ, ngược lại là lý do từ chối (engine bỏ qua + log)."""
    ben = set(hd.cac_ben)
    if len(ben) < 2:
        return "cần ≥2 bên"
    for b in ben:
        if b == "?":
            continue  # placeholder đề nghị công khai — validate đầy đủ khi ký
        if b not in w.agents and b not in getattr(w, "entities", {}):
            return f"bên không tồn tại: {b}"
        if b in w.agents and not w.agents[b].con_song:
            return f"bên đã chết: {b}"
        if b not in w.agents and not w.entities[b].con_hoat_dong:
            return f"entity đã giải thể: {b}"
    if hd.hinh_thuc == "van_ban":
        can_e = int(w.cfg.get("hop_dong.van_ban_can_E_nguoi_soan"))
        soan = hd.nguoi_soan or hd.cac_ben[0]
        if soan in w.agents and w.agents[soan].e_bac < can_e:
            return f"người soạn {soan} chưa biết chữ (E<{can_e})"
    if hd.the_chap and hd.hinh_thuc != "van_ban":
        return "thế chấp chỉ hiệu lực với văn bản"
    if hd.thoi_han is not None and hd.thoi_han < 1:
        return f"thời hạn không hợp lệ: {hd.thoi_han}"
    for ck in hd.dieu_khoan:
        for vai in ("tu", "den"):
            v = getattr(ck, vai, None)
            if v is not None and v not in ben:
                return f"clause nhắc tới {v} không phải một bên"
        if ck.loai == "quyen_su_dung" and ck.tai_san.startswith("thua:"):
            pid = ck.tai_san.split(":", 1)[1]
            p = w.parcels.get(pid)
            if p is None:
                return f"thửa không tồn tại: {pid}"
            if ck.tu != "?" and p.chu != ck.tu:
                return f"{ck.tu} không sở hữu {pid}"
        if ck.loai == "quyen_su_dung" and ck.tai_san.startswith("blueprint:"):
            bid = ck.tai_san.split(":", 1)[1]
            bp = getattr(w, "blueprints", {}).get(bid)
            if bp is None:
                return f"blueprint không tồn tại: {bid}"
            if ck.tu != "?" and bp.chu != ck.tu:
                return f"{ck.tu} không sở hữu {bid}"
        if ck.loai == "chia_loi_nhuan" and ck.entity not in getattr(w, "entities", {}):
            return f"entity không tồn tại: {ck.entity}"
        if ck.loai == "chia_san_luong" and not ck.nguon.startswith("thua:"):
            # executor chỉ thi hành được nguồn "thua:" — từ chối ngay thay vì hứa câm
            return f"chia_san_luong nguồn chưa hỗ trợ: {ck.nguon}"
        if ck.loai == "chuyen_giao_mot_lan" and ck.tai == "dao_han" and hd.thoi_han is None:
            return "chuyển giao tại đáo hạn nhưng hợp đồng vô thời hạn"
    for tc in hd.the_chap:
        if ":" not in tc:
            return f"thế chấp sai định dạng: {tc}"
        loai_tc, gia_tri = tc.split(":", 1)
        if loai_tc == "thua":
            p = w.parcels.get(gia_tri)
            if p is None or p.chu not in ben:
                return f"thế chấp thửa không hợp lệ: {tc}"
    return None


# ---------------------------------------------------------------- executor


def _chuyen_an_toan(w, tu: str, den: str, tai_san: str, so_luong: float, ly_do: str,
                    hd_id: str | None = None) -> bool:
    """Chuyển nếu đủ; trả False nếu thiếu (→ vi phạm). hd_id → ghi event dựng lại đồ thị."""
    from engine.ledger import LoiSoKep

    if so_luong <= 0:
        return True
    try:
        w.ledger.chuyen(tu, den, tai_san, so_luong, ly_do, w.tick)
        w.kl_hd_tick = getattr(w, "kl_hd_tick", 0.0) + gia_tri_thi_truong(w, tai_san, so_luong)
        if hd_id is not None:
            w.events.ghi(w.tick, "hd_chuyen_giao", hd=hd_id, tu=tu, den=den,
                         tai_san=tai_san, sl=round(so_luong, 3))
        return True
    except LoiSoKep:
        return False


def _su_kien_xay_ra(w, neu: dict, vo_no_tick: set[str], chet_tick: set[str]) -> bool:
    loai = neu.get("loai")
    if loai == "han_lu":
        return w.thoi_tiet(w.tick)[0] == "han_lu"
    if loai == "chet":
        return neu.get("ai") in chet_tick
    if loai == "vo_no":
        return neu.get("ai") in vo_no_tick
    if loai == "gia":
        gia = w.gia_gan_nhat(neu.get("tai_san", "thoc"))
        if gia is None:
            return False
        nguong = float(neu.get("nguong", 0))
        return gia > nguong if neu.get("chieu", ">") == ">" else gia < nguong
    return False


def gia_tri_thi_truong(w, tai_san: str, so_luong: float) -> float:
    """Quy giá về kg thóc theo giá chợ gần nhất; không có giá → giá trị 0 khi xiết."""
    if tai_san == "thoc":
        return so_luong
    gia = w.gia_gan_nhat(tai_san)
    return so_luong * gia if gia is not None else 0.0


def xiet_the_chap(w, hd: HopDong, chu_no: str, con_no: str, no_con_lai_thoc: float) -> None:
    """Xiết thế chấp theo giá chợ gần nhất; thừa hoàn lại (SPEC 3.2)."""
    for tc in hd.the_chap:
        if no_con_lai_thoc <= 1e-9:
            break
        loai_tc, gia_tri = tc.split(":", 1)
        if loai_tc == "thua":
            p = w.parcels.get(gia_tri)
            if p is None or p.chu != con_no:
                continue
            gia_dat = w.gia_gan_nhat(f"dat:{gia_tri}") or w.gia_gan_nhat("dat") or 0.0
            p.chu = chu_no
            w.events.ghi(w.tick, "xiet", hd=hd.id, mon=tc, gia_quy_thoc=gia_dat)
            # đất không chia nhỏ được — phần giá trị vượt nợ phải HOÀN LẠI bằng thóc
            if gia_dat > no_con_lai_thoc:
                thua_ra = gia_dat - no_con_lai_thoc
                hoan = min(thua_ra, w.ledger.so_du(chu_no, "thoc"))
                if hoan > 0:
                    _chuyen_an_toan(w, chu_no, con_no, "thoc", hoan, f"hoàn thừa xiết {hd.id}")
            no_con_lai_thoc -= gia_dat
        else:
            so_luong = min(float(gia_tri), w.ledger.so_du(con_no, loai_tc))
            if so_luong <= 0:
                continue
            gia_mot = 1.0 if loai_tc == "thoc" else (w.gia_gan_nhat(loai_tc) or 0.0)
            gia_tri_xiet = so_luong * gia_mot
            if gia_mot > 0 and gia_tri_xiet > no_con_lai_thoc:
                so_luong = no_con_lai_thoc / gia_mot  # thừa hoàn lại — chỉ xiết đủ nợ
                gia_tri_xiet = no_con_lai_thoc
            _chuyen_an_toan(w, con_no, chu_no, loai_tc, so_luong, f"xiết thế chấp {hd.id}")
            w.events.ghi(w.tick, "xiet", hd=hd.id, mon=f"{loai_tc}:{round(so_luong, 2)}",
                         gia_quy_thoc=gia_tri_xiet)
            no_con_lai_thoc -= gia_tri_xiet


def phat_vi_pham(w, hd: HopDong, ke_vi_pham: str) -> None:
    """Cưỡng chế: miệng → trừ uy tín + tin đồn; văn bản → thi hành khi_pha_vo."""
    hd.trang_thai = "vi_pham"
    hd.ke_vi_pham = ke_vi_pham
    nan_nhan = [ben_hien_tai(w, hd.id, b) for b in hd.cac_ben]
    nan_nhan = [b for b in nan_nhan if b != ke_vi_pham]
    w.events.ghi(w.tick, "vi_pham", hd=hd.id, ai=ke_vi_pham, hinh_thuc=hd.hinh_thuc)
    w.ghi_ky_uc(ke_vi_pham, f"tôi THẤT HỨA giao kèo {hd.id} — mất mặt với làng")
    for nn in nan_nhan:
        w.ghi_ky_uc(nn, f"{ke_vi_pham} thất hứa giao kèo {hd.id} với tôi")
    phat_mieng = float(w.cfg.get("hop_dong.uy_tin.phat_vi_pham_mieng"))
    for nn in nan_nhan:
        w.cong_quan_he(ke_vi_pham, nn, phat_mieng)
    # tin đồn lan theo đồ thị (1 bước): người quen CÒN SỐNG của nạn nhân dè chừng
    he_so_lan = float(w.cfg.get("hop_dong.uy_tin.he_so_lan_tin_don"))
    for (a, b), trong_so in list(w.quan_he.items()):
        if trong_so <= 0:
            continue
        for nn in nan_nhan:
            if nn in (a, b):
                nguoi_quen = b if a == nn else a
                if nguoi_quen != ke_vi_pham and w.chu_the_hoat_dong(nguoi_quen):
                    w.cong_quan_he(ke_vi_pham, nguoi_quen, phat_mieng * he_so_lan)
    if hd.hinh_thuc == "van_ban":
        khi_pha_vo = next((c for c in hd.dieu_khoan if c.loai == "khi_pha_vo"), None)
        if khi_pha_vo is None:
            return
        if khi_pha_vo.phat == "xiet_the_chap" and hd.the_chap:
            # nợ còn lại = tổng nghĩa vụ chuyển giao chưa hoàn thành quy thóc
            no = sum(
                gia_tri_thi_truong(w, c.tai_san, c.so_luong)
                for c in hd.dieu_khoan
                if c.loai in ("chuyen_giao_mot_lan", "chuyen_giao_dinh_ky")
                and getattr(c, "tu", None) == ke_vi_pham
            )
            # chỉ xiết cho bên đòi CÒN HOẠT ĐỘNG — vị thế vô thừa nhận (chủ nợ chết
            # không người kế) thì không ai nhận đất, thế chấp ở lại với con nợ
            chu_no = next((n for n in nan_nhan if w.chu_the_hoat_dong(n)), None)
            if chu_no:
                xiet_the_chap(w, hd, chu_no, ke_vi_pham, max(no, 0.0))
        elif khi_pha_vo.phat == "phat_chuyen_giao" and khi_pha_vo.phat_chuyen_giao:
            c = khi_pha_vo.phat_chuyen_giao
            # bên thực tế = chủ vị thế hiện tại (vị thế chuyển nhượng được)
            _chuyen_an_toan(w, ben_hien_tai(w, hd.id, c.tu), ben_hien_tai(w, hd.id, c.den),
                            c.tai_san, c.so_luong, f"phạt phá vỡ {hd.id}", hd_id=hd.id)


def xay_vi_the_chu(w) -> None:
    """Vị thế hợp đồng là token 'vi_the:{hd}:{bên gốc}' trong sổ — chuyển nhượng được
    trên chợ. Bên thực tế của mọi clause = chủ token hiện tại."""
    w.vi_the_chu = {}
    for (chu_the, ts), v in w.ledger._so_du.items():
        if v > 0.5 and ts.startswith("vi_the:"):
            _, hd_id, ben_goc = ts.split(":", 2)
            w.vi_the_chu[(hd_id, ben_goc)] = chu_the


def ben_hien_tai(w, hd_id: str, ten_goc: str) -> str:
    return getattr(w, "vi_the_chu", {}).get((hd_id, ten_goc), ten_goc)


def dot_vi_the(w, hd: HopDong) -> None:
    """Hợp đồng kết thúc → token vị thế bị hủy (khỏi chủ hiện tại)."""
    for ben in hd.cac_ben:
        ts = f"vi_the:{hd.id}:{ben}"
        chu = ben_hien_tai(w, hd.id, ben)
        sl = w.ledger.so_du(chu, ts)
        if sl > 0:
            w.ledger.huy(chu, ts, sl, "het_hd", f"hết hợp đồng {hd.id}", w.tick)


def thi_hanh_hop_dong_tick(w, chet_tick: set[str] | None = None) -> None:
    """Bước 7 pipeline: chạy clause định kỳ, đáo hạn, phát hiện vi phạm, cưỡng chế."""
    chet_tick = chet_tick or set()
    vo_no_tick: set[str] = set()
    xay_vi_the_chu(w)
    for hd in sorted(w.hop_dong.values(), key=lambda h: h.id):
        if hd.trang_thai != "hieu_luc":
            continue

        def _r(ten: str, _hd=hd) -> str:
            return ben_hien_tai(w, _hd.id, ten)

        tuoi = w.tick - hd.tick_ky
        dao_han = hd.thoi_han is not None and tuoi >= hd.thoi_han
        # một bên (thực tế) chết hoặc vị thế vô thừa nhận → hợp đồng chấm dứt
        def _ben_mat(bid: str) -> bool:
            if bid in w.agents:
                return not w.agents[bid].con_song
            return bid not in getattr(w, "entities", {})  # VO_THUA_NHAN, v.v.

        ben_chet = [b for b in hd.cac_ben if _ben_mat(_r(b))]

        # phân loại thu nhập từ hợp đồng này cho người nhận (observatory dùng)
        co_gop_cong_tu = {ck2.tu for ck2 in hd.dieu_khoan if ck2.loai == "gop_cong"}
        co_qsd_tu = {ck2.tu for ck2 in hd.dieu_khoan if ck2.loai == "quyen_su_dung"}

        def _nhom_thu_nhap(nguoi_goc: str, _gop=co_gop_cong_tu, _qsd=co_qsd_tu) -> str:
            if nguoi_goc in _gop:
                return "gop_cong"  # lương đổi công
            if nguoi_goc in _qsd:
                return "dat"  # tô / cho thuê tài sản
            return "hop_dong"

        # bên (đã resolve) của một leg KHÔNG hoạt động → SKIP leg đó: không phạt,
        # không chuyển tài sản vào túi người chết/vị thế vô thừa nhận (điều luật #1)
        def _hoat_dong_ca_hai(tu_r: str, den_r: str) -> bool:
            return w.chu_the_hoat_dong(tu_r) and w.chu_the_hoat_dong(den_r)

        cong_qh = float(w.cfg.get("quan_he.cong_moi_tuong_tac"))
        vi_pham_boi: str | None = None
        for ck in hd.dieu_khoan:
            if ck.loai == "chuyen_giao_dinh_ky":
                tu_r, den_r = _r(ck.tu), _r(ck.den)
                if tuoi > 0 and tuoi % ck.moi_n_tick == 0 and _hoat_dong_ca_hai(tu_r, den_r):
                    if not _chuyen_an_toan(w, tu_r, den_r, ck.tai_san, ck.so_luong,
                                           f"định kỳ {hd.id}", hd_id=hd.id):
                        vi_pham_boi = tu_r
                    else:
                        w.ghi_thu_nhap(den_r, _nhom_thu_nhap(ck.den),
                                       gia_tri_thi_truong(w, ck.tai_san, ck.so_luong))
                        # giữ trọn giao kèo định kỳ → thành bạn hàng tin nhau dần
                        w.cong_quan_he_gioi_han(tu_r, den_r, cong_qh)
            elif ck.loai == "chuyen_giao_mot_lan":
                tu_r, den_r = _r(ck.tu), _r(ck.den)
                den_han = (
                    (ck.tai == "dao_han" and dao_han)
                    or (ck.tai == "tick_T" and ck.tick_t is not None and tuoi == ck.tick_t)
                )
                if (den_han and _hoat_dong_ca_hai(tu_r, den_r)
                        and not _chuyen_an_toan(w, tu_r, den_r, ck.tai_san,
                                                ck.so_luong, f"đáo hạn {hd.id}",
                                                hd_id=hd.id)):
                    vi_pham_boi = tu_r
            elif ck.loai == "chia_san_luong":
                if ck.nguon.startswith("thua:"):
                    pid = ck.nguon.split(":", 1)[1]
                    nguoi_gat, kg = w.gat_tick.get(pid, (None, 0.0))
                    den = _r(ck.den)
                    if (nguoi_gat and kg > 0 and nguoi_gat != den
                            and _hoat_dong_ca_hai(nguoi_gat, den)):
                        phan = kg * ck.ty_le
                        if not _chuyen_an_toan(w, nguoi_gat, den, "thoc", phan,
                                               f"chia sản {hd.id}", hd_id=hd.id):
                            vi_pham_boi = nguoi_gat
                        else:
                            w.ghi_thu_nhap(den, "dat", phan)
            elif ck.loai == "dieu_kien_su_kien":
                # GIỮ chi trả sự kiện (kể cả sự kiện "chet" của người thứ ba)
                # khi cả hai bên của leg chi trả còn hoạt động
                if _su_kien_xay_ra(w, ck.neu, vo_no_tick, chet_tick):
                    c2 = ck.thi
                    tu_r, den_r = _r(c2.tu), _r(c2.den)
                    if (_hoat_dong_ca_hai(tu_r, den_r)
                            and not _chuyen_an_toan(w, tu_r, den_r, c2.tai_san, c2.so_luong,
                                                    f"điều kiện {hd.id}", hd_id=hd.id)):
                        vi_pham_boi = tu_r
            elif ck.loai == "hoan_tra_theo_yeu_cau":
                tu_r, den = _r(ck.tu), _r(ck.den)
                yeu_cau = w.yeu_cau_rut_tick.get((hd.id, den), 0.0)
                if yeu_cau > 0 and _hoat_dong_ca_hai(tu_r, den):
                    rut = min(yeu_cau, ck.tran_rut_moi_tick)
                    if not _chuyen_an_toan(w, tu_r, den, ck.tai_san, rut,
                                           f"hoàn trả theo yêu cầu {hd.id}", hd_id=hd.id):
                        vi_pham_boi = tu_r
            # gop_cong thi hành ở bước 5 (sản xuất); quyen_su_dung là trạng thái, không luồng

        if vi_pham_boi:
            vo_no_tick.add(vi_pham_boi)
            phat_vi_pham(w, hd, vi_pham_boi)
            dot_vi_the(w, hd)
            continue
        if dao_han or ben_chet:
            hd.trang_thai = "hoan_thanh" if not ben_chet else "huy"
            w.events.ghi(w.tick, "huy_hd" if ben_chet else "hoan_thanh_hd", hd=hd.id)
            if not ben_chet:
                # đi trọn giao kèo đến đáo hạn — chữ tín được ghi nhận
                ben_r = sorted({_r(b) for b in hd.cac_ben})
                for i, b1 in enumerate(ben_r):
                    for b2 in ben_r[i + 1:]:
                        w.cong_quan_he_gioi_han(b1, b2, cong_qh)
            dot_vi_the(w, hd)
        elif hd.huy_bao_truoc_tu is not None and w.tick - hd.huy_bao_truoc_tu >= hd.bao_truoc:
            hd.trang_thai = "huy"
            w.events.ghi(w.tick, "huy_hd", hd=hd.id, ly_do="bao_truoc")
            dot_vi_the(w, hd)
    w.yeu_cau_rut_tick.clear()


def gop_cong_dau_san_xuat(w) -> None:
    """Clause gop_cong thi hành ĐẦU bước 5 để bên nhận dùng được công trong tick."""
    xay_vi_the_chu(w)
    for hd in sorted(w.hop_dong.values(), key=lambda h: h.id):
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if ck.loai != "gop_cong":
                continue
            tu, den = ben_hien_tai(w, hd.id, ck.tu), ben_hien_tai(w, hd.id, ck.den)
            # bên chết/vị thế vô thừa nhận → skip, KHÔNG dán nhãn vi_pham cho cái chết
            # (hợp đồng sẽ bị hủy ở bước 7 cùng tick)
            if not (w.chu_the_hoat_dong(tu) and w.chu_the_hoat_dong(den)):
                continue
            # đình công: bên góp công là thành viên nghiệp đoàn đình công tick này →
            # HOÃN giao công (không thực hiện clause tick này), KHÔNG tính vi phạm
            cq = getattr(w, "chinh_quyen", None)
            if cq is not None and tu in cq.dinh_cong_tick:
                continue
            if not _chuyen_an_toan(w, tu, den, "cong", ck.so_cong_moi_tick,
                                   f"góp công {hd.id}", hd_id=hd.id):
                phat_vi_pham(w, hd, tu)
                dot_vi_the(w, hd)
                break


def quyen_su_dung_thua(w, aid: str) -> set[str]:
    """Các thửa aid được canh nhờ clause quyen_su_dung đang hiệu lực."""
    ket_qua: set[str] = set()
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if (
                ck.loai == "quyen_su_dung"
                and ben_hien_tai(w, hd.id, ck.den) == aid
                and ck.tai_san.startswith("thua:")
            ):
                ket_qua.add(ck.tai_san.split(":", 1)[1])
    return ket_qua
