# P0 — Adversarial re-review (independent gate, round 2)

Tác giả: `adversarial-reviewer`. Ngày: 2026-07-13. Read-only trên code; không mạng/provider/`.env`.

## Verdict: **P0 GATE = PASS WITH RISKS** — *tạm thời*, và **VÔ HIỆU nếu tree không được đóng băng
rồi chạy lại gate MỘT LẦN, TUẦN TỰ.**

Bốn blocker **được sửa THẬT, không phải nắn test**. Tôi tái hiện từng fix độc lập qua đường code
sống, không tin suite. Nhưng review này được tiến hành trên một **tree đang chuyển động**: repo bị
sửa liên tục *trong lúc tôi đo*. Tôi thấy `verify_local` chuyển ĐỎ rồi XANH trong vòng một giờ.
**Chưa ai — kể cả parent — từng chứng minh gate này xanh trên một commit đóng băng.**

## Tree pin (19:15 +0700) — mọi claim dưới đây gắn với ĐÚNG cái này

```
2e50ba17fd682a27  minds/prompts.py         50c1ddd13fe088b2  minds/transcript.py
247b37e854ae3e0f  minds/capabilities.py    2625b33f4c6dd260  tools/experiments.py
dfa9e9ec72228c4e  minds/real.py            0d7cc4b8aa6395a4  tools/replay.py
10b554435d237084  run.py                   340253facbdf19f5  tools/verify_research_run.py
9ecefb0e53d7315a  engine/journal.py
catalog_hash() = a928fe2e612f7d0c…   prompt_template_hash() = cdc0ca92e806c894…
```

## Evidence (tree cuối, chạy sạch tuần tự)

| Đo | Kết quả |
|---|---|
| `pytest -q` | **477 passed, 1 skipped, 0 failed** |
| `ruff check .` | clean |
| `tools.verify_local` | **XANH ✅ 5/5** |
| 3 hash pin legacy | **3/3 MATCH** |
| Test inventory HEAD→nay | **302 → 384 fn, 0 bị gỡ**, không skip mới |
| `p0gate_mock` / `p0gate_resume` / `verify_local_…s41` | `replay_verified`, exit **0** |
| `real60_spatial` | `diagnostic_only_unreplayable`, exit **1** |
| `mock60_spatial`, `p0check_mock`, `p0check_resume` | `skipped_version_mismatch`, exit **1** |

## Disposition từng blocker

### A-01 (suite đỏ) — **CLOSED** (có sẹo, xem N-01)
477/1/0, tự đo. **Không test nào bị xóa/đổi tên/skip/nới**: HEAD 302 fn → 384 nay, hiệu tập tên = ∅.
Hai param từng đỏ VẪN nằm trong danh sách (`tests/test_prompt_config_parity.py:207-208`:
`("san_xuat.recipe.xu.cong", 6)`, `("san_xuat.recipe.xu.ra", 11)`). Chúng xanh vì **prompt đổi**,
không phải vì test đổi.

### A-02 (recipe `xu` không được công bố) — **CLOSED (lõi) / FIXED-BUT-WEAK (tổng quát hóa)**
Render thật, base *và* spatial: `xu: 5 công + 1 quặng đồng → 10 xu`. Đủ 3 số ở cả hai.
Fix **có cấu trúc, không phải vá chuỗi**: `minds/capabilities.py:889-893` (`_gt_xay`) suy CẢ danh
sách `mon` được quảng cáo LẪN chi tiết recipe từ **CÙNG MỘT** dict `cong_thuc_xay(w)` ⇒ quảng cáo
một `mon` mà giấu kinh tế học của nó giờ **bất khả về cấu trúc** cho `xay`. `may` — vốn CŨNG bị
giấu — nay cũng được công bố kèm điều kiện blueprint. Ngôn từ trung lập: không "tiền", không
"nên đúc", không xếp hạng.

**NHƯNG invariant tổng quát chỉ nằm trên giấy.** `minds/capabilities.py:20-30` khai **CAP-5**
("không quảng cáo mà giấu kinh tế học"). `grep -rn "CAP-5" tests/` → **rỗng**. Tệ hơn, hook của
chính nó CHẾT: `mon_recipe_khong_co_duong_che(w)` (`:244`, docstring ghi "Hook cho test CAP-5")
có **đúng một hit: chính định nghĩa nó**. Zero caller. → **N-02**.

### A-03 (false-green) — **CLOSED**
Một nguồn sự thật: `Ket.du_bang_chung()` (`:93-95`) đòi `artifact_status == REPLAY_VERIFIED`;
`ma_thoat()` (`:97-102`) suy exit code từ đó. Tôi audit **cả 6** site `ket.add(..., None, ...)`
(`:205,212,214,312,314,316`) đối chiếu `_tinh_nhan` (`:398-421`): **không đường `ok=None` nào tới
được xanh** — mọi SKIP dồn về `PENDING` → exit 2.
- `--quick` → `CHƯA CHỨNG MINH ⏸`; `--json` → `"ok": false, "exit_code": 2`. Banner "ĐỦ BẰNG CHỨNG ✅" đã biến mất.
- Carve-out `p_malformed` **bị GỠ**; transcript replay giờ `hard=True` ở MỌI mode (`:334-349`).
- Bằng chứng gate giờ CẮN: `p0check_*` — chính bằng chứng đầu bảng cũ — lập tức rơi xuống
  `skipped_version_mismatch`/exit 1 ngay khi catalog đổi.

### A-04 (F-28 priming) — **VẪN OPEN, đúng như yêu cầu. KHÔNG SCOPE CREEP.**
Cả 5 kênh nguyên vẹn; không ai lén nhét fix P3 vào P0:

| Kênh | file:line |
|---|---|
| (a) `[BẠN LÀ NGƯỜI SỐNG]` thang utility | `minds/prompts.py:397` |
| (b) `VI_DU_QUYET_DINH` với `chia_san_luong ty_le 0.4` | `minds/prompts.py:404, 408` |
| (c) `Đơn vị giá trị: kg thóc.` | `minds/prompts.py:422` |
| (d) nhãn `"địa chủ"` | `minds/prompts.py:475` |
| (e) engine BẢO agent **thuê nhân công** | `minds/prompts.py:259-260` |

⇒ **MỌI CLAIM EMERGENCE VẪN BỊ CẤM.**

### A-06 (catalog hash thiếu ở resume identity) — **CLOSED (verified trên đường sống)**
Tôi **không tin** test của repo (nó tamper manifest). Tôi chạy thật: mock run, hard kill tick 8,
rồi monkeypatch `minds.capabilities.catalog_hash` — mô phỏng một lần *sửa catalog thật* giữa hai
segment — rồi resume:
```
SystemExit: [E-JM-05] capability_catalog_hash đổi giữa hai segment:
            manifest a928fe2e612f7d0c ≠ hiện tại bbbbbbbbbbbbbbbb.
0 byte bị ghi (fingerprint bất biến): True
```
Fail-closed, không một byte bị ghi. **Fix thật.**

### A-09 (bằng chứng resume chưa diễn tập con bệnh) — **CLOSED**
`data/runs/p0gate_resume/journal_recovery.jsonl`:
`from_tick=15 bytes_truncated=435631 records_truncated=1100 rows_superseded=158`, tail moved to
`checkpoints/orphans/…`. Và `world_hash` của run bị-kill-rồi-resume == `world_hash` của run liền
(`2c32ea9c4be16a96…`), **cả hai ở `p_malformed=0.0`** — điều này cũng khai tử phàn nàn cũ của tôi
rằng `p0check_*` chạy ở 0.05 nơi cổng transcript chỉ là WARN. **Đây mới là bệnh nhân thật, được
diễn tập thật.**

### A-11 (tautology) — **CLOSED**
`cost_accounting_identity` (`:286-300`) với ba check thật, phủ định được: `burned == effective +
superseded`; `superseded == Σ journal_recovery.rows_superseded`; và `MAX(call_id) == COUNT(*)` —
cái cuối mới thực sự bắt được trò "xóa row cho hóa đơn đẹp".

### A-14 — **CLOSED, vượt yêu cầu**
`unrecognized_intents.jsonl` giờ là journal Class-A (truncate+quarantine) **kèm check đối ứng
sổ-kép** với record `unrecognized_intent` trong `events` (`engine/journal.py:885-921`).

### F-TE-1 (route nền thứ 3) — **CLOSED**
`minds/real.py:241` gọi `_ghi_call_loi` trong `except` của `_dich_intent_la`. Tôi quét **MỌI**
`except` quanh provider call: phủ ở `minds/real.py:177,241,329` và `minds/orchestrator.py:290,306`.
Không còn route nào đốt một call mà không có row transcript.

---

## Finding MỚI

### N-01 — **BLOCKING (quy trình/toàn vẹn): code bị sửa LIÊN TỤC trong lúc đang review.**
Không phải suy diễn — đo được: `tools/experiments.py` 18:37, `tools/replay.py` 18:38,
`engine/journal.py` 18:39, `run.py` 18:38 *và lại nữa* (`c2f9f545…` → `10b55443…`),
`minds/transcript.py` **18:59:42**. Artifact bị tạo lại giữa review: `p0gate_mock` 18:43:47,
`p0gate_resume` 18:50:26.

Hệ quả quan sát được:
1. `p0gate_mock` trả `replay_verified`/exit 0 lúc ~18:30, `skipped_version_mismatch`/exit 1 lúc
   ~18:43 (vì `FILE_RENDER_PROMPT` mở rộng để gồm `capabilities.py` ⇒ đổi `prompt_template_hash`
   ⇒ artifact bị bỏ rơi), rồi `replay_verified`/exit 0 lúc 19:15 sau khi được tạo lại.
2. **`tools.verify_local` ĐỎ ❌ (4/5, `FAIL pytest`) lúc ~18:50 và ~18:58** — tôi tái hiện HAI LẦN,
   tuần tự, sau khi kill mọi process lạc ⇒ không phải nhiễm từ tôi. Root cause:
   `TranscriptWriter.dong()` flush một handle ĐÃ ĐÓNG (`ValueError: I/O operation on closed file`),
   quật ngã ~20 test JOURNAL-1/2/3 + ablation. 18:59:42 file được sửa; `dong()` giờ có guard.
   Tới 19:10 `verify_local` XANH.

**Đây là bệnh A-01 trong bộ áo mới: một con số xanh không gắn với tree nào cả.** Một cái gate là
một phát biểu về **artifact đóng băng**; cái này là một cuốn phim.

### N-02 — **MAJOR: CAP-5 được khai, KHÔNG được cưỡng chế.** (xem A-02)
Lỗ `xu` đã bịt về cấu trúc, nhưng **LỚP** defect ("quảng cáo mà giấu kinh tế học") có **zero test**
và một **hook chết**. Một `mon` mới, hay một action mới có chi phí chỉ nằm trong config, sẽ hồi quy
**IM LẶNG** — mà đó chính là confound đã vô hiệu hóa so sánh `đúc xu 0 (real) / 1738 (mock)`.

### N-03 — MINOR: danh sách khóa của PROMPT-1 là thủ công
`KHOA_BASE`/`KHOA_SPATIAL` không có test nào bảo đảm chúng phủ hết leaf config vật lý. Quét độc
lập: ~30 (base) / 37 (spatial) khóa không hề làm prompt đổi. Phần lớn im lặng CHÍNH ĐÁNG (phân
phối thời tiết, `tong_tick` horizon — đúng là phải giấu, nội bộ decay uy tín, và
`khong_gian.cham_tre.gia_cong_goi_y` vốn **chỉ dành cho rulebot**). Hai cái cần quyết định tường minh:
- `hop_dong.uy_tin.phat_vi_pham_mieng` — menu quảng cáo hợp đồng miệng; **độ lớn** hình phạt uy tín
  khi phá vỡ **không bao giờ được công bố** (chỉ có định tính "mất uy tín").
- `khong_gian.ga_rung.cong_moi_con` là **khóa config CHẾT** — engine đọc
  `chan_nuoi.bat_ga_cong_moi_con` (`engine/chan_nuoi.py:106`), vốn CÓ được công bố. Vệ sinh, không phải confound.

### N-04 — MINOR: `_kiem_identity` fail-OPEN với `None` legacy
`engine/journal.py:487`: `if a is not None and b is not None and a != b`. Manifest cũ (trước khi có
trường catalog) resume im lặng. Back-compat chấp nhận được — nhưng phải NÊU, đừng để mục rữa.

### N-05 — QUESTION: `test_journal2_identity_catalog_doi_fail_closed` match `E-JM-0`
(`tests/test_p0_resume_independent.py:519`) ⇒ nó cũng pass với `E-JM-03`/`E-JM-04`. Siết về `E-JM-05`
để nó test đúng cái nó tuyên bố.

---

## Vẫn OPEN từ vòng 1 (không thuộc P0)

A-05 (`config_sha256` không đơn ánh trên hành vi) · A-08 (F-33: 686 miss của `mock60_spatial` VẪN
chưa root-cause, và giờ **không quan sát được** sau `skipped_version_mismatch`) · A-10 (văn bản
claim-boundary tự mâu thuẫn giữa `Report_v2-ledger.md`, `reports/final_handoff.md:67`,
`reports/world_class_readiness.md:38-39`) · A-12 · A-13 · A-15 · A-16.

## Invariant tôi tấn công mà KHÔNG phá được

- Test bị xóa/đổi tên/skip/nới? **KHÔNG.** 302 → 384 fn, 0 bị gỡ.
- Param bị lặng lẽ bỏ để PROMPT-1 xanh? **KHÔNG** — `recipe.xu.{cong,ra}` vẫn trong `KHOA_BASE`.
- Kênh priming bị lén "sửa" như scope creep P0? **KHÔNG** — cả 5 nguyên văn.
- Hash pin dịch chuyển? **KHÔNG** — 3/3.
- `real60_spatial` bị retcon? **KHÔNG** — vẫn `diagnostic_only_unreplayable`, exit 1, `git status data/runs/` rỗng.
- Xóa row giấu trong `llm_calls`? **KHÔNG** — và `MAX(call_id) == COUNT(*)` giờ chủ động canh.

## Claim boundary (ràng buộc)

Khi điều kiện freeze bên dưới thỏa, nhãn DUY NHẤT được phép là **`technical-ready` — và KHÔNG GÌ HƠN.**

Vẫn **CẤM tuyệt đối**:
- **Mọi** claim emergence — nghề, tiền, lao động làm công, tá điền, phân tầng, định chế. A-04 còn
  mở; engine **theo đúng nghĩa đen** trao cho agent một hàm hữu dụng, một numéraire, một ví dụ
  chiến lược có biện giải, một nhãn giai cấp, và một chỉ dẫn đi thuê thợ.
- Trích `đúc xu 0 (real) / 1738 (mock)` (`reports/real60_evaluation.md` §2) như bằng chứng hành vi.
  Những run đó được sinh bởi một interface **giấu recipe đúc tiền**. **Interface-confounded — gắn
  nhãn, hoặc bỏ.**
- `mechanism-ready`, `research-ready`, `empirically-validated`.
- Trích `real60_spatial` (diagnostic-only), `mock60_spatial` / `p0check_*` (version-mismatched) làm
  bằng chứng cho bất cứ điều gì.
- Trình bày `p0gate_*` như bằng chứng về hành vi LLM/kinh tế/collapse/provider. Chúng chứng minh
  **interface + journal + counter continuity + determinism của một mock 30 tick**, và KHÔNG GÌ KHÁC.
  `prompt_hash` của mock khóa theo `(agent_id, tick)` với **zero world state**
  (`"request": "[mock 1-to-1] id=A0005 tick=1"`) ⇒ mock transcript-replay **về cấu trúc bất khả**
  để phủ định lớp defect F-33.

## Next handoff

| Tới | Việc |
|---|---|
| **parent / integration-manager** | **BLOCKING: ĐÓNG BĂNG TREE**, rồi chạy **MỘT LẦN, TUẦN TỰ, không có gì khác chạy song song**: `verify_local` + `verify_research_run` trên toàn bộ run. Dán output. Chừng nào chưa có cái đó, `technical-ready` là **chưa xứng đáng**. **Đừng sửa code trong lúc gate đang review lần nữa** — nó phá hủy tính review-được của artifact. |
| `test-engineer` | **N-02**: viết test CAP-5 — gọi `mon_recipe_khong_co_duong_che(w)` và assert ∅; assert MỌI `mon`/action được quảng cáo có cost+output render từ config sống. **N-05**: siết match `E-JM-0` → `E-JM-05`. |
| `spec-governor` | **N-03** · **A-13** |
| `reproducibility-steward` | **A-10**: hòa giải ba văn bản claim-boundary mâu thuẫn về đúng một nhãn duy nhất. |
| `minds-engineer` (P3) | **A-04** — năm kênh priming. **Không gì về emergence là bảo vệ được cho tới khi chúng biến mất.** |
