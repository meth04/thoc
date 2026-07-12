# Paper outline (draft) — THÓC

Ngày: 2026-07-12. **KHÔNG chứa finding bịa.** Đây là khung + danh mục bằng chứng CÒN THIẾU cho
mỗi hướng (REVIEW Phụ lục B–C). Chỉ viết manuscript khi các cổng tương ứng đạt (charter §2).
Không tuyên bố kết quả thực chứng chưa có.

## Hướng A — Kinh tế sử định lượng (REVIEW Hướng 1, khuyến nghị)

**Tiêu đề (ví dụ):** *Land scarcity, weather risk, and the emergence of informal credit in a
pre-industrial agrarian community: a structural micro-to-macro benchmark.*

1. Introduction — câu hỏi nhân quả hẹp (đất khan × rủi ro thời tiết → bất bình đẳng/tín dụng).
2. Related work — ABM kinh tế sử; giới hạn nhận diện của "rich artificial worlds".
3. Model — 5 lớp (charter §3), accounting identities, scope xác định (địa bàn/thời đoạn THẬT).
4. Data — package versioned có provenance (đất/dân số/giá/tô/nợ/thời tiết); codebook; DOI/license.
5. Calibration — SMM/ABC/history-matching trên moment in-sample; posterior + identifiability.
6. Out-of-sample validation — holdout theo thời gian; scoring rule khóa trước.
7. Counterfactual/placebo — đúng dấu + placebo + sensitivity; ≥30 seed; báo bất định.
8. Results, limitations, reproducibility.

**Bằng chứng CÒN THIẾU (blocker):** raw data có nguồn + holdout; hiệu chuẩn nhiều moment; ensemble
30-seed; địa bàn/thời đoạn cụ thể. Cho tới khi có → không viết được §4–6.

## Hướng B — Phương pháp LLM-ABM có kiểm toán (REVIEW Hướng 2)

**Tiêu đề (ví dụ):** *Constraint-accounted LLM agents: does ledger/action-compiler/replay reduce
invalid behavior and improve institutional robustness across models?*

1. Introduction — claim: hạch toán ràng buộc + action compiler + replay giảm hành vi không hợp lệ.
2. System — gateway, intent validation, ledger, replay artifact, quota-aware execution.
3. Benchmark — micro-tasks có ground truth (chọn sản xuất khi ngân sách/đất hữu hạn; thực hiện
   hợp đồng; tránh bán tài sản không sở hữu; phản ứng cú sốc). Đo constraint violation, welfare
   regret, diversity, cost/token, fallback rate, stability.
4. Baselines — rulebot / feasible_random / hand-coded rational / LLM policy (paired seed).
5. Experiments — ≥2 model/provider, nhiều snapshot; ≥30 seed/điều kiện; paired CI; ablation
   (bỏ accounting/action-validation/social-memory/contract-language/survival-floor).
6. Results — transcript/cache replay tạo đúng action trace; báo failure modes.

**Bằng chứng CÒN THIẾU (blocker):** cache/transcript + prompt/model hash cho real; ≥2 model +
≥30 seed/điều kiện; micro-task suite có ground truth; paired CI. Chưa chạy real trong phiên này.

## Quyết định

KHÔNG theo cả hai cùng lúc. Chọn một claim chính, thiết kế data/baseline/phép bác bỏ đúng claim
đó (REVIEW Phụ lục B). Cả hai hướng hiện đều BỊ CHẶN ở bằng chứng nêu trên; phần mềm đã sẵn sàng
làm hạ tầng cho một trong hai.
