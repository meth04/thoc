# P2 — Design memo: rừng (biomass/canopy), gà rừng, đò/hai bờ, crop economics

- Vai: `spatial-ecology-specialist` (reviewer/designer). **Verdict: DESIGN ONLY — không sửa code
  production.** Memo này là contract cho `engine-surgeon` (implement) + `test-engineer` (test).
- Nguồn quyền lực: `Report_v2.md` §4.4, §5 P2, §6; `docs/adr/0005-spatial-livelihood-economy.md`
  (§2, §4.1, §6, §8, §11); `docs/MODEL_CHARTER.md` §3 (5 lớp), §5 (cổng định chế + anti-teleology).
- Claim tier của mọi con số đề xuất ở đây: **`design_assumption`**. Không mục nào là
  `calibrated_fact`; không mục nào khẳng định hiện thực lịch sử.
- Không chạy LLM/API/mạng. Mọi probe chạy `conda run -n thoc-env python` với `THOC_BLOCK_NETWORK=1`.

---

## 0. Xác minh lỗ hổng (file:line + probe output)

| # | Lỗ hổng | Bằng chứng |
|---|---|---|
| G1 | **Gỗ khai thác VÔ HẠN.** `khai_thac` chỉ kiểm `any(p.loai == "rung")` toàn bản đồ rồi mint gỗ theo công; không ô nào bị trừ gì. | `engine/production.py:353-376` — `:362-363` (`loai_o="rung"`; `any(...)`), `:373-374` (`thu_duoc = cong_co * dinh_muc * hieu_suat * he_so_may` → `ledger.sinh`). Config `config/world.yaml:33` `cong_moi_go: 10`. Ô rừng chỉ đổi qua `khai_hoang` (`production.py:159` `p.loai = "ruong"`). |
| G2 | **K gà rừng đếm SỐ Ô, không đếm habitat.** | `engine/world.py:761-768`: `so_o = sum(1 for p ... if p.loai == "rung"); return so_o * suc_chua_moi_o`. Chặt trụi một ô không đổi K. |
| G3 | **Rò rỉ bờ: khai thác gỗ/quặng KHÔNG kiểm `co_the_o_bo`.** Toàn bộ `mo_dong` nằm bờ `hoang` nhưng người bờ `dan_cu` vẫn khai được mà không cần đò. | `engine/production.py:353-376` (không gọi `co_the_o_bo`), đối lập với `chan_nuoi.py:84-87` (`bat_ga` CÓ kiểm) và `production.py:239,311` (canh tác CÓ kiểm). Probe (seed 7, overlay ON): parcels `mo_dong` = 2 ô, **cả 2 ở bờ `hoang`**; `co_the_o_bo(A0001,"hoang") = False`; vẫn thu `go = 25.0`, `quang_dong = 12.5`. |
| G4 | **Clamp K→ton âm thầm.** Khi K tụt dưới `ton`, `tai_sinh_ga_rung` cắt `ton` không event; K=0 ⇒ `ton=0` không event. | `engine/chan_nuoi.py:201-208`. |
| G5 | **Đường LLM cho `qua_song`/`rao_do`/`dong_thuyen` không tồn tại.** | `minds/schemas.py:14-18` (`LOAI_HANH_DONG` có `khai_hoang`, `canh_vu_dong`, `cham_tre`; KHÔNG có 3 action đò); `minds/translate.py:186,208-216`. Chỉ `minds/rulebot.py:366-396` set trực tiếp field `KeHoach`. → **P0 owns fix**; P2 chỉ phủ test. |
| G6 | **Tham số sinh thái overlay không có provenance row.** | `scenarios/agrarian_transition_v1/provenance.csv` không có dòng nào cho `khong_gian.*` (ga_rung, vu_dong, khai_hoang, do). |

Probe (không mạng): `conda run -n thoc-env python <scratchpad>/p2probe/probe2.py`, seed 7, overlay
`spatial_v1.yaml`:

```text
parcels by (loai,bo): {('song',None):30, ('ruong','dan_cu'):252, ('mo_dong','hoang'):2,
                       ('rung','dan_cu'):91, ('doi','dan_cu'):92, ('doi','hoang'):216,
                       ('rung','hoang'):217}
WITHOUT crossing river: go = 25.0 | quang_dong = 12.5          # G3
after 10 more logging ticks: go = 525.0 | so o rung = 308      # G1 (rừng không suy giảm)
```

---

## 1. Per-cell forest state (TỐI THIỂU)

### 1.1 State

**Một field duy nhất trên `Parcel`:**

```python
# engine/types.py — Parcel
sinh_khoi: float | None = None   # đơn vị: "gỗ" (CÙNG đơn vị asset ledger `go`); None = mô hình rừng TẮT
```

- **Canopy là DẪN XUẤT, không lưu**: `tan_che(p) = clamp(p.sinh_khoi / B_max(p.loai), 0, 1)`.
  Không thêm field thứ hai (Report_v2 §9 non-goal: không thêm chi tiết vi mô). Một float/ô là
  đủ cho toàn bộ chuỗi nhân quả yêu cầu.
- **Bounded:** `0 ≤ p.sinh_khoi ≤ B_max(p.loai)`; `B_max` từ config theo loại đất
  (`rung` > 0; `doi`/`ruong`/`mo_dong`/`song` = 0 ⇒ `sinh_khoi = 0.0`).
- **Đơn vị**: `sinh_khoi` đo bằng đúng đơn vị của asset `go`. Lý do: bất biến "extraction ≤
  available" trở thành so sánh cùng đơn vị, không cần hệ số quy đổi ẩn.

### 1.2 Flows (4 dòng, không hơn)

| Flow | Công thức | Ghi chú |
|---|---|---|
| `tai_sinh_rung(w)` | **Logistic + seed-rain**: `B ← min(B_max, B + r·B·(1 − B/B_max) + s)` với `s = hat_giong_tu_nhien` (kg/tick), chỉ áp cho ô `loai=="rung"`. | **Chọn logistic** (không phải tuyến-tính-bão-hòa) vì: (a) đồng khuôn với `tai_sinh_ca` (`chan_nuoi.py:177-190`) và `tai_sinh_ga_rung` (`:193-208`) ⇒ cùng một property test `0≤S≤K` + "giảm áp lực ⇒ hồi đơn điệu"; (b) MSY = `r·K/4` là một đại lượng công bố được để pre-register shock. **Seed-rain `s` là bắt buộc** nếu không muốn `B=0` thành trạng thái hấp thụ vĩnh viễn (logistic thuần: `B=0 ⇒ ΔB=0` mãi mãi). `s=0` là một ablation hợp lệ để **đo** tính bất khả hồi, không phải mặc định ẩn. |
| `khai_thac_go` (**logging chọn lọc**) | `thu = min(cong/cong_moi_go · hieu_suat · he_so_may, Σ B của ô khả dụng)`; trừ B theo thứ tự tất định. **KHÔNG đổi `p.loai`.** | Ô khả dụng = `{p : p.loai=="rung" ∧ co_the_o_bo(w,aid,p.bo) ∧ (p.chu is None ∨ p.chu==aid ∨ pid ∈ qsd_map[aid])}`, **sort theo `(khoang_cach(nha, p), p.id)`** (gần trước, tie-break id). Rút cạn ô gần rồi mới sang ô kế. |
| `khai_hoang` (**clearing**) | `p.loai: rung/doi → ruong`; thu hồi một lần `go += ty_le_thu_hoi_go · B`; `B ← 0`; canopy → 0 ⇒ ô rời khỏi Σ habitat. | Đường hiện có `production.py:126-162` giữ nguyên; chỉ **thêm** thu hồi gỗ + zero-out B. Flow mới `go/khai_hoang` (nguon). `ty_le_thu_hoi_go = 0` ⇒ đốt nương (ablation). |
| `trong_rung` (**reforestation**) | **PENDING — spec đầy đủ ở §1.5, mặc định OFF.** | KHÔNG được báo cáo là "đã có" nếu không implement (tiền lệ ADR 0005 §4.2). |

**INVARIANT E1 (cứng):** *không thu được gỗ khi biomass đã cạn, dù ô còn nhãn `rung`.*
`extraction ≤ Σ available`. Nhãn `loai` KHÔNG còn là giấy phép mint. Công đã bỏ mà không có
biomass ⇒ trả về 0 gỗ + `_ghi_su_co` reason code `rung_can_kiet` (đối xứng `danh_ca`
`chan_nuoi.py:232`). Công vẫn bị tiêu (đi rừng cả buổi về tay không) — đúng khuôn `danh_ca`,
KHÔNG hoàn công.

**INVARIANT E2 (stock-flow identity, kiểm mỗi tick):**
`Σ B(t) − Σ B(t−1) = tai_sinh − khai_thac_go − sinh_khoi_mat_do_khai_hoang + trong_rung_moi`
với sai số ≤ `1e-6`. Đây là "conservation/upper-bound test" của P2; pool rừng KHÔNG nằm trong
ledger nên nó **không** thay `kiem_toan(ledger)`, nó là một audit **thứ hai**, độc lập.

**Event before/after (bắt buộc, Report_v2 §4.4):**
- `khai_thac_go{id, thua, kg, sinh_khoi_truoc, sinh_khoi_sau, tan_che_sau}` (mỗi ô bị chặt).
- `khai_hoang{id, thua, tu_loai, sinh_khoi_mat, go_thu_hoi}` (mở rộng event hiện có
  `production.py:161`).
- `tai_sinh_rung{tong_truoc, tong_sau, so_o}` — **một event/tick tổng hợp** (308 ô ⇒ không ghi
  per-cell, tránh phình journal).
- `rung_can_kiet{id, cong_mat, ly_do}`.

### 1.3 Vị trí trong tick (thứ tự nhân quả)

`engine/tick.py` hiện: reset transient `:130` → `sinh_cong :133` → care `:138` → `gop_cong :139`
→ **ferry `:147`** → **`thi_hanh_san_xuat` `:148`** (chứa `khai_hoang` `production.py:209` +
`khai_thac go` `:353`) → `tai_sinh_ca :155` → `tai_sinh_ga_rung :156` → `bat_ga :163`.

**Chèn `tai_sinh_rung(w)` ngay TRƯỚC `production.thi_hanh_san_xuat` (tức sau `spatial.buoc_qua_song`
`tick.py:147`).** Hệ quả (đúng và phải giữ):

1. rừng hồi trước, người chặt sau (đồng khuôn cá/gà: regen trước extraction);
2. `khai_hoang` + `khai_thac_go` trong cùng pha production hạ canopy **ngay tick này**;
3. `tai_sinh_ga_rung` (`:156`) chạy **SAU** production ⇒ `_ga_rung_suc_chua` đọc canopy **đã bị
   hạ** ⇒ K↓ ngay tick này ⇒ clamp `ton` ngay tick này ⇒ `bat_ga` (`:163`) chịu hậu quả **cùng
   tick**. Không cần đổi thứ tự nào khác.

**RNG:** logistic + seed-rain là tất định ⇒ **KHÔNG tiêu RNG mới** ⇒ không dịch chuyển cây RNG ⇒
không có nguy cơ phá determinism của các subsystem khác.

### 1.4 Hash — trả lời CHÍNH XÁC

Đọc `World.behavioral_state()` (`engine/world.py:460-570`):

```python
two_bank = bool(self.cfg.get("khong_gian.hai_bo", False))   # world.py:470
parcels = {pid: p for pid, p in self.parcels.items()}       # :471-474  → Parcel DATACLASS
if not two_bank:
    parcels = {pid: {"id","r","c","loai","mau_mo","mau_mo_goc","chu","lang",
                     "nguoi_canh","homestead_dem","homestead_ai"} ...}   # :478-493 → 11 KHÓA
```

`_canonical_state` (`world.py:38-42`) băm dataclass bằng **mọi field** khai báo. Do đó:

- **`hai_bo` OFF (mọi run legacy, `preindustrial_closed_v1`, base `agrarian_transition_v1`):**
  parcels được chiếu qua **whitelist 11 khóa** ⇒ **field `sinh_khoi` mới KHÔNG vào hash** ⇒
  **hash legacy BẤT BIẾN, bit-for-bit, tự động.** Đã xác minh bằng probe (`test_spatial.py:42`
  cũng đã chứng minh cùng tính chất cho `bo`):
  `OFF hash insensitive to 'bo' (whitelist projection): True`.
- **`hai_bo` ON (`spatial_v1`):** parcels băm **toàn bộ dataclass** ⇒ **thêm một field bất kỳ SẼ
  đổi world_hash của `spatial_v1`**, kể cả khi giá trị là `None`. Probe:
  `ON hash sensitive to 'bo' (full-dataclass hashing): True`.

**Hệ quả bắt buộc — 2 việc, không được bỏ:**

1. **Điều kiện chiếu parcels phải mở rộng**, nếu không sẽ có một khe determinism thật:
   một config `khong_gian.bat=true, hai_bo=false, rung.bat=true` sẽ rơi vào nhánh whitelist ⇒
   **biomass ảnh hưởng hành vi nhưng NGOÀI hash** (vi phạm charter §3/§D). Sửa (1 dòng):
   `full = _hai_bo_bat(self) or _rung_bat(self)` thay cho `two_bank`; whitelist chỉ dùng khi cả
   hai OFF. (Ablation "biomass ON, hai_bo OFF" là một cell thật của ma trận §6 ⇒ khe này KHÔNG
   giả định.)
2. **`_behavioral_config` (`world.py:85-97`) phải thêm `"rung"` vào tuple sub-block**
   `("do","khai_hoang","vu_dong","ga_rung","cham_tre","endowment")` (`world.py:90`). Thiếu dòng
   này, một config có block `rung: {bat: false, ...}` sẽ băm khác một config không có block →
   phá tính chất "tắt = như chưa từng có".

**Khai báo minh bạch (không được im lặng):** world_hash của **`spatial_v1` ON sẽ đổi** sau khi
thêm field. Điều này **không** vi phạm ADR 0005 §11.4 (điều kiện gate chỉ ràng buộc nhánh OFF/
legacy) và không vi phạm Report_v2 §5 P2.5 ("cannot silently alter **legacy** runs") — nhưng nó
**phải** được ghi vào `DECISIONS.md` + manifest, và `real60_spatial` giữ nguyên nhãn
`diagnostic_only_unreplayable` (không retcon). Không có literal hash nào bị pin trong `tests/`
(đã grep: 0 hit cho hằng hex 16–64 ký tự) ⇒ không test nào vỡ vì lý do này.

> **Phương án thay thế B (nếu team muốn đóng băng cả hash `spatial_v1`):** giữ biomass ở
> `World.rung_sinh_khoi: dict[pid, float]` và chèn vào `behavioral_state()["commons"]` bằng
> **khóa có điều kiện** (`**({"forest_biomass": ...} if rung_bat else {})`) ⇒ hash của **mọi**
> config hiện có bất biến 100%, và `v2 (rung OFF) ≡ spatial_v1` theo hash — một baseline ablation
> rất sạch. Giá phải trả: state per-parcel sống ngoài `Parcel` (rủi ro desync khi `loai` đổi).
> **Khuyến nghị: Phương án A (field trên `Parcel`)** vì cohesion + fail-closed (mọi field Parcel
> mới tự động vào hash ở nhánh ON), với điều kiện thực hiện đủ 2 việc trên và khai báo hash
> `spatial_v1` đổi. Nếu reproducibility-steward yêu cầu đóng băng `spatial_v1`, chuyển sang B —
> quyết định thuộc về steward, không thuộc người implement.

**Migration `nap_checkpoint` (`world.py:619-688`, theo đúng khuôn `ca_ton`/`ga_rung_ton` `:640-647`):**

```python
# migration P2: sinh khối rừng — checkpoint cũ (OFF hoặc spatial_v1) nạp lại ⇒ trung tính
rung_on = bool(w.cfg.get("khong_gian.rung.bat", False)) and _khong_gian_bat(w)
for p in w.parcels.values():
    if not hasattr(p, "sinh_khoi"):
        p.sinh_khoi = (
            _b_max(w, p.loai) * float(w.cfg.get("khong_gian.rung.ty_le_ban_dau"))
            if rung_on and p.loai == "rung" else (0.0 if rung_on else None)
        )
```

OFF ⇒ `sinh_khoi=None` ⇒ mọi code path rừng no-op ⇒ replay + hash legacy y nguyên.

### 1.5 `trong_rung` — PENDING spec (KHÔNG giả vờ đã có)

Nếu **không** implement ở P2: ghi PENDING, và **cấm** mọi report/metric nói tới reforestation.
Acceptance P2 ("regeneration/reforestation changes the opposite direction") **đã thỏa được bằng
tái sinh thụ động** ⇒ reforestation không phải blocker.

Nếu implement (flag `khong_gian.rung.trong_rung.bat`, mặc định **false**):

- Intent `trong_rung: list[str]` (KeHoach) → cần đường P0: `intents` + `schemas.LOAI_HANH_DONG` +
  `translate` + menu (đi cùng gói P0 của `qua_song`).
- Điều kiện: `p.loai ∈ {ruong, doi}`, `p.chu is None or p.chu == aid`, ô KHÔNG canh tick này,
  `co_the_o_bo(w, aid, p.bo)`.
- Chi phí: `cong_moi_thua` (đề xuất 60 công) — NGUYÊN TỬ qua `_lam_nguyen_tu`.
- Kết quả: `p.loai = "rung"`, `p.sinh_khoi = sinh_khoi_ban_dau` (đề xuất 5), `p.chu` **giữ nguyên**
  (nếu tước quyền sở hữu thì không ai trồng — đó sẽ là một luật ẩn chống trồng rừng).
- **Thời gian là chi phí thật, không cần cơ chế mới**: canopy hồi theo logistic ⇒ mất nhiều tick
  mới đóng góp habitat đáng kể.
- **Dự đoán có dấu (phải report, không được "sửa cho đẹp"):** habitat là **hàng hóa công không
  loại trừ** (K gộp toàn map, `bat_ga` không hỏi `p.chu`) ⇒ người trồng chịu 100% chi phí, hưởng
  ~1/N lợi ích ⇒ **dự đoán adoption THẤP**. Đó là một kết quả cơ chế hợp lệ (free-rider), **không**
  phải bug cần vá bằng trợ cấp.

---

## 2. K gà rừng từ canopy, không từ số ô

### 2.1 Công thức

```python
# engine/world.py::_ga_rung_suc_chua  (thay :767)
K = Σ_{p.loai=="rung"} tan_che(p) * suc_chua_moi_o          # khi khong_gian.rung.bat
K = Σ_{p.loai=="rung"} 1.0        * suc_chua_moi_o          # khi rung.bat = false (spatial_v1 y nguyên)
```

Với `tan_che(p) = p.sinh_khoi / B_max`. Ở canopy đầy, K trùng khớp giá trị `spatial_v1` hiện tại
(probe: 308 ô × 8 = 2464) ⇒ **baseline so sánh được**.

**Cờ tách kênh (bắt buộc cho thiết kế nhân quả):** `khong_gian.ga_rung.k_theo_tan_che: bool`.
`false` ⇒ K = số ô (semantics cũ) **ngay cả khi biomass đang bật** ⇒ cho phép ablate **riêng kênh
habitat** trong khi vẫn giữ kênh khan hiếm gỗ. Không có cờ này thì "logging shock → ít gà" không
tách được khỏi "logging shock → thiếu gỗ → thiếu nhà → sức khỏe kém" (§7 F-confound).

CPUE + regeneration **giữ nguyên khuôn đã có** — không viết lại: `bat_ga` mật độ `ton/K`, cap
`min(..., ton)` (`chan_nuoi.py:96-103,123`); `tai_sinh_ga_rung` logistic (`chan_nuoi.py:193-208`).

### 2.2 Chuỗi nhân quả kiểm chứng được — và cái bẫy phải tránh

```text
logging shock → Σ sinh_khoi ↓ → tan_che ↓ → K ↓ → [clamp] ton ↓
              → sản lượng bền vững r·K/4 ↓ → catch tích lũy trên H tick ↓
```

**CẢNH BÁO cho test-engineer (nếu bỏ qua sẽ viết test SAI rồi nới assertion):** ngay sau shock,
`mat_do = ton/K` **KHÔNG giảm** — nó **tăng lên 1.0** vì clamp kéo `ton` xuống bằng K. CPUE
tức thời (gỗ/công) do đó có thể **tăng** một tick. Dấu phải đo là:

| Bước | Đại lượng | Dấu kỳ vọng | Cách đo |
|---|---|---|---|
| 1 | `Σ p.sinh_khoi` | ↓ | tổng biomass sau shock < trước |
| 2 | `mean tan_che` trên ô rừng | ↓ | derived |
| 3 | `_ga_rung_suc_chua(w)` (K) | ↓ | strictly < |
| 4 | `w.ga_rung_ton` | ↓ | do clamp `ton ≤ K` |
| 5 | `mat_do = ton/K` | **KHÔNG kiểm dấu** | có thể ↑ tạm thời — assert `≤ 1.0` thôi |
| 6 | **catch tích lũy trên H tick** với cùng công bắt gà | ↓ | so hai nhánh paired-seed |

### 2.3 Biên

- **K < ton:** `ton ← min(ton, K)`; ghi event `ga_rung_suc_chua_giam{K_truoc, K_sau, ton_truoc,
  ton_sau, mat}`. **Không phá bảo toàn:** `ga_rung_ton` là **pool tự nhiên**, một `float` trên
  `World` — **không phải chủ thể ledger, không có bút toán đối ứng nào** (ADR 0005 §6/§11.1).
  Ledger chỉ thấy `ga_con/bat_rung` (nguon, đã đăng ký `world.py:718`) khi có người bắt được;
  pool chỉ **chặn trên** cho source đó (đúng như `ca/danh_ca`). "Burn" pool ⇒ 0 dòng ledger ⇒
  `kiem_toan` (`audit.py:39-62`) không bị động tới. Hiện tại clamp này **đã âm thầm xảy ra**
  (`chan_nuoi.py:205-208`) — P2 chỉ thêm event, không thêm hành vi.
- **K = 0** (chặt trụi / khai hoang hết rừng): `ton = 0`; `bat_ga` trả 0 với reason code
  `habitat_can_kiet` (hiện `chan_nuoi.py:99-104` return im lặng — phải thêm `_ghi_su_co`).
- **Trạng thái hấp thụ:** K=0 ∧ `s=0` ∧ `trong_rung` OFF ⇒ gà rừng mất vĩnh viễn ⇒ cửa vào đàn
  nuôi (`bat_ga → ga_con`, nguồn `ga_con` duy nhất ngoài `sinh_san`) đóng lại. Ai không còn `ga`
  chỉ có thể **mua** trên chợ. Đây là **path dependency có thật**, phải report, không được vá.

### 2.4 Anti-teleology (INVARIANT)

Nuôi gà (`ga_con → ga`, `chan_nuoi.py:15-70`) là **lựa chọn khác có chi phí thật** (thóc nuôi
`ga_an_thoc_moi_tick`, công bắt/giết, trần đàn, chết già) — **KHÔNG** phải compensation tự động
khi gà rừng cạn. Engine **cấm**: bất kỳ nhánh nào dạng `if ga_rung_ton < x: boost husbandry`,
mọi buff năng suất chăn nuôi theo mức cạn kiệt, mọi gợi ý prompt "gà rừng hết rồi, nên nuôi gà".
Nếu chăn nuôi **không** tăng sau shock, đó là kết quả hợp lệ và phải được report như vậy.

---

## 3. Gỗ nối vào recipe/project — khan hiếm trở thành thật

Cầu gỗ hiện có (`config/world.yaml:28-33`, overlay `spatial_v1.yaml:29-30`):
`cong_cu` **2 gỗ**, `nha` **8 gỗ**, `thuyen` **6 gỗ**, `may` (research recipe), `go/chi_cong`
(thủy lợi, fiscal). Cung gỗ hôm nay = ∞ (G1) ⇒ mọi recipe trên **không cạnh tranh nguồn**.

Với `B` hữu hạn:

- **Ferry vs House cạnh tranh trực tiếp**: 6 gỗ (một thuyền = một cửa sang bờ hoang) đấu 8 gỗ
  (một nhà = tránh phạt `vo_gia_cu` mùa mưa). Đây là trade-off **vật lý đã công bố**, không phải
  luật nghề.
- **Vòng phản hồi cần đo (chứ không cần thiết kế thêm):** rừng bờ `dan_cu` chỉ có 91/308 ô
  (probe, seed 7) ⇒ MSY bờ nhà nhỏ ⇒ khi áp lực logging vượt MSY bờ nhà, **gỗ bờ kia** mới đáng
  giá ⇒ đò **có thể** trở nên có giá trị. **Có thể**, không **phải**. Nếu không ai đóng thuyền và
  làng cạn gỗ rồi hết nhà — đó là kết quả.
- **Sửa G3 là điều kiện cần**: nếu khai thác gỗ/quặng vẫn không kiểm `co_the_o_bo`, toàn bộ rừng
  + 100% quặng bờ hoang vẫn lấy được từ nhà ⇒ đò không bao giờ có giá trị kinh tế và "far-bank
  access" chỉ là chuyện kể. **Fix (P2, `production.py:353-376`): thêm `co_the_o_bo(w, aid, p.bo)`
  vào tập ô khả dụng cho cả `go` và `quang_dong`** (đúng như `bat_ga` `chan_nuoi.py:86`). Cá
  (`song`, `bo=None`) giữ nguyên: sông không thuộc bờ nào.

**Audit:** `go/khai_thac` (nguon, `world.py:701`) trở thành **source bị pool giới hạn**, y hệt
`ca/danh_ca`. Thêm `f.dang_ky("go", "khai_hoang", "nguon")` cho gỗ thu hồi khi vỡ hoang (đăng ký
thừa **không** đổi hash — tiền lệ `world.py:742-752`). `kiem_toan_the_gioi` (`audit.py:21-36`)
giữ nguyên (số thửa không đổi: logging không đổi `loai`; `khai_hoang`/`trong_rung` đổi `loai` chứ
không tạo/xóa thửa). Audit thứ hai = **E2** (§1.2).

---

## 4. Đò / hai bờ / khai hoang — test coverage

`engine/spatial.py:112-190` (`buoc_qua_song`): đóng thuyền `:122-126`; chủ thuyền tự qua
`:146-151`; khớp khách–chủ đò theo `(phí giảm dần, id)` `:155-183`; capacity `:130,176-177`; phí =
`ledger.chuyen` `:179`; `LoiSoKep` ⇒ không qua, không âm sổ `:180-181`; hao mòn `:186-190`.

| # | Case | Trạng thái engine | Test hiện có | Việc phải làm |
|---|---|---|---|---|
| F1 | **Route thành công** (có thuyền, trả thóc, đúng bờ) | ĐÃ CÓ | `tests/test_ferry.py:96` | giữ |
| F2 | **Không thuyền / không chủ đò** ⇒ kẹt bờ | ĐÃ CÓ | `test_ferry.py:82` | **MỞ RỘNG**: thêm case "có `rao_do` nhưng `so_du(op,'thuyen') < 1`" (`spatial.py:159`) — **CHƯA có test** |
| F3 | **Không đủ phí** ⇒ không qua, sổ không âm | ĐÃ CÓ | `test_ferry.py:127` | giữ |
| F4 | **Quá capacity** ⇒ chở đúng `cap`, thứ tự tất định | ĐÃ CÓ | `test_ferry.py:142` | **MỞ RỘNG**: nhiều chủ đò cùng tick; khách đã qua không được qua lần hai (`spatial.py:135` `kid in ben_kia`) — **CHƯA có test** |
| F5 | **Hết hạn (expiry)** | **KHÔNG CÓ KHÁI NIỆM** — `rao_do`/`qua_song` là field per-tick, offer "hết hạn" mỗi tick theo thiết kế | — | **NEW**: (a) test khẳng định offer KHÔNG sống qua tick (regression trên semantics transient); (b) **fare trả sau** bằng clause `chuyen_giao_mot_lan` (ADR 0005 §2.3) → hết `thoi_han` mà không trả ⇒ hợp đồng vào `vi_pham`, không có chuyến "miễn phí ngầm" |
| F6 | **Project** (thuyền dựng nhiều tick / nhiều người góp) | **CHƯA CÓ** — `_dong_thuyen` (`spatial.py:95-109`) nguyên tử một tick | `test_ferry.py:179,193` (atomic) | **NEW, phụ thuộc P1** (generic work-order): thuyền 80 công > 120 công/tick vẫn vừa một người, nhưng nhà 240 công thì không ⇒ dùng cùng primitive; test: góp công nhiều tick, hủy giữa chừng ⇒ refund đúng một lần |
| F7 | **Ownership** — chỉ chủ thuyền mới được rao; hao mòn về 0 ⇒ hết vận hành | Engine có check `:159`, hao mòn `:186-190` | không | **NEW** |
| F8 | **Transient access** — qua sông chỉ có hiệu lực trong tick đó (`tick.py:130` reset) | ĐÃ CÓ | không | **NEW**: tick sau không qua ⇒ `co_the_o_bo == False` ⇒ khai hoang/bắt gà bờ kia bị chặn |
| F9 | **Rò rỉ bờ ở khai thác gỗ/quặng (G3)** | **BUG** | không | **NEW (blocking)**: không đò ⇒ `go`/`quang_dong` từ ô bờ kia = 0; có đò ⇒ > 0 |
| F10 | **Khai hoang bờ hoang cần đò** | ĐÃ CÓ (`production.py:150-152`) | `tests/test_spatial_land.py` (kiểm) | giữ + thêm: khai hoang **giảm** habitat K (link §2) |
| F11 | **Đường LLM** (`qua_song`/`rao_do`/`dong_thuyen` từ JSON action → engine intent) | **KHÔNG CÓ** (G5) | không | **NEW — P0 sửa, P2 test**: parity test schema↔translate↔handler |

---

## 5. Crop economics — fact-only, engine không chọn cây

### 5.1 Chốt nguyên tắc

`lua` / `ngo` / `khoai` khác nhau **chỉ ở vật lý đã công bố**:
`cong`, `san_luong_kg`, `quy_doi_dinh_duong`, mùa được phép
(`spatial_v1.yaml:89-92`: ngo `{40 công, 280kg, 0.9}`, khoai `{30 công, 333kg, 0.7}`; lúa
`san_xuat.san_luong_goc_kg=300`, `cong_moi_thua=40`, `giong=40kg`, chỉ mùa `lua_1/lua_2`).
Engine **KHÔNG** tính "cây nào lãi nhất" ở bất kỳ đâu: `thi_hanh_san_xuat` chỉ thực thi
`kh.canh_vu_dong` mà agent đã chọn (`production.py:297-351`). **Giữ nguyên tính chất này.** Cấm:
mọi hàm engine trả về "cây tốt nhất", mọi tie-break theo lợi nhuận, mọi default cây khi agent
không chọn.

### 5.2 Đánh giá `minds/prompts.py:110-117` (câu hỏi trực tiếp)

Chuỗi hiện tại: `"Vụ đông đang mở: bạn có thể trồng khoai (30 công → ~333kg), ngo (40 công →
~280kg)"`.

**Đánh giá: CHƯA phải fact card trung tính — nó là một tập dữ kiện KHUYẾT tạo ra thứ hạng ngầm.**
Ba lỗi:

1. **Thiếu biến quyết định:** `quy_doi_dinh_duong` bị bỏ (0.9 vs 0.7). Ở hệ số gốc, food-equivalent
   là ngô 280×0.9 = **252 kg-thóc-tương-đương** vs khoai 333×0.7 = **233**. Con số duy nhất được
   hiển thị (kg thô) **đảo ngược** thứ tự theo dinh dưỡng ⇒ card "nói sự thật" nhưng chọn đúng
   con số dễ gây hiểu sai. Đây chính là "xếp hạng ngầm" mà Report_v2 §4.5.3 cấm.
2. **Con số KHÔNG phải kỳ vọng của agent đó:** sản lượng thực =
   `san_luong_kg × mau_mo × he_so_tt × tool × health × research × tay_nghe`
   (`production.py:321-329`). "~280kg" là hệ số gốc, không phải sản lượng dự kiến trên thửa cụ thể
   ⇒ prompt đang khẳng định một con số engine không giao. Đáng chú ý: **không có RNG** trong công
   thức và thời tiết đã biết lúc quyết định (`prompts.py:119`) ⇒ **kỳ vọng có thể tính CHÍNH XÁC**.
   Không có lý do gì để đưa con số gần đúng sai lệch.
3. **Thiếu ràng buộc + thiếu lựa chọn "không làm gì":** không nói ngân sách công (120/tick), không
   nói thửa nào hợp lệ, không nói được phép bỏ vụ.

### 5.3 Opportunity card — schema bắt buộc (input cho minds-engineer, P3)

Card sinh bởi **cùng một hàm preflight mà engine dùng để thực thi** (P1 feasibility planner) —
nếu render bằng một hàm riêng, card sẽ nói dối. Trường bắt buộc:

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `hoat_dong` | str | `canh_lua` \| `canh_vu_dong:ngo` \| `canh_vu_dong:khoai` \| `khai_thac_go` \| `bat_ga` \| `danh_ca` \| `nuoi_ga` \| `khai_hoang` \| `dong_thuyen` \| `qua_song` \| `xay_nha` \| `cham_tre` \| `gop_cong` |
| `doi_tuong` | str\|None | thửa/ô/đối tác cụ thể (card **per-parcel**, không phải per-crop chung chung) |
| `kha_thi` | bool | |
| `reason_code` | str\|None | `insufficient_labor`, `no_right`, `no_inventory`, `no_boat`, `wrong_season`, `rung_can_kiet`, `habitat_can_kiet`, ... |
| `dau_vao` | dict | `{cong: 40, thoc_giong: 40}` — **có đơn vị** |
| `san_luong_ky_vong` | dict | `{ngo: 268.4}` — tính bằng **đúng** công thức engine với `mau_mo`/`he_so_tt`/`tay_nghe`/tool/health của chính agent |
| `quy_doi_thuc_pham` | float | kg-thóc-tương-đương = `san_luong × quy_doi_dinh_duong` |
| `thoi_gian_hoan_thanh` | int | tick (1 với canh; nhiều tick với project) |
| `tac_dong_tai_nguyen` | dict\|None | `{sinh_khoi: -12.0, tan_che_sau: 0.61}` / `{ga_rung_ton: -1.2, mat_do: 0.44}` — Report §4.5.3 "resource impact" |
| `bang_chung_thi_truong` | dict\|None | `{tai_san, gia_gan_nhat, khoi_luong, tick, so_giao_dich}`; **None khi coverage thưa** (không bịa giá) |
| `niem_tin_gia` | dict\|None | `agent.gia_ky_vong[ts]` + độ phân tán — **prior riêng, không phải giá đúng** |

**CẤM trong card:** `xep_hang`, `khuyen_nghi`, `loi_nhuan_ky_vong` do engine quy về một đơn vị
tiền/thóc duy nhất, sắp xếp theo lợi nhuận, hoặc bất kỳ tính từ nào ("tốt hơn", "nên"). Thứ tự
hiển thị: **tất định theo `(hoat_dong, doi_tuong)`**, không theo giá trị. Luôn có card ngầm
"không làm gì" (agent được phép nhàn/để dành công cho việc khác — Report §5 P3.1).

---

## 6. Ablation & scenario versioning

**Khuyến nghị: tạo overlay MỚI, tự chứa: `scenarios/agrarian_transition_v1/spatial_livelihood_v2.yaml`.**
KHÔNG sửa `spatial_v1.yaml` (giữ nguyên byte ⇒ giữ được đối chứng + lịch sử `real60_spatial`).
`load_config(overlays=[...])` (`engine/config.py:57-93`) hỗ trợ nhiều overlay, nhưng một file
tự chứa cho digest/provenance dễ đọc hơn và tránh phụ thuộc thứ tự merge.

Khối mới (mọi số = `design_assumption`, **phải** có dòng trong `provenance.csv` — hiện file này
chưa có dòng nào cho `khong_gian.*`, xem G6):

```yaml
khong_gian:
  rung:
    bat: true
    sinh_khoi_toi_da_moi_o: 60      # đơn vị: gỗ/ô  (design_assumption)
    ty_le_ban_dau: 0.8              # B(t0) = 0.8 × B_max
    tai_sinh_moi_tick: 0.05         # r logistic, mỗi tick 4 tháng
    hat_giong_tu_nhien: 0.3         # kg/tick/ô rừng — chống trạng thái hấp thụ B=0
    ty_le_thu_hoi_go_khi_khai_hoang: 0.5
    trong_rung:
      bat: false                    # PENDING (§1.5) — false = KHÔNG tồn tại, không báo cáo
      cong_moi_thua: 60
      sinh_khoi_ban_dau: 5
  ga_rung:
    k_theo_tan_che: true            # false ⇒ K = số ô (semantics spatial_v1) ⇒ ablate riêng kênh habitat
```

Định cỡ (để cơ chế **có thể** binding cả hai chiều — không phải để ép kết quả):
K_gỗ = 308 ô × 60 = **18 480**; MSY = r·K/4 ≈ **231 gỗ/tick**. Một người logging toàn thời gian:
120 công / 10 công-mỗi-gỗ × 0.5 (không công cụ) = **6 gỗ/tick** (12 với công cụ). ⇒ ~20 người
toàn thời gian có công cụ mới vượt MSY. Rừng bờ `dan_cu` chỉ 91 ô ⇒ MSY bờ nhà ≈ **68 gỗ/tick**
⇒ áp lực vừa phải đã chạm trần bờ nhà. **Đây là lý do phải sweep** (§7 uncertainty): nếu `B_max`
quá lớn/`r` quá cao, cơ chế **trơ** (không bao giờ khan hiếm ⇒ null result do thiết kế, không do
hành vi); nếu quá nhỏ, rừng sập **bất kể** agent làm gì (kết quả bị ép về mặt cơ học).

**Ma trận ablation (paired seeds, `tools/counterfactual.py`):**

| Cell | Cấu hình | Câu hỏi |
|---|---|---|
| A0 | `rung.bat=false` (≡ `spatial_v1`) | baseline |
| A1 | `rung.bat=true` | gỗ hữu hạn có đổi phân bổ công/nhà/thuyền? |
| A2 | A1 + `ga_rung.k_theo_tan_che=false` | tách kênh habitat khỏi kênh khan-hiếm-gỗ |
| A3 | A1, `tai_sinh_moi_tick` ∈ {0.02, 0.05, 0.10} | độ nhạy tốc độ hồi |
| A4 | A1, `sinh_khoi_toi_da_moi_o` ∈ {30, 60, 120} | độ nhạy trữ lượng |
| A5 | A1, `hat_giong_tu_nhien = 0` | bất khả hồi sau clear-cut |
| A6 | A1 + `trong_rung.bat=true` | adoption reforestation (dự đoán: thấp, free-rider §1.5) |
| A7 | A1, `ty_le_thu_hoi_go_khi_khai_hoang` ∈ {0.0, 0.5} | đốt nương vs tận thu |
| A8 | A1, shock logging cao/thấp (paired seed, cùng policy) | dấu của chuỗi §2.2 |

**Điều kiện gate cứng (ADR 0005 §11.4):** overlay OFF ⇒ mọi code path P2 no-op ⇒
**world_hash + config_digest legacy BẤT BIẾN**. Không thêm bất kỳ key `khong_gian.*` nào vào
`config/world.yaml` (giữ base digest ⇒ resume guard `run.py:171` không vỡ).

---

## 7. Test matrix P2 (tên + assert — để `test-engineer` viết, KHÔNG phải tác giả code viết)

Thế giới nhỏ (8×8, 10 agent, ≤20 tick) trừ khi ghi rõ khác. Không hard-code seed để lấy kết quả
đẹp; shock áp bằng **intent** (kế hoạch logging), không bằng cách set state tay.

**Ecology — stock-flow (`tests/test_ecology_rung.py`, NEW)**

1. `test_off_rung_no_op_hash_legacy_bat_bien` — overlay OFF: 2 run cùng seed ⇒ cùng hash; và hash
   **không đổi** khi gán `p.sinh_khoi` bất kỳ (chứng minh field ngoài whitelist `world.py:478-493`).
2. `test_logging_giam_sinh_khoi_khong_doi_loai` — sau `khai_thac go`: `Σ B` ↓ đúng bằng gỗ thu
   (`ΔB == -kg` với `hieu_suat`/`he_so_may` đã tính); `p.loai == "rung"` **không đổi**.
3. `test_khong_thu_go_khi_rung_can` (**INVARIANT E1**) — B của mọi ô khả dụng = 0 ⇒ `go` thu = 0,
   `su_co` có `rung_can_kiet`, ledger không âm, audit xanh.
4. `test_extraction_khong_vuot_available` (property, hypothesis, nhiều seed) — với mọi lịch công
   ngẫu nhiên: `kg_thu ≤ Σ B_truoc`; `0 ≤ p.sinh_khoi ≤ B_max` mọi tick.
5. `test_stock_flow_identity_moi_tick` (**INVARIANT E2**) — `ΔΣB == tai_sinh − khai_thac −
   mat_do_khai_hoang + trong_rung` (|err| ≤ 1e-6) mọi tick.
6. `test_clearing_khac_logging` — `khai_hoang` ⇒ `loai` đổi + B → 0 + gỗ thu hồi = `ty_le × B`;
   `khai_thac` ⇒ `loai` giữ + B giảm dần. Hai đường có **hậu quả habitat khác nhau**.
7. `test_giam_ap_luc_thi_rung_hoi` — ngừng logging N tick ⇒ `Σ B` **tăng đơn điệu** về `B_max`
   (chiều ngược của (2)).
8. `test_hat_giong_zero_thi_bat_kha_hoi` (ablation A5) — `hat_giong_tu_nhien=0` ∧ B=0 ⇒ B ở 0 mãi.

**Ecology — habitat → gà (`tests/test_ecology_ga_rung.py`, NEW)**

9. `test_K_theo_canopy_khong_theo_so_o` — chặt 50% biomass của mọi ô rừng (không đổi `loai`) ⇒
   `_ga_rung_suc_chua` ≈ 50% giá trị cũ; số ô rừng **không đổi**.
10. `test_chuoi_nhan_qua_logging_shock` (bảng dấu §2.2) — paired seed, hai nhánh (shock/no-shock):
    assert dấu ở bước 1,2,3,4 và **catch tích lũy H tick** ↓; **assert `mat_do ≤ 1.0`, KHÔNG assert
    `mat_do` giảm** (bẫy §2.2).
11. `test_clamp_ton_khi_K_giam_co_event` — K < ton ⇒ `ton == K`, event `ga_rung_suc_chua_giam` có
    `mat > 0`; `kiem_toan(ledger)` **vẫn xanh** (pool ngoài ledger).
12. `test_K_bang_0_thi_bat_ga_tra_0_co_reason` — chặt/khai hoang hết rừng ⇒ `ton == 0`, `bat_ga`
    mint 0 `ga_con`, reason `habitat_can_kiet`.
13. `test_property_0_le_ton_le_K` (property, nhiều seed, ≥30 tick) — mọi tick: `0 ≤ ga_rung_ton ≤
    _ga_rung_suc_chua(w)`; và cùng thế cho `ca_ton`/`_ca_suc_chua`.
14. `test_nuoi_ga_khong_duoc_buff_khi_ga_rung_can` (**anti-teleology**) — sản lượng/chi phí đàn
    nuôi **giống hệt** ở hai nhánh `ga_rung_ton` cao/thấp (chỉ khác qua cửa `bat_ga`).

**Gỗ ↔ recipe/project (`tests/test_ecology_go_recipe.py`, NEW)**

15. `test_go_khan_hiem_thi_nha_va_thuyen_canh_tranh` — tổng gỗ khả dụng < (8 + 6) ⇒ chỉ một trong
    hai hoàn thành; ledger + audit xanh; không double-consume.
16. `test_clearing_wood_house_boat_flows_reconcile` — chuỗi khai hoang → gỗ thu hồi → đóng thuyền
    → xây nhà: `kiem_toan_the_gioi` xanh **mỗi tick**; số thửa không đổi; `go` khớp
    FlowRegistry.

**Spatial / ferry (`tests/test_ferry.py` mở rộng + `tests/test_ferry_project.py` NEW)**
17–26: đúng 6 case Report §6 + các case NEW ở bảng §4: F1 (giữ), F2+ownership-no-boat (NEW),
F3 (giữ), F4+multi-operator+no-double-cross (NEW), F5 expiry/fare-trả-sau (NEW), F6 project
(NEW, sau P1), F7 hao mòn về 0 (NEW), F8 transient access (NEW), **F9 far-bank leak gỗ/quặng
(NEW, blocking)**, F10 khai hoang giảm K (NEW), F11 parity LLM schema↔translate↔handler (NEW,
sau P0).

**Crop (`tests/test_crop_facts.py`, NEW)**

27. `test_crop_khac_nhau_chi_do_vat_ly` — hai agent **giống hệt** (cùng `mau_mo`, `tay_nghe`,
    health, công) trồng ngô vs khoai ⇒ chênh lệch sản lượng + food-equivalent **đúng bằng** tỷ lệ
    config; không có hằng số nào khác trong công thức.
28. `test_engine_khong_chon_cay` — grep-level/behavioral: với `kh.canh_vu_dong = []`, engine trồng
    **0** thửa (không có default cây); đổi thứ tự crop trong config **không** đổi outcome.
29. `test_card_khong_xep_hang` — card render ra: có đủ 11 trường §5.3; thứ tự tất định theo
    `(hoat_dong, doi_tuong)`; **không** chứa `xep_hang`/`khuyen_nghi`; `san_luong_ky_vong` **bằng
    đúng** sản lượng engine giao khi thực thi (so sánh card vs kết quả thực thi, sai số 0).

**Determinism / regression**

30. `test_replay_same_seed_same_hash_v2` — overlay v2 ON: 2 run cùng seed ⇒ cùng hash; replay từ
    checkpoint ⇒ cùng hash (`sinh_khoi` sống trong pickle + migration).
31. `test_overlay_off_hash_legacy_bat_bien` (**gate cứng**) — `preindustrial_closed_v1` + base
    `agrarian_transition_v1`: hash **bằng** giá trị của HEAD trước diff (so bằng cách chạy cùng
    seed trên cả hai commit trong CI, hoặc pin hash trong test **sau khi** đo — không tự bịa).
32. `test_config_off_block_bang_khong_co_block` — config có `khong_gian.rung.bat=false` cho hash
    **giống** config không có block `rung` (yêu cầu sửa `_behavioral_config` `world.py:90`).
33. `test_migration_checkpoint_cu` — nạp checkpoint trước-P2 (OFF và spatial_v1) ⇒ không exception;
    hash OFF không đổi.

Lệnh chạy tối thiểu trước handoff:

```powershell
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m pytest -q --basetemp .tmp\pytest
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m ruff check .
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m tools.verify_local
```

---

## 8. Bất định tham số & giải thích thay thế (bắt buộc report, không được lờ)

1. **Không có tham số nào ở đây là `calibrated_fact`.** `B_max`, `r`, `s`, `suc_chua_moi_o`,
   `cong_moi_go` đều là `design_assumption`. Kết luận "khai thác gỗ làm giảm gà rừng" là
   **mechanism_result của một tập luật do ta viết**, không phải phát hiện về thế giới thật.
2. **Cơ chế có thể trơ hoặc bị ép** tùy định cỡ (§6): MSY ≫ áp lực lao động khả dĩ ⇒ không bao giờ
   khan hiếm (null do thiết kế); MSY ≪ áp lực ⇒ rừng sập bất kể hành vi (kết quả cơ học). Cả hai
   đều **không** là bằng chứng về hành vi agent. ⇒ **Phải sweep A3/A4 và report toàn phân phối.**
3. **Confound bắt buộc kiểm soát:** logging shock đồng thời làm (a) K↓ (kênh habitat) và (b) gỗ↓ ⇒
   nhà khó xây ⇒ `vo_gia_cu` ↑ ⇒ health↓ ⇒ tử vong↑ ⇒ **công lao động toàn làng ↓** ⇒ catch gà
   giảm **vì ít người đi bắt**, không phải vì ít gà. Tách bằng ablation **A2**
   (`ga_rung.k_theo_tan_che=false`) và bằng cách chuẩn hóa catch theo **công bắt gà đã chi**, không
   theo tổng số con.
4. **Giải thích thay thế cho "nuôi gà tăng sau shock"**: (i) giá `ga`/`thit` tăng do khan hiếm ⇒
   người **mua** gà, không phải người bắt gà, mở rộng đàn; (ii) hộ chuyển sang nuôi vì **dư thóc**,
   không vì rừng cạn; (iii) hiệu ứng của `truong_thanh_ga` trễ một tick. Không được kết luận "cạn
   kiệt gây ra chăn nuôi" nếu chưa loại các đường này bằng paired-seed.
5. **Giải thích thay thế cho "đò xuất hiện"**: đò có thể xuất hiện vì **quặng** (100% bờ hoang)
   chứ không vì gỗ, hoặc vì **đất khai hoang**, hoặc không xuất hiện gì cả. Metric phải phân rã
   theo **mục đích chuyến** (hoạt động thực thi ở bờ kia sau khi qua), không chỉ đếm chuyến.
6. **Không ép occupation.** Nếu sau P2 không ai làm nghề rừng/đò/chăn nuôi, đó là **kết quả hợp
   lệ** và phải được report nguyên trạng (Report_v2 §7.3: "Report both activation and
   non-activation... Do not tune to force any path").

---

## 9. Findings (severity / owner / fix)

| ID | Sev | Finding | Owner | Fix bắt buộc |
|---|---|---|---|---|
| **F-1** | **Blocking** | Gỗ mint vô hạn (G1) — `rung` là nhãn, không phải stock | `engine-surgeon` | §1: `Parcel.sinh_khoi` + 4 flow + E1/E2 |
| **F-2** | **Blocking** | K gà rừng = số ô (G2) ⇒ **không tồn tại** feedback logging→habitat (Report §3 hàng cuối) | `engine-surgeon` | §2.1 canopy-weighted K + cờ `k_theo_tan_che` |
| **F-3** | **Blocking** | Khai thác gỗ/quặng bỏ qua `co_the_o_bo` (G3) — 100% quặng ở bờ hoang vẫn lấy được từ nhà ⇒ đò/hai-bờ **chỉ là chuyện kể**, không phải ràng buộc vật lý | `engine-surgeon` | thêm gate bờ vào `production.py:353-376`; test F9 |
| **F-4** | High | Hash: thêm field Parcel ⇒ `spatial_v1` ON đổi hash; và nhánh whitelist sẽ **giấu** biomass khỏi hash nếu `hai_bo=false, rung=true` | `engine-surgeon` + `reproducibility-steward` | §1.4: mở rộng điều kiện chiếu + thêm `"rung"` vào `_behavioral_config` `world.py:90`; ghi `DECISIONS.md` |
| **F-5** | High | Clamp `ton` khi K giảm + K=0 ⇒ `ton=0` **âm thầm** (`chan_nuoi.py:201-208`) | `engine-surgeon` | event `ga_rung_suc_chua_giam` + reason code |
| **F-6** | High | Crop card `prompts.py:110-117` khuyết `quy_doi_dinh_duong` và dùng hệ số gốc như thể là kỳ vọng ⇒ **xếp hạng ngầm theo kg** | `minds-engineer` (P3) | §5.3 card schema; sinh từ preflight engine |
| **F-7** | Medium | Không tham số `khong_gian.*` nào có dòng `provenance.csv` (G6) | `spec-governor` | thêm row `parameter,unit,status=design_assumption` cho mọi param cũ + mới |
| **F-8** | Medium | Không có expiry/deferred-fare cho đò; `rao_do` sống 1 tick (semantics ngầm) | `engine-surgeon` + `test-engineer` | §4 F5: test khẳng định semantics + fare-trả-sau qua clause |
| **F-9** | Info | Reforestation **chưa tồn tại**; habitat là public good ⇒ dự đoán adoption thấp nếu thêm | `research-planner` | §1.5 PENDING spec; không report như đã có |
| **F-10** | Info | `bat_ga` không hỏi `p.chu` ⇒ habitat commons kể cả trên rừng có chủ | — | giữ (có chủ ý), nêu trong report |

---

## 10. Claim boundary

Memo này **chứng minh** (bằng file:line + probe không mạng): gỗ hiện lấy vô hạn; K gà rừng đếm ô;
khai thác gỗ/quặng không bị sông chặn; `spatial_v1` băm toàn bộ dataclass `Parcel` còn legacy băm
whitelist 11 khóa; đường LLM cho 3 action đò không tồn tại; card vụ đông khuyết hệ số dinh dưỡng.

Memo này **KHÔNG chứng minh**: rằng agent sẽ chặt rừng, sẽ chuyển sang chăn nuôi, sẽ mở dịch vụ
đò, hay rằng bất kỳ nghề nào sẽ xuất hiện. Nó **không** thiết lập bất kỳ con số sinh thái nào là
đúng với thực tế lịch sử. Sau khi implement, trạng thái cao nhất có thể đạt là
**`mechanism-ready`** (có scenario + ablation + execution data), **không** phải
`empirically-validated`.

## 11. Next handoff

- `spec-governor`: quyết F-4 (đổi hash `spatial_v1` — chấp nhận Phương án A, hay ép Phương án B?),
  ghi `DECISIONS.md`; thêm provenance rows (F-7).
- `engine-surgeon`: implement §1 (`types.py`, `production.py`, `world.py`, `chan_nuoi.py`,
  `tick.py`, `spatial.py`), F-3, F-5; **serial** (đụng hotspot `world.py`/`tick.py`/`production.py`
  — ADR 0005 §15).
- `test-engineer` (độc lập): §7, ưu tiên 1, 3, 4, 5, 10, 11, 13, 14, F9, 31, 32.
- `minds-engineer` (P3, sau P0): §5.3 card; `agrarian-economist`: review định cỡ §6.
- `reality-auditor` + `adversarial-reviewer`: gate độc lập trên F-1…F-6.
