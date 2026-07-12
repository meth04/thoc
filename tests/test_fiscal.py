"""Tài khóa / khu vực công (fiscal.bat) — ADR 0004 §T08-C, cổng định chế §5.

Chứng minh:
(a) MẶC ĐỊNH bat=false → hành vi rebate + world-hash LEGACY bất biến (khối fiscal không
    đụng determinism);
(b) bật → thuế TÍCH LŨY vào treasury (CONG_QUY), KHÔNG rebate; chi_cong xây thủy lợi (tài
    sản ledger có nguồn + counterpart); depreciation trừ đúng; ĐỊNH DANH TÀI KHÓA ĐÓNG mỗi
    tick; audit xanh; no phantom wealth;
(c) placebo (he_so_loi_ich=0) → thủy lợi KHÔNG cải thiện mất mùa;
(d) trưởng làng chết/khuyết → không chi được, treasury không mất;
(e) replay: fiscal-on cùng seed + kế hoạch → cùng world-hash (tất định).

Nguyên tắc: state ngân khố + hàng công nằm trong LEDGER (đã hash qua so_du_s); LLM/policy
chỉ phát intent; engine validate + apply; mọi flow có đối ứng + đăng ký FlowRegistry.
"""

from __future__ import annotations

from engine import audit, politics
from engine.config import Config, deep_merge, load_config
from engine.intents import KeHoach
from engine.tick import chay_mot_tick
from engine.world import CONG_QUY, ChinhQuyen, tao_the_gioi
from minds.rulebot import quyet_dinh_tat_ca
from tests.helpers import cap_ruong, chay_tick, mind_tinh, the_gioi_test

CT, CG, CC = 400.0, 4.0, 60.0  # = fiscal.chi_phi_thoc/go/cong_moi_don_vi (config)


def _ids_song(w) -> list[str]:
    return sorted(a for a, ag in w.agents.items() if ag.con_song)


def _cfg_fiscal(overlay: dict | None = None) -> Config:
    """Config với fiscal.bat=true (+ overlay tuỳ chọn). chinh_tri giữ mặc định (true)."""
    merged = deep_merge(load_config().raw(), {"fiscal": {"bat": True}})
    if overlay:
        merged = deep_merge(merged, overlay)
    return Config(merged)


def _the_gioi_fiscal(seed: int, giu_lai: int = 4, thoc_moi_nguoi: float = 2000.0,
                     overlay: dict | None = None):
    """Như the_gioi_test nhưng config fiscal-on."""
    w = tao_the_gioi(_cfg_fiscal(overlay), seed)
    ids = sorted(w.agents)
    for aid in ids[giu_lai:]:
        w.agents[aid].con_song = False
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "rời cuộc chơi (fixture)", 0)
    for aid in ids[:giu_lai]:
        hien_co = w.ledger.so_du(aid, "thoc")
        if thoc_moi_nguoi > hien_co:
            w.ledger.sinh(aid, "thoc", thoc_moi_nguoi - hien_co, "khoi_tao", "fixture", 0)
        w.agents[aid].health = 100.0
    return w


# ---------------------------------------------------- (a) mặc định TẮT: legacy bất biến


def test_default_bat_false():
    """Config mặc định: fiscal.bat = false."""
    assert bool(load_config().get("fiscal.bat", False)) is False


def test_default_off_rebate_nhu_cu():
    """bat=false: thu_thue_va_chia CHIA HẾT ngay (rebate) — CONG_QUY về 0, không thủy lợi."""
    w = the_gioi_test(seed=5, giu_lai=6, thoc_moi_nguoi=1000)
    ids = _ids_song(w)
    w.chinh_quyen = ChinhQuyen(truong_lang=ids[0], thue_suat=0.2, nhiem_ky_den=999)
    w.gat_tick = {"Pxx": (ids[0], 500.0)}
    tong0 = w.ledger.tong_tai_san("thoc")
    politics.thu_thue_va_chia(w)
    assert w.ledger.so_du(CONG_QUY, "thoc") < 1e-6          # rebate như cũ
    assert w.ledger.tong_tai_san("thuy_loi") == 0.0          # không hàng công
    assert abs(w.ledger.tong_tai_san("thoc") - tong0) < 1e-6
    audit.kiem_toan(w.ledger, w.tick)


def test_hash_legacy_bat_bien_khi_fiscal_off():
    """Khối fiscal (bat=false) KHÔNG đổi world-hash: run 20 tick rulebot với config có khối
    fiscal == config KHÔNG có khối fiscal (mô phỏng trạng thái tiền-fiscal)."""
    base = load_config().raw()
    khong_fiscal = deep_merge(base, {})
    khong_fiscal.pop("fiscal", None)

    def chay(cfg_dict) -> str:
        w = tao_the_gioi(Config(cfg_dict), seed=11)
        tong = len(w.parcels)
        while w.tick < 20:
            chay_mot_tick(w, quyet_dinh_tat_ca, tong)
        return w.world_hash()

    assert chay(deep_merge(base, {})) == chay(khong_fiscal)


# ---------------------------------------------------- (b) bật: treasury + chi công + hao mòn


def test_thue_tich_luy_vao_treasury():
    """bat=true: thuế GIỮ trong CONG_QUY (treasury stock), KHÔNG rebate; chuyển CÂN."""
    w = _the_gioi_fiscal(seed=5, giu_lai=6, thoc_moi_nguoi=1000)
    ids = _ids_song(w)
    w.chinh_quyen = ChinhQuyen(truong_lang=ids[0], thue_suat=0.2, nhiem_ky_den=999)
    w.gat_tick = {"Pxx": (ids[0], 500.0)}
    tong0 = w.ledger.tong_tai_san("thoc")
    politics.thu_thue_va_chia(w)
    assert w.ledger.so_du(CONG_QUY, "thoc") > 1e-6          # tích lũy, KHÔNG rebate
    assert abs(w.ledger.tong_tai_san("thoc") - tong0) < 1e-6  # no phantom (chuyển CÂN)
    audit.kiem_toan(w.ledger, w.tick)


def test_chi_cong_xay_thuy_loi():
    """Trưởng làng chi treasury (thóc) + gỗ/công của mình → thủy lợi của CONG_QUY. Mỗi
    đơn vị có nguồn + counterpart; no phantom (thóc/gỗ/công BIẾN thành thủy lợi)."""
    w = _the_gioi_fiscal(seed=6, giu_lai=3, thoc_moi_nguoi=1000)
    leader = _ids_song(w)[0]
    w.chinh_quyen = ChinhQuyen(truong_lang=leader, nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thoc", 5000.0, "khoi_tao", "treasury seed", 0)
    w.ledger.sinh(leader, "go", 50.0, "khai_thac", "test", 0)
    w.ledger.sinh(leader, "cong", 200.0, "sinh_cong", "test", 0)
    treas0 = w.ledger.so_du(CONG_QUY, "thoc")
    go0 = w.ledger.so_du(leader, "go")
    cong0 = w.ledger.so_du(leader, "cong")
    kh = {leader: KeHoach(id=leader, ban_hanh_luat={"loai": "chi_cong", "so_don_vi": 2})}
    politics.thi_hanh_chi_cong(w, kh)
    assert w.ledger.tong_tai_san("thuy_loi") == 2.0
    assert abs(w.ledger.so_du(CONG_QUY, "thoc") - (treas0 - 2 * CT)) < 1e-6
    assert abs(w.ledger.so_du(leader, "go") - (go0 - 2 * CG)) < 1e-6
    assert abs(w.ledger.so_du(leader, "cong") - (cong0 - 2 * CC)) < 1e-6
    audit.kiem_toan(w.ledger, w.tick)  # per-asset conservation vs FlowRegistry


def test_chi_cong_bi_tran_va_thieu_treasury():
    """Trần chi_cong_toi_da_moi_tick + kiểm đủ TRƯỚC: treasury chỉ đủ 1 đơn vị → xây 1,
    không trừ nửa vời cho đơn vị thứ 2 (nguyên tử)."""
    w = _the_gioi_fiscal(seed=6, giu_lai=3, thoc_moi_nguoi=1000)
    leader = _ids_song(w)[0]
    w.chinh_quyen = ChinhQuyen(truong_lang=leader, nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thoc", CT + 10.0, "khoi_tao", "treasury seed", 0)  # đủ 1 đv
    w.ledger.sinh(leader, "go", 50.0, "khai_thac", "test", 0)
    w.ledger.sinh(leader, "cong", 200.0, "sinh_cong", "test", 0)
    kh = {leader: KeHoach(id=leader, ban_hanh_luat={"loai": "chi_cong", "so_don_vi": 9})}
    politics.thi_hanh_chi_cong(w, kh)
    assert w.ledger.tong_tai_san("thuy_loi") == 1.0          # chỉ xây được 1
    assert abs(w.ledger.so_du(CONG_QUY, "thoc") - 10.0) < 1e-6  # đơn vị 2 KHÔNG trừ nửa vời
    audit.kiem_toan(w.ledger, w.tick)


def test_depreciation_thuy_loi():
    """Thủy lợi hao mòn ty_le mỗi tick qua SINK đã đăng ký."""
    w = _the_gioi_fiscal(seed=7, giu_lai=3)
    w.chinh_quyen = ChinhQuyen(truong_lang=_ids_song(w)[0], nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thuy_loi", 10.0, "chi_cong", "seed", 0)
    politics.hao_mon_thuy_loi(w)
    ty_le = float(w.cfg.get("fiscal.hao_mon_ty_le_moi_tick"))
    assert abs(w.ledger.so_du(CONG_QUY, "thuy_loi") - 10.0 * (1.0 - ty_le)) < 1e-9
    audit.kiem_toan(w.ledger, w.tick)


def _cong_quy_hao_kho(w, tick: int) -> float:
    """Thóc treasury (CONG_QUY) mất do hao hụt kho tick này — thóc là VẬT CHẤT nên treasury
    grain cũng mục như mọi kho thóc (không có kho magic bất hoại). SINK 'hao_kho' đã đăng ký."""
    return sum(
        -d.so_luong for tx in w.ledger.lich_su if tx.tick == tick
        for d in tx.sinh_huy
        if d.chu_the == CONG_QUY and d.tai_san == "thoc" and d.luong == "hao_kho"
    )


def test_dinh_danh_tai_khoa_dong_mot_tick():
    """ĐỊNH DANH TÀI KHÓA ĐÓNG mỗi tick (qua chay_mot_tick đầy đủ, audit chạy trong tick):
    treasury_end = treasury_start + taxes − spending − storage_loss (thóc treasury cũng mục);
    public_good_end = public_good_start + built − depreciation; built·đơn_giá == spending."""
    w = _the_gioi_fiscal(seed=3, giu_lai=4, thoc_moi_nguoi=3000)
    leader = _ids_song(w)[0]
    thua = cap_ruong(w, leader, 1)
    w.chinh_quyen = ChinhQuyen(truong_lang=leader, thue_suat=0.3, nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thoc", 5000.0, "khoi_tao", "treasury seed", 0)
    w.ledger.sinh(CONG_QUY, "thuy_loi", 2.0, "chi_cong", "pubgood seed", 0)
    w.ledger.sinh(leader, "go", 50.0, "khai_thac", "test", 0)
    treasury_start = w.ledger.so_du(CONG_QUY, "thoc")
    pubgood_start = w.ledger.so_du(CONG_QUY, "thuy_loi")

    plans = {1: {leader: KeHoach(id=leader, canh_thua=thua,
                 ban_hanh_luat={"loai": "chi_cong", "so_don_vi": 2})}}
    m = None
    tong = len(w.parcels)
    while w.tick < 1:
        m = chay_mot_tick(w, mind_tinh(plans), tong)  # audit raise nếu bảo toàn vỡ

    r = m["research"]
    taxes, spending = r["tax_revenue"], r["fiscal_spending"]
    depreciation = r["depreciation"]
    treasury_end, pubgood_end = r["treasury_balance"], r["public_good_stock"]
    storage_loss = _cong_quy_hao_kho(w, 1)
    built = spending / CT
    assert spending > 0 and taxes > 0 and built == 2.0     # cơ chế thực sự exercise
    assert storage_loss > 0                                # treasury grain cũng mục (honest)
    # định danh tài khóa ĐÓNG: mọi thóc treasury có đối ứng (thuế vào, chi ra, mục kho ra)
    assert abs(treasury_end - (treasury_start - spending + taxes - storage_loss)) < 1e-3
    # định danh hàng công ĐÓNG: mọi đơn vị thủy lợi có nguồn (built) + sink (depreciation)
    assert abs(pubgood_end - (pubgood_start + built - depreciation)) < 1e-6
    assert r["treasury_balance"] == r["fiscal_balance"]     # treasury == số dư thóc CONG_QUY


# ---------------------------------------------------- (c) placebo / ablation lợi ích


def test_placebo_loi_ich_bang_0():
    """he_so_loi_ich=0 → thủy lợi KHÔNG cải thiện mất mùa (lợi ích đến từ hệ số đã khai
    báo, không phải magic); >0 và đủ ngưỡng → cải thiện; dưới ngưỡng → không cải thiện."""
    han = 0.55  # hệ số thời tiết hạn/lũ (<1 → mất mùa)

    w = _the_gioi_fiscal(seed=8, giu_lai=3)  # loi mặc định 0.5
    w.chinh_quyen = ChinhQuyen(truong_lang=_ids_song(w)[0], nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thuy_loi", 3.0, "chi_cong", "seed", 0)
    assert politics.he_so_thoi_tiet_thuy_loi(w, han) > han       # giảm thiệt hại
    assert politics.he_so_thoi_tiet_thuy_loi(w, 1.25) == 1.25    # mùa tốt KHÔNG thưởng thêm

    w0 = _the_gioi_fiscal(seed=8, giu_lai=3,
                          overlay={"fiscal": {"he_so_loi_ich_han_lu": 0.0}})
    w0.chinh_quyen = ChinhQuyen(truong_lang=_ids_song(w0)[0], nhiem_ky_den=999)
    w0.ledger.sinh(CONG_QUY, "thuy_loi", 3.0, "chi_cong", "seed", 0)
    assert politics.he_so_thoi_tiet_thuy_loi(w0, han) == han     # PLACEBO: không cải thiện

    w2 = _the_gioi_fiscal(seed=8, giu_lai=3)  # thủy lợi = 0 < ngưỡng
    w2.chinh_quyen = ChinhQuyen(truong_lang=_ids_song(w2)[0], nhiem_ky_den=999)
    assert politics.he_so_thoi_tiet_thuy_loi(w2, han) == han     # dưới ngưỡng → không lợi ích


def test_loi_ich_tat_khi_fiscal_off():
    """fiscal.bat=false: dù có thủy lợi trong sổ (checkpoint lai), benefit helper trả
    nguyên he_so_tt → không rẽ nhánh production → hash legacy bất biến."""
    w = the_gioi_test(seed=8, giu_lai=3)  # config mặc định (bat=false)
    w.ledger.sinh(CONG_QUY, "thuy_loi", 5.0, "chi_cong", "seed", 0)
    assert politics.he_so_thoi_tiet_thuy_loi(w, 0.55) == 0.55


# ---------------------------------------------------- (d) death / office vacancy


def test_truong_lang_chet_khong_chi_duoc():
    """Trưởng làng chết → KHÔNG chi được; treasury KHÔNG mất (governance ≠ capacity)."""
    w = _the_gioi_fiscal(seed=9, giu_lai=3)
    leader = _ids_song(w)[0]
    w.chinh_quyen = ChinhQuyen(truong_lang=leader, nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thoc", 5000.0, "khoi_tao", "treasury seed", 0)
    w.ledger.sinh(leader, "go", 50.0, "khai_thac", "test", 0)
    w.ledger.sinh(leader, "cong", 200.0, "sinh_cong", "test", 0)
    w.agents[leader].con_song = False  # trưởng chết
    treas0 = w.ledger.so_du(CONG_QUY, "thoc")
    kh = {leader: KeHoach(id=leader, ban_hanh_luat={"loai": "chi_cong", "so_don_vi": 3})}
    politics.thi_hanh_chi_cong(w, kh)
    assert w.ledger.so_du(CONG_QUY, "thoc") == treas0  # treasury không mất
    assert w.ledger.tong_tai_san("thuy_loi") == 0.0
    # dọn công thừa để không vướng test khác dùng cùng ledger? ledger riêng mỗi world → ok


def test_office_vacancy_khong_chi_duoc():
    """Khuyết trưởng làng (truong_lang=None) → không ai chi được treasury."""
    w = _the_gioi_fiscal(seed=9, giu_lai=3)
    other = _ids_song(w)[1]
    w.chinh_quyen = ChinhQuyen(truong_lang=None, nhiem_ky_den=999)
    w.ledger.sinh(CONG_QUY, "thoc", 5000.0, "khoi_tao", "treasury seed", 0)
    w.ledger.sinh(other, "go", 50.0, "khai_thac", "test", 0)
    w.ledger.sinh(other, "cong", 200.0, "sinh_cong", "test", 0)
    treas0 = w.ledger.so_du(CONG_QUY, "thoc")
    kh = {other: KeHoach(id=other, ban_hanh_luat={"loai": "chi_cong", "so_don_vi": 3})}
    politics.thi_hanh_chi_cong(w, kh)  # người thường KHÔNG chi được công quỹ
    assert w.ledger.so_du(CONG_QUY, "thoc") == treas0
    assert w.ledger.tong_tai_san("thuy_loi") == 0.0


# ---------------------------------------------------- (e) replay tất định


def test_replay_fiscal_on_cung_hash():
    """Fiscal-on: hai run cùng seed + kế hoạch scripted → cùng world-hash (điều luật #4);
    cơ chế thực sự được exercise (thủy lợi > 0)."""
    def run():
        w = _the_gioi_fiscal(seed=5, giu_lai=4, thoc_moi_nguoi=3000)
        leader = _ids_song(w)[0]
        thua = cap_ruong(w, leader, 2)
        w.chinh_quyen = ChinhQuyen(truong_lang=leader, thue_suat=0.3, nhiem_ky_den=999)
        w.ledger.sinh(CONG_QUY, "thoc", 6000.0, "khoi_tao", "treasury seed", 0)
        w.ledger.sinh(leader, "go", 60.0, "khai_thac", "test", 0)
        plans = {1: {leader: KeHoach(id=leader, canh_thua=thua,
                     ban_hanh_luat={"loai": "chi_cong", "so_don_vi": 2})}}
        chay_tick(w, mind_tinh(plans), 3)
        return w

    w1, w2 = run(), run()
    assert w1.world_hash() == w2.world_hash()
    assert w1.ledger.tong_tai_san("thuy_loi") > 0.0
