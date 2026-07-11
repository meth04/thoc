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
| 2026-07-11 | 1 | Hiệu chỉnh `sinh_san.p_goc` 0.22 → 0.13 trong world.yaml | Nghiệm thu Phase 1 yêu cầu dân số cuối ∈ [60,500]; với 0.22 cân bằng ~600–700 (thức ăn quá dồi dào nên sinh sản luôn max). PHASES cho phép chỉnh world.yaml. |
| 2026-07-11 | 1 | health_mult trong công thức gặt = 0.5 + 0.5×(health/100) | Công sinh ra đã tỷ lệ theo health; nhân thẳng health/100 nữa là phạt kép quá nặng. |
| 2026-07-11 | 1 | Nhà là tài sản đếm được trong sổ (không gắn thửa cụ thể); "có nhà ở" = hộ sở hữu ≥1 nhà | Đơn giản nhất; thị trường nhà Phase 2 = mua bán tài sản `nha` trên chợ. |
| 2026-07-11 | 1 | Trẻ em góp công = chuyển tài sản `cong` cho cha/mẹ qua ledger | Công là tài sản chuyển nhượng được (SPEC 2.3 coi công như tài sản sinh mỗi tick); giữ mọi dịch chuyển trong sổ kép. |
| 2026-07-11 | 1 | Tài sản vô thừa nhận → tài khoản `VO_THUA_NHAN`; đất vô thừa nhận → về công (chu=None) | SPEC chỉ nói "đất về công"; tài sản khác cần đích ghi sổ để không phá bảo toàn. |
| 2026-07-11 | 1 | Audit dùng dung sai tương đối `max(1e-6, tổng×1e-9)` | Seed 43 vỡ audit ở tick 489 do trôi float64 1e-6 trên tổng 1.36 triệu kg (sai số tương đối 7e-13 — không phải luồng lậu). Luồng lậu thật luôn ≥ gram nên vẫn bị bắt. |
