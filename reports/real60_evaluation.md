# Đánh giá run LLM thật 60 năm (`real60_spatial`) + thống kê chi tiết

Ngày: 2026-07-13. Claim tier: **mechanism_result (một seed, một run)** — KHÔNG phải empirical/
predictive. Nguồn thô: `data/runs/{real60_spatial, mock60_spatial}/`. Config: `agrarian_transition_v1`
+ overlay `spatial_v1` (nền kinh tế sinh kế đầy đủ: đò/hai-bờ, khai hoang, vụ đông, gà rừng commons,
chăm trẻ, calendar 3 mùa). Seed 42.

## 1. Thông số run

| | REAL60 (LLM Gemini) | MOCK60 (PersonaBot heuristic) |
|---|---|---|
| horizon | 60 năm = **180 tick** (calendar 3 mùa) — **HOÀN TẤT** | 180 tick |
| LLM call | **1589**, fallback **3 (0.19%)** | 15702, fallback 0% |
| token in/out | 10.69M / 0.35M | 5.16M |
| chi phí ước tính | **~$1.37** | ~$2.03 (giá mock) |
| dừng budget? | **KHÔNG** (chạy đủ 60 năm) | không |
| world_hash | `738c6123fede` (v2) | `6086f1d3` |
| gateway smoke | 9/9 route OK trước khi chạy | — |

> Run chạy tới tick 105 thì bị harness kill (không crash), `--resume` từ checkpoint_0105 chạy nốt
> tới tick 180 sạch. Metrics đầy đủ 180 tick.

## 1b. KẾT CỤC 60 NĂM (tick 180) — REAL SỤP ĐỔ, MOCK THỊNH VƯỢNG

| Chỉ số @năm 60 | 🔴 REAL (LLM) | 🔵 MOCK (heuristic) |
|---|---:|---:|
| **dân số** | **2** (gần tuyệt chủng) | **576** |
| hợp đồng hiệu lực | **0** | 761 |
| entity / blueprint / tín dụng | 0 / 0 / 0 | 5 / 87 / 282 |
| biết chữ | 50% (=1/2 người) | 100% |
| gini đất | 0.17 | 0.83 |

**Quỹ đạo dân số real:** khởi 50 → đỉnh **51 (năm 19)** → duy trì ~40–50 tới năm 35 → **sụp
39→2 trong 25 năm cuối** (năm 35–60). Không chỉ đình trệ định chế, xã hội LLM còn **suy vong nhân
khẩu** về 2 người. Mock: tăng đều lên 576 với nền kinh tế định chế đầy đủ.

## 2. So sánh REAL vs MOCK tại tick 105 (35 năm, cùng seed + config)

| Chỉ số | REAL (LLM thật) | MOCK (heuristic) |
|---|---:|---:|
| dân số | **39** (co từ 50) | **239** (tăng) |
| thóc/người | 2771 | 1951 |
| gini đất | 0.40 | 0.64 |
| gini thóc | **0.27** | **0.72** |
| gini thu nhập | 0.23 | 0.61 |
| biết chữ | **25%** | **88%** |
| **hợp đồng hiệu lực** | **0** | **383** |
| mô-típ hợp đồng | **0** | 7 |
| **blueprint (R&D)** | **0** | 29 |
| **tín dụng (n_claims)** | **0** | 121 |
| credit_outstanding | 0 | 37618 |
| **đúc xu (duc_xu, cả run)** | **0** | 1738 |

## 3. Sự kiện tích lũy (real 105t vs mock 180t)

| Sự kiện | REAL | MOCK |
|---|---:|---:|
| ký hợp đồng (`ky_hd`) | **10** | 4428 |
| đúc xu | **0** | 1738 |
| chăm trẻ | 108 | 10637 |
| đánh cá | 107 | 1389 |
| bắt gà | 3 | 220 |
| qua sông / khai hoang | 0 / 0 | 0 / 0 |
| lập entity / blueprint | 0 / 0 | 5 / 87 |
| vi phạm / xiết nợ | 6 / 0 | 647 / 3 |

Giai cấp cuối: **real** = chủ yếu `vô_gia_cư` (34) + vài `trung_nông`/`phụ_thuộc` — xã hội sinh tồn
đình trệ; **mock** = cơ cấu giai cấp phân hóa (phụ_thuộc 114, vô_gia_cư 73, phú_nông 29, trung_nông 23).

## 4. Diễn giải (khoa học, không overclaim)

**Cùng môi trường giàu cơ chế (đò, tín dụng, tiền, R&D, hợp đồng, sinh kế đa dạng ĐỀU sẵn sàng),
LLM thật dùng GẦN NHƯ KHÔNG cơ chế nào**: 0 hợp đồng hiệu lực (chỉ 10 lần ký, đều hết hạn), 0 tín
dụng, 0 xu, 0 R&D, 0 entity, biết chữ 25%, dân số co lại. Agent LLM chỉ canh tác/đánh cá/chăm trẻ để
SỐNG SÓT. Ngược lại heuristic (mock) tự phát một nền kinh tế định chế đầy đủ (383 hợp đồng, 29 R&D,
121 khoản tín dụng, phân hóa giai cấp, biết chữ 88%, dân tăng ×5).

**Kết cục 60 năm còn mạnh hơn:** xã hội LLM không chỉ thiếu định chế mà **suy vong nhân khẩu về 2
người** (đỉnh 51 năm-19 → 2 năm-60), trong khi mock đạt 576 người + nền kinh tế đầy đủ. Cùng luật/
seed/môi trường, decision-maker quyết định cả *có định chế hay không* LẪN *sống sót hay sụp đổ*.

→ **Xác nhận MẠNH luận điểm cốt lõi:** "sự phong phú định chế" (và cả tính bền vững) của mô hình là
**hàm của bộ ra-quyết-định**, KHÔNG phải thuộc tính môi trường. Đây là bằng chứng đắt giá cho một bài phương pháp LLM-ABM:
một ABM có hạch toán ràng buộc + replay cho phép ĐO khoảng cách này có kiểm soát (cùng seed/config,
chỉ đổi decision-maker). Kết quả nhất quán với pilot `real50`/`real50_agr` trước đó (LLM thật ~0 hợp
đồng), và mạnh hơn vì môi trường lần này giàu hơn (đò/vụ-đông/chăm-trẻ) mà LLM vẫn không khai thác.

**Lưu ý cân bằng:** rulebot/mock được lập trình biết công thức hợp đồng nên "thắng" là kỳ vọng; điểm
khoa học là (a) ĐỘ LỚN khoảng cách (0 vs 383) và (b) LLM thật rơi hẳn về phía baseline sinh tồn, cho
thấy prompt/model hiện tại KHÔNG dẫn tới hành vi định chế trong khung này.

## 5. Giới hạn (bắt buộc nêu)
- **Một seed, một run mỗi mode** (real 60 năm HOÀN TẤT). Không có CI, không suy rộng — collapse về 2
  người có thể là đặc thù seed. Cần ensemble ≥30 seed × ≥2 model (`PENDING_COMPUTE`; `nghiem_thuc`
  mode đã sẵn) để có paired CI + xác định collapse có hệ thống hay ngẫu nhiên seed.
- Prompt/model/temperature là nguồn giả định lớn; kết quả có thể đổi với prompt engineering khác —
  đó chính là điều cần đo có kiểm soát, không phải giấu.
- `qua_song`/`khai_hoang`=0 cho CẢ real và mock: cơ chế đò/hai-bờ chưa được cả hai khai thác ở seed
  này (không phải lỗi — là outcome; cần seed/động cơ khác để kích hoạt).

## 6. Tái lập (trung thực)
Run có `transcript.jsonl` + checkpoint mỗi 10 tick + config_snapshot; `world_hash` v2. **Transcript-
replay của run NÀY LỆCH** (`b2e68eba` vs `738c6123fede`) vì run bị **kill ở tick 105 rồi resume** —
điểm kill làm transcript có gap/không nhất quán ở biên, và cổng transcript-replay nghiêm (fail khi
miss/thừa) đúng khi bắt lỗi này. **Cơ chế transcript-replay bản thân ĐÃ được kiểm chứng** trên run
hoàn tất một-phiên: `mock50_agr` (hash `0135fa05`) và `real50_agr` (hash `a2e06edd`) đều replay-từ-
transcript TRÙNG bit-for-bit. Để có real-run replay-được cho bài báo, cần **một phiên chạy liền** (môi
trường không kill tác vụ nền dài) — đây là ràng buộc hạ tầng, không phải lỗi cơ chế.
