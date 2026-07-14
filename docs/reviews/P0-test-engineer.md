# P0 — Bộ test độc lập (test-engineer)

- Vai: `test-engineer`. Ngày: 2026-07-13. **Không phải người implement P0.1/P0.2.**
- Spec: `docs/adr/0006-capability-catalog-and-run-journal.md` §6 (test matrix), §A.3 (CAP-1..4),
  §B.2 (PROMPT-1), §C.5 (JOURNAL-1..3), §C.4 (cổng verify).
- Diff đã đọc (kiểm chứ không tin): `docs/reviews/P0.1-minds-engineer.md`,
  `docs/reviews/P0.2-engine-surgeon.md`, `docs/reviews/Report_v2-ledger.md` (F-01..F-38).
- **Chỉ ghi `tests/*.py` MỚI + file này.** Không sửa một dòng production code.
  Không đụng `data/runs/real60_spatial/`, `data/runs/mock60_spatial/` (chứng minh bằng sha256
  từng file trước/sau — xem `tests/test_verify_gate.py::test_f06_...`).

## 1. Verdict

**PASS WITH RISKS** — P0.1 và P0.2 giữ đúng phần lớn hợp đồng ADR 0006, nhưng **5 test tôi viết
ĐỎ**, tất cả là defect thật (không phải test sai). Để ĐỎ, bàn giao cho implementer.

| Nhóm ADR §6 | Kết quả |
|---|---|
| CAP-1..4 (capability) | XANH 30/30 |
| PROMPT-1 (prompt/config parity) | **83/85** — 2 ĐỎ (`san_xuat.recipe.xu.*`) |
| JOURNAL-1..3 + ablation | **13/16** — 3 ĐỎ (2× catalog identity, 1× F-P02-1b) |
| Verify gate (F-06/F-07) | XANH 12/12 |

## 2. Scope — file đã thêm

| File | Test | Nội dung |
|---|---|---|
| `tests/test_capability_parity.py` | 30 | CAP-1..4, `catalog_hash` reorder/interface, roundtrip **phủ MỌI action**, no-mutation |
| `tests/test_prompt_config_parity.py` | 85 | parity base/spatial, F-34 (600 ≠ 650), asset list, property 64+14 khóa config |
| `tests/test_p0_resume_independent.py` | 16 | JOURNAL-1..3 qua ĐƯỜNG THẬT `run.py`, fail-closed, ablation, F-P02-1 |
| `tests/test_verify_gate.py` | 12 | F-06/F-07 regression trên `real60_spatial`, identity mismatch, 3 hash pin |

## 3. Invariant được cưỡng chế

- **CAP-2 chống vacuous**: `test_cap2_them_field_gia_thi_test_phai_do` dựng subclass `KeHoach`
  có field lạ ⇒ checker PHẢI bắt. Không có test này, CAP-2 là assertion rỗng.
- **CAP-1 roundtrip đủ**: `test_cap1_roundtrip_phu_MOI_action_cong_khai` set **cả 14 field mà
  `tests/test_translate_roundtrip.py::_ke_hoach_du_truong` KHÔNG set** (`dong_thuyen`, `rao_do`,
  `qua_song`, `khai_hoang`, `canh_vu_dong`, `cham_tre_cho` + 8 field chính trị) rồi assert
  `set(loai phát ra) ⊇ mọi action cong_khai`. **Đây chính là test lẽ ra đã bắt F-02 từ đầu**:
  bộ test cũ pass GIẢ vì field default rỗng thì roundtrip luôn bằng nhau.
- **CAP-4 không lách được**: bộ chặn là bản SAO ĐỘC LẬP + thêm `TU_XEP_HANG` (xếp hạng sinh kế)
  và `NHAN_GIAI_CAP_CAM` (nhãn Lớp-5 rò vào Lớp-4). Kèm
  `test_bo_chan_prompt_ky_luat_khong_bi_noi_long` pin nguyên văn bộ chặn của
  `tests/test_prompt_ky_luat.py` — nới nó ⇒ test này đỏ.
- **JOURNAL-2 fail-closed đo bằng sha256 TỪNG FILE** (không chỉ size `*.jsonl`): 5 kịch bản hỏng
  ⇒ `SystemExit` + `_dau_van_tay(rd)` bất biến.
- **`journal_continuity` tính từ NỘI DUNG FILE**: xác nhận trên `real60_spatial` (không có
  `journal_manifest.json`) vẫn bắt được 403 dup `call_id` + 1 tick lùi.

## 4. Command + OUTPUT THẬT

```
$ THOC_BLOCK_NETWORK=1 PYTHONIOENCODING=utf-8 PYTHONUTF8=1 conda run -n thoc-env \
    python -m pytest -q --basetemp .tmp/te -p no:cacheprovider
SKIPPED [1] tests\test_tools_check.py:29: thiếu run cnq2 (integration data)
FAILED tests/test_p0_resume_independent.py::test_journal_identity_phai_co_capability_catalog_hash
FAILED tests/test_p0_resume_independent.py::test_journal2_identity_catalog_doi_fail_closed
FAILED tests/test_p0_resume_independent.py::test_fp02_1b_route_dich_intent_hong_van_co_row_transcript
FAILED tests/test_prompt_config_parity.py::test_prompt1_doi_khoa_config_base_thi_prompt_doi[san_xuat.recipe.xu.cong]
FAILED tests/test_prompt_config_parity.py::test_prompt1_doi_khoa_config_base_thi_prompt_doi[san_xuat.recipe.xu.ra]
5 failed, 463 passed, 1 skipped, 14 warnings in 192.74s (0:03:12)

$ ... python -m ruff check .
All checks passed!
```

Baseline 325 passed / 1 skipped ⇒ **463 + 5 = 468 = 325 + 143 test mới**. **KHÔNG một test
legacy nào đỏ, bị skip hay bị nới** (đối chiếu inventory: HEAD 302 hàm test trong file tracked →
working tree 302, `comm` cho tập MẤT = rỗng).

### ABLATION (bắt buộc — P0.2 có thừa không?)

```
[ABLATION] dup_call_id=23 · continuity_loi=['events: seq trùng (9 bản)',
  'events: seq không liên tục 1..E', 'transcript: 23 call_id BỊ DÙNG LẠI ⇒ TranscriptReader
   FIFO trả response của phiên trước ⇒ replay lệch hash']
  · misses=7 unused=23 hash_match=False ok=False
```
Tắt truncate/supersede/rebase ⇒ **tái hiện đúng bệnh `real60_spatial`**. Bật lại ⇒ sạch.
**P0.2 KHÔNG thừa.**

### F-P02-4 (rủi ro tồn dư của P0.2) — KHÔNG tái hiện

```
test_resume_journal.py::test_journal_3_tail_bi_bo_van_ton_tai_trong_orphans  ×20 : pass=20 fail=0
test_p0_resume_independent.py::test_journal3_...                            ×20 : pass=20 fail=0
```
⇒ Đề nghị hạ F-P02-4 xuống **INFO / không tái hiện** (giả thuyết của engine-surgeon — file đang
được ghi trong lúc pytest collect — nhất quán với dữ liệu).

### Ba hash pin (ADR 0007 §0.1) — TÁI LẬP

```
LEGACY_OFF seed=11 t=20 : 4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b
LEGACY_OFF seed=42 t=20 : f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153
SPATIAL_ON seed=11 t=20 : afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745
```
⇒ P0 **hash-neutral**. Pin vào `tests/test_verify_gate.py::test_world_hash_legacy_bat_bien`.

## 5. Findings còn mở (5 test ĐỎ)

| ID | Sev | Finding | Owner |
|---|---|---|---|
| **F-TE-1** | **BLOCKER** | **F-P02-1 CHƯA ĐÓNG HẾT.** Parent vá `_nen_hoi_ky` (`minds/real.py:177`) + `_reflection` (`:323`) nhưng **BỎ SÓT route nền thứ ba** `_dich_intent_la` (`minds/real.py:234-236`): nhánh `except` chỉ `w.events.ghi(..., "dich_intent_loi")`, **không** `_ghi_call_loi`. Đo được trên artifact HOÀN TOÀN SẠCH (`journal_continuity: True []`): `event dich_intent_loi=1`, `transcript row lỗi=0`, `replay → misses=1, ok=False`. ⇒ **mọi run real có ≥1 call dịch-intent hỏng sẽ trượt cổng hard `misses==0`** — đúng lớp lỗi F-P02-1. Sửa: 1 dòng `self._ghi_call_loi(w, req, e)` | `minds-engineer` |
| **F-TE-2** | **MAJOR** | **`JournalIdentity` thiếu `capability_catalog_hash`** (`engine/journal.py:68-75`), dù ADR 0006 §C.2 liệt kê nó trong `identity` và §C.4 bắt resume verify identity. `catalog_hash()` ĐÃ có và ĐÃ vào `experiment_manifest`, nhưng **không vào journal identity** ⇒ **thêm/bớt action giữa hai segment KHÔNG bị fail-closed**: một run resume có thể nửa đầu chạy interface cũ (không `qua_song`), nửa sau interface mới, mà cổng resume vẫn xanh. `run.py:290-292` dựng `JournalIdentity` thiếu trường này | `engine-surgeon` / parent (P0.3) |
| **F-TE-3** | **MAJOR** | **PROMPT-1 thủng ở `san_xuat.recipe.xu.*`.** Menu `xay` quảng cáo `"mon":"cong_cu"\|"nha"\|"xu"` (CAP-3 nói `xu` khả dụng) nhưng **luật vật lý KHÔNG BAO GIỜ nêu recipe `xu`** (`1 quang_dong + 5 cong → 10 xu`). Đổi `recipe.xu.cong` hay `recipe.xu.ra` ⇒ **prompt không đổi một ký tự**. 62/64 khóa base khác đều đổi ⇒ đây là lỗ THẬT, không phải renderer sai. **Hệ quả khoa học:** `xu` là tài sản giống-tiền duy nhất; agent được mời đúc nó mà không được cho biết giá đúc/năng suất ⇒ **không được kết luận "tiền không tự phát sinh"** khi interface giấu chính công thức đúc tiền. Cùng lớp với F-03 | `minds-engineer` |
| **F-TE-4** | INFO | **F-15 xác nhận:** hệ số tự-học ×2 (`engine/education.py:65`) là hằng TRONG ENGINE, không có khóa config ⇒ property test PROMPT-1 không phủ được. Pin bằng `test_f15_he_so_tu_hoc_khong_co_khoa_config` để không bị quên | `spec-governor` |
| **F-TE-5** | INFO | **F-34 xác nhận:** `config/world.yaml:23` = `san_luong_goc_kg: 600`; renderer xuất **600**. **ADR 0006 §B.2 ghi `650` là SAI** (hằng số chết đã trôi trong `LUAT_VAT_LY` cũ). Test chốt **600** và cấm `650` quay lại khối luật vật lý. **ADR cần sửa một dòng** | `spec-governor` |

### Đã CỐ Ý tấn công, KHÔNG tìm thấy vấn đề

- **Nới assertion?** `git diff HEAD -- tests/test_prompt_ky_luat.py`: chỉ đổi import (hằng → hàm)
  + dựng world. **Mọi assertion giữ nguyên từng chữ.** Pin lại bằng test guard.
- **Test bị xóa/skip?** HEAD 302 → now 302 hàm test; tập MẤT = rỗng; không skip mới.
- **CAP-4 bị lách?** Không: 38 descriptor, không xếp hạng nghề, không gợi ý action nào tốt hơn,
  không nhãn giai cấp. (Nhắc: **F-24/F-28 vẫn OPEN** nhưng nằm ở `minds/prompts.py`
  `_cau_can_tinh`/`VI_DU_QUYET_DINH`/`[BẠN LÀ NGƯỜI SỐNG]` — **ngoài** catalog, ngoài scope P0.)
- **`journal_continuity` từ manifest hay nội dung file?** Từ **nội dung file** — xác nhận trên
  `real60_spatial` (không có manifest) vẫn FAIL đúng chỗ.
- **`world_hash` legacy?** 3/3 pin trùng.

## 6. Claim boundary

Bộ test này chứng minh **interface đúng + artifact replay được** ⇒ cấp `technical-ready`
(Report_v2 §8). Nó **KHÔNG** chứng minh `mechanism-ready`, `research-ready`,
`empirically-validated`. Một menu đầy đủ + transcript khớp hash **không** hàm ý LLM sẽ chuyên môn
hóa, làm nghề đò hay phát minh tiền. `real60_spatial` giữ nhãn `diagnostic_only_unreplayable`
vĩnh viễn (test `test_f06_...` cưỡng chế điều đó).

**Chưa được phủ (rủi ro tồn dư, KHÔNG phải scope P0):** F-33 (transcript replay hỏng độc lập với
resume trên `mock60_spatial` — chưa tái hiện ở quy mô nhỏ trong bộ test này); F-26 (replay MÙ với
tool layer — sửa `world_tools.py` xong replay vẫn xanh); F-25 (mock không đọc prompt);
F-14/F-24/F-28/F-30 (đều OPEN, thuộc P2/P3).

## 7. Next handoff

| Nhận | Việc |
|---|---|
| `minds-engineer` | **F-TE-1** (BLOCKER, 1 dòng): `_ghi_call_loi` ở `except` của `_dich_intent_la`. **F-TE-3**: render recipe `xu` (và `may`) vào luật vật lý |
| `engine-surgeon` / parent P0.3 | **F-TE-2**: thêm `capability_catalog_hash` vào `JournalIdentity` + `run.py` dựng identity + `_kiem_identity` |
| `spec-governor` | **F-TE-5**: sửa ADR 0006 §B.2 `650 → 600`. **F-TE-4**: quyết hệ số tự-học vào config hay giữ hằng |
| `qa-verifier` / `adversarial-reviewer` | Cổng độc lập trên chính bộ test này. 5 ĐỎ phải có disposition tường minh trước khi P0 GATE xanh |
