"""SÁNG CHẾ — R&D mở, blueprint, hàng mới, khuếch tán, máy, tri thức (SPEC 3.5).

KHÔNG danh sách phát minh định sẵn, KHÔNG thứ tự bắt buộc, KHÔNG kỷ nguyên.
Blueprint nhân (1+độ_lớn) vào tham số vật lý lĩnh vực CHO NGƯỜI ÁP DỤNG.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from engine.ledger import LoiSoKep
from engine.world import World

TEN_HANG_GOI_Y = ["Vải", "Rượu", "Đường", "Giấy", "Mắm", "Chiếu", "Nón", "Gốm", "Dầu", "Bột"]


@dataclass
class Blueprint:
    id: str
    linh_vuc: str
    do_lon: float
    ten: str
    chu: str  # người hoặc entity
    tick_sinh: int = 0
    # chỉ cho che_bien: hàng mới
    hang_moi: str | None = None
    recipe: dict[str, float] = field(default_factory=dict)
    hieu_ung: str | None = None
    hieu_ung_do_lon: float = 0.0


def diem_nghien_cuu(w: World, aid: str, cong: float, thoc: float) -> float:
    r = w.cfg.raw()["research"]["diem_nghien_cuu"]
    e = w.agents[aid].e_bac if aid in w.agents else 2
    he_so = r["he_so_E"].get(f"E{max(e, 1)}", 1.0)
    return (cong / r["cong_moi_diem"] + thoc / r["thoc_moi_diem"]) * he_so


def thi_hanh_nghien_cuu(w: World, aid: str, linh_vuc: str, cong: float, thoc: float) -> None:
    """Trả công/thóc để tích điểm nghiên cứu; roll blueprint ở buoc_nghien_cuu."""
    r = w.cfg.raw()["research"]
    if linh_vuc not in r["linh_vuc"]:
        w.ghi_unrecognized(aid, "nghien_cuu", f"lĩnh vực lạ: {linh_vuc}")
        return
    cong = min(cong, w.ledger.so_du(aid, "cong"))
    thoc = min(thoc, w.ledger.so_du(aid, "thoc"))
    if cong <= 0 and thoc <= 0:
        return
    try:
        if cong > 0:
            w.ledger.huy(aid, "cong", cong, "dung", f"nghiên cứu {linh_vuc}", w.tick)
        if thoc > 0:
            w.ledger.huy(aid, "thoc", thoc, "nghien_cuu", f"nghiên cứu {linh_vuc}", w.tick)
    except LoiSoKep:
        return
    diem = diem_nghien_cuu(w, aid, cong, thoc)
    key = (aid, linh_vuc)
    w.diem_nc[key] = w.diem_nc.get(key, 0.0) + diem
    w.events.ghi(w.tick, "nghien_cuu", ai=aid, linh_vuc=linh_vuc,
                 diem=round(diem, 2), tich_luy=round(w.diem_nc[key], 2))


def _muc_linh_vuc(w: World, linh_vuc: str) -> int:
    return sum(1 for bp in w.blueprints.values() if bp.linh_vuc == linh_vuc)


def buoc_nghien_cuu(w: World) -> None:
    """Mỗi tick: ai có điểm tích lũy thì roll p thành công (lợi suất giảm dần)."""
    r = w.cfg.raw()["research"]
    xs = r["xac_suat_thanh_cong"]
    kt = r["khuech_tan"]
    g = w.rng.get("blueprint", w.tick)
    for key in sorted(w.diem_nc):
        aid, linh_vuc = key
        diem = w.diem_nc[key]
        if diem <= 0:
            continue
        muc = _muc_linh_vuc(w, linh_vuc)
        # khuếch tán: sao chép rẻ dần theo blueprint lưu hành cùng lĩnh vực
        giam = max(kt["san"], kt["giam_chi_phi_moi_blueprint_luu_hanh"] ** muc)
        k0 = xs["k0"] * giam
        p = 1.0 - math.exp(-diem / (k0 * (1.0 + muc) ** xs["d"]))
        if g.random() >= p * 0.25:  # roll mỗi tick trên p đã tích lũy — nhân 0.25 để mượt
            continue
        w.diem_nc[key] = 0.0
        sinh_blueprint(w, aid, linh_vuc, g)


def sinh_blueprint(w: World, chu: str, linh_vuc: str, g) -> Blueprint:
    r = w.cfg.raw()["research"]
    bp_cfg = r["blueprint"]
    do_lon = min(float(g.lognormal(bp_cfg["do_lon_lognormal"]["mu"],
                                   bp_cfg["do_lon_lognormal"]["sigma"]) - 1.0 + 0.05),
                 bp_cfg["do_lon_tran"])
    do_lon = max(0.02, do_lon)
    w._next_bp += 1
    bid = f"BP{w._next_bp:04d}"
    ten = f"Bí quyết {linh_vuc.replace('_', ' ')} #{w._next_bp}"
    bp = Blueprint(id=bid, linh_vuc=linh_vuc, do_lon=round(do_lon, 4), ten=ten, chu=chu,
                   tick_sinh=w.tick)
    if linh_vuc == "che_bien":
        hm = r["hang_moi"]
        inputs = list(g.choice(hm["input_menu"], size=int(g.integers(1, 3)), replace=False))
        bp.recipe = {str(ts): float(g.integers(1, 4)) for ts in inputs}
        bp.recipe["cong"] = float(g.integers(20, 60))
        bp.hieu_ung = str(g.choice(hm["hieu_ung_menu"]))
        bp.hieu_ung_do_lon = max(0.02, min(0.5, float(
            g.lognormal(hm["do_lon_hieu_ung"]["mu"], hm["do_lon_hieu_ung"]["sigma"]) - 1.0
            + 0.05)))
        goc = TEN_HANG_GOI_Y[int(g.integers(0, len(TEN_HANG_GOI_Y)))]
        bp.hang_moi = f"{goc.lower()}_{w._next_bp}"
        w.ten_hang[bp.hang_moi] = f"{goc} {bp.ten}"
        w.ledger.flows.dang_ky(bp.hang_moi, "che_tac", "nguon")
        w.ledger.flows.dang_ky(bp.hang_moi, "tieu_dung", "sink")
        w.events.ghi(w.tick, "hang_moi", ten=bp.hang_moi, recipe=bp.recipe,
                     hieu_ung=bp.hieu_ung)
    w.blueprints[bid] = bp
    w.events.ghi(w.tick, "blueprint_moi", id=bid, linh_vuc=linh_vuc,
                 do_lon=bp.do_lon, chu=chu, ten=ten)
    return bp


def duoc_ap_dung(w: World, aid: str, linh_vuc: str) -> float:
    """Tổng độ lớn blueprint lĩnh vực mà aid ÁP DỤNG ĐƯỢC (sở hữu / li-xăng quyen_su_dung)."""
    tong = 0.0
    quyen: set[str] = set()
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if ck.loai == "quyen_su_dung" and ck.tai_san.startswith("blueprint:"):
                from engine.contracts import ben_hien_tai

                if ben_hien_tai(w, hd.id, ck.den) == aid:
                    quyen.add(ck.tai_san.split(":", 1)[1])
    for bp in w.blueprints.values():
        if bp.linh_vuc == linh_vuc and (bp.chu == aid or bp.id in quyen):
            tong += bp.do_lon
    return tong


def tinh_tri_thuc(w: World) -> float:
    tong_bp = sum(math.log(1.0 + bp.do_lon) for bp in w.blueprints.values())
    nguoi_lon = [a for a in w.agents.values() if a.con_song and a.tuoi_nam >= 16]
    biet_chu = (sum(1 for a in nguoi_lon if a.e_bac >= 1) / len(nguoi_lon)) if nguoi_lon else 0
    return tong_bp + 3.0 * biet_chu


def cap_nhat_san_tier(w: World) -> None:
    """Sàn tier model toàn dân tăng theo tri thức nội sinh — không đầu tư thì đứng im."""
    tri_thuc = tinh_tri_thuc(w)
    w.tri_thuc = tri_thuc
    nguong = w.cfg.raw()["research"]["tri_thuc"]["nguong_san_tier"]
    san = 0
    for muc in nguong:
        if tri_thuc >= muc["tri_thuc"]:
            san = max(san, int(str(muc["san"]).lstrip("T")))
    if san > getattr(w, "san_tri_thuc_tier", 0):
        w.san_tri_thuc_tier = san
        w.events.ghi(w.tick, "san_tri_thuc_tang", san=f"T{san}", tri_thuc=round(tri_thuc, 2))
