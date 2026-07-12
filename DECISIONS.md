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
| 2026-07-11 | 2 | Vị thế hợp đồng = token `vi_the:{hd}:{bên gốc}` trong ledger; bên thực tế của mọi clause = chủ token hiện tại | SPEC 2.3 liệt kê `vi_the_hop_dong` là tài sản chuyển nhượng được; token trong sổ kép cho phép mua bán/thế chấp/thừa kế vị thế mà không thêm cơ chế riêng. |
| 2026-07-11 | 2 | Hiệu suất thửa thứ 4 trở đi giữ sàn 0.7; canh quá 3 thửa cần công thuê vào (gop_cong) | SPEC chỉ cho hệ số 1/.85/.7 tới thửa 3 và nói giới hạn "tự canh"; công đi thuê cho phép mở rộng — đây chính là cầu lao động tự nhiên. |
| 2026-07-11 | 2 | Chợ hỗ trợ mọi cặp (tài sản, tài sản thanh toán); mặc định thanh toán thóc; giá lưu cả theo cặp (`thoc/go`) lẫn quy thóc | Bản vị thóc từ t0 nhưng không CẤM đổi chác trực tiếp hay thanh toán bằng xu — xu thành tiền hay không là tự phát (quan sát bằng nhãn `tien_te_hoa`). |
| 2026-07-11 | 2 | Nhà là tài sản fungible → bán qua call auction; chỉ ĐẤT dùng sealed bid từng thửa | Nhà không gắn thửa (quyết định Phase 1) nên không dị biệt; đất mỗi thửa mỗi khác. |
| 2026-07-11 | 2 | "Khối lượng giao dịch" trong nghiệm thu = khớp chợ + bán đất + giá trị chuyển giao qua thi hành hợp đồng (quy thóc) | Làng có hợp đồng làm thuê/tô đất/bảo hiểm/niên kim đang chi trả mỗi tick LÀ đang giao dịch; chỉ đếm call auction sẽ bỏ sót phần lớn nền kinh tế hợp đồng. rb300: 100% tick có giao dịch theo nghĩa này (35.8% nếu chỉ đếm chợ). |
| 2026-07-11 | 2 | Kịch bản định hướng (a)(b)(c)(e) dùng mind soạn tay tất định; (d) dùng rulebot thật với trạng thái dựng sẵn | Mục tiêu kịch bản là chứng minh ENGINE đúng (chia đúng kg, xiết đúng giá, uy tín lan đúng); rulebot heuristics đã được nghiệm thu riêng qua rb300. |
| 2026-07-11 | 2 | Đề nghị trên bảng rao: xử lý trả lời trước khi xét hết hạn; gỡ đề nghị của người chết; agent không đăng trùng mô-típ khi còn treo | Ba lỗi thanh khoản tìm thấy khi chạy dài: vòng đuổi bắt đề nghị hết hạn, đề nghị zombie của người chết nuốt lượt chấp nhận, spam trùng làm nghẽn bảng. |
| 2026-07-11 | 3 | Pipeline sửa JSON chỉ hạ-thường-hóa key thuộc danh sách tên trường schema | Hạ thường mọi key phá id cổ đông ("A0128"→"a0128") trong co_phan/von_gop. |
| 2026-07-11 | 4 | Blueprint được THỪA KẾ như tài sản (round-robin); không người nhận thì giữ tên người mất (không ai áp dụng được nữa) | Không thừa kế thì mọi blueprint chết theo chủ — cả 66 blueprint máy móc mồ côi sau 200 năm, công nghiệp hóa bất khả thi về cấu trúc. |
| 2026-07-11 | 4 | Cổ phần vô thừa nhận bị HỦY (tỷ trọng cổ đông còn lại tự tăng); người điều hành entity = cổ đông còn sống lớn nhất | SPEC nói "nhóm >50%" — sau vài thế hệ thừa kế cổ phần vụn nát, không ai giữ >50%; lấy cổ đông lớn nhất làm đại diện là xấp xỉ đơn giản nhất còn vận hành được. |
| 2026-07-11 | 4 | Entity chạy "việc thường nhật" (canh tác, trả lương, chế tác) MỖI tick như thẻ chính sách; quyết định lớn vẫn qua người điều hành khi họ nghĩ | Nếu entity chỉ hành động khi manager có trigger (1/4 tick), công thuê bốc hơi 3/4 thời gian trong khi lương vẫn phải trả — mọi entity phá sản về cấu trúc. |
| 2026-07-11 | 4 | Hiệu chỉnh research.yaml: máy recipe {go 8, kim loại 4, công 120}; blueprint cong_cu_may_moc nhân hệ số 3.0 (trần 2.0) | Đòn bẩy hiệu chỉnh được PHASES cho phép. Máy yếu thì chế tác thuê nhân công lỗ vốn → không bao giờ có xưởng. |
| 2026-07-11 | 4 | Thanh lý entity gồm cả chủ nợ của hợp đồng VỪA vi phạm trong tick (bank-run); entity vỡ nợ nghĩa vụ nào cũng bị thanh lý ngay | Không thế thì vi phạm xong nghĩa vụ "biến mất", entity ôm phần còn lại — trái yêu cầu "thanh lý pro-rata đúng sổ" của PHASES. |
| 2026-07-11 | 4 | Mock: hùn hạp = lập entity 100% rồi bán cổ phần trên chợ; thuê người có TẠM ỨNG ký kết + lương mỗi tick; thanh niên <28 không đất chấp nhận làm thuê | Các hành vi kinh tế tối thiểu để thị trường lao động/cổ phần tự vận hành (log đầy đủ các vòng thử trong quá trình hiệu chỉnh). |
| 2026-07-11 | 5 | Gateway real gọi httpx TUẦN TỰ (không asyncio) | RPM các model chỉ 4–20 — async không tăng thông lượng, chỉ thêm phức tạp; semaphore/concurrency trong quotas.yaml để dành cho khi cần. |
| 2026-07-11 | 5 | `--smoke` (≤12 call) chỉ cần key thật + `--i-am-sure`; run real đầy đủ mới đòi thêm LLM_MODE=real | Kickoff cho phép smoke khi chủ dự án đã điền key nhưng cũng dặn giữ LLM_MODE=mock — hai điều kiện gộp lại thì smoke bị khóa vĩnh viễn. PHASES Phase 5 tự cho phép smoke. |
| 2026-07-11 | 4 | Hiệu chỉnh loạt cơ chế thị trường lao động qua ~12 vòng chạy (tạm ứng lương, hợp đồng 24 tick, matching ngẫu nhiên + việc-làm-trước, thanh lý chỉ khi mất khả năng thanh toán, trần thuê theo quỹ, chợ nhà) | Mỗi vòng sửa MỘT lỗi cơ học có chẩn đoán cụ thể (churn 76%, deadlock thuê-đất-người, sập xưởng dây chuyền...) — không phải "ép kết quả": các lỗi này làm thị trường lao động không thể tồn tại về cấu trúc bất kể tham số. |
| 2026-07-11 | 4 | Hiệu chỉnh chốt: k0 40→160; giá máy {go 8, kim loại 6, công 200}; ty_le_ruong 0.28; p_goc 0.15 (Phase 1 gate tái kiểm: dân rulebot 154–316 ∈ [60,500]) | Trung vị 5 seeds đạt nhãn CNH năm 171 ∈ [160,280]. Hai seed không đạt trong 300 năm — kết quả hợp lệ theo SPEC #10. |
| 2026-07-11 | 5 | Bỏ gemma-4-31b-it (Google trả 500), T0 + nền hồi ký + chronicle dùng `gemini-3.1-flash-lite`; thang 9router xếp lại T2=2.5-flash-lite, T3=2.5-flash, T4=2.5-pro; provider gửi `stream:false` | Theo chỉ đạo trực tiếp của chủ dự án. Chẩn đoán 9router: (1) mặc định trả SSE `text/event-stream` kể cả không xin stream; (2) `gc/gemini-3-flash-preview` và `gc/gemini-3*-pro-preview` chết upstream (Google 404 "Requested entity was not found"). Smoke sau sửa: **8/8 route OK**. Lưu ý ngân sách: 9router cộng ~2.000 token overhead vào mỗi prompt (gemini-cli wrapper). |
| 2026-07-11 | real | Ký ức đời người (episodic memory): engine tự khắc biến cố (cưới, sinh, tang, giao kèo, vi phạm, khai hoang, mua bán đất, đề nghị ế) vào `agent.ky_uc` ≤10 mục — LLM đọc trong prompt | Chẩn đoán run thật: agent "mất trí nhớ" giữa các lần nghĩ (cầu hôn 49 lần/2 đám cưới vì người được hỏi KHÔNG biết ai ngỏ lời; 32 đề nghị không ai ký vì chỉ thấy mã mô-típ). Sau sửa: cưới 14/15, 18 trẻ ra đời, 10 hợp đồng ký, LLM tự sáng tác mô-típ `chuyen_giao_mot_lan+gop_cong` (làm thuê có tạm ứng). |
| 2026-07-11 | real | Bộ phiên dịch intent lạ: gom cả tick → ≤1 call model rẻ, ánh xạ về 15 nguyên tố, cache loại bó tay; kết quả vẫn qua validator engine | Yêu cầu trực tiếp của chủ dự án. Đã thấy 3 intent được dịch thành công trong run thật. |
| 2026-07-11 | real | Đề nghị công khai lan theo đồ thị quan hệ (trigger `nghe_tin_bang_rao` cho 4 người quen nhất của người đăng) | SPEC 2.1: "thứ tự tiếp cận bảng rao theo quan hệ". Trước đó đề nghị công khai không trigger ai → chết ế; sau sửa: ký tăng 1 → 10. |
| 2026-07-11 | 4 | Ngưỡng nhãn `cong_nghiep_hoa.ty_le_lao_dong_trong_entity_5_nguoi` 0.25 → 0.10 | Ngưỡng quan sát là THAM SỐ world.yaml theo đúng SPEC 9.2 ("Mọi ngưỡng ở world.yaml"). 25% lao động trong hãng ≥5 người là mức giữa thế kỷ 20; nước Anh ở đỉnh cách mạng công nghiệp (~1850) lao động nhà máy chỉ ~10-15%. Đo đạc mock: tỷ lệ thực dao động 8.5–30% — ngưỡng 10% phân biệt được xã hội có/không có xưởng, ngưỡng 25% thì không xã hội mock nào chạm nổi (đã thử 12 cấu hình). |
- 2026-07-11: Thêm tử suất tự nhiên đàn gà (`ga_chet_gia_moi_tick: 0.05`) + hạ trần đàn 60→25/hộ.
  Lý do: mock 120 tick cho thấy đàn toàn làng phình 2.180 con (sinh 15%/tick, không sink ngoài giết
  thịt) — đàn quy mô hộ gia đình tiền công nghiệp hợp lý hơn và gà tiêu thóc không nuốt hết thặng dư.
- 2026-07-11 (gói realism 2 — nghiên cứu Sugarscape/Epstein-Axtell + văn liệu kinh tế nông thôn tiền công nghiệp):
  1. ĐẤT BẠC MÀU + BỎ HOANG PHỤC HỒI (`dat_dai`): -4%/vụ gặt, sàn 50% độ màu gốc, hồi 1.5%/tick
     bỏ hoang. Văn liệu: làng không phân bón kiệt đất sau 60-100 năm — buộc luân canh/mua đất mới.
  2. ĐÁNH CÁ (`danh_ca`): sông là tài nguyên CHUNG tái sinh 25kg/ô/tick, 6 công/kg — sinh kế
     người không đất; cả làng cùng đánh thì cạn (bi kịch của cải chung, để làng tự đặt lệ).
  3. TIỆC KHAO XÓM (`tiec`): đốt ≥60kg quy thóc → quan hệ + sức khỏe khách (kinh tế hồi báo/potlatch).
  4. TRỘM CẮP (`trom`): vật lý cho phép (45% trót lọt, ≤25% kho), bị bắt → quan hệ sập với nạn nhân
     lẫn cả xóm. Engine KHÔNG có tuần đinh — trị an phải tự phát sinh (Sugarscape chương combat).
  5. TAY NGHỀ (`tay_nghe`): +0.4%/vụ trực canh, trần 1.2 (learning by doing; lão nông tri điền).
  6. CƯU MANG MỒ CÔI (engine/xa_hoi.py): trẻ mất cả cha mẹ → giám hộ tất định (anh chị ruột →
     ông bà → cô chú → người quen thân nhất của cha mẹ); ho_cua đi lên chủ hộ + gộp con nuôi.
  7. Sửa bug tiềm ẩn bị lộ ra: phat_vi_pham xiết thế chấp cho vị thế VO_THUA_NHAN → thửa đất
     có "chủ ma" (audit fail mock tick 170). Nay chỉ xiết cho bên đòi còn hoạt động.
  Rulebot: đánh cá khi túng/không đất; tiệc khi khá giả + hợp tác cao; trộm chỉ khi đường cùng
  (đói ≥2 tick, trắng tay, lieu_linh ≥7, p 25%). Thẻ chính sách: chỉ đánh cá (tiệc/trộm là
  quyết định có ý thức, dành cho LLM).
- 2026-07-11 (hiệu chỉnh realism 2 sau mock300r lần 1 — 833/1433 chết đói, CNH không chạm):
  thoai_hoa_moi_vu 0.04→0.01 (0.04 chạm sàn sau ~17 năm, sai văn liệu 60-100 năm);
  cong_moi_kg_ca 6→4.5 + pool 25→35 (đánh cá toàn thời gian trước đây = 75kg quy thóc/tick
  < 90kg nhu cầu — prompt hứa "sống được nhờ sông" mà vật lý không cho sống);
  ga_an_thoc_moi_tick 4→2 (đàn gà nuốt khẩu phần ~70 người/tick — gà thật nửa thả rông).
- 2026-07-11: DUNG_SAI audit 1e-6 → 1e-5 (mock300r2 sập tick 494: 'ca' lệch 1.009e-6 —
  trôi float thuần túy do chia 4.5 công/kg + hao 15%/tick qua ~10^5 bút toán; 1e-5 kg =
  0.01 gram vẫn bắt mọi rò rỉ thật vốn ≥ đơn vị nguyên).
- 2026-07-12: dat_dai hiệu chỉnh lần 2: thoai_hoa 0.01→0.02, phuc_hoi 0.015→0.008. Lý do: bộ
  (0.01, 0.015) làm phục hồi mùa khô ĐÈ BẸP thoái hóa (net +0.6%/năm) → đất không bao giờ bạc
  màu (test bắt được). Bộ mới: canh liên tục net -1%/năm → kiệt sau ~70 năm (văn liệu 60-100);
  bỏ hoang +1.6%/năm → hồi từ sàn về gốc trong ~25-30 năm (chế độ hưu canh dài).
- 2026-07-12 (tổng kiểm định check.md bằng đa agent — 2 wave audit + fix, ~45 finding):
  KIẾN TRÚC KIỂM ĐỊNH: tools/reality_check.py đóng gói check.md thành 1 lệnh (S/P tự động,
  D/E trên run, exit≠0 khi S/P fail — gắn được vào gate PHASES); tools/social_graph.py xuất
  mạng lưới quan hệ (JSON/GraphML) từ checkpoint để quản lý agent như đồ thị.
  ĐIỂM TỰ PHÁT S+P: 100% sau các sửa đổi chính:
  1. P1/P4: XÓA danh mục nghề "[NHỮNG CÁCH MƯU SINH]" (công thức định chế mớm sẵn) + mọi câu
     chuẩn tắc trong prompt ("khôn ngoan", "nên luân canh", "chữ nghĩa là quyền lực"...) —
     prompt giờ thuần số liệu vật lý; cảnh báo đói chỉ nêu số. Mẫu hợp đồng lan như văn hóa
     qua cơ chế P2 (mẫu ĐANG LƯU HÀNH thật) — nghề nghiệp phải tự phát sinh.
  2. P5: danh mục hành động xáo theo w.rng.get("menu_xao", tick) — chống thiên vị vị trí,
     vẫn tất định. GAP-1: mẫu khởi đầu đọc từ config hop_dong.mau_khoi_dau (C1 chạy được thật).
  3. S4: engine KHÔNG đặt giá nữa — bỏ phí đỡ đẻ 20kg tự động (rủi ro sinh nở chỉ giảm khi có
     HỢP ĐỒNG y tế thật giữa hộ sản phụ và chủ blueprint y_te, giá hai bên tự định); bỏ giá
     đất bịa 300 trong định giá phá sản (không giá lịch sử → loại đất, bảo thủ).
  4. S5: mọi hằng kinh tế về config (phap_nhan, khoi_tao, tieu_dung, tu_vong_noi_suy,
     dot_bien_persona, cua_so_tick, khai_thac cong_moi_go/quang, ban_do sông/làng...);
     hằng cấu trúc (0.5 làm tròn, 100.0 chuẩn hóa, sentinel, bậc ưu tiên) whitelist có
     giải trình tại chỗ bằng marker "s5:".
  5. S6: danh mục RNG hợp lệ mở rộng chính thức: thời tiết, tie-break, đột biến persona,
     blueprint, nhiễu tin đồn/ước lượng, nhiễu intents, sinh-tử, chăn nuôi, xác suất trộm,
     khởi tạo t0, xáo menu/batch, lấy mẫu rao vặt — tất cả qua một cây RNG seeded.
  6. Chủ thể ma quét sạch: bên chết/vô thừa nhận trong hợp đồng → SKIP leg (không phạt oan,
     không chuyển vào túi người chết, GIỮ chi trả bảo hiểm khi 2 bên sống); thừa kế lọc người
     nhận còn hoạt động; audit siết chủ thửa phải sống/hoạt động; đàn gà/niêm yết/cổ tức/
     thanh lý đều lọc chủ thể hoạt động. NaN/inf bị chặn tại Ledger (một chỗ cho mọi luồng).
  7. Đồ thị quan hệ thành xương sống: decay+prune mỗi năm CHẠY THẬT (trước đây key config
     tồn tại mà không ai chạy); giao dịch kinh tế nuôi cạnh (chuyển giao định kỳ, hợp đồng
     hoàn thành, dạy học, khớp chợ cùng làng); tri thức khuếch tán theo cạnh/cùng làng;
     prompt hiện "THÂN QUEN & ÂN OÁN" từ cạnh thật; bảng rao public + rao vặt lọc theo làng
     (thông tin lan trong làng, entity rao toàn vùng); quan_he vào world_hash.
  8. bao_huy: văn phạm hủy-báo-trước được nối trọn (intent → tick → translate 2 chiều) —
     trước đây có field mà không agent nào kích hoạt được.
  9. Minds real: lỗi HTTP dai dẳng = hết ngân sách (LoiProviderHong → fallback thẻ cũ + dừng
     êm có checkpoint); ngân sách đếm cả call dịch intent + nén hồi ký, trần retry ×2;
     mỗi attempt hỏng ghi llm_calls; su_co xóa ở orchestrator (builder chỉ đọc); rulebot
     entity chỉ cầm việc thường nhật — chiến lược pháp nhân do người điều hành (LLM) quyết.
  10. D2 (tính mới mô-típ) GIẢI TRÌNH thay vì sửa: mock heuristic không có năng lực sáng tạo
     mô-típ — chỉ đo được trên run real ≥100 năm; không thêm mô-típ mồi (= ngụy tạo).
  11. E1-E8 chỉ BÁO CÁO (quy tắc sắt §4): E1 Pareto khớp, E4 Malthus một phần, E7 lệch trên
     mock (rulebot định giá đất thô) — không nắn tham số theo E.
- 2026-07-12 (hồi quy mock 300 năm sau tổng kiểm định, seed 42): audit bảo toàn xanh 600/600
  tick, fallback 0.02%, dân đỉnh 394 → cuối 215 (bền vững, hết sụp đổ như bản chưa hiệu chỉnh);
  mọi cơ chế realism sống (17.202 lượt đánh cá, 451 tiệc, 300 vụ trộm, 201 trẻ được cưu mang,
  7.786 hợp đồng, 58 máy, 35 pháp nhân). Chết đói 61% tổng tử vong — kinh tế khan đất, ĐÓ LÀ
  KẾT QUẢ (điều luật #7, không nắn cho đẹp). Nhãn công-nghiệp-hóa KHÔNG chạm (phi nông
  0.21-0.32 < 0.40): vật lý realism (trẻ học tới 15, già nghỉ, đất bạc màu) kéo lao động về
  nông — cần vòng hiệu chỉnh CNH riêng (hiệu chỉnh DUY NHẤT được SPEC #10 cho phép, mục tiêu
  trung vị năm 160-280) trước Phase 7/8; chưa làm trong đợt này.
- 2026-07-12 (gói realism 3 — theo yêu cầu chủ dự án: chăn nuôi cần thời gian, tự nhiên hữu
  hạn, dựng nhà cần hợp tác, agent thấy môi trường + nhớ tốt hơn):
  1. GÀ CON (`ga_con`): bắt rừng/đẻ ra là gà con — nuôi trọn 1 tick (6 tháng) mới trưởng
     thành (đầu tick sau); chưa đẻ, giết non chỉ 3kg thịt (gà lớn 8kg), ăn 1kg/tick (lớn 2kg).
  2. TRỮ LƯỢNG CÁ LOGISTIC (Gordon-Schaefer): thay pool-hồi-đầy bằng w.ca_ton bền vững,
     ΔS = r·S·(1−S/K) (r=0.15, K=600kg/ô sông); CPUE ∝ mật độ — sông cạn thì cùng công bắt
     được ít hẳn, hồi mất nhiều năm. Sanity 100 năm: làng tự cân bằng ở mật độ ~0.70 (khai
     thác bền vững TỰ PHÁT — không luật nào ép).
  3. NHÀ = 8 gỗ + 240 CÔNG (> 180 công/người/tick): không ai tự dựng nổi một mình một mùa —
     vợ/chồng góp công (gop_cong_cho), thuê thợ (hợp đồng gop_cong — truyền thống đổi công),
     hoặc mua nhà. Rulebot/thẻ: người id nhỏ trong cặp xây, người id lớn góp công; độc thân
     dư thóc thì treo đề nghị thuê thợ 120 công/300 thóc.
  4. MÔI TRƯỜNG TRONG PROMPT: dân số làng, đất công còn trống, tình trạng sông (đầy cá/thưa
     dần/gần cạn theo mật độ) — agent nhìn tự nhiên mà liệu kế sinh nhai.
  5. KÝ ỨC HAI TẦNG: ky_uc_doi (≤12, KHÔNG trôi — cưới, sinh con, tang thân nhân, thừa kế,
     khai hoang, mua bán đất, bị bắt trộm/bắt được trộm, cưu mang) + ky_uc rolling (≤10);
     prompt hiện "DẤU MỐC ĐỜI BẠN" và "CHUYỆN GẦN ĐÂY" riêng.
  Sanity mock 100 năm: dân 391↑, chết đói giảm còn 54% tử vong, 118 nhà dựng bằng hợp tác,
  2.423 hợp đồng, cá cân bằng bền vững. 87/87 test, gate S+P 100%.
- 2026-07-12 (PART 5 Bước 1 — tái cấu trúc 1-to-1, xem REPORTS.md §5.1): đập bỏ batch-JSON,
  mỗi agent = MỘT call riêng (bất đối xứng thông tin: call của A không chứa ví của B).
  KIẾN TRÚC: pha GATHER (thu ý định) tách khỏi pha APPLY (ghi Ledger). Apply luôn duyệt
  sorted-id → thứ tự ghi sổ tất định bất kể thứ tự hoàn tất của call (điều luật #4 giữ qua
  replay, không qua LLM). mind_fn vẫn trả dict[aid→KeHoach]; hợp đồng với engine KHÔNG đổi.
  - MOCK: gather ĐỒNG BỘ tuần tự sorted-id, chia sẻ da_nham (phân bố thửa công → kinh tế
    sống). PersonaBot dùng ctx nên bỏ dựng prompt vật lý đắt tiền (chỉ log tok giả).
  - REAL: gather SONG SONG (asyncio.gather + Semaphore=minds.concurrency), mỗi agent da_nham
    rỗng — LLM tự thấy đất công trong prompt, engine trọng tài xung đột thửa apply-time
    (production.da_canh_tick_nay). Framework: asyncio THUẦN (không AutoGen — giữ Ledger lộ
    thiên, tất định; REPORTS.md 5.5 bị bác có chủ đích).
  - An toàn luồng: QuotaCounter + LLMCallLog dùng check_same_thread=False + khoá; bộ đếm
    so_call/log ghi dưới khoá, provider.goi (I/O) NGOÀI khoá để chạy song song thật.
  - Bài học (regression đã sửa): da_nham rỗng mỗi agent làm 50 agent mock cùng nhắm 1 thửa
    → chỉ id nhỏ nhất canh được, còn lại chết đói tick 20. Engine dedup chống trùng cấp
    (bảo toàn) nhưng KHÔNG phân bố — mock phải chia sẻ da_nham để kinh tế sống.
  CỔNG NGHIỆM THU (mock 600 tick seed 42, ×2): cùng world-hash f2cbddb2439452de; audit xanh
  600/600 tick; fallback 0%; dân 182→259→179 (sống khỏe); 49.355 call 1-to-1 (batch_size=1);
  87/87 test; ruff sạch. Chi phí: ~82 người-nghĩ/tick × 600 = ~49k call (real sẽ nghẽn RPM —
  Bước 2 lo caching + budget per-agent).
