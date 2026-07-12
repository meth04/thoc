# T12 — Gate độc lập cuối cùng

Ngày: 2026-07-12. Reviewer độc lập (không viết code phiên này): reality-auditor (quét code),
adversarial-reviewer (diff+report). qa-verifier + reproducibility-steward đã ký T02/T03
(`T02-T03-qa.md`).

## Full suite + lint (integration-manager chạy)
- `pytest -q --basetemp .tmp/pytest_main -p no:cacheprovider` → **204 passed, 0 failed** (82s).
- `ruff check .` → **All checks passed**.
- world-hash bất biến: 2 run cùng seed → `b9f7002821d3648f` trùng (metric research read-only).
- `verify_research_run` + `replay --verify` (scenario/permute/policy) → replay TRÙNG hash, audit xanh.

## reality-auditor — VERDICT: PASS (0 BLOCKING/MAJOR)
Quét tĩnh 10 file phiên + đối chiếu Charter §3/§5 + ADR 0001–0004:
1. **Hard-code outcome — PASS**: `chinh_tri.bat=false` thực sự TẮT Gini-riot ở agrarian
   (`politics.py:234-235,185-186,48-49`); không năm/ngưỡng nào trực tiếp ép định chế. Anti-teleology OK.
2. **Magic fallback — PASS**: các `or 0.0` là chuẩn hóa numéraire/giá-thiếu→0 trong quy đổi giá
   trị, KHÔNG phải `or <giá cứng>` trong quyết định.
3. **Metric điều khiển engine — PASS**: `metrics_research.py` thuần đọc; không vào `world_hash`;
   `m["research"]` sau audit.
4. **Định chế ẩn — PASS**: `claims_view` tái dựng từ contract (single source of truth), không state
   trùng/bút toán mới.
5. **Determinism — PASS**: `w.rng`, `sorted`, 0 `np.random`/`random`/`time.now`.
6. **Prompt leakage — PASS (N/A)**: không đụng prompt; policy/safety chỉ trả intent.
7. **PENDING trung thực — PASS**: `AdaptivePolicy` raise NotImplementedError; `poverty_streak`/
   `failed_settlement`/registry-Claim = **0 tham chiếu toàn repo** (chưa cài, không bịa);
   undefined→None.

**MINOR (đã xử lý)**: survival-floor BẬT (kế thừa) ở agrarian scenario nhưng scope chưa liệt kê.
→ Đã thêm `behavioral_assumptions.survival_floor` vào `scenarios/agrarian_transition_v1/scope.yaml`
(minh bạch flag + cách ablation). Validation vẫn xanh.

## adversarial-reviewer — VERDICT: minor-revision (0 BLOCKING) → mọi finding ĐÃ SỬA
Xác nhận PASS: anti-teleology (test_politics chứng minh Gini cực cao + cả làng bạo động → 0 sung
công), test-fit (invariant thật, không assert outcome đẹp), observation-vs-mechanism rõ, không
overclaim (gate chặn empirical).

- **M1 (MAJOR, đã sửa)**: `verify_research_run.py` hardcode rulebot cho mode=="rulebot", bỏ qua
  `reproducibility.policy` → run tạo bằng `--policy feasible_random` bị replay bằng rulebot → hash
  LỆCH → false "THIẾU BẰNG CHỨNG". → **SỬA**: tái dựng `tao_policy(policy.name)` từ manifest (như
  replay.py); thêm test regression `test_replay_tai_dung_policy_tu_manifest` (feasible_random replay
  ĐỦ BẰNG CHỨNG, và ≠ rulebot để test có nghĩa). Verified: run thật `t12_pol_check` (feasible_random)
  → replay hash `e88cca606909` TRÙNG, verify PASS.
- **Regression tự phát hiện khi test M1**: scope.yaml `on: true` — YAML parse `on` thành khóa BOOL
  → `write_manifest` `sort_keys=True` fail khi tạo run agrarian. → **SỬA**: đổi `on` → `enabled`.
  Run agrarian tạo lại thành công.
- **m1 (MINOR, đã sửa)**: số test cũ 185/197 → cập nhật **204** (205 sau test M1) trong handoff +
  readiness.
- **m2 (MINOR, đã sửa)**: methodology §7 command `--seeds 41..70` (pseudo) → liệt kê literal 30 seed.
- **q1 (QUESTION, đã xử lý)**: methodology §7 thêm bracket [p10,p90] cho cột GDP.

## Kết luận T12
Full suite **205 passed** (sau fix), ruff sạch, replay/verify TRÙNG hash (rulebot/mock/scenario/
permute/**policy**), reality-auditor PASS, adversarial-reviewer minor-revision→đã sửa hết. Không có
BLOCKING/MAJOR còn lại. Gate cuối: **ĐẠT**.

