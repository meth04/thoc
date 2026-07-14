# Report_v2 — Dependency / evidence ledger

Owner: `integration-manager`. Cập nhật liên tục trong suốt chương trình P0→P4.
Đây là **sổ bằng chứng**, không phải checklist tường thuật. Một package chỉ `DONE` khi đủ 7 mục
của `Report_v2.md` §8.

> **Trạng thái chương trình (2026-07-13, SAU independent gate):** **P0 = FAIL** (cổng độc lập chặn).
> P1–P4 = BLOCKED. **KHÔNG được tuyên bố `technical-ready`** — G1 (parity) và G8 (suite) đang ĐỎ.
> `real60_spatial` = `diagnostic_only_unreplayable`. `mock60_spatial` = `skipped_version_mismatch`.
> **Dự án hiện KHÔNG có run nào citable cho nghiên cứu.**
>
> Đây là **phán quyết hiện hành** và nó THẮNG mọi dòng "technical-ready" ở §0-bis bên dưới (đó là
> phép đo TRƯỚC khi `test-engineer` thêm bộ test độc lập — xem A-01).

---

## 0-bis. TRẠNG THÁI P0 SAU IMPLEMENTATION (đo bởi parent, 2026-07-13)

| Cổng | TRƯỚC | SAU |
|---|---|---|
| `verify_research_run real60_spatial` | exit **0**, `ĐỦ BẰNG CHỨNG ✅` (false-green F-06) | exit **1**, `journal_continuity FAIL`, `replay_from_transcript FAIL`, `artifact_status: diagnostic_only_unreplayable` |
| `verify_research_run --json` | `ValueError: too many values to unpack` (F-07) | JSON hợp lệ, exit 1 |
| Resume → replay | hash lệch, 403 dup `call_id`, 313 bản ghi mồ côi | **`p0check_resume` (15+15 có `--resume`) CÙNG `world_hash` `8b4ac89064adf309…` với `p0check_mock` (30 tick liền)**; `0 miss / 0 unused`; `artifact_status: replay_verified`; exit 0 |
| Artifact version-mismatch | in `LỆCH ❌` (đọc như "mô phỏng mất tất định") | `skipped_version_mismatch ❌` + giải thích rõ đây KHÔNG phải bằng chứng mất tất định |
| LLM gọi được `qua_song`/`rao_do`/`dong_thuyen` | **KHÔNG** (thiếu schema+translate+menu) | **CÓ** — catalog 38 descriptor, CAP-1..4 test-enforced |
| Prompt luật vật lý | tĩnh (6 tháng/90kg/180 công, sai cho spatial; và `650kg` sai cả cho base) | render từ `w.cfg` đang chạy |
| Route nền hỏng (F-P02-1) | không ghi transcript row ⇒ replay miss ⇒ trượt cổng dù artifact sạch | **đã sửa** (`minds/real.py`): 10 row lỗi ⇒ replay `misses=0, unused=0`, hash trùng |
| Test / lint / verify_local | 308 passed · clean · — | ⚠️ **ĐO CŨ: 325 passed.** Sau khi `test-engineer` thêm bộ độc lập: **5 failed / 463 passed** (A-01) |

`catalog_hash()` = `795188c725fc971f069ed01cd375888f756a8d12772500a2e874456f8e8d3ff4` (38 descriptor).

> ## ⛔ ĐÍNH CHÍNH SAU INDEPENDENT GATE — bảng trên là ĐO CŨ, KHÔNG phải trạng thái hiện hành
>
> `adversarial-reviewer` và `reproducibility-steward` (độc lập, không viết code) **cùng FAIL P0**.
> Ba đính chính bắt buộc cho chính bảng này:
>
> 1. **"325 passed" là SAI.** Đó là phép đo TRƯỚC khi `test-engineer` thêm bộ test độc lập. Thật sự:
>    **5 failed / 463 passed** (A-01 / F-P03-0). Gate đang tự-báo-xanh dựa trên số liệu cũ.
> 2. **`p0check_resume` KHÔNG diễn tập con bệnh nó chữa.** `journal_recovery.jsonl` ghi
>    `bytes_truncated: 0, records_truncated: 0` ⇒ đó là **dừng êm rồi resume**; tail mồ côi **chưa hề có mặt**.
>    Nó chứng minh rebase counter + hash continuity, **KHÔNG** phải minh chứng cấp-artifact của JOURNAL-1/3 (A-09).
>    **Bằng chứng THẬT**: `tests/test_resume_journal.py` (kill giữa tick) và run của `reproducibility-steward`
>    (`repro_rb_ngat`: **293 event mồ côi bị cắt**, vẫn ra đúng hash run liền `a1fb65f2cb2d6786`).
> 3. **False-green CÒN SÓT** (A-03): `--quick` và mock `p_malformed>0` vẫn in `ĐỦ BẰNG CHỨNG ✅` + exit 0
>    ngay cả khi `artifact_status = diagnostic_only_unreplayable`. Và **`p0check_*` chạy với `p_malformed=0.05`**
>    ⇒ với chúng `replay_from_transcript` là **WARN, không phải gate**.
>
> **Claim boundary hiện hành:** **KHÔNG được tuyên bố `technical-ready`.** G1 (parity) và G8 (suite) ĐỎ.
> Report_v2 §5: *"Không đạt một mục = dừng P1."*

> ⚠️ **F-28 (priming) CHƯA ĐƯỢC SỬA** — thuộc P3.1, không thuộc P0. Chừng nào prompt còn trao sẵn
> thang utility, còn demo cấy rẽ 40%, còn nói "Mọi trao đổi tính bằng thóc", và còn gọi agent là
> "địa chủ", thì **MỌI claim về emergence (nghề, tiền, phân tầng, định chế) đều KHÔNG bảo vệ được**,
> bất kể gate xanh đến đâu.

---

## 0. Bằng chứng đã CHẠY THẬT (read-only, `THOC_BLOCK_NETWORK=1`)

| Lệnh | Output | Kết luận |
|---|---|---|
| `pytest -q` (baseline, trước mọi thay đổi) | `308 passed, 1 skipped in 134.67s` | baseline xanh |
| `ruff check .` (baseline) | `All checks passed!` | baseline sạch |
| `python -m tools.verify_research_run real60_spatial` | 8×PASS, `[SKIP] replay_world_hash — bỏ qua (mode=real cần transcript)`, `KẾT QUẢ: ĐỦ BẰNG CHỨNG ✅`, **exit 0** | **F-06 XÁC NHẬN — false-green** |
| `python -m tools.verify_research_run real60_spatial --quick --json` | `ValueError: too many values to unpack (expected 3)` @ `tools/verify_research_run.py:240` | **F-07 XÁC NHẬN** |
| audit đọc `data/runs/real60_spatial/` (không sửa) | events: 230 dòng trùng khít, 1 tick regression @ dòng 4158 (117→106); transcript: 1595 rows / 1192 distinct `call_id` ⇒ **403 call_id bị dùng lại**; llm_calls: 1589 rows ≠ 1595 | **F-05 XÁC NHẬN** |
| audit sâu (model-architect) | 3 journal dừng ở **3 tick khác nhau** sau cùng một lần kill: events→117, llm_calls→118, transcript→119. **9 `prompt_hash` trùng giữa tail mồ côi và segment 2, cả 9 có response KHÁC NHAU.** | Cơ chế lệch hash được **chứng minh**, không còn là suy đoán |

**Hệ quả của F-06 (nêu to):** mọi phát biểu dạng "verify_research_run đã pass cho real60_spatial"
là **vô hiệu về mặt bằng chứng**. Đây đúng là pattern FAIL→PASS-bằng-diễn-giải mà charter cấm,
chỉ khác là nó đã được **tự động hóa**.

**Hệ quả của 3-tick-khác-nhau:** không heuristic quét nội dung nào tìm được điểm cắt an toàn.
Chỉ byte-offset ghi tại thời điểm checkpoint (sau flush+fsync) là hợp lệ. ⇒ manifest là **bắt buộc**,
không phải tiện lợi.

---

## 1-quinquies. P1 LANDED (residence + estate) — 2026-07-13

`pytest` **584 passed, 1 skipped, 0 failed** · `ruff` clean · `verify_local` XANH ·
**3 hash pin legacy BẤT BIẾN** (parent verify độc lập TRƯỚC + SAU).

Bệnh được chữa, và test **tự chứng minh non-vacuous**:
`test_case_a0051_khong_chet_doi` được **parametrize**: gate **TẮT** ⇒ **assert người vừa 16 tuổi VẪN
CHẾT ĐÓI** (bệnh còn nguyên); gate **BẬT** ⇒ không chết. Nếu ai đó "sửa" bệnh bằng cách nới test, nhánh
OFF sẽ đỏ.

| Finding | Trạng thái |
|---|---|
| F-18 adult-orphaning | **FIXED** — residence là state bền (`w.cu_tru`), trưởng thành KHÔNG còn là biến cố tách hộ |
| F-19 `VO_THUA_NHAN` absorbing sink | **FIXED** — `DI_SAN:<aid>` có hạn; **E1′ (no absorbing sink / no renamed sink)** kiểm mỗi tick trong `kiem_toan_the_gioi`. Nó **bắt được chính test fixture của engine-surgeon** (một người chết còn ôm 194 kg) ⇒ invariant SỐNG, không phải trang trí |
| F-20 nợ chết theo con nợ | **FIXED** — nợ settle TỪ estate TRƯỚC khi heir nhận |
| F-36 sink đổi tên (`het_han:"cong"`) | **FIXED** — chặn fail-closed ở `tao_the_gioi` |
| F-22 hash trap (`Agent` dataclass) | **TRÁNH ĐƯỢC** — state ở World-level `w.cu_tru`, block hash chỉ chèn khi gate ON |

### Finding MỚI của P1 (quan trọng)

| ID | Sev | Finding |
|---|---|---|
| **F-P1-3** | **BLOCKER (đã sửa)** | **Legacy KHÔNG chỉ "nợ chết theo con nợ" — nó còn có NỢ THỪA KẾ IM LẶNG.** `thua_ke_mac_dinh` chuyển token `vi_the:<hd>:<A>` cho heir như một tài sản di động ⇒ `_ben_mat` = False ⇒ hợp đồng **SỐNG SÓT** và một nghĩa vụ **300 kg âm thầm rơi xuống đầu một đứa trẻ 10 tuổi**. F-20 ("nợ chết") chỉ là nhánh **không-có-heir**. Cả hai đã tái hiện trong test, cả hai đã sửa |
| **F-P1-1** | **BLOCKER (spec)** | **INVARIANT P-1 trong ADR 0007 §B.3 là SAI ở mức bit.** ADR tuyên bố bật riêng `ho.cap_luong_thuc` cho `world_hash` Y HỆT. Chứng minh của ADR ở mức GIÁ TRỊ; nhưng `world_hash` băm `float.hex()` và cộng IEEE-754 **không kết hợp**. Legacy áp **một** delta `-tru`; provisioning áp `-x₁, -x₂, …`. Đo được: base/seed 11/**tick 4**, `('A0042','thoc')` OFF=`977.4906109560651` vs PROV=`977.4906109560652` (**1 ULP**). Đây là **bất khả tránh một cách trung thực**: một người vừa nuôi người khác vừa ăn từ cùng một lần rút *bắt buộc* sinh ≥2 dòng ledger. engine-surgeon **GIỮ** `cap_luong_thuc` trong behavioral config thay vì gỡ nó ra — gỡ ra sẽ cho **hai quỹ đạo khác nhau CÙNG một config identity** (false-equivalence cho replay). ⇒ ADR 0007 §B.3 + §G.4 phải được **sửa công khai**, không âm thầm |
| **F-P1-2** | **BLOCKER** | `tach_ho` / `yeu_cau_di_san` **chưa có đường LLM**. engine-surgeon **CHỦ ĐỘNG TỪ CHỐI** thêm field `KeHoach` mồ côi — `test_cap2_khong_co_field_kehoach_mo_coi` (P0) **đỏ ngay khi họ thử** ⇒ **cổng P0 đang làm đúng việc, chặn tái phát F-02**. ⇒ **KHÔNG được claim gì về hành vi tách hộ** cho tới khi descriptor ship |
| **F-P1-4** | MAJOR (open) | `engine/entities.py:254` `thanh_ly` dùng `tong_no` làm mẫu số vô điều kiện ⇒ **một chủ nợ đơn độc nuốt 100% tài sản bất kể quy mô claim**. Estate mới dùng `max(Σno, giá_trị_estate)` (đúng); `entities.py` vẫn sai |

---

## 1-quater. ⭐ FROZEN SERIAL GATE RUN — bằng chứng P0 chính thức

> Đáp ứng **N-01** của `adversarial-reviewer` vòng 2: *"một cái gate là phát biểu về artifact ĐÓNG
> BĂNG; cái trước đó là một cuốn phim."* Tree được đóng băng, không sửa gì trong lúc chạy, chạy
> **MỘT LẦN, TUẦN TỰ**, không có gì khác chạy song song.

### Tree fingerprint (sha256, 16 ký tự đầu)

```
minds/prompts.py               ca78efb9db838bcc      engine/journal.py              9ecefb0e53d7315a
minds/capabilities.py          0d690d3f94ac9819      engine/events.py               7987e5ff84594211
minds/real.py                  dfa9e9ec72228c4e      run.py                         10b554435d237084
minds/transcript.py            50c1ddd13fe088b2      tools/replay.py                0d7cc4b8aa6395a4
minds/gateway.py               e7c8fbb44e1a496b      tools/verify_research_run.py   340253facbdf19f5
                                                     tools/experiments.py           2625b33f4c6dd260
catalog_hash() = 1926b8811298545b40d719bb7f206f83e19aff40208e916b7c93293df60a392f
```

### Kết quả

```
===== 1/4  pytest =====      553 passed, 1 skipped, 0 failed  (232.51s)
===== 2/4  ruff =====        All checks passed!
===== 3/4  verify_local ===== [ruff] PASS · [pytest] PASS · [scenario_validation] PASS
                              [smoke_run] PASS · [verify_research_run] PASS      KẾT QUẢ: XANH ✅
===== 4/4  verify_research_run — TOÀN BỘ 19 run trong data/runs =====
RUN                                      EXIT   ARTIFACT_STATUS
p0gate_mock                              0      replay_verified          ← run liền
p0gate_resume                            0      replay_verified          ← KILL THẬT + resume
verify_local_agrarian_transition_v1_s41  0      replay_verified
real60_spatial                           1      diagnostic_only_unreplayable   ← ĐÚNG: bị từ chối
repro_recov                              1      diagnostic_only_unreplayable   ← --recover-journal hạ cấp VĨNH VIỄN
mock60_spatial / p0check_* / repro_{rb,mock,sp}_* 1   skipped_version_mismatch  ← ĐÚNG: cũ hơn interface
repro_fc_*                               1      pending_verification           ← artifact fail-closed test (cố ý hỏng)
```

**Đọc bảng này cho đúng:** dự án có **3 artifact `replay_verified`** — và cả ba đều là **mock 30 tick**.
Con số `1` ở mọi hàng khác **KHÔNG phải lỗi**; đó là gate đang **làm đúng việc của nó**: từ chối artifact
không replay được và từ chối artifact cũ hơn interface hiện tại.

**Nhãn được phép sau lần chạy này: `technical-ready` — VÀ KHÔNG GÌ HƠN.**

---

## 1-ter. SAU KHI SỬA BLOCKER (2026-07-13, đo bởi parent)

| Cổng | Kết quả |
|---|---|
| `pytest -q` | **477 passed, 1 skipped, 0 failed** (trước fix: 5 failed / 463 passed) |
| `ruff check .` | clean |
| `tools.verify_local` | **XANH ✅ 5/5** (ruff · pytest · scenario_validation · smoke_run · verify_research_run) |
| `verify_research_run real60_spatial` | exit **1** · `diagnostic_only_unreplayable` |
| `verify_research_run mock60_spatial --quick` | exit **2** · `CHƯA CHỨNG MINH ⏸ (pending_verification)` — **KHÔNG còn in "ĐỦ BẰNG CHỨNG ✅"** (A-03 CLOSED) |
| Prompt nêu recipe `xu` | **CÓ** — base + spatial đều nêu đủ `quang_dong=1, cong=5, ra=10`. Fix **tổng quát hóa**: MỌI recipe render dạng "input → output mỗi lần chế" (A-02 CLOSED) |
| `real60_spatial` / `mock60_spatial` | `git status --porcelain` **rỗng** — byte-identical, KHÔNG bị đụng |

### ⭐ Bằng chứng resume THẬT (thay cho `p0check_resume` yếu — đóng A-09)

`p0gate_resume` = **kill THẬT giữa run** rồi resume, `p_malformed=0.0` (⇒ `replay_from_transcript` là gate **HARD**):

```json
{"kind":"truncate_on_resume","from_tick":15,"from_segment_id":0,"new_segment_id":1,
 "bytes_truncated":498261,"records_truncated":1137,"rows_superseded":195,
 "files_moved":["checkpoints/orphans/seg0000_after_tick0015/events.jsonl",
                "checkpoints/orphans/seg0000_after_tick0015/transcript.jsonl"]}
```

| run | p_malformed | world_hash | artifact_status | exit |
|---|---|---|---|---|
| `p0gate_mock` (30 tick LIỀN) | 0.0 | `2c32ea9c4be16a96…` | `replay_verified` | 0 |
| `p0gate_resume` (kill + resume) | 0.0 | **`2c32ea9c4be16a96…`** (BẰNG NHAU) | `replay_verified` | 0 |

⇒ Con bệnh **CÓ MẶT THẬT** (1137 bản ghi mồ côi), được **cách ly chứ không xóa**, và run resumed vẫn tái
lập **bit-for-bit** hash của run liền — dưới một cổng **CỨNG**. Đây mới là minh chứng cấp-artifact của
JOURNAL-1/JOURNAL-3. (Bằng chứng độc lập song song: `repro_rb_ngat` của `reproducibility-steward` cắt
**293** event mồ côi, cùng ra hash `a1fb65f2cb2d6786` của run liền.)

---

## 1-bis. INDEPENDENT GATE RESULTS (2026-07-13) — `adversarial-reviewer` + `reproducibility-steward`

**Verdict cả hai: P0 FAIL.** Đầy đủ ở `docs/reviews/P0-adversarial-review.md` và
`docs/reviews/P0-reproducibility-steward.md`.

| ID | Sev | Finding | Owner | Status |
|---|---|---|---|---|
| **A-01 / F-P03-0** | **BLOCKER (G8)** | `pytest` ĐỎ: **5 failed / 463 passed**. Con số "325 passed" trong ledger là phép đo TRƯỚC khi test-engineer thêm bộ độc lập ⇒ gate tự-báo-xanh trên số liệu cũ | parent + `minds-engineer` + `engine-surgeon` | **FIXING** |
| **A-02 / F-P03-0** | **BLOCKER (G1)** | **Recipe đúc xu KHÔNG BAO GIỜ được nói cho agent, trong khi action VẪN được quảng cáo.** `config/world.yaml:32` `xu: {quang_dong:1, cong:5, ra:10}`; `engine/production.py:411-421` thi hành; `minds/capabilities.py:787-799` `_gt_xay` render `mon` từ `sorted(recipe)` ⇒ **có `"xu"`** nhưng chỉ nêu chi phí `cong_cu` + `nha`. ⇒ **Agent được mời "đúc xu" với KHÔNG chi phí, KHÔNG sản lượng nào công bố, và phải ĐOÁN.** `reports/real60_evaluation.md` §2 ghi `đúc xu 0 (real) / 1738 (mock)` ⇒ **interface-confounded**. **`duc_xu` LÀ kênh đúc tiền — chính cơ chế tiền-tệ-tự-phát mà dự án tuyên bố đang đo. Hành động DUY NHẤT đúc ra tiền lại là hành động mà prompt giấu kinh tế học của nó.** Lý do interface-confound ĐỘC LẬP THỨ BA (sau F-01 sai vật lý, F-02 orphan capability) | `minds-engineer` | **FIXING** |
| **A-03** | **BLOCKER (G9)** | **False-green CÒN SÓT** — cùng cơ chế F-06, đổi chỗ. `Ket.failed()` chỉ fail khi `ok is False and hard`; `artifact_status` tính riêng ⇒ **bất đồng, exit code nghe cái sai**. (i) `--quick` ⇒ SKIP → `ok=None` → `ĐỦ BẰNG CHỨNG ✅` + exit 0. (ii) mock `p_malformed>0` ⇒ `hard=False` ⇒ in `diagnostic_only_unreplayable` **VÀ** `ĐỦ BẰNG CHỨNG ✅` **VÀ** exit 0 dù replay ra thế giới KHÁC. ⚠️ `p0check_*` chạy `p_malformed=0.05` ⇒ bằng chứng đầu bảng tựa vào check KHÔNG cưỡng chế | `engine-surgeon` | **FIXING** |
| **A-04** | **PERMANENT BAN** | **F-28 CÒN NGUYÊN + kênh thứ 5 MỚI.** Ngoài 4 kênh đã biết, phát hiện **(e) engine tự tay gợi ý THUÊ NHÂN CÔNG**: `minds/prompts.py:276-281` — khi `recipe.nha.cong > ngay_cong_moi_tick` (ĐÚNG ở MỌI config đã ship: 240>180 base, 240>120 spatial) prompt nói *"cần người góp công (…hoặc **thuê thợ bằng hợp đồng `gop_cong`**)"* ⇒ **engine BẢO agent đi thuê lao động làm công, rồi dự án hỏi lao động làm công có tự phát không.** Đính chính: F-28(c) `prompts.py:82` là **dead code** (`build_system` không caller); mồi numéraire SỐNG là `prompts.py:441` `"Đơn vị giá trị: kg thóc."` | P3.1 | **OPEN — CẤM MỌI CLAIM EMERGENCE** |
| **A-05 / F-P02-2** | **MAJOR (vi phạm điều luật #4)** | `config_sha256` **KHÔNG đơn ánh trên hành vi**. Phản ví dụ đã chạy: cùng digest `151c58e9ba25`, cùng `world_hash` t0, **quỹ đạo phân kỳ ở tick 28**. Site duy nhất: `engine/economy.py:43` + `engine/consumption.py:60`. Fix ĐÚNG (không phải `sorted()` — alphabet là lựa chọn hành vi tùy tiện): khóa config tường minh `thu_tu_an: [ngo, khoai]` để nó VÀO digest | `spec-governor` + `model-architect` | OPEN |
| **A-06 / F-P03-1** | **MAJOR** | `capability_catalog_hash` THIẾU ở `engine/journal.py:68-74` `JournalIdentity` ⇒ **cổng identity của RESUME không thấy catalog drift**. `prompt_template_hash = sha256(minds/prompts.py)` KHÔNG phủ `minds/capabilities.py` (nơi giờ chứa menu + wire contract). Sửa catalog giữa 2 segment ⇒ resume VẪN chạy ⇒ artifact "hai-nửa-hai-luật". Replay đã được bảo vệ; **chỉ resume hở** | `engine-surgeon` | **FIXING** |
| **A-07** | MAJOR | `artifact_ledger.md:22` CŨ: `mock60_spatial` giờ là `skipped_version_mismatch` (exit 1), không phải `replay_verified` | `research-artifact-integrity-auditor` | OPEN |
| **A-08** | MAJOR | F-33 **KHÔNG tái hiện** trên code hiện tại (probe 120 tick: 0 miss/0 unused/hash match). Nguyên nhân = **version drift**, không phải defect thứ hai. NHƯNG 686 miss của mock60 vẫn **chưa root-cause**. ⚠️ **Và mock transcript `prompt_hash` khóa theo `(agent_id, tick)` — ZERO world state** (`minds/orchestrator.py:274-275`) ⇒ replay transcript mock **gần như tautology**, **về cấu trúc bất khả** để bắt lớp defect F-33 | `reproducibility-steward` | DOWNGRADED → MAJOR-with-carry |
| **A-09** | MAJOR | **Bằng chứng resume đầu bảng chưa từng diễn tập con bệnh.** `p0check_resume`: `bytes_truncated=0, records_truncated=0` ⇒ dừng êm, không có tail mồ côi. Bằng chứng THẬT: `tests/test_resume_journal.py` (kill giữa tick) + `repro_rb_ngat` (**293 event mồ côi bị cắt**, vẫn ra đúng hash run liền) | parent | **ĐÃ ĐÍNH CHÍNH** |
| **A-10** | MAJOR | Ledger tự mâu thuẫn (§dòng 8 vs §0-bis); `reports/final_handoff.md:67` + `reports/world_class_readiness.md:38-39` tuyên bố "research-ready phần lớn ĐẠT" — mâu thuẫn trực tiếp `Report_v2.md` | `integration-manager` | **ĐÃ ĐÍNH CHÍNH ledger**; 2 report cần banner |
| **A-11** | MINOR | `cost_accounting_split` (`verify_research_run.py:245`) là **tautology** (`burned=COUNT(*) >= effective=COUNT(superseded=0)` luôn đúng) nhưng được in như bằng chứng ở mọi PASS | `engine-surgeon` | **FIXING** |
| **A-14** | MINOR | `kiem_lien_tuc` KHÔNG soi `unrecognized_intents.jsonl` (journal thứ 5) ⇒ đúng cách 1 bản ghi mồ côi tick 109 của real60 lọt lưới | `engine-surgeon` | **FIXING** |
| **F-P03-2** | MAJOR | Output isolation một phần: chạy lại cùng `--run-name` **âm thầm ghi đè** `run_meta`/`manifest`/`metrics` và để `.pkl` run cũ không nhãn ⇒ mất chính bằng chứng cần để biết cái gì đã bị phá | `engine-surgeon` | OPEN |
| **F-10** | — | **PHÁN QUYẾT: (a), RATIFIED.** Tiền đề F-10 đã CŨ — pool **ĐÃ NẰM TRONG `world_hash`** tại `engine/world.py:563-568` (`"commons": {fish_stock, wild_chicken_stock}`), verified bằng mutation. ADR 0005 §216-222 + bảng §334 **mâu thuẫn code**, phải supersede. **Hệ quả P2: forest biomass BẮT BUỘC vào hash** (nó điều khiển hành vi mạnh hơn `ca_ton`); **F-17 mới là bẫy P2 thật và vẫn OPEN** — phải sửa OFF-projection whitelist + bump `behavioral-state-v3` **TRƯỚC** khi thêm `Parcel.sinh_khoi` | `reproducibility-steward` | **RESOLVED (a)** |
| **F-P02-1** | — | Route nền hỏng không ghi transcript row | parent (`minds/real.py`) | **CLOSED** (verified độc lập) |

### Cái reviewer TẤN CÔNG mà KHÔNG phá được (ghi vào biên bản — đây là việc thật)
- **Test KHÔNG bị nới/xóa/skip.** 302 test fn ở HEAD → 319; **0 cái bị gỡ**. `TU_MOM`/`TEN_DINH_CHE_CAM` giữ nguyên từng chữ.
- **Catalog KHÔNG lén xếp hạng nghề** (đọc cả 38 descriptor): không điểm ưu tiên, không ranking, không tính từ chuẩn tắc. Menu vẫn xáo theo `w.rng`.
- **Hash legacy BẤT BIẾN 3/3 + golden.** F-35 là **FIX, không phải hồi quy**: rulebot bypass `translate` nên hash spatial của nó không đổi; chỉ mock+`hai_bo` đổi vì ferry intent mà `translate` từng nuốt im lặng nay tới được wire.
- **`llm_calls` KHÔNG row nào bị DELETE**; `--recover-journal` KHÔNG BAO GIỜ làm run xanh.
- **`real60_spatial` KHÔNG bị retcon**, run dir byte-identical.
- **Zero provider call trong replay** — chứng minh bằng socket guard + monkeypatch `httpx.send`, không phải giả định.

---

## 1. Findings register

| ID | Sev | Finding | Evidence | Owner | Đóng bởi | Status |
|---|---|---|---|---|---|---|
| F-01 | BLOCKER | `LUAT_VAT_LY` tĩnh: "6 tháng", 90/45kg, 180 công, mùa lẻ/chẵn, 60kg giống+60 công, ~650kg, nhà 240 công — overlay chạy 4 tháng, 60/30kg, 120 công, 40/40, 300kg, `[lua_1,lua_2,dong]`. Agent nhận **luật vật lý sai** | `minds/prompts.py:241-279` vs `scenarios/agrarian_transition_v1/spatial_v1.yaml:14-31` | P0.1 `minds-engineer` | `test-engineer` + `adversarial-reviewer` | OPEN |
| F-02 | BLOCKER | **Capability mồ côi bất đối xứng**: `dong_thuyen`/`rao_do`/`qua_song` có ở `engine/intents.py:50-52`, thật sự chạy ở `engine/spatial.py:112`, **và rulebot phát ra chúng** (`minds/rulebot.py:366-396`) — nhưng KHÔNG có trong `LOAI_HANH_DONG`, KHÔNG có handler translate, KHÔNG có trong menu. ⇒ **rulebot chạy được kinh tế đò; LLM không gọi nổi tên nó.** Mọi so sánh LLM-vs-rulebot về đa dạng sinh kế là **interface-confounded** | `engine/intents.py:50-52`; `engine/spatial.py:112`; `minds/rulebot.py:366-396`; `minds/schemas.py:14-20`; `minds/prompts.py:169-209` | P0.1 | `test-engineer` + `adversarial-reviewer` | OPEN |
| F-03 | MAJOR | `khai_hoang` mồ côi NGƯỢC CHIỀU: có schema + translate + văn xuôi nhưng **không có ví dụ JSON** trong `MUC_HANH_DONG` ⇒ LLM phải đoán tên trường `thua` | `minds/prompts.py:128,169-209` | P0.1 | `test-engineer` | OPEN |
| F-04 | MAJOR | `dat_lenh` menu hardcode `go\|cong_cu\|quang_dong\|xu\|nha\|thoc\|co_phan:E0001\|<mã hàng>` — thiếu `ngo`,`khoai`,`ga`,`ga_con`,`thit`,`ca`,`thuyen`. Parity test phải assert **hai chiều** | `minds/prompts.py:181-182` | P0.1 | `test-engineer` | OPEN |
| F-05 | BLOCKER | Resume phá replay: `run.py:206-224` nạp checkpoint tick N nhưng **không truncate tail**; `minds/transcript.py:51-52` mở `"a"` với `_n=0` ⇒ call_id lặp từ 1; segment bỏ dở còn nằm trong transcript ⇒ FIFO theo `prompt_hash` trả response phiên-1 ⇒ **lệch hash** | `run.py:206-224`; `minds/transcript.py:51-52`; audit artifact | P0.2 `engine-surgeon` | `reproducibility-steward` + `test-engineer` | OPEN |
| F-06 | **CRITICAL** | **Gate phát false-green trên artifact không replay được.** `verify_research_run.py:199-200` SKIP replay khi mode≠rulebot/mock; SKIP lưu `ok=None`; `Ket.failed()` (`:49-50`) chỉ fail khi `ok is False` ⇒ in `ĐỦ BẰNG CHỨNG ✅` và **exit 0** | executed (§0) | P0.2 | `reproducibility-steward` + `adversarial-reviewer` | OPEN |
| F-07 | MAJOR | `verify_research_run.py:240` unpack 3 phần tử từ `Ket.add`'s 4-tuple (`:46-47`) ⇒ `--json` luôn ValueError ⇒ output máy-đọc-được của gate đã chết | executed (§0) | P0.2 | `test-engineer` (regression test `--json`) | OPEN |
| F-08 | MAJOR | ADR 0005 tự mâu thuẫn về calendar: §8 (banner SUPERSEDED, 3 mùa) vs §17/§18 ("GIỮ 2 tick/năm") | `docs/adr/0005:246-248` vs `:542,557,573` | `spec-governor` | `adversarial-reviewer` | **RESOLVED** — ADR 0006 §D.2: §8 thắng; banner tại chỗ trên §17/§18 |
| F-09 | MAJOR | ADR 0003 "hộ = derived view, không pantry" vs Report_v2 §4.2 "residence là state bền" | `docs/adr/0003:68-79` vs `Report_v2.md:113-121` | `spec-governor` | `adversarial-reviewer` | **ROUTED** — ADR 0006 §D.3: không mâu thuẫn luật, chỉ thời điểm; **ADR 0007 là tiền điều kiện của P1** |
| F-10 | MAJOR | Pool sinh thái (`ca_ton`, `ga_rung_ton`) NGOÀI `world_hash` vs Report_v2 §2.6 ("mọi state ảnh hưởng lựa chọn sau vào world_hash") | `docs/adr/0005:216-222,334` vs `Report_v2.md:59-61` | `reproducibility-steward` (P2.5) | `adversarial-reviewer` | OPEN — **phải quyết TRƯỚC khi làm forest biomass (P2.1)** |
| F-11 | INFO | ADR 0005 §11.2 nói overlay ở `.../overlays/spatial_v1.yaml`; đường thật là `scenarios/agrarian_transition_v1/spatial_v1.yaml` | `docs/adr/0005:344-346` | — | — | INFO |
| F-12 | MAJOR | `unrecognized_intents.jsonl` (`engine/world.py:399-406`) là **journal thứ 5** cùng bệnh resume — thiếu trong brief ban đầu | `engine/world.py:399-406` | P0.2 | `test-engineer` | OPEN |
| F-13 | OPEN QUESTION | `tools/analyze.py`, `calibrate.py`, `reality_check.py` đã đọc events của `real60_spatial` với bản ghi trùng. Có con số nào trong `reports/` hay `Report_v2.md` mang nhiễm bẩn này không? | model-architect | `research-artifact-integrity-auditor` | `adversarial-reviewer` | OPEN |
| F-14 | **BLOCKER** | **Rò rỉ khai thác bờ kia — đò không có mục đích kinh tế.** `engine/production.py:361-363` gate gỗ/quặng bằng `any(p.loai == loai_o for p in w.parcels.values())` — một kiểm tra **TOÀN CỤC** ("thế giới có ô rừng/mỏ nào không") — KHÔNG kiểm bờ, KHÔNG kiểm sở hữu, KHÔNG kiểm khoảng cách. Đối chiếu `engine/chan_nuoi.py:84-87` `bat_ga` ĐÚNG: `co_the_o_bo(w, aid, p.bo)`. ⇒ Agent ở bờ `dan_cu` khai thác gỗ + quặng đồng của bờ `hoang` **mà không cần thuyền**. Probe (spatial-ecology, seed 7): **2/2 ô `mo_dong` nằm ở bờ `hoang`**, nhưng agent có `co_the_o_bo(...,"hoang")==False` vẫn thu `go=25.0`, `quang_dong=12.5`. **Xác nhận độc lập bởi parent.** ⇒ "Không ai làm nghề đò" KHÔNG phải kết quả hành vi — đò vốn không có lý do tồn tại về kinh tế | `engine/production.py:361-363` vs `engine/chan_nuoi.py:84-87` | P2.3 `engine-surgeon` | `reality-auditor` + `test-engineer` | OPEN |
| F-15 | MAJOR | Clamp im lặng: `engine/chan_nuoi.py:201-208` cắt `ton` về K (và K=0 ⇒ `ton=0`) **không có event** ⇒ mất bằng chứng pool bị hủy | `engine/chan_nuoi.py:201-208` | P2.2 | `test-engineer` | OPEN |
| F-16 | MAJOR | Crop card thiên lệch ngầm: `minds/prompts.py:110-117` hiện chỉ show `san_luong_kg` thô (ngô 280 / khoai 333) mà **bỏ `quy_doi_dinh_duong`** (0.9 vs 0.7). Food-equivalent thật: ngô 252 > khoai 233 — **con số duy nhất hiển thị ĐẢO NGƯỢC thứ tự thật**. Đây không phải fact card trung lập mà là tập dữ kiện KHUYẾT gây xếp hạng sai | `minds/prompts.py:110-117`; `engine/production.py:321-329` | P2.4 / P3.3 | `adversarial-reviewer` | OPEN |
| F-18 | **BLOCKER** | **Adult-orphaning tái lập ở CẢ rulebot ⇒ không phải hành vi LLM.** `engine/world.py:455` (`not c.truong_thanh(tt)`) văng người vừa 16 tuổi khỏi hộ; `engine/consumption.py:50,63-70` ăn theo đúng cái hộ đó. Dữ liệu: `real60_spatial` vùng CHƯA nhiễm resume (tick ≤105) — 2/17 ca chết là `chet_doi`, **cả hai 17.7 và 18.3 tuổi**; **3/3** agent từng `an_doi` có event đói ĐẦU TIÊN rơi đúng tick trưởng thành ±1 (A0051: sinh t=47 → trưởng thành t=95 → `an_doi` t=95 `ty_le_no=0.0` → chết t=100), trong khi cha mẹ giữ 3429.8 / 3329.6 kg. **`mock60_spatial` (PersonaBot heuristic, KHÔNG LLM, cùng seed/config): 159/168 = 94.6%** agent sinh-trong-sim có `an_doi` đầu tiên trong ±1 tick quanh sinh nhật 16 ⇒ **policy-independent** | `engine/world.py:433-457`; `engine/consumption.py:50,63-70`; artifact | P1.2 | `test-engineer` + `adversarial-reviewer` | OPEN |
| F-19 | **BLOCKER** | **`VO_THUA_NHAN` là absorbing sink nuốt nền kinh tế.** Checkpoint tick 180: giữ **41 329 kg thóc = 92.5% toàn thế giới**, `khoai` 98.1%, `go` 94.9%, **`ga` 100%**, **`nha` 1.0/1.0 — căn nhà DUY NHẤT của thế giới**. 2 người sống sót vô gia cư vĩnh viễn. ⇒ 92.5% của cải nằm ngoài tầm với của **MỌI** policy | checkpoint `real60_spatial` tick 180 | P1.3 | `test-engineer` + `reality-auditor` | OPEN |
| F-20 | **BLOCKER** | **Nợ chết theo con nợ.** `engine/contracts.py:423-425`: `if dao_han or ben_chet: trang_thai="huy"` + `dot_vi_the`, **KHÔNG settlement**. Thứ tự tick: hợp đồng `tick.py:222` chạy TRƯỚC chết/thừa kế `tick.py:242` ⇒ chủ nợ **không bao giờ** đòi được; heir hưởng tài sản **sạch nợ** | `engine/contracts.py:423-425`; `engine/tick.py:222,242` | P1.3 | `test-engineer` | OPEN |
| F-21 | **CRITICAL** | **`events.jsonl` của `real60_spatial` chứa HAI lịch sử phản-thực ở tick 106–117.** Event `chet` lặp: A0031@106, A0053@110, A0003@112; **A0054 chết ở CẢ tick 116 lẫn 118**. ⇒ **mọi death rate / mortality / life-table tính từ file đó SAI THEO ĐỊNH NGHĨA**, không phải sai số. Đây là câu trả lời trực tiếp cho F-13 | `data/runs/real60_spatial/events.jsonl` | P4 | `research-artifact-integrity-auditor` | OPEN |
| F-22 | **BLOCKER (hash trap)** | Thêm field vào dataclass `Agent` sẽ **đổi hash của MỌI run legacy**: `engine/world.py:515` `"population": self.agents` + `_canonical_state` duyệt `fields()`. ⇒ residence **KHÔNG được** là `Agent.residence_id`; phải là World-level `w.cu_tru` với key chỉ chèn vào `behavioral_state()` khi gate ON | `engine/world.py:515`, `:38-42` | P1.2 | `reproducibility-steward` | OPEN |
| F-23 | HIGH | **Không có metric nhân khẩu nào.** Grep toàn repo: 0 match `life_expectancy\|tuoi_tho` trong `engine/`, `tools/`, `observatory/` ⇒ chưa có file:line nào phạm lỗi "gọi tuổi TB người sống là life expectancy" — nhưng cũng **chưa có life table nào cả** | grep | P4 | `empirical-validation` | OPEN |
| F-24 | **BLOCKER (anti-teleology)** | **Nhãn giai cấp quay ngược vào prompt — Lớp-5 → Lớp-4.** `engine/tick.py:322` `w.phan_loai = obs["phan_loai"]` (observatory); `minds/prompts.py:391` `nhan = GIAI_CAP_VN.get(phan_loai.get(a.id))` → `_cau_can_tinh` render **"Bạn là địa chủ 34 tuổi"** ở ĐẦU khối riêng. Comment `tick.py:321` biện hộ "engine KHÔNG rẽ nhánh theo nhãn này" — đúng chữ (engine không branch) nhưng **sai tinh thần**: prompt LÀ input của Lớp-4. Charter §3 dòng 69-71: "Nhãn KHÔNG được quay lại điều khiển engine". Report_v2 §5 P3 acceptance đòi "≥2 sinh kế khả thi **without any job label being assigned**". ⇒ **Mô hình GÁN NGHỀ cho agent rồi hỏi nghề có tự phát sinh không.** Xác nhận độc lập bởi parent | `engine/tick.py:321-322`; `minds/prompts.py:362-397` | P3.1 | `adversarial-reviewer` + `reality-auditor` | OPEN |
| F-25 | **BLOCKER** | **Mock KHÔNG BAO GIỜ đọc prompt** ⇒ Report_v2 P3.5 ("benchmark LLM interface only with mock/FakeTransport fixtures") **không thực hiện được** với `MindMock` hiện tại. `minds/orchestrator.py:274-275`: mode mock dựng prompt GIẢ `f"[mock 1-to-1] id={aid} tick={w.tick}"`; PersonaBot quyết từ `ctx`, không từ text. `MockProvider` không có `goi_agentic`; `dung_cong_cu` yêu cầu `not self._tuan_tu` ⇒ **mock chưa bao giờ chạy vòng công cụ, chưa bao giờ đọc fact card**. Cần `ScriptedPromptBot` mới | `minds/orchestrator.py:274-282`; `minds/gateway.py:76-86` | P3.5 | `test-engineer` | OPEN |
| F-26 | **MAJOR (cổng tái lập thủng)** | **Transcript replay MÙ với tool layer.** `minds/transcript.py:20-26` tự khai: vòng công cụ ghi **1 entry/agent** (prompt đầu + quyết định cuối); `TranscriptProvider.goi_agentic:134-136` trả thẳng quyết định theo `prompt_hash`. ⇒ Sửa `minds/world_tools.py` xong, replay **vẫn ra đúng world-hash** và `--verify` vẫn XANH, dù **information set của agent đã khác**. Cổng tái lập hiện KHÔNG phủ information set | `minds/transcript.py:20-26,134-136` | P3.2 | `reproducibility-steward` | OPEN |
| F-27 | INFO (xác nhận) | `grep -rniE "escrow\|reserve\|ky_quy\|dat_coc\|giu_cho" engine/` ⇒ **ZERO match**. Escrow/reservation **thật sự không tồn tại** ⇒ A2A settlement locking là NEW thật, không phải "mở rộng cái đã có". `bang_rao` + `HopDong` đã phủ ~60% (thread id, parties, counteroffer, accept/reject, settlement nguyên tử đúng-một-lần `board.py:51-90`) | grep (parent verified) | P3.4 | — | CONFIRMED |
| F-28 | **CRITICAL (anti-teleology)** | **Prompt MỚM ĐÚNG NHỮNG THỨ mô hình tuyên bố đang đo sự tự phát của chúng.** Bốn kênh độc lập, không cái nào bị `TU_MOM` bắt: **(a) Hàm hữu dụng viết sẵn** — `minds/prompts.py:416-419` "[BẠN LÀ NGƯỜI SỐNG] Bạn có nhu cầu như mọi con người: no bụng hôm nay; an toàn ngày mai (dự trữ, nhà cửa); gia đình (...để lại gia sản); và **vị thế** (đất đai, của cải, chữ nghĩa, **tiếng thơm**)" ⇒ đây LÀ một thang ưu tiên/utility function được trao tay, rồi mô hình hỏi phân tầng xã hội có tự phát không. **(b) Ví dụ chiến lược CÓ BIỆN GIẢI** — `:423-429` `VI_DU_QUYET_DINH` không phải ví dụ ĐỊNH DẠNG mà là một chiến lược hoàn chỉnh kèm lý do: *"Canh 2 thửa đủ ăn, thửa xa cho **cấy rẽ lấy 4 phần**, và đến tuổi phải tính chuyện gia đình"* ⇒ demo **phát canh thu tô 40%** + timing hôn nhân, rồi mô hình hỏi tá điền/địa tô có tự phát không. **(c) Mồi tiền-tệ-là-thóc + phát biểu SAI SỰ THẬT** — `:82` `mo_ta_the_gioi`: *"Mọi trao đổi tính bằng thóc"* — **sai**, `Lenh.thanh_toan` cho phép MỌI asset ⇒ vừa mớm numéraire vừa nói dối agent, rồi mô hình hỏi phương tiện trao đổi có tự phát không. **(d) Nhãn nghề** — xem F-24. Xác nhận độc lập bởi parent (4/4) | `minds/prompts.py:416-419`, `:423-429`, `:82`, `:362-397` | P3.1 | `adversarial-reviewer` + `reality-auditor` | OPEN |
| F-29 | MAJOR | Khối chính trị trong `LUAT_VAT_LY` render **VÔ ĐIỀU KIỆN** kể cả khi `chinh_tri.bat=false` ⇒ prompt mô tả một cỗ máy **không tồn tại**, và **tiết lộ ngưỡng Gini bạo động như một đòn bẩy** | `minds/prompts.py` (khối LUAT_VAT_LY chính trị) | P3.1 | `reality-auditor` | OPEN |
| F-30 | MAJOR | **~20 đường từ chối IM LẶNG** — engine nuốt intent không báo lý do, tập trung đúng ở `engine/market.py:119-122,171-179,206-225` và `engine/board.py:31-36,103-113,144,151-154` — tức **chính bề mặt mà `real60_spatial` "không thấy giao dịch"**. `board.py:144` `_ky_hop_dong` trả `False` **im lặng** khi cùng 100kg backing N offer (double-spend protocol). ⇒ **Không thể kết luận "LLM không chịu giao dịch" khi engine không bao giờ nói vì sao lệnh của nó biến mất** | `engine/market.py`, `engine/board.py` | P3.3 | `test-engineer` | OPEN |
| F-31 | MAJOR | `TU_MOM` blacklist có hai lỗi thiết kế: (1) cấm `"tối đa"` sẽ sai (đó là **dữ kiện trần cứng**: "canh tối đa 3 thửa") — phải cấm `"tối đa hóa"`; (2) blacklist phải áp **CHỈ cho scaffolding do engine viết**, vì `niem_tin` do chính LLM sinh (`minds/real.py:295`) quay lại prompt ⇒ agent viết "đáng tin" sẽ làm gate đỏ oan | `tests/test_prompt_ky_luat.py:22` | P3.1 | `test-engineer` | OPEN |
| F-32 | MAJOR | `get_phan_bo_cua_cai` (`minds/world_tools.py:152`) trao **Gini + phân vị TOÀN LÀNG cho BẤT KỲ AI**; docstring nói dành cho Trưởng làng nhưng `thuc_thi` (`:203`) **không kiểm gì**. `nghe_ve` nhận bất kỳ agent nào toàn thế giới. `cong_cu_max_luot: 10` cap **lượt model**, không cap **số tool call** — một lượt mang nhiều `functionCall` (`minds/providers_real.py:147,154-161`) ⇒ world-read **không giới hạn** | `minds/world_tools.py:152,203`; `minds/providers_real.py:147,154-161` | P3.2 | `reality-auditor` | OPEN |
| F-33 | **CRITICAL (NEW — mở rộng phạm vi P0.2)** | **Transcript-replay HỎNG ĐỘC LẬP với resume.** `mock60_spatial` **chưa bao giờ resume**, một segment duy nhất, `call_id` duy nhất, và **pass seed-replay bit-for-bit** (`replay mock60_spatial --verify` ⇒ TRÙNG `6086f1d3…`) — **NHƯNG** `replay mock60_spatial --from-transcript --verify` ⇒ **686 miss / 1025 chưa dùng, LỆCH hash**. ⇒ Câu chuyện "real60 lệch **vì** resume" (Report_v2 §3, ADR 0006 §1.3) là **KHÔNG ĐẦY ĐỦ**: có defect thứ hai độc lập. **P0.2 một mình KHÔNG làm G3 xanh được.** Nghi phạm (chưa xác nhận): `minds/transcript.py:24-26` tự thừa nhận `a.hoi_ky`/`a.niem_tin` **NGOÀI `world_hash` nhưng TRONG prompt tick sau**; `minds/gateway.py:303` retry phát prompt sửa lỗi **không có trong transcript** ⇒ một miss lan truyền | `tools.replay mock60_spatial --from-transcript --verify` (executed) | P0.2 `engine-surgeon` | `reproducibility-steward` | **OPEN — GATE G3 BLOCKER** |
| F-34 | MAJOR | **Prompt base nói dối sản lượng 8% TRƯỚC cả overlay.** ADR 0006 §B.2 yêu cầu base nói `650kg`, nhưng `config/world.yaml:23` là `san_luong_goc_kg: 600` và `engine/production.py:255-264` dùng đúng khóa đó. `~650kg` là **hằng số CHẾT đã trôi**. Renderer mới xuất **600**. Parity test phải assert **600**, không phải 650. ADR 0006 §B.2 cần sửa một dòng | `config/world.yaml:23`; `minds/prompts.py` (cũ) | P0.1 | `spec-governor` | OPEN (ADR fix) |
| F-35 | INFO (chủ ý, phải nêu TO) | **`world_hash` của run `mock` + `khong_gian.hai_bo=true` SẼ ĐỔI** — đây là **hệ quả của việc sửa F-02, không phải hồi quy.** Rulebot phát ferry intent cho **15/50** agent ở spatial; wire JSON CŨ mang **0** (translate nuốt im lặng), wire MỚI mang **20**. Base/legacy: `0 → 0`, hash **BẤT BIẾN** (chứng minh bằng diff wire JSON byte-identical với `git HEAD`, 43/43 action) | P0.1 evidence | P0.1 | `reproducibility-steward` | ACCEPTED |
| F-36 | **BLOCKER (ADR 0007 §G-2)** | **Route estate mặc định của P1 memo là một SINK ĐỔI TÊN.** Memo §4.3 gửi estate hết hạn về `CONG_QUY`, lập luận `thu_thue_va_chia` sẽ chia lại. Nhưng `engine/politics.py:194-195` **return sớm khi `chinh_tri.bat=false`**, và `scenarios/agrarian_transition_v1/parameters.yaml:16` đặt **`chinh_tri.bat: false`** — **đúng cái scenario P1 nhắm tới**. Kể cả khi ON, `_chia_deu` (`politics.py:225,230-238`) chỉ chia **thuế của tick này** và chỉ `"thoc"` ⇒ nhà/gà/gỗ vào `CONG_QUY` **không bao giờ ra**. ⇒ Sẽ **tái tạo F-19 dưới tên mới** trong khi vẫn PASS invariant E1 của memo. ADR 0007 §D.6 chặn `het_han:"cong"` ở config-validation (fail-closed) và thay E1 bằng **E1′ (no absorbing sink / no renamed sink)** | `engine/politics.py:194-195,225,230-238`; `scenarios/agrarian_transition_v1/parameters.yaml:16` | P1.3 | `adversarial-reviewer` | RESOLVED trong ADR 0007 |
| F-37 | MAJOR (trung thực) | **Chế độ truyền tài sản (`ho.di_san.che_do`) LÀ định chế có tên và TRƯỢT điều kiện #2 của cổng charter §5: cost = 0** (thừa kế miễn phí — không probate, không tranh chấp, không phí chuyển). ⇒ Giữ như **`institutional_assumption` / `experimental_treatment`** tường minh, **KHÔNG BAO GIỜ** được gọi là "tự phát". Bắt buộc ablation pre-registered đối chứng `tan_ra` (null regime). ADR 0007 **từ chối bịa ra một phí probate chỉ để qua checklist** | `docs/adr/0007` §E | P1 | `monetary-fiscal-economist` | ACCEPTED (PENDING tier escalation) |
| F-38 | MAJOR | Nhiễm bẩn số liệu **XÁC NHẬN nhưng có biên**: chỉ nằm ở `reports/real60_evaluation.md` §3. **`Report_v2.md` §3 KHÔNG có số nào bị nhiễm** (thuần định tính); `reports/paper_draft.md` **không trích run này**. Chi tiết: §3 dùng **raw (chưa dedupe) counts trên `events.jsonl` cắt ở tick ≤111** — một snapshot GIỮA resume. `ky_hd` 10→**9** (clean), `danh_ca` 107→**100** (clean ≤111) và **154** (clean full 180t). Header nói "real 105t" nhưng data là ≤111. Mọi số §1b/§2 (từ `metrics.jsonl`, được ghi đè cuối run) **KHÔNG nhiễm** | `docs/reviews/P0-artifact-integrity.md` | P4 | report owner (KHÔNG phải agent) | OPEN |
| F-17 | MAJOR | Hash gate rẽ nhánh theo cờ: `engine/world.py:470-493` — khi `khong_gian.hai_bo` **OFF**, parcel bị chiếu về whitelist 11 khóa ⇒ field mới KHÔNG vào hash; khi **ON**, `Parcel` dataclass thô được canonicalize ⇒ **MỌI** field vào hash. ⇒ thêm `Parcel.sinh_khoi` sẽ **đổi hash của `spatial_v1` ON**; và một ablation `hai_bo=false, rung=true` sẽ **giấu state ảnh-hưởng-hành-vi khỏi hash** | `engine/world.py:470-493`, `:90` | P2.1 / P2.5 | `reproducibility-steward` | OPEN — liên quan F-10 |

---

## 2. Hard ordering

```
D0 (design gate)  ✔ ADR 0006 Accepted · P0.2 design done · ledger done
   → P0.1 (parity)  ∥  P0.2 (journal/resume/replay gate)
   → P0-integration (capability_catalog_hash vào manifest)   [cần P0.1 + P0.2]
   → ══ P0 GATE: test-engineer + qa-verifier + adversarial-reviewer (không ai là tác giả) ══
   → ADR 0007 (household/estate) → P1.2 ∥ P1.3 → P1.4 → P1.5 → ══ P1 GATE ══
   → P2.1 → P2.2 ; P2.3 (cần P1.5 + P0.1) ; P2.4 ; P2.5 → ══ P2 GATE ══
   → P3.1 → P3.2 ∥ P3.3 ; P3.4 (cần P1.4/P1.5 escrow) → P3.5 → ══ P3 GATE ══
   → P4
```

Không package P1+ nào được giao cho implementer trước khi P0 có verdict **độc lập**.

### HOTSPOT SERIAL — một implementer / file / lượt

| File | Package chạm | Luật |
|---|---|---|
| `engine/tick.py` | P1.4, P1.5, P2.1, P2.2, P3.4 | SERIAL |
| `engine/world.py` | P0.2, P1.2, P1.3, P2.1 | SERIAL (hash-struct + checkpoint + FlowRegistry) |
| `engine/intents.py` | P0.1, P1.5, P2.3, P3.4 | SERIAL |
| `minds/prompts.py` | P0.1, P3.1, P3.3 | SERIAL (nguồn của `prompt_template_hash` ⇒ ảnh hưởng replay) |
| `minds/translate.py` | P0.1, P3.3 | SERIAL |
| `minds/schemas.py` | P0.1, P3.4 | SERIAL |
| `minds/transcript.py`, `minds/gateway.py` | P0.2 | SERIAL |
| `run.py` | P0.2 | SERIAL |
| `engine/production.py` | P1.4, P2.1, P2.4 | SERIAL (ADR 0005 §15) |
| `tools/verify_research_run.py` | P0.2, P4 | SERIAL — **nó CHÍNH LÀ cái gate** |

PARALLEL-SAFE: file mới (`minds/capabilities.py`, `engine/journal.py`, `engine/estate.py`,
`engine/projects.py`, `engine/forest.py`, `minds/tools_local.py`, `minds/a2a.py`), `tests/test_*.py` mới,
memo trong `docs/reviews/`.

**Phân công tránh va chạm P0 (đã áp dụng):**
- `minds-engineer` (P0.1) sở hữu: `minds/capabilities.py`(NEW), `minds/schemas.py`, `minds/translate.py`, `minds/prompts.py`.
- `engine-surgeon` (P0.2) sở hữu: `engine/journal.py`(NEW), `engine/events.py`, `minds/transcript.py`, `minds/gateway.py`, `run.py`, `tools/{replay,verify_research_run,experiments}.py`.
- `capability_catalog_hash` vào manifest = **integration step của parent SAU khi cả hai landed** (tránh hai agent cùng sửa `run.py`/`experiments.py`).

---

## 3. LEDGER

Legend: `TODO` = chưa có diff, chưa có evidence file.

### D0 — Design gate

| ID | Scope | Owner | Gate độc lập | Evidence file | Status |
|---|---|---|---|---|---|
| D0.1 | Giải mâu thuẫn C1–C5 (calendar, cổng định chế, pantry, `ho_cua`, pool-ngoài-hash) | `spec-governor` | `adversarial-reviewer` | `docs/adr/0006-capability-catalog-and-run-journal.md` §D | **DONE** (C5/F-10 route sang P2.5) |
| D0.2 | ADR capability registry (khai-báo-một-lần: intent field + schema + translate + handler + scenario gate + availability predicate + prompt render + outcome codes) | `spec-governor` | `engine-surgeon` + `adversarial-reviewer` | `docs/adr/0006` §A, §B | **DONE** |
| D0.3 | RunJournalManifest / segment / resume-truncate semantics | `model-architect` + `spec-governor` | `engine-surgeon` + `test-engineer` | `docs/adr/0006` §C + `docs/reviews/P0.2-model-architect-journal-design.md` | **DONE** |
| D0.4 | Dependency/evidence ledger | `integration-manager` | — | file này | **DONE** |
| D0.5 | Design memo P1 (residence/estate/metrics) | `household-demography-specialist` | `agrarian-economist` | `docs/reviews/P1-household-demography-design.md` | IN-PROGRESS |
| D0.6 | Design memo P2 (forest/habitat/ferry/crop) | `spatial-ecology-specialist` | `reality-auditor` | `docs/reviews/P2-spatial-ecology-design.md` | IN-PROGRESS |
| D0.7 | Design memo P3 (fact cards/tools/feedback/A2A) | `agent-autonomy-protocol-designer` | `qa-verifier` | `docs/reviews/P3-autonomy-protocol-design.md` | IN-PROGRESS |

### P0 — Interface truth + reproducible artifact (BLOCKING)

| ID | Scope | Files | Invariant | Owner | Gate độc lập | Acceptance (Report_v2 §5) | Evidence | Status |
|---|---|---|---|---|---|---|---|---|
| P0.1 | Prompt/config/capability parity: `LUAT_VAT_LY`+preamble → renderer từ `World.cfg`; bỏ list tĩnh; phủ `dong_thuyen`/`rao_do`/`qua_song`; audit mọi engine action tìm orphan | `minds/capabilities.py`(NEW), `minds/schemas.py`⚠️, `minds/translate.py`⚠️, `minds/prompts.py`⚠️ | CAP-1..4, PROMPT-1 (ADR 0006 §A.3, §B.2) | `minds-engineer` | `test-engineer`, `qa-verifier`, `adversarial-reviewer` | (a) prompt spatial nói `4 tháng`/`60kg`/`120 công`/3 mùa; (b) prompt base giữ luật base; (c) **test FAIL nếu** engine action không có đường LLM **hoặc** menu quảng cáo action không thực thi được (hai chiều); (d) `ngo`,`khoai`,`ga`,`thit`,`ca`,`go`,`thuyen` có đường qua chợ/menu | `docs/reviews/P0.1-minds-engineer.md` | TODO |
| P0.2 | Resume-safe journals + transcript replay là HARD GATE cho `real` | `engine/journal.py`(NEW), `engine/events.py`, `minds/transcript.py`, `minds/gateway.py`, `run.py`⚠️, `tools/{replay,verify_research_run,experiments}.py`⚠️ | JOURNAL-1..3 (ADR 0006 §C.5) | `engine-surgeon` | `reproducibility-steward`, `test-engineer`, `qa-verifier`, `adversarial-reviewer` | (a) run FakeTransport chia 2 phiên + resume ⇒ event/metric/call ID duy nhất, world-hash **BẰNG** run liền; (b) `replay --from-transcript --verify` yêu cầu `misses==0`, `unused==0`, hash==manifest, identity khớp; (c) `verify_research_run` chạy cổng replay cho **mode=real** không mạng — **xóa hẳn nhánh skip**; (d) journal lệch checkpoint ⇒ **fail closed**; (e) `--json` không crash | `docs/reviews/P0.2-engine-surgeon.md` | TODO |
| P0.3 | Integration: `run_uuid` + `capability_catalog_hash` vào manifest; replay/verify kiểm identity | `run.py`, `tools/experiments.py`, `tools/replay.py` | ADR 0006 §A.2, §C.4 | parent (sau P0.1+P0.2) | `reproducibility-steward` | catalog hash ổn định khi reorder, đổi khi đổi interface; replay FAIL khi identity mismatch (`skipped_version_mismatch`) | `docs/reviews/P0.3-integration.md` | TODO |

**Acceptance P0 (`Report_v2.md:243-245`):** capability matrix tự kiểm + prompt không còn hằng stale
+ resume-hai-phiên bằng hash run liền + transcript replay không mạng pass. **Thiếu một mục = P1 dừng.**

### P1 / P2 / P3 / P4

Xem `Report_v2.md` §5. Ledger chi tiết được mở khi P0 GATE xanh. Ràng buộc đã chốt:
- **P1 bị chặn bởi ADR 0007** (`docs/adr/0006` §D.3): không engine change nào cho household/estate
  trước khi ADR 0007 Accepted.
- **P2.1 bị chặn bởi F-10** (pool-trong-hash?): forest biomass ảnh hưởng hành vi mạnh hơn `ca_ton`;
  phải có phán quyết `reproducibility-steward` trước.
- **P3.4 (A2A escrow)** phải qua cổng định chế charter §5 (5 điều kiện) hoặc được tuyên bố là
  Lớp-1/2 (vật lý + kế toán) — `spec-governor` phán quyết khi P3 mở.

---

## 4. Artifact người dùng — KHÔNG ĐỤNG

| Path | Lý do |
|---|---|
| `reports/paper_draft.md` | uncommitted, người dùng đang sửa (`Report_v2.md:53-55`) |
| `reports/real60_evaluation.md` | untracked; nguồn chẩn đoán của Report_v2 §3 |
| `Report_v2.md` | untracked; chính là execution authority |
| `data/runs/real60_spatial/**` | artifact lịch sử; `Report_v2.md:239-241` cấm retcon. **Không chạy `--repair` lên nó.** |
| `data/runs/**` | chỉ đọc |
| `.claude/agents/*.md` | user-owned config |
| `.env` | cấm đọc |

Ghi được: `engine/`, `minds/`, `tools/`, `tests/`, `config/`, `scenarios/**` (mới/versioned),
`docs/adr/`, `docs/reviews/`, `DECISIONS.md`.

---

## 5. Release gate table

| # | Gate | Bằng chứng bắt buộc | Hôm nay |
|---|---|---|---|
| G1 | Prompt/config/catalog parity | prompt spatial render test + parity hai chiều engine↔schema↔translate↔menu | **NO OUTPUT** (P0.1) |
| G2 | Journal/resume continuity | FakeTransport 2 phiên + resume; ID duy nhất; offset hỏng ⇒ fail closed | **NO OUTPUT** (P0.2) |
| G3 | Transcript replay | `replay --from-transcript --verify` ⇒ `misses==0`, `unused==0`, hash==manifest | **NO OUTPUT**; F-05 dự đoán FAIL sau resume |
| G4 | Ledger/audit | `kiem_toan_the_gioi` mỗi tick; mọi flow có counterpart | baseline xanh (308 passed) |
| G5 | Household/estate/labor/project | acceptance P1 (5 gạch, `Report_v2.md:267-273`) | **NO OUTPUT** |
| G6 | Ecology/spatial | logging shock ⇒ biomass↓⇒K↓⇒catch↓; 6 case đò | **NO OUTPUT** |
| G7 | Autonomy / A2A settlement | fixture: khám phá mọi action; quote settle ĐÚNG MỘT LẦN; ≥2 sinh kế | **NO OUTPUT** |
| G8 | Tests / lint | `pytest -q` + `ruff check .` + `tools.verify_local` | baseline: 308 passed/1 skipped; ruff sạch; verify_local chưa chạy |
| G9 | Artifact manifest | `verify_research_run` pass **gồm cả** transcript replay + identity + event uniqueness | **FAIL** — F-06 (false-green) + F-07 (`--json` crash) |
| G10 | Adversarial verdict | disposition tường minh cho **mọi** blocking finding | **NO OUTPUT** |

---

## 6. Claim boundary

Ledger này chứng minh: (1) hai defect của gate trong `tools/verify_research_run.py`, tái hiện bằng
lệnh đã chạy; (2) cơ chế lệch-hash-sau-resume, chứng minh bằng audit artifact (403 call_id lặp,
9 prompt_hash trùng với response khác nhau, 3 journal dừng ở 3 tick khác nhau); (3) một cấu trúc
dependency/ordering có tài liệu.

Nó **KHÔNG** chứng minh gì về hành vi LLM, kết cục kinh tế, tử vong, sụp đổ, hình thành tiền, hay
so sánh provider. Số liệu `real60_spatial` giữ nhãn
`diagnostic observation from an unreplayable run`.
