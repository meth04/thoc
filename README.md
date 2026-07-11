# THÓC — Bộ khởi động cho Claude Code

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
`reports/final_analysis.md` (ma trận dịch chuyển giai cấp 12 thế hệ, Gini, phân bố của cải
theo giai cấp, thu nhập theo "trí thông minh"), `final.mp4` (timelapse dọc 9:16 để chia sẻ),
và toàn bộ log để bất kỳ ai replay lại 300 năm lịch sử.
