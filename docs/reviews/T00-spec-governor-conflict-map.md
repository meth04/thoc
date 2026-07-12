# T00 — Conflict Map (spec-governor)

Ngày: 2026-07-12
Vai trò: spec-governor độc lập (chỉ đọc + viết file review này).
Phạm vi so sánh: `CLAUDE.md`, `SPEC.md`, `PHASES.md`, `REPORTS.md`, `REVIEW.md`,
`TASKS.md`, `scenarios/preindustrial_closed_v1/`, và code (`engine/politics.py`,
`engine/economy.py`, `engine/market.py`, `engine/world.py`, `observatory/observer.py`,
`engine/production.py`, `engine/tick.py`, `minds/safety.py`, `config/world.yaml`).

Ràng buộc đã tuân thủ: không chạy real/API/mạng; không đọc `.env`; không sửa file nào
ngoài file này; không dùng git reset/checkout/clean.

## Quy ước phân loại

- `INVARIANT` — bất biến phải giữ (bảo toàn, sổ kép, seed/replay, policy isolation,
  anti-teleology). Nếu code/doc vi phạm thì invariant thắng, code/doc phải sửa.
- `ASPIRATION_OUTDATED` — khát vọng cũ đã lỗi thời; cần đánh dấu superseded, giữ như
  nhãn lịch sử, không xóa.
- `IMPLEMENTATION_EXISTS` — code đã làm khác spec; cần ADR hợp thức hóa (như một
  institution scenario minh bạch) hoặc refactor.
- `OPEN_DECISION` — còn mở, phải quyết trong T01+.

Lưu ý quan trọng: cả `ledger`/`FlowRegistry`, `policy isolation` (LLM/policy không chạm
state), `mock mặc định` hiện đang được TÔN TRỌNG trong code chính trị/kinh tế được soi
(mọi chuyển dịch đi qua `w.ledger.chuyen`/`Transaction` với chủ thể `CONG_QUY`; survival
floor chỉ sửa `ke_hoach` rồi engine thực thi). Các invariant đó KHÔNG được suy yếu khi
giải quyết các mâu thuẫn dưới đây.

---

## C1 — `ChinhQuyen`: định chế "nhà nước" có tên được mã hóa trong engine

- **Cấm (spec):** `CLAUDE.md:45-47` (điều luật 7: "trong `engine/` không được tồn tại
  khái niệm bank/loan/company/insurance/wage như code riêng ... tên định chế chỉ được
  xuất hiện trong `observatory/`"); `SPEC.md:10` (Quyết định #1 "Không nhà nước, không
  ngân hàng trung ương."); `SPEC.md:18` (Quyết định #9 "Engine không được chứa định chế
  có tên.").
- **Vi phạm (code):** `engine/world.py:25-39` (`class ChinhQuyen` với `truong_lang`,
  `thue_suat`, `luong_toi_thieu`, `nghiep_doan`); `engine/world.py:88`
  (`chinh_quyen: ChinhQuyen | None` là field của `World`); toàn bộ `engine/politics.py`
  (bầu cử `:62-93`, lập pháp `:96-121`, hối lộ `:124-141`, nghiệp đoàn/đình công
  `:144-156`); nối vào pipeline VÔ ĐIỀU KIỆN tại `engine/tick.py:114`.
- **Ghi nhận từ tài liệu mới:** `TASKS.md:56-58` đã nêu đây là "mâu thuẫn đặc tả phải
  giải quyết có chủ ý"; `REVIEW.md:703` (chính quyền phải là tổ chức có ngân sách/quyền
  cưỡng chế hữu hạn, không phải object có sẵn).
- **Phân loại:** `IMPLEMENTATION_EXISTS`.
- **Hành động T01:** ADR `0001-scope-and-institutional-layers` phải: (a) tách "engine
  mechanism" khỏi "scenario institution"; (b) cho phép một module `public_sector`/chính
  quyền MINH BẠCH chỉ khi có accounting identity, chi phí, alternative và scenario flag
  (đúng ràng buộc `TASKS.md:116-118`); (c) giữ `preindustrial_closed_v1` replay được
  như legacy, nhưng không gọi `ChinhQuyen` là "state formation nội sinh". Chi tiết fiscal
  đẩy sang ADR của T08 (`TASKS.md:287-315`).

## C2 — Thuế và lương tối thiểu là cơ chế engine (điều luật 7 cấm "wage")

- **Cấm (spec):** `CLAUDE.md:45-47` (cấm `wage` là code riêng trong engine);
  `SPEC.md:18` (#9).
- **Vi phạm (code):** `engine/politics.py:96-121` (`_lap_phap` đặt `thue`/
  `luong_toi_thieu`); `engine/politics.py:170-198` (`thu_thue_va_chia` thu theo suất
  trên sản lượng gặt → `CONG_QUY` → chia đều đầu người); `engine/world.py:35-36`
  (`thue_suat`, `luong_toi_thieu`); `config/world.yaml:216` (`thue_suat_toi_da: 0.5`);
  nối pipeline `engine/tick.py:125`.
- **Điểm tích cực cần bảo toàn:** thu/chia là `w.ledger.chuyen` CÂN (`politics.py:187,209`)
  nên bảo toàn tự xanh — invariant sổ kép KHÔNG bị suy yếu.
- **Phân loại:** `IMPLEMENTATION_EXISTS`.
- **Hành động T01/T08:** ADR fiscal phải đóng identity
  `assets_end = assets_start + taxes + borrowing − spending − debt service − depreciation`
  (`REVIEW.md:756-764`, `TASKS.md:298-301`), có treasury balance sheet + chi phí thu +
  compliance; đưa tax vào scenario overlay, không mặc định bật ở scenario mới.

## C3 — Bạo động sung công theo ngưỡng Gini (teleology / "Gini trigger")

- **Cấm (invariant anti-teleology):** `REVIEW.md:104-106` (2.2.G: "Không nên để một
  ngưỡng Gini duy nhất xác định bạo động mặc định ... luật này phải được tách thành
  scenario hoặc ước lượng từ dữ liệu"); `REVIEW.md:710` (D.2 #4 "Không teleology ...
  'Gini cao sinh chính phủ'"); `TASKS.md:418-419` (prohibited shortcut: "No fixed year,
  Gini threshold, label or milestone directly causes ... redistribution ... in the new
  scenario"); `TASKS.md:306-310` (T08: không để ngưỡng Gini trực tiếp sung công ở
  `agrarian_transition_v1`).
- **Vi phạm (code):** `engine/politics.py:215-256` (`buoc_bao_dong`: nếu
  `gini(thoc) > nguong` VÀ đủ số đông → sung công `ty_le_sung_cong` của top-decile chia
  đều bottom-decile); `config/world.yaml:217` (`gini_nguong_bao_dong: 0.85`),
  `:219-220` (`ty_le_sung_cong_bao_dong`, `phan_vi_giau_ngheo`); nối pipeline VÔ ĐIỀU
  KIỆN `engine/tick.py:226`; `parameters.yaml:4` scenario overlay rỗng `{}` nên KHÔNG
  có gì tắt nó.
- **Nguồn khát vọng cũ:** `REPORTS.md:47` ("Khi Gini > 0.85 ... Engine sẽ tước đoạt tài
  sản ... Đây là cơ chế *Reset Hệ thống*").
- **Phân loại:** `INVARIANT` (anti-teleology). Không thể "hợp thức hóa như hiện trạng":
  ngưỡng Gini trực tiếp gây tái phân phối là teleology bị cấm. Cần scenario-gate/loại bỏ
  khỏi default; nếu giữ, phải chuyển thành treatment có action tập thể, chi phí, đường
  pháp lý/kế toán (đúng `TASKS.md:306-310`, `REVIEW.md:264-272`).
- **Hành động T01→T08:** ADR 0001 ghi rõ anti-teleology rule; ADR T08 chuyển riot thành
  collective-action treatment có placebo; `preindustrial_closed_v1` được giữ replay
  nhưng nhãn là `historical_rule`/`experimental_treatment` (`REVIEW.md:272`), mặc định
  TẮT ở scenario mới.

## C4 — `xu` (coin): tài sản đúc được vs "phương tiện trao đổi cạnh tranh"

- **Spec hiện tại (KHÔNG mâu thuẫn với `xu` đúc):** `SPEC.md:11` (#2 "Tiền kim loại
  KHÔNG được cài sẵn: ... 'xu' là hàng chế tác; việc xã hội có dùng xu làm tiền hay
  không là kết quả tự phát"). Code hiện phù hợp: `engine/production.py:298-308`
  (đúc xu từ recipe vật lý), `engine/world.py:420` (FlowRegistry đăng ký `xu`),
  `engine/market.py:1-6,100-132` (chợ cho thanh toán bằng xu), nhãn `tien_te_hoa` chỉ ở
  observatory (`observatory/observer.py:150-160`). Đây là điểm code TUÂN THỦ.
- **Hướng mới (đề xuất refactor):** `REVIEW.md:746-750` (D.4 #4: "Không tạo `coin` rồi
  bắt mọi giao dịch dùng nó" — cho nhiều tài sản cạnh tranh, đo adoption);
  `REVIEW.md:719` (D.3 lớp 3 metrics); `TASKS.md:259-284` (T07: refactor `xu` từ "asset
  đúc được" thành candidate instrument đo theo chợ–thời gian–mạng, không chỉ theo một
  threshold observatory).
- **Phân loại:** `OPEN_DECISION` (không phải vi phạm spec; là chọn hướng nâng cấp T07).
- **Hành động T07:** ADR monetary instrument (barter/credit/nhiều asset cạnh tranh,
  metrics adoption trước run, absence/competition/supply-shock tests). Giữ `xu` legacy
  compatible.

## C5 — Nhãn định chế trong observatory (bank/insurance/industrialization)

- **Trạng thái:** TUÂN THỦ điều luật 7 — nhãn `ngan_hang`, `bao_hiem`, `xuong`,
  `tien_te_hoa`, `cong_nghiep_hoa` sống ở `observatory/observer.py:102-190`, CHỈ ĐỌC
  state/log, không rẽ nhánh engine. `SPEC.md:348-354` cho phép đúng như vậy.
- **Rủi ro cần canh:** `REVIEW.md:426,542` (nhãn không được "quay lại điều khiển engine",
  không được "đặt tên rồi coi là giải thích"). Đã kiểm: classifier không feedback vào
  engine. Không phải conflict.
- **Phân loại:** (không tính vào 4 nhóm) — COMPLIANT, ghi để tránh nhầm với C1–C3.
- **Hành động T01:** charter khẳng định observatory là "empirical claim tier" tách khỏi
  "engine mechanism"; thêm gate cấm export nhãn với chữ `empirically_validated` khi
  targets/provenance rỗng (`TASKS.md:128-130`).

## C6 — Tiêu chí "median industrialization year 160–280" + định nghĩa hoàn thành theo mock/LLM

- **Khát vọng cũ:** `CLAUDE.md:121-129` (mục 8 định nghĩa hoàn thành: "Run mock 300 năm
  end-to-end ... hiệu chỉnh đạt: seed trung vị chạm nhãn công-nghiệp-hóa trong năm
  160–280"); `SPEC.md:19` (#10 "hiệu chỉnh `research.yaml` bằng mock ... để seed trung vị
  đạt nhãn trong khoảng năm 160–280"); `PHASES.md:77-80` (Phase 4 calibration).
- **Bác bỏ (khoa học mới):** `REVIEW.md:84-88` (2.2.C: "Một mốc được chọn trước rồi điều
  chỉnh tham số để đạt mốc đó không thể được dùng tiếp như bằng chứng"); `REVIEW.md:386`
  (báo xác suất/khoảng, không phải "năm 171"); `REVIEW.md:710` (anti-teleology);
  `TASKS.md:9-11` (T00 mục tiêu: "không phải ép một run đi đến công nghiệp hóa");
  `TASKS.md:126-127` (T01: "Bỏ acceptance criterion 'tune median industrialization
  year' khỏi định nghĩa khoa học; có thể giữ nó như legacy regression label riêng").
- **Phân loại:** `ASPIRATION_OUTDATED`.
- **Hành động T01:** đánh dấu superseded trong `CLAUDE.md` §8, `SPEC.md` #10,
  `PHASES.md` Phase 4 bằng link tới charter; giữ như "legacy regression label" cho
  `preindustrial_closed_v1`; KHÔNG xóa lịch sử benchmark, KHÔNG đổi nhãn báo cáo cũ.

## C7 — "LLM quyết định tất cả" vs behavior policy tách khỏi LLM

- **Hiện trạng/khát vọng cũ:** `CLAUDE.md:3-5` (50 agent LLM là chủ thể quyết định);
  `SPEC.md:99` (sinh con `× ý_định(0/.5/1, LLM)`); `CLAUDE.md:121-129` (định nghĩa hoàn
  thành xoay quanh run mock/LLM). Đã có sẵn `rulebot` (no-LLM baseline) — một phần hướng
  mới đã tồn tại.
- **Hướng mới:** `REVIEW.md:100-102` (2.2.F: LLM chưa là mô hình hành vi được nhận
  diện; quyết định cuối nên qua hàm lựa chọn đo được); `REVIEW.md:189-205` (4.3 hàm hành
  vi lai); `REVIEW.md:444-450` (7.2: calibration/validation phải chạy policy không gọi
  mạng); `REVIEW.md:528-537` (Giai đoạn 5: LLM là treatment, không là lõi);
  `TASKS.md:317-338` (T09: `BehaviorPolicy` interface, tách named strategies, LLM chỉ là
  treatment sau cùng).
- **Invariant được bảo toàn:** điều luật 3 (`CLAUDE.md:34-35`) "LLM/policy không chạm
  state" ĐÚNG cho cả hai hướng — không suy yếu.
- **Phân loại:** `OPEN_DECISION` (kiến trúc T09; phần "định nghĩa hoàn thành = LLM run"
  thuộc C6 ASPIRATION_OUTDATED).
- **Hành động T09:** ADR `BehaviorPolicy` deterministic/replayable với state-observation
  contract; kết luận mechanism chính không phụ thuộc PersonaBot/LLM.

## C8 — Đơn vị quyết định: cá nhân (code) vs hộ gia đình (REVIEW/TASKS)

- **Hiện trạng (cá nhân):** `SPEC.md:97` (t0 "50 người lớn độc thân"); agent là cá nhân,
  quyết định theo từng agent. Hộ hiện chỉ là VIEW chỉ-đọc để đo metric:
  `engine/economy.py:15-57` (`households()`, `household_snapshot()` — không chuyển tài
  sản); `minds/safety.py:31-63` (survival floor duyệt theo hộ nhưng người canh phải tự
  có giống/công, không "rút kho chung").
- **Hướng mới:** `REVIEW.md:118` và `REVIEW.md:173-187` (4.2: hộ là chủ thể tối ưu hóa;
  cá nhân giữ vai trò nhân khẩu/lao động/hôn nhân/thừa kế); `REVIEW.md:703` (D.2);
  `TASKS.md:181-208` (T04: household model + membership + budget; nếu thêm pantry chung
  phải là chủ thể ledger, không âm thầm gom tài sản; nếu không, budget chỉ là derived
  read-only).
- **Phân loại:** `OPEN_DECISION` (T04). Hiện `economy.py` đã đúng dạng "derived read-only
  view" mà T04 yêu cầu như phương án tối thiểu.
- **Hành động T04:** ADR household (membership ổn định, ownership cá nhân vs pantry
  chung, serialization/migration, income/consumption/assets/liquidity không lẫn).

## C9 — REPORTS.md manifesto (Science/Nature/NeurIPS, GDP/velocity) vs claim-tier trung thực

- **Overclaim cũ:** `REPORTS.md:3` (đích "Science, Nature Human Behaviour hoặc NeurIPS");
  `REPORTS.md:24-32` (GDP thực/velocity `V = P×Q/M`, "Chứng minh được tiền quay vòng
  nhanh hơn khi ... ngân hàng ... xuất hiện"); `REPORTS.md:40-47` (state formation +
  riot-as-reset).
- **Hiệu chỉnh (khoa học mới):** `REVIEW.md:577-609` (Phụ lục A: "Chưa đủ điều kiện cho
  bài tầm cỡ thế giới"; `:591-593` targets/provenance rỗng nên chưa có calibration);
  `REVIEW.md:390-402` (6.1: GDP nội bộ không nên gọi là GDP thực chứng khi thiếu độ phủ
  giá); `TASKS.md:54-55` ("`REPORTS.md` là manifesto/đề xuất, không phải bằng chứng thực
  chứng"). Bằng chứng scenario trung thực: `scope.yaml:16` (`validation_tier:
  mechanism_benchmark`), `targets_in_sample.yaml:3` (`targets: []`), `provenance.csv`
  (3 dòng đều `design_assumption`).
- **Phân loại:** `ASPIRATION_OUTDATED`.
- **Hành động T01/T11:** đánh dấu `REPORTS.md` là manifesto/aspirational bằng link tới
  charter; `world_class_readiness.md` (T11) dùng bảng pass/partial/fail và nêu rõ bài
  thực chứng còn bị chặn tới khi có dữ liệu thật.

## C10 — Cú sốc dịch bệnh: sự kiện kịch bản hóa thứ hai ngoài thời tiết

- **Cấm (spec cũ):** `CLAUDE.md:53` (điều luật 7: "sự kiện kịch bản hóa (ngoại lệ duy
  nhất: thời tiết rút từ phân phối có seed)"); `SPEC.md:62` (thời tiết là "ngẫu nhiên
  ngoại sinh DUY NHẤT").
- **Code:** `config/world.yaml:104-107` (`cu_soc.dich_benh {bat: false, ...}` — TẮT mặc
  định, có ghi chú "Scenario thực chứng có thể bật với chuỗi/xác suất và hiệu ứng có
  provenance riêng"); nối pipeline `engine/tick.py:207` (`consumption.dich_benh(w)`).
- **Hướng mới cho phép:** `REVIEW.md:96-98` (2.2.E: nên bổ sung dịch bệnh như một lớp
  cú sốc scenario CÓ dữ liệu và kiểm định).
- **Phân loại:** `OPEN_DECISION` (mặc định tắt + scenario-gated đã đúng tinh thần mới;
  cần ADR chính thức nới điều luật 7 cho scenario shocks có provenance).
- **Hành động T03/T08:** ADR "scenario shock layer" (magnitude có seed/version,
  provenance), giữ mặc định tắt ở benchmark khép kín.

## C11 — Survival floor (`minds/safety.py`) là treatment hành vi cần khai báo ablation

- **Code:** `minds/safety.py:17-64` (bổ sung 1 thửa canh khả thi khi hộ dưới dự trữ tối
  thiểu và chưa ai dự định canh); `config/world.yaml:245-249` (`minds.san_an_toi_thieu`,
  có `bat`/ngưỡng); ghi event mỗi lần áp dụng (`safety.py:61-63`).
- **Tuân thủ:** nằm ở `minds/` (tầng hành vi), chỉ sửa `ke_hoach`/`da_nham`, KHÔNG chạm
  ledger → điều luật 3 giữ nguyên.
- **Yêu cầu mới:** `REVIEW.md:641` (liệt kê "bỏ survival floor" là một ablation đăng ký
  trước); `TASKS.md:145-147` (T02: state ảnh hưởng hành vi phải vào hash/replay);
  `TASKS.md:334-335` (policy là treatment paired-seed, không âm thầm gộp vào kinh tế).
- **Phân loại:** `OPEN_DECISION` (mostly compliant; cần khai báo là treatment ablatable
  và đảm bảo determinism/replay).
- **Hành động T09/T10:** đăng ký survival floor như một behavior treatment có ablation
  và expected direction.

## C12 — Deterministic replay phải bao trùm state mới (ChinhQuyen, nghiệp đoàn, disease, floor, payment stats)

- **Invariant:** `CLAUDE.md:36-37` (điều luật 4 "Cùng seed + cùng transcript → cùng
  world-hash. Có test chứng minh"); `SPEC.md:325-333` (checkpoint mỗi 10 tick;
  `replay --verify` so world-hash).
- **State mới cần kiểm:** `engine/world.py:88` (`chinh_quyen`), `:89`
  (`so_bao_dong_tick`), `ChinhQuyen.phieu/nghiep_doan/dinh_cong_tick`
  (`world.py:37-39`), disease-year map, `giao_dich_dat` (`world.py:82`), payment
  statistics; `TASKS.md:145-147` (T02: "Audit migration/checkpoint/world hash cho mọi
  state hiện có ... trạng thái ảnh hưởng hành vi phải vào hash/replay").
- **Phân loại:** `INVARIANT` (phải giữ; xác minh serialization đầy đủ, không suy yếu).
- **Hành động T02:** audit checkpoint/world-hash cho toàn bộ state mới + test hồi quy
  replay; nếu thiếu thì đây là regression phải sửa trong T02, không phải nới test.

---

## Bảng tóm tắt

| # | Mâu thuẫn | Spec/doc (file:line) | Code/impl (file:line) | Nhóm | ADR/Task |
|---|---|---|---|---|---|
| C1 | `ChinhQuyen` nhà nước có tên trong engine | CLAUDE.md:45-47; SPEC.md:10,18 | world.py:25-39,88; politics.py:62-156; tick.py:114 | IMPLEMENTATION_EXISTS | ADR 0001 (T01) + T08 |
| C2 | Thuế / lương tối thiểu là cơ chế engine | CLAUDE.md:45-47; SPEC.md:18 | politics.py:96-121,170-198; world.yaml:216; tick.py:125 | IMPLEMENTATION_EXISTS | ADR 0001 (T01) + T08 |
| C3 | Bạo động sung công theo ngưỡng Gini (teleology) | REVIEW.md:104-106,710; TASKS.md:306-310,418-419 | politics.py:215-256; world.yaml:217-220; tick.py:226 | INVARIANT | ADR 0001 anti-teleology + T08 |
| C4 | `xu` đúc-được vs phương tiện trao đổi cạnh tranh | SPEC.md:11; REVIEW.md:746-750; TASKS.md:259-284 | production.py:298-308; market.py:100-132; observer.py:150-160 | OPEN_DECISION | ADR tiền tệ (T07) |
| C5 | Nhãn định chế observatory (COMPLIANT) | CLAUDE.md:45-47; SPEC.md:348-354 | observer.py:102-190 | (compliant) | charter gate (T01) |
| C6 | Tiêu chí "median industrialization 160–280" + done=mock run | CLAUDE.md:121-129; SPEC.md:19; PHASES.md:77-80 | (calibration harness / research.yaml) | ASPIRATION_OUTDATED | mark superseded (T01) |
| C7 | "LLM quyết định tất cả" vs behavior policy | SPEC.md:99; CLAUDE.md:3-5; REVIEW.md:189-205,444-450 | rulebot/orchestrator (đã có no-LLM baseline) | OPEN_DECISION | ADR BehaviorPolicy (T09) |
| C8 | Đơn vị quyết định cá nhân vs hộ | SPEC.md:97; REVIEW.md:173-187; TASKS.md:181-208 | economy.py:15-57 (derived); safety.py:31-63 | OPEN_DECISION | ADR household (T04) |
| C9 | REPORTS.md Science/Nature + GDP/velocity vs claim-tier | REPORTS.md:3,24-47; REVIEW.md:577-609,390-402 | scope.yaml:16; targets_in_sample.yaml:3; provenance.csv | ASPIRATION_OUTDATED | mark superseded (T01/T11) |
| C10 | Dịch bệnh: cú sốc kịch bản thứ hai | CLAUDE.md:53; SPEC.md:62; REVIEW.md:96-98 | world.yaml:104-107; tick.py:207 | OPEN_DECISION | ADR scenario shock (T03/T08) |
| C11 | Survival floor là behavior treatment cần ablation | REVIEW.md:641; TASKS.md:145-147,334-335 | safety.py:17-64; world.yaml:245-249 | OPEN_DECISION | ablation (T09/T10) |
| C12 | Replay phải bao trùm state mới | CLAUDE.md:36-37; SPEC.md:325-333; TASKS.md:145-147 | world.py:37-39,82,88-89 | INVARIANT | audit hash/replay (T02) |

### Đếm theo nhóm
- INVARIANT: 2 (C3, C12)
- ASPIRATION_OUTDATED: 2 (C6, C9)
- IMPLEMENTATION_EXISTS: 2 (C1, C2)
- OPEN_DECISION: 5 (C4, C7, C8, C10, C11)
- Compliant (không tính): 1 (C5)

### Nguyên tắc bàn giao cho T01 (planner/architect/adversarial-reviewer)
1. ADR 0001 (T01) phải khép C1, C2, C6, C9 và ghi anti-teleology rule bao trùm C3.
2. C3 và C12 là INVARIANT: không được "hợp thức hóa cho đẹp"; C3 phải scenario-gate/loại
   khỏi default, C12 phải xác minh serialization đầy đủ.
3. Không xóa lịch sử benchmark; giữ `preindustrial_closed_v1` replay được như legacy;
   mọi phần bị supersede chỉ được đánh dấu + link tới ADR/charter.
</content>
</invoke>
