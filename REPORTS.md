# SIÊU KIẾN TRÚC & ĐỊNH HƯỚNG NÂNG CẤP DỰ ÁN THÓC (MASTER BLUEPRINT)

**Tài liệu này là Thiết kế Hệ thống cấp cao nhất (High-level System Architecture) và Cẩm nang Nghiên cứu (Research Manifesto) dành cho dự án THÓC. Mục tiêu là đưa dự án trở thành một "Phòng Thí Nghiệm Kinh Tế Chính Trị Nhân Tạo" (Artificial Political Economy Lab) đạt chuẩn công bố tại các tạp chí Science, Nature Human Behaviour hoặc NeurIPS.**

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
*   **Hạn chế cũ:** Nhồi nhiều Agent vào 1 LLM Call làm mất đi "Bất đối xứng thông tin" (Information Asymmetry).
*   **Đột phá:** Mỗi tác tử là 1 Thread, 1 LLM Call độc lập. Chấp nhận tăng số lượng Request và thời gian chờ để lấy sự tinh khiết tuyệt đối của dữ liệu. Tác tử A không biết ví tiền của tác tử B.

### 5.2. Function Calling và Model Context Protocol (MCP)
*   **Hạn chế cũ:** Output JSON cứng nhắc dễ gây lỗi cú pháp (Parsing errors).
*   **Đột phá:** Chuyển Không gian Hành động thành **Native Function Calling**. 
    *   LLM gọi `ky_hop_dong()`, `bo_phieu()`.
    *   Dùng **MCP** để cho phép LLM chủ động "hỏi" thế giới: `check_weather()`, `get_market_price('thoc')`. LLM từ kẻ thụ động (bị nhồi prompt) trở thành kẻ chủ động khám phá.

### 5.3. Bộ Nhớ Phân Tầng (Episodic Memory & Reflection)
*   Tích hợp Vector Database (như ChromaDB/Faiss) vào mỗi Agent.
*   **Episodic Memory:** Lưu trữ mọi giao dịch đã xảy ra ("Bị X lừa 2 thóc vào tick 40").
*   **Reflection (Tự Phản Tư):** Sau mỗi 10 tick, Agent gọi LLM để tóm tắt các mảnh ký ức thành "Niềm tin cốt lõi" (Core Beliefs). Ví dụ: "X là kẻ lừa đảo". Uy tín (Reputation) của xã hội sẽ tự phát sinh từ trí nhớ này.

### 5.4. Mạng Lưới P2P (Agent-to-Agent Communication)
*   Cho phép tác tử mở luồng chat 1-1 với nhau để "Mặc cả giá" hoặc "Lobby chính trị" trước khi kết thúc một Tick. Đây là nơi phát sinh Chủ nghĩa Tư bản Thân hữu.

### 5.5. Chuyển Đổi Sang Framework Chuyên Dụng (AutoGen / LangGraph)
*   Để quản lý hàng trăm LLM Calls độc lập, P2P Chat, và Auto-retry, Engine cần được bọc trong các Framework công nghiệp như **Microsoft AutoGen** hoặc **LangGraph**. Việc này giải quyết triệt để bài toán Concurrency (Đồng thời) của dự án.

---

## 6. HƯỚNG DẪN THỰC THI DÀNH CHO CLAUDE CODE (IMPLEMENTATION DIRECTIVES)

Khi **Claude Code** (hoặc bất kỳ AI Agent nào) nhận nhiệm vụ thực thi tài liệu này, CẦN TUÂN THỦ TỐI ĐA các nguyên tắc sau:

1. **Sự Tôn Nghiêm Của Ledger (Ledger Sanctity):** Mọi Intent mới (Bạo động, Cướp đoạt, Thuế) bắt buộc phải đi qua hệ thống `Double-Entry Ledger`. Không bao giờ được cung cấp hàm cho LLM sửa trực tiếp object `World.agents[id].tai_san`.
2. **Backward Compatibility:** 9 điều khoản hợp đồng gốc (`engine/contracts.py`) là nền tảng của nền kinh tế. Khi thêm các tính năng về Chính quyền, tuyệt đối không làm gãy logic của Hợp đồng làm thuê và Cổ phần.
3. **Thứ tự Triển khai (Execution Pipeline):** Bắt buộc phải thực hiện **PHẦN 5 (Tái cấu trúc 1-to-1 + Function Calling)** đầu tiên. Chỉ khi lõi kiến trúc Multi-Agent ổn định, mới được đắp thêm các Logic Chính trị (Bầu cử/Bạo động) của Phần 3 vào. Hãy bắt đầu bằng việc phân tích module sinh prompt và chuyển đổi nó sang cơ chế 1 LLM Call.
