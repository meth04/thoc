# Data dictionary — agrarian_transition_v1

Scenario này chưa dùng dữ liệu lịch sử làm đầu vào. Mọi tham số hiện tại là **design
assumption** (xem `priors.yaml`, `provenance.csv`). Tài liệu này định nghĩa các metric mà
scenario quan tâm theo năm lớp phát triển, tách rõ **ĐÃ CÓ trong code** với **PENDING**
(chưa cài — không được tuyên bố đã đo). Nguồn code: `engine/economy.py`, `engine/metrics.py`.

## Quy ước missing / zero / undefined (áp cho mọi metric)

- **undefined / missing**: mẫu số không xác định hoặc không có quan sát (vd. tỷ số cần
  giao dịch thật mà tick không có giao dịch). KHÔNG được thay bằng 0; báo là missing.
- **zero (0.0)**: giá trị đo được thật sự bằng 0 (vd. `velocity=0` khi M(xu)≈0 → CHƯA tiền
  tệ hóa; `gia_dat_tren_san_luong_ky_vong=0` khi không có giao dịch đất trong cửa sổ — đây
  là quy ước "không đủ dữ liệu", đọc kèm bộ đếm coverage, không diễn giải là "giá = 0").
- **coverage counter**: mọi tỷ số/giá phải đi kèm bộ đếm mẫu (vd. `so_gd_dat_cua_so`); không
  suy luận price/velocity khi coverage dưới ngưỡng đã công bố (MODEL_CHARTER §7, TASKS T05/T07).

## Metric ĐÃ CÓ trong code (thuần quan sát, lớp 5 — không điều khiển engine)

| metric (key) | định nghĩa | đơn vị | nguồn code |
|---|---|---|---|
| `food_security` | tồn thóc hộ / nhu cầu thóc hộ một tick | ratio | economy.py `household_snapshot` |
| `ty_le_ho_thieu_an` | tỷ lệ hộ có food_security < 1.0 | ratio | metrics.py |
| `so_ho` | số hộ sống không trùng lặp | count | economy.py `households` |
| `thoc_ho_trung_vi` | tồn thóc hộ trung vị | kg | metrics.py |
| `gini_thoc` / `gini_thoc_ho` | Gini của cải (thóc) cá nhân / hộ | index 0–1 | metrics.py |
| `gini_dat` | Gini sở hữu đất | index 0–1 | metrics.py |
| `gini_thu_nhap` | Gini thu nhập (dòng chảy, cửa sổ 4 tick) | index 0–1 | metrics.py |
| `gdp` | GDP thực (value-added), quy thóc | kg-thóc quy đổi | metrics.py `gdp_thuc` |
| `velocity` | P·Q / M(xu); =0 khi chưa có xu | ratio | metrics.py `velocity_tien` |
| `ty_le_phi_ly` | tỷ lệ giao dịch lệch >kσ mặt bằng lịch sử | ratio | metrics.py `ty_le_phi_ly` |
| `gia_dat_tren_san_luong_ky_vong` | giá đất / sản lượng ròng kỳ vọng (khi có giao dịch) | ratio | economy.py `land_price_productivity` |
| `so_gd_dat_cua_so` | số giao dịch đất trong cửa sổ (coverage) | count | economy.py |

Lưu ý: `gini_thoc` là bất bình đẳng **của cải** (thóc làm proxy), `gini_thu_nhap` là bất
bình đẳng **thu nhập** — hai khái niệm tách biệt, không hoán đổi. **Consumption Gini** riêng
CHƯA có (food_security là tỷ số an ninh lương thực cấp hộ, không phải Gini tiêu dùng).

## Metric PENDING (design intent — CHƯA đo được, không được tuyên bố đã có)

| metric | lớp | task cài | ghi chú |
|---|---|---|---|
| `marketed_surplus` (thặng dư đưa ra chợ / thương phẩm hóa) | L2 | T04/T05 | tách sản lượng tự tiêu vs bán |
| `consumption_gini` | L1/L2 | T04 | Gini tiêu dùng tách khỏi của cải/thu nhập |
| `poverty_duration`, `mobility`, `liquidity` | L1 | T04 | thời lượng nghèo, dịch chuyển, thanh khoản |
| `debt_service`, `arrears`, `default_rate`, `claims_concentration`, `secured_share` | L3 | T06 | từ `Claim` registry, mỗi flow có đối ứng |
| `monetary_share` (theo value/volume), `acceptance_breadth`, `payment_concentration`, `barter_share`, `credit_share`, `failed_settlement` | L4 | T07 | adoption đo theo chợ–thời gian–mạng, không theo một ngưỡng |
| `tax_compliance`, `fiscal_balance`, `public_return`, `public_good_stock`, `collection_cost` | L5 | T08 | treasury balance sheet đóng; public good có depreciation |

Các kết quả từ scenario này chỉ kiểm chứng cơ chế nội bộ (`mechanism_result`); chúng KHÔNG
phải dự báo ngoài mẫu và không được gọi là empirical/calibrated/validated.
