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
    """Đọc-only. Sau ADR 0006 §C.1, một row có thể bị ``superseded=1`` (đoạn quỹ đạo bị bỏ
    khi resume) — row đó **vẫn đã tốn tiền thật** nên KHÔNG bị xóa và vẫn vào chi phí.

    Hai đại lượng phải phân biệt:
    - ``call_burned`` = MỌI row  → chi phí/quota đã tiêu (ngữ nghĩa cũ của ``tong_call``);
    - ``call_effective`` = ``COALESCE(superseded,0)=0`` → số call trên quỹ đạo được công bố.

    DB cũ không có cột ``superseded`` ⇒ ``PRAGMA table_info`` guard, coi mọi row là effective.
    Read path KHÔNG BAO GIỜ ``ALTER TABLE``.
    """
    bang_gia = bang_gia or {"mac_dinh": {"vao": 0.0, "ra": 0.0}}
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cot = {r[1] for r in conn.execute("PRAGMA table_info(llm_calls)")}
    sup = "COALESCE(superseded,0)" if "superseded" in cot else "0"
    rows = list(conn.execute(
        "SELECT tick, tier, provider, model, key_hash, tok_in, tok_out, latency_ms,"
        f" retries, fallback, {sup} AS superseded FROM llm_calls"))  # noqa: S608
    conn.close()
    if not rows:
        return {"tong_call": 0, "call_burned": 0, "call_effective": 0}

    hieu_luc = [r for r in rows if not int(r["superseded"] or 0)]
    tong = {"tong_call": len(rows), "tok_in": 0, "tok_out": 0, "fallback": 0,
            "luot_cong_cu": 0, "chi_phi_usd": 0.0,
            # chi phí = mọi row (điều luật #6: không làm đẹp chi phí);
            # quỹ đạo = row chưa bị supersede (số đi vào bảng kết quả khoa học)
            "call_burned": len(rows), "call_effective": len(hieu_luc),
            "call_superseded": len(rows) - len(hieu_luc),
            "fallback_effective": sum(int(r["fallback"] or 0) for r in hieu_luc),
            "fallback_rate_effective": (
                round(sum(int(r["fallback"] or 0) for r in hieu_luc) / len(hieu_luc), 4)
                if hieu_luc else 0.0),
            "tok_in_effective": sum(int(r["tok_in"] or 0) for r in hieu_luc),
            "tok_out_effective": sum(int(r["tok_out"] or 0) for r in hieu_luc)}
    theo_tier: dict[str, dict] = {}
    theo_model: dict[str, dict] = {}
    theo_key: dict[str, dict[str, int]] = {}  # provider → {key_hash: call} (tách nhà cung cấp)
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
            pk = theo_key.setdefault(r["provider"] or "?", {})
            pk[r["key_hash"]] = pk.get(r["key_hash"], 0) + 1

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
        # phân phối call theo key, TÁCH nhà cung cấp (aistudio nhiều key vs 9router 1 key):
        # lệch max-min CHỈ tính trong pool nhiều-key mới có nghĩa (chứng minh least-loaded)
        "phan_tai_key": {
            prov: {
                "so_key": len(keys),
                "call_moi_key": dict(sorted(keys.items(), key=lambda kv: -kv[1])),
                "lech_max_min": (max(keys.values()) - min(keys.values())) if keys else 0,
            }
            for prov, keys in sorted(theo_key.items())
        },
    }


def phan_tich_ngan_sach_tick(run_dir: Path) -> dict[str, Any]:
    """Đọc-only audit cho treatment LLM 1..N **mỗi agent**.

    ``llm_calls.sqlite`` ghi outcome logic; số request thực (retry/MCP cũng
    tính) nằm trong metrics tick.  Vì vậy phép kiểm này lấy metrics làm nguồn
    chuẩn, rồi dùng ``batch_size`` trong SQLite để chứng minh không dồn nhiều
    cư dân vào một decision call.
    """
    metrics_path = run_dir / "metrics.jsonl"
    if not metrics_path.exists():
        return {"ap_dung": False, "ly_do": "khong_co_metrics"}
    rows: list[tuple[int, dict[str, Any]]] = []
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        metric = json.loads(line)
        llm = metric.get("llm")
        if isinstance(llm, dict) and llm.get("api_call_scope") == "moi_agent":
            rows.append((int(metric.get("tick", 0)), llm))
    if not rows:
        return {"ap_dung": False, "ly_do": "treatment_khong_bat"}

    tong_request = 0
    tong_agent_tick = 0
    min_tick: int | None = None
    max_tick = 0
    vi_pham_san: list[dict[str, Any]] = []
    vi_pham_tran: list[dict[str, Any]] = []
    for tick, llm in rows:
        request = int(llm.get("api_call", 0))
        tong_request += request
        min_tick = request if min_tick is None else min(min_tick, request)
        max_tick = max(max_tick, request)
        min_agent = int(llm.get("api_call_min_moi_agent", 1))
        cap_agent = int(llm.get("api_call_cap_moi_agent", 0))
        by_agent = llm.get("api_call_by_agent", {})
        if not isinstance(by_agent, dict):
            by_agent = {}
        tong_agent_tick += max(len(by_agent), int(llm.get("api_call_min_required", 0)))
        under = {
            str(aid).removeprefix("agent:")
            for aid in llm.get("api_call_min_violations", [])
        }
        under.update(str(aid) for aid, n in by_agent.items() if int(n) < min_agent)
        if llm.get("api_call_min_met") is False and not under:
            under.add("<khong-xac-dinh>")
        for aid in sorted(under):
            vi_pham_san.append({"tick": tick, "agent": aid})
        if cap_agent > 0:
            for aid, n in sorted(by_agent.items()):
                if int(n) > cap_agent:
                    vi_pham_tran.append({"tick": tick, "agent": str(aid), "call": int(n)})

    batch_vi_pham: list[dict[str, int]] = []
    sqlite_path = run_dir / "llm_calls.sqlite"
    if sqlite_path.exists():
        conn = sqlite3.connect(sqlite_path)
        try:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(llm_calls)")}
            if "batch_size" in columns:
                for tick, max_batch in conn.execute(
                    "SELECT tick, MAX(batch_size) FROM llm_calls GROUP BY tick"
                ):
                    if int(max_batch or 0) > 1:
                        batch_vi_pham.append({"tick": int(tick), "batch_size": int(max_batch)})
        finally:
            conn.close()

    return {
        "ap_dung": True,
        "scope": "moi_agent",
        "so_tick": len(rows),
        "agent_tick": tong_agent_tick,
        "request_total": tong_request,
        "request_moi_tick": {"min": min_tick or 0, "max": max_tick},
        "vi_pham_san": vi_pham_san,
        "vi_pham_tran": vi_pham_tran,
        "vi_pham_batch": batch_vi_pham,
        "dat": not (vi_pham_san or vi_pham_tran or batch_vi_pham),
    }


def viet_md(kq: dict, run_name: str) -> str:
    if kq.get("tong_call", 0) == 0:
        return f"# Telemetry LLM — `{run_name}`\n\n(không có call nào trong llm_calls.sqlite)\n"
    d = [f"# Telemetry LLM — run `{run_name}`", ""]
    d.append(f"- **Tổng call:** {kq['tong_call']:,} · fallback {kq['fallback_rate']:.2%} "
             f"({kq['fallback']}) · retry/lượt-công-cụ {kq['luot_cong_cu']:,} "
              f"(cột retries: MCP tắt = số retry; MCP bật = số lượt gọi công cụ)")
    ngan_sach = kq.get("ngan_sach_tick")
    if isinstance(ngan_sach, dict) and ngan_sach.get("ap_dung"):
        ket = "PASS" if ngan_sach.get("dat") else "FAIL"
        tick_range = ngan_sach.get("request_moi_tick", {})
        d.append(
            f"- **Autonomy budget mỗi agent:** **{ket}** · "
            f"{ngan_sach['so_tick']:,} tick · {ngan_sach['agent_tick']:,} agent-tick · "
            f"{ngan_sach['request_total']:,} request · request/tick "
            f"{tick_range.get('min', 0):,}–{tick_range.get('max', 0):,} · "
            f"vi phạm sàn/trần/batch = {len(ngan_sach['vi_pham_san'])}/"
            f"{len(ngan_sach['vi_pham_tran'])}/{len(ngan_sach['vi_pham_batch'])}."
        )
    if kq.get("call_superseded"):
        d.append(f"- **Chi phí vs quỹ đạo** (ADR 0006 §C.1): `call_burned` "
                 f"{kq['call_burned']:,} (đã trả tiền, KHÔNG xóa) · `call_effective` "
                 f"{kq['call_effective']:,} (trên quỹ đạo) · superseded "
                 f"{kq['call_superseded']:,} (đoạn bị bỏ khi resume)")
    d.append(f"- **Token:** vào {kq['tok_in']:,} + ra {kq['tok_out']:,} = "
             f"**{kq['tok_tong']:,}** · ước tính **${kq['chi_phi_usd']:.4f}** (giá xấp xỉ, cấu hình được)")
    lm = kq["latency_ms"]
    d.append(f"- **Latency (ms):** tb {lm['trung_binh']} · p50 {lm['p50']} · "
             f"p90 {lm['p90']} · p99 {lm['p99']} · max {lm['max']}")
    pk = kq["phan_tai_key"]
    tom = " · ".join(f"{prov} {v['so_key']} key (lệch {v['lech_max_min']})"
                     for prov, v in pk.items())
    d.append(f"- **Phân tải key** (tách nhà cung cấp): {tom} — lệch thấp trong pool nhiều-key "
             f"= least-loaded trải đều")
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
    d += ["", "## Phân tải key (call/key — least-loaded, tách nhà cung cấp)", ""]
    for prov, v in pk.items():
        d.append(f"**{prov}** ({v['so_key']} key, lệch max-min {v['lech_max_min']}):")
        d.append("  " + " · ".join(f"`{kh}`={n}" for kh, n in v["call_moi_key"].items()))
    return "\n".join(d) + "\n"


def sinh_bao_cao(run_dir: Path, bang_gia: dict | None = None) -> dict:
    """Đọc llm_calls.sqlite → ghi reports/telemetry.md + telemetry.json. Trả kết quả."""
    sq = run_dir / "llm_calls.sqlite"
    if not sq.exists():
        return {"tong_call": 0}
    kq = phan_tich(sq, bang_gia)
    kq["ngan_sach_tick"] = phan_tich_ngan_sach_tick(run_dir)
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
