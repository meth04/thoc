"""OBSERVATORY — dán nhãn giai cấp + định chế + milestones + chronicle (SPEC 9).

CHỈ ĐỌC trạng thái/log. Không một nhãn nào ở đây là cơ chế engine: "ngân hàng",
"công nghiệp hóa"... chỉ là tên đặt cho cấu trúc đo được. Ngưỡng ở world.yaml.
"""

from __future__ import annotations

import numpy as np

from engine.contracts import ben_hien_tai
from engine.world import World

GIAI_CAP = [
    "phu_thuoc", "vo_gia_cu", "chu_xuong", "dia_chu", "phu_nong", "thuong_nhan",
    "tho_thu_cong", "gioi_dich_vu", "cong_nhan", "ta_dien", "co_nong", "trung_nong",
]


def _thu_nhap_4_tick(w: World, aid: str) -> dict[str, float]:
    tong: dict[str, float] = {}
    for d in w.thu_nhap_4:
        for nguon, v in d.get(aid, {}).items():
            tong[nguon] = tong.get(nguon, 0.0) + v
    return tong


def phan_loai_giai_cap(w: World) -> dict[str, str]:
    """Classifier 12 nhãn, ưu tiên trên xuống (SPEC 9.1). Không ai 'sinh ra là' gì."""
    cfg = w.cfg.raw()["giai_cap"]
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    song = {aid: a for aid, a in w.agents.items() if a.con_song}

    dat_dem: dict[str, int] = {}
    for p in w.parcels.values():
        if p.chu:
            dat_dem[p.chu] = dat_dem.get(p.chu, 0) + 1
    dat_nguoi = [dat_dem.get(aid, 0) for aid in song]
    p90 = float(np.percentile(dat_nguoi, cfg["dia_chu_percentile_dat"])) if song else 0
    p75 = float(np.percentile(dat_nguoi, cfg["phu_nong_percentile_dat"])) if song else 0

    # ai đang mua công người khác / là cổ đông chi phối entity có ≥3 hợp đồng góp công
    mua_cong: set[str] = set()
    gop_cong_vao_entity: dict[str, int] = {}
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if ck.loai == "gop_cong":
                den = ben_hien_tai(w, hd.id, ck.den)
                mua_cong.add(den)
                if den in w.entities:
                    gop_cong_vao_entity[den] = gop_cong_vao_entity.get(den, 0) + 1
    chu_xuong: set[str] = set()
    from engine.entities import co_dong_cua

    for eid, so_gop in gop_cong_vao_entity.items():
        if so_gop >= cfg["chu_xuong_gop_cong_toi_thieu"]:
            cd = co_dong_cua(w, eid)
            for cid, cp in cd.items():
                if cp > 50.0 and cid in song:
                    chu_xuong.add(cid)

    ket_qua: dict[str, str] = {}
    for aid, a in sorted(song.items()):
        tn = _thu_nhap_4_tick(w, aid)
        tong_tn = sum(v for k, v in tn.items() if not k.startswith("canh_"))
        dat = dat_dem.get(aid, 0)
        if a.tuoi_nam < tt or (a.tuoi_nam >= 70 and tong_tn <= 0):
            ket_qua[aid] = "phu_thuoc"
        elif a.vo_gia_cu:
            ket_qua[aid] = "vo_gia_cu"
        elif aid in chu_xuong:
            ket_qua[aid] = "chu_xuong"
        elif (dat >= max(p90, 1) and tong_tn > 0
              and tn.get("dat", 0) / tong_tn >= cfg["dia_chu_ty_le_thu_nhap_dat"]):
            ket_qua[aid] = "dia_chu"
        elif dat >= max(p75, 1) and aid in mua_cong:
            ket_qua[aid] = "phu_nong"
        elif tong_tn > 0 and (tn.get("ban_thoc", 0) + tn.get("ban_xu", 0)) / tong_tn >= 0.5:
            ket_qua[aid] = "thuong_nhan"
        elif tong_tn > 0 and tn.get("che_tac", 0) / tong_tn >= 0.5:
            ket_qua[aid] = "tho_thu_cong"
        elif tong_tn > 0 and tn.get("dich_vu", 0) / tong_tn >= 0.5:
            ket_qua[aid] = "gioi_dich_vu"
        elif (tong_tn > 0
              and tn.get("gop_cong", 0) / tong_tn >= cfg["cong_nhan_ty_le_thu_nhap_gop_cong"]):
            ket_qua[aid] = "cong_nhan"
        elif (tn.get("canh_thua_tong", 0) > 0
              and tn.get("canh_thue_thua", 0) / tn["canh_thua_tong"]
              >= cfg["ta_dien_ty_le_dat_thue"]):
            ket_qua[aid] = "ta_dien"
        elif dat == 0 and tn.get("gop_cong", 0) > 0:
            ket_qua[aid] = "co_nong"
        elif dat == 0 and tong_tn <= 0:
            ket_qua[aid] = "co_nong"
        else:
            ket_qua[aid] = "trung_nong"
    return ket_qua


def nhan_dinh_che(w: World) -> dict[str, list[str]]:
    """Nhãn định chế (SPEC 9.2) — một chủ thể có thể mang nhiều nhãn."""
    q = w.cfg.raw()["quan_sat"]
    nhan: dict[str, list[str]] = {}

    # ngân hàng: tổng nghĩa vụ hoàn_tra_theo_yeu_cau ≥ ngưỡng từ ≥N chủ nợ
    hoan_tra: dict[str, tuple[float, set[str]]] = {}
    bao_hiem_ban: dict[str, int] = {}
    gop_cong_den: dict[str, set[str]] = {}
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if ck.loai == "hoan_tra_theo_yeu_cau":
                tu = ben_hien_tai(w, hd.id, ck.tu)
                den = ben_hien_tai(w, hd.id, ck.den)
                tong, chu_no = hoan_tra.get(tu, (0.0, set()))
                hoan_tra[tu] = (tong + ck.tran_rut_moi_tick, chu_no | {den})
            elif ck.loai == "dieu_kien_su_kien":
                ben_tra = ben_hien_tai(w, hd.id, ck.thi.tu)
                bao_hiem_ban[ben_tra] = bao_hiem_ban.get(ben_tra, 0) + 1
            elif ck.loai == "gop_cong":
                den = ben_hien_tai(w, hd.id, ck.den)
                gop_cong_den.setdefault(den, set()).add(ben_hien_tai(w, hd.id, ck.tu))
    nh = q["ngan_hang"]
    nhan["ngan_hang"] = sorted(
        ai for ai, (tong, chu_no) in hoan_tra.items()
        if tong >= nh["nghia_vu_hoan_tra_toi_thieu_thoc"]
        and len(chu_no) >= nh["so_chu_no_toi_thieu"]
    )
    nhan["bao_hiem"] = sorted(
        ai for ai, so in bao_hiem_ban.items()
        if so >= q["bao_hiem"]["so_hop_dong_su_kien_toi_thieu"]
    )
    nhan["xuong"] = sorted(
        eid for eid, nguoi in gop_cong_den.items()
        if eid in w.entities and len(nguoi) >= q["xuong"]["so_hop_dong_gop_cong_toi_thieu"]
    )
    # thị trường cổ phần: ≥k giao dịch cổ phần/năm (đếm từ giá lịch sử)
    nam_nay = w.tick - 2
    so_gd_cp = sum(
        1 for ts, ls in w.gia_lich_su.items() if ts.startswith("co_phan:")
        for (t, _g, _kl, _tt) in ls if t > nam_nay
    )
    nhan["thi_truong_co_phan"] = (
        ["cho_lang"] if so_gd_cp >= q["thi_truong_co_phan"]["giao_dich_moi_nam_toi_thieu"]
        else []
    )
    # tiền tệ hóa: ≥50% giá trị khớp chợ (cửa sổ 4 tick) thanh toán bằng xu
    kl_4: dict[str, float] = {}
    for d in w.kl_thanh_toan_4:
        for k, v in d.items():
            kl_4[k] = kl_4.get(k, 0.0) + v
    tong_kl = sum(kl_4.values())
    if tong_kl > 0 and (kl_4.get("xu", 0.0) / tong_kl
                        >= q["tien_te_hoa"]["ty_le_gia_tri_thanh_toan_bang_xu"]):
        nhan["tien_te_hoa"] = ["cho_lang"]
    else:
        nhan["tien_te_hoa"] = []

    # CÔNG NGHIỆP HÓA — cột mốc đo được (cửa sổ 4 tick = 2 mùa mưa + 2 mùa khô)
    cn = q["cong_nghiep_hoa"]
    cong_4: dict[str, float] = {}
    for d in w.cong_dung_4:
        for k, v in d.items():
            cong_4[k] = cong_4.get(k, 0.0) + v
    tong_cong = sum(cong_4.values())
    phi_nong = cong_4.get("phi_nong", 0.0)
    so_may = w.ledger.tong_tai_san("may")
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    lao_dong = [a for a in w.agents.values() if a.con_song and a.truong_thanh(tt)]
    entity_5 = {eid for eid, nguoi in gop_cong_den.items()
                if eid in w.entities and len(nguoi) >= 5}
    lam_entity5 = set()
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if ck.loai == "gop_cong" and ben_hien_tai(w, hd.id, ck.den) in entity_5:
                lam_entity5.add(ben_hien_tai(w, hd.id, ck.tu))
    dieu_kien = (
        tong_cong > 0
        and phi_nong / tong_cong > cn["ty_trong_cong_phi_nong_toi_thieu"]
        and so_may >= cn["so_may_hoat_dong_toi_thieu"]
        and lao_dong
        and len(lam_entity5) / len(lao_dong) >= cn["ty_le_lao_dong_trong_entity_5_nguoi"]
    )
    nhan["cong_nghiep_hoa"] = ["xa_hoi"] if dieu_kien else []
    return nhan


# ------------------------------------------------------------------ milestones

TEN_MILESTONE = {
    "hop_dong_van_ban_dau", "vi_pham_cuong_che_dau", "mo_tip_gui_rut_dau", "entity_dau",
    "co_phan_doi_chu_dau", "blueprint_dau", "hang_moi_dau", "may_dau", "nhan_xuong_dau",
    "bao_hiem_dau", "xu_qua_50", "lang_moi", "san_tri_thuc_tang", "cong_nghiep_hoa",
    "mat_het_dat_dau", "soan_ngoi_giau_nhat",
}


def quet_milestones(w: World, nhan: dict[str, list[str]]) -> None:
    da_co = {m["ten"] for m in w.milestones}

    def ghi(ten: str, **chi_tiet) -> None:
        if ten in da_co:
            return
        da_co.add(ten)
        w.milestones.append({"ten": ten, "tick": w.tick, **chi_tiet})
        w.events.ghi(w.tick, "milestone", ten=ten, **chi_tiet)

    import itertools

    can_quet_hd = not {"hop_dong_van_ban_dau", "mo_tip_gui_rut_dau",
                       "vi_pham_cuong_che_dau"} <= da_co
    for hd in itertools.chain(w.hop_dong.values(),
                              w.hop_dong_xong.values() if can_quet_hd else ()):
        if hd.hinh_thuc == "van_ban":
            ghi("hop_dong_van_ban_dau", hd=hd.id)
        for ck in hd.dieu_khoan:
            if ck.loai == "hoan_tra_theo_yeu_cau":
                ghi("mo_tip_gui_rut_dau", hd=hd.id)
        if hd.trang_thai == "vi_pham":
            ghi("vi_pham_cuong_che_dau", hd=hd.id)
    if w.entities:
        ghi("entity_dau", entity=sorted(w.entities)[0])
    if w.blueprints:
        ghi("blueprint_dau", bp=sorted(w.blueprints)[0])
    if any(bp.hang_moi for bp in w.blueprints.values()):
        ghi("hang_moi_dau",
            hang=next(bp.hang_moi for bp in w.blueprints.values() if bp.hang_moi))
    if w.ledger.tong_tai_san("may") >= 1:
        ghi("may_dau")
    if nhan.get("xuong"):
        ghi("nhan_xuong_dau", entity=nhan["xuong"][0])
    if nhan.get("bao_hiem"):
        ghi("bao_hiem_dau", ai=nhan["bao_hiem"][0])
    if nhan.get("tien_te_hoa"):
        ghi("xu_qua_50")
    if len(w.villages) > 1:
        ghi("lang_moi", lang=w.villages[-1].ten)
    if w.san_tri_thuc_tier >= 1:
        ghi("san_tri_thuc_tang", san=w.san_tri_thuc_tier)
    if nhan.get("cong_nghiep_hoa"):
        ghi("cong_nghiep_hoa", nam=w.nam())
    for ts, ls in w.gia_lich_su.items():
        if ts.startswith("co_phan:") and ls:
            ghi("co_phan_doi_chu_dau", tai_san=ts)
            break


# ---------------------------------------------- chỉ số vĩ mô (CHỈ ĐỌC metrics)

# Bốn chỉ số kinh tế vĩ mô "viện hàn lâm" — GDP thực, vòng quay tiền (velocity),
# Gini thu nhập, tỷ lệ giao dịch phi lý — do engine/metrics.py TÍNH và ghi vào mỗi
# bản ghi metrics. Chúng THUẦN QUAN SÁT (điều luật #7): không một quy luật kinh tế
# nào bị mã hóa để engine rẽ nhánh theo — ta chỉ ĐO cái đã tự phát xảy ra. Hàm dưới
# đây thuộc observatory (CHỈ ĐỌC nhật ký metrics) để tools trực quan hóa quỹ đạo.
GINI_QUY_DAO = ("gini_thoc", "gini_dat", "gini_thu_nhap")


def quy_dao_gini(w: World) -> list[tuple[int, float, float, float]]:
    """Quỹ đạo bất bình đẳng theo thời gian để tools vẽ đường: mỗi phần tử là
    (tick, gini_thoc, gini_dat, gini_thu_nhap). Chỉ đọc w.metrics_lich_su."""
    return [
        (m["tick"], m.get("gini_thoc", 0.0), m.get("gini_dat", 0.0),
         m.get("gini_thu_nhap", 0.0))
        for m in w.metrics_lich_su
    ]


def buoc_observatory(w: World) -> dict:
    """Chạy trong bước két toán: dán nhãn, milestones; trả metrics bổ sung."""
    nhan = nhan_dinh_che(w)
    w.nhan_dinh_che = nhan
    quet_milestones(w, nhan)
    giai_cap = phan_loai_giai_cap(w)
    dem: dict[str, int] = {}
    for _aid, gc in giai_cap.items():
        dem[gc] = dem.get(gc, 0) + 1
    for ten_nhan, ai_list in nhan.items():
        if ai_list:
            w.events.ghi(w.tick, "nhan_dinh_che", nhan=ten_nhan, ai=ai_list)
    return {"giai_cap": dem, "nhan_dinh_che": {k: len(v) for k, v in nhan.items() if v},
            "phan_loai": giai_cap}


def viet_chronicle(w: World, delta_metrics: dict) -> str:
    """Sử ký ≤120 từ (mock viết) từ milestones mới + biến động chính."""
    nam = w.nam()
    moi = [m for m in w.milestones if m["tick"] > w.tick - 20]
    phan_mo_dau = f"Năm {nam}: làng có {delta_metrics.get('dan_so', '?')} nhân khẩu."
    if moi:
        ten_su_kien = ", ".join(m["ten"].replace("_", " ") for m in moi[:4])
        phan_mo_dau += f" Chuyện đáng nhớ: {ten_su_kien}."
    gini = delta_metrics.get("gini_dat")
    if gini is not None:
        phan_mo_dau += f" Ruộng đất kẻ nhiều người ít (gini {gini})."
    tt = delta_metrics.get("ty_le_biet_chu")
    if tt is not None:
        phan_mo_dau += f" {round(float(tt) * 100)}% người lớn biết chữ."
    return phan_mo_dau[:600]
