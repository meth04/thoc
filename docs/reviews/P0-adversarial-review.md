# P0 — Adversarial review (independent gate)

Tác giả: `adversarial-reviewer` (KHÔNG viết code, KHÔNG sửa test). Ngày: 2026-07-13.

**Verdict: `FAIL`** — cổng P0 KHÔNG được tuyên bố đóng hôm nay. Ba blocking finding, hai trong số đó
tái hiện được dưới một phút. Phần kỹ thuật bên dưới phần lớn là vững; nhưng **trạng thái được tuyên
bố là SAI SỰ THẬT**, và tool gate vẫn phát đèn xanh trên chính artifact mà nó gắn nhãn không-replay-được.

## Scope

Read-only. Không mạng, không provider, không `.env`, không `--smoke`, không mutate `data/runs/**` hay
`git`. Mọi lệnh `THOC_BLOCK_NETWORK=1 ... conda run -n thoc-env`. Đã đọc: ADR 0006/0007, `Report_v2.md`,
`docs/reviews/{Report_v2-ledger,P0.1-minds-engineer,P0.2-engine-surgeon,P0-artifact-integrity,artifact_ledger}.md`,
`git diff HEAD`, và 4 run dir.

---

## BLOCKING

### A-01 — `pytest` ĐỎ. Con số "325 passed / 1 skipped" được tuyên bố là SAI.

```
$ conda run -n thoc-env python -m pytest -q -p no:cacheprovider
2 failed, 438 passed, 1 skipped, 14 warnings in 163.69s
FAILED tests/test_prompt_config_parity.py::test_prompt1_doi_khoa_config_base_thi_prompt_doi[san_xuat.recipe.xu.cong]
FAILED tests/test_prompt_config_parity.py::test_prompt1_doi_khoa_config_base_thi_prompt_doi[san_xuat.recipe.xu.ra]
```
`ruff check .` → clean (phần đó đúng).

Bộ test độc lập của `test-engineer` đẩy tổng lên 439 và **hai cái ĐỎ**. `Report_v2-ledger.md` vẫn quảng
cáo "325 passed · ruff clean · verify_local XANH ✅". **Gate đang tự-báo-xanh dựa trên một phép đo cũ.**

### A-02 — Test đỏ là THỰC CHẤT: **recipe đúc xu KHÔNG BAO GIỜ được nói cho agent**, trong khi action VẪN được quảng cáo.

`config/world.yaml:32` → `xu: {quang_dong: 1, cong: 5, ra: 10}`. `engine/production.py:411-421` thi hành
(event `duc_xu`). `minds/capabilities.py:787-799` (`_gt_xay`) render danh sách `mon` — **có `"xu"`** —
nhưng chỉ nêu chi phí của `cong_cu` và `nha`. **Không nơi nào render `recipe.xu.cong` hay `recipe.xu.ra`.**
Vì thế đổi hai khóa đó không làm prompt đổi ⇒ PROMPT-1 FAIL.

**Hệ quả, và đây mới là phần quan trọng:** agent được mời *"đúc xu"* trên menu với **không chi phí, không
sản lượng nào được công bố**, và phải ĐOÁN. `reports/real60_evaluation.md` §2 ghi
`đúc xu (cả run) 0 (real) / 1738 (mock)`. Con số đó **interface-confounded ĐÚNG KIỂU F-01/F-02**: LLM chưa
bao giờ được cho biết đúc xu tốn gì hay ra gì; PersonaBot đọc `ctx`, không đọc prompt.
**Câu hỏi đầu bảng của dự án là liệu tiền có tự phát sinh. Hành động DUY NHẤT đúc ra tiền lại chính là
hành động mà prompt giấu kinh tế học của nó.** Đây không phải lỗi thẩm mỹ.

### A-03 — **FALSE-GREEN CÒN SÓT** trong `tools/verify_research_run.py` — cùng hình dạng F-06, chỉ đổi chỗ.

`Ket.failed()` (`:68-69`) chỉ fail khi `ok is False and hard`. `artifact_status` tính riêng (`:337-360`).
**Hai cái bất đồng, và exit code nghe theo cái sai.**

**(i) mock + `p_malformed > 0`** (`hard = (mode=="real") or (mode=="mock" and p_mal==0.0)`, `:272`):
```
### p_malformed=0.5: misses=31 unused=41 hash_match=False ok=False
    verify: replay_from_transcript ok=False hard=False
    artifact_status=diagnostic_only_unreplayable  failed()=False  EXIT=0
```
Tool in `artifact_status: diagnostic_only_unreplayable` **VÀ** `KẾT QUẢ: ĐỦ BẰNG CHỨNG ✅` **VÀ** exit 0,
trên một artifact mà transcript replay ra một thế giới KHÁC.

**(ii) `--quick`** trên bất kỳ run nào:
```
[SKIP] replay_world_hash — bỏ qua (--quick)
[SKIP] replay_from_transcript — bỏ qua (--quick)
artifact_status: pending_verification
KẾT QUẢ: ĐỦ BẰNG CHỨNG ✅        EXIT_QUICK=0
```
Đây đúng là cơ chế F-06 (`SKIP` → `ok=None` → `failed()` bỏ qua → xanh) mà P0.2 tuyên bố đã "XÓA HẲN".

Carve-out `p_malformed` CÓ lý do thật (`da_nham` side-effect xảy ra trước khi text hỏng —
`tests/test_transcript.py:90-98`). Một giới hạn đã biết thì được. Nhưng phát **"ĐỦ BẰNG CHỨNG ✅" + exit 0**
lên trên nó thì KHÔNG.

⚠️ Điều này chạm cả bằng chứng đầu bảng: **`p0check_mock` và `p0check_resume` đều chạy với
`p_malformed=0.05`** ⇒ với hai run đó `replay_from_transcript` là **WARN, không phải gate**. Chúng TÌNH CỜ
pass (0 miss/0 unused, hash trùng — tôi chạy lại cả hai, exit 0); nhưng bằng chứng đầu bảng đang tựa vào
một check mà ở đúng cấu hình đó **không cưỡng chế**.

### A-04 — F-28 CÒN NGUYÊN VẸN. Mọi claim về emergence phải tiếp tục bị CẤM.

Render `build_agent_prompt` thật trên base, spatial-only, và scenario `agrarian_transition_v1`:

| Kênh | file:line | base | spatial | agr |
|---|---|---|---|---|
| (a) hàm hữu dụng trao tay: `[BẠN LÀ NGƯỜI SỐNG] … no bụng … an toàn … gia đình … và **vị thế** (đất đai, của cải, chữ nghĩa, **tiếng thơm**)` | `minds/prompts.py:415-420` | CÓ | CÓ | CÓ |
| (b) ví dụ chiến lược CÓ BIỆN GIẢI: `chia_san_luong ty_le 0.4` + `cau_hon`, `ly_do:"…thửa xa cho cấy rẽ lấy 4 phần, và đến tuổi phải tính chuyện gia đình."` | `minds/prompts.py:423-429` | CÓ | CÓ | CÓ |
| (c) mồi numéraire: `Đơn vị giá trị: kg thóc.` | `minds/prompts.py:441` | CÓ | CÓ | CÓ |
| (d) nhãn nghề: `Bạn là địa chủ 34 tuổi` (Lớp-5 → `engine/tick.py:322` → `minds/prompts.py:519`) | `minds/prompts.py:512-525` | CÓ | CÓ | CÓ |
| **(e) MỚI — engine tự tay gợi ý THUÊ NHÂN CÔNG** | `minds/prompts.py:276-281` | CÓ | CÓ | CÓ |

**(e) là kênh thứ NĂM mà register chưa liệt kê.** Khi `recipe.nha.cong > nhu_cau.ngay_cong_moi_tick`
(đúng ở MỌI config đã ship: 240>180 base, 240>120 spatial), prompt thêm: *"KHÔNG AI tự dựng nổi nhà một
mình trong một mùa: cần người góp công (vợ/chồng, con lớn `gop_cong_cho`, hoặc **thuê thợ bằng hợp đồng
`gop_cong`**), hoặc mua nhà có sẵn."* ⇒ **Engine BẢO agent đi thuê lao động làm công**, rồi dự án hỏi lao
động làm công có tự phát sinh không.

Hai đính chính cho register (độ chính xác của một sổ finding là quan trọng):
- F-28(c) như đã ghi (`"Mọi trao đổi tính bằng thóc"`, `minds/prompts.py:82`) nằm trong `mo_ta_the_gioi`,
  chỉ được gọi từ `build_system` — mà **`build_system` KHÔNG CÓ CALLER NÀO** (`grep -rn "build_system"` chỉ
  ra chính định nghĩa của nó). Đó là **dead code**. Mồi numéraire THẬT SỰ SỐNG là `prompts.py:441`.
  Finding vẫn đứng; trích dẫn thì sai.
- F-29 **đã được sửa một phần như tác dụng phụ của P0.1**: khối chính trị (gồm đúng ngưỡng Gini bạo động
  và tỷ lệ sung công) giờ gated theo `chinh_tri.bat` (`minds/prompts.py:400`), và `chinh_tri.bat=false`
  trong `agrarian_transition_v1` ⇒ không còn render ở đó. Nó VẪN render ngưỡng-như-đòn-bẩy ở mọi scenario
  bật chính trị.

**Disposition:** P0.1 KHÔNG được giao sửa mấy cái này (P3.1 sở hữu). Nhưng chúng **đang sống trong MỌI
prompt dự án render hôm nay**. Chừng nào chưa gỡ, **không claim nào về sự tự phát của nghề, tiền, phân
tầng, tá điền, lao động làm công, hay định chế là bảo vệ được — bất kể gate xanh đến đâu.**

---

## MAJOR

### A-05 — `config_sha256` **KHÔNG đơn ánh trên hành vi**. Toàn bộ câu chuyện identity/replay tựa vào nó.

`engine/config.py:47` tính digest với `sort_keys=True`. `engine/economy.py:43` duyệt
`khong_gian.vu_dong.cay` theo **insertion order**; `engine/consumption.py:60` ăn theo ĐÚNG thứ tự đó.
`world_hash` canonical-sort (`engine/world.py:45,54`) ⇒ **không thấy**.

Phản ví dụ đã chạy (rulebot, seed 9, spatial overlay, chỉ khác thứ tự khóa YAML của `vu_dong.cay`):
```
insertion order A: ['ngo','khoai']     insertion order B: ['khoai','ngo']
digest A == digest B : True 151c58e9ba253b4e
food_equivalence A   : ['thoc','ngo','khoai']
food_equivalence B   : ['thoc','khoai','ngo']
world_hash t0 equal  : True
*** QUỸ ĐẠO PHÂN KỲ ở tick 28: 4500a32e108b0c61 != 2700cc4ef8a98f66  (CÙNG config_sha256!)
```
Bất biến "cùng `config_sha256` ⇒ cùng quỹ đạo" là **SAI hôm nay** ⇒ câu "identity là một phép so hash"
(ADR 0006 §A.2/§C.4) **chưa đúng**. P0.2 chỉ vá triệu chứng (`engine/world.py:626`) và đã nói thật điều đó.

### A-06 — `capability_catalog_hash` THIẾU ở cổng identity của **resume**.

`engine/journal.py:68-74` `JournalIdentity = {config_sha256, prompt_template_hash, git_revision}` — không
có catalog hash. `_kiem_identity` (`:466-477`) chỉ so 2 trường đầu. Mà
`prompt_template_hash = sha256(minds/prompts.py)` — **KHÔNG phủ `minds/capabilities.py`**, nơi giờ chứa
TOÀN BỘ menu và hợp đồng wire.

⇒ Sửa `minds/capabilities.py` rồi `--resume`: **E-JM-04 KHÔNG kích hoạt** ⇒ đúng artifact
"transcript hai-nửa-hai-luật" mà E-JM-04 sinh ra để chặn. ADR 0006 §C.2 ghi rõ trường này trong
`journal_manifest.identity`.

Tin tốt: `tools/replay._kiem_identity:93` CÓ kiểm nó và nó chạy đúng (nhờ vậy `mock60_spatial` được gắn
cờ đúng — xem A-07). Lỗ hổng CHỈ ở đường resume.

### A-07 — `docs/reviews/artifact_ledger.md` đã CŨ: `mock60_spatial` không còn `replay_verified`.
```
$ python -m tools.verify_research_run mock60_spatial
[FAIL] replay_world_hash — skipped_version_mismatch …
       prompt_template_hash [6b585250… → 4f48eb2a…], capability_catalog_hash [None → 795188c7…]
artifact_status: skipped_version_mismatch     EXIT=1
```
Ledger `:22` vẫn ghi `replay_verified` / "citable ở tier `mechanism_result`". **Dự án hiện có KHÔNG một
artifact `replay_verified` nào** ngoài hai run smoke 30-tick `p0check_*`.

### A-08 — F-33/F-14 chưa được root-cause; nó đã trở nên **không quan sát được**.
Bằng chứng gốc (`replay mock60_spatial --from-transcript` → 686 miss) giờ short-circuit ở identity (A-07)
nên replay không bao giờ chạy. Defect chưa được truy nguyên; nó chỉ bị làm cho vô hình.

Tôi chạy phản-test mà parent chưa chạy: **run mock spatial 120 tick MỚI trên code hiện tại** (pop 283,
6780 call), rồi transcript replay:
```
=== F-33 PROBE ===  ticks=120 total=6780 misses=0 unused=0 hash_match=True identity_ok=True ok=True
```
⇒ F-33 **KHÔNG tái hiện** trên code hiện tại ở 2/3 horizon của mock60. Đó là bằng chứng thật và hữu ích —
nhưng **không phải root cause**; 686 miss của mock60 vẫn chưa được giải thích. Hạ từ BLOCKING xuống
MAJOR-with-carry.

⚠️ **Và đây là điều `p0check_*` THỰC SỰ chứng minh:** transcript của mock có `request` đúng nghĩa đen là
`"[mock 1-to-1] id=A0005 tick=1"` (`data/runs/p0check_mock/transcript.jsonl:1`; `minds/orchestrator.py:274-275`).
`prompt_hash` của nó vì thế là hash của `(agent_id, tick)` và **mang ZERO world state**. Replay transcript
mock gần như một **tautology**: nó chỉ xác nhận cùng những agent được hỏi ở cùng những tick.
Nó **về cấu trúc là bất khả** để bắt lỗi loại "prompt phụ thuộc state ngoài `world_hash`" (chính là nghi
phạm số một của F-33: `a.hoi_ky`/`a.niem_tin`, `minds/transcript.py:24-26`). Bằng chứng THỰC SỰ có ý nghĩa
cho đường real là các test `FakeTransport` in-process (`tests/test_resume_journal.py:358,393`), vốn CÓ chạy
`build_agent_prompt`. Hãy trình bày đúng như vậy; đừng trình bày `p0check_*` như bằng chứng cổng replay real
chạy end-to-end trên artifact.

### A-09 — Bằng chứng resume đầu bảng CHƯA BAO GIỜ diễn tập con bệnh nó chữa.
`data/runs/p0check_resume/journal_recovery.jsonl` (dòng duy nhất):
```json
{"kind":"truncate_on_resume","from_tick":15,"bytes_truncated":0,"records_truncated":0,
 "rows_superseded":0,"files_moved":[]}
```
0 byte cắt, 0 record quarantine, 0 row superseded. `p0check_resume` là **dừng êm ở tick 15 rồi resume** —
journal vốn đã đúng bằng checkpoint. **Con bệnh (tail mồ côi sau hard kill, ba journal dừng ở ba tick khác
nhau) CHƯA HỀ có mặt trong run này.** Câu "`p0check_resume` (15+15) CÙNG `world_hash`" là ĐÚNG và có giá
trị (rebase counter, `seq`/`call_id` liên tục), nhưng **KHÔNG phải** minh chứng cấp-artifact của
JOURNAL-1/JOURNAL-3 như nó đang được bán.

Minh chứng thật CÓ TỒN TẠI và tốt — `tests/test_resume_journal.py` kill giữa tick (`_NgatTaiTick`,
`KILL_TICK=7`), assert `records_truncated > 0` + `files_moved`, và có ablation thật
(`test_ablation_khong_truncate_thi_vo`) tái hiện con bệnh rồi cho thấy nó biến mất.
**Hãy trích các TEST, đừng trích cái RUN.**

### A-10 — Văn bản claim-boundary TỰ MÂU THUẪN, và hai report đã ship thì OVERCLAIM.
- `Report_v2-ledger.md:8-9`: "*Không gate nào có output. Do đó **không** được tuyên bố `technical-ready`…*"
  vs `:30-31`: "*Claim boundary P0: đây là `technical-ready`*". **Cùng một file.**
- `reports/final_handoff.md:67` — "**technical-ready**: ĐẠT. **research-ready (mechanism benchmark)**: phần
  lớn ĐẠT"; `reports/world_class_readiness.md:38-39` — tương tự. Chúng có trước `Report_v2.md` và giờ mâu
  thuẫn trực tiếp với nó.

---

## MINOR

- **A-11** `cost_accounting_split` assert `call_burned >= call_effective` (`:245`). `burned = COUNT(*)`,
  `effective = COUNT(superseded=0)` ⇒ **tautology, không bao giờ fail được**, nhưng được in như bằng chứng ở
  mọi block PASS. Thay bằng identity thật: `burned == effective + rows_superseded`.
- **A-12** `minds/prompts.py:70-95` (`mo_ta_the_gioi`, `build_system`) là **dead code** — không caller. Vẫn
  chứa câu SAI "Mọi trao đổi tính bằng thóc".
- **A-13** ADR 0006 §C.3 bắt `metrics.jsonl` thành append-only per-tick. Implementation giữ ghi-đè cuối run
  (`run.py`), có biện hộ hợp lý ("Class B — derived"). ADR giờ lệch code ⇒ phải amend ADR (spec-governor),
  không để lệch ngầm.
- **A-14** `kiem_lien_tuc` (`engine/journal.py:732`) **không bao giờ** soi `unrecognized_intents.jsonl` — đúng
  cách mà 1 bản ghi mồ côi của nó ở `real60_spatial` (tick 109, tick vẫn đơn điệu) lọt lưới.
- **A-15** `tests/test_resume_journal.py:43-47` còn comment cũ nói F-P02-1 chưa sửa. Nó **ĐÃ** sửa
  (`minds/real.py:173-177`, `:321-323`). Nhưng overlay vẫn nâng quota lên 100 000 ⇒ **không test nào chứng
  minh cái fix**. Thêm một test trong đó route nền THẬT SỰ hỏng mà transcript vẫn replay `misses == 0`.
- **A-16** `luat_vat_ly` vẫn công bố đúng ngưỡng bạo động (`gini_nguong_bao_dong`) và tỷ lệ sung công như một
  đòn bẩy khả dụng khi `chinh_tri.bat` bật. F-29 mới chỉ được *gate*, chưa *giải quyết*.

---

## Cái tôi đã TẤN CÔNG mà KHÔNG phá được (ghi vào biên bản — đây là việc thật)

| Bề mặt | Kết quả | Bằng chứng |
|---|---|---|
| Test bị nới / đổi tên / xóa? | **KHÔNG.** 302 test fn ở HEAD → 319 giờ; **0 cái bị gỡ**. `git diff HEAD -- tests/` là 8 insert / 5 delete trong `test_prompt_ky_luat.py`, toàn bộ là import-và-dựng-world; `TU_MOM`, `TEN_DINH_CHE_CAM` và MỌI assertion giữ nguyên từng chữ. Chỉ 2 skip toàn repo, cả hai có sẵn/chính đáng. | `tests/test_prompt_ky_luat.py:22-23,79-80` |
| `hard=` bị lật để lách gate? | **KHÔNG** với các soft check có sẵn. Carve-out MỚI duy nhất (`:272`) là giới hạn đã biết có thật — nhưng nó cặp với một false-green (**A-03**). | `git diff HEAD -- tools/verify_research_run.py` |
| Catalog lén xếp hạng nghề (CAP-4)? | **KHÔNG.** Đọc cả 38 descriptor. Không điểm ưu tiên, không ranking, không tính từ chuẩn tắc, không nhãn nghề. Chỉ chi phí/điều kiện/mã kết quả. Menu vẫn xáo theo `(agent, tick)` qua `w.rng`. | `minds/prompts.py:447-448` |
| Hash legacy thật sự bất biến? | **CÓ, 3/3 + golden.** rulebot 20t seed 11 = `4ba32e51…`, seed 42 = `f1f8cd4b…`, spatial-ON seed 11 = `afc5b09e…`, golden seed 7 = `8be4915e…`. Tất cả MATCH. **F-35 là FIX, không phải hồi quy**: rulebot bypass `translate` nên hash spatial của nó không đổi; chỉ mock+`hai_bo` đổi, vì ferry intent mà `translate` từng nuốt im lặng nay tới được wire. | executed |
| `llm_calls` có row nào bị DELETE? | **KHÔNG.** `_supersede_llm_calls` chỉ `UPDATE … SET superseded=1`. Tail quarantine được **MOVE**, không xóa. | `engine/journal.py:624-669` |
| `--recover-journal` có bao giờ làm run xanh? | **KHÔNG.** `artifact_status_forced` short-circuit `_tinh_nhan`; `journal_replay_complete` là hard FAIL. | — |
| `real60_spatial` bị retcon / trích như bằng chứng hành vi? | **KHÔNG.** exit 1, `diagnostic_only_unreplayable`, run dir byte-identical. `reports/paper_draft.md` không trích nó. | executed |

---

## Disposition MỌI blocking finding

| ID | Disposition | Cần gì trước khi chạy lại cổng P0 |
|---|---|---|
| **A-01** | **OPEN — chặn G8.** | `pytest -q` xanh; sửa dòng ledger về con số THẬT. |
| **A-02** | **OPEN — chặn G1.** | Render `san_xuat.recipe.xu.{cong,ra}` (+ audit MỌI `mon` được quảng cáo); gắn nhãn interface-confounded cho so sánh `đúc xu 0/1738`. |
| **A-03** | **OPEN — chặn G9.** | `verify_research_run` phải exit non-zero trừ khi `artifact_status == replay_verified`; chạy lại `p0check_*` với `--p-malformed 0.0`. |
| **A-04** | **GHI NHẬN, KHÔNG SỬA ĐƯỢC TRONG P0 (owner P3.1).** KHÔNG chặn cổng *kỹ thuật*. **CHẶN VĨNH VIỄN mọi claim emergence** cho tới khi đóng. Thêm kênh **(e)** (`prompts.py:276-281`, gợi ý thuê nhân công) vào register F-28; sửa trích dẫn (c) thành `prompts.py:441`. | Banner phải sống sót vào MỌI report P1–P4, nguyên văn. |

## Claim boundary (ràng buộc)

Nếu A-01/A-02/A-03 đóng, nhãn ĐÚNG là **`technical-ready` cho lớp interface và journal, và KHÔNG GÌ HƠN**:
- Cổng transcript-replay được chứng minh **trên đường real CHỈ in-process** (`FakeTransport`).
  **KHÔNG artifact `real` trên đĩa nào pass nó hôm nay.**
- Bằng chứng replay cấp-artifact là **mock only**, và `prompt_hash` của mock khóa theo `(agent_id, tick)`
  với **zero world state** ⇒ nó **không thể** phủ định lớp defect F-33.
- `p0check_*` chứng minh **interface + counter continuity + determinism của một mock 30 tick**. Chúng chứng
  minh **KHÔNG GÌ** về hành vi LLM, kinh tế, collapse, tử vong, tiền, hay so sánh provider.
- `config_sha256` **không đơn ánh trên hành vi** (A-05) ⇒ "identity đã verify" mới là một phát biểu *một phần*.
- `mock60_spatial` = `skipped_version_mismatch`; `real60_spatial` = `diagnostic_only_unreplayable`.
  **Dự án KHÔNG có run nào citable cho nghiên cứu.**
- **ZERO** claim emergence (nghề, tiền, lao động làm công, tá điền, phân tầng, định chế) là bảo vệ được
  chừng nào A-04 còn đứng.
