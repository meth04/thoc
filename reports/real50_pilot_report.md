# Pilot report — `real50` (LLM thật 50 năm) vs `mock50`

Ngày: 2026-07-12. Claim tier: **mechanism_result (một seed, một run)** — KHÔNG phải empirical/
predictive/causal. Đây là pilot LLM thật theo yêu cầu chủ dự án, KHÔNG phải bằng chứng về nền
kinh tế thật (charter §2). Nguồn thô: `data/runs/{real50,mock50}/`.

## 1. Tham số run

| | mock50 | real50 |
|---|---|---|
| mode | mock (PersonaBot) | **real (Gemini, 15 aistudio key + 9router)** |
| seed / horizon | 42 / 100 tick (50 năm) | 42 / 100 tick (50 năm) |
| config | default `world.yaml` | default `world.yaml` |
| thời gian | 25.0s | 2443.8s (~41 phút) |
| call / fallback | 4272 / **0.00%** | 1347 / **0.00%** |
| token in/out | 1.23M | 8.90M / 0.35M |
| chi phí ước tính | ~$0.48 (mock giá) | **~$1.03** |
| dừng vì budget? | không | **không (chạy đủ 100 tick)** |
| world-hash | 3005ea50ce20 | 9bada012e965 |

Gate mock-trước-real: mock50 audit xanh + replay TRÙNG hash + fallback 0% → ĐẠT trước khi chạy
real. Real gateway smoke 9 route OK trước run. verify_research_run(real50): ĐỦ BẰNG CHỨNG (manifest/
meta/outcome-hash/metrics contiguous; replay SKIP vì real cần transcript).

## 2. Kết quả real50 (mechanism_result)

Xã hội **KHÔNG phát triển**: dân số **co lại 50 → 21** trong 50 năm (không tuyệt chủng); KHÔNG
công nghiệp hóa, KHÔNG pháp nhân/entity, KHÔNG blueprint, KHÔNG chính quyền (trưởng làng None,
thuế 0), KHÔNG bạo động. Giai cấp cuối: 12 vô-gia-cư / 8 trung-nông / 1 phụ-thuộc. Tín dụng/tiền:
`credit_outstanding=0`, `n_claims=0`, `monetary_share=0` (kinh tế đổi chác thuần). Phân phối:
`income_gini=0.44`, `consumption_gini=0.12`, `gini_dat=0.18`.

**Đây là một kết quả hợp lệ** (charter/REVIEW: không phải seed nào cũng phát triển; đình trệ/co
lại là mechanism_result hợp lệ, phải báo — không giấu). Một seed KHÔNG suy rộng được.

## 3. Phát hiện then chốt: real ≠ mock (divergence mạnh)

| chỉ số @tick100 | mock50 | real50 | ghi chú |
|---|---:|---:|---|
| dân số | 203 (tăng) | 21 (co) | quỹ đạo NGƯỢC nhau |
| hợp đồng hiệu lực | 271 | **0** | real gần như KHÔNG ký hợp đồng |
| mô-típ hợp đồng | 7 | **0** | không hình thành định chế hợp đồng |
| khối lượng giao dịch | 2261 | 108 | real gần như không giao thương |
| biết chữ | 84% | 38% | real đầu tư học ít hơn |
| gini đất | 0.73 | 0.18 | mock phân hóa; real san bằng (do co dân) |
| gini thóc | 0.75 | 0.28 | tương tự |

**Diễn giải (khoa học, không overclaim):** PersonaBot (mock) tự phát sinh một nền kinh tế hợp đồng
phong phú (271 hợp đồng, 7 mô-típ, giao thương cao, dân số tăng, bất bình đẳng + biết chữ tăng);
LLM thật ở cùng seed/luật lại **gần như không ký hợp đồng, ít giao thương, dân số co lại**. Điều
này **xác nhận trực tiếp luận điểm cốt lõi của `REVIEW.md`/charter**: mock KHÔNG phải proxy tốt cho
hành vi LLM thật; **kết luận cơ chế KHÔNG được phụ thuộc mock**, và LLM là một *treatment* có sai số
riêng, không phải "sự thật" hành vi. "Định chế tự phát" quan sát trong mock có thể là hiện vật của
PersonaBot heuristic, không tái lập dưới LLM thật ở seed này.

## 4. Giới hạn (bắt buộc nêu)

- **Một seed, một run mỗi mode** — KHÔNG có khoảng bất định. Không suy rộng. Cần ensemble ≥30 seed
  (PENDING_COMPUTE) + nhiều model/provider để có bất kỳ claim nào.
- Real 50 năm ≠ 300 năm; horizon ngắn, ít thời gian cho định chế hình thành.
- Prompt/model version/temperature là nguồn giả định lớn (charter §7); real không replay được nếu
  không có transcript (chỉ có world-hash + llm_calls log của run này).
- `luot_cong_cu=0`: agent không dùng world-tool trong run này (trả lời trực tiếp) — một đặc điểm
  hành vi của model/prompt, cần ghi nhận khi diễn giải.
- KHÔNG phải bằng chứng empirical/causal/predictive. Chỉ là pilot kỹ thuật cho thấy pipeline real
  chạy sạch (fallback 0%) + divergence real-vs-mock đáng chú ý để nghiên cứu tiếp.

## 5. Artifact tái lập
- `data/runs/real50/` (events, metrics, checkpoints, llm_calls.sqlite, manifest, reports/).
- `data/runs/real50/reports/final_analysis.md` + PNG (isolated).
- `data/runs/mock50/reports/compare_real50.md` (bảng so sánh đầy đủ).
- Lệnh: mock `run.py --mode mock --years 50 --seed 42 --fast --run-name mock50`; real
  `run.py --mode real --years 50 --seed 42 --i-am-sure --until-budget --run-name real50`.
