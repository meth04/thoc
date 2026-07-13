"""Prompt builder tiếng Việt (SPEC 4.6, Phụ lục A) — mô tả thế giới SINH TỪ TRẠNG THÁI THẬT.

Mock không đọc prompt (dùng ctx), nhưng prompt vẫn được build + log để (a) Phase 7 dùng
ngay, (b) llm_calls có tok_in trung thực.
"""

from __future__ import annotations

from engine.world import World

# Mẫu hợp đồng khởi đầu: tên mô-típ (config hop_dong.mau_khoi_dau) → JSON minh họa.
# Config rỗng → prompt không có mẫu mồi nào (điều kiện phản chứng C1).
MAU_KHOI_DAU_THEO_TEN: dict[str, str] = {
    # đổi công lấy thóc, trả trọn một lần khi ký — trao đổi nguyên thủy
    "doi_cong_lay_thoc_mot_lan":
        '{"cac_ben":["A","B"],"hinh_thuc":"mieng","thoi_han":1,"dieu_khoan":[{"loai":"gop_cong",'
        '"tu":"A","den":"B","so_cong_moi_tick":60},{"loai":"chuyen_giao_mot_lan","tu":"B",'
        '"den":"A","tai_san":"thoc","so_luong":240,"tai":"ky_ket"}]}',
    # cho mượn có hoàn trả — mượn bao nhiêu trả bấy nhiêu (điều kiện khác là chuyện mặc cả)
    "cho_muon_co_hoan_tra":
        '{"cac_ben":["A","B"],"hinh_thuc":"mieng","thoi_han":4,"dieu_khoan":[{"loai":'
        '"chuyen_giao_mot_lan","tu":"A","den":"B","tai_san":"thoc","so_luong":200,"tai":"ky_ket"},'
        '{"loai":"chuyen_giao_mot_lan","tu":"B","den":"A","tai_san":"thoc","so_luong":200,'
        '"tai":"dao_han"}]}',
}


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
        ten_mau = w.cfg.get("hop_dong.mau_khoi_dau", []) or []
        mau = [MAU_KHOI_DAU_THEO_TEN[t] for t in ten_mau if t in MAU_KHOI_DAU_THEO_TEN]
    return mau


def mo_ta_the_gioi(w: World) -> str:
    """Khối mô tả thế giới sinh động từ trạng thái thật — KHÔNG gán nhãn bối cảnh dựng sẵn."""
    # lọc tài sản kỹ thuật nội bộ (vi_the:* là vị thế hợp đồng — không phải của cải,
    # phơi ra là lộ mọi cặp bên hợp đồng toàn thế giới)
    tai_san_ton_tai = sorted(
        ts for ts in w.ledger.cac_tai_san() - {"cong"} if not ts.startswith("vi_the:")
    )
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
        f"năm {w.nam()}. Tính cách (1-9): {a.persona.as_dict()}. "
        f"Gia huấn: \"{a.gia_huan or '(chưa có)'}\". Hồi ký: {a.hoi_ky or '(trống)'}. "
        f"Thế giới bạn biết: {mo_ta_the_gioi(w)} Bạn chỉ biết những gì làng bạn biết. "
        f"Hãy quyết định như CHÍNH BẠN, nhất quán với tính cách và ký ức riêng, kể cả khi "
        f"khác mọi người. Chỉ trả về DUY NHẤT một JSON đúng schema: {schema_str}"
    )


def build_user_chung(w: World) -> str:
    loai_tt, he_so = w.thoi_tiet(w.tick)
    gia = {ts: w.gia_gan_nhat(ts) for ts in ("go", "cong_cu", "dat")}
    gia_str = ", ".join(f"{ts}: {g:.0f} thóc" for ts, g in gia.items() if g)
    if not gia_str:
        gia_str = ("chưa có phiên chợ nào — ai rao trước người ấy định giá "
                   "(dat_lenh sẽ khớp khi có người mua-bán gặp giá nhau)")
    so_rao = len(w.bang_rao)
    mau = mau_hop_dong_luu_hanh(w, int(w.cfg.get("minds.mau_hop_dong_trong_prompt_top_k")))
    # môi trường tự nhiên — agent nhìn sông, nhìn đất mà liệu kế sinh nhai
    from engine.world import _ca_suc_chua

    suc_chua = _ca_suc_chua(w)
    mat_do_ca = (float(getattr(w, "ca_ton", suc_chua)) / suc_chua) if suc_chua > 0 else 0.0
    ta_song = ("sông đầy cá" if mat_do_ca > 0.6 else
               "cá sông thưa dần" if mat_do_ca > 0.3 else
               "sông gần cạn cá — đánh cả buổi được vài con")
    dat_cong_con = sum(1 for p in w.parcels.values() if p.loai == "ruong" and p.chu is None)
    dan_song = sum(1 for a in w.agents.values() if a.con_song)
    mua_hien = w.mua()
    ten_mua = {
        "lua": "mưa / lúa",
        "lua_1": "lúa vụ 1",
        "lua_2": "lúa vụ 2",
        "dong": "đông",
        "kho": "khô",
    }.get(mua_hien, mua_hien)
    vu_dong = ""
    if bool(w.cfg.get("khong_gian.vu_dong.bat", False)) and mua_hien == "dong":
        crops = w.cfg.get("khong_gian.vu_dong.cay", {})
        chi_tiet = ", ".join(
            f"{name} ({float(spec['cong']):.0f} công → ~{float(spec['san_luong_kg']):.0f}kg)"
            for name, spec in sorted(crops.items())
        )
        vu_dong = f" Vụ đông đang mở: bạn có thể trồng {chi_tiet} trên ruộng hợp lệ."
    return (
        f"[TÌNH HÌNH CHUNG] Mùa {ten_mua}, thời tiết {loai_tt} "
        f"(hệ số {he_so}). Làng có {dan_song} nhân khẩu; đất công chưa ai khai hoang "
        f"còn {dat_cong_con} thửa; {ta_song}. "
        f"Giá chợ gần nhất: {gia_str or 'chưa có phiên nào'}. {vu_dong}"
        f"Bảng rao có {so_rao} đề nghị.{_tinh_hinh_viec_lang(w)} "
        f"[CÁC DẠNG THỎA THUẬN ĐANG LƯU HÀNH] {mau if mau else '(chưa từng có thỏa thuận nào)'} "
        f"[BẠN CÓ THỂ] đề nghị/trả lời hợp đồng (văn phạm 9 điều khoản: chuyen_giao_dinh_ky, "
        f"chuyen_giao_mot_lan, quyen_su_dung, gop_cong, chia_san_luong, chia_loi_nhuan, "
        f"dieu_kien_su_kien, hoan_tra_theo_yeu_cau, khi_pha_vo), lap_phap_nhan, dat_lenh "
        f"mua/bán mọi tài sản, niem_yet/tra_gia_dat, phan_bo_cong, khai_hoang, canh_vu_dong, "
        f"cham_tre, xay, "
        f"nghien_cuu, buon_chuyen, cau_hon, viet_di_chuc, di_cu, ung_cu, bo_phieu."
    )


def _tinh_hinh_viec_lang(w: World) -> str:
    """Trạng thái nhà nước làng (Trưởng làng, thuế, lương tối thiểu, ứng viên) — thuần dữ
    kiện, sinh từ w.chinh_quyen nếu định chế chính trị đã tồn tại (getattr an toàn)."""
    cq = getattr(w, "chinh_quyen", None)
    if cq is None:
        return ""
    truong = getattr(cq, "truong_lang", None)
    ten_truong = (f"{w.agents[truong].ten} ({truong})"
                  if truong and truong in w.agents else "chưa bầu ai")
    thue = float(getattr(cq, "thue_suat", 0.0) or 0.0)
    luong = float(getattr(cq, "luong_toi_thieu", 0.0) or 0.0)
    phieu = getattr(cq, "phieu", None)
    ung_vien = sorted(phieu) if isinstance(phieu, dict) and phieu else []
    s = (f" [VIỆC LÀNG] Trưởng làng đương nhiệm: {ten_truong}; thuế thu hoạch {thue:.0%} "
         f"nộp công quỹ chia đều lại; lương tối thiểu {luong:.1f} thóc/công.")
    if ung_vien:
        s += f" Người đang ứng cử: {ung_vien}."
    return s


SCHEMA_DAU = """[ĐỊNH DẠNG TRẢ LỜI — BẮT BUỘC]
Trả về DUY NHẤT JSON (không lời dẫn, không markdown). Quyết định của một người có dạng:
{"id":"A0001","the_chinh_sach":{...tùy chọn},"hanh_dong":[...],"ly_do":"1 câu"}.
Không hành động gì thì để "hanh_dong":[]. Quyết định ĐỘC LẬP theo tính cách riêng của bạn.

the_chinh_sach (thói quen tự chạy khi bạn không được hỏi — chỉ ghi trường muốn đổi):
{"du_tru_muc_tieu":2.5,"canh_toi_da":3,"khai_go_khi_ranh":true,"hoc_khi_du_an":false,
 "day_con":true,"y_dinh_sinh_con":0|0.5|1,"nhan_lam_cong_gia_toi_thieu":3.5,
 "nhan_gui_thoc":false,"ban_go_nguong":4,"mua_cong_cu_khi_hong":true,"nguong_rao_dat":0.3,
 "phung_duong_cha_me":true,"du_dinh":"mục tiêu dài hạn của bạn, ≤200 chữ"}

hanh_dong hợp lệ (loai + tham số, thứ tự liệt kê không mang ý nghĩa gì):"""

# Danh mục hành động — mỗi phần tử một mục; thứ tự được XÁO theo seed×tick khi ghép
# prompt (schema_quyet_dinh) để không mớm ưu tiên qua vị trí liệt kê.
MUC_HANH_DONG: list[str] = [
    '- {"loai":"phan_bo_cong","canh_thua":["P15_04"],"khai_go_cong":60,"khai_quang_cong":0,\n'
    '   "hoc":true,"day_cho":["A0012"]}   (canh thửa mình/thửa công/thửa có quyền dùng)',
    '- {"loai":"xay","mon":"nha"|"che_tac"|"may"|"xu"|"<mã hàng mới>","so_luong":1}',
    '- {"loai":"canh_vu_dong","thua":"P15_04","cay":"ngo"|"khoai"}  (chỉ khi mùa khô '
    'và scenario cho phép; mỗi thửa một cây)',
    '- {"loai":"cham_tre","tre":"A0012"}  (tự nguyện dùng công trông một trẻ; có thể là '
    'người thân hoặc người đã nhận hợp đồng góp công của cha/mẹ)',
    '- {"loai":"de_nghi_hop_dong","den":"A0031"|null,"hop_dong":{"cac_ben":["<id bạn>","?"],\n'
    '   "hinh_thuc":"mieng"|"van_ban","thoi_han":8,"the_chap":["thua:P15_04"],"dieu_khoan":[...]}}\n'
    '  ("?" = bên chưa biết, người nhận lời sẽ thế chỗ; bạn PHẢI là một bên; văn bản cần E1)',
    '- {"loai":"tra_loi_hop_dong","ref":"DN00012","tra_loi":"chap_nhan"|"tu_choi"}',
    '- {"loai":"dat_lenh","chieu":"mua"|"ban","tai_san":"go|cong_cu|quang_dong|xu|nha|thoc|\n'
    '   co_phan:E0001|<mã hàng>","sl":4,"gia":12.5,"thanh_toan":"thoc"}',
    '- {"loai":"niem_yet","tai_san":"thua:P15_04","gia":600}   (rao bán đất của mình)',
    '- {"loai":"tra_gia_dat","thua":"P15_04","gia":650}        (trả giá đất đang niêm yết)',
    '- {"loai":"yeu_cau_hoan_tra","ref":"HD00007","so_luong":200}  (rút từ hợp đồng gửi)',
    '- {"loai":"nghien_cuu","linh_vuc":"nong_nghiep|cong_cu_may_moc|luu_kho|van_chuyen|y_te|\n'
    '   vat_lieu|che_bien","cong":60,"thoc":50}',
    '- {"loai":"lap_phap_nhan","ten":"...","co_phan":{"<id bạn>":100},\n'
    '   "von_gop":{"<id bạn>":{"thoc":1500}}}   (vốn góp chỉ từ túi bạn)',
    '- {"loai":"quyet_dinh_entity","entity":"E0001","hanh_dong_con":[<các hành động trên>]}',
    '- {"loai":"cau_hon","den":"A0042"} · {"loai":"tra_loi_cau_hon","cua":"A0042","dong_y":true}',
    '- {"loai":"viet_di_chuc","phan_bo":{"A0051":60,"A0052":40},"gia_huan":"≤100 từ"}',
    '- {"loai":"di_cu"} · {"loai":"don_phuong_pha_vo","ref":"HD00003"}',
    '- {"loai":"chan_nuoi","bat_ga_cong":60,"giet_ga":2}  (bắt gà rừng / giết gà lấy thịt)',
    '- {"loai":"bieu","den":"A0002","tai_san":"thoc","so_luong":90}  (biếu tặng — không cần\n'
    '  hợp đồng)',
    '- {"loai":"danh_ca","cong":120}  (đánh cá trên sông)',
    '- {"loai":"mo_tiec","thoc":150,"thit":10}  (mở tiệc mời hàng xóm)',
    '- {"loai":"trom","muc_tieu":"A0002","tai_san":"thoc","so_luong":100}  (lấy trộm —\n'
    '  hơn nửa số lần bị bắt quả tang)',
    '- {"loai":"nhan_tin","den":"A0002","noi_dung":"..."}  (nhắn riêng 1 người: mặc cả giá,\n'
    '  hỏi mua, rủ hùn hạp, vận động... — họ đọc được ở lượt sau và có thể nhắn lại)',
    # ---- việc làng: bầu bán, thuế khóa, đấu tranh (mọi thứ tự phát từ ý dân) ----
    '- {"loai":"ung_cu"}  (tự ra ứng cử làm Trưởng làng ở kỳ bầu tới)',
    '- {"loai":"bo_phieu","cho":"A0001"}  (bỏ lá phiếu cho một người đang ứng cử Trưởng làng)',
    '- {"loai":"ban_hanh_luat","luat":{"loai":"thue","suat":0.1}}  hoặc\n'
    '  {"loai":"ban_hanh_luat","luat":{"loai":"luong_toi_thieu","muc":2.0}}\n'
    '  (chỉ Trưởng làng đương nhiệm: đặt thuế suất trên thu hoạch nộp vào công quỹ, hoặc\n'
    '   mức lương tối thiểu cho mỗi công làm thuê)',
    '- {"loai":"hoi_lo","den":"A0001","thoc":100}  (đưa riêng thóc cho một người để đổi lấy\n'
    '  lá phiếu hoặc ân huệ — người kia nhận hay không là tùy họ)',
    '- {"loai":"nghiep_doan","gia_nhap":true}  (gia nhập nhóm người làm công cùng thương\n'
    '  lượng điều kiện; đặt false để rời nhóm)',
    '- {"loai":"dinh_cong"}  (ngừng góp công theo giao kèo làm thuê để gây sức ép)',
    '- {"loai":"bao_dong"}  (cùng nhiều người nổi dậy sung công của cải nhà giàu chia lại —\n'
    '  chỉ diễn ra được khi bất bình đẳng cực đoan và đủ đông người cùng nổi dậy)',
    '- {"loai":"keu_goi","noi_dung":"..."}  (nói trước cả làng ở buổi họp — lời vận động\n'
    '  thuần, tự nó không dịch chuyển của cải)',
]

VAN_PHAM_CLAUSE = """Văn phạm dieu_khoan (9 loại — ghép tự do thành mọi kiểu thỏa thuận):
chuyen_giao_dinh_ky{tu,den,tai_san,so_luong,moi_n_tick} ·
chuyen_giao_mot_lan{tu,den,tai_san,so_luong,tai:"ky_ket"|"dao_han"} ·
quyen_su_dung{tai_san:"thua:P.."|"blueprint:BP..",tu,den} · gop_cong{tu,den,so_cong_moi_tick} ·
chia_san_luong{nguon:"thua:P..",ty_le:0.4,den} ·
dieu_kien_su_kien{neu:{"loai":"han_lu"},thi:<chuyen_giao_*>} ·
hoan_tra_theo_yeu_cau{tu,den,tai_san,tran_rut_moi_tick} ·
khi_pha_vo{phat:"xiet_the_chap"|"khong"} · chia_loi_nhuan{entity,theo_co_phan:true}"""


def schema_quyet_dinh(muc_hanh_dong: list[str] | None = None) -> str:
    """Ghép schema quyết định; truyền danh mục hành động đã xáo để chống thiên vị vị trí."""
    muc = MUC_HANH_DONG if muc_hanh_dong is None else muc_hanh_dong
    return SCHEMA_DAU + "\n" + "\n".join(muc) + "\n\n" + VAN_PHAM_CLAUSE


# Bản thứ tự chuẩn (không xáo) — dùng cho call dịch intent lạ (minds/real.py).
SCHEMA_QUYET_DINH = schema_quyet_dinh()


LUAT_VAT_LY = """[LUẬT VẬT LÝ — không ai thoát được]
- Mỗi tick = 6 tháng. Người lớn PHẢI ăn 90kg thóc/tick (trẻ em 45kg) — thiếu ăn là mất
  sức khỏe, sức khỏe cạn là CHẾT. Không ai phát chẩn cho bạn.
- Kho thóc hao 3%/tick (mọt, chuột). Mỗi tick bạn có 180 ngày công (theo sức khỏe).
- MÙA MƯA (tick lẻ): gieo + gặt lúa cùng tick. Mỗi thửa cần 60kg thóc giống + 60 công,
  thu ~650kg × màu mỡ. Tự canh tối đa 3 thửa (thửa 2-3 kém dần). MÙA KHÔ (tick chẵn):
  nếu scenario mở vụ đông thì có thể trồng ngô HOẶC khoai (công/sản lượng ghi trong tình hình
  mùa); nếu không, dành cho khai thác gỗ/quặng, chế tác, xây, học, hôn sự.
- Canh CÙNG MỘT thửa đất công 2 mùa mưa liên tiếp → thửa đó thành CỦA BẠN (khai hoang).
- Nhà = 8 gỗ + 240 CÔNG (không nhà → mất sức mùa mưa). Một người chỉ có 180 công/tick
  — KHÔNG AI tự dựng nổi nhà một mình trong một mùa: cần người góp công (vợ/chồng,
  con lớn gop_cong_cho, hoặc thuê thợ bằng hợp đồng gop_cong), hoặc mua nhà có sẵn.
  Công cụ = 2 gỗ + 60 công (+30% năng suất, mòn dần). Gỗ ~10 công/cây, quặng ~20 công.
- Đời người hữu hạn (già là chết). KHÔNG kết hôn thì không con cái — của cải về công,
  dòng họ tuyệt tự. Cầu hôn ở mùa nào cũng được; người kia trả lời tick sau.
- CHĂN NUÔI cần THỜI GIAN: bắt gà rừng được GÀ CON (30 công/con, làng có rừng); gà
  đẻ ra cũng là gà con. Gà con nuôi 1 tick (6 tháng) mới thành gà lớn — chưa đẻ,
  giết non chỉ được 3kg thịt. Gà lớn ăn 2kg thóc/tick (gà con 1kg), no đủ thì đàn
  đẻ +15%/tick. Giết 1 gà lớn → 8kg thịt (1kg thịt no bằng 3kg thóc); thịt ôi nhanh
  (hao 20%/tick), gà sống thì không hao.
- TUỔI TÁC: trẻ dưới 15 KHÔNG làm đồng (đi học thì được — hoc/day_cho). Từ 15 tuổi
  phụ giúp được 30% sức. Quá 60 tuổi sức yếu dần (nửa công, hao sức mỗi tick), quá 70
  gần như nghỉ hẳn — người già không còn tự kiếm ăn được, không có thóc là đói.
- CHỮ NGHĨA: học nâng bậc chữ E từng bậc một (tự học mất gấp đôi thời gian so với có
  người biết chữ day_cho). Hợp đồng MIỆNG ai cũng lập được; hợp đồng VĂN BẢN — loại
  duy nhất kèm được thế chấp và cưỡng chế khi phá vỡ — chỉ người biết chữ (E1 trở
  lên) soạn được.
- SINH NỞ có rủi ro cho sản phụ; rủi ro chỉ giảm khi hộ sản phụ CÓ HỢP ĐỒNG hiệu lực
  với người nắm bí quyết y_te (giá cả, điều khoản do hai bên tự thỏa thuận).
- ĐẤT BẠC MÀU: canh cùng một thửa liên tục thì độ màu giảm 2%/vụ (chạm đáy ở nửa độ
  màu gốc); BỎ HOANG thì độ màu hồi dần.
- TAY NGHỀ: mỗi vụ trực tiếp canh tác, kinh nghiệm đồng áng tăng dần (tối đa +20%
  năng suất) — lão nông tri điền gặt nhiều hơn tay mơ trên cùng một thửa.
- ĐÁNH CÁ: sông là CỦA CHUNG, không cần ruộng, mùa nào cũng được — sông đầy cá thì
  ~4.5 công/kg; đàn cá là TÀI NGUYÊN TÁI TẠO CÓ HẠN: đánh quá tay thì cá thưa dần,
  cùng buổi công bắt được ít hẳn đi, và trữ lượng phải NHIỀU NĂM mới hồi. 1kg cá no
  bằng 2.5kg thóc, cá ươn nhanh (hao 15%/tick).
- TIỆC KHAO XÓM: bỏ ra ≥60kg (thóc/thịt quy đổi) mời hàng xóm — của cải mất đi,
  những người đến dự thêm quý mến người mở tiệc.
- TRỘM CẮP: về mặt vật lý KHÔNG gì ngăn bạn lấy trộm (được thì ~1/4 kho người ta),
  nhưng hơn nửa số lần sẽ BỊ BẮT QUẢ TANG — nạn nhân thù, cả xóm coi khinh. Làng
  KHÔNG có tuần đinh hay hình phạt dựng sẵn nào.
- TRẺ MỒ CÔI cả cha lẫn mẹ được thân nhân gần nhất (hoặc một hàng xóm) cưu mang,
  ăn chung nồi cơm nhà người nuôi — nhà cưu mang có thêm một miệng ăn.
- VIỆC LÀNG: cứ định kỳ cả làng bầu một Trưởng làng bằng lá phiếu — ai cũng có thể tự
  ứng cử hoặc bỏ phiếu. Trưởng làng đương nhiệm được ban thuế suất trên thu hoạch và mức
  lương tối thiểu cho công làm thuê. Thuế thu vào CÔNG QUỸ chung rồi chia đều lại cho cả
  làng. Khi chênh lệch giàu nghèo (hệ số Gini) vượt ngưỡng VÀ đủ đông người cùng bạo động,
  một phần của cải nhà giàu bị sung công chia lại cho người nghèo. Người làm công có thể
  lập nghiệp đoàn và đình công để gây sức ép. Ngoài những gì dân tự lập ra, làng KHÔNG có
  sẵn nhà nước, luật lệ hay lực lượng cưỡng chế nào.

[BẠN LÀ NGƯỜI SỐNG] Bạn có nhu cầu như mọi con người: no bụng hôm nay; an toàn ngày
mai (dự trữ, nhà cửa); gia đình (dựng vợ gả chồng, con cái, cha mẹ già, để lại gia
sản); và vị thế (đất đai, của cải, chữ nghĩa, tiếng thơm). Nặng nhẹ ra sao
là tùy TÍNH CÁCH bạn. Muốn có con: đặt y_dinh_sinh_con (0/0.5/1) trong the_chinh_sach."""

VI_DU_QUYET_DINH = """[VÍ DỤ ĐỊNH DẠNG một quyết định — hoàn cảnh mỗi người mỗi khác, quyết theo hoàn cảnh CỦA BẠN]
{"id":"A0017","hanh_dong":[{"loai":"phan_bo_cong","canh_thua":["P14_25","P14_26"]},
{"loai":"de_nghi_hop_dong","den":"A0031","hop_dong":{"cac_ben":["A0017","A0031"],
"hinh_thuc":"mieng","thoi_han":8,"dieu_khoan":[{"loai":"quyen_su_dung","tai_san":"thua:P15_02",
"tu":"A0017","den":"A0031"},{"loai":"chia_san_luong","nguon":"thua:P15_02","ty_le":0.4,
"den":"A0017"}]}},{"loai":"cau_hon","den":"A0042"}],
"ly_do":"Canh 2 thửa đủ ăn, thửa xa cho cấy rẽ lấy 4 phần, và đến tuổi phải tính chuyện gia đình."}"""


def build_agent_prompt(w: World, aid: str, triggers: dict[str, list[str]]) -> str:
    """Prompt 1-to-1 (PART 5.1): CHỈ khối riêng của MỘT agent — bất đối xứng thông tin
    tuyệt đối (call này không chứa ví/ý định của ai khác). Luật vật lý + tình hình chung
    dùng chung (nên bọc vào context-cache khi gọi thật để khỏi gửi lặp)."""
    dau = (
        "Bạn là người dưới đây trong một làng khép kín (1 tick = 6 tháng). Bạn chỉ biết "
        "những gì cả làng đều biết và những gì của RIÊNG bạn — KHÔNG biết ví tiền hay ý "
        "định của người khác. Quyết định như CHÍNH BẠN, nhất quán với tính cách, ký ức, "
        "gia huấn riêng, kể cả khi khác số đông. Đơn vị giá trị: kg thóc.\n\n"
    )
    chung = build_user_chung(w)
    rieng = build_user_rieng(w, aid, triggers.get(aid, []))
    # xáo danh mục hành động theo seed×(agent,tick) — chống thiên vị vị trí, vẫn tất định
    g_menu = w.rng.get(f"menu_xao:{aid}", w.tick)
    muc_xao = [MUC_HANH_DONG[i] for i in g_menu.permutation(len(MUC_HANH_DONG))]
    return f"{dau}{LUAT_VAT_LY}\n\n{chung}\n\n{rieng}\n\n{schema_quyet_dinh(muc_xao)}\n\n" \
           f"{VI_DU_QUYET_DINH}\n" \
           f'Trả về DUY NHẤT một JSON object cho chính bạn (id "{aid}"): ' \
           f'{{"id":"{aid}","hanh_dong":[...],"ly_do":"1 câu"}}.'


def _mo_ta_clause(ck, aid: str) -> str:
    """Việt hóa một điều khoản để người nhận đọc hiểu được mình cam kết gì."""

    def ten(x: str) -> str:
        return "BẠN" if x in ("?", aid) else x

    loai = ck.loai
    if loai == "chuyen_giao_dinh_ky":
        return (f"{ten(ck.tu)} trả {ten(ck.den)} {ck.so_luong:.0f} {ck.tai_san} "
                f"mỗi {ck.moi_n_tick} tick")
    if loai == "chuyen_giao_mot_lan":
        luc = {"ky_ket": "ngay khi ký", "dao_han": "khi đáo hạn"}.get(ck.tai, ck.tai)
        return f"{ten(ck.tu)} trao {ten(ck.den)} {ck.so_luong:.0f} {ck.tai_san} {luc}"
    if loai == "quyen_su_dung":
        return f"{ten(ck.den)} được quyền dùng {ck.tai_san} của {ten(ck.tu)}"
    if loai == "gop_cong":
        return f"{ten(ck.tu)} góp {ck.so_cong_moi_tick:.0f} công/tick cho {ten(ck.den)}"
    if loai == "chia_san_luong":
        return f"{ten(ck.den)} nhận {ck.ty_le:.0%} sản lượng từ {ck.nguon}"
    if loai == "dieu_kien_su_kien":
        return f"nếu {ck.neu.get('loai')} thì {_mo_ta_clause(ck.thi, aid)}"
    if loai == "hoan_tra_theo_yeu_cau":
        return (f"{ten(ck.den)} được rút lại {ck.tai_san} từ {ten(ck.tu)} bất kỳ lúc nào "
                f"(tối đa {ck.tran_rut_moi_tick:.0f}/tick)")
    if loai == "khi_pha_vo":
        return f"phá vỡ thì {ck.phat}"
    if loai == "chia_loi_nhuan":
        return f"chia lợi nhuận {ck.entity} theo cổ phần"
    return loai


# Nhãn giai cấp (observatory) → cụm danh xưng tiếng Việt cho câu CĂN TÍNH ở đầu khối riêng.
# Chỉ là DỮ KIỆN về thân phận hiện thời (không phải bẩm sinh, không phải lời khuyên);
# danh xưng dùng mô tả hoạt động, không gắn tên định chế có sẵn.
GIAI_CAP_VN: dict[str, str] = {
    "phu_thuoc": "người sống lệ thuộc",
    "vo_gia_cu": "kẻ không nhà",
    "chu_xuong": "chủ cơ sở làm ăn",
    "dia_chu": "địa chủ",
    "phu_nong": "phú nông",
    "thuong_nhan": "thương nhân",
    "tho_thu_cong": "thợ thủ công",
    "gioi_dich_vu": "người làm nghề dịch vụ",
    "cong_nhan": "người làm công",
    "ta_dien": "tá điền",
    "co_nong": "cố nông",
    "trung_nong": "trung nông",
}

# Cap hiển thị trong prompt riêng — chống phình prompt khi tài sản/giao kèo tích lũy.
HD_HIEN_TOI_DA = 10       # giao kèo liệt kê chi tiết (ưu tiên sắp đáo hạn), dư thì đếm gộp
DAT_HIEN_TOI_DA = 8       # thửa đất liệt kê chi tiết, dư thì tóm tắt
QUAN_HE_DUONG_TOI_DA = 4  # số mối thân thiết hiện trong THÂN QUEN & ÂN OÁN
QUAN_HE_AM_TOI_DA = 3     # số mối hiềm khích hiện trong THÂN QUEN & ÂN OÁN


def _cau_can_tinh(w: World, a) -> str:
    """Câu CĂN TÍNH GIAI CẤP mở đầu khối riêng — rút TỪ SỰ KIỆN: nhãn giai cấp hiện thời
    (nếu observatory đã phân loại vào w.phan_loai), tuổi, và tối đa 2 dấu mốc đời nặng nhất
    từ ky_uc_doi. Thuần dữ kiện đời người, KHÔNG lời khuyên (giữ check.md P4)."""
    phan_loai = getattr(w, "phan_loai", None)
    nhan = None
    if isinstance(phan_loai, dict):
        nhan = GIAI_CAP_VN.get(phan_loai.get(a.id))
    than_phan = nhan or "dân làng"
    cau = f"Bạn là {than_phan} {a.tuoi_nam:.0f} tuổi"
    bien_co = list(a.ky_uc_doi)[-2:] if a.ky_uc_doi else []
    if bien_co:
        cau += "; đời bạn từng trải: " + "; ".join(bien_co)
    return cau + "."


def build_user_rieng(w: World, aid: str, ly_do_trigger: list[str]) -> str:
    a = w.agents[aid]
    tai_san = w.ledger.tai_san_cua(aid)
    tai_san_str = ", ".join(
        f"{ts}: {sl:.0f}" for ts, sl in sorted(tai_san.items())
        if not ts.startswith("vi_the:")
    )
    # độ màu từng thửa — nhìn là biết thửa nào đang bạc màu; nhiều thửa thì tóm tắt
    dat_hien = [
        f"{p.id}(màu {p.mau_mo:.2f}"
        + (", ĐANG BẠC MÀU" if p.mau_mo_goc > 0 and p.mau_mo < p.mau_mo_goc * 0.8 else "")
        + ")"
        for p in sorted((q for q in w.parcels.values() if q.chu == aid), key=lambda q: q.id)
    ]
    if len(dat_hien) > DAT_HIEN_TOI_DA:
        con_lai = dat_hien[DAT_HIEN_TOI_DA:]
        so_bac_mau = sum(1 for m in con_lai if "ĐANG BẠC MÀU" in m)
        dat_hien = dat_hien[:DAT_HIEN_TOI_DA] + [
            f"… và {len(con_lai)} thửa nữa ({so_bac_mau} thửa trong đó đang bạc màu)"
        ]
    # giao kèo hiệu lực — ưu tiên sắp đáo hạn, vô thời hạn xếp sau, dư thì đếm gộp
    hd_hieu_luc = sorted(
        (h for h in w.hop_dong.values()
         if h.trang_thai == "hieu_luc" and aid in h.cac_ben),
        key=lambda h: (h.thoi_han is None,
                       (h.tick_ky + h.thoi_han - w.tick) if h.thoi_han is not None else 0,
                       h.id),
    )
    hd_cua = []
    for h in hd_hieu_luc[:HD_HIEN_TOI_DA]:
        dk = "; ".join(_mo_ta_clause(c, aid) for c in h.dieu_khoan)
        han = f"hạn {h.thoi_han} tick" if h.thoi_han is not None else "không thời hạn"
        hd_cua.append(f"{h.id}: {dk} ({han})")
    if len(hd_hieu_luc) > HD_HIEN_TOI_DA:
        hd_cua.append(f"… và {len(hd_hieu_luc) - HD_HIEN_TOI_DA} giao kèo nữa")
    rao_cho_toi = []
    for dn in sorted(w.bang_rao.values(), key=lambda d: d.id):
        if dn.tu == aid:
            continue
        # đề nghị công khai chỉ nghe được trong CÙNG LÀNG (pháp nhân không thuộc làng
        # nào — rao của nó vang khắp vùng); đề nghị đích danh thì luôn tới tay
        nguoi_rao = w.agents.get(dn.tu)
        cong_khai_nghe_duoc = dn.den is None and (
            nguoi_rao is None or nguoi_rao.lang == a.lang)
        if dn.den == aid or cong_khai_nghe_duoc:
            dk = "; ".join(_mo_ta_clause(c, aid) for c in dn.hd.dieu_khoan)
            rao_cho_toi.append(f"{dn.id} (từ {dn.tu}): {dk}")
    rao_cho_toi = rao_cho_toi[:8]
    dang_treo_cua_toi = [
        f"{dn.id}" for dn in w.bang_rao.values() if dn.tu == aid
    ]
    # gia đình — vợ/chồng, con cái, CHA MẸ GIÀ (tên + tuổi, đọc là hiểu cảnh nhà)
    vo_chong = a.vo_chong if a.vo_chong and w.agents.get(a.vo_chong, None) else None
    con_song = [c for c in a.con if c in w.agents and w.agents[c].con_song]
    gia_dinh = []
    if vo_chong:
        vc = w.agents[vo_chong]
        gia_dinh.append(f"vợ/chồng: {vc.ten} ({vo_chong}, {vc.tuoi_nam:.0f} tuổi)")
    if con_song:
        gia_dinh.append("con: " + ", ".join(
            f"{w.agents[c].ten} ({c}, {w.agents[c].tuoi_nam:.0f}t)" for c in con_song))
    cha_me_gia = [
        p for p in (a.cha, a.me)
        if p and p in w.agents and w.agents[p].con_song
    ]
    if cha_me_gia:
        gia_dinh.append("cha mẹ còn sống: " + ", ".join(
            f"{w.agents[p].ten} ({p}, {w.agents[p].tuoi_nam:.0f}t"
            + (", đã già yếu" if w.agents[p].tuoi_nam >= 60 else "") + ")"
            for p in cha_me_gia))
    # cầu hôn đang chờ TÔI trả lời — phải biết ai ngỏ lời thì mới đáp được
    cau_hon_cho_toi = []
    for tu, den, _t in w.cau_hon_cho:
        if den == aid and tu in w.agents and w.agents[tu].con_song:
            nguoi = w.agents[tu]
            gia_san = w.ledger.so_du(tu, "thoc")
            dat_ho = sum(1 for p in w.parcels.values() if p.chu == tu)
            cau_hon_cho_toi.append(
                f"{nguoi.ten} ({tu}, {nguoi.tuoi_nam:.0f} tuổi, {gia_san:.0f}kg thóc, "
                f"{dat_ho} thửa đất) đã NGỎ LỜI CẦU HÔN bạn — đáp bằng "
                f'{{"loai":"tra_loi_cau_hon","cua":"{tu}","dong_y":true/false}}'
            )
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
    tinh_trang = "độc thân" if a.vo_chong is None else "đã có gia đình"
    dong = [
        _cau_can_tinh(w, a),
        f"[NGƯỜI {aid}] {a.ten}, {a.tuoi_nam:.0f} tuổi, {'nữ' if a.gioi_tinh == 'nu' else 'nam'}, "
        f"{tinh_trang}, học vấn E{a.e_bac}, sức khỏe {a.health:.0f}/100. "
        f"Tính cách (1-9): {a.persona.as_dict()}.",
        f"Hồi ký: {a.hoi_ky or '(trống)'} | Gia huấn: \"{a.gia_huan or '(chưa có)'}\"",
        f"Tài sản: {tai_san_str or 'trắng tay'}. Đất của bạn: {dat_hien or 'không có'}.",
    ]
    if a.gia_ky_vong:
        gia_rieng = ", ".join(
            f"{ts}≈{gia:.1f} thóc" for ts, gia in sorted(a.gia_ky_vong.items())
        )
        dong.append("ƯỚC GIÁ RIÊNG (kinh nghiệm của bạn, không phải giá bắt buộc): " + gia_rieng)
    if a.tay_nghe > 1.02:
        dong.append(f"Kinh nghiệm đồng áng: năng suất +{(a.tay_nghe - 1) * 100:.0f}% "
                    f"(tay nghề tích qua từng vụ).")
    if a.ky_uc_doi:
        dong.append("DẤU MỐC ĐỜI BẠN (không bao giờ quên): " + " | ".join(a.ky_uc_doi))
    if a.ky_uc:
        dong.append("CHUYỆN GẦN ĐÂY: " + " | ".join(a.ky_uc[-7:]))
    if a.niem_tin:
        dong.append(f"NIỀM TIN CỐT LÕI CỦA BẠN (đúc từ trải đời): {a.niem_tin}")
    thu = w.hom_thu.get(aid) or []
    if thu:
        dong.append("📨 TIN NHẮN GỬI RIÊNG BẠN (trả lời bằng nhan_tin nếu muốn tiếp chuyện): "
                    + " | ".join(f"{tu} nhắn: \"{noi}\"" for tu, noi, _t in thu[:5]))
    if gia_dinh:
        dong.append("Gia đình: " + "; ".join(gia_dinh) + ".")
    # thân quen & ân oán — trải nghiệm tích lũy của CHÍNH BẠN với từng người còn sống
    # (chỉ mô tả trạng thái, sort tất định theo trọng số rồi id)
    quen: list[tuple[float, str]] = []
    for (x, y), trong_so in w.quan_he.items():
        khac = y if x == aid else x if y == aid else None
        if khac is None or trong_so == 0.0:
            continue
        b = w.agents.get(khac)
        if b is None or not b.con_song:
            continue
        quen.append((trong_so, khac))
    than = sorted((q for q in quen if q[0] > 0),
                  key=lambda q: (-q[0], q[1]))[:QUAN_HE_DUONG_TOI_DA]
    oan = sorted((q for q in quen if q[0] < 0),
                 key=lambda q: (q[0], q[1]))[:QUAN_HE_AM_TOI_DA]
    if than or oan:
        phan = []
        if than:
            phan.append("thân thiết với: " + ", ".join(
                f"{w.agents[i].ten} ({i}, {ts:+.1f})" for ts, i in than))
        if oan:
            phan.append("có hiềm khích với: " + ", ".join(
                f"{w.agents[i].ten} ({i}, {ts:+.1f})" for ts, i in oan))
        dong.append("THÂN QUEN & ÂN OÁN (theo trải nghiệm của riêng bạn, số âm là oán): "
                    + "; ".join(phan) + ".")
    if cau_hon_cho_toi:
        dong.append("💍 " + " ".join(cau_hon_cho_toi))
    if dang_treo_cua_toi:
        dong.append(f"Đề nghị bạn đã rao còn treo (chưa ai nhận): {dang_treo_cua_toi} "
                    f"— rao thêm bản y hệt cũng chỉ nằm cạnh bản cũ.")
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
    # cảnh báo đói: dự trữ hộ so với miệng ăn
    ho = w.ho_cua(aid)
    nc = w.cfg.raw()["nhu_cau"]
    from engine.economy import household_food_equivalent

    thoc_ho = sum(w.ledger.so_du(m, "thoc") for m in ho)
    food_ho = household_food_equivalent(w, ho)
    nhu_cau = sum(
        nc["nguoi_lon_kg_tick"] if w.agents[m].truong_thanh(16) else nc["tre_em_kg_tick"]
        for m in ho
    )
    if nhu_cau > 0 and food_ho < nhu_cau * 2:
        so_tick = food_ho / nhu_cau
        dong.append(
            f"⚠ NGUY CƠ ĐÓI: nhà bạn {len(ho)} miệng ăn cần {nhu_cau:.0f}kg thóc/tick, "
            f"kho lương thực quy thóc còn {food_ho:.0f}kg (trong đó thóc {thoc_ho:.0f}kg) "
            f"— đủ ăn ~{so_tick:.1f} tick nữa."
        )
    # hàng xóm quanh nhà — biết ƯỚC LƯỢNG tài sản của nhau (nhiễu ±30%, không biết
    # chính xác; thóc trong kho chỉ đoán mờ qua nếp sống)
    hang_xom = w.hang_xom_cua(aid)
    if hang_xom:
        nam_nay = w.nam()
        mo_ta_hx = []
        for hx in hang_xom:
            b = w.agents[hx]
            g_nx = w.rng.get(f"nhin_hx:{aid}:{hx}", nam_nay)
            ga = w.ledger.so_du(hx, "ga")
            ruong = sum(1 for p in w.parcels.values() if p.chu == hx)
            thoc_b = w.ledger.so_du(hx, "thoc")
            nep = ("có vẻ dư dả" if thoc_b > 1500 else
                   "đủ ăn" if thoc_b > 400 else "trông túng bấn")
            chi_tiet = [f"{b.ten} ({hx}, {b.tuoi_nam:.0f}t, {nep}"]
            if ruong:
                chi_tiet.append(f"~{max(1, round(ruong * float(g_nx.uniform(0.7, 1.3))))} thửa ruộng")
            if ga >= 1:
                chi_tiet.append(f"nuôi ~{max(1, round(ga * float(g_nx.uniform(0.7, 1.3))))} con gà")
            if w.ledger.so_du(hx, "may") >= 1:
                chi_tiet.append("có máy")
            mo_ta_hx.append(", ".join(chi_tiet) + ")")
        dong.append("HÀNG XÓM QUANH BẠN (ước chừng qua mắt thấy tai nghe): "
                    + "; ".join(mo_ta_hx) + ".")
    # rao vặt phong thanh từ phiên chợ trước — "muốn mua thì biết tìm đến ai"
    rao_vat = getattr(w, "rao_vat", [])
    if rao_vat:
        g_rv = w.rng.get(f"tin_don:{aid}", w.tick)
        nhieu = float(w.cfg.get("thuong_mai.nhieu_tin_don_gia"))
        # tin đồn chợ chỉ lan trong CÙNG LÀNG (pháp nhân không thuộc làng — nghe khắp vùng)
        tin = [
            f"{ai} {'đang rao bán' if chieu == 'ban' else 'đang hỏi mua'} "
            f"{sl:.0f} {ts} (giá nghe đâu ~{gia * (1 + float(g_rv.uniform(-nhieu, nhieu))):.0f})"
            for ai, chieu, ts, sl, gia in rao_vat
            if ai != aid and (ai not in w.agents or w.agents[ai].lang == a.lang)
        ][:6]
        if tin:
            dong.append("NGHE PHONG THANH Ở CHỢ: " + "; ".join(tin) + ".")
    # dự định dài hạn tự ghi lần trước — sống có mục tiêu, đừng quên mình định làm gì
    the_cu = w.policy_cards.get(aid) or {}
    if the_cu.get("du_dinh"):
        dong.append(f"DỰ ĐỊNH BẠN TỰ GHI LẦN TRƯỚC: “{the_cu['du_dinh']}” — cập nhật "
                    f"bằng the_chinh_sach.du_dinh nếu đổi ý.")
    # phản hồi việc không thành tick trước — builder CHỈ ĐỌC, không xóa;
    # orchestrator xóa su_co sau khi prompt của tick đã build xong
    if a.su_co:
        dong.append(f"Chuyện vừa rồi KHÔNG THÀNH (rút kinh nghiệm): {a.su_co}")
    dong.append(f"Vì sao bạn được hỏi lúc này: {ly_do_trigger}.")
    return "\n".join(dong)
