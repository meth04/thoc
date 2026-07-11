"""Hiệu chỉnh công nghiệp hóa: chạy mock 300 năm với seeds {41..45} song song,
xuất reports/calibration.md (năm đạt nhãn từng seed + phân bố mô-típ hợp đồng).

  python -m tools.calibrate [--ticks 600] [--seeds 41 42 43 44 45]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
DATA_DIR = GOC / "data" / "runs"
REPORT_DIR = GOC / "reports"


def chay_seed(seed: int, ticks: int) -> subprocess.Popen:
    run_name = f"cal_s{seed}"
    import shutil

    shutil.rmtree(DATA_DIR / run_name, ignore_errors=True)
    return subprocess.Popen(
        [sys.executable, str(GOC / "run.py"), "--mode", "mock", "--ticks", str(ticks),
         "--seed", str(seed), "--fast", "--run-name", run_name, "--p-malformed", "0.15"],
        cwd=GOC, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def doc_ket_qua(seed: int):
    run_dir = DATA_DIR / f"cal_s{seed}"
    ms = [json.loads(x) for x in open(run_dir / "metrics.jsonl", encoding="utf-8")]
    cnh = next((m["nam"] for m in ms if m.get("cong_nghiep_hoa")), None)
    motif = Counter()
    for line in open(run_dir / "events.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if e["loai"] == "ky_hd":
            motif[e["mo_tip"]] += 1
    cuoi = ms[-1]
    return cnh, motif, cuoi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=600)
    ap.add_argument("--seeds", type=int, nargs="+", default=[41, 42, 43, 44, 45])
    args = ap.parse_args()

    procs = {s: chay_seed(s, args.ticks) for s in args.seeds}
    for s, p in procs.items():
        ret = p.wait()
        print(f"seed {s}: exit {ret}")

    REPORT_DIR.mkdir(exist_ok=True)
    dong = ["# Hiệu chỉnh công nghiệp hóa (mock, 5 seeds)", "",
            "| seed | năm đạt CNH | dân cuối | máy | entity | phi nông | công nhân |",
            "|---|---|---|---|---|---|---|"]
    cac_nam = []
    tong_motif = Counter()
    for s in args.seeds:
        cnh, motif, cuoi = doc_ket_qua(s)
        cac_nam.append(cnh if cnh is not None else 10**9)
        tong_motif.update(motif)
        dong.append(
            f"| {s} | {cnh if cnh is not None else '—'} | {cuoi['dan_so']} "
            f"| {cuoi.get('so_may', 0):.0f} | {cuoi.get('so_entity', 0)} "
            f"| {cuoi.get('ty_trong_phi_nong', 0):.0%} "
            f"| {cuoi['giai_cap'].get('cong_nhan', 0)} |"
        )
    cac_nam.sort()
    trung_vi = cac_nam[len(cac_nam) // 2]
    dat = 160 <= trung_vi <= 280 if trung_vi < 10**9 else False
    dong += ["", f"**Seed trung vị đạt nhãn năm: {trung_vi if trung_vi < 10**9 else '—'} → "
             + ("ĐẠT mục tiêu [160, 280] ✅" if dat else "CHƯA đạt mục tiêu [160, 280] ❌"), "",
             "## Phân bố mô-típ hợp đồng (tổng 5 seed)", ""]
    for m, so in tong_motif.most_common():
        dong.append(f"- `{m}`: {so}")
    (REPORT_DIR / "calibration.md").write_text("\n".join(dong), encoding="utf-8")
    print(f"[xong] reports/calibration.md — trung vị: {trung_vi}, đạt: {dat}")
    return 0 if dat else 1


if __name__ == "__main__":
    sys.exit(main())
