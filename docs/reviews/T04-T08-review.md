# T04–T08 — Thiết kế (ADR) + tầng quan sát read-only

Ngày: 2026-07-12. Design: model-architect (ADR 0003, 0004, grounded file:line). Khảo sát nền:
Explore agent. Implement read-only metrics: implementation-engineer. Review độc lập: sim-economist
+ adversarial-reviewer + reality-auditor (T12 quét toàn diff).

## Thiết kế (ADR) — HOÀN TẤT

- `docs/adr/0003-household-market-land.md` (T04+T05): chốt household model (ownership cá nhân,
  KHÔNG pantry chung, membership = `economy.households`), seasonal accounting-identity view, market
  locality (per-làng order book đã có), price dispersion qua event `lang` (đường ít-rủi-ro không
  đổi world-hash), `expected_land_value` chỉ là anchor. Test matrix + IMPLEMENTED/do-now/PENDING.
- `docs/adr/0004-credit-money-fiscal.md` (T06+T07+T08): CLAIMS VIEW read-only tái dựng nợ từ clause
  (contracts là single source of truth; nợ không là số âm); commodity money + metric adoption (cấm
  ép xu); tax/fiscal metric read-only (fiscal_balance=0 vì rebate — báo trung thực); accounting
  identity đóng cho treasury PENDING. Migration bảo toàn hash legacy.

**QA của integration-manager (đọc cả 2 ADR):** grounded chính xác (file:line khớp khảo sát); tách
IMPLEMENTED/do-now/PENDING rõ; anti-teleology + cổng định chế §5 tuân thủ; đường read-only chứng
minh không đổi world-hash; mọi mục engine-mutation (registry `Claim`, treasury/public-goods,
`poverty_streak`, `ghi_gia`-by-làng, `failed_settlement`) đánh dấu PENDING kèm điều kiện cổng §5 +
review. Không có claim thực chứng. **Đạt yêu cầu "thiết kế trước code".**

## Phân định phạm vi mỗi task

| Task | IMPLEMENTED (đã có) | LÀM NGAY (read-only metric) | PENDING (engine mutation + review) |
|---|---|---|---|
| T04 hộ | membership/snapshot/food_security, ownership cá nhân, survival floor | seasonal identity view; `marketed_surplus`, `consumption_gini`, `yield_per_parcel` | `poverty_duration` (`w.poverty_streak`); pantry (nếu cần) |
| T05 chợ/đất | per-làng order book, call auction, sealed-bid đất, transport-fee-via-ledger, price≠rent | `price_dispersion_by_asset` (event `lang`); coverage-guard | `ghi_gia` khóa theo làng (phá hash) |
| T06 tín dụng | nợ=tổ hợp clause, thế chấp+xiết, ledger cấm âm | CLAIMS VIEW + `debt_service`/`outstanding`/`concentration`/`arrears` | registry object `Claim` (seniority/transfer/resolution) |
| T07 tiền | xu commodity money, agent chọn thanh toán, velocity+nhãn tiền tệ hóa | `monetary_share_by_value/stock`, `acceptance_breadth`, `payment_concentration`, barter/credit share | `failed_settlement` counter |
| T08 tài khóa | CONG_QUY conduit, thuế-rebate, `chinh_tri.bat` gate, Gini-riot gated OFF | `tax_revenue`, `fiscal_balance` (=0, trung thực) | treasury balance sheet + public goods + depreciation |

## Read-only metrics implementation — VERIFIED
`engine/metrics_research.py` (implementation-engineer): `research_metrics(w)` + `claims_view(w)`,
thuần đọc ledger/hợp đồng/cửa sổ thanh toán; gọi trong `tick.py` SAU audit, gắn `m["research"]`,
KHÔNG vào `world_hash`; thêm field `lang` vào event `khop_cho` (chỉ payload journal).
- Bằng chứng: **204 passed** (test `test_metrics_research.py` 7 pass); ruff sạch; **world-hash
  bất biến** (2 run cùng seed → `b9f7002821d3648f` trùng — metric read-only không đụng determinism).
- Run thật `t12_cf_check_baseline_s41` (agrarian, 20 tick): `m["research"]` có **24 khóa**;
  `credit_outstanding=2049`, `n_claims=39` (tái dựng từ clause), `income_gini=0.687` (tách khỏi
  `gini_thoc`), `monetary_share_by_value=0` (chưa dùng xu — trung thực), `tax_revenue=0`/
  `fiscal_balance=0` (politics off — trung thực), undefined→`None` (không 0 giả).
- PENDING trung thực (KHÔNG bịa): `poverty_duration`, `failed_settlement`, Claim registry object,
  treasury/public-goods, `ghi_gia`-by-làng. Undefined→None, chưa cài engine mutation.

Review độc lập: reality-auditor (quét code) + adversarial-reviewer (T12) — xem `docs/reviews/T12-gates.md`.

## Trạng thái task
T04–T08 = **thiết kế xong (ADR) + tầng quan sát do-now (metric/test)**; các cơ chế engine-mutation
(registry, treasury, public goods, poverty streak, per-làng price key, failed-settlement) là
**PENDING** có spec + điều kiện cổng §5 — KHÔNG bịa là đã implement.
