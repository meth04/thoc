# PROGRESS.md — trạng thái nghiệm thu từng phase

| Phase | Trạng thái | Lệnh nghiệm thu | Kết quả chính | Ngày |
|---|---|---|---|---|
| 0 | ✅ xanh | `pytest -q tests/test_ledger.py tests/test_rng.py` → **16 passed**; `ruff check .` → **All checks passed** | Ledger sổ kép nguyên tử (không âm số dư, cân từng tài sản), FlowRegistry bắt luồng lậu (2 test cài lậu cố tình đều bị bắt), hypothesis 300 examples pass, cây RNG tất định theo (subsystem, tick). | 2026-07-11 |
| 1 | ✅ xanh | `run.py --mode rulebot --years 300 --seed 42 --run-name rb300` → **159.6s < 5 phút, audit xanh 600/600 tick**; dân số cuối s41=327, s42=352, s43=475 ∈ [60,500], không tuyệt chủng; `tools.replay rb300 --verify` → **TRÙNG hash**; resume 100+100 tick = 200 liền → **hash trùng 3ca8542429831dc5**; `pytest -q` 22 passed; ruff sạch | Thế giới sống: map 30×30 seeded, thời tiết, nông nghiệp + khai thác + chế tác, health–đói–chết, cưới/sinh/chết/thừa kế mặc định, homestead, dạy chữ tại nhà + tự học, rulebot v0 persona-hóa, checkpoint/resume. Hiệu chỉnh p_goc 0.22→0.13 (DECISIONS.md). | 2026-07-11 |
