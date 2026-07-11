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
    if kh.xay_may:
        hd_list.append({"loai": "xay", "mon": "may", "so_luong": kh.xay_may})
    if kh.duc_xu:
        hd_list.append({"loai": "xay", "mon": "xu", "so_luong": kh.duc_xu})
    for ma, sl in sorted(kh.che_hang.items()):
        hd_list.append({"loai": "xay", "mon": ma, "so_luong": sl})
    if kh.nghien_cuu:
        lv, cong, thoc = kh.nghien_cuu
        hd_list.append({"loai": "nghien_cuu", "linh_vuc": lv, "cong": cong, "thoc": thoc})
    if kh.lap_phap_nhan:
        hd_list.append({"loai": "lap_phap_nhan", **kh.lap_phap_nhan})
    for eid, kh_con in kh.quyet_dinh_entity:
        qd_con = ke_hoach_thanh_quyet_dinh(kh_con)
        hd_list.append({"loai": "quyet_dinh_entity", "entity": eid,
                        "hanh_dong_con": qd_con["hanh_dong"]})
    if kh.viet_di_chuc:
        hd_list.append({"loai": "viet_di_chuc", **kh.viet_di_chuc})
    if kh.di_cu:
        hd_list.append({"loai": "di_cu"})
    if kh.bat_ga_cong or kh.giet_ga:
        hd_list.append({"loai": "chan_nuoi", "bat_ga_cong": kh.bat_ga_cong,
                        "giet_ga": kh.giet_ga})
    for den, ts, sl in kh.bieu:
        hd_list.append({"loai": "bieu", "den": den, "tai_san": ts, "so_luong": sl})
    if kh.danh_ca_cong:
        hd_list.append({"loai": "danh_ca", "cong": kh.danh_ca_cong})
    if kh.mo_tiec:
        hd_list.append({"loai": "mo_tiec", "thoc": kh.mo_tiec[0], "thit": kh.mo_tiec[1]})
    if kh.trom:
        hd_list.append({"loai": "trom", "muc_tieu": kh.trom[0], "tai_san": kh.trom[1],
                        "so_luong": kh.trom[2]})
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


def quyet_dinh_thanh_ke_hoach(w, qd: QuyetDinh,
                              thung_intent_la: list | None = None) -> KeHoach:
    """QuyetDinh (đã validate schema) → KeHoach.

    Hành động lạ/sai tham số: có `thung_intent_la` → gom vào thùng cho bộ phiên dịch
    intent (LLM) thử ánh xạ; không có thùng → bỏ + log như cũ (điều luật #3).
    """
    kh = KeHoach(id=qd.id)
    for hd in qd.hanh_dong:
        try:
            _mot_hanh_dong(w, kh, hd, thung_intent_la)
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as e:
            if thung_intent_la is not None:
                thung_intent_la.append((qd.id, hd.model_dump(), f"tham số sai: {e}"))
            else:
                w.ghi_unrecognized(qd.id, hd.loai, f"tham số sai: {e}")
    # ý định sinh con nằm trong thẻ (patch xử lý ở orchestrator)
    return kh


def _mot_hanh_dong(w, kh: KeHoach, hd: HanhDong, thung: list | None = None) -> None:
    d = hd.model_dump()
    loai = d.get("loai")
    if loai not in LOAI_HANH_DONG:
        if thung is not None:
            thung.append((kh.id, d, "loại hành động lạ"))
        else:
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
        elif mon == "may":
            kh.xay_may += max(0, sl)
        elif mon == "xu":
            kh.duc_xu += max(0, sl)
        elif isinstance(mon, str) and mon in w.ten_hang:
            kh.che_hang[mon] = kh.che_hang.get(mon, 0) + max(0, sl)
        elif thung is not None:
            thung.append((kh.id, d, f"món lạ: {mon}"))
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
    elif loai == "nghien_cuu":
        kh.nghien_cuu = (str(d["linh_vuc"]), float(d.get("cong", 0)), float(d.get("thoc", 0)))
    elif loai == "lap_phap_nhan":
        kh.lap_phap_nhan = {
            "ten": str(d.get("ten", "")),
            "co_phan": {str(k): float(v) for k, v in dict(d.get("co_phan", {})).items()},
            "von_gop": {
                str(k): {str(t): float(s) for t, s in dict(v).items()}
                for k, v in dict(d.get("von_gop", {})).items()
            },
        }
    elif loai == "quyet_dinh_entity":
        eid = str(d["entity"])
        con = d.get("hanh_dong_con", [])
        kh_con = KeHoach(id=eid)
        for hd_con in con if isinstance(con, list) else []:
            try:
                _mot_hanh_dong(w, kh_con, HanhDong.model_validate(hd_con))
            except Exception:  # noqa: BLE001 — hành động con hỏng thì bỏ riêng nó
                w.ghi_unrecognized(eid, "hanh_dong_con", "hành động con hỏng")
        kh.quyet_dinh_entity.append((eid, kh_con))
    elif loai == "viet_di_chuc":
        kh.viet_di_chuc = {
            "phan_bo": {str(k): float(v) for k, v in dict(d.get("phan_bo", {})).items()},
            "gia_huan": str(d.get("gia_huan", ""))[:400],
        }
    elif loai == "di_cu":
        kh.di_cu = True
    elif loai == "chan_nuoi":
        kh.bat_ga_cong += max(0.0, float(d.get("bat_ga_cong", 0) or 0))
        kh.giet_ga += max(0, int(d.get("giet_ga", 0) or 0))
    elif loai == "bieu":
        kh.bieu.append((str(d["den"]), str(d.get("tai_san", "thoc")),
                        float(d["so_luong"])))
    elif loai == "danh_ca":
        kh.danh_ca_cong += max(0.0, float(d.get("cong", d.get("so_cong", 0)) or 0))
    elif loai == "mo_tiec":
        kh.mo_tiec = (max(0.0, float(d.get("thoc", 0) or 0)),
                      max(0.0, float(d.get("thit", 0) or 0)))
    elif loai == "trom":
        kh.trom = (str(d["muc_tieu"]), str(d.get("tai_san", "thoc")),
                   max(0.0, float(d.get("so_luong", 50) or 0)))
    elif loai == "buon_chuyen":
        chieu = d.get("chieu", "ban")
        if chieu in ("mua", "ban"):
            kh.dat_lenh.append(Lenh(kh.id, chieu, str(d["tai_san"]), float(d["sl"]),
                                    float(d["gia"]), str(d.get("thanh_toan", "thoc")),
                                    lang=int(d["lang"])))
    else:
        if thung is not None:
            thung.append((kh.id, d, "nguyên tố chưa mở ở phase hiện tại"))
        else:
            w.ghi_unrecognized(kh.id, str(loai), "nguyên tố chưa mở ở phase hiện tại")
