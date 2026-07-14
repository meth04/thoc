# Artifact ledger — nhãn tái lập cho mọi run trong `data/runs/`

Owner: `research-artifact-integrity-auditor` + `reproducibility-steward`.
Nguồn thẩm quyền: `docs/adr/0006-capability-catalog-and-run-journal.md` §C.6.

> **Nhãn được TÍNH TẠI CHỖ.** Không nhãn nào trong file này được ghi vào `data/runs/*/`.
> Manifest cũ KHÔNG được ghi đè để nhét nhãn vào (ADR 0006 §C.6). Ledger này chỉ đọc artifact.
>
> Vocabulary (ADR 0006 §C.6): `replay_verified` · `diagnostic_only_unreplayable` ·
> `pending_verification` · `skipped_version_mismatch`.

Ngày kiểm: **2026-07-13**. Code kiểm: HEAD `db8e4fb` (= `git_revision` trong cả hai manifest).
Mọi lệnh chạy với `THOC_BLOCK_NETWORK=1`, không mạng, không LLM, không `--repair`.

---

## Bảng

| run | mode | seed | ticks | ngày | artifact_status | lý do | lệnh verify | verdict |
|---|---|---|---|---|---|---|---|---|
| `real60_spatial` | real (Gemini) | 42 | 180 (60 năm; 3 tick/năm) | 2026-07-13 (manifest `created_at_utc` 04:14:58Z) | **`diagnostic_only_unreplayable`** | Bị kill @tick 117–119, resume từ checkpoint 105, **journal tail KHÔNG truncate**: (a) events.jsonl chứa **313 bản ghi mồ côi** (tick 106–117 của segment-1) trong đó 230 trùng byte với segment-2 và **83 phân kỳ**; (b) transcript 1595 rows / 1192 distinct `call_id` ⇒ **403 call_id lặp**; (c) **9 `prompt_hash` trùng, cả 9 có `response_raw` KHÁC NHAU**; (d) transcript (1595) ≠ llm_calls (1589); (e) `unrecognized_intents.jsonl` chứa 1 bản ghi mồ côi (tick 109) **không lộ ra bằng tick-monotonicity**; (f) transcript-replay LỆCH hash | `python -m tools.replay real60_spatial --from-transcript --verify` | **INVALID FOR RESEARCH** — chỉ `diagnostic observation from an unreplayable run`. Không dùng cho claim về hành vi LLM / collapse / so sánh model. |
| `mock60_spatial` | mock (PersonaBot) | 42 | 180 (60 năm; 3 tick/năm) | 2026-07-13 | **`replay_verified`** *(phạm vi: **seed-replay**)* + **CẢNH BÁO F-14** | Một phiên liền mạch: không tick regression, 15702 transcript rows = 15702 llm_calls rows, `call_id` duy nhất 100%, metrics 180 tick liền mạch. Seed-replay tái dựng **đúng `world_hash` `6086f1d3…`**. **NHƯNG** transcript-replay KHÔNG khép kín (686 miss, 1025 unused, hash `5fe0b8e8…` ≠ `6086f1d3…`) ⇒ **không được trích như bằng chứng rằng cơ chế transcript-replay hoạt động** | `python -m tools.verify_research_run mock60_spatial` (9/9 PASS) · `python -m tools.replay mock60_spatial --verify` (TRÙNG ✅) | **VERIFIED (seed-replay)** — quỹ đạo/metrics/events tái dựng được bit-for-bit từ seed ⇒ citable ở tier `mechanism_result` cho nhánh mock. Transcript của nó = `pending_verification` (F-14). |
| `quota_counters.sqlite` | — | — | — | — | *(không phải run)* | DB đếm quota dùng chung, không có manifest/metrics | — | n/a |

`ls data/runs/` ⇒ chỉ có **2 run** + `quota_counters.sqlite`. Không còn run nào khác.

---

## Ghi chú bắt buộc

1. **`real60_spatial` KHÔNG được nâng cấp thành verified bằng bất kỳ đường nào** (ADR 0006 §7).
   Nó giữ nguyên từng byte; không ai chạy `--repair` lên nó. Nhãn ở đây, không ở run dir.
2. **`mock60_spatial` `replay_verified` chỉ có nghĩa seed-replay.** Đây là cổng mà
   `tools/verify_research_run.py:205-224` thực sự áp cho mode mock và nó PASS. Nó **không**
   chứng minh transcript khép kín — xem F-14.
3. **Figure mồ côi:** `reports/*.png` (`mock300_*`, `review_mock_30y_*`, `review_real_30y_v1_*`,
   `vidtest_*`) trỏ tới các run **không còn tồn tại** trong `data/runs/` ⇒ không truy được về
   event/metric thô ⇒ không được dùng làm bằng chứng; cần sinh lại từ artifact hiện có hoặc gỡ.
4. Nhãn `skipped_version_mismatch` **đang áp cho working tree hôm nay**: `minds/prompts.py` đã trôi
   (`prompt_template_hash` code = `9e32bcac…` vs manifest `6b585250…`). Mọi replay phải chạy tại
   HEAD `db8e4fb` (đã xác minh: `sha256(HEAD:minds/prompts.py)` = `6b585250…` = manifest).
   `tools/replay.py` hiện **không** kiểm identity ⇒ nó vẫn chạy và in ra số — đây chính là lỗ hổng
   ADR 0006 §C.4 yêu cầu bịt (P0.3).
