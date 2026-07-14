"""Prompt builder tiếng Việt (SPEC 4.6, Phụ lục A) — mô tả thế giới SINH TỪ TRẠNG THÁI THẬT.

Mock không đọc prompt (dùng ctx), nhưng prompt vẫn được build + log để (a) Phase 7 dùng
ngay, (b) llm_calls có tok_in trung thực.

ADR 0006 §B (PROMPT-1): mọi luật vật lý trong prompt được RENDER TỪ `World.cfg` đang chạy —
KHÔNG còn hằng số vật lý nào trong module này. Menu hành động + danh sách tài sản được render
từ capability registry (`minds/capabilities.py`) + tài sản thật của thế giới. Vì vậy
`LUAT_VAT_LY`/`MUC_HANH_DONG`/`SCHEMA_QUYET_DINH` (hằng cũ) trở thành HÀM nhận `World`:
`luat_vat_ly(w)`, `muc_hanh_dong(w)`, `schema_quyet_dinh_cho(w)`.
"""

from __future__ import annotations

from engine.world import World
from minds.capabilities import (
    NHAN_NGUYEN_LIEU,
    cay_vu_dong,
    dinh_muc_bat_ga,
    kha_dung_trong,
    lich_mua,
    mua_gieo_cay,
    mua_kho,
    phan_tram,
    so,
)

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


# A-12 (XÓA, 2026-07-13): `mo_ta_the_gioi()` + `build_system()` là DEAD CODE — không caller
# nào trong `engine/`, `minds/`, `tools/`, `tests/`. `build_system` còn phát biểu SAI SỰ THẬT
# ("Mọi trao đổi tính bằng thóc"): `engine.market.Lenh.thanh_toan` nhận MỌI tài sản làm phương
# tiện thanh toán, và `minds.capabilities` (dòng menu `dat_lenh`) nói đúng điều đó. Giữ lại
# một hàm chết nói sai luật thị trường là mồi cho lần copy-paste sau. Prompt đang chạy là
# `build_agent_prompt` (1-to-1) — nó không đi qua hai hàm này.


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
    # [BẠN CÓ THỂ]: tên action lấy TỪ CATALOG, chỉ những action khả dụng trong thế giới này
    # (CAP-3 — không quảng cáo hàng không có). Thứ tự khai báo, không xếp hạng.
    ten_hanh_dong = ", ".join(c.ten for c in kha_dung_trong(w))
    return (
        f"[TÌNH HÌNH CHUNG] Mùa {ten_mua}, thời tiết {loai_tt} "
        f"(hệ số {he_so}). Làng có {dan_song} nhân khẩu; ruộng công chưa có người sở hữu "
        f"còn {dat_cong_con} thửa; {ta_song}. "
        f"Giá chợ gần nhất: {gia_str or 'chưa có phiên nào'}. {vu_dong}"
        f"Bảng rao có {so_rao} đề nghị.{_tinh_hinh_viec_lang(w)} "
        f"[CÁC DẠNG THỎA THUẬN ĐANG LƯU HÀNH] {mau if mau else '(chưa từng có thỏa thuận nào)'} "
        f"[BẠN CÓ THỂ] {ten_hanh_dong} "
        f"(văn phạm hợp đồng 9 điều khoản: chuyen_giao_dinh_ky, chuyen_giao_mot_lan, "
        f"quyen_su_dung, gop_cong, chia_san_luong, chia_loi_nhuan, dieu_kien_su_kien, "
        f"hoan_tra_theo_yeu_cau, khi_pha_vo)."
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

the_chinh_sach là PATCH tùy chọn cho thói quen tự chạy khi bạn không được hỏi:
- bỏ hẳn `the_chinh_sach` để GIỮ nguyên thói quen cũ;
- nếu đổi, chỉ ghi CÁC TRƯỜNG muốn đổi, ví dụ `{"du_tru_muc_tieu":3}` hoặc
  `{"khai_go_khi_ranh":false}`. Đừng chép một object mặc định.
- trường có thể patch: du_tru_muc_tieu (0..20), canh_toi_da (0..10), khai_go_khi_ranh,
  hoc_khi_du_an, day_con, y_dinh_sinh_con (0..1), nhan_lam_cong_gia_toi_thieu,
  nhan_gui_thoc, ban_go_nguong, mua_cong_cu_khi_hong, nguong_rao_dat,
  phung_duong_cha_me, an_toan_sinh_ton, du_dinh (≤200 chữ). Để bỏ một ngưỡng có thể null,
  dùng `{"bo_nguong":["ban_go_nguong"]}` hoặc `{"bo_nguong":["nguong_rao_dat"]}`.

hanh_dong hợp lệ (loai + tham số, thứ tự liệt kê không mang ý nghĩa gì):"""

def muc_hanh_dong(w: World) -> list[str]:
    """Danh mục hành động — RENDER TỪ CATALOG, chỉ action `kha_dung(w)` (CAP-3).

    Mỗi phần tử một mục; thứ tự được XÁO theo seed×(agent,tick) khi ghép prompt
    (`build_agent_prompt`) để không mớm ưu tiên qua vị trí liệt kê.
    """
    return [c.mau_prompt(w) for c in kha_dung_trong(w)]


VAN_PHAM_CLAUSE = """Văn phạm dieu_khoan (9 loại — ghép tự do thành mọi kiểu thỏa thuận):
chuyen_giao_dinh_ky{tu,den,tai_san,so_luong,moi_n_tick} ·
chuyen_giao_mot_lan{tu,den,tai_san,so_luong,tai:"ky_ket"|"dao_han"} ·
quyen_su_dung{tai_san:"thua:P.."|"blueprint:BP..",tu,den} · gop_cong{tu,den,so_cong_moi_tick} ·
chia_san_luong{nguon:"thua:P..",ty_le:0.4,den} ·
dieu_kien_su_kien{neu:{"loai":"han_lu"},thi:<chuyen_giao_*>} ·
hoan_tra_theo_yeu_cau{tu,den,tai_san,tran_rut_moi_tick} ·
khi_pha_vo{phat:"xiet_the_chap"|"khong"} · chia_loi_nhuan{entity,theo_co_phan:true}"""


def schema_quyet_dinh_cho(w: World, muc: list[str] | None = None) -> str:
    """Ghép schema quyết định cho thế giới `w`; truyền danh mục đã xáo để chống thiên vị."""
    danh_muc = muc_hanh_dong(w) if muc is None else muc
    return SCHEMA_DAU + "\n" + "\n".join(danh_muc) + "\n\n" + VAN_PHAM_CLAUSE


def _mua_str(cac_mua: tuple[str, ...]) -> str:
    return ", ".join(cac_mua) if cac_mua else "(không có)"


def luat_vat_ly(w: World) -> str:
    """Luật vật lý RENDER TỪ `w.cfg` — không một hằng số vật lý nào nằm trong code này.

    Bảng khóa config: ADR 0006 §B.1. Đoạn nào phụ thuộc cổng scenario (vụ đông, đò, khai
    hoang, chăm trẻ, việc làng) chỉ xuất hiện khi cổng BẬT — nói đúng thế giới đang chạy.
    """
    cfg = w.cfg
    raw = cfg.raw()
    sx, nc, dd = raw["san_xuat"], raw["nhu_cau"], raw["dat_dai"]
    kt, rc = sx["khai_thac"], sx["recipe"]
    lt, cn, dc = raw["lao_dong_theo_tuoi"], raw["chan_nuoi"], raw["danh_ca"]
    thang = so(cfg.get("thoi_gian.thang_moi_tick"))
    cong_tick = float(nc["ngay_cong_moi_tick"])
    mua_lua, mua_k = mua_gieo_cay(w), mua_kho(w)
    hieu_suat = ", ".join(
        f"thửa thứ {i + 2} còn {phan_tram(h)}"
        for i, h in enumerate(sx["hieu_suat_thua_2_3"])
    )
    dong: list[str] = ["[LUẬT VẬT LÝ — không ai thoát được]"]
    dong.append(
        f"- Mỗi tick = {thang} tháng; một năm = {w.tick_moi_nam()} tick. Vòng mùa trong năm: "
        f"{' → '.join(lich_mua(w))}."
    )
    dong.append(
        f"- Người lớn PHẢI ăn {so(nc['nguoi_lon_kg_tick'])}kg thóc/tick (trẻ em "
        f"{so(nc['tre_em_kg_tick'])}kg) — thiếu ăn là mất sức khỏe, sức khỏe cạn là CHẾT. "
        f"Không ai phát chẩn cho bạn."
    )
    dong.append(
        f"- Kho thóc hao {phan_tram(sx['hao_hut_kho_moi_tick'])}/tick (mọt, chuột). Mỗi tick "
        f"bạn có {so(cong_tick)} ngày công (theo sức khỏe)."
    )
    dong.append(
        f"- MÙA LÚA ({_mua_str(mua_lua)}): gieo + gặt lúa cùng tick. Mỗi thửa cần "
        f"{so(sx['giong_kg_moi_thua'])}kg thóc giống + {so(sx['cong_moi_thua'])} công, thu "
        f"~{so(sx['san_luong_goc_kg'])}kg × màu mỡ × thời tiết. Tự canh tối đa "
        f"{so(sx['thua_toi_da_tu_canh'])} thửa ({hieu_suat})."
    )
    cay = cay_vu_dong(w)
    if cay:
        ct = "; ".join(
            f"{ten}: {so(spec['cong'])} công → ~{so(spec['san_luong_kg'])}kg "
            f"(1kg no bằng {so(spec['quy_doi_dinh_duong'])}kg thóc)"
            for ten, spec in cay.items()
        )
        dong.append(
            f"- MÙA KHÔ ({_mua_str(mua_k)}): trồng được một cây vụ đông trên mỗi thửa ruộng "
            f"hợp lệ — {ct}. Mùa khô cũng dành cho khai thác gỗ/quặng, chế tác, xây, học, "
            f"hôn sự."
        )
    else:
        dong.append(
            f"- MÙA KHÔ ({_mua_str(mua_k)}): không gieo lúa được; dành cho khai thác gỗ/quặng, "
            f"chế tác, xây, học, hôn sự."
        )
    dong.append(
        f"- Canh CÙNG MỘT thửa đất công {so(sx['homestead_tick_lien_tiep'])} mùa lúa liên tiếp "
        f"→ thửa đó thành CỦA BẠN."
    )
    nha_cong, nha_go = float(rc["nha"]["cong"]), float(rc["nha"]["go"])
    ct_r = rc["cong_cu"]
    dong_nha = (
        f"- Nhà = {so(nha_go)} gỗ + {so(nha_cong)} CÔNG (không nhà → mất sức mùa lúa)."
    )
    if nha_cong > cong_tick:
        dong_nha += (
            f" Một người chỉ có {so(cong_tick)} công/tick — KHÔNG AI tự dựng nổi nhà một mình "
            f"trong một mùa: cần người góp công (vợ/chồng, con lớn gop_cong_cho, hoặc thuê thợ "
            f"bằng hợp đồng gop_cong), hoặc mua nhà có sẵn."
        )
    dong.append(dong_nha)
    dong.append(
        f"- Công cụ = {so(ct_r['go'])} gỗ + {so(ct_r['cong'])} công "
        f"(năng suất ×{so(ct_r['tang_nang_suat'])}, mòn "
        f"{phan_tram(ct_r['hao_mon_moi_tick_dung'])}/tick khi dùng). Gỗ ~"
        f"{so(kt['cong_moi_go'])} công/cây, quặng ~{so(kt['cong_moi_quang'])} công; không có "
        f"công cụ thì khai thác chỉ được {phan_tram(kt['hieu_suat_khong_cong_cu'])} hiệu suất."
    )
    r_thuyen = cfg.get("san_xuat.recipe.thuyen", {})
    if r_thuyen and bool(cfg.get("khong_gian.hai_bo", False)):
        dong.append(
            f"- SÔNG CHIA HAI BỜ: bờ dân cư và bờ hoang. Không thuyền thì KHÔNG qua được bờ "
            f"kia (không canh, không khai thác, không tới chợ bờ kia). Thuyền = "
            f"{so(r_thuyen['go'])} gỗ + {so(r_thuyen['cong'])} công; chủ thuyền tự qua không "
            f"mất phí, hoặc rao phí chở khách (tối đa "
            f"{so(cfg.get('khong_gian.do.khach_toi_da_moi_tick', 0))} khách/tick, thuyền hao "
            f"{so(cfg.get('khong_gian.do.hao_mon_moi_tick_dung', 0.0))} mỗi tick vận hành). "
            f"Phí do hai bên tự thỏa thuận — không có giá quy định."
        )
    if bool(cfg.get("khong_gian.bat", False)) and bool(
            cfg.get("khong_gian.khai_hoang.bat", False)):
        dong.append(
            f"- KHAI HOANG: vỡ thửa rừng/đồi CÔNG thành ruộng tốn "
            f"{so(cfg.get('khong_gian.khai_hoang.cong_moi_thua'))} công; đất mới vỡ có độ màu "
            f"{so(cfg.get('khong_gian.khai_hoang.mau_mo_khai_hoang'))}. Vỡ xong vẫn là đất "
            f"công tới khi canh đủ số mùa homestead. Rừng bị vỡ thì mất habitat gà rừng."
        )
    dong.append(
        "- Đời người hữu hạn (già là chết). KHÔNG kết hôn thì không con cái — của cải về "
        "công, dòng họ tuyệt tự. Cầu hôn ở mùa nào cũng được; người kia trả lời tick sau."
    )
    # CAP-5 (F-CAP5-1): định mức công/con là khóa ENGINE ĐANG ĐỌC dưới scenario này
    # (`minds.capabilities.dinh_muc_bat_ga` — gương của `engine.chan_nuoi.bat_ga`), KHÔNG
    # phải khóa legacy cố định: pool gà rừng bật thì `khong_gian.ga_rung.cong_moi_con` mới là
    # luật, và hôm nay hai khóa TRÙNG GIÁ TRỊ nên bản cũ đúng chỉ vì may mắn.
    dong.append(
        f"- CHĂN NUÔI cần THỜI GIAN: bắt gà rừng được GÀ CON "
        f"({so(dinh_muc_bat_ga(w))} công/con, làng có rừng); gà đẻ ra cũng là gà con. "
        f"Gà con nuôi 1 tick ({thang} tháng) mới thành gà lớn — chưa đẻ, giết non chỉ được "
        f"{so(cn['thit_moi_ga_con_kg'])}kg thịt. Gà lớn ăn {so(cn['ga_an_thoc_moi_tick'])}kg "
        f"thóc/tick (gà con {so(cn['ga_con_an_thoc_moi_tick'])}kg), no đủ thì đàn đẻ "
        f"+{phan_tram(cn['ga_sinh_san_moi_tick'])}/tick (trần "
        f"{so(cn['ga_toi_da_moi_ho'])} con/hộ). Giết 1 gà lớn → {so(cn['thit_moi_ga_kg'])}kg "
        f"thịt (1kg thịt no bằng {so(cn['thit_quy_doi_dinh_duong'])}kg thóc); thịt ôi nhanh "
        f"(hao {phan_tram(cn['thit_hao_moi_tick'])}/tick), gà sống thì không hao."
    )
    dong.append(
        f"- TUỔI TÁC: trẻ dưới {so(nc['tre_em_gop_cong_tu_tuoi'])} KHÔNG làm đồng (đi học thì "
        f"được — hoc/day_cho). Từ {so(nc['tre_em_gop_cong_tu_tuoi'])} tuổi phụ giúp được "
        f"{phan_tram(nc['ty_le_cong_tre_em'])} sức. Quá {so(lt['tuoi_giam_suc'])} tuổi sức yếu "
        f"dần (công ×{so(lt['he_so_sau_giam'])}, hao sức mỗi tick), quá {so(lt['tuoi_nghi'])} "
        f"gần như nghỉ hẳn (công ×{so(lt['he_so_sau_nghi'])}) — người già không còn tự kiếm ăn "
        f"được, không có thóc là đói."
    )
    gd = raw["giao_duc"]
    bac = "; ".join(
        f"E{i}: {so(gd[f'E{i}'][1])} tick, mất {phan_tram(gd[f'E{i}'][2])} công"
        for i in range(1, 5) if f"E{i}" in gd
    )
    dong.append(
        f"- CHỮ NGHĨA: học nâng bậc chữ E từng bậc một ({bac}); tự học mất gấp đôi số tick so "
        f"với có người biết chữ day_cho. Hợp đồng MIỆNG ai cũng lập được; hợp đồng VĂN BẢN — "
        f"loại duy nhất kèm được thế chấp và cưỡng chế khi phá vỡ — chỉ người biết chữ "
        f"(E{so(cfg.get('hop_dong.van_ban_can_E_nguoi_soan'))} trở lên) soạn được."
    )
    ss = raw["nhan_khau"]["sinh_san"]
    dong.append(
        f"- SINH NỞ có rủi ro cho sản phụ ({phan_tram(ss['rui_ro_me'])} mỗi lần sinh); rủi ro "
        f"chỉ giảm khi hộ sản phụ CÓ HỢP ĐỒNG hiệu lực với người nắm bí quyết y_te (giá cả, "
        f"điều khoản do hai bên tự thỏa thuận)."
    )
    dong.append(
        f"- ĐẤT BẠC MÀU: canh cùng một thửa liên tục thì độ màu giảm "
        f"{phan_tram(dd['thoai_hoa_moi_vu'])}/vụ (chạm đáy ở "
        f"{phan_tram(dd['san_ty_le_mau_mo'])} độ màu gốc); BỎ HOANG thì độ màu hồi "
        f"{phan_tram(dd['phuc_hoi_moi_tick_bo_hoang'])}/tick."
    )
    tn = raw["tay_nghe"]
    dong.append(
        f"- TAY NGHỀ: mỗi vụ trực tiếp canh tác, kinh nghiệm đồng áng tăng "
        f"{phan_tram(tn['tang_moi_vu'])} (tối đa ×{so(tn['tran'])} năng suất) — người canh "
        f"lâu năm gặt nhiều hơn người mới trên cùng một thửa."
    )
    dong.append(
        f"- ĐÁNH CÁ: sông là CỦA CHUNG, không cần ruộng, mùa nào cũng được — sông đầy cá thì "
        f"~{so(dc['cong_moi_kg_ca'])} công/kg; đàn cá là TÀI NGUYÊN TÁI TẠO CÓ HẠN (hồi "
        f"{phan_tram(dc['tai_sinh_moi_tick'])}/tick theo trữ lượng còn lại): đánh quá tay thì "
        f"cá thưa dần, cùng buổi công bắt được ít hẳn đi. 1kg cá no bằng "
        f"{so(dc['ca_quy_doi_dinh_duong'])}kg thóc, cá ươn nhanh "
        f"(hao {phan_tram(dc['ca_hao_moi_tick'])}/tick)."
    )
    if bool(cfg.get("khong_gian.ga_rung.bat", False)):
        dong.append(
            f"- GÀ RỪNG cũng là trữ lượng chung có hạn (sức chứa theo số ô rừng còn lại, hồi "
            f"{phan_tram(cfg.get('khong_gian.ga_rung.tai_sinh_moi_tick'))}/tick): bắt quá tay "
            f"thì cùng số công bắt được ít con hơn."
        )
    if bool(cfg.get("khong_gian.cham_tre.bat", False)):
        dong.append(
            f"- CHĂM TRẺ tốn CÔNG THẬT: mỗi trẻ dưới "
            f"{so(cfg.get('khong_gian.cham_tre.tuoi_can_cham'))} tuổi cần "
            f"{so(cfg.get('khong_gian.cham_tre.cong_cham_moi_tre'))} công/tick. Công ấy trừ "
            f"vào công của người chăm; ai chăm, trả công thế nào là chuyện hai bên thỏa thuận "
            f"(cham_tre + hợp đồng gop_cong)."
        )
    tc = raw["tiec"]
    dong.append(
        f"- TIỆC KHAO XÓM: bỏ ra ≥{so(tc['chi_phi_toi_thieu_thoc'])}kg (thóc/thịt quy đổi) mời "
        f"tối đa {so(tc['khach_toi_da'])} hàng xóm — của cải mất đi, những người đến dự thêm "
        f"quý mến người mở tiệc."
    )
    tr = raw["trom"]
    dong.append(
        f"- TRỘM CẮP: về mặt vật lý KHÔNG gì ngăn bạn lấy trộm (được thì tối đa "
        f"{phan_tram(tr['ty_le_lay_toi_da'])} kho người ta), nhưng "
        f"{phan_tram(1.0 - float(tr['p_thanh_cong']))} số lần sẽ BỊ BẮT QUẢ TANG — nạn nhân "
        f"thù, cả xóm coi khinh. Làng KHÔNG có tuần đinh hay hình phạt dựng sẵn nào."
    )
    dong.append(
        "- TRẺ MỒ CÔI cả cha lẫn mẹ được thân nhân gần nhất (hoặc một hàng xóm) cưu mang, ăn "
        "chung nồi cơm nhà người nuôi — nhà cưu mang có thêm một miệng ăn."
    )
    if bool(cfg.get("chinh_tri.bat", True)):
        ctri = raw["chinh_tri"]
        dong.append(
            f"- VIỆC LÀNG: cứ {so(ctri['bau_cu_moi_n_tick'])} tick cả làng bầu một Trưởng làng "
            f"bằng lá phiếu — ai cũng có thể tự ứng cử hoặc bỏ phiếu. Trưởng làng đương nhiệm "
            f"được ban thuế suất trên thu hoạch (trần "
            f"{phan_tram(ctri['thue_suat_toi_da'])}) và mức lương tối thiểu cho công làm thuê. "
            f"Thuế thu vào CÔNG QUỸ chung rồi chia đều lại cho cả làng. Khi chênh lệch giàu "
            f"nghèo (hệ số Gini thóc) vượt {so(ctri['gini_nguong_bao_dong'])} VÀ ≥"
            f"{phan_tram(ctri['ty_le_so_dong_bao_dong'])} người lớn cùng bạo động, "
            f"{phan_tram(ctri['ty_le_sung_cong_bao_dong'])} của cải nhóm giàu nhất bị sung "
            f"công chia lại cho nhóm nghèo nhất. Người làm công có thể lập nghiệp đoàn và đình "
            f"công để gây sức ép. Ngoài những gì dân tự lập ra, làng KHÔNG có sẵn nhà nước, "
            f"luật lệ hay lực lượng cưỡng chế nào."
        )
    dong.append(
        "\n[BẠN LÀ NGƯỜI SỐNG] Bạn có nhu cầu như mọi con người: no bụng hôm nay; an toàn ngày "
        "mai (dự trữ, nhà cửa); gia đình (dựng vợ gả chồng, con cái, cha mẹ già, để lại gia "
        "sản); và vị thế (đất đai, của cải, chữ nghĩa, tiếng thơm). Nặng nhẹ ra sao là tùy "
        "TÍNH CÁCH bạn. Muốn có con: đặt y_dinh_sinh_con (0/0.5/1) trong the_chinh_sach."
    )
    return "\n".join(dong)

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
        f"Bạn là người dưới đây trong một làng khép kín "
        f"(1 tick = {so(w.cfg.get('thoi_gian.thang_moi_tick'))} tháng). Bạn chỉ biết "
        "những gì cả làng đều biết và những gì của RIÊNG bạn — KHÔNG biết ví tiền hay ý "
        "định của người khác. Quyết định như CHÍNH BẠN, nhất quán với tính cách, ký ức, "
        "gia huấn riêng, kể cả khi khác số đông. Đơn vị giá trị: kg thóc.\n\n"
    )
    chung = build_user_chung(w)
    rieng = build_user_rieng(w, aid, triggers.get(aid, []))
    # xáo danh mục hành động theo seed×(agent,tick) — chống thiên vị vị trí, vẫn tất định
    danh_muc = muc_hanh_dong(w)
    g_menu = w.rng.get(f"menu_xao:{aid}", w.tick)
    muc_xao = [danh_muc[i] for i in g_menu.permutation(len(danh_muc))]
    return f"{dau}{luat_vat_ly(w)}\n\n{chung}\n\n{rieng}\n\n" \
           f"{schema_quyet_dinh_cho(w, muc_xao)}\n\n" \
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


def _bi_quyet_cua(w: World, aid: str) -> list[str]:
    """Blueprint agent SỞ HỮU hoặc được cấp `quyen_su_dung` — kèm CÔNG THỨC hàng mới (CAP-5).

    Menu `xay` chào `mon:"<mã hàng mới>"`; công thức của hàng đó KHÔNG nằm trong config mà
    nằm trong `Blueprint.recipe` (engine rút từ phân phối lúc sáng chế thành công). Không có
    khối này thì `<mã hàng mới>` là lời hứa suông: agent được mời chế một món mà không đâu
    nói nó tốn gì — đúng cái bệnh của `duc_xu` (A-02).

    Bất đối xứng thông tin GIỮ NGUYÊN: chỉ liệt kê blueprint của CHÍNH agent hoặc blueprint
    đã có điều khoản `quyen_su_dung` hiệu lực trỏ về agent. Chỉ đọc, không mutate.
    """
    from engine.contracts import ben_hien_tai

    duoc_cap: set[str] = set()
    for hd in w.hop_dong.values():
        if hd.trang_thai != "hieu_luc":
            continue
        for ck in hd.dieu_khoan:
            if (getattr(ck, "loai", "") == "quyen_su_dung"
                    and str(getattr(ck, "tai_san", "")).startswith("blueprint:")
                    and ben_hien_tai(w, hd.id, ck.den) == aid):
                duoc_cap.add(str(ck.tai_san).split(":", 1)[1])
    cong_mac_dinh = float(w.cfg.get("research.hang_moi.cong_mac_dinh"))
    ra: list[str] = []
    for bp in sorted(w.blueprints.values(), key=lambda b: b.id):
        cua_minh = bp.chu == aid
        if not (cua_minh or bp.id in duoc_cap):
            continue
        nguon = "của bạn" if cua_minh else "bạn được cấp quyền dùng"
        mo = f"{bp.id} [{bp.linh_vuc}, {nguon}]"
        if bp.hang_moi:
            cong = float(bp.recipe.get("cong", cong_mac_dinh))
            vat_lieu = " + ".join(
                f"{float(sl):g} {NHAN_NGUYEN_LIEU.get(ts, ts)}"
                for ts, sl in sorted(bp.recipe.items()) if ts != "cong"
            )
            chi_phi = f"{cong:g} công" + (f" + {vat_lieu}" if vat_lieu else "")
            mo += (f' → chế được mã hàng "{bp.hang_moi}" bằng '
                   f'{{"loai":"xay","mon":"{bp.hang_moi}","so_luong":1}}: '
                   f"{chi_phi} → 1 {bp.hang_moi}")
        ra.append(mo)
    return ra


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


def _fact_cards_cuc_bo(w: World, aid: str) -> list[str]:
    """Visible, engine-owned targets; facts only, never livelihood advice.

    The distinction between a common *field* and common *forest/hill* is
    intentionally explicit.  A field may be cultivated and homesteaded; only
    forest/hill is a legal target of ``khai_hoang``.  This prevents an LLM from
    inventing a parcel id or repeatedly clearing a rice field.
    """
    from engine.spatial import co_the_o_bo

    reachable = [p for p in w.parcels.values() if co_the_o_bo(w, aid, p.bo)]
    fields = sorted((p for p in reachable if p.loai == "ruong" and p.chu is None),
                    key=lambda p: p.id)[:6]
    rows: list[str] = []
    if fields:
        rows.append(
            "FACT CARD — RUỘNG CÔNG CÓ THỂ CANH: "
            + ", ".join(f"{p.id}(màu {p.mau_mo:.2f})" for p in fields)
            + ". Dùng phan_bo_cong.canh_thua; đây KHÔNG phải mục tiêu khai_hoang."
        )
    if bool(w.cfg.get("khong_gian.khai_hoang.bat", False)):
        clearable = sorted(
            (p for p in reachable if p.loai in {"rung", "doi"} and p.chu is None),
            key=lambda p: p.id,
        )[:6]
        if clearable:
            rows.append(
                "FACT CARD — RỪNG/ĐỒI CÔNG CÓ THỂ KHAI HOANG: "
                + ", ".join(f"{p.id}({p.loai})" for p in clearable)
                + ". Dùng khai_hoang.thua; tốn công theo luật vật lý."
            )
    from engine.projects import visible_to
    from engine.quotes import quote_visible_to

    projects = visible_to(w, aid)
    if projects:
        rows.append(
            "FACT CARD — DỰ ÁN MỞ: "
            + ", ".join(
                f"{p.id}({p.loai}; công còn {max(0.0, p.cong_can - p.cong_da):g})"
                for p in projects[:6]
            )
            + ". Chỉ dùng đúng id đã nêu khi góp vật liệu/công."
        )
    quotes = quote_visible_to(w, aid)
    if quotes:
        rows.append(
            "FACT CARD — BÁO GIÁ MỞ: "
            + ", ".join(
                f"{q.id}({q.chieu} {q.con_lai:g} {q.tai_san} @ {q.don_gia:g} {q.thanh_toan})"
                for q in quotes[:6]
            )
            + ". Chỉ dùng đúng id đã nêu khi chấp nhận báo giá."
        )
    return rows


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
    bi_quyet = _bi_quyet_cua(w, aid)
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
    if bi_quyet:
        dong.append("BÍ QUYẾT BẠN NẮM (blueprint của riêng bạn / được cấp quyền dùng): "
                    + "; ".join(bi_quyet) + ".")
    if dat_cong:
        dong.append(f"Ruộng công gần làng còn trống để CANH: {[p.id for p in dat_cong]}.")
    dong.extend(_fact_cards_cuc_bo(w, aid))
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
