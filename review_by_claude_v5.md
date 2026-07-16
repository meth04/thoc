# Review độc lập run `real15_v5` và lộ trình nâng THÓC lên chuẩn công bố quốc tế

**Ngày:** 2026-07-15 · **Người review:** Claude (4 agent độc lập: project-map, sim-economist, reality-auditor, adversarial-reviewer)
**Đối tượng:** run `data/runs/real15_v5` (mode real, seed 59, 45 tick = 15 năm, scenario `agrarian_transition_v1`, git `967e0f5`, ~$2.30, 1.936 call LLM)
**Tài liệu khung tham chiếu:** `docs/MODEL_CHARTER.md`, `docs/adr/0001`, `docs/adr/0008`, `reports/reality_check_real30_v3.md`, `reports/reality_check_real15_v4_paced.md`

---

## 0. Kết luận điều hành (TL;DR)

1. **v5 giải được bài toán sống còn** mà v4 thất bại: v4 tuyệt chủng tick 21 vì deadlock nhà ở–quyền đất; v5 sống trọn 45 tick, 49 nhà, `vo_gia_cu=0`, thóc 4.580 kg/người, health trung bình 100.
2. **Nhưng toàn bộ kinh tế bậc cao bằng 0** — 0 giao dịch chợ khớp, 0 đất tư hữu, 0 hợp đồng hiệu lực, 0 entity/máy/blueprint, 0 milestone — và **ít nhất 3 nguyên nhân thiết kế đủ để khóa kết quả này bất kể agent thông minh đến đâu** (Finding A1, A2, A3) cộng 1 bug kỹ thuật P0 (B1).
3. **Tầng báo cáo đang in con số gây hiểu lầm**: "fallback 0.05%" là fallback cấp call; thực tế **167/2.099 agent-tick (~8%) quyết định bằng rulebot/policy card**, có tick quá nửa làng chạy bằng thẻ. Run cũng chạy **trước khi thỏa gate do chính báo cáo v4 đặt ra**.
4. **Dữ liệu thô nhất quán nội bộ, không có số ngụy tạo** — vấn đề nằm ở pipeline report và thiết kế môi trường, không phải ở tính toàn vẹn dữ liệu.
5. **Ranh giới diễn giải bắt buộc:** run này KHÔNG được đọc là "LLM không tự phát sinh định chế". Claim hợp lệ duy nhất: *mechanism result trên 1 seed, trong chế độ dư thừa tài nguyên + shelter floor luôn-bật, với ~8% quyết định là rulebot*. Chỉ dùng làm **diagnostic run**.

---

## 1. Bối cảnh: run này là gì và đã đạt gì

### 1.1 Chuỗi tiến hóa v3 → v5

| Run | Cơ chế mới | Kết cục | Bài học |
|---|---|---|---|
| `real30_v3` | Instrument action outcomes end-to-end | Tuyệt chủng tick 23; chỉ 22/90 tick có call — scheduler cũ không bảo đảm mỗi agent có lượt nghĩ | Không dùng được làm bằng chứng treatment LLM |
| `real15_v4_paced` | Autonomy budget per-agent + preflight RPM fail-closed | Tuyệt chủng **hợp lệ** tick 21: deadlock nhà ở–quyền đất, phân bổ ruộng công theo ID | 5 đề xuất sửa → thiết kế v5 |
| `real15_v5` | Settlement survival treatment (`engine/settlement.py`, `engine/common_land.py`, sàn chỗ ở `minds/safety.py`) | **Sống trọn 45 tick** nhưng kinh tế phẳng | Báo cáo này |

### 1.2 Những gì v5 làm ĐÚNG (ghi nhận để công bằng)

- **Cơ chế settlement sạch về mặt nguyên tắc**: lô cư trú chỉ là *quyền đặt dự án nhà*, không mint tài sản; nhà vẫn cần 8 gỗ + 240 công qua ledger; trùng lô giải bằng **lottery seeded** theo `(lô, tick, rank)` — hết hẳn hiệu ứng ID của v4 (`engine/settlement.py:140-205`).
- **Phân bổ ruộng công equal-access hoạt động**: 1.994 event `phan_bo_ruong_cong` qua lottery, ưu tiên người chưa có ruộng (`engine/common_land.py:80-91`).
- **Action journal khép kín**: funnel 4.624 planned → 4.294 preflight ok → 3.305 executed / 1.149 rejected / 71 unobserved (coverage 98,5%).
- **Sinh thái có feedback thật**: rừng có sinh khối/tán (khai 573 gỗ, canopy 0,70–0,79), CPUE cá giảm (27 `fishery_depleted`), tái sinh rừng 45 event.
- **Nhân khẩu/giáo dục khớp config** (Finding A9): 11 sinh − 6 chết, kỳ vọng lý thuyết ~10 sinh; biết chữ 16%→73% nhất quán với chi phí giáo dục trong config.
- **Autonomy budget về mặt attempt là thật**: mọi agent-tick có ≥1 request được cấp slot, không batch, không agent vượt trần 10 — xác minh độc lập từ `metrics.jsonl`.
- **World-hash + replay tự khai OK** (`replay_complete: true` — lưu ý: chưa được kiểm độc lập trong review này).

---

## 2. Catalog lỗi & điểm chưa hợp lý (xếp theo mức nghiêm trọng)

### NHÓM A — Thiết kế môi trường/giao diện làm kết quả "phẳng" được định trước

#### A1 — Sở hữu đất bất khả thi trên thực tế → `gini_dat = 0.0` là artifact cơ chế **[BLOCKING]**

**Luật engine:** homestead cần canh cùng một thửa công **4 mùa lúa liên tiếp** (`san_xuat.homestead_tick_lien_tiep: 4`; `engine/production.py:341-351`, reset streak tại `:652-656`).

**Giao diện chống lại chính luật này:**
1. Prompt **không bao giờ cho agent biết tiến độ homestead của mình** — `homestead_dem` không được render ở bất kỳ đâu trong `minds/` (chỉ rulebot đọc được, `minds/rulebot.py:57`). Agent không có dữ kiện "bạn đã canh P08_07 được 2/4 mùa".
2. Fact card "RUỘNG CÔNG CÓ THỂ CANH" **xoay ngẫu nhiên offset mỗi agent × tick** (`minds/prompts.py:591-599`) — vá lỗi va chạm thửa của run trước, nhưng tác dụng phụ là mớm 6 thửa *khác nhau mỗi mùa*, chủ động phá streak.
3. Lottery ruộng công mỗi mùa + survival-floor bridge chọn thửa ngẫu nhiên (`minds/safety.py:142-143`) phá tiếp tính liên tục.

**Bằng chứng run:** 0/1.663 cặp (agent, thửa) đạt streak ≥ 4 trong 30 mùa lúa (phân bố streak max: 1 → 1.566 cặp, 2 → 79, 3 → 18; kỷ lục là A0007 đạt 3/4 rồi mất thửa). 0 event `homestead`; `dat_tu_huu = 0` cả 45 tick; `niem_yet`/`tra_gia_dat` được gọi 0 lần. Median mỗi agent gặt trên 36 thửa khác nhau.

**Bác bỏ giải thích thay thế** ("agent chủ đích luân canh"): transcript tick 20, A0013 ghi rõ "canh tác 3 thửa ruộng công *để tích lũy quyền sở hữu đất lâu dài*" — agent **muốn** homestead nhưng không có thông tin để làm đúng.

**Hệ quả dây chuyền:** không đất tư → không thị trường đất, không thế chấp, không địa tô, không phân hóa giai cấp (`giai_cap_snapshot` toàn `trung_nong`) → **toàn bộ tầng thể chế L2–L4 bị khóa từ gốc.** Đây là điểm chưa hợp lý quan trọng nhất của run.

#### A2 — Sàn chỗ ở v5 cấu hình luôn-bật, trưng dụng 100% quỹ công **[BLOCKING]**

- `spatial_livelihood_v5.yaml:32`: `nguong_health_khoi_cong: 100` trong khi health tối đa = 100 → điều kiện chặn `min(health) > nguong` (`minds/safety.py:232`) **không bao giờ đúng** → sàn kích hoạt mọi tick với mọi hộ chưa nhà. (v4 đặt 90 kèm lý do; v5 nâng lên 100 **không có ADR**, comment mô tả sai thực chất always-on.)
- Nhánh xin lô cư trú (`minds/safety.py:204-230`) chạy **trước** cả check ngưỡng.
- `cong_gop_moi_tick: 120` = đúng 100% quỹ công một người lớn một tick → floor chiếm trọn lao động của builder.

**Bằng chứng run:** 318 event `san_cho_o_toi_thieu` (vs chỉ 9 `san_an_toi_thieu`); origin `survival_floor` = 351 action; 49 nhà xây trong ~9 tick.

**Hệ quả diễn giải:** cơn sốt xây nhà đầu run về cơ bản là **engine điều khiển, không phải quyết định LLM**. Provenance có tách nhãn (đúng cam kết scope — không phải hidden bot), nhưng mọi claim về shelter/mortality/health của run này chỉ được phép là "treatment result".

#### A3 — Kinh tế không có khan hiếm → không có động cơ trao đổi; đồng thời người thiếu thật thì không có kênh **[MAJOR — quyết định nghiên cứu]**

- Số học config: nhu cầu 60 kg/người-lớn/tick; một thửa lúa 40 công + 40 kg giống → ~300 kg × màu mỡ 0.6–1.4 → **~8–10 công (trong quỹ 120) đã nuôi đủ một người một tick**. Vụ đông thêm ngô/khoai. ~252 thửa công cho ~50 người, cá + gà dồi dào.
- Bằng chứng run: `tong_thoc` 30.000 → **251.920 kg** (×7,6 dù hao kho 2%/tick); `ty_le_ho_thieu_an ≈ 0`; hạn lụt tick 4–8, 37–38 chỉ giảm ~50% sản lượng một mùa — không đủ tạo khan hiếm. Không sink hấp thụ thặng dư (xu=0, R&D chỉ 12 lượt vì `k0: 160` quá xa, 17 `mo_tiec`).
- **Ca đối chứng A0021** chứng minh có cầu giao dịch thật mà thể chế không kịp nảy sinh: thua lottery 2 lần đầu → sàn chỗ ở trưng dụng công mỗi tick cho dự án nhà trong lúc đói → hết thóc giống ở tick 8 → thắng lottery 3 thửa tick 10 nhưng `rejected insufficient_inputs` (không còn 40 kg giống/thửa) → chỉ còn đánh cá 7–21 kg/tick vs nhu cầu 60 → **chết đói tick 24, tuổi 25,5, di sản = 1 căn nhà + 0,116 gỗ**, khi kho làng có 125 tấn. Không bán được nhà (không chợ bất động sản), không vay được (không tín dụng), không mua được thóc (chợ chết — A4), không xin được (0 `nhan_tin`; `cap_luong_thuc` chỉ chạy nội hộ). **Cả hai sàn an toàn đều yêu cầu nạn nhân tự có ≥ 40 kg thóc giống** (`minds/safety.py:48`, `:118`) — người nghèo nhất đúng nghĩa bị loại khỏi lưới an toàn bằng điều kiện khả thi của chính lưới.
- Phân loại đúng: **provisioning + liquidity failure giữa dư thừa**, cộng **floor design trap** (sàn chỗ ở ưu tiên nhà hơn an ninh lương thực).

#### A4 — Chợ khớp lệnh chết hoàn toàn: 583 lệnh, 0 khớp trong 45 tick **[MAJOR]**

- Chợ là phiên khớp trong-tick, **lệnh không tồn qua tick** (`engine/market.py:170-228`) → xác suất mua–bán trùng tick ≈ 0 khi thanh khoản mỏng.
- Sổ lệnh một chiều: gần như toàn `mua go/thoc`, mẫu lặp **"8.0 @ 13–15"** (8 = đúng recipe nhà 8 gỗ; giá 13–15 anchoring theo ví dụ `don_gia:12`/`14` trong menu prompt — dấu hiệu prompt-induced).
- **Hai kênh chợ song song** (khớp lệnh `dat_lenh` vs báo giá A2A `bao_gia`) chia cắt thanh khoản vốn đã mỏng. Kênh báo giá v5 hoạt động nhưng li ti: 37 đăng → 11 khớp → **8 settlement, tổng 153 kg thóc / 15 năm**; 34/37 báo giá cũng lại là mua gỗ. Từ chối: 92 `insufficient_payment` (menu hiển thị quote **không lọc theo tồn kho người xem**), 49 `quote_exhausted`.
- Hệ quả: **không tồn tại bất kỳ giao dịch lương thực, lao động, hay đất nào trong toàn run** — kết hợp A3, người thiếu ăn không có chỗ mua thóc dù làng thừa 250 tấn.

#### A5 — Kênh hợp đồng gần như chết; cổng biết-chữ khóa ngược thời điểm **[MAJOR]**

- 15 năm: 26 request `de_nghi_hop_dong` → 6 offer → 4 ký → 4 hoàn thành, **tất cả là chuyển-giao-một-lần + góp công thời hạn 1 tick** → "hợp đồng hiệu lực 0" cuối run là đương nhiên. Không thuê đất, cấy rẽ, vay mượn nào.
- Cổng `van_ban_can_E_nguoi_soan = 1` + biết chữ khởi điểm 16%: đầu run — lúc nhu cầu phối hợp cao nhất (mỗi nhà 240 công) — đa số dân **không được phép đề nghị hợp đồng**, kể cả hình thức miệng bị chặn ở validator (event tick 5, 16). Khi biết chữ đạt 73% thì kinh tế đã dư thừa, hết động cơ. **Timing thể chế bị khóa ngược.**

### NHÓM B — Bug kỹ thuật

#### B1 — Bug dịch intent nuốt `phan_bo_cong`: 75 lượt lao động mất trắng vì `null` **[P0 — sửa 1 dòng]**

- `minds/capabilities.py:368`: `[str(x) for x in d.get("canh_thua", [])]` — khi LLM gửi tường minh `"canh_thua": null` (rất tự nhiên vào mùa đông), `d.get` trả về `None` → `TypeError: 'NoneType' object is not iterable` → **cả action bị vứt, kéo theo cả `hoc`, `khai_go_cong`, `day_cho` hợp lệ đính kèm**. Cùng pattern ở `:373` (`day_cho`).
- **Bằng chứng:** 75/79 dòng `unrecognized_intents.jsonl` là đúng lỗi này. 3 dòng còn lại: `de_nghi_hop_dong` (2 mù chữ, 1 thiếu `dieu_khoan`), 1 `nghien_cuu` lĩnh vực ngoài catalog.
- **Trớ trêu:** chính mẫu menu trong prompt (`minds/capabilities.py:1311`) dạy `"gop_cong_cho":null` — dạy model rằng null hợp lệ cho field không dùng.
- **Fix:** `(d.get("canh_thua") or [])` + test negative "mọi field optional = null".

#### B2 — World tools được quảng cáo nhưng 0/1.936 call sử dụng **[MAJOR]**

- Mọi record transcript có `tool_turns: []`; `luot_cong_cu_phien = 0`, trong khi prompt quảng cáo công cụ chỉ-đọc (`minds/prompts.py:790-793`, `:996-999`).
- **Nghi phạm chính:** chỉ thị cứng "Trả về DUY NHẤT JSON (không lời dẫn, không markdown)" (`minds/prompts.py:152-153`) mâu thuẫn trực tiếp với việc phát tool-call turn. 5 model × 1.936 call × 0 tool là tín hiệu giao diện, không phải lựa chọn model.
- Hệ quả: gate P3 ("agent khám phá được mọi hành động qua catalog/tool") chỉ đúng trên fixture, không chuyển giao sang run real.

### NHÓM C — Đo lường & báo cáo (verdict adversarial-review: **major revision**)

#### C1 — Hai định nghĩa "fallback" trộn lẫn; report chọn con số đẹp hơn 160 lần **[BLOCKING cho mọi bảng kết quả]**

- **Định nghĩa A (call-level):** cột `fallback` trong `llm_calls.sqlite` = {0: 1935, 1: 1} → `fallback_rate = 0.0005` (nguồn: `tools/telemetry.py:59-62`, `run.py:493-495`). Đây là con số duy nhất xuất hiện trong `telemetry.md:3` và `session_1.md:7`.
- **Định nghĩa B (decision-level):** `so_fallback_phien = 167` = agent-tick mà quyết định rơi về policy card/rulebot (`minds/orchestrator.py:207,242`). Đối chiếu độc lập từ `metrics.jsonl` `decision_provenance.plans`: `{llm: 1932, fallback: 167, policy_card: 110}` — khớp chính xác. **167/2.099 = 7,96% agent-tick không do LLM quyết.**
- **Tệ hơn trung bình — dồn cụm theo nghẽn RPM:** tick 23 = 23/47 agent (48,9%), tick 37 = 23/45 (51,1%), tick 24/38/44 = 18–19 agent. Có những tick **quá nửa làng chạy bằng thẻ**, và rulebot canh tác "chuẩn" hơn LLM → nhiễu chuỗi hành vi.
- Gate D1 của `tools/reality_check.py:502-533` cũng chỉ đo định nghĩa A → run sẽ pass D1 với 0.05% dù 8% quyết định là fallback. Đây là **artifact selection cấu trúc** trong pipeline report.

#### C2 — Run vi phạm gate do chính báo cáo v4 đặt ra và cam kết trong manifest của chính nó **[BLOCKING]**

- `reality_check_real15_v4_paced.md:90-102` đã phát biểu đúng bệnh: *"PASS hiện tại chỉ nói 'mỗi agent đã thử gọi provider', chưa nói 'mỗi agent đã nhận đúng một quyết định LLM parse được'. Một nghiên cứu không được gộp hai khái niệm này"* — và đặt gate (`:132-141`): **không chạy ensemble 15 năm cho tới khi smoke 12-tick có `parsed_decision_coverage` đạt ngưỡng + log mọi HTTP attempt.**
- `real15_v5` chạy 45 tick ngay sau đó: không có metric `parsed_decision_coverage`, không có smoke 12-tick trong `data/runs/`, per-attempt log chưa implement.
- `experiment_manifest.json:83` cam kết: *"Khi RPM không đủ cho lượt bắt buộc của cả cohort, run dừng trước tick **thay vì chạy một phần dân số bằng policy card**."* Thực tế: preflight chỉ bảo đảm headroom cho lượt *tối thiểu* (`minds/real.py:156-169`); bão retry giữa tick vẫn khiến 49–51% dân của tick 23/37 chạy bằng thẻ. **Giữ được phần chữ (attempt coverage), vỡ phần nghĩa (decision coverage).**

#### C3 — 4.594 HTTP request không có vết per-request — điều luật #6 chưa thỏa ở mode real **[MAJOR]**

- `so_api_call_phien = 6530` slot tiêu ngay trước `client.post` (`minds/tick_budget.py:129-148`) vs chỉ **1.936 row** trong DB/transcript → **4.594 HTTP post thật (429/disconnect/JSON hỏng, ~70% attempt) chỉ tồn tại dưới dạng tổng đếm**, không có model/key/latency/error-code per attempt.
- Vòng retry (`providers_real.py:490-507`) nuốt lỗi; cột `retries` trong DB chỉ còn 2 — **undercount ~2.300 lần** so với attempt thật.
- Hệ quả: latency p50/p99 và chi phí $2.3003 trong telemetry chỉ tính call thành công; caveat chi phí từng có trong report v4 bị bỏ ở v5.
- **192 agent-tick chạm trần 10 request, trong đó 167 kết thúc bằng fallback** (tương quan gần 1:1 theo tick) — trần 10 chủ yếu bị *đốt bởi retry hạ tầng*, không phải agent "suy nghĩ nhiều lượt". "PASS 0/0/0" đúng số học về attempt nhưng đang được đọc như coverage quyết định.
- Nghẽn gốc: quota gộp ~72 RPM với concurrency 34 → bão 429; **28% runtime (1.263 s/4.466 s) chỉ để chờ preflight** — và đó còn là under-count (sleep trong `_cho_slot` không được cộng).

#### C4 — Metric/schema gây hiểu lầm **[MINOR nhưng lan tỏa]**

| Vấn đề | Chi tiết | Vị trí |
|---|---|---|
| GDP ≈ 0 hoặc âm | Định giá bằng giá khớp gần nhất; chưa từng khớp → giá 0. Tick 9: GDP = −741 vì xây nhà tiêu gỗ-có-giá tạo nhà-giá-0, dù làng gặt 87 tấn khoai + 156 tấn ngô cả run | `engine/metrics.py:44-50` |
| `gini_dat = 0.0` | Mẫu số = 0 thửa tư hữu (A1) — giá trị rỗng, không phải đo bình đẳng; report in không chú thích | `session_1.md:4` |
| `p_malformed = 0.0` | Tham số adversarial của Mock, hardcode khi khởi tạo MindReal và in vô nghĩa vào report real, cạnh "fallback 0.05%" → dễ đọc nhầm là "tỷ lệ JSON hỏng = 0" | `minds/real.py:93` |
| `luot_cong_cu` hai nghĩa | run_meta đếm tool-turn MCP (=0); telemetry đếm `SUM(retries)` (=2) — cùng tên khác nghĩa | `tools/telemetry.py:74` |
| Model `?` trong bảng | Row lỗi `call_id=51, provider='loi', model=''` (RemoteProtocolError) bị gộp thành `?` | `tools/telemetry.py:82` |
| 1935 vs 1936 | Bộ đếm mind chỉ tăng ở call thành công; row lỗi ghi qua `_ghi_call_loi` không tăng | `orchestrator.py:445-452` |
| `treatments: []` trong manifest | v4/v5 là treatment-only, 3 survival floor đang bật, nhưng field treatments rỗng — phải tự suy từ overlay | `experiment_manifest.json` |
| Magic constant trong code | `HD_HIEN_TOI_DA=10`, board slice `[:6]`/`[:5]`/`[:8]` (chính `[:6]`+rotation tham gia A1) — vi phạm quy ước "mọi tham số về YAML" | `minds/prompts.py:511-514` |
| Run bỏ dở trùng tên | `data/runs/real15_v5_full`: 0 call, không run_meta, còn `-journal` — không phải cherry-pick (không có outcome) nhưng nên dọn/ghi chú | — |

---

## 3. Hướng giải quyết triệt để

Nguyên tắc chung: **mỗi thay đổi luật nền đi qua ADR; mọi fix hành vi phải có test hồi quy; mỗi treatment phải có ablation.** Chia 4 đợt theo dependency.

### Đợt 1 — Sửa ngay, không cần ADR (bug + reporting; ~1–2 ngày)

| # | Việc | File | Nghiệm thu |
|---|---|---|---|
| 1.1 | Fix `NoneType`: `(d.get("canh_thua") or [])`, tương tự `day_cho`; quét toàn bộ `capabilities.py` cho pattern `d.get(x, [])` khi x có thể null | `minds/capabilities.py:368,373` | Test negative: mọi field optional gửi `null` → action vẫn dịch được; replay fixture 79 intent cũ → unrecognized ≤ 4 |
| 1.2 | Telemetry in **decision-fallback**: `fallback_plans/agent_tick` (= 167/2099) + phân bố theo tick, cạnh call-fallback; gate D1 đổi nguồn sang `decision_provenance` | `tools/telemetry.py`, `run.py:548-553`, `tools/reality_check.py:502-533` | telemetry.md của run cũ regenerate ra cả 2 con số |
| 1.3 | Bỏ in `p_malformed` ở mode real; tách `luot_cong_cu` thành `tool_turns` và `json_retries`; provider `loi` không lẫn vào bảng model | `minds/real.py:93`, `tools/telemetry.py:74,82` | Schema run_meta có docstring từng field |
| 1.4 | `session_1.md` in `gini_dat` kèm mẫu số (`n_thua_tu_huu`), GDP kèm "tỷ lệ đầu ra không định giá được" | `engine/metrics.py`, generator report | Report tự sinh không còn số trần trụi gây hiểu lầm |
| 1.5 | Manifest ghi tường minh `treatments: [survival_floor_food, survival_floor_shelter, settlement_entry_v5, common_land_lottery]`; dọn `real15_v5_full` | `run.py` (ghi manifest) | Manifest mới tự mô tả đủ treatment stack |

### Đợt 2 — Đo lường & hạ tầng LLM (điều kiện tiên quyết cho mọi run real kế tiếp; ~3–5 ngày)

| # | Việc | Thiết kế | Nghiệm thu |
|---|---|---|---|
| 2.1 | **Log per-attempt**: mỗi HTTP post (kể cả 429/disconnect) một row `attempt_log` (call_id cha, provider, model, key-hash, status, latency, error-class) | Bảng mới trong `llm_calls.sqlite`; điều luật #6 áp dụng đủ cho mode real | `COUNT(attempt_log) == so_api_call_phien` chính xác tuyệt đối |
| 2.2 | **Sàn autonomy đếm theo completed decision**, không theo attempt: metric mới `parsed_decision_coverage` per tick per agent; "PASS" đổi định nghĩa | `minds/tick_budget.py`, `orchestrator.py` | Gate mới: run real chỉ hợp lệ đưa vào bảng E khi coverage ≥ ngưỡng công bố (đề xuất 98%/tick) |
| 2.3 | **Pacing client-side theo RPM** thay retry-storm: token-bucket theo (provider×key), reserve slot response cuối cho mỗi agent (đúng đề xuất v4 `:128-130`); tick partial-cohort được đánh dấu trong metrics và tự động loại khỏi claim hành vi | `minds/real.py`, `providers_real.py`, `tick_budget.py` | Smoke 12-tick: 0 tick partial-cohort; attempt-waste < 20% (hiện 70%) |
| 2.4 | **Smoke real 12-tick bắt buộc trước mọi run dài** (gate v4 chưa từng được thỏa): coverage + per-attempt log + telemetry 2 định nghĩa fallback đều xanh | Script `tools/smoke_real.py` hoặc lệnh run.py flag | HUMAN-GATE chỉ mở sau smoke xanh |
| 2.5 | Sửa mâu thuẫn tool-call: chỉ thị "DUY NHẤT JSON" → "JSON là *lượt trả lời cuối*; trước đó được phép gọi công cụ chỉ-đọc"; test fixture xác nhận payload thật mang tool declarations | `minds/prompts.py:152-153` | Smoke: tool_turns > 0 xuất hiện tự nhiên ở ≥1 model |

### Đợt 3 — Sửa thiết kế môi trường/giao diện (qua ADR; ~1–2 tuần)

| # | Việc | Thiết kế | ADR/Nghiệm thu |
|---|---|---|---|
| 3.1 | **Fact card homestead** (engine-owned fact, không phải lời khuyên): "bạn đang tích homestead thửa Pxx: n/4 mùa; bỏ mùa này sẽ mất" + **pin thửa đang homestead đứng đầu board**, loại nó khỏi phép xoay ngẫu nhiên | `minds/prompts.py` (render `p.homestead_ai/homestead_dem`) | ADR-000X; nghiệm thu: mock run 60 tick có ≥1 homestead thành công; test "thửa đang homestead luôn hiển thị" |
| 3.2 | **Sàn chỗ ở về đúng nghĩa sàn**: `nguong_health_khoi_cong` về vùng nguy hiểm thực (50–60), nhánh xin lô cũng phải qua ngưỡng, `cong_gop_moi_tick` < 100% quỹ công (đề xuất 60), sàn không trưng dụng công của hộ đang `an_doi` | `minds/safety.py:204-232`, `spatial_livelihood_v6.yaml` | ADR bắt buộc (v5 đổi 90→100 không ADR); **ablation floor-off** như scope đã hứa |
| 3.3 | **Sàn ăn có đường thoát cho người hết giống**: bỏ điều kiện "tự có ≥40 kg giống" (`minds/safety.py:48,118`) — thay bằng intent hợp lệ: đổi công lấy giống qua quote, hoặc xin cấp giống từ kho hộ khác qua kênh có ledger. Tuyệt đối không mint | cùng file | Test: agent 0 thóc 0 giống không bị loại khỏi lưới; ca A0021 replay không chết |
| 3.4 | **Chợ**: lệnh persist ≥ N tick (config, đề xuất 3); bắc cầu 2 kênh (quote hết hạn tự đổ vào order book hoặc ngược lại — chọn 1 qua ADR); menu lọc quote theo tồn kho người xem; ví dụ giá trong menu lấy từ giá khớp/quote gần nhất thay vì hằng số 12/14 (chống anchoring) | `engine/market.py:170-228`, `minds/capabilities.py` | Property test khớp lệnh persist; mock run: matched > 0 |
| 3.5 | **Hợp đồng miệng** không cần biết chữ (chỉ hợp đồng *văn bản* — có thể cưỡng chế mạnh hơn — cần E≥1): tách hai bậc qua ADR, phản ánh đúng lịch sử (giao kèo miệng có trước chữ viết) | `engine/contracts.py`, validator | ADR; mock run đầu kỳ có hợp đồng miệng được ký |
| 3.6 | Giá trong prompt render động từ `tai_san_giao_dich(w)` thay vì hard-code 3 tài sản | `minds/prompts.py:82` | Đúng Report_v2 P0.1 |
| 3.7 | Board slice `[:6]`/`[:5]`/`[:8]`, `HD_HIEN_TOI_DA`… về YAML | `minds/prompts.py:511-514` | ruff + grep không còn magic number |

### Đợt 4 — Hiệu chỉnh khan hiếm (quyết định nghiên cứu, qua ADR + sensitivity; ~2–3 tuần)

Đây KHÔNG phải bug — là lựa chọn tham số quyết định câu hỏi nghiên cứu có ràng buộc thật hay không. Ở chế độ hiện tại (8–10 công nuôi một người, 5 thửa/người), tiền/tín dụng/thuê mướn gần như không có lý do tồn tại; kết quả "phẳng" nằm sẵn trong tham số.

- **4.1** ADR hiệu chỉnh độ khan hiếm với provenance (không phải "cho ra chuyện hay"): tỷ lệ đất canh được/người, variance thời tiết đủ tạo năm mất mùa thật, chi phí canh tác, hao kho — tham chiếu khoảng giá trị nông nghiệp tiền công nghiệp (FAO/Allen/Clark có sẵn trong tài liệu kinh tế sử).
- **4.2** Chạy **sensitivity sweep** (`tools/sensitivity.py`) trên trục khan hiếm với rulebot (rẻ) trước, xác định vùng tham số có: (a) không tuyệt chủng, (b) có biến động thặng dư thật giữa hộ/năm. Vùng đó mới là nơi câu hỏi "thể chế có tự phát không" có nghĩa.
- **4.3** Xem lại sink/động cơ đầu tư: `k0: 160` cho R&D so với 12 lượt nghiên cứu/15 năm — hoặc R&D quá đắt hoặc lợi ích không nhìn thấy được từ prompt; kiểm tra fact card R&D.

---

## 4. Lộ trình lên chuẩn "bài báo tốt nhất thế giới"

### 4.1 Định vị khoa học — điểm mạnh có thật của THÓC

So với các công trình generative-agent hiện có (Smallville-style social sims, AgentSociety, các LLM-economy sandbox), THÓC có 4 lợi thế cấu trúc **hiếm có** nếu giữ được kỷ luật:

1. **Kế toán bảo toàn + sổ kép + audit từng tick** — hầu hết sim LLM không có; đây là điều kiện để claim kinh tế có nghĩa.
2. **Tất định & replay từ transcript → cùng world-hash** — mức reproducibility gần như không sandbox LLM nào công bố được.
3. **Anti-teleology có cổng minh bạch** (charter/ADR): định chế không được code sẵn, chỉ được là tổ hợp văn phạm hợp đồng — trả lời đúng phê phán "cài kết quả vào cơ chế" mà giới ABM (agent-based modeling) đã nêu hàng chục năm.
4. **Provenance từng quyết định** (llm/fallback/policy_card/survival_floor) — cho phép tách "hành vi LLM" khỏi "treatment", điều mà chính review này dựa vào để bắt lỗi.

**Câu hỏi đáng giá nhất bài báo** (đúng charter, không cần nói quá): *Trong môi trường nông nghiệp khan hiếm có kế toán bảo toàn nghiêm ngặt, những điều kiện tối thiểu nào (thông tin, văn phạm hợp đồng, ma sát) để trao đổi → chuyên môn hóa → tín dụng quan hệ tự phát từ agent LLM — và khi nào chúng KHÔNG tự phát?* Kết quả âm tính có kiểm soát tốt cũng là đóng góp — chính run v5 (sau khi sửa A1–A4, B1) là ví dụ: "thể chế không nảy sinh dưới dư thừa" là một data point hợp lệ **nếu** loại được confound.

### 4.2 Chuẩn bằng chứng bắt buộc (từ trạng thái hiện tại → publishable)

| Trụ cột | Hiện tại | Yêu cầu công bố |
|---|---|---|
| **Ensemble** | 1 seed/điều kiện | ≥ 20–30 seed/điều kiện, paired-seed giữa treatment (`tools/counterfactual.py` đã có khung) |
| **Baseline** | rulebot có nhưng chưa đối chứng hệ thống | Mọi claim "LLM làm X" phải kèm rulebot cùng seed + null model (random-valid-intent); hiệu ứng = LLM − baseline, kèm CI |
| **Ablation** | scope hứa nhưng chưa chạy | Mỗi treatment (shelter floor, food floor, settlement entry, common land lottery) một trục on/off; bảng 2^k fractional nếu tốn |
| **Coverage gate** | attempt-based, 8% rulebot lẫn vào | `parsed_decision_coverage ≥ 98%`/tick; tick partial-cohort loại khỏi phân tích hành vi |
| **Đa model** | 4 model Gemini cùng họ | ≥ 2 họ model khác nhau để claim không phải "đặc tính Gemini"; báo cáo per-model |
| **Prompt sensitivity** | 1 phiên bản prompt | Ít nhất 2 biến thể prompt tương đương ngữ nghĩa (đổi thứ tự menu, đổi ví dụ giá) để chứng minh kết quả không phải anchoring — run v5 đã cho thấy anchoring giá 12/14 là rủi ro thật |
| **Pre-registration nội bộ** | reality_check hậu kiểm | Trước mỗi ensemble: file protocol đóng băng (câu hỏi, metric chính, ngưỡng, quy tắc loại run) — commit trước khi chạy; chống garden-of-forking-paths |
| **Claim tier** | mechanism_benchmark (đúng) | Giữ nguyên; tuyệt đối không chữ "validated/empirical" khi chưa có calibration + holdout (đúng ADR 0001 §E) |

### 4.3 Khung thí nghiệm đề xuất cho bài báo

**Thiết kế 2×2×2 (tối thiểu):**
- Trục 1 — **Khan hiếm**: abundance (config hiện tại) vs calibrated-scarcity (Đợt 4).
- Trục 2 — **Thông tin**: giao diện hiện tại vs giao diện đã sửa A1/3.6 (homestead fact, giá động).
- Trục 3 — **Mind**: LLM vs rulebot (paired seed).

**Outcome chính (đăng ký trước):** (1) thời điểm giao dịch tự nguyện đầu tiên và khối lượng trao đổi/năm; (2) số hợp đồng đa-tick còn hiệu lực; (3) chỉ số chuyên môn hóa (entropy phân bố lao động theo hộ); (4) tập trung đất (gini trên mẫu số thửa tư hữu, in kèm n); (5) tử vong do phân phối (chết đói khi kho làng > ngưỡng — "ca A0021").

**Outcome phụ:** tín dụng quan hệ (hợp đồng hoãn-đối-ứng), xuất hiện tài sản trung gian trao đổi (proto-money — đo bằng tần suất một tài sản xuất hiện ở cả 2 vế giao dịch tam giác), phân tầng.

**Ngân sách:** với ~$2.3/run 45 tick hiện tại, ensemble 8 điều kiện × 25 seed × 45 tick ≈ **$500–700 + thời gian RPM** — khả thi; nút cổ chai thật là quota (cần Đợt 2.3 để attempt-waste < 20%, và cân nhắc tier trả phí cho ensemble chính thức).

### 4.4 Trụ reproducibility khi công bố

1. Repo + config + seed list + transcript đầy đủ → **bất kỳ ai replay không cần API key ra đúng world-hash từng run** (điểm bán độc nhất của THÓC — hiện đã gần đạt, cần kiểm độc lập `replay_complete` thay vì self-report).
2. `attempt_log` per-request công khai (Đợt 2.1) → chi phí/latency/failure tái kiểm được.
3. Một lệnh `make paper` (hoặc script) dựng lại mọi bảng/hình trong bài từ `data/runs/` thô — không con số nào chép tay.
4. Khai báo đầy đủ treatment stack trong manifest từng run (Đợt 1.5) + bảng provenance quyết định (llm/fallback/card/floor) trong phụ lục.

### 4.5 Venue và khung bài

- **Venue phù hợp:** track agents/multi-agent của NeurIPS/ICML/ICLR (đóng góp: benchmark + negative result có kiểm soát), hoặc PNAS/Science Advances/Nature Human Behaviour nếu trục kinh tế-thể chế mạnh (cần ensemble + hiệu chỉnh khan hiếm thật tốt), hoặc JASSS/Artificial Life cho cộng đồng ABM (dễ vào hơn, ít impact hơn). Chiến lược hợp lý: **một bài methods/benchmark trước** (THÓC như instrument: bảo toàn + replay + provenance + funnel intent), rồi bài kết quả thể chế sau khi có ensemble.
- **Khung bài benchmark:** (i) vấn đề: sim LLM hiện nay không kiểm toán được; (ii) THÓC: 5 lớp, 7 điều luật, cổng định chế minh bạch; (iii) instrument validation: funnel action journal, decision provenance, replay; (iv) case study chẩn đoán = chính chuỗi v3→v5 này (kể cả các lỗi trong review này — **câu chuyện "chúng tôi bắt được confound của chính mình bằng instrument" là điểm mạnh, không phải điểm yếu**); (v) release: code + data + protocol.

### 4.6 Định nghĩa hoàn thành cho "publishable"

1. Đợt 1–3 hoàn tất, mọi test xanh, ruff sạch; smoke real 12-tick xanh theo gate mới.
2. ADR khan hiếm (Đợt 4) chốt + sensitivity sweep rulebot xác định vùng tham số.
3. Protocol pre-registered commit trước ensemble; ensemble 2×2×2 × ≥20 seed chạy xong, replay kiểm độc lập ≥ 3 run ngẫu nhiên.
4. Mọi bảng/hình dựng tự động từ dữ liệu thô; claim tier ghi rõ trên từng bảng.
5. Một reviewer độc lập (adversarial-reviewer agent hoặc người) pass toàn bộ artifact mà không tìm được confound mới ở mức blocking.

---

## 5. Phụ lục — Đối chiếu số liệu telemetry (để sửa schema)

| Field | Giá trị | Nghĩa thật | Ghi chú |
|---|---|---|---|
| `so_call` = 1936 | row trong DB | 1932 call quyết định + 2 retry-JSON + 1 row lỗi + 1 response hỏng | |
| `so_call_phien` = 1935 | bộ đếm mind | chỉ tăng ở call thành công; row lỗi không tăng | vênh 1 = 1 call lỗi |
| `so_luot_nghi_phien` = 2099 | agent-tick có kế hoạch | = 1932 LLM + 167 fallback (110 policy_card chủ động không tốn call, đếm riêng) | |
| `so_fallback` = 1 | call-level | 1 provider error được log | nguồn của "0.05%" |
| `so_fallback_phien` = 167 | decision-level | 8% agent-tick quyết bằng rulebot/card | **con số phải công bố** |
| `so_api_call_phien` = 6530 | slot HTTP attempt | 4.594 attempt không có vết per-request | cần `attempt_log` |
| `so_api_call_bi_tu_choi_phien` = 54 | từ chối tại trần | không post | |
| `luot_cong_cu_phien` = 0 | tool-turn MCP thật | MCP tắt trong run | |
| `luot_cong_cu` = 2 | SUM(retries) trong DB | 2 retry sửa JSON | đổi tên |
| `cho_burst_preflight_s_phien` = 1263 | sleep preflight | 28% runtime; under-count (sleep `_cho_slot` không cộng) | |
| `p_malformed` = 0.0 | tham số Mock | vô nghĩa ở mode real | bỏ in |

**Trạng thái xác minh:** mọi con số trên đã được đối chiếu độc lập giữa `llm_calls.sqlite`, `transcript.jsonl`, `metrics.jsonl` (`decision_provenance`), `events.jsonl` và code đếm; không phát hiện ngụy tạo. Riêng `replay_complete: true` là self-report, chưa replay kiểm chứng trong review này.

---

*Review này là mechanism-level trên 1 run/1 seed; các finding về code/config là CONFIRMED (có file:line); các giả thuyết nhân quả hành vi (anchoring giá, lý do model không gọi tool) là PLAUSIBLE — cần thí nghiệm Đợt 2–3 để chốt.*
