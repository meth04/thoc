# CLAUDE.md — Sổ tay vận hành dự án THÓC (dành cho Claude Code)

Dự án: **Thóc** — mô phỏng 300 năm (600 tick) của một nền kinh tế khép kín với 50 agent LLM
khởi đầu không giai cấp, không tiền, không nhà nước. Mọi định chế (giá cả, làm thuê, tín dụng,
ngân hàng, giai cấp) phải TỰ PHÁT SINH từ quyết định của agent.

> **⚠️ SUPERSEDED một phần (2026-07-12).** Hướng khoa học hiện hành do `docs/MODEL_CHARTER.md`
> và `docs/adr/0001-scope-and-institutional-layers.md` quyết định; khi tài liệu này mâu thuẫn
> với charter/ADR về *cấp độ claim* hoặc *định chế có tên*, **charter/ADR thắng**. Cụ thể:
> (a) điều luật #7 "cấm tuyệt đối định chế có tên" được thay bằng *cổng định chế minh bạch*
> (ADR §B); (b) tiêu chí "median công-nghiệp-hóa 160–280" ở §8 KHÔNG còn là tiêu chí khoa học
> (ADR §E, chỉ giữ như legacy label). Các điều luật bảo toàn/sổ kép/replay/policy-isolation
> vẫn là INVARIANT. `TASKS.md` là execution authority của phiên nghiên cứu hiện tại.

**Thứ tự đọc bắt buộc trước khi viết bất kỳ dòng code nào:**
1. `SPEC.md` — thiết kế đầy đủ (cái gì, tại sao, công thức, schema).
2. `PHASES.md` — thứ tự xây và tiêu chí nghiệm thu từng giai đoạn.
3. `config/*.yaml` và `.env.example` — mọi tham số nằm ở đây, không nằm trong code.

---

## 1. Môi trường

- Conda env tên **`thoc-env`**, Python 3.11. Nếu chưa có:
  `conda create -n thoc-env python=3.11 -y`
- Mọi lệnh chạy qua env này: `conda run -n thoc-env python ...`, `conda run -n thoc-env pytest -q`.
- Cài gói bằng pip bên trong env; duy trì `requirements.txt` (pin version).
  Gói lõi dự kiến: numpy, pandas, pyarrow, pydantic>=2, pyyaml, httpx, python-dotenv,
  json-repair, tenacity, pytest, hypothesis, ruff, rich, streamlit, matplotlib, pygame, imageio-ffmpeg.
- Gọi API bằng **httpx trực tiếp** (không dùng SDK nặng) — cả AI Studio lẫn 9router
  (endpoint OpenAI-compatible). Chi tiết trong SPEC mục 7.

## 2. Bảy điều luật bất khả xâm phạm

Vi phạm bất kỳ điều nào dưới đây = bug nghiêm trọng, dừng lại sửa ngay, không đi tiếp.

1. **Bảo toàn tài nguyên.** Tổng đất không đổi. Thóc chỉ sinh ra từ thu hoạch, chỉ mất đi qua
   tiêu thụ, hao hụt kho, và gieo giống. Module `audit` phải assert phương trình bảo toàn
   SAU MỖI TICK (SPEC mục 2.4). Assert fail → raise, checkpoint, dừng.
2. **Sổ kép.** Mọi dịch chuyển tài sản là một transaction có bên nợ + bên có, ghi vào ledger.
   Không có số dư âm (nợ là object riêng, không phải số âm).
3. **LLM không bao giờ chạm vào state.** LLM chỉ trả về ý định (intent). Engine validate theo
   whitelist hành động rồi mới thực thi. Intent không hợp lệ → bỏ qua + log, không lỗi.
4. **Tất định & tái lập.** Một cây RNG duy nhất (numpy Generator, spawn theo subsystem × tick).
   Cùng seed + cùng transcript LLM (replay từ log) → cùng world-hash. Có test chứng minh.
5. **Mock trước, thật sau.** `LLM_MODE=mock` là mặc định. Không một call API thật nào được phép
   xảy ra trước khi toàn bộ gate mock trong PHASES.md xanh. Mode real yêu cầu đồng thời
   `LLM_MODE=real` trong .env VÀ cờ `--i-am-sure` trên CLI.
6. **Ghi lại mọi vết tích.** `events.jsonl` append-only cho mọi sự kiện thế giới; bảng `llm_calls`
   cho mọi call (kể cả mock): model, key-hash, token vào/ra, latency, retry, fallback, raw response.
7. **Nguyên tắc tự phát.** Engine chỉ là VẬT LÝ + 3 NGUYÊN TỐ (hợp đồng, pháp nhân, sáng
   chế — SPEC mục 3). Cấm tuyệt đối:
   *(SUPERSEDED một phần — ADR 0001 §B: lệnh cấm tuyệt đối định chế có tên nay là **cổng định
   chế minh bạch** — module `credit/money/fiscal/government` được phép khi thỏa đủ 5 điều kiện
   alternative+cost+accounting+scenario-flag+ablation; anti-teleology vẫn giữ nguyên là INVARIANT.)*
   - **mã hóa định chế có tên thành cơ chế**: trong `engine/` không được tồn tại khái niệm
     bank/loan/company/insurance/wage như code riêng — chúng chỉ là TỔ HỢP điều khoản hợp
     đồng; tên định chế chỉ được xuất hiện trong `observatory/` (nhãn phân tích, chỉ đọc);
   - danh sách công nghệ/phát minh định sẵn hay thứ tự phát triển bắt buộc (R&D là đầu tư
     mở theo lĩnh vực, kết quả rút từ phân phối — xem `config/research.yaml`);
   - engine tự đặt giá hay "điều tiết" giá (giá chỉ từ khớp lệnh cung–cầu);
   - hardcode hành vi theo giai cấp ("địa chủ thì làm X");
   - gán sẵn nghề/vai trò cho agent cụ thể;
   - sự kiện kịch bản hóa (ngoại lệ duy nhất: thời tiết rút từ phân phối có seed);
   - âm thầm hạ tier model khi thiếu quota (thiếu thì dừng êm, không đánh tráo trí thông minh);
   - "sửa kết quả cho đẹp". Nếu nền kinh tế sụp đổ hay bất bình đẳng cực đoan, đó LÀ kết quả.

## 3. Kỷ luật kiểm thử

- Mỗi phase trong PHASES.md có lệnh nghiệm thu. **Không chuyển phase khi nghiệm thu chưa xanh.**
- Viết test cho invariant TRƯỚC khi viết engine (ledger, bảo toàn, auction dùng cả
  property-based test với hypothesis).
- Unit test dùng thế giới nhỏ (map 8×8, 10 agent, 20 tick) để chạy nhanh; integration test
  mới dùng cấu hình thật.
- Mock adversarial: MockLLM phải có chế độ cố tình trả JSON hỏng (p cấu hình được) để chứng minh
  pipeline sửa JSON cứu được ≥95% (SPEC mục 7.5). Đây là yêu cầu trực tiếp của chủ dự án:
  "mock test phải work thật tốt".
- Không nới lỏng test để cho qua. Nếu một test sai về bản chất, sửa test và ghi lý do vào
  `DECISIONS.md`.
- `ruff check .` sạch trước mỗi commit.

## 4. An toàn ngân sách & bí mật

- Bộ đếm RPM/RPD theo (provider × model × key) persist trong SQLite — restart không quên.
- Trước mỗi tick ở mode real: ước lượng số call cần; nếu ngân sách còn lại × safety_margin
  không đủ → checkpoint và dừng êm, in báo cáo. Không degrade, không cố.
- Không bao giờ in API key ra log/console/commit. Key chỉ hiện dạng hash 8 ký tự.
- `.env` nằm trong `.gitignore` ngay từ commit đầu tiên.
- Loader key phải đọc file `.env` trực tiếp bằng regex (SPEC 7.1) vì tên biến có gạch ngang
  (`GEMINI-API-KEY-1`) không hợp lệ với shell thông thường.

## 5. Quy ước code

- Python 3.11, type hints đầy đủ, pydantic v2 cho mọi schema (decision, policy card, config).
- Định danh code bằng tiếng Anh; docstring, log, prompt cho agent, chronicle bằng tiếng Việt.
- Không magic number trong code — mọi tham số đọc từ `config/*.yaml`.
- Không global mutable state. World là một object truyền tường minh.
- asyncio cho gateway; phần engine thuần là synchronous, đơn luồng, tất định.

## 6. Quy trình làm việc

- Làm tuần tự theo PHASES.md. Sau mỗi phase: chạy lệnh nghiệm thu, commit
  (`git commit -m "phase-N: ..."`), cập nhật bảng trạng thái trong `PROGRESS.md`
  (phase | trạng thái | lệnh nghiệm thu | kết quả chính | ngày).
- Gặp điểm SPEC chưa nói rõ: **tự quyết theo phương án đơn giản nhất còn đúng nguyên tắc
  tự phát**, ghi một dòng vào `DECISIONS.md`, đi tiếp. Không dừng lại hỏi.
- Chỉ dừng chờ con người tại các mốc đánh dấu **HUMAN-GATE** trong PHASES.md
  (trước khi đốt call API thật).
- Chạy dài (mock 300 năm) nên chạy nền và theo dõi bằng log; nếu quá 45 phút, tối ưu
  (tắt mô phỏng latency của mock, vector hóa phần engine) rồi chạy lại.

## 7. Cấu trúc repo chuẩn

```
thoc/
  engine/        # world, ledger(FlowRegistry), parcels, market(chợ generic), board(bảng rao),
                 # contracts(văn phạm+executor+cưỡng chế), entities(pháp nhân+cổ phần),
                 # research(sáng chế+khuếch tán), production, demography, health, education, audit
  minds/         # gateway, providers (aistudio, ninerouter, mock), keypool, budget,
                 # batching, prompts, schemas, policy_cards, triggers, memory
  observatory/   # classifier giai cấp, nhãn định chế, milestones, chronicle — CHỈ ĐỌC log
  tools/         # audit, replay, session_report, analyze (mobility matrix, gini, records)
  viz/           # dashboard (streamlit), render_video (pygame+ffmpeg), charts
  data/runs/<run_name>/   # world.sqlite, events.jsonl, llm_calls.sqlite, reports/, frames/
  config/        # world.yaml, models.yaml, quotas.yaml, research.yaml
  tests/
  run.py
  requirements.txt
  PROGRESS.md  DECISIONS.md  README.md
```

## 8. Định nghĩa hoàn thành tổng thể

1. `pytest` xanh toàn bộ; `ruff` sạch.
2. Run đối chứng rule-bot 300 năm: < 5 phút, bảo toàn xanh từng tick.
3. **Run mock 300 năm end-to-end hoàn chỉnh**: 50 agent → dân số tự biến động; hợp đồng,
   pháp nhân, cổ phần, sáng chế, thừa kế đều được exercise; fallback_rate < 5% với
   adversarial mock; ~~**hiệu chỉnh đạt: seed trung vị chạm nhãn công-nghiệp-hóa trong năm
   160–280**~~ *(SUPERSEDED — ADR 0001 §E: KHÔNG còn là tiêu chí khoa học; chỉ giữ như legacy
   regression label trên `preindustrial_closed_v1`, không áp cho `agrarian_transition_v1`)*;
   video MP4 render được từ log; dashboard mở được.
4. Chỉ sau đó mới đến smoke test thật (≤ 12 call) và HUMAN-GATE cho pilot thật.
