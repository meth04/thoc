"""Phân tích telemetry LLM từ llm_calls.sqlite — token, chi phí, phân tải key, latency.

CLI: python -m tools.telemetry data/runs/<run>
Sinh: reports/telemetry.md + telemetry.json. Gọi được từ run.py cuối phiên.

Mọi thống kê rút TRỰC TIẾP từ bảng llm_calls (điều luật #6 — mọi call đều có vết):
tick, tier, provider, model, key_hash, batch_size, tok_in, tok_out, latency_ms,
retries (số vòng sửa JSON), fallback, raw.

HAI ĐỊNH NGHĨA FALLBACK — không thay thế nhau (review v5, mục C1):

- ``fallback_call_level``: cột ``fallback`` trong llm_calls.sqlite — call mà provider
  trả lỗi/hết đường. Đo SỨC KHỎE HẠ TẦNG per-call.
- ``fallback_decision_level``: từ ``decision_provenance.plans`` trong metrics.jsonl —
  agent-tick được xếp lịch nghĩ bằng LLM/mock nhưng kế hoạch cuối cùng rơi về
  rulebot/thẻ chính sách. Đo ĐỘ PHỦ QUYẾT ĐỊNH của thí nghiệm hành vi; đây là con số
  phải công bố cạnh mọi bảng kết quả.
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
    # ``retries`` is a legacy aggregate. New accounting writes the three counters
    # separately; old artifacts retain their documented JSON-repair interpretation.
    provider_retries = "COALESCE(provider_retries,0)" if "provider_retries" in cot else "0"
    json_repairs = (
        "COALESCE(json_repair_retries,retries,0)"
        if "json_repair_retries" in cot else "COALESCE(retries,0)"
    )
    tool_turns = "COALESCE(tool_turns,0)" if "tool_turns" in cot else "0"
    rows = list(conn.execute(
        "SELECT tick, tier, provider, model, key_hash, tok_in, tok_out, latency_ms,"
        f" retries, fallback, {sup} AS superseded, {provider_retries} AS provider_retries,"
        f" {json_repairs} AS json_repair_retries, {tool_turns} AS tool_turns FROM llm_calls"))  # noqa: S608
    # A logical LLM response may contain several local function calls, while a
    # physical provider turn is one HTTP attempt.  Read both without forcing a
    # migration on historic artifacts and retain the old logical counter below.
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    physical_turns = {"tool_turn_burned": 0, "tool_turn_effective": 0,
                      "decision_turn_burned": 0, "decision_turn_effective": 0}
    if "llm_attempts" in tables:
        attempt_columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_attempts)")}
        if {"source", "attempt_started"} <= attempt_columns:
            attempt_sup = "COALESCE(superseded,0)" if "superseded" in attempt_columns else "0"
            for source, started, superseded in conn.execute(
                "SELECT source, attempt_started, "
                f"{attempt_sup} AS superseded FROM llm_attempts"  # noqa: S608
            ):
                if not int(started or 0):
                    continue
                if source == "tool_turn":
                    physical_turns["tool_turn_burned"] += 1
                    if not int(superseded or 0):
                        physical_turns["tool_turn_effective"] += 1
                elif source in {"decision_initial", "decision_final", "json_repair"}:
                    physical_turns["decision_turn_burned"] += 1
                    if not int(superseded or 0):
                        physical_turns["decision_turn_effective"] += 1
    conn.close()
    if not rows:
        return {"tong_call": 0, "call_burned": 0, "call_effective": 0}

    hieu_luc = [r for r in rows if not int(r["superseded"] or 0)]
    tong = {"tong_call": len(rows), "tok_in": 0, "tok_out": 0, "fallback": 0,
            # Ba counter khác nhau: retry provider, repair JSON và tool turn. Không alias
            # ``retries`` thành tool counter (review v5 C4).
            "provider_retries": 0, "json_repair_retries": 0, "tool_turns": 0,
            "legacy_retries": 0,
            # row provider='loi' (RemoteProtocolError...) không có model, không billed —
            # tách riêng thay vì gộp thành model '?' trong bảng
            "call_loi_provider": 0, "chi_phi_usd": 0.0,
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
        tong["provider_retries"] += max(0, int(r["provider_retries"] or 0))
        tong["json_repair_retries"] += max(0, int(r["json_repair_retries"] or 0))
        tong["tool_turns"] += max(0, int(r["tool_turns"] or 0))
        tong["legacy_retries"] += max(0, int(r["retries"] or 0))
        gia = _gia_model(r["model"] or "", bang_gia)
        chi_phi = ti / 1e6 * gia["vao"] + to / 1e6 * gia["ra"]
        tong["chi_phi_usd"] += chi_phi
        lat = int(r["latency_ms"] or 0)
        if lat > 0:
            latency.append(lat)
        # row lỗi provider (provider='loi', model rỗng, tok 0): đếm riêng, KHÔNG gộp
        # vào bảng model dưới nhãn '?' (review v5 C4).
        loi_provider = (r["provider"] or "") == "loi"
        if loi_provider:
            tong["call_loi_provider"] += 1
        for bang, khoa in ((theo_tier, r["tier"]), (theo_model, r["model"])):
            if bang is theo_model and loi_provider:
                continue
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
        # tên tường minh cho định nghĩa call-level (docstring module): giữ song song với
        # các khóa phẳng cũ để tool/test hiện hữu không gãy
        "fallback_call_level": {
            "so": tong["fallback"],
            "rate": round(tong["fallback"] / len(rows), 4),
            "so_effective": tong["fallback_effective"],
            "rate_effective": tong["fallback_rate_effective"],
        },
        "latency_ms": {"trung_binh": round(sum(latency) / len(latency)) if latency else 0,
                       "p50": pct(0.5), "p90": pct(0.9), "p99": pct(0.99),
                       "max": latency[-1] if latency else 0},
        "theo_tier": {k: {**v, "chi_phi_usd": round(v["chi_phi_usd"], 4)}
                      for k, v in sorted(theo_tier.items())},
        "theo_model": {k: {**v, "chi_phi_usd": round(v["chi_phi_usd"], 4)}
                       for k, v in sorted(theo_model.items())},
        # phân phối call theo key, TÁCH nhà cung cấp (aistudio nhiều key vs 9router 1 key):
        # lệch max-min CHỈ tính trong pool nhiều-key mới có nghĩa (chứng minh least-loaded)
        # ``tool_turns`` remains the backward-compatible count of logical local
        # function calls attested in LLM responses.  The separate physical count
        # is HTTP turns whose source was ``tool_turn``; one such turn can request
        # multiple tools, so the two must never be presented as interchangeable.
        "tool_calls_logical": tong["tool_turns"],
        "tool_provider_turns_physical": physical_turns["tool_turn_burned"],
        "tool_provider_turns_physical_effective": physical_turns["tool_turn_effective"],
        "decision_provider_turns_physical": physical_turns["decision_turn_burned"],
        "decision_provider_turns_physical_effective": physical_turns["decision_turn_effective"],
        "phan_tai_key": {
            prov: {
                "so_key": len(keys),
                "call_moi_key": dict(sorted(keys.items(), key=lambda kv: -kv[1])),
                "lech_max_min": (max(keys.values()) - min(keys.values())) if keys else 0,
            }
            for prov, keys in sorted(theo_key.items())
        },
    }


def phan_tich_attempt(run_dir: Path) -> dict[str, Any]:
    """Tóm tắt billability của từng HTTP attempt, không suy từ logical call.

    ``llm_calls`` là outcome logic; một response có thể bao gồm nhiều attempt provider,
    JSON repair hoặc tool turn. Những attempt đã bắt đầu nhưng lỗi giữ ``unknown`` thay
    vì bị coi là miễn phí; denial trước khi request rời process là ``not_billable``.
    """
    sqlite_path = run_dir / "llm_calls.sqlite"
    if not sqlite_path.exists():
        return {"ap_dung": False, "ly_do": "khong_co_llm_calls"}
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "llm_attempts" not in tables:
            return {"ap_dung": False, "ly_do": "schema_cu_khong_co_llm_attempts"}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(llm_attempts)")}
        superseded = "COALESCE(superseded,0)" if "superseded" in columns else "0"
        rows = list(conn.execute(
            "SELECT attempt_started, billability, status, source, "
            f"{superseded} AS superseded FROM llm_attempts"  # noqa: S608
        ))
    finally:
        conn.close()

    def _summary(selected: list[sqlite3.Row]) -> dict[str, Any]:
        by_billability: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_source: dict[str, int] = {}
        for row in selected:
            billability = str(row["billability"] or "unknown")
            status = str(row["status"] or "unknown")
            source = str(row["source"] or "unknown")
            by_billability[billability] = by_billability.get(billability, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
            by_source[source] = by_source.get(source, 0) + 1
        return {
            "total": len(selected),
            "started": sum(int(row["attempt_started"] or 0) for row in selected),
            "denied_before_start": sum(not int(row["attempt_started"] or 0) for row in selected),
            "by_billability": dict(sorted(by_billability.items())),
            "by_status": dict(sorted(by_status.items())),
            "by_source": dict(sorted(by_source.items())),
        }

    effective = [row for row in rows if not int(row["superseded"] or 0)]
    return {"ap_dung": True, "burned": _summary(rows), "effective": _summary(effective)}


def phan_tich_terminal_quyet_dinh(run_dir: Path) -> dict[str, Any]:
    """Coverage terminal/parsed từ counters per-tick, không dùng miss transcript.

    Trường chỉ tồn tại từ transcript-2 accounting. Artifact cũ được ghi là thiếu dữ
    liệu thay vì pass ngầm từ số HTTP attempt hoặc số logical call.
    """
    metrics_path = run_dir / "metrics.jsonl"
    if not metrics_path.exists():
        return {"ap_dung": False, "ly_do": "khong_co_metrics"}
    scheduled = completed = parsed = 0
    reasons: dict[str, int] = {}
    ticks: list[int] = []
    exact_ticks: list[int] = []
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            metric = json.loads(line)
        except json.JSONDecodeError:
            continue
        llm = metric.get("llm")
        if not isinstance(llm, dict) or "scheduled_agent_decision" not in llm:
            continue
        tick = int(metric.get("tick", 0))
        ticks.append(tick)
        scheduled += int(llm.get("scheduled_agent_decision", 0) or 0)
        completed += int(llm.get("completed_agent_decision_turn", 0) or 0)
        parsed += int(llm.get("parsed_agent_decision", 0) or 0)
        if llm.get("exact_one_terminal_decision") is True:
            exact_ticks.append(tick)
        for reason, count in (llm.get("terminal_reason_counts") or {}).items():
            reasons[str(reason)] = reasons.get(str(reason), 0) + int(count or 0)
    if not ticks:
        return {"ap_dung": False, "ly_do": "khong_co_terminal_counters"}
    return {
        "ap_dung": True,
        "so_tick": len(ticks),
        "scheduled_agent_decision": scheduled,
        "completed_agent_decision_turn": completed,
        "parsed_agent_decision": parsed,
        "terminal_coverage": round(completed / scheduled, 4) if scheduled else None,
        "parsed_decision_coverage": round(parsed / scheduled, 4) if scheduled else None,
        "exact_one_terminal": len(exact_ticks) == len(ticks),
        "exact_one_terminal_ticks": len(exact_ticks),
        "terminal_reason_counts": dict(sorted(reasons.items())),
    }


def phan_tich_fallback_quyet_dinh(run_dir: Path) -> dict[str, Any]:
    """Fallback DECISION-LEVEL từ ``decision_provenance`` trong metrics.jsonl (chỉ đọc).

    Khác với cột ``fallback`` của llm_calls.sqlite (call-level: provider trả lỗi trên
    một call), đây đếm AGENT-TICK mà kế hoạch cuối cùng rơi về rulebot/thẻ dù agent
    được xếp lịch nghĩ bằng LLM/mock. Mẫu số ``agent_tick_nghi`` = plans llm + mock +
    fallback; ``policy_card`` chủ động (không tốn call) và ``external`` KHÔNG vào mẫu
    số — đúng đối chiếu review v5 C1 (167/2099 = 7.96% trên real15_v5).
    """
    metrics_path = run_dir / "metrics.jsonl"
    if not metrics_path.exists():
        return {"ap_dung": False, "ly_do": "khong_co_metrics"}
    tong_fb = 0
    tong_nghi = 0
    tong_plan = 0
    theo_nguon: dict[str, int] = {}
    theo_tick: list[dict[str, Any]] = []
    co_du_lieu = False
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            metric = json.loads(line)
        except json.JSONDecodeError:
            continue  # dòng hỏng không được làm sập audit đọc-only
        dp = metric.get("decision_provenance")
        plans = dp.get("plans") if isinstance(dp, dict) else None
        if not isinstance(plans, dict):
            continue
        co_du_lieu = True
        fb = int(plans.get("fallback", 0) or 0)
        nghi = fb + int(plans.get("llm", 0) or 0) + int(plans.get("mock", 0) or 0)
        tong_fb += fb
        tong_nghi += nghi
        tong_plan += int(dp.get("plan_total", 0) or 0)
        for nguon, so in plans.items():
            theo_nguon[str(nguon)] = theo_nguon.get(str(nguon), 0) + int(so or 0)
        if fb > 0:
            theo_tick.append({
                "tick": int(metric.get("tick", 0)),
                "fallback": fb,
                "agent_tick_nghi": nghi,
                "rate": round(fb / nghi, 4) if nghi else 0.0,
            })
    if not co_du_lieu:
        return {"ap_dung": False, "ly_do": "khong_co_decision_provenance"}
    theo_tick.sort(key=lambda d: d["tick"])
    return {
        "ap_dung": True,
        "fallback_plans": tong_fb,
        "agent_tick_nghi": tong_nghi,
        "plan_total": tong_plan,
        "rate": round(tong_fb / tong_nghi, 4) if tong_nghi else 0.0,
        "plans_theo_nguon": dict(sorted(theo_nguon.items())),
        "theo_tick": theo_tick,
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
        d = [f"# Telemetry LLM — `{run_name}`", "", "(không có logical call nào trong llm_calls.sqlite)"]
        terminal = kq.get("terminal_decision_coverage")
        if isinstance(terminal, dict) and terminal.get("ap_dung"):
            d.append(
                f"- Terminal decision coverage: {terminal.get('terminal_coverage')} "
                f"({terminal['completed_agent_decision_turn']}/"
                f"{terminal['scheduled_agent_decision']}); parsed: "
                f"{terminal.get('parsed_decision_coverage')}."
            )
        attempts = kq.get("attempts")
        if isinstance(attempts, dict) and attempts.get("ap_dung"):
            d.append(f"- HTTP attempts: {attempts['burned']['total']} burned; "
                     f"billability {attempts['burned']['by_billability']}.")
        return "\n".join(d) + "\n"
    d = [f"# Telemetry LLM — run `{run_name}`", ""]
    d.append(
        f"- **Tổng logical call:** {kq['tong_call']:,} · provider_retries "
        f"{kq['provider_retries']:,} · json_repair_retries "
        f"{kq['json_repair_retries']:,} · logical tool calls {kq['tool_turns']:,}."
    )
    d.append(
        "  Logical tool calls là số function call trong response; không phải số HTTP turn."
    )
    d.append(
        f"- **Tool HTTP turns:** {kq.get('tool_provider_turns_physical', 0):,} burned · "
        f"{kq.get('tool_provider_turns_physical_effective', 0):,} effective; "
        f"decision HTTP turns {kq.get('decision_provider_turns_physical', 0):,} burned · "
        f"{kq.get('decision_provider_turns_physical_effective', 0):,} effective."
    )
    if kq.get("call_loi_provider"):
        d.append(f"- **Lỗi provider (không billed):** {kq['call_loi_provider']} call "
                 f"(row provider='loi', không có model — tách khỏi bảng model)")
    d.append("- **Fallback — hai định nghĩa, KHÔNG thay thế nhau:**")
    d.append(f"  - `fallback_call_level` (cột fallback trong llm_calls.sqlite — provider "
             f"trả lỗi trên một call): {kq['fallback_rate']:.2%} "
             f"({kq['fallback']}/{kq['tong_call']})")
    qd = kq.get("fallback_decision_level")
    if isinstance(qd, dict) and qd.get("ap_dung"):
        d.append(f"  - `fallback_decision_level` (agent-tick quyết bằng rulebot/thẻ dù "
                 f"được xếp lịch LLM/mock — decision_provenance trong metrics.jsonl): "
                 f"**{qd['rate']:.2%}** ({qd['fallback_plans']}/{qd['agent_tick_nghi']} "
                 f"agent-tick nghĩ; plan_total mọi nguồn = {qd['plan_total']:,})")
    else:
        ly_do = (qd or {}).get("ly_do", "khong_co_metrics")
        d.append(f"  - `fallback_decision_level`: không đọc được ({ly_do}) — thiếu "
                 f"decision_provenance trong metrics.jsonl")
    terminal = kq.get("terminal_decision_coverage")
    if isinstance(terminal, dict) and terminal.get("ap_dung"):
        terminal_rate = terminal.get("terminal_coverage")
        parsed_rate = terminal.get("parsed_decision_coverage")
        terminal_text = f"{terminal_rate:.2%}" if terminal_rate is not None else "N/A (0 scheduled)"
        parsed_text = f"{parsed_rate:.2%}" if parsed_rate is not None else "N/A (0 scheduled)"
        d.append(
            f"- **Terminal decision coverage:** {terminal_text} "
            f"({terminal['completed_agent_decision_turn']}/"
            f"{terminal['scheduled_agent_decision']}); parsed decision coverage: {parsed_text} "
            f"({terminal['parsed_agent_decision']}/{terminal['scheduled_agent_decision']}); "
            f"exact-one terminal={'PASS' if terminal['exact_one_terminal'] else 'FAIL'} "
            f"trên {terminal['so_tick']} tick."
        )
    else:
        d.append("- **Terminal decision coverage:** không đọc được (artifact cũ hoặc thiếu metrics).")
    attempts = kq.get("attempts")
    if isinstance(attempts, dict) and attempts.get("ap_dung"):
        burned = attempts["burned"]
        effective = attempts["effective"]
        d.append(
            f"- **HTTP attempts / billability:** burned {burned['total']:,} "
            f"(started {burned['started']:,}; {burned['by_billability']}); effective "
            f"{effective['total']:,} (started {effective['started']:,}; "
            f"{effective['by_billability']})."
        )
    elif isinstance(attempts, dict):
        d.append(f"- **HTTP attempts / billability:** không đọc được ({attempts.get('ly_do')}).")
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
    if isinstance(qd, dict) and qd.get("ap_dung") and qd.get("theo_tick"):
        d += ["", "## Phân bố decision-fallback theo tick (chỉ tick có > 0)", "",
              "| tick | fallback | agent-tick nghĩ | tỷ lệ |", "|---|---|---|---|"]
        for row in qd["theo_tick"]:
            d.append(f"| {row['tick']} | {row['fallback']} | {row['agent_tick_nghi']} | "
                     f"{row['rate']:.1%} |")
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
    if kq.get("call_loi_provider"):
        d.append("")
        d.append(f"*Lỗi provider (không billed): {kq['call_loi_provider']} call — "
                 f"không thuộc model nào, đã tách khỏi bảng trên.*")
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
    kq["fallback_decision_level"] = phan_tich_fallback_quyet_dinh(run_dir)
    kq["terminal_decision_coverage"] = phan_tich_terminal_quyet_dinh(run_dir)
    kq["attempts"] = phan_tich_attempt(run_dir)
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
