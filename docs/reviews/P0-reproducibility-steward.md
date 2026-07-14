# P0 — Reproducibility steward audit (independent gate)

Tác giả: `reproducibility-steward`. Ngày: 2026-07-13. Read-only trên code/test/artifact có sẵn.
Chỉ tạo run mới `data/runs/repro_*` + script `.tmp/repro/`. `git status --porcelain data/runs/` cho thấy
**ZERO** thay đổi ở `real60_spatial` / `mock60_spatial`. Không `--repair`, không mạng, không `.env`, không real.

## Verdict: **PARTIAL** — P0 KHÔNG ký được là `technical-ready`

Bộ máy journal/resume/replay của P0.2 là **TÁI LẬP ĐƯỢC** và tôi đã tự kiểm chứng từng claim.
Nhưng **P0 tổng thể ĐỎ**: acceptance suite fail 2 test, cộng hai lỗ hổng reproducibility MỚI và F-P02-2
được xác nhận.

---

## 1. Resume ≡ liền mạch — ĐÃ TỰ CHẠY, không tin báo cáo

| run | mode | world_hash | segment |
|---|---|---|---|
| `repro_rb_lien` | rulebot 24t | `a1fb65f2cb2d6786` | 0 |
| `repro_rb_ngat` | rulebot, **kill@14** → resume | `a1fb65f2cb2d6786` | 1 |
| `repro_mock_ngat` | mock+transcript, kill@14 → resume | `9fd7b5aa1b49d8a5` | 1 (= run liền) |
| `repro_sp_lien` | mock+transcript, `agrarian_transition_v1`+`spatial_v1` 24t | `5ccec5251b2fbe82` | 0 |
| `repro_sp_ngat` | same, **kill@20** → resume | `5ccec5251b2fbe82` | 1 |

Kill để lại tail BẨN THẬT (rulebot: checkpoint tick 10 tại `byte_offset=119963`, file phình tới 153777 →
**293 event record mồ côi**). Khi resume:
```
[recovery] cắt 293 event / 0 transcript / supersede 0 llm_call sau tick 10;
           bằng chứng giữ ở checkpoints/orphans/seg0000_after_tick0010/
[xong] tick 24 | hash a1fb65f2cb2d6786
```
⇒ **Đây mới là minh chứng cấp-artifact THẬT của JOURNAL-1/3** (khác `p0check_resume` vốn `bytes_truncated=0`).

ID/continuity trên mọi run resumed: event `seq` duy nhất **và** liên tục `1..E`, 0 tick regression;
transcript `call_id` duy nhất; `llm_calls.call_id` duy nhất; metric tick duy nhất+liên tục.

Accounting identity đúng chính xác, ZERO delete:
- `repro_mock_ngat`: `call_burned=713 = call_effective=604 + rows_superseded=109`.
- `repro_sp_ngat`: `884 = 693 + 191`.

## 2. Transcript replay hard gate — VERIFIED, **zero provider call** (chứng minh, không giả định)

```
python -m tools.replay repro_sp_ngat --from-transcript --verify
transcript  : 693 call, 0 miss, 0 chưa dùng
hash replay : 5ccec5251b2fbe82…   hash gốc : 5ccec5251b2fbe82…
KẾT QUẢ     : TRÙNG ✅   exit=0
```
Tôi **chứng minh** "zero provider call" thay vì giả định: cài socket guard **và** monkeypatch
`httpx.Client.send` / `AsyncClient.send` để raise, rồi chạy `replay_from_transcript` trên cả hai run resumed
→ `ok=True, misses=0, unused=0, identity_ok=True`, **`socket.connect` = 0, httpx request = 0**.

Ghi chú: `p_malformed=0.05` ĐANG BẬT ở các run này và replay vẫn đóng ở 0/0.

## 3. F-14 / F-33 — **KHÔNG TÁI HIỆN**

`mock60_spatial` fail transcript replay (686 miss / 1025 unused). Run mock spatial MỚI của tôi, cùng
scenario + overlay, seed 42, **pass ở 0/0**. Nguyên nhân là **version drift**, và gate giờ gọi đúng tên nó:
```
artifact_status: skipped_version_mismatch
  prompt_template_hash: ['6b5852508bd050f8…', '4f48eb2abdc8c14d…']
  capability_catalog_hash: [None, '795188c725fc971f…']
```
Gate **TỪ CHỐI** thay vì in một hash gây hiểu nhầm. F-33 nên được phân loại lại từ "defect thứ hai CRITICAL"
thành **"giải thích được bằng identity mismatch"**; phần dư là `mock60_spatial` là một artifact **cũ hơn interface**.

## 4. Fail-closed — VERIFIED, **0 byte được ghi** trong mọi case

| corruption | exit | code | file đổi |
|---|---|---|---|
| `byte_offset` +5000 trong `journal_manifest.json` | 1 | `E-JM-07` | **0** |
| lật 1 bit trong prefix `events.jsonl` | 1 | `E-JM-07` | **0** |
| xóa `journal_manifest.json` | 1 | `E-JM-01` (+ hướng dẫn) | **0** |
| `prompt_template_hash` khác giữa 2 segment | 1 | `E-JM-04` | **0** |

`--recover-journal`: quarantine tất cả, `replay_complete=false` + `artifact_status_forced=diagnostic_only_unreplayable`,
và `journal_replay_complete` là **hard FAIL**. Nó **KHÔNG BAO GIỜ** làm run xanh — đã chạy để xác nhận.

## 5. `capability_catalog_hash` — tính chất đúng
Reorder/shuffle `CATALOG` → hash không đổi (`795188c725fc971f…`). Mọi thay đổi interface (thêm schema field,
đổi `ma_ket_qua`, đổi `mau_prompt_template`, đổi `kha_dung_key`, bỏ một action) → hash ĐỔI.

---

## Findings

### F-P03-0 (**BLOCKER cho P0 sign-off**) — acceptance suite ĐỎ
```
2 failed, 438 passed, 1 skipped
FAILED tests/test_prompt_config_parity.py::…[san_xuat.recipe.xu.cong]
FAILED tests/test_prompt_config_parity.py::…[san_xuat.recipe.xu.ra]
```
PROMPT-1 (ADR 0006 §B.2) đang làm ĐÚNG việc của nó. Root cause `minds/capabilities.py:787-799` (`_gt_xay`):
`mon` suy từ `sorted(recipe)` nên **quảng cáo `"xu"`**, nhưng chỉ render chi phí `cong_cu` + `nha`.
`config/world.yaml:32` → `xu: {quang_dong:1, cong:5, ra:10}` **không bao giờ được nói cho agent**.
Không cosmetic: `duc_xu` LÀ kênh đúc tiền — cơ chế tiền-tệ-tự-phát mà dự án tuyên bố đang đo.
`real60_spatial` ghi `duc_xu = 0`. Con số đó giờ interface-confounded vì **lý do độc lập thứ BA**
(sau F-01 sai vật lý và F-02 capability mồ côi). **G1 không xanh ⇒ Acceptance P0 không đạt ⇒ P1 KHÔNG được bắt đầu.**

### F-P03-1 (**MAJOR, MỚI**) — cổng identity của resume KHÔNG thấy catalog drift
`engine/journal.py:68-74` `JournalIdentity` thiếu `capability_catalog_hash`; `_kiem_identity` chỉ so
`config_sha256` + `prompt_template_hash`. Mà `prompt_template_hash = sha256(minds/prompts.py)` — và P0.1 đã
**chuyển menu + asset list + `LOAI_HANH_DONG` sang `minds/capabilities.py`**
(`sha256=c67d64f4…`, **không được ghi ở đâu**). ⇒ Sửa catalog giữa hai segment ⇒ **resume vẫn chạy** ⇒ tạo đúng
artifact "hai-nửa-hai-luật" mà `E-JM-04` sinh ra để chặn. ADR 0006 §C.2 ghi rõ trường này. **Replay đã được
bảo vệ; chỉ resume hở.**

### F-P02-2 (**MAJOR, XÁC NHẬN — vi phạm điều luật #4**) — engine phụ thuộc thứ tự chèn dict config
Site DUY NHẤT: `engine/economy.py:43` `food_equivalence` duyệt `khong_gian.vu_dong.cay` theo insertion order;
`engine/consumption.py:60` ăn theo đúng thứ tự đó. `Config.digest()` dùng `sort_keys=True`, `world_hash`
canonical-sort ⇒ **cả hai đều không thấy nguyên nhân**.
```
need 60 kg-thoc; stock ngo 40 (×0.9), khoai 40 (×0.7)
cay={ngo,khoai} → eat ['thoc','ngo','khoai'] → sau: ngo 0.0,    khoai 5.7143
cay={khoai,ngo} → eat ['thoc','khoai','ngo'] → sau: ngo 4.4444, khoai 0.0
config_sha256 giống hệt: True     tồn kho kết quả KHÁC: True
```
Vi phạm trực tiếp CLAUDE.md §2 #4. Tiềm ẩn (cần hộ thiếu `thoc` mà giữ hai loại cây) — đúng vì thế nó sống sót.

Grep toàn engine: `pricing.py:49` `sorted()` (an toàn); `education.py:54` `sum` (an toàn);
`production.py:301` keyed `.get()` (an toàn); `production.py:472` `sorted(bp.recipe.items())` (an toàn);
`consumption.py:21` duyệt ledger balance nhưng mỗi mục decay độc lập, không RNG (an toàn).
**`food_equivalence` là site SỐNG duy nhất.**

**Fix ĐÚNG (khuyến nghị, cần `spec-governor`):** ĐỪNG chỉ thêm `sorted()` — thứ tự alphabet (`khoai` trước
`ngo`) là một lựa chọn HÀNH VI tùy tiện, âm thầm đổi scenario spatial. Hãy làm thứ tự ăn thành **một khóa
config tường minh** (vd `khong_gian.vu_dong.thu_tu_an: [ngo, khoai]`), validate theo khóa của `cay`, để nó
VÀO `config_sha256` và ổn định thứ tự. Thêm test: hai config chỉ khác thứ tự khóa YAML ⇒ cùng quỹ đạo.

### F-P03-2 (**MAJOR, MỚI**) — output isolation chỉ một phần
Chạy lại với `--run-name` đã tồn tại thì quarantine đúng các journal Class-A (`kind: fresh_run_reset`) và
supersede `llm_calls` cũ. NHƯNG nó **âm thầm ghi đè** `run_meta.json`, `experiment_manifest.json`,
`metrics.jsonl`, và để lại `.pkl` của run cũ không nhãn:
```
checkpoints/ : checkpoint_0006.pkl  checkpoint_0010.pkl  checkpoint_0020.pkl  checkpoint_0024.pkl
run_meta     : world_hash f67ba280… tick_cuoi 6  mode rulebot   (meta của run mock 9fd7b5aa… ĐÃ MẤT)
metrics.jsonl: 6 rows                                            (trước là 24)
```
⇒ Journal của run bị phá thì giữ được, nhưng **identity/outcome hash/metrics thì KHÔNG** — đúng cái bằng
chứng cần để biết cái gì đã bị phá. Checkpoint từ `run_uuid` khác nằm chung thư mục không có cross-check.

### F-10 (POOL SINH THÁI) — **PHÁN QUYẾT: (a). Đã de-facto implement. RATIFY.**

Tiền đề của F-10 đã **CŨ**. `ca_ton` và `ga_rung_ton` **ĐÃ NẰM TRONG `world_hash`** ở HEAD `db8e4fb`:

`engine/world.py:563-568`
```python
"commons": {
    "fish_stock": getattr(self, "ca_ton", None),
    "wild_chicken_stock": getattr(self, "ga_rung_ton", None),
},
```
Xác minh bằng mutation trên checkpoint thật: `ca_ton += 1 → world_hash đổi: True`;
`ga_rung_ton += 1 → world_hash đổi: True`. `git log -S "fish_stock"` → vào ở `db8e4fb`, cùng commit bump
`hash_schema` lên `behavioral-state-v2`; `DECISIONS.md:318` ghi migration và gọi tên `commons`.

**Phán quyết (ADR 0005 §6 ủy quyền):** chọn **(a)** — pool tự nhiên ảnh-hưởng-hành-vi **thuộc về `world_hash`**.
Tôi ratify implementation hiện có. Bác (b): "replay-từ-t0 là đủ" **SAI** như một invariant tổng quát, vì
`world_hash` CÒN là neo toàn vẹn cho **checkpoint/resume**. Pool ngoài hash ⇒ hai thế giới khác trữ lượng cá
lại **so sánh BẰNG NHAU** ở checkpoint, và resume từ pickle hỏng/migrate sẽ **pass hash check** trong khi mang
CPUE khác — âm thầm.

**Sửa tài liệu (không đổi code):**
- `docs/adr/0005:216-222` ("**NGOÀI world_hash-struct**") và hàng bảng `:334` **mâu thuẫn với code**. Supersede tại chỗ.
- `Report_v2-ledger.md` F-10: `OPEN` → **RESOLVED (ratified: pool trong hash, behavioral-state-v2)**.

**Hệ quả cho P2 — và nó KHÔNG miễn phí:**
1. **Forest biomass BẮT BUỘC vào hash.** Cùng luật, và biomass điều khiển hành vi MẠNH HƠN `ca_ton` nhiều
   (canopy → habitat K → sản lượng gà rừng → chọn đốn gỗ hay chăn nuôi). Trả lời câu hỏi đã đặt: **KHÔNG**,
   (b) sẽ KHÔNG an toàn cho biomass, và tôi KHÔNG cấp nó.
2. **F-17 mới là cái bẫy P2 thật và nó vẫn OPEN.** `engine/world.py:468-495`: khi `khong_gian.hai_bo` **OFF**,
   parcel bị chiếu qua whitelist 11 khóa; khi **ON**, `Parcel` dataclass thô được canonicalize ⇒ **MỌI** field
   vào hash. Do đó thêm `Parcel.sinh_khoi` (a) **đổi hash của MỌI run `spatial_v1`-ON**, và (b) một ablation
   `hai_bo=false, rung=true` sẽ **GIẤU biomass khỏi hash hoàn toàn** — tái tạo đúng cái defect mà F-10 nói tới.
   **Trước P2.1:** thêm `sinh_khoi` vào whitelist OFF-projection (hoặc biến projection thành danh sách field
   có version), bump `hash_schema` lên `behavioral-state-v3`, ghi legacy break vào `DECISIONS.md` như đã làm
   cho v2. **KHÔNG ship biomass dưới `behavioral-state-v2`.**

### Lesser
- **F-P02-1 ĐÃ ĐÓNG** (kiểm lại, ghi công): `minds/real.py:177` và `:323` giờ gọi `_ghi_call_loi` ở cả hai
  nhánh `except` của route nền.
- **Network guard chỉ có ở TEST.** `THOC_BLOCK_NETWORK=1` chỉ được `tests/conftest.py:38` tôn trọng.
  `run.py`, `tools/replay.py`, `tools/verify_research_run.py` **không có socket guard runtime** — tính chất
  "không mạng" của cổng replay dựa vào CẤU TRÚC (`tao_mind_replay` thay `TranscriptProvider` + đóng httpx
  client), không dựa vào CƯỠNG CHẾ. Đề nghị đưa `_chan_mang()` ra khỏi `conftest.py` thành module mà tool
  import khi env var bật, để gate tự cưỡng chế tiền đề của chính nó.
- **`artifact_ledger.md:22` CŨ**: gắn `mock60_spatial` = `replay_verified`. Ở tree hiện tại gate trả
  `skipped_version_mismatch` + **exit 1**.

---

## Invariants (tự kiểm chứng lại)

| ID | Status |
|---|---|
| JOURNAL-1 resume ≡ liền mạch (rulebot, mock, mock+spatial) | **HOLDS** — cùng `world_hash`, 3/3 |
| JOURNAL-2 fail-closed, 0 byte ghi | **HOLDS** — 4/4 case |
| JOURNAL-3 tail giữ trong `orphans/` + `journal_recovery.jsonl` | **HOLDS** (293 record thật) |
| INV-J2 `seq`/`call_id`/metric tick duy nhất, đơn điệu | **HOLDS** |
| INV-J5 `call_burned = call_effective + rows_superseded`, 0 DELETE | **HOLDS** |
| Replay gate: `misses==0 ∧ unused==0 ∧ hash ∧ identity`, zero provider call | **HOLDS** |
| Artifact cũ không tương thích: gắn nhãn, không bao giờ ghi lại | **HOLDS** |
| Catalog hash: reorder-stable, interface-sensitive | **HOLDS** |
| **Resume identity phủ đủ interface** | **FAILS** — F-P03-1 |
| **PROMPT-1 (không hằng chết / không action quảng cáo mà giấu giá)** | **FAILS** — F-P03-0 |
| **Điều luật #4: cùng seed + cùng config ⇒ cùng hash** | **FAILS** — F-P02-2 |
| **Output isolation** | **PARTIAL** — F-P03-2 |

## Claim boundary

- Cái P0.2 kiếm được, và CHỈ cái này: *"artifact của một run bị ngắt rồi resume replay bit-for-bit từ
  transcript của nó, offline."* Chứng minh cho **provider THUẦN** (rulebot / PersonaBot). Với LLM thật,
  provider **KHÔNG thuần** ⇒ tính chất chứng minh được là **"artifact resumed tự nhất quán và replay ra chính
  hash của nó"** — **KHÔNG phải** "resume == liền mạch". Cả `P0.2-engine-surgeon.md` §7 lẫn
  `P0.2-model-architect-journal-design.md` §8.2 đều nói ĐÚNG điều này. **Không tìm thấy overclaim ở hai file đó.**
  Nhưng `Report_v2.md` §5 "Acceptance P0" ("cùng hash như run liền") chỉ đúng dưới FakeTransport-thuần và nên
  mang qualifier.
- **KHÔNG AI được tuyên bố `technical-ready` hôm nay.** Với run của tôi, **G2 và G3 giờ XANH**, nhưng **G1 ĐỎ**
  (2 parity test fail) và **G8 ĐỎ** (suite không xanh). Report_v2 §5: "Không đạt một mục = dừng P1."
- Không gì ở đây nói bất cứ điều gì về hành vi LLM, collapse, tiền, hay so sánh model. **Một journal sạch
  KHÔNG PHẢI một kết quả.**
- Đây là audit **sạch môi trường**: không lệnh nào fail vì lý do môi trường; mọi màu đỏ ở trên là đỏ CODE/SPEC.
