# ADR 0007 — Residence, household provisioning, và estate lifecycle (tiền điều kiện P1)

- Status: **Proposed (design)** — 2026-07-13. Implementation PENDING (xem §H Handoff).
- Deciders: `model-architect` (tác giả). Design input **bắt buộc**:
  `docs/reviews/P1-household-demography-design.md` (`household-demography-specialist`) — §1–§6 của
  memo đó là *decision*, ADR này **không thiết kế lại từ đầu**; nó chốt, sửa hai chỗ sai, thêm
  failure/rollback/ordering/gate và giao hợp đồng test.
- Independent review PENDING: `engine-surgeon`, `test-engineer`, `reproducibility-steward`,
  `adversarial-reviewer`, `qa-verifier`.
- Route đến từ: **ADR 0006 §D.3** ("ADR 0006 KHÔNG quyết household/estate; P1 PHẢI có ADR 0007").
  ADR 0006 là Accepted ⇒ điều kiện thủ tục của ADR 0003 §A.2 ("nếu cần pantry thì phải có ADR
  riêng") được thỏa bằng chính tài liệu này.
- **Supersede (một phần): `docs/adr/0003-household-market-land.md` §A.1** (hộ = derived view từ
  huyết thống). **GIỮ NGUYÊN** ADR 0003 §A.2 (không pantry chung), §A.3 (bốn khoản không lẫn),
  §B (accounting identity), §C (undefined thay vì 0 giả), §D, §E/§F (khuôn observation-state +
  migration). Không có hai hệ hộ song song.
- Kế thừa, **không nới**: `CLAUDE.md` §2 (7 điều luật), `docs/MODEL_CHARTER.md` §3 (5 lớp), §5
  (cổng định chế + anti-teleology), ADR 0001 §A (invariant), §B (cổng), §D (determinism phủ state
  mới), ADR 0002 (policy chỉ trả intent), ADR 0005 §11 (khuôn scenario-gate + hash + migration).
- Scope guard: **ADR này KHÔNG implement engine.** Mọi số ở đây là `design_assumption`
  (charter §2). Không mục nào là bằng chứng thực chứng.

---

## 0. Bằng chứng nền (verify lại trực tiếp trên working tree, không suy đoán)

### 0.1 Ba hash pin — ĐÃ TÁI LẬP (điều kiện tiên quyết để ADR này có hiệu lực)

Chạy trên working tree hiện tại (đã chứa thay đổi P0 đang làm dở ở `run.py`/`minds/*`/
`engine/events.py`), rulebot, 20 tick, `THOC_BLOCK_NETWORK=1`, không mạng:

```
LEGACY_OFF seed=11 t=20 : 4ba32e514c2ec7e695ad5d0f7b9dc852aa45be723e5712b93f10c8b3cad0292b  MATCH
LEGACY_OFF seed=42 t=20 : f1f8cd4ba7dc53dbc505e8454c85cf31ba44c632bf8f541570c3dece4c7ed153  MATCH
SPATIAL_ON seed=11 t=20 : afc5b09e850495c041c5c825eeca7ae558e53d3b46721d07c92305595439b745  MATCH
```

Hai hệ quả: (a) baseline của `docs/reviews/P1-household-demography-design.md` §0.3 còn đúng, ADR
này đứng trên nền chưa trôi; (b) công việc P0 đang làm (journal seq / transcript / manifest) là
**hash-neutral** đúng như ADR 0006 §C.6 hứa. **Ba chuỗi này là gate cứng của P1** (§G.3).

### 0.2 Bốn defect load-bearing (file:line đã đọc lại)

| ID | Sự thật | Chứng cứ |
|---|---|---|
| **F-18** | `ho_cua()` loại con **đã trưởng thành** khỏi hộ cha mẹ; `an_va_suc_khoe` ăn theo đúng hộ đó ⇒ người vừa 16 tuổi, 0 kho, ăn 0 kg dù cha mẹ đầy thóc | `engine/world.py:433-457` (đặc biệt `:455` `not c.truong_thanh(tt)`); `engine/consumption.py:50`, `:63-70` |
| | Policy-independent: `mock60_spatial` (PersonaBot heuristic, KHÔNG LLM) — **159/168 = 94.6%** agent sinh-trong-sim có `an_doi` đầu tiên trong ±1 tick quanh sinh nhật 16 | memo §0.2(b) |
| **F-19** | Tài sản không người thừa kế → `VO_THUA_NHAN`; đó **không phải chủ thể hoạt động** ⇒ không ai giao dịch/trộm/ký hợp đồng/nhận đất với nó ⇒ **kẹt vĩnh viễn**. Checkpoint tick 180 `real60_spatial`: **92.5% thóc, 100% gà, căn nhà DUY NHẤT của thế giới** | `engine/demography.py:279`; `engine/world.py:23`, `:315-321` (`chu_the_hoat_dong`); memo §0.2(c) |
| **F-20** | Nợ chết theo con nợ: `if dao_han or ben_chet: trang_thai="huy"` + `dot_vi_the`, **KHÔNG settlement**; thứ tự tick khiến chủ nợ không bao giờ đòi được (hợp đồng bước 7, chết+thừa kế bước 9 **cùng tick**) | `engine/contracts.py:423-425`; `engine/tick.py:222` vs `:242` |
| **F-22** | **HASH TRAP:** `behavioral_state()` băm `"population": self.agents`, và `_canonical_state` duyệt `dataclasses.fields()` ⇒ **thêm MỘT field vào dataclass `Agent` là đổi hash của MỌI run legacy** (kể cả field `None`) | `engine/world.py:515`, `:38-42` |

### 0.3 Hai sự thật kỹ thuật quyết định thiết kế (mới, verify trong ADR này)

| ID | Sự thật | Chứng cứ | Dùng ở |
|---|---|---|---|
| **G-1** | `FlowRegistry` khóa theo **`(tai_san, luong)`**, KHÔNG theo chủ thể; `chuyen` là bút toán CÂN (không ghi flow); `behavioral_state()["ledger"]` chỉ chứa `balances` + `flow_*`, **không** chứa transaction journal | `engine/ledger.py:55-70`, `:162-177`; `engine/world.py:509-514`, `:463` | §B.3 (chứng minh hash-neutral) |
| **G-2** | **`CONG_QUY` KHÔNG có đường thoát trong scenario đích.** `politics.thu_thue_va_chia` return sớm khi `chinh_tri.bat` false; `agrarian_transition_v1` đặt `chinh_tri.bat: false`. Và ngay cả khi ON, `_chia_deu` chỉ rebate **`tong_thu` của tick đó** và **chỉ tài sản `"thoc"`** — `nha`/`ga`/`go`/`cong_cu`/`khoai` vào `CONG_QUY` sẽ **không bao giờ** ra | `engine/politics.py:194-195`, `:225`, `:230-238`; `scenarios/agrarian_transition_v1/parameters.yaml:16` | §D.6 (**sửa memo §4.3 bậc 4**) |

> **G-2 là một correction thật sự đối với design input.** Memo §4.3 chốt `het_han: "cong"` (mặc
> định) với lý do "`CONG_QUY` là chủ thể có thật, tiêu được: `thu_thue_va_chia` rebate đầu người
> khi fiscal OFF ⇒ của cải quay lại nền kinh tế người sống". Trong `agrarian_transition_v1` —
> **đúng scenario mà P1 nhắm** — mệnh đề đó **SAI**: tầng chính trị TẮT ⇒ hàm rebate return ở dòng
> đầu. Route estate → `CONG_QUY` ở đó chỉ **đổi tên cái sink**, mà vẫn **PASS** invariant E1 của
> memo (`so_du(VO_THUA_NHAN)==0`). ADR này vì vậy siết invariant (E1′) và đổi route mặc định (§D.6).

---

## §A. Residence là STATE BỀN (supersede ADR 0003 §A.1; GIỮ §A.2)

### A.1 Quyết định

> **Cư trú (residence) là state bền, engine-owned, scenario-gated. `w.ho_cua()` trở thành lookup
> trên state đó khi gate ON, và giữ NGUYÊN TỪNG DÒNG hành vi derived-view legacy khi gate OFF.**

```python
# engine/household.py (module MỚI)
@dataclass
class CuTru:
    id: str                # "R0001"
    thanh_vien: list[str]  # SORTED, single source of truth
    lang: int              # làng của hộ (cho di cư + escheat §D.6)
    nha_thua: str | None   # thửa đặt nhà (con trỏ VỊ TRÍ, không phải quyền sở hữu)
    quy_tac_cap: str       # "nhu_cau_deu" (mặc định, công khai, vào hash khi ON)
    lap_tick: int

# engine/world.py — World (KHÔNG đụng dataclass Agent — F-22)
cu_tru: dict[str, CuTru] = {}
_next_cu_tru: int = 0
```

`economy.households(w)` (`engine/economy.py:15`) trở thành wrapper mỏng: ON → các
`CuTru.thanh_vien` còn sống; OFF → nguyên trạng. Nhờ vậy **mọi call-site tự đúng theo** mà không
phải sửa từng nơi (`consumption.py:50,122`, `care.py:18`, `demography.py:112,126`,
`metrics_research.py:397`, `minds/safety.py:31`, `minds/prompts.py:589`, `minds/policy_cards.py:37`,
`minds/triggers.py:62`, `minds/rulebot.py:187,421,908,990,1004`, `minds/world_tools.py:172`,
`tick.py:272`).

### A.2 Vì sao tiền đề của ADR 0003 §A.1 SAI (phải nói thẳng, không supersede im lặng)

ADR 0003 §A.1 lập luận: *"Cưới/sinh/chết/tái hôn/cưu mang đã thay đổi
`Agent.vo_chong/cha/me/giam_ho/con/con_nuoi` … nên hộ tự cập nhật"* (`docs/adr/0003:73-74`). Tiền
đề ngầm là **"đồng-cư-trú suy ra được từ quan hệ huyết thống"**. Nó sai vì:

> **Sinh nhật thứ 16 không phải một biến cố quan hệ** — không event, không quyết định, không bút
> toán, không ai làm gì cả — **nhưng nó đổi membership** trong `ho_cua()` (`world.py:455`) ⇒ đổi ai
> được ăn (`consumption.py:50`) ⇒ đổi ai sống. **Một biến-cố-không-tồn-tại không được phép có hệ
> quả vật lý.**

Đây không phải "tinh chỉnh tham số": nó là một **luật vật lý ẩn** (`tuổi ≥ 16 ⇒ mất quyền tiếp cận
kho của hộ`) không được khai báo ở bất kỳ đâu, không tắt được, không đo được, và tái lập được dưới
policy phi-LLM (F-18). Nó phải bị xóa bằng một **state có tên, có owner, có event** — không phải
bằng cách nới điều kiện tuổi trong `ho_cua`.

### A.3 Alternatives (đã cân nhắc và loại — ghi để phản biện được)

| # | Phương án | Vì sao KHÔNG |
|---|---|---|
| A | Giữ derived view, chỉ nới `ho_cua` cho "con trưởng thành **chưa lập gia đình**" | Vẫn suy từ huyết thống: không phân biệt con 30 tuổi đã ra riêng với con 17 tuổi còn ở nhà; không có chỗ treo event `tach_ho`; không đo được di cư; và **vẫn đổi hash vô điều kiện** nên không hề rẻ hơn. Chỉ **dời bug sang tuổi khác**. |
| B | `Agent.residence_id: str` | Gọn về cú pháp, nhưng F-22: `behavioral_state()` băm mọi field của `Agent` ⇒ legacy hash đổi ngay khi field tồn tại. Muốn giữ hash phải *project bỏ field* khi OFF (khuôn `Parcel.bo`, `world.py:470-493`) — cơ chế đó **giòn**: field `Agent` thêm sau này sẽ **âm thầm rơi khỏi hash** khi overlay OFF. Rủi ro reproducibility > lợi ích cú pháp. |
| C | Object `Household` là chủ thể ledger (có pantry) | ADR 0003 §A.2 đã loại; và nó tạo **đúng loại ghost-subject có vòng đời** mà §D đang phải dọn (`VO_THUA_NHAN`). Thêm ghost mới trong lúc dọn ghost cũ là tự mâu thuẫn. Xem §B. |
| **D** | **(CHỌN) World-level `w.cu_tru` + key hash CÓ ĐIỀU KIỆN** | Không đụng `Agent`; key `"residence"` **chỉ được chèn vào `behavioral_state()` khi gate ON** ⇒ OFF cho ra **JSON y hệt hôm nay** ⇒ ba hash §0.1 bất biến. State bền, có id, có lifecycle, có event, checkpoint được, ablation được. |

### A.4 Owner / lifecycle của từng state (charter §D)

| State | Owner (single-writer) | Lifecycle | Vào `world_hash`? | Checkpoint |
|---|---|---|---|---|
| `w.cu_tru` | `engine/household.py` **duy nhất** | tạo ở `tao_the_gioi` (ON) hoặc khi `cuoi`/`tach_ho`/`di_cu`; giải thể khi rỗng | **CÓ khi ON** (đổi ai được ăn ⇒ đổi quỹ đạo) | có (pickle) |
| `w._next_cu_tru` | `engine/household.py` | đơn điệu tăng | **CÓ khi ON** (quyết định id tương lai ⇒ tie-break) — đặt trong khối `"residence"`, **KHÔNG** nhét vào `state["ids"]` (nhét vào `ids` là đổi layout ngay cả khi OFF) | có |
| `w.cuoi_tick`, `w.cuu_mang_tick`, `w.di_cu_tick`, `w.tach_ho_tick` (cờ transient) | module tạo ra sự kiện (`demography`/`xa_hoi`/`tick._di_cu`), **đọc-và-xóa** bởi `household.buoc_cu_tru` | reset đầu tick (khuôn `ben_kia_tick`, `tick.py:130`) | **KHÔNG** (chết trong tick) | không cần |
| `w.di_san`, `w.di_san_xong`, `w._next_di_san` | `engine/estate.py` **duy nhất** | mở khi chết, đóng khi hết tài sản/hết hạn | **CÓ khi `ho.di_san.bat`** | có |
| `w.poverty_streak` (re-key theo `rid`) | `engine/tick.py:271-280` | như ADR 0003 §E | **KHÔNG** (observation state) | có |
| `m["demography"]` | `engine/metrics_demography.py` | mỗi tick | **KHÔNG** (Lớp-5) | không |

### A.5 Serialization / hash (khuôn ADR 0005 §11)

`engine/world.py:460 behavioral_state()` — thêm **ĐÚNG MỘT khối, CÓ ĐIỀU KIỆN**, sau `"production"`:

```python
if _cu_tru_bat(self):                    # engine/household.py, đọc cfg.get("ho.cu_tru_ben_vung")
    state["residence"] = {"cu_tru": self.cu_tru, "next_id": self._next_cu_tru}
if _di_san_bat(self):                    # engine/estate.py
    state["estate"] = {"mo": self.di_san, "next_id": self._next_di_san}
```

- **OFF ⇒ KHÔNG có key** ⇒ blob JSON không đổi **một byte** ⇒ `world_hash()` không đổi ⇒ ba hash
  §0.1 giữ nguyên, mọi checkpoint/artifact cũ verify được.
- **KHÔNG bump `hash_schema`** (giữ `"behavioral-state-v2"`, `world.py:496`). **KHÔNG** thêm key
  rỗng "cho đẹp" — key rỗng cũng đổi hash.
- ON ⇒ hash khác. Đúng và mong muốn: đó là **thí nghiệm khác** (ADR 0005 §11.4). Hai run cùng
  seed + cùng overlay phải cùng hash (T-40).
- **`di_san_xong` KHÔNG vào hash** (kho lưu trữ chỉ observatory đọc — khuôn `hop_dong_xong`… *lưu ý:
  `hop_dong_xong` HIỆN ĐANG ở trong hash, `world.py:524`; ta cố ý **không** bắt chước chỗ đó, vì
  estate đã đóng không ảnh hưởng quỹ đạo. Ghi rõ để reviewer bắt bẻ được.*)

### A.6 Cổng scenario (KHÔNG thêm key vào base `config/world.yaml`)

Đọc bằng `cfg.get("ho....", False)` ⇒ `cfg.digest()` của base **bất biến**, config cũ thiếu block
và config mới `bat:false` có **cùng transition function** (đúng lý do `_behavioral_config` tồn tại,
`world.py:69-75`).

```yaml
# scenarios/agrarian_transition_v1/spatial_livelihood_v2.yaml  (overlay MỚI; KHÔNG sửa spatial_v1.yaml)
ho:
  bat: false                  # cờ tổng
  cu_tru_ben_vung: false      # §A/§C — membership bền; trưởng thành KHÔNG tự tách
  cap_luong_thuc: false       # §B — provisioning có ledger + event (HASH-NEUTRAL khi bật một mình)
  tach_ho: {bat: false}       # §C — split tường minh
  di_san:                     # §D — estate lifecycle
    bat: false
    claim_han_tick: 3         # = 1 năm ở calendar 3 mùa (design_assumption, chưa có provenance)
    che_do: "kin"             # "kin" | "chia_deu_lang" | "dau_gia" | "tan_ra"  (§E)
    het_han: "chia_deu_lang"  # đích khi hết hạn mà không ai nhận (§D.6) — "cong" bị chặn (§D.6)
```

Helper `engine/household.py:_ho_bat/_cu_tru_bat/_cap_luong_thuc_bat/_tach_ho_bat` và
`engine/estate.py:_di_san_bat` — **đúng khuôn `engine/spatial.py:16-40 _khong_gian_bat`**: sub-flag
TẮT ⇒ path đó **no-op độc lập** ⇒ ablation làm được **từng trục**.

- `preindustrial_closed_v1`: **TẮT vĩnh viễn** (legacy regression, charter §6). Semantics lỗi được
  **đóng băng có ghi chú**, không retcon.
- `agrarian_transition_v1` (base) + overlay `spatial_v1`: **TẮT** ⇒ `real60_spatial`/`mock60_spatial`
  vẫn verify được hash cũ.
- `spatial_livelihood_v2` (scenario MỚI): **BẬT** — và chỉ scenario này mới được diễn giải về hộ.

### A.7 Invariant §A

- **R1 (partition):** cuối mỗi tick, mỗi agent còn sống thuộc **đúng một** `CuTru`;
  Σ|thành viên sống| == số agent sống.
- **R2 (NO AGE-BASED ORPHANING — invariant then chốt của ADR này):** membership **không đổi vì
  tuổi**. Không có code path nào đọc `truong_thanh()` để quyết định membership khi gate ON.
- **R3 (event-explainable):** diff membership giữa tick t−1 và t phải được giải thích **hết** bởi
  event của tick t (replay membership từ event journal ⇒ trùng state).
- **R4 (no dead resident):** không agent chết nào còn trong `thanh_vien` cuối tick; `CuTru` rỗng ⇒
  giải thể + event `tan_ho`.
- **R5 (OFF ⇒ y nguyên):** gate OFF ⇒ `ho_cua`, hash, hành vi, metrics **không đổi một bit**.

### A.8 Failure / rollback §A

- `CuTru` rỗng (cả nhà chết) ⇒ giải thể; `nha_thua` **không** kéo theo quyền sở hữu nhà (nhà là tài
  sản cá nhân trong ledger, đi theo estate §D).
- Trẻ mồ côi chưa được cưu mang trong tick cha mẹ chết: `xa_hoi.cuu_mang_mo_coi` (`tick.py:246`)
  chạy **trước** `buoc_cu_tru` (9b) ⇒ trẻ luôn có hộ trước khi tick kết thúc. Nếu **không ứng viên
  nào** (`xa_hoi.py:145-146` `continue`) ⇒ trẻ giữ `CuTru` cũ (nay chỉ còn mình nó) ⇒ **nó đói
  thật**. Đó là kết quả hợp lệ (không có ai nuôi) — **khác hẳn** với việc engine cắt nó khỏi hộ cha
  mẹ **còn sống**. Không được "cứu" bằng luật ngầm.
- Split khiến người tách vô gia cư: hợp lệ; phạt health đã có (`consumption.py:116-130`).
- **Rollback toàn bộ §A:** đặt `ho.bat: false` trong overlay ⇒ mọi path no-op ⇒ hash + hành vi về
  đúng legacy. Không có state nào bị mất (checkpoint vẫn giữ `cu_tru` cũ, chỉ không đọc).
- **Cấm bật/tắt gate giữa run:** `run.py:296-302` đã chặn resume với config digest khác. ADR này
  ghi rõ: **gate hộ là thuộc tính của run**. Test resume phải chứng minh (T-42).

---

## §B. Provisioning — chọn **(B): tài sản cá nhân + transfer tường minh** (GIỮ ADR 0003 §A.2)

### B.1 Quyết định

> **Tài sản vẫn là CỦA CÁ NHÂN. Việc nuôi nhau trong hộ trở thành một dịch chuyển tài sản TƯỜNG
> MINH:** `ledger.chuyen(người-cấp → người-ăn)` **NGAY TRƯỚC** `ledger.huy(người-ăn, "an")`, kèm
> event `cap_luong_thuc{tu, den, tai_san, so_luong, quy_thoc, ho, ly_do}`.
> **KHÔNG thêm pantry chung** (ADR 0003 §A.2 giữ nguyên).

### B.2 Vì sao (B) chứ không (A) pantry

1. Pantry là **một chủ thể ledger mới có vòng đời sinh/giải thể** — đúng loại vật thể đang gây thảm
   họa `VO_THUA_NHAN` (§D). Thêm ghost-subject mới trong lúc dọn ghost-subject cũ là tự mâu thuẫn.
2. (B) đóng **đúng** cái lỗ Report_v2 §4.2 nêu ("không dùng helper read-only để ngầm tiêu thóc
   người khác mà không có event/đối ứng"). Hiện `consumption.py:69` đốt thóc của thành viên khác
   **không để lại bất kỳ dấu vết nào** về ai nuôi ai.
3. (B) cho **đo được** transfer/provisioning (Report_v2 §P4) mà không cần tài khoản mới.
4. **Tính chất reproducibility (quan trọng nhất — xem B.3):** (B) tách bạch được "cái gì đổi quỹ
   đạo" khỏi "cái gì chỉ thêm sổ sách". (A) không có tính chất này.

### B.3 HASH-NEUTRALITY của `ho.cap_luong_thuc` (chứng minh, không phải hy vọng)

> **Bật RIÊNG `ho.cap_luong_thuc` (membership vẫn legacy) ⇒ `world_hash()` TRÙNG HỆT run OFF.**

Chứng minh (dựa trên G-1):

| Thành phần hash | Trước | Sau | Lý do |
|---|---|---|---|
| `ledger.balances` (`world.py:510`) | m mất `tru` | m mất `tru`; `nguoi_an` +`tru` rồi −`tru` = 0 | `chuyen` + `huy` triệt tiêu ⇒ **số dư cuối tick từng (chủ thể, tài sản) y hệt** |
| `ledger.flow_totals` (`:513`) | `(ts,"an") += tru` | `(ts,"an") += tru` | `FlowRegistry.ghi` khóa **`(tai_san, luong)`**, KHÔNG theo chủ thể (`ledger.py:68-70`); `chuyen` là bút toán CÂN, **không ghi flow** (`ledger.py:162-177`) |
| transaction journal | — | dài hơn | **KHÔNG nằm trong `behavioral_state()`** (`world.py:463` docstring, `:509-514`) |
| `population` (Agent.health, doi_tick…) | — | — | `ty_le_no` (`consumption.py:86`) và mọi hiệu ứng health **phải được tính y hệt hôm nay** (mức hộ, thiếu-đều-theo-tỷ-lệ) |
| `events` | — | thêm `cap_luong_thuc` | events **không** trong hash (ADR 0003 §D.1) |

**INVARIANT P-1 (provisioning is bookkeeping-only):** bật riêng `ho.cap_luong_thuc` ⇒ `world_hash`
**bằng đúng** run OFF, trên ≥2 seed × ≥20 tick. Test T-14.

**Điều kiện bắt buộc để P-1 đúng** (nếu vi phạm là đổi hash, và test sẽ bắt): quy tắc phân bổ khi
**thiếu** phải giữ nguyên semantics hôm nay — *thiếu đều theo tỷ lệ, `ty_le_no` là của cả hộ*.
**KHÔNG** được nhân dịp này thêm luật ưu tiên trẻ em/người già. Ưu tiên hộ là một **treatment
riêng** (`ho.quy_tac_cap: "uu_tien_tre"`), có ablation, **KHÔNG thuộc P1**.

Vì sao tính chất này đáng giá: nó cho phép **ablation sạch** — chạy 4 ô
(membership OFF/ON × provisioning OFF/ON) và biết chắc rằng bất kỳ khác biệt quỹ đạo nào **chỉ có
thể** đến từ membership. Không có nó, mọi so sánh P1 đều bị confound.

### B.4 Thiết kế chi tiết

Trong `engine/consumption.py:an_va_suc_khoe` (`:60-85`), khi `_cap_luong_thuc_bat(w)`:

```python
if m != nguoi_an:                                   # rút kho người khác trong hộ
    w.ledger.chuyen(m, nguoi_an, ts, tru, f"cấp lương thực {ts}", w.tick)
    w.events.ghi(w.tick, "cap_luong_thuc", tu=m, den=nguoi_an, tai_san=ts,
                 so_luong=round(tru, 6), quy_thoc=round(tru * quy_doi, 6),
                 ho=rid, ly_do="quy_tac_ho")
w.ledger.huy(nguoi_an, ts, tru, "an", f"ăn {ts}", w.tick)
```

- **`nguoi_an` là ai:** quy tắc **công khai + tất định** gắn trên `CuTru.quy_tac_cap`; mặc định
  `"nhu_cau_deu"` = mỗi thành viên được cấp đúng `nhu_cau` của mình
  (`nhu_cau.nguoi_lon_kg_tick` / `.tre_em_kg_tick`).
- **Nguồn rút:** giữ **đúng thứ tự hiện có** `sorted(ho, key=lambda x: -ton_kho[x])`
  (`consumption.py:64`) — kho lớn nhất gánh trước. Không đổi (nếu đổi là mất P-1).
- **Bảo toàn:** `chuyen` cân theo từng tài sản; `huy` dùng sink `"an"` đã đăng ký (`world.py:696`).
  Mỗi kg đi qua **đúng một** `chuyen` (tùy chọn) và **đúng một** `huy`. Không mint, không
  double-consume. `kiem_toan_the_gioi` xanh không đổi.
- **Không âm số dư:** `tru = min(ton_kho[m], thieu/quy_doi)` giữ nguyên ⇒ `chuyen` không bao giờ
  vượt số dư ⇒ không `LoiSoKep`.

### B.5 Ranh giới "ai được ăn ké kho ai" (ba điều kiện ĐỒNG THỜI, không ngoại lệ)

1. **Membership:** người ăn và người cấp cùng **một `CuTru`** (R1). Ngoài hộ ⇒ **0 kg**, không có
   đường nào khác trong `an_va_suc_khoe` (T-15).
2. **Rule công khai:** `CuTru.quy_tac_cap` nằm trong state, trong hash (khi ON), hiển thị trong
   prompt ⇒ agent **biết** mình đang nuôi ai và bị ai nuôi (local-information boundary: agent chỉ
   thấy hộ **của mình**, không thấy hộ người khác).
3. **Event bắt buộc:** mỗi kg vượt ranh giới cá nhân đều có `cap_luong_thuc` ⇒ "ăn ké" **hiện ra**
   trong journal + metric transfer.

Người trưởng thành muốn **thoát nghĩa vụ nuôi** (hoặc thôi bị nuôi) ⇒ `tach_ho` (§C): một quyết
định có event, có hệ quả (tự lo ăn, có thể vô gia cư). **Engine không cưỡng chế lòng tốt và cũng
không cưỡng chế ích kỷ.** Không có luật "phải nuôi con đã trưởng thành"; chỉ có luật "người ở chung
một hộ thì ăn theo quy tắc của hộ đó; không muốn thì tách ra **bằng một hành động**".

### B.6 Rủi ro + PENDING

- **Parasitism:** hộ 8 người lớn ở lì ăn kho một người giàu. Chặn bằng: hộ **chỉ lớn lên** qua
  `sinh`/`cuoi`/`cuu_mang` — **cố ý KHÔNG có** intent "xin vào hộ người khác". Trục xuất
  (`duoi_khoi_ho`) là một action có chi phí quan hệ ⇒ **PENDING, KHÔNG thuộc P1** (giữ scope nhỏ;
  nếu P4 thấy parasitism chi phối kết quả thì mở ADR bổ sung).
- **Mất động cơ lao động của người trẻ:** đó là một **kết quả**, không phải bug — và nó **đo được**
  (`chuyen_giao.ty_le_tu_nuoi`, §F). **Không hard-code chống lại nó.**

---

## §C. Life-course — biến cố nào được đổi membership (và trưởng thành KHÔNG nằm trong đó)

### C.1 Tập biến cố hợp lệ

Membership chỉ được đổi bởi các biến cố sau, **và không gì khác**:

`S = { sinh, cuoi (bao gồm tái hôn), tach_ho, cuu_mang (nhận nuôi), di_cu, chet }` — cộng
`tan_ho` (**hệ quả**, không phải biến cố: hộ rỗng thì giải thể).

> **Ghi chú thẳng thắn về "6 biến cố":** brief giao việc liệt kê *cưới / tách hộ / di cư / nhận
> nuôi / chết / tái hôn*; memo §1.6 R2 liệt kê *sinh / cưới / tách hộ / cưu mang / di cư / chết*.
> Hai danh sách khác nhau ở `sinh` vs `tái hôn`. Sự thật engine: **tái hôn KHÔNG phải code path
> riêng** — nó là `cuoi` áp lên người goá (`demography.py:321-322` xoá `vo_chong`), còn `sinh`
> **thực sự** thêm một thành viên. Vì vậy ADR chốt tập `S` ở trên (6 phần tử, tái hôn là trường hợp
> của `cuoi`). **Con số 6 không load-bearing; điều load-bearing là: `trưởng thành ∉ S`.**

### C.2 Single-writer + điểm chèn

`engine/tick.py` — thêm **đúng hai dòng**, sau `xa_hoi.cuu_mang_mo_coi(w)` (`:246`), trước
`education.buoc_giao_duc` (`:249`):

```python
    xa_hoi.cuu_mang_mo_coi(w)
    household.buoc_cu_tru(w, ke_hoach)   # 9b — MỌI mutation membership ở đây, và CHỈ ở đây
    estate.buoc_di_san(w)                # 9c — §D
```

**Single-writer (INVARIANT):** ngoài `engine/household.py` / `engine/estate.py`, **không module nào**
được sửa `w.cu_tru` / `w.di_san`. `demography`/`xa_hoi`/`tick._di_cu` chỉ **đặt cờ transient** rồi
`buoc_cu_tru` đọc và áp dụng. Cưỡng chế bằng test grep-level (T-07b: `w.cu_tru` chỉ bị gán trong
`engine/household.py`).

Vị trí này còn thỏa hai ràng buộc cứng: (a) **trước** `audit.kiem_toan_the_gioi` (`tick.py:260`) ⇒
không có tick nào "tạm lệch rồi cân sau"; (b) **sau** `cuu_mang_mo_coi` ⇒ trẻ mồ côi đã có giám hộ
trước khi tính hộ.

### C.3 Bảng transition (deterministic ordering + tie-break)

Trong `buoc_cu_tru`, xử lý theo **đúng thứ tự** này; mọi vòng lặp duyệt `sorted(...)` theo id; `rid`
mới cấp từ `_next_cu_tru` tăng đơn điệu ⇒ tất định tuyệt đối, **không phụ thuộc dict order**.

| # | Transition | Điều kiện | Ai quyết | Hiệu ứng membership | Event | Tie-break |
|---|---|---|---|---|---|---|
| 1 | **chet** | `cai_chet` (`demography.py:193`) | engine (hazard) | rời `CuTru`; hộ rỗng ⇒ `tan_ho` | `chet` (đã có) | `sorted(w.agents)` (đã có) |
| 2 | **sinh** | `sinh_con` (`demography.py:93`) | agent + RNG | newborn vào `CuTru` của **mẹ**; mẹ chết ⇒ cha; cả hai chết ⇒ để `cuu_mang` xử | `sinh` + `vao_ho{tre, ho}` | id trẻ |
| 3 | **cuu_mang** | mồ côi cả cha lẫn mẹ, chưa trưởng thành (`xa_hoi.py:117`) | engine (bậc máu mủ → người dưng) | trẻ chuyển sang `CuTru` của `giam_ho` | `cuu_mang` + `chuyen_ho{nguoi, tu_ho, den_ho}` | `(bậc, -tuổi, id)` (đã có, `xa_hoi.py:121-147`) |
| 4 | **cuoi / tái hôn** | `xu_ly_cau_hon` chấp nhận (`demography.py:63-69`) | **agent** | **spouse-joins:** người có `rid` **lớn hơn** chuyển sang `CuTru` của người kia, **mang theo** người phụ thuộc mà mình là cha/mẹ/giám hộ **duy nhất còn sống** (con riêng đi theo cha/mẹ ruột); hộ cũ rỗng ⇒ `tan_ho` | `cuoi` (đã có) + `nhap_ho{nguoi, mang_theo, tu_ho, den_ho}` | `rid` nhỏ hơn thắng; `rid` bằng nhau (đã cùng hộ) ⇒ **no-op** |
| — | **trưởng thành** | `tuoi_nam >= tuoi_truong_thanh` | — | **KHÔNG LÀM GÌ** (INVARIANT R2) | — | — |
| 5 | **tach_ho** | intent `tach_ho`; người tách: **sống + đã trưởng thành**; hộ nguồn còn **≥1 người lớn sống** sau khi trừ người đi (không để trẻ/già lại không người lớn) | **agent** | lập `CuTru` MỚI cùng làng; mang theo người phụ thuộc trực hệ | `tach_ho{nguoi, mang_theo, tu_ho, den_ho}` | `sorted(ke_hoach)` |
| 6 | **di_cu** | `_di_cu` thành công (`tick.py:347-373`) | **agent** | người di cư (+ phụ thuộc trực hệ) lập `CuTru` MỚI ở **làng mới**; hiệu lực **cuối tick** — họ **đã ăn với hộ cũ** trong tick này (**hành vi khai báo, không phải bug**) | `di_cu` (đã có) + `tach_ho{ly_do:"di_cu"}` | `sorted(ke_hoach)` |
| 7 | **tan_ho** | `thanh_vien` sống = ∅ | engine | giải thể | `tan_ho{ho}` | `sorted(w.cu_tru)` |

`thua_ke` **không** đổi membership (đó là tài sản — §D).

### C.4 Hệ quả miễn phí (không thêm state)

- **Caretaker:** `care.py:16-18` (`_ho_tre`) đã gọi `w.ho_cua(child)` ⇒ khi gate ON, **anh/chị đã
  trưởng thành sống chung nhà tự động là caretaker hợp lệ**; `gop_cong` trả công chăm trẻ chạy y
  nguyên (T-13).
- **Người già:** `production.sinh_cong` (`:23-26`) đã giảm công theo tuổi; `consumption.py:105-106`
  đã hao sức tuổi già. Với residence bền, người già **ở lại hộ con cháu** và được cấp lương thực
  qua §B — đúng cái mà docstring `production.py:11-12` đã hứa nhưng engine chưa làm được.

### C.5 Rejection / unrecognized-intent (LLM không chạm state — điều luật #3)

| Intent | Từ chối khi | Mã lý do |
|---|---|---|
| `tach_ho` | người chưa trưởng thành | `chua_truong_thanh` |
| `tach_ho` | bỏ lại trẻ/già không người lớn | `no_adult_left` |
| `tach_ho` | người không tồn tại / đã chết | `khong_hoat_dong` |
| `yeu_cau_di_san` (§D) | không thuộc bậc thừa kế hợp lệ | `no_right` |
| `yeu_cau_di_san` | quá `han_tick` | `het_han` |

Mọi từ chối ⇒ `w.ghi_unrecognized(...)` + **bỏ qua êm**, không raise (điều luật #3).

---

## §D. Estate lifecycle — `VO_THUA_NHAN` thôi làm ví vĩnh viễn

### D.1 Quyết định

> **Di sản (`DI_SAN:<aid>`) là một chủ thể ledger CÓ HẠN, không phải một cái ví vĩnh viễn.** Nó mở
> khi người chết, đóng bắt buộc chậm nhất sau `ho.di_san.claim_han_tick`, và **mọi tài sản / mọi
> khoản nợ có ĐÚNG MỘT đích hợp pháp**.

```python
# engine/estate.py (module MỚI)
@dataclass
class DiSan:
    id: str                          # "DI_SAN:A0051"
    nguoi_mat: str
    lang: int                        # làng lúc chết (cho escheat §D.6)
    mo_tick: int
    han_tick: int                    # mo_tick + claim_han_tick
    trang_thai: str                  # "mo" | "dong"
    yeu_cau: list[tuple[str, str]]   # (claimant, ly_do) — SORTED, tất định
# World: di_san: dict[str, DiSan]; di_san_xong: dict[str, DiSan]; _next_di_san: int
```

### D.2 Đường đi CHÍNH là NGUYÊN TỬ TRONG TICK CHẾT (làm rõ chỗ memo để ngỏ)

Memo §4.3 mô tả 5 bậc nhưng không nói bậc nào chạy ở tick nào. ADR chốt:

> **Bậc 0–3 chạy TRỌN VẸN trong bước 9c của CHÍNH tick người đó chết.** Claim window
> (`claim_han_tick`) **chỉ có ý nghĩa khi bậc 3 không tìm được người nhận nào** — khi đó estate ở
> lại trạng thái `"mo"` để người có tư cách `yeu_cau_di_san`; hết hạn ⇒ bậc 4.

Lý do (3 cái, đều là ràng buộc cứng của repo):

1. **Audit mỗi tick (điều luật #1).** Nếu bậc 1–3 rải qua nhiều tick thì có tick mà tài sản nằm
   trong một chủ thể không-hoạt-động trong khi người sống đang đói — chính là F-19 thu nhỏ. Nguyên
   tử ⇒ không có "tick tạm lệch".
2. **Đất.** `audit.py:30` cấm thửa có chủ không hoạt động. Estate **không được** đứng tên đất. Nếu
   thừa kế đất rải nhiều tick, đất phải về `None` rồi "cấp lại" cho heir — tức là **mint quyền sở
   hữu**, một định chế cấp đất mới. **Không nới `audit.py:30` để cho tiện.** Nguyên tử ⇒ đất đi
   thẳng từ người chết sang heir **đúng như hôm nay** (`demography.py:306-309`), và chỉ đi về công
   (`None`) khi **thật sự không có heir** (`:311`).
3. **Hợp đồng.** Contracts chạy bước 7 (`tick.py:222`), chết chạy bước 9 (`:242`). Ở tick chết,
   bước 7 đã chạy xong với người còn sống ⇒ nghĩa vụ định kỳ của tick đó **đã được trả** ⇒ estate
   chỉ phải xử **nghĩa vụ tồn đọng**, không có double-pay.

**Hệ quả cho memo §4.3 bậc 0 (đất):** memo đề xuất `DiSan.dat_ve_cong` để "claim bậc 3 xin cấp
lại". **BỎ.** Không có field đó, không có cơ chế cấp lại đất. Đất về công **chỉ** khi không heir, và
việc lấy lại đất công đã có đường hợp lệ sẵn (khai hoang / mua). Ghi vào event `thua_ke{ve_cong:[…]}`
cho forensic; **không** vào state.

### D.3 Thứ tự xử lý (deterministic, `estate.buoc_di_san`, tick.py 9c)

Duyệt `sorted(w.di_san)`; trong mỗi estate duyệt `sorted(...)` theo id.

| Bậc | Đích | Quy tắc | Ledger |
|---|---|---|---|
| **0. Mở** | `DI_SAN:<aid>` | **Toàn bộ** `ledger.tai_san_cua(aid)` **trừ `"cong"`** (công bốc hơi cuối tick, `tick.py:254`) chuyển sang estate — **kể cả** `vi_the:*` và `co_phan:*` ⇒ người chết có **số dư 0** ngay trong tick chết. **Đất KHÔNG vào estate** (audit.py:30) — xử ở bậc 3/4 trực tiếp từ `p.chu`. | `chuyen(aid → DI_SAN:aid, ts, sl)` |
| **1. Chủ nợ / hợp đồng** | các bên **còn hoạt động** của hợp đồng `hieu_luc`/`vi_pham` mà người chết có nghĩa vụ | **TÁI DÙNG khuôn `entities.thanh_ly`** (`entities.py:218-244`, đã chạy trong production): `chu_no[den] += gia_tri_thi_truong(...)` cho (a) `chuyen_giao_mot_lan` **chưa trả** và (b) `hoan_tra_theo_yeu_cau` (trần rút). Trả **pro-rata theo giá trị nghĩa vụ**, bằng **hiện vật**, `sorted(chu_no)`. Thiếu ⇒ event `khong_thu_du{hd, chu_no, thieu}` — **mất mát là THẬT, không giấu, không mint bù**. Sau đó `hd.trang_thai = "huy"` + `dot_vi_the` + event `thanh_toan_di_san`. | `chuyen(DI_SAN → chu_no)` |
| | **`chuyen_giao_dinh_ky` không thời hạn** (`thoi_han=None`) | **KHÔNG có nghĩa vụ tồn đọng xác định** ⇒ dòng thu tương lai **chấm dứt**; event `nghia_vu_cham_dut{hd, loai:"dinh_ky_khong_thoi_han"}`. Đây là một **quyết định**, không phải một lỗi làm ngơ: định giá một annuity vô hạn cần discount rate — một tham số **không có provenance** — nên ta **không bịa** nó. | — |
| | **`the_chap`** | Nếu hợp đồng có thế chấp: **`xiet_the_chap` chạy TRƯỚC pro-rata** (`contracts.py:216`) ⇒ chủ nợ có bảo đảm được ưu tiên **đúng như khi con nợ còn sống**. Không tạo thứ tự ưu tiên mới. | theo `xiet_the_chap` |
| **2. Di chúc** | `a.di_chuc["phan_bo"]` | Áp trên **phần còn lại sau nợ** — logic hiện có (`demography.py:236-251`) giữ nguyên, **chỉ đổi nguồn** từ `aid` sang `DI_SAN:aid` | `chuyen(DI_SAN → nguoi_nhan)` |
| **3. Kin claim** | con còn sống → vợ/chồng → **(MỚI) người đồng cư trú lúc chết** | Thứ tự hiện có (`demography.py:252-263`, kể cả filter `chu_the_hoat_dong`) **+ một bậc mới cuối cùng**: thành viên `CuTru` của người chết (loại người đã nhận ở bậc 2), `sorted()`. Đây là chỗ residence "trả tiền" cho chính nó: **sống chung thì thừa kế**. **Đất** chia round-robin cho `nguoi_nhan` (y như `demography.py:302-309`); không heir ⇒ `p.chu = None` (`:311`). | `chuyen(DI_SAN → nguoi_nhan)` |
| **4. Hết hạn** | `w.tick >= han_tick` **và** còn số dư | Theo `ho.di_san.het_han` — **xem §D.6**. Mặc định `chia_deu_lang`. | `chuyen(DI_SAN → …)` |
| **5. Đóng** | mọi tài sản = 0 | `trang_thai="dong"`; chuyển sang `di_san_xong`; event `dong_di_san{id, nguoi_nhan_cuoi, theo_tai_san}` | — |

**Chi tiết implementation phải nói trước (bẫy đã thấy khi đọc code):**

- `xay_vi_the_chu` (`contracts.py:296-303`) suy chủ vị thế **từ số dư**. Khi `vi_the:*` nằm trong
  `DI_SAN`, `ben_hien_tai` trả `DI_SAN:*` ⇒ `_hoat_dong_ca_hai` (`contracts.py:357-358`) trả
  `False` ⇒ **mọi leg của hợp đồng đó bị SKIP** trong bước 7. Đây là hành vi **đúng và mong muốn**
  (không trả tiền cho/từ một cái xác), và nó **an toàn** vì bậc 1 đã đóng hợp đồng ngay trong tick
  chết ⇒ bước 7 tick sau bỏ qua nó (`contracts.py:325-327` chỉ chạy `trang_thai == "hieu_luc"`).
- Hợp đồng do estate đóng ở 9c sẽ được sweep vào `hop_dong_xong` ở **đầu bước 7 tick sau**
  (`tick.py:229-231`) — chậm một tick, **vô hại** (đã bị skip), nhưng phải ghi ra để không ai tưởng
  là rò rỉ.
- `co_phan:*` vô thừa nhận: giữ nguyên hành vi hiện tại — **hủy** qua sink `"giai_the"` đã đăng ký
  (`demography.py:277`), tỷ trọng cổ đông còn lại tự tăng. Đó **không** phải sink lậu (có đối ứng).
- **Blueprint mồ côi** (`demography.py:296-300`, giữ tên người chết ⇒ ghost-owner): **PENDING, KHÔNG
  sửa trong P1.** Ghi nhận tường minh là **defect đã biết** (F-7 của memo). Sửa nó chạm `research.py`
  ⇒ ADR riêng. Nêu ra để không ai tưởng §D đã dọn sạch mọi ghost.

### D.4 F-20 — sửa ở đâu, và hệ quả hash

`engine/contracts.py:423-425` hiện làm: `if dao_han or ben_chet: trang_thai="huy" ... dot_vi_the`.

**Khi `ho.di_san.bat` ON:** nhánh `ben_chet` cho **agent** trở thành **không thể xảy ra** — vì estate
đã đóng hợp đồng đó ở bước 9c của **chính tick chết**, trước khi bước 7 của tick sau chạy. Vẫn phải
**giữ nhánh** cho trường hợp `_ben_mat` do **entity biến mất** (`contracts.py:340`) và làm nó
**fail-loud** nếu gặp agent chết mà estate ON (assert ⇒ nghĩa là estate đã bỏ sót một hợp đồng ⇒
bug thật, phải dừng, điều luật #1).

**Khi OFF:** **không đổi một ký tự hành vi** ⇒ ba hash pin bất biến.

> **Chốt về thứ tự tick:** ADR này **KHÔNG đổi thứ tự các bước tick**. Đảo `demography` lên trước
> `contracts` sẽ đổi quỹ đạo của **mọi** run, kể cả gate OFF ⇒ vi phạm ADR 0001 §D. Cách sửa F-20 là
> **thêm bước 9c**, không phải hoán vị bước 7/9.

### D.5 Ghost offer — chặn ở đâu (và sự thật: phần lớn ĐÃ được chặn)

| Bề mặt | Trạng thái hôm nay | Cần làm |
|---|---|---|
| Đề nghị hợp đồng | `board.dang_de_nghi` (`board.py:34`) gọi `validate_hop_dong` ⇒ `contracts.py:118-121` trả `"bên không tồn tại: DI_SAN:*"` (không phải agent/entity) và `"bên đã chết: A00xx"` | **TEST** (T-24 a,b), không cần code mới |
| Đặt lệnh chợ | `tick.py:187` lọc `chu_the_hoat_dong(aid)`; `ke_hoach` chỉ chứa agent | **TEST** (T-24c) |
| Trộm | `xa_hoi.py:50-52` kiểm `chu_the_hoat_dong(muc_tieu)` ⇒ `DI_SAN:*`/người chết bị `unrecognized` | **TEST** (T-24d) |
| Đứng tên đất | `audit.py:30` raise nếu chủ không hoạt động | **TEST** (T-24e) — và **KHÔNG được nới** để estate giữ đất |
| Tin nhắn | `tick.py:83-84` | **TEST** |
| Thành viên `CuTru` | R4 | **TEST** |

⇒ Kết luận thật thà: **bề mặt ghost-offer về cơ bản đã đóng bởi `chu_the_hoat_dong`.** Cái còn
thiếu là (a) **test** cưỡng chế, và (b) bảo đảm rằng **chính §D không mở ra đường mới** (estate
không được đặt lệnh, không được ký, không được nhận đất). Không có code chặn mới ⇒ không có hash
change ⇒ tốt.

### D.6 **Hết hạn: `CONG_QUY` bị CHẶN — đổi route mặc định (correction đối với memo §4.3 bậc 4)**

Bằng chứng G-2: trong `agrarian_transition_v1` (`chinh_tri.bat: false`), `CONG_QUY` **không có
đường thoát nào**; và ngay cả khi `chinh_tri.bat: true`, `_chia_deu` chỉ rebate **`tong_thu` của
tick đó** và **chỉ `"thoc"`**. Một căn nhà / con gà / khúc gỗ vào `CONG_QUY` sẽ **kẹt vĩnh viễn** —
tức là **F-19 đội tên khác**, mà vẫn pass invariant E1 của memo.

**Quyết định — `ho.di_san.het_han` là enum, mặc định `chia_deu_lang`:**

| Giá trị | Cơ chế | Đích của từng loại tài sản | Ghi chú |
|---|---|---|---|
| **`chia_deu_lang`** (MẶC ĐỊNH) | Escheat-to-commons per-capita: chia cho **người lớn còn sống của làng người mất** (`DiSan.lang`), `sorted(id)` | Tài sản **chia lẻ được** (thoc, khoai, go, ga…): pro-rata, **người cuối nhận phần dư** (khuôn `_chia_deu`, `politics.py:230-238`) ⇒ số dư estate về **đúng 0**. Tài sản **nguyên chiếc** (`TAI_SAN_ROI = nha, cong_cu, may`, `demography.py:13`): **round-robin** theo `sorted(recipients)` | Làng rỗng (không người lớn sống) ⇒ mở rộng ra **toàn thế giới**, `sorted(id)`; không còn ai sống ⇒ estate rơi xuống `tan_ra` (không còn ai để chia — bảo toàn qua sink) |
| `dau_gia` (P2) | Estate bán qua `phien_cho` **đúng một lần** (đất qua `phien_dat`); **tiền thu về estate** rồi **chia theo `chia_deu_lang`** | như trên, sau khi quy về thóc/xu | Auction **không** tự nó có đích cuối — nó chỉ đổi *ai* nhận vật; **phải** kèm route phân phối tiền. "Auction vào hư không" bị cấm. |
| `tan_ra` | Phân hủy: `ledger.huy(DI_SAN, ts, sl, "tan_ra", …)` qua **sink đăng ký MỚI** `(ts, "tan_ra")` cho mọi `ts` | biến mất khỏi thế giới, có đối ứng, audit xanh | **Đây là ablation/null-treatment** — "không ai nhận thì của cải mất". Về mặt vật lý là hợp lý (nhà không người ở thì sập). **Đây là baseline để đo xem chế độ truyền thừa có tác dụng gì.** |
| `cong` | về `CONG_QUY` | — | **CHẶN Ở TẦNG CONFIG.** `household.kiem_tra_cau_hinh(cfg)` (gọi trong `tao_the_gioi`) **raise `SystemExit`** nếu `het_han == "cong"` mà **không** (`chinh_tri.bat` **và** một drain đã khai báo phủ **mọi** loại tài sản). Không có nhánh "cứ chạy đi rồi tính". |

**INVARIANT E1′ (NO ABSORBING SINK — thay thế và bao hàm E1 của memo):**

> Với mọi tick, mọi **terminal subject** S ∈ {`VO_THUA_NHAN`, `DI_SAN:*`, `CONG_QUY`} và mọi tài sản
> `ts`: **hoặc** `so_du(S, ts) == 0`, **hoặc** S có một **drain đã khai báo** (hàm có tên + cờ
> scenario đang BẬT) rút được **đúng loại tài sản đó** về tay chủ thể hoạt động.
> Danh sách terminal subject + drain là một **bảng tường minh trong code**; thêm chủ thể ledger mới
> mà quên khai báo drain ⇒ **test FAIL** (T-16).

E1′ bắt được cả trò "đổi tên sink". E1 gốc của memo (`so_du(VO_THUA_NHAN)==0`) được **giữ** như một
trường hợp riêng.

### D.7 Invariant §D

- **E1′** (trên) — no absorbing sink, no renamed sink.
- **E1** (giữ từ memo): gate ON ⇒ `so_du(VO_THUA_NHAN, ts) == 0` ∀ts, ∀tick; và mọi estate có
  `w.tick > han_tick` có số dư 0 ∀ts. Assert trong nhánh gated của `audit.kiem_toan_the_gioi`.
- **E2 (đúng một đích):** mỗi kg / mỗi thửa / mỗi khoản nợ có **đúng một** đích hợp pháp và được xử
  **đúng một lần**. Pro-rata không vượt tổng; không double-pay; không double-consume.
- **E3 (bảo toàn):** ∀ts: tổng trước chết == tổng sau khi estate đóng (trừ phần đi qua **sink đã
  đăng ký**: `"an"`, `"giai_the"`, `"tan_ra"`). `kiem_toan_the_gioi` xanh **mọi tick** suốt lifecycle.
- **E4 (no ghost actor):** người chết và `DI_SAN:*` **không** là bên hợp đồng mới, không đặt lệnh
  chợ, không là mục tiêu trộm, không nhận tin nhắn, không là thành viên `CuTru`, không đứng tên đất.

### D.8 Failure / rollback §D

- Estate **không đủ trả nợ** ⇒ chủ nợ nhận pro-rata, phần thiếu **mất thật** (`khong_thu_du`).
  Không mint bù, không số dư âm, **không** cho nợ "sống tiếp" sang heir (đó sẽ là **nợ truyền đời**
  — một định chế mới, cần ADR riêng; **KHÔNG thuộc P1**).
- Người nhận thừa kế **chết cùng tick** ⇒ đã bị loại bởi filter `chu_the_hoat_dong`
  (`demography.py:263`, giữ nguyên) ⇒ rơi xuống bậc kế tiếp.
- Mọi bậc rỗng ⇒ estate ở `"mo"` tới `han_tick` ⇒ bậc 4.
- **`LoiSoKep` trong estate settlement: KHÔNG nuốt** (khác `market.py:116-117`). Estate settlement
  phải nguyên tử; raise ở đây **là bug thật** ⇒ dừng + checkpoint (điều luật #1).
- **Rollback:** `ho.di_san.bat: false` ⇒ `buoc_di_san` no-op ⇒ hành vi + hash về đúng legacy
  (bao gồm cả `VO_THUA_NHAN` sink — legacy được **đóng băng có ghi chú**, không retcon).

---

## §E. Cổng định chế (charter §5) — estate có phải "định chế có tên" không?

**Phán quyết, tách làm hai (vì hai thứ này bị memo gộp làm một):**

### E.1 *Cơ chế* estate (chủ thể ledger có hạn + closure "mọi tài sản có đúng một đích") = **Lớp-1/2, KHÔNG cần cổng**

Lý do: đây không phải một *lựa chọn thể chế*, đây là **hệ quả bắt buộc của Lớp-2**. Người chết
mang theo tài sản; kế toán sổ kép **buộc** tài sản đó phải có một đích. Engine hôm nay **đã** có một
đích (`VO_THUA_NHAN`) — nó chỉ là một đích **sai** (đích hấp thụ vĩnh viễn). Thay một đích hấp thụ
bằng một quy trình đóng có thời hạn **không thêm năng lực gì cho ai**: không tạo tín dụng, không
tạo tiền, không tạo quyền lực. Nó **sửa một lỗi kế toán**. Không có cổng nào áp cho việc sửa lỗi
kế toán, và **không được** dùng cổng làm cớ để trì hoãn sửa F-19.

### E.2 *Chế độ truyền thừa* (`ho.di_san.che_do` ∈ {`kin`, `chia_deu_lang`, `dau_gia`, `tan_ra`}) = **`institutional_assumption`, PHẢI qua cổng**

Đây **là** một định chế có tên: nó phân bổ của cải **không qua thị trường và không cần sự đồng ý
của người sống**. Áp cổng charter §5 — **trả lời thật thà từng điều kiện**:

| # | Điều kiện | Đáp ứng? | Bằng chứng / lời thú nhận |
|---|---|---|---|
| 1 | **Alternative** khả thi | **CÓ** | ≥3 chế độ cài được và bật/tắt bằng config: `chia_deu_lang` (commons escheat), `dau_gia` (thị trường), `tan_ra` (phân hủy — **null treatment**). `kin` không phải "cách duy nhất". |
| 2 | **Cost**: tạo/duy trì tốn lao động/tài nguyên đo được | **KHÔNG. Chi phí = 0.** | Không có công chứng, không có tranh chấp, không có phí chuyển nhượng. Thừa kế trong thiết kế này là **miễn phí**. Đây là một **THẤT BẠI THẬT của điều kiện 2** — ADR **không** giả vờ đã thỏa. |
| 3 | **Accounting identity** | **CÓ** | Mọi flow có đối ứng; audit mỗi tick; E1′/E2/E3. |
| 4 | **Scenario flag** | **CÓ** | `ho.di_san.bat` + `che_do` + `het_han`; mặc định OFF; legacy TẮT vĩnh viễn. |
| 5 | **Ablation** có outcome dự báo trước | **BẮT BUỘC** (§G.4) | Pre-register: `tan_ra` ⇒ Gini tài sản **thấp hơn** và persistence liên thế hệ **yếu hơn** so với `kin`; nếu **không** thấy dấu đó, chế độ truyền thừa **không** phải cơ chế giải thích. |

**Phán quyết cuối:** chế độ truyền thừa **KHÔNG THỎA ĐỦ 5 điều kiện** (rớt #2). Theo charter §5,
"không thỏa đủ 5 → module không được vào engine, **hoặc phải chuyển thành treatment tường minh**".
**Ta chọn vế thứ hai:**

> **`ho.di_san.che_do` được khai báo là `institutional_assumption` / `experimental_treatment`
> (charter §4), KHÔNG phải "định chế tự phát".** Cấm tuyệt đối mọi phát biểu kiểu "thừa kế nổi lên
> nội sinh trong THÓC". Nó là **cấu trúc do người thiết kế đặt vào qua scenario overlay**, và mọi
> kết quả phụ thuộc nó phải báo kèm ablation `tan_ra`.
>
> **PENDING (điều kiện để nâng tier):** nếu P4 phát hiện chế độ truyền thừa **chi phối** kết quả
> đầu bảng (bất bình đẳng, tích tụ đất, phân tầng), thì **trước** khi công bố ở bất kỳ tier nào cao
> hơn `mechanism_result`, phải thêm một **chi phí thừa kế thật** (công chứng/tranh chấp/phí chuyển
> nhượng — có sink đăng ký) và chạy lại. **Không được** phát minh chi phí *bây giờ* chỉ để cho qua
> cổng — bịa một tham số không nguồn để làm đẹp một checklist còn tệ hơn là thừa nhận nó rỗng.

**Phản biện tự nêu (để reviewer công kích):** có thể lập luận "counterfactual của thừa kế không phải
*không có gì*, mà là *một đích khác*, và mọi đích đều miễn phí ⇒ điều kiện #2 không áp dụng được cho
*closure rule*". Lập luận đó có sức nặng và là lý do ADR vẫn cho `che_do` vào engine. Nhưng nó
**không** biến chi phí 0 thành chi phí có thật ⇒ nhãn `institutional_assumption` **giữ nguyên**, và
`tan_ra` **phải** tồn tại như một chế độ chạy được để bất kỳ ai cũng kiểm chứng được điều đó.

### E.3 Residence + provisioning có qua cổng không?

- **Residence membership**: **Lớp-1/2.** "Ai sống chung nhà với ai" là một dữ kiện vật lý; đích của
  §A là **xóa một luật vật lý ẩn không khai báo** (tuổi ⇒ mất quyền tiếp cận kho). Không cần cổng.
- **Provisioning**: **Lớp-2 thuần** — nó chỉ **ghi ra** một dòng chảy **đã xảy ra** hôm nay trong im
  lặng (P-1: hash-neutral ⇒ **không thêm hành vi nào**). Không cần cổng. Đây là lập luận mạnh nhất
  ủng hộ phương án (B): *một cơ chế không đổi quỹ đạo thì không thể là một định chế mới.*
- **`quy_tac_cap` (quy tắc phân bổ trong hộ)**: mặc định `"nhu_cau_deu"` giữ **đúng** semantics hôm
  nay. Bất kỳ quy tắc **khác** (ưu tiên trẻ em / người lao động / chủ hộ) **là một định chế phân
  phối** ⇒ phải qua cổng đầy đủ ⇒ **PENDING, ngoài P1**.

---

## §F. Metrics nhân khẩu (chuẩn bị P4) — Lớp-5, ngoài `world_hash`

### F.1 Sự thật nền

`engine/metrics.py:143-195` **không có một chỉ số nhân khẩu nào** ngoài `dan_so`, `nguoi_lon`,
`health_tb`. Grep `life_expectancy|tuoi_tho|age_at_death` trong `engine/`, `tools/`, `observatory/`:
**0 match** (F-23). ⇒ **Hiện chưa có file:line nào phạm lỗi.** INV-M1 dưới đây là **phòng ngừa**,
không phải sửa lỗi đã có. Rủi ro nằm ở tầng **báo cáo** (rất dễ viết "tuổi thọ giảm còn X" từ tuổi
trung bình người sống).

### F.2 INVARIANT M1 (tuyệt đối)

> **TUYỆT ĐỐI KHÔNG được đặt key `life_expectancy` / `tuoi_tho` từ tuổi của người CÒN SỐNG.**
> Hai đại lượng phải nằm ở **hai key khác nhau, khác tên gốc**. Một key tên `e0_*` chỉ được tồn tại
> khi nó là `e0` tính từ **period life table** có `exposure` khai báo **và** có missing-data policy.
> Test T-31 phải FAIL nếu `m["demography"]` chứa `life_expectancy`/`tuoi_tho`.

### F.3 Schema (`engine/metrics_demography.py` → `m["demography"]`)

| Key | Định nghĩa | `None` khi |
|---|---|---|
| `song.n`, `song.tuoi_tb`, `song.tuoi_trung_vi` | **của người ĐANG SỐNG** | `n == 0` |
| `chet.n_tick`, `chet.theo_nguyen_nhan` | đếm **từ state trong tick** (nhãn đúng `demography.py:206-216`) | — |
| `chet.tuoi_tb_khi_chet`, `chet.tuoi_trung_vi_khi_chet` | **AGE AT DEATH** (cửa sổ `quan_sat.cua_so_nhan_khau_tick`) | `n_deaths < quan_sat.min_n_tu_vong` ⇒ **None**, KHÔNG phải 0.0 |
| `ty_suat_chet` | deaths(W) / **person-ticks**(W) × `tick_moi_nam` (đơn vị **/người/năm**, ghi trong key doc) | person-ticks < ngưỡng |
| `ty_suat_sinh` | births(W) / person-ticks(W) × `tick_moi_nam` | như trên |
| `ty_suat_sinh_theo_tuoi_me` | births(W) / **woman-ticks** trong `[tuoi_me_min, tuoi_me_max]` | woman-ticks < ngưỡng |
| `ty_le_phu_thuoc` | (trẻ < `tuoi_truong_thanh` + già > `tuoi_nghi`) / (người trong tuổi lao động) | mẫu = 0 |
| `bang_song` (P4) | `nqx` theo band tuổi từ deaths/person-ticks; `e0_period` **chỉ** khi **mọi** band đủ exposure | band thiếu exposure ⇒ band=None ⇒ `e0_period = None` |
| `cu_tru.n`, `cu_tru.co_so_thanh_vien` | số hộ + phân bố quy mô (**đơn vị = residence** khi ON) | — |
| `cu_tru.ty_le_thieu_an` | share hộ có `food_security < 1` (**key MỚI**, đơn vị residence). Giữ `ty_le_ho_thieu_an` legacy **riêng** để **không lẫn hai đơn vị** | 0 hộ |
| `cu_tru.thoi_gian_ngheo` | poverty duration — **re-key `w.poverty_streak` theo `rid`** thay vì head-id ⇒ **sửa luôn giới hạn ADR 0003 §E** ("head đổi ⇒ streak gãy") | hộ mới ⇒ 0 |
| `chuyen_giao.luong_thuc_quy_thoc` | Σ `cap_luong_thuc.quy_thoc` trong tick (§B) | `cap_luong_thuc` OFF ⇒ None |
| `chuyen_giao.ty_le_tu_nuoi` | (thóc **tự ăn**) / (tổng ăn) — đo **phụ thuộc** | tổng ăn = 0 |
| `di_san.n_mo`, `.n_dong`, `.gia_tri_dang_treo` | estate đang mở / đã đóng / giá trị treo (quy thóc) | estate OFF ⇒ None |
| `di_san.ket_vinh_vien` | Σ `so_du(terminal subject không có drain)` quy thóc — **phải = 0 khi ON** (E1′) | — |

- **Missing-data policy (bắt buộc, khuôn ADR 0003 §C):** mẫu số < ngưỡng ⇒ **`None`**. Không 0 giả,
  không NaN im lặng. Ngưỡng trong `quan_sat.*`, không magic number.
- **Chống nhiễm journal (P0.2 / F-21):** mọi chỉ số nhân khẩu tính từ **state engine trong tick**,
  ghi vào `metrics.jsonl` một dòng/tick. **CẤM** tính death/birth rate bằng cách **đọc lại**
  `events.jsonl` — `real60_spatial` chứng minh vì sao (hai lịch sử phản-thực chồng nhau ở tick
  106–117).
- **Ngoài `world_hash`** (Lớp-5, khuôn `m["research"]`, `tick.py:263-265`) nhưng **phải tái dựng
  được** từ `metrics_lich_su`.

---

## §G. Migration, hash gate, config, test matrix

### G.1 Migration `nap_checkpoint` (`world.py:619`, khuôn `poverty_streak`/`ben_kia_tick` `:668-688`)

```python
if not hasattr(w, "cu_tru"):        w.cu_tru = {}
if not hasattr(w, "_next_cu_tru"):  w._next_cu_tru = 0
if not hasattr(w, "di_san"):        w.di_san = {}
if not hasattr(w, "di_san_xong"):   w.di_san_xong = {}
if not hasattr(w, "_next_di_san"):  w._next_di_san = 0
```

Checkpoint cũ (OFF) nạp lại ⇒ dict rỗng ⇒ key `"residence"`/`"estate"` **vẫn không xuất hiện** (gate
OFF) ⇒ **hash y nguyên** ⇒ resume run cũ không gãy (T-41, T-42).

**Khởi tạo khi ON:** `household.khoi_tao_cu_tru(w)` gọi **một lần** trong `tao_the_gioi` (sau khi tạo
agent, `world.py:833`): mỗi agent t0 = một `CuTru` riêng (t0 toàn người lớn độc thân,
`world.py:788`); id cấp theo `sorted(w.agents)`.

### G.2 Config

- **KHÔNG thêm key `ho:` vào `config/world.yaml`** ⇒ `cfg.digest()` base **bất biến**.
- Overlay MỚI `scenarios/agrarian_transition_v1/spatial_livelihood_v2.yaml` (§A.6). **KHÔNG sửa**
  `spatial_v1.yaml` (nếu sửa, hash pin `SPATIAL_ON` chết).
- Đơn vị + source status của mọi tham số mới (charter §7): `claim_han_tick` = **tick**,
  `design_assumption`, **không** provenance. Phải xuất hiện trong `provenance.csv` của scenario với
  cột status = `design_assumption`.
- `household.kiem_tra_cau_hinh(cfg)` chạy trong `tao_the_gioi`: `het_han == "cong"` mà không có
  drain ⇒ **SystemExit** (§D.6). Fail-closed, không có nhánh "chạy tạm".

### G.3 **GATE CỨNG (điều kiện dừng của P1 — không thương lượng)**

1. Overlay hộ **TẮT** ⇒ rulebot 20 tick phải ra **đúng ba hash §0.1**. Lệch **một ký tự** = FAIL.
   Test `test_hash_legacy_pinned_off` (T-05/T-43).
2. **Toàn bộ suite legacy xanh** + `ruff` sạch + `tools.verify_local` xanh.
3. `ho.cap_luong_thuc` bật RIÊNG ⇒ hash **trùng** run OFF (P-1, T-14).
4. Gate ON ⇒ `kiem_toan_the_gioi` **không raise lần nào** suốt 40+ tick có chết/thừa kế/nợ (T-28).

### G.4 Ablation (bắt buộc, pre-registered — điều kiện của §E.2)

Ma trận **2×2×2** trên `spatial_livelihood_v2`, ≥5 seed, rulebot **và** mock (LLM là treatment cuối,
không phải bằng chứng chính — charter §7):

| Trục | OFF | ON |
|---|---|---|
| `ho.cu_tru_ben_vung` | membership legacy (có adult-orphaning) | membership bền |
| `ho.cap_luong_thuc` | không event (hash-neutral — dùng để **kiểm tra chính test harness**) | có event/ledger |
| `ho.di_san.che_do` | `tan_ra` (null) | `kin` |

**Dự báo trước (pre-registration, viết TRƯỚC khi chạy):**
- `cu_tru_ben_vung` ON ⇒ `chet_doi` ở nhóm 16–19 tuổi **giảm mạnh** (F-18 là nguyên nhân trực tiếp).
- `di_san.che_do = kin` (vs `tan_ra`) ⇒ Gini tài sản **cao hơn**, tương quan tài sản cha–con **dương
  hơn**.
- Nếu **KHÔNG** thấy dấu dự báo ⇒ cơ chế đó **không** giải thích được kết quả ⇒ **báo kết quả âm**,
  không đi tìm seed đẹp (charter §7, Report_v2 §1).

### G.5 Test matrix — **dùng T-01…T-43 của memo §6 nguyên văn** + 4 test MỚI của ADR này

`docs/reviews/P1-household-demography-design.md` §6 là **hợp đồng test chính thức** (T-01…T-15
residence/provisioning; T-20…T-28 estate; T-30…T-35 metrics; T-40…T-43 replay/regression).
**Không viết lại, không nới, không bỏ.** `test-engineer` viết **độc lập** (không đọc diff của
`engine-surgeon`).

Bốn test **BỔ SUNG** do ADR này thêm (đánh số không đụng memo):

| # | Test | Assert |
|---|---|---|
| **T-16** | `test_khong_co_absorbing_sink_nao` (**E1′**, property, ON, 60 tick tử vong cao) | ∀tick, ∀terminal subject S ∈ bảng khai báo, ∀`ts`: `so_du(S, ts) == 0` **hoặc** S có drain đang BẬT phủ `ts`. Bảng terminal-subject là **dữ liệu trong code**; thêm chủ thể ledger mới mà quên khai báo ⇒ **FAIL** |
| **T-17** | `test_het_han_cong_bi_chan_khi_khong_co_drain` (**§D.6**) | `ho.di_san.het_han: "cong"` + `chinh_tri.bat: false` ⇒ `tao_the_gioi` **raise SystemExit**; không có world nào được tạo, không có sink im lặng |
| **T-18** | `test_no_dinh_ky_khong_thoi_han_cham_dut_co_event` (**§D.3**) | Con nợ có `chuyen_giao_dinh_ky` (`thoi_han=None`) chết ⇒ event `nghia_vu_cham_dut{loai:"dinh_ky_khong_thoi_han"}`; chủ nợ **không** nhận thêm; **không** mint; bảo toàn xanh |
| **T-19** | `test_single_writer_cu_tru` (**§C.2**) | Tĩnh: chỉ `engine/household.py` gán `w.cu_tru`/`w._next_cu_tru`; chỉ `engine/estate.py` gán `w.di_san*`. Vi phạm ⇒ FAIL |

Lệnh gate (không mạng):

```powershell
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m pytest -q --basetemp .tmp\pytest
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m ruff check .
$env:THOC_BLOCK_NETWORK='1'; conda run -n thoc-env python -m tools.verify_local
```

### G.6 Cái gì KHÔNG đổi (chống scope creep)

- Thứ tự bước tick: **không hoán vị** (§D.4). Chỉ **thêm** 9b/9c.
- `Agent` dataclass: **không thêm field nào** (F-22).
- `audit.py:30` (chủ đất phải hoạt động): **KHÔNG NỚI**. Nếu ai đó nới nó để estate giữ đất ⇒
  `adversarial-reviewer` phải chặn (memo §8 Next-handoff 5a).
- `hash_schema`: giữ `"behavioral-state-v2"`.
- Policy Lớp-4 / rulebot / prompt: **không đổi** trong P1 (trừ việc `ho_cua` trả kết quả khác khi
  ON — đó là **dữ kiện**, không phải mớm ý).
- Blueprint mồ côi, `duoi_khoi_ho`, `quy_tac_cap` khác `nhu_cau_deu`, nợ truyền đời, pantry:
  **PENDING, ngoài P1**.

---

## 8. Claim boundary (phải nêu trong mọi report dùng ADR này)

- ADR 0007 chỉ tạo được bằng chứng **`technical-ready` → `mechanism-ready`**: cơ chế đúng, kế toán
  đóng, ablation chạy được. **KHÔNG** tạo `calibrated_fact`, **KHÔNG** `validated_result`.
- Sửa xong P1 **không** làm kết quả cũ đúng lên. `real60_spatial` giữ nhãn
  `diagnostic_only_unreplayable` (ADR 0006 §C.6), **không** được nâng cấp bằng bất kỳ đường nào.
- **Cấm** (mỗi lý do tự nó đã đủ để vô hiệu hóa diễn giải):
  1. *"LLM để dân chết đói"* — SAI: `an_doi` đầu tiên của **159/168** người trẻ trong **mock**
     (PersonaBot, KHÔNG LLM) rơi đúng tick sinh nhật 16. Đây là **engine**.
  2. *"Dân số sụp đổ vì agent không lập được định chế"* — chưa kết luận được: 92.5% thóc + 100% nhà
     nằm trong `VO_THUA_NHAN`, nơi **không policy nào** lấy ra được.
  3. *"Tuổi thọ giảm còn X"* — repo **không có** đại lượng đó (F-23 / INV-M1).
  4. **Bất kỳ** death/birth rate nào tính từ `events.jsonl` của `real60_spatial` (F-21).
  5. *"Thừa kế nổi lên nội sinh"* — SAI theo định nghĩa: nó là `institutional_assumption` do
     scenario đặt vào (§E.2).
- **Được phép nói ngay bây giờ** (tier `mechanism_result`): *"Môi trường như đang cài có một defect
  adult-orphaning độc lập với policy và một absorbing wealth sink; sụp đổ nhân khẩu của run LLM bị
  confound bởi cả hai."*
- Sau khi P1 xanh, mortality chỉ được diễn giải khi có **cả ba**: (a) baseline rulebot/mock cùng
  seed; (b) ablation §G.4; (c) artifact replay được từ transcript (P0.2). **Nếu collapse không sống
  sót qua ablation ⇒ nó là artifact, không phải kết quả.**

---

## §H. Handoff

**`engine-surgeon`** (implement **SAU KHI** ADR này Accepted; **KHÔNG** trước):
- `engine/household.py` (**MỚI**): `CuTru`, `_ho_bat/_cu_tru_bat/_cap_luong_thuc_bat/_tach_ho_bat`
  (khuôn `spatial.py:16-40`), `khoi_tao_cu_tru`, `buoc_cu_tru`, `kiem_tra_cau_hinh`.
- `engine/estate.py` (**MỚI**): `DiSan`, `_di_san_bat`, `buoc_di_san` (bậc 0–5), bảng terminal-subject
  + drain (E1′). **Tái dùng** khuôn `entities.thanh_ly` (`entities.py:218-244`), không phát minh
  đại số nợ mới.
- `engine/world.py:433` `ho_cua` (nhánh ON), `:460` `behavioral_state` (**hai khối có điều kiện**),
  `:619` `nap_checkpoint` (migration), `:833` `tao_the_gioi` (khởi tạo khi ON).
- `engine/economy.py:15` `households` → wrapper mỏng.
- `engine/consumption.py:60-85` provisioning (§B.4) — **giữ nguyên** thứ tự nguồn rút và `ty_le_no`.
- `engine/tick.py:246` chèn 9b/9c; `:271-280` re-key `poverty_streak` theo `rid`.
- `engine/contracts.py:423-425` nhánh gated + fail-loud (§D.4).
- `engine/intents.py` + `minds/capabilities.py` (ADR 0006 §A): action `tach_ho`, `yeu_cau_di_san` —
  **phải** có descriptor đủ bốn chân (CAP-1) và `kha_dung(w)` theo gate; **KHÔNG** được mớm ý (CAP-4).
- `engine/metrics_demography.py` (**MỚI**, §F) + `engine/audit.py:21` nhánh gated E1/E1′.
- **KHÔNG** đụng: `Agent` dataclass, `audit.py:30`, thứ tự bước tick, `hash_schema`,
  `config/world.yaml`, `spatial_v1.yaml`.

**`test-engineer`** (độc lập): T-01…T-43 (memo §6) + T-16…T-19 (§G.5). Không nới assertion, không
skip, không hardcode seed ngoài ba hash pin.

**`reproducibility-steward`** + **`qa-verifier`**: xác minh ba hash pin §0.1 **trước và sau**;
P-1 hash-neutrality; resume ON == run liền mạch; migration checkpoint cũ.

**`adversarial-reviewer`**: soi đúng bốn chỗ dễ gian:
(a) có ai **nới `audit.py:30`** để estate giữ đất không;
(b) có ai đặt key `life_expectancy` từ tuổi người **sống** không (INV-M1);
(c) có ai **đổi tên sink** (estate → `CONG_QUY`/một chủ thể khác) để pass E1 mà vi phạm E1′ không;
(d) có test nào bị **nới** để ba hash pin xanh không.

**`agrarian-economist`** + **`sim-economist`**: pre-register dấu của ablation §G.4 **trước** khi chạy.

**`spec-governor`**: cập nhật conflict map; ADR 0003 đã mang banner "superseded (một phần) §A.1"
tại chỗ (không xóa chữ).
