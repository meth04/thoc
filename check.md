# check.md — Giao thức tự kiểm định TÍNH THỰC TẾ (Claude Code tự chấm dự án)

Mục đích: trả lời một cách CÓ BẰNG CHỨNG câu hỏi của chủ dự án — *"môi trường này đã mang
tính thực tế cao nhất và ít mang tính setup nhất chưa?"* — thay vì trả lời bằng cảm tính.

Định nghĩa dùng trong toàn file:
- **Thực tế** = (a) engine tối giản như định luật vật lý, không chứa "cốt truyện";
  (b) hiện tượng nổi lên trong run KHỚP các quy luật thực nghiệm của kinh tế học
  mà KHÔNG hề được cài vào code; (c) hành vi đa dạng và truy được nguồn gốc về quyết định
  của agent, không phải về tham số của lập trình viên.
- **Setup** = bất cứ thứ gì định trước kết quả: định chế có tên trong engine, danh mục
  phát minh, hành vi theo nhãn giai cấp, tham số được nắn để "ra đúng chuyện hay",
  prompt mớm ý, mock heuristic rò rỉ sang mode real.

## 0. Ranh giới không thể xóa — KHÔNG tính là setup (nhưng phải TỐI GIẢN)
Ba thứ sau là giàn giáo bắt buộc; check.md không đòi xóa chúng, chỉ đòi chứng minh chúng
tối giản và trung lập:
1. **Vật lý** (bảo toàn, sinh học, recipe hàng cơ bản, thời tiết seeded) — không có vật lý
   thì LLM bịa ra tài nguyên và mô phỏng vô giá trị.
2. **Văn phạm hành động** (15 nguyên tố + 9 clause) — ngôn ngữ phải có ngữ pháp; kiểm định
   ở đây là ngữ pháp có ĐỦ TỔNG QUÁT không, chứ không phải có tồn tại hay không.
3. **Tri thức tiền huấn luyện của LLM** (anachronism) — không xóa được; chỉ khóa bằng
   action-gating + prompt trung lập, và TUYÊN BỐ trong README.

---

## 1. Kiểm định TĨNH — quét code & config (tự động hóa: `tools/reality_check.py`)
Xây script chạy được bằng một lệnh, xuất pass/fail từng mục:

- [S1] `grep -riE "bank|loan|company|firm|insurance|wage|salary" thoc/engine/` → 0 kết quả
  (trừ comment giải thích vì sao KHÔNG có). Định chế có tên chỉ được sống trong
  `observatory/` và `viz/`.
- [S2] Không tồn tại file/bảng liệt kê phát minh định sẵn; `research.yaml` chỉ chứa lĩnh vực
  + phân phối. `grep -ri "tech_tree\|unlock_list" thoc/` → 0.
- [S3] Không một nhánh `if` nào trong engine rẽ theo nhãn giai cấp/định chế:
  `grep -rE "class_|giai_cap|dia_chu|ta_dien" thoc/engine/` → 0 (nhãn chỉ ở observatory).
- [S4] Engine không gán giá: mọi giá đến từ auction/sealed-bid; `grep -ri "price ="` trong
  engine chỉ được xuất hiện ở module market với nguồn là khớp lệnh.
- [S5] Magic number: AST-scan engine, đếm hằng số > 1 chữ số nằm ngoài config → danh sách
  phải RỖNG (mọi tham số về YAML).
- [S6] Ngẫu nhiên ngoại sinh duy nhất là thời tiết: liệt kê mọi điểm gọi RNG trong engine,
  đối chiếu với danh mục được phép (thời tiết, tie-break, đột biến persona, rút blueprint,
  nhiễu tin đồn, nhiễu tham số intents) — điểm lạ → fail.
- [S7] Điều kiện kích hoạt theo TICK/NĂM cụ thể: `grep -rE "tick ==|nam ==|year =="` engine
  → 0 (không sự kiện hẹn giờ).
- [S8] `mau_khoi_dau` trong world.yaml ≤ 2 mẫu và cả hai đều là trao đổi nguyên thủy
  (không mẫu nào là tín dụng/thuê đất/gửi tiền dựng sẵn).

## 2. Kiểm định PROMPT — bài test "câu hỏi mớm"
Prompt là nơi setup lẻn vào tinh vi nhất. Kiểm bằng mắt + script trên template thật:

- [P1] Menu trong prompt là NGỮ PHÁP (nguyên tố + văn phạm clause), không phải danh mục
  định chế. Cấm các cụm kiểu "bạn có thể mở ngân hàng / lập công ty / mua bảo hiểm".
  `grep -riE "ngân hàng|công ty|bảo hiểm|xưởng" thoc/minds/prompts/` → chỉ được 0.
- [P2] Mẫu hợp đồng trong prompt phải rút từ hợp đồng ĐANG LƯU HÀNH THẬT của run (ẩn danh),
  không phải danh sách tĩnh. Test: run mới tinh → prompt chỉ chứa ≤2 mẫu khởi đầu; năm 50
  → mẫu trong prompt trùng với top-k mô-típ thật trong world.sqlite.
- [P3] Mô tả thế giới sinh từ TRẠNG THÁI (tài sản tồn tại, thỏa thuận lưu hành, tri thức),
  không có chữ "kỷ nguyên/thời đại" gán sẵn.
- [P4] Không nêu gợi ý chiến lược ("nên tích trữ", "nên cho vay lấy lãi") — chỉ mô tả tình
  hình + văn phạm. Duyệt tay 5 prompt render thật ở 3 tier, dán vào báo cáo.
- [P5] Trung lập giữa lựa chọn: thứ tự nguyên tố trong menu xáo theo seed mỗi call (chống
  thiên vị vị trí).

## 3. Kiểm định PHẢN CHỨNG — chạy counterfactual bằng mock (miễn phí)
Nguyên tắc: nếu kết quả vĩ mô SỤP ĐỔ khi rút một "gợi ý nhỏ", thì kết quả đó là sản phẩm
của setup, không phải của nền kinh tế. Mỗi bài chạy 3 seed, 300 năm, `--fast`:

- [C1] **Rút mẫu khởi đầu**: `mau_khoi_dau = []`. Đạt: kinh tế vẫn phát triển hợp đồng
  (chậm hơn được), ≥3 mô-típ xuất hiện trước năm 80. Nếu không có mẫu nào ra đời →
  văn phạm quá khó dùng → sửa PROMPT/văn phạm chứ không thêm mẫu mồi.
- [C2] **Đảo persona**: xáo persona giữa các agent (giữ nguyên thế giới) → quỹ đạo vĩ mô
  PHẢI khác đáng kể (Gini, năm đạt milestones lệch). Nếu giống hệt → hành vi không thật sự
  đến từ agent mà từ engine.
- [C3] **Tắt nhiễu tham số** (`nhieu_tham_so_so = 0`) → kết quả không được thay đổi về
  CHẤT (nhiễu chỉ là gia vị chống đồng nhất, không phải động cơ của bất bình đẳng).
- [C4] **Đổi phân phối thời tiết** (hạn nhiều hơn) → nền kinh tế phản ứng CÓ HƯỚNG
  (giá thóc cao hơn, dân số thấp hơn) — thế giới phải "biết đau".
- [C5] **Rulebot vs Mock cùng seed**: quỹ đạo phải phân kỳ rõ sau ~năm 30. Trùng khít →
  minds không thực sự cầm lái.

## 4. Kiểm định HIỆN TƯỢNG NỔI LÊN — bảng đối chiếu quy luật thực nghiệm (CHỈ CHẨN ĐOÁN)
⚠️ Quy tắc sắt: bảng này để BÁO CÁO mức giống-thực-tế, TUYỆT ĐỐI không được dùng làm mục
tiêu tinh chỉnh (trừ một hiệu chỉnh duy nhất đã được SPEC #10 cho phép: thời điểm công
nghiệp hóa). Nắn tham số để "khớp Pareto" chính là ngụy tạo — nếu không khớp, ghi nhận
trung thực.

Với run mock300 (và sau này pilot/main), `tools/reality_check.py --emergent` tính và chấm
"khớp / lệch / không đủ dữ liệu" cho từng dòng:
- [E1] Phân phối của cải lệch phải, đuôi dày (fit Pareto đuôi top 20%, báo cáo α).
- [E2] Quy luật Engel: tỷ trọng chi cho lương thực GIẢM khi thu nhập tăng (hồi quy cắt lớp).
- [E3] Hội tụ giá giữa làng khi có thương nhân hoạt động; chênh giá ~ chi phí vận chuyển.
- [E4] Động học Malthus giai đoạn tiền-máy-móc: lương thực tế nghịch chiều dân số.
- [E5] Lãi suất ngầm giảm dần khi tín-dụng-kiểu-hợp-đồng dày lên và uy tín/thế chấp phổ biến.
- [E6] Phân phối quy mô "xưởng" (số hợp đồng góp công/entity) lệch phải.
- [E7] Giá đất vốn hóa địa tô: giá thửa tương quan với dòng tô/màu mỡ của thửa.
- [E8] Đường Kuznets? (bất bình đẳng theo giai đoạn phát triển) — chỉ ghi nhận có/không.
Mỗi dòng ghi rõ: "quy luật này KHÔNG được mã hóa ở đâu trong engine" (dẫn chứng file) —
đó mới là giá trị của việc nó tự xuất hiện.

## 5. Kiểm định NGUỒN GỐC QUYẾT ĐỊNH & ĐA DẠNG
- [D1] fallback_rate < 5% (mock adversarial) / < 10% (real, từng model) — VÀ kiểm tra
  fallback không thiên vị: phân bố hành động của nhóm tick-bị-fallback không lệch hệ thống
  so với nhóm thường (fallback = đứng yên, không được âm thầm "lái").
- [D2] Tính mới của mô-típ: đến năm 100, ≥30% giá trị hợp đồng lưu hành thuộc mô-típ KHÔNG
  trùng 8 công thức của PersonaBot (mock) / không trùng mẫu khởi đầu (real). Đo bằng
  auto-cluster tổ hợp clause.
- [D3] Heterogeneity trong batch (test Phase 3) vẫn xanh trên bản build hiện tại.
- [D4] `unrecognized_intents.jsonl`: đọc, phân loại, đếm. Nếu >5% quyết định chứa cùng MỘT
  loại ý định ngoài văn phạm (vd "trộm", "kiện", "lập hội") → báo cáo như PHÁT HIỆN THIẾT KẾ
  (văn phạm có thể thiếu một nguyên tố phổ quát) — đề xuất trong DECISIONS.md, chỉ được
  thêm nguyên tố GIỮA các run, không bao giờ giữa một run.
- [D5] Mock không rò sang real: `grep -ri "PersonaBot\|mock" thoc/minds/prompts/ thoc/engine/`
  → 0; provider real không import gì từ mock.

## 6. Thang điểm & báo cáo
`python -m thoc.tools.reality_check data/runs/<run>` xuất `reports/reality_check_<run>.md`:
- Bảng S1–S8, P1–P5, C1–C5, D1–D5: pass/fail + bằng chứng (lệnh, số liệu, diff).
- Bảng E1–E8: khớp/lệch + biểu đồ + dòng "không được mã hóa tại đâu".
- **Điểm tự phát** = %(S+P+C+D pass). Ngưỡng hành động: <100% mục S/P (tĩnh & prompt) →
  PHẢI sửa trước khi qua gate; C/D fail → sửa hoặc giải trình trong DECISIONS.md;
  E chỉ báo cáo.
- Kết luận một đoạn, giọng trung thực: điều gì là tự phát thật, điều gì vẫn là giàn giáo,
  điều gì chưa biết.

## 7. Lịch chạy (bắt buộc — gắn vào gate của PHASES.md)
- Cuối Phase 2: mục S (trên engine mới có hợp đồng).
- Cuối Phase 4: TOÀN BỘ (S, P, C, D, E trên mock300) — điều kiện của TỔNG NGHIỆM THU MOCK.
- Cuối Phase 7 (pilot thật): P, D, E trên pilot20 — đưa vào `pilot_review.md`.
- Trước Phase 8: xác nhận reality_check gần nhất còn hiệu lực với HEAD hiện tại (không có
  commit nào sau lần check cuối chạm engine/ minds/).
- Trong Phase 8: KHÔNG sửa gì theo kết quả check giữa run — ghi chú để làm sau run.

## 8. Lời thề của người kiểm định (Claude Code đọc trước mỗi lần chạy check)
Mục tiêu của tôi không phải là làm cho mô phỏng "ra chuyện hay". Mục tiêu là bảo đảm rằng
BẤT CỨ chuyện gì xảy ra — kể cả một xã hội nghèo mãi, một nền kinh tế sụp đổ, hay 300 năm
không có nổi một cái xưởng — đều truy được về quyết định của agent và vật lý của thế giới,
chứ không phải về một dòng code có chủ ý của tôi. Khi phân vân giữa "thực tế hơn" và
"hay hơn", tôi chọn thực tế hơn.
