"""tools/verify_local — một lệnh kiểm tra cục bộ, KHÔNG mạng, không LLM thật.

Chạy tuần tự và báo cáo:
  1. ruff check .
  2. pytest toàn bộ (temp path trong workspace, guard mạng bật)
  3. một smoke rulebot ngắn + tools.verify_research_run (replay cùng hash + audit)
  4. validate scenario benchmark (không overclaim)

Mọi bước dùng chính interpreter đang chạy (sys.executable) nên chạy được qua
``conda run -n thoc-env python -m tools.verify_local``. Trả nonzero nếu bất kỳ bước fail.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp"


def _run(name: str, cmd: list[str], env: dict[str, str] | None = None) -> bool:
    print(f"\n=== {name} ===\n$ {' '.join(cmd)}")
    full_env = {**os.environ, **(env or {})}
    full_env.setdefault("PYTHONIOENCODING", "utf-8")
    full_env.setdefault("PYTHONUTF8", "1")
    proc = subprocess.run(cmd, cwd=ROOT, env=full_env)
    ok = proc.returncode == 0
    print(f"[{name}] {'PASS' if ok else 'FAIL'} (exit {proc.returncode})")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm tra cục bộ không-mạng cho THÓC")
    ap.add_argument("--scenario", default="agrarian_transition_v1")
    ap.add_argument("--seed", type=int, default=41)
    ap.add_argument("--ticks", type=int, default=20)
    ap.add_argument("--skip-sim", action="store_true", help="bỏ smoke run + replay")
    args = ap.parse_args(argv)
    (TMP / "pytest").mkdir(parents=True, exist_ok=True)
    (TMP / "logs").mkdir(parents=True, exist_ok=True)
    py = sys.executable
    results: list[tuple[str, bool]] = []

    results.append(("ruff", _run("ruff", [py, "-m", "ruff", "check", "."])))
    results.append(("pytest", _run(
        "pytest",
        [py, "-m", "pytest", "-q", "--basetemp", str(TMP / "pytest"), "-p", "no:cacheprovider"],
        env={"THOC_BLOCK_NETWORK": "1"},
    )))
    results.append(("scenario_validation", _run(
        "scenario_validation", [py, "-m", "tools.validation", args.scenario])))

    if not args.skip_sim:
        # A verification smoke is a new experiment, never permission to overwrite
        # an earlier artifact with the same convenient name.  The nonce is runtime
        # identity only; ``run.py`` records the complete reproducibility contract.
        run_name = f"verify_local_{args.scenario}_s{args.seed}_{uuid.uuid4().hex[:12]}"
        smoke_ok = _run("smoke_run", [
            py, "run.py", "--mode", "rulebot", "--ticks", str(args.ticks),
            "--seed", str(args.seed), "--scenario", args.scenario, "--run-name", run_name,
        ])
        results.append(("smoke_run", smoke_ok))
        if smoke_ok:
            results.append(("verify_research_run", _run(
                "verify_research_run", [py, "-m", "tools.verify_research_run", run_name])))
        else:
            results.append(("verify_research_run", False))

    print("\n===== TỔNG KẾT =====")
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    all_ok = all(ok for _, ok in results)
    print("KẾT QUẢ: " + ("XANH ✅" if all_ok else "ĐỎ ❌"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
