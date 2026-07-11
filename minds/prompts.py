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


def build_user_rieng(w: World, aid: str, ly_do_trigger: list[str]) -> str:
    tai_san = w.ledger.tai_san_cua(aid)
    tai_san_str = ", ".join(f"{ts}: {sl:.0f}" for ts, sl in sorted(tai_san.items()))
    dat = sorted(p.id for p in w.parcels.values() if p.chu == aid)
    hd_cua = [
        h.id for h in w.hop_dong.values()
        if h.trang_thai == "hieu_luc" and aid in h.cac_ben
    ]
    rao_cho_toi = [
        f"{dn.id}({dn.motif})" for dn in w.bang_rao.values()
        if dn.den == aid or dn.den is None
    ][:10]
    return (
        f"[NGƯỜI {aid}] Tài sản: {tai_san_str or 'trắng tay'}. Đất: {dat or 'không'}. "
        f"Hợp đồng hiệu lực: {hd_cua or 'không'}. Vì sao bạn được hỏi: {ly_do_trigger}. "
        f"Đề nghị thấy được: {rao_cho_toi or 'không'}."
    )
