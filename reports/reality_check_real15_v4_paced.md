# Reality check — `real15_v4_paced`

Ngày chạy: 2026-07-15. Seed 42. Treatment: `spatial_v1` + `spatial_livelihood_v2`
+ `v3` + `v4`; LLM thật, `1..10 request/agent/tick`, không batch.

## Kết luận ngắn

Run **không đạt horizon 15 năm** (45 tick). Nó dừng hợp lệ ở tick 21 (năm 7) vì dân số
về 0, không phải vì quota. Artifact là một bằng chứng chẩn đoán tốt về một deadlock đầu kỳ,
nhưng **không được dùng** để kết luận về quá trình hình thành thị trường, tiền tệ hoặc chính
quyền.

Pacing V4 đã hoạt động: gateway chờ tổng 249 giây cho cửa sổ RPM hồi lại, không chạy một
tick nửa cohort. Tuy nhiên, chất lượng quyết định thực tế và các quyền khởi đầu vẫn chưa đủ
để xã hội sống sót.

| Chỉ tiêu | Kết quả |
|---|---:|
| Tick/yêu cầu chạy | 45 / 15 năm |
| Tick/y đạt được | 21 / năm 7 |
| Lý do dừng | `population_extinct` |
| Dân số: t0 → t7 → t8 → t9 → t21 | 50 → 48 → 27 → 11 → 0 |
| Tuổi chết trung bình / trung vị | 25.25 / 26.2 |
| Tử vong dưới 40 tuổi | 50 / 50 |
| Nguyên nhân chết | 44 `chet_doi`, 5 `phoi_nhiem`, 1 `tu_vong_co_ban` |
| Nhà hoàn thành | 0 |
| Giao dịch chợ / khối lượng giao dịch | 0 / 0 |
| Hợp đồng ký được | 1 (vi phạm ở tick kế) |
| LLM agent-tick | 487 |
| Request provider vật lý | 1,367 |
| Response logic ghi được | 468 |
| Ước tính chi phí token hiện tại | $0.471 (không đủ để suy ra chi phí mọi retry/429) |

## Điều gì đã đúng

### Coverage LLM và reproducibility

- Mọi tick có người sống đều báo `api_call_min_met=true`; không có vi phạm sàn/trần/batch.
  `llm_calls.sqlite` có 468 row và tất cả có `batch_size=1`.
- 487 agent-tick đã có tối thiểu một request provider; 10 request bị scheduler từ chối khi
  một agent đã tiêu hết trần 10. Đây là giới hạn cứng đúng mong muốn, không có request thứ 11.
- Preflight RPM đã không làm biến tick 2 thành một tick policy-card. Nó chờ trước tick và
  không làm world-time tiến khi cohort chưa đủ headroom.
- Action journal khép kín: 575 action được ghi outcome, `unobserved=0`.
- Không có collapse sinh thái: cuối run canopy rừng trung bình 0.972, biomass 23,949 / 24,640,
  gà rừng 2,279 / K 2,395 và cá còn 16,315kg. Do đó không thể đổ kết quả cho cạn kiệt tài nguyên.

### Hành vi có xuất hiện nhưng chưa tạo nền kinh tế

- Có 35 vụ lúa, 8 vụ đông (toàn khoai), 29 lần đốn gỗ, 331 lần đánh cá, 1 hôn nhân,
  2 báo giá và 1 hợp đồng góp công.
- LLM sử dụng 1–10 request theo agent khi cần; một số intent lạ được dịch thành công.
- Tuy nhiên, các mảnh hành vi này không ghép thành chuỗi sinh kế bền vững hoặc thị trường.

## Chẩn đoán nhân quả

### 1. Deadlock nhà ở–quyền đất

Ở mọi tick có người sống, `vo_gia_cu == dan_so`; `so_nha` luôn bằng 0.

- V3 làm sức khỏe mất do phơi nhiễm khi không nhà. Health trung bình đi 91.0 (tick 1) →
  75.7 (tick 4) → 38.0 (tick 7) → 29.3 (tick 8).
- Hành động xây nhà có tồn tại, nhưng 6 dự án nhà đều bị `no_right`: người tạo không sở hữu
  thửa đặt công trình.
- Không có event `san_cho_o_toi_thieu` và không có event `homestead`. Safety floor chỗ ở
  không tạo tài nguyên (đúng), nhưng cũng không có đường **hợp lệ** để mở dự án cho người chưa
  có title (không đủ).
- Trong scenario này title ruộng cần 4 mùa lúa liên tiếp trên cùng ruộng công. Người không có
  site không thể dựng nhà trong khi chờ 4 mùa; họ chết trước khi quyền đó tích lũy.

Đây là lỗi thiết kế về *entry right*, không phải bằng chứng rằng nhà ở hoặc bất động sản phải
được cấp miễn phí. Chỉ đổi ngưỡng health hay tăng gỗ không giải quyết được `no_right`.

### 2. Nút thắt phân bổ ruộng công và hiệu ứng ID

155 action bị từ chối với `parcel_claimed`, lớn nhất trong các rejection execution. Nhiều người
độc lập chọn cùng vài ruộng gần làng; engine apply theo `sorted(id)` nên người có ID nhỏ thắng
đều. Ví dụ A0001 gặt ba ruộng ngay tick 1 trong khi phần lớn cohort không có vụ mùa.

Kết quả là 85.7% hộ thiếu ăn từ tick 2–7, dù `thoc_moi_nguoi` đôi lúc dương và GDP vật lý có
ghi nhận. Đây là phân phối/tiếp cận lương thực thất bại, không phải thiếu tổng sản lượng đơn thuần.
Food floor chỉ kích hoạt 6 lần, quá ít để bù cho cơ chế quyền sử dụng ruộng bị nghẽn.

### 3. Đói + phơi nhiễm gây pha chuyển tử vong

177 event `an_doi` xuất hiện từ tick 4. Sau khi health xuống dưới ngưỡng nguy kịch, dân số rơi
theo cụm: 48→27 ở tick 8, rồi 27→11 ở tick 9. 44/50 tử vong mang nhãn đói, 5 do phơi nhiễm.
Thóc/người tăng mạnh sau các đợt chết chỉ vì mẫu số co lại; đó **không** là phục hồi phúc lợi.

### 4. Coverage request không bằng coverage quyết định hữu dụng

Đây là vấn đề đo lường quan trọng nhất của tầng LLM:

- Scheduler báo 487/487 agent-tick đạt sàn request, nhưng chỉ có 468 response logic được ghi.
- Decision provenance ghi khoảng 35 plan `fallback` (xấp xỉ 7.2% cohort), trong khi
  `run_meta.fallback_rate=0.43%`. Hai thước đo mâu thuẫn.
- Ví dụ tick 6 có 49 agent, 303 request vật lý, 7 request bị cap từ chối và 19 plan fallback.
  Các retry/rate-limit đã tiêu budget của một số agent trước khi một JSON quyết định hữu dụng
  được ghi. Transcript hiện không chứa đầy đủ mỗi failed physical attempt.

Vì vậy PASS hiện tại chỉ nói “mỗi agent đã thử gọi provider”, chưa nói “mỗi agent đã nhận đúng
một quyết định LLM parse được”. Một nghiên cứu không được gộp hai khái niệm này.

### 5. Không có cầu nối tới thị trường

`kl_cho=0`, `kl_giao_dich=0`, không có đất bán, không có entity/blueprint/tiền. Khi survival
và quyền cư trú chưa ổn định, không thể diễn giải sự vắng mặt này như “thị trường chưa tự phát”;
nó chỉ là quần thể chưa vượt qua giai đoạn sống còn.

## Ưu tiên sửa trước real run kế tiếp

1. **Tạo đường quyền cư trú hợp lệ nhưng không tặng nhà hay ruộng.** Thêm `quyen_cu_tru_tam`
   trên ô dân cư/công gần làng: claim công khai, một hộ một site, không cho sản lượng nông nghiệp,
   chỉ cho phép đặt dự án nhà. Nhà vẫn cần 8 gỗ + 240 công và có thể cần hợp tác/hợp đồng.
   Hoặc cho phép dự án nhà trên thửa `homestead_ai` của chính người đang tích lũy quyền, với
   quyền mất đi nếu họ bỏ thửa. Cả hai đều phải config-gated, action/event/audit rõ ràng.
2. **Thay `parcel_claimed` theo ID bằng cơ chế phân bổ công khai đồng thời.** Người gửi claim
   ruộng công; nếu cầu vượt cung, dùng lottery seeded hoặc đấu giá/công-credit tùy config.
   LLM chỉ thấy registry và outcome tick sau. Không dùng prompt gợi ý thửa riêng hay shortcut
   theo ID.
3. **Nâng safety floor thành feasibility bridge.** Khi household nguy cấp và chưa có site,
   safety chỉ được tạo một *intent quyền cư trú* hợp lệ; sau đó mới tạo work-order nhà. Không
   mint đất/gỗ/công, không hoàn thành nhà tự động.
4. **Tách request coverage khỏi decision coverage.** Log mọi HTTP attempt (kể cả 429/retry),
   mỗi agent phải có `parsed_decision=true|false`, và telemetry fallback phải lấy cùng nguồn
   `decision_provenance`. Với treatment autonomy, không chấp nhận run khoa học khi parsed
   decision coverage dưới ngưỡng khai báo.
5. **Pace theo quota thực nghiệm, không chỉ quota YAML.** Học headroom sau 429, reserve một slot
   response cho agent thay vì để retry đốt hết 10 slot, và ghi chi phí/bằng chứng của attempt
   lỗi. Điều này giảm spike 303 request/tick và làm chi phí có thể audit.

## Gate trước lần chạy real tiếp theo

Không chạy ensemble kinh tế 15 năm cho tới khi một smoke 12 tick thỏa đồng thời:

- không terminal extinction;
- `parsed_decision_coverage` được ghi và đạt ngưỡng công bố;
- không agent vượt 10 request, không batch;
- ít nhất một đường hợp lệ từ “không đất/không nhà” sang site cư trú và dự án nhà được quan sát;
- `parcel_claimed` không còn bị quyết định bởi thứ tự ID;
- audit ledger/action journal/replay đều xanh.

Các gate trên là điều kiện chất lượng artifact, **không** phải mốc engine ép xã hội phải có
nhà, chợ hay tiền ở một tick định trước.
