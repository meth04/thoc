# THÓC — Bộ khởi động cho Claude Code

> **⚠️ Định hướng khoa học hiện hành:** đọc `docs/MODEL_CHARTER.md` và
> `docs/adr/0001-scope-and-institutional-layers.md` trước. THÓC hiện là **mechanism benchmark**
> (không phải mô phỏng nền kinh tế thật). Quy trình nghiên cứu không-mạng và phân biệt scenario
> `preindustrial_closed_v1` (legacy) vs `agrarian_transition_v1` (mới) sẽ được cập nhật đầy đủ ở
> T11. Hướng dẫn provider/real bên dưới là *opt-in future work*, không phải mặc định.

## Quy trình nghiên cứu KHÔNG-MẠNG (mặc định hiện tại)

THÓC là **mechanism benchmark** (đọc `docs/MODEL_CHARTER.md`). Mọi lệnh chạy qua conda env
`thoc-env`, KHÔNG gọi provider/LLM thật. Trên Windows, nếu `conda run` lỗi encoding, prefix
`PYTHONIOENCODING=utf-8 PYTHONUTF8=1`.

```bash
# 1. Kiểm tra cục bộ một-lệnh (ruff + test + validation + smoke + verify tái lập):
conda run -n thoc-env python -m tools.verify_local

# 2. Toàn bộ test (temp trong workspace, guard mạng):
mkdir -p .tmp/pytest
THOC_BLOCK_NETWORK=1 conda run -n thoc-env python -m pytest -q --basetemp .tmp/pytest -p no:cacheprovider

# 3. Validate scenario (không được overclaim):
conda run -n thoc-env python -m tools.validation agrarian_transition_v1

# 4. Chạy baseline rulebot + kiểm toán tái lập:
conda run -n thoc-env python run.py --mode rulebot --ticks 20 --seed 41 \
    --scenario agrarian_transition_v1 --run-name agr_rb_s41
conda run -n thoc-env python -m tools.verify_research_run agr_rb_s41
conda run -n thoc-env python -m tools.replay agr_rb_s41 --verify

# 5. Ensemble phản chứng paired-seed (smoke; full 30-seed = PENDING_COMPUTE):
conda run -n thoc-env python -m tools.counterfactual \
    --scenario agrarian_transition_v1 --seeds 41 42 43 --ticks 60 --mode rulebot --prefix agr_cf
```

**Hai scenario, KHÔNG lẫn nhau** (ADR `docs/adr/0001`):
- `preindustrial_closed_v1` — legacy mechanism/regression benchmark.
- `agrarian_transition_v1` — benchmark mới (nông nghiệp→chợ→tín dụng→tiền→tài khóa); tầng chính
  trị/bạo động TẮT mặc định.

Cả hai đều `validation_tier: mechanism_benchmark` — **chưa** phải empirical (thiếu data/calibration/
holdout; xem `reports/world_class_readiness.md`).

## (Legacy) Bootstrap real-provider — OPT-IN FUTURE WORK, không phải mặc định

> ⚠️ Phần dưới là hướng dẫn cũ chạy provider thật (Phase 5–8, HUMAN-GATE). KHÔNG dùng trong phiên
> nghiên cứu không-mạng. Chỉ bật khi có key + chủ dự án duyệt.

Bộ file này để bạn **copy nguyên vào một thư mục trống** rồi giao cho Claude Code tự xây
toàn bộ dự án mô phỏng kinh tế 300 năm. Bạn gần như không phải động tay.

## Cách dùng (5 bước)

1. Tạo thư mục dự án (vd `thoc/`), copy toàn bộ nội dung bundle này vào
   (gồm `CLAUDE.md`, `SPEC.md`, `PHASES.md`, `KICKOFF_PROMPT.md`, `.env.example`, `config/`).
2. Mở Claude Code trong thư mục đó.
3. Dán nguyên văn prompt trong `KICKOFF_PROMPT.md`. Claude Code sẽ tự chạy Phase 0 → 6
   ở chế độ **mock** (không tốn một call API nào), tự kiểm thử, tự commit.
4. Khi nó dừng ở **HUMAN-GATE 1**: bạn điền 8 key vào `.env`, bật 9router, mở
   `config/models.yaml` sửa ID model cho đúng tài khoản của bạn (2 phút), rồi gõ
   **"chạy Phase 7"** — pilot thật 20 năm.
5. Đọc `reports/pilot_review.md`, ưng thì gõ **"chạy run chính"**. Từ đây mỗi tối bạn chỉ
   cần chạy lại một lệnh (Claude Code sẽ chỉ cho bạn) — hệ thống tự resume, tự dừng khi
   chạm ngân sách quota, tự xuất báo cáo phiên + clip video của đoạn vừa mô phỏng.

## Hai điểm duy nhất cần tay bạn
- Điền key vào `.env` và mở 9router (bước 4).
- Rà lại ID model trong `config/models.yaml` + `config/quotas.yaml` cho khớp tài khoản.

## Kết quả cuối
`data/runs/<ten-run>/reports/final_analysis.md` (ma trận dịch chuyển giai cấp 12 thế hệ, Gini, phân bố của cải
theo giai cấp, thu nhập theo "trí thông minh"), `final.mp4` (timelapse dọc 9:16 để chia sẻ),
và toàn bộ log để bất kỳ ai replay lại 300 năm lịch sử.
