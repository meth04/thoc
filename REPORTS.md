# SIÊU KIẾN TRÚC & ĐỊNH HƯỚNG NÂNG CẤP DỰ ÁN THÓC (MASTER BLUEPRINT)

**Tài liệu này là Thiết kế Hệ thống cấp cao nhất (High-level System Architecture) và Cẩm nang Nghiên cứu (Research Manifesto) dành cho dự án THÓC. Mục tiêu là đưa dự án trở thành một "Phòng Thí Nghiệm Kinh Tế Chính Trị Nhân Tạo" (Artificial Political Economy Lab) đạt chuẩn công bố tại các tạp chí Science, Nature Human Behaviour hoặc NeurIPS.**

> **⚠️ ĐÂY LÀ MANIFESTO/ĐỀ XUẤT, KHÔNG PHẢI BẰNG CHỨNG (SUPERSEDED một phần, 2026-07-12).**
> `REVIEW.md` + `docs/MODEL_CHARTER.md` + `docs/adr/0001` là đánh giá khoa học hiện hành. Các
> khung "state formation", "bạo động khi Gini > 0.85 → Engine tước đoạt tài sản" (§3.2) và
> "đạt chuẩn Science/Nature/NeurIPS" là *khát vọng*, **chưa** có dữ liệu/hiệu chuẩn/holdout để
> đỡ. Cơ chế bạo động Gini-gate bị anti-teleology (ADR §C) hạ xuống **experimental_treatment**,
> mặc định TẮT ở `agrarian_transition_v1`. Không trích tài liệu này như evidence thực chứng.

---

## PHẦN 1: TỔNG QUAN KIẾN TRÚC HIỆN TẠI VÀ SỰ ĐỘT PHÁ

Dự án THÓC đã phá vỡ lối mòn của ABM (Agent-Based Modeling) truyền thống. Thay vì áp đặt các phương trình vĩ mô từ trên xuống (Top-down), THÓC đi theo trường phái **Tự phát Triệt để (Radical Emergence)**.

### 1.1. Chén Thánh "Không Định Chế" (Institution-less Genesis)
Sự xuất sắc của THÓC nằm ở việc Động cơ (Engine) chỉ cung cấp các định luật vật lý nền tảng (năng lượng tiêu hao, thời tiết, sinh lão bệnh tử) và một bộ Ngữ pháp Hợp đồng (9 điều khoản). Toàn bộ xã hội loài người—từ Ngân hàng, Bảo hiểm đến Giai cấp địa chủ—phải tự nảy sinh (emerge) từ hàng vạn quyết định vi mô của các LLM.

### 1.2. Hàng Rào Kỹ Thuật: Hệ Thống Kế Toán Kép (Double-Entry Ledger)
Sự kết hợp giữa `Ledger` và `FlowRegistry` đã giải quyết được tử huyệt của LLM trong giả lập kinh tế: Ảo giác (Hallucination). LLM không thể tự "in tiền" hay giao dịch khống. Engine đứng vai trò "Thượng đế" kiểm toán mọi Intent trước khi thay đổi State.

---

## PHẦN 2: PHASE 1 - ĐẠT CHUẨN VIỆN HÀN LÂM (SCIENTIFIC METRICS)

Để hội đồng phản biện quốc tế chấp nhận, THÓC phải xuất ra được các báo cáo mang ngôn ngữ toán học kinh tế tiêu chuẩn. Cần cập nhật module `engine/metrics.py`.

### 2.1. Bộ Chỉ Số Kinh Tế Vĩ Mô (Macro-Economic Indicators)
*   **GDP Thực Tế (Real GDP - Value Added Method):** 
    $$GDP = \sum (Giá\_Trị\_Đầu\_Ra - Chi\_Phí\_Đầu\_Vào)$$
    Phải đo lường sự giàu lên thực sự thay vì chỉ cộng dồn tài sản. Quy đổi về giá thóc của năm cơ sở (Base Year) để loại bỏ lạm phát.
*   **Vòng Quay Tiền Tệ (Velocity of Money - $V$):** Khi xu/thóc được dùng làm tiền tệ, tính $V = \frac{P \times Q}{M}$. Chứng minh được tiền quay vòng nhanh hơn khi các "ngân hàng" (pháp nhân) xuất hiện.
*   **Chỉ số Gini Động học (Dynamic Gini Coefficient):** Tracking realtime Gini theo từng tick để thấy rõ đường cong phân hóa giai cấp.
*   **Độ Nhạy Giá & Bounded Rationality:** Đo lường tỷ lệ các giao dịch bị đặt sai lệch chuẩn quá $3\sigma$ để đánh giá "độ phi lý trí" của LLM.

### 2.2. Kiểm Chứng Bằng Monte Carlo (Statistical Significance)
Tuyệt đối không dùng kết quả của 1 lần chạy (Mock300) để kết luận. Phải xây dựng pipeline chạy song song 30 seeds khác nhau. Báo cáo cuối cùng phải vẽ ra **Dải tin cậy 95% (Confidence Interval)** cho sự xuất hiện của Cách mạng Công nghiệp.

---

## PHẦN 3: PHASE 2 - KINH TẾ CHÍNH TRỊ VÀ QUYỀN LỰC (POLITICAL ECONOMY)

Không có nền kinh tế nào thuần khiết, nó luôn gắn liền với việc phân bổ quyền lực. Đây là tính năng nâng cấp tối thượng để LLM thực sự trở thành "Con người".

### 3.1. Sự Hình Thành Chính Quyền (State Formation & Elections)
*   **Cơ chế:** Thêm Intent `ung_cu` (tranh cử) và `bo_phieu` (bỏ phiếu) vào `engine/intents.py`. Thêm struct `ChinhQuyen` vào `engine/world.py`.
*   **Hành vi:** LLM có thể vận động tranh cử bằng cách hứa hẹn. Kẻ thắng cử (Mayor) có quyền `ban_hanh_luat` (Tax, Minimum Wage).
*   **Lobbying (Tư bản Thân hữu):** Các đại địa chủ có thể dùng tài sản để hối lộ (`hoi_lo`) chính quyền nhằm ban hành luật độc quyền.

### 3.2. Đấu Tranh Giai Cấp (Class Struggle: Unions & Riots)
*   **Nghiệp đoàn (Unions):** LLM công nhân có thể chọn `gia_nhap_nghiep_doan` và `dinh_cong` (Strike) tập thể nếu lương dưới mức sống. Đưa bài toán **Trò chơi Tối hậu thư (Ultimatum Game)** vào mô phỏng: Liệu chủ xưởng và công nhân có thỏa hiệp được không, hay sẽ đình công đến chết đói?
*   **Bạo động (Riots):** Khi Gini > 0.85, LLM có thể kích hoạt Intent `bao_dong`. Nếu đủ số đông (Critical Mass), Engine sẽ tước đoạt tài sản trong Ledger của địa chủ và chia cho người nghèo. Đây là cơ chế *Reset Hệ thống* tự nhiên nhất.

---

## PHẦN 4: PHASE 3 - TÍCH HỢP NGHIÊN CỨU HÀN LÂM TIÊN TIẾN NHẤT (SOTA 2024-2026)

Làm sao để Agent thực sự biết "Bầu cử" hay "Bạo động" một cách có não? Áp dụng ngay 3 framework đỉnh cao của thế giới:

### 4.1. Demographic Personas (Lấy cảm hứng từ FlockVote)
*   Tránh việc LLM bị "Zero-shot bias" (ví dụ LLM luôn tỏ ra đạo đức).
*   **Thực thi:** Đóng gói lịch sử tài sản của Agent thành một **Persona**. System prompt phải là: *"Bạn là một cố nông 45 tuổi, đã 2 lần chết đói, bị địa chủ X sa thải. Bạn sẽ bầu cho ai?"*. Tính giai cấp sẽ quyết định lá phiếu.

### 4.2. Động Lực Học Đám Đông (Multi-Agent Social Simulation - MASS)
*   Bạo động không sinh ra từ cái đói, mà lây lan qua giao tiếp.
*   **Thực thi:** Nâng cấp "Bảng rao" thành chức năng lan truyền thông điệp (Townhall). Đo lường **Discourse Fidelity** xem LLM truyền bá sự thù hận giai cấp như thế nào trước khi nổ ra bạo động.

### 4.3. Agentic RAG cho Hành vi Lập pháp (Legislative Deliberation)
*   Trưởng làng LLM không thể đoán mò mức thuế.
*   **Thực thi:** Sử dụng Agentic RAG. Cấp cho Trưởng làng các "External Tools" (Công cụ bên ngoài). Nó phải gọi hàm `get_wealth_distribution()` để lấy phổ tài sản của làng trước khi quyết định đánh thuế 10%.

---

## PHẦN 5: PHASE 4 - TÁI CẤU TRÚC KIẾN TRÚC MULTI-AGENT (BƯỚC CHUYỂN MÌNH KỸ THUẬT)

Để đạt được *Full Autonomy*, lõi tương tác giữa Engine và LLM hiện tại (Batching JSON) phải bị đập bỏ và nâng cấp lên kiến trúc Multi-Agent hiện đại.

### 5.1. Mô Hình 1-to-1 (Độc Lập Nhận Thức Hoàn Toàn)
*   Mỗi tác tử là 1 Thread, 1 LLM Call độc lập. 
*   **Giá trị:** Tạo ra "Bất đối xứng thông tin" (Information Asymmetry). Tác tử A không biết ví tiền của tác tử B.

### 5.2. Function Calling và Model Context Protocol (MCP)
*   Chuyển Không gian Hành động thành **Native Function Calling**. 
*   Dùng **MCP** để cho phép LLM chủ động "hỏi" thế giới: `check_weather()`, `get_market_price('thoc')`.

### 5.3. Bộ Nhớ Phân Tầng (Episodic Memory & Reflection)
*   **Episodic Memory:** Lưu trữ mọi giao dịch đã xảy ra vào Vector DB.
*   **Reflection (Tự Phản Tư):** Tóm tắt các mảnh ký ức thành "Niềm tin cốt lõi" (Core Beliefs). Ví dụ: "X là kẻ lừa đảo".

---

## PHẦN 6: KỶ LUẬT THÉP CHO PROMPT & TOOL SCHEMA (ANTI-HALLUCINATION)

Khi chuyển sang kiến trúc tự chủ bằng LLM Tools, rủi ro lớn nhất là Agent gọi tool bừa bãi hoặc truyền tham số sai logic vật lý. Hệ thống Prompt phải được cấu trúc lại cực kỳ chặt chẽ (Hardened Prompts).

### 6.1. Thiết Kế Tool Schema Chuẩn Mực Cấp Enterprise
Tuyệt đối không dùng mô tả tool chung chung. Phải dùng schema nghiêm ngặt:
*   **Mô tả rõ ràng giới hạn:** Ví dụ tool `bo_phieu(candidate_id)` phải ghi rõ `"Chỉ được truyền ID của những người có Intent ung_cu. Nếu truyền ID không hợp lệ, phiếu sẽ bị hủy."`
*   **Ép kiểu dữ liệu (Strict Typing):** Sử dụng `enum` cho các tham số cố định (như loại hàng hóa `thoc`, `go`, `xu`).
*   **Tool Phản hồi Trạng thái (Feedback Loops):** Nếu Agent gọi tool sai, Engine không được crash. Hàm phải trả về mã lỗi bằng ngôn ngữ tự nhiên để Agent tự sửa sai. Ví dụ: `{"status": "error", "message": "Bạn không đủ số dư lúa để ký hợp đồng này. Đề nghị gọi tool check_balance() trước."}`

### 6.2. Cấu Trúc System Prompt Cho Sub-Agents (The "Iron-Clad" Prompt)
Mỗi Agent con khi được khởi tạo phải nhận một System Prompt chứa 3 lớp (3-layer Context):
1.  **Lớp Căn Cước (Identity Layer):** *"Bạn là [Tên], thuộc giai cấp [Giai cấp], tài sản hiện tại [N]. Mục tiêu sinh tồn của bạn là tối đa hóa tài sản và quyền lực. Bạn rất [Thù dai / Nhát gan] dựa trên lịch sử của bạn."*
2.  **Lớp Môi Trường (State Layer):** *"Thế giới đang ở năm thứ [Y]. Trưởng làng hiện tại là [Z]. Mức thuế là [T]%. Thời tiết đang là [W]. Giá thóc trung bình là [P]."*
3.  **Lớp Kỷ Luật (Constraint Layer):** *"CẢNH BÁO QUAN TRỌNG: Bạn chỉ được phép thực hiện hành động thông qua việc gọi Tools. Không được bịa đặt ID của người khác. Nếu bạn đói, hãy dùng tool `tim_viec()`. Nếu bạn phẫn nộ với giai cấp thống trị, dùng tool `bao_dong()`."*

---

## PHẦN 7: HƯỚNG DẪN THỰC THI DÀNH CHO TRƯỞNG NHÓM (AI LEAD ARCHITECT)

Khi **Claude Code** đọc tài liệu này, hãy đóng vai trò là một **Lead Architect**. Bạn phải chia nhỏ công việc và ủy quyền cho các Agent con (Sub-agents) xử lý song song để tiết kiệm thời gian.

1. **Sự Tôn Nghiêm Của Ledger:** Mọi tool calls từ Sub-agents phải đi qua hệ thống `Double-Entry Ledger`. Không bao giờ cấp quyền sửa trực tiếp `World.agents[id].tai_san`.
2. **Kích hoạt Sub-agents Workflow:** 
   * Agent 1: Viết test cases và logic cho `metrics.py` (Phase 1).
   * Agent 2: Bổ sung cấu trúc dữ liệu `ChinhQuyen` và Intents chính trị (Phase 2).
   * Agent 3: Viết lại toàn bộ hệ thống System Prompts với chuẩn "Kỷ luật thép" (Phase 6).
3. **Mục tiêu:** Hoàn thiện toàn bộ các Phase còn lại nhanh nhất, chuẩn xác nhất và sát với thực tế nhất!
