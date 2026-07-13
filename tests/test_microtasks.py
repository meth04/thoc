"""Kiểm thử micro-task benchmark (P3): ground-truth tất định + độc lập decision-maker.

Mỗi task được chấm ĐÚNG trên một policy đã biết trước kết quả:
- subsistence luôn feasible ở constraint_following;
- policy over-reach / bán-không-sở-hữu / phá-vỡ-hợp-đồng bị PHÁT HIỆN (kể cả khi baseline
  hiện không vi phạm — chứng minh harness bắt được vi phạm, không phải "đáp án đẹp");
- adaptive phản ứng ĐÚNG DẤU với cú sốc, subsistence không phản ứng → None (undefined).
"""

from __future__ import annotations

import json

from engine.intents import KeHoach
from engine.market import Lenh
from engine.world import World
from tools.microtasks import (
    TASKS,
    _cap_canh_vat_ly,
    cham_diem,
    chay_benchmark,
    danh_gia_task,
    dung_the_gioi,
    main,
    tong_hop_metrics,
)


class _CanhTatCaThuaSoHuu:
    """Over-reach: đòi canh MỌI thửa mình sở hữu (quá giống/quá công)."""

    name = "_overreach"
    version = "0"

    def __init__(self) -> None:
        self.params: dict = {}

    def __call__(self, w: World) -> dict[str, KeHoach]:
        out: dict[str, KeHoach] = {}
        for aid in sorted(w.agents):
            if not w.agents[aid].con_song:
                continue
            owned = sorted(p.id for p in w.parcels.values() if p.chu == aid)
            out[aid] = KeHoach(id=aid, canh_thua=owned)
        return out


class _BanKhongSoHuu:
    """Đặt lệnh bán gỗ trong khi số dư gỗ = 0."""

    name = "_sell_unowned"
    version = "0"

    def __init__(self) -> None:
        self.params: dict = {}

    def __call__(self, w: World) -> dict[str, KeHoach]:
        out: dict[str, KeHoach] = {}
        for aid in sorted(w.agents):
            if not w.agents[aid].con_song:
                continue
            kh = KeHoach(id=aid)
            kh.dat_lenh.append(Lenh(aid, "ban", "go", 5.0, 10.0))
            out[aid] = kh
        return out


class _PhaVoHopDong:
    """Đơn phương phá vỡ mọi hợp đồng đang hiệu lực dù đủ tài sản thực hiện."""

    name = "_breach"
    version = "0"

    def __init__(self) -> None:
        self.params: dict = {}

    def __call__(self, w: World) -> dict[str, KeHoach]:
        active = sorted(h.id for h in w.hop_dong.values() if h.trang_thai == "hieu_luc")
        out: dict[str, KeHoach] = {}
        for aid in sorted(w.agents):
            if not w.agents[aid].con_song:
                continue
            kh = KeHoach(id=aid)
            kh.don_phuong_pha_vo = list(active)
            out[aid] = kh
        return out


def test_ground_truth_cap_tat_dinh_va_doc_lap_policy():
    w1, kept1 = dung_the_gioi("constraint_following", 41)
    w2, kept2 = dung_the_gioi("constraint_following", 41)
    assert kept1 == kept2
    cap1 = {aid: _cap_canh_vat_ly(w1, aid) for aid in kept1}
    # cap vật lý = min(180//60=3 công, 150//60=2 giống) = 2 cho mọi hộ đã dựng
    assert set(cap1.values()) == {2}
    # chạy một policy KHÔNG được đổi ground truth (policy chỉ đọc world)
    from minds.policies import tao_policy

    tao_policy("adaptive")(w1)
    cap_sau = {aid: _cap_canh_vat_ly(w1, aid) for aid in kept1}
    assert cap_sau == cap1
    assert {aid: _cap_canh_vat_ly(w2, aid) for aid in kept2} == cap1


def test_constraint_subsistence_luon_feasible():
    recs = danh_gia_task("constraint_following", "subsistence", 41)
    assert recs and all(r["feasible"] and not r["violation"] for r in recs)


def test_constraint_phat_hien_overreach():
    w, kept = dung_the_gioi("constraint_following", 41)
    kh_map = _CanhTatCaThuaSoHuu()(w)
    recs = cham_diem("constraint_following", w, kept, kh_map, 41)
    # mỗi hộ sở hữu 4 thửa nhưng cap = 2 → đòi canh 4 = vi phạm
    assert recs and all(r["violation"] for r in recs)


def test_nosell_phat_hien_ban_khong_so_huu_va_baseline_sach():
    w, kept = dung_the_gioi("no_selling_unowned", 41)
    recs_xau = cham_diem("no_selling_unowned", w, kept, _BanKhongSoHuu()(w), 41)
    assert recs_xau and all(r["violation"] for r in recs_xau)
    # subsistence chỉ giữ thóc, không đặt lệnh bán → không vi phạm
    recs_ok = danh_gia_task("no_selling_unowned", "subsistence", 41)
    assert recs_ok and all(not r["violation"] for r in recs_ok)


def test_contract_phat_hien_pha_vo_va_baseline_sach():
    w, kept = dung_the_gioi("contract_execution", 41)
    recs_xau = cham_diem("contract_execution", w, kept, _PhaVoHopDong()(w), 41)
    assert recs_xau and all(r["violation"] for r in recs_xau)
    recs_ok = danh_gia_task("contract_execution", "rulebot", 41)
    assert recs_ok and all(not r["violation"] for r in recs_ok)


def test_shock_adaptive_dung_dau_subsistence_undefined():
    adap = danh_gia_task("shock_response", "adaptive", 41)
    # adaptive: hạn/lũ ⇒ dự trữ mục tiêu cao hơn ⇒ bán ít hơn ⇒ đúng dấu
    assert adap and all(r["correct_sign"] is True for r in adap)
    subs = danh_gia_task("shock_response", "subsistence", 41)
    # subsistence không nhìn tín hiệu sốc ⇒ không phản ứng ⇒ undefined
    assert subs and all(r["correct_sign"] is None for r in subs)


def test_tong_hop_metrics_schema_va_undefined_thanh_none():
    recs = danh_gia_task("shock_response", "subsistence", 41)
    m = tong_hop_metrics(recs)
    assert set(m) == {
        "constraint_violation_rate", "feasible_rate", "shock_correct_sign_rate",
        "action_diversity", "welfare_regret", "fallback_rate", "cost_token", "n_decisions",
    }
    # không có tín hiệu shock ⇒ correct-sign-rate None; interface LLM None
    assert m["shock_correct_sign_rate"] is None
    assert m["welfare_regret"] is None and m["fallback_rate"] is None
    assert m["cost_token"] is None


def test_benchmark_payload_va_determinism_2_run():
    a = chay_benchmark(list(TASKS), ["rulebot", "adaptive"], [41, 42])
    b = chay_benchmark(list(TASKS), ["adaptive", "rulebot"], [42, 41])
    assert a == b  # tất định + không phụ thuộc thứ tự dm/seed đầu vào
    assert a["schema_version"] == 1
    assert a["decision_makers"] == ["adaptive", "rulebot"]
    assert set(a["results"]["adaptive"]) == {"aggregate", "by_task"}
    assert set(a["results"]["adaptive"]["by_task"]) == set(TASKS)


def test_cli_ghi_summary_va_refuse_overwrite(tmp_path):
    out = tmp_path / "mt_run"
    rc = main(["--tasks", "all", "--decision-makers", "subsistence", "adaptive",
               "--seeds", "41", "--out", str(out)])
    assert rc == 0
    assert (out / "summary.json").exists() and (out / "summary.md").exists()
    payload = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert payload["decision_makers"] == ["adaptive", "subsistence"]
    # refuse-overwrite: chạy lại vào thư mục đã tồn tại → dừng
    try:
        main(["--tasks", "all", "--decision-makers", "subsistence",
              "--seeds", "41", "--out", str(out)])
        raise AssertionError("phải từ chối ghi đè")
    except SystemExit:
        pass


def test_cli_determinism_hai_thu_muc(tmp_path):
    p1, p2 = tmp_path / "r1", tmp_path / "r2"
    main(["--tasks", "all", "--decision-makers", "rulebot", "--seeds", "41", "--out", str(p1)])
    main(["--tasks", "all", "--decision-makers", "rulebot", "--seeds", "41", "--out", str(p2)])
    assert (p1 / "summary.json").read_text(encoding="utf-8") == \
        (p2 / "summary.json").read_text(encoding="utf-8")
