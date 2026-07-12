# ADR 0003 — Household core, seasonal budget, market locality & land (T04+T05)

- Status: **Proposed** (2026-07-12)
- Context: `docs/MODEL_CHARTER.md` §1 (hộ là đơn vị kinh tế), §3 (5 lớp — Lớp-1 vật lý, Lớp-2 kế
  toán, Lớp-5 observatory chỉ đọc), §5 (cổng định chế), anti-teleology §5;
  `docs/adr/0001-scope-and-institutional-layers.md` §A (invariant), §D (determinism phủ state mới);
  `docs/adr/0002-behavior-policy-interface.md` (policy chỉ trả intent); `TASKS.md` T04, T05.
- Deciders: agrarian-economist + model-architect (design). Implementation & independent test/QA
  sign-off PENDING (xem Handoff).
- Scope guard: ADR này **không** implement engine. Nó chốt interface, ownership, accounting
  identity, test matrix và phân định rõ **IMPLEMENTED vs PENDING**. Không mục nào ở đây được coi
  là bằng chứng thực chứng (charter §2, mọi số là `design_assumption`).

## Context — sự thật nền đã khảo sát (file:line)

Đây là bản đồ cơ chế **đang có**, xác minh trực tiếp từ code. ADR chỉ được đề xuất mở rộng trên
nền này, không viết lại.

### Hộ gia đình (T04) — đã có, thuần read-only
- `engine/economy.py:15` `households(w)` chuẩn hóa hộ sống từ `w.ho_cua(aid)`, định danh ổn định
  theo **id nhỏ nhất** trong nhóm; dedupe bằng `set(tuple(sorted(...)))` để không đếm cặp vợ
  chồng hai lần. `engine/world.py:276` `ho_cua` định nghĩa membership: chủ hộ + vợ/chồng còn sống
  + con (đẻ lẫn nuôi) chưa trưởng thành, trẻ mồ côi quy về người giám hộ.
- `engine/economy.py:29-57` `household_food_need` / `household_grain` / `household_snapshot`:
  `food_security = grain / need`. **Toàn bộ là derived view** — không transfer, không đặt giá,
  không rẽ nhánh (docstring `economy.py:1-6`).
- Ownership tài sản là **cá nhân**: `household_grain` cộng `w.ledger.so_du(aid,"thoc")` từng thành
  viên; **không có pantry/kho chung**. `minds/safety.py:45-47` khẳng định: tại thời điểm gieo,
  người canh phải **tự có giống** (`own_grain >= giong`), không có cơ chế "rút kho chung".
- Survival floor `minds/safety.py:17` config-gated (`minds.san_an_toi_thieu.bat`), ghi event
  `san_an_toi_thieu` mỗi lần áp dụng; chỉ **thêm intent canh** cho hộ dưới ngưỡng dự trữ và chưa ai
  định canh — không mutate ledger.
- Metrics hộ đã emit tại `engine/metrics.py:180-183`: `so_ho`, `thoc_ho_trung_vi`, `gini_thoc_ho`,
  `ty_le_ho_thieu_an`. Metrics cá nhân song song (`gini_thoc`, `gini_dat`, `gini_thu_nhap`) giữ
  riêng để hai khái niệm không lẫn (`metrics.py:178-179`).

### Chợ / giá / vận tải / đất (T05) — đã có
- `engine/market.py:141` `phien_cho` gom lệnh theo khóa **`(lang, tai_san, thanh_toan)`** → **mỗi
  làng một sổ lệnh riêng**; `market.py:42` `_khop_mot_so_lenh` là **call auction uniform clearing
  price** p* (tối đa khối lượng, khớp pro-rata tại biên), transaction nguyên tử bốn chân qua
  `ledger.ap_dung` (`market.py:83-94`).
- `engine/market.py:176` `phien_dat` là **sealed-bid first-price** từng thửa (bid cao nhất ≥ ask
  thắng, trả đúng giá bid).
- Phí vận chuyển: `market.py:27` `_phi_buon_chuyen` burn 2%/khoảng-cách qua
  `ledger.huy(..., "phi_van_chuyen", ...)` — **đã đi ledger/FlowRegistry**, không chỉ trừ metric.
- Đất: `Parcel.chu` (sở hữu); thuê = clause `quyen_su_dung` (`contracts.py:35`); tô =
  `chia_san_luong` (`contracts.py:49`); thế chấp đất = string trong `HopDong.the_chap`
  (`contracts.py:97`), xiết qua `xiet_the_chap` (`contracts.py:216`). **Price (bán) và rent (tô)
  đã là hai khái niệm tách.**
- `engine/economy.py:84` `expected_land_value` = DCF phần sản lượng thuộc chủ đất pha với giá chợ
  gần nhất — docstring nói rõ đây là **NEO hành vi**, "Chợ vẫn là nơi duy nhất quyết định giá giao
  dịch" (`economy.py:90`). `expected_parcel_net_output` (`economy.py:66`) là thước đo **vật chất**,
  không phải giá.
- `engine/economy.py:110` `land_price_productivity` chỉ báo tỷ số price/expected-output **khi có
  giao dịch thật** (`giao_dich_dat` ghi tại `market.py:209`), tránh bịa giá thửa chưa thanh khoản.

### Lỗ hổng đo lường đã xác nhận (là lý do của ADR)
- `engine/world.py:171` `ghi_gia` khóa lịch sử giá **chỉ theo `tai_san`** (hoặc `tai_san/thanh_toan`),
  **KHÔNG theo làng**. Trong `market.py:127-132` mọi làng ghi chung một chuỗi giá. ⇒ **không đo
  được price dispersion giữa làng** dù order book đã tách theo làng.
- `khop_cho` event (`market.py:96-98`) **không mang trường `lang`** ⇒ không tái dựng được phân tán
  giá per-làng từ event journal.
- Chưa có metric: `marketed_surplus`, `consumption_gini` (tách khỏi grain/income), `yield_per_parcel`,
  `poverty_duration`, `price_dispersion_by_asset`.

## Decision

### A. Household model — chốt (giữ nguyên ownership cá nhân, không pantry)

1. **Membership = `economy.households(w)`** là single source of truth cho "hộ". Head = id nhỏ nhất
   (ổn định qua sort). Đây là **derived view trên state cá nhân** (`Agent`), KHÔNG là một object
   `Household` có state riêng ⇒ không có state field mới cần hash/checkpoint, không có lifecycle
   mới. Cưới/sinh/chết/tái hôn/cưu mang đã thay đổi `Agent.vo_chong/cha/me/giam_ho/con/con_nuoi`
   (đã vào `world_hash` tại `world.py:304-310`) nên hộ tự cập nhật, không double-count.
2. **KHÔNG thêm pantry chung.** Household budget vẫn là **derived read-only view**. Lý do: pantry
   chung sẽ là một chủ thể ledger mới (như `CONG_QUY`) với lifecycle sinh/giải thể khi hộ hình
   thành/tan; chi phí kế toán và rủi ro "âm thầm gom tài sản thành viên" (TASKS T04 gạch đầu dòng
   2) lớn hơn lợi ích ở tầng mechanism benchmark. Nếu tương lai cần pantry, nó **phải** là chủ thể
   ledger tường minh với transfer vào/ra explicit (PENDING, cần ADR riêng + engine-surgeon).
3. **Bốn khoản không được lẫn** (định nghĩa cho metric layer, không đổi engine):
   - *income* = dòng chảy cửa sổ `thu_nhap_4` (đã có, `ghi_thu_nhap` `world.py:113`), loại nguồn
     `canh_*` (đó là bộ đếm thửa, không phải thóc — `metrics.py:100-101`).
   - *consumption* = thóc/thịt bị `an_va_suc_khoe` + `hao_hut_kho` tiêu trong tick (Lớp-1 vật lý).
   - *assets (stock)* = `ledger.tai_san_cua(aid)` (thóc, đất, công cụ, nhà, xu…).
   - *liquidity* = tập con assets thanh khoản (thóc + xu) — báo tách khỏi đất/nhà.
   Metric mới chỉ **đọc** bốn khoản này; cấm trộn stock với flow trong cùng một con số.

### B. Seasonal budget — accounting identity (đo, không cưỡng chế)

Định nghĩa **identity kiểm toán mỗi tick per-hộ** (read-only, để test và report; engine đã bảo
toàn ở tầng ledger — đây là *view* trên các flow đã có, KHÔNG là luật engine mới):

```
grain_end(ho)  = grain_start(ho)
               + harvest(ho)              [flow "gat",  +]
               - seed(ho)                 [flow "giong", tiêu hao khi gieo]
               - eaten(ho)                [an_va_suc_khoe]
               - spoilage(ho)             [hao_hut_kho]
               + net_market(ho)           [Σ khớp chợ mua−bán, quy thóc]
               + net_transfer(ho)         [tô/hợp đồng/thuế-rebate/thừa kế]
```

Mỗi hạng phải map về flow/transaction đã có trong ledger (không có hạng "khác"). Stock (grain,
đất, công cụ) tách khỏi flow (harvest, eaten); hiện vật (kg thóc, số thửa) tách khỏi giá trị quy
thóc (numéraire=1). `expected_parcel_net_output` là **decision-anchor**, đánh dấu rõ khác với
`yield_per_parcel` **quan sát** (mục C).

### C. Observability metrics cần THÊM — read-only, làm được NGAY

Tất cả thuần đọc `ledger`/`gia_lich_su`/`events`/`giao_dich_dat`; **không mutate engine**, không
đọc lại để rẽ nhánh (charter Lớp-5). Đặt trong `engine/economy.py` (view) + surface qua
`engine/metrics.py:tinh_metrics`. Định nghĩa missing/zero/undefined tường minh:

| Metric | Định nghĩa | undefined khi |
|---|---|---|
| `marketed_surplus` | Σ khối lượng bán ra chợ / Σ sản lượng gặt, per-hộ & tổng | không gặt ⇒ undefined (không phải 0) |
| `consumption_gini` | Gini của `eaten(ho)` (không phải grain-stock) | <2 hộ ⇒ undefined |
| `income_gini` vs `consumption_gini` | báo **tách**; `gini_thu_nhap` đã có, thêm consumption | như trên |
| `yield_per_parcel` | sản lượng gặt thực / số thửa canh (quan sát) | 0 thửa canh ⇒ undefined |
| `poverty_duration` | số tick liên tiếp `food_security<1` per-hộ; cần **state đếm** (mục E) | hộ mới lập ⇒ 0 |
| `price_dispersion_by_asset` | coefficient-of-variation giá khớp giữa làng, per-asset per-tick | <2 làng có khớp ⇒ undefined |

Quy tắc coverage (T05 gạch cuối): **không suy luận price-to-rent/dispersion khi số giao dịch <
ngưỡng** `quan_sat.cua_so_dat_tick`; luôn báo kèm `n_transactions`/`n_villages_traded`.

### D. Price dispersion per-làng — QUYẾT ĐỊNH đường ít rủi ro

Có hai đường; chọn đường không đụng world-hash trước.

1. **Read-only (làm ngay, KHÔNG đổi world-hash):** thêm trường `lang=lang` vào payload event
   `khop_cho` (`market.py:96`). Event journal (`events.jsonl`) **không** nằm trong `world_hash`
   (`world.py:349-354` chỉ hash tick/seed/agents/parcels/so_du/hd/gia/p4/qh/cq — không hash
   events). `price_dispersion_by_asset` được tính trong observatory/metrics bằng cách đọc lại
   `khop_cho` của tick hiện tại theo `lang`. **Rủi ro world-hash: KHÔNG** (chỉ thêm field journal).
   ⚠️ Ràng buộc: chỉ thêm `lang` vào **event payload**, tuyệt đối không thêm field vào `Lenh` hay
   `gia_lich_su`.
2. **Engine mutation (PENDING, cần review):** đổi `ghi_gia` để khóa `(lang, tai_san)`. Việc này
   **thay đổi keys của `gia_lich_su`** ⇒ `gia_s` trong `world_hash` (`world.py:325-327`) đổi ⇒
   **phá replay của mọi checkpoint/run cũ**. Chỉ làm sau migration có versioning (mục F) và chỉ bật
   cho `agrarian_transition_v1`. Đường này KHÔNG làm trong T05 nếu đường (1) đủ để đo dispersion.

`expected_land_value` giữ nguyên vai trò **signal hành vi** (ADR 0001 §A #3 policy-only); T05
không được để nó đặt giá giao dịch (đã đúng — `phien_dat` dùng bid, không dùng anchor).

### E. State ownership & lifecycle của metric mới

- **Không có `Household` object** ⇒ không owner state mới cho hộ. Toàn bộ mục C trừ `poverty_duration`
  là **stateless derived** mỗi tick.
- `poverty_duration` cần **một state field đếm** per-hộ-head: `w.poverty_streak: dict[str,int]`.
  - Owner: engine (cập nhật ở bước ket-toan, sau audit `tick.py:227`), **không** policy.
  - Reset-per-tick: KHÔNG reset; là streak tích lũy. Reset về 0 khi `food_security>=1`.
  - Head đổi (chết/tái hôn) ⇒ key theo head-id có thể "gãy"; quy ước: streak theo head hiện tại,
    hộ mới head ⇒ bắt đầu 0 (ghi rõ là giới hạn đo lường, không phải bug).
  - **Serialization/checkpoint:** vì ảnh hưởng report chứ không hành vi, nó là *observation state*.
    Theo charter §D "mọi state ảnh hưởng hành vi phải vào hash". `poverty_streak` KHÔNG ảnh hưởng
    hành vi (engine không đọc lại) ⇒ **không cần vào `world_hash`**, nhưng **phải reconstruct được
    từ metric journal** (`metrics_lich_su`) để replay report. Nếu muốn an toàn tuyệt đối, đưa vào
    checkpoint pickle (đã tự động qua `luu_checkpoint` `world.py:357` pickle toàn bộ World) nhưng
    **không** vào `world_hash`. ⇒ Đây là mục **PENDING (engine mutation nhỏ, cần review §D charter)**.

### F. Migration path — không phá run/checkpoint cũ

- Đường D(1) + toàn bộ mục C (trừ poverty_streak): **không đổi world-hash, không đổi checkpoint
  schema** ⇒ run/checkpoint cũ replay y nguyên. Metric mới chỉ xuất hiện trong `metrics_lich_su`
  của run mới; tool phân tích cũ bỏ qua key lạ.
- Đường D(2) và `poverty_streak`-vào-hash: **cần bump artifact version** và scenario-gate. Checkpoint
  cũ thiếu field ⇒ `nap_checkpoint` (`world.py:371`) đã có migration pattern (vd `mau_mo_goc` tại
  `world.py:381`); thêm default an toàn (`getattr(w,"poverty_streak",{})`). Không sửa hash của
  `preindustrial_closed_v1`.

## Failure / rollback / ordering deterministic

- **Thứ tự tick liên quan** (đã có, không đổi): sản xuất `tick.py:121-123` → thuế `:125` → chợ
  `phien_cho :187` / `phien_dat :188` → hợp đồng `:191` → tiêu dùng/sức khỏe `:203-207` → nhân
  khẩu `:211` → ket-toan+audit `:227` → metrics `:229`. **Metric hộ/chợ mới đọc SAU audit** để phản
  ánh state đã đóng sổ.
- **Deterministic ordering:** mọi vòng lặp metric phải `sorted(...)` theo id/khóa (như
  `households` đã `sorted(groups)`); dispersion đọc `khop_cho` theo `sorted(lang)`. Không phụ thuộc
  dict order.
- **Failure/rollback:** transaction chợ đã nguyên tử — bên thiếu hàng ⇒ `LoiSoKep` nuốt tại
  `market.py:116-117`, phần khớp đó bỏ (đã đúng). Metric read-only **không** được raise làm gãy
  tick; undefined ⇒ trả `None`/NaN-sentinel có ghi chú, không trả 0 giả.
- **FlowRegistry/ledger:** mục C/D(1) **không tạo bút toán mới** (chỉ đọc). Không đăng ký flow mới.
  Nếu D(2) hay pantry được làm sau, mọi flow phải có counterpart + đăng ký nguồn/sink (ledger #1/#2).

## Test matrix

**Unit (thế giới nhỏ 8×8, 10 agent, 20 tick — CLAUDE §3):**
- `households` dedupe: cặp vợ chồng đếm 1 lần; trẻ mồ côi thuộc hộ giám hộ; head = id nhỏ nhất.
- Bốn khoản không lẫn: income/consumption/assets/liquidity của cùng hộ khác nhau về đơn vị/nguồn.
- Metric undefined trả sentinel đúng (0 thửa canh ⇒ yield undefined, không 0).

**Property / invariant (hypothesis):**
- Seasonal identity (B) đóng per-hộ mỗi tick với sai số ≤ 1e-6 trên nhiều seed.
- Trẻ chưa trưởng thành **không bao giờ rơi khỏi mọi hộ** (partition property).
- `marketed_surplus ∈ [0,1]` khi có gặt; tổng bán ≤ tổng tồn+gặt.

**Comparative statics (paired-seed, ceteris paribus):**
- mưa↑ (dịch `thoi_gian.thoi_tiet` sang tay `duoc_mua`) ⇒ `expected_parcel_net_output` kỳ vọng↑ và
  sản lượng gặt trung vị↑.
- màu mỡ↑ giữ vị trí thửa ⇒ `expected_parcel_net_output` **không giảm** (monotone in `mau_mo`).
- transport cost↑ (`thuong_mai.phi_van_chuyen_moi_khoang_cach`) ⇒ `price_dispersion_by_asset`
  **không giảm có hệ thống** (dấu ≥ 0); market participation không tăng.

**Replay:** run có metric mới (đường D(1)) replay ra **cùng `world_hash`** như run không có metric
(chứng minh read-only không đụng determinism).

**Negative:**
- Intent bán nhiều hơn tồn ⇒ phần dư bị bỏ, ledger không âm, hộ không "mất tài sản trái phép".
- Death/inheritance: tổng tài sản trước = sau (không tạo/mất) — dùng audit hiện có.
- Metric không được raise khi 0 hộ/0 giao dịch (báo undefined).

## IMPLEMENTED vs PENDING

**IMPLEMENTED (đã có trong tree, ADR chỉ chốt/đặt tên):**
- Household membership + snapshot + food_security (`economy.py:15-57`), ownership cá nhân, không
  pantry; survival floor config-gated (`safety.py`).
- Per-làng order book + call auction + sealed-bid land + transport-fee-via-ledger (`market.py`).
- Price vs rent tách; `expected_land_value` là anchor; `land_price_productivity` coverage-guarded.
- Metrics hộ/gini đã emit: `so_ho`, `gini_thoc_ho`, `ty_le_ho_thieu_an`, `gini_thu_nhap`,
  `gia_dat_tren_san_luong_ky_vong` (`metrics.py`).

**LÀM NGAY ĐƯỢC — read-only, không engine mutation, không world-hash change:**
- Metrics mục C trừ `poverty_duration`: `marketed_surplus`, `consumption_gini`, `yield_per_parcel`,
  `price_dispersion_by_asset` (qua đường D(1): thêm `lang` vào event `khop_cho`).
- Seasonal accounting-identity **view + test** (mục B) đọc flow đã có.

**PENDING — cần engine mutation + review độc lập:**
- `poverty_duration` (state đếm `w.poverty_streak`, engine-owned, migration §F, quyết định
  hash/không-hash theo charter §D) — engine-surgeon + reproducibility-steward.
- Đường D(2) `ghi_gia` khóa theo làng (phá hash, cần versioning + scenario-gate) — chỉ nếu D(1)
  không đủ.
- Pantry chung (nếu từng cần) = chủ thể ledger tường minh — ADR riêng.

## Handoff

- **implementation-engineer / engine-surgeon:** (a) thêm `lang` vào payload event `khop_cho`
  (`market.py:96`) — không đụng `Lenh`/`gia_lich_su`; (b) thêm view mục C trong `engine/economy.py`
  + surface qua `metrics.py:tinh_metrics` với sentinel undefined; (c) PENDING: `w.poverty_streak`
  engine-owned, cập nhật sau audit (`tick.py:227`), migration `nap_checkpoint`. Không policy nào
  ghi các field này.
- **test-engineer:** viết test matrix ở trên; ưu tiên property seasonal-identity + comparative
  statics paired-seed (mưa/màu-mỡ/transport) + replay-same-hash cho đường read-only. Không nới
  assertion, không hard-code seed.
- **qa-verifier / reality-auditor:** xác nhận không có magic price mới, metric không rẽ nhánh
  engine, undefined không bị thay bằng 0 giả; kiểm world-hash bất biến cho đường D(1); chặn mọi
  claim "giá thị trường" khi coverage dưới ngưỡng.
