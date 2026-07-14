# ADR 0006 — Capability catalog, prompt-from-config, và run journal tái lập được (P0 của Report_v2)

- Status: **Accepted (design)** — 2026-07-13. Implementation PENDING (xem §8 Handoff).
- Deciders: spec-governor (tác giả). Independent review PENDING: `adversarial-reviewer`,
  `qa-verifier`, `reproducibility-steward`.
- Context sources (execution authority theo thứ tự): `CLAUDE.md`, `docs/MODEL_CHARTER.md`,
  `docs/adr/0001`–`0005`, `TASKS.md`, `REVIEW.md`, `Report_v2.md` (§2 luật thực thi, §4.5
  dynamic capability catalog, §5 P0, §6 test matrix, §7 rollout gates).
- Scope guard: **ADR này KHÔNG implement engine.** Nó chốt interface, state ownership,
  ledger/journal identity, invariant có test cưỡng chế, migration, ranh giới claim và handoff.
  Không mục nào ở đây là bằng chứng thực chứng; mọi tham số vẫn là `design_assumption`
  (charter §2).
- Quan hệ với ADR khác:
  - **Bổ sung** ADR 0001 §A (invariant), §B (cổng định chế), §D (determinism phủ state mới).
  - **Không thay** ADR 0002 (policy chỉ trả intent), ADR 0004.
  - **Sửa tàn dư mâu thuẫn tại chỗ** trong ADR 0005 §17/§18 (calendar — xem §D.2 dưới đây).
  - **Route sang ADR 0007 (PENDING)**: household/residence provisioning + estate lifecycle —
    ADR 0006 **KHÔNG** tự quyết (xem §D.3).

---

## 1. Context — sự thật nền đã xác minh (file:line + artifact)

Bản đồ mâu thuẫn dưới đây được verify trực tiếp trên working tree, không suy đoán.

### 1.1 Prompt nói SAI luật cho run spatial

| Sự thật | Bằng chứng |
|---|---|
| `LUAT_VAT_LY` là **string tĩnh hardcode**: `Mỗi tick = 6 tháng`, `90kg` (trẻ `45kg`), `180 ngày công`, "MÙA MƯA (tick lẻ)/MÙA KHÔ (tick chẵn)", `60kg thóc giống + 60 công`, `~650kg`, `Nhà = 8 gỗ + 240 CÔNG`, `hao 3%/tick`. | `minds/prompts.py:241-279` |
| Overlay spatial đặt: `thang_moi_tick: 4`, `lich_mua: [lua_1, lua_2, dong]`, `nguoi_lon_kg_tick: 60`, `tre_em_kg_tick: 30`, `ngay_cong_moi_tick: 120`, `giong_kg_moi_thua: 40`, `cong_moi_thua: 40`, `san_luong_goc_kg: 300`, `homestead_tick_lien_tiep: 4`, `hao_hut_kho_moi_tick: 0.0201`. | `scenarios/agrarian_transition_v1/spatial_v1.yaml:14-31` |
| Prompt được ghép từ hằng số này cho **mọi** scenario (không đọc `w.cfg`). | `minds/prompts.py:231-238` (`schema_quyet_dinh`), `build_agent_prompt` |

⇒ Trong `real60_spatial`, agent LLM nhận **luật vật lý sai** ở gần như mọi hằng số quyết định
(khẩu phần, ngày công, giống, sản lượng, lịch mùa). Không được diễn giải hành vi của run đó
như "LLM chọn sai" khi input mô tả một thế giới khác thế giới đang chạy.

### 1.2 Capability mồ côi (engine làm được, LLM không gọi được)

| Action | Engine | LLM path |
|---|---|---|
| `dong_thuyen`, `rao_do`, `qua_song` | Field CÓ ở `engine/intents.py:50-52`; executor CÓ ở `engine/spatial.py:112` `buoc_qua_song` (+ `_dong_thuyen` `:95`) | **KHÔNG** trong `minds/schemas.py:14` `LOAI_HANH_DONG`; **KHÔNG** có handler trong `minds/translate.py:183` `_mot_hanh_dong`; **KHÔNG** trong `minds/prompts.py:169` `MUC_HANH_DONG` |
| `khai_hoang` | Field `engine/intents.py:54`; schema CÓ (`schemas.py:18`); translate CÓ (`translate.py:208`) | **KHÔNG** có trong menu `MUC_HANH_DONG` ⇒ agent không biết action tồn tại |
| Tài sản trong `dat_lenh` | World có `ngo`,`khoai`,`ga`,`ga_con`,`thit`,`ca`,`thuyen` | Menu hardcode `"go|cong_cu|quang_dong|xu|nha|thoc|co_phan:E0001|<mã hàng>"` — `prompts.py:181-182` |

⇒ "Không có ai làm nghề đò / không ai khai hoang / chợ chỉ có gỗ" trong `real60_spatial`
**không phải** bằng chứng về lựa chọn của agent. Đó là bằng chứng về interface thiếu.

### 1.3 Journal không resume-safe ⇒ artifact không đạt cổng replay của chính dự án

| Sự thật | Bằng chứng |
|---|---|
| Resume nạp checkpoint tick N nhưng **không** đưa journal về trạng thái tick N | `run.py:206-224` (nạp `checkpoint_moi_nhat.json` → `World.nap_checkpoint`; không truncate/segment `events.jsonl`, `transcript.jsonl`, `llm_calls.sqlite`) |
| `EventLog` mở `"a"`, không có id/sequence | `engine/events.py:16,18-22` |
| `TranscriptWriter` mở `"a"` nhưng `self._n = 0` ⇒ **call_id lặp lại từ 1** sau resume | `minds/transcript.py:51-52,63,66` |
| `metrics.jsonl` được **ghi đè** cuối run từ `w.metrics_lich_su` (không phải journal append-only) | `run.py:274-276` |
| `llm_calls.call_id` là AUTOINCREMENT (unique) nhưng **không có** `segment_id`/`superseded` ⇒ call của đoạn bị bỏ vẫn tính vào thống kê | `minds/gateway.py:45-63` |
| `tools.verify_research_run` **bỏ qua replay cho mode real** | `tools/verify_research_run.py:200-201` (`elif mode not in ("rulebot","mock"): SKIP`) |
| `tools.replay --from-transcript --verify` ĐÃ fail khi `misses`/`unused` — nhưng không ai gọi nó cho real | `tools/replay.py:58-61` |

**Audit artifact (chỉ đọc, không sửa, không mạng)** —
`conda run -n thoc-env python <scratch>/audit_journal.py` trên `data/runs/real60_spatial/`:

```
events:      179 distinct ticks, max tick 180
             230 exact duplicate event lines; 1 tick regression tại dòng 4158 (tick 117 → 106)
metrics:     180 rows, 180 distinct, contiguous (vì được ghi đè cuối run, không phải journal)
transcript:  1595 rows, 1192 distinct call_id, 403 call_id BỊ DÙNG LẠI
llm_calls:   1589 rows, 1589 distinct call_id, tick 1..180
```

⇒ Diễn giải tất định: run bị ngắt ở tick 117, resume từ checkpoint tick 105, chạy lại 106–117.
Đoạn tail cũ **vẫn nằm trong journal** (230 event trùng, 403 call_id trùng); transcript
(1595) ≠ llm_calls (1589). Vì vậy `replay --from-transcript` báo `misses`/`unused` và lệch hash
— đúng như `Report_v2.md` §3 ghi. Đây là **lỗi hạ tầng artifact**, không phải phát hiện khoa học.

### 1.4 Documentation drift nhỏ (ghi nhận, không cần banner)

`minds/schemas.py:13` vẫn ghi comment "15 nguyên tố hành động (SPEC 5)" trong khi
`LOAI_HANH_DONG` đã có 35 mục. Registry ở §A sẽ là nơi đếm/khai báo duy nhất; docstring cũ
được cập nhật khi implement (không phải mâu thuẫn spec cần supersession).

---

## 2. Nguyên tắc chi phối (kế thừa, KHÔNG nới)

Mọi quyết định dưới đây phải giữ nguyên các INVARIANT của `CLAUDE.md` §2 + charter §3 +
ADR 0001 §A:

1. Bảo toàn tài nguyên + audit mỗi tick.
2. Sổ kép, không số dư âm.
3. **LLM/policy chỉ trả intent; engine là chủ duy nhất của state mutation.**
4. Tất định & replay: một cây RNG; cùng seed + cùng transcript ⇒ cùng `world_hash`.
5. Mock trước, thật sau; ghi mọi vết tích.
6. **Anti-teleology** (charter §5, ADR 0001 §C): không ngưỡng/nhãn/năm nào TRỰC TIẾP tạo định
   chế; không gán nghề; không xếp hạng sinh kế.

ADR 0006 **thêm** ba invariant (§A.3, §B.2, §C.5) và **không nới** invariant nào.

---

## A. Capability descriptor registry — single source of truth cho một action

### A.1 Quyết định

Tạo module **MỚI `minds/capabilities.py`**. Mỗi action được khai báo **ĐÚNG MỘT LẦN** bằng một
descriptor bất biến (frozen dataclass / pydantic v2 model) với các trường **bắt buộc**:

| Trường | Nghĩa | Ai đọc |
|---|---|---|
| `ten` | tên action (`"qua_song"`) — khóa duy nhất trong catalog | tất cả |
| `kehoach_field` | tên field trên `engine.intents.KeHoach` mà action này ghi vào | translate, test |
| `schema_fields` | tên + kiểu tham số JSON mà LLM được phép gửi | `minds/schemas.py` |
| `to_kehoach` | hàm QuyetDinh(JSON đã validate) → mutate `KeHoach` | `minds/translate.py` |
| `from_kehoach` | hàm `KeHoach` → QuyetDinh JSON (chiều ngược, cho PersonaBot/roundtrip) | `minds/translate.py` |
| `engine_handler` | tham chiếu **tên** bước engine tiêu thụ field (vd `engine.spatial.buoc_qua_song`) | test (không import ngược) |
| `kha_dung(w) -> bool` | availability predicate: scenario flag + điều kiện vật lý/vai trò | prompts (render), test |
| `mau_prompt(w) -> str` | render một dòng menu **thuần dữ kiện** từ `w.cfg` | prompts |
| `ma_ket_qua` | tập outcome/reason code hợp lệ (`ok`, `thieu_cong`, `khong_co_thuyen`, ...) | engine, metrics, feedback |
| `cong_khai` | `True` = action agent gọi được; `False` = field engine-owned (không quảng cáo) | test |

**Hướng import (không vòng):** `minds/capabilities.py` → chỉ import `engine.intents`/`engine.world`
(type) + stdlib. `minds/schemas.py`, `minds/translate.py`, `minds/prompts.py` **import từ**
`capabilities`. Cụ thể `schemas.LOAI_HANH_DONG` trở thành *derived*:
`LOAI_HANH_DONG = frozenset(c.ten for c in CATALOG if c.cong_khai)` — giữ nguyên tên public để
không phá import hiện có (`minds/translate.py:17`).

**Vì sao KHÔNG nhồi vào `prompts.py`:** (a) `prompts.py` là *renderer* và bị băm thành
`prompt_template_hash` (`run.py:63-64`) — trộn interface vào đó làm mọi thay đổi câu chữ trông
như thay đổi interface; (b) `schemas.py` không được phép import `prompts.py` (prompts import
`engine.world`, sẽ tạo phụ thuộc nặng cho lớp schema); (c) registry là hợp đồng chung của ba
module, không thuộc riêng module nào.

### A.2 Catalog KHÔNG vào `world_hash`; catalog hash vào manifest

- **KHÔNG vào `world_hash`.** Catalog là *interface/code*, không phải state của thế giới. Đưa nó
  vào hash sẽ phá `world_hash` của mọi run legacy mà không thêm bảo đảm nào (charter §3 D:
  state ảnh hưởng hành vi phải vào hash **hoặc** có artifact version rõ ràng — ta chọn vế sau,
  đúng tiền lệ `prompt_template_hash`).
- **CÓ vào manifest**: thêm `reproducibility.capability_catalog_hash` =
  `sha256(canonical_json([{ten, kehoach_field, schema_fields, ma_ket_qua, kha_dung_key,
  mau_prompt_template} for c in sorted(CATALOG)]))`.
  - Băm **nội dung khai báo**, không băm file ⇒ refactor thuần (đổi thứ tự, đổi docstring) KHÔNG
    làm đổi hash; đổi *interface* (thêm/bớt action, đổi tham số, đổi câu render) thì ĐỔI hash.
  - Replay verify (§C.4) so `capability_catalog_hash` của code hiện tại với manifest ⇒ **prompt
    identity kiểm chứng được**, không còn phải tin "prompt chắc giống".
- Test bắt buộc: render/serialize catalog **không mutate World** (snapshot `world_hash()`
  trước/sau — cùng khuôn với ADR 0002 §A.1 no-mutation test).

### A.3 INVARIANT MỚI (test-enforced) — không có capability mồ côi

Đặt tên **CAP-1..CAP-4**. Test phải **FAIL** (không warn, không skip) khi vi phạm:

- **CAP-1 (bốn chân đủ):** mọi descriptor `cong_khai=True` phải có đồng thời: entry trong
  `LOAI_HANH_DONG`, `to_kehoach` + `from_kehoach` chạy được (roundtrip), `mau_prompt` render
  được, và `engine_handler` tồn tại (import được bằng tên).
- **CAP-2 (không field mồ côi):** mọi field của `engine.intents.KeHoach` phải hoặc (a) được một
  descriptor khai báo qua `kehoach_field`, hoặc (b) nằm trong allowlist tường minh
  `FIELD_KHONG_PHAI_ACTION` **kèm lý do** (vd `id`, field do policy-card điều khiển). Test đọc
  `dataclasses.fields(KeHoach)` ⇒ **thêm field mới mà quên khai báo là FAIL**. Đây chính là cái
  bắt được `dong_thuyen`/`rao_do`/`qua_song` hôm nay.
- **CAP-3 (không quảng cáo hàng không có):** menu render cho một `w` chỉ chứa action có
  `kha_dung(w) == True`; và mọi action `kha_dung(w) == True` phải xuất hiện trong menu. Test chạy
  với **base config** và với **overlay `spatial_v1`** (đò/khai hoang/vụ đông/chăm trẻ chỉ hiện khi
  ON).
- **CAP-4 (anti-teleology gate — điều kiện gate của ADR này):** descriptor mô tả *khả thi + chi
  phí + điều kiện + mã kết quả*. **TUYỆT ĐỐI KHÔNG** có: điểm ưu tiên, xếp hạng lợi nhuận, gợi ý
  "action nào tốt hơn", nhãn nghề, tính từ chuẩn tắc. Test mở rộng bộ chặn hiện có
  (`tests/test_prompt_ky_luat.py:22-25`: `TU_MOM`, `TEN_DINH_CHE_CAM`) sang **toàn bộ text render
  từ catalog**, và giữ nguyên cơ chế xáo menu theo `w.rng` (`menu_xao`, DECISIONS 2026-07-12 mục
  P5) để vị trí liệt kê không mớm ưu tiên.

### A.4 Cái gì KHÔNG đổi

- `KeHoach` là dataclass engine-owned; capability registry **không** thêm field nào vào nó trong
  P0 (chỉ *khai báo* field đã có). Thêm capability mới = việc của P1–P3.
- Engine vẫn validate lần cuối (điều luật #3): descriptor **không** thay thế validator engine.
- Rulebot/policy (`minds/policies.py`, `minds/rulebot.py`) **không** phụ thuộc catalog trong P0 ⇒
  `world_hash` của mọi run rulebot legacy bất biến.

---

## B. Prompt render từ config đang chạy, không từ hằng số

### B.1 Quyết định

`LUAT_VAT_LY: str` (hằng, `minds/prompts.py:241`) trở thành **hàm**
`luat_vat_ly(w: World) -> str` (giữ tên module-level cũ như alias chỉ khi cần cho tool đọc, nhưng
mọi call-site đọc `w.cfg`). Bảng parity bắt buộc (mọi giá trị đọc từ config, không hằng trong
code):

| Nội dung prompt | Khóa config |
|---|---|
| tháng/tick, tick/năm, tên mùa | `thoi_gian.thang_moi_tick`, `thoi_gian.lich_mua` |
| khẩu phần người lớn/trẻ em, ngày công | `nhu_cau.nguoi_lon_kg_tick`, `.tre_em_kg_tick`, `.ngay_cong_moi_tick` |
| giống/công/sản lượng mỗi thửa | `san_xuat.giong_kg_moi_thua`, `.cong_moi_thua`, `.san_luong_goc_kg` |
| hao kho | `san_xuat.hao_hut_kho_moi_tick` |
| homestead ngưỡng | `san_xuat.homestead_tick_lien_tiep` |
| recipe nhà/công cụ/máy/thuyền | `san_xuat.recipe.*` |
| tuổi lao động/nghỉ, chăm trẻ | `lao_dong_theo_tuoi.*`, `khong_gian.cham_tre.*` (khi ON) |
| cá, gà rừng, đất bạc màu, tay nghề | `danh_ca.*`, `chan_nuoi.*`, `khong_gian.ga_rung.*`, `dat_dai.*` |
| vụ đông (cây/công/sản lượng) | `khong_gian.vu_dong.cay.*` |
| đò (capacity/hao mòn) | `khong_gian.do.*` |

Menu hành động + danh sách tài sản `dat_lenh` được render từ **catalog (§A)** + tài sản thật của
world (`w.ten_hang` + asset đang có sổ dư/được phép giao dịch), không hardcode.

### B.2 INVARIANT MỚI — PROMPT-1 (prompt-config parity)

Prompt **không được chứa hằng số vật lý nào không đọc từ config đang chạy**. Cưỡng chế bằng hai
test (test-engineer, độc lập):

1. **Parity table test:** render prompt thật (`build_agent_prompt`) với
   (a) **base config** ⇒ phải nói `6 tháng`, `90kg`, `45kg`, `180` công, `60kg` giống, `650kg`,
       nhà `240` công (đúng như hôm nay — legacy không được đổi nghĩa);
   (b) **overlay `spatial_v1`** ⇒ phải nói `4 tháng`, `60kg`, `30kg`, `120` công, `40kg` giống,
       `300kg`, ba mùa `lua_1`/`lua_2`/`dong`, và có mặt đò/khai hoang/vụ đông trong menu.
2. **Property test (chống hardcode tái phát):** với mỗi khóa trong bảng parity, đổi giá trị trong
   cfg ⇒ text prompt render **phải khác**. Khóa nào đổi mà prompt không đổi = còn hằng số chết.

Giữ nguyên (không nới) các test kỷ luật prompt đang có: không từ mớm ý
(`nên/hãy/khôn ngoan/đáng`), không tên định chế — `tests/test_prompt_ky_luat.py:34-67`.

### B.3 Migration & compatibility

- Sửa `minds/prompts.py` ⇒ `prompt_template_hash` (`run.py:59-64`, `sha256_file(prompts.py)`) ĐỔI
  ⇒ manifest của **run MỚI** khác run cũ. **Run cũ KHÔNG bị retcon**: manifest cũ giữ nguyên hash
  cũ + `git_revision` cũ (`tools/experiments.py:117-133`).
- **Rulebot không dùng prompt** ⇒ `world_hash` của `preindustrial_closed_v1` và mọi run rulebot
  **bất biến**. Mock (PersonaBot) quyết định từ `ctx`, không từ text prompt ⇒ `world_hash` mock
  cũng bất biến; chỉ token-count log thay đổi.
- **Ranh giới thật thà (phải nói ra):** transcript replay khóa theo `prompt_hash`
  (`minds/transcript.py:40-42`). Đổi prompt ⇒ **transcript CŨ không replay được bằng code MỚI**.
  ADR này **không hứa** cross-version transcript replay. Thay vào đó §C.4 bắt tool **fail loud**:
  khi `prompt_template_hash`/`capability_catalog_hash`/`config_sha256` của code hiện tại ≠
  manifest, verify trả `replay_status = skipped_version_mismatch` và **FAIL** (không im lặng PASS,
  cũng không giả vờ FAIL nội dung). Run cũ vẫn citable ở đúng cấp `diagnostic` (§C.6).
- `tools/reality_check.py` và test đang import `LUAT_VAT_LY`/`MUC_HANH_DONG` như hằng
  (`tests/test_prompt_ky_luat.py:12-18`) ⇒ phải chuyển sang hàm render. Đây là công việc trong
  scope P0, không phải nới test.

---

## C. Run journal manifest + resume-safe segments

### C.1 Quyết định: **(a) truncate tail an toàn**, KHÔNG dùng segment ẩn trong reader

Chọn **(a)**: khi resume từ checkpoint tick N, mọi journal được đưa về **đúng prefix tại tick N**
(byte-offset đã ghi lúc checkpoint), phần tail bị bỏ được **bảo tồn ra chỗ khác** (không xóa) rồi
mới ghi tiếp.

**Vì sao (a) chứ không (b) "segment tường minh + reader bỏ qua":**

1. **Khép kín cho consumer duy nhất quan trọng:** `tools.replay --from-transcript` tiêu thụ
   transcript như một **stream tuyến tính** (`TranscriptReader` nạp toàn file → FIFO theo
   `prompt_hash`, `minds/transcript.py:93-117`). Với (b), MỌI reader (replay, verify, telemetry,
   analyze, viz, metrics) phải học ngữ nghĩa segment; quên một chỗ là im lặng sai số.
   Với (a), reader không đổi và `con_lai() == 0` trở thành một bất biến kiểm được.
2. **Kiểm chứng rẻ và mạnh:** prefix có `sha256` ⇒ "journal đúng bằng trạng thái checkpoint" là
   một phép so hash, không phải một phép suy luận.
3. **Không mất bằng chứng:** phần tail bị bỏ **không bị xóa** — nó được chuyển sang
   `data/runs/<run>/discarded/` kèm audit record (§C.3). Điều đó thỏa yêu cầu "không xóa lịch sử
   khó chịu" mà vẫn giữ journal chính khép kín.
4. **Cái bị bỏ là công đã sẽ được tính lại tất định** (tick N+1..M được chạy lại từ cùng
   checkpoint + cùng transcript/seed), không phải dữ liệu khoa học độc nhất.

**Ngoại lệ có chủ ý — `llm_calls.sqlite` KHÔNG bị truncate.** Những call đó **đã thực sự xảy ra và
đã thực sự tốn tiền**; xóa chúng là làm đẹp chi phí. Thay vào đó thêm cột `segment_id INTEGER` và
`superseded INTEGER DEFAULT 0`; khi resume, các row có `tick > checkpoint_tick` của segment trước
được `superseded = 1` bằng một câu lệnh có audit record. Telemetry báo **cả hai**:
`call_effective` (superseded=0, dùng cho thống kê run) và `call_burned` (tất cả, dùng cho chi phí).

### C.2 Schema `RunJournalManifest`

File **MỚI** `data/runs/<run>/journal_manifest.json`, ghi **atomically** ở mỗi checkpoint sau khi
`flush()` mọi journal. Owner: **`tools/journal.py` (module MỚI)** — KHÔNG nhồi vào `engine/world.py`
(journal là artifact của run, không phải state của thế giới; giữ engine sạch để journal nằm ngoài
`world_hash`).

```jsonc
{
  "schema_version": "journal-1",
  "run_uuid": "e3b0c442-...",          // sinh MỘT LẦN khi tạo run; cũng ghi vào experiment_manifest
  "segment_id": 2,                      // tăng 1 mỗi lần resume
  "checkpoint_tick": 105,
  "identity": {                         // để phát hiện version drift khi resume/replay
    "config_sha256": "...",
    "prompt_template_hash": "...",
    "capability_catalog_hash": "...",
    "git_revision": "..."
  },
  "journals": {
    "events.jsonl":     {"byte_offset": 1234567, "record_count": 4041, "sha256_prefix": "..."},
    "metrics.jsonl":    {"byte_offset":  456789, "record_count":  105, "sha256_prefix": "..."},
    "transcript.jsonl": {"byte_offset":  987654, "record_count": 1192, "sha256_prefix": "..."},
    "llm_calls.sqlite": {"max_call_id": 1421,    "record_count": 1421, "sha256_prefix": null}
  },
  "segments": [                          // append-only lịch sử, KHÔNG rewrite
    {"segment_id": 1, "start_tick": 0,   "end_tick": 117, "status": "closed_truncated_to_105",
     "discarded": ["discarded/events_seg1_t106-117.jsonl", "discarded/transcript_seg1_t106-117.jsonl"]},
    {"segment_id": 2, "start_tick": 105, "end_tick": null, "status": "active"}
  ]
}
```

- SQLite không có byte-offset ổn định ⇒ dùng `max_call_id` + `record_count` (call_id là
  AUTOINCREMENT, `minds/gateway.py:46`).
- `experiment_manifest.json` thêm: `run.run_uuid`, `reproducibility.capability_catalog_hash`.
  Trường mới, optional-với-manifest-cũ (verify coi thiếu = legacy, xem §C.6).

### C.3 Identity của bản ghi journal

| Journal | Quyết định | Chỗ sửa |
|---|---|---|
| `events.jsonl` | thêm `seq` **đơn điệu, duy nhất toàn run** (khởi tạo từ `record_count` khi resume). INVARIANT: `seq` tăng nghiêm ngặt, không gap, không lặp. | `engine/events.py:16-22` (`EventLog` nhận `start_seq`) |
| `metrics.jsonl` | trở thành **append-only journal ghi mỗi tick** (bỏ ghi đè cuối run). INVARIANT: mỗi tick xuất hiện **đúng một lần**, tăng dần. | `run.py:274-276` (bỏ rewrite), ghi trong vòng tick |
| `transcript.jsonl` | `call_id` **duy nhất toàn run**: `TranscriptWriter(path, start_call_id=N)`; thêm `run_uuid` + `segment_id` vào mỗi row (forensic; khóa replay **vẫn là `prompt_hash`**). | `minds/transcript.py:48-52,63-80` |
| `llm_calls.sqlite` | `call_id` đã unique; thêm `segment_id`, `superseded`; **không xóa row**. | `minds/gateway.py:44-63` |

### C.4 Fail-closed + cổng replay bắt buộc

- **Resume:** `tools.journal.restore(run_dir, tick)` verify từng journal: kích thước ≥
  `byte_offset` **và** `sha256(prefix)` khớp **và** `identity` khớp code/config hiện tại. **Bất kỳ
  sai lệch nào ⇒ run DỪNG** (`SystemExit` có mã lỗi rõ), **không mutate gì cả**. Không có nhánh
  "bỏ qua cho chạy".
- **Recovery chỉ qua lệnh explicit:** `python -m tools.journal --repair <run> --confirm` — thực
  hiện truncate + move tail sang `discarded/` + ghi **`journal_recovery.jsonl`** (append-only:
  utc, actor, run_uuid, from_tick, bytes_truncated, files_moved, lý do). Không có tự-sửa ngầm.
- **Cổng replay (hard):** `tools.replay --from-transcript --verify` PASS ⟺
  `misses == 0` **AND** `unused (con_lai()) == 0` **AND** `world_hash == manifest.outcome.world_hash`
  **AND** identity khớp (`config_sha256`, `prompt_template_hash`, `capability_catalog_hash`).
  (Ba điều kiện đầu đã có ở `tools/replay.py:58-61`; điều kiện identity là MỚI.)
- **`tools.verify_research_run` chạy cổng này cho `real`, không mạng:** **BỎ HẲN** nhánh
  `elif mode not in ("rulebot","mock"): SKIP` (`tools/verify_research_run.py:200-201`). Mode real ⇒
  chạy `_replay_tu_transcript` với `TranscriptProvider` (không provider, không key, không network —
  `minds/transcript.py:120-151`), kết quả là **hard check**.
  Thêm hard check: `journal_continuity` (seq/tick/call_id unique + khớp `journal_manifest`).
  *(Defect kèm theo, cùng file, trong scope: `tools/verify_research_run.py:240` unpack 3 phần tử
  từ `Ket.items` vốn là 4-tuple ⇒ `--json` crash. Sửa khi đụng file.)*

### C.5 INVARIANT MỚI — JOURNAL-1..3

- **JOURNAL-1 (resume ≡ liền mạch):** run FakeTransport chia hai phiên (ngắt + resume) phải cho
  **cùng `world_hash`**, cùng tập event (bỏ qua `seq` gán lại), transcript **tiêu thụ đúng hết**,
  `call_id` duy nhất, metric tick duy nhất — y hệt run liền một mạch.
- **JOURNAL-2 (fail-closed):** journal lệch checkpoint (offset hỏng / file bị cắt / identity khác)
  ⇒ resume **DỪNG**, không ghi thêm byte nào.
- **JOURNAL-3 (không xóa lịch sử):** mọi tail bị bỏ phải tồn tại trong `discarded/` + một dòng
  `journal_recovery.jsonl`. Test: sau repair, tổng số record (chính + discarded) ≥ trước repair.

### C.6 `world_hash` KHÔNG đổi + migration artifact cũ

- **Journal nằm ngoài `world_hash`** — verify tại `engine/world.py:460-469`
  (`behavioral_state()` docstring: *"Không đưa event journal, metric history, transaction journal,
  cache thuần đọc và observation state vào đây"*), và `world_hash()` băm đúng
  `behavioral_state()` (`engine/world.py:572-584`); DECISIONS 2026-07-13 `behavioral-state-v2`.
  ⇒ Thêm `seq` vào event, đổi cách ghi `metrics.jsonl`, thêm cột SQLite **KHÔNG đụng hash struct**
  ⇒ **mọi test replay legacy phải vẫn xanh** (điều kiện gate của §C).
- **Artifact cũ KHÔNG được sửa/retcon.** `data/runs/real60_spatial/` giữ nguyên từng byte
  (events/transcript/llm_calls/checkpoints/manifest). Không chạy `--repair` lên nó.
- **Nhãn đặt ở đâu:**
  1. **Output của `tools.verify_research_run`**: thêm field `artifact_status` ∈
     {`replay_verified`, `diagnostic_only_unreplayable`, `pending_verification`,
     `skipped_version_mismatch`} — **tính toán tại chỗ, không ghi vào run dir**.
  2. **Một dòng trong ledger artifact**: `docs/reviews/artifact_ledger.md` (file MỚI, owner
     `research-artifact-integrity-auditor` + `reproducibility-steward`), mỗi run một hàng:
     run | mode | ngày | status | lý do | lệnh verify | verdict.
     `real60_spatial` ⇒ `diagnostic_only_unreplayable` (lý do: journal tail chưa truncate ở resume
     tick 105→117; 403 call_id lặp; prompt/catalog identity khác code sau P0).
  3. **Một dòng trong `DECISIONS.md`** (đã thêm cùng ADR này).
  Manifest cũ trong `data/runs/real60_spatial/` **KHÔNG** được ghi đè để nhét nhãn vào.
- Mọi trích dẫn số liệu từ run đó phải kèm nhãn
  `diagnostic observation from an unreplayable run` (Report_v2 §3). Không dùng làm bằng chứng về
  hành vi LLM, collapse, hay so sánh model/provider.

---

## D. Mâu thuẫn xử lý tường minh

### D.1 `CLAUDE.md` §2 #7 (cấm tuyệt đối định chế có tên) vs charter §5 (cổng định chế)

- Hai bên: `CLAUDE.md` §2 điều luật #7 ("trong `engine/` không được tồn tại khái niệm bank/loan/
  company/insurance/wage") vs `docs/MODEL_CHARTER.md` §5 (cổng 5 điều kiện) +
  `docs/adr/0001-scope-and-institutional-layers.md` §B.
- **Ai thắng:** charter §5 + ADR 0001 §B (đã supersede; `CLAUDE.md` đã có banner tại chỗ).
  **Không có phán quyết mới ở đây.**
- **Xác nhận cho ADR 0006:** capability registry **KHÔNG tạo mâu thuẫn mới** — nó là *interface*
  khai báo các action **vật lý đã có trong engine** (đóng thuyền, qua sông, khai hoang, canh vụ
  đông), không phải một *định chế*. Nó không thêm code `bank/loan/wage`, không gán nghề, không xếp
  hạng sinh kế. Ràng buộc này được cưỡng chế bằng **CAP-4** (§A.3). Nhãn "lái đò/địa chủ/thợ" vẫn
  chỉ tồn tại ở observatory (Lớp-5, chỉ đọc) — như ADR 0005 §14 đã chốt.
- Migration: không. Không sửa `CLAUDE.md`.

### D.2 ADR 0005: §8 (3 mùa, hiện hành) vs tàn dư §17/§18 ("GIỮ 2 tick/năm")

- Hai bên:
  - `docs/adr/0005-spatial-livelihood-economy.md:246-268` §8 — có banner **SUPERSEDED (2026-07-13)**;
    quyết định hiện hành: overlay `spatial_v1` dùng **3 mùa × 4 tháng** `[lua_1, lua_2, dong]`;
    base/legacy **không nạp overlay** giữ đúng 2 tick/năm.
  - `docs/adr/0005:542` §17 — "Vụ đông (ngô/khoai) mùa khô — **GIỮ 2 tick/năm** (không đổi đơn vị
    thời gian)."
  - `docs/adr/0005:557` §18 handoff — "Vụ đông **GIỮ 2 tick/năm** (§8)."
  - Code hiện hành đứng về phía §8: `scenarios/agrarian_transition_v1/spatial_v1.yaml:14-16`
    (`thang_moi_tick: 4`, `lich_mua: [lua_1, lua_2, dong]`), và `run.py:177-179` tính
    `tick_moi_nam` từ config.
- **Phán quyết:** **§8 (bản 2026-07-13) THẮNG.** §17/§18 là **tàn dư của bản thiết kế đầu**. Được
  đánh dấu SUPERSEDED **tại chỗ** (không xóa chữ, giữ lịch sử) trỏ về §8 + ADR 0006 §D.2.
- **Vì sao §8 thắng:** (i) nó là bản sửa sau, có banner, và đã được implement + regression test
  (calendar `lua_1,lua_2,dong`, weather-theo-năm, tuổi +1 sau 3 tick, legacy 2-tick bất biến);
  (ii) `DECISIONS.md` 2026-07-13 ghi rõ "Supersede riêng calendar của `spatial_v1`"; (iii) giữ
  §17/§18 làm luật sẽ mâu thuẫn trực tiếp với file config đang chạy.
- **Hệ quả cho §B:** prompt renderer **không được** giả định 2 tick/năm **hay** 3 mùa — nó đọc
  `thoi_gian.thang_moi_tick` + `thoi_gian.lich_mua`. Đây chính là lý do §B tồn tại.
- Migration: chỉ sửa banner trong ADR 0005 (đã làm cùng ADR này). Không đụng code/hash.

### D.3 ADR 0003 §A.2 ("KHÔNG thêm pantry chung") vs Report_v2 §4.2 (residence/household có ledger)

- Hai bên:
  - `docs/adr/0003-household-market-land.md:68-79` §A.1–A.2: hộ là **derived read-only view**
    (`engine/economy.py:15` `households`, `engine/world.py:276` `ho_cua`); **KHÔNG** pantry chung;
    *"Nếu tương lai cần pantry, nó **phải** là chủ thể ledger tường minh với transfer vào/ra
    explicit (PENDING, cần **ADR riêng** + engine-surgeon)"*.
  - `Report_v2.md` §4.2: residence/household là **state bền** có provisioning + lifecycle; hoặc
    (A) pantry account có ledger transfer, hoặc (B) tài sản cá nhân + event provisioning tường
    minh; **cấm** helper read-only ngầm tiêu thóc người khác. Cộng thêm estate lifecycle thay cho
    `VO_THUA_NHAN` làm ví vĩnh viễn.
- **Phán quyết:** **KHÔNG MÂU THUẪN VỀ LUẬT, chỉ mâu thuẫn về thời điểm.** Report_v2 là execution
  authority về *phạm vi và thứ tự*; ADR 0003 §A.2 đặt *tiền điều kiện thủ tục* ("cần ADR riêng").
  Cả hai đều được tôn trọng nếu ta **route** thay vì tự quyết.
- **Quyết định của ADR 0006:** ADR 0006 **KHÔNG** quyết (A) hay (B), **KHÔNG** đụng
  `World.ho_cua`/`economy.households`/`VO_THUA_NHAN`, và **CẤM** P0 thêm capability provisioning
  hộ vào catalog. Thay vào đó:
  > **P1 PHẢI có ADR successor: `docs/adr/0007-residence-household-estate.md`** — tác giả
  > `household-demography-specialist` + `model-architect`; reviewer độc lập `engine-surgeon`,
  > `test-engineer`, `reproducibility-steward`. ADR 0007 phải chốt: chọn (A) hay (B) + lý do;
  > state owner; ledger identity của mọi transfer; lifecycle (cưới/tách hộ/di cư/nhận nuôi/chết/
  > tái hôn); estate claim/auction/commons + số phận `VO_THUA_NHAN`; `world_hash`/checkpoint
  > migration; test matrix; và **supersession link tường minh tới ADR 0003 §A.2**.
- Cho tới khi ADR 0007 được Accept: **không** engine change nào cho household/estate. (`real60_spatial`
  case A0051 chết trẻ trong khi cha mẹ còn thóc vẫn là **diagnostic**, chưa được dùng làm bằng chứng
  về mortality/welfare — Report_v2 §3.)

### D.4 `CLAUDE.md` §8 "median công-nghiệp-hóa 160–280"

- Đã **superseded** bởi ADR 0001 §E (chỉ còn là *legacy regression label* trên
  `preindustrial_closed_v1`, không áp cho `agrarian_transition_v1`); `CLAUDE.md` §8 đã mang banner
  tại chỗ. **Chỉ xác nhận, không hành động, không sửa file.**

---

## 5. Cái gì KHÔNG đổi (chống scope creep)

- `world_hash` struct: **không đổi** (§C.6). Mọi test replay/hash legacy phải vẫn xanh — đây là
  điều kiện dừng của P0.
- Engine physics/accounting: **không đổi**. Không thêm/bớt action, không đổi recipe, không đổi
  ledger flow. (Phủ `dong_thuyen`/`rao_do`/`qua_song` qua schema/translate/menu là **nối interface
  tới handler ĐÃ CÓ**, không phải cơ chế mới.)
- Policy Lớp-4 (ADR 0002) và rulebot: **không đổi**.
- Household/estate/`VO_THUA_NHAN`: **không đụng** (§D.3 → ADR 0007).
- Ecology/forest/ferry economics: **không đụng** (P2).
- Không chạy LLM/API/mạng ở bất kỳ test/gate nào của P0. Replay real dùng `TranscriptProvider`
  (`minds/transcript.py:120`), không provider.

## 6. Test matrix P0 (behavioral contract — test-engineer viết độc lập)

| Nhóm | Test bắt buộc | Invariant |
|---|---|---|
| Capability | bốn-chân-đủ; không field `KeHoach` mồ côi (đọc `dataclasses.fields`); menu không quảng cáo action không `kha_dung`; mọi action `kha_dung` đều có trong menu (base **và** spatial); catalog render không mutate `world_hash`; catalog hash ổn định khi reorder, đổi khi đổi interface; menu không chứa từ mớm/tên định chế | CAP-1..4 |
| Prompt/config | parity base (6 tháng/90/45/180/60/650/240) và spatial (4 tháng/60/30/120/40/300 + 3 mùa + đò/khai hoang/vụ đông); property "đổi khóa config ⇒ prompt đổi" | PROMPT-1 |
| Resume/replay | rulebot + mock + FakeTransport-real: chạy liền vs chia hai phiên ⇒ cùng `world_hash`; event `seq` unique/monotone; metric tick unique; `call_id` unique toàn run; transcript tiêu thụ hết (`misses==0 && unused==0`); offset hỏng ⇒ fail-closed; tail bị bỏ tồn tại trong `discarded/` + `journal_recovery.jsonl` | JOURNAL-1..3 |
| Verify gate | `verify_research_run` mode **real** chạy transcript replay (không mạng) và coi là **hard**; identity mismatch ⇒ `skipped_version_mismatch` = FAIL; `--json` không crash | §C.4 |
| Regression | toàn bộ suite legacy xanh; overlay OFF ⇒ hash bất biến (ADR 0005 §16.11); `tests/test_prompt_ky_luat.py` giữ nguyên assertion chống mớm ý | §C.6 |

Lệnh gate (bắt buộc, không mạng):

```powershell
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m pytest -q --basetemp .tmp\pytest
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m ruff check .
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m tools.verify_local
```

## 7. Claim boundary (bắt buộc nêu trong mọi report dùng ADR này)

- ADR 0006 chỉ tạo được bằng chứng **`technical-ready`** (Report_v2 §8): interface đúng + artifact
  replay được. Nó **KHÔNG** tạo `mechanism-ready`, **KHÔNG** `research-ready`, **KHÔNG**
  `empirically-validated`.
- Sửa xong P0 **không** làm cho kết quả cũ đúng lên, cũng **không** hứa kết quả mới đẹp hơn. Một
  kết quả âm sau khi sửa vẫn là kết quả hợp lệ (Report_v2 §1).
- Một prompt render đúng, một menu đầy đủ, một transcript replay khớp hash **không** là bằng chứng
  rằng LLM sẽ chuyên môn hóa, phát minh tiền, hay lập nhà nước.
- `real60_spatial` giữ nhãn `diagnostic_only_unreplayable`; không được nâng cấp thành verified bằng
  bất kỳ đường nào.

## 8. Handoff (file cụ thể, đúng vai)

**`minds-engineer`** (§A, §B):
- `minds/capabilities.py` (**MỚI**): descriptor + `CATALOG` + `catalog_hash()` +
  `FIELD_KHONG_PHAI_ACTION` (allowlist có lý do).
- `minds/schemas.py:14`: `LOAI_HANH_DONG` derived từ catalog (giữ tên public); sửa docstring
  "15 nguyên tố".
- `minds/translate.py:183`: `_mot_hanh_dong` dispatch qua `descriptor.to_kehoach`; thêm
  `dong_thuyen`/`rao_do`/`qua_song`; roundtrip hai chiều đủ.
- `minds/prompts.py:169,181-182,241`: `MUC_HANH_DONG` → render từ catalog (giữ xáo theo `w.rng`);
  `dat_lenh` asset list → từ world; `LUAT_VAT_LY` → `luat_vat_ly(w)` đọc `w.cfg` (bảng parity §B.1).
- **KHÔNG** thêm field mới vào `KeHoach`; **KHÔNG** thêm action mới ngoài 3 action mồ côi đã có
  handler.

**`reproducibility-steward`** + **`engine-surgeon`** (§C):
- `tools/journal.py` (**MỚI**): `JournalManifest` (pydantic v2), `capture()`, `restore()`,
  `verify()`, `--repair --confirm` + `journal_recovery.jsonl`.
- `engine/events.py:16-22`: `EventLog(start_seq=...)` + field `seq`.
- `minds/transcript.py:48-52`: `TranscriptWriter(path, start_call_id=...)` + `run_uuid`/`segment_id`.
- `minds/gateway.py:44-63`: cột `segment_id`, `superseded` (migration `ALTER TABLE` an toàn cho db cũ).
- `run.py:206-224`: resume ⇒ `journal.restore()` **trước** khi mở writer; fail-closed.
  `run.py:274-276`: bỏ ghi đè `metrics.jsonl`, chuyển sang append per-tick.
  `run.py:59-64` + `tools/experiments.py:108-134`: thêm `run_uuid`, `capability_catalog_hash`.
- `tools/verify_research_run.py:196-227`: bỏ nhánh skip-real; thêm hard check
  `transcript_replay`, `journal_continuity`, field `artifact_status`; sửa bug `--json` (`:240`).
- `tools/replay.py:58-61`: thêm điều kiện identity (config/prompt/catalog hash).

**`test-engineer`** (độc lập, không phải người implement): viết đủ §6. Không nới assertion, không
skip, không hardcode seed.

**`research-artifact-integrity-auditor`**: tạo `docs/reviews/artifact_ledger.md`; ghi
`real60_spatial = diagnostic_only_unreplayable` với lý do + bằng chứng (§1.3). **KHÔNG** sửa
`data/runs/real60_spatial/`.

**`model-architect`** + **`household-demography-specialist`**: bắt đầu **ADR 0007** (§D.3) — điều
kiện tiên quyết của P1. P0 không chờ ADR 0007; P1 không được bắt đầu trước khi nó Accepted.

**`adversarial-reviewer`** / **`qa-verifier`**: cổng độc lập. Đặc biệt soi: (a) catalog có lén xếp
hạng/gợi ý nghề không (CAP-4); (b) truncate có làm mất bằng chứng call thật không (§C.1 ngoại lệ
`llm_calls`); (c) có test nào bị nới để `world_hash` legacy xanh không.
