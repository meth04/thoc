# DECISIONS.md — nhật ký quyết định khi SPEC im lặng hoặc mâu thuẫn

| Ngày | Phase | Quyết định | Lý do |
|---|---|---|---|
| 2026-07-11 | 0 | Bỏ qua `config/tech_tree.yaml` (không load, không dùng) | Mâu thuẫn SPEC v3 mục 3.5: "KHÔNG có danh sách phát minh định sẵn, KHÔNG có kỷ nguyên" — R&D mở theo `research.yaml`. SPEC thắng; file giữ lại làm di tích v2. |
| 2026-07-11 | 0 | Tạo lại conda env `thoc-env` bằng Python 3.11 (env cũ là 3.12, gần trống) | CLAUDE.md mục 1 quy định Python 3.11. |
| 2026-07-11 | 0 | Số dư ledger dùng float với EPSILON=1e-9, audit dung sai 1e-6 | Thóc/công là đại lượng liên tục (kg, ngày công); dung sai chặn sai số float tích lũy nhưng vẫn bắt được mọi luồng lậu thực chất. |
| 2026-07-11 | 0 | Transaction nguyên tử: kiểm tra toàn bộ (cân, luồng, không âm) trước khi cam kết | Đơn giản nhất bảo đảm điều luật #1+#2: thất bại không để lại state dở dang. |
| 2026-07-11 | 1 | Tuổi lưu bằng tick (6 tháng); "tuổi+1" ở bước 1 pipeline = +1 tick tuổi; tuổi năm = tick/2 | SPEC không nói rõ đơn vị; lưu tick chính xác hơn cho Gompertz nội suy. |
| 2026-07-11 | 1 | Persona 5 trục (1–9): `lieu_linh, cham_chi, trong_hoc, hop_tac, tiet_kiem` | SPEC 4.5 nói "5 trục" nhưng không đặt tên. Chọn 5 trục phủ các quyết định kinh tế chính. |
| 2026-07-11 | 1 | E ban đầu t0 seeded: 80% E0, 16% E1, 4% E2 | Học cần thầy E≥bậc mục tiêu; nếu 100% mù chữ thì chữ viết không bao giờ xuất hiện (deadlock). Gieo mầm tri thức tối thiểu, phần còn lại tự phát. |
| 2026-07-11 | 1 | Tự học: người E=k tự học lên k+1 với số tick GẤP ĐÔI (vẫn mất 50% công), không cần thầy | SPEC chỉ cho 2 đường học đều cần người E≥mục tiêu → E cao nhất t0 là trần vĩnh viễn (deadlock). Tự học đắt gấp đôi giữ vai trò thầy/trường tự phát vẫn kinh tế hơn. |
| 2026-07-11 | 1 | Khai thác không công cụ vẫn được nhưng hiệu suất 0.5 (thêm `khai_thac.hieu_suat_khong_cong_cu` vào world.yaml) | Công cụ cần gỗ, gỗ cần công cụ → deadlock vật lý ở t0. `can_cong_cu` hiểu là "cần để đạt hiệu suất đủ". |
| 2026-07-11 | 1 | Tài sản khởi đầu (200kg thóc/người) mint qua luồng đăng ký `khoi_tao` (chỉ tick 0) | Bảo toàn vẫn kiểm được: mọi kg thóc đều có nguồn ghi sổ. |
