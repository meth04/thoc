# T02 — Nền tảng chạy được, kiểm toán được, output không lẫn nhau

Ngày: 2026-07-12. Owner: engine-surgeon + implementation-engineer (author) + integration-manager.
Reviewer độc lập: test-engineer (test verify tool), qa-verifier + reproducibility-steward (gate).

## Sản phẩm & bằng chứng

### 1. Lệnh local không-mạng, một-lệnh
- `tools/verify_local.py` (mới): chạy ruff → pytest (temp workspace + `THOC_BLOCK_NETWORK=1`)
  → scenario validation → rulebot smoke → `verify_research_run`. Kết quả:
  ```
  PASS ruff | PASS pytest | PASS scenario_validation | PASS smoke_run | PASS verify_research_run
  KẾT QUẢ: XANH ✅  (.tmp/logs/T02_verify_local.log)
  ```
  → pytest 176 passed **với guard mạng bật** (chứng minh suite không cần mạng).
- `tests/conftest.py` (mới): guard mạng OPT-IN — `THOC_BLOCK_NETWORK=1` chặn socket ra ngoài
  (loopback vẫn cho). Mặc định TẮT nên không đổi hành vi chạy cục bộ.

### 2. Output isolation
- `run.py`: mọi artifact của run nằm dưới `data/runs/<name>/` (events, metrics, checkpoints,
  reports/session_*.md, manifest, telemetry). Không ghi repo-root.
- `tools/analyze.py` + `tools/compare.py`: đã sửa (diff hiện tại) để ghi vào
  `data/runs/<run>/reports/…` / output chỉ định, KHÔNG đè `reports/final_analysis.md` chung.
  Test: `tests/test_analyze_isolation.py`, `tests/test_compare_isolation.py` (pass trong suite 176).

### 3. Audit world-hash / checkpoint cho state mới (C12 INVARIANT)
- `engine/world.py:303 world_hash()` bao phủ: agents (health/e_bac/persona/quan hệ gia đình),
  parcels, TOÀN BỘ số dư ledger, hợp đồng (id/trạng thái/clause), giá, quan hệ, entities +
  blueprints + research + tri_thuc + san_tier, **và `ChinhQuyen`** (truong_lang/thue_suat/
  luong_toi_thieu/nhiem_ky/nghiep_doan/phieu — dòng 340-348).
- Disease: hiệu ứng vào hash qua `agent.health`; cache `dich_benh_nam` là suy diễn tất định từ
  `w.rng` (không cần vào hash). Strike/riot set là transient (dựng lại mỗi tick).
- Checkpoint (`luu_checkpoint`) pickle TOÀN BỘ World (mọi field mới) + `nap_checkpoint` có
  migration cho checkpoint cũ (chinh_quyen/dich_benh_nam/giao_dich_dat…).
- **Kết luận C12: ĐẠT** — replay tái tạo hash cho cả run có state chính trị (test
  `test_chinh_tri_bat_khong_pha_tat_dinh`) và run counterfactual.

### 4. tools/verify_research_run.py (mới) — kiểm toán tái lập một run
Kiểm: manifest schema + trường bắt buộc; đồng nhất manifest↔meta; config digest tái dựng từ
overlay (SOFT/WARN khi base config trôi); scenario files sha256; metrics liên tục tới tick cuối;
events tồn tại; **replay rulebot/mock world-hash + audit mỗi tick** (real → skip, cần transcript).
Trả nonzero khi bằng chứng cứng thiếu. Đã chạy:
- `verify_research_run review_manifest_smoke` → ĐỦ BẰNG CHỨNG ✅ (replay hash trùng, config drift
  chỉ là WARN vì base config trôi sau run cũ).
- `verify_research_run agr_smoke_rb_s41` → tất cả PASS gồm config_digest_reproduced (run mới,
  config khớp), replay hash trùng, audit xanh mỗi tick.

### 5. Sửa reproducibility gap của replay
- `tools/replay.py`: trước đây dùng `load_config()` (chỉ config gốc) → replay run scenario/
  counterfactual sẽ LỆCH hash. Đã sửa: tái dựng overlay từ manifest (gồm scenario) + áp treatment
  `permute_personas`. Kiểm: replay `agr_smoke_rb_s41` (scenario) và
  `review_cf_smoke_v1_c2_permute_personas_s31` (permute) → **TRÙNG hash ✅**.

### 6. CI portable, không-network
- `.github/workflows/ci.yml` (mới): Python 3.11, cài pin từ `requirements.txt`, ruff + pytest
  (`THOC_BLOCK_NETWORK=1`, temp workspace), scenario validation (không overclaim), rulebot smoke +
  verify_research_run. Không gọi provider thật.

## Bằng chứng bổ sung
- Test verify tool (test-engineer độc lập): `tests/test_verify_research_run.py` — **6 passed**,
  ruff sạch, KHÔNG tìm thấy bug production. Gồm test end-to-end thật (rulebot 3 tick trong tmp →
  replay world-hash TRÙNG) + test hard/soft (thiếu manifest FAIL, metrics không liên tục FAIL,
  outcome hash lệch FAIL, config digest lệch chỉ WARN).
- Gate độc lập T02+T03: xem `docs/reviews/T02-T03-qa.md` (qa-verifier + reproducibility-steward).
