# PHASES.md — Lộ trình xây & nghiệm thu v3 (Claude Code tự chấm, không tự bỏ gate)

Quy tắc: làm tuần tự; kết thúc phase = chạy ĐỦ lệnh nghiệm thu, dán kết quả vào PROGRESS.md,
commit `phase-N: ...`. Mọi lệnh qua conda env `thoc-env`. `--fast` tắt latency mock.
Chỉ 2 HUMAN-GATE (trước call thật quy mô).

> **⚠️ SUPERSEDED một phần (2026-07-12).** Đây là lộ trình xây dựng *legacy* (Phase 0–8) và đã
> hoàn tất tới mock (xem PROGRESS.md). Phiên nghiên cứu hiện tại theo `TASKS.md` (T00–T12) và
> `docs/MODEL_CHARTER.md`. Cụ thể: tiêu chí "hiệu chỉnh median công-nghiệp-hóa 160–280" ở Phase
> 4 KHÔNG còn là tiêu chí khoa học (ADR 0001 §E) — giữ như legacy regression label. Không chạy
> Phase 5–8 (provider/real/pilot) trong phiên nghiên cứu không-mạng.

---

## Phase 0 — Khung xương, sổ kép, FlowRegistry
**Làm:** scaffold repo (CLAUDE.md mục 7); conda env + requirements.txt; config loader; cây
RNG (spawn theo subsystem×tick); `ledger` (sổ kép, đa tài sản, đa chủ thể người/pháp nhân);
`audit` + FlowRegistry (SPEC 2.4); `.gitignore` có `.env`, `data/`.
**Nghiệm thu:** `pytest -q tests/test_ledger.py tests/test_rng.py` xanh, gồm hypothesis:
chuỗi transaction ngẫu nhiên không bao giờ âm số dư, luôn cân nợ–có, FlowRegistry bắt được
một luồng "lậu" cố tình cài trong test. `ruff check .` sạch.

## Phase 1 — Thế giới sống được (chưa chợ, chưa hợp đồng, chưa LLM)
**Làm:** map/parcels/làng; thời tiết; sản xuất nông + khai thác + chế tác cơ bản (recipe
vật lý); nhu cầu–health–chết đói; nhân khẩu (cưới rulebot, sinh, chết, thừa kế mặc định);
homestead; giáo dục vật lý (dạy tại nhà); rulebot v0 persona-hóa tự cung tự cấp; vòng tick
(bỏ bước 4, 6, 7); metrics cơ bản; checkpoint/resume.
**Nghiệm thu:**
- `python run.py --mode rulebot --years 300 --seed 42 --run-name rb300` < 5 phút, audit
  xanh TỪNG tick.
- Dân số cuối ∈ [60, 500], không tuyệt chủng với seeds {41,42,43} (lệch → chỉnh world.yaml,
  ghi DECISIONS.md).
- `tools/replay rb300 --verify` trùng hash; test resume (100 tick + resume 100 = 200 liền).

## Phase 2 — CONTRACT ENGINE + chợ generic + bảng rao (trái tim của v3)
**Làm:** văn phạm 9 clause + executor thi hành MỌI tổ hợp hợp lệ; miệng/văn bản; uy tín;
cưỡng chế + xiết thế chấp; bảng rao (đề nghị công khai/đích danh, chấp nhận/từ chối/mặc cả);
chợ call auction generic mọi tài sản + sealed bid đất/nhà; chuyển nhượng vị thế hợp đồng;
buôn chuyến; rulebot v1 dùng 8 công thức hợp đồng (SPEC 7.5).
**Nghiệm thu:**
- Hypothesis trên executor: sinh hợp đồng ngẫu nhiên hợp lệ từ văn phạm, chạy K tick →
  không vi phạm bảo toàn, không âm số dư, vi phạm được phát hiện đúng tick.
- Unit auction: fixture bid/ask → giá & khối lượng đúng đáp án tay; không khớp quá cung/cầu.
- Kịch bản định hướng (thế giới nhỏ, điều kiện dựng để rulebot chắc chắn kích hoạt):
  (a) hợp đồng cấy rẽ (quyền_sử_dụng + chia_sản 40%) chạy đúng 8 tick, chia đúng từng kg;
  (b) vay văn bản có thế chấp đất → mất mùa → vi phạm → xiết đúng giá chợ, thừa hoàn lại;
  (c) vi phạm hợp đồng MIỆNG → không xiết, chỉ trừ uy tín + tin đồn lan đúng đồ thị;
  (d) hạn hán → giá thóc phiên sau tăng ≥20%; (e) một thửa 3 bid → bán đúng bid cao nhất ≥ ask.
- `rulebot --years 300`: khối lượng giao dịch > 0 ở ≥80% tick sau năm 5; ≥3 mô-típ hợp đồng
  khác nhau đang lưu hành ở năm 50; audit xanh.

## Phase 3 — Minds ở chế độ MOCK
**Làm:** triggers; policy cards + thi hành thẻ; batching; prompt builder (menu nguyên tố +
văn phạm + mẫu hợp đồng đang lưu hành — khởi đầu 2 mẫu tối giản); gateway interface;
**MockLLM PersonaBot** (8 công thức + persona + ngẫu hứng p=.02) + **adversarial**; pipeline
sửa JSON + fallback; whitelist validate; memory 2 lớp (mock nén); llm_calls logging;
unrecognized_intents.jsonl.
**Nghiệm thu:**
- `tests/test_json_repair.py`: corpus ≥ 80 mẫu hỏng đủ 7 kiểu phá, **≥30 mẫu là hợp đồng
  lồng nhau** → cứu ≥95%.
- `tests/test_batch_heterogeneity.py`: 8 persona khác nhau cùng hoàn cảnh → ≥4 khác biệt
  thực chất (hành động khác hoặc tham số lệch >15%).
- `python run.py --mode mock --years 300 --seed 42 --fast --run-name mock300` trọn vẹn;
  p_malformed=0.15 cho run này; fallback_rate < 5%; audit xanh; llm_calls đủ 100% call.
- Determinism: chạy lại → world-hash trùng. Sinh `reports/compare_baseline.md` (mock vs rb).

## Phase 4 — Pháp nhân, cổ phần, R&D, khuếch tán, observatory + HIỆU CHỈNH CÔNG NGHIỆP HÓA
**Làm:** entities + cổ phần token + quản trị >50% + phá sản/thanh lý; cổ phần list được lên
chợ; R&D 7 lĩnh vực + blueprint (engine rút độ lớn) + hàng mới (recipe + hiệu ứng engine rút,
tên LLM đặt) + li-xăng + khuếch tán 0.9^n; máy; đúc xu; tri_thuc & sàn tier nội sinh;
di chúc LLM + gia huấn; di cư; observatory (nhãn định chế 9.2 + milestones 9.5) + chronicle
(mock viết); dashboard tab Hợp đồng (mô-típ auto-cluster theo tổ hợp clause).
**Nghiệm thu (kịch bản định hướng — exercise cơ chế, không ép kết quả run tự do):**
- (a) 3 agent lập entity 50/30/20, góp vốn, 2 hợp đồng góp công, chia lợi nhuận theo cổ phần
  đúng từng kg; một cổ đông bán 20% trên chợ → sang tên đúng;
- (b) chuỗi 5 hợp đồng gửi-rút vào 1 entity → observatory tự dán nhãn `ngan_hang`; ép rút
  đồng loạt vượt dự trữ → vi phạm hàng loạt → thanh lý pro-rata đúng sổ; milestone ghi nhận;
- (c) đầu tư R&D dồn `cong_cu_may_moc` → blueprint → dựng máy → entity 5 công nhân có năng
  suất/đầu người CAO HƠN hộ tự canh trong fixture; observatory dán `xuong`;
- (d) blueprint `che_bien` → hàng mới có tên xuất hiện, được mua bán, hiệu ứng đúng;
- (e) hợp đồng dieu_kien_su_kien (mất mùa → bồi thường) chi trả đúng khi hạn hán → nhãn
  `bao_hiem` khi đủ 5 hợp đồng.
- **Hiệu chỉnh:** ~~chạy mock 300 năm với seeds {41..45} (--fast): seed TRUNG VỊ đạt nhãn
  `cong_nghiep_hoa` trong năm [160, 280]~~ **(SUPERSEDED — ADR 0001 §E: KHÔNG còn là tiêu chí
  khoa học; chỉ giữ như legacy regression label, không áp cho `agrarian_transition_v1`)**.
  Chưa đạt → CHỈ chỉnh `research.yaml`/giá máy (không sửa hành vi bot để ép), ghi DECISIONS.md,
  chạy lại. Xuất `reports/calibration.md`: năm đạt nhãn từng seed + phân bố mô-típ hợp đồng.
- mock300 full-feature: audit xanh; milestones không rỗng; `tools/analyze` ra ma trận dịch
  chuyển giai cấp + wealth-share + thu nhập theo tier.

## Phase 5 — Provider thật + hạ tầng quota (chưa đốt quota)
**Làm:** aistudio + ninerouter (giữ nguyên tiền tố `gc/` trong model id); keypool regex;
routes/tier có tràn (T1: key → 9router); token-bucket persist; cooldown 429; budget guard;
`--smoke`; health-check 9router.
**Nghiệm thu:** FakeTransport unit: (a) 429 xen kẽ → cooldown & xoay key đúng; (b) chạm RPD
→ model khóa tới reset; (c) restart không mất bộ đếm; (d) budget thiếu → dừng êm + checkpoint,
KHÔNG degrade; (e) T1 cạn route key → tự tràn sang route 9router, log đúng provider.
Nếu `.env` có key thật: `run.py --mode real --smoke --i-am-sure` (≤12 call, 1 call/route) →
bảng model | ok | tok | latency. Chưa có key → ghi "PENDING KEYS", đi tiếp.

## Phase 6 — Dashboard + video + phân tích
**Làm:** dashboard 6 tab (SPEC 10); render_video 9:16 + caption; session_report; analyze
(mobility matrix, β thừa kế, records, PNGs).
**Nghiệm thu:** `render_video mock300 --last-years 60 --out demo.mp4` → mp4 hợp lệ có
caption; dashboard mở đủ tab (tab Hợp đồng hiện mô-típ); `analyze mock300` →
`reports/final_analysis.md` + PNGs.

### ✅ TỔNG NGHIỆM THU MOCK (bắt buộc trước mọi call thật quy mô)
`pytest -q` xanh; mock300 full: audit 0 vi phạm, fallback < 5%, calibration đạt, video ok,
dashboard ok, analyze ok, replay --verify ok. Dán bảng tổng vào PROGRESS.md.

---

## 🔒 HUMAN-GATE 1 — trước Phase 7
Dừng. In: kết quả tổng nghiệm thu + hướng dẫn chủ dự án: (1) điền key `.env`; (2) mở 9router;
(3) rà `config/models.yaml`/`quotas.yaml` (ID model đã điền sẵn theo xác nhận: gemma-4-31b-it,
gemini-3.1-flash-lite, gc/gemini-3.1-flash-lite-preview, gc/gemini-2.5-flash,
gc/gemini-2.5-pro, gc/gemini-3-flash-preview — chỉ cần xác nhận đúng); (4) gõ "chạy Phase 7".

## Phase 7 — Pilot thật 20 năm (40 tick)
`run.py --mode real --years 20 --seed 42 --run-name pilot20 --until-budget --i-am-sure`.
**Nghiệm thu:** audit xanh; fallback_rate TỪNG model thật < 10% (model nào cao hơn → tinh
chỉnh prompt/schema cho model đó, chạy lại pilot); ≥2 mô-típ hợp đồng do LLM tự soạn (không
trùng mẫu khởi đầu); đọc 20 quyết định ngẫu nhiên: có lý & khác biệt theo persona; session
report token/call/key; clip pilot. Xuất `reports/pilot_review.md`.

## 🔒 HUMAN-GATE 2 — chủ dự án duyệt pilot, gõ "chạy run chính".

## Phase 8 — RUN CHÍNH 300 năm + phân tích + open source
Các phiên `--mode real --until-budget --run-name main300` (resume tự động, ~4–7 phiên tối);
mỗi phiên tự xuất report + clip đoạn mới. Kết thúc: analyze full; video final 9:16;
README open source (kiến trúc, cách chạy, giới hạn phương pháp luận: anachronism tri thức,
1 run = 1 lịch sử khả dĩ, công nghiệp hóa không bảo đảm by design, vùng xám quota);
so sánh main300 vs rb300; "10 phát hiện đáng chú ý" từ milestones + chronicle + mô-típ
hợp đồng do LLM phát minh (unrecognized_intents có gì thú vị thì đưa vào phần Phụ lục
"những điều agent muốn làm mà thế giới chưa cho phép").
