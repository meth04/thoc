# Lộ trình phát triển THÓC thành bài báo hội thảo mạnh (chi tiết, thực thi được)

Ngày: 2026-07-13. Cơ sở: `REVIEW.md` (Phụ lục B–D), `reports/design_reevaluation.md`,
`reports/world_class_readiness.md`, và tài sản đã có (T00–T13 + pilot real50/mock50).
Nguyên tắc xuyên suốt: **không overclaim** — mỗi bước nêu rõ nó chứng minh gì và chưa chứng minh gì.

---

## 0. Chốt CLAIM và VENUE trước khi làm bất cứ gì

**Chọn đúng một hướng** (không làm cả ba — REVIEW Phụ lục B). Đề xuất mạnh nhất theo tài sản
hiện có:

**Hướng chính (khuyến nghị): Bài PHƯƠNG PHÁP + BENCHMARK LLM-ABM có kiểm toán.**
- **Câu hỏi/claim:** "Một LLM-ABM có *hạch toán ràng buộc, action-validation và replay* cho phép
  ĐO và TÁCH BIỆT ảnh hưởng của *bộ ra quyết định* (heuristic / LLM / random) lên động lực định
  chế nội sinh — và cho thấy tác nhân LLM khác biệt HỆ THỐNG với baseline heuristic, nên các tuyên
  bố 'định chế tự phát' phụ thuộc mạnh vào lớp hành vi, không phải thuộc tính của môi trường."
- **Tính mới (điều reviewer mua):** không phải 'thế giới giả lập giàu cơ chế' (REVIEW cảnh báo:
  nhiều cơ chế ≠ bài mạnh), mà là **hạ tầng đo lường + kết quả nhận diện**: ledger bảo toàn + replay
  tất định + benchmark micro-task có ground-truth cho phép so sánh có kiểm soát các bộ quyết định.
- **Hạt nhân đã có:** phát hiện `real50 ≠ mock50` (LLM thật ~0 hợp đồng/dân co; mock 271 hợp đồng/
  dân tăng) — bằng chứng sơ khởi cho claim. Cần nâng lên đa-seed/đa-model.
- **Venue phù hợp:** NeurIPS Datasets & Benchmarks, AAMAS, ICWSM, Computational Economics, hoặc
  workshop AI-for-Science/LLM-agents có phản biện. KHÔNG nhắm tạp chí kinh tế top (thiếu dữ liệu).

**Hướng phụ (chỉ nếu có dữ liệu thật): Kinh tế sử định lượng** — bị CHẶN CỨNG bởi thiếu data
package + calibration + holdout (REVIEW §5). Không theo trừ khi có nguồn dữ liệu thật.

---

## 1. Bốn cổng bắt buộc (REVIEW Phụ lục C) — làm đủ mới nộp

| Cổng | Hiện trạng | Việc phải làm |
|---|---|---|
| **Claim** đo được | ✅ có (real≠mock) | Phát biểu chính xác + sign/effect dự đăng ký trước |
| **Dữ liệu/benchmark** có version | ⚠️ một phần | Micro-task suite có ground-truth (mục 3) + task versioned |
| **Hiệu lực** (nhiều baseline/model, ablation) | ❌ | Ensemble đa-DM × đa-model × ≥30 seed + ablation đăng ký trước |
| **Tái lập** (cache/transcript replay, cost log) | ⚠️ | Transcript layer cho real + prompt/model hash (mục 2) |
| **Độ bền** (≥30 seed, sensitivity, placebo) | ⚠️ hạ tầng có | Chạy ở quy mô + báo paired CI (mục 4) |
| **Minh bạch** (failure modes) | ✅ có kỷ luật | Giữ nguyên: báo cả seed không-đò, real đình trệ |

---

## 2. Hạ tầng CÒN THIẾU cần xây (kỹ thuật, không mạng để phát triển)

**P1 — Transcript/replay cho real (BẮT BUỘC cho reproducibility gate).**
- Thêm lớp lưu vào gateway real: mỗi call ghi `{prompt_hash, model, provider, temperature, seed,
  request, response, tokens}` vào `data/runs/<run>/transcript.jsonl` (append-only, mã hóa/nén nếu cần).
- Nâng `tools/replay.py`: mode `--from-transcript` → nạp response theo call-id thay vì gọi API →
  replay real tạo ĐÚNG action trace (không chỉ cùng seed). Test: replay real == world-hash gốc.
- Manifest: thêm `prompt_template_hash`, `model_snapshot`, `temperature` vào `reproducibility`.
- *Chứng minh:* "kết luận real tái lập được từ artifact" — điều reviewer đòi.

**P2 — Cấu hình đa-model/đa-provider.**
- `config/models.yaml`: khai báo ≥2 họ model (đã có gemini; thêm 1 provider/model khác qua 9router
  hoặc OpenAI-compatible). Mỗi model là một *treatment* riêng, cùng prompt budget + temperature.
- Không đổi lõi; chỉ mở rộng route + ghi model vào manifest/telemetry.

**P3 — Micro-task benchmark harness (đóng góp benchmark chính).**
- `tools/microtasks.py` + `scenarios/microtasks/`: một tập task NHỎ, có GROUND TRUTH, mỗi task là
  một `World` được dựng cố định + câu hỏi quyết định:
  1. *Constraint-following*: chọn sản xuất khi ngân sách/đất/công hữu hạn (đáp án tối ưu tính được).
  2. *Contract execution*: thực hiện đúng clause đã ký (vi phạm = sai).
  3. *No-selling-unowned*: không bán tài sản không sở hữu (feasibility).
  4. *Shock response*: phản ứng đúng dấu với hạn/lũ (dự trữ tăng).
- Đo cho mỗi bộ quyết định: **constraint-violation rate, welfare-regret, action-diversity, cost/
  token, fallback rate, stability**. Đây là "dữ liệu có version + expected outcome" reviewer cần.

**P4 — Ensemble runner cho real + missingness.**
- Nâng `tools/counterfactual.py`/mới `tools/ensemble.py`: chạy real-mode paired-seed ở quy mô,
  xử lý run bị quota/cost/fail (đã có `n_failed`; thêm cột model + provider + cost), lưu transcript.
- Bootstrap CI + paired comparison sẵn (đã có median/p10/p90 + paired_delta).

**P5 — Sensitivity/identifiability đầy đủ.**
- Nâng `tools/sensitivity.py`: Morris/Sobol (không chỉ one-at-a-time grid) trên priors đã khai báo;
  báo parameter importance để TÁCH "hiệu ứng do cơ chế" vs "do tham số".

---

## 3. Chương trình thí nghiệm (đăng ký TRƯỚC khi xem kết quả)

Khóa `scenarios/agrarian_transition_v1/preanalysis_protocol.yaml` + phiên bản cho micro-task, RỒI chạy:

**E1 — Decision-maker comparison (claim chính).**
- Bộ quyết định: `rulebot, feasible_random, subsistence, adaptive, mock, real(model A), real(model B)`.
- ≥30 seed paired mỗi bộ, horizon 100–200 tick, scenario `agrarian_transition_v1`.
- Outcome: contract-formation, institution labels, distribution (gini đất/thu-nhập/tiêu-dùng),
  survival, welfare. **Dự đăng ký:** real khác mock có ý nghĩa (paired CI không chứa 0).

**E2 — Micro-task benchmark (đóng góp benchmark).**
- Mỗi bộ quyết định × N task × seed → bảng constraint-violation / regret / diversity / cost.
- **Dự đăng ký:** accounting/action-validation làm giảm constraint-violation; LLM đa dạng hơn nhưng
  regret/cost cao hơn. (Nếu LLM KHÔNG thắng — vẫn là kết quả tốt: báo giới hạn LLM-ABM.)

**E3 — Ablation đăng ký trước.**
- Tắt lần lượt: accounting audit / action-validation / social-memory / contract-language /
  survival-floor / spatial. Đo tác động lên outcome E1/E2. Hạ tầng scenario-flag đã có.

**E4 — Robustness + placebo.**
- Sensitivity (Morris/Sobol) + placebo shock (không cú sốc → không phản ứng giả) + permute-persona/
  permute-asset (đã có counterfactual). Báo seed-distribution, không một seed.

**Quy tắc:** mọi bảng/hình ghi n / horizon / policy / model / scenario / uncertainty + nhãn
mechanism-vs-empirical. Báo cả failure (seed không đò, real đình trệ) — KHÔNG cherry-pick.

---

## 4. Cấu trúc bài (bản thảo)

1. **Abstract** — claim đo được + kết quả real≠mock + benchmark release.
2. **Introduction** — khoảng trống: LLM-ABM tuyên bố "định chế tự phát" nhưng không tách được
   cơ chế vs tham số vs prompt/model; đóng góp = hạ tầng đo + nhận diện.
3. **Related work** — ABM kinh tế, LLM-agent societies, giới hạn nhận diện của "rich artificial worlds".
4. **System** — ledger sổ kép + FlowRegistry + audit; action compiler/validation; RNG tree + replay;
   scenario overlay + cổng định chế minh bạch; anti-teleology.
5. **Benchmark** — micro-task suite (P3) + metric ground-truth + scenario `agrarian_transition_v1`.
6. **Experiments** — E1–E4, protocol đăng ký trước, đa-model, ≥30 seed, paired CI.
7. **Results** — real≠mock (đa-seed đa-model), fragility (emergence phụ thuộc seed), ablation,
   micro-task bảng, sensitivity.
8. **Limitations** — single-context artifacts, prompt/temperature-sensitivity, cost, một-thế-giới-
   -giả-định (chưa empirical), horizon.
9. **Reproducibility & release** — one-command non-network reproduction (rulebot/mock) + transcript
   replay (real) + cost/quota/fail log + artifact (code + scenario + benchmark + seeds).

---

## 5. Lộ trình theo pha (deliverable + cổng)

- **Pha 1 (1–2 tuần) — Khóa claim + protocol.** Chọn venue; viết pre-analysis 2 trang (claim,
  outcome, baseline, model, seed list, tiêu chí loại run). Cổng: protocol khóa, không sửa sau khi xem.
- **Pha 2 (2–4 tuần) — Hạ tầng P1–P5.** Transcript replay + đa-model + micro-task harness + ensemble
  real + sensitivity. Cổng: replay real từ transcript == world-hash; micro-task có đáp án; CI xanh.
- **Pha 3 (compute) — Chạy E1–E4.** Rulebot/mock (không mạng, chạy ngay khi có CPU); real đa-model
  ≥30 seed (tốn budget API — `PENDING_COMPUTE`, ước tính ~$1/run × ~hàng trăm run + thời gian/quota).
  Cổng: bảng/hình tự sinh từ manifest, paired CI, failure được báo.
- **Pha 4 (2–3 tuần) — Viết + phản biện nội bộ.** Bản thảo theo mục 4; adversarial-reviewer +
  reality-auditor + reproducibility-steward pass; sửa mọi overclaim. Cổng: docs không overclaim,
  newcomer tái lập được.

---

## 6. Điều biến "bài tốt" thành "bài xuất sắc" (khác biệt hóa)

1. **Kết quả âm trung thực** (real đình trệ, emergence mong manh, LLM có thể thua rulebot trên
   micro-task) — reviewer đánh giá cao sự trung thực hơn là "mọi seed đều đẹp".
2. **Artifact tái lập một-lệnh** (không mạng cho baseline) + transcript replay cho real — hiếm và mạnh.
3. **Nhận diện (identification)**: tách rõ cơ chế vs tham số vs decision-maker qua ablation +
   sensitivity + paired-seed — đây là điều REVIEW nói "rich world thiếu".
4. **Kỷ luật claim-tier** (gate `assert_no_overclaim`, provenance, anti-teleology) — bản thân là
   đóng góp phương pháp về cách KHÔNG overclaim trong LLM-ABM.

## 7. Rủi ro & phản-bác cần phòng trước

- "Chỉ là một thế giới giả định" → trả lời: đóng góp là *phương pháp đo decision-maker*, không phải
  claim về kinh tế thật; benchmark có ground-truth độc lập với thế giới mô phỏng.
- "Prompt/model là hộp đen" → trả lời: hash prompt/model + transcript replay + đa-model + đo cost —
  biến prompt/model thành *treatment có version*, không phải hộp đen.
- "Không có dữ liệu thật" → thừa nhận thẳng: đây là bài PHƯƠNG PHÁP/benchmark, không phải kinh tế
  thực chứng; nêu rõ điều gì cần để lên empirical (data + calibration + holdout).

## 8. Việc làm được NGAY (không mạng, không tốn budget) — có thể bắt đầu tuần này
1. P1 transcript-replay layer + prompt/model hash (code + test, mock/FakeTransport).
2. P3 micro-task harness + ≥4 task có ground-truth + metric (rulebot/mock chạy được ngay).
3. E1/E2 phần rulebot/mock/feasible_random/subsistence/adaptive ở ≥30 seed (không mạng) → đã có
   một nửa bảng so sánh + toàn bộ paired CI trước khi cần một call real nào.
4. P5 Morris/Sobol sensitivity trên priors.
Chỉ Pha-3-real là cần budget API + thời gian; phần còn lại xây + chạy được hoàn toàn cục bộ.
