# ADR 0004 — Credit as counterpart claims, competing commodity money, fiscal capacity (T06+T07+T08)

- Status: **Proposed** (2026-07-12)
- Context: `docs/MODEL_CHARTER.md` §3 (Lớp-2 kế toán sổ kép/không số dư âm, Lớp-3 định chế
  bật/tắt, Lớp-5 chỉ đọc), §4 (định nghĩa tự phát), §5 (cổng định chế + anti-teleology);
  `docs/adr/0001-scope-and-institutional-layers.md` §A (invariant), §B (cổng 5 điều kiện),
  §C (anti-teleology: Gini không tự sung công), §D (determinism), §G; `TASKS.md` T06, T07, T08.
- Deciders: monetary-fiscal-economist + model-architect (design). Implementation & independent
  test/QA sign-off PENDING (xem Handoff).
- Scope guard: **không** implement engine. Chốt data model, accounting identity, state ownership,
  test matrix, và phân định **IMPLEMENTED vs PENDING**. Mọi số là `design_assumption` (charter §2);
  không mục nào ở đây là bằng chứng thực chứng.

## Context — sự thật nền đã khảo sát (file:line)

### Tín dụng (T06) — KHÔNG có registry, chỉ là tổ hợp clause
- **Không có object `Claim`/loan registry.** Vay = TỔ HỢP clause của `HopDong`: giải ngân
  `chuyen_giao_mot_lan` (`contracts.py:25`) + thế chấp `HopDong.the_chap: list[str]`
  (`contracts.py:97`, dạng `"thoc:200"`, `"thua:P01_02"`) + `khi_pha_vo` với
  `phat="xiet_the_chap"` (`contracts.py:77-79`) + rút linh hoạt `hoan_tra_theo_yeu_cau`
  (`contracts.py:69`) + kích hoạt `dieu_kien_su_kien` `neu.loai=vo_no` (`contracts.py:63-66`).
- Cưỡng chế: `xiet_the_chap` (`contracts.py:216`) chuyển tài sản thế chấp con nợ→chủ nợ khi phá vỡ.
- `engine/ledger.py:142-148` **cấm số dư âm** — nợ KHÔNG bao giờ là số âm, luôn là **nghĩa vụ hợp
  đồng** ở Lớp-3 (đúng invariant #2, charter Lớp-2).
- "Ngân hàng" chỉ là **nhãn observatory** (Lớp-5). **CHƯA có** bảng cân đối chủ nợ–con nợ, **CHƯA
  có** metric debt-service / outstanding / concentration.

### Tiền (T07) — commodity money, agent chọn phương tiện
- `xu` đúc qua recipe sản xuất (flow `duc_xu`, `metrics.py:38`); agent CHỌN `Lenh.thanh_toan`
  ∈ {thoc, xu} (`market.py:24`). **Engine KHÔNG ép xu** (docstring `market.py:3-5`).
- `engine/metrics.py:77` `velocity_tien` = P·Q / M với M=`ledger.tong_tai_san("xu")`; M≈0 ⇒
  velocity=0 (quy ước "chưa tiền tệ hóa"). `kl_thanh_toan_tick` (`market.py:106`) tích lũy **giá
  trị khớp theo phương tiện thanh toán** (quy thóc); reset mỗi tick (`tick.py:120`), cửa sổ 4 tick
  `kl_thanh_toan_4` (`tick.py:260-262`). Nhãn `tien_te_hoa` (≥50% giá trị khớp bằng xu) ở
  observatory.
- **CHƯA có:** monetary_share theo tồn kho, acceptance_breadth, payment_concentration, barter/credit
  share, failed_settlement.

### Tài khóa (T08) — conduit rebate, không treasury, không public goods
- `CONG_QUY` (`world.py:21`) là **chủ thể ledger** (conduit). `thu_thue_va_chia`
  (`politics.py:182`) thu thuế = `thue_suat × sản lượng gặt` → `CONG_QUY` rồi **CHIA NGAY** đều đầu
  người lớn (`_chia_deu` `politics.py:215`). ⇒ **rebate, KHÔNG tích lũy treasury, KHÔNG public
  goods, KHÔNG chi tiêu công.** Mọi bước là `ledger.chuyen` cân ⇒ bảo toàn tự xanh.
- `chinh_tri.bat` flag: `_chinh_tri_bat(w)` gate `thu_thue_va_chia` (`politics.py:185`) và tầng
  chính trị — TẮT cho `agrarian_transition_v1` (ADR 0001 §C).
- `buoc_bao_dong` (`politics.py:229`) Gini-gated riot: sung công qua ledger, giữ replay cho legacy,
  **default OFF** ở scenario mới (ADR 0001 §C — Gini KHÔNG được là nguyên nhân duy nhất).
- **CHƯA có:** treasury balance sheet, public goods (đường/thủy lợi) + depreciation, chi tiêu công.

## Decision

### T06 — Credit: CLAIMS VIEW read-only trước, registry object PENDING

**Nguyên tắc:** `HopDong` (contract grammar) là **single source of truth**; nợ đã là nghĩa vụ hợp
đồng, không phải số âm. Vì vậy trước khi thêm object mới, ta **tái dựng** dư nợ từ clause đang hiệu
lực — không tạo state trùng lặp, không rủi ro world-hash.

**A. CLAIMS VIEW (làm ngay, read-only, Lớp-5):**
`observatory` (hoặc `engine/economy.py` view thuần) đọc `w.hop_dong` (`trang_thai=="hieu_luc"`) +
`w.hop_dong_xong` + event journal, phân loại clause thành **quan hệ chủ nợ→con nợ** và tính:

```
Claim(view) = {
  hop_dong_id, creditor, debtor, unit(tai_san),
  principal      = Σ chuyen_giao_mot_lan (giải ngân, tai="ky_ket")
  scheduled_out  = Σ chuyen_giao_dinh_ky còn lại đến thoi_han  (nghĩa vụ tương lai)
  collateral     = HopDong.the_chap  (list "unit:qty")
  trigger        = dieu_kien_su_kien.neu (vo_no|han_lu|gia|chet)
  breach_penalty = khi_pha_vo.phat (xiet_the_chap|phat_chuyen_giao|khong)
}
```

Metric surface (thuần đọc): `debt_service` (nghĩa vụ chuyển giao định kỳ tick này), `outstanding`
(tổng nghĩa vụ tương lai còn lại), `claims_concentration` (Herfindahl theo creditor),
`secured_vs_unsecured` (có/không `the_chap`), `arrears`/`default` (đếm event `xiet`/`vi_pham`).

**B. INVARIANT (test-enforced):**
- **Đối xứng claim:** với mỗi clause chuyển giao trong hợp đồng hiệu lực, "tài sản đòi nợ của
  creditor theo (unit, qty)" = "nghĩa vụ của debtor theo (unit, qty)" — reconstruct từ cùng một
  clause ⇒ đối xứng theo cấu trúc (test khẳng định không có claim mồ côi/không counterpart).
- **Không số dư âm** (đã có `ledger.py:142`): settlement rút từ số dư ≥ 0; thiếu ⇒ `LoiSoKep` ⇒
  xiết thế chấp hoặc vi phạm, KHÔNG âm sổ.
- **Mọi settlement có event + ledger counterpart:** giải ngân/trả/ xiết đều qua `ledger.chuyen`/
  `xiet_the_chap` + event (`xiet` `contracts.py:246`).

**C. Registry object — PENDING (cần engine mutation + review):**
Nếu view không đủ (vd cần seniority, restructuring, transfer nợ, resolution-on-death một cách
chuẩn hóa), spec object `Claim` (TASKS T06 gạch 1) để engine-surgeon cài SAU:
`id, creditor, debtor, unit, principal, outstanding, rate/condition, maturity, collateral,
seniority, repayment_schedule, default_state, restructuring, transfer, resolution_on_exit`.
Ràng buộc bắt buộc nếu cài:
- Một nguồn sự thật (không nhân đôi state với contract grammar) — hoặc registry **là** projection
  của contract, hoặc contract clause tín dụng migrate **vào** registry với migration versioned.
- Vào `world_hash`/checkpoint (charter §D) vì ảnh hưởng hành vi (con nợ quyết định theo dư nợ).
- Cổng định chế §5 charter: alternative (barter/tín-dụng-quan-hệ), cost (soạn hợp đồng), accounting
  identity (đối xứng creditor–debtor), scenario flag (bật cho `agrarian_transition_v1`), ablation
  (credit disabled vs enabled — TASKS T06 gạch 5). **KHÔNG predeclare rằng credit tăng welfare.**
- Legacy: hợp đồng định kỳ cũ **không tự động** thành loan; chỉ expose migration cho scenario mới
  (TASKS T06 gạch 3); `preindustrial_closed_v1` replay y nguyên.

### T07 — Money: metric adoption trước, cấm ép xu

**A. Giữ xu là candidate instrument.** Agent/policy chọn payment asset theo holdings khả thi + tập
được-chấp-nhận cục bộ + chi phí giao dịch + thông tin giới hạn (charter Lớp-4). Engine tuyệt đối
không ép xu (giữ đúng `market.py:3-5`). Barter (thanh toán bằng thoc) và credit settlement (clause)
là alternative luôn khả thi.

**B. Metrics adoption cần THÊM (làm ngay, read-only):** định nghĩa TRƯỚC run (TASKS T07 gạch 4),
đọc `kl_thanh_toan_tick`/`kl_thanh_toan_4`/`ledger`/`events`:

| Metric | Định nghĩa | undefined khi |
|---|---|---|
| `monetary_share_by_value` | Σ giá trị khớp bằng xu / Σ giá trị khớp mọi phương tiện (từ `kl_thanh_toan`) | tổng khớp = 0 |
| `monetary_share_by_stock` | `ledger.tong_tai_san("xu")` quy thóc / tổng tài sản thanh khoản | không có giá xu |
| `acceptance_breadth` | # agent phân biệt đã **bán và nhận xu** ≥1 lần / # agent giao dịch | 0 giao dịch |
| `payment_concentration` | Herfindahl khối lượng xu theo người nhận | <2 người nhận |
| `barter_share` / `credit_share` | tỷ trọng giá trị thanh toán bằng thoc-chợ vs qua clause hợp đồng | tổng = 0 |
| `failed_settlement` | # lần `LoiSoKep` bị nuốt ở khớp chợ (`market.py:116`) — cần đếm (mục C) | — |

**Velocity chỉ báo khi mẫu số/coverage có nghĩa** (M>ε và có khớp) — giữ quy ước `velocity=0` khi
M≈0 nhưng **gắn cờ coverage**, không diễn giải P×Q/M khi price coverage thưa (TASKS T07 gạch 4).

**C. failed_settlement — PENDING nhỏ (engine mutation):** hiện `LoiSoKep` bị nuốt im lặng
(`market.py:116-117`). Để đo, thêm **bộ đếm read-observation** `w.settlement_fail_tick` tăng tại
điểm nuốt + reset mỗi tick (như `kl_thanh_toan_tick` `tick.py:120`). Không đổi hành vi khớp; là
observation state (không vào hash nếu engine không đọc lại — charter §D; reconstruct từ metric
journal). Engine-surgeon + review.

### T08 — Fiscal: tách governance khỏi capacity; treasury + public goods PENDING

**A. Tách "governance procedure" khỏi "fiscal capacity"** (TASKS T08 gạch 4): election/consensus/
coercion/legitimacy là **institutional modes cấu hình** (đã có tầng chính trị, gate `chinh_tri.bat`);
fiscal capacity (thu/giữ/chi) là năng lực đo được, độc lập. **Gini KHÔNG trực tiếp sung công** —
đã gate OFF ở `agrarian_transition_v1` (ADR 0001 §C); riot là treatment có action/participation/
cost/legal-path.

**B. Metric read-only làm NGAY:** `tax_revenue` (Σ thóc vào `CONG_QUY` qua event `thue`
`politics.py:211`), `fiscal_balance` = thu − chi. **Hiện `fiscal_balance = 0`** vì rebate chia hết
ngay (không giữ số dư); báo đúng 0, không ngụy tạo thặng dư.

**C. Treasury balance sheet + public goods — PENDING (engine mutation lớn, cần cổng §5):**
Spec accounting identity **đóng** mỗi tick, mỗi flow có counterpart (TASKS T08 gạch 2):

```
assets_end   = assets_start
             + taxes            [chuyen agent→CONG_QUY, có counterpart]
             + borrowing        [claim: CONG_QUY là debtor, có creditor]
             + issuance         [mint qua FlowRegistry nguồn đã đăng ký]
             - spending         [chuyen CONG_QUY→nhà cung cấp/lao động]
             - debt_service     [chuyen CONG_QUY→creditor]
             - depreciation     [burn qua FlowRegistry sink; public good hao mòn]
```

Public goods (tập nhỏ, vật chất, có depreciation — TASKS T08 gạch 3): vd `thuy_loi`/`duong_cho`,
mỗi good có input/cost/maintenance/benefit đo được; benefit đi vào Lớp-1 (vd tăng `mau_mo` hiệu
dụng hoặc giảm transport cost) qua flow tường minh, KHÔNG phải bonus miễn phí. Depreciation là sink
đăng ký. Treasury là chủ thể ledger (mở rộng `CONG_QUY` từ conduit thành **stock có số dư**) ⇒
**thay đổi behavior + hash** ⇒ cần:
- Cổng định chế §5: alternative (đóng góp tự nguyện vs thuế — TASKS T08 gạch 5), cost (thu/giữ tốn
  lao động), accounting identity (công thức trên), scenario flag, ablation (public-good available/
  unavailable; low/high enforcement; benefit removed = placebo).
- Vào `world_hash`/checkpoint (treasury balance, public-good stock, depreciation state).
- Không tạo "public wealth" phantom (TASKS T08 gạch 6) — mọi đơn vị công có nguồn + counterpart.

### Determinism, ordering, failure/rollback (chung T06–T08)

- **Thứ tự tick liên quan** (đã có): chính quyền `tick.py:114` → sản xuất → thuế `:125` → chợ
  `:187-188` → thi hành hợp đồng (clause định kỳ/đáo hạn/vi phạm/cưỡng chế) `:191` → entity chia
  lãi/phá sản `:195-196` → tiêu dùng `:203` → nhân khẩu `:211` → bạo động `:226` → audit `:227`.
  Metric T06/T07/T08 đọc **SAU audit** (`tick.py:229`).
- **Deterministic ordering:** mọi settlement/registry lặp `sorted(...)` theo id (đã có:
  `thu_thue_va_chia` `sorted(w.gat_tick)`, `xiet_the_chap`). Registry/claims view phải sort theo
  `hop_dong_id`.
- **Failure/rollback:** thiếu tài sản khi settle ⇒ `LoiSoKep`, không âm sổ; xiết thế chấp hoặc ghi
  vi phạm. Metric read-only không raise; undefined ⇒ sentinel, không 0 giả.
- **FlowRegistry/ledger entries:** view T06/T07 + metric T08 hiện tại **không tạo bút toán mới**.
  Mọi mục PENDING tạo flow (issuance, depreciation, borrowing) **phải** đăng ký nguồn/sink và có
  counterpart (ledger #1/#2); mint/burn qua `DongSinhHuy` gắn `luong` đã đăng ký (`ledger.py:55`).

## Migration path — không phá run/checkpoint cũ

- Claims view (T06 A), money metrics (T07 B), `tax_revenue`/`fiscal_balance` (T08 B): **read-only,
  không đổi world-hash, không đổi checkpoint schema** ⇒ run/checkpoint cũ replay y nguyên; key
  metric mới chỉ trong run mới.
- `w.settlement_fail_tick` (T07 C): observation state, default `getattr(...,0)` khi nap checkpoint
  cũ; không vào hash.
- Registry object (T06 C), treasury/public-goods (T08 C): **đổi hash/behavior** ⇒ scenario-gate cho
  `agrarian_transition_v1` + bump artifact version; `nap_checkpoint` (`world.py:371`) thêm default
  cho field mới (theo pattern `mau_mo_goc` `world.py:381`); **không** đổi hash của
  `preindustrial_closed_v1`.

## Test matrix

**Unit (thế giới nhỏ):**
- Claims view tái dựng đúng creditor/debtor/unit/collateral từ một hợp đồng vay mẫu.
- money metric: hai instrument (thoc+xu) ⇒ share cộng lại = 1; 0 giao dịch ⇒ undefined.
- `tax_revenue` khớp Σ event `thue`; `fiscal_balance`==0 khi rebate.

**Property / invariant (hypothesis):**
- Đối xứng claim: Σ tài sản-đòi-nợ creditor == Σ nghĩa-vụ debtor theo (unit) mỗi tick.
- Không số dư âm sau mọi settlement (dùng audit + ledger có sẵn).
- monetary_share ∈ [0,1]; acceptance_breadth ∈ [0,1].

**Integration / comparative (paired-seed):**
- Credit ablation: credit disabled vs enabled — báo phân phối outcome; **không** assert enabled tốt
  hơn (TASKS T06 gạch 5).
- Money: absence (không instrument) / competition (hai instrument) / supply-shock (đúc thêm xu) /
  unaccepted-asset (asset không ai nhận). Adoption ĐƯỢC PHÉP thất bại; không test nào assert đạt %
  định trước (TASKS T07 gạch 5).
- Fiscal (khi treasury/public-good có): available/unavailable, low/high enforcement, voluntary vs
  tax, placebo (benefit removed). Báo compliance/exit/public-return/fiscal-balance/failure-mode.

**Replay:** run có metric mới read-only replay ra **cùng world_hash** như run không có (chứng minh
không đụng determinism).

**Negative:**
- Loan default với collateral không đủ ⇒ xiết phần có, phần còn lại ghi vi phạm, KHÔNG âm sổ.
- Death/entity-exit của con nợ/chủ nợ: claim resolution không tạo/mất tài sản (audit).
- Tax khi 0 người lớn ⇒ thóc ở lại `CONG_QUY`, bảo toàn xanh (`politics.py:208`) — regression.
- Fiscal PENDING: no phantom public wealth — mọi đơn vị công có nguồn + counterpart; policy KHÔNG
  mutate treasury trực tiếp.

## IMPLEMENTED vs PENDING

**IMPLEMENTED (đã có; ADR chỉ chốt/đặt tên):**
- T06: nợ = tổ hợp clause (`contracts.py`), thế chấp + xiết (`xiet_the_chap`), ledger cấm âm.
- T07: xu là commodity money đúc qua recipe; agent chọn `thanh_toan`; `velocity_tien` +
  `kl_thanh_toan` + nhãn `tien_te_hoa`.
- T08: `CONG_QUY` conduit; `thu_thue_va_chia` (rebate); `chinh_tri.bat` gate; `buoc_bao_dong` gated.

**LÀM NGAY ĐƯỢC — read-only, không engine mutation, không world-hash change:**
- T06: **CLAIMS VIEW** + metrics `debt_service`/`outstanding`/`claims_concentration`/
  `secured_vs_unsecured`/`arrears` (đọc `hop_dong`/`hop_dong_xong`/events).
- T07: `monetary_share_by_value`/`by_stock`, `acceptance_breadth`, `payment_concentration`,
  `barter_share`/`credit_share` (đọc `kl_thanh_toan_*`/`ledger`).
- T08: `tax_revenue`, `fiscal_balance` (=0 hiện tại, báo trung thực).

**PENDING — cần engine mutation + review độc lập:**
- T06: registry object `Claim` (seniority/restructuring/transfer/resolution) — vào hash, cổng §5,
  ablation — engine-surgeon + monetary-fiscal-economist + adversarial-reviewer.
- T07: bộ đếm `failed_settlement` (`w.settlement_fail_tick`, observation state) — engine-surgeon +
  reproducibility-steward.
- T08: treasury balance sheet (CONG_QUY thành stock) + public goods + depreciation + chi tiêu công,
  identity đóng, cổng §5, vào hash — engine-surgeon + spec-governor + qa-verifier.

## Handoff

- **implementation-engineer / engine-surgeon:** (a) claims view + T06/T07/T08 metrics read-only
  trong `engine/economy.py`/observatory + surface qua `metrics.py:tinh_metrics`; (b) PENDING:
  `w.settlement_fail_tick` (đếm tại `market.py:116`, reset `tick.py:120`); (c) PENDING lớn: `Claim`
  registry và treasury/public-goods **chỉ sau** memo monetary-fiscal-economist + cổng định chế §5
  đầy đủ + review. Policy/LLM không được ghi các field này.
- **test-engineer:** viết test matrix ở trên; ưu tiên property đối-xứng-claim + no-negative-balance
  + money-share∈[0,1] + credit/money ablation paired-seed (không predeclare winner) + replay-same-
  hash cho read-only. Không nới assertion, không hard-code % adoption.
- **qa-verifier / reality-auditor / spec-governor:** xác nhận Gini không tự sung công ở scenario
  mới; không có engine ép xu; claim view không rẽ nhánh engine; mọi mục PENDING đi qua cổng §5
  (alternative/cost/identity/scenario-flag/ablation) trước khi vào engine; không phantom public
  wealth; world-hash bất biến cho đường read-only.
