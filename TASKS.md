# TASKS — Chương trình hoàn thiện THÓC theo chuẩn khoa học

Ngày lập: 2026-07-12  
Chế độ thực thi: tự chủ, không dùng provider/LLM thật, không dùng mạng.  
Tài liệu vận hành cho Claude Code: dùng cùng `.claude/agents/README.md`.

## 0. Mục tiêu thật và định nghĩa hoàn thành

Mục tiêu của chương trình này **không** phải ép một run đi đến “công nghiệp hóa”, cũng
không phải tuyên bố rằng THÓC đã mô phỏng đúng một nền kinh tế thật. Mục tiêu là đưa repo
đến một nền tảng nghiên cứu có thể kiểm toán cho câu hỏi hẹp:

> Trong một cộng đồng nông nghiệp có đất, mùa vụ, dị biệt hộ và thông tin cục bộ, điều
> kiện nào làm chuyên môn hóa, tín dụng, phương tiện trao đổi và năng lực công quyền bền
> vững hơn các lựa chọn thay thế?

Kết thúc chương trình, dự án phải có một scenario mới `agrarian_transition_v1` được ghi
rõ là **mechanism benchmark**, lõi hạch toán/feasibility/tái lập mạnh, các lớp hộ–chợ–tín
dụng–tiền hàng hóa–tài khóa có thể bật/tắt theo scenario, baseline không LLM, bộ thí
nghiệm paired-seed, và report trung thực về những gì mô hình chứng minh/chưa chứng minh.

“Hoàn thành” **không** có nghĩa có dữ liệu lịch sử hoặc được phép gửi paper thực chứng.
Nếu không có raw data có nguồn, targets và holdout, trạng thái đúng là
`mechanism_benchmark`, không phải `empirically_validated`.

## 1. Luật thực thi không được thương lượng

1. Chỉ chạy Python bằng `conda run -n thoc-env python ...`. Không tạo/cài lại conda env
   nếu env đã tồn tại. Không dùng Python bên ngoài env.
2. Không gọi mode `real`, `--smoke`, provider, MCP từ xa, WebSearch hay bất kỳ API/LLM
   nào. Không đọc, in, sửa hoặc commit `.env`/secret. Dùng `rulebot`, mock cục bộ,
   FakeTransport và transcript fixture nếu cần.
3. Working tree đang bẩn và chứa thay đổi quan trọng của người dùng. Không chạy `git
   reset`, `git checkout`, `git clean`, không xóa/ghi đè run/report có sẵn, không staging
   hoặc commit tự động. Không sửa thay đổi ngoài phạm vi task.
4. Không được bịa data source, DOI, unit, calibration target, historical result hay test
   result. `design_assumption` phải giữ nguyên nhãn cho đến khi có evidence thật.
5. Không nới assertion, skip test, tăng tolerance, hard-code seed/horizon/threshold hoặc
   đổi report để làm outcome đẹp. Kết quả “không hình thành tiền/chính phủ”, sụp đổ hoặc
   bất ổn là kết quả hợp lệ.
6. Mọi mutation tài sản/nợ/tiền/công quỹ đi qua giao dịch có đối ứng và audit. Mọi random
   đi qua `w.rng`; mọi mutation có thứ tự ổn định; policy/LLM không được sửa `World` trực
   tiếp.
7. Chỉ agent độc lập mới đóng gate: người viết code không tự phê duyệt code/test/report
   của mình. Mọi finding `blocking` phải được giải quyết hoặc ghi rõ là chưa hoàn thành.
8. Không tự hỏi người dùng để chọn hướng. Khi có chi tiết chưa xác định, chọn phương án
   nhỏ nhất có thể kiểm chứng, ghi ADR/DECISIONS và tiếp tục. Chỉ dừng nếu không thể bảo
   toàn thay đổi hiện có mà không có một hành động phá hủy.

## 2. Bằng chứng đầu vào cần tôn trọng

- `preindustrial_closed_v1` tự nhận là `mechanism_benchmark`; cả in-sample và holdout
  targets đều rỗng; `provenance.csv` chỉ có design assumptions. Không được đổi nhãn này.
- `PROGRESS.md` là báo cáo nghiệm thu mock cũ; `REPORTS.md` là manifesto/đề xuất, không
  phải bằng chứng thực chứng. `REVIEW.md` là đánh giá khoa học mới hơn và cần được đọc kỹ.
- `CLAUDE.md`/`SPEC.md` cũ cấm định chế có tên, nhưng mã hiện có đã có `ChinhQuyen`, thuế,
  bạo động, xu, pháp nhân và các nhãn ngân hàng. Đây là mâu thuẫn đặc tả phải giải quyết
  có chủ ý, không được lờ đi.
- Kết quả đã lưu: mock/rulebot có audit và replay tốt; real pilot 30 năm không phải
  ensemble và khác mạnh với mock. Chúng chỉ là evidence kỹ thuật/pilot, không là evidence
  hành vi hay kinh tế sử.
- Suite hiện có 170 tests được collect. Lần audit sandbox trước đó đạt 158 pass nhưng 12
  lỗi fixture `tmp_path` do quyền thư mục tạm Windows; không được ghi thành “toàn bộ xanh”
  cho tới khi chạy lại trên thư mục tạm writable.

## 3. Cách dùng agent và bằng chứng

`integration-manager` điều phối; không giao một thay đổi lớn cho một agent duy nhất.
Với mỗi task code, workflow tối thiểu là:

1. `spec-governor` (nếu có xung đột) + `research-planner` + economist phù hợp tạo memo;
2. `model-architect` tạo ADR/interface/test matrix;
3. `implementation-engineer` hoặc specialist (`engine-surgeon`, `minds-engineer`,
   `graph-architect`) implement;
4. `test-engineer` bổ sung test độc lập;
5. `qa-verifier`, `reproducibility-steward` và `adversarial-reviewer` kiểm độc lập;
6. `integration-manager` ghi factual status vào task/report.

Lưu evidence ngắn vào `docs/reviews/<TASK-ID>-<role>.md` (do agent chính ghi lại từ kết
quả của reviewer nếu reviewer chỉ đọc). Mỗi memo phải có command, output, file:line và
verdict. Chỉ đánh dấu checkbox sau khi acceptance criteria có evidence.

## 4. Backlog theo dependency

### T00 — Chụp baseline an toàn và lập bản đồ mâu thuẫn

**Owner:** `integration-manager`  
**Độc lập:** `qa-verifier`, `reproducibility-steward`, `spec-governor`

- [x] Ghi snapshot chỉ-đọc của `git status --short`, `git diff --check`, commit hiện tại,
  Python/requirements version, scenario/run inventory và test collection vào
  `docs/reviews/T00-baseline.md`. Không đặt lại hoặc stage file nào.
  → `docs/reviews/T00-baseline.md`: commit d23b86c, Python 3.11.15, 170 tests collected, 45 run cũ.
- [x] Chạy collection và suite có đường tmp nằm trong workspace, ví dụ tạo `.tmp/pytest`
  rồi chạy `conda run -n thoc-env python -m pytest -q --basetemp .tmp/pytest -p
  no:cacheprovider`. Nếu sandbox/ACL vẫn cản, thử một đường workspace khác hợp lệ, ghi
  nguyên error và tiếp tục các task không phụ thuộc; không sửa test chỉ để né ACL.
  → **170 passed** (`.tmp/logs/T00_pytest.log`); blocker ACL cũ (12 lỗi) được vòng tránh bằng
  `--basetemp .tmp/pytest`. ruff sau fix: **All checks passed** (`.tmp/logs/T00_ruff*.log`).
- [x] Lập “conflict map” có file:line giữa `CLAUDE.md`, `SPEC.md`, `PHASES.md`,
  `REPORTS.md`, `REVIEW.md`, scenario và code hiện tại. Phân loại: invariant bất biến,
  aspiration đã lỗi thời, implementation hiện hữu, và quyết định còn mở.
  → `docs/reviews/T00-spec-governor-conflict-map.md`: 11 mâu thuẫn (INVARIANT 2, ASPIRATION 2,
  IMPLEMENTATION 2, OPEN 5) + 1 compliant, file:line hai phía.
- [x] Rà thay đổi chưa commit hiện có, nhất là scenario/manifest/validation, household
  metrics, survival floor, disease, output-isolation. Sửa bug/regression xác thực được
  trong phạm vi đó và thêm test hồi quy; không xem một diff bẩn là lý do để vứt code.
  → `docs/reviews/T00-engine-surgeon-uncommitted.md`: **0 BLOCKING**; sửa ruff gate (B023 +
  4 auto-fix); MINOR 2–6 route sang T02/T03/T09/T10/T12. B023 không đổi hành vi (fmt gọi ngay)
  nên không cần test hồi quy mới; suite 170 vẫn xanh.

**Gate:** có baseline report trung thực; suite/lint có kết quả hoặc blocker môi trường có
bằng chứng; không có thay đổi bị mất. → **ĐẠT** (2026-07-12).

### T01 — Charter và migration đặc tả: từ “radical emergence” sang mô hình có thể kiểm định

**Owner:** `spec-governor`  
**Độc lập:** `research-planner`, `adversarial-reviewer`, `reality-auditor`

- [x] Viết `docs/MODEL_CHARTER.md`: scope của THÓC, cấp độ claim, đơn vị phân tích, layers
  (physical constraints / accounting / institution / behavior / observatory), definition
  của endogenous emergence, các giới hạn và anti-teleology rules. → `docs/MODEL_CHARTER.md`.
- [x] Viết ADR `0001-scope-and-institutional-layers.md`. Quyết định phải bảo toàn ledger,
  replay và policy isolation, đồng thời cho phép các module minh bạch `credit`, `money`,
  `fiscal` khi và chỉ khi có alternative, cost, accounting identity, scenario flag và
  ablation. Không gọi mọi cấu trúc state là “tự phát”. → `docs/adr/0001-...md` (§B cổng 5 điều kiện).
- [x] Quy định hai track không lẫn nhau (charter §6, ADR §F):
  - `preindustrial_closed_v1`: legacy mechanism/regression benchmark, không retcon thành
    lịch sử thật;
  - `agrarian_transition_v1`: benchmark mới cho đường nông nghiệp → trao đổi → tín dụng
    → tiền hàng hóa → năng lực công quyền.
- [x] Đồng bộ có chọn lọc `CLAUDE.md`, `SPEC.md`, `PHASES.md`, `README.md`, `REPORTS.md`
  và agent docs bằng link tới charter/ADR. Mark phần superseded, không xóa lịch sử hay đổi
  report cũ. Bỏ acceptance criterion “tune median industrialization year” khỏi định nghĩa
  khoa học; có thể giữ nó như legacy regression label riêng. → banner + strikethrough inline
  (CLAUDE §7/§8, SPEC row10, PHASES Phase4, README, REPORTS).
- [x] Thêm test/documentation gate để scenario benchmark không thể in hoặc export với nhãn
  `empirically_validated` khi targets/provenance cần thiết rỗng. → `tools/validation.py`
  (`assert_no_overclaim`/`claim_tier_label`/`EMPIRICAL_TIERS`) + `tests/test_validation.py` (5 passed).

**Gate:** không còn mâu thuẫn im lặng về định chế có tên; reader mới biết chính xác điều gì
là engine mechanism, scenario assumption, observatory label và empirical claim.
→ **ĐẠT** — review độc lập `docs/reviews/T01-review.md` (reality-auditor PASS; adversarial-reviewer
no-BLOCKING, mọi MAJOR/MINOR đã sửa). W2 route T03.

### T02 — Nền tảng chạy được, kiểm toán được và output không lẫn nhau

**Owner:** `engine-surgeon` + `implementation-engineer`  
**Độc lập:** `test-engineer`, `qa-verifier`, `reproducibility-steward`

- [x] Hoàn thiện một lệnh local, không mạng để chạy test/lint/audit/replay trong thư mục
  tạm writable; thêm script/documentation verification nếu cần. Không làm CI pass bằng
  bỏ test integration. → `tools/verify_local.py` (ruff+pytest+validation+smoke+verify) → XANH;
  `tests/conftest.py` guard `THOC_BLOCK_NETWORK`. (`.tmp/logs/T02_verify_local.log`)
- [x] Chuẩn hóa output isolation: manifest, events, metrics, report, figures và analysis
  của mỗi run nằm dưới run directory hoặc output directory explicit. Tools không được
  ghi đè `reports/final_analysis.md`/PNG chung. → `analyze.py`/`compare.py` ghi vào
  `data/runs/<run>/reports/`; test `test_analyze_isolation`/`test_compare_isolation` pass.
- [x] Audit migration/checkpoint/world hash cho mọi state hiện có (household helper,
  political state, disease, safety floor, entities, payment statistics). → C12 ĐẠT:
  `world_hash` phủ ChinhQuyen/entities/quan hệ; disease qua health; checkpoint pickle toàn bộ +
  migration (`docs/reviews/T02-review.md §3`).
- [x] Tạo `tools/verify_research_run.py`: kiểm manifest schema, config digest, scenario hash,
  event/metric consistency, ledger audit và replay rulebot/mock. Tool chỉ đọc, nonzero khi
  evidence thiếu. → `tools/verify_research_run.py` + `tests/test_verify_research_run.py` (6 passed).
- [x] Thêm CI config cục bộ/portable cho Python 3.11, tests, ruff và không-network guard.
  → `.github/workflows/ci.yml` (THOC_BLOCK_NETWORK=1, pin requirements, không provider thật).

**Gate:** test suite xanh trên temp path writable; rulebot/mock smoke run replay cùng hash;
output không chồng. → **ĐẠT** (reproducibility-steward độc lập: **185 passed**, replay scenario+permute
TRÙNG hash, isolation OK, C12 OK; `docs/reviews/T02-T03-qa.md`). Sửa kèm: `replay.py` tái dựng
overlay/treatment từ manifest.

### T03 — Scenario package và provenance có cấu trúc cho `agrarian_transition_v1`

**Owner:** `research-planner` + `empirical-validation`  
**Độc lập:** `agrarian-economist`, `reproducibility-steward`

- [x] Tạo `scenarios/agrarian_transition_v1/` với `scope.yaml`, `parameters.yaml`,
  `priors.yaml`, `provenance.csv`, `data_dictionary.md`, `targets_in_sample.yaml`,
  `targets_holdout.yaml`, `policy_experiments.yaml` và overlay config rõ ràng. → 9 file
  (+`data_contract.md`); `tools.validation` xanh.
- [x] Scope phải là cộng đồng nông nghiệp giả định, một đơn vị thời gian/mùa vụ và biên
  thương mại rõ; ban đầu đặt `validation_tier: mechanism_benchmark`. Không giả địa danh,
  lịch sử, source hoặc target. → `scope.yaml` (hộ+cá nhân, tick=6 tháng, biên nội bộ).
- [x] Parameter registry bao phủ parameter kinh tế quan trọng scenario override: unit,
  semantic meaning, central/range/prior, status, role. Số chưa có data → `design_assumption`.
  → `priors.yaml` (6 tham số) + `provenance.csv` (status=design_assumption, source trống).
- [x] Nâng `tools.validation` để validate schema, units, provenance status, missing data,
  target split và claim tier; fail descriptive nếu scenario tự nhận empirical mà metadata
  thiếu. → `missing_units`/`provenance_all_sourced`(W2)/`target_split_error`; 8 test pass.
- [x] Viết import-template/data-contract cho dữ liệu tương lai, không tải data mạng.
  → `scenarios/agrarian_transition_v1/data_contract.md` (raw→processed→scenario versioned + test).

**Gate:** scenario mới load/manifest/replay được; test xác nhận không nhầm với empirical; package
đủ thông tin để người ngoài biết mỗi số là assumption hay evidence. → **ĐẠT** — run thật
`agr_smoke_rb_s41` verify xanh; `docs/reviews/T03-review.md`. QA độc lập: `docs/reviews/T02-T03-qa.md`.

### T04 — Lõi hộ nông nghiệp, mùa vụ và phân phối

**Owner:** `agrarian-economist` + `model-architect`  
**Implementer:** `implementation-engineer`/`engine-surgeon`  
**Độc lập:** `test-engineer`, `sim-economist`, `adversarial-reviewer`

- [ ] Chốt ADR cho household model trước code: membership ổn định qua cưới/sinh/chết/tái
  hôn/cưu mang; household head/decision representation; ownership cá nhân so với pantry
  chung; serialization/migration; income, consumption, assets và liquidity không lẫn.
- [ ] Thực hiện tối thiểu model đã chốt. Nếu pantry chung được thêm, nó phải là chủ thể
  ledger hoặc mọi transfer vào/ra phải explicit; không âm thầm gom tài sản của thành viên.
  Nếu không thêm pantry, household budget phải vẫn chỉ là derived, read-only view.
- [ ] Xây seasonal budget constraint cho đất, hạt giống, công lao động, sản lượng, tồn
  kho, hao hụt, dinh dưỡng, nhà ở và thừa kế. Tách rõ stock/flow, danh nghĩa/hiện vật,
  và giá trị quan sát/decision rule.
- [ ] Thay magic fallback kinh tế trong policy (ví dụ price/wage cố định ẩn) bằng state,
  scenario parameter có unit hoặc explicit “no-information” behavior. Không để metric
  điều khiển engine.
- [ ] Mở rộng metrics/event journal: household food security, marketed surplus, yield per
  parcel, land/wealth/consumption/income Gini tách biệt, poverty duration, mobility và
  liquidity. Định nghĩa rõ missing/zero/undefined.
- [ ] Viết invariant/property/negative tests: trẻ không rơi khỏi hộ; ăn đủ không giảm khi
  household grain tăng; đất màu mỡ hơn không giảm expected output ceteris paribus; shock
  chỉ đi qua declared state; death/inheritance không tạo/mất tài sản trái phép.

**Gate:** agrarian core chạy rulebot deterministic với audit xanh; metric household không
double-count; tests chứng minh seasonal/accounting identities và không rely on one seed.
→ **DESIGN+METRICS (T04)**: ADR `docs/adr/0003` chốt (ownership cá nhân, KHÔNG pantry, membership
= `economy.households`); magic price fallback đã gỡ (T00); metric read-only `income_gini` (tách),
`consumption_gini`, `marketed_surplus`, `yield_per_parcel` (`engine/metrics_research.py`, verified,
world-hash bất biến). **`poverty_duration` ĐÃ CÀI** (`w.poverty_streak` observation-state, không
vào world_hash, migration + 8 test, 2-run-same-seed-same-hash). **PENDING**: seasonal-identity view
+ comparative-statics test đầy đủ, pantry — cần engine mutation + review. `docs/reviews/T04-T08-review.md`.

### T05 — Chợ địa phương, giá, vận tải và đất đai

**Owner:** `agrarian-economist` + `model-architect`  
**Implementer:** `implementation-engineer`/`engine-surgeon`  
**Độc lập:** `test-engineer`, `qa-verifier`, `reality-auditor`

- [ ] Thiết kế market locality: chợ/session/location, reachable sellers/buyers, transport
  cost paid by a declared party, information set and timing. Không dùng một global price
  như engine truth; transaction price là kết quả khớp lệnh.
- [ ] Giữ call auction/land auction nếu phù hợp, nhưng khi nhiều làng tồn tại phải có
  price dispersion and trading frictions. Market access/transport costs phải đi vào
  ledger/event, không chỉ trừ metric.
- [ ] Hoàn thiện land module: ownership, use-right/rent, sale, collateral, fertility,
  expected net return và market valuation là các khái niệm tách. `expected_land_value`
  chỉ là behavioral signal minh bạch, không được đặt giá giao dịch.
- [ ] Tạo comparative-statistics suite: tăng transport cost không làm price dispersion
  giảm có hệ thống; productive parcel không có expected return thấp hơn khi các điều
  kiện khác giữ nguyên; bỏ chợ/bịt đường không làm market participation tăng.
- [ ] Báo liquidity/price coverage trước khi suy luận price-to-rent. Không suy luận từ
  fewer-than-threshold transactions.

**Gate:** mọi market/land transaction còn audit/replay; report có coverage và không có
claim về “giá thị trường” khi dữ liệu mô phỏng quá thưa.
→ **DESIGN+METRICS (T05)**: ADR `docs/adr/0003`; per-làng order book + call auction + sealed-bid
đất + transport-fee-via-ledger đã CÓ; price≠rent tách; `expected_land_value` chỉ là anchor;
`price_dispersion_by_asset` + coverage-guard (`metrics_research.py`, event `lang` mới — không đổi
world-hash). **Gate T05 ĐẠT bằng đường D1** (event `lang`). **KHÔNG cài `ghi_gia`-by-làng (D2) có
chủ đích** — ADR 0003 §D nói D2 phá hash mọi run/checkpoint cũ, chỉ làm "nếu D1 không đủ"; D1 đủ đo
dispersion. D2 = refinement tùy chọn (scenario-gated + version) nếu tương lai cần. PENDING (còn):
comparative-statics suite đầy đủ (transport↑→dispersion↑) — T10/test-engineer.

### T06 — Tín dụng là claim có đối ứng, không phải một hợp đồng mơ hồ

**Owner:** `monetary-fiscal-economist` + `model-architect`  
**Implementer:** `engine-surgeon`/`implementation-engineer`  
**Độc lập:** `test-engineer`, `qa-verifier`, `adversarial-reviewer`

- [ ] Viết ADR/data model cho `Claim`/credit registry: id, creditor, debtor, unit,
  principal/outstanding, rate/condition, maturity, collateral, seniority, repayment,
  default, restructuring/forgiveness, transfer và resolution on death/entity exit.
- [ ] Thực hiện registry có một nguồn sự thật. Tài sản đòi nợ của creditor phải luôn là
  liability của debtor theo quantity/unit; no negative cash/commodity balance; tất cả
  settlement/collateral/charge-off có event và ledger counterpart.
- [ ] Tích hợp với grammar hợp đồng theo migration rõ ràng, nhưng không coi các contract
  periodic cũ tự động là loan. Preserve/replay legacy contracts and expose migration only
  for new scenario.
- [ ] Bổ sung borrower/lender balance-sheet views and metrics: debt service, arrears,
  default, claims concentration, secured/unsecured exposure, risk sharing. Market-value
  estimate là observation tách với face value.
- [ ] Test loan origination/repayment/default/collateral/death/bankruptcy/claim-transfer,
  including exact balance-sheet identity each tick and a failure case with insufficient
  collateral. Add paired counterfactual: credit disabled vs enabled; do not predeclare
  that it raises welfare.

**Gate:** không có “nợ” biểu diễn bằng số dư âm hoặc lost counterparty; auditor có thể
reconstruct all outstanding claims from event/ledger records.
→ **DESIGN+METRICS (T06)**: ADR `docs/adr/0004`; ledger cấm số dư âm (nợ = nghĩa vụ clause, không
âm); **CLAIMS VIEW read-only** `claims_view(w)` tái dựng creditor/debtor/collateral từ hợp đồng
(single source of truth) + metric `credit_outstanding`/`debt_service`/`arrears`/`n_claims` (verified:
run thật n_claims=39, outstanding=2049; đối xứng claim test). **Gate T06 ĐẠT bằng VIEW**: auditor
tái dựng được mọi claim từ event/ledger (không số dư âm). **KHÔNG cài registry OBJECT có chủ đích**
— ADR 0004 §T06-C nói object chỉ cần "nếu view không đủ" và cảnh báo NHÂN ĐÔI state với contract
(single source of truth); view đã đủ cho seniority/transfer đọc-được. Registry object = refinement
tùy chọn tương lai (nếu cần restructuring chuẩn hóa), KHÔNG phải gap. Ablation credit on/off = T10 PENDING.

### T07 — Tiền hàng hóa như một kết quả cạnh tranh, trước tiền pháp định

**Owner:** `monetary-fiscal-economist` + `research-planner`  
**Implementer:** `implementation-engineer`/`engine-surgeon`  
**Độc lập:** `test-engineer`, `sim-economist`, `reality-auditor`

- [ ] Tạo ADR về monetary instrument. Giai đoạn này chỉ có commodity money/claim receipt;
  không thêm central bank hay fiat money. Nêu rõ issuer/asset backing, supply flow,
  divisibility, durability, carrying cost, settlement and redemption.
- [ ] Cho phép barter, credit settlement và nhiều assets thanh toán cạnh tranh. Agent/policy
  chọn payment asset dựa trên feasible holdings, local accepted set, transaction cost and
  bounded information; engine không ép `xu` là money.
- [ ] Giữ `xu` legacy compatible, nhưng refactor từ “asset đúc được” thành candidate
  instrument có acceptance/adoption được đo theo chợ–thời gian–mạng, không chỉ theo một
  threshold observatory. Lý do issuer/flow of every new instrument phải audit được.
- [ ] Định nghĩa metrics trước run: monetary share by value/volume, acceptance breadth,
  payment concentration, velocity only when denominator/coverage meaningful, price
  dispersion, barter/credit shares, and failed settlement. Không diễn giải nominal GDP
  hoặc P×Q/M khi price coverage không đủ.
- [ ] Test absence case (no instrument), competition case (two instruments), supply shock,
  unaccepted asset and replay. Adoption can fail; no test may assert it always reaches a
  preset percentage.

→ **DESIGN+METRICS (T07)**: ADR `docs/adr/0004`; `xu` là commodity money, agent CHỌN
`Lenh.thanh_toan` (engine KHÔNG ép xu); metric read-only `monetary_share_by_value/by_stock`,
`acceptance_breadth`, `payment_concentration`, `barter_share`/`credit_share`, velocity+coverage-flag
(`metrics_research.py`, verified undefined→None). **`failed_settlement` ĐÃ CÀI**
(`w.settlement_fail_tick` đếm tại điểm nuốt `LoiSoKep` trong market.py, observation-state, reset mỗi
tick, không đổi hành vi khớp). **PENDING (còn)**: test
absence/competition/supply-shock/unaccepted-asset (không assert đạt % định trước).

**Gate:** monetary label/report is derived from transparent adoption evidence; changing
barter transaction cost or instrument properties has pre-registered, testable direction
without forcing a winner.

### T08 — Tài khóa và chính phủ: năng lực, chi phí, hàng hóa công, không “Gini trigger”

**Owner:** `monetary-fiscal-economist` + `spec-governor` + `model-architect`  
**Implementer:** `engine-surgeon`/`implementation-engineer`  
**Độc lập:** `test-engineer`, `qa-verifier`, `adversarial-reviewer`

- [ ] Audit `engine/politics.py` hiện hữu: government object tạo từ political intent, tax
  thu rồi rebate ngay, and riot redistribution gated by Gini. Giữ nó có thể replay cho
  legacy benchmark, nhưng không gọi nó là state formation/causal mechanism trong scenario
  mới.
- [ ] Thiết kế `public_sector`/fiscal module có treasury balance sheet, tax base,
  assessment/collection capacity, collection cost, compliance/evasion, public inventory,
  debt and declared spending rule. Công thức tài khóa mỗi tick phải đóng:
  `assets_end = assets_start + taxes + borrowing + issuance - spending - debt service -
  depreciation`, với counterpart cho mỗi flow.
- [ ] Thêm một tập public goods nhỏ, vật chất và có depreciation (ví dụ irrigation,
  market road hoặc dispute enforcement); mỗi good có input/cost/maintenance/benefit
  explicitly measured. Không thêm danh sách luật xã hội vô hạn.
- [ ] Tách governance procedure khỏi fiscal capacity: election, consensus, coercion and
  legitimacy are configurable institutional modes. Do not make a Gini threshold directly
  confiscate assets in `agrarian_transition_v1`; riot/redistribution phải là treatment
  có action, collective participation, cost and legal/accounting path rõ.
- [ ] Thử nghiệm tối thiểu gồm public-good available/unavailable, low/high enforcement
  capacity, voluntary contribution vs tax mode, and a placebo where benefit is removed.
  Report compliance, exit, public return, fiscal balance, distribution and failure modes.
- [ ] Test tax/issue/borrow/spend/default paths, no phantom public wealth, capacity limits,
  death/office vacancy, deterministic replay and no direct state mutation from policy.

**Gate:** chính phủ không phải object quyền lực miễn phí; treasury và public-good stock có
audit trail; report phân biệt “institutional treatment works” với “institution emerged”.
→ **DESIGN+GATE+METRICS (T08)**: ADR `docs/adr/0004`; **`chinh_tri.bat` gate** đã cài
(`engine/politics.py` + test `test_politics.py`; Gini-riot TẮT ở `agrarian_transition_v1`,
reality-auditor xác nhận PASS); tax/fiscal metric read-only `tax_revenue`, `fiscal_balance` (=0
TRUNG THỰC vì rebate — không phantom); governance tách khỏi capacity (đã audit legacy politics).
**treasury + public goods ĐÃ CÀI** (`engine/politics.py` `thi_hanh_chi_cong`/`_xay_mot_don_vi`/
`hao_mon_thuy_loi` + `production.py` benefit + `config fiscal.bat=false`): treasury = số dư
`CONG_QUY` (ledger, đã hash), public good `thuy_loi` = tài sản ledger, xây NGUYÊN TỬ (kiểm đủ TRƯỚC,
no phantom), depreciation qua FlowRegistry sink, benefit thời tiết đo được (placebo-able),
governance tách capacity, Gini KHÔNG tự chi. **Định danh tài khóa đóng** (gồm carrying-cost 3%
storage-loss của treasury) + **legacy hash bất biến** (fiscal off) — 13 test `test_fiscal.py`,
suite **239 passed**. Đề xuất: monetary-fiscal-economist review độc lập đầy đủ (đã self-review
no-phantom + gate). `chi_tiêu công vô hạn` KHÔNG thêm (chỉ 1 public good có chi phí).

### T09 — Hành vi baseline có thể thay thế, LLM chỉ là treatment sau cùng

**Owner:** `research-planner` + `model-architect`  
**Implementer:** `implementation-engineer`, `minds-engineer` khi cần  
**Độc lập:** `sim-economist`, `test-engineer`, `adversarial-reviewer`

- [x] Định nghĩa một `BehaviorPolicy` interface thuần, deterministic/replayable với state
  observation contract. Preserve `rulebot` as legacy baseline. → `minds/policies.py`
  (ADR 0002); `RulebotPolicy` bọc nguyên rulebot (named-strategy split = future work, ghi docstring).
- [x] Cài tối thiểu: feasible random policy (negative baseline), subsistence policy, and
  adaptive/expectations policy. → `feasible_random` + `subsistence` + **`adaptive` ĐÃ CÀI**
  (EWMA kỳ vọng giá `E_t=α·p_t+(1-α)·E_{t-1}` + tiết kiệm phòng ngừa theo volatility/thời tiết,
  state nội bộ policy; smoke+replay TRÙNG hash). Manifest ghi `reproducibility.policy`; không mutate world.
- [x] Tách behavioral policy khỏi physical/institution layers. Policy swap không đổi luật hạch
  toán. → policy chỉ trả intent; swap `--policy` cùng seed → audit xanh, hash khác (có tác động).
- [x] LLM/mock chỉ so sánh sau khi baseline không-mạng chạy được; không chạy real now.
  → baseline không-mạng chạy được; real KHÔNG chạy (yêu cầu cache/transcript/prompt-hash trước —
  ghi trong ADR 0002 §D, chưa có). Không đo "LLM intelligence".
- [x] Test feasible actions, policy swap, permutation/ordering invariance, distribution.
  → `tests/test_policies.py` (12 test): feasible (0/15,0/30 intent bị lọc), no-mutation, swap
  (3 hash khác + audit xanh), determinism, ordering-invariance, registry, adaptive PENDING.

**Gate:** kết luận mechanism chính không phụ thuộc PersonaBot/LLM; khác biệt policy báo như
treatment. → **ĐẠT (impl)** — **197 passed**, smoke `--policy feasible_random` replay TRÙNG hash.
Review độc lập T09 (test-fit check) gộp vào T12 adversarial-reviewer. Ghi chú: resume không chặn
đổi `--policy` (chỉ guard config-digest) — edge case ngoài phạm vi, siết sau nếu cần.

### T10 — Thí nghiệm, uncertainty, validation và phản chứng

**Owner:** `empirical-validation` + `research-planner`  
**Implementer:** `implementation-engineer`/`sim-economist`  
**Độc lập:** `reproducibility-steward`, `adversarial-reviewer`, `qa-verifier`

- [x] Tạo machine-readable pre-analysis protocol cho `agrarian_transition_v1`.
  → `scenarios/agrarian_transition_v1/preanalysis_protocol.yaml` (question/estimand/seed-list/
  horizon/policy-set/failed-run-handling/primary+secondary metrics/expected-sign+falsifier/
  no-claim-conditions/uncertainty).
- [x] Nâng runner ensemble/counterfactual: paired seeds, isolated run dirs, deterministic summary,
  n/failed count, median/quantiles, effect distribution. → `tools/counterfactual.py`: per-làng…
  isolated dir (refuse overwrite), `_summary` n/mean/median/p10/p90, `paired_delta_vs_baseline`
  align-theo-seed, **failed-count graceful** (`n_success`/`n_failed`/`failed_seeds`). Verified:
  `t12_cf_check` → n_success=2/n_failed=0/paired_delta_seeds=[41,42].
- [ ] **PARTIAL** — Suites: land_scarcity/weather_risk/transport_cost/placebo + policy_swap khả thi
  ngay (protocol có overlay + falsifier); credit/monetary/fiscal ablation **PENDING** (cần cơ chế
  T06/T07/T08 engine-mutation). Mỗi treatment đã ghi `what_would_falsify`.
- [x] Sensitivity runner rút từ priors/ranges + parameter importance. → `tools/sensitivity.py`
  (grid tất định trong `plausible_range`, tách param-variation khỏi seed-noise, `identifiable` flag,
  non-identified báo rõ); `tests/test_sensitivity.py` 9 pass; smoke `san_luong_goc_kg` chạy.
- [x] 3-seed short-horizon smoke validate orchestration. → `data/experiments/t10_agr_smoke_rulebot_60t`
  (baseline+4 treatment × 3 seed × 60 tick, paired delta + quantiles). **30 paired seed × 600 tick
  = `PENDING_COMPUTE`** (command trong protocol + methodology §7); KHÔNG bịa kết quả 30-seed.
- [x] Validation report refuses `validated` khi targets rỗng + data ingestion contract + split
  enforce. → `tools/validation.py` gate (T01/T03) + `scenarios/agrarian_transition_v1/data_contract.md`.

**Gate:** reviewer rerun được mọi row từ manifest/seed/overlay; mọi hình ghi n/horizon/policy/
scenario/uncertainty + mechanism-vs-empirical. → **PARTIAL** — orchestration + protocol + smoke +
validation-gate ĐẠT; suites đầy đủ + sensitivity + 30-seed ensemble = PENDING/PENDING_COMPUTE.

### T11 — Báo cáo, documentation và publication-readiness thật thà

**Owner:** `integration-manager`  
**Độc lập:** `sim-economist`, `empirical-validation`, `reproducibility-steward`,
`adversarial-reviewer`

- [x] Create `reports/agrarian_transition_v1_methodology.md` + generated experiment report.
  → methodology (scope/5-lớp/accounting-identities/baselines/protocol/runs/uncertainty/failures/
  limitations); generated report = `data/experiments/t10_agr_smoke_rulebot_60t/summary.{md,json}`
  (isolated dir). Bảng §7 có n/horizon/policy + [p10,p90] + nhãn mechanism_result.
- [~] Generate figures/tables from reproducible raw metrics/events. → bảng smoke sinh từ
  `summary.json` (raw), không hand-edit, có failure/no-effect (c1/c3 = baseline báo trung thực).
  **PENDING**: figure PNG tự sinh cho ensemble đầy đủ (chờ 30-seed PENDING_COMPUTE).
- [x] Update README (workflow không-mạng, scenario distinction, lệnh literal; legacy real = opt-in).
  → `README.md` §"Quy trình nghiên cứu KHÔNG-MẠNG" + banner legacy opt-in.
- [x] Write `reports/world_class_readiness.md` (pass/partial/fail cho question/novelty/data/
  calibration/holdout/robustness/LLM-repro/artifact). → nêu rõ world-class empirical BỊ CHẶN tới
  khi có data + independent validation.
- [x] Draft paper outline (không bịa finding) cho (a) kinh tế sử + (b) LLM-ABM methodology.
  → `reports/paper_outline.md` (mỗi hướng ghi evidence CÒN THIẾU).

**Gate:** docs make no overclaim; newcomer reproduce được benchmark + hiểu vì sao chưa phải empirical
reconstruction. → **ĐẠT** (adversarial-reviewer T12 xác nhận không overclaim; figure PNG ensemble =
PENDING_COMPUTE).

### T12 — Final independent gates and handoff

**Owner:** `integration-manager`  
**Independent sign-off:** `qa-verifier`, `reproducibility-steward`,
`adversarial-reviewer`, `reality-auditor`

- [x] Run and record final collection, full pytest, ruff, scenario validation, rulebot smoke
  audit, replay verification, output-isolation. → **205 passed, 0 failed**
  (`.tmp/logs/T12_final_suite.log`); ruff **All checks passed**; validation 2 scenario
  mechanism_benchmark exit 0; `verify_research_run`/`replay --verify` (rulebot/scenario/permute/
  **policy**) TRÙNG hash; isolation OK. Không gọi provider thật.
- [x] `reality-auditor` scan code mới. → **PASS 0 BLOCKING/MAJOR** (`docs/reviews/T12-gates.md`):
  hard-code/magic-fallback/metric-điều-khiển-engine/định-chế-ẩn/determinism/PENDING đều PASS; phân
  biệt định chế scenario minh bạch vs setup ẩn. MINOR (survival-floor scope note) đã xử lý.
- [x] `adversarial-reviewer` review diff + report (referee thù địch). → **minor-revision, 0 BLOCKING**;
  mọi finding actionable ĐÃ SỬA: M1 (verify tool đọc policy) + regression scope.yaml `on`-key +
  m1/m2/q1 (test count/literal seeds/GDP brackets). `docs/reviews/T12-gates.md`.
- [x] Update checkbox theo evidence; external-data/compute để unchecked có lý do; viết
  `reports/final_handoff.md`. → done; external-data/30-seed = PENDING_COMPUTE ghi rõ.
- [x] KHÔNG commit trừ khi người dùng yêu cầu sau khi đọc handoff. → **KHÔNG commit** (working tree
  giữ nguyên; không stage/reset).

**Gate:** final handoff differentiates `technical-ready`, `research-ready` and
`empirically-validated`; no category is inflated.

## 5. Prohibited shortcuts checklist

- [ ] No fixed year, Gini threshold, label or milestone directly causes money, government,
  industrialization, redistribution or a named social class in the new scenario.
- [ ] No observed output is reused as a calibration target without a source/holdout split.
- [ ] No `or <magic price>` fallback remains in an economic decision without an explicitly
  declared information/anchor assumption and test.
- [ ] No event path creates money, public wealth, debt claim, land title or goods without a
  registered source and an identifiable counterpart.
- [ ] No report calls a mock/one-seed/legacy result empirical, causal, predictive or
  world-class evidence.
- [ ] No test, scenario, report or source data is silently deleted to make gates green.

## 6. Completion message format

At the end, return a compact factual table:

| Task | Status | Evidence/artifact | Remaining blocker |
|---|---|---|---|

Then list: test/lint commands and exact results; all runs made (mode, seeds, horizon);
files changed; claim tier reached; and the next command the user may run. Do not claim
success for unchecked tasks or any external-data validation that did not occur.

---

## 7. Backlog mở rộng sau handoff

### T13 — Không gian kinh tế, sinh kế đa dạng và tài nguyên tái tạo

**Mục đích:** biến `agrarian_transition_v1` thành một xã hội có lựa chọn sinh kế thật,
không phải một làng nơi tất cả người dân mặc định cày ruộng mỗi tick. Thiết kế vẫn phải gọn:
mô phỏng động cơ, thời gian, chi phí, khả năng tiếp cận và tài nguyên hữu hạn; không biến dự
án thành mô hình nông học chi tiết.

**Owner:** `research-planner` + `agrarian-economist` + `model-architect`  
**Implementer:** `implementation-engineer`/`engine-surgeon`/`graph-architect`  
**Độc lập:** `test-engineer`, `qa-verifier`, `sim-economist`,
`reproducibility-steward`, `adversarial-reviewer`

- [ ] Viết ADR trước code cho “spatial livelihood economy”: ownership/state của thửa đất,
  quyền sử dụng/thuê, work order, thời gian lao động theo mùa, crossing/route, tài nguyên
  tự nhiên, event/ledger schema, migration/replay và acceptance tests. Cơ chế mới phải là
  optional overlay của `agrarian_transition_v1`; không làm hỏng replay legacy scenario.

- [ ] Đặt endowment khởi đầu theo **một năm food-equivalent mỗi thành viên/hộ** thay vì
  một con số kg ngầm. Scenario quy đổi theo calendar/độ tuổi hiện hành, ghi rõ đây là
  `design_assumption`. Tài sản đó là tồn kho thật: hộ có thể giữ dự trữ, tiêu dùng, bán,
  cho vay, mua công cụ, thuê người hoặc đầu tư và vẫn chịu rủi ro cạn lương thực. Không
  có khoản trợ cấp/food mint bí mật sau tick 0.

- [ ] Thiết kế calendar tối giản cho hai vụ lúa và một vụ đông (ngô **hoặc** khoai). Với
  scenario mới, nếu cần chuyển từ hai tick/năm sang ba mùa/tick, phải chuyển đổi có chủ ý
  toàn bộ age, consumption, contract duration, annual hazard, weather and reporting;
  không đổi đơn vị thời gian bằng cách nhân/chia ngầm tham số. Mỗi cây chỉ cần season,
  công lao động, output/risk/storage-value và tác động đất ở mức tối giản; một thửa không
  được gieo hai cây trong cùng mùa. Không thêm mô phỏng hạt giống/nước/dinh dưỡng chi tiết
  nếu chưa có câu hỏi nghiên cứu cần chúng.

- [ ] Hoàn thiện **thuê đất** bằng quyền sử dụng/hợp đồng đã có: chủ đất không muốn canh
  có thể rao cho thuê theo tô cố định, chia sản hoặc đổi công; người thuê nhận quyền canh
  trong thời hạn rõ; chủ không thu sản lượng nếu không có contract hợp lệ. Rulebot/adaptive
  policy phải biết phát hiện cơ hội này, nhưng engine không ép chủ nhiều đất phải cho thuê.
  Báo land-use rate, rent/share terms, vacancy, landlord/tenant income và contract default.

- [ ] Xây một primitive `work order`/dịch vụ tổng quát thay vì hard-code danh sách nghề.
  Work order phải xuất phát từ nhu cầu/vật lý thật (ruộng vượt năng lực lao động mùa vụ,
  khai hoang, dựng/sửa nhà, vận chuyển, chăm trẻ), nêu rõ người thuê, người làm, công,
  duration, địa điểm, payment asset và output. Người nhận việc mất thời gian cho việc khác;
  payment qua ledger/hợp đồng. Không gán nghề vĩnh viễn cho agent.

- [ ] Mô hình hóa các sinh kế đầu tiên bằng primitive đó:
  1. khai hoang đất chưa sử dụng ở bờ bên kia;
  2. xây/sửa nhà và thuê thợ khi hộ thiếu năng lực;
  3. chăm trẻ có trả công hoặc nhờ mạng thân tộc, với time trade-off thật cho cha mẹ/người
     chăm;
  4. chở người/hàng qua sông bằng đò.
  Người có thể kết hợp nhiều sinh kế trong một năm/mùa; không có “nông dân”, “lái đò” hay
  “thợ xây” là class cố định.

- [ ] Bổ sung geography cho scenario: sông tạo hai bờ có access khác nhau; phía dân cư có
  nơi ở/chợ ban đầu, phía kia có đất chưa khai hoang và tài nguyên tự nhiên. Không hard-code
  vị trí/ID người hưởng lợi; map seed tạo topology và route/ferry capacity. Đò là dịch vụ:
  người vận hành phải có/duy trì phương tiện hoặc quyền vận hành, chuyến đi có capacity và
  chi phí; khách trả thóc trước khi có phương tiện tiền tệ được chấp nhận, rồi có thể trả
  bằng settlement asset hợp lệ sau đó. Không teleport người/hàng hoặc tự tạo tiền công.

- [ ] Chuẩn hóa tài nguyên tái tạo, có giới hạn theo không gian: cá và quần thể gà rừng có
  stock, carrying capacity, extraction/hunting, regeneration và event/audit trail. Bắt gà
  rừng có thể cho thịt hoặc chuyển thành đàn nuôi; khai thác quá mức làm sản lượng tương lai
  giảm. Không để cá/gà sinh vô hạn, nhưng cũng không bảo đảm cạn vĩnh viễn nếu áp lực khai
  thác giảm.

- [ ] Mở rộng behavior/survival policy theo thứ tự ưu tiên có thể giải thích: dự trữ hộ →
  canh tác/thuê đất → nhận/rao work order → chợ/đò/vận chuyển → A2A xin hỗ trợ/thương lượng
  → tín dụng hợp lệ → khai thác trong giới hạn → di cư. MCP/world tools chỉ trả thông tin
  cục bộ, read-only và có giới hạn lượt; A2A có độ trễ, phạm vi, uy tín và không sửa state.
  Không bắt một agent dùng mọi tool; policy chọn phương án feasible có lợi ích kỳ vọng cao.

- [ ] Thêm metrics và reports: seasonal time-use, diversity of income sources/occupation
  entropy, work-order vacancy/fill/wage, childcare burden, crop mix, land-use/clearance,
  river-crossing volume/fare/payment asset, resource stock/extraction/regeneration,
  price/wage dispersion hai bờ và mobility. Tất cả là observation, không quay lại điều
  khiển engine.

- [ ] Viết test độc lập cho: chủ đất không canh có thể cho thuê nhưng không tự thu tô; hộ
  không đủ công có thể thuê người; childcare đổi time/income mà không tạo lao động; người/
  hàng không qua sông khi không có route/đò/fee; fare bằng thóc trước tiền tệ; khai hoang
  cần công và tạo quyền đất hợp lệ; khai thác cá/gà không vượt stock; quần thể phục hồi;
  cùng seed/config replay cùng hash; agent vẫn có thể thất bại/suy kiệt khi toàn bộ lựa
  chọn không feasible.

- [ ] Chạy smoke paired-seed không mạng và các counterfactual: có/không có đò, phí đò cao/
  thấp, thuê đất bật/tắt, khai hoang xa/gần, resource capacity cao/thấp. Report cả trường
  hợp không phát sinh dịch vụ hoặc tài nguyên cạn; không ép xã hội phải có lái đò, thuê đất
  hoặc phát minh trong mọi seed.

**Gate:** một xã hội có thể tự tạo các sinh kế khác nhau từ land/time/location/scarcity,
nhưng mọi nghề, khoản trả công, quyền đất, chuyến đò và tài nguyên vẫn truy ngược được về
nhu cầu vật lý, hợp đồng, ledger, map và seed. Kết quả chỉ được gọi là mechanism result;
không suy rộng sang lịch sử thật khi chưa có dữ liệu/validation.
→ **PHẦN LỚN ĐẠT (core coded, scenario-gated OFF, legacy hash bất biến)**: ADR `docs/adr/0005`;
Phase A (spatial.py + Parcel.bo + two-bank + overlay `spatial_v1.yaml`); ferry-dịch-vụ (thuyền
asset + qua_song + fare-thóc-trước-tiền + capacity + hao mòn, sông chặn liên bờ); khai hoang bờ kia
(qua homestead, cross-required); endowment food-equiv; spatial-aware rulebot/policy; spatial metrics
(river-crossing/ben_kia/land-use-by-bank/occupation-entropy/resource-stock). **283 test xanh**, ruff
sạch, OFF=legacy hash chứng minh trực tiếp. Thuê đất/work-order/cá/nhà-thuê-thợ = tái dùng cơ chế
sẵn có (audit xác nhận). Trial `spatial50` + ensemble 3-seed on/off: cơ chế exercise thật (đò/chuyến)
nhưng far-bank clearing KHÔNG hình thành + tác động vĩ mô trong nhiễu seed (mechanism_result trung
thực). **HOÃN có chủ đích (ADR spec, không bịa)**: vụ đông (E), gà rừng commons (F), chăm trẻ (G).
Đánh giá + lộ trình xuất bản: `reports/design_reevaluation.md`. Review độc lập: reality-auditor
(`docs/reviews/T13-*`) + `docs/reviews/T13-plan.md`.
