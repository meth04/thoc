# THÓC — Final handoff (phiên tự chủ 2026-07-12)

Chế độ: tự chủ, KHÔNG mạng/real/API/`.env`. Không commit (chờ người dùng duyệt). Claim tier tổng:
**mechanism_benchmark** (technical-ready + phần lớn research-ready; **KHÔNG** empirically-validated).

## Bảng T00–T12

| Task | Status | Evidence/artifact | Blocker còn lại |
|---|---|---|---|
| T00 baseline + conflict map | ✅ DONE | `docs/reviews/T00-baseline.md`, `T00-spec-governor-conflict-map.md`, `T00-engine-surgeon-uncommitted.md`; 170→ pass, ACL blocker vòng tránh | — |
| T01 charter + ADR-0001 + doc-sync + overclaim gate | ✅ DONE | `docs/MODEL_CHARTER.md`, `docs/adr/0001`, banners, `tools/validation.py` gate; `docs/reviews/T01-review.md` (reality-auditor PASS, adversarial no-blocking) | — |
| T02 verify tool + isolation + C12 + CI + net-guard | ✅ DONE | `tools/verify_research_run.py`, `verify_local.py`, `.github/workflows/ci.yml`, `tests/conftest.py`; `docs/reviews/T02-T03-qa.md` (steward PASS) | — |
| T03 `agrarian_transition_v1` package + validation upgrade | ✅ DONE | `scenarios/agrarian_transition_v1/` (10 file), `tools/validation.py` (units/W2/split); `docs/reviews/T03-review.md` | — |
| T04 hộ nông nghiệp | 🟡 DESIGN+METRICS | ADR `docs/adr/0003`; read-only metrics `engine/metrics_research.py` | `poverty_streak`, pantry (PENDING engine) |
| T05 chợ/đất | 🟡 DESIGN+METRICS | ADR 0003; `price_dispersion` qua event `lang`; per-làng order book đã có | `ghi_gia`-by-làng (phá hash) PENDING |
| T06 tín dụng | 🟡 DESIGN+METRICS | ADR `docs/adr/0004`; CLAIMS VIEW + debt-service/outstanding metrics | Registry object `Claim` PENDING |
| T07 tiền hàng hóa | 🟡 DESIGN+METRICS | ADR 0004; monetary-share/acceptance/concentration metrics | `failed_settlement` counter PENDING |
| T08 tài khóa/chính phủ | 🟡 DESIGN+GATE+METRICS | ADR 0004; `chinh_tri.bat` gate + tests; tax/fiscal metrics | Treasury balance-sheet + public goods PENDING |
| T09 BehaviorPolicy baseline | ✅ DONE (impl) | `minds/policies.py` (rulebot/feasible_random/subsistence; adaptive PENDING); `tests/test_policies.py` (12) | adaptive policy (PENDING) |
| T10 experiments/uncertainty/validation | 🟡 PARTIAL | protocol + runner hardening + 3-seed smoke + validation-gate + data-contract | suites đầy đủ + sensitivity + **30-seed = PENDING_COMPUTE** |
| T11 báo cáo/docs | ✅ DONE | `reports/{world_class_readiness,agrarian_transition_v1_methodology,paper_outline}.md`, README | generated experiment report (từ smoke) |
| T12 final gates + handoff | ✅ DONE | reality-auditor PASS + adversarial-reviewer minor-revision→đã sửa; `docs/reviews/T12-gates.md`; **205 passed** | — |

Chú thích: 🟡 = thiết kế (ADR) + tầng quan sát read-only đã làm; cơ chế engine-mutation đánh dấu
PENDING có spec + điều kiện cổng định chế §5 (charter). KHÔNG bịa là đã implement.

## Commands đã chạy & kết quả (chọn lọc)

- `pytest -q --basetemp .tmp/pytest -p no:cacheprovider` → **204 passed** (170 gốc → +politics/
  validation/verify/policies/metrics; **205** sau fix T12 thêm test regression M1). 0 fail.
  `THOC_BLOCK_NETWORK=1` không phá test.
- `ruff check .` → **All checks passed** (sau mỗi thay đổi).
- `tools.verify_local` → XANH (ruff+pytest+validation+smoke+verify).
- `tools.validation preindustrial_closed_v1 | agrarian_transition_v1` → mechanism_benchmark,
  empirical_ready=false, không overclaim, exit 0.
- `run.py --mode rulebot --scenario agrarian_transition_v1` + `verify_research_run` + `replay
  --verify` → replay TRÙNG hash, audit xanh, politics off.
- `tools.counterfactual --scenario agrarian_transition_v1 --seeds 41 42 43 --ticks 60` → ensemble
  paired-seed, quantiles, paired-delta (mechanism_result, KHÔNG empirical).

## Runs tạo trong phiên (mode/seed/horizon)
- `agr_smoke_rb_s41` (rulebot, seed 41, 20 tick, scenario) — verify xanh.
- `t12_pol_check`/`t_adaptive_smoke` (rulebot, `--policy feasible_random`/`adaptive`) — replay TRÙNG.
- `data/experiments/t10_agr_smoke_rulebot_60t/` (rulebot, seeds 41/42/43, 60 tick, 5 treatment).
- **`mock50`** (mock, seed 42, 100 tick/50 năm, default config): fallback **0.00%**, 4272 call,
  audit xanh, replay TRÙNG hash `3005ea50ce20` — **GATE mock-trước-real ĐẠT**.
- **`real50`** (real LLM Gemini, seed 42, **100 tick/50 năm HOÀN TẤT**, ~41 phút): **1347 call,
  fallback 0.00%**, 8.9M+0.35M token, **~$1.03**, KHÔNG dừng budget, hash `9bada012e965`.
  verify ĐỦ BẰNG CHỨNG. Kết quả: xã hội KHÔNG phát triển — dân 50→21, 0 hợp đồng, 0 entity, 0
  chính quyền, kinh tế đổi chác (mechanism_result 1-seed). Báo cáo: `reports/real50_pilot_report.md`.
- **Phát hiện then chốt (real ≠ mock)**: mock50 tự phát 271 hợp đồng/7 mô-típ/dân 203; real50 gần
  như 0 hợp đồng/dân 21 — xác nhận luận điểm REVIEW/charter: **mock KHÔNG phải proxy cho LLM thật**,
  kết luận cơ chế không được phụ thuộc mock. (`data/runs/mock50/reports/compare_real50.md`)
- KHÔNG xóa/ghi đè run cũ.

## Goal mới (2026-07-12): code pending + mock50 + real50
- ✅ Đã code: `poverty_duration`(T04), `failed_settlement`(T07), `adaptive` policy(T09), sensitivity
  runner(T10), **treasury+public-goods(T08)** — suite **239 passed**, ruff sạch, world-hash bất
  biến cho mọi thứ read-only/scenario-off. Treasury/thủy lợi: ledger-based, xây nguyên tử (no
  phantom), định danh tài khóa đóng (gồm carrying-cost), 13 test `test_fiscal.py`.
- Còn PENDING nhưng là **ADR-optional (không phải gap)**: Claim registry OBJECT — claims VIEW đã
  đủ, gate T06 ĐẠT (ADR 0004 cảnh báo nhân đôi state); per-làng price key T05-D2 — D1 (event
  `lang`) đã đủ, gate T05 ĐẠT (ADR 0003 cảnh báo D2 phá hash legacy). Cả hai để tương lai nếu cần.
- Đề xuất review độc lập tiếp: monetary-fiscal-economist cho fiscal; test-engineer comparative-statics.

## Claim tier đạt được
- **technical-ready**: ĐẠT. **research-ready (mechanism benchmark)**: phần lớn ĐẠT (còn cơ chế
  credit-registry/treasury/public-goods PENDING + ensemble đầy đủ PENDING_COMPUTE).
  **empirically-validated**: **CHƯA** (thiếu data/calibration/holdout — `reports/world_class_readiness.md`).

## Bước tiếp theo có giá trị nhất (external)
Chọn MỘT hướng (khuyến nghị: kinh tế sử định lượng — REVIEW Hướng 1), tạo **data package versioned
có provenance** theo `scenarios/agrarian_transition_v1/data_contract.md`, khóa in-sample/holdout,
rồi hiệu chuẩn + kiểm định ngoài mẫu. Đây là điều kiện DUY NHẤT để nâng khỏi `mechanism_benchmark`.

## Rủi ro/PENDING chưa giải quyết cục bộ
- 30-seed × 600-tick ensemble: PENDING_COMPUTE (command trong methodology §7).
- Cơ chế engine-mutation T06/T07/T08 (registry/treasury/public-goods) + T04 poverty_streak +
  T05 per-làng price key: PENDING, cần cổng định chế §5 + review độc lập trước khi vào engine.
- Sensitivity/Sobol runner: chưa cài.
- Resume không chặn đổi `--policy` (chỉ guard config-digest) — edge case.

## Không commit
Working tree bẩn (thay đổi người dùng + phiên này). KHÔNG stage/commit/reset. Người dùng tự duyệt.

## Publication phase (2026-07-13): hạ tầng bài báo + thí nghiệm + pilot
Hướng: bài phương pháp LLM-ABM (không phải kinh tế thực chứng). Đã code + chạy (không mạng cho phần local):
- **P3 micro-task benchmark** (`tools/microtasks.py`, 10 test): 4 task ground-truth (constraint/
  contract/no-sell/shock). E2: mọi baseline 0% vi phạm (engine enforce feasibility); action-diversity
  phân biệt (rulebot 2.14 > subsistence 0.99); chỉ adaptive phản ứng sốc.
- **P1 transcript-replay** (`minds/transcript.py`, `replay.py --from-transcript`, 6 test): mock/real
  ghi `transcript.jsonl`; replay-từ-transcript TRÙNG hash (mock50_agr 4267 call → hash `0135fa05`).
  Manifest thêm prompt/model/temperature hash.
- **E1 decision-maker ensemble** (4 policy × 3 seed): rulebot 337 hợp đồng vs feasible_random/
  subsistence/adaptive **0 hợp đồng** — "định chế tự phát" là hàm của decision-maker (`reports/
  E1_decision_maker_results.md`).
- **Bản thảo**: `reports/paper_draft.md` (v0.1) + `reports/publication_roadmap.md` +
  `reports/design_reevaluation.md`. Claim tier: mechanism_benchmark + methodology (KHÔNG empirical).
- Suite **299 passed**, ruff sạch. Pilot: `mock50_agr` (transcript-replay TRÙNG hash `0135fa05`).
- **`real50_agr`** (real LLM benchmark scenario, transcript-backed): dừng ÊM ở tick 46 (budget guard
  do server T0 disconnect dai dẳng — không degrade), 649 call, fallback 0.46%, ~$0.47. Kết quả: 2 hợp
  đồng, 0 entity, biết chữ 12% (real LLM tối thiểu định chế — nhất quán real50). **Real transcript-
  replay TRÙNG hash `a2e06edd`** (kể cả đường repair/fallback) → run LLM THẬT tái lập bit-for-bit từ
  transcript, không mạng. Đây là cổng reproducibility cho real mà LLM-ABM thường thiếu.
- **PENDING_COMPUTE (external)**: ensemble ≥30 seed × ≥2 model real + paired CI; ablation đăng ký;
  sensitivity Morris/Sobol; related-work + figures. Đây là điều kiện để lên "top-tier" thật.
