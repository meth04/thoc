"""Render video timelapse 9:16 offline từ log + checkpoint (SPEC 10).

  python -m viz.render_video mock300 --last-years 60 --out demo.mp4 [--fps 30]

Bản đồ giữa (màu theo giai cấp chủ thửa), "Năm N", panel wealth-share + dân số,
caption milestones/chronicle. 2 frame/tick; bản đồ cập nhật theo checkpoint 10-tick.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"

MAU_GIAI_CAP = {
    "phu_thuoc": (150, 150, 150), "vo_gia_cu": (60, 60, 60),
    "chu_xuong": (170, 40, 200), "dia_chu": (200, 40, 40), "phu_nong": (230, 120, 40),
    "thuong_nhan": (240, 200, 60), "tho_thu_cong": (90, 170, 220),
    "gioi_dich_vu": (120, 220, 220), "cong_nhan": (40, 90, 220),
    "ta_dien": (170, 130, 90), "co_nong": (120, 90, 60), "trung_nong": (70, 170, 70),
}
MAU_O = {"ruong": (46, 110, 50), "rung": (24, 70, 30), "doi": (110, 95, 70),
         "mo_dong": (140, 120, 60), "song": (50, 90, 160)}
MAU_ENTITY = (255, 0, 255)

W, H = 1080, 1920


def doc_du_lieu(run: str):
    run_dir = DATA_DIR / run
    metrics = [json.loads(x) for x in open(run_dir / "metrics.jsonl", encoding="utf-8")]
    milestones, chronicles, snapshots = [], [], {}
    for line in open(run_dir / "events.jsonl", encoding="utf-8"):
        e = json.loads(line)
        if e["loai"] == "milestone":
            milestones.append(e)
        elif e["loai"] == "chronicle":
            chronicles.append(e)
        elif e["loai"] == "giai_cap_snapshot":
            snapshots[e["tick"]] = e["du_lieu"]
    checkpoints = sorted((run_dir / "checkpoints").glob("checkpoint_0*.pkl"))
    return metrics, milestones, chronicles, snapshots, checkpoints


def ve_frame(font, font_to, font_nho, m, parcels, giai_cap_snap, caption: str):
    surf = pygame.Surface((W, H))
    surf.fill((16, 16, 24))
    # tiêu đề năm
    surf.blit(font_to.render(f"Năm {m['nam']}", True, (255, 255, 255)), (40, 40))
    surf.blit(font_nho.render(
        f"dân số {m['dan_so']} · biết chữ {m['ty_le_biet_chu']:.0%} · "
        f"gini đất {m['gini_dat']:.2f} · máy {m.get('so_may', 0):.0f}",
        True, (200, 200, 210)), (40, 130))

    # bản đồ 30×30 giữa màn hình
    o = 32
    x0, y0 = (W - 30 * o) // 2, 220
    for p in parcels:
        r, c, loai, chu = p
        mau = MAU_O.get(loai, (40, 40, 40))
        if chu:
            if chu.startswith("E"):
                mau = MAU_ENTITY
            else:
                gc = (giai_cap_snap.get(chu) or ["trung_nong"])[0]
                mau = MAU_GIAI_CAP.get(gc, (70, 170, 70))
        pygame.draw.rect(surf, mau, (x0 + c * o, y0 + r * o, o - 1, o - 1))

    # panel dưới: cơ cấu giai cấp (stacked bar) + chú thích
    y1 = y0 + 30 * o + 50
    gc_dem = m.get("giai_cap", {})
    tong = sum(gc_dem.values()) or 1
    x = 40
    for gc, so in sorted(gc_dem.items(), key=lambda kv: -kv[1]):
        w_bar = int((W - 80) * so / tong)
        pygame.draw.rect(surf, MAU_GIAI_CAP.get(gc, (99, 99, 99)), (x, y1, w_bar, 46))
        x += w_bar
    surf.blit(font_nho.render("cơ cấu giai cấp", True, (180, 180, 190)), (40, y1 + 56))
    y2 = y1 + 110
    for i, (gc, so) in enumerate(sorted(gc_dem.items(), key=lambda kv: -kv[1])[:6]):
        pygame.draw.rect(surf, MAU_GIAI_CAP.get(gc, (99, 99, 99)),
                         (40 + (i % 3) * 340, y2 + (i // 3) * 44, 26, 26))
        surf.blit(font_nho.render(f"{gc} {so}", True, (210, 210, 220)),
                  (76 + (i % 3) * 340, y2 + (i // 3) * 44))

    # caption sử ký / milestone
    if caption:
        y3 = y2 + 130
        for i, dong in enumerate(_ngat_dong(caption, 52)[:5]):
            surf.blit(font.render(dong, True, (255, 230, 150)), (40, y3 + i * 44))
    return surf


def _ngat_dong(text: str, do_dai: int) -> list[str]:
    tu, dong, ket_qua = text.split(), "", []
    for t in tu:
        if len(dong) + len(t) + 1 > do_dai:
            ket_qua.append(dong)
            dong = t
        else:
            dong = (dong + " " + t).strip()
    if dong:
        ket_qua.append(dong)
    return ket_qua


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name")
    ap.add_argument("--last-years", type=int, default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default="demo.mp4")
    args = ap.parse_args()

    pygame.init()
    pygame.font.init()
    font = pygame.font.SysFont("arial", 34)
    font_to = pygame.font.SysFont("arial", 72, bold=True)
    font_nho = pygame.font.SysFont("arial", 30)

    metrics, milestones, chronicles, snapshots, checkpoints = doc_du_lieu(args.run_name)
    if args.last_years:
        tick_dau = max(1, metrics[-1]["tick"] - args.last_years * 2)
        metrics = [m for m in metrics if m["tick"] >= tick_dau]

    # nạp bản đồ từ checkpoint gần nhất cho từng mốc 10-tick
    ban_do_theo_tick: dict[int, list] = {}
    for ck in checkpoints:
        try:
            w = pickle.load(open(ck, "rb"))
        except Exception:  # noqa: BLE001 — checkpoint hỏng thì bỏ, dùng mốc kế
            continue
        ban_do_theo_tick[w.tick] = [
            (p.r, p.c, p.loai, p.chu or "") for p in w.parcels.values()
        ]
    if not ban_do_theo_tick:
        raise SystemExit("không có checkpoint để vẽ bản đồ")
    cac_moc = sorted(ban_do_theo_tick)

    frame_dir = DATA_DIR / args.run_name / "frames"
    frame_dir.mkdir(exist_ok=True)
    for f in frame_dir.glob("*.png"):
        f.unlink()

    caption = ""
    for i, m in enumerate(metrics):
        tick = m["tick"]
        moc = max((t for t in cac_moc if t <= tick), default=cac_moc[0])
        snap_tick = max((t for t in snapshots if t <= tick), default=None)
        snap = snapshots.get(snap_tick, {}) if snap_tick else {}
        ms_moi = [x for x in milestones if x["tick"] == tick]
        ch_moi = [x for x in chronicles if x["tick"] == tick]
        if ms_moi:
            caption = "★ " + ms_moi[0]["ten"].replace("_", " ")
        elif ch_moi:
            caption = ch_moi[0]["van"]
        surf = ve_frame(font, font_to, font_nho, m, ban_do_theo_tick[moc], snap, caption)
        for j in range(2):  # 2 frame/tick
            pygame.image.save(surf, str(frame_dir / f"f{i * 2 + j:06d}.png"))

    # ghép mp4 bằng ffmpeg đóng gói sẵn
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    out = Path(args.out)
    subprocess.run([
        ffmpeg, "-y", "-framerate", str(args.fps),
        "-i", str(frame_dir / "f%06d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ], check=True, capture_output=True)
    print(f"[xong] {out} ({len(metrics) * 2} frames @ {args.fps}fps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
