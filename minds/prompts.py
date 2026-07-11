"""Prompt builder tiếng Việt (SPEC 4.6, Phụ lục A) — mô tả thế giới SINH TỪ TRẠNG THÁI THẬT.

Mock không đọc prompt (dùng ctx), nhưng prompt vẫn được build + log để (a) Phase 7 dùng
ngay, (b) llm_calls có tok_in trung thực.
"""

from __future__ import annotations

from engine.world import World

MAU_KHOI_DAU = [
    '{"cac_ben":["A","B"],"hinh_thuc":"mieng","thoi_han":1,"dieu_khoan":[{"loai":"gop_cong",'
    '"tu":"A","den":"B","so_cong_moi_tick":60},{"loai":"chuyen_giao_mot_lan","tu":"B",'
    '"den":"A","tai_san":"thoc","so_luong":240,"tai":"ky_ket"}]}',
    '{"cac_ben":["A","B"],"hinh_thuc":"mieng","thoi_han":4,"dieu_khoan":[{"loai":'
    '"chuyen_giao_mot_lan","tu":"A","den":"B","tai_san":"thoc","so_luong":200,"tai":"ky_ket"},'
    '{"loai":"chuyen_giao_mot_lan","tu":"B","den":"A","tai_san":"thoc","so_luong":220,'
    '"tai":"dao_han"}]}',
]


def mau_hop_dong_luu_hanh(w: World, top_k: int) -> list[str]:
    """Mẫu THẬT từ hợp đồng đang hiệu lực (ẩn danh hóa, top-k theo tần suất mô-típ).

    Khởi đầu chỉ 2 mẫu tối giản — chuẩn mực lan như văn hóa (SPEC 3.2).
    """
    from engine.board import mo_tip_hop_dong

    dem: dict[str, tuple[int, str]] = {}
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        motif = mo_tip_hop_dong(hd)
        so, _ = dem.get(motif, (0, ""))
        ten_map = {b: chr(65 + i) for i, b in enumerate(hd.cac_ben)}
        vd = hd.model_dump(include={"cac_ben", "hinh_thuc", "thoi_han", "dieu_khoan"})
        vd_str = str(vd)
        for goc, an in ten_map.items():
            vd_str = vd_str.replace(goc, an)
        dem[motif] = (so + 1, vd_str)
    xep = sorted(dem.items(), key=lambda kv: -kv[1][0])[:top_k]
    mau = [vd for _, (_, vd) in xep]
    if not mau:
        mau = MAU_KHOI_DAU
    return mau


def mo_ta_the_gioi(w: World) -> str:
    """Khối mô tả thế giới sinh động từ trạng thái thật (không kỷ nguyên kịch bản)."""
    tai_san_ton_tai = sorted(w.ledger.cac_tai_san() - {"cong"})
    so_hd = sum(1 for h in w.hop_dong.values() if h.trang_thai == "hieu_luc")
    dan = sum(1 for a in w.agents.values() if a.con_song)
    return (
        f"Làng có {dan} người. Của cải đang lưu hành: {', '.join(tai_san_ton_tai)}. "
        f"Trong làng đang có {so_hd} thỏa thuận còn hiệu lực. "
        f"Mọi trao đổi tính bằng thóc; ai thất hứa sẽ bị cả làng nhớ mặt."
    )


def build_system(w: World, aid: str, schema_str: str) -> str:
    a = w.agents[aid]
    return (
        f"Bạn là {a.ten}, {a.tuoi_nam:.0f} tuổi, làng {w.villages[a.lang].ten}, "
        f"năm {w.tick // 2}. Tính cách (1-9): {a.persona.as_dict()}. "
        f"Gia huấn: \"{a.gia_huan or '(chưa có)'}\". Hồi ký: {a.hoi_ky or '(trống)'}. "
        f"Thế giới bạn biết: {mo_ta_the_gioi(w)} Bạn chỉ biết những gì làng bạn biết. "
        f"Hãy quyết định như CHÍNH BẠN, nhất quán với tính cách và ký ức riêng, kể cả khi "
        f"khác mọi người. Chỉ trả về DUY NHẤT một JSON đúng schema: {schema_str}"
    )


def build_user_chung(w: World) -> str:
    loai_tt, he_so = w.thoi_tiet(w.tick)
    gia = {ts: w.gia_gan_nhat(ts) for ts in ("go", "cong_cu", "dat")}
    gia_str = ", ".join(f"{ts}: {g:.0f} thóc" for ts, g in gia.items() if g)
    so_rao = len(w.bang_rao)
    mau = mau_hop_dong_luu_hanh(w, int(w.cfg.get("minds.mau_hop_dong_trong_prompt_top_k")))
    return (
        f"[TÌNH HÌNH CHUNG] Mùa {'mưa' if w.mua_mua() else 'khô'}, thời tiết {loai_tt} "
        f"(hệ số {he_so}). Giá chợ gần nhất: {gia_str or 'chưa có phiên nào'}. "
        f"Bảng rao có {so_rao} đề nghị. "
        f"[CÁC DẠNG THỎA THUẬN ĐANG LƯU HÀNH] {mau} "
        f"[BẠN CÓ THỂ] đề nghị/trả lời hợp đồng (văn phạm 9 điều khoản: chuyen_giao_dinh_ky, "
        f"chuyen_giao_mot_lan, quyen_su_dung, gop_cong, chia_san_luong, chia_loi_nhuan, "
        f"dieu_kien_su_kien, hoan_tra_theo_yeu_cau, khi_pha_vo), lap_phap_nhan, dat_lenh "
        f"mua/bán mọi tài sản, niem_yet/tra_gia_dat, phan_bo_cong, khai_hoang, xay, "
        f"nghien_cuu, buon_chuyen, cau_hon, viet_di_chuc, di_cu."
    )


SCHEMA_QUYET_DINH = """[ĐỊNH DẠNG TRẢ LỜI — BẮT BUỘC]
Trả về DUY NHẤT một MẢNG JSON (không lời dẫn, không markdown), mỗi phần tử là quyết định
của MỘT người: {"id":"A0001","the_chinh_sach":{...tùy chọn},"hanh_dong":[...],"ly_do":"1 câu"}.
Không hành động gì thì để "hanh_dong":[]. Mỗi người quyết định ĐỘC LẬP theo tính cách riêng.

the_chinh_sach (thói quen tự chạy khi bạn không được hỏi — chỉ ghi trường muốn đổi):
{"du_tru_muc_tieu":2.5,"canh_toi_da":3,"khai_go_khi_ranh":true,"hoc_khi_du_an":false,
 "day_con":true,"y_dinh_sinh_con":0|0.5|1,"nhan_lam_cong_gia_toi_thieu":3.5,
 "nhan_gui_thoc":false,"ban_go_nguong":4,"mua_cong_cu_khi_hong":true,"nguong_rao_dat":0.3}

hanh_dong hợp lệ (loai + tham số):
- {"loai":"phan_bo_cong","canh_thua":["P15_04"],"khai_go_cong":60,"khai_quang_cong":0,
   "hoc":true,"day_cho":["A0012"]}   (canh thửa mình/thửa công/thửa có quyền dùng)
- {"loai":"xay","mon":"nha"|"che_tac"|"may"|"xu"|"<mã hàng mới>","so_luong":1}
- {"loai":"de_nghi_hop_dong","den":"A0031"|null,"hop_dong":{"cac_ben":["<id bạn>","?"],
   "hinh_thuc":"mieng"|"van_ban","thoi_han":8,"the_chap":["thua:P15_04"],"dieu_khoan":[...]}}
  ("?" = bên chưa biết, người nhận lời sẽ thế chỗ; bạn PHẢI là một bên; văn bản cần E1)
- {"loai":"tra_loi_hop_dong","ref":"DN00012","tra_loi":"chap_nhan"|"tu_choi"}
- {"loai":"dat_lenh","chieu":"mua"|"ban","tai_san":"go|cong_cu|quang_dong|xu|nha|thoc|
   co_phan:E0001|<mã hàng>","sl":4,"gia":12.5,"thanh_toan":"thoc"}
- {"loai":"niem_yet","tai_san":"thua:P15_04","gia":600}   (rao bán đất của mình)
- {"loai":"tra_gia_dat","thua":"P15_04","gia":650}        (trả giá đất đang niêm yết)
- {"loai":"yeu_cau_hoan_tra","ref":"HD00007","so_luong":200}  (rút từ hợp đồng gửi)
- {"loai":"nghien_cuu","linh_vuc":"nong_nghiep|cong_cu_may_moc|luu_kho|van_chuyen|y_te|
   vat_lieu|che_bien","cong":60,"thoc":50}
- {"loai":"lap_phap_nhan","ten":"...","co_phan":{"<id bạn>":100},
   "von_gop":{"<id bạn>":{"thoc":1500}}}   (vốn góp chỉ từ túi bạn)
- {"loai":"quyet_dinh_entity","entity":"E0001","hanh_dong_con":[<các hành động trên>]}
- {"loai":"cau_hon","den":"A0042"} · {"loai":"tra_loi_cau_hon","cua":"A0042","dong_y":true}
- {"loai":"viet_di_chuc","phan_bo":{"A0051":60,"A0052":40},"gia_huan":"≤100 từ"}
- {"loai":"di_cu"} · {"loai":"don_phuong_pha_vo","ref":"HD00003"}

Văn phạm dieu_khoan (9 loại — ghép tự do thành mọi kiểu thỏa thuận):
chuyen_giao_dinh_ky{tu,den,tai_san,so_luong,moi_n_tick} ·
chuyen_giao_mot_lan{tu,den,tai_san,so_luong,tai:"ky_ket"|"dao_han"} ·
quyen_su_dung{tai_san:"thua:P.."|"blueprint:BP..",tu,den} · gop_cong{tu,den,so_cong_moi_tick} ·
chia_san_luong{nguon:"thua:P..",ty_le:0.4,den} ·
dieu_kien_su_kien{neu:{"loai":"han_lu"},thi:<chuyen_giao_*>} ·
hoan_tra_theo_yeu_cau{tu,den,tai_san,tran_rut_moi_tick} ·
khi_pha_vo{phat:"xiet_the_chap"|"khong"} · chia_loi_nhuan{entity,theo_co_phan:true}"""


def build_batch_prompt(w: World, ids: list[str], triggers: dict[str, list[str]]) -> str:
    """Prompt trọn gói cho một batch: luật chơi + tình hình chung + N khối riêng + schema."""
    dau = (
        "Bạn sẽ đóng vai TỪNG NGƯỜI dưới đây trong một làng tự cung tự cấp (1 tick = 6 "
        "tháng). Mỗi người chỉ biết những gì làng mình biết, quyết định như CHÍNH HỌ — "
        "nhất quán với tính cách, ký ức, gia huấn riêng, kể cả khi khác số đông. "
        "Đơn vị giá trị: kg thóc.\n\n"
    )
    chung = build_user_chung(w)
    rieng = "\n\n".join(build_user_rieng(w, aid, triggers.get(aid, [])) for aid in ids)
    return f"{dau}{chung}\n\n{rieng}\n\n{SCHEMA_QUYET_DINH}\n" \
           f"Trả mảng JSON đúng {len(ids)} phần tử, id theo thứ tự: {ids}."


def build_user_rieng(w: World, aid: str, ly_do_trigger: list[str]) -> str:
    a = w.agents[aid]
    tai_san = w.ledger.tai_san_cua(aid)
    tai_san_str = ", ".join(
        f"{ts}: {sl:.0f}" for ts, sl in sorted(tai_san.items())
        if not ts.startswith("vi_the:")
    )
    dat = sorted(p.id for p in w.parcels.values() if p.chu == aid)
    hd_cua = []
    for h in w.hop_dong.values():
        if h.trang_thai == "hieu_luc" and aid in h.cac_ben:
            mo_ta = "+".join(sorted(c.loai for c in h.dieu_khoan))
            hd_cua.append(f"{h.id}({mo_ta}, hạn {h.thoi_han})")
    rao_cho_toi = [
        f"{dn.id}<{dn.motif}, từ {dn.tu}>" for dn in sorted(
            w.bang_rao.values(), key=lambda d: d.id)
        if (dn.den == aid or dn.den is None) and dn.tu != aid
    ][:8]
    # gia đình
    vo_chong = a.vo_chong if a.vo_chong and w.agents.get(a.vo_chong, None) else None
    con_song = [c for c in a.con if c in w.agents and w.agents[c].con_song]
    gia_dinh = []
    if vo_chong:
        gia_dinh.append(f"vợ/chồng {vo_chong}")
    if con_song:
        gia_dinh.append(f"con: {con_song}")
    # ứng viên hôn nhân (độc thân, khác giới, cùng làng — đồ thị xã hội rút gọn)
    ung_vien = []
    if a.vo_chong is None and 16 <= a.tuoi_nam <= 45:
        from engine.demography import can_huyet

        khac = "nu" if a.gioi_tinh == "nam" else "nam"
        ung_vien = [
            b.id for b in w.agents.values()
            if b.con_song and b.vo_chong is None and b.gioi_tinh == khac
            and b.truong_thanh(16) and b.lang == a.lang and not can_huyet(w, aid, b.id)
        ][:6]
    # đất công gần làng (để khai hoang/canh)
    lang = w.villages[a.lang]
    dat_cong = sorted(
        (p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None),
        key=lambda p: (abs(p.r - lang.r) + abs(p.c - lang.c), p.id),
    )[:5]
    # entity mình điều hành / cổ phần (map điều hành cache MỘT lần mỗi tick)
    co_phan = [f"{ts.split(':', 1)[1]}: {sl:.0f}%" for ts, sl in sorted(tai_san.items())
               if ts.startswith("co_phan:")]
    if getattr(w, "_cache_dh_tick", None) != w.tick:
        from engine.entities import nguoi_dieu_hanh

        w._cache_dh = {}
        for eid, e in w.entities.items():
            if e.con_hoat_dong:
                mgr = nguoi_dieu_hanh(w, eid)
                if mgr:
                    w._cache_dh.setdefault(mgr, []).append(eid)
        w._cache_dh_tick = w.tick
    dieu_hanh = [
        f"{eid}({w.entities[eid].ten}, thóc {w.ledger.so_du(eid, 'thoc'):.0f}, "
        f"máy {w.ledger.so_du(eid, 'may'):.0f})"
        for eid in w._cache_dh.get(aid, ())
    ]
    dong = [
        f"[NGƯỜI {aid}] {a.ten}, {a.tuoi_nam:.0f} tuổi, {'nữ' if a.gioi_tinh == 'nu' else 'nam'}, "
        f"học vấn E{a.e_bac}, sức khỏe {a.health:.0f}/100. "
        f"Tính cách (1-9): {a.persona.as_dict()}.",
        f"Hồi ký: {a.hoi_ky or '(trống)'} | Gia huấn: \"{a.gia_huan or '(chưa có)'}\"",
        f"Tài sản: {tai_san_str or 'trắng tay'}. Đất của bạn: {dat or 'không có'}.",
    ]
    if gia_dinh:
        dong.append("Gia đình: " + "; ".join(gia_dinh) + ".")
    if hd_cua:
        dong.append(f"Giao kèo đang hiệu lực của bạn: {hd_cua}.")
    if co_phan:
        dong.append(f"Cổ phần: {co_phan}.")
    if dieu_hanh:
        dong.append(f"Bạn đang điều hành: {dieu_hanh} (dùng quyet_dinh_entity).")
    if dat_cong:
        dong.append(f"Đất công gần làng còn trống: {[p.id for p in dat_cong]}.")
    if ung_vien:
        dong.append(f"Người độc thân bạn quen: {ung_vien}.")
    if rao_cho_toi:
        dong.append(f"Đề nghị trên bảng rao bạn thấy: {rao_cho_toi}.")
    dong.append(f"Vì sao bạn được hỏi lúc này: {ly_do_trigger}.")
    return "\n".join(dong)
