# Data contract — `agrarian_transition_v1`

Trạng thái: **CHƯA có dữ liệu thực chứng.** Scenario này là `mechanism_benchmark`. Tài liệu này
là *hợp đồng nhập liệu* cho tương lai: khi (và chỉ khi) có dữ liệu thật có nguồn, quy trình dưới
đây biến nó thành parameter/target versioned. KHÔNG tải dữ liệu qua mạng trong phiên hiện tại;
KHÔNG bịa nguồn/DOI/target (charter §2, ADR 0001 §Compliance).

## 1. Nguyên tắc (REVIEW §5.1–5.2, §7)

1. **Đóng băng thiết kế trước khi xem kết quả**: chọn scope + data → chọn moment in-sample →
   khóa tham số/code/seed → chạy nhiều seed → chấm trên holdout chưa dùng để fit.
2. **Raw bất biến**: file gốc để nguyên trong `data/raw/<source_id>/`, không sửa tay.
3. **Conversion có version + test**: mọi biến đổi raw → config/target nằm trong
   `data/processed/` sinh bởi script versioned trong `tools/ingest/` kèm test; KHÔNG chép số
   vào YAML bằng tay.
4. **Provenance bắt buộc**: mỗi số đưa vào `parameters.yaml`/`targets_*` phải có dòng
   `provenance.csv` với `source` THẬT (URL/DOI/citation + ngày truy xuất) và `status ≠
   design_assumption`. Gate `tools/validation.py` từ chối nhãn empirical khi thiếu (T01/T03).

## 2. Bộ dữ liệu tối thiểu để chuyển sang tầng thực chứng (REVIEW §5.2)

| Nhóm | Trường cần | Đơn vị | Dùng cho |
|---|---|---|---|
| Nhân khẩu | dân số, cơ cấu tuổi, sinh, tử, quy mô hộ | người, tỷ lệ/năm | hiệu chuẩn vòng đời/lao động |
| Nông nghiệp | diện tích canh, năng suất, mùa vụ, giá đầu vào | ha, kg/ha, kg | sản xuất & cung lương thực |
| Giá | thóc/gạo, gỗ, gia súc, tiền công, tô đất | đơn vị tiền/kg, /ngày công | thị trường & giá tương đối |
| Tài sản | quy mô đất, nhà, công cụ, nợ | ha, đơn vị, đơn vị tiền | phân phối & tích lũy |
| Thể chế | thuế, tô, luật thừa kế, quyền đất | tỷ lệ, quy tắc | scenario & policy |
| Địa lý | đất, sông, đường, khoảng cách chợ | m, km | năng suất & ma sát thương mại |
| Cú sốc | mưa/lũ/hạn, dịch bệnh, giá ngoại thương | chỉ số/năm | kiểm định phản ứng động |

## 3. Schema hợp đồng cho một nguồn (`data/raw/<source_id>/manifest.yaml`)

```yaml
source_id: <slug>            # định danh nguồn
title: <tên bộ dữ liệu>
provider: <cơ quan/tác giả>
citation: <trích dẫn đầy đủ>
doi_or_url: <DOI hoặc URL>   # BẮT BUỘC — không có thì không được dùng làm target
license: <giấy phép>
retrieved_utc: <ngày truy xuất>
files: [<file>, ...]         # sha256 ghi kèm khi ingest
unit_notes: <đơn vị & quy ước>
geography: <địa bàn thật>    # nếu nguồn gắn địa danh → scenario PHẢI đổi scope tương ứng
period: <niên đại>
```

## 4. Pipeline chuyển đổi (khi có data)

```
data/raw/<source_id>/           # bất biến + manifest.yaml + sha256
        │  tools/ingest/<source_id>.py   (versioned, có test trong tests/ingest/)
        ▼
data/processed/<source_id>/     # bảng chuẩn hóa đơn vị + provenance mỗi cột
        │  tools/ingest/to_scenario.py
        ▼
scenarios/agrarian_transition_v1/
    parameters.yaml (calibrated)     ← chỉ tham số in-sample
    targets_in_sample.yaml           ← moment để fit (khóa trước khi xem holdout)
    targets_holdout.yaml             ← moment KHÔNG dùng để fit
    provenance.csv                   ← source THẬT + status calibrated/validated
```

## 5. Tách in-sample / holdout (REVIEW §5.4) — kỹ thuật, phải enforce bằng test

- Chia theo THỜI GIAN (fit sớm, holdout muộn) và/hoặc theo LOẠI moment.
- `targets_in_sample.yaml` và `targets_holdout.yaml` KHÔNG được chia sẻ cùng một target id.
- Khi có data: thêm test `tests/ingest/test_split_disjoint.py` khẳng định hai tập rời nhau và
  holdout không xuất hiện trong loss hiệu chuẩn.

## 6. Điều kiện nâng `validation_tier`

- `mechanism_benchmark` → `calibrated`: có ≥1 moment in-sample có source thật + provenance
  status `calibrated` + fit report tái lập.
- `calibrated` → `validated`: ≥5 moment holdout dự báo trong khoảng bất định đã đăng ký trước
  (REVIEW §10). Gate `tools/validation.py` phải xanh cho tier tương ứng.

Cho tới khi các điều kiện này có bằng chứng, scenario giữ `mechanism_benchmark`.
