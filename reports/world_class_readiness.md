# THÓC — Đánh giá sẵn sàng công bố (world-class readiness)

Ngày: 2026-07-12. Cơ sở: `docs/MODEL_CHARTER.md`, `REVIEW.md` (Phụ lục A–D), kết quả T00–T12
của phiên nghiên cứu này. Nhãn claim tier dùng nhất quán: `design_assumption` / `mechanism_result`
/ `calibrated_fact` / `validated_result` (charter §2).

> **Cập nhật 2026-07-13:** đánh giá lại toàn diện + lộ trình xuất bản chi tiết ở
> `reports/design_reevaluation.md` (sau T13 spatial economy + pilot real50). Con đường khả tín =
> bài phương pháp LLM-ABM quanh phát hiện **real50 ≠ mock50**, không phải kinh tế thực chứng.

## Phán quyết một dòng

THÓC hiện là một **mechanism benchmark** có lõi hạch toán/tái lập mạnh. Một bài báo thực chứng
"tầm cỡ thế giới" **VẪN BỊ CHẶN** cho tới khi có (a) dữ liệu thật có nguồn, (b) hiệu chuẩn nhiều
moment, (c) kiểm định holdout độc lập. Đây KHÔNG phải hạn chế kỹ thuật của phần mềm mà là thiếu
bằng chứng thực chứng — đúng bản chất của một benchmark cơ chế.

## Bảng pass / partial / fail

| Hạng mục | Trạng thái | Bằng chứng / Vì sao |
|---|---|---|
| **Câu hỏi nghiên cứu** | PASS | Hẹp, có thể bác bỏ (charter §1); anti-teleology (ADR 0001 §C). |
| **Nhất quán kế toán (tầng 1)** | PASS | Ledger sổ kép + FlowRegistry + audit mỗi tick; replay TRÙNG hash (T02). |
| **Tái lập** | PASS | manifest + config digest + seed tree + `verify_research_run` (replay + audit, đọc policy từ manifest). **205 test** xanh không-mạng. |
| **Provenance/claim discipline** | PASS | Gate `assert_no_overclaim`; benchmark không thể đội nhãn empirical (T01/T03). |
| **Hợp lý cơ chế (tầng 2)** | PARTIAL | Chợ locality, hợp đồng-clause, đất, xu, tài khóa có; nhưng nhiều tham số là `design_assumption`, chưa phản biện bằng dữ liệu vi mô. |
| **Baseline không-LLM** | PARTIAL | rulebot + BehaviorPolicy interface + feasible_random/subsistence (T09); adaptive PENDING. |
| **Dữ liệu & nguồn gốc** | FAIL | Chưa có raw data có nguồn; mọi tham số `design_assumption`; `data_contract.md` mới là template. |
| **Hiệu chuẩn (calibration)** | FAIL | targets in-sample rỗng; chưa có SMM/ABC/history-matching trên data thật. |
| **Kiểm định holdout (tầng 4)** | FAIL | targets holdout rỗng; chưa có backtest ngoài mẫu. |
| **Khớp stylized facts (tầng 3)** | PARTIAL/FAIL | Có comparative-statics test cơ chế; chưa so với moment lịch sử có nguồn. |
| **Bền vững (robustness)** | PARTIAL | Runner paired-seed + quantiles + sensitivity runner có; demo 3-seed spatial on/off cho thấy tác động trong nhiễu seed + emergence phụ thuộc seed mạnh; ensemble 30-seed × đa-model đầy đủ = PENDING_COMPUTE. |
| **LLM reproducibility** | PARTIAL | Replay rulebot/mock TRÙNG hash; real cần transcript (chưa có); prompt/model hash chưa khóa cho real. |
| **Artifact release** | PARTIAL | Code + scenario package + manifest + CI có; chưa đóng gói data (vì chưa có data). |

## Diễn giải theo 3 tầng sẵn sàng (T12)

- **technical-ready**: ĐẠT — chạy/kiểm toán/tái lập không-mạng, output isolation, verify tool, CI.
- **research-ready** (mechanism benchmark): PHẦN LỚN ĐẠT — charter/scenario/protocol/baseline;
  còn thiếu ensemble đầy đủ + một số cơ chế (credit registry, treasury, public goods) PENDING.
- **empirically-validated**: **CHƯA** — thiếu data/calibration/holdout. Không được tuyên bố.

## Điều kiện gỡ chặn (theo REVIEW Phụ lục C)

1. Chọn MỘT hướng (khuyến nghị: kinh tế sử định lượng — REVIEW Hướng 1) và khóa câu hỏi nhân quả.
2. Data package versioned có provenance (đất/dân số/giá/tô/nợ/thời tiết) theo `data_contract.md`.
3. Chia in-sample/holdout theo thời gian, khóa prior + loss + seed TRƯỚC khi xem holdout.
4. Hiệu chuẩn nhiều moment (SMM/ABC/history-matching); báo posterior + identifiability.
5. Chạy ≥30 seed cho mỗi treatment; placebo + sensitivity; báo bất định, không báo một seed đẹp.
6. Chỉ thêm LLM như treatment sau cùng, có cache/transcript + prompt/model hash + cost/fallback.

Cho tới khi 1–5 có bằng chứng, nhãn đúng là `mechanism_benchmark`, không phải `empirically_validated`.
