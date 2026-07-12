"""Phân tích telemetry LLM từ llm_calls.sqlite — token, chi phí, phân tải key, latency.

CLI: python -m tools.telemetry data/runs/<run>
Sinh: reports/telemetry.md + telemetry.json. Gọi được từ run.py cuối phiên.

Mọi thống kê rút TRỰC TIẾP từ bảng llm_calls (điều luật #6 — mọi call đều có vết):
tick, tier, provider, model, key_hash, batch_size, tok_in, tok_out, latency_ms,
retries (vòng agentic = số lượt công cụ), fallback, raw.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


def _gia_model(model: str, bang_gia: dict) -> dict:
    """Khớp giá theo chuỗi con dài nhất trong tên model; không khớp → mặc định."""
    khop = [(k, v) for k, v in bang_gia.items() if k != "mac_dinh" and k in model]
    if khop:
        khop.sort(key=lambda kv: -len(kv[0]))
        return khop[0][1]
    return bang_gia.get("mac_dinh", {"vao": 0.0, "ra": 0.0})


def phan_tich(sqlite_path: Path, bang_gia: dict | None = None) -> dict[str, Any]:
    bang_gia = bang_gia or {"mac_dinh": {"vao": 0.0, "ra": 0.0}}
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT tick, tier, provider, model, key_hash, tok_in, tok_out, latency_ms,"
        " retries, fallback FROM llm_calls"))
    conn.close()
    if not rows:
        return {"tong_call": 0}

    tong = {"tong_call": len(rows), "tok_in": 0, "tok_out": 0, "fallback": 0,
            "luot_cong_cu": 0, "chi_phi_usd": 0.0}
    theo_tier: dict[str, dict] = {}
    theo_model: dict[str, dict] = {}
    theo_key: dict[str, int] = {}
    latency: list[int] = []
    for r in rows:
        ti, to = int(r["tok_in"] or 0), int(r["tok_out"] or 0)
        tong["tok_in"] += ti
        tong["tok_out"] += to
        tong["fallback"] += int(r["fallback"] or 0)
        tong["luot_cong_cu"] += max(0, int(r["retries"] or 0))
        gia = _gia_model(r["model"] or "", bang_gia)
        chi_phi = ti / 1e6 * gia["vao"] + to / 1e6 * gia["ra"]
        tong["chi_phi_usd"] += chi_phi
        lat = int(r["latency_ms"] or 0)
        if lat > 0:
            latency.append(lat)
        for bang, khoa in ((theo_tier, r["tier"]), (theo_model, r["model"])):
            d = bang.setdefault(khoa or "?", {"call": 0, "tok_in": 0, "tok_out": 0,
                                              "chi_phi_usd": 0.0, "fallback": 0})
            d["call"] += 1
            d["tok_in"] += ti
            d["tok_out"] += to
            d["chi_phi_usd"] += chi_phi
            d["fallback"] += int(r["fallback"] or 0)
        if r["key_hash"]:
            theo_key[r["key_hash"]] = theo_key.get(r["key_hash"], 0) + 1

    latency.sort()
    def pct(p: float) -> int:
        return latency[min(len(latency) - 1, int(len(latency) * p))] if latency else 0

    return {
        **tong,
        "chi_phi_usd": round(tong["chi_phi_usd"], 4),
        "tok_tong": tong["tok_in"] + tong["tok_out"],
        "fallback_rate": round(tong["fallback"] / len(rows), 4),
        "latency_ms": {"trung_binh": round(sum(latency) / len(latency)) if latency else 0,
                       "p50": pct(0.5), "p90": pct(0.9), "p99": pct(0.99),
                       "max": latency[-1] if latency else 0},
        "theo_tier": {k: {**v, "chi_phi_usd": round(v["chi_phi_usd"], 4)}
                      for k, v in sorted(theo_tier.items())},
        "theo_model": {k: {**v, "chi_phi_usd": round(v["chi_phi_usd"], 4)}
                       for k, v in sorted(theo_model.items())},
        "phan_tai_key": {  # phân phối call theo key — chứng minh least-loaded trải đều
            "so_key_dung": len(theo_key),
            "call_moi_key": dict(sorted(theo_key.items(), key=lambda kv: -kv[1])),
            "lech_max_min": (max(theo_key.values()) - min(theo_key.values())) if theo_key else 0,
        },
    }


def viet_md(kq: dict, run_name: str) -> str:
    if kq.get("tong_call", 0) == 0:
        return f"# Telemetry LLM — `{run_name}`\n\n(không có call nào trong llm_calls.sqlite)\n"
    d = [f"# Telemetry LLM — run `{run_name}`", ""]
    d.append(f"- **Tổng call:** {kq['tong_call']:,} · fallback {kq['fallback_rate']:.2%} "
             f"({kq['fallback']}) · lượt gọi công cụ MCP {kq['luot_cong_cu']:,}")
    d.append(f"- **Token:** vào {kq['tok_in']:,} + ra {kq['tok_out']:,} = "
             f"**{kq['tok_tong']:,}** · ước tính **${kq['chi_phi_usd']:.4f}** (giá xấp xỉ, cấu hình được)")
    lm = kq["latency_ms"]
    d.append(f"- **Latency (ms):** tb {lm['trung_binh']} · p50 {lm['p50']} · "
             f"p90 {lm['p90']} · p99 {lm['p99']} · max {lm['max']}")
    pk = kq["phan_tai_key"]
    d.append(f"- **Phân tải key:** dùng {pk['so_key_dung']} key · lệch nhiều-ít "
             f"{pk['lech_max_min']} call (thấp = trải đều tốt)")
    d += ["", "## Theo tier", "", "| tier | call | tok vào | tok ra | $ | fallback |",
          "|---|---|---|---|---|---|"]
    for k, v in kq["theo_tier"].items():
        d.append(f"| {k} | {v['call']:,} | {v['tok_in']:,} | {v['tok_out']:,} | "
                 f"${v['chi_phi_usd']:.4f} | {v['fallback']} |")
    d += ["", "## Theo model", "", "| model | call | tok vào | tok ra | $ |",
          "|---|---|---|---|---|"]
    for k, v in kq["theo_model"].items():
        d.append(f"| {k} | {v['call']:,} | {v['tok_in']:,} | {v['tok_out']:,} | "
                 f"${v['chi_phi_usd']:.4f} |")
    d += ["", "## Phân tải key (call/key — least-loaded)", ""]
    for kh, n in pk["call_moi_key"].items():
        d.append(f"- `{kh}`: {n:,} call")
    return "\n".join(d) + "\n"


def sinh_bao_cao(run_dir: Path, bang_gia: dict | None = None) -> dict:
    """Đọc llm_calls.sqlite → ghi reports/telemetry.md + telemetry.json. Trả kết quả."""
    sq = run_dir / "llm_calls.sqlite"
    if not sq.exists():
        return {"tong_call": 0}
    kq = phan_tich(sq, bang_gia)
    rp = run_dir / "reports"
    rp.mkdir(exist_ok=True)
    (rp / "telemetry.md").write_text(viet_md(kq, run_dir.name), encoding="utf-8")
    (rp / "telemetry.json").write_text(
        json.dumps(kq, ensure_ascii=False, indent=2), encoding="utf-8")
    return kq


def main() -> int:
    if len(sys.argv) < 2:
        print("dùng: python -m tools.telemetry data/runs/<run>")
        return 2
    run_dir = Path(sys.argv[1])
    try:
        from engine.config import load_config
        bang_gia = load_config().get("models.gia_token")
    except Exception:  # noqa: BLE001 — chạy độc lập không cần config vẫn được (chỉ mất giá)
        bang_gia = None
    kq = sinh_bao_cao(run_dir, bang_gia)
    print(viet_md(kq, run_dir.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
