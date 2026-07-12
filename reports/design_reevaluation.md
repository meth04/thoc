# Đánh giá lại thiết kế THÓC & lộ trình lên bài báo hội thảo quốc tế

Ngày: 2026-07-13. Người tổng hợp: integration-manager. Cơ sở: `REVIEW.md`,
`reports/world_class_readiness.md`, kết quả T00–T13 + hai pilot `mock50`/`real50` + trial
`spatial50`. Đây là đánh giá TRUNG THỰC để định hướng, KHÔNG phải tuyên bố đã sẵn sàng.

## 1. Phán quyết điều hành (thẳng thắn)

THÓC hiện là một **mechanism benchmark** kỹ thuật rất tốt (hạch toán/tái lập/đa cơ chế), nhưng
**CHƯA** là một bài báo hội thảo hàng đầu, và con đường lên đó **không** phải hướng "kinh tế thực
chứng" (thiếu dữ liệu thật + calibration + holdout — chưa có, và không thể bịa). Con đường KHẢ TÍN
nhất là **bài phương pháp LLM-ABM có kiểm toán** (REVIEW Phụ lục B, Hướng 2/3) — và dự án đã có sẵn
**một phát hiện phương pháp mạnh, đo được, chưa ai công bố cho hệ này**:

> **real50 ≠ mock50 (cùng seed/luật):** LLM thật (Gemini) tạo ~0 hợp đồng, dân số co 50→21; mock
> PersonaBot tạo 271 hợp đồng, 7 mô-típ, dân 50→203. → "định chế tự phát" quan sát ở mock có thể là
> hiện vật của heuristic, KHÔNG tái lập dưới LLM thật. **Mock không phải proxy cho hành vi LLM.**

Đây là hạt nhân một đóng góp: *một ABM có hạch toán ràng buộc + replay + action-validation cho phép
ĐO được sự khác biệt hành vi giữa các bộ ra-quyết-định (heuristic vs LLM vs random), thay vì giả
định chúng tương đương.* Nhưng để công bố, nó cần bằng chứng ĐA-SEED, ĐA-MODEL (mục 6).

## 2. Điểm mạnh (giữ và làm nổi bật)

| Trụ cột | Trạng thái | Bằng chứng |
|---|---|---|
| Hạch toán nhất quán (tầng 1) | **Mạnh** | ledger sổ kép + FlowRegistry + audit MỖI tick; 0 vi phạm qua mọi run |
| Tái lập tất định | **Mạnh** | seed tree + world-hash + `verify_research_run` (replay + audit); replay TRÙNG hash rulebot/mock/scenario/policy/spatial |
| Kỷ luật claim-tier | **Mạnh** | `assert_no_overclaim` chặn nhãn empirical khi thiếu target/provenance |
| Đa cơ chế có cổng | **Tốt** | hộ/chợ-locality/hợp đồng-clause/pháp nhân/tín-dụng-view/tiền-hàng-hóa/tài-khóa-treasury/không-gian-đò — mỗi cái scenario-gated + accounting identity + OFF=legacy hash |
| Baseline không-LLM | **Tốt** | rulebot + feasible_random + subsistence + adaptive (+ spatial-aware) — tách LLM khỏi lõi |
| **Phát hiện real≠mock** | **Đặc sắc** | `reports/real50_pilot_report.md` — divergence đo được, đúng cảnh báo REVIEW |

## 3. Điểm còn thiếu để "world-class" (khoảng cách thật)

| Hạng mục | Thiếu gì | Cần để lấp |
|---|---|---|
| Dữ liệu & nguồn | Không raw data có provenance; mọi tham số `design_assumption` | data package theo `data_contract.md` (route kinh tế sử) |
| Hiệu chuẩn/holdout | targets rỗng; chưa SMM/ABC | data + fit + holdout khóa trước |
| Robustness | Pilot 1-seed/mode; chưa ensemble ≥30 seed, chưa đa-model | compute + ≥2 provider (mục 6) |
| LLM reproducibility | real chưa replay-từ-transcript; prompt/model hash chưa khóa | cache transcript + hash prompt/model |
| Micro-task ground truth | Chưa có bộ task đo constraint-violation/welfare-regret | thiết kế task suite (Hướng 2) |
| Định danh (identification) | Chưa tách "cơ chế" vs "tham số" vs "policy/prompt" | ablation + sensitivity + paired-seed đã có hạ tầng |

## 4. Đánh giá T13 (spatial livelihood economy) — mechanism_result

Cơ chế MỚI (2 bờ + đò-dịch-vụ + khai hoang bờ kia + endowment food-equiv) đã cài, **scenario-gated
OFF**, legacy hash BẤT BIẾN, 283 test xanh. Trial `spatial50` (rulebot 50 năm, overlay ON):
- **Cơ chế được exercise THẬT:** 4 thuyền đóng, 14 chuyến qua sông trên 13 tick (peak 2 người bờ
  kia), audit xanh suốt; `occupation_entropy` 0–1.28; fish stock 16820.
- **NHƯNG far-bank clearing KHÔNG hình thành** (`far_bank_cleared=0` cả run; `khai_hoang` không
  kích hoạt). → kết quả hợp lệ: agent qua sông nhưng chưa phát triển nông nghiệp bờ kia dưới
  policy/seed này. Diễn giải: động cơ khai hoang bờ kia yếu, hoặc qua sông vì lý do khác.
- Ý nghĩa: đúng nguyên tắc T13 gate — xã hội *có thể* tạo sinh kế không gian nhưng KHÔNG bị ép;
  "không phát sinh dịch vụ/khai hoang" là outcome được báo, không giấu.
- Đã HOÃN có chủ đích (ADR 0005 spec, không bịa hoàn thành): vụ đông (E), gà rừng commons (F),
  chăm trẻ (G) — depth bổ sung, không thiết yếu cho trial/xuất bản.

## 5. Cải tiến ĐÃ làm phiên này (hướng xuất bản)

- Đa cơ chế + spatial → benchmark giàu hơn cho "institutional stress test" (Hướng 3).
- Robustness INFRASTRUCTURE: `tools/counterfactual.py` (paired-seed, n/failed, median/p10/p90),
  `tools/sensitivity.py` (rút từ priors, identifiability).
- **Demo robustness paired-seed spatial ON/OFF (3 seed, `data/runs/robust_*`)** — kết quả TRUNG THỰC:
  tác động vĩ mô của kinh tế không gian NẰM TRONG nhiễu seed (dân số OFF 199[185,199,235] vs ON
  215[172,215,263]; gini_dat 0.72 cả hai; biết chữ 93% vs 92% — dải chồng lấp, n=3). Bản thân
  "kinh tế đò" CỰC KỲ phụ thuộc seed: seed42=14 chuyến/4 thuyền, seed43=**0/0 (không đò)**,
  seed44=42 chuyến/9 thuyền. → "hình thành không gian" là mong manh/ngẫu nhiên; cần nhiều seed để
  tách khỏi nhiễu — đúng thông điệp một bài phương pháp nên báo (không cherry-pick seed có đò).
- Khung bài phương pháp quanh real≠mock (`reports/paper_outline.md` Hướng 2).
- Kỷ luật: mọi cơ chế mới OFF=legacy-hash, accounting identity đóng, observation không điều khiển
  engine, anti-teleology — đủ chuẩn "reproducible artifact" mà reviewer đòi.

## 6. Lộ trình lên bài báo (khả tín, có thứ tự) + việc còn thiếu

**Chọn Hướng 2 (LLM-ABM methodology) làm claim chính** — phù hợp nhất với tài sản hiện có:

*Claim:* "Constraint-accounted LLM-ABM (ledger + action-validation + replay) cho phép đo và tách
biệt tác động của bộ ra-quyết-định lên động lực định chế; cụ thể, LLM thật khác biệt hệ thống với
heuristic baseline, nên kết luận 'định chế tự phát' phụ thuộc mạnh vào lớp hành vi."

Cổng còn thiếu (theo REVIEW Phụ lục C — đây là **việc external/compute, không bịa được**):
1. **Ensemble ≥30 seed × ≥2 model/provider** cho real vs mock vs rulebot, paired CI. → `PENDING_COMPUTE`
   (real tốn ~$1/run × 30 × nhiều-model; cần ngân sách API + thời gian). Command trong mục 7.
2. **Cache/transcript replay cho real** + hash prompt/model/temperature (hiện chỉ có world-hash +
   llm_calls log). → cần thêm lớp lưu transcript trong gateway real.
3. **Micro-task suite có ground truth** (chọn sản xuất khi ràng buộc, thực hiện hợp đồng, tránh bán
   tài sản không sở hữu, phản ứng cú sốc) đo constraint-violation/welfare-regret/diversity. → thiết kế mới.
4. **Ablation đăng ký trước**: bỏ accounting/action-validation/social-memory/contract-language/
   survival-floor → đo tác động. Hạ tầng scenario-flag đã có; cần chạy + báo.

Nếu chọn **Hướng 1 (kinh tế sử)**: bắt buộc data package có provenance + calibration + holdout —
CHƯA có, là blocker cứng. Không được gọi empirical khi chưa có.

## 7. Hành động external có giá trị cao nhất (một việc)
Khóa protocol Hướng 2, chạy **ensemble 30-seed real+mock+rulebot cho ≥2 model** rồi báo paired CI:
```
# rulebot/mock (không mạng) — chạy được ngay khi có compute:
python -m tools.counterfactual --scenario agrarian_transition_v1 --seeds <30 seed> --ticks 100 --mode rulebot
python -m tools.counterfactual --scenario agrarian_transition_v1 --seeds <30 seed> --ticks 100 --mode mock
# real (tốn budget API, cần --i-am-sure) — 30 seed × ≥2 model, lưu transcript:
for s in <30 seed>: python run.py --mode real --years 50 --seed $s --i-am-sure --until-budget --run-name real50_s$s
```
Chỉ sau khi có phân phối đa-seed đa-model + micro-task + ablation thì mới đủ để nộp bài phương pháp.
Cho tới lúc đó: **`mechanism_benchmark` + pilot**, không phải `empirically_validated`.
