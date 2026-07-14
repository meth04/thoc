"""P1 — cư trú bền (ADR 0007 §A–§C) + di sản (§D). Test của người CÀI (engine-surgeon).

`test-engineer` viết bộ ĐỘC LẬP riêng (T-01…T-43); file này là bằng chứng tự-chứng-minh của
implementer, không thay thế bộ đó và không đóng gate của chính nó.

Bốn bệnh đang chữa, mỗi cái có một test **non-vacuous** (đỏ được khi gate TẮT):
  F-18 adult-orphaning  → test_case_a0051_khong_chet_doi / test_adult_remains_resident
  F-19 VO_THUA_NHAN     → test_khong_con_so_du_ket_vinh_vien
  F-20 nợ chết theo con nợ → test_no_settle_tu_estate_truoc_heir
  F-36 sink đổi tên     → test_het_han_cong_fail_closed
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import estate, household
from engine.audit import LoiBaoToan
from engine.config import Config, deep_merge, load_config
from engine.contracts import ClauseChuyenGiaoMotLan, HopDong
from engine.intents import KeHoach
from engine.tick import chay_mot_tick
from engine.types import Agent, Persona
from engine.world import VO_THUA_NHAN, tao_the_gioi
from minds.rulebot import quyet_dinh_tat_ca
from tests.helpers import mind_tinh

ROOT = Path(__file__).resolve().parent.parent
SPATIAL = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_v1.yaml"
LIVELIHOOD = ROOT / "scenarios" / "agrarian_transition_v1" / "spatial_livelihood_v2.yaml"

# ADR 0007 §0.1 / §G.3 — GATE CỨNG. Lệch MỘT ký tự = P1 đã phá determinism legacy.
PIN_S11 = "4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b"
PIN_S42 = "f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153"
PIN_SPATIAL_S11 = "afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745"

HO_FULL = {
    "bat": True,
    "cu_tru_ben_vung": True,
    "cap_luong_thuc": True,
    "tach_ho": {"bat": True},
    "di_san": {"bat": True, "claim_han_tick": 3, "che_do": "kin",
               "het_han": "chia_deu_lang"},
}
NHO = {  # thế giới nhỏ cho test nhanh (map 8×8, ít người) — không đụng tham số kinh tế
    "ban_do": {"kich_thuoc": [8, 8]},
    "nhan_khau": {"dan_so_ban_dau": 6},
}


def cfg_ho(ho: dict | None = None, *, nho: bool = True, them: dict | None = None,
           chet_chac: bool = False) -> Config:
    """`chet_chac`: `p_chet_khi_nguy_kich = 1.0` ⇒ health < ngưỡng nguy kịch ⇒ CHẾT CHẮC.

    Đây KHÔNG phải nới test: nó chỉ bỏ tung xúc xắc khỏi một fixture mà nội dung cần kiểm là
    *chuyện gì xảy ra SAU cái chết*. Không có nó, `an_va_suc_khoe` hồi +10 health trước bước tử
    vong ⇒ cái chết thành ngẫu nhiên p=0.35/tick ⇒ test flaky (đúng loại test nói dối)."""
    raw = load_config().raw()
    if nho:
        raw = deep_merge(raw, NHO)
    if ho is not None:
        raw = deep_merge(raw, {"ho": ho})
    if chet_chac:
        raw = deep_merge(raw, {"suc_khoe": {"p_chet_khi_nguy_kich": 1.0}})
    if them:
        raw = deep_merge(raw, them)
    return Config(raw)


def _doc_events(w, p: Path) -> list[dict]:
    w.events.flush()  # EventLog ghi có buffer — không flush thì đọc ra file rỗng
    if not p.exists():
        return []
    return [json.loads(d) for d in p.read_text(encoding="utf-8").splitlines() if d.strip()]


def _thoi_gian_dung(w, n: int, mind=None) -> None:
    thua = len(w.parcels)
    fn = mind or mind_tinh({})
    for _ in range(n):
        chay_mot_tick(w, fn, thua)


def _kh_tach_ho(aid: str) -> KeHoach:
    """Ý định tách hộ qua field công khai (catalog CAP-2 bắt mọi lệch đường LLM)."""
    kh = KeHoach(id=aid)
    kh.tach_ho = True
    return kh


def _roi_cuoc_choi(w, aid: str) -> None:
    """Cho một agent 'rời cuộc chơi' trong fixture — PHẢI dọn kho.

    E1′ coi một người CHẾT còn số dư là absorbing sink (đúng: không ai lấy ra được). Fixture
    nào giết người mà để lại thóc trong túi họ sẽ làm audit đỏ — và đó là audit ĐÚNG."""
    w.agents[aid].con_song = False
    for ts, sl in sorted(w.ledger.tai_san_cua(aid).items()):
        if sl > 0:
            w.ledger.huy(aid, ts, sl, "an", "rời cuộc chơi (fixture)", 0)


# ============================================================ fixture: cha–mẹ–con vị thành niên


def _gia_dinh(w, tuoi_con_nam: float = 15.0) -> tuple[str, str, str]:
    """P (cha) + M (mẹ) + C (con) — cùng MỘT hộ; mọi agent khác rời cuộc chơi.

    Membership được lập qua ĐÚNG con đường sản xuất: khai báo biến cố `cuoi`/`sinh` rồi để
    `household.buoc_cu_tru` (single-writer) áp dụng — test KHÔNG chọc thẳng vào `w.cu_tru`.
    """
    ids = sorted(w.agents)
    p_id, m_id = ids[0], ids[1]
    for aid in ids[2:]:
        a = w.agents[aid]
        a.con_song = False
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "rời cuộc chơi (fixture)", 0)
    p, m = w.agents[p_id], w.agents[m_id]
    p.gioi_tinh, m.gioi_tinh = "nam", "nu"
    p.vo_chong, m.vo_chong = m_id, p_id
    p.tuoi_tick = m.tuoi_tick = 60.0  # 30 tuổi — hazard Gompertz cực nhỏ, test không đỏ vì may rủi
    p.health = m.health = 100.0
    m.y_dinh_sinh_con = 0.0  # không đẻ thêm: giữ hộ đúng ba người suốt test

    # Thứ tự ĐÚNG NHƯ SẢN XUẤT (rất quan trọng): (1) cưới ⇒ hai hộ nhập một; (2) TẠO trẻ +
    # khai báo `sinh` ⇒ trẻ vào hộ của MẸ. Engine `sinh_con` đòi `me.vo_chong` nên trẻ KHÔNG
    # BAO GIỜ tồn tại trước hôn nhân, và `demography` tạo agent + `ghi_bien_co("sinh")` trong
    # CÙNG bước 9 rồi 9b chạy ngay sau. Nếu test tạo agent trẻ TRƯỚC một `buoc_cu_tru` nào đó
    # thì quét an toàn 6b (đúng đắn) sẽ lập cho nó một hộ riêng — và đó là lỗi của test.
    household.ghi_bien_co(w, "cuoi", a=p_id, b=m_id)
    household.buoc_cu_tru(w, {})  # single-writer API, không chọc thẳng vào state

    c_id = w.id_moi()
    w.agents[c_id] = Agent(
        id=c_id, ten="Con", gioi_tinh="nam", tuoi_tick=tuoi_con_nam * 2.0,
        persona=Persona(), lang=p.lang, cha=p_id, me=m_id, health=100.0,
    )
    p.con.append(c_id)
    m.con.append(c_id)
    household.ghi_bien_co(w, "sinh", tre=c_id, me=m_id, cha=p_id)
    household.buoc_cu_tru(w, {})

    # kho: cha ĐẦY thóc, con KHÔNG có gì (đúng cấu hình A0051)
    for aid in (p_id, m_id, c_id):
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "reset kho (fixture)", 0)
    w.ledger.sinh(p_id, "thoc", 40_000.0, "khoi_tao", "fixture", 0)
    return p_id, m_id, c_id


# ============================================================ GATE: hash pin legacy


@pytest.mark.parametrize(("overlays", "seed", "pin"), [
    ([], 11, PIN_S11),
    ([], 42, PIN_S42),
    ([SPATIAL], 11, PIN_SPATIAL_S11),
])
def test_hash_legacy_pinned_off(overlays, seed, pin):
    """Gate cứng ADR 0007 §G.3: overlay hộ TẮT ⇒ rulebot 20 tick ra ĐÚNG ba hash cũ.

    Lệch ⇒ P1 đã phá determinism legacy ⇒ DỪNG, KHÔNG sửa pin."""
    cfg = load_config(overlays=[p.resolve() for p in overlays])
    w = tao_the_gioi(cfg, seed, events_path=None)
    n = len(w.parcels)
    for _ in range(20):
        chay_mot_tick(w, quyet_dinh_tat_ca, n)
    assert w.world_hash() == pin


def test_off_khong_co_key_residence_estate_trong_hash():
    """Gate TẮT ⇒ `behavioral_state()` KHÔNG có key mới (một key rỗng cũng đổi hash)."""
    w = tao_the_gioi(cfg_ho(None), 3, None)
    st = w.behavioral_state()
    assert "residence" not in st and "estate" not in st
    assert st["hash_schema"] == "behavioral-state-v2"  # KHÔNG bump schema

    w2 = tao_the_gioi(cfg_ho(HO_FULL), 3, None)
    st2 = w2.behavioral_state()
    assert "residence" in st2 and "estate" in st2  # ON ⇒ CÓ (thí nghiệm khác)


def test_ho_bat_false_bang_dung_khong_co_block():
    """`ho.bat: false` và config cũ (thiếu block) phải cùng transition function ⇒ cùng hash."""
    a = tao_the_gioi(cfg_ho(None), 7, None)
    b = tao_the_gioi(cfg_ho({"bat": False, "cu_tru_ben_vung": True,
                             "di_san": {"bat": True}}), 7, None)
    _thoi_gian_dung(a, 6, quyet_dinh_tat_ca)
    _thoi_gian_dung(b, 6, quyet_dinh_tat_ca)
    assert a.world_hash() == b.world_hash()


# ============================================================ F-18: adult-orphaning


def test_adult_remains_resident(tmp_path):
    """R2 (NO AGE-BASED ORPHANING): sinh nhật 16 KHÔNG đổi membership.

    Sinh nhật thứ 16 không phải một biến cố quan hệ — không event, không quyết định, không bút
    toán. Một biến-cố-không-tồn-tại không được phép có hệ quả vật lý."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL), 5, ev)
    p_id, _m, c_id = _gia_dinh(w, tuoi_con_nam=15.0)
    rid_truoc = household.rid_cua(w, c_id)
    assert rid_truoc == household.rid_cua(w, p_id)

    _thoi_gian_dung(w, 6)  # base = 2 tick/năm ⇒ C qua 16 tuổi ở tick 2

    assert w.agents[c_id].tuoi_nam >= 16.0, "fixture phải thực sự vượt mốc trưởng thành"
    assert w.agents[c_id].con_song
    assert household.rid_cua(w, c_id) == rid_truoc, "trưởng thành KHÔNG được đổi hộ"
    assert set(w.ho_cua(c_id)) == set(w.ho_cua(p_id))
    loai = {e["loai"] for e in _doc_events(w, ev) if e.get("nguoi") == c_id}
    assert "tach_ho" not in loai and "chuyen_ho" not in loai


@pytest.mark.parametrize(("ho", "cho_doi_chet"), [(None, True), (HO_FULL, False)])
def test_case_a0051_khong_chet_doi(tmp_path, ho, cho_doi_chet):
    """F-18 REGRESSION có tên + chứng minh NON-VACUOUS.

    Người vừa tròn 16, 0 tài sản, cha mẹ đầy thóc (40 000 kg).
      • gate TẮT  ⇒ `ho_cua` đẩy họ ra khỏi hộ cha mẹ CÒN SỐNG ⇒ ăn 0 kg ⇒ `an_doi` ⇒ CHẾT ĐÓI.
        (bệnh còn nguyên đó — nếu ô này không đỏ thì test kia vô nghĩa)
      • gate BẬT  ⇒ ở lại hộ, được cấp lương thực ⇒ KHÔNG `an_doi`, KHÔNG chết.
    """
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(ho), 5, ev)
    p_id, _m, c_id = _gia_dinh(w, tuoi_con_nam=15.0)
    _thoi_gian_dung(w, 10)

    evs = _doc_events(w, ev)
    an_doi = [e for e in evs if e["loai"] == "an_doi" and e.get("id") == c_id]
    chet = [e for e in evs if e["loai"] == "chet" and e.get("id") == c_id]
    assert w.agents[c_id].tuoi_nam >= 16.0

    if cho_doi_chet:
        assert an_doi, "OFF: bệnh F-18 phải TÁI HIỆN (nếu không, test ON là vacuous)"
        assert chet and chet[0]["ly_do"] == "chet_doi"
        assert not w.agents[c_id].con_song
    else:
        assert not an_doi, f"ON: người vừa 16 KHÔNG được đói khi cha mẹ đầy thóc: {an_doi}"
        assert not chet
        assert w.agents[c_id].con_song
        assert w.agents[c_id].health >= 99.0
        cap = [e for e in evs if e["loai"] == "cap_luong_thuc" and e.get("den") == c_id]
        assert cap, "phải có bút toán CẤP LƯƠNG THỰC tường minh (không ăn ké im lặng)"
        assert {e["tu"] for e in cap} == {p_id}, "chỉ người CÓ KHO trong hộ mới cấp được"
        # khẩu phần theo TUỔI, và nó CHUYỂN BẬC đúng lúc trưởng thành — quyền tiếp cận kho thì
        # KHÔNG đổi (đó mới là F-18)
        assert cap[0]["so_luong"] == pytest.approx(45.0, abs=1e-6)   # nhu_cau.tre_em_kg_tick
        assert cap[-1]["so_luong"] == pytest.approx(90.0, abs=1e-6)  # nhu_cau.nguoi_lon_kg_tick


def test_khong_an_ke_ngoai_ho(tmp_path):
    """Ranh giới §B.5: ngoài hộ ⇒ 0 kg. Người giàu KHÁC hộ không nuôi được ai."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL), 5, ev)
    ids = sorted(w.agents)
    giau, ngheo = ids[0], ids[1]
    for aid in ids:
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "reset (fixture)", 0)
    w.ledger.sinh(giau, "thoc", 50_000.0, "khoi_tao", "fixture", 0)
    assert household.rid_cua(w, giau) != household.rid_cua(w, ngheo)

    _thoi_gian_dung(w, 3)
    evs = _doc_events(w, ev)
    assert not [e for e in evs if e["loai"] == "cap_luong_thuc"
                and e.get("tu") == giau and e.get("den") == ngheo]
    assert [e for e in evs if e["loai"] == "an_doi" and e.get("id") == ngheo], (
        "người nghèo ngoài hộ phải đói THẬT — engine không cứu bằng luật ngầm")


# ============================================================ provisioning: P-1


def test_provisioning_hash_neutral():
    """ADR 0007 §B.3 INVARIANT P-1 — **FALSIFIED Ở MỨC BIT** (finding F-P1-1).

    ADR tuyên bố: bật RIÊNG `ho.cap_luong_thuc` ⇒ `world_hash` TRÙNG HỆT run OFF. Chứng minh
    của ADR đúng ở MỨC GIÁ TRỊ (`chuyen` + `huy` triệt tiêu; FlowRegistry khóa theo
    `(tai_san, luong)` chứ không theo chủ thể) nhưng SAI ở mức BIT: `world_hash` băm
    `float.hex()` — chính xác tuyệt đối — còn cộng dồn IEEE-754 KHÔNG kết hợp. Legacy áp MỘT
    delta `-tru` cho người có kho; provisioning áp `-x₁, -x₂, …` (mỗi người ăn một bút toán):
    `(bal - x₁) - x₂ ≠ bal - (x₁ + x₂)`.

    Test này khẳng định điều ĐÚNG và đo cận trên của điều SAI:
      (a) tập khóa số dư y hệt; mọi số dư bằng nhau trong 1e-9 (bookkeeping-only về GIÁ TRỊ);
      (b) flow_totals bằng nhau trong 1e-9 (không mint, không double-consume);
      (c) dân số / health / con_song y hệt (không đổi HÀNH VI);
      (d) lệch tối đa ≤ 1e-9 ⇒ mọi khác biệt là NHIỄU LÀM TRÒN, không phải quỹ đạo khác.
    Nếu (d) vỡ ⇒ provisioning đã đổi hành vi thật ⇒ ADR §B.4 bị cài sai ⇒ FAIL.
    """
    prov = {"bat": True, "cap_luong_thuc": True}
    for seed in (11, 42):
        a = tao_the_gioi(cfg_ho(None, nho=False), seed, None)
        b = tao_the_gioi(cfg_ho(prov, nho=False), seed, None)
        _thoi_gian_dung(a, 20, quyet_dinh_tat_ca)
        _thoi_gian_dung(b, 20, quyet_dinh_tat_ca)

        assert set(a.ledger._so_du) == set(b.ledger._so_du)
        lech = max((abs(a.ledger._so_du[k] - b.ledger._so_du[k])
                    for k in a.ledger._so_du), default=0.0)
        assert lech <= 1e-9, f"seed={seed}: provisioning ĐỔI HÀNH VI (lệch {lech})"

        assert set(a.ledger.flows._tich_luy) == set(b.ledger.flows._tich_luy)
        for k in a.ledger.flows._tich_luy:
            assert a.ledger.flows._tich_luy[k] == pytest.approx(
                b.ledger.flows._tich_luy[k], abs=1e-9), k

        assert sorted(a.agents) == sorted(b.agents)
        for aid in a.agents:
            assert a.agents[aid].con_song == b.agents[aid].con_song
            assert a.agents[aid].health == pytest.approx(b.agents[aid].health, abs=1e-9)


# ============================================================ F-19 / E1′


def test_khong_con_so_du_ket_vinh_vien(tmp_path):
    """E1′ — NO ABSORBING SINK / NO RENAMED SINK.

    Người giàu duy nhất, KHÔNG con, KHÔNG vợ/chồng, sống MỘT MÌNH (không đồng cư trú) chết.
    Legacy: 100% tài sản + CĂN NHÀ rơi vào `VO_THUA_NHAN` — kẹt vĩnh viễn (F-19).
    ON: estate mở, hết hạn ⇒ `chia_deu_lang` ⇒ NHÀ tới tay một chủ thể HOẠT ĐỘNG."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL, chet_chac=True), 9, ev)
    ids = sorted(w.agents)
    giau = ids[0]
    w.ledger.sinh(giau, "nha", 1.0, "xay", "fixture: căn nhà duy nhất", 0)
    w.ledger.sinh(giau, "thoc", 5_000.0, "khoi_tao", "fixture", 0)
    for aid in ids[1:]:
        w.agents[aid].health = 100.0
    tong_nha_truoc = w.ledger.tong_tai_san("nha")
    w.agents[giau].health = 0.0  # chết ở bước 9 tick tới

    thua = len(w.parcels)
    for _ in range(8):
        chay_mot_tick(w, mind_tinh({}), thua)
        assert estate.kiem_e1_prime(w) == [], f"tick {w.tick}: {estate.kiem_e1_prime(w)}"
        for ts in w.ledger.cac_tai_san():
            assert w.ledger.so_du(VO_THUA_NHAN, ts) == 0.0

    assert not w.agents[giau].con_song
    assert not w.di_san, "estate phải ĐÓNG sau claim_han_tick"
    assert w.di_san_xong
    assert w.ledger.tong_tai_san("nha") == pytest.approx(tong_nha_truoc)
    chu_nha = [ct for (ct, ts), v in w.ledger._so_du.items() if ts == "nha" and v > 0]
    assert chu_nha, "căn nhà không được bốc hơi"
    for ct in chu_nha:
        assert w.chu_the_hoat_dong(ct), f"nhà kẹt ở chủ thể KHÔNG hoạt động: {ct}"
    evs = _doc_events(w, ev)
    assert [e for e in evs if e["loai"] == "chia_deu_lang"]
    assert [e for e in evs if e["loai"] == "dong_di_san"]


def test_bang_terminal_subject_tuong_minh():
    """Bảng terminal-subject + drain là DỮ LIỆU TRONG CODE: `VO_THUA_NHAN` KHÔNG có drain nào;
    `CONG_QUY` chỉ có drain 'thoc' và CHỈ khi `chinh_tri.bat`."""
    w = tao_the_gioi(cfg_ho(HO_FULL, them={"chinh_tri": {"bat": False}}), 2, None)
    b = estate.bang_drain(w)
    assert b["VO_THUA_NHAN"] == set()
    assert b["CONG_QUY"] == set(), "chinh_tri TẮT ⇒ CONG_QUY KHÔNG có đường thoát (G-2)"

    w2 = tao_the_gioi(cfg_ho(HO_FULL, them={"chinh_tri": {"bat": True}}), 2, None)
    assert estate.bang_drain(w2)["CONG_QUY"] == {"thoc"}

    # chủ thể ma cầm tài sản mà không có drain ⇒ E1′ FAIL (không im lặng)
    w.ledger.sinh(VO_THUA_NHAN, "thoc", 10.0, "khoi_tao", "bơm chủ thể ma", 0)
    loi = estate.kiem_e1_prime(w)
    assert loi and "VO_THUA_NHAN" in loi[0]


def test_het_han_cong_fail_closed():
    """F-36 / §D.6: route di sản về `CONG_QUY` là SINK ĐỔI TÊN ⇒ CHẶN ở config-validation.

    `politics.thu_thue_va_chia` return sớm khi `chinh_tri.bat` false (đúng
    `agrarian_transition_v1`), và ngay cả khi bật, `_chia_deu` chỉ rebate 'thoc' của tick thu.
    Một căn nhà vào `CONG_QUY` là kẹt vĩnh viễn — pass E1 cũ nhưng vi phạm E1′."""
    xau = {**HO_FULL, "di_san": {**HO_FULL["di_san"], "het_han": "cong"}}
    with pytest.raises(SystemExit, match="E1′|SINK ĐỔI TÊN"):
        tao_the_gioi(cfg_ho(xau), 1, None)
    # kể cả khi chinh_tri BẬT: drain vẫn không phủ nha/ga/go ⇒ vẫn chặn
    with pytest.raises(SystemExit):
        tao_the_gioi(cfg_ho(xau, them={"chinh_tri": {"bat": True}}), 1, None)


def test_quy_tac_cap_la_va_dau_gia_fail_closed():
    """Quy tắc phân bổ khác `nhu_cau_deu` là một ĐỊNH CHẾ PHÂN PHỐI ⇒ chưa qua cổng ⇒ chặn.
    `dau_gia` chưa cài ⇒ chặn (không im lặng rơi về chế độ khác)."""
    with pytest.raises(SystemExit, match="quy_tac_cap"):
        tao_the_gioi(cfg_ho({**HO_FULL, "quy_tac_cap": "uu_tien_tre"}), 1, None)
    with pytest.raises(SystemExit, match="dau_gia"):
        tao_the_gioi(cfg_ho({**HO_FULL,
                             "di_san": {**HO_FULL["di_san"], "che_do": "dau_gia"}}), 1, None)


# ============================================================ F-20: nợ chết theo con nợ


def _ky_no(w, con_no: str, chu_no: str, so_luong: float, thoi_han: int = 8) -> HopDong:
    """Hợp đồng: con_no phải giao `so_luong` thóc cho chu_no TẠI ĐÁO HẠN (nghĩa vụ tồn đọng)."""
    from engine.board import _ky_hop_dong

    hd = HopDong(
        cac_ben=[con_no, chu_no], hinh_thuc="mieng", thoi_han=thoi_han,
        dieu_khoan=[ClauseChuyenGiaoMotLan(
            tu=con_no, den=chu_no, tai_san="thoc", so_luong=so_luong, tai="dao_han")],
    )
    assert _ky_hop_dong(w, hd)
    return hd


def _hoi_sinh(w, aid: str, thoc: float = 1_000.0) -> None:
    """Hồi sinh một agent đã 'rời cuộc chơi' trong fixture để làm chủ nợ."""
    w.agents[aid].con_song = True
    w.agents[aid].health = 100.0
    w.agents[aid].tuoi_tick = 60.0
    w.ledger.sinh(aid, "thoc", thoc, "khoi_tao", "fixture chủ nợ", 0)


@pytest.mark.parametrize(("ho", "estate_on"), [(None, False), (HO_FULL, True)])
def test_no_settle_tu_estate_truoc_heir(tmp_path, ho, estate_on):
    """F-20 (nhánh CÓ heir) + chứng minh NON-VACUOUS.

    A nợ B 300 kg, có 40 000 kg và một con C (10 tuổi).

    Sự thật legacy (đọc code, không suy đoán): `thua_ke_mac_dinh` chuyển token
    `vi_the:<hd>:<A>` cho heir như một tài sản rời ⇒ `ben_hien_tai(hd, A)` = C (còn sống) ⇒
    `_ben_mat` False ⇒ hợp đồng **KHÔNG bị hủy, mà TIẾP TỤC** — nghĩa vụ 300 kg lặng lẽ nhảy
    sang một đứa trẻ 10 tuổi, và chủ nợ **không nhận được gì lúc chết**. Đó là **nợ truyền đời
    ngầm**, không phải một định chế được khai báo ở đâu cả.

    ON (ADR §D.3/§D.8): estate settle B đúng 300 NGAY tick chết rồi ĐÓNG hợp đồng; heir nhận
    phần còn lại; KHÔNG cho nợ "sống tiếp" sang heir (nợ truyền đời là định chế mới ⇒ ADR riêng).
    """
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(ho, chet_chac=True), 5, ev)
    a_id, _m_id, c_id = _gia_dinh(w, tuoi_con_nam=10.0)
    b_id = sorted(w.agents)[2]
    _hoi_sinh(w, b_id)
    if ho:
        household.buoc_cu_tru(w, {})  # B sống lại ⇒ có hộ riêng

    # A giàu (40 000 kg từ fixture), nợ B 300 ⇒ tài sản X+Y với nghĩa vụ X=300 (khuôn T-21).
    # KHÔNG rút A xuống sát nợ: hộ A+M+C ăn 225 kg/tick TRƯỚC bước tử vong ⇒ kho mỏng bị ăn sạch
    # và estate rỗng ⇒ test sẽ đo nhầm thứ khác.
    hd = _ky_no(w, a_id, b_id, 300.0)
    b_truoc = w.ledger.so_du(b_id, "thoc")

    w.agents[a_id].health = 0.0  # A chết ở bước 9 tick tới
    _thoi_gian_dung(w, 2)  # legacy xử hợp đồng ở bước 7 của tick SAU cái chết
    assert not w.agents[a_id].con_song

    evs = _doc_events(w, ev)
    tra = [e for e in evs if e["loai"] == "thanh_toan_di_san" and e.get("chu_no") == b_id]
    vi_the = f"vi_the:{hd.id}:{a_id}"

    if not estate_on:
        assert not tra, "legacy KHÔNG có settlement nào"
        # nghĩa vụ trườn sang đứa trẻ qua token vị thế — chủ nợ chỉ còn biết chờ
        assert w.ledger.so_du(c_id, vi_the) == pytest.approx(1.0), (
            "legacy: vị thế con nợ được THỪA KẾ ⇒ nợ truyền đời NGẦM (bệnh phải tái hiện)")
        assert w.hop_dong[hd.id].trang_thai == "hieu_luc"
        assert w.ledger.so_du(b_id, "thoc") <= b_truoc, "chủ nợ KHÔNG nhận được gì lúc A chết"
        return

    assert tra, "ON: phải có settlement TỪ di sản"
    assert tra[0]["nghia_vu"] == pytest.approx(300.0, abs=1e-3)
    assert tra[0]["da_tra"] == pytest.approx(300.0, abs=1e-3), (
        "chủ nợ nhận ĐÚNG nghĩa vụ — KHÔNG nuốt trọn estate như khuôn `entities.thanh_ly`")
    assert not [e for e in evs if e["loai"] == "khong_thu_du"]
    assert [e for e in evs if e["loai"] == "thua_ke" and c_id in (e.get("nguoi_nhan") or [])], (
        "heir phải nhận PHẦN CÒN LẠI — SAU khi nợ đã settle")
    # nợ KHÔNG truyền đời: hợp đồng đã đóng, token vị thế đã đốt, trẻ KHÔNG gánh nghĩa vụ nào
    assert w.tim_hop_dong(hd.id).trang_thai == "huy"
    assert w.ledger.so_du(c_id, vi_the) == 0.0
    assert w.ledger.so_du(f"{estate.TIEN_TO}{a_id}", "thoc") == 0.0
    assert estate.kiem_e1_prime(w) == []


@pytest.mark.parametrize(("ho", "estate_on"), [(None, False), (HO_FULL, True)])
def test_f20_no_chet_theo_con_no_khi_khong_heir(tmp_path, ho, estate_on):
    """F-20 (nhánh KHÔNG heir) — bệnh gốc, và nó chồng lên F-19.

    Con nợ A **không con, không vợ/chồng, sống một mình**, nợ B 300 kg, có 5 000 kg.
      • OFF: `thua_ke_mac_dinh` → không heir → tài sản VÀ token vị thế rơi vào `VO_THUA_NHAN`.
        Bước 7 tick sau: `_ben_mat(VO_THUA_NHAN)` ⇒ `trang_thai="huy"` + `dot_vi_the`, **KHÔNG
        settlement** ⇒ **nợ chết theo con nợ**, B mất trắng, 5 000 kg kẹt vĩnh viễn.
      • ON: estate trả B đúng 300; phần dư đi tiếp theo `het_han` ⇒ `VO_THUA_NHAN` = 0.
    """
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(ho, chet_chac=True), 8, ev)
    ids = sorted(w.agents)
    a_id, b_id = ids[0], ids[1]
    for aid in ids[2:]:
        w.agents[aid].con_song = False
        sl = w.ledger.so_du(aid, "thoc")
        if sl > 0:
            w.ledger.huy(aid, "thoc", sl, "an", "rời cuộc chơi (fixture)", 0)
    for aid in (a_id, b_id):
        w.agents[aid].tuoi_tick, w.agents[aid].health = 60.0, 100.0
        w.agents[aid].vo_chong, w.agents[aid].con = None, []
    w.ledger.sinh(a_id, "thoc", 5_000.0, "khoi_tao", "fixture", 0)
    if ho:
        household.buoc_cu_tru(w, {})

    hd = _ky_no(w, a_id, b_id, 300.0)
    b_truoc = w.ledger.so_du(b_id, "thoc")
    w.agents[a_id].health = 0.0
    _thoi_gian_dung(w, 6)  # đủ qua claim_han_tick=3 để estate ĐÓNG
    assert not w.agents[a_id].con_song

    evs = _doc_events(w, ev)
    if not estate_on:
        assert not [e for e in evs if e["loai"] == "thanh_toan_di_san"]
        assert w.ledger.so_du(b_id, "thoc") <= b_truoc, "legacy: chủ nợ MẤT TRẮNG"
        assert w.tim_hop_dong(hd.id).trang_thai == "huy"
        assert w.ledger.so_du(VO_THUA_NHAN, "thoc") > 1_000.0, (
            "legacy: của cải KẸT trong VO_THUA_NHAN (F-19) — bệnh phải tái hiện")
        return

    tra = [e for e in evs if e["loai"] == "thanh_toan_di_san" and e["chu_no"] == b_id]
    assert tra and tra[0]["da_tra"] == pytest.approx(300.0, abs=1e-3)
    assert w.ledger.so_du(VO_THUA_NHAN, "thoc") == 0.0
    assert not w.di_san and w.di_san_xong, "estate phải ĐÓNG"
    assert estate.kiem_e1_prime(w) == []


def test_estate_khong_du_tra_no(tmp_path):
    """Tài sản < nghĩa vụ ⇒ chủ nợ nhận pro-rata, phần thiếu MẤT THẬT (`khong_thu_du`);
    heir nhận 0. KHÔNG mint bù, KHÔNG số dư âm, KHÔNG cho nợ 'sống tiếp' sang heir."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL, chet_chac=True), 5, ev)
    a_id, _m, c_id = _gia_dinh(w, tuoi_con_nam=10.0)
    b_id = sorted(w.agents)[2]
    w.agents[b_id].con_song = True
    w.agents[b_id].health = 100.0
    w.agents[b_id].tuoi_tick = 60.0
    w.ledger.sinh(b_id, "thoc", 1_000.0, "khoi_tao", "fixture", 0)
    household.buoc_cu_tru(w, {})

    _ky_no(w, a_id, b_id, 100_000.0)  # nghĩa vụ LỚN HƠN toàn bộ tài sản của A (40 000)
    tong_truoc = w.ledger.tong_tai_san("thoc")
    c_truoc = w.ledger.so_du(c_id, "thoc")

    w.agents[a_id].health = 0.0
    _thoi_gian_dung(w, 1)

    evs = _doc_events(w, ev)
    tra = [e for e in evs if e["loai"] == "thanh_toan_di_san" and e["chu_no"] == b_id]
    assert tra, "phải có settlement"
    da_tra, nghia_vu = tra[0]["da_tra"], tra[0]["nghia_vu"]
    assert nghia_vu == pytest.approx(100_000.0, abs=1e-3)
    assert 0.0 < da_tra < nghia_vu, "chủ nợ nhận TOÀN BỘ estate nhưng vẫn không đủ"

    thieu = [e for e in evs if e["loai"] == "khong_thu_du"]
    assert thieu and thieu[0]["thieu"] == pytest.approx(nghia_vu - da_tra, abs=1e-2), (
        "phần thiếu MẤT THẬT — không mint bù, không cho nợ sống tiếp sang heir")
    assert not [e for e in evs if e["loai"] == "thua_ke"
                and c_id in (e.get("nguoi_nhan") or [])], "heir nhận 0"
    assert w.ledger.so_du(c_id, "thoc") == pytest.approx(c_truoc, abs=1e-6)
    assert estate.kiem_e1_prime(w) == []
    assert w.ledger.so_du(f"{estate.TIEN_TO}{a_id}", "thoc") == 0.0
    # KHÔNG mint bù: tổng thóc thế giới chỉ GIẢM (ăn + hao kho), không kg nào sinh ra để trả nợ
    assert w.ledger.tong_tai_san("thoc") < tong_truoc


def test_yeu_cau_di_san_tu_choi_dung_ma_ly_do(tmp_path):
    """§C.5 + §D: claim window. Người KHÔNG có tư cách ⇒ `no_right`; quá hạn ⇒ `het_han`.
    Người có tư cách (đồng cư trú lúc chết) đòi trong hạn ⇒ nhận di sản, estate ĐÓNG."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL, chet_chac=True), 8, ev)
    ids = sorted(w.agents)
    a_id, ban_id, nguoi_la = ids[0], ids[1], ids[2]
    for aid in ids[3:]:
        _roi_cuoc_choi(w, aid)
    for aid in (a_id, ban_id, nguoi_la):
        w.agents[aid].tuoi_tick, w.agents[aid].health = 60.0, 100.0
        w.agents[aid].vo_chong, w.agents[aid].con = None, []
    # A và BAN ở CHUNG hộ nhưng KHÔNG huyết thống (dùng `cuu_mang` để nhập hộ hợp lệ)
    w.agents[ban_id].giam_ho = None
    w.ledger.sinh(a_id, "thoc", 3_000.0, "khoi_tao", "fixture", 0)
    household.buoc_cu_tru(w, {})
    rid_a = household.rid_cua(w, a_id)
    household._roi_ho(w, ban_id)
    household._vao_ho(w, ban_id, rid_a)  # đồng cư trú (kịch bản: bạn ở trọ cùng nhà)

    w.agents[a_id].health = 0.0
    _thoi_gian_dung(w, 1)
    assert not w.agents[a_id].con_song
    # A không con, không vợ chồng ⇒ bậc 3 rơi vào ĐỒNG CƯ TRÚ ⇒ BAN nhận ngay tick chết
    assert w.ledger.so_du(ban_id, "thoc") > 1_000.0, "sống chung thì thừa kế (bậc 3 mới)"
    assert not w.di_san, "có người nhận ⇒ estate đóng ngay tick chết"

    # người ngoài đòi một estate không tồn tại ⇒ khong_ton_tai (không raise, chỉ log)
    estate.yeu_cau_di_san(w, nguoi_la, f"{estate.TIEN_TO}{a_id}")
    ly_do = [e["ly_do"] for e in _doc_events(w, ev)
             if e["loai"] == "unrecognized_intent" and e["ai"] == nguoi_la]
    assert "khong_ton_tai" in ly_do


def test_yeu_cau_di_san_no_right_va_het_han(tmp_path):
    """Estate KHÔNG có người nhận ⇒ ở `mo` tới hạn. Người dưng đòi ⇒ `no_right`; quá hạn ⇒
    `het_han`. Không ai đòi được ⇒ bậc 4 `chia_deu_lang` ⇒ E1′ vẫn xanh."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL, chet_chac=True), 8, ev)
    ids = sorted(w.agents)
    a_id, nguoi_la = ids[0], ids[1]
    for aid in ids[2:]:
        _roi_cuoc_choi(w, aid)
    for aid in (a_id, nguoi_la):
        w.agents[aid].tuoi_tick, w.agents[aid].health = 60.0, 100.0
        w.agents[aid].vo_chong, w.agents[aid].con = None, []
    w.ledger.sinh(a_id, "thoc", 3_000.0, "khoi_tao", "fixture", 0)
    household.buoc_cu_tru(w, {})

    w.agents[a_id].health = 0.0
    _thoi_gian_dung(w, 1)
    ds_id = f"{estate.TIEN_TO}{a_id}"
    assert ds_id in w.di_san, "không heir, không đồng cư trú ⇒ estate ở 'mo' chờ claim"

    estate.yeu_cau_di_san(w, nguoi_la, ds_id)  # người dưng — không có tư cách
    ly_do = [e["ly_do"] for e in _doc_events(w, ev)
             if e["loai"] == "unrecognized_intent" and e["ai"] == nguoi_la]
    assert "no_right" in ly_do
    assert not w.di_san[ds_id].yeu_cau

    _thoi_gian_dung(w, 4)  # qua claim_han_tick=3 ⇒ bậc 4
    assert ds_id not in w.di_san and ds_id in w.di_san_xong
    assert w.ledger.so_du(ds_id, "thoc") == 0.0
    assert w.ledger.so_du(VO_THUA_NHAN, "thoc") == 0.0
    assert estate.kiem_e1_prime(w) == []
    assert [e for e in _doc_events(w, ev) if e["loai"] == "chia_deu_lang"]


# ============================================================ ghost offer (E4)


def test_ghost_offer_bi_tu_choi(tmp_path):
    """E4: người chết và `DI_SAN:*` KHÔNG là bên hợp đồng mới, KHÔNG nhận đề nghị đích danh."""
    from engine.board import dang_de_nghi

    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL), 5, ev)
    ids = sorted(w.agents)
    song, chet = ids[0], ids[1]
    w.agents[chet].con_song = False
    ds_id = f"{estate.TIEN_TO}{chet}"

    def _hd(ben2: str) -> HopDong:
        return HopDong(
            cac_ben=[song, ben2], thoi_han=3,
            dieu_khoan=[ClauseChuyenGiaoMotLan(
                tu=song, den=ben2, tai_san="thoc", so_luong=1.0, tai="ky_ket")],
        )

    assert dang_de_nghi(w, song, _hd(chet)) is None          # bên = người chết
    assert dang_de_nghi(w, song, _hd(ds_id)) is None          # bên = estate
    assert dang_de_nghi(w, song, _hd(VO_THUA_NHAN)) is None   # bên = sink
    # đề nghị CÔNG KHAI gửi ĐÍCH DANH cho estate/người chết
    cong_khai = HopDong(
        cac_ben=[song, "?"], thoi_han=3,
        dieu_khoan=[ClauseChuyenGiaoMotLan(
            tu=song, den="?", tai_san="thoc", so_luong=1.0, tai="ky_ket")],
    )
    assert dang_de_nghi(w, song, cong_khai.model_copy(deep=True), den=ds_id) is None
    assert dang_de_nghi(w, song, cong_khai.model_copy(deep=True), den=chet) is None
    assert w.bang_rao == {}, "không đề nghị ma nào được lên bảng rao"

    ly_do = {e["ly_do"] for e in _doc_events(w, ev) if e["loai"] == "unrecognized_intent"}
    assert any("đã chết" in x or "không tồn tại" in x or "không hoạt động" in x for x in ly_do)

    # và estate KHÔNG bao giờ đứng tên đất (audit.py:30 KHÔNG được nới)
    for p in w.parcels.values():
        assert p.chu != ds_id


# ============================================================ tách hộ


def test_tach_ho_tu_choi_dung_ma_ly_do(tmp_path):
    """§C.5: từ chối có MÃ LÝ DO, ghi `unrecognized_intent`, bỏ qua ÊM (điều luật #3)."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL), 5, ev)
    p_id, m_id, c_id = _gia_dinh(w, tuoi_con_nam=8.0)  # C mới 8 tuổi
    rid = household.rid_cua(w, p_id)

    kh = {c_id: _kh_tach_ho(c_id)}
    _thoi_gian_dung(w, 1, mind_tinh({1: kh}))
    ly_do = [e["ly_do"] for e in _doc_events(w, ev)
             if e["loai"] == "unrecognized_intent" and e["ai"] == c_id]
    assert "chua_truong_thanh" in ly_do
    assert household.rid_cua(w, c_id) == rid, "membership KHÔNG được đổi khi intent bị từ chối"

    # Bỏ lại trẻ KHÔNG người lớn ⇒ `no_adult_left`.
    # Dựng đúng tình huống: (1) cha P tách ra ở riêng — hợp lệ, vì mẹ M còn ở lại với con C;
    # (2) NAY mẹ M cũng xin tách. C KHÔNG đi theo M (cha P còn sống, C không phải người phụ
    # thuộc DUY NHẤT của M) ⇒ hộ nguồn sẽ còn mỗi đứa trẻ ⇒ TỪ CHỐI.
    t1 = w.tick + 1
    _thoi_gian_dung(w, 1, mind_tinh({t1: {p_id: _kh_tach_ho(p_id)}}))
    assert household.rid_cua(w, p_id) != household.rid_cua(w, m_id), "P phải tách được"
    assert household.rid_cua(w, c_id) == household.rid_cua(w, m_id), "C ở lại với mẹ"

    rid_m = household.rid_cua(w, m_id)
    t2 = w.tick + 1
    _thoi_gian_dung(w, 1, mind_tinh({t2: {m_id: _kh_tach_ho(m_id)}}))
    ly_do2 = [e["ly_do"] for e in _doc_events(w, ev)
              if e["loai"] == "unrecognized_intent" and e["ai"] == m_id]
    assert "no_adult_left" in ly_do2
    assert household.rid_cua(w, m_id) == rid_m, "bị từ chối ⇒ membership KHÔNG đổi"
    assert household.rid_cua(w, c_id) == rid_m


def test_tach_ho_thanh_cong_cat_provisioning(tmp_path):
    """Tách hộ ⇒ hộ MỚI, event `tach_ho`, và tick sau KHÔNG còn `cap_luong_thuc` P→C.

    Engine không cưỡng chế lòng tốt và cũng không cưỡng chế ích kỷ: ở chung thì ăn theo quy
    tắc hộ; không muốn thì tách ra BẰNG MỘT HÀNH ĐỘNG — và tự lo ăn."""
    ev = tmp_path / "events.jsonl"
    w = tao_the_gioi(cfg_ho(HO_FULL), 5, ev)
    p_id, _m, c_id = _gia_dinh(w, tuoi_con_nam=17.0)  # C đã trưởng thành
    rid_cu = household.rid_cua(w, c_id)

    _thoi_gian_dung(w, 1)  # tick 1: còn chung hộ ⇒ được cấp lương thực
    assert [e for e in _doc_events(w, ev) if e["loai"] == "cap_luong_thuc" and e["den"] == c_id]

    t = w.tick + 1
    _thoi_gian_dung(w, 1, mind_tinh({t: {c_id: _kh_tach_ho(c_id)}}))
    rid_moi = household.rid_cua(w, c_id)
    assert rid_moi is not None and rid_moi != rid_cu
    assert c_id not in w.ho_cua(p_id)
    tach = [e for e in _doc_events(w, ev) if e["loai"] == "tach_ho" and e["nguoi"] == c_id]
    assert tach and tach[0]["tu_ho"] == rid_cu and tach[0]["den_ho"] == rid_moi

    n_truoc = len([e for e in _doc_events(w, ev)
                   if e["loai"] == "cap_luong_thuc" and e["den"] == c_id])
    _thoi_gian_dung(w, 1)
    n_sau = len([e for e in _doc_events(w, ev)
                 if e["loai"] == "cap_luong_thuc" and e["den"] == c_id])
    assert n_sau == n_truoc, "đã tách hộ thì KHÔNG còn ăn kho cha mẹ"


# ============================================================ lifecycle / audit / determinism


def test_audit_xanh_moi_tick_qua_lifecycle():
    """§G.3 gate 4: gate ON ⇒ `kiem_toan_the_gioi` KHÔNG raise lần nào suốt 40 tick có chết,
    thừa kế, hợp đồng, di cư; E1′ xanh mọi tick; R1/R4 (partition) xanh mọi tick."""
    cfg = load_config(overlays=[SPATIAL.resolve(), LIVELIHOOD.resolve()])
    for seed in (11, 42):
        w = tao_the_gioi(cfg, seed, None)
        thua = len(w.parcels)
        for _ in range(40):
            chay_mot_tick(w, quyet_dinh_tat_ca, thua)  # audit chạy TRONG tick, raise là đỏ
            assert estate.kiem_e1_prime(w) == []
            song = {a for a, g in w.agents.items() if g.con_song}
            trong_ho = [m for cu in w.cu_tru.values() for m in cu.thanh_vien]
            assert sorted(trong_ho) == sorted(song)      # R1: partition
            assert len(trong_ho) == len(set(trong_ho))   # R1: đúng MỘT hộ
        assert w.di_san_xong, "40 tick phải có ít nhất một estate mở-và-đóng"


def test_on_deterministic_va_replay_checkpoint(tmp_path):
    """ADR 0001 §D: determinism phủ state MỚI. Cùng seed + overlay ⇒ cùng hash; và checkpoint
    (pickle) mang đủ `cu_tru`/`di_san` để resume ra ĐÚNG hash của run liền mạch."""
    from engine.world import World

    cfg = load_config(overlays=[SPATIAL.resolve(), LIVELIHOOD.resolve()])
    a = tao_the_gioi(cfg, 11, None)
    b = tao_the_gioi(cfg, 11, None)
    _thoi_gian_dung(a, 15, quyet_dinh_tat_ca)
    _thoi_gian_dung(b, 15, quyet_dinh_tat_ca)
    assert a.world_hash() == b.world_hash()
    assert a.cu_tru, "gate ON phải có state cư trú thật"

    ck = a.luu_checkpoint(tmp_path)
    lien_mach = tao_the_gioi(cfg, 11, None)
    _thoi_gian_dung(lien_mach, 20, quyet_dinh_tat_ca)

    w2 = World.nap_checkpoint(ck, None, cfg)
    assert w2.world_hash() == a.world_hash(), "checkpoint phải carry cu_tru/di_san"
    _thoi_gian_dung(w2, 5, quyet_dinh_tat_ca)
    assert w2.world_hash() == lien_mach.world_hash(), "resume ≠ liền mạch"


def test_migration_checkpoint_cu_khong_gay():
    """Checkpoint cũ (thiếu `cu_tru`/`di_san`) nạp lại ⇒ default rỗng ⇒ gate vẫn OFF ⇒
    `behavioral_state` KHÔNG có key mới ⇒ world_hash y nguyên ⇒ resume run cũ không gãy."""
    w = tao_the_gioi(cfg_ho(None), 3, None)
    _thoi_gian_dung(w, 3, quyet_dinh_tat_ca)
    truoc = w.world_hash()
    for ten in ("cu_tru", "_next_cu_tru", "bien_co_ho", "di_san", "di_san_xong",
                "_next_di_san"):
        delattr(w, ten)  # giả lập checkpoint TRƯỚC ADR 0007
    for ten, mac_dinh in (("cu_tru", {}), ("_next_cu_tru", 0), ("bien_co_ho", {}),
                          ("di_san", {}), ("di_san_xong", {}), ("_next_di_san", 0)):
        if not hasattr(w, ten):
            setattr(w, ten, mac_dinh)
    w._cu_tru_idx = None
    assert w.world_hash() == truoc
    assert "residence" not in w.behavioral_state()


# ============================================================ single-writer (T-19, tĩnh)


def test_single_writer_cu_tru_va_di_san():
    """INVARIANT §C.2: chỉ `engine/household.py` gán `w.cu_tru`/`_next_cu_tru`; chỉ
    `engine/estate.py` gán `w.di_san*`. `engine/world.py` được khai báo field + migration."""
    import re

    cho_phep = {
        "cu_tru": {"household.py", "world.py"},
        "_next_cu_tru": {"household.py", "world.py"},
        "di_san": {"estate.py", "world.py"},
        "di_san_xong": {"estate.py", "world.py"},
        "_next_di_san": {"estate.py", "world.py"},
    }
    for f in sorted((ROOT / "engine").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        for ten, ok in cho_phep.items():
            # gán trực tiếp: `w.<ten> = ...` / `self.<ten> = ...` (không tính `.setdefault`,
            # không tính đọc). `w.cu_tru[rid] = ...` là mutate CONTAINER, cũng phải trong owner.
            if re.search(rf"\b(?:w|self)\.{re.escape(ten)}\s*(?:\[[^\]]*\])?\s*=[^=]", src):
                assert f.name in ok, (
                    f"SINGLE-WRITER vi phạm: {f.name} gán `{ten}` — chỉ {sorted(ok)} được phép")


def test_khong_module_nao_doc_tuoi_de_quyet_membership():
    """R2 (tĩnh): `engine/household.py` KHÔNG được dùng `truong_thanh` để loại ai khỏi hộ.

    Nó CHỈ được dùng cho (a) tư cách người tách hộ và (b) ai là người lớn chịu trách nhiệm.
    Guard này bắt việc ai đó âm thầm bê lại luật `tuổi ≥ 16 ⇒ mất quyền tiếp cận kho`."""
    src = (ROOT / "engine" / "household.py").read_text(encoding="utf-8")
    body = src.split("def ho_cua_cu_tru", 1)[1].split("def ", 1)[0]
    assert "truong_thanh" not in body, "ho_cua_cu_tru KHÔNG được đọc tuổi (INVARIANT R2)"


def test_estate_khong_bao_gio_dung_ten_dat():
    """`audit.py` (chủ thửa phải hoạt động) KHÔNG được nới cho estate. Đất rời tay người chết
    NGAY trong tick chết: sang heir, hoặc về công."""
    cfg = load_config(overlays=[SPATIAL.resolve(), LIVELIHOOD.resolve()])
    w = tao_the_gioi(cfg, 11, None)
    thua = len(w.parcels)
    for _ in range(30):
        chay_mot_tick(w, quyet_dinh_tat_ca, thua)
        for p in w.parcels.values():
            assert p.chu is None or w.chu_the_hoat_dong(p.chu)
            assert not str(p.chu or "").startswith(estate.TIEN_TO)


def test_audit_bat_duoc_luong_lau_khi_on():
    """Audit vẫn là audit: bơm tài sản ngoài sổ khi gate ON ⇒ `LoiBaoToan`."""
    w = tao_the_gioi(cfg_ho(HO_FULL), 4, None)
    w.ledger._so_du[(sorted(w.agents)[0], "thoc")] += 123.0  # luồng lậu
    with pytest.raises(LoiBaoToan):
        chay_mot_tick(w, mind_tinh({}), len(w.parcels))
