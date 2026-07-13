"""tools/social_graph — xuất đồ thị xã hội của một run ra JSON/GraphML (CHỈ ĐỌC).

  python -m tools.social_graph data/runs/<ten_run> [--tick T] [--graphml] [--include-dead]

Nạp checkpoint pickle gần T nhất (World.nap_checkpoint) rồi dựng đồ thị:
  - nodes: mỗi agent (mặc định chỉ người còn sống) với
    {id, ten, tuoi, gioi_tinh, lang, e_bac, thoc, so_thua}
  - edges: {a, b, w, loai} — loai là danh sách nhãn gộp cho từng cặp:
    vo_chong | cha_con | giam_ho | hop_dong (đang hiệu lực) | quan_he (w.quan_he ≠ 0);
    w là trọng số quan hệ trong w.quan_he (0 nếu cặp chưa có mục nào).

Ghi reports/social_graph/graph_<run>_<tick>.json; --graphml ghi thêm bản .graphml
cùng tên cho Gephi. Tool chỉ đọc checkpoint — không sửa trạng thái thế giới nào.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "reports" / "social_graph"


def tim_run_dir(ten: str) -> Path | None:
    """data/runs/<ten> hoặc đường dẫn trực tiếp."""
    ung_vien = [Path(ten), REPO / ten, REPO / "data" / "runs" / ten]
    for p in ung_vien:
        if p.is_dir():
            return p
    return None


def chon_checkpoint(run_dir: Path, tick: int | None) -> Path | None:
    """Checkpoint có tick gần T nhất (tie-break: tick nhỏ hơn); không có T → mới nhất."""
    rx = re.compile(r"checkpoint_(\d+)\.pkl$")
    cks: list[tuple[int, Path]] = []
    for p in sorted((run_dir / "checkpoints").glob("checkpoint_*.pkl")):
        m = rx.search(p.name)
        if m:
            cks.append((int(m.group(1)), p))
    if not cks:
        return None
    if tick is None:
        return max(cks)[1]
    return min(cks, key=lambda tp: (abs(tp[0] - tick), tp[0]))[1]


def dung_do_thi(w: Any, include_dead: bool) -> dict[str, Any]:
    """Dựng {tick, nam, nodes, edges} từ World — tất định (mọi duyệt đều sorted)."""
    chon = {aid for aid, a in w.agents.items() if include_dead or a.con_song}

    nodes: list[dict[str, Any]] = []
    for aid in sorted(chon):
        a = w.agents[aid]
        so_thua = sum(1 for p in w.parcels.values() if p.chu == aid)
        nodes.append({
            "id": a.id, "ten": a.ten, "tuoi": round(a.tuoi_nam, 1),
            "gioi_tinh": a.gioi_tinh, "lang": a.lang, "e_bac": a.e_bac,
            "thoc": round(w.ledger.so_du(aid, "thoc"), 2), "so_thua": so_thua,
        })

    # gộp nhãn theo cặp (a, b) chuẩn hóa a < b
    loai_cap: dict[tuple[str, str], set[str]] = {}

    def them(x: str, y: str, loai: str) -> None:
        if x in chon and y in chon and x != y:
            loai_cap.setdefault((min(x, y), max(x, y)), set()).add(loai)

    for aid in sorted(chon):
        a = w.agents[aid]
        if a.vo_chong:
            them(aid, a.vo_chong, "vo_chong")
        for pid in (a.cha, a.me):
            if pid:
                them(aid, pid, "cha_con")
        if a.giam_ho:
            them(aid, a.giam_ho, "giam_ho")
        for cid in a.con_nuoi:
            them(aid, cid, "giam_ho")

    for hid in sorted(w.hop_dong):
        hd = w.hop_dong[hid]
        if getattr(hd, "trang_thai", "") != "hieu_luc":
            continue
        ben = sorted(set(hd.cac_ben) & chon)
        for i, x in enumerate(ben):
            for y in ben[i + 1:]:
                them(x, y, "hop_dong")

    for (x, y), trong_so in sorted(w.quan_he.items()):
        if trong_so != 0:
            them(x, y, "quan_he")

    edges = [
        {"a": x, "b": y, "w": round(w.quan_he.get((x, y), 0.0), 4),
         "loai": sorted(loai)}
        for (x, y), loai in sorted(loai_cap.items())
    ]
    return {"tick": w.tick, "nam": w.nam(), "nodes": nodes, "edges": edges}


def _gml_key(kid: str, kfor: str, ktype: str) -> str:
    return f'  <key id="{kid}" for="{kfor}" attr.name="{kid}" attr.type="{ktype}"/>'


def ghi_graphml(do_thi: dict[str, Any], duong: Path) -> None:
    """GraphML tối giản cho Gephi — không phụ thuộc networkx."""
    dong = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for kid, ktype in [("ten", "string"), ("tuoi", "double"), ("gioi_tinh", "string"),
                       ("lang", "int"), ("e_bac", "int"), ("thoc", "double"),
                       ("so_thua", "int")]:
        dong.append(_gml_key(kid, "node", ktype))
    dong.append(_gml_key("w", "edge", "double"))
    dong.append(_gml_key("loai", "edge", "string"))
    dong.append('  <graph edgedefault="undirected">')
    for n in do_thi["nodes"]:
        dong.append(f'    <node id="{escape(n["id"])}">')
        for k in ("ten", "tuoi", "gioi_tinh", "lang", "e_bac", "thoc", "so_thua"):
            dong.append(f'      <data key="{k}">{escape(str(n[k]))}</data>')
        dong.append("    </node>")
    for e in do_thi["edges"]:
        dong.append(f'    <edge source="{escape(e["a"])}" target="{escape(e["b"])}">')
        dong.append(f'      <data key="w">{e["w"]}</data>')
        dong.append(f'      <data key="loai">{escape("|".join(e["loai"]))}</data>')
        dong.append("    </edge>")
    dong += ["  </graph>", "</graphml>", ""]
    duong.write_text("\n".join(dong), encoding="utf-8")


def xuat_do_thi(run_dir: Path, tick: int | None = None, graphml: bool = False,
                include_dead: bool = False) -> tuple[dict[str, Any], Path]:
    """Nạp checkpoint gần tick nhất, dựng đồ thị, ghi JSON (+GraphML). Trả (đồ thị, path)."""
    from engine.world import World

    ck = chon_checkpoint(run_dir, tick)
    if ck is None:
        raise FileNotFoundError(f"Run {run_dir.name} không có checkpoint nào "
                                f"trong {run_dir / 'checkpoints'}")
    w = World.nap_checkpoint(ck)
    do_thi = dung_do_thi(w, include_dead)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    duong = OUT_DIR / f"graph_{run_dir.name}_{w.tick:04d}.json"
    duong.write_text(json.dumps(do_thi, ensure_ascii=False, indent=1), encoding="utf-8")
    if graphml:
        ghi_graphml(do_thi, duong.with_suffix(".graphml"))
    return do_thi, duong


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Xuất đồ thị xã hội từ checkpoint (chỉ đọc)")
    ap.add_argument("run", help="data/runs/<ten_run> hoặc tên run")
    ap.add_argument("--tick", type=int, default=None,
                    help="lấy checkpoint gần tick này nhất (mặc định: mới nhất)")
    ap.add_argument("--graphml", action="store_true", help="ghi thêm bản .graphml cho Gephi")
    ap.add_argument("--include-dead", action="store_true",
                    help="giữ cả agent đã chết (mặc định chỉ người còn sống)")
    args = ap.parse_args(argv)

    run_dir = tim_run_dir(args.run)
    if run_dir is None:
        print(f"Không tìm thấy run: {args.run}")
        return 2
    try:
        do_thi, duong = xuat_do_thi(run_dir, args.tick, args.graphml, args.include_dead)
    except FileNotFoundError as e:
        print(str(e))
        return 2
    print(f"Run {run_dir.name} tick {do_thi['tick']} (năm {do_thi['nam']}): "
          f"{len(do_thi['nodes'])} node, {len(do_thi['edges'])} cạnh.")
    print(f"Đã ghi: {duong.relative_to(REPO)}"
          + (f" + {duong.with_suffix('.graphml').name}" if args.graphml else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
