# Methodology — `agrarian_transition_v1` (mechanism benchmark)

Ngày: 2026-07-12. Claim tier: **mechanism_benchmark** (không phải empirical — charter §2).
Tài liệu này mô tả PHƯƠNG PHÁP; kết quả (nếu có) chỉ là `mechanism_result`, không phải bằng
chứng về nền kinh tế thật. Nguồn: `docs/MODEL_CHARTER.md`, `docs/adr/0001..0004`,
`scenarios/agrarian_transition_v1/` (scope, priors, provenance, protocol, data_contract).

## 1. Phạm vi & đơn vị

Cộng đồng nông nghiệp GIẢ ĐỊNH, khép kín một phần. Đơn vị kinh tế = **hộ gia đình**; đơn vị nhân
khẩu = **cá nhân** (tuổi/giới/kỹ năng/hôn nhân/thừa kế/lao động). 1 tick = 6 tháng (mùa mưa/khô).
Biên thương mại: nội bộ (chưa có thị trường ngoại vùng). Không địa danh/lịch sử thật.

## 2. Kiến trúc 5 lớp (charter §3)

| Lớp | Nội dung | Ràng buộc |
|---|---|---|
| 1 Vật lý | đất, mùa vụ, tồn kho, lao động, vận tải, dân số, thời tiết | DUY NHẤT lớp bảo toàn vật chất; random qua `w.rng` |
| 2 Kế toán | ledger sổ kép + FlowRegistry; audit mỗi tick | không số dư âm; mọi flow có đối ứng |
| 3 Thể chế | quyền đất, hợp đồng-clause, pháp nhân, (tín dụng/tiền/tài khóa) | bật/tắt theo scenario flag; cổng minh bạch (ADR 0001 §B) |
| 4 Hành vi | BehaviorPolicy (rulebot/feasible_random/subsistence/…); LLM là treatment | không mutate world; tất định |
| 5 Đài quan sát | classifier giai cấp, nhãn định chế, metrics, chronicle | CHỈ ĐỌC; nhãn không điều khiển engine |

Tầng chính trị/bạo động (bầu cử, thuế, sung công Gini) **TẮT mặc định** ở scenario này
(`chinh_tri.bat: false`), chỉ bật như treatment tường minh (ADR 0001 §C).

## 3. Accounting identities (INVARIANT, audit mỗi tick)

- Bảo toàn từng tài sản: `tổng_cuối = tổng_đầu + Σ nguồn − Σ hủy` (FlowRegistry).
- Đất: tổng thửa const; mỗi thửa đúng 1 chủ (người/pháp nhân) hoặc công.
- Tín dụng: tài sản đòi nợ của chủ nợ = nghĩa vụ con nợ (theo clause hợp đồng; nợ KHÔNG là số âm).
- Tài khóa (khi bật): `công_quỹ_cuối = công_quỹ_đầu + thuế + vay + phát_hành − chi − trả_nợ − hao_mòn`
  (mỗi flow có counterpart). Hiện tại tax = rebate ngay (chưa có treasury tích lũy — PENDING T08).

## 4. Baseline hành vi (ADR 0002)

- `rulebot` — legacy heuristic (baseline hợp lệ).
- `feasible_random` — negative baseline (chọn ngẫu nhiên trong hành động khả thi).
- `subsistence` — canh đủ ăn, không hợp đồng/đầu tư.
- `adaptive` — kỳ vọng thích nghi (PENDING nếu chưa cài đủ).
- `mock`/`real` (LLM) — CHỈ treatment sau cùng; không dùng cho kết luận cơ chế.

## 5. Giao thức thí nghiệm (pre-registered)

`scenarios/agrarian_transition_v1/preanalysis_protocol.yaml` khóa: câu hỏi, estimand/outcome,
seed list (smoke 3 / primary 30), horizon, policy set, treatment overlay + expected_sign +
falsifier, failed-run handling (đếm, extinction hợp lệ), no-claim conditions, uncertainty
(median + p10/p90 + failed count). **Khóa TRƯỚC khi chạy ensemble đầy đủ; không tune sau khi xem.**

## 6. Runs & uncertainty

- Runner: `tools/counterfactual.py` — paired-seed, isolated experiment dir, summary
  n/mean/median/p10/p90 + paired_delta_vs_baseline.
- Smoke orchestration (3 seed, horizon ngắn): xem §7.
- Ensemble đầy đủ (30 seed × 600 tick × policy/treatment): **PENDING_COMPUTE** — command tái lập
  trong protocol; KHÔNG bịa kết quả.

## 7. Kết quả smoke orchestration (mechanism_result — KHÔNG phải empirical)

**Cảnh báo diễn giải:** đây là smoke để KIỂM ORCHESTRATION, KHÔNG phải phân tích chính. n=3 seed,
horizon=60 tick (rất ngắn), policy=rulebot, scenario=agrarian_transition_v1. Treatment ở đây là
bộ C1–C4 của runner (no_contract_seeds/permute_personas/no_parameter_noise/adverse_weather), KHÁC
với treatment vật lý trong `preanalysis_protocol.yaml` (land_scarcity/weather_risk/transport_cost/
placebo — chưa nối vào runner, xem §hạn chế). Nguồn: `data/experiments/t10_agr_smoke_rulebot_60t/`.

Mỗi ô = mean [p10, p90] trên n=3 seed (khoảng RẤT rộng ở n=3 — không đọc mean như điểm).

| treatment | dân số | thóc/người | Gini đất | Gini thóc | GDP |
|---|---:|---:|---:|---:|---:|
| baseline | 155.0 [144, 168] | 2864 [2623, 3127] | 0.675 [0.669, 0.680] | 0.734 [0.725, 0.740] | 23316 [21312, 24995] |
| c1_no_contract_seeds | 155.0 [144, 168] | 2864 [2623, 3127] | 0.675 | 0.734 | 23316 [21312, 24995] |
| c2_permute_personas | 168.3 [161, 175] | 2929 [2558, 3386] | 0.669 | 0.727 | 27772 [14283, 42840] |
| c3_no_parameter_noise | 155.0 [144, 168] | 2864 [2623, 3127] | 0.675 | 0.734 | 23316 [21312, 24995] |
| c4_adverse_weather | 147.7 [143, 154] | 2227 [1956, 2456] | 0.691 [0.676, 0.708] | 0.766 [0.745, 0.788] | 21822 [15144, 30076] |

Quan sát (mechanism_result): (a) `c4_adverse_weather` → thóc/người↓, Gini đất/thóc↑ — đúng dấu cơ
chế; (b) `c1`/`c3` TRÙNG baseline ở horizon 60 tick với rulebot (mẫu hợp đồng ban đầu và nhiễu
tham số chưa tạo khác biệt sớm) — báo trung thực, không phải bằng chứng "không có tác động" ở
horizon dài; (c) `ty_trong_phi_nong`=0 ở mọi ô (chưa chuyên môn hóa ở 60 tick).

**Ensemble đầy đủ (30 seed × 600 tick × policy/treatment): `PENDING_COMPUTE`.** Command tái lập
(seed liệt kê literal — `--seeds` nhận nargs, KHÔNG có cú pháp range):
```
python -m tools.counterfactual --scenario agrarian_transition_v1 \
    --seeds 41 42 43 44 45 46 47 48 49 50 51 52 53 54 55 56 57 58 59 60 \
            61 62 63 64 65 66 67 68 69 70 \
    --ticks 600 --mode rulebot --prefix agr_full
```
Chạy lại với `--suite baseline c4_adverse_weather ...` cho từng treatment; đổi policy qua
`run.py --policy` + counterfactual per-policy. Không bịa kết quả 30-seed; không coi smoke là phân
tích chính. Ước tính compute: 30 seed × 5 treatment × 600 tick rulebot ≈ vài giờ CPU cục bộ.

## 8. Failure modes & giới hạn

- Một run = một lịch sử khả dĩ; báo phân phối theo seed, không báo một seed.
- Tham số phần lớn `design_assumption` → kết quả nhạy với giả định chưa hiệu chuẩn.
- Cơ chế credit registry / treasury / public goods còn PENDING (ADR 0004) → kết luận về tín
  dụng/tài khóa hạn chế.
- Chưa có holdout → không có claim tầng 4. Xem `reports/world_class_readiness.md`.
