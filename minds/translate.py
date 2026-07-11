"""Ánh xạ hai chiều KeHoach ↔ QuyetDinh (15 nguyên tố hành động, SPEC 5).

- PersonaBot nghĩ bằng KeHoach → xuất QuyetDinh JSON (như một LLM thật sẽ trả).
- Validator nhận QuyetDinh (đã sửa JSON) → dựng lại KeHoach cho engine.
Tham số sai / loại lạ → bỏ + ghi unrecognized, KHÔNG lỗi (điều luật #3).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from engine.contracts import HopDong
from engine.intents import KeHoach
from engine.market import Lenh
from minds.schemas import LOAI_HANH_DONG, HanhDong, QuyetDinh


def ke_hoach_thanh_quyet_dinh(kh: KeHoach, patch: dict | None = None,
                              ly_do: str = "") -> dict[str, Any]:
    """KeHoach → dict QuyetDinh (sẵn sàng serialize JSON)."""
    hd_list: list[dict[str, Any]] = []
    pbc: dict[str, Any] = {}
    if kh.canh_thua:
        pbc["canh_thua"] = list(kh.canh_thua)
    if kh.gop_cong_cho:
        pbc["gop_cong_cho"] = kh.gop_cong_cho
    if kh.cong_khai_go:
        pbc["khai_go_cong"] = kh.cong_khai_go
    if kh.cong_khai_quang:
        pbc["khai_quang_cong"] = kh.cong_khai_quang
    if kh.hoc:
        pbc["hoc"] = True
    if kh.day_cho:
        pbc["day_cho"] = list(kh.day_cho)
    if pbc:
        hd_list.append({"loai": "phan_bo_cong", **pbc})
    if kh.che_tao_cong_cu:
        hd_list.append({"loai": "xay", "mon": "che_tac", "so_luong": kh.che_tao_cong_cu})
    if kh.xay_nha:
        hd_list.append({"loai": "xay", "mon": "nha", "so_luong": kh.xay_nha})
    for hd, den in kh.de_nghi_hop_dong:
        hd_list.append({
            "loai": "de_nghi_hop_dong",
            "den": den,
            "hop_dong": hd.model_dump(exclude={"id", "trang_thai", "tick_ky",
                                               "huy_bao_truoc_tu"}),
        })
    for ref, tl in kh.tra_loi_de_nghi.items():
        muc = {"loai": "tra_loi_hop_dong", "ref": ref}
        if tl == "chap_nhan" or tl == "tu_choi":
            muc["tra_loi"] = tl
        elif isinstance(tl, HopDong):
            muc["tra_loi"] = "mac_ca"
            muc["sua_doi"] = tl.model_dump(exclude={"id", "trang_thai", "tick_ky"})
        hd_list.append(muc)
    for ref in kh.don_phuong_pha_vo:
        hd_list.append({"loai": "don_phuong_pha_vo", "ref": ref})
    for le in kh.dat_lenh:
        hd_list.append({"loai": "dat_lenh", "chieu": le.chieu, "tai_san": le.tai_san,
                        "sl": le.so_luong, "gia": le.gia, "thanh_toan": le.thanh_toan})
    for thua, gia in kh.niem_yet_dat:
        hd_list.append({"loai": "niem_yet", "tai_san": f"thua:{thua}", "gia": gia})
    for thua, gia in kh.tra_gia_dat:
        hd_list.append({"loai": "tra_gia_dat", "thua": thua, "gia": gia})
    for ref, sl in kh.yeu_cau_rut.items():
        hd_list.append({"loai": "yeu_cau_hoan_tra", "ref": ref, "so_luong": sl})
    if kh.cau_hon:
        hd_list.append({"loai": "cau_hon", "den": kh.cau_hon})
    for tu, dong_y in kh.tra_loi_cau_hon.items():
        hd_list.append({"loai": "tra_loi_cau_hon", "cua": tu, "dong_y": dong_y})
    qd: dict[str, Any] = {"id": kh.id, "hanh_dong": hd_list, "ly_do": ly_do}
    if patch:
        qd["the_chinh_sach"] = patch
    return qd


def quyet_dinh_thanh_ke_hoach(w, qd: QuyetDinh) -> KeHoach:
    """QuyetDinh (đã validate schema) → KeHoach; hành động lạ/sai tham số → bỏ + log."""
    kh = KeHoach(id=qd.id)
    for hd in qd.hanh_dong:
        try:
            _mot_hanh_dong(w, kh, hd)
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as e:
            w.ghi_unrecognized(qd.id, hd.loai, f"tham số sai: {e}")
    # ý định sinh con nằm trong thẻ (patch xử lý ở orchestrator)
    return kh


def _mot_hanh_dong(w, kh: KeHoach, hd: HanhDong) -> None:
    d = hd.model_dump()
    loai = d.get("loai")
    if loai not in LOAI_HANH_DONG:
        w.ghi_unrecognized(kh.id, str(loai), "loại hành động lạ")
        return
    if loai == "phan_bo_cong":
        kh.canh_thua = [str(x) for x in d.get("canh_thua", [])][:10]
        if d.get("gop_cong_cho"):
            kh.gop_cong_cho = str(d["gop_cong_cho"])
        kh.cong_khai_go = max(0.0, float(d.get("khai_go_cong", 0) or 0))
        kh.cong_khai_quang = max(0.0, float(d.get("khai_quang_cong", 0) or 0))
        kh.hoc = bool(d.get("hoc", False))
        kh.day_cho = [str(x) for x in d.get("day_cho", [])]
    elif loai == "khai_hoang":
        thua = str(d.get("thua", ""))
        if thua and thua not in kh.canh_thua:
            kh.canh_thua.append(thua)
    elif loai == "xay":
        mon = d.get("mon", d.get("nha", "nha"))
        sl = int(d.get("so_luong", 1))
        if mon in ("che_tac", "cong_cu"):
            kh.che_tao_cong_cu += max(0, sl)
        elif mon == "nha":
            kh.xay_nha += max(0, sl)
        else:
            w.ghi_unrecognized(kh.id, "xay", f"món lạ: {mon}")
    elif loai == "de_nghi_hop_dong":
        hop_dong = HopDong(**d["hop_dong"])
        den = d.get("den")
        kh.de_nghi_hop_dong.append((hop_dong, str(den) if den else None))
    elif loai == "tra_loi_hop_dong":
        ref = str(d["ref"])
        tl = d.get("tra_loi", "tu_choi")
        if tl == "mac_ca" and d.get("sua_doi"):
            kh.tra_loi_de_nghi[ref] = HopDong(**d["sua_doi"])
        elif tl in ("chap_nhan", "tu_choi"):
            kh.tra_loi_de_nghi[ref] = tl
    elif loai == "don_phuong_pha_vo":
        kh.don_phuong_pha_vo.append(str(d["ref"]))
    elif loai == "dat_lenh":
        chieu = d.get("chieu", d.get("mua_ban"))
        if chieu not in ("mua", "ban"):
            raise ValueError(f"chiều lạ: {chieu}")
        kh.dat_lenh.append(Lenh(kh.id, chieu, str(d["tai_san"]), float(d["sl"]),
                                float(d["gia"]), str(d.get("thanh_toan", "thoc"))))
    elif loai == "niem_yet":
        ts = str(d["tai_san"])
        if ts.startswith("thua:"):
            kh.niem_yet_dat.append((ts.split(":", 1)[1], float(d["gia"])))
        else:
            kh.dat_lenh.append(Lenh(kh.id, "ban", ts, float(d.get("sl", 1)), float(d["gia"])))
    elif loai == "tra_gia_dat":
        kh.tra_gia_dat.append((str(d["thua"]), float(d["gia"])))
    elif loai == "yeu_cau_hoan_tra":
        kh.yeu_cau_rut[str(d["ref"])] = float(d["so_luong"])
    elif loai == "cau_hon":
        kh.cau_hon = str(d["den"])
    elif loai == "tra_loi_cau_hon":
        kh.tra_loi_cau_hon[str(d["cua"])] = bool(d["dong_y"])
    else:
        # nguyên tố chưa mở ở phase này (nghien_cuu, lap_phap_nhan, di_cu, viet_di_chuc,
        # buon_chuyen, quyet_dinh_entity) → mỏ ý định mới lạ
        w.ghi_unrecognized(kh.id, str(loai), "nguyên tố chưa mở ở phase hiện tại")
