"""Micro-task benchmark có GROUND TRUTH cho các bộ ra-quyết-định (P3, roadmap §2).

Mỗi micro-task dựng một ``World`` NHỎ tất định (seed cố định) đặt agent vào MỘT tình
huống quyết định mà đáp án ĐÚNG tính được TRỰC TIẾP từ vật lý/ràng buộc engine — KHÔNG
từ output của policy. Với mỗi (task × decision-maker) ta gọi policy, lấy intent, rồi
CHẤM theo ground truth độc lập đó.

Bốn task:
  1. constraint_following — hộ có đất+giống+công hữu hạn, mùa gieo. GT = số thửa canh
     KHẢ THI tối đa (min(công//công-mỗi-thửa, thóc//giống-mỗi-thửa)). Vi phạm = intent
     canh NHIỀU HƠN sức (đòi canh quá giống/quá công).
  2. contract_execution — có hợp đồng gop_cong/chuyen_giao_dinh_ky đang hiệu lực, hai
     bên đủ tài sản. GT = KHÔNG được đơn phương phá vỡ. Vi phạm = phát ``don_phuong_pha_vo``.
  3. no_selling_unowned — agent chỉ giữ thóc. GT = lệnh bán tài sản có số dư < khối lượng
     là INVALID. Vi phạm = đặt lệnh bán tài sản không đủ/không sở hữu.
  4. shock_response — dự báo hạn/lũ (thời tiết xấu) so với được mùa. GT = DẤU phản ứng:
     hạn/lũ ⇒ bán thóc ÍT hơn (giữ dự trữ). Không phản ứng (bằng nhau) ⇒ undefined → None.

Nguyên tắc (điều luật #3, #4): policy CHỈ đọc world; ground truth độc lập với policy;
mọi ngẫu nhiên qua ``w.rng``; sort trước khi mutate; KHÔNG mạng, KHÔNG LLM thật. Không
"đáp án đẹp" — báo trung thực nếu một policy (kể cả rulebot) vi phạm.

mock/real (LLM) là treatment SAU: interface ``fallback_rate``/``cost_token`` đã có sẵn
trong schema metric (giá trị None cho baseline; run LLM sẽ điền từ bảng ``llm_calls``).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from engine.config import load_config
from engine.contracts import ClauseChuyenGiaoDinhKy, ClauseGopCong, HopDong
from engine.intents import KeHoach
from engine.market import Lenh
from engine.world import World, tao_the_gioi
from minds.policies import REGISTRY, tao_policy

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "data" / "experiments"
SCHEMA_VERSION = 1

TASKS: tuple[str, ...] = (
    "constraint_following",
    "contract_execution",
    "no_selling_unowned",
    "shock_response",
)


# --------------------------------------------------------------- vật lý (ground truth)


def _sinh_cong(w: World, a) -> float:
    """Công một tick — KHỚP ``production.sinh_cong`` (health × hệ số tuổi)."""
    ld = w.cfg.raw()["lao_dong_theo_tuoi"]
    ngay = float(w.cfg.get("nhu_cau.ngay_cong_moi_tick"))
    tt = float(w.cfg.get("nhan_khau.tuoi_truong_thanh"))
    tuoi_gop = float(w.cfg.get("nhu_cau.tre_em_gop_cong_tu_tuoi"))
    ty_tre = float(w.cfg.get("nhu_cau.ty_le_cong_tre_em"))
    if a.tuoi_nam > float(ld["tuoi_nghi"]):
        he = float(ld["he_so_sau_nghi"])
    elif a.tuoi_nam > float(ld["tuoi_giam_suc"]):
        he = float(ld["he_so_sau_giam"])
    elif a.truong_thanh(tt):
        he = 1.0
    elif a.tuoi_nam >= tuoi_gop:
        he = ty_tre
    else:
        return 0.0
    return ngay * (a.health / 100.0) * he


def _cap_canh_vat_ly(w: World, aid: str) -> int:
    """Số thửa canh KHẢ THI tối đa — thuần vật lý: rào công ∩ rào giống (thóc riêng).

    Khớp per-thửa của ``production.thi_hanh_san_xuat`` (mỗi thửa tốn ``cong_moi_thua``
    công + ``giong_kg_moi_thua`` giống). KHÔNG áp ``thua_toi_da_tu_canh`` (đó là quy ước
    policy, không phải vật lý). Đây là GROUND TRUTH: độc lập với mọi decision-maker.
    """
    a = w.agents[aid]
    cong = _sinh_cong(w, a)
    cong_moi_thua = float(w.cfg.get("san_xuat.cong_moi_thua"))
    giong = float(w.cfg.get("san_xuat.giong_kg_moi_thua"))
    thoc = w.ledger.so_du(aid, "thoc")
    return min(int(cong // cong_moi_thua), int(thoc // giong))


def _thua_hop_le(w: World, aid: str, pid: str) -> bool:
    """Thửa mà agent CANH được: ruộng của mình / công / đang homestead."""
    p = w.parcels.get(pid)
    return p is not None and p.loai == "ruong" and (
        p.chu == aid or p.chu is None or p.homestead_ai == aid
    )


# --------------------------------------------------------------- dựng world nhỏ


def _base_world(seed: int, giu: int) -> tuple[World, list[str]]:
    """Thế giới thật, giữ ``giu`` người lớn đầu (sorted id), còn lại rời cuộc chơi."""
    w = tao_the_gioi(load_config(), seed)
    ids = sorted(w.agents)
    kept = ids[:giu]
    for aid in ids[giu:]:
        w.agents[aid].con_song = False
    for aid in kept:
        w.agents[aid].health = 100.0
    return w, kept


def _dat_thoc(w: World, aid: str, muc_tieu: float) -> None:
    """Đưa số dư thóc của agent về đúng ``muc_tieu`` qua luồng đã đăng ký (sinh/hủy)."""
    hien = w.ledger.so_du(aid, "thoc")
    if muc_tieu > hien + 1e-9:
        w.ledger.sinh(aid, "thoc", muc_tieu - hien, "khoi_tao", "microtask endow", 0)
    elif hien > muc_tieu + 1e-9:
        w.ledger.huy(aid, "thoc", hien - muc_tieu, "an", "microtask trim", 0)


def _cap_ruong(w: World, aid: str, so_thua: int) -> None:
    """Gán ``so_thua`` ruộng công gần làng nhất cho agent (tất định theo id thửa)."""
    lang = w.villages[0]
    ruong = sorted(
        (p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None),
        key=lambda p: (abs(p.r - lang.r) + abs(p.c - lang.c), -p.mau_mo, p.id),
    )
    for p in ruong[:so_thua]:
        p.chu = aid


def _dung_constraint(seed: int) -> tuple[World, list[str]]:
    """Mùa gieo: mỗi hộ có 4 thửa nhưng thóc chỉ đủ giống 2 thửa → cap vật lý = 2."""
    w, kept = _base_world(seed, 3)
    w.tick = 1  # mùa mưa
    w.thoi_tiet_nam[0] = "binh_thuong"
    for aid in kept:  # sorted → tất định
        _cap_ruong(w, aid, 4)
        _dat_thoc(w, aid, 150.0)  # 150//60 = 2 thửa giống; công 180//60 = 3 → cap = 2
    return w, kept


def _dung_contract(seed: int) -> tuple[World, list[str]]:
    """Hợp đồng gop_cong đang hiệu lực, hai bên dư thóc (đủ nghĩa vụ)."""
    w, kept = _base_world(seed, 2)
    w.tick = 1
    w.thoi_tiet_nam[0] = "binh_thuong"
    a_id, b_id = kept
    _dat_thoc(w, a_id, 1000.0)
    _dat_thoc(w, b_id, 1000.0)
    hd = HopDong(
        id="MT_HD", cac_ben=[a_id, b_id], hinh_thuc="mieng", thoi_han=8,
        dieu_khoan=[
            ClauseGopCong(tu=a_id, den=b_id, so_cong_moi_tick=60.0),
            ClauseChuyenGiaoDinhKy(tu=b_id, den=a_id, tai_san="thoc",
                                   so_luong=120.0, moi_n_tick=1),
        ],
        trang_thai="hieu_luc", tick_ky=0, nguoi_soan=a_id,
    )
    w.hop_dong[hd.id] = hd
    return w, kept


def _dung_nosell(seed: int) -> tuple[World, list[str]]:
    """Chỉ giữ thóc (không đất, không gỗ/gà/công cụ) — lệnh bán thứ khác là INVALID."""
    w, kept = _base_world(seed, 3)
    w.tick = 2  # mùa khô
    w.thoi_tiet_nam[1] = "binh_thuong"
    for aid in kept:
        _dat_thoc(w, aid, 1000.0)
    return w, kept


def _dung_shock(seed: int, thoi_tiet: str) -> tuple[World, list[str]]:
    """Mùa khô, dư thóc; thời tiết năm ép cứng để đo dấu phản ứng."""
    w, kept = _base_world(seed, 3)
    w.tick = 2
    w.thoi_tiet_nam[1] = thoi_tiet
    for aid in kept:
        _dat_thoc(w, aid, 300.0)
    return w, kept


_BUILDERS = {
    "constraint_following": _dung_constraint,
    "contract_execution": _dung_contract,
    "no_selling_unowned": _dung_nosell,
}


def dung_the_gioi(task: str, seed: int) -> tuple[World, list[str]]:
    """Dựng world cho task đơn-thế-giới (1–3). shock_response dùng hai thế giới riêng."""
    if task not in _BUILDERS:
        raise ValueError(f"dung_the_gioi không hỗ trợ {task!r} (shock dùng đường riêng)")
    return _BUILDERS[task](seed)


# --------------------------------------------------------------- chấm điểm


def _nhan_hanh_dong(kh: KeHoach | None) -> str:
    """Nhãn hành động chủ đạo của một intent — để đo action-diversity (entropy)."""
    if kh is None:
        return "nghi"
    if kh.canh_thua:
        return "canh"
    lenh = [le for le in kh.dat_lenh if isinstance(le, Lenh)]
    if any(le.chieu == "ban" for le in lenh):
        return "ban"
    if any(le.chieu == "mua" for le in lenh):
        return "mua"
    if kh.cong_khai_go > 0:
        return "khai_go"
    if kh.cong_khai_quang > 0:
        return "khai_quang"
    if kh.don_phuong_pha_vo:
        return "pha_vo"
    if kh.de_nghi_hop_dong or kh.tra_loi_de_nghi:
        return "hop_dong"
    return "nghi"


def _rec(task: str, seed: int, aid: str, *, feasible: bool | None, violation: bool | None,
         correct_sign: bool | None, action: str, chi_tiet: str) -> dict[str, Any]:
    return {
        "task": task, "seed": seed, "agent": aid,
        "feasible": feasible, "violation": violation, "correct_sign": correct_sign,
        "action": action, "chi_tiet": chi_tiet,
    }


def _cham_constraint(w: World, kept: list[str], kh_map: dict[str, KeHoach],
                     seed: int) -> list[dict[str, Any]]:
    recs = []
    for aid in kept:
        cap = _cap_canh_vat_ly(w, aid)  # ground truth, độc lập policy
        kh = kh_map.get(aid)
        yeu_cau = [pid for pid in (kh.canh_thua if kh else []) if _thua_hop_le(w, aid, pid)]
        vi = len(yeu_cau) > cap
        recs.append(_rec("constraint_following", seed, aid, feasible=not vi, violation=vi,
                         correct_sign=None, action=_nhan_hanh_dong(kh),
                         chi_tiet=f"canh {len(yeu_cau)}/cap {cap}"))
    return recs


def _cham_contract(w: World, kept: list[str], kh_map: dict[str, KeHoach],
                   seed: int) -> list[dict[str, Any]]:
    hieu_luc = {h.id: h for h in w.hop_dong.values() if h.trang_thai == "hieu_luc"}
    recs = []
    for aid in kept:
        kh = kh_map.get(aid)
        pha_vo = [ref for ref in (kh.don_phuong_pha_vo if kh else [])
                  if ref in hieu_luc and aid in hieu_luc[ref].cac_ben]
        du_kha_nang = w.ledger.so_du(aid, "thoc") > 0  # dựng cả hai bên solvent
        vi = bool(pha_vo) and du_kha_nang
        recs.append(_rec("contract_execution", seed, aid, feasible=not vi, violation=vi,
                         correct_sign=None, action=_nhan_hanh_dong(kh),
                         chi_tiet=f"pha_vo {len(pha_vo)}"))
    return recs


def _cham_nosell(w: World, kept: list[str], kh_map: dict[str, KeHoach],
                 seed: int) -> list[dict[str, Any]]:
    recs = []
    for aid in kept:
        kh = kh_map.get(aid)
        xau = []
        for le in (kh.dat_lenh if kh else []):
            if isinstance(le, Lenh) and le.ai == aid and le.chieu == "ban":
                if w.ledger.so_du(aid, le.tai_san) + 1e-9 < le.so_luong:
                    xau.append(le.tai_san)
        vi = bool(xau)
        recs.append(_rec("no_selling_unowned", seed, aid, feasible=not vi, violation=vi,
                         correct_sign=None, action=_nhan_hanh_dong(kh),
                         chi_tiet=("ban_khong_so_huu " + ",".join(sorted(xau))) if xau else "ok"))
    return recs


_SCORERS = {
    "constraint_following": _cham_constraint,
    "contract_execution": _cham_contract,
    "no_selling_unowned": _cham_nosell,
}


def cham_diem(task: str, w: World, kept: list[str], kh_map: dict[str, KeHoach],
              seed: int = 0) -> list[dict[str, Any]]:
    """Chấm intent theo ground truth cho task đơn-thế-giới (1–3)."""
    if task not in _SCORERS:
        raise ValueError(f"cham_diem không hỗ trợ {task!r}")
    return _SCORERS[task](w, kept, kh_map, seed)


def _ban_thoc(kh: KeHoach | None) -> float:
    if kh is None:
        return 0.0
    return sum(le.so_luong for le in kh.dat_lenh
               if isinstance(le, Lenh) and le.chieu == "ban" and le.tai_san == "thoc")


def _cham_shock(dm: str, seed: int) -> list[dict[str, Any]]:
    """Hai thế giới giống hệt trừ thời tiết; đo DẤU thay đổi lượng bán thóc."""
    w_xau, kept = _dung_shock(seed, "han_lu")
    w_tot, _ = _dung_shock(seed, "duoc_mua")
    kh_xau = tao_policy(dm)(w_xau)   # instance MỚI cho mỗi thế giới (state adaptive sạch)
    kh_tot = tao_policy(dm)(w_tot)
    recs = []
    for aid in kept:
        ban_xau = _ban_thoc(kh_xau.get(aid))
        ban_tot = _ban_thoc(kh_tot.get(aid))
        if abs(ban_xau - ban_tot) < 1e-9:
            dung = None  # không phản ứng ⇒ dấu undefined ⇒ None (không tính là vi phạm)
        else:
            dung = ban_xau < ban_tot  # đúng dấu: hạn/lũ ⇒ bán ÍT hơn (giữ dự trữ)
        recs.append(_rec("shock_response", seed, aid, feasible=None, violation=None,
                         correct_sign=dung, action=_nhan_hanh_dong(kh_xau.get(aid)),
                         chi_tiet=f"ban_han={ban_xau:.0f} ban_muagat={ban_tot:.0f}"))
    return recs


def danh_gia_task(task: str, dm: str, seed: int) -> list[dict[str, Any]]:
    """Chấm một (task × decision-maker × seed) → list record theo ground truth."""
    if task == "shock_response":
        return _cham_shock(dm, seed)
    w, kept = dung_the_gioi(task, seed)
    kh_map = tao_policy(dm)(w)
    return cham_diem(task, w, kept, kh_map, seed)


# --------------------------------------------------------------- tổng hợp metric


def _entropy_bits(labels: list[str]) -> float | None:
    """Shannon entropy (bit) của phân phối nhãn hành động — cao = đa dạng."""
    if not labels:
        return None
    n = len(labels)
    return round(-sum((c / n) * math.log2(c / n) for c in Counter(labels).values()), 4)


def _rate(vals: list[bool]) -> float | None:
    return round(sum(1 for v in vals if v) / len(vals), 4) if vals else None


def tong_hop_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Metric per decision-maker. undefined → None (không bịa số)."""
    feas = [r["feasible"] for r in records if r["feasible"] is not None]
    viol = [r["violation"] for r in records if r["violation"] is not None]
    sign = [r["correct_sign"] for r in records if r["correct_sign"] is not None]
    return {
        "constraint_violation_rate": _rate(viol),
        "feasible_rate": _rate(feas),
        "shock_correct_sign_rate": _rate(sign),
        "action_diversity": _entropy_bits([r["action"] for r in records]),
        # welfare_regret: không định nghĩa được optimum welfare đã kiểm định cho các task
        # thuần-ràng-buộc này (canh tối đa ≠ tối ưu phúc lợi vì subsistence chủ ý chừa ăn)
        # → None trung thực thay vì áp một "đáp án đẹp".
        "welfare_regret": None,
        "fallback_rate": None,   # interface mock/real (từ bảng llm_calls) — baseline không có
        "cost_token": None,      # interface mock/real
        "n_decisions": len(records),
    }


def _tom_tat_task(records: list[dict[str, Any]]) -> dict[str, Any]:
    viol = [r["violation"] for r in records if r["violation"] is not None]
    feas = [r["feasible"] for r in records if r["feasible"] is not None]
    sign = [r["correct_sign"] for r in records if r["correct_sign"] is not None]
    return {
        "violation_rate": _rate(viol),
        "feasible_rate": _rate(feas),
        "correct_sign_rate": _rate(sign),
        "n": len(records),
    }


def chay_benchmark(tasks: list[str], dms: list[str],
                   seeds: list[int]) -> dict[str, Any]:
    """Chạy toàn bộ lưới (task × dm × seed) → payload tất định (đã sort)."""
    ket_qua: dict[str, Any] = {}
    for dm in sorted(dms):
        records: list[dict[str, Any]] = []
        by_task: dict[str, Any] = {}
        for task in tasks:  # giữ thứ tự TASKS
            task_recs: list[dict[str, Any]] = []
            for seed in sorted(seeds):
                task_recs.extend(danh_gia_task(task, dm, seed))
            records.extend(task_recs)
            by_task[task] = _tom_tat_task(task_recs)
        ket_qua[dm] = {"aggregate": tong_hop_metrics(records), "by_task": by_task}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "tools.microtasks",
        "config_digest": load_config().digest(),
        "tasks": list(tasks),
        "decision_makers": sorted(dms),
        "seeds": sorted(seeds),
        "results": ket_qua,
    }


# --------------------------------------------------------------- báo cáo


def _o(x: float | None, phan_tram: bool = False) -> str:
    if x is None:
        return "—"
    return f"{x * 100:.0f}%" if phan_tram else f"{x:.2f}"


def viet_summary_md(payload: dict[str, Any]) -> str:
    tasks = payload["tasks"]
    dong = ["# Micro-task benchmark (ground-truth)", "",
            f"- Decision-makers: {', '.join(payload['decision_makers'])}",
            f"- Seeds: {payload['seeds']}; tasks: {', '.join(tasks)}",
            f"- config_digest: `{payload['config_digest'][:12]}`", "",
            "## Constraint-violation-rate theo task (thấp = tốt); shock = correct-sign-rate",
            "",
            "| decision_maker | " + " | ".join(tasks) + " | action_div |",
            "|---|" + "---|" * (len(tasks) + 1)]
    for dm in payload["decision_makers"]:
        res = payload["results"][dm]
        o = []
        for task in tasks:
            bt = res["by_task"][task]
            if task == "shock_response":
                o.append(f"sign {_o(bt['correct_sign_rate'], True)}")
            else:
                o.append(_o(bt["violation_rate"], True))
        o.append(_o(res["aggregate"]["action_diversity"]))
        dong.append(f"| {dm} | " + " | ".join(o) + " |")
    dong += ["", "Ghi chú: welfare_regret=None (chưa có optimum phúc lợi kiểm định);",
             "fallback_rate/cost_token=None (interface LLM, baseline không dùng)."]
    return "\n".join(dong) + "\n"


def _in_bang(payload: dict[str, Any]) -> None:
    print("decision_maker      | c_viol% | contract% | nosell% | shock_sign% | act_div")
    for dm in payload["decision_makers"]:
        res = payload["results"][dm]
        bt = res["by_task"]
        cf = _o(bt.get("constraint_following", {}).get("violation_rate"), True)
        ce = _o(bt.get("contract_execution", {}).get("violation_rate"), True)
        ns = _o(bt.get("no_selling_unowned", {}).get("violation_rate"), True)
        sh = _o(bt.get("shock_response", {}).get("correct_sign_rate"), True)
        ad = _o(res["aggregate"]["action_diversity"])
        print(f"{dm:<19} | {cf:>7} | {ce:>9} | {ns:>7} | {sh:>11} | {ad:>7}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Micro-task benchmark có ground-truth (THÓC)")
    parser.add_argument("--tasks", nargs="+", default=["all"],
                        help="all | tên task (constraint_following, ...)")
    parser.add_argument("--decision-makers", nargs="+", default=sorted(REGISTRY),
                        choices=sorted(REGISTRY),
                        help="bộ ra-quyết-định (baseline không-mạng)")
    parser.add_argument("--seeds", nargs="+", type=int, default=[41, 42, 43])
    parser.add_argument("--out", required=True,
                        help="thư mục đầu ra (refuse-overwrite); tương đối → theo repo root")
    args = parser.parse_args(argv)

    tasks = list(TASKS) if "all" in args.tasks else list(args.tasks)
    la = [t for t in tasks if t not in TASKS]
    if la:
        parser.error(f"task không hỗ trợ: {la}; có: {', '.join(TASKS)}")

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    if out.exists():
        raise SystemExit(f"Thư mục đã tồn tại, không ghi đè: {out}; đổi --out.")

    payload = chay_benchmark(tasks, args.decision_makers, args.seeds)
    out.mkdir(parents=True)
    (out / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    (out / "summary.md").write_text(viet_summary_md(payload), encoding="utf-8")
    _in_bang(payload)
    try:
        print(f"[xong] {out.relative_to(ROOT)}")
    except ValueError:
        print(f"[xong] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
