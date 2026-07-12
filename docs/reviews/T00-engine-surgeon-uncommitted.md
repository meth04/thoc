# T00 — Review độc lập các thay đổi chưa commit (engine-surgeon, chỉ đọc)

Ngày: 2026-07-12. Reviewer: engine-surgeon (chế độ chỉ đọc — không sửa file). Ghi lại bởi
integration-manager. Bằng chứng reviewer đã chạy: `pytest` 170 passed; 22 test mới passed;
subset determinism/replay/audit/resume/ledger 25 passed; `ruff check .` → 5 lỗi (đã sửa, xem §Kết).

## BLOCKING (vi phạm 7 điều luật): KHÔNG CÓ

Đã kiểm cụ thể và xác nhận an toàn:
- **Bảo toàn**: `dich_benh` chỉ trừ `agent.health` (không qua ledger — không sinh/hủy tài sản);
  metric đất/hộ (`engine/economy.py`) và survival floor (`minds/safety.py`) chỉ đọc hoặc ghi
  *intent*, không chuyển tài sản. Audit xanh trên 170 test.
- **Tất định**: disease dùng `w.rng.get("dich_benh", year)` (cache theo năm); `permute_personas`
  dùng nhánh RNG riêng `counterfactual_persona` (không nhiễu stream chính); `households()` luôn
  `sorted`. Test `test_dich_benh_bat_theo_scenario` khẳng định hai world cùng hash; disease vào
  hash qua `a.health`.
- **Output isolation**: `tools/analyze.py`/`compare.py` nay ghi vào `data/runs/<run>/reports/…`
  thay vì `reports/final_analysis.md` chung — **vá đúng lỗi cũ** (khớp T02 yêu cầu).
- **LLM/policy chạm state**: `minds/safety.py` chỉ mutate `ke_hoach` + `da_nham` (như helper
  rulebot/entity sẵn có), không đụng `World`.
- **Magic fallback giá**: các `w.gia_gan_nhat("dat") or 600.0` đã **bị gỡ**, thay bằng
  `expected_land_value` (neo minh bạch từ config `hanh_vi.dat_dai`) — đúng hướng T04/T05 và
  checklist cấm §5 TASKS.

## MAJOR

1. **ruff gate 5 lỗi** (`tools/counterfactual.py:207` B023 + `minds/orchestrator.py:10`,
   `tests/test_disease_shock.py:5` F401, `tests/test_experiments.py:3`,
   `tests/test_household_economics.py:3` I001). Phá gate CLAUDE.md §3 / T00 / T12.
   → **ĐÃ SỬA trong T00** (xem §Kết).

## MINOR (robustness/provenance — không chặn, chuyển sang task tương ứng)

2. `run.py` nhánh `--resume` run legacy chưa có manifest: đóng dấu `config_sha256` hiện tại cho
   TOÀN BỘ quỹ đạo (kể cả đoạn đã chạy bằng config khác) → provenance sai cho đoạn cũ. Đã có
   comment thừa nhận. → T02 (provenance/manifest).
3. `tools/validation.py` `main()` với `--run`: `load_targets` có thể ném `ValueError` không bắt
   khi targets YAML hỏng (khác nhánh `validate_package` đã bắt). Benchmark hiện targets rỗng nên
   chưa kích hoạt. → T03 (nâng validation).
4. `config/world.yaml` `minds.san_an_toi_thieu.bat: true` — survival floor **BẬT mặc định**, đổi
   quỹ đạo mọi run mock so với baseline cũ. Hợp lệ (thuộc `minds/`, config-gated, ghi event, vào
   `config_sha256`) NHƯNG "baseline" mock nay đã gồm một can thiệp sinh kế chủ động — **không được
   diễn giải là hành vi thuần LLM/rulebot**. → T09/T10 (ghi rõ trong protocol + báo cáo).
5. `tools/reality_check.py:369` `_tim_tu` bỏ qua dòng `#` — làm yếu nhẹ lớp quét-nguồn. → T12.
6. `engine/world.py` `giao_dich_dat` list append-only không trim, pickle mỗi checkpoint. Nit bộ
   nhớ ở 600 tick. → theo dõi, không hành động.

## Ghi chú xác nhận (không phải lỗi)

- Overlay phản chứng `c4_adverse_weather` (thời tiết 0.10/0.45/0.45 = 1.0) và `c3_no_parameter_noise`
  (`minds.nhieu_tham_so_so`) dùng đúng khóa; `deep_merge` thay đủ.
- `run.py` telemetry keys khớp `tools/telemetry.py` — không silent-zero.

## Kết luận & hành động T00

- **0 BLOCKING.** Item MAJOR-1 (ruff) đã sửa trong phạm vi T00: B023 bằng cách bind biến vòng lặp
  (`def fmt(..., metrics=s)`, `tools/counterfactual.py:206-207`); 4 lỗi còn lại bằng
  `ruff check . --fix` (import order + gỡ import thừa). Sau sửa: `ruff check .` → **All checks
  passed**; `pytest tests/test_experiments.py tests/test_household_economics.py
  tests/test_disease_shock.py` → **13 passed**. Không đổi logic.
- MINOR 2–6 chuyển sang T02/T03/T09/T10/T12 với con trỏ ở trên; không có finding nào là lý do để
  vứt code trong diff bẩn — trái lại diff hiện thực hóa nhiều mục T04/T05 (neo đất minh bạch,
  output isolation, metric hộ read-only).
