# Prompt khởi động — dán nguyên văn vào Claude Code (mở trong thư mục chứa các file này)

```
Đây là dự án THÓC — mô phỏng 300 năm của một nền kinh tế khép kín bằng agent LLM.

Nhiệm vụ của bạn: xây dựng toàn bộ dự án từ đầu tới cuối, hoàn toàn tự động, theo đúng ba
file sau (đọc kỹ trước khi viết bất kỳ dòng code nào, theo đúng thứ tự):
1. CLAUDE.md  — luật vận hành, 7 điều luật bất khả xâm phạm, kỷ luật kiểm thử
2. SPEC.md    — thiết kế đầy đủ (nguồn chân lý duy nhất)
3. PHASES.md  — lộ trình Phase 0 → 8 với lệnh nghiệm thu từng phase

Yêu cầu thi hành:
- Tạo conda env `thoc-env` (Python 3.11) nếu chưa có; mọi lệnh chạy qua env này.
- `git init` ngay từ đầu; `.env` phải nằm trong .gitignore trước commit đầu tiên;
  copy `.env.example` thành `.env` (giữ LLM_MODE=mock).
- Thực hiện tuần tự Phase 0 → Phase 6. KHÔNG hỏi tôi bất cứ điều gì trong quãng này:
  gặp điểm chưa rõ thì tự chọn phương án đơn giản nhất đúng "nguyên tắc tự phát" trong
  CLAUDE.md và ghi vào DECISIONS.md rồi đi tiếp.
- Không được chuyển phase khi lệnh nghiệm thu của phase hiện tại chưa xanh. Dán kết quả
  nghiệm thu vào PROGRESS.md sau mỗi phase, commit "phase-N: ...".
- Tuyệt đối không thực hiện call API thật nào (trừ `--smoke` ở Phase 5 NẾU tôi đã điền key
  vào .env; nếu chưa có key thì đánh dấu PENDING KEYS và đi tiếp bằng FakeTransport).
- Mock phải hoạt động thật tốt: đây là tiêu chí quan trọng nhất — chạy trọn 300 năm mock
  end-to-end, mọi invariant bảo toàn xanh từng tick, fallback_rate < 5% với mock adversarial,
  render được video MP4 từ log, dashboard mở được.
- Hoàn tất Phase 6 thì dừng tại HUMAN-GATE 1: in báo cáo tổng nghiệm thu mock + hướng dẫn
  tôi điền key/mở 9router/rà models.yaml, và chờ tôi gõ "chạy Phase 7".

Bắt đầu từ Phase 0 ngay bây giờ.
```
