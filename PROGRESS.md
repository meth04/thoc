# PROGRESS.md — trạng thái nghiệm thu từng phase

| Phase | Trạng thái | Lệnh nghiệm thu | Kết quả chính | Ngày |
|---|---|---|---|---|
| 0 | ✅ xanh | `pytest -q tests/test_ledger.py tests/test_rng.py` → **16 passed**; `ruff check .` → **All checks passed** | Ledger sổ kép nguyên tử (không âm số dư, cân từng tài sản), FlowRegistry bắt luồng lậu (2 test cài lậu cố tình đều bị bắt), hypothesis 300 examples pass, cây RNG tất định theo (subsystem, tick). | 2026-07-11 |
