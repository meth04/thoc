# E1 — So sánh bộ ra quyết định (decision-maker), cục bộ, không mạng

Ngày: 2026-07-13. Scenario `agrarian_transition_v1`, horizon 100 tick (50 năm), paired seed
{41,42,43}, rulebot mode + `--policy`. Deterministic, không LLM/mạng. Claim tier: **mechanism_result**
(n=3, không suy rộng). Nguồn: `data/runs/e1_<policy>_s<seed>/`.

## Kết quả (trung vị [dải seed])

| policy | dân số | gini_dat | hợp đồng hiệu lực | mô-típ hợp đồng | biết chữ |
|---|---:|---:|---:|---:|---:|
| **rulebot** (contract-aware) | 235 [185,235,254] | 0.73 | **337** [291,337,398] | 7 | 93% |
| feasible_random | 12 [7,12,16] | 0.03 | **0** [0,0,0] | 0 | 14% |
| subsistence | 15 [12,15,18] | 0.00 | **0** [0,0,0] | 0 | 17% |
| adaptive | 15 [12,15,18] | 0.00 | **0** [0,0,0] | 0 | 17% |

## Diễn giải (khoa học, không overclaim)

- Toàn bộ "định chế tự phát" (hợp đồng, bất bình đẳng đất, tích lũy, biết chữ cao) **CHỈ** xuất hiện
  dưới `rulebot` — heuristic được lập trình tường minh với 8 công thức hợp đồng. Ba policy đơn giản
  (feasible_random/subsistence/adaptive) tạo **0 hợp đồng, 0 mô-típ**, dân số gần sụp (12–15), gini≈0.
- Kết hợp pilot `real50` (LLM thật cũng ~0 hợp đồng, dân co 50→21) → **LLM thật hành xử GẦN các
  baseline đơn giản HƠN là rulebot contract-aware.**
- **Luận điểm cốt lõi (bằng chứng cục bộ mạnh):** "sự phong phú định chế" của THÓC là HÀM CỦA bộ ra
  quyết định, KHÔNG phải thuộc tính của môi trường. Một ABM có hạch toán + replay cho phép ĐO điều
  này có kiểm soát (paired-seed, tất định). → cảnh báo phương pháp: tuyên bố "định chế tự phát" trong
  LLM-ABM phụ thuộc mạnh lớp hành vi.

## Giới hạn
n=3, một scenario, một horizon; rulebot cố tình biết công thức hợp đồng nên "thắng" là kỳ vọng —
điểm mấu chốt là ĐỘ LỚN khoảng cách (337 vs 0) và việc real LLM rơi về phía baseline. Cần ≥30 seed +
đa-model real (PENDING_COMPUTE) để có CI + suy rộng. Micro-task benchmark (E2) sẽ đo constraint-
following/regret có ground-truth để bổ sung cho so sánh vĩ mô này.
