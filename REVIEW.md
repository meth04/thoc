# REVIEW — Lộ trình nâng THÓC thành mô phỏng kinh tế thực chứng

Ngày đánh giá: 2026-07-12  
Phạm vi: đánh giá kinh tế học và kiến trúc mô phỏng; không sử dụng request LLM trong quá trình đánh giá.

## Kết luận điều hành

THÓC hiện là một mô hình tác nhân (agent-based model, ABM) có lõi **bảo toàn vật chất và quyền sở hữu** đáng giá. Nó có thể tạo ra một xã hội nông nghiệp khép kín với giá, hợp đồng, tích lũy tài sản, bất bình đẳng, tổ chức sản xuất và đổi mới. Vì vậy nó là một phòng thí nghiệm tốt để nghiên cứu **cơ chế có thể xảy ra**.

Tuy nhiên, một mô hình "có hiện tượng giống đời thật" chưa tự động là mô hình "phản ánh nền kinh tế thật". Để đạt mức đó, THÓC cần chuyển trọng tâm từ:

> Một thế giới nhất quán, giàu cơ chế và có narrative

sang:

> Một mô hình có phạm vi lịch sử xác định, tham số có nguồn gốc dữ liệu, được hiệu chuẩn trước khi xem kết quả, và bị kiểm định bằng những dữ liệu không dùng để hiệu chuẩn.

Mục tiêu thực tế nhất không phải là mô phỏng "mọi nền kinh tế". Không có mô hình nào làm được điều đó một cách đáng tin. Mục tiêu đề xuất là xây dựng **một họ mô hình**: mỗi cấu hình đại diện cho một bối cảnh có thể định nghĩa và kiểm định được, chẳng hạn:

1. Một làng nông nghiệp Bắc Bộ, 1850–1945;
2. Một huyện nông nghiệp Việt Nam, 1986–2025;
3. Một nền kinh tế nông nghiệp tiền công nghiệp giả định, khép kín một phần.

Trong ba mục tiêu này, (3) gần với lõi hiện có nhất. Hệ thống nên hoàn thiện (3) trước, sau đó mở rộng sang (1) hoặc (2), thay vì cố mô phỏng nền kinh tế hiện đại ngay lập tức.

## 1. Tiêu chuẩn để gọi là “thực tế”

Một mô hình kinh tế có bốn tầng giá trị khác nhau. THÓC nên công bố rõ mình đang đạt tầng nào ở từng phiên bản.

| Tầng | Câu hỏi | Bằng chứng cần có |
|---|---|---|
| Nhất quán kế toán | Tài sản, nợ, hàng hóa có bị tạo/hủy vô cớ không? | Audit, kiểm thử đơn vị, tái lập theo seed |
| Hợp lý cơ chế | Các quy tắc vi mô có phù hợp kinh tế học và lịch sử không? | Mô tả hành vi, dữ liệu vi mô, chuyên gia phản biện |
| Khớp dữ kiện | Mô hình có tái tạo các “stylized facts” đã biết không? | So sánh nhiều chỉ tiêu theo thời gian và theo phân phối |
| Giá trị dự báo/nhân quả | Khi đổi điều kiện hoặc chính sách, mô hình có dự báo đúng ngoài mẫu không? | Holdout, backtest, giả dược, kiểm định phản chứng |

Lõi hiện tại khá mạnh ở tầng 1, có tiềm năng ở tầng 2, mới có bằng chứng hạn chế ở tầng 3, và chưa có bằng chứng ở tầng 4. Không nên nhảy từ tầng 1–2 sang tuyên bố tầng 4.

### 1.1. Điều kiện tối thiểu cho một kết luận đáng tin

Một kết luận như “đất khan làm bất bình đẳng tăng” chỉ nên được công bố khi đồng thời thỏa:

- Cơ chế đất khan được mô tả và tham số hóa từ bằng chứng độc lập;
- Kết quả giữ hướng ở nhiều seed và nhiều cấu hình hợp lý;
- Kết quả vẫn xuất hiện khi thay bộ quyết định tác nhân (rulebot, mô hình hành vi, LLM);
- Mô hình tái tạo được các thống kê không dùng để chỉnh tham số;
- Có phản chứng: nới đất, đổi thời tiết, đổi phân phối ban đầu và tắt cơ chế phải tạo phản ứng đúng hướng;
- Khoảng bất định được báo cáo, không chỉ một run “đẹp”.

## 2. Chẩn đoán hệ thống hiện tại

### 2.1. Những nền tảng nên giữ

1. **Sổ cái kép và FlowRegistry.** Đây là ưu thế lớn. Một mô hình kinh tế thiếu kiểm toán thường sinh ra của cải “ma”; THÓC đã tránh được rủi ro này.
2. **Đất hữu hạn, sản xuất vật chất và tồn kho.** Chúng tạo ràng buộc thực, đặc biệt quan trọng trong xã hội tiền công nghiệp.
3. **Thị trường và hợp đồng tổng quát.** Cách biểu diễn hợp đồng bằng điều khoản cho phép nghiên cứu thể chế mà không phải cài cứng tên định chế.
4. **Dị biệt cá nhân và mạng xã hội.** Đây là điều kiện cần để nghiên cứu phân phối và lan truyền thể chế.
5. **Tái lập theo seed và đối chứng rulebot.** Cần phát triển chúng thành một quy trình khoa học bắt buộc.

### 2.2. Những điểm khiến mô hình chưa đại diện tốt cho kinh tế thật

#### A. Chưa có “đối tượng kinh tế” xác định

Một cấu hình vừa có đất công, làng, xu kim loại, bầu cử, thuế, pháp nhân, cổ phần và công nghiệp hóa 300 năm là một thế giới giả định hợp lý, nhưng không tương ứng trực tiếp với một xã hội lịch sử cụ thể. Vì vậy không có bộ dữ liệu quan sát nào để nói nó “đúng” hay “sai” theo nghĩa thực chứng.

**Khuyến nghị:** mỗi scenario phải có `scope.yaml` ghi rõ địa điểm, niên đại, biên giới, dân số đầu kỳ, thành phần sản xuất, chế độ đất, tiền tệ, mức mở thương mại và các cơ chế cố ý bỏ qua.

#### B. Nhiều tham số là giả định thiết kế hơn là ước lượng

Ví dụ: năng suất gốc, phân phối độ màu mỡ, xác suất sinh, tử vong, hiệu suất công cụ, chi phí máy, thời tiết, học tập, ngưỡng bạo động. Chúng có thể tạo một thế giới hợp lý, nhưng nếu không có đơn vị, nguồn, khoảng tin cậy và phân tích nhạy cảm thì không thể biết kết quả do cơ chế nào hay do tham số nào.

**Khuyến nghị:** đưa mọi tham số kinh tế–xã hội vào sổ đăng ký tham số, không chỉ YAML.

| Trường bắt buộc | Ví dụ |
|---|---|
| Tên và đơn vị | `san_luong_goc_kg`, kg/thửa/vụ |
| Ý nghĩa kinh tế | Sản lượng thóc trước thời tiết, kỹ năng và công cụ |
| Giá trị trung tâm | 600 |
| Khoảng hợp lý / prior | 450–750 |
| Nguồn | Điều tra lịch sử, FAOSTAT, nghiên cứu địa phương, hoặc giả định có nhãn |
| Cách dùng | Hiệu chuẩn / giữ cố định / phân tích nhạy cảm |
| Phiên bản nguồn | URL, DOI, file snapshot, ngày truy xuất |

#### C. Kiểm định hiện còn nội sinh và ít mẫu

Báo cáo hiệu chỉnh dùng 5 seed và nhắm mốc công nghiệp hóa mong muốn. Đây là kiểm tra ổn định sơ bộ, không phải xác nhận thực chứng. Một mốc được chọn trước rồi điều chỉnh tham số để đạt mốc đó không thể được dùng tiếp như bằng chứng mô hình đúng.

Các báo cáo hiện có cũng tự nêu rằng phản chứng C1–C5 chưa tự động hóa. Đây là khoảng trống quan trọng: nếu bỏ mẫu hợp đồng, đổi persona, tắt nhiễu, đổi khí hậu hoặc đổi bộ ra quyết định mà kết quả thay đổi hoàn toàn, kết luận “tự phát” không còn vững.

#### D. Giá đất chưa vốn hóa lợi tức kỳ vọng

Kiểm tra hiện tại tìm thấy tương quan âm giữa giá đất và độ màu mỡ cơ bản. Trong một nền kinh tế nông nghiệp, giá đất thường chịu ảnh hưởng mạnh từ dòng lợi tức kỳ vọng, rủi ro, khả năng tiếp cận chợ, quyền sở hữu và thanh khoản. Đấu giá một lần với số người mua ít có thể rất nhiễu.

**Khuyến nghị:** không áp đặt giá đất, nhưng bổ sung cho tác nhân một quy tắc dự báo lợi tức tối giản và đo “giá trên lợi tức”. Xem mục 5.3.

#### E. Các cú sốc và liên kết vĩ mô quá nghèo

Thời tiết là cú sốc ngoại sinh chính. Kinh tế thật còn có dịch bệnh, giá ngoại thương, biến động năng suất, chi phí vận tải, xung đột, thay đổi luật, lãi suất, niềm tin và di cư. Không cần đưa tất cả cùng lúc; nhưng phải bổ sung từng lớp có dữ liệu và có kiểm định.

#### F. Tác nhân LLM không phải mô hình hành vi đã được nhận diện

LLM có thể tạo hành vi đa dạng và ngôn ngữ tự nhiên, nhưng bản thân prompt, model version và nhiệt độ là một nguồn giả định khổng lồ. Kết quả không nên được diễn giải là hành vi của người thật nếu chưa hiệu chuẩn bằng dữ liệu hành vi. LLM phù hợp nhất trong giai đoạn đầu là tạo ứng viên hành động/hợp đồng; quyết định cuối nên đi qua hàm lựa chọn có thể đo lường, tái lập và kiểm định.

#### G. Chính trị–phân phối có một số luật trực tiếp

Ngưỡng Gini kích hoạt bạo động và cơ chế sung công/chia lại tài sản là một quy tắc hợp lý để mô phỏng, nhưng nó trực tiếp định hình phân phối. Nếu mục tiêu là kiểm tra bất bình đẳng “tự phát”, luật này phải được tách thành scenario hoặc ước lượng từ dữ liệu lịch sử thay vì mặc định chung.

## 3. Chọn phạm vi trước khi thêm cơ chế

### 3.1. Scenario tham chiếu đề xuất: làng nông nghiệp tiền công nghiệp

Đây là scenario nên hoàn thiện đầu tiên vì tương thích với kiến trúc hiện có.

| Hạng mục | Đề xuất |
|---|---|
| Không gian | 5–20 làng; khoảng cách, sông/đường và chi phí vận tải quan sát được |
| Thời gian | 1850–1945 hoặc một khoảng 100–150 năm có tài liệu lịch sử |
| Tác nhân | Hộ gia đình là đơn vị quyết định chính; cá nhân giữ vai trò lao động, hôn nhân và thừa kế |
| Sản xuất | Lúa/thóc, gia súc, thủ công, thương mại nhỏ; đầu vào và mùa vụ theo dữ liệu |
| Thể chế | Chế độ đất, tô thuê, nghĩa vụ thuế, luật thừa kế theo scenario |
| Ngoại thương | Ít nhất một thị trường bên ngoài với giá và chi phí vận tải ngoại sinh quan sát được |
| Mục tiêu kiểm định | Dân số, diện tích canh tác, năng suất, giá thóc, tiền công, tô đất, phân phối đất, nợ và di cư |

### 3.2. Cấu trúc scenario bắt buộc

Tạo thư mục dạng:

```text
scenarios/
  vietnam_rural_1850_1945/
    scope.yaml
    parameters.yaml
    priors.yaml
    data_dictionary.md
    targets_in_sample.yaml
    targets_holdout.yaml
    policy_experiments.yaml
    provenance.csv
```

`scope.yaml` cần trả lời: đơn vị quan sát là gì, ai được xem là cư dân, biên giới có mở không, hàng hóa nào tồn tại, tiền có phải pháp định không, mô hình bỏ qua điều gì. Không cho phép dùng kết quả của scenario A làm “bằng chứng” cho scenario B nếu khác bối cảnh.

## 4. Kiến trúc mô hình đề xuất

### 4.1. Tách ba lớp: vật lý, thể chế, hành vi

Hiện nay các lớp này đã có manh mối trong code, nhưng cần tách rành mạch để kiểm định.

```text
Dữ liệu / tham số / cú sốc
          │
          ▼
Lớp 1: Ràng buộc vật lý
đất, mùa vụ, tồn kho, công nghệ, vận tải, dân số
          │
          ▼
Lớp 2: Thể chế
quyền đất, thuế, tòa án, tiền, tín dụng, luật phá sản
          │
          ▼
Lớp 3: Hành vi có dị biệt
kỳ vọng, tiêu dùng, tiết kiệm, đầu tư, vay, di cư, lựa chọn đối tác
          │
          ▼
Thị trường / giá / phân phối / chỉ tiêu vĩ mô
          │
          ▼
So sánh dữ liệu, hiệu chuẩn, kiểm định ngoài mẫu
```

Quy tắc quan trọng: chỉ lớp 1 bảo toàn vật chất; lớp 2 được bật/tắt theo scenario; lớp 3 phải được thay thế được. Một mô hình hành vi mới không được đụng vào logic hạch toán.

### 4.2. Chuyển đơn vị quyết định từ cá nhân sang hộ gia đình

Trong xã hội nông nghiệp, tiêu dùng, tồn kho, lao động, canh tác, nợ và rủi ro thường được quyết định ở cấp hộ. Cá nhân vẫn cần thiết cho nhân khẩu học, kỹ năng, hôn nhân và thừa kế, nhưng hộ nên là chủ thể tối ưu hóa/nguyên tắc hành vi.

Mỗi hộ cần có:

- thành viên theo tuổi, giới, sức khỏe và kỹ năng;
- tài sản sản xuất, nợ, ruộng đang sở hữu/thuê;
- kho lương thực và quy tắc dự trữ;
- nhu cầu tiêu dùng tối thiểu và ngoài tối thiểu;
- sổ thu nhập–chi tiêu–dòng tiền;
- mạng lưới thân tộc, tín dụng và thương mại;
- kỳ vọng về giá, thời tiết và thu hoạch.

Điều này giúp phân biệt nghèo do thu nhập thấp, nghèo do thiếu tài sản, và thiếu thanh khoản tạm thời — ba trạng thái rất khác nhau trong kinh tế thật.

### 4.3. Hàm hành vi lai thay cho “LLM quyết định tất cả”

Đề xuất dùng kiến trúc lai:

1. **Nhu cầu và ràng buộc cứng:** ngân sách, calo, thời gian, khả năng trả nợ, quyền sở hữu; engine xử lý.
2. **Quy tắc hành vi có tham số:** tiết kiệm phòng ngừa, aversion rủi ro, lựa chọn cây trồng, mức dự trữ mục tiêu, quyết định di cư; có thể ước lượng.
3. **LLM tùy chọn:** tạo mô tả, ý tưởng hợp đồng, hoặc xác suất ưu tiên có kiểm soát; không được là nguồn duy nhất của quyết định định lượng.
4. **Bộ giải quyết lựa chọn:** chọn hành động khả thi có utility/loss rõ ràng, có log gồm tập lựa chọn, dự báo, utility và hành động thực tế.

Ví dụ, hộ `h` chọn lượng thóc dự trữ `s`, đầu tư `i`, lao động nông nghiệp `l_a`, lao động phi nông `l_n` để tối đa hóa:

```text
E[ u(c) - chi_phi_lao_dong(l_a + l_n) - phi_rui_ro × shortfall ]
```

với ràng buộc ngân sách, thời gian, tồn kho và tín dụng. Không cần giả vờ hộ tối ưu hoàn hảo: các tham số có thể đại diện cho thiên lệch hiện tại, giới hạn thông tin và quy tắc kinh nghiệm.

### 4.4. Kỳ vọng thích nghi và thông tin không hoàn hảo

Thị trường thật vận hành trên kỳ vọng. Tác nhân nên không nhìn thấy “giá đúng”, sản lượng tương lai hay trạng thái của người khác. Họ có thể tạo dự báo:

```text
E_t[p_(t+1)] = alpha × p_t + (1 - alpha) × E_(t-1)[p_t] + tin_don + tin_hieu_ngoai_thi_truong
```

Các hệ số `alpha`, chất lượng thông tin và tốc độ lan truyền phải là tham số scenario. Sau đó có thể kiểm định forecast error, độ phân tán kỳ vọng và mức độ phản ứng với giá.

### 4.5. Thị trường: từ một phiên chợ sang cấu trúc có ma sát

Call auction là một cơ chế sạch và tốt để bắt đầu, nhưng nó có thể quá hiệu quả đối với làng nghèo. Nên giữ auction như một loại market clearing, đồng thời thêm các tùy chọn scenario:

- chợ làng theo phiên; chợ huyện theo kỳ dài hơn;
- chi phí đi lại, hao hụt hàng và giới hạn tải trọng;
- quan hệ tín nhiệm và chênh lệch giá mua–bán;
- thương lái trung gian, độc quyền cục bộ và thông tin giá có trễ;
- nợ thương mại và bán chịu;
- hàng hóa không đồng nhất về chất lượng.

Mục tiêu không phải làm thị trường “phức tạp hơn”, mà là tái tạo được các moment quan sát được: dispersion giá giữa làng, tỷ lệ giao dịch, co giãn cung/cầu và tốc độ hội tụ giá.

### 4.6. Đất đai và tô đất

Đất là kênh giàu nghèo trung tâm trong scenario nông nghiệp. Cần bổ sung:

- chất lượng đất theo dữ liệu hoặc phân phối có căn cứ;
- chi phí khai khẩn, cải tạo, tưới tiêu và suy thoái;
- quyền đất có mức độ bảo đảm khác nhau;
- thuê đất, tô cố định và chia sản lượng;
- thị trường đất có thanh khoản thấp, chi phí chuyển nhượng, thừa kế và cưỡng chế nợ;
- định giá dựa trên **lợi tức kỳ vọng**, không phải giá do một đấu giá cô lập.

Chỉ số kiểm định quan trọng:

```text
land_price / expected_net_rent
```

Tỷ số này phải được so sánh theo vùng, chất lượng đất và thời gian; nếu mô hình không có đủ giao dịch, cần báo khoảng tin cậy lớn thay vì suy luận mạnh.

### 4.7. Tín dụng, tiền và bảng cân đối kế toán tài chính

Nếu mục tiêu dừng ở kinh tế tự cung tự cấp, phần này có thể tối giản. Nếu mục tiêu là quá trình phát triển, nó là bắt buộc.

Mỗi khoản vay phải có:

- chủ nợ, con nợ, tài sản thế chấp, kỳ hạn, lịch trả nợ;
- lãi suất danh nghĩa và đơn vị thanh toán;
- xác suất vỡ nợ và quy tắc tái cơ cấu;
- ảnh hưởng lên khả năng vay kỳ sau;
- bảng cân đối đầy đủ của cả hai bên.

Khi đưa trung gian tài chính vào, phải mô hình hóa bảng cân đối của trung gian: tiền gửi là nợ phải trả, cho vay là tài sản; không được chuyển tiền “vô nguồn”. Có thể khởi đầu bằng mạng lưới cho vay hộ–hộ trước khi thêm ngân hàng.

Các chỉ số cần đo: tỷ lệ hộ vay, debt-service ratio, lãi suất theo loại người vay, vỡ nợ, tập trung chủ nợ, thanh khoản và chênh lệch giá trị tài sản–nợ.

### 4.8. Khu vực công và chính trị

Không nên để một ngưỡng Gini duy nhất xác định bạo động mặc định. Thay bằng ba tầng:

1. **Năng lực nhà nước:** thuế thu được bao nhiêu, chi cho đâu, chi phí hành chính và cưỡng chế;
2. **Ưu tiên chính trị:** hộ/cá nhân có sở thích, mạng lưới, niềm tin và chi phí tham gia khác nhau;
3. **Quy trình tập thể:** bỏ phiếu, thương lượng, nổi dậy hoặc tuân thủ tùy scenario.

Mọi luật phân phối phải có nhãn: `institutional_assumption`, `historical_rule` hoặc `experimental_treatment`. Khi nghiên cứu bất bình đẳng tự phát, tắt các luật tái phân phối cơ học; khi nghiên cứu chính trị, đưa chúng vào như treatment có so sánh đối chứng.

### 4.9. Ngoại thương và di cư

Một nền kinh tế chỉ có một làng không thể tạo giá tương đối hoặc chuyên môn hóa giống thực tế. Bước tối thiểu là thêm một “thị trường bên ngoài” không cần agent đầy đủ:

- giá mua/bán bên ngoài theo chuỗi thời gian;
- hạn mức và chi phí vận tải;
- nhu cầu xuất khẩu hoặc nguồn cung nhập khẩu;
- chênh giá do biên giới và thương nhân;
- di cư đi/về có chi phí, mạng lưới và tiền gửi về nhà.

Sau khi khớp dữ liệu ở mức này, mới đáng xây hệ nhiều vùng với thương mại nội sinh.

## 5. Dữ liệu, hiệu chuẩn và kiểm định

### 5.1. Nguyên tắc “đóng băng thiết kế trước khi xem kết quả”

Quy trình đúng là:

1. Chọn scope và dữ liệu;
2. Chọn một tập chỉ tiêu **in-sample** để hiệu chuẩn;
3. Khóa tham số, code và seed protocol;
4. Chạy nhiều seed;
5. Đánh giá bằng chỉ tiêu **holdout** chưa từng dùng để điều chỉnh;
6. Chỉ sau đó mới sửa mô hình và tạo phiên bản mới.

Không được vừa xem kết quả cuối vừa điều chỉnh tham số để khớp chính kết quả đó rồi coi đó là kiểm định.

### 5.2. Bộ dữ liệu tối thiểu

Không cần đợi dữ liệu hoàn hảo. Hãy bắt đầu bằng một data package có provenance rõ.

| Nhóm | Dữ liệu cần có | Mục đích |
|---|---|---|
| Nhân khẩu | dân số, cơ cấu tuổi, sinh, tử, hộ | hiệu chuẩn vòng đời và lao động |
| Nông nghiệp | diện tích, năng suất, mùa vụ, giá đầu vào | sản xuất và cung lương thực |
| Giá | thóc, gạo, gỗ, gia súc, tiền công, tô đất | thị trường và giá tương đối |
| Tài sản | quy mô đất, nhà, công cụ, nợ | phân phối và tích lũy |
| Thể chế | thuế, tô, luật thừa kế, quyền đất | scenario và policy |
| Địa lý | đất, sông, đường, khoảng cách chợ | năng suất và ma sát thương mại |
| Cú sốc | mưa, lũ, hạn, dịch bệnh, giá ngoại thương | kiểm định phản ứng động |

Mọi file dữ liệu gốc cần được giữ không chỉnh sửa trong `data/raw/`; quy trình biến đổi tái lập nằm trong `data/processed/` và script có version. Không chép số vào YAML bằng tay mà không có provenance.

### 5.3. Hiệu chuẩn nhiều mục tiêu

Không nên chỉ khớp một mốc công nghiệp hóa. Hãy dùng hàm mất mát trên nhiều moment:

```text
Loss(theta) = Σ_j w_j × distance(simulated_moment_j, observed_moment_j)
```

Moment có thể gồm:

- mức và tốc độ tăng dân số;
- năng suất và biến động sản lượng;
- tỷ trọng lao động nông nghiệp;
- giá thóc / tiền công thực;
- giá đất / tô ròng;
- tỷ lệ biết chữ;
- Gini đất, tài sản và thu nhập;
- tỷ lệ vay nợ, vỡ nợ, di cư;
- mức độ tập trung doanh nghiệp nếu scenario có doanh nghiệp.

Nên dùng một trong ba cách:

1. **Bayesian calibration / Approximate Bayesian Computation:** phù hợp ABM, trả về phân phối tham số thay vì một con số;
2. **Simulated Method of Moments:** tốt khi moment được xác định rõ;
3. **History matching:** loại các vùng tham số không thể phù hợp trước, giảm chi phí tính toán.

Kết quả phải báo phân phối hậu nghiệm/prior, không chỉ “tham số tốt nhất”.

### 5.4. Kiểm định ngoài mẫu

Chia dữ liệu theo cả thời gian và loại chỉ tiêu:

- Hiệu chuẩn trên 1850–1900, kiểm tra 1901–1945;
- Khớp dân số, giá thóc, năng suất và phân phối đất; để lại tiền công, giá đất/tô và di cư làm holdout;
- Hiệu chuẩn ở một số làng, kiểm tra ở làng khác.

Kết quả holdout cần có biểu đồ khoảng 5–95% giữa các seed và tham số, cùng một scoring rule đã định trước. Một đường mô phỏng đi qua số liệu ở một năm không đủ.

### 5.5. Kiểm định phản chứng và placebo

Tự động hóa năm thử nghiệm đã đề xuất trong `reality_check` là ưu tiên cao:

1. Bỏ mẫu hợp đồng ban đầu;
2. Hoán đổi persona;
3. Tắt nhiễu tham số;
4. Đổi phân phối thời tiết;
5. So sánh rulebot và mock cùng seed.

Mở rộng với:

- tắt thị trường đất; dự đoán thuê đất và phân phối đổi thế nào;
- tăng chi phí vận tải; dự đoán dispersion giá tăng;
- cú sốc năng suất có lịch sử; dự đoán giá thóc tăng và tiêu dùng giảm;
- placebo shock vào thời điểm không có cú sốc; không được xuất hiện phản ứng giả;
- hoán đổi network nhưng giữ tài sản; đo vai trò quan hệ;
- hoán đổi tài sản nhưng giữ network; đo vai trò của cải ban đầu.

Mỗi bài phải được chạy ít nhất 30 seed; nếu chi phí cao, dùng sequential stopping rule nhưng không chọn seed theo kết quả đẹp.

### 5.6. Phân tích nhạy cảm và bất định

ABM dễ tạo kết quả do tương tác phi tuyến. Vì vậy mỗi báo cáo chính phải có:

- phân phối kết quả theo seed;
- độ nhạy cục bộ và toàn cục (Sobol/Morris nếu phù hợp);
- biến thiên do tham số và biến thiên do stochasticity;
- xác suất đạt một kết quả, thay vì chỉ một năm milestone;
- danh sách “parameter importance”.

Ví dụ không nên viết “công nghiệp hóa xảy ra năm 171”, mà viết: “với posterior hiện tại, 62% run đạt ngưỡng công nghiệp hóa trong 160–280 năm; trung vị 171; khoảng 10–90% là X–Y”.

## 6. Định nghĩa lại chỉ tiêu kinh tế

### 6.1. GDP và tài khoản quốc gia

GDP nội bộ hiện hữu ích như sản lượng có định giá thị trường, nhưng không nên gọi là GDP thực chứng nếu thiếu giá cho hàng không giao dịch và dịch vụ. Cần tách:

- `physical_output`: kg thóc, giờ công, sản lượng vật chất;
- `market_value_added`: giá trị gia tăng theo giá giao dịch;
- `imputed_value_added`: giá trị tự tiêu dùng, định giá theo quy tắc công khai;
- `real_output_index`: chỉ số khối lượng với rổ hàng và năm gốc;
- `nominal_output`: giá hiện hành;
- `price_index`: Laspeyres/Paasche/Fisher tùy mục tiêu.

Chỉ số cần đi kèm độ phủ: bao nhiêu phần trăm output được định giá từ giao dịch thật, bao nhiêu là định giá quy ước.

### 6.2. Phúc lợi thay cho chỉ GDP

Kinh tế phát triển không chỉ là output. Theo dõi thêm:

- xác suất thiếu calo và thời gian thiếu ăn;
- tử vong theo tuổi, tuổi thọ, sức khỏe;
- tiêu dùng thực bình quân và median;
- bất bình đẳng tiêu dùng, không chỉ tồn kho;
- giáo dục, cơ động xã hội và tiếp cận đất;
- tỷ lệ mắc nợ quá hạn, vô gia cư, di cư bất đắc dĩ;
- mức độ dễ tổn thương trước cú sốc.

### 6.3. Phân phối và mobility

Gini là cần nhưng chưa đủ. Báo cáo chuẩn nên có:

- Lorenz curve và top 1/10/20%;
- Gini đất, tài sản ròng, thu nhập, tiêu dùng tách biệt;
- intergenerational rank-rank slope và elasticity;
- ma trận chuyển tầng theo định nghĩa **được khóa trước**;
- chênh lệch theo giới, tuổi, địa lý, và xuất thân;
- tỷ lệ nghèo kéo dài nhiều kỳ.

Nhãn “giai cấp” chỉ nên là lớp diễn giải sau cùng, không được quay lại điều khiển engine.

## 7. Chuẩn thí nghiệm và tái lập

### 7.1. Một run không phải một kết quả

Mỗi experiment phải ghi:

- git commit và hash toàn bộ config;
- scenario, nguồn dữ liệu và version;
- seed list được tạo trước;
- engine version, Python environment và dependency lock;
- loại mind policy/model version, temperature và prompt hash;
- số run thành công/thất bại và lý do;
- thống kê trung tâm, phân vị và raw outputs.

### 7.2. Phân biệt ba loại run

| Loại | Mục đích | Có thể dùng LLM? |
|---|---|---|
| Deterministic benchmark | kiểm toán, regression test, tái lập | Không |
| Behavioral benchmark | kiểm tra quy tắc quyết định so với dữ liệu/experiment | Có thể, nhưng phải cache và version |
| Research ensemble | ước lượng, phản chứng, forecast | Không nên phụ thuộc LLM nếu cần hàng nghìn run |

Mặc định, toàn bộ calibration và validation phải chạy với policy không gọi mạng. LLM chỉ là treatment riêng, không phải điều kiện cần để tái tạo kết quả nền.

### 7.3. Regression test kinh tế

Ngoài unit test, thêm `tests/economics/` với các invariant và hướng dự đoán:

- tăng mưa thuận lợi, giữ mọi thứ khác cố định → sản lượng kỳ vọng tăng;
- giảm tồn kho ban đầu → xác suất thiếu ăn không giảm;
- tăng chi phí vận tải → không làm dispersion giá giảm một cách hệ thống;
- tăng độ màu mỡ, giữ quyền đất và vị trí cố định → lợi tức ròng kỳ vọng không giảm;
- tăng trả nợ bắt buộc → thanh khoản con nợ không tăng;
- tắt tái phân phối → không thể trực tiếp tạo bình đẳng hơn bằng chính cơ chế đó.

Các test này không khẳng định mô hình đúng, nhưng ngăn sự thoái hóa của trực giác kinh tế cơ bản khi code thay đổi.

## 8. Lộ trình triển khai ưu tiên

### Giai đoạn 0 — Tuyên bố phạm vi và chuẩn dữ liệu (1–2 tuần)

**Deliverables**

- `scenarios/` và một scenario tham chiếu;
- parameter registry + provenance;
- data dictionary;
- experiment manifest;
- định nghĩa chỉ tiêu in-sample và holdout.

**Tiêu chí đạt:** một người ngoài repo có thể trả lời mọi tham số lấy từ đâu và mô hình đại diện cho nơi/thời gian nào.

### Giai đoạn 1 — Khóa lõi hạch toán và baseline không LLM (2–4 tuần)

**Công việc**

- hoàn tất test không cần mạng trong conda environment;
- tự động hóa C1–C5;
- tạo benchmark ensemble 30–100 seed;
- tách scenario config khỏi config chung;
- khắc phục mọi fallback định giá và giao dịch không truy nguyên được;
- lưu đầy đủ balance sheet cấp hộ, entity và công quỹ.

**Tiêu chí đạt:** từ commit và manifest, tái tạo được toàn bộ bảng/bản đồ trong báo cáo mà không gọi API.

### Giai đoạn 2 — Hộ gia đình, hành vi và đất đai (4–8 tuần)

**Công việc**

- tạo Household entity;
- rule-based/adaptive expectations;
- tiêu dùng–tồn kho–tiết kiệm–vay tối giản;
- thuê đất/tô đất và cải tạo đất;
- chỉ số price-to-rent, labor share, debt service.

**Tiêu chí đạt:** các hướng comparative statics cơ bản vượt qua regression suite và giá đất không còn nghịch chiều độ màu mỡ sau khi kiểm soát vị trí/thanh khoản.

### Giai đoạn 3 — Dữ liệu, hiệu chuẩn và validation (6–12 tuần)

**Công việc**

- xây data pipeline;
- chọn prior/range có nguồn;
- chạy ABC/SMM hoặc history matching;
- báo cáo posterior và importance;
- chạy out-of-sample và counterfactual ensemble.

**Tiêu chí đạt:** có một báo cáo reproducible nêu rõ chỉ tiêu nào khớp, chỉ tiêu nào không khớp và độ bất định ra sao.

### Giai đoạn 4 — Mở nền kinh tế và phát triển dài hạn (8–16 tuần)

**Công việc**

- thị trường ngoài vùng, vận tải và thương nhân;
- di cư và remittance;
- tín dụng/tiền theo bảng cân đối;
- cú sốc đa nguồn;
- thể chế thay đổi theo scenario.

**Tiêu chí đạt:** mô hình tái tạo đồng thời các chuỗi giá, cơ cấu lao động, năng suất, dân số và phân phối trong một bối cảnh xác định.

### Giai đoạn 5 — LLM là lớp thử nghiệm, không là lõi (sau validation)

**Công việc**

- so sánh policy hành vi chuẩn với policy LLM cache;
- đo phân phối hành động, không chỉ narrative;
- version prompt/model; replay từ cache;
- coi LLM như một treatment và báo sai số riêng.

**Tiêu chí đạt:** kết luận kinh tế chính không sụp đổ khi không có LLM; LLM chỉ cải thiện một đại lượng có đo lường được.

## 9. Các lỗi cần tránh

1. **Thêm cơ chế vì nghe giống đời thật.** Mỗi cơ chế phải có câu hỏi, dữ liệu và moment kiểm định.
2. **Đặt tên hiện tượng rồi coi nó là giải thích.** “Công nghiệp hóa”, “giai cấp”, “ngân hàng” phải có định nghĩa quan sát được.
3. **Điều chỉnh tham số sau khi xem biểu đồ đẹp.** Đây là overfitting mô phỏng.
4. **Báo một seed.** Seed đẹp không phải bằng chứng.
5. **Dùng LLM như hộp đen có quyền lực nhân quả.** Mọi ảnh hưởng của prompt/model phải được đo và version.
6. **Nhầm cân bằng thị trường với tính hiện thực.** Một cơ chế khớp lệnh đúng vẫn có thể thiếu ma sát, phân khúc và thông tin.
7. **Dùng Gini duy nhất làm bất bình đẳng.** Tồn kho, tài sản ròng, tiêu dùng, nợ và quyền lực là các chiều khác nhau.
8. **Suy rộng từ làng khép kín sang quốc gia hiện đại.** Mỗi phạm vi cần scenario và validation riêng.

## 10. Thước đo thành công đề xuất

Không đặt mục tiêu “mô phỏng giống thật nhất” theo cảm giác. Đặt các mục tiêu có thể bác bỏ:

| Hạng mục | Mục tiêu có thể đo |
|---|---|
| Tái lập | 100% benchmark không LLM replay cùng output từ manifest |
| Kế toán | 0 vi phạm conservation/balance sheet trong ensemble |
| Dữ liệu | 100% tham số kinh tế quan trọng có đơn vị, range và provenance |
| Hiệu chuẩn | Moment in-sample nằm trong dải dữ liệu với tiêu chuẩn định trước |
| Ngoài mẫu | Ít nhất 5 moment holdout được dự báo trong khoảng bất định |
| Bền vững | Kết luận chính giữ hướng qua 30+ seed và policy hành vi thay thế |
| Minh bạch | Công bố cả failure modes, không chỉ run đạt công nghiệp hóa |
| So sánh chính sách | Chỉ thực hiện sau khi baseline qua holdout; luôn có placebo và sensitivity |

## Kết luận cuối

THÓC không cần từ bỏ ý tưởng “thể chế tự phát”. Nhưng cần đổi tiêu chuẩn chứng minh: một định chế chỉ đáng gọi là tự phát khi nó xuất hiện ổn định dưới nhiều seed, không được prompt mớm, không phụ thuộc một luật ngầm, và đồng thời tạo ra các dấu vết dữ liệu giống bối cảnh lịch sử đã chọn.

Con đường đáng tin nhất là: **thu hẹp phạm vi → đưa dữ liệu và provenance vào tham số → tách hành vi khỏi LLM → hiệu chuẩn nhiều mục tiêu → kiểm định ngoài mẫu → báo bất định và phản chứng**. Khi hoàn thành chuỗi này, hệ thống sẽ không chỉ kể một câu chuyện kinh tế hấp dẫn; nó sẽ trở thành một công cụ khoa học có thể bị kiểm tra, bác bỏ và cải thiện.

---

## Phụ lục A — Tái thẩm định khả năng công bố quốc tế (2026-07-12)

### Phán quyết

**Chưa đủ điều kiện cho một bài nghiên cứu “tầm cỡ thế giới” ở thời điểm đánh giá.** Cụ thể hơn:

| Đích công bố | Phán quyết hiện tại | Lý do quyết định |
|---|---|---|
| Tạp chí kinh tế hàng đầu / kinh tế lượng / kinh tế sử thực chứng | Chưa phù hợp | Không có câu hỏi nhân quả đã khóa, bối cảnh quan sát thật, dữ liệu, hiệu chuẩn hay kiểm định ngoài mẫu. |
| Tạp chí computational economics tốt | Chưa đủ bằng chứng, nhưng có đường đi rõ | Cần mô hình hóa hành vi có cơ sở, uncertainty quantification và benchmark thực nghiệm nghiêm ngặt. |
| Computational social science / AI-for-science tốt | Có tiềm năng sau một gói thực nghiệm lớn | Điểm mới khả dĩ là LLM-ABM có hạch toán, replay, quota-aware execution và kiểm toán phản chứng; hiện chưa chứng minh lợi ích khoa học của lớp LLM. |
| Workshop / demo phương pháp có phản biện | Có thể chuẩn bị sau khi hoàn thiện reproducibility package | Phải đóng khung là **benchmark cơ chế**, không phải tái tạo hay dự báo nền kinh tế thật. |

Vì vậy, phần mềm đáng để tiếp tục như một **research platform**, nhưng kết quả hiện tại chưa đủ để suy luận về nền kinh tế thực, về lịch sử Việt Nam, hoặc về tác động chính sách. Một “run” hình thành công nghiệp hóa là kết quả của tập luật đang cài đặt; chưa phải bằng chứng rằng cơ chế tương ứng đã tạo ra công nghiệp hóa ngoài đời.

### Bằng chứng kiểm tra trực tiếp trong repo

1. `scenarios/preindustrial_closed_v1/scope.yaml` đặt `validation_tier: mechanism_benchmark` và nói rõ đây không phải địa phương hay quốc gia lịch sử. Đây là cách tự mô tả đúng đắn, đồng thời là giới hạn đối với claim của bài báo.
2. `targets_in_sample.yaml` và `targets_holdout.yaml` đều có `targets: []`. Do đó chưa tồn tại calibration hay external validation có thể audit.
3. `provenance.csv` mới có ba tham số, đều mang nhãn `design_assumption`, không có nguồn dữ liệu. Các moment được sinh ra trong mô hình không thể đồng thời đóng vai trò dữ liệu để xác nhận mô hình.
4. `reports/calibration.md` là bài tập tuning mock 5 seed để seed trung vị đạt một nhãn công nghiệp hóa nội sinh. Hai trong năm seed không đạt nhãn trong horizon 300 năm. Đây là sanity check hữu ích, không phải calibration thực chứng; chính mục tiêu của nó đã được chọn từ cấu hình nghiên cứu.
5. Pilot `reports/reality_check_review_real_30y_v1.md` xác nhận pipeline LLM có fallback thấp trong run đó, nhưng không chứng minh ổn định hành vi. Báo cáo thực 30 năm khác mạnh với mock theo kết quả pilot đã lưu; chưa có ensemble LLM thật sau khi thêm survival floor.
6. Lớp phần mềm đáng tin hơn lớp khoa học: RNG có seed tree, manifest, replay cho rulebot/mock, ledger/audit, counterfactual runner và test bao phủ nhiều invariant. Replay hiện không hỗ trợ real mode nếu không có transcript (`tools/replay.py`), nên reproducibility của kết luận dùng LLM thật vẫn chưa đóng.

### Kiểm tra kỹ thuật trong lần tái thẩm định

Đã chạy `conda run -n thoc-env python -m pytest -q` mà không gửi request LLM/API. Kết quả: **158 passed; 12 errors**. Các lỗi xảy ra tại fixture `tmp_path` vì tiến trình sandbox không có quyền tạo/đọc thư mục tạm của Windows (`PermissionError` ở `C:\Users\nguye\AppData\Local\Temp\pytest-of-nguye`), không phải assertion thất bại của mô hình. Chạy lại với `--basetemp C:\tmp\thoc_pytest_review` cũng bị chính sandbox chặn quyền tạo thư mục. Kết quả này là bằng chứng tích cực nhưng **không được ghi là “test suite xanh hoàn toàn”** cho đến khi CI chạy được trên runner có thư mục tạm hợp lệ.

### Vì sao tính mới khoa học hiện chưa đủ

Một bài quốc tế mạnh cần trả lời rõ “điều gì trước đây chưa biết mà bài này biết được?”. THÓC hiện có nhiều cơ chế (đất, hợp đồng, chính trị, đổi mới, LLM) nhưng chưa tách được ba khả năng cạnh tranh:

- Kết quả do một cơ chế kinh tế có ý nghĩa;
- Kết quả do tham số/treatment được thiết kế để tạo hiệu ứng;
- Kết quả do policy của PersonaBot, prompt hoặc phiên bản LLM.

Nếu không phân biệt được ba khả năng này, đóng góp sẽ bị reviewer xem là một “rich artificial world”: hấp dẫn để minh họa, nhưng không có nhận diện hay hiệu lực ngoài mô hình. Nhiều cơ chế hơn không tự làm bài báo mạnh hơn; thường chỉ tăng không gian tham số và giảm khả năng nhận diện.

## Phụ lục B — Ba hướng cải tiến mới có thể tạo đóng góp thật

Không nên đồng thời theo cả ba. Cần chọn một claim chính, rồi thiết kế dữ liệu, baseline và phép bác bỏ đúng với claim đó.

### Hướng 1 (khuyến nghị) — Kinh tế sử định lượng, tập trung vào đất, rủi ro và bất bình đẳng

**Câu hỏi ví dụ:** “Khan hiếm đất và biến động khí hậu khuếch đại bất bình đẳng tài sản liên thế hệ tại nông thôn Bắc Bộ như thế nào, khi thị trường thuê đất và tín dụng phi chính thức cùng tồn tại?”

Đây là hướng phù hợp nhất với lõi vật chất hiện có. Đóng góp không nằm ở việc để LLM kể chuyện, mà ở việc nối một cơ chế vi mô có thể kiểm toán với distributional facts lịch sử.

Thiết kế bắt buộc:

1. Chọn một địa bàn, thời đoạn và đơn vị quan sát duy nhất; không tuyên bố “Việt Nam” khi dữ liệu chỉ là một vài làng/huyện.
2. Tạo data package versioned gồm đất đai, hộ khẩu/dân số, sản lượng, giá gạo, tiền công, tô, nợ, di cư và mưa/nhiệt độ. Mỗi số trong scenario phải trỏ đến dòng provenance, đơn vị và khoảng không chắc chắn.
3. Chia dữ liệu theo thời gian: fit 1850–1915, holdout 1916–1945 chẳng hạn. Khóa prior, loss function và seed list trước khi xem holdout.
4. Hiệu chuẩn rule-based baseline bằng simulated method of moments, ABC hoặc history matching; báo parameter non-identification thay vì ép một bộ số duy nhất.
5. Giữ riêng các moment phân phối: top land share, Gini tài sản/tiêu dùng, tỷ lệ thuê đất, debt-service, mobility giữa thế hệ. GDP hay một Gini đơn lẻ không đủ.
6. Kiểm định phản chứng “đúng dấu” và placebo: đổi mưa nhưng không đổi đất; đổi điều kiện tín dụng tại nơi không có nhu cầu vay; permute parcel quality. Chỉ báo claim nếu kết quả còn qua placebo và sensitivity.

**Điều làm hướng này mới:** tạo một “structural micro-to-macro counterfactual laboratory” có ràng buộc tồn kho–đất–nợ và được test trên distributional holdout. LLM chỉ được thêm sau cùng như một policy treatment, không phải nguồn nhận diện.

### Hướng 2 — Bài phương pháp LLM-ABM có kiểm toán, thay vì bài về kinh tế thật

**Claim khả dĩ:** “Hạch toán ràng buộc, action compiler và replay artifact làm giảm hành vi không hợp lệ của LLM-agent, đồng thời cho phép kết luận thể chế bền vững hơn qua model/provider.”

Đây là hướng AI/CSS, phù hợp nếu không có dữ liệu lịch sử đủ tốt. Bài phải benchmark **lớp LLM**, chứ không chỉ benchmark kết quả thế giới mô phỏng.

Thiết kế mới cần có:

- Ít nhất hai LLM/provider hoặc hai họ model, nhiều snapshot/model version, cùng prompt budget và temperature; rulebot, PersonaBot/mock và policy-card là baseline.
- Ablation có đăng ký trước: bỏ accounting/action validation, bỏ social memory, bỏ contract language, bỏ survival floor, đổi thứ tự menu, đổi persona/seed. Nêu rõ outcome chính trước khi chạy.
- Một tập task vi mô có ground truth: lựa chọn sản xuất khi ngân sách/đất hữu hạn, thực hiện hợp đồng, tránh bán tài sản không sở hữu, phản ứng với cú sốc. Đo constraint violation, welfare regret, diversity, cost/token, fallback rate và stability—not just narrative richness.
- Transcript/cache hoặc response hash + encrypted artifact; replay real mode từ transcript phải tạo đúng action trace, không chỉ cùng seed.
- Ensemble tối thiểu 30 seed cho mỗi model–treatment và confidence interval/paired comparisons. Báo tỷ lệ run bị quota/cost/failure và xử lý missingness.

Nếu LLM không vượt rulebot trên outcome đã định nghĩa, đó vẫn là kết quả tốt: bài báo nên kết luận giới hạn của LLM-ABM thay vì tìm thêm prompt để làm nó thắng.

### Hướng 3 — “Institutional stress test” như một benchmark mở

Hướng này bỏ claim tái tạo lịch sử và xây một chuẩn dùng chung cho cộng đồng: các thể chế (quyền đất, thi hành hợp đồng, bảo hiểm cộng đồng, tín dụng) phải được đánh giá dưới các cú sốc có kiểm soát.

Đóng góp mới có thể là một benchmark gồm:

| Thành phần | Yêu cầu công bố |
|---|---|
| State/action contract | Sơ đồ đầy đủ ràng buộc quyền sở hữu, tài sản, nợ và thông tin mà agent được thấy |
| Shock suite | Hạn hán, dịch bệnh, đóng thị trường, thay đổi luật đất, thay đổi chi phí vận tải; magnitude có seed và version |
| Invariants | Không tạo tài sản/tiền trái phép, bankruptcy logic, accounting identity, quyền tài sản |
| Outcomes | survival, consumption floor, asset concentration, mobility, market clearance, institutional persistence |
| Baselines | rulebot, random feasible policy, hand-coded rational policy, LLM policy |
| Evaluation | paired seeds, pre-registered score, Pareto frontier giữa welfare–equity–resilience–compute |

Một benchmark như vậy có thể có giá trị quốc tế ngay cả khi nó không phát biểu về một quốc gia thật. Giá trị của nó là tính đo được, mở và có thể tái lập; không phải độ chân thực bằng cảm giác.

## Phụ lục C — Cổng quyết định trước khi viết bài

Chỉ nên bắt đầu viết manuscript khi tất cả cổng tương ứng với hướng đã chọn đều đạt.

| Cổng | Hướng 1: kinh tế sử | Hướng 2/3: phương pháp/benchmark |
|---|---|---|
| Claim | Một câu hỏi nhân quả, sign/range dự báo trước | Một hypothesis đo được LLM/architecture cải thiện điều gì |
| Dữ liệu | Raw data, codebook, DOI/citation, license, holdout khóa | Task suite và expected outcomes có version |
| Hiệu lực | Fit nhiều moment và pass holdout chưa dùng để fit | So sánh đa baseline/model, ablation và paired CI |
| Tái lập | One-command non-network reproduction của figures/tables | Cache/transcript replay, cost/quota/failure log |
| Độ bền | ≥30 seed; sensitivity/prior posterior; placebo | ≥30 seed mỗi điều kiện; model/provider/time robustness |
| Minh bạch | Nêu moment không khớp, non-identification, thất bại | Công bố failure modes và điều kiện LLM kém baseline |

### Ưu tiên 90 ngày

1. **Tuần 1–2:** chọn duy nhất hướng 1, 2 hoặc 3; viết pre-analysis plan 2 trang với outcome chính, baseline, seed list và tiêu chí loại run.
2. **Tuần 3–6:** hoàn thiện data/benchmark package, parameter registry và CI không mạng; sửa môi trường test để toàn bộ suite chạy xanh trên runner sạch.
3. **Tuần 7–10:** chạy ensemble rulebot trước (30–100 seed theo chi phí), sensitivity/ablation và tạo figures tự sinh từ manifest.
4. **Tuần 11–12:** chỉ chạy LLM thật khi protocol đã khóa; coi đây là treatment bổ sung, lưu replay artifact và toàn bộ chi phí/failure.

Kết luận cập nhật không thay đổi: **THÓC có hạt nhân kỹ thuật đáng đầu tư và có thể dẫn tới công trình quốc tế tốt. Nhưng hiện nó chưa có bằng chứng thực chứng hoặc thiết kế benchmark đủ chặt để xứng đáng với claim “world-class research paper”.** Bước đột phá cần làm là tăng khả năng bác bỏ và đo lường—not tăng số cơ chế hay độ dài narrative.

---

## Phụ lục D — Hướng chuyên sâu khuyến nghị: nền kinh tế đi từ nông nghiệp đến tiền tệ và nhà nước

### D.1. Có phù hợp không?

**Có, và đây nên là hướng trung tâm của THÓC.** Một mô hình tập trung vào quá trình phát triển từ cộng đồng nông nghiệp sẽ nhất quán hơn với lõi hiện có (đất hữu hạn, lao động, tồn kho, sản xuất, hợp đồng và phân phối) so với việc cố mô phỏng mọi bộ phận của kinh tế hiện đại.

Tuy nhiên, không nên mô tả nó như một quy luật lịch sử tất yếu: nông nghiệp không tự động dẫn tới tiền kim loại, ngân hàng hay chính phủ hiện đại. Nhiều xã hội dừng ở tự cung tự cấp, dùng tín dụng quan hệ, tiền hàng hóa, quyền lực phi chính thức hoặc bị ngoại lực can thiệp. Vì vậy mục tiêu khoa học đúng là:

> Xác định các điều kiện vật chất, thông tin và thể chế khiến một cộng đồng nông nghiệp **có xu hướng** chuyển sang chuyên môn hóa, trao đổi, tiền tệ và năng lực công quyền; đồng thời xác định khi nào quá trình này thất bại hoặc đảo ngược.

Điều này vừa có tính kinh tế học, vừa tạo được các dự báo có thể bác bỏ. Mô hình phải sinh ra cả các trường hợp “không phát triển”, không chỉ dẫn mọi seed đến công nghiệp hóa.

### D.2. Đơn vị phân tích và nguyên tắc thiết kế

**Hộ gia đình** là đơn vị kinh tế chính ở các giai đoạn đầu; cá nhân là đơn vị nhân khẩu học, kỹ năng, hôn nhân/thừa kế và lao động. Khi có tổ chức sản xuất, mới thêm firm/entity. Chính quyền không được xuất hiện như một object có sẵn; nó là tổ chức có ngân sách, quyền cưỡng chế hữu hạn và tính chính danh phải được hình thành/duy trì.

Mỗi giai đoạn phải tuân bốn nguyên tắc:

1. **Ràng buộc trước, hành vi sau.** Đất, mùa vụ, thời gian lao động, tồn kho, vận tải và thông tin giới hạn action space; agent không được “sáng tạo” nguồn lực.
2. **Sổ sách theo bảng cân đối.** Hàng hóa, đất, tiền, khoản phải thu/phải trả, vốn của tổ chức và công quỹ phải có counterpart. Thuế hay phát hành tiền không phải dòng tài sản vô chủ.
3. **Thể chế là lựa chọn có chi phí.** Tòa án, chợ, kho công, tiền tệ, cảnh vệ và thu thuế tiêu tốn lao động/tài nguyên; lợi ích của chúng phải vượt chi phí trong một số điều kiện, không phải luôn thắng.
4. **Không teleology.** Không dùng điều kiện kiểu “năm 100 sinh tiền”, “Gini cao sinh chính phủ” hoặc “đủ blueprint thì công nghiệp hóa”. Những sự kiện này chỉ có thể là outcome của ngưỡng/chi phí/niềm tin đã công bố.

### D.3. Lộ trình mô hình hóa theo lớp phát triển

| Lớp | Câu hỏi kinh tế | Cơ chế tối thiểu cần có | Điều không nên cài cứng | Bằng chứng/đầu ra cần đo |
|---|---|---|---|---|
| 0. Nền nông nghiệp sinh tồn | Hộ tồn tại và tái sản xuất thế nào dưới đất, mùa vụ, thời tiết? | hộ; đất; lao động theo tuổi; hạt giống; tồn kho lương thực; tiêu dùng tối thiểu; sinh/tử; thừa kế | tăng trưởng, “giai cấp”, giá cân bằng | năng suất, thiếu ăn, dân số, phân bố đất/tồn kho |
| 1. Chuyên môn hóa và trao đổi | Khi nào trao đổi tốt hơn tự cung tự cấp? | nhiều hàng hóa; comparative advantage dị biệt; chợ định kỳ; chi phí tìm kiếm/vận tải; thông tin giá cục bộ | một mức giá chung hoặc chợ luôn thanh khoản | trade share, price dispersion, market participation, surplus |
| 2. Tín dụng quan hệ và hợp đồng | Vì sao nợ/tín dụng xuất hiện dù cam kết không hoàn hảo? | vay hiện vật; thế chấp; uy tín; vỡ nợ; collateral; thực thi cộng đồng | lãi suất ngoại sinh “đẹp”, trả nợ chắc chắn | debt-service, default, risk sharing, concentration of claims |
| 3. Tiền hàng hóa và tiền tệ | Khi nào một tài sản được dùng làm phương tiện trao đổi? | chi phí barter; divisibility; durability; acceptability network; inventory/carrying cost; unit of account | ép mọi người nhận xu hoặc ấn giá cố định | monetary share, velocity, bid-ask spread, seigniorage, price distribution |
| 4. Tổ chức công và chính phủ sơ khai | Khi nào cung cấp hàng hóa công/thực thi luật đáng với thuế? | hàng hóa công; thuế; ngân sách; collector capacity; compliance; legitimacy; public ledger | chính phủ luôn thu được thuế và phân phối hiệu quả | tax compliance, public-good return, fiscal capacity, revolt/exit |
| 5. Nhà nước tài khóa–tiền tệ | Điều gì kiềm chế lạm phát, nợ công và đặc quyền? | công trái; ngân sách liên thời gian; mint/treasury; ngân hàng dự trữ một phần (tùy scope); luật phá sản | tiền pháp định ổn định, ngân hàng không phá sản | inflation, debt/GDP, default, fiscal dominance, wealth inequality |
| 6. Phát triển và mở cửa | Khi nào vốn, công nghệ, di cư và ngoại thương chuyển cấu trúc sản xuất? | firm; đầu tư; học hỏi; hạ tầng; thị trường ngoài vùng; di cư; biến động giá ngoại sinh | công nghiệp hóa như mốc mặc định | sector share, wages, TFP proxy, urbanization, mobility |

Chỉ chuyển sang lớp kế tiếp khi lớp trước đã có identity kế toán, benchmark hành vi và test phản chứng. Các lớp vẫn hoạt động đồng thời sau khi được thêm; tiền tệ không xóa hàng đổi hàng, và nhà nước không xóa tín dụng quan hệ.

### D.4. Cơ chế cốt lõi cần ưu tiên, theo thứ tự

#### 1. Hộ, ngân sách và sản xuất nông nghiệp

Trước khi thêm tiền, phải làm cho kinh tế hiện vật đúng. Mỗi hộ cần quyết định phân bổ lao động giữa canh tác, chăn nuôi/thủ công, tích trữ, đi chợ và đóng góp công; có budget constraint theo mùa; tích lũy hạt giống/công cụ; và chịu rủi ro thời tiết/sức khỏe. Output phải phân biệt rõ **sản lượng, thu nhập, tiêu dùng, tài sản ròng và thanh khoản**.

Chỉ số bắt buộc: food-security rate, yield/ha, subsistence share, marketed surplus, land Gini, consumption Gini, inventory-to-needs và intergenerational mobility.

#### 2. Giá và thị trường phân đoạn

Tránh “một market clearing price” toàn thế giới. Mỗi chợ có không gian, thời điểm mở, số người mua/bán, chi phí vận tải và thông tin không hoàn hảo. Giá là transaction price; price index là đo lường hậu nghiệm. Điều này tạo lý do kinh tế thực cho thương nhân, kho, tín dụng và tiền tệ.

Các kiểm tra comparative statics: tăng chi phí vận tải phải làm price dispersion và tự cung tự cấp tăng; năng suất vùng A tăng phải làm xuất khẩu ròng A tăng nếu đường thương mại còn mở; cú sốc mất mùa phải tạo phản ứng giá/tồn kho có độ trễ hợp lý.

#### 3. Tín dụng trước tiền tệ

Trong lịch sử, tín dụng và đơn vị ghi nợ thường quan trọng trước hoặc song song với tiền kim loại. Vì vậy, thêm loan book và clearing of obligations trước khi xây ngân hàng. Khoản vay phải có principal, đơn vị, lãi/điều kiện, đáo hạn, collateral, seniority và recovery. Chủ nợ có đối ứng tài sản; khoản xóa nợ là transfer/loss được ghi rõ.

Đây là điều kiện để đo “financial development” thực: không phải số lượng hợp đồng, mà là khả năng chia sẻ rủi ro, phân bổ vốn, mức default và mức tập trung quyền đòi nợ.

#### 4. Tiền tệ như kết quả cạnh tranh

Không tạo `coin` rồi bắt mọi giao dịch dùng nó. Hãy cho phép một tập tài sản có thể được chào giá/thanh toán: thóc, muối, kim loại, chứng thư nợ được bảo chứng. Tác nhân chọn tài sản thanh toán theo expected acceptability, chi phí mang/hao hụt, divisibility, biến động giá và network effect. Một tài sản chỉ trở thành tiền khi nó tăng tỷ trọng thanh toán trong nhiều chợ, không phải vì engine đổi cờ.

Khi đó có thể kiểm định các giả thuyết thật: tăng trade network density có làm giảm barter cost và tăng monetary share không; kho công/bảo chứng có làm tăng trust của chứng thư không; phát hành quá mức có làm giảm acceptability không.

#### 5. Chính phủ như một bảng cân đối có năng lực hữu hạn

Chính phủ tối thiểu gồm treasury, tax rolls, public inventory, công trái, nhân lực thực thi và sổ cái công khai. Nó phải lựa chọn thuế (hiện vật, tiền, lao động), đầu tư hàng hóa công (đường, thủy lợi, an ninh, tòa án), trả nợ và/hoặc đúc tiền. Compliance phụ thuộc vào khả năng phát hiện, sanction, lợi ích công nhận được, công bằng cảm nhận và exit/migration—not only Gini.

Định danh tài khóa tối thiểu mỗi tick:

```text
Tài sản công cuối kỳ = tài sản công đầu kỳ
                       + thuế + vay + seigniorage
                       - chi tiêu công - trả nợ gốc/lãi - hao mòn
```

Nếu phát hành tiền được thêm, counterpart phải là nghĩa vụ của treasury/central issuer hoặc tài sản mua vào; nếu không, mô hình sẽ tạo của cải danh nghĩa mà không thể phân tích lạm phát hay nợ công.

### D.5. Kiến trúc phần mềm cần thay đổi để phục vụ hướng này

1. Tạo `HouseholdLedger` và `PublicLedger` tách khỏi ledger giao dịch chung: balance sheet, income statement và cash/commodity-flow statement theo hộ, firm, treasury.
2. Chuẩn hóa đơn vị: kg lương thực, ngày công, hecta, đơn vị tiền, kỳ mùa vụ. Mọi phép cộng/trừ khác đơn vị phải bị chặn ở runtime/test.
3. Tách `production`, `market`, `credit`, `money`, `fiscal`, `demography` thành module có interface state/action rõ ràng. LLM/policy chỉ phát đề xuất; engine kiểm feasibility rồi apply theo thứ tự xác định.
4. Đưa tất cả institution rule vào scenario overlay. Không để tax rate, monetary acceptance hay property-right enforcement ẩn trong persona/prompt.
5. Thêm event-sourced economic journal: mọi giao dịch ghi debit/credit, giá, chợ, counterparty, tax/legal status. Từ journal phải tái tạo được toàn bộ national accounts và wealth distribution.
6. Thêm `stylized_facts` test suite: Walrasian accounting identity không đủ; phải test hướng biến động, độ trễ, phân phối và failure mode của từng lớp.

### D.6. Thiết kế thí nghiệm để chứng minh “hình thành”, không phải “được lập trình sẵn”

Một thể chế chỉ được gọi là hình thành nội sinh nếu thỏa cả năm điều kiện:

1. Không tồn tại ở tick 0 hoặc không được bắt buộc dùng;
2. Có ít nhất một cơ chế thay thế khả thi (barter, tín dụng quan hệ, chợ tư, tự bảo vệ);
3. Tác nhân/tổ chức phải trả chi phí tạo và duy trì nó;
4. Nó tăng adoption/persistence dưới nhiều seed, không phụ thuộc một prompt hay một luật kích hoạt;
5. Khi tắt lợi ích nền tảng của nó (ví dụ giảm transaction cost của barter), adoption giảm theo hướng dự báo.

Ví dụ thí nghiệm tiền tệ: cùng điều kiện đầu, thay đổi duy nhất là divisibility và carrying cost của kim loại. Nếu monetary share không thay đổi, thì “tiền” trong model có lẽ đang do quy tắc ẩn, không do động cơ kinh tế. Ví dụ thí nghiệm chính phủ: cho phép hai village cạnh tranh một bên có thể tự đánh thuế để làm thủy lợi/an ninh, bên kia chỉ dựa vào tự nguyện; so sánh welfare, compliance, exit và fiscal sustainability trong cùng seed.

### D.7. Mốc phát triển khả thi

**Phiên bản nghiên cứu 1 — Agrarian core (8–12 tuần):** chỉ lớp 0–2, không LLM thật. Mục tiêu là hộ, đất, mùa vụ, chợ địa phương, tín dụng hiện vật và tài khoản phân phối đáng tin cậy. Đây đã là một bài tốt nếu có dữ liệu/validation.

**Phiên bản nghiên cứu 2 — Money emergence (6–10 tuần tiếp):** thêm lớp 3 với cạnh tranh giữa phương tiện thanh toán và measurement của adoption. Không thêm ngân hàng trung ương hoặc lạm phát hiện đại trước khi monetary acceptance được xác minh.

**Phiên bản nghiên cứu 3 — Fiscal state (8–12 tuần tiếp):** thêm lớp 4–5 với treasury, public goods, compliance, debt và currency issuer. Tách rõ state capacity, legitimacy và coercion.

**Phiên bản nghiên cứu 4 — Structural transformation:** chỉ sau khi các lớp nền qua validation, thêm firm, ngoại thương, hạ tầng, di cư và công nghệ. “Công nghiệp hóa” khi đó là outcome đo bằng cơ cấu việc làm, năng suất và vốn, không phải nhãn điều khiển logic.

### D.8. Câu hỏi nghiên cứu mạnh nhất cho hướng này

Thay vì một paper nói “mô phỏng sự hình thành nền kinh tế”, hãy tách thành chuỗi paper có thể kiểm định:

1. *Land scarcity, weather risk, and the emergence of informal credit in agrarian communities.*
2. *When does a medium of exchange emerge? Transaction costs, trust networks, and competing monies.*
3. *Fiscal capacity from below: public goods, tax compliance, and the durability of local government.*
4. *From agrarian surplus to structural transformation: which institutions make investment persistent?*

Chuỗi này giúp mỗi bài có claim hẹp, dữ liệu/benchmark phù hợp và giá trị độc lập. Hệ thống THÓC là hạ tầng chung, không cần ép một manuscript gánh toàn bộ lịch sử kinh tế.
