# Hiệu chỉnh công nghiệp hóa (mock 300 năm, p_malformed=0.15, seeds 41–45)

Cấu hình chốt: `research.yaml` k0=160, máy {go 8, kim loại 6, công 200}, blueprint
máy móc ×3.0 (trần 2.0); `world.yaml` ty_le_ruong 0.28, p_goc 0.15, ngưỡng lao động
trong entity ≥5 người = 10% (căn cứ lịch sử — DECISIONS.md).

| seed | năm đạt nhãn CNH | dân cuối | máy | entity | phi nông cuối |
|---|---|---|---|---|---|
| 41 | 146 | 286 | 52 | 24 | 32% |
| 42 | 160 | 355 | 45 | 18 | 42% |
| 43 | — (không đạt trong 300 năm) | 376 | 54 | 31 | 45% |
| 44 | 171 | 293 | 24 | 20 | 36% |
| 45 | — (không đạt trong 300 năm) | 335 | 19 | 26 | 37% |

**Seed trung vị đạt nhãn năm 171 → ĐẠT mục tiêu [160, 280] ✅**

Hai seed không đạt nhãn trong 300 năm là kết quả hợp lệ (SPEC quyết định #10:
công nghiệp hóa là kết quả mong đợi, không bảo đảm).

## Phân bố mô-típ hợp đồng (tổng số lượt ký, 5 seed)

- `chuyen_giao_dinh_ky+dieu_kien_su_kien`: 10594
- `chuyen_giao_dinh_ky+quyen_su_dung`: 9187
- `chuyen_giao_mot_lan+hoan_tra_theo_yeu_cau`: 4389
- `chuyen_giao_dinh_ky+chuyen_giao_mot_lan+gop_cong`: 2292
- `chia_san_luong+quyen_su_dung`: 1968
- `chuyen_giao_dinh_ky+gop_cong`: 1416
- `chuyen_giao_dinh_ky+chuyen_giao_mot_lan`: 806
- `chuyen_giao_mot_lan+chuyen_giao_mot_lan`: 230
- `chuyen_giao_mot_lan+chuyen_giao_mot_lan+khi_pha_vo`: 213
- `dieu_kien_su_kien`: 8
- `hoan_tra_theo_yeu_cau`: 3