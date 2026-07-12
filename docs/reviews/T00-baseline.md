# T00 — Baseline chỉ-đọc & bản đồ mâu thuẫn

Ngày: 2026-07-12. Owner: integration-manager (phiên tự chủ). Chế độ: không mạng, không LLM
thật, không đọc `.env`. Đây là snapshot chỉ-đọc; không có file nào bị stage/reset/ghi đè.

## 1. Snapshot Git (chỉ đọc)

- Commit hiện tại: `d23b86cdbdadbd9d25b19c8a2cb6d0c4ec86ac8d`
  (`real20: hiệu chỉnh nghi_dinh_ky 1→4 (bi kịch commons cold-start) + bầu cử 20→10 tick`, 2026-07-12).
- Branch: `main`. Git user: Nguyễn Văn Thân.
- `git diff --check`: chỉ có cảnh báo LF→CRLF (line-ending), **không có lỗi whitespace/conflict marker**.
- `git status --short`: 18 file modified (M), nhiều file/thư mục mới untracked (??).
  - Modified (M): `README.md`, `config/world.yaml`, `engine/{config,consumption,market,metrics,politics,tick,world}.py`,
    `minds/{orchestrator,policy_cards,prompts,rulebot}.py`, `run.py`,
    `tools/{analyze,compare,reality_check}.py`, `reports/{final_analysis,reality_check_static}.md`.
  - Untracked mới quan trọng: `engine/economy.py`, `minds/safety.py`, `scenarios/`,
    `tools/{counterfactual,experiments,validation}.py`, 8 test mới, `.claude/agents/*`,
    `REVIEW.md`, `TASKS.md`, nhiều report review mới.

**Không mất thay đổi nào**: mọi thao tác dưới đây là read-only + tạo file mới trong `docs/`,
`.tmp/`. Working tree bẩn của người dùng được giữ nguyên.

## 2. Môi trường

- Python: **3.11.15** (conda env `thoc-env`).
- Gói lõi khớp `requirements.txt`: numpy 1.26.4, pandas 2.2.3, pydantic 2.9.2 (pin đầy đủ trong
  `requirements.txt`, 17 gói).
- `.env` tồn tại trong tree nhưng **đã nằm trong `.gitignore`** (dòng 2) → không thể commit; không đọc/in.
- `data/` cũng gitignored → run artifacts không vào git.

## 3. Test collection & suite (temp path trong workspace)

- Collection: **170 tests collected in 2.40s** (khớp con số TASKS.md nêu).
- Full suite: `conda run -n thoc-env python -m pytest -q --basetemp .tmp/pytest -p no:cacheprovider`
  → **170 passed, 14 warnings in 82.41s, EXIT=0**. Log: `.tmp/logs/T00_pytest.log`.
- **Giải quyết blocker ACL cũ**: REVIEW.md/TASKS.md ghi 12 lỗi fixture `tmp_path` do quyền thư
  mục tạm Windows. Khi trỏ `--basetemp` vào đường workspace (`.tmp/pytest`), **toàn bộ 170 pass**.
  → blocker là môi trường (đường tmp mặc định), không phải assertion mô hình. Đây là lệnh chuẩn
  cho các task sau.

## 4. Lint (ruff 0.7.4)

- Lệnh: `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 conda run -n thoc-env python -m ruff check .`
  (env encoding bắt buộc — xem §6). Log: `.tmp/logs/T00_ruff.log`.
- **5 lỗi**, đều trong file mới/đã sửa của diff hiện tại:
  1. `minds/orchestrator.py:10` — I001 import chưa sắp (auto-fixable).
  2. `tests/test_disease_shock.py:5` — F401 `engine.intents.KeHoach` import thừa (auto-fixable).
  3. `tests/test_experiments.py:3` — I001 (auto-fixable).
  4. `tests/test_household_economics.py:3` — I001 (auto-fixable).
  5. `tools/counterfactual.py:207` — **B023** closure `fmt` không bind biến vòng lặp `s`
     (bug thật, không phải style — xem T00-engine-surgeon review + T02).
- **Cập nhật (đã sửa trong T00 sau review engine-surgeon)**: B023 sửa bằng bind biến vòng lặp
  (`tools/counterfactual.py:206`), 4 lỗi còn lại `ruff check . --fix`. Sau sửa: `ruff check .` →
  **All checks passed**; 13 test liên quan vẫn pass. Không đổi logic. Xem
  `T00-engine-surgeon-uncommitted.md`.

## 5. Inventory scenario & run

- Scenario có sẵn: **`preindustrial_closed_v1`** — `validation_tier: mechanism_benchmark`;
  `targets_in_sample.yaml`/`targets_holdout.yaml` đều `targets: []`; provenance chỉ có
  `design_assumption`. **Không đổi nhãn này** (điều kiện đầu vào T-doc §2).
- Scenario cần tạo (T03): **`agrarian_transition_v1`** — chưa tồn tại.
- `data/runs/`: ~45 run cũ (rb300, mock300*, real6/15/20/30*, cal_*, det*, quota_counters.sqlite…).
  **Không xóa/ghi đè** bất kỳ run nào.
- `tools/validation.py` đã có: enforce target phải có id/metric/tick|year/unit/source + expected|[lower,upper];
  cờ `empirical_ready` chỉ True khi tier=="empirical" ∧ có target in_sample+holdout ∧ provenance đủ cột.
  → nền tốt cho T03; cần siết thêm (units, design_assumption gate) trong T03.

## 6. Ghi chú môi trường quan trọng (blocker đã vòng tránh)

`conda run -n thoc-env <cmd>` **crash** với `UnicodeEncodeError: 'charmap' codec ... '�'`
khi lệnh con in ký tự ngoài cp1252 (ruff diagnostics, tiếng Việt). Lỗi ở conda `main_run.py`
`print(response.stdout)`, KHÔNG phải ở tool. Vòng tránh (dùng cho mọi lệnh sau):
- Prefix `PYTHONIOENCODING=utf-8 PYTHONUTF8=1 conda run ...`, HOẶC
- Redirect stdout ra file trong cùng lệnh (`> log 2>&1`) — cách pytest đã chạy được.

## 7. Kết luận T00

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Git snapshot | Sạch, không mất thay đổi | §1, `git status/diff --check` |
| Môi trường | Python 3.11.15, gói khớp pin | §2 |
| Test suite | 170 passed (temp workspace) | §3, `.tmp/logs/T00_pytest.log` |
| Lint | 5 lỗi (4 trivial + 1 B023 thật) | §4, `.tmp/logs/T00_ruff.log` |
| Scenario/run inventory | Ghi nhận, không sửa | §5 |
| Conflict map | Xem `T00-spec-governor-conflict-map.md` | file riêng |
| Review diff bẩn | Xem `T00-engine-surgeon-uncommitted.md` | file riêng |

**Gate T00**: baseline trung thực ✓; suite xanh trên temp path writable ✓ (blocker ACL cũ được
vòng tránh, có bằng chứng); lint có kết quả ✓; **không thay đổi nào bị mất** ✓.
