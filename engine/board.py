"""Bảng rao (SPEC 3.1): đăng đề nghị hợp đồng công khai/đích danh; chấp nhận/từ chối/mặc cả.

Khớp đầu tiên thắng, thứ tự người trả lời theo quan hệ (tie-break seeded).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.contracts import HopDong, validate_hop_dong

HET_HAN_DE_NGHI = 4  # tick


@dataclass
class DeNghi:
    id: str
    hd: HopDong
    tu: str
    den: str | None  # None = công khai
    tick: int
    vong_mac_ca: int = 0
    tra_loi: dict[str, object] = field(default_factory=dict)  # ai → "chap_nhan" | HopDong sửa
    motif: str = ""  # cache mô-típ (tính một lần khi đăng)


def dang_de_nghi(w, tu: str, hd: HopDong, den: str | None = None, vong: int = 0) -> str | None:
    """Mind đề nghị hợp đồng; engine validate cấu trúc trước khi lên bảng."""
    hd.nguoi_soan = hd.nguoi_soan or tu
    ly_do = validate_hop_dong(hd, w)
    if ly_do is not None:
        w.ghi_unrecognized(tu, "de_nghi_hop_dong", ly_do)
        return None
    w._next_dn += 1
    dn = DeNghi(id=f"DN{w._next_dn:05d}", hd=hd, tu=tu, den=den, tick=w.tick,
                vong_mac_ca=vong, motif=mo_tip_hop_dong(hd))
    w.bang_rao[dn.id] = dn
    w.events.ghi(w.tick, "de_nghi_hd", ref=dn.id, tu=tu, den=den,
                 mo_tip=mo_tip_hop_dong(hd))
    return dn.id


def mo_tip_hop_dong(hd: HopDong) -> str:
    """Mô-típ = tổ hợp loại clause, sắp xếp — auto-cluster, KHÔNG phải tên định chế."""
    return "+".join(sorted(c.loai for c in hd.dieu_khoan))


def _ky_hop_dong(w, hd: HopDong) -> bool:
    """Ký: thi hành mọi chuyển giao tại ký kết NGUYÊN TỬ; thất bại → không ký."""
    from engine.contracts import _chuyen_an_toan

    ly_do = validate_hop_dong(hd, w)
    if ly_do is not None:
        return False
    # thử các khoản ky_ket — nếu khoản nào hụt thì hoàn tác các khoản trước
    da_chuyen: list = []
    for ck in hd.dieu_khoan:
        if ck.loai == "chuyen_giao_mot_lan" and ck.tai == "ky_ket":
            if _chuyen_an_toan(w, ck.tu, ck.den, ck.tai_san, ck.so_luong, "ký kết"):
                da_chuyen.append(ck)
            else:
                for c2 in da_chuyen:
                    _chuyen_an_toan(w, c2.den, c2.tu, c2.tai_san, c2.so_luong, "hoàn ký hụt")
                return False
    w._next_hd += 1
    hd.id = f"HD{w._next_hd:05d}"
    hd.tick_ky = w.tick
    hd.trang_thai = "hieu_luc"
    w.hop_dong[hd.id] = hd
    # vị thế mỗi bên = token chuyển nhượng được (SPEC 2.3)
    for ben in hd.cac_ben:
        ts = f"vi_the:{hd.id}:{ben}"
        w.ledger.flows.dang_ky(ts, "ky_hd", "nguon")
        w.ledger.flows.dang_ky(ts, "het_hd", "sink")
        w.ledger.sinh(ben, ts, 1.0, "ky_hd", f"vị thế {hd.id}", w.tick)
    for a in hd.cac_ben:
        for b in hd.cac_ben:
            if a < b:
                w.cong_quan_he(a, b, w.cfg.get("quan_he.cong_moi_tuong_tac"))
    w.events.ghi(w.tick, "ky_hd", hd=hd.id, cac_ben=hd.cac_ben,
                 hinh_thuc=hd.hinh_thuc, mo_tip=mo_tip_hop_dong(hd),
                 thoi_han=hd.thoi_han)
    return True


def khop_bang_rao(w) -> None:
    """Bước 4 pipeline: xử lý trả lời trên bảng rao; khớp đầu tiên thắng."""
    g = w.rng.get("bang_rao", w.tick)
    toi_da_vong = int(w.cfg.get("hop_dong.mac_ca_toi_da_vong"))
    for dn_id in sorted(w.bang_rao):
        dn = w.bang_rao.get(dn_id)
        if dn is None:
            continue
        # người đăng (hoặc người được mời đích danh) đã chết → gỡ khỏi bảng
        nguoi_lien_quan = [dn.tu] + ([dn.den] if dn.den else [])
        if any(x in w.agents and not w.agents[x].con_song for x in nguoi_lien_quan):
            del w.bang_rao[dn_id]
            continue
        if not dn.tra_loi:
            # chỉ hết hạn khi KHÔNG có trả lời đang chờ xử lý
            if w.tick - dn.tick > HET_HAN_DE_NGHI:
                del w.bang_rao[dn_id]
            continue
        # thứ tự ưu tiên: quan hệ với người đăng giảm dần, tie-break seeded
        nguoi_tra_loi = sorted(
            dn.tra_loi,
            key=lambda ai: (-w.uy_tin(dn.tu, ai), g.random()),
        )
        khop_xong = False
        for ai in nguoi_tra_loi:
            tl = dn.tra_loi[ai]
            if tl == "tu_choi":
                continue
            if tl == "chap_nhan":
                hd = dn.hd.model_copy(deep=True)
                # đề nghị công khai: người nhận thế chỗ "?"
                hd.cac_ben = [ai if b == "?" else b for b in hd.cac_ben]
                for ck in hd.dieu_khoan:
                    for vai in ("tu", "den"):
                        if getattr(ck, vai, None) == "?":
                            setattr(ck, vai, ai)
                    if ck.loai == "dieu_kien_su_kien":
                        for vai in ("tu", "den"):
                            if getattr(ck.thi, vai, None) == "?":
                                setattr(ck.thi, vai, ai)
                if _ky_hop_dong(w, hd):
                    khop_xong = True
                    break
            elif isinstance(tl, HopDong):  # mặc cả: gửi lại bản sửa cho người đăng
                if dn.vong_mac_ca < toi_da_vong:
                    dang_de_nghi(w, ai, tl, den=dn.tu, vong=dn.vong_mac_ca + 1)
                    w.events.ghi(w.tick, "mac_ca", ref=dn.id, tu=ai, den=dn.tu)
        if khop_xong:
            del w.bang_rao[dn_id]
        else:
            dn.tra_loi.clear()
            # có người trả lời mà vẫn không ký được → không giữ zombie quá hạn
            if w.tick - dn.tick > HET_HAN_DE_NGHI:
                del w.bang_rao[dn_id]
