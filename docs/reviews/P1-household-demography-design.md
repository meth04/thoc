# P1 — Design memo: residence/household, life-course, estate, mortality metrics

- Vai: `household-demography-specialist` (độc lập, KHÔNG implement).
- Verdict: **DESIGN ONLY**. Không sửa file production, không sửa test, không chạy real/API/network.
- Ngày: 2026-07-13. Commit khảo sát: `db8e4fb`. Authority: `Report_v2.md` §4.2, §5 P1, §6.
- Claim tier của mọi số trong memo này: `design_assumption` (thiết kế) + `mechanism_result`
  (chẩn đoán từ artifact đã có, một seed, một run). **Không có** `calibrated_fact`/`validated_result`.
- Tài liệu chi phối: `docs/MODEL_CHARTER.md` §1/§3/§5; ADR 0001 §A/§D; ADR 0003 §A/§E/§F;
  ADR 0005 §11 (khuôn scenario-gate + hash + migration).

Memo này là input cho **ADR 0006 (successor của ADR 0003 về hộ/estate)** mà `model-architect` +
`agrarian-economist` phải viết trước khi `engine-surgeon` chạm code (Report_v2 §5 P1.1, §7.1).

---

## 0. Bằng chứng (file:line + artifact + command)

### 0.1 Code (đọc trực tiếp)

| # | Sự thật | Chứng cứ |
|---|---|---|
| E1 | Hộ = **derived view** từ quan hệ huyết thống; chỉ gồm chủ hộ + vợ/chồng + con **CHƯA TRƯỞNG THÀNH** | `engine/world.py:433-457` (`ho_cua`), đặc biệt `:455` `not c.truong_thanh(tt)` |
| E2 | Người vừa chạm `tuoi_truong_thanh` ⇒ `ho_cua(aid)` trả về **[chính họ]** (vòng lặp `:439-445` chỉ chuyển lên hộ cha/mẹ khi CHƯA trưởng thành) | `engine/world.py:438-446` |
| E3 | Ăn theo hộ, đốt thóc **của từng thành viên** trong hộ đó | `engine/consumption.py:50` (`ho = w.ho_cua(aid)`), `:63-70` (`huy(m, ts, ...)` theo `sorted(ho, key=-ton_kho)`) |
| E4 | ⇒ người vừa 16 tuổi, 0 tài sản, **ăn 0 kg** dù cha mẹ đầy thóc; không có event nào ghi "ai nuôi ai" | E2 + E3; không có event `cap_luong_thuc`/transfer nào trong `consumption.py` |
| E5 | Survival floor **không cứu được** người mới trưởng thành: điều kiện gieo là `own_grain >= giong` | `minds/safety.py:45-47` |
| E6 | Người mới trưởng thành cũng **không được LLM nhìn thấy** như thành viên gia đình: prompt render hộ từ `ho_cua` | `minds/prompts.py:589`, `minds/policy_cards.py:37`, `minds/triggers.py:62` |
| E7 | Tài sản không người thừa kế → `VO_THUA_NHAN`, **không claim window, không auction, không đích cuối** | `engine/demography.py:279` (`chuyen(aid, VO_THUA_NHAN, ts, sl, ...)`), `engine/world.py:23` |
| E8 | `VO_THUA_NHAN` **không phải chủ thể hoạt động** ⇒ không ai giao dịch, trộm, ký hợp đồng, nhận đất với nó ⇒ **kẹt vĩnh viễn** | `engine/world.py:315-321` (`chu_the_hoat_dong`), `engine/contracts.py:118-121`, `engine/xa_hoi.py:52-53`, `engine/entities.py:265-268`, `engine/audit.py:29-31` |
| E9 | Đàn gà của chủ không hoạt động **đứng im** (không ăn, không đẻ) ⇒ gà trong estate là stock chết | `engine/chan_nuoi.py:27-29` |
| E10 | **Nợ chết theo con nợ.** Hợp đồng có một bên chết ⇒ `trang_thai = "huy"` + `dot_vi_the`, **không settlement** | `engine/contracts.py:342`, `:423-425` |
| E11 | Thứ tự tick khiến chủ nợ **không bao giờ** đòi được từ người chết: hợp đồng chạy bước 7, chết + thừa kế chạy bước 9 (cùng tick), nên đến bước 7 tick sau thì di sản đã chia xong | `engine/tick.py:222` (hợp đồng) vs `engine/tick.py:242` (`buoc_nhan_khau`) |
| E12 | Entity **đã có** khuôn thanh lý đúng (chủ nợ → cổ đông → về công) — người thì không | `engine/entities.py:243-275` (`thanh_ly`), `:194-212` (`kiem_tra_pha_san`) |
| E13 | `behavioral_state()` băm **toàn bộ dataclass `Agent`** (`"population": self.agents` + `_canonical_state` duyệt `fields()`) ⇒ **thêm 1 field vào `Agent` là đổi hash của MỌI run, kể cả legacy** | `engine/world.py:515`, `:38-42` |
| E14 | Tiền lệ loại một field khỏi hash khi overlay OFF: `Parcel.bo` bị **project bỏ** khỏi `parcels` khi `hai_bo` tắt | `engine/world.py:470-493` |
| E15 | Tiền lệ observation-state ngoài hash + migration `nap_checkpoint` | `engine/world.py:199-213`, `:668-688`; ADR 0003 §E/§F |
| E16 | Metrics **không có một chỉ số tuổi/tử vong nào**: không age-at-death, không death rate, không dependency ratio | `engine/metrics.py:143-195` (`tinh_metrics`) — grep `tuoi_tho|life_expect|age_at_death` toàn repo: 0 match trong `engine/`, `tools/`, `observatory/` |
| E17 | `poverty_streak` khóa theo **head-id**, gãy khi head chết/đổi (ADR 0003 §E tự thừa nhận) | `engine/tick.py:271-280`, ADR 0003 §E |

### 0.2 Artifact (chỉ đọc `data/runs/`, không sửa)

Command (đã chạy, `THOC_BLOCK_NETWORK=1`, không mạng):

```
conda run -n thoc-env python <script đọc data/runs/*/events.jsonl + checkpoints/*.pkl>
```

**(a) Chữ ký bệnh "adult-orphaning" — `real60_spatial`, vùng KHÔNG bị nhiễm resume (tick ≤ 105):**

- 17 ca chết: `tuoi_gia` 14, `kiet_suc` 1, **`chet_doi` 2**.
- Cả 2 ca `chet_doi` là người **sinh trong mô phỏng, chết ở tuổi 17.7 và 18.3**: `A0051` (tick 100),
  `A0052` (tick 104).
- **Toàn bộ 3 agent từng có event `an_doi`** đều là trẻ sinh trong sim, và **event đói ĐẦU TIÊN rơi
  đúng vào tick trưởng thành ±1**:

  | agent | sinh (tick) | trưởng thành (tick, 16 tuổi = +48 tick ở calendar 3 mùa) | `an_doi` đầu tiên | chết |
  |---|---|---|---|---|
  | A0051 | 47 | **95** | **95** (`ty_le_no=0.0`) | 100, `chet_doi`, 17.7 tuổi |
  | A0052 | 49 | **97** | 98 | 104, `chet_doi`, 18.3 tuổi |
  | A0053 | 57 | **105** | **105** | 110, `chet_doi`, 17.7 tuổi |

- Trong khi đó cha/mẹ của A0051 (`A0026`, `A0040`) giữ **3429.8 / 3329.6** (quy thóc) tại
  `giai_cap_snapshot` tick 90 — và A0051 ăn **0.0**.
- **Không một người lớn t0 nào chết đói.** Bệnh chỉ đánh vào đúng nhóm vừa qua sinh nhật 16.

**(b) Bệnh là ENGINE, không phải LLM** — `mock60_spatial` (cùng engine, cùng seed 42, cùng config,
policy heuristic PersonaBot, KHÔNG LLM):

- **168** agent sinh-trong-sim từng có `an_doi`; **159 (94.6%)** có event đói đầu tiên **trong ±1
  tick quanh đúng tick trưởng thành**.
- Mock 0 ca `chet_doi` (kinh tế mock có 383 hợp đồng gop_cong ⇒ người trẻ kiếm được thóc sau đó),
  nhưng **chữ ký đói-lúc-16-tuổi vẫn y hệt**. ⇒ Đây là **defect vật lý/kế toán của engine**, tái lập
  dưới policy phi-LLM.

**(c) Wealth sink `VO_THUA_NHAN` — checkpoint cuối `real60_spatial` (tick 180):**

| tài sản | VO_THUA_NHAN giữ | tổng thế giới | % kẹt |
|---|---:|---:|---:|
| `thoc` | **41 329.0** | 44 693.0 | **92.5%** |
| `khoai` | 7 576.8 | 7 725.7 | 98.1% |
| `go` | 2 649.1 | 2 790.3 | 94.9% |
| `ga` | 25.7 | 25.7 | **100%** |
| `nha` | **1.0** | 1.0 | **100%** (căn nhà DUY NHẤT của thế giới) |
| `cong_cu` | 15.0 | 16.0 | 93.8% |

2 người sống sót giữ 3364 kg thóc và **vô gia cư vĩnh viễn** — trong khi căn nhà duy nhất tồn tại,
nằm trong tài khoản không ai chạm tới được (E8). 897/900 thửa `chu=None` (về công — đường này ổn).
45 event `thua_ke` với `nguoi_nhan=["cong"]` (không người thừa kế).

**(d) Journal của run này còn bị nhiễm resume (P0.2):** events `chet` bị **lặp** ở tick 106/110/112
(`A0031`, `A0053`, `A0003` xuất hiện 2 lần), và `A0054` chết ở tick 116 **và** 118 với tuổi khác nhau
⇒ file chứa **hai lịch sử phản-thực chồng lên nhau** trong vùng 106–117. Mọi con số tử vong tính từ
`events.jsonl` của run này ở vùng đó **sai theo định nghĩa**.

### 0.3 Hash baseline (đóng cọc cho gate cứng)

Chạy tại commit `db8e4fb`, rulebot, 20 tick (`THOC_BLOCK_NETWORK=1`):

```
LEGACY_OFF  seed=11 t=20 : 4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b
LEGACY_OFF  seed=42 t=20 : f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153
SPATIAL_ON  seed=11 t=20 : afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745
```

**Ba chuỗi này là điều kiện gate cứng của P1**: sau khi implement, chạy lại đúng ba cấu hình đó với
overlay hộ **TẮT** phải ra **đúng ba hash này**. Lệch một ký tự = FAIL, không thương lượng
(ADR 0001 §D, ADR 0005 §11.4).

---

## 1. Residence/household: state BỀN hay derived view?

### 1.1 Quyết định

> **Residence là STATE BỀN, sở hữu bởi engine, gated theo scenario. `ho_cua()` trở thành một
> *lookup* trên state đó khi gate ON, và giữ nguyên hành vi derived-view legacy khi gate OFF.**

Cụ thể (phương án NHỎ NHẤT):

- Thêm **World-level** side table (KHÔNG thêm field vào `Agent` — xem §1.4):
  ```python
  @dataclass
  class CuTru:                      # engine/household.py
      id: str                       # "R0001"
      thanh_vien: list[str]         # SORTED, single source of truth
      nha_thua: str | None          # thửa đặt nhà của hộ (nếu có)
      quy_tac_cap: str              # "nhu_cau_deu" (mặc định, công khai)
      lap_tick: int
  # World:
  cu_tru: dict[str, CuTru] = {}     # rid → CuTru
  _next_cu_tru: int = 0
  ```
- `w.ho_cua(aid)`: nếu `_ho_bat(w)` → trả `sorted(m for m in cu_tru[rid_cua(aid)].thanh_vien if còn sống)`;
  ngược lại → **giữ nguyên code hiện tại từng dòng** (`world.py:433-457`).
- `economy.households(w)` (`economy.py:15`) trở thành wrapper mỏng: ON → `[cu.thanh_vien (còn sống)]`;
  OFF → nguyên trạng. Nhờ vậy **mọi call-site tự đúng theo** mà không phải sửa từng nơi:
  `consumption.py:50,122`, `care.py:18`, `demography.py:112,126`, `metrics_research.py:397`,
  `minds/safety.py:31`, `minds/prompts.py:589`, `minds/policy_cards.py:37`, `minds/triggers.py:62`,
  `minds/rulebot.py:187,421,908,990,1004`, `minds/world_tools.py:172`, `tick.py:272`.

### 1.2 Reconcile ADR 0003 (KHÔNG tạo layer song song)

ADR 0003 §A.1 chốt "hộ là derived view, không object `Household`, không state mới cần hash". Lý do nó
đưa ra: *"Cưới/sinh/chết/tái hôn/cưu mang đã thay đổi `Agent.vo_chong/cha/me/giam_ho/con/con_nuoi`
nên hộ tự cập nhật"* (ADR 0003 §A.1). **Tiền đề đó SAI**, và bằng chứng là §0.2(a)/(b):

> **Quan hệ huyết thống không mã hóa được đồng-cư-trú.** Sinh nhật thứ 16 không phải một biến cố
> quan hệ (không event, không quyết định, không ledger) nhưng nó **đổi membership** của hộ trong
> `ho_cua()` ⇒ đổi ai được ăn ⇒ đổi ai sống. Một biến-cố-không-tồn-tại không được phép có hệ quả
> vật lý (Report_v2 §4.2: "Thành viên trưởng thành không tự tách chỉ vì sinh nhật; tách chỉ qua event
> rõ ràng").

Vì vậy ADR 0006 **supersede ADR 0003 §A.1** (membership) và **GIỮ NGUYÊN ADR 0003 §A.2** (không pantry
chung — xem §2), §A.3 (bốn khoản income/consumption/assets/liquidity không lẫn), §B (identity theo hộ),
§C (metric undefined thay vì 0 giả), §E/§F (khuôn observation-state + migration). Đây là **một** trục
kế thừa, không phải hai hệ hộ song song.

### 1.3 Alternatives đã cân nhắc

| Phương án | Vì sao KHÔNG chọn |
|---|---|
| **A. Giữ derived view, chỉ nới `ho_cua` cho "con trưởng thành chưa lập gia đình"** | Vẫn là suy diễn từ huyết thống: không phân biệt được người con 30 tuổi đã ra ở riêng với người con 17 tuổi còn ở nhà; không có chỗ treo event `tach_ho`; không đo được migration; và **vẫn đổi hash vô điều kiện** nên chẳng rẻ hơn. Nó chỉ dời cái bug sang tuổi khác. |
| **B. `Agent.residence_id: str`** | Ngắn gọn hơn về mặt code, nhưng `behavioral_state()` băm **mọi field của dataclass `Agent`** (E13) ⇒ legacy hash đổi ngay khi field tồn tại (kể cả `None`). Muốn giữ hash phải **project bỏ field** khi gate OFF theo kiểu `Parcel.bo` (E14) — cơ chế đó **giòn**: field `Agent` thêm sau này sẽ âm thầm rơi khỏi hash khi overlay OFF. Rủi ro reproducibility cao hơn lợi ích cú pháp. |
| **C. Object `Household` là chủ thể ledger (có pantry)** | Xem §2 — bị ADR 0003 §A.2 loại, và tạo đúng loại "chủ thể ma có vòng đời" mà §4 đang phải dọn (`VO_THUA_NHAN`). |
| **D (CHỌN). World-level `w.cu_tru` + key hash có điều kiện** | Không đụng `Agent`; key `"residence"` chỉ **được chèn vào `behavioral_state()` khi gate ON** ⇒ OFF cho ra **JSON y hệt hôm nay** ⇒ ba hash §0.3 bất biến; state bền, có id, có lifecycle, có event, checkpoint được. |

### 1.4 Hash / serialization / migration — chính xác phải làm gì

**`engine/world.py:460` `behavioral_state()`** — thêm ĐÚNG một khối, **có điều kiện**:

```python
# ... sau "production": {...}
if _ho_bat(self):                      # engine/household.py, đọc cfg.get("ho.bat", False)
    state["residence"] = {
        "cu_tru": self.cu_tru,         # dict[str, CuTru] — dataclass, _canonical_state tự duyệt
        "next_id": self._next_cu_tru,
    }
```

- **Gate OFF ⇒ KHÔNG có key `"residence"`** ⇒ blob JSON không đổi một byte ⇒ `world_hash()` không đổi
  ⇒ ba hash §0.3 giữ nguyên, mọi checkpoint/artifact cũ vẫn verify được. **Không** bump `hash_schema`
  (giữ `"behavioral-state-v2"`), **không** thêm key rỗng "cho đẹp" (key rỗng cũng đổi hash).
- **Gate ON ⇒ hash khác** — đúng và mong muốn (thí nghiệm khác, ADR 0005 §11.4). Hai run cùng
  seed+overlay phải cùng hash.
- `_next_cu_tru` **phải** vào hash khi ON (nó quyết định id hộ tương lai ⇒ ảnh hưởng tie-break ⇒ ảnh
  hưởng hành vi). Đặt trong khối `"residence"`, KHÔNG nhét vào `state["ids"]` (nhét vào `ids` là đổi
  layout khi OFF).

**`engine/world.py:618` `nap_checkpoint()`** — thêm migration trung tính (khuôn `ca_ton`/`ben_kia_tick`,
`world.py:669-688`):

```python
if not hasattr(w, "cu_tru"):
    w.cu_tru = {}
if not hasattr(w, "_next_cu_tru"):
    w._next_cu_tru = 0
```

Checkpoint cũ (OFF) nạp lại ⇒ `cu_tru = {}` ⇒ key `"residence"` vẫn không xuất hiện (gate OFF) ⇒
**hash y nguyên** ⇒ resume của run cũ không gãy.

**Khởi tạo khi ON:** `household.khoi_tao_cu_tru(w)` gọi **một lần** ở `tao_the_gioi` (sau khi tạo
agent, `world.py:833`): mỗi agent t0 = một `CuTru` riêng (t0 toàn người lớn độc thân — `world.py:788`),
id cấp theo `sorted(w.agents)`. **Cấm bật gate giữa run**: `run.py` đã chặn đổi config khi resume
(config digest guard); ADR 0006 phải ghi rõ "gate hộ là thuộc tính của run, không được bật/tắt giữa
chừng" và test resume phải chứng minh.

### 1.5 Cổng scenario — tên cờ và mặc định

Theo khuôn ADR 0005 §11.2 (**không thêm key vào base `config/world.yaml`** để giữ `cfg.digest()` base
bất biến, đọc bằng `cfg.get("...", False)`):

```yaml
# scenarios/spatial_livelihood_v2/... (overlay MỚI, không sửa spatial_v1.yaml)
ho:
  bat: false                 # cờ tổng — MẶC ĐỊNH TẮT
  cu_tru_ben_vung: false     # §1: membership bền, trưởng thành không tự tách
  cap_luong_thuc: false      # §2: provisioning có ledger + event
  tach_ho:                   # §3: split tường minh
    bat: false
  di_san:                    # §4: estate lifecycle
    bat: false
    claim_han_tick: 3        # = 1 năm ở calendar 3 mùa (design_assumption)
    het_han: "cong"          # "cong" | "dau_gia"
```

Helper `engine/household.py:_ho_bat(w)`, `_cu_tru_bat(w)`, `_cap_luong_thuc_bat(w)`, `_di_san_bat(w)`
— **đúng khuôn `engine/spatial.py:_khong_gian_bat`** (`spatial.py:16-40`): mỗi sub-flag TẮT ⇒ path đó
no-op độc lập ⇒ ablation làm được từng trục.

- `preindustrial_closed_v1`: **TẮT vĩnh viễn** (legacy regression, charter §6). Semantics lỗi được
  **đóng băng có ghi chú**, không retcon.
- `agrarian_transition_v1` (base) + overlay `spatial_v1`: **TẮT** ⇒ artifact `real60_spatial` /
  `mock60_spatial` vẫn verify được hash cũ.
- **`spatial_livelihood_v2`** (scenario mới của Report_v2 §1): **BẬT toàn bộ**.

> Nếu sửa `ho_cua()` vô điều kiện: mọi run legacy đổi hash ⇒ vi phạm ADR 0001 §D + ADR 0005 §11.4 ⇒
> **package FAIL**. Gate là bắt buộc, không phải tùy chọn.

### 1.6 Invariants (§1)

- **R1 (partition):** cuối mỗi tick, mỗi agent còn sống thuộc **đúng một** `CuTru`. Σ|thành viên sống|
  = số agent sống.
- **R2 (no birthday orphaning):** membership **không đổi** vì tuổi. Chỉ 6 biến cố đổi membership:
  `sinh`, `cuoi`, `tach_ho`, `cuu_mang`, `di_cu`, `chet`.
- **R3 (event-explainable):** diff membership giữa tick t−1 và t phải được giải thích **hết** bởi các
  event của tick t (replay membership từ event journal ⇒ trùng state).
- **R4 (no dead resident):** không agent chết nào còn trong `thanh_vien` cuối tick; `CuTru` rỗng ⇒ bị
  giải thể + event `tan_ho`.
- **R5 (OFF ⇒ y nguyên):** gate OFF ⇒ `ho_cua`, hash, hành vi, metrics **không đổi một bit**.

### 1.7 Failure cases

- `CuTru` rỗng (cả nhà chết) ⇒ giải thể, `nha_thua` trở về... **không có gì** (nhà là tài sản cá nhân
  trong ledger, đi theo estate §4 — `CuTru.nha_thua` chỉ là con trỏ vị trí, không phải quyền sở hữu).
- Trẻ mồ côi chưa được cưu mang trong tick chết của cha mẹ: `cuu_mang_mo_coi` (`tick.py:246`) chạy ngay
  sau `buoc_nhan_khau` ⇒ `buoc_cu_tru` (§3) chạy **sau** nó ⇒ trẻ luôn có hộ trước khi tick kết thúc.
  Nếu **không ứng viên nào** (`xa_hoi.py:145-146` `continue`) ⇒ trẻ giữ `CuTru` cũ (nay chỉ còn mình
  nó) ⇒ nó đói thật. Đó là kết quả hợp lệ (không có ai nuôi), **khác hẳn** với việc bị engine cắt khỏi
  hộ cha mẹ còn sống.
- Split khiến người tách vô gia cư: hợp lệ, đã có cơ chế phạt health (`consumption.py:116-130`).

---

## 2. Provisioning: (A) pantry hay (B) sở hữu cá nhân + event/ledger?

### 2.1 Quyết định

> **Chọn (B): tài sản vẫn là CỦA CÁ NHÂN. Việc nuôi nhau trong hộ trở thành một dịch chuyển tài sản
> TƯỜNG MINH: `ledger.chuyen(người-cấp → người-ăn)` NGAY TRƯỚC `ledger.huy(người-ăn, "an")`, kèm event
> `cap_luong_thuc`.** Giữ nguyên ADR 0003 §A.2 ("KHÔNG thêm pantry chung").

### 2.2 Lý do

1. **ADR 0003 §A.2 đã loại pantry** với lý do vẫn đúng: pantry là **một chủ thể ledger mới có vòng
   đời sinh/giải thể** — tức là đúng loại vật thể đang gây ra thảm họa `VO_THUA_NHAN` ở §4. Thêm một
   ghost-subject mới trong khi đang dọn ghost-subject cũ là tự mâu thuẫn.
2. (B) **đóng đúng cái lỗ Report_v2 §4.2 nêu**: "Không dùng một helper read-only để ngầm tiêu thóc
   người khác mà không có event/đối ứng." Hiện tại `consumption.py:69` đốt thóc của thành viên khác
   **không có bất kỳ dấu vết nào** về ai nuôi ai.
3. (B) cho ta **đo được transfer/provisioning** (Report_v2 §P4: "transfer/provisioning" là metric bắt
   buộc) mà không cần một tài khoản mới.
4. **Bonus reproducibility (quan trọng):** `chuyen` là bút toán CÂN (không đụng `FlowRegistry`), và
   lượng `huy` theo từng tài sản **không đổi** ⇒ số dư cuối tick **giống hệt** hôm nay ⇒
   **`ho.cap_luong_thuc` BẬT một mình (membership giữ legacy) là HASH-NEUTRAL**. Đây là một tính chất
   test được, và nó tách bạch "cái gì đổi hash" (membership) khỏi "cái gì chỉ thêm sổ sách"
   (provisioning). Yêu cầu test riêng cho tính chất này (§6 T-14).

### 2.3 Thiết kế chi tiết

Trong `engine/consumption.py:an_va_suc_khoe`, phần rút kho (`:60-70` và `:73-85`), khi
`_cap_luong_thuc_bat(w)`:

```python
# thay cho: w.ledger.huy(m, ts, tru, "an", ...)
if m != nguoi_an:                       # rút kho người khác trong hộ
    w.ledger.chuyen(m, nguoi_an, ts, tru, f"cấp lương thực {ts}", w.tick)
    w.events.ghi(w.tick, "cap_luong_thuc",
                 tu=m, den=nguoi_an, tai_san=ts,
                 so_luong=round(tru, 6), quy_thoc=round(tru * quy_doi, 6),
                 ho=rid, ly_do="quy_tac_ho")
w.ledger.huy(nguoi_an, ts, tru, "an", f"ăn {ts}", w.tick)
```

- **Ai là `nguoi_an`?** Quy tắc phân bổ phải **công khai + tất định**, gắn trên `CuTru.quy_tac_cap`:
  mặc định `"nhu_cau_deu"` = mỗi thành viên được cấp đúng `nhu_cau` của mình (người lớn
  `nhu_cau.nguoi_lon_kg_tick`, trẻ `nhu_cau.tre_em_kg_tick`); **nguồn rút** theo đúng thứ tự hiện có
  (`sorted(ho, key=lambda x: -ton_kho[x])`, `consumption.py:64`) — kho lớn nhất gánh trước. Thiếu tổng
  ⇒ **thiếu đều theo tỷ lệ** (giữ đúng `ty_le_no` chung của hộ như hôm nay — không tạo luật ưu tiên
  trẻ em/người già; đó sẽ là một treatment riêng, có ablation).
- **Bảo toàn:** `chuyen` cân theo từng tài sản (`ledger.py:122-124`), `huy` dùng sink `"an"` đã đăng ký
  (`world.py:696`). Không mint, không double-consume: mỗi kg đi qua **đúng một** `chuyen` (tùy chọn) và
  **đúng một** `huy`. `kiem_toan_the_gioi` xanh không đổi.
- **Không âm số dư:** `tru = min(ton_kho[m], thieu/quy_doi)` giữ nguyên ⇒ `chuyen` không bao giờ vượt số dư.

### 2.4 Ranh giới: "ai được ăn ké kho ai"

Ba điều kiện **đồng thời**, không có ngoại lệ:

1. **Membership**: người ăn và người cấp cùng **một `CuTru`** (R1). Ngoài hộ ⇒ 0 kg, không có đường
   nào khác trong `an_va_suc_khoe`.
2. **Rule công khai**: `CuTru.quy_tac_cap` nằm trong state, trong hash (khi ON), hiển thị trong prompt
   ⇒ agent **biết** mình đang nuôi ai và bị ai nuôi (feedback loop, Report_v2 §4.5.5).
3. **Event bắt buộc**: mỗi kg vượt ranh giới cá nhân đều có `cap_luong_thuc` ⇒ ai muốn "ăn ké" thì
   phải nằm trong hộ, và việc đó **hiện ra trong journal + metric transfer**.

Người trưởng thành muốn thoát nghĩa vụ nuôi (hoặc muốn thôi bị nuôi) ⇒ **`tach_ho`** (§3): một quyết
định có event, có hệ quả (tự lo ăn, có thể vô gia cư). **Engine không cưỡng chế lòng tốt và cũng không
cưỡng chế ích kỷ.** Không có luật "phải nuôi con đã trưởng thành"; chỉ có luật "người ở chung một hộ
thì ăn theo quy tắc của hộ đó, và nếu không muốn thì tách ra bằng một hành động".

### 2.5 Rủi ro và cách chặn

- **Rủi ro:** hộ 8 người lớn cùng ở lì để ăn kho của một người giàu. **Chặn bằng:** (a) hộ chỉ lớn lên
  qua `sinh`/`cuoi`/`cuu_mang` — không có intent "xin vào hộ người khác" (cố tình KHÔNG thêm, để tránh
  parasitism không có chi phí); (b) chủ kho luôn có `tach_ho` để đuổi... **KHÔNG** — `tach_ho` chỉ cho
  phép *người tách* tự đi. Nếu muốn cho phép trục xuất, đó là một action riêng (`duoi_khoi_ho`) có chi
  phí quan hệ; **P1 không thêm nó** (giữ scope nhỏ, ghi vào "PENDING" của ADR 0006).
- **Rủi ro:** provisioning làm mất động cơ lao động của người trẻ. Đó là một **kết quả**, không phải
  bug — và nó đo được (`ty_le_tu_nuoi`, §5). Không hard-code chống lại nó.

---

## 3. Life-course transitions: tường minh, tất định, serialized

### 3.1 Điểm chèn duy nhất trong `engine/tick.py`

Hiện: bước 9 = `demography.buoc_nhan_khau(w, ke_hoach)` (`tick.py:242`) → `xa_hoi.cuu_mang_mo_coi(w)`
(`tick.py:246`) → bước 10 giáo dục (`:249`).

**Thêm đúng một dòng, sau `cuu_mang_mo_coi`, trước `education`:**

```python
    xa_hoi.cuu_mang_mo_coi(w)
    household.buoc_cu_tru(w, ke_hoach)      # 9b — MỌI mutation membership ở đây, và chỉ ở đây
    estate.buoc_di_san(w)                   # 9c — §4 (estate settlement/expiry)
```

Nguyên tắc **single-writer**: ngoài `engine/household.py`/`engine/estate.py`, **không module nào** được
sửa `w.cu_tru`. `demography`/`xa_hoi`/`tick._di_cu` chỉ **đặt cờ transient** (`w.cuoi_tick`,
`w.cuu_mang_tick`, `w.di_cu_tick`) rồi `buoc_cu_tru` đọc và áp dụng. Cờ transient reset đầu tick (khuôn
`ben_kia_tick`, `tick.py:130`) và **không vào hash** (chúng chết trong tick).

### 3.2 Bảng transition

| Transition | Điều kiện | Ai quyết | Thứ tự trong `buoc_cu_tru` | Event | Tie-break |
|---|---|---|---|---|---|
| **chet** | `cai_chet` (`demography.py:193`) | engine (hazard) | **1** | `chet` (đã có) | `sorted(w.agents)` (đã có) |
| **sinh** | `sinh_con` (`demography.py:93`) | agent (`y_dinh_sinh_con`) + engine (RNG) | **2** — newborn vào `CuTru` của **mẹ**; mẹ chết → cha; cả hai chết → `cuu_mang` | `sinh` (đã có) + `vao_ho{tre, ho}` | id trẻ |
| **cuu_mang (adoption)** | mồ côi cả cha lẫn mẹ, chưa trưởng thành (`xa_hoi.py:117`) | engine (thứ tự ưu tiên máu mủ → hàng xóm) | **3** — trẻ chuyển sang `CuTru` của `giam_ho` | `cuu_mang` (đã có) + `chuyen_ho{nguoi, tu_ho, den_ho}` | `(bậc, -tuổi, id)` (đã có, `xa_hoi.py:121-147`) |
| **cuoi (marriage)** | `xu_ly_cau_hon` chấp nhận (`demography.py:63-69`) | **agent** (cầu hôn + trả lời) | **4** — **spouse-joins**: người có `rid` **lớn hơn** chuyển sang `CuTru` của người kia, **mang theo** những người phụ thuộc mà mình là cha/mẹ/giám hộ **duy nhất còn sống**; hộ cũ rỗng → giải thể | `cuoi` (đã có) + `nhap_ho{nguoi, mang_theo, tu_ho, den_ho}` | `rid` nhỏ hơn thắng; `rid` bằng nhau (đã cùng hộ) ⇒ no-op |
| **remarriage** | goá (`vo_chong=None`, `demography.py:321-322`) rồi cưới lại | agent | như `cuoi`; **con riêng đi theo cha/mẹ ruột** | như `cuoi` | như trên |
| **trưởng thành** | `tuoi_nam >= tuoi_truong_thanh` | — | **KHÔNG LÀM GÌ (INVARIANT R2)** | — | — |
| **tach_ho (split)** | intent `tach_ho`; người tách: sống, **đã trưởng thành**; hộ nguồn còn ≥1 người lớn sống **sau khi** trừ những người sẽ đi (không để trẻ/già lại không người lớn) | **agent** | **5** | `tach_ho{nguoi, mang_theo, tu_ho, den_ho}` | `sorted(ke_hoach)` |
| **di_cu (migration)** | `_di_cu` thành công (`tick.py:347-373`) | agent | **6** — người di cư (+ người phụ thuộc trực hệ) lập `CuTru` MỚI ở làng mới; hiệu lực **cuối tick** (đã ăn với hộ cũ tick này — ghi rõ, không phải bug) | `di_cu` (đã có) + `tach_ho{ly_do:"di_cu"}` | `sorted(ke_hoach)` |
| **thua_ke** | sau `chet` | engine | không đổi membership (đó là tài sản, §4) | `thua_ke` (đã có) | — |
| **tan_ho** | `CuTru.thanh_vien` sống = ∅ | engine | **7** (dọn cuối) | `tan_ho{ho}` | `sorted(w.cu_tru)` |

Mọi vòng lặp trong `buoc_cu_tru` duyệt theo `sorted(...)` theo id; `rid` mới cấp từ `_next_cu_tru` tăng
đơn điệu ⇒ tất định tuyệt đối, không phụ thuộc dict order.

### 3.3 Dependency: caretaker / trẻ / người già

- **Không thêm state mới.** `care.py:16-18` (`_ho_tre`) đã gọi `w.ho_cua(child)` ⇒ khi gate ON, **anh
  chị đã trưởng thành sống chung nhà tự động là caretaker hợp lệ** cho em nhỏ, và hợp đồng `gop_cong`
  trả công chăm trẻ vẫn chạy y nguyên. Đây là một hệ quả **miễn phí** của việc sửa membership — và là
  một lý do nữa để chọn phương án state bền.
- **Người già:** `production.sinh_cong` (`production.py:23-26`) đã giảm công theo tuổi
  (`tuoi_giam_suc`, `tuoi_nghi`); `consumption.py:105-106` đã hao sức tuổi già. Với residence bền,
  người già **ở lại hộ con cháu** và được cấp lương thực qua §2 thay vì bị bỏ rơi — đây chính là
  "con cháu phụng dưỡng" mà docstring `production.py:11-12` đã hứa nhưng engine chưa thực hiện được.
- **Dependency ratio** (đo, không cưỡng chế) — định nghĩa ở §5.

### 3.4 Invariant + test then chốt

- **`test_adult_remains_resident`** (§6 T-01): trưởng thành **không** đổi `rid`, **không** sinh event.

---

## 4. Estate lifecycle: người chết → di sản → chủ nợ → di chúc → kin → hết hạn

### 4.1 Bệnh (chính xác)

1. `thua_ke_mac_dinh` (`demography.py:231`) chia tài sản **trước khi ai kịp đòi nợ**, và khi không có
   người nhận thì **đẩy hết vào `VO_THUA_NHAN`** (`:279`) — một tài khoản mà `chu_the_hoat_dong` trả
   `False` (E8) ⇒ **không ai, không cơ chế nào**, có thể lấy ra. Kết quả đo được: **92.5% thóc, 100%
   nhà, 100% gà** của thế giới nằm trong đó ở tick 180 (§0.2c).
2. Chủ nợ của người chết **mất trắng**: hợp đồng có bên chết ⇒ `"huy"` + `dot_vi_the`, không settlement
   (`contracts.py:423-425`), và thứ tự tick khiến không có cơ hội đòi (E11).
3. Blueprint của người chết không người nhận **giữ tên người chết** (`demography.py:298-300`) ⇒ một
   dạng ghost-owner khác (không ai `duoc_ap_dung` được nữa).

### 4.2 Quyết định

> **Di sản (`DI_SAN:<aid>`) là một chủ thể ledger CÓ HẠN, không phải một cái ví vĩnh viễn.** Nó mở khi
> người chết, đóng bắt buộc sau `ho.di_san.claim_han_tick`, và **mọi tài sản/mọi khoản nợ có ĐÚNG MỘT
> đích hợp pháp**.

State (chỉ khi gate ON, khuôn §1.4):

```python
@dataclass
class DiSan:                       # engine/estate.py
    id: str                        # "DI_SAN:A0051"
    nguoi_mat: str
    mo_tick: int
    han_tick: int                  # mo_tick + claim_han_tick
    trang_thai: str                # "mo" | "dong"
    yeu_cau: list[tuple[str, str]] # (claimant, ly_do) — sorted, tất định
# World: di_san: dict[str, DiSan]; di_san_xong: dict[str, DiSan]
```

`behavioral_state()["estate"]` chỉ chèn khi `_di_san_bat(w)` (⇒ OFF: hash bất biến). Migration
`nap_checkpoint`: `if not hasattr(w, "di_san"): w.di_san = {}` (+ `di_san_xong`).

### 4.3 Thứ tự xử lý (deterministic, `estate.buoc_di_san` — tick.py bước 9c)

Với mỗi estate theo `sorted(w.di_san)`:

| Bậc | Đích | Quy tắc | Ledger |
|---|---|---|---|
| **0. Mở** (tại tick chết) | `DI_SAN:<aid>` | **Toàn bộ** `ledger.tai_san_cua(aid)` (trừ `cong`, vốn bốc hơi) chuyển sang estate ⇒ **người chết có số dư 0** ngay trong tick chết. Đất: `p.chu` giữ nguyên **1 tick**? **KHÔNG** — `audit.py:30` cấm chủ không hoạt động ⇒ đất chuyển thẳng `p.chu = None` **hoặc** sang estate-as-owner **không được** (audit fail). **Quyết định: đất về `None` (công) ngay, như hiện nay (`demography.py:311`), NHƯNG được ghi vào `DiSan.dat_ve_cong` để claim bậc 3 có thể xin cấp lại.** (Alternative "estate giữ đất" bị loại vì phải nới `audit.py:30` — không nới invariant để tiện.) | `chuyen(aid → DI_SAN:aid, ts, sl)` |
| **1. Chủ nợ / hợp đồng** | các bên còn sống của hợp đồng đang hiệu lực mà người chết có nghĩa vụ | Duyệt `sorted(w.hop_dong, key=id)`; quy nghĩa vụ về thóc (dùng `entities.nghia_vu_quy_thoc` khuôn có sẵn); trả từ estate theo **pro-rata** nếu không đủ; thiếu ⇒ event `khong_thu_du{hd, chu_no, thieu}` (mất mát là THẬT, không giấu). Sau đó mới `dot_vi_the` + đóng hợp đồng. **Thay cho `contracts.py:423-425` khi gate ON.** | `chuyen(DI_SAN → chu_no)` |
| **2. Di chúc** | `a.di_chuc["phan_bo"]` | Áp trên **phần còn lại sau nợ** (logic hiện có `demography.py:236-251` giữ nguyên, chỉ đổi nguồn từ `aid` sang `DI_SAN:aid`) | `chuyen(DI_SAN → nguoi_nhan)` |
| **3. Kin claim** | con còn sống → vợ/chồng → **(MỚI) người đồng cư trú tại thời điểm chết** | Thứ tự hiện có (`demography.py:252-260`) + một bậc mới cuối: thành viên `CuTru` của người chết (loại người đã nhận ở bậc 2). Đây là chỗ residence "trả tiền" cho chính nó: sống chung thì thừa kế. Trong `claim_han_tick`, người đủ tư cách có thể chủ động `yeu_cau_di_san` (intent); người **không** đủ tư cách ⇒ `unrecognized_intent{no_right}`. | `chuyen(DI_SAN → nguoi_nhan)` |
| **4. Hết hạn** | `w.tick >= han_tick` và còn số dư | `het_han: "cong"` (mặc định) ⇒ **toàn bộ về `CONG_QUY`** — một chủ thể **có thật, tiêu được**: `politics.thu_thue_va_chia` rebate đầu người khi fiscal OFF ⇒ của cải **quay lại nền kinh tế người sống**. `het_han: "dau_gia"` (biến thể, P2) ⇒ estate đặt lệnh bán qua `phien_cho` (đúng một lần), tiền thu về estate rồi về `CONG_QUY`; **phải có người nhận cuối cùng**, không có "auction vào hư không". | `chuyen(DI_SAN → CONG_QUY)` |
| **5. Đóng** | mọi tài sản = 0 | `trang_thai="dong"`, chuyển sang `di_san_xong` (khuôn `hop_dong_xong`, `tick.py:229-231`); event `dong_di_san{id, nguoi_nhan_cuoi, theo_tai_san}` | — |

Blueprint: bậc 2/3 nhận như tài sản (round-robin, khuôn `demography.py:295-300`); hết hạn ⇒ `bp.chu =
CONG_QUY` (chủ thể hoạt động? **không** — `CONG_QUY` không phải agent/entity ⇒ `duoc_ap_dung` sẽ không
resolve). **Quyết định: hết hạn ⇒ blueprint `chu = None` + `w.blueprints[bid].cong_khai = True`
(tri thức thành công cộng)** — cần một dòng ADR riêng vì nó chạm `research.py`; nếu muốn scope tối
thiểu thì **giữ nguyên hành vi hiện tại và ghi là PENDING**, nhưng **phải** ghi rõ trong ADR 0006 rằng
blueprint mồ côi là ghost-owner đã biết.

### 4.4 Invariants (§4)

- **E1 (không sink vĩnh viễn):** với gate ON, tại **mọi tick**: `ledger.so_du(VO_THUA_NHAN, ts) == 0`
  ∀ts, **và** mọi estate có `w.tick > han_tick` có số dư 0 ∀ts. Assert trong
  `audit.kiem_toan_the_gioi` (thêm nhánh gated, `audit.py:21`).
- **E2 (không ghost actor):** người chết và `DI_SAN:*` **không** được: là bên hợp đồng mới
  (`contracts.py:118-121` đã chặn agent chết + chủ thể lạ — thêm chặn tường minh prefix `DI_SAN:`);
  đặt lệnh chợ (`tick.py:186` lọc `chu_the_hoat_dong`); là mục tiêu trộm (`xa_hoi.py:52-53`); nhận tin
  nhắn (`tick.py:83-84`); là thành viên `CuTru` (R4); đứng tên đất (`audit.py:30`). **Test riêng cho
  từng chốt** (§6 T-24).
- **E3 (bảo toàn):** ∀ tài sản: tổng trước chết == tổng sau khi estate đóng. `kiem_toan_the_gioi` xanh
  **mọi tick** qua toàn bộ lifecycle (không có tick nào "tạm lệch rồi cân sau").
- **E4 (đúng một đích):** mỗi kg / mỗi thửa / mỗi khoản nợ được xử lý **đúng một lần**; pro-rata không
  vượt tổng; không double-pay.

### 4.5 Failure / rollback

- Estate không đủ trả nợ ⇒ chủ nợ nhận pro-rata, phần thiếu **mất thật** (event `khong_thu_du`).
  Không mint bù. Không cho số dư âm.
- Người nhận thừa kế chết **trong cùng tick** ⇒ đã bị loại bởi `chu_the_hoat_dong` filter
  (`demography.py:263`, giữ nguyên) ⇒ rơi xuống bậc kế tiếp.
- Estate của một người mà mọi bậc đều rỗng ⇒ chạy thẳng bậc 4 khi hết hạn ⇒ `CONG_QUY`.
- `LoiSoKep` khi chuyển ⇒ **không nuốt** ở đây (khác market): estate settlement phải nguyên tử; nếu
  raise thì đó là bug thật, phải dừng (điều luật #1).

---

## 5. Metrics nhân khẩu trung thực

### 5.1 Sự thật hiện tại

`engine/metrics.py:143-195` **không có một chỉ số nhân khẩu nào** ngoài `dan_so`, `nguoi_lon`,
`health_tb`. Grep toàn repo cho `tuoi_tho|life_expect|age_at_death|kỳ vọng sống`: **0 match trong
`engine/`, `tools/`, `observatory/`**.

> ⇒ **Hiện KHÔNG có file:line nào gọi "mean age của người còn sống" là "life expectancy".** Invariant
> dưới đây là **phòng ngừa**, không phải sửa lỗi đã có. Rủi ro nằm ở tầng **báo cáo** (một report tương
> lai rất dễ viết "tuổi thọ giảm còn X" từ `dan_so`/tuổi trung bình người sống).

### 5.2 Invariant (INV-M1)

> **TUYỆT ĐỐI không được gọi mean/median tuổi của người CÒN SỐNG là "life expectancy"/"tuổi thọ".**
> Hai đại lượng phải nằm ở hai key khác nhau, khác tên gốc, và không key nào được đặt tên
> `life_expectancy`/`tuoi_tho` trừ khi nó là `e0` tính từ **period life table** có `exposure` khai báo
> và có missing-data policy. Test bắt buộc: §6 T-31.

### 5.3 Schema đề xuất (`engine/metrics_demography.py` → `m["demography"]`)

Lớp-5 thuần đọc, **ngoài `world_hash`** (khuôn `m["research"]`, `tick.py:263-265`), nhưng **phải tái
dựng được từ `metrics_lich_su` + events**.

| Key | Định nghĩa | `None` khi |
|---|---|---|
| `song.n` | số agent `con_song` | — |
| `song.tuoi_tb`, `song.tuoi_trung_vi` | **mean/median age of LIVING** | `n == 0` |
| `chet.n_tick` | số `chet` **trong tick** (đếm từ state, KHÔNG đọc lại journal) | — |
| `chet.theo_nguyen_nhan` | dict `{chet_doi, kiet_suc, benh_tat, tuoi_gia, tu_vong_sinh_no}` (đúng nhãn `demography.py:206-216`, `:148`) | — |
| `chet.tuoi_tb_khi_chet`, `chet.tuoi_trung_vi_khi_chet` | **mean/median AGE AT DEATH** (cửa sổ `quan_sat.cua_so_nhan_khau_tick`) | `n_deaths < quan_sat.min_n_tu_vong` ⇒ **None, KHÔNG phải 0** |
| `ty_suat_chet` | deaths(W) / **person-ticks**(W) × `tick_moi_nam` (đơn vị: /người/năm, ghi rõ trong key doc) | person-ticks < ngưỡng |
| `ty_suat_sinh` | births(W) / person-ticks(W) × `tick_moi_nam` | như trên |
| `ty_suat_sinh_theo_tuoi_me` | births(W) / **woman-ticks** trong `[tuoi_me_min, tuoi_me_max]` (`nhan_khau.sinh_san.tuoi_me`) | woman-ticks < ngưỡng |
| `ty_le_phu_thuoc` | (trẻ < `tuoi_truong_thanh` + già > `lao_dong_theo_tuoi.tuoi_nghi`) / (người trong tuổi lao động) | mẫu = 0 |
| `bang_song` (P4) | `nqx` theo band tuổi từ deaths/person-ticks; `e0` **chỉ** khi mọi band đủ exposure | band thiếu exposure ⇒ band = None ⇒ `e0 = None` |
| `cu_tru.n`, `cu_tru.co_so_thanh_vien` | số hộ + phân bố quy mô (đơn vị = **residence** khi ON) | — |
| `cu_tru.ty_le_thieu_an` | share hộ có `food_security < 1` (**key mới**, đơn vị residence) — giữ `ty_le_ho_thieu_an` legacy riêng để không lẫn hai đơn vị | 0 hộ |
| `cu_tru.thoi_gian_ngheo` | poverty duration — **re-key `w.poverty_streak` theo `rid`** thay vì head-id ⇒ **sửa luôn giới hạn ADR 0003 §E** ("head đổi ⇒ streak gãy") | hộ mới ⇒ 0 |
| `chuyen_giao.luong_thuc_quy_thoc` | Σ `cap_luong_thuc.quy_thoc` trong tick (§2) | gate `cap_luong_thuc` OFF ⇒ None |
| `chuyen_giao.ty_le_tu_nuoi` | (thóc tự ăn) / (tổng ăn) per-capita — đo **phụ thuộc** | tổng ăn = 0 |
| `di_san.n_mo`, `.n_dong`, `.gia_tri_dang_treo` | estate đang mở/đã đóng/giá trị treo (quy thóc) | gate estate OFF ⇒ None |
| `di_san.kẹt_vinh_vien` | `so_du(VO_THUA_NHAN)` quy thóc — **phải = 0 khi gate ON** | — |

**Chính sách missing-data (bắt buộc, khuôn ADR 0003 §C):** mẫu số < ngưỡng ⇒ trả **`None`**, không trả
0 giả, không NaN im lặng. Ngưỡng đặt trong `quan_sat.*`, không magic number.

**Chống nhiễm journal (P0.2):** mọi chỉ số nhân khẩu tính từ **state engine trong tick** và ghi vào
`metrics.jsonl` (1 dòng/tick). **Cấm** tính death rate bằng cách đọc lại `events.jsonl` — artifact
`real60_spatial` chứng minh vì sao: file đó có 2 lịch sử chồng nhau ở tick 106–117 (§0.2d).

---

## 6. Test matrix P1 (tên + assert — để `test-engineer` viết ĐỘC LẬP)

File: `tests/test_household_residence.py`, `tests/test_estate.py`, `tests/test_metrics_demography.py`;
regression bổ sung trong `tests/test_household_economics.py`. Thế giới nhỏ (8×8, ≤10 agent, ≤40 tick)
theo CLAUDE §3.

### A. Residence / provisioning

| # | Test | Assert |
|---|---|---|
| T-01 | `test_adult_remains_resident` (ON) | Cha P + con C; đẩy tuổi C qua `tuoi_truong_thanh`; `w.ho_cua(C) == w.ho_cua(P)`; `rid(C) == rid(P)`; **không** event `tach_ho`/`chuyen_ho` |
| T-02 | `test_adult_an_duoc_khi_cha_me_du_thoc` (ON) | P có 10 000 kg, C có 0; chạy `an_va_suc_khoe`; **không** event `an_doi` cho C; `C.health` không giảm; tồn tại event `cap_luong_thuc{tu:P, den:C, so_luong≈nhu_cau.nguoi_lon_kg_tick}`; `so_du(P)` giảm đúng bằng nhu cầu hộ; `kiem_toan` xanh |
| T-03 | `test_case_a0051_khong_chet_doi` (ON, regression có tên) | Tái dựng đúng cấu hình A0051 (calendar 3 mùa, trẻ sinh tick t, cha mẹ ≥3000 kg); chạy 20 tick qua mốc trưởng thành; assert **0** `an_doi`, agent **còn sống**, `chet_doi == 0` |
| T-04 | `test_off_giu_nguyen_semantics_cu` (OFF) | Cùng fixture T-02 nhưng gate OFF ⇒ C **CÓ** `an_doi` (ghi nhận semantics legacy tường minh, không âm thầm đổi) |
| T-05 | `test_hash_legacy_pinned_off` | rulebot 20 tick: base+seed 11 ⇒ `4ba32e51…0292b`; base+seed 42 ⇒ `f1f8cd4b…d153`; overlay `spatial_v1`+seed 11 ⇒ `afc5b09e…5745` (§0.3). **Gate cứng.** |
| T-06 | `test_residence_partition` (hypothesis, ON) | Sau N tick rulebot ngẫu nhiên: mỗi agent sống ∈ **đúng 1** `CuTru`; không agent chết trong `thanh_vien`; Σ|members| == số người sống |
| T-07 | `test_membership_diff_giai_thich_boi_event` (ON) | Diff membership tick t−1→t **được giải thích hết** bởi event tick t (`sinh|cuoi|tach_ho|cuu_mang|di_cu|chet|tan_ho`) |
| T-08 | `test_tach_ho_doi_provisioning_chi_qua_event` (ON) | C phát intent `tach_ho` ⇒ event `tach_ho`; tick sau **không** còn `cap_luong_thuc{P→C}`; `so_du(P)` không còn giảm vì C; audit xanh |
| T-09 | `test_tach_ho_bi_tu_choi_khi_bo_lai_tre_khong_nguoi_lon` (ON) | Người lớn **duy nhất** của hộ có trẻ nhỏ xin tách ⇒ `unrecognized_intent{no_adult_left}`; membership không đổi |
| T-10 | `test_cuoi_nhap_ho_va_con_rieng_di_theo` (ON, tái hôn) | Goá phụ có con riêng cưới lại ⇒ con riêng **cùng chuyển**, được `cap_luong_thuc`, và `households()` đếm **đúng một lần** (không double-count) |
| T-11 | `test_mo_coi_vao_ho_giam_ho` (ON) | Cha mẹ chết cùng tick ⇒ `cuu_mang_mo_coi` gán `giam_ho` ⇒ cuối tick trẻ ở `CuTru` của giám hộ; tick sau được cấp lương thực |
| T-12 | `test_di_cu_lap_ho_moi_cuoi_tick` (ON) | `di_cu` thành công ⇒ `CuTru` mới ở làng mới; người di cư **vẫn ăn với hộ cũ trong tick di cư** (hành vi khai báo, không phải bug) |
| T-13 | `test_anh_chi_truong_thanh_lam_caretaker` (ON) | Anh/chị đã trưởng thành cùng hộ ⇒ `care._ho_tre(em)` chứa họ ⇒ `cham_tre` hợp lệ, công bị đốt đúng, `gop_cong` trả công đúng |
| T-14 | `test_cap_luong_thuc_la_hash_neutral` | Bật **riêng** `ho.cap_luong_thuc` (membership vẫn legacy) ⇒ `world_hash()` **trùng hệt** run OFF (chứng minh provisioning chỉ thêm sổ sách/event, không đổi quỹ đạo) |
| T-15 | `test_khong_an_ke_ngoai_ho` (ON) | Agent X giàu không cùng `CuTru` với Y nghèo ⇒ **không** `cap_luong_thuc{X→Y}`; Y đói thật |

### B. Estate

| # | Test | Assert |
|---|---|---|
| T-20 | `test_estate_co_heir_bao_toan` | Tổng mỗi tài sản trước chết == sau khi estate đóng; heir nhận phần dư; `so_du(DI_SAN:*) == 0`; `so_du(VO_THUA_NHAN) == 0`; audit xanh **mọi tick** |
| T-21 | `test_estate_tra_chu_no_truoc_heir` | Con nợ chết còn nghĩa vụ X, tài sản X+Y ⇒ chủ nợ nhận **X**, heir nhận **Y**; event `thanh_toan_di_san`; hợp đồng đóng **sau** thanh toán |
| T-22 | `test_estate_khong_du_tra_no` | Tài sản < nghĩa vụ ⇒ chủ nợ nhận pro-rata theo `sorted(hd.id)`, heir nhận **0**, event `khong_thu_du{thieu}`; **không** số dư âm; **không** mint bù |
| T-23 | `test_estate_khong_heir_khong_chu_no_het_han_ve_cong` | Sau `claim_han_tick`: toàn bộ → `CONG_QUY`; `DI_SAN` đóng; `VO_THUA_NHAN == 0`; **căn nhà tới được một chủ thể tiêu được** (đối chứng trực tiếp với §0.2c) |
| T-24 | `test_ghost_offer_bi_tu_choi` | (a) `de_nghi_hop_dong` với bên = agent chết ⇒ `validate_hop_dong` trả `"bên đã chết"`; (b) bên = `DI_SAN:*` ⇒ `"bên không tồn tại"`; (c) `Lenh` với `ai=DI_SAN:*` **không** vào `phien_cho`; (d) `trom` nhắm `DI_SAN:*` ⇒ `unrecognized_intent`; (e) `DI_SAN:*` đứng tên thửa ⇒ `kiem_toan_the_gioi` **raise** |
| T-25 | `test_claim_window_nhan_kin_tu_choi_nguoi_dung` | Kin/đồng-cư-trú `yeu_cau_di_san` trong hạn ⇒ nhận; người dưng ⇒ `unrecognized_intent{no_right}`, không nhận gì |
| T-26 | `test_dau_gia_di_san_settle_dung_mot_lan` (biến thể `het_han: "dau_gia"`) | Estate bán qua `phien_cho` **đúng một lần**; tiền về `CONG_QUY`; bảo toàn; không double-settle |
| T-27 | `test_khong_con_so_du_ket_vinh_vien` (property, ON, 60 tick rulebot tử vong cao) | ∀tick: `so_du(VO_THUA_NHAN, *) == 0` **và** ∀estate quá hạn: số dư = 0 |
| T-28 | `test_audit_xanh_suot_lifecycle` | 40 tick rulebot ON có chết/thừa kế/nợ ⇒ `kiem_toan_the_gioi` **không raise lần nào** |

### C. Metrics

| # | Test | Assert |
|---|---|---|
| T-30 | `test_age_at_death_dung` | Giết 3 agent tuổi đã biết ⇒ `chet.tuoi_tb_khi_chet` = trung bình số học; `song.tuoi_tb` **khác** nó; cả hai cùng có mặt |
| T-31 | `test_khong_goi_tuoi_nguoi_song_la_tuoi_tho` (**INV-M1**) | `m["demography"]` **không có** key `life_expectancy`/`tuoi_tho`; nếu có `e0_period` thì **bắt buộc** kèm `exposure` + `None` khi thiếu exposure |
| T-32 | `test_period_rate_dung_person_ticks` | Thế giới mà dân số giảm nửa giữa cửa sổ ⇒ `ty_suat_chet` dùng **person-ticks**, không dùng dân số cuối kỳ (giá trị kỳ vọng tính tay) |
| T-33 | `test_undefined_khi_mau_so_nho` | 0 ca chết trong cửa sổ ⇒ `chet.tuoi_tb_khi_chet is None` (**không phải 0.0**); 0 người trong tuổi lao động ⇒ `ty_le_phu_thuoc is None` |
| T-34 | `test_khong_double_count_qua_ho` | Σ thành viên các `CuTru` == số agent sống; `cu_tru.ty_le_thieu_an` và `ty_le_ho_thieu_an` (legacy) là **hai key khác nhau**, không lẫn đơn vị |
| T-35 | `test_poverty_duration_song_qua_cai_chet_cua_head` (ON) | Head chết, hộ còn ⇒ streak (key theo `rid`) **không reset về 0** (sửa giới hạn ADR 0003 §E) |

### D. Replay / regression

| # | Test | Assert |
|---|---|---|
| T-40 | `test_replay_same_hash_on` | 2 run cùng seed + overlay v2 ⇒ cùng `world_hash` |
| T-41 | `test_checkpoint_roundtrip_on` | `luu_checkpoint` → `nap_checkpoint` ⇒ `world_hash` trùng (khuôn `test_livelihood_extensions.py:180`) |
| T-42 | `test_resume_bang_run_lien_mach_on` | Run 20 tick liền == run 10+10 tick có resume ⇒ cùng hash, không event trùng id |
| T-43 | `test_overlay_off_hash_bat_bien` | = T-05 (nhắc lại ở tầng regression: **toàn bộ suite legacy xanh + 3 hash pin không đổi**) |

---

## 7. Claim boundary — điều gì **KHÔNG ĐƯỢC** diễn giải cho tới khi P0/P1 xanh

`real60_spatial` là **diagnostic-only, unreplayable** (Report_v2 §3, README agents §"Gates"). Cho tới
khi P0 **và** P1 có test xanh, **cấm** các phát biểu sau — mỗi lý do dưới đây **tự nó đã đủ** để vô
hiệu hóa diễn giải:

1. **"LLM để dân chết đói / không biết nuôi con"** — SAI. `an_doi` đầu tiên của **3/3** người trẻ
   (pre-resume) và **159/168** người trẻ trong mock rơi đúng vào **tick sinh nhật 16**. Đây là engine
   cắt liên kết lương thực, **tái lập dưới policy heuristic phi-LLM**.
2. **"Dân số sụp đổ vì agent không tạo được định chế"** — chưa kết luận được. Tại tick 180, **92.5%
   thóc + 100% nhà + 100% gà** của thế giới nằm trong `VO_THUA_NHAN`, nơi **không policy nào** (LLM,
   rulebot, hay con người) có thể lấy ra. Người sống đói giữa một kho của cải bị đóng băng bởi kế toán.
3. **"Tuổi thọ / life expectancy giảm còn X"** — không có đại lượng đó trong repo (§5.1). Mọi con số
   tuổi hiện có là **tuổi của người còn sống** hoặc **tuổi lúc chết**, và cả hai đều **không phải** life
   expectancy.
4. **Bất kỳ death/birth rate nào tính từ `data/runs/real60_spatial/events.jsonl`** — journal chứa **hai
   lịch sử phản-thực** ở tick 106–117 (event `chet` lặp: A0031@106, A0053@110, A0003@112; A0054 chết ở
   cả 116 lẫn 118) (P0.2).
5. **So sánh mortality LLM vs mock như bằng chứng về decision quality** — hai run khác nhau ở *policy*
   nhưng **cùng chịu** defect (1) và (2); mock chỉ thoát chết vì nó tình cờ có 383 hợp đồng `gop_cong`
   nuôi người trẻ. Đó là một confound, không phải một phát hiện.

**Được phép nói ngay bây giờ** (tier `mechanism_result`): *"Môi trường như đang cài có một defect
adult-orphaning độc lập với policy và một absorbing wealth sink; sụp đổ nhân khẩu của run LLM bị
confound bởi cả hai."*

**Sau khi P1 xanh**, mortality chỉ được diễn giải khi có **cả ba**: (a) baseline rulebot/mock cùng
seed; (b) **ablation** bật/tắt riêng `ho.cu_tru_ben_vung` và `ho.di_san.bat` (cờ đã thiết kế cho đúng
mục đích này); (c) artifact replay được từ transcript (P0.2). Nếu collapse **không sống sót** qua
ablation ⇒ nó là artifact, không phải kết quả.

---

## 8. Handoff

**Verdict:** DESIGN ONLY — không sửa code/test; memo này là input bắt buộc cho ADR 0006.

**Scope / files examined:** `engine/world.py`, `engine/consumption.py`, `engine/demography.py`,
`engine/xa_hoi.py`, `engine/economy.py`, `engine/tick.py`, `engine/contracts.py`, `engine/board.py`,
`engine/entities.py`, `engine/audit.py`, `engine/ledger.py`, `engine/types.py`, `engine/metrics.py`,
`engine/care.py`, `engine/chan_nuoi.py`, `engine/production.py`, `engine/spatial.py`,
`minds/safety.py`; `docs/MODEL_CHARTER.md`, `docs/adr/0001`, `0003`, `0005`; `Report_v2.md`;
`data/runs/{real60_spatial,mock60_spatial}` (**chỉ đọc**). **File duy nhất được ghi:** chính file này.

**Findings (severity):**

| ID | Severity | Finding | Owner sửa |
|---|---|---|---|
| **F1** | **BLOCKER** | Adult-orphaning: `world.py:433` + `consumption.py:50` ⇒ người vừa trưởng thành bị cắt khỏi hộ và chết đói dù cha mẹ giàu. Policy-independent (159/168 trong mock). | `engine-surgeon` (sau ADR 0006) |
| **F2** | **BLOCKER** | `VO_THUA_NHAN` là absorbing sink: 92.5% thóc + 100% nhà/gà kẹt vĩnh viễn ở tick 180. | `engine-surgeon` |
| **F3** | **BLOCKER** | Nợ chết theo con nợ (`contracts.py:423-425` + thứ tự `tick.py:222` vs `:242`) ⇒ chủ nợ mất trắng, heir hưởng tài sản sạch nợ. | `engine-surgeon` |
| **F4** | **HIGH** | Provisioning ngầm: `consumption.py:69` đốt thóc người khác **không event, không đối ứng** ⇒ không đo được transfer (vi phạm Report_v2 §4.2). | `engine-surgeon` |
| **F5** | **HIGH** | Không có **bất kỳ** metric nhân khẩu nào (`metrics.py:143-195`) ⇒ mọi phát biểu về mortality hiện nay là suy diễn ngoài dữ liệu. | `sim-economist` + `engine-surgeon` |
| **F6** | **MEDIUM** | ADR 0003 §A.1 dựa trên tiền đề sai ("huyết thống suy ra được hộ") ⇒ phải supersede tường minh, không im lặng. | `spec-governor` / `model-architect` |
| **F7** | **MEDIUM** | Blueprint mồ côi giữ tên người chết (`demography.py:298-300`) — ghost-owner còn lại sau khi F2 được sửa. | `engine-surgeon` (PENDING trong ADR 0006) |
| **F8** | **LOW** | `poverty_streak` khóa theo head-id ⇒ gãy khi head chết (ADR 0003 §E tự thừa nhận); re-key theo `rid` sửa miễn phí. | `engine-surgeon` |

**Invariants phải được test chứng minh:** R1–R5 (§1.6), E1–E4 (§4.4), INV-M1 (§5.2), và ba hash pin
(§0.3).

**Next handoff:**

1. `model-architect` + `agrarian-economist` → **ADR 0006** (household/residence + estate): lấy §1–§4
   làm decision, thêm consequences/rollback, đánh dấu PENDING cho `duoi_khoi_ho`, blueprint mồ côi,
   `het_han: "dau_gia"`.
2. `engine-surgeon` → implement **sau khi ADR 0006 accepted**, đúng gate `ho.*`, đúng điểm chèn
   `tick.py` 9b/9c, không đụng `Agent` dataclass.
3. `test-engineer` → viết T-01…T-43 **độc lập** (không đọc diff của engine-surgeon).
4. `qa-verifier` + `reproducibility-steward` → xác minh ba hash pin §0.3 và replay/resume ON.
5. `adversarial-reviewer` → kiểm chính xác hai điểm dễ gian: (a) có ai nới `audit.py:30` để estate giữ
   đất không; (b) có ai đặt key `life_expectancy` từ tuổi người sống không.
