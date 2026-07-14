# FIX ENGINE — chương trình sửa chữa sau `real30_v2`

Ngày mở: 2026-07-14  
Trạng thái: **execution authority** cho đợt sửa lỗi này.  
Nguồn chẩn đoán: `data/runs/real30_v2/`, `Report_v2.md`, `docs/MODEL_CHARTER.md` và
phân tích artifact ngày 2026-07-14.

## 0. Mục tiêu và ranh giới claim

Mục tiêu là tạo một phiên bản scenario mới, tạm gọi `spatial_livelihood_v3`, trong đó:

1. mọi lựa chọn LLM nhìn thấy đều có tập tham số khả thi, kết quả thực thi và phản hồi có thể
   kiểm tra;
2. LLM, policy card, survival floor và fallback được phân biệt trong ledger/metrics, không thể
   gộp thành một claim "LLM đã làm";
3. đất công, khai hoang, dự án, nhà, đò, chợ, sinh thái, hộ và nhân khẩu học cùng tuân theo
   cùng một config đang chạy;
4. tài nguyên/cây trồng/nhà ở tạo trade-off vật lý thật nhưng không ép nghề, tiền tệ, chính
   phủ hay một kết cục phát triển; và
5. mock/replay/audit có thể chứng minh interface và invariants, không biến một run hay mock
   thành validation lịch sử.

`real30_v2` là artifact lịch sử `replay_verified`; tuyệt đối không sửa, retcon hay dùng nó như
bằng chứng hành vi sau khi code đổi. `spatial_v1.yaml` và `spatial_livelihood_v2.yaml` được giữ
nguyên để bảo toàn replay; thay đổi hành vi mới phải đi qua overlay versioned v3.

Không chạy provider/API/LLM thật, mode `real`, smoke, web hay remote MCP trong chương trình này.
Mọi Python command chạy bằng `conda run -n thoc-env python ...` với `THOC_BLOCK_NETWORK=1`.

## 1. Findings phải đóng

| ID | Finding từ `real30_v2` | Mức | Tiêu chí đóng |
|---|---|---|---|
| F01 | Policy card dùng `180` công khi config spatial dùng `120`; 83.35% agent-tick đi qua policy thay vì LLM mới. | BLOCKER | Không magic number; policy lấy công/chi phí từ active `World.cfg`; metric phân tách LLM/policy/floor/fallback. |
| F02 | 725 intent `khai_hoang` đều nhắm ruộng, trong khi engine chỉ cho rừng/đồi; phần lớn bị bỏ im lặng. | BLOCKER | Fact card phân biệt ruộng công để canh với rừng/đồi để khai hoang; mỗi reject có event/result code. |
| F03 | Project IDs bị LLM bịa; 0/26 góp công và chỉ 1/29 góp vật liệu tham chiếu project còn mở. | BLOCKER | Project ID chỉ đến từ world state; open project card/enum; create→outcome→contribute path được test end-to-end. |
| F04 | Prompt policy template bị copy đồng loạt; policy tự động sinh nhiều hành vi chợ. | MAJOR | Policy patch là delta, không mớm default; origin của mỗi intent/flow được quan sát và ablate được. |
| F05 | Nhà, đò, A2A, quote settlement, bờ hoang, gà nuôi không kích hoạt; tool config bật nhưng 0 tool use. | MAJOR | Opaque/local opportunities có fact card deterministic; tool transcript đầy đủ; fixture chứng minh mỗi path có thể được khám phá/thực thi. |
| F06 | Khoai strict-dominates ngô; food/forest/cá quá dư nên không có trade-off. | MAJOR | V3 config có trade-off công khai, không crop nào strict-dominates trên mọi state; resource pressure/recovery có test. |
| F07 | Không nhà 30 năm nhưng health gần 100; shelter không phải ràng buộc kinh tế hữu hiệu. | MAJOR | Shelter effect tích lũy/không bị xóa ngay bởi một bữa no; test housing changes health/productivity risk theo config. |
| F08 | 11 người chết ở tuổi 23.8–56.5 đều mang nhãn `tuoi_gia`. | MAJOR | Cause label phân biệt mortality nền và tuổi già; period-life output không diễn giải quá dữ liệu. |
| F09 | Chợ khớp gỗ trung tâm/pro-rata, không phải A2A; session snapshot che mất cumulative flow. | MAJOR | Report metrics tách tick-flow/cumulative, direct market/quote/A2A, planned/executed/failed. |
| F10 | `kg thóc` được công bố là unit value từ tick 0 và chợ/hợp đồng đã có sẵn. | CLAIM BLOCKER | Prompt/metrics gọi đây là accounting/food unit, không phải tiền; report cấm claim money/market emergence nếu institution đã được cấp sẵn. |

## 2. Thứ tự thực thi và commit checkpoints

### C0 — Kế hoạch và baseline

- Ghi file này, chụp `git status`, giữ nguyên thay đổi không thuộc phạm vi.
- Chạy baseline targeted tests offline trước code.
- **Commit:** `docs: add real30_v2 engine remediation plan`.

### C1 — Parity và provenance của behavioral layer

- Thay hard-code labor/food/recipe trong `minds/policy_cards.py` bằng active config.
- Tạo `decision_origin`/telemetry tách `llm`, `policy_card`, `survival_floor`, `fallback`,
  `translator` cho plan/action outcome; không thay đổi ledger ownership.
- Policy patch chỉ ghi delta rõ ràng; prompt không in một object default dễ bị copy như lựa chọn
  bắt buộc.
- Bổ sung config/policy parity tests cho base và spatial 120 công.
- **Commit:** `fix: align policy cards with active scenario config`.

### C2 — Feasibility catalog và action-result journal

- Tạo fact cards riêng cho: ruộng công có thể canh, rừng/đồi có thể khai hoang, parcel bờ hoang
  cần đò, project/quote/estate visible, và action parameters đúng quyền của agent.
- Mọi action đã parse đi qua preflight/result path: `ok|rejected`, stable reason code, intent id,
  action, target; result được journal và đưa vào ký ức/fact card tick sau.
- Không còn silent `continue` cho malformed/unavailable user/LLM intent; legacy/off behavior
  được giữ dưới flag/versioned overlay.
- **Commit:** `fix: expose feasible actions and journal action outcomes`.

### C3 — Project, quote và A2A coordination

- Project create tạo ID engine-owned; ID được render từ open local projects và không có trong
  cùng atomic action as create+contribute.
- Có state machine dự án: create → factual result → escrow material/labor → progress → complete/
  cancel/expiry. Test contributor, owner death, invalid/stale ref and exact-once refund.
- Quote/A2A có state settlement riêng; free chat không settlement. Local world tools, nếu được
  dùng, phải transcript từng call/result (không chỉ final response).
- **Commit:** `fix: make projects and local settlement executable by agents`.

### C4 — V3 economics, ecology, shelter và demography

- Tạo `spatial_livelihood_v3.yaml`, không sửa v1/v2. Mọi số mới ghi `design_assumption` và unit.
- Đưa land/resource/crop/shelter constraints về scenario config. Crop choice cần ít nhất một
  trade-off state-dependent mà không thêm water/seed genetics/nutrients vi mô.
- Shelter penalty có đường nhân quả bền vững qua health/productivity/risk, không bị erase ngay
  bởi full meal; test on/off và config parity.
- Mortality nền có cause riêng; `tuoi_gia` chỉ sau threshold config. Initial condition/hộ được
  versioned và metrics báo age-at-death đầy đủ, không gọi survivor age là life expectancy.
- Rừng/cá/gà có recovery pressure và ablation logging/clearing/reforestation.
- **Commit:** `feat: add v3 livelihood tradeoffs and honest demography`.

### C5 — Metrics, regression và evidence

- Metrics/report phân biệt last-tick versus cumulative, intent versus execution, direct market
  versus quote/A2A, origin, tool use and reason-code funnel.
- Ghi ADR/DECISIONS cho thay đổi state ownership/law. Tạo review evidence factual, không nắn
  claim.
- Chạy full offline suite, ruff, verify_local, deterministic v3 mock/replay/audit probes.
- **Commit:** `test: verify v3 engine remediation end to end`.
- **Hoàn tất 2026-07-14:** `ruff check .` xanh; toàn bộ suite đã chạy theo các nhóm dưới giới
  hạn terminal: **636 passed, 1 skipped** (`cnq2` không có integration artifact). Scenario
  validation vẫn gắn nhãn `mechanism_benchmark`; smoke rulebot 20 tick seed 41 tái lập hash
  `9f332a3f3977…` và `verify_research_run` trả `replay_verified`. Lệnh gộp
  `tools.verify_local` vượt giới hạn 64 giây của terminal, nên từng bước tương đương của nó đã
  được chạy riêng, cùng môi trường offline.

## 3. Acceptance matrix

| Area | Must pass before DONE |
|---|---|
| Config parity | Spatial prompt/policy/action preflight all use 4 months, 60kg, 120 labor, active recipes. |
| Land | A real forest/doi card can clear; a common ruong card can cultivate/homestead; wrong action emits reason code. |
| Project | No fictitious ID can mutate state; real ID from prior result can fund, add labor and complete house/boat over ticks. |
| Autonomy | Every result says origin; policy defaults are not silently copied; local tool calls replay with transcript. |
| Economy | Crop trade-off tests choose different feasible crop under different factual states; no hard-coded job/outcome. |
| Ecology | Controlled logging lowers biomass/canopy/K/catch; recovery/reforestation reverse it; no over-extraction. |
| Shelter/demography | Homeless full-fed case differs from housed case according to config; young background death never labeled old age. |
| Artifact | Legacy v1/v2 hashes/tests remain intact; new v3 mock run replay/audit passes; reports mark claim tier correctly. |

## 4. Verification commands

```powershell
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m pytest -q --basetemp .tmp\pytest
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m ruff check .
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m tools.verify_local
```

No real LLM run is part of acceptance. A future real pilot requires a new user-authorized
budget and must be labelled `mechanism interface pilot`, not empirical validation.
