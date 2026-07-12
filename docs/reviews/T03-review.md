# T03 — Scenario package & provenance cho `agrarian_transition_v1`

Ngày: 2026-07-12. Owner: research-planner + empirical-validation (author). Reviewer độc lập:
agrarian-economist + reproducibility-steward (xem `docs/reviews/T02-T03-qa.md`).

## Sản phẩm
- `scenarios/agrarian_transition_v1/` — 9 file: `scope.yaml`, `parameters.yaml`, `priors.yaml`,
  `provenance.csv`, `data_dictionary.md`, `targets_in_sample.yaml`, `targets_holdout.yaml`,
  `policy_experiments.yaml`, `data_contract.md`.
- `validation_tier: mechanism_benchmark`; đơn vị = hộ + cá nhân; 1 tick = 6 tháng (mùa mưa/khô);
  biên thương mại nội bộ; 5 lớp phát triển bật/tắt, tầng chính trị/bạo động **default OFF**
  (`chinh_tri.bat: false` — flag do engine gate ở T02/T08 thực thi; đã kiểm run thật politics off).
- `parameters.yaml`: chỉ 1 override có chủ đích (`chinh_tri.bat: false`), phần còn lại kế thừa
  `config/world.yaml` (không "ép" kết quả).
- `priors.yaml`/`provenance.csv`: 6 tham số, TẤT CẢ `status: design_assumption`, source TRỐNG,
  có unit + plausible_range. Không bịa địa danh/lịch sử/nguồn/DOI/target.
- `data_contract.md`: hợp đồng nhập liệu cho data thật tương lai (raw bất biến → processed
  versioned → scenario; provenance bắt buộc; split in-sample/holdout enforce bằng test).

## Nâng cấp validation (implementation-engineer, W2 từ T01)
- `tools/validation.py`: thêm `missing_units`, `provenance_all_sourced` (W2: chỉ empirical khi mọi
  provenance status ∉ {design_assumption, ""}), `target_split_error` (in_sample ∩ holdout = ∅),
  `targets_sourced`; tách hàm thuần `_empirical_ready`. `assert_no_overclaim` message đầy đủ hơn.
- Test: `tests/test_validation.py` — **8 passed** (5 cũ + 3 mới, gồm: provenance design_assumption
  KHÔNG thể empirical; target split disjoint bị bắt; hai benchmark vẫn không đổi).

## Bằng chứng
- `tools.validation preindustrial_closed_v1` và `... agrarian_transition_v1` → cả hai
  `empirical_ready=false`, `provenance_all_sourced=false`, `missing_units=[]`,
  `target_split_error=null`, `safe_claim_label=mechanism_benchmark`, exit 0 (KHÔNG overclaim).
- Run thật `agr_smoke_rb_s41` (rulebot 20 tick, scenario): `verify_research_run` ĐỦ BẰNG CHỨNG,
  0 political event (politics off qua flag). `pytest tests/test_validation.py` 8 passed; ruff sạch.

## Còn mở (route)
- `chinh_tri.bat` engine gate: **đã thực hiện** (T02/T08 groundwork, `engine/politics.py` +
  `config/world.yaml`, test `test_politics.py`).
- Layer L2–L4 (tín dụng/tiền/tài khóa) trong scope.yaml phần lớn là **design intent** — cơ chế
  engine tương ứng: một phần ĐÃ có (chợ, xu, clause tín dụng), một phần PENDING (registry nợ,
  treasury, public goods) — xem ADR T06/T07/T08.
