# T13 — Review độc lập & bằng chứng (spatial livelihood economy)

Ngày: 2026-07-13. Design: model-architect (ADR 0005). Implement: engine-surgeon ×3 (Phase A,
ferry, clearing+endowment) + minds-engineer (policy) + implementation-engineer (metrics). Review
độc lập: reality-auditor. Mock test + integration: integration-manager.

## Kết quả tích hợp
- **283 test passed**, ruff sạch (`.tmp/logs/T13_full_suite.log`).
- **Combined OFF=legacy BẤT BIẾN (proof mạnh nhất)**: replay `mock50` (tạo TRƯỚC T13, mock, default
  config) dưới engine post-T13 → hash `3005ea50ce20` **TRÙNG**; `agr_smoke_rb_s41` (scenario) TRÙNG.
  → toàn bộ 6 wave T13 inert khi overlay OFF.

## reality-auditor — VERDICT: PASS (0 BLOCKING/MAJOR)
1. OFF=legacy bất biến — PASS (mọi path gated, không draw RNG thêm; replay-committed-hash = proof).
2. Phantom/teleport — PASS (phí đò `ledger.chuyen` cân; thuyền nguyên tử + flow đăng ký; endowment
   chỉ mint tick 0; khai hoang tốn công, KHÔNG title free; không teleport).
3. Anti-teleology — PASS (không hardcode ID/vị trí; `bo` từ hình học seed; hành vi keyed persona/
   thiếu-đất, không class-branch; nghề per-tick không lock).
4. Determinism — PASS (spatial.py 0 RNG; sorted; stream riêng `spatial:{aid}`; ON 2-run cùng hash).
5. Metric read-only — PASS (OFF→None; coverage-guard; ngoài world_hash).
6. Định chế ẩn (CLAUDE #7) — PASS (đò=asset+contract, nhãn chỉ observatory; DECISIONS.md ghi chủ ý).

## MINOR (non-blocking, ghi nhận)
- `minds/rulebot.py:342,368-381`: hằng heuristic policy hardcode (phí, công, ngưỡng) chưa đọc config
  — Lớp-4, không đụng bảo toàn/determinism, nhưng lệch CLAUDE §5. → follow-up: đưa vào `spatial_v1.yaml`
  block `policy:`.
- ADR §10 `khop_cho.bo` payload + `price_wage_dispersion_by_bank` CHƯA implement — cùng nhóm HOÃN
  có-chủ-đích (vụ đông/gà rừng/chăm trẻ). Ghi PENDING đúng, không bịa.
- `world.py:498` literal `12.0` (tháng/năm) — calendar-identity, có thể đặt tên hằng.

## Trial + đánh giá
`spatial50` (rulebot 50y, overlay ON): cơ chế exercise thật (4 thuyền, 14 chuyến/13 tick) nhưng
far-bank clearing KHÔNG hình thành. Ensemble 3-seed on/off: tác động vĩ mô trong nhiễu seed; đò
CỰC phụ thuộc seed (seed43=0 chuyến, seed44=42). mechanism_result trung thực. Đánh giá đầy đủ +
lộ trình xuất bản: `reports/design_reevaluation.md`.

## Kết luận
Gate T13 **PHẦN LỚN ĐẠT**: core spatial+ferry+clearing+endowment+policy+metrics coded, gated OFF,
legacy bất biến, independent PASS. HOÃN có chủ đích (ADR spec): vụ đông/gà-rừng-commons/chăm-trẻ +
dispersion-by-bank + đưa hằng policy vào config. KHÔNG bịa hoàn thành.
