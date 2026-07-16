# Báo cáo phân tích run LLM thật `real15_v5`

Ngày: 2026-07-15  
Phạm vi: seed 59, 45 tick = 15 năm, scenario `agrarian_transition_v1` với các overlay spatial v1 đến livelihood v5.  
Artifact gốc: `data/runs/real15_v5/`

## Kết luận ngắn

Bản v5 đã sửa được lỗi nền tảng nghiêm trọng nhất của các run trước: cộng đồng không còn rơi vào vòng xoáy vô gia cư–đói ngay từ đầu. Tuy nhiên nó **chưa mô phỏng một nền kinh tế đang hình thành**. Sau 15 năm, xã hội trở thành một làng nông nghiệp cực kỳ dư thừa lương thực, xây được nhà và lập gia đình, nhưng không tạo được quyền sở hữu ruộng, thị trường hoạt động, nghề chuyên môn ổn định, giao thông qua sông, tiền tệ, tín dụng, chính quyền hay đổi mới công nghệ.

Nghiêm trọng hơn, một người vẫn chết đói trong lúc phần còn lại của làng giữ lượng lương thực rất lớn; và artifact không replay kín được. Vì vậy run này rất hữu ích để chẩn đoán, nhưng chưa được dùng làm bằng chứng khoa học có thể tái lập hay làm căn cứ để tuyên bố “LLM agents tự chủ hoàn toàn”.

## 1. Phương pháp và trạng thái bằng chứng

Các nguồn được đối chiếu là:

- `metrics.jsonl`, `events.jsonl`, `transcript.jsonl`, `unrecognized_intents.jsonl`;
- checkpoint cuối `checkpoint_0045.pkl`;
- manifest, telemetry và trình xác minh `tools.verify_research_run`;
- mã engine/prompt liên quan đến đất công, tiêu dùng, nhân khẩu, thị trường, research và transcript replay.

Không có LLM/provider call nào được thực hiện để làm báo cáo này.

### Tính toàn vẹn artifact

| Kiểm tra | Kết quả | Diễn giải |
|---|---:|---|
| Config, calendar, scenario files, journal | Pass | Artifact và cấu hình chạy được lưu đầy đủ. |
| World hash | Pass | Hash replay của thế giới là `c46f412c8742…`, trùng hash gốc. |
| Transcript replay kín | **Fail** | 1.936 transcript row được tiêu thụ nhưng có **167 transcript miss**. |
| Trạng thái nghiên cứu | `diagnostic_only_unreplayable` | Không được gọi là replay-verified hoặc publication-grade. |

Hash trùng chỉ chứng minh rằng nhánh fallback hiện tại tình cờ tái tạo cùng trạng thái cuối. Nó không chứng minh tất cả quyết định LLM và mọi nhánh điều khiển đã được ghi rồi phát lại kín.

## 2. Ảnh chụp kết quả

### Những phần thực sự tốt hơn

| Chỉ số | Tick 1 | Tick 45 | Nhận xét |
|---|---:|---:|---|
| Dân số | 50 | 55 | Có 11 ca sinh và 6 ca chết. |
| Nhà | 0 | 49 | Cơ chế quyền lô cư trú + dự án nhà đã chặn được khủng hoảng nhà ở ban đầu. |
| Vô gia cư | 50 | 0 | Thành quả quan trọng, nhưng có can thiệp safety floor. |
| Tỷ lệ biết chữ | 16,0% | 72,7% | Học chữ đã lan rộng. |
| Công cụ | 0 | 18,95 | Có chế tác cơ bản. |
| Hôn nhân | 0 | 18 | Hành vi gia đình/xã hội không hoàn toàn bị tê liệt. |
| Giao dịch quote đã thanh toán | 0 | 8 | Có mầm trao đổi song phương, chủ yếu là gỗ. |
| Hợp đồng hoàn thành | 0 | 4 | Có hợp tác lao động nhỏ, nhưng chưa thành thị trường lao động. |

Agent cũng đã dùng cả ngô và khoai: có 377 vụ thu hoạch ngô và 266 vụ khoai. Đây là dấu hiệu tích cực rằng tập hành động không bị khóa vào thóc duy nhất.

### Những phần không hình thành

| Cơ chế cần hình thành | Kết quả cuối run |
|---|---:|
| Ruộng tư hữu | 0 |
| Giao dịch đất | 0 |
| Khớp lệnh chợ trung tâm | 0 |
| Giá trị giao dịch chợ trung tâm | 0 thóc |
| Giá trị trao đổi đã settlement | 513 thóc trong 15 năm |
| Thuyền / qua sông / đò | 0 / 0 / 0 |
| Khai hoang bờ hoang | 0 |
| Tiền `xu`, credit, nợ | 0 |
| Chính quyền, thuế, công quỹ | 0 |
| Blueprint, máy, pháp nhân | 0 |
| Lao động chăm trẻ có trả công | 0 |

Đây không chỉ là “chưa đủ lâu”. Một số nhánh có động cơ kinh tế yếu hoặc không thể quan sát được đối với agent, nên trong cấu hình hiện tại chúng bị thống trị bởi tự canh tác và tích trữ.

## 3. Các phát hiện ưu tiên cao

### P0-1. Replay transcript và cam kết “mỗi người một LLM turn” đang sai về mặt kiểm chứng

**Bằng chứng**

- Run báo 2.099 logical agent-turn, nhưng transcript có 1.936 row tổng cộng, bao gồm cả call phụ.
- Trình xác minh phát hiện đúng 167 miss. Ví dụ tick 23 có 47 logical task nhưng chỉ 24 transcript call; tick 37 có 45 logical task nhưng chỉ 23 transcript call.
- Có 24/45 tick có số transcript call thấp hơn số người/thinking task.
- Dù vậy metrics vẫn ghi `api_call_min_met: true` cho mọi tick.

**Nguyên nhân gốc đã xác nhận**

`NganSachLLMTick` đếm một HTTP request đã bắt đầu, không đếm một quyết định cuối cùng đã được ghi và dùng được. Khi `LoiVuotNganSachTick` xuất hiện, agent đi vào fallback nhưng không có transcript row đại diện cho nhánh “budget denied”. Trong replay, `TranscriptProvider` không tái tạo bước lấy budget slot mà cố hỏi transcript cho prompt vốn chưa từng được ghi; nó tạo 167 miss rồi lại rơi về fallback. Đây là lý do hash vẫn trùng nhưng gate replay vẫn phải fail.

**Tác hại**

- Không thể chứng minh mỗi người đã có một turn quyết định LLM hoàn chỉnh.
- Câu “minimum 1 LLM call per adult per tick” hiện chỉ đúng ở nghĩa hẹp là có slot/request bắt đầu, không đúng ở nghĩa hành vi mà người dùng cần.
- Bất cứ phân tích nào về autonomy, tool use hoặc quyết định cá nhân đều bị yếu đi.

**Cách sửa**

1. Mỗi nhánh terminal phải ghi transcript/journal: `response`, `provider_error`, `budget_denied`, `parse_unusable`, `fallback_selected`.
2. Replay phải tiêu thụ row này và ném đúng `LoiVuotNganSachTick` cho `budget_denied`, thay vì dùng miss như một tín hiệu fallback ngầm.
3. Tách hai chỉ số:
   - `provider_request_started`;
   - `completed_agent_decision_turn`.
   Chỉ số thứ hai mới là invariant autonomy.
4. Bổ sung `completed_turn_by_agent`, `terminal_reason_by_agent`, và hard gate: mỗi adult/tick có đúng một trạng thái terminal được ghi.
5. Viết regression test cố ý làm đầy cap của một agent, rồi yêu cầu `replay_from_transcript(...).misses == 0`, `unused == 0` và world hash trùng.

Không được “sửa” artifact cũ bằng cách chèn tay 167 row vào transcript. Artifact `real15_v5` phải được giữ là diagnostic artifact; chỉ run mới sau khi sửa mới có thể đạt chuẩn.

### P0-2. Một agent chết đói trong một xã hội dư lương thực

**Bằng chứng**

- `A0021` bị ghi `an_doi` liên tiếp từ tick 15 đến 24, rồi chết `chet_doi` ở tick 24 khi 25,5 tuổi.
- Trong 11 turn trước khi chết, LLM liên tục nhận ra nguy cơ chết đói nhưng chỉ chọn `danh_ca` với 120 công. Tick cuối bắt được 7 kg cá, không đủ nhu cầu 60 kg thóc-equivalent/tick.
- Không có tin nhắn, xin hỗ trợ, tặng biếu, hợp đồng đổi công lấy thóc, tín dụng hay chuyển vào hộ được tạo bởi agent này.
- Trong cùng giai đoạn, xã hội đã có tổng kho rất lớn; đến tick 24 tổng thóc là 125.221 kg. Chết đói ở đây là thất bại tìm kiếm/điều phối, không phải khan hiếm vật chất toàn làng.
- Safety floor lương thực chỉ thêm một vụ canh khi agent có giống và công khả thi. Nó không cứu được người đã hết thóc giống.

**Vấn đề mô hình**

Prompt nói “hãy làm mọi cách để sống”, nhưng không đưa cho agent một bài toán cứu sinh có thể hành động: mỗi lựa chọn không có ước lượng thực phẩm ròng, không có danh sách con đường cứu trợ hợp pháp, không có cơ chế tìm đối tác có khả năng cho vay/đổi công, và không có vòng thương lượng đủ nhanh. LLM vì vậy lặp lại một hành động sinh tồn cục bộ nhưng bị thống trị.

**Cách sửa mà không tạo tài nguyên miễn phí**

1. Khi food runway dưới ngưỡng, hiển thị một `survival feasibility card`: nhu cầu tick này, lượng food-equivalent ròng của mỗi hành động khả thi, thời gian có kết quả, và các ràng buộc.
2. Cung cấp các hành động xã hội có hiệu lực thật: `xin_ho_tro`/`doi_cong_lay_luong_thuc`/`vay_thoc_doi_cong_tuong_lai`, với đối tác nhìn thấy hợp pháp qua quan hệ gần, bảng rao hoặc tín hiệu “có dư” chứ không lộ ví tiền toàn làng.
3. Cho phép yêu cầu khẩn cấp và phản hồi trong cùng tick hoặc một sub-round có giới hạn; tiền/thóc phải bị escrow và mọi chuyển khoản phải vào ledger.
4. LLM vẫn chọn phương án; engine chỉ liệt kê phương án hợp lệ. Không mint thóc, công, đất hay nhà.
5. Safety floor phải có mode ablation. Nếu còn dùng, ghi rõ số quyết định, người và outcome do floor tạo; không gộp vào autonomy LLM.

**Test bắt buộc**: dựng fixture giàu–nghèo giống A0021 (một người không hạt giống, hàng xóm có surplus, cá không đủ calo). Agent phải được cung cấp ít nhất một đường hợp pháp để thương lượng; không được chết chỉ vì lặp lại hành động có food balance âm.

### P0-3. Quyền đất không thể nổi lên vì agent không giữ được mục tiêu homestead

**Bằng chứng**

- Có 1.994 lượt phân ruộng công trên 250 thửa, nhưng `dat_tu_huu = 0`.
- Phân tích chuỗi người–thửa cho thấy độ dài canh liên tục lớn nhất là **1 mùa lúa**; không một ai quay lại cùng thửa ở mùa lúa kế tiếp.
- Luật cần 4 mùa lúa liên tiếp để thành chủ.
- Prompt có nhắc luật homestead, nhưng các fact card xoay danh sách ruộng công và không nói rõ: “bạn đang giữ Pxx, đã 1/4 mùa, cần quay lại Pxx ở vụ sau”.

**Nguyên nhân gốc**

Đây là lỗi information architecture và memory/action binding, không phải kết luận rằng LLM “không muốn sở hữu đất”. Engine đã bảo vệ `homestead_ai`, nhưng UI của agent không biến quyền tạm thời đó thành một mục tiêu nổi bật, bền và có payoff nhìn thấy được. LLM chọn lại các thửa có vẻ tốt ở mỗi turn.

**Cách sửa**

1. Thêm fact card ưu tiên cao: `HOMESTEAD CỦA BẠN: Pxx, tiến độ 2/4, vụ tiếp theo cần canh Pxx, phần thưởng: title`.
2. Không random-rotate thửa đang homestead của chính agent; chỉ xoay bảng ruộng công chưa ai giữ.
3. Thêm policy goal bền như `muc_tieu_dat: giu_Pxx_den_title`, có thể được LLM sửa/hủy rõ ràng.
4. Thêm action cấp cao `tiep_tuc_homestead` để compiler chọn đúng thửa khi dữ liệu đã quan sát; không tự cấp đất.
5. Hiển thị chi phí cơ hội: năng suất, độ màu, mùa còn lại và khả năng cho thuê sau khi có title.
6. Test nhiều seed: một agent kiên định phải nhận title sau đúng 4 mùa lúa; một agent bỏ vụ phải mất tiến độ; agent khác không cướp được thửa đang tích lũy.

Quyền đất phải được sửa trước khi đánh giá tô đất, thuê ruộng, thừa kế đất, phân tầng giai cấp hay chính quyền địa phương.

## 4. Nền kinh tế đang dư thừa, nên không có áp lực để chuyên môn hóa

### Bằng chứng về cân bằng lương thực không thực tế

Trong 15 năm:

- lúa thu hoạch: khoảng 571.807 kg;
- ngô: khoảng 155.886 kg;
- khoai: khoảng 87.242 kg;
- cá bắt được: khoảng 2.913 kg;
- quy đổi sơ bộ food-equivalent của bốn nguồn trên: khoảng **784.817 kg thóc-equivalent**.

Trong khi đó, ledger ghi tiêu dùng lương thực thấp hơn rất nhiều và vẫn có hao kho lớn: riêng hao kho là khoảng 123.627 kg thóc, 43.157 kg ngô và 27.398 kg khoai. Dù đã có hao kho 2,01% mỗi tick, cuối run vẫn giữ 251.920 kg thóc, 111.676 kg ngô và 58.249 kg khoai. Thóc/người tăng từ 606 lên 4.580 kg.

Điều này giải thích phần lớn kết quả còn lại:

- tự canh tác luôn chi phối việc đi làm thuê hay buôn bán;
- không có lý do mạnh để bán ngô/khoai, thuê đất, mạo hiểm qua sông hoặc đầu tư collective;
- không có khủng hoảng đủ thật để tạo nhu cầu credit, bảo hiểm, chính quyền hoặc đổi mới;
- một cái chết đói lại càng cho thấy vấn đề là phân phối/search, không phải tổng cung.

### Hướng sửa đúng

Không nên thêm chi tiết vi mô như hạt giống, nước hay dưỡng chất chỉ để làm hệ thống phức tạp. Cần hiệu chỉnh **cân bằng vĩ mô tối giản**:

1. Xác định dải mục tiêu cho surplus thực phẩm dài hạn bằng dữ liệu/giả định có provenance, thay vì nhắm vào một con số kết quả.
2. Calibrate đồng thời năng suất, lao động, giống, hao kho, diện tích sẵn có và rủi ro thời tiết. Một thay đổi yield đơn lẻ sẽ tạo tác dụng phụ.
3. Đo food-equivalent theo hộ, không chỉ `tong_thoc`; báo cáo production, consumption, seed, spoilage và stock cùng một bảng cân đối.
4. Cho lợi thế so sánh có quy mô nhỏ nhưng rõ: một số vị trí/agent làm gỗ, cá, chế tác hoặc cây vụ đông tốt hơn; không gán nghề cố định.
5. Bảo đảm vẫn có surplus tự nguyện để trao đổi. Mục tiêu không phải làm dân nghèo đi để ép thị trường xuất hiện.

## 5. Thị trường có giao diện nhưng chưa có vòng cung–cầu

### Bằng chứng

- 426 lệnh chợ do LLM tạo: 244 lệnh mua gỗ, 175 mua công cụ, chỉ 6 lệnh bán toàn bộ các hàng.
- 583 lệnh chợ không khớp; `central_market_matched_quantity = 0` và `kl_cho = 0` toàn run.
- Quote song phương cũng lệch một chiều: 34/37 quote đăng là mua gỗ, chỉ 1 quote bán gỗ. Có 8 settlement nhỏ, tổng 153 thóc qua quote.
- Tổng giá trị settlement của quote + contract chỉ 513 thóc, quá nhỏ so với kho lương thực.
- Hầu hết người tự khai gỗ hoặc tích lũy, không nhìn thấy một cơ hội trở thành người bán có lãi.

### Nguyên nhân

1. Cầu xây nhà xuất hiện đồng thời, nhưng supply gỗ không được đóng gói thành một nghề có giá trị kỳ vọng rõ ràng.
2. Bảng giá cung cấp “giá ước riêng” và vài giá quote, nhưng agent không thấy rõ order book nào đang thiếu hàng, doanh thu kỳ vọng sau lao động, hay người mua đáng tin.
3. Gỗ/công cụ không tạo lợi thế chuyên môn đủ bền so với tự làm; vì toàn xã hội dư lương thực, chi phí cơ hội của tự túc thấp.
4. Lệnh chợ và quote là hai giao thức khác nhau, làm tăng tải nhận thức và khả năng gửi nhầm/bị hết quote.

### Hướng sửa

- Hiển thị public market radar theo thông tin công khai: bên mua/bán, giá tốt nhất, khối lượng còn thiếu, khoảng cách và lợi nhuận ròng ước tính sau lao động/vận chuyển.
- Thêm work order thực: chủ nhà/ruộng/đò đăng escrow thóc và yêu cầu công/gỗ; worker chấp nhận, giao nhận và thanh toán tự động qua hợp đồng. Đây là thị trường lao động, không phải trợ cấp.
- Hợp nhất luồng “tìm–mặc cả–ký–settle” thành một protocol có state machine và feedback cho cả hai bên. Tin nhắn vẫn hữu ích cho thương lượng, nhưng hợp đồng/quote phải có payoff rõ ràng.
- Dùng comparative advantage, kỹ năng, vị trí và tồn kho làm nguồn của specialization; không đặt nghề cố định hay ép agent bán hàng.
- Báo cáo tỷ lệ buyer/seller, fill rate, cancellation, delivery failure, spread, thời gian tìm đối tác và market share theo tài sản.

## 6. Bờ sông, rừng và sinh thái đang tồn tại về code nhưng không phải một lực kinh tế

### Bằng chứng

- Không có thuyền, qua sông, lái đò, khai hoang bờ hoang hay dân số bờ kia.
- Khai thác được khoảng 572,75 gỗ để xây 49 nhà, nhưng biomass rừng tăng từ 20.116 lên 24.009, gần sức chứa 24.640.
- Gà rừng tăng từ khoảng 1.624 lên 2.391; cá cũng phục hồi. Có bắt cá/gà, nhưng không có áp lực tài nguyên lâu dài.

### Diễn giải

Không xây thuyền là lựa chọn hợp lý trong setup này: còn 252 ruộng công gần làng, rừng gần làng dồi dào, bờ kia không có chênh lệch lợi ích đủ lớn, và chưa có hành khách hay hàng hóa tạo doanh thu cho đò. Đây không nên bị gán là “LLM thiếu sáng tạo”.

### Hướng sửa

1. Thiết kế chênh lệch không gian có thể quan sát: bờ kia có đất/nguồn lực/đường đi hoặc năng suất khác, nhưng có chi phí và rủi ro vận chuyển thật.
2. Tạo nhu cầu qua sông nội sinh: thiếu đất gần làng, buyer gỗ/quặng ở phía kia, hoặc nguồn thực phẩm/đất có lợi thế tương đối.
3. Thuyền phải có economics rõ: capacity, hao mòn, lịch chuyến, passenger/freight order và doanh thu escrow; chủ đò tự đặt giá.
4. Sinh thái phải chịu tác động khi khai thác tăng: forest cover giảm thì gà rừng giảm; reforestation có độ trễ và chi phí cơ hội. Không cần mô hình nước/đất chi tiết.
5. Thử nghiệm stress riêng cho commons để kiểm tra bi kịch tài nguyên, phục hồi, thuê khai thác và quy tắc cộng đồng.

## 7. Tiền tệ, chính quyền và phát minh chưa có động cơ nội sinh đủ mạnh

### Tiền tệ

Hiện thóc vừa là đơn vị giá trị trong prompt vừa là phương tiện thanh toán mặc định của lệnh/quote. `xu` tốn công và quặng nhưng chưa giảm chi phí giao dịch, chưa giải quyết double coincidence, chưa tạo liquidity advantage và chưa có mạng chấp nhận. Không đúc xu trong run này là hành vi kinh tế hợp lý.

Để tiền có thể hình thành:

- tách rõ unit of account khỏi medium of exchange;
- thêm search friction, tính chia nhỏ, độ bền, chi phí cất giữ/vận chuyển và mạng chấp nhận;
- để người dân tự niêm yết/nhận một commodity money khi nó tốt hơn barter/thóc, không dùng threshold “đủ năm thì có tiền”;
- đo acceptance breadth, payment concentration, velocity, price dispersion và coexistence giữa thóc, hàng hóa, credit, xu.

### Chính quyền

Không có title đất, tranh chấp lớn, hạ tầng chung cần duy tu, thuế base hay public-good return nên không có lý do kinh tế–chính trị để hình thành chính quyền. Cần chuỗi thể chế dần dần: hội đồng tự nguyện/thoả ước làng → đóng góp có escrow → public work quan sát được → quy tắc giải quyết tranh chấp → thuế/ủy quyền nếu người dân chấp nhận. Chính quyền không được tự bật chỉ vì dân số hoặc năm mô phỏng.

### Đổi mới

Có 12 lần đóng góp research và literacy cao, nhưng điểm nghiên cứu phân tán: lớn nhất chỉ 18,7 điểm trong khi `k0 = 160`; xác suất ra blueprint trong 15 năm vì thế thấp. Không có blueprint không chứng minh engine research hỏng, nhưng chứng minh rằng hành vi hiện tại không tạo một tổ chức đổi mới đủ mạnh.

Nên thêm:

- dự án nghiên cứu tập thể có vốn/công/royalty escrow;
- quyền sử dụng/giấy phép và lợi ích thương mại của blueprint;
- “bottleneck card” từ sản xuất, ví dụ hao kho, năng suất, vận tải, để nghiên cứu có nhu cầu thực;
- hội thợ/trường học/lab như tổ chức do agent thành lập, không phải tech tree định sẵn.

Không nên chỉ hạ `k0` để ép một phát minh xuất hiện. Điều đó làm kết quả trông sinh động nhưng không tăng tính nội sinh.

## 8. Hộ gia đình, nhà ở và lao động chưa tạo được thị trường dịch vụ

Kết thúc run có 49 nhà nhưng chỉ 29 hộ. Nhiều nhà nằm ở cùng một người, trong khi cơ chế sức khỏe chỉ kiểm tra `any(member has nha)` cho cả hộ. Nhà hiện gần như là inventory an toàn, không phải một đơn vị không gian có cư dân, sức chứa, quyền ở, thuê, sửa chữa hay bỏ trống. Vì vậy không có thị trường thuê nhà dù có dư công trình tương đối.

Tương tự, childcare có 84 hành động chăm trẻ nhưng `childcare_paid_labor = 0`; work order vacancy và fill rate đều không hình thành. Hợp tác xây nhà có xảy ra, nhưng phần lớn không qua lương/hợp đồng rõ ràng.

Hướng sửa tối giản:

1. Mỗi nhà có location, capacity, occupancy và tenure: owner-occupied, hosted, rented, vacant hoặc abandoned.
2. Nhà cho thuê và ruộng cho thuê là contract có thời hạn, rent escrow, quyền sử dụng, quyền đòi trả nhà/đất khi hết hạn, và repair/depreciation đơn giản.
3. Chăm trẻ, xây nhà, khai gỗ và chở đò cùng dùng một job/work-order interface thay vì các action rời rạc.
4. Bảo vệ household sharing tự nguyện, nhưng không để một căn nhà inventory vô vị trí che mất toàn bộ vấn đề cư trú.

## 9. Nhân khẩu học chưa đủ thực tế để dùng cho kết luận dài hạn

### Bằng chứng

- Toàn bộ 50 người khởi tạo đều là người lớn 16–28 tuổi, trung bình khoảng 21,5. Không có trẻ em, người già hoặc cấu trúc nhiều thế hệ ban đầu.
- Có 6 ca tử vong: 5 `tu_vong_co_ban` ở tuổi 23,3–34,3 và 1 `chet_doi` ở tuổi 25,5.
- Cơ chế sinh chưa có thai kỳ/khoảng cách sinh. Ví dụ một cặp sinh ở tick 26 và 28, cách 8 tháng; một cặp khác sinh ở tick 38, 39, 43, 45, gồm khoảng cách 4 và 8 tháng.

### Hệ quả

Run 15 năm không thể kiểm định thừa kế, già hóa, chăm sóc người già, chuyển giao đất giữa thế hệ hay động lực dân số dài hạn. Birth spacing hiện tại còn phi sinh học, nên dân số có thể tăng bằng một cơ chế không thật.

### Hướng sửa

- Khởi tạo age pyramid và household composition có provenance, không chỉ 50 người độc thân trẻ.
- Thêm trạng thái conception → gestation 2–3 tick → sinh → postpartum/lactation interval; twins là event hiếm có khai báo riêng.
- Calibrate mortality theo tuổi và điều kiện sức khỏe; báo cáo age-specific rates, life table có đủ exposure, maternal mortality và starvation mortality riêng.
- Không dùng final `ty_le_ho_thieu_an = 0` làm bằng chứng không có đói: chỉ số đó loại người đã chết. Cần cumulative hunger exposure, food-runway distribution và avoidable starvation death.

## 10. Giao diện LLM đang làm giảm autonomy thay vì tăng nó

### Bằng chứng

- Prompt trung bình khoảng 20.965 ký tự/call, trong khi response trung bình chỉ khoảng 326 ký tự.
- Có 1.936 provider record nhưng mọi `tool_turns` trong transcript đều rỗng. Telemetry cuối tick ghi 0 world-tool call; `run_meta` lại ghi 2 lượt tool, nên instrumentation cũng không nhất quán.
- 75/79 unrecognized intent là `phan_bo_cong` bị lỗi `NoneType is not iterable`, tức là phần lớn là lỗi schema/normalization chứ không phải “ý tưởng mới lạ”.
- Có 17 raw response không parse JSON trực tiếp; nhiều response có code fence hoặc bị cắt.
- Action journal có 1.149 rejection; các mã phổ biến là `unfilled` 583, `parcel_claimed` 206, `insufficient_labor` 185, `insufficient_inputs` 127, `common_land_lottery_lost` 87, `season_not_available` 81 và `unrecognized_intent` 78.

### Hướng sửa

1. Dùng structured output/function schema của provider nếu có thể; normalizer phải biến `null` ở list optional thành `[]` trước validation khi semantics cho phép.
2. Prompt theo tầng:
   - common physical laws ngắn và versioned;
   - private state;
   - seasonal action menu chỉ gồm action đang khả thi;
   - 3–5 cơ hội kinh tế nổi bật;
   - goal stack và feedback từ tick trước.
3. Tool call phải là function call thật, không chỉ nói bằng chữ “bạn có thể dùng tool”. Cho LLM một vòng observe → decide → act, giới hạn call để không bùng chi phí.
4. Tool trả về facts chứ không trả lời thay agent: feasibility, order book công khai, dự án gần, progress homestead, food balance, đối tác hợp lệ.
5. Đưa `nhan_tin`/quote/contract vào action plan khi có payoff; hiện chỉ có 9 tin nhắn trong toàn run.
6. LLM giữ mục tiêu cấp cao; deterministic compiler chỉ chọn ID/công/số lượng hợp lệ và trả feasibility diff để LLM xác nhận. Compiler không được tự quyết nghề hay tạo outcome.

## 11. Các metric hiện chưa đủ để đánh giá khoa học

`gdp` hiện là value-added theo bút toán có giá thị trường gần nhất. Hàng chưa có giá được định giá 0, trong khi hạt giống thóc vẫn là input có giá 1; vì vậy metric có thể âm hoặc biến động mạnh khi thị trường chưa hoạt động. Nó không phải GDP có thể so sánh giữa run hay với lịch sử.

Cần tách tối thiểu:

- physical production và food-equivalent;
- consumption, seed, spoilage, capital formation;
- settled trade theo từng protocol;
- stock và wealth theo cá nhân/hộ;
- market price chỉ cho asset có volume/coverage đủ;
- survival: minimum runway, hunger person-ticks, death cause, homeless exposure;
- autonomy: scheduled/completed/fallback/repair/tool turns theo agent;
- institutions: proposal, participation, compliance, public return;
- ecology: harvest pressure, regeneration, stock/capacity và land-use change.

Mọi chart cuối run phải hiển thị denominator và cumulative series; tránh survivor bias và tránh gọi price quote đơn lẻ là “giá thị trường”.

## 12. Lộ trình triển khai đề nghị

### Giai đoạn A — sửa tính đúng đắn và khả năng kiểm chứng trước

1. Đóng kín transcript replay và sửa terminal accounting của mỗi adult/tick.
2. Sửa schema `phan_bo_cong`/optional lists, JSON repair và telemetry tool/fallback.
3. Thêm regression fixtures cho budget denial, malformed response, tool turn, and fallback.
4. Không chạy LLM thật cho đến khi test/mock và replay của artifact mới pass.

### Giai đoạn B — làm agent thực sự có đường sống và mục tiêu dài hạn

1. Survival feasibility card + social rescue/contract paths.
2. Goal stack bền cho nhà, ruộng homestead, dự án, gia đình, dự trữ và nghề.
3. Homestead progress UI/action; test title đất trong nhiều seed.
4. Residence/house occupancy và work-order đồng nhất.

### Giai đoạn C — tạo vòng kinh tế tối thiểu có khả năng tự phát

1. Recalibrate food balance và comparative advantage.
2. Tạo market radar, seller incentives, escrow và job contracts.
3. Sau khi market có turnover thật mới đánh giá land rent, credit và commodity money.
4. Sau khi có externality/public work thật mới đánh giá council, tax và government.

### Giai đoạn D — không gian, sinh thái và đổi mới

1. Bờ sông có chênh lệch lợi ích và logistics thực.
2. Khai thác–tái sinh rừng/gà/cá có feedback nhìn thấy được.
3. Research collective, royalty và diffusion qua mạng xã hội/thị trường.

### Giai đoạn E — thiết kế nghiên cứu

1. Dùng mock/rule-based để kiểm tra cơ chế qua ít nhất nhiều seed và sensitivity matrix trước.
2. Với LLM, pre-register model, prompt hash, budget, seed, outcome và stopping rule.
3. So sánh treatment có/không safety floor, có/không spatial gradient, có/không market information; không chỉ kể một trajectory đẹp.
4. Chỉ gọi đây là `mechanism benchmark` cho tới khi parameters có provenance, calibration/holdout targets và external validation. Scope hiện tại cũng đã nói rõ không phải tái dựng lịch sử hay dự báo GDP hiện đại.

## 13. Cổng nghiệm thu trước run LLM kế tiếp

Run mới chỉ nên được xem là tiến bộ khi thỏa tất cả các điều sau:

- `python -m tools.verify_research_run <run>` pass hoàn toàn: hash, `misses == 0`, `unused == 0`.
- Mỗi adult/tick có một terminal decision record; nếu không có LLM response phải có lý do minh bạch và run không được gắn nhãn full autonomy.
- Không có chết đói tránh được trong fixture thừa lương thực có đường thương lượng hợp pháp.
- Homestead có thể thành title qua hành vi nhất quán; bỏ dở thì mất tiến độ.
- Không còn lỗi `NoneType is not iterable` cho action hợp lệ có field optional null/omitted.
- Tool telemetry thống nhất với transcript; tool turns nếu có phải replay được.
- Market report trình bày cả hai phía supply–demand, fill rate và settlement; không gọi order chưa khớp là thương mại.
- Demography không tạo các ca sinh cách nhau 4–8 tháng trừ event twins được khai báo.
- Safety floor có bảng provenance riêng và ablation; kết quả sống sót không được gán toàn bộ cho LLM.

## Đánh giá cuối cùng

`real15_v5` là một **bước tiến tốt về ổn định định cư**, không phải một nền kinh tế phát triển tự phát. Nó chứng minh cơ chế xây nhà, nông nghiệp mùa vụ, học chữ, gia đình và một phần hợp tác có thể cùng chạy. Nó đồng thời chỉ ra rất rõ những tầng còn thiếu: survival search, quyền đất bền, market-making từ cung thật, không gian có giá trị kinh tế, tổ chức lao động, nhân khẩu học, và đặc biệt là replay/autonomy accounting.

Ưu tiên đúng không phải thêm ngay tiền tệ hay chính phủ. Trước hết phải làm cho một người nghèo có thể nhìn thấy và sử dụng những đường sống hợp pháp; làm cho đất, nhà, gỗ và công có chi phí cơ hội thật; rồi mới để thị trường, tiền, tổ chức và nhà nước có lý do xuất hiện.
