# T01 — Charter & migration đặc tả: review độc lập

Ngày: 2026-07-12. Owner: spec-governor (conflict map) + integration-manager (author charter/ADR).
Reviewer độc lập: adversarial-reviewer, reality-auditor (không sửa sản phẩm do mình tạo).

## Sản phẩm
- `docs/MODEL_CHARTER.md` (mới) — scope, 4 cấp claim, 5 lớp, định nghĩa tự phát, cổng định chế
  minh bạch, anti-teleology, hai track, giới hạn.
- `docs/adr/0001-scope-and-institutional-layers.md` (mới) — giải C1/C2/C3/C6/C9/C10/C12 có chủ đích.
- Banner SUPERSEDED + marker inline: `CLAUDE.md` (§7, §8), `SPEC.md` (§0 banner + row10 inline),
  `PHASES.md` (banner + Phase4 inline), `README.md`, `REPORTS.md`.
- Gate chống overclaim: `tools/validation.py` (`assert_no_overclaim`, `claim_tier_label`,
  `EMPIRICAL_TIERS`) + 3 test mới `tests/test_validation.py`.

## reality-auditor — VERDICT: PASS (không che định chế, không overclaim)
- Gate không có bypass: `claim_tier_label` chỉ trả "empirical" khi `empirical_ready`; gate raise +
  exit 2 khi tier thực chứng mà thiếu bằng chứng; observatory/reports không có wording empirical.
- Cổng định chế §5 là thật (5 điều kiện đo được), không tẩy trắng hardcode.
- C1/C2/C3 được gọi thẳng là `experimental_treatment`, không gọi "state formation nội sinh".
- 2 watch-item (low): **W1** cổng #4/#5 chưa code-enforce → `chinh_tri.bat` (đã thực hiện, xem
  T02/T08); **W2** gate chỉ kiểm `source` khác rỗng, chưa kiểm nguồn thật → siết ở T03.

## adversarial-reviewer — VERDICT: no BLOCKING, minor revision
Đã xử lý toàn bộ finding:
- **MAJOR** (marker inline SPEC row10 + PHASES Phase4 thiếu) → **ĐÃ SỬA** (strikethrough + trỏ ADR §E).
- **MINOR-1** (`EMPIRICAL_TIERS` thiếu causal/predictive/world_class) → **ĐÃ SỬA** (thêm 3 từ).
- **MINOR-2** (`empirical_ready` hardcode `== "empirical"`, không lower) → **ĐÃ SỬA** (chuẩn hóa
  `.strip().lower() in EMPIRICAL_TIERS`, nhất quán hai hàm).
- **MINOR-3 / C10** (disease shock xung đột im lặng CLAUDE.md "chỉ thời tiết") → **ĐÃ SỬA** (ADR §G:
  shock là treatment scenario-flag, default OFF).
- **QUESTION** (charter §2 trích replay làm evidence tầng-1 khi replay chưa phủ state mới) → **ĐÃ
  SỬA** (softening + cross-ref ADR §D).

## Bằng chứng chạy lại sau sửa
- `pytest tests/test_validation.py` → **5 passed**.
- `tools.validation preindustrial_closed_v1` → `empirical_ready=false`,
  `safe_claim_label=mechanism_benchmark`, exit 0 (không overclaim).
- `ruff check tools/validation.py` → clean.

## Gate T01: ĐẠT
Không còn mâu thuẫn im lặng về định chế có tên; reader phân biệt được engine mechanism / scenario
assumption / observatory label / empirical claim. W2 (provenance thật cho target empirical) route
sang T03; W1 (chinh_tri.bat enforce) đã thực hiện trong T02/T08 groundwork.
