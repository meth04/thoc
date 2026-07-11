"""tools/analyze — ma trận dịch chuyển giai cấp, β thừa kế, kỷ lục, PNGs (SPEC 9.4).

  python -m tools.analyze mock300
→ reports/final_analysis.md + reports/*.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"

GIAI_CAP = [
    "phu_thuoc", "vo_gia_cu", "chu_xuong", "dia_chu", "phu_nong", "thuong_nhan",
    "tho_thu_cong", "gioi_dich_vu", "cong_nhan", "ta_dien", "co_nong", "trung_nong",
]


def doc_run(run: str):
    run_dir = DATA_DIR / run
    metrics = [json.loads(x) for x in open(run_dir / "metrics.jsonl", encoding="utf-8")]
    sinh: dict[str, dict] = {}
    snapshots: dict[int, dict] = {}
    milestones: list[dict] = []
    chronicles: list[dict] = []
    for line in open(run_dir / "events.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if e["loai"] == "sinh":
            sinh[e["id"]] = e
        elif e["loai"] == "giai_cap_snapshot":
            snapshots[e["tick"]] = e["du_lieu"]
        elif e["loai"] == "milestone":
            milestones.append(e)
        elif e["loai"] == "chronicle":
            chronicles.append(e)
    return metrics, sinh, snapshots, milestones, chronicles


def snap_gan(snapshots: dict[int, dict], tick: int):
    if not snapshots:
        return None
    t = min(snapshots, key=lambda x: abs(x - tick))
    return snapshots[t] if abs(t - tick) <= 10 else None


def ma_tran_dich_chuyen(sinh, snapshots) -> tuple[np.ndarray, int]:
    """Cha lúc con 16 tuổi × con lúc con 40 tuổi (12×12)."""
    mt = np.zeros((len(GIAI_CAP), len(GIAI_CAP)))
    n = 0
    for cid, e in sinh.items():
        if e.get("khoi_tao") or not e.get("cha"):
            continue
        t_sinh = e["tick"]
        s16 = snap_gan(snapshots, t_sinh + 32)
        s40 = snap_gan(snapshots, t_sinh + 80)
        if not s16 or not s40:
            continue
        cha = s16.get(e["cha"]) or s16.get(e["me"] or "")
        con = s40.get(cid)
        if not cha or not con:
            continue
        i = GIAI_CAP.index(cha[0]) if cha[0] in GIAI_CAP else -1
        j = GIAI_CAP.index(con[0]) if con[0] in GIAI_CAP else -1
        if i >= 0 and j >= 0:
            mt[i, j] += 1
            n += 1
    return mt, n


def beta_thua_ke(sinh, snapshots) -> tuple[float, int]:
    """β hồi quy log-của-cải con (40t) theo log-của-cải cha (lúc con 16t)."""
    x, y = [], []
    for cid, e in sinh.items():
        if e.get("khoi_tao") or not e.get("cha"):
            continue
        s16 = snap_gan(snapshots, e["tick"] + 32)
        s40 = snap_gan(snapshots, e["tick"] + 80)
        if not s16 or not s40:
            continue
        cha = s16.get(e["cha"]) or s16.get(e["me"] or "")
        con = s40.get(cid)
        if not cha or not con or cha[1] <= 0 or con[1] <= 0:
            continue
        x.append(np.log(cha[1]))
        y.append(np.log(con[1]))
    if len(x) < 10:
        return float("nan"), len(x)
    return float(np.polyfit(x, y, 1)[0]), len(x)


def ve_bieu_do(metrics, run: str) -> list[str]:
    REPORT_DIR.mkdir(exist_ok=True)
    files = []
    nam = [m["nam"] for m in metrics]

    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    axes[0][0].plot(nam, [m["dan_so"] for m in metrics])
    axes[0][0].set_title("Dân số")
    axes[0][1].plot(nam, [m["gini_dat"] for m in metrics], label="đất")
    axes[0][1].plot(nam, [m["gini_thoc"] for m in metrics], label="thóc")
    axes[0][1].legend()
    axes[0][1].set_title("Gini")
    axes[1][0].plot(nam, [m["ty_le_biet_chu"] for m in metrics])
    axes[1][0].set_title("Tỷ lệ biết chữ")
    axes[1][1].plot(nam, [m.get("tri_thuc", 0) for m in metrics])
    axes[1][1].set_title("Tri thức")
    fig.tight_layout()
    f1 = REPORT_DIR / f"{run}_tong_quan.png"
    fig.savefig(f1, dpi=110)
    plt.close(fig)
    files.append(f1.name)

    # wealth share theo giai cấp (stacked) — từ đếm giai cấp
    cac_gc = GIAI_CAP
    dem = np.array([[m.get("giai_cap", {}).get(gc, 0) for gc in cac_gc] for m in metrics])
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.stackplot(nam, dem.T, labels=cac_gc)
    ax.legend(loc="upper left", fontsize=7, ncols=4)
    ax.set_title("Cơ cấu giai cấp theo thời gian (số người)")
    f2 = REPORT_DIR / f"{run}_giai_cap.png"
    fig.savefig(f2, dpi=110)
    plt.close(fig)
    files.append(f2.name)
    return files


def main() -> int:
    run = sys.argv[1]
    metrics, sinh, snapshots, milestones, chronicles = doc_run(run)
    mt, n_mt = ma_tran_dich_chuyen(sinh, snapshots)
    beta, n_beta = beta_thua_ke(sinh, snapshots)
    pngs = ve_bieu_do(metrics, run)
    cuoi = metrics[-1]

    lines = [f"# Phân tích cuối run `{run}`", ""]
    lines.append(f"- Tick cuối: {cuoi['tick']} (năm {cuoi['nam']}); dân số {cuoi['dan_so']}; "
                 f"gini đất {cuoi['gini_dat']}; biết chữ {cuoi['ty_le_biet_chu']:.0%}; "
                 f"tri thức {cuoi.get('tri_thuc', 0)}")
    lines.append(f"- β thừa kế của cải (log-log, n={n_beta}): **{beta:.3f}**")
    cn = next((m for m in metrics if m.get("cong_nghiep_hoa")), None)
    lines.append("- Công nghiệp hóa: "
                 + (f"NĂM {cn['nam']}" if cn else "chưa đạt trong run này"))
    lines += ["", f"## Ma trận dịch chuyển giai cấp cha→con (n={n_mt})", ""]
    lines.append("| cha \\ con | " + " | ".join(GIAI_CAP) + " |")
    lines.append("|" + "---|" * (len(GIAI_CAP) + 1))
    for i, gc in enumerate(GIAI_CAP):
        if mt[i].sum() == 0:
            continue
        lines.append(f"| **{gc}** | " + " | ".join(str(int(x)) for x in mt[i]) + " |")
    lines += ["", "## Milestones", ""]
    for ms in milestones:
        lines.append(f"- Năm {ms['tick'] // 2}: {ms['ten']}")
    lines += ["", "## Sử ký (chronicle)", ""]
    for ch in chronicles[-10:]:
        lines.append(f"> {ch['van']}")
        lines.append("")
    lines += ["## Biểu đồ", ""] + [f"![{p}]({p})" for p in pngs]
    ra = REPORT_DIR / "final_analysis.md"
    ra.write_text("\n".join(lines), encoding="utf-8")
    print(f"[xong] {ra} + {len(pngs)} PNG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
