# P1 — engine-surgeon: residence (P1.2) + estate (P1.3) theo ADR 0007

- Role: `engine-surgeon` (implementer). **Không tự đóng gate của mình.**
- Input: `docs/adr/0007-residence-household-estate.md` (Accepted),
  `docs/reviews/P1-household-demography-design.md`, `docs/reviews/Report_v2-ledger.md` (F-18/19/20/22/36).
- Verdict: **PASS WITH RISKS** — cơ chế xanh, gate cứng xanh, nhưng **hai finding blocking cho
  package kế** (F-P1-1 làm SAI một invariant của chính ADR; F-P1-2 làm `tach_ho` chưa có đường LLM).

---

## 1. Invariant — ba hash pin (TRƯỚC và SAU)

Lệnh (rulebot, 20 tick, không mạng): `.tmp/p1pins/pins.py`

```
--- TRƯỚC khi sửa ---
LEGACY_OFF seed=11 t=20 : 4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b  MATCH
LEGACY_OFF seed=42 t=20 : f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153  MATCH
SPATIAL_ON seed=11 t=20 : afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745  MATCH
ALL PINS OK

--- SAU khi sửa (toàn bộ P1.2 + P1.3) ---
LEGACY_OFF seed=11 t=20 : 4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b  MATCH
LEGACY_OFF seed=42 t=20 : f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153  MATCH
SPATIAL_ON seed=11 t=20 : afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745  MATCH
ALL PINS OK
```

Cơ chế giữ pin: `w.cu_tru`/`w.di_san` là field của **World** (KHÔNG phải `Agent` — F-22), và hai
khối `"residence"`/`"estate"` **chỉ được chèn vào `behavioral_state()` khi cờ BẬT**
(`engine/world.py:614-630`). Gate TẮT ⇒ blob JSON không đổi một byte. `hash_schema` giữ
`"behavioral-state-v2"`. Không thêm key `ho:` vào `config/world.yaml` ⇒ `cfg.digest()` base bất biến.

## 2. Nghiệm thu (output THẬT)

```
$ THOC_BLOCK_NETWORK=1 PYTHONIOENCODING=utf-8 PYTHONUTF8=1 conda run -n thoc-env \
    python -m pytest -q --basetemp .tmp/p1 -p no:cacheprovider
SKIPPED [1] tests\test_tools_check.py:29: thiếu run cnq2 (integration data)
584 passed, 1 skipped, 14 warnings in 260.72s (0:04:20)

$ ... python -m ruff check .
All checks passed!

$ ... python -m tools.verify_local
  PASS  ruff
  PASS  pytest
  PASS  scenario_validation
  PASS  smoke_run
  PASS  verify_research_run
KẾT QUẢ: XANH ✅
```

Baseline 553 passed + 1 skipped ⇒ **553 + 31 (test mới) = 584, 0 failed**. Không test cũ nào bị sửa.

## 3. File đã đổi

| File | Nội dung |
|---|---|
| `engine/household.py` (**MỚI**, 380 dòng) | `CuTru`; gate `_ho_bat/_cu_tru_bat/_cap_luong_thuc_bat/_tach_ho_bat` (khuôn `spatial.py:17-44`); `kiem_tra_cau_hinh` (fail-closed); `khoi_tao_cu_tru`; `buoc_cu_tru` (**single-writer**); `cap_va_an` (provisioning §B.4); `_kiem_invariant` (R1/R4 fail-loud) |
| `engine/estate.py` (**MỚI**, 400 dòng) | `DiSan`; `_di_san_bat`; `mo_di_san` (bậc 0); `buoc_di_san` (bậc 1–5); `bang_drain` + `kiem_e1_prime` (**E1′**); `yeu_cau_di_san` (claim) |
| `engine/world.py` | `_behavioral_config` chuẩn hóa khối `ho`; 6 field World mới; `ho_cua` nhánh ON; `behavioral_state` 2 khối có điều kiện; `nap_checkpoint` migration; `tao_the_gioi` gọi `kiem_tra_cau_hinh` + `khoi_tao_cu_tru` |
| `engine/consumption.py:32-100` | provisioning: `chuyen(người-cấp → người-ăn)` + event `cap_luong_thuc` TRƯỚC `huy(..., "an")` |
| `engine/tick.py:246-258` | chèn **9b** (`household.buoc_cu_tru`) + **9c** (`estate.buoc_di_san`) sau `cuu_mang_mo_coi`, TRƯỚC audit. `_di_cu` khai báo biến cố. `poverty_streak` re-key theo `rid` |
| `engine/demography.py` | `buoc_nhan_khau`: estate ON ⇒ `mo_di_san` thay `thua_ke_mac_dinh`; `cuoi`/`sinh` khai báo biến cố |
| `engine/contracts.py:216-227, 425-460` | `xiet_the_chap(..., chu_dat=None)` (mặc định = legacy); `_chan_no_chet_theo_con_no` **fail-loud** khi estate ON |
| `engine/audit.py:36-46` | nhánh **gated** E1′ trong `kiem_toan_the_gioi` |
| `engine/board.py:30-39` | ghost offer: `den` không hoạt động ⇒ từ chối |
| `engine/economy.py:63-90` | `household_snapshot` mang thêm `rid` khi ON |
| `engine/xa_hoi.py:156-160` | `cuu_mang` khai báo biến cố |
| `engine/intents.py:80-95` | **CỐ Ý KHÔNG thêm field** — xem F-P1-2 |
| `scenarios/agrarian_transition_v1/spatial_livelihood_v2.yaml` (**MỚI**) | overlay `ho:` (BẬT). `spatial_v1.yaml` KHÔNG bị sửa |
| `scenarios/agrarian_transition_v1/provenance.csv` | 4 dòng mới (`che_do` = `institutional_assumption`) |
| `tests/test_household_estate.py` (**MỚI**, 31 test) | test của implementer |

**KHÔNG đụng:** `Agent` dataclass · `audit.py` land check · thứ tự bước tick · `hash_schema` ·
`config/world.yaml` · `spatial_v1.yaml` · `minds/capabilities.py` · `minds/prompts.py` · `tests/**` cũ ·
`data/runs/**` · `reports/**`.

## 4. Accounting identity

- **Bậc 0:** `∀ts: chuyen(aid → DI_SAN:aid, ts, so_du(aid,ts))` ⇒ `so_du(người chết) = 0` NGAY tick chết.
  Đất **không** vào estate (`audit` cấm chủ không hoạt động) ⇒ đi thẳng sang heir hoặc về công cùng tick.
- **Bậc 1:** `phan(nid, ts) = sl(ts) × no(nid) / max(Σno, giá_trị_estate)`.
  Mẫu số `max(...)` là **sửa lỗi so với khuôn `entities.thanh_ly`** (`entities.py:254` dùng `tong_no`
  vô điều kiện ⇒ một chủ nợ duy nhất nuốt 100% tài sản dù nợ nhỏ hơn nhiều). Thiếu ⇒ `khong_thu_du`,
  mất THẬT, không mint bù, không nợ truyền đời.
- **Bậc 4 `chia_deu_lang`:** chia lẻ pro-rata (người cuối nhận phần dư ⇒ estate về **đúng 0**); nguyên
  chiếc round-robin; `co_phan:*` → sink `giai_the` (đã đăng ký); `vi_the:*` → sink `het_hd`.
- **`tan_ra`:** sink `(ts, "tan_ra")` **đăng ký lazy** khi dùng (đăng ký vô điều kiện sẽ đổi
  `flow_sinks` ⇒ đổi hash legacy).
- **E1′:** `∀tick, ∀(S,ts) với so_du(S,ts)>0 và not chu_the_hoat_dong(S)`: **hoặc** S là estate đang
  mở còn hạn, **hoặc** `ts ∈ drain(S)` với drain ĐANG BẬT. Bảng `estate.bang_drain`:
  `VO_THUA_NHAN → ∅` (không drain nào, đây là sự thật), `CONG_QUY → {thoc}` chỉ khi `chinh_tri.bat`
  (+`{go,cong}` khi `fiscal.bat`). **Người chết còn số dư ⇒ FAIL.** Chạy trong `kiem_toan_the_gioi`.

## 5. Migration policy

- `nap_checkpoint`: `cu_tru/_next_cu_tru/bien_co_ho/di_san/di_san_xong/_next_di_san` thiếu ⇒ default
  rỗng; `_cu_tru_idx` (chỉ mục derived, ngoài hash) dựng lại. Checkpoint cũ (OFF) ⇒ dict rỗng ⇒ key
  `"residence"`/`"estate"` **vẫn không xuất hiện** ⇒ `world_hash` y nguyên (`test_migration_checkpoint_cu_khong_gay`).
- Gate hộ là **thuộc tính của run** (`run.py` đã chặn resume khác config digest).
  `test_on_deterministic_va_replay_checkpoint`: resume từ checkpoint ON == run liền mạch (cùng hash).
- Rollback: `ho.bat: false` ⇒ mọi path no-op ⇒ hash + hành vi về đúng legacy. Không mất state.

---

## 6. Findings

### F-P1-1 (**BLOCKING cho spec-governor**) — INVARIANT P-1 của ADR 0007 §B.3 **SAI Ở MỨC BIT**

ADR §B.3 tuyên bố: *"Bật RIÊNG `ho.cap_luong_thuc` ⇒ `world_hash()` TRÙNG HỆT run OFF"*, và §G.4 dùng
nó làm **trục kiểm tra chính test harness** trong ablation 2×2×2.

**Chứng minh của ADR đúng ở MỨC GIÁ TRỊ nhưng SAI ở mức BIT.** `world_hash` băm `float.hex()` (chính
xác tuyệt đối); cộng dồn IEEE-754 **không kết hợp**. Legacy áp **MỘT** delta `-tru` cho người có kho
(`consumption.py` cũ: `huy(m, ts, tru, "an")`); provisioning áp `-x₁, -x₂, …` (mỗi người ăn một bút
toán) ⇒ `(bal − x₁) − x₂ ≠ bal − (x₁ + x₂)`.

Đo được (base, rulebot, seed 11, **tick 4**):

```
LỆCH ĐẦU TIÊN tại tick 4
  ('A0042','thoc'): OFF=977.4906109560651  PROV=977.4906109560652  delta=1.1368683772161603e-13
  số (chủ thể,tài sản) khác BIT: 1
  flow_totals khác BIT: 0
  agent khác health/con_song: 0        dân số OFF=54 PROV=54
```

Đây **không phải bug cài đặt mà là bất khả thi cấu trúc**: để `so_du(m)` bằng nhau từng bit, `m` phải
xuất hiện **đúng một lần** trong `Ledger.ap_dung.thay_doi`; nhưng một người vừa **nuôi người khác** vừa
**tự ăn** từ cùng một lần rút thì **buộc** phải có ≥2 dòng. Không có cách viết provisioning trung thực
nào tránh được, trừ khi đổi `Ledger` (sẽ đổi hash legacy).

**Xử lý (fail-closed, KHÔNG che):** `_behavioral_config` **GIỮ** `cap_luong_thuc` trong behavioral
config (`engine/world.py:107-130`). Cờ này **có** đổi quỹ đạo số học ⇒ nó **thuộc** transition
function ⇒ để nó ngoài hash sẽ tạo **false-equivalence cho replay** (hai quỹ đạo khác nhau chia chung
một config identity). Thà nhận một finding còn hơn một cổng replay nói dối.

**Hệ quả phải sửa ở tài liệu (owner: `spec-governor` + `research-planner`):**
1. ADR 0007 §B.3 INVARIANT P-1 phải hạ xuống: *"provisioning là bookkeeping-only về **GIÁ TRỊ**
   (|Δsố dư| ≤ 1e-9, flow totals bằng nhau, dân số/health y hệt) — **không** bit-exact."*
2. ADR §G.4: trục `ho.cap_luong_thuc` **KHÔNG dùng được** làm harness check. Giữ nó **CỐ ĐỊNH (ON)**
   qua mọi ô của ma trận ablation, nếu không mọi so sánh sẽ nhiễu 1-ULP.
3. Test T-14 (`test_cap_luong_thuc_la_hash_neutral`) trong hợp đồng test của memo §6 **sẽ FAIL như đã
   viết** — `test-engineer` phải viết nó theo dạng giá-trị, không dạng bit.

Test hiện hành: `tests/test_household_estate.py::test_provisioning_hash_neutral` khẳng định điều ĐÚNG
(value-level identity, |Δ| ≤ 1e-9, cùng flow totals, cùng dân số/health) và **FAIL LOUD** nếu lệch bao
giờ vượt 1e-9 (tức là provisioning đã đổi HÀNH VI thật).

### F-P1-2 (**BLOCKING cho `minds-engineer`**) — `tach_ho` / `yeu_cau_di_san` chưa có đường LLM

ADR §H giao cho `engine-surgeon` cả `minds/capabilities.py`; brief của package này **CẤM ĐỤNG**
`minds/capabilities.py` + `minds/prompts.py` (P0.1 đóng băng `catalog_hash`/`prompt_template_hash`).
Hai chỉ thị mâu thuẫn. Đã chọn phía **fail-closed**:

- **KHÔNG** thêm field `tach_ho`/`yeu_cau_di_san` vào `KeHoach`. Thêm field mà không có descriptor sẽ
  tái tạo **đúng defect F-02** (engine nhận một intent mà không policy nào phát ra được ⇒ mọi kết luận
  *"agent không tách hộ"* là **interface-confounded**) — và `tests/test_capability_parity.py::
  test_cap2_khong_co_field_kehoach_mo_coi` **đã bắt đúng việc đó** khi tôi thử (đỏ ⇒ đã revert).
- Engine đọc bằng `getattr(kh, "tach_ho", False)` / `getattr(kh, "yeu_cau_di_san", ())` ⇒ **cơ chế đã
  SẴN SÀNG**, bật ngay khi field xuất hiện, **không cần sửa engine**.

⇒ **Hiện trạng: `ho.tach_ho.bat: true` là cơ chế sẵn sàng nhưng POLICY CHƯA VỚI TỚI.** Không được diễn
giải bất kỳ kết quả nào về "hộ không tách" cho tới khi `minds-engineer` ship descriptor (một package
riêng, bump `catalog_hash`, qua cổng P0).

### F-P1-3 (medium, đã sửa trong package này) — legacy có **nợ truyền đời NGẦM**, không chỉ "nợ chết theo con nợ"

Đọc code (`demography.py:280-288` + `contracts.py:337-342`): `thua_ke_mac_dinh` chuyển token
`vi_the:<hd>:<A>` cho heir **như một tài sản rời** ⇒ `ben_hien_tai(hd, A)` = heir (còn sống) ⇒
`_ben_mat` False ⇒ **hợp đồng KHÔNG bị hủy mà TIẾP TỤC**. Nghĩa vụ lặng lẽ nhảy sang một đứa trẻ.
Tức là legacy có **HAI** hành vi, không phải một:

| Tình huống | Legacy | Hệ quả |
|---|---|---|
| Con nợ chết, **CÓ** heir | vị thế → heir; hợp đồng sống tiếp | **nợ truyền đời ngầm** (định chế chưa ai khai báo) |
| Con nợ chết, **KHÔNG** heir | vị thế → `VO_THUA_NHAN`; `_ben_mat` ⇒ `huy` + `dot_vi_the` | **F-20 đúng nghĩa**: nợ bốc hơi, chủ nợ mất trắng, tài sản kẹt (F-19) |

Report_v2/ADR chỉ mô tả vế thứ hai. Cả hai đều được tái hiện trong test
(`test_no_settle_tu_estate_truoc_heir[None-False]`, `test_f20_no_chet_theo_con_no_khi_khong_heir[None-False]`)
và cả hai đều bị estate ON sửa (ADR §D.8: **KHÔNG** cho nợ sống tiếp sang heir).

### F-P1-4 (medium, đã sửa) — `entities.thanh_ly` over-pay chủ nợ

`entities.py:254` `phan = sl * (no / tong_no)` ⇒ **một chủ nợ duy nhất nhận 100% tài sản entity dù nợ
nhỏ hơn nhiều**. `estate._bac1_chu_no` **KHÔNG** lặp lại lỗi này (mẫu số `max(tong_no, giá_trị_estate)`).
**`entities.thanh_ly` vẫn còn lỗi** — ngoài scope P1, owner: `engine-surgeon` package sau.

### F-P1-5 (low, đã sửa trong household) — cưới/di cư có thể bỏ rơi trẻ

Luật §C.3 ("mang theo người phụ thuộc mà mình là cha/mẹ/giám hộ **duy nhất còn sống**") để lọt một
lỗ: khi hộ nguồn TAN vì người lớn cuối cùng đi cưới/di cư, trẻ có **cả hai** cha mẹ còn sống (một
người ở hộ khác) sẽ **không đi theo ai** ⇒ ở lại một mình ⇒ đói. Đó là **tái tạo orphaning, chỉ đổi
nguyên nhân từ "tuổi" sang "cha mẹ đi cưới"**. Đã thêm luật KHÔNG-BỎ-RƠI trong
`household._mang_theo_khi_roi_ho`: hộ nguồn không còn người lớn nào ⇒ cả nhà đi theo. `tach_ho` thì
ngược lại — **TỪ CHỐI** (`no_adult_left`), vì tách hộ là lựa chọn còn cưới/di cư là hộ đang tan.

### F-P1-6 (OPEN, ngoài P1) — chưa có `engine/metrics_demography.py`

ADR §F giao module metrics nhân khẩu (Lớp-5, ngoài hash). **Chưa làm** — giữ diff auditable, và nó
không thuộc gate P1 (§G.3). INV-M1 hiện **không bị vi phạm** (grep `life_expectancy|tuoi_tho`: 0 match).
Owner package sau. `cu_tru.thoi_gian_ngheo` đã có nền: `poverty_streak` đã re-key theo `rid`.

### F-P1-7 (OPEN, ADR đã ghi) — blueprint mồ côi

`demography.py:296-300` giữ tên người chết ⇒ ghost-owner. ADR §D.3 khai là PENDING. **Chưa sửa.**
Estate **không** dọn nó ⇒ §D chưa dọn sạch mọi ghost.

---

## 7. Claim boundary (bắt buộc)

- Sửa xong P1 **KHÔNG** làm kết quả cũ đúng lên. Mọi số mortality/welfare từ `real60_spatial` vẫn
  **vô hiệu** (4 confound độc lập); artifact giữ nhãn `diagnostic_only_unreplayable`.
- P1 chỉ mua **`technical-ready`**. `mechanism-ready` cần ablation §G.4 (chưa chạy) + baseline
  rulebot/mock cùng seed + artifact replay được.
- **Thừa kế KHÔNG phải "tự phát".** `ho.di_san.che_do` là **`institutional_assumption` /
  `experimental_treatment`** (ADR §E.2: trượt điều kiện #2 của cổng charter §5 — chi phí = 0). Cấm mọi
  phát biểu "thừa kế nổi lên nội sinh trong THÓC". Đã ghi vào `provenance.csv` với status
  `institutional_assumption`.
- `claim_han_tick = 3` là `design_assumption`, **không có provenance**.
- Cơ chế `tach_ho` **chưa có đường LLM** (F-P1-2) ⇒ không kết luận gì về hành vi tách hộ.

## 8. Next handoff

| Agent | Việc |
|---|---|
| `spec-governor` | **F-P1-1**: sửa ADR 0007 §B.3 (P-1 → value-level) + §G.4 (bỏ trục provisioning khỏi ablation). Ghi ADR/decision, không sửa im lặng. |
| `test-engineer` | T-01…T-43 + T-16…T-19 **độc lập**. Lưu ý T-14 phải viết dạng giá-trị (F-P1-1). Thêm negative test cho `_mang_theo_khi_roi_ho` (F-P1-5). |
| `minds-engineer` | **F-P1-2**: descriptor `tach_ho` + `yeu_cau_di_san` (CAP-1 bốn chân, `kha_dung(w)` theo gate, CAP-4 anti-teleology) + field `KeHoach`. Bump `catalog_hash` ⇒ qua cổng P0. |
| `reproducibility-steward` | Xác minh 3 pin độc lập; resume ON == liền mạch; migration checkpoint cũ. |
| `adversarial-reviewer` | Soi đúng 4 chỗ ADR §H liệt: (a) `audit.py` land check có bị nới không (**không** — `test_estate_khong_bao_gio_dung_ten_dat`); (b) `life_expectancy` từ người sống (**không có**); (c) sink đổi tên (**E1′** + `test_het_han_cong_fail_closed`); (d) test bị nới để pin xanh (**không** — pin verify TRƯỚC/SAU bằng script ngoài pytest). |
| `agrarian-economist` + `sim-economist` | Pre-register dấu ablation §G.4 **trước** khi chạy. |
