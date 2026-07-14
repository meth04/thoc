# P0 — Artifact integrity audit + truy nhiễm bẩn (F-13)

Tác giả: `research-artifact-integrity-auditor` (chỉ đọc). Ngày: 2026-07-13.
Gate độc lập đề nghị: `adversarial-reviewer`, `qa-verifier`.

**Verdict: `INVALID FOR RESEARCH` cho `real60_spatial`** (giữ nguyên `diagnostic_only_unreplayable`)
· **`VERIFIED` (phạm vi seed-replay) cho `mock60_spatial`** · **F-13 = CÓ NHIỄM BẨN, khoanh vùng được**
· **F-14 (MỚI, CRITICAL) = transcript-replay hỏng cả trên run KHÔNG resume.**

## 1. Scope & ràng buộc

- Chỉ đọc `data/runs/**`. Không sửa/xóa/di chuyển; không `--repair`. `real60_spatial` giữ nguyên
  từng byte (mtime `2026-07-13 12:21:02`, không đổi sau audit).
- Không mạng/LLM/`.env`. Mọi lệnh chạy với `THOC_BLOCK_NETWORK=1` trong `conda run -n thoc-env`.
- Replay chạy trên **bản sao HEAD trong scratchpad** (`git archive HEAD | tar -x`), vì working tree
  đã trôi (xem §6). Repo và working tree không bị đụng.
- Việc này chứng minh **tính toàn vẹn artifact**. Nó **KHÔNG** chứng minh gì về hành vi LLM hay kinh
  tế, và **không** nâng cấp bất kỳ run nào thành verified.

## 2. Phương pháp — hai định nghĩa "trùng" (phải phân biệt)

| Định nghĩa | Cách đo | Kết quả trên `real60_spatial/events.jsonl` |
|---|---|---|
| **A — dòng trùng byte** | đếm bản dư của dòng text giống hệt | **230** (khớp Report_v2-ledger) |
| **B — bản ghi mồ côi** (đúng về nhân quả) | bản ghi có `idx < 4158` (điểm nối segment) **và** `tick > 105` (checkpoint cuối) | **313** (khớp model-architect) |

Hai con số **đều đúng**, đo hai thứ khác nhau: 313 bản ghi tail của segment-1 (tick 106..117) bị bỏ
lại trong journal; trong đó **230 trùng byte** với bản ghi segment-2 và **83 phân kỳ** (segment-2
chạy lại ra kết quả KHÁC: `gat` 58, `danh_ca` 8, `nhan_tin` 3, `ky_hd` 1, `chet` 1, ...).

⇒ **Định nghĩa A một mình bỏ sót 83 bản ghi mồ côi.** Đối chứng: `mock60_spatial` có 98 dòng
trùng-byte (toàn `che_tac`) mà **không hề resume** ⇒ "trùng byte" tự nó KHÔNG phải bằng chứng nhiễm
bẩn. Chỉ byte-offset ghi tại checkpoint mới cắt đúng được (đúng như ADR 0006 §C.1).

## 3. F-13 — TRUY NHIỄM BẨN: kết quả

**Câu hỏi:** có con số nào trong `reports/real60_evaluation.md` hay `Report_v2.md` §3 mang nhiễm bẩn
từ `events.jsonl` (file có bản ghi trùng) không?

### 3.1 Kết luận TO và RÕ

- **`Report_v2.md` §3: KHÔNG NHIỄM.** §3 **không chứa một con số định lượng nào** của run (bảng §3
  thuần định tính + trỏ nguồn). Không có gì phải rút lại. **Đây là tin tốt và phải được ghi lại.**
- **`reports/paper_draft.md`: KHÔNG NHIỄM.** Không nhắc `real60` hay bất kỳ số nào của run.
- **`reports/real60_evaluation.md` §1b, §2: KHÔNG NHIỄM.** Mọi số đến từ `metrics.jsonl`, mà file này
  **được ghi đè cuối run từ `w.metrics_lich_su`** (`run.py:274-276`) ⇒ 180 rows, 180 tick distinct,
  liền mạch 1..180, **không có bản trùng**. Kiểm từng số: khớp tuyệt đối.
- **`reports/real60_evaluation.md` §3 ("Sự kiện tích lũy"): CÓ NHIỄM + SAI NHÃN HORIZON.**

### 3.2 §3 — bằng chứng nhiễm bẩn (phần quan trọng nhất)

Tôi dò **6 phương pháp đếm × 81 mốc tick** để tìm cấu hình tái hiện được cột REAL của §3.
**Chỉ MỘT cấu hình khớp toàn bộ: đếm RAW (nguyên trạng, CÓ bản trùng) trên `events.jsonl`, cắt ở
tick ≤ 111 (hoặc 112).**

| sự kiện | §3 công bố | raw ≤111 (phương pháp đã dùng) | clean ≤111 (dedupe) | delta nhiễm | clean toàn run (đúng cho 180 tick) |
|---|---:|---:|---:|---:|---:|
| `ky_hd` | **10** | 10 | **9** | **+1** | 10 |
| `danh_ca` | **107** | 107 | **100** | **+7** | **154** |
| `cham_tre` | 108 | 108 | 108 | 0 | 108 |
| `bat_ga` | 3 | 3 | 3 | 0 | 3 |
| `vi_pham` | 6 | 6 | 6 | 0 | 6 |
| `duc_xu`,`qua_song`,`khai_hoang`,`lap_entity`,`blueprint`,`xiet_no` | 0 | 0 | 0 | 0 | 0 |

**Ba lỗi độc lập trong một bảng:**

1. **NHIỄM:** tập đếm chứa **158 bản ghi trùng** (raw≤111 = 4164 bản ghi vs clean≤111 = 4006).
   `ky_hd` bị đếm **+1** (hợp đồng tick 108 đếm hai lần), `danh_ca` bị đếm **+7**.
2. **SAI NHÃN HORIZON:** tiêu đề §3 ghi *"real 105t vs mock 180t"* — thực tế cột real là **tick ≤
   111/112**, tức một **snapshot giữa chừng lúc resume**, không phải 105, cũng không phải run hoàn tất.
3. **DƯỚI-BÁO NGHIÊM TRỌNG:** với run ĐÃ HOÀN TẤT 180 tick, `danh_ca` thật (clean) = **154**, không
   phải 107. Bảng đang so **real@111-tick-nhiễm** với **mock@180-tick-sạch** — lệch cả horizon lẫn
   chất lượng dữ liệu.

Cột MOCK của §3 **sạch** (raw = clean, file một segment): `ky_hd` 4428, `duc_xu` 1738, `cham_tre`
10637, `danh_ca` 1389, `bat_ga` 220, `vi_pham` 647 — khớp chính xác. (Hai ô dùng tên khác: "blueprint
87" = event `blueprint_moi` / metric `so_blueprint`; "xiết nợ 3" = event `xiet`.)

### 3.3 Phán quyết từng con số

| Con số (`real60_evaluation.md`) | Nguồn | Phán quyết |
|---|---|---|
| §1 `world_hash 738c6123fede`; horizon 180 tick; "không dừng budget" | `run_meta.json` / manifest | **KHÔNG NHIỄM** |
| §1 **"1589 LLM call"** | `llm_calls.sqlite` (append-only, **giữ cả call bị bỏ**) | **NHIỄM (đếm gộp)**: 1589 = `call_burned`. **122 call** của segment-1 (tick 106..118) đã bị vứt bỏ khi resume ⇒ **`call_effective` = 1467** |
| §1 **"fallback 3 (0.19%)"** | llm_calls | **NHIỄM**: 1/3 fallback nằm trong đoạn bị bỏ ⇒ effective **2/1467 = 0.14%** |
| §1 **"token in/out 10.69M / 0.35M"** | `reports/telemetry.json` | **SAI ĐỘC LẬP**: telemetry ghi `tok_in=10,229,193` (10.23M), `tok_out=459,040` (0.46M), `tok_tong=10,688,233`. "10.69M in" thực ra là **tổng in+out**; **"0.35M" không khớp trường nào** ⇒ **KHÔNG XÁC ĐỊNH ĐƯỢC** |
| §1 "chi phí ~$1.37" | telemetry `chi_phi_usd=1.3735` | **KHÔNG NHIỄM** — chi phí *phải* gồm cả call bị bỏ (tiền đã đốt thật), đúng ADR 0006 §C.1 |
| §1 "gateway smoke 9/9" | — | **KHÔNG XÁC ĐỊNH ĐƯỢC** (không có log trong run dir) |
| §1b/§2: dân số 2 / 39 · thóc/người 2771 · gini 0.40/0.27/0.23/0.17 · biết chữ 25%/50% · entity/blueprint/n_claims/credit = 0 · mock 576/239/0.64/0.72/0.88/121/37618/29 | `metrics.jsonl` | **KHÔNG NHIỄM** — khớp tuyệt đối tại tick 105 và 180 |
| §1b quỹ đạo "50 → đỉnh 51 (năm 19) → 39 (năm 35) → 2 (năm 60)" | `metrics.jsonl` | **KHÔNG NHIỄM** — đỉnh thật = tick 57 (năm 19), dân 51 |
| §2 "đúc xu (cả run) 0 / 1738" | events | **KHÔNG NHIỄM** (0 bất biến qua mọi phương pháp; file mock sạch) |
| §3 `ky_hd` 10 · `danh_ca` 107 | **events.jsonl RAW ≤111** | **NHIỄM** (delta +1 và +7); `danh_ca` còn sai horizon (thật = **154** @180 tick) |
| §3 `cham_tre` 108 · `bat_ga` 3 · `vi_pham` 6 · các số 0 | events | **KHÔNG NHIỄM** (bất biến qua mọi phương pháp) |
| §3 "Giai cấp cuối: real vô_gia_cư 34...; mock phụ_thuộc 114..." | `metrics.jsonl` **tick 105** | **KHÔNG NHIỄM nhưng SAI NHÃN**: đó là snapshot **tick 105**, không phải "cuối". Cuối thật: real@180 = `{phu_thuoc:1, vo_gia_cu:1}`; mock@180 = `{phu_thuoc:323, vo_gia_cu:142, phu_nong:56, trung_nong:34, cong_nhan:21}` |

**Không có biểu đồ nào bị nhiễm:** `tools/analyze.py` **chưa từng chạy** trên `real60_spatial`
(không có `final_analysis.md`/PNG trong `data/runs/real60_spatial/reports/`). Cảnh báo cho tương lai:
`analyze.py:37-46` gom `sinh`/`giai_cap_snapshot` bằng **dict theo id/tick** (idempotent với bản
trùng) nhưng `milestones`/`chronicles` là **list** ⇒ sẽ **nhân đôi** nếu ai đó chạy nó trên file này.

## 4. Hard checks — command + output THẬT

Lệnh (rút gọn tiền tố `THOC_BLOCK_NETWORK=1 PYTHONIOENCODING=utf-8 PYTHONUTF8=1 conda run -n thoc-env`):

```
python -m tools.verify_research_run real60_spatial
  [PASS] manifest_schema ... [PASS] metrics_contiguous_to_final — n=180 last=180 tick_cuoi=180
  [PASS] events_present
  [SKIP] replay_world_hash — bỏ qua (mode=real cần transcript)
  KẾT QUẢ: ĐỦ BẰNG CHỨNG   exit=0     ⇒ F-06 TÁI HIỆN: false-green trên artifact hỏng

python -m tools.verify_research_run real60_spatial --quick --json
  ValueError: too many values to unpack (expected 3)   @ tools/verify_research_run.py:240
                                                       ⇒ F-07 TÁI HIỆN

[HEAD db8e4fb] python -m tools.replay real60_spatial --from-transcript --verify
  transcript  : 1595 call, 261 miss, 403 chưa dùng
  hash replay : b2e68eba1253...      hash gốc : 738c6123fede...
  KẾT QUẢ     : LỆCH   exit=1        ⇒ transcript KHÔNG tiêu thụ khép kín;
                                        403 unused = đúng 403 call_id lặp của segment-2

[HEAD db8e4fb] python -m tools.replay mock60_spatial --verify                      # seed-replay
  hash replay : 6086f1d378f4...      hash gốc : 6086f1d378f4...
  KẾT QUẢ     : TRÙNG   exit=0

[HEAD db8e4fb] python -m tools.replay mock60_spatial --from-transcript --verify
  transcript  : 15702 call, 686 miss, 1025 chưa dùng
  hash replay : 5fe0b8e82ae4...      hash gốc : 6086f1d378f4...
  KẾT QUẢ     : LỆCH   exit=1        ⇒ F-14 (MỚI)

python -m tools.verify_research_run mock60_spatial
  9/9 PASS (gồm [PASS] replay_world_hash — 6086f1d378f4 vs 6086f1d378f4, audit xanh mỗi tick)
```

Journal identity đo trực tiếp trên `real60_spatial` (script chỉ đọc):

```
events      : 5237 dòng; 1 tick regression @dòng 4159 (117→106); 313 bản ghi mồ côi; 230 trùng byte
metrics     : 180 rows, 180 distinct, liền mạch 1..180                        ⇒ SẠCH
transcript  : 1595 rows, 1192 distinct call_id ⇒ 403 lặp;
              9 prompt_hash trùng — 9/9 có response_raw KHÁC NHAU (tick 106 ×8, tick 108 ×1)
llm_calls   : 1589 rows, call_id unique; segment-1 dừng @tick 118, segment-2 bắt đầu @tick 106
              ⇒ 122 call bị bỏ  (burned=1589, effective=1467; tok_in bỏ 877,237)
unrecognized: 5 dòng — 1 dòng mồ côi (tick 109) nhưng tick VẪN ĐƠN ĐIỆU (98,109,110,131,160)
              ⇒ nhiễm bẩn KHÔNG lộ ra với heuristic quét tick    (F-12)
```

**3 journal dừng ở 3 tick khác nhau sau cùng một lần kill: events→117, llm_calls→118,
transcript→119.** Xác nhận. ⇒ Không heuristic nội dung nào tìm được điểm cắt an toàn; chỉ byte-offset
tại checkpoint (sau flush+fsync) là hợp lệ — đúng như ADR 0006 §C.1/§C.2 lập luận.

## 5. F-14 (MỚI — CRITICAL): transcript-replay hỏng ĐỘC LẬP với resume

`mock60_spatial` **chưa bao giờ bị ngắt**: một segment, không tick regression, 15702 transcript rows
= 15702 llm_calls rows, `call_id` duy nhất 100%, 0 `prompt_hash` trùng, metrics liền mạch. Nó **PASS
seed-replay đúng `world_hash`**. Vậy mà **transcript-replay của nó FAIL** (686 miss, 1025 unused,
hash lệch) — chạy tại **đúng HEAD `db8e4fb`** với `prompt_template_hash` khớp manifest (`6b585250...`).

⇒ **Câu chuyện nhân quả hiện hành ("real60 lệch hash VÌ resume" — `Report_v2.md` §3, ADR 0006 §1.3,
`real60_evaluation.md` §6) là CHƯA ĐỦ.** Resume chắc chắn gây hại (403 call_id lặp + 9 prompt_hash
trùng với response khác nhau — đã chứng minh), nhưng **tồn tại một lỗi THỨ HAI, độc lập**, và
**P0.2 (journal resume-safe) một mình sẽ KHÔNG làm cổng `misses==0 && unused==0` (G3) xanh.**

Nghi phạm cụ thể (bàn giao `engine-surgeon`; **chưa xác nhận**, tôi không sửa code):

- `minds/transcript.py:8-15` — lập luận tất định dựa trên *"Prompt là hàm THUẦN của trạng thái thế
  giới"*, nhưng chính docstring `:24-26` thừa nhận `a.hoi_ky`/`a.niem_tin` **KHÔNG vào `world_hash`**
  mà **CÓ trong prompt tick sau**. Một input của prompt nằm NGOÀI state được băm ⇒ "cùng seed ⇒ cùng
  chuỗi prompt" **chưa được chứng minh**. Đây là lỗ hổng thiết kế, không phải lỗi đánh máy.
- `minds/transcript.py:194` — replay dựng mind mock bằng `tao_mind_mock(w, fast=True, run_dir=None)`
  trong khi run gốc dùng `run.py:37` `tao_mind_mock(w, fast=args.fast, run_dir=run_dir, ...)`
  ⇒ harness replay ≠ harness run.
- `minds/gateway.py:303` — `resp2 = self.provider.goi(req2, attempt=1)`: một miss sinh prompt sửa lỗi
  mới → prompt đó không có trong transcript → miss tiếp ⇒ **một miss đơn lẻ tự khuếch đại thành
  cascade**.

**Hệ quả cho claim §6 của `real60_evaluation.md`** ("cơ chế transcript-replay ĐÃ được kiểm chứng trên
`mock50_agr`/`real50_agr` — replay bit-for-bit"): hai run đó **không còn trong `data/runs/`** ⇒ claim
**KHÔNG kiểm chứng lại được hôm nay**. Không được dùng nó để trấn an rằng cơ chế lành lặn.

## 6. Version drift đang xảy ra (cảnh báo vận hành)

Working tree hôm nay đã trôi khỏi HEAD ở `minds/{prompts,schemas,translate,transcript,gateway}.py`,
`engine/events.py`, `run.py`, `tools/{replay,experiments,telemetry}.py` (P0.1/P0.2 đang landing).
`sha256(minds/prompts.py)` = `9e32bcac...` ≠ manifest `6b585250...` ⇒ **mọi replay chạy từ working
tree hôm nay phải bị coi là `skipped_version_mismatch`**. `tools/replay.py` hiện **không kiểm
identity** nên nó vẫn chạy và **in ra số trông có vẻ hợp lệ** — đúng lỗ hổng ADR 0006 §C.4 / P0.3
phải bịt. Tôi né bằng cách replay trên bản sao HEAD trong scratchpad; đã xác minh
`sha256(HEAD:minds/prompts.py)` = `6b585250...` = manifest ⇒ HEAD **chính là** code sinh ra hai run.

## 7. Findings

| ID | Sev | Finding | Bằng chứng |
|---|---|---|---|
| **F-13** | **MAJOR** | **XÁC NHẬN CÓ NHIỄM**, khoanh gọn trong `reports/real60_evaluation.md` §3: `ky_hd` **+1**, `danh_ca` **+7** (đếm raw ≤111 trên tập chứa 158 bản ghi trùng); `danh_ca` thật @180 tick = **154**, không phải 107; nhãn horizon "105t" sai. **`Report_v2.md` §3 và `reports/paper_draft.md` KHÔNG nhiễm.** | §3.2 |
| **F-14** | **CRITICAL** | **MỚI** — transcript-replay FAIL trên run **không resume** (`mock60_spatial`: 686 miss / 1025 unused) dù seed-replay TRÙNG bit-for-bit. **P0.2 một mình không đóng được cổng G3** | §5 |
| F-15 | MAJOR | "1589 call / fallback 0.19%" là `call_burned`; `call_effective` = **1467**, fallback **0.14%**. Telemetry chưa tách hai khái niệm (ADR 0006 §C.1 đã yêu cầu) | `run_meta.json`, `llm_calls.sqlite` |
| F-16 | MINOR | "token in/out 10.69M / 0.35M" (§1) không khớp telemetry (10.23M / 0.46M); 10.69M thực ra là **tổng** | `reports/telemetry.json` |
| F-17 | MINOR | "Giai cấp cuối" (§3) thực ra là snapshot **tick 105** cho cả real lẫn mock | `metrics.jsonl` t=105 vs t=180 |
| F-18 | MINOR | `reports/*.png` (`mock300_*`, `review_*_30y_*`, `vidtest_*`) trỏ tới run **không còn tồn tại** trong `data/runs/` ⇒ chart không truy được về event/metric thô | `ls data/runs/` |
| F-12 | xác nhận | `unrecognized_intents.jsonl` nhiễm **1 bản ghi mồ côi** mà **tick vẫn đơn điệu** ⇒ chỉ byte-offset manifest mới bắt được | §4 |
| F-05/F-06/F-07 | xác nhận | tái hiện đúng bằng lệnh ở §4 | §4 |

## 8. Kế hoạch phục hồi tối thiểu (KHÔNG sửa artifact, KHÔNG sửa evidence trong im lặng)

1. **Không đụng `data/runs/real60_spatial/`.** Nhãn sống ở `docs/reviews/artifact_ledger.md`, không
   ghi vào run dir (ADR 0006 §C.6).
2. **`reports/real60_evaluation.md` §3** (chủ sở hữu là người viết report — tôi **KHÔNG** sửa): thay
   cột REAL bằng số **clean toàn-run** (`ky_hd` 10, `danh_ca` **154**, `cham_tre` 108, `bat_ga` 3,
   `vi_pham` 6) **hoặc** giữ số cũ nhưng ghi nhãn tường minh `raw @tick≤111, chứa 158 bản ghi trùng`.
   Mọi trích dẫn kèm nhãn `diagnostic observation from an unreplayable run`.
3. §1: `call_burned 1589` / `call_effective 1467`; fallback `2/1467 = 0.14%`; token in/out
   `10.23M / 0.46M`. §3 đổi "Giai cấp cuối" → "Giai cấp @tick 105".
4. **F-14 phải vào findings register và vào scope P0.2 TRƯỚC khi `engine-surgeon` tuyên bố G3 xanh** —
   nếu không, P0.2 sẽ "sửa xong" mà cổng vẫn đỏ vì lý do khác.
5. P0.3: `tools/replay.py` + `tools/verify_research_run.py` phải **từ chối** khi identity ≠ manifest
   (`skipped_version_mismatch`) thay vì in số như hiện nay.

## 9. Claim boundary

Memo này chứng minh **tính toàn vẹn artifact** và **đường đi của nhiễm bẩn số liệu**. Nó **KHÔNG**
chứng minh gì về hành vi LLM, sụp đổ dân số, hình thành định chế, hay so sánh model/provider — kể cả
với các con số §1b/§2 mà tôi xác nhận "không nhiễm": **không nhiễm ≠ có giá trị khoa học**; chúng vẫn
nằm trên một artifact **không replay được**.

`real60_spatial` **giữ nguyên `diagnostic_only_unreplayable`**; không con đường nào trong memo này
nâng cấp nó. `mock60_spatial` `replay_verified` **chỉ có nghĩa seed-replay** (quỹ đạo tái dựng được
bit-for-bit từ seed), **không** có nghĩa transcript của nó khép kín (F-14).
