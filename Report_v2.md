# REPORT V2 — Chương trình sửa chữa nền tảng cho THÓC sau `real60_spatial`

Ngày: 2026-07-13
Trạng thái: **execution authority** cho đợt sửa chữa kế tiếp; thay thế các phần còn mở
trong `TASKS.md` khi chúng mâu thuẫn với tài liệu này.
Claim tier hiện tại của dự án: **mechanism benchmark**, không phải mô hình lịch sử đã được
hiệu chuẩn hay dự báo kinh tế thực.

## 1. Quyết định điều hành

`real60_spatial` là một chẩn đoán rất có giá trị, nhưng **chưa được dùng làm bằng chứng
khoa học về hành vi LLM hay kinh tế học**. Nó cho thấy đồng thời ba việc khác nhau:

1. môi trường có những cơ chế kinh tế tốt trên giấy nhưng LLM không nhìn thấy hoặc không
   thể gọi được;
2. một số quy tắc xã hội và kế toán hiện làm chết hoặc cô lập tài sản theo cách không chủ
   ý; và
3. artifact của run bị resume chưa có replay transcript khép kín, nên không đạt cổng tái
   lập của chính dự án.

Do đó, không được giải thích kết cục “LLM không tự phát minh nghề/tiền” trước khi các lỗi
P0 bên dưới được sửa. Một kết quả âm sau khi sửa vẫn là kết quả hoàn toàn hợp lệ; mục tiêu
không phải làm cho nền kinh tế hay LLM trông thành công.

Mục tiêu kỹ thuật của đợt này là tạo scenario mới **`spatial_livelihood_v2`** (hoặc một
overlay có tên tương đương, versioned) mà trong đó:

- mọi lựa chọn mà engine thực sự hỗ trợ đều có thể được nhìn thấy, đề xuất, kiểm tra khả
  thi, thực thi và nhận phản hồi bởi agent;
- hộ gia đình, lao động, tài sản người chết, dự án nhiều mùa, thị trường và sinh thái có
  trạng thái rõ ràng, có sổ cái và replay được;
- agent được hỗ trợ bằng dữ kiện, tập lựa chọn khả thi và phản hồi từ hành động trước, chứ
  không bị “mớm” một nghề hay một thể chế phải phát minh; và
- mọi run real sau này được replay từ transcript không mạng, bit-for-bit, kể cả khi đã
  dừng và resume.

## 2. Luật thực thi không thương lượng

1. Đọc theo thứ tự: `CLAUDE.md`, `docs/MODEL_CHARTER.md`, ADR 0001–0005, `TASKS.md`,
   `REVIEW.md`, tài liệu này và code/tests trong phạm vi. Khi mâu thuẫn, viết ADR/decision
   có file:line; không âm thầm chọn văn bản thuận tiện.
2. Chỉ chạy Python bằng `conda run -n thoc-env python ...`. Mọi test/run cục bộ phải bật
   chặn mạng, ví dụ trong PowerShell:

   ```powershell
   $env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m pytest -q --basetemp .tmp\pytest
   ```

3. **Cấm tuyệt đối** mode `real`, `--smoke`, provider/API/LLM, WebSearch, MCP từ xa, đọc
   `.env`, hoặc thay đổi secret. Chỉ dùng rulebot, mock cục bộ, `httpx.MockTransport`,
   `FakeTransport`, transcript fixture và world tool thuần cục bộ. Không có ngoại lệ vì
   “muốn xem thử”.
4. Không reset, checkout, clean, stash, stage hay commit tự động. Working tree hiện có
   thay đổi của người dùng, đặc biệt `reports/paper_draft.md` và các artifact/report đã
   tồn tại; không được sửa, xóa, di chuyển hay ghi đè chúng nếu không thuộc work package.
5. Mọi nguồn lực/tài sản/nợ/công quỹ qua `ledger` và `FlowRegistry`, với đối ứng rõ ràng.
   LLM/policy chỉ tạo intent; engine là chủ duy nhất của state mutation. Không có số dư
   âm để biểu diễn nợ, không mint/hủy ngầm, không tài sản mồ côi vĩnh viễn.
6. Mọi random qua `w.rng`; mọi thứ tự mutation được sort/tie-break; mọi state ảnh hưởng
   lựa chọn sau này vào `world_hash` và checkpoint. Event/metric/transcript là journal có
   định danh, không chỉ là log thuận tiện.
7. Không làm outcome đẹp bằng hard-code nghề, giá, thu nhập, tiền tệ, tỷ lệ sống, đường
   phát triển hay seed. Không giảm assertion, skip test, nới tolerance hoặc đổi report để
   biến fail thành pass.
8. Người implement không tự đóng gate. Mọi work package phải để lại evidence file ngắn ở
   `docs/reviews/` gồm scope, file đổi, command, output, verdict, rủi ro còn lại. Một
   mock run hoặc một seed chỉ là bằng chứng kỹ thuật, không là validation lịch sử.

## 3. Baseline đã xác nhận và cách diễn giải đúng

Nguồn chẩn đoán: `data/runs/real60_spatial/`, manifest/checkpoint/transcript/events của
run, và `reports/real60_evaluation.md` (chỉ đọc; không sửa artifact cũ).

| Quan sát | Bằng chứng hiện có | Hệ quả triển khai |
|---|---|---|
| Prompt nói `1 tick = 6 tháng`, `90kg`, `180 công`, mùa lẻ/chẵn; overlay spatial dùng 4 tháng, 60kg, 120 công, `lua_1 → lua_2 → dong`. | `minds/prompts.py` có `LUAT_VAT_LY` và preamble tĩnh; `scenarios/agrarian_transition_v1/spatial_v1.yaml` có calendar khác. | Đây là P0: agent LLM nhận luật vật lý sai, nên không thể dùng run để kết luận về chiến lược. |
| Engine có `dong_thuyen`, `rao_do`, `qua_song`, nhưng LLM schema/translate/menu không phủ đủ. | `engine/intents.py` có field; `minds/schemas.py`, `minds/translate.py`, `MUC_HANH_DONG` không có các action tương ứng. | Không có qua sông/đò trong run không phải bằng chứng rằng agent đã từ chối nghề đò. |
| Transcript resume không khép kín; journal có hàng lặp/gap ở vùng resume và replay transcript lệch hash. | `tools.replay --from-transcript --verify` báo miss/unused và hash khác; `tools/verify_research_run.py` hiện bỏ qua replay cho real. | Artifact `real60_spatial` chỉ là diagnostic. Cổng real transcript replay phải thành hard gate. |
| Thành viên vừa trưởng thành bị tách khỏi chia sẻ lương thực dù cha mẹ còn thóc. | `World.ho_cua()` chỉ gom con chưa trưởng thành; case A0051 trong checkpoint/evaluation chết trẻ trong khi cha mẹ giàu. | Sửa mô hình residence/household trước khi đánh giá mortality hay welfare. |
| Thóc lớn bị kẹt tại `VO_THUA_NHAN`; những người sống không thể claim/đấu giá. | `engine/world.py` định nghĩa `VO_THUA_NHAN`; checkpoint cuối còn tài sản không thừa kế lớn. | Đây là wealth sink giả tạo, phải có estate/claim/commons lifecycle có ledger. |
| Kế hoạch xây/khai thác nhiều nhưng hành động hoàn thành ít; LLM thường phân bổ vượt công và tin rằng công có thể để dành. | Event/plan analysis: labor không storable, recipe nhà cần nhiều công, production/tick không có work order bền. | Cần feasibility preflight + project tiến độ nhiều tick + feedback kết quả. |
| Giá/market menu tĩnh, thiếu `ngo`, `khoai`, `ga`, `thit`, `ca`; giao dịch gần như chỉ gỗ. | `minds/prompts.py` hard-code danh sách `dat_lenh`, dù world có hàng khác. | Agent không thể chọn cây/nguồn sinh kế theo tín hiệu kinh tế mình quan sát. |
| Chat A2A tạo lời hứa mua bán nhưng không settlement. | Transcript có đồng ý mua gỗ không có ledger trade tương ứng. | Chat tự do cần song hành với protocol quote/accept/escrow/settle có state. |
| Gỗ vẫn lấy được khi còn ô rừng; rừng/gà chưa liên kết bằng biomass/canopy. | Spatial hiện đếm ô rừng và stock gà; log/clear chưa giảm stock rừng theo lượng khai thác. | Chưa có feedback tự nhiên “khai thác gỗ → habitat giảm → gà rừng giảm → nuôi gà có động cơ”. |

Các số population/tuổi/thóc của artifact cũ chỉ được trích dẫn với nhãn
`diagnostic observation from an unreplayable run`; không dùng để chứng minh collapse hay
so sánh model/provider.

## 4. Thiết kế đích: môi trường sống đa dạng nhưng không teleological

### 4.1. Chuỗi nguyên nhân cần mô phỏng

Mỗi nghề hoặc thể chế phải là kết quả của một chuỗi có thể kiểm toán:

```text
tài nguyên + vị trí + thời gian + quyền dùng
    → tập hành động khả thi
    → kỳ vọng riêng / thông tin cục bộ / mặc cả
    → intent có ràng buộc
    → preflight + ledger + thực thi hoặc từ chối có lý do
    → tồn kho, quan hệ, giá giao dịch, sinh thái và ký ức cập nhật
    → tập hành động kỳ sau thay đổi
```

Không mã hóa “nông dân phải thành lái đò”, “chặt rừng phải dẫn đến chăn nuôi”, “xã hội phải
phát minh tiền” hay “ngô/khoai luôn tốt hơn lúa”. Engine chỉ cấp vật lý, quyền, chi phí và
giao thức; khác biệt nghề nghiệp là nhãn quan sát từ ledger/event đã thực thi.

### 4.2. Đơn vị xã hội và tài sản

- **Cá nhân** giữ tuổi, sức khỏe, kỹ năng, quan hệ, lời hứa, quyền sở hữu cá nhân và hành
  động trực tiếp.
- **Residence/household** là state bền: danh sách cư dân, nhà ở, người đại diện quyết định
  (nếu cần), quy tắc provisioning và lifecycle. Thành viên trưởng thành không tự tách chỉ
  vì sinh nhật; tách chỉ qua event rõ ràng như hôn nhân + nơi ở, thỏa thuận split, di cư,
  lập nhà, hay quyết định residence khác.
- **Tài sản** không được tự gom mơ hồ. Chọn một trong hai thiết kế sau trong ADR rồi thực
  hiện nhất quán: (A) một account pantry của household, mọi nộp/rút là ledger transfer;
  hoặc (B) tài sản vẫn cá nhân, engine ghi rõ owner đã cung cấp lương thực cho resident nào.
  Không dùng một helper read-only để ngầm tiêu thóc người khác mà không có event/đối ứng.
- **Estate** giữ tài sản người chết trong thời hạn claim có config; nợ/hợp đồng/di chúc/kin
  claim được xử lý theo thứ tự xác định. Hết hạn, state chuyển qua commons hoặc auction
  minh bạch có người nhận cuối cùng. `VO_THUA_NHAN` không được là ví tiền vĩnh viễn không
  ai chạm tới.

### 4.3. Lao động, dự án và việc làm

Lao động là dòng theo tick, không phải asset tích lũy. Mỗi action đề xuất phải đi qua một
preflight deterministic tạo outcome chi tiết: `requested`, `feasible`, `reserved`,
`executed`, `rejected_or_partial`, `reason_code`.

- Tổng công của một người trong tick, kể cả canh, logging, khai hoang, đánh cá, chăm trẻ,
  học, giúp nhà, dự án và hợp đồng, không vượt capacity theo tuổi/sức khỏe.
- Một **project/work-order** generic có owner, recipe, material escrow/reservation, công
  cần, công đã góp theo người/tick, deadline, cancellation/refund policy, trạng thái và
  event trail. Nhà, thuyền, hàng rào và công trình khác dùng cùng primitive; không tạo một
  hệ “nhà đặc biệt” chỉ để qua test.
- Người nhiều đất có thể tự canh một phần, thuê/góp công phần còn lại, hoặc cho thuê quyền
  dùng đất. Người ít đất có thể làm logging, đánh cá, trông trẻ, xây dựng, lái đò, khai
  hoang, chế tác hay trao đổi nếu action khả thi. Lương/chia sản lượng/rent chỉ được tạo từ
  hợp đồng/quote đã settlement, không từ nghề gán sẵn.
- Project không bảo đảm thành công: thiếu vật liệu, thiếu đối tác, hết hạn, giá đổi, chết
  hoặc rút lui đều phải tạo outcome có ledger/rollback đúng.

### 4.4. Không gian và sinh thái

Không cần mô phỏng hạt giống, nước hay vi chất. Cần mô phỏng tối thiểu stock-flow đủ để các
lựa chọn tác động ngược lại môi trường:

- Mỗi ô rừng có `biomass`/`canopy` bounded, tái sinh có config và event before/after.
  Logging lấy gỗ giảm stock; clearing chuyển đất, giảm canopy/habitat; logging chọn lọc và
  clearing có tác động khác nhau. Không được thu gỗ vô hạn chỉ vì ô còn mang nhãn `rung`.
- Sức chứa gà rừng phụ thuộc tổng habitat/canopy, không chỉ số ô. Catch có CPUE theo stock;
  regeneration logistic; nuôi gà là lựa chọn khác sử dụng gà con/thức ăn/công, không phải
  compensation tự động khi gà rừng giảm. Reforestation là lựa chọn có chi phí/thời gian nếu
  thêm vào.
- Sông, hai bờ, đò, quyền qua sông, phí, capacity và maintenance là physical/network state.
  Muốn khai hoang bờ hoang phải qua sông hợp lệ; thuyền/đò phải được xây, sở hữu và vận hành
  qua ledger. Không tạo tàu/đường tắt vì một agent “đã lên kế hoạch”.
- Calendar `lua_1 → lua_2 → dong` phải đi qua một API thời gian duy nhất. Lúa, ngô và khoai
  là crop options có labor/output/nutrition riêng trong scenario; quyết định dựa trên ràng
  buộc và thông tin agent có, không dựa vào lời khuyên ưu tiên của prompt.

### 4.5. Thị trường, thông tin, A2A và autonomy

“Prompt mạnh hơn” không có nghĩa nhồi thêm lời khuyên. Nó có nghĩa agent nhận được thông tin
đúng, ngắn, khả thi và có phản hồi để học.

1. **Dynamic capability catalog.** Khai báo action một lần (descriptor/registry) gồm
   intent field, schema validation, translate, engine handler, scenario gate, availability
   predicate, prompt rendering, tool schema và outcome codes. Test phải fail nếu engine
   public action không có đường đi LLM, hoặc menu quảng cáo action không thực thi được.
2. **Fact cards, không phải giá do engine áp đặt.** Mỗi agent chỉ thấy tài sản mình có thể
   chuyển/mua/bán, inventory own/household hợp lệ, giao dịch địa phương gần đây, bid/ask và
   depth nếu quan sát được, coverage, chi phí đi lại, price belief riêng cùng độ bất định,
   và opportunity card của từng hoạt động khả thi. Giá lịch sử là evidence, không phải
   “giá đúng”; private prior không phải settlement price.
3. **Opportunity card.** Với lúa/ngô/khoai, logging, gà rừng, nuôi gà, cá, đò, xây dựng,
   chăm trẻ, thuê/cho thuê đất... hiển thị chỉ khi feasible hoặc gần feasible: labor,
   required input, expected output/nutrition, tồn kho reserve, time-to-completion, resource
   impact và market evidence mà agent được phép biết. Card nói sự thật, không xếp hạng nghề.
4. **Local world tools bị giới hạn.** Nếu dùng tool-call, chỉ có các tool read-only deterministic
   như `xem_thi_truong_local`, `xem_co_hoi_san_xuat`, `xem_du_an`, `xem_bao_gia`,
   `xem_tai_nguyen_gan_day`. Tool có schema, authorization theo vị trí/quan hệ, quota nhỏ,
   transcript đầy đủ và không truy cập network/MCP từ xa. Tool không sửa `World`; mọi mutation
   vẫn là action JSON đã validate.
5. **Feedback loop.** Prompt/ký ức phải ghi outcome action gần đây: accepted/partial/rejected,
   quantities thực hiện, counterpart, price/payment thực, project progress, lý do thất bại.
   Không ghi “bạn đã làm X” nếu chỉ là intent; không để agent lặp mãi action không feasible.
6. **A2A commerce thread.** Giữ `nhan_tin` tự do, nhưng thêm structured protocol:

   ```text
   request_quote → quote → counteroffer → accept/reject
       → reserve_or_escrow → delivery/settlement → completed | expired | cancelled
   ```

   Mỗi thread có ID, parties, asset, quantity, unit price, payment asset, expiry,
   delivery/location và state machine deterministic. `accept` phải khóa đủ hàng/payment
   (hoặc reject rõ); settlement chuyển đúng một lần qua ledger; expiry giải phóng reserve.
   Một tin nhắn “đồng ý” không được tự tạo trade, và một quote không được chi tiêu cùng một
   inventory nhiều lần.

## 5. Work packages theo thứ tự bắt buộc

Không làm P1–P4 như một feature bundle trước khi P0 có test xanh. Mỗi package cần ADR khi
đổi state ownership/law nền; người implement, test, QA và reproducibility phải khác vai.

### P0 — Sự thật giao diện và artifact tái lập (blocking)

**Owners:** `spec-governor`, `minds-engineer`, `engine-surgeon`, `reproducibility-steward`
**Independent gates:** `test-engineer`, `qa-verifier`, `adversarial-reviewer`

#### P0.1 Prompt/config/capability parity

- Thay `LUAT_VAT_LY` và preamble static bằng renderer từ active `World.cfg`: months/tick,
  seasons, food, labor, crop/recipe, age/childcare, resource and scenario gates. Một source
  of truth duy nhất; prompt không được tự tính các hằng số có thể khác config.
- Bỏ danh sách assets/action hard-code trong `MUC_HANH_DONG`. Tạo catalog dynamic và
  render action only when role/scenario/availability predicate cho phép. `ngo`, `khoai`,
  `ga`, `thit`, `ca`, `go`, `thuyen` và hàng hợp lệ mới phải có đường qua market/menu.
- Phủ `dong_thuyen`, `rao_do`, `qua_song` qua `KeHoach`, schema, translator, menu, outcome
  and test. Cùng audit các action engine khác để không còn capability mồ côi.
- Render một prompt spatial thật trong test và assert nó nói đúng `4 tháng`, `60kg`,
  `120 công`, ba mùa và crop/đò đúng context; test base legacy vẫn có đúng luật base.

#### P0.2 Resume-safe journals và transcript replay bắt buộc

- Thiết kế `RunJournalManifest`/checkpoint metadata có run UUID, segment ID, checkpoint tick,
  byte offsets/record counts/hash của `events.jsonl`, `metrics.jsonl`, `transcript.jsonl` và
  call log. Khi resume, hoặc truncate an toàn phần tail sau checkpoint (chỉ trong run đang
  resume) hoặc mở segment rõ ràng; không append trùng mù quáng.
- Thêm unique monotonic event ID/sequence, unique metric tick within segment, unique call ID
  và continuity checks. Nếu journal không khớp checkpoint, run phải fail closed hoặc yêu cầu
  recovery command explicit có audit record; không tự “bỏ qua cho chạy”.
- `tools.replay --from-transcript --verify` phải yêu cầu `misses == 0`, `unused == 0`, hash
  bằng manifest và config/prompt identity đúng. `tools.verify_research_run` phải chạy cổng
  này cho **real** mà không gọi mạng; không còn nhánh “mode real nên bỏ qua”.
- Viết recovery/migration cho artifact cũ chỉ nếu có thể chứng minh; nếu không, đánh nhãn
  `diagnostic_only_unreplayable`, không sửa số liệu âm thầm. `real60_spatial` giữ nguyên
  lịch sử và không được retcon thành verified.

**Acceptance P0:** capability matrix tự kiểm; prompt active config không còn hằng stale;
run FakeTransport chia hai phiên + resume có event/metric/transcript unique, cùng hash như
run liền; transcript replay không mạng pass. Không đạt một mục = dừng P1.

### P1 — Hộ, vòng đời, estate, feasibility và project

**Owners:** `agrarian-economist`, `model-architect`, `engine-surgeon`
**Independent gates:** `household-demography-specialist`, `test-engineer`, `qa-verifier`

1. Viết ADR successor cho household/residence and estate, nêu owner/lifecycle/schema/hash/
   migration/ledger identity. Reconcile ADR 0003 thay vì tạo layer song song.
2. Implement residence membership stable. Consumption/food security đo ở unit đã định nghĩa;
   adulthood không tách ngay. Marriage, residence split, migration, adoption, death, inheritance
   và remarriage có transitions explicit, deterministic, serialized.
3. Implement estate lifecycle and claim/auction/commons transfer. Bảo toàn từng asset type,
   close/redirect contract positions, prohibit dead/estate ghost from receiving new offers.
4. Tạo feasibility planner deterministic cho toàn tick, không mutating before validation.
   Nó xử lý labor budget, input/reserve, ownership, location/river, contract status and project
   capacity; execution consumes only accepted allocation.
5. Implement generic projects/work-orders with material/labor progress across ticks, event
   schema and contract integration. Mỗi cancellation/default/path phải ledger-audited.

**Acceptance P1:**

- adult resident có thể ăn từ household arrangement hợp pháp trong khi parents còn đủ food;
  không có automatic age-based orphaning;
- death case có/không heir, creditor, claim expiry và auction đều preserve balance;
- requested labor > capacity produces deterministic partial/reject, never hidden overwork;
- house/boat can complete from several ticks/contributors only when material and work are
  truly supplied; no double pay or double consume;
- same seed/checkpoint/replay world hash match.

### P2 — Rừng, gà, đò, khai hoang và crop economics

**Owners:** `spatial-ecology-specialist`, `graph-architect`, `engine-surgeon`
**Independent gates:** `agrarian-economist`, `reality-auditor`, `test-engineer`

1. Add per-cell forest state and explicit flows for regrowth/logging/clearing/reforestation
   (if enabled). Move all rates to scenario config with units and source status.
2. Recompute wild-chicken habitat K from canopy/biomass; use stock/K/CPUE/regeneration and
   journal each extraction. Prevent impossible catch/logging after stock depleted.
3. Connect wood to recipes/projects, ferry construction and housing. Validate river access
   and ferry service outcomes through the capability catalog from P0.
4. Expose crop choice factual cards: expected physical output, food equivalent, labor,
   possible market evidence and private belief. Do not choose crop in engine from a global
   “best profit” calculation.
5. Preserve legacy/off hash behavior as stated by ADR 0005; v2 scenario must version all
   changed parameters and cannot silently alter legacy runs.

**Acceptance P2:** a controlled logging shock lowers biomass then canopy/habitat K and
eventually wild catch yield; regeneration/reforestation changes the opposite direction;
clearing/wood/house/boat flows reconcile. Ferry/far-bank tests cover successful, no-boat,
insufficient-fare, capacity, expiry and project cases. Crop outcomes differ only due declared
physics/market evidence, not a hard-coded profession rule.

### P3 — Agent autonomy, local tools and economic settlement

**Owners:** `minds-engineer`, `agent-autonomy-protocol-designer`
**Independent gates:** `sim-economist`, `adversarial-reviewer`, `qa-verifier`

1. Replace verbose stale instruction with a concise “survive, preserve options, make a
feasible choice” runtime prompt built only from state/fact cards. Explicitly tell agents
that they may choose inaction, cooperate, trade, rent, work for others, cultivate, fish,
log, ferry, build, care for children or explore only if the displayed constraints allow.
   Never tell them which one maximizes welfare or that an invention/money/government is desired.
2. Add bounded deterministic local world tools and transcript them. Tool use must be optional;
   equal prompt + tool transcript must reproduce same decision. No remote/MCP/network tool is
   part of economic production or state.
3. Add action outcome cards/memory and planned-vs-executed evidence. Intent rejection codes
   must be actionable (`insufficient_labor`, `no_right`, `no_inventory`, `no_boat`,
   `counterparty_unavailable`, `expired_quote`, ...), not a generic silent discard.
4. Implement quote/escrow/settlement threads; retain chat only as communication. Add market
   catalog and price coverage cards with local information boundaries.
5. Benchmark LLM interface only with mock/FakeTransport fixtures. Include malformed JSON,
   tool errors, stale quote, partial action and transcript replay tests.

**Acceptance P3:** fixture agents can discover every available action through catalog/tool,
negotiate a quote that settles exactly once, receive and react to a failed action, and select
at least two distinct feasible livelihood paths under different factual states without any
job label being assigned. This demonstrates interface capability, **not** that a real LLM
will innovate.

### P4 — Metrics, research artifacts and honest evaluation

**Owners:** `research-artifact-integrity-auditor`, `sim-economist`,
`reproducibility-steward`
**Independent gates:** `empirical-validation`, `adversarial-reviewer`, `qa-verifier`

Add versioned metrics/events with definitions and missing-data policy:

- life table: age at death by cause, period mortality, birth/death rates, dependency ratio,
  mean/median age of living population **and** age-at-death; never call survivor mean age
  “life expectancy”;
- household/residence: food security, poverty duration, transfer/provisioning, housing,
  household split/merge and estate disposition;
- work/project funnel: prompted → parsed → translated → feasible → reserved → executed →
  completed/failed, by action and reason code;
- economy: crop/food-equivalent production, marketed surplus, transactions/assets/payment,
  quote-to-settlement conversion, price coverage/book depth, rent/wage only when observed;
- ecology/spatial: biomass/canopy, forest area, wild stock/K/catch, domestic stock, river
  crossings, ferry capacity/utilization, far-bank settlement and resource flows;
- reproducibility: artifact segment, journal continuity, prompt/config/catalog hash, transcript
  consumption, fallback/malformed/tool usage, cost fields when real artifacts are later used.

Every chart/report must say whether it uses executed ledger/event outcomes or merely intents.
No statistic with insufficient denominator/coverage gets an economic interpretation.

## 6. Required test matrix

Tests belong in appropriate domain files; names below are behavioral contracts, not an excuse
to write one giant integration test.

| Area | Required deterministic tests |
|---|---|
| Prompt/config | Base + spatial rendered prompt carries active months, food, labor and season; no action advertised without schema/translate/handler; no handler action hidden without declared reason. |
| Resume/replay | uninterrupted vs two-segment resume for rulebot, mock, and FakeTransport-real; same world hash; no duplicate event/call IDs; metric sequence valid; transcript exactly consumed; corrupt offset fails closed. |
| Household | adult remains resident; explicit split changes provisioning only via ledger event; marriage/adoption/death/remarriage serializes; enough shared food prevents artificial starvation. |
| Estate | heir, creditor, no claimant, expiry/auction, and rejected ghost offer; each asset and debt has exactly one legal destination; no permanent inaccessible balance. |
| Feasibility/project | overallocated work, competing actions, missing inputs, partial progress, cancellation, contributor death, exact-once payment/refund; deterministic ordering. |
| Ecology | log/clear/recover/reforest stock-flow; chicken K and CPUE response; no extraction over stock; same-seed replay. |
| Spatial/ferry | all route/fare/capacity/ownership/project states; LLM schema/translation reaches engine intents. |
| Market/A2A | dynamic assets including crop/animal/food; quote/counter/accept/reject/expiry; escrow/reservation and exact-once settlement; chat alone cannot settle. |
| Minds/tools | malformed response, invalid tool args, quota, unavailable action, localized information, action-result memory, transcript replay without provider. |
| Metrics | denominator/undefined behavior, executed-vs-planned funnel, age-at-death correctness, no double-count across resident household, artifact schema backward migration. |
| Regression | full legacy suite and off-overlay hash guarantees asserted explicitly; no unrelated output overwrite. |

Run at minimum after relevant packages and before handoff:

```powershell
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m pytest -q --basetemp .tmp\pytest
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m ruff check .
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m tools.verify_local
```

If a command fails because of an existing environment limitation, record the raw failure and
do not reinterpret it as pass. Do not invoke any real endpoint to fill a test gap.

## 7. Rollout and gates

1. **Design gate:** update conflict map; write ADRs for P0 journal/capability registry and
   P1 residence/estate/project before production changes. Freeze `real60_spatial` label as
   diagnostic-only.
2. **P0 technical gate:** all prompt/capability/replay tests green. The implementation must
   demonstrate interrupted/resumed FakeTransport run equals uninterrupted run.
3. **P1/P2 mechanism gate:** run deterministic/rulebot small worlds and a predeclared mock
   ensemble with paired seeds. Report both activation and non-activation of ferry, rent,
   clearing, domestic chicken, project and crop paths. Do not tune to force any path.
4. **P3 interface gate:** run local mock/FakeTransport fixtures with tool and settlement
   coverage; inspect transcript and execution funnel. This validates the interface, not
   human realism.
5. **Research artifact gate:** `verify_research_run` must pass including transcript replay,
   manifest/config/catalog/prompt identity and event uniqueness. Only then may a future
   human-authorized real pilot be considered.
6. **Human gate for real LLM:** out of scope for this task. It requires explicit user approval,
   cost budget, provider configuration and a clean one-session or resume-safe execution plan.

For any future real comparison, preregister seeds, models, temperature/prompt/catalog hash,
horizon, primary metrics, collapse definition, fallback policy and stopping rule. Report all
failed/aborted runs and paired uncertainty. Do not compare heuristic PersonaBot success to
LLM behavior as proof of emergence: it is an interface/policy baseline with known built-in
knowledge.

## 8. Agent orchestration and handoff contract

Claude Code must use `.claude/agents/README.md` and the specialized agents updated with this
report. The integration manager must maintain a dependency/evidence ledger, not a narrative
checklist. A package is `DONE` only when all are present:

```text
scope + ADR/decision (when needed)
+ economic/mechanism memo
+ implementation diff constrained to scope
+ independent test additions
+ QA command/output/verdict
+ reproducibility command/output/verdict
+ adversarial review and explicit disposition of every blocking finding
```

The final handoff must distinguish exactly:

- `technical-ready`: code/test/audit/replay gate passes;
- `mechanism-ready`: a bounded causal mechanism has scenario, ablations and execution data;
- `research-ready`: artifacts/protocol/uncertainty are adequate for the stated benchmark;
- `empirically-validated`: **not available** without sourced data, calibration and holdout.

No agent is allowed to turn planned action counts, prompt text, one mock run, an attractive
chart, or an unreplayable real run into a claim of autonomous economic development.

## 9. Explicit non-goals for this execution

- Do not add micro-details such as seed genetics, water, nutrients or an exhaustive job list.
- Do not introduce external web data, calibration targets, provider calls or historical claims.
- Do not force the formation of money, government, firms, wage labor or innovation.
- Do not rewrite legacy history/output merely to make `spatial_livelihood_v2` clean.
- Do not optimize token cost by silently reducing decision quality/model tier; the current
  task does not run real LLM at all.

The desired result is a harder, more legible experiment: agents can genuinely try many
feasible ways to survive and cooperate, can fail for discoverable reasons, and leave an
artifact that another researcher can replay and challenge.
