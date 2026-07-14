# P3 — Autonomy protocol design memo (fact cards, local tools, action-outcome, A2A quote/escrow)

- Ngày: 2026-07-13
- Vai: `agent-autonomy-protocol-designer`
- Verdict: **DESIGN ONLY** — không sửa code production, không chạy LLM/mạng.
- Nguồn quyền lực: `Report_v2.md` §4.5 (1–6), §5 P3, §6 (Market/A2A + Minds/tools);
  `docs/MODEL_CHARTER.md` §3 (Lớp-4 chỉ trả intent, Lớp-5 chỉ đọc), §5 (anti-teleology);
  `docs/adr/0002-behavior-policy-interface.md` §A; `docs/adr/0005-spatial-livelihood-economy.md`
  §9, §11.4.
- Phạm vi đọc (không sửa): `minds/prompts.py`, `minds/schemas.py`, `minds/translate.py`,
  `minds/world_tools.py`, `minds/orchestrator.py`, `minds/real.py`, `minds/transcript.py`,
  `minds/providers_real.py`, `engine/intents.py`, `engine/board.py`, `engine/market.py`,
  `engine/contracts.py`, `engine/production.py`, `engine/pricing.py`, `engine/tick.py`,
  `engine/world.py`, `config/world.yaml`, `tests/test_prompt_ky_luat.py`,
  `tests/test_world_tools.py`.

Memo này là **hợp đồng giao diện**, không phải claim về hành vi LLM. Xem §8 (Claim boundary).

---

## 0. Tóm tắt phán quyết (đọc 60 giây)

| Hạng mục Report_v2 | Trạng thái thật trong code | Kết luận |
|---|---|---|
| §4.5.1 capability catalog | Chưa có; menu `MUC_HANH_DONG` hard-code, `khai_hoang` được quảng cáo (prompts.py:128) nhưng KHÔNG có mục JSON; `mac_ca` có ở engine (board.py:147) + translate (translate.py:245) nhưng KHÔNG có trong menu (prompts.py:180); `dong_thuyen`/`rao_do`/`qua_song` có ở `KeHoach` (intents.py:50-52) nhưng KHÔNG có trong `LOAI_HANH_DONG` | P0.1 sở hữu; P3 phụ thuộc |
| §4.5.2 fact cards | Có mầm (ước giá riêng prompts.py:526-530, hàng xóm nhiễu 606-629, rao vặt cùng làng 630-643) nhưng **boundary bị thủng ở 5 chỗ** (§2.2) | SỬA + MỞ RỘNG |
| §4.5.3 opportunity card | **KHÔNG tồn tại** | NEW |
| §4.5.4 bounded local tools | 7 tool read-only đã có (world_tools.py:192-200); **không authorization, không quota lượt-gọi, không transcript, error không mã** | SỬA + 5 tool NEW |
| §4.5.5 action outcome | `a.su_co` ĐÃ TỒN TẠI (types.py:59, production.py:103-107, prompts.py:651) — **có mầm nhưng THIẾU** (§5.1: free text, không mã, không phủ market/board/translate, chỉ ghi thất bại) | THAY bằng `KetQua` |
| §4.5.6 A2A quote/escrow/settlement | `bang_rao` + `HopDong` phủ ~60% (thread id, parties, counteroffer, accept/reject, settlement **nguyên tử đúng-một-lần** board.py:51-90). **`reserve`/`escrow` = ZERO** (grep `reserve\|escrow\|khoa\|giu_cho\|ky_quy\|dat_coc` trên `engine/` chỉ ra false-positive `dieu_khoan`/`khoai`/`khoảng`) | escrow/expiry-per-thread/declared-economics/cancel là **NEW THẬT** |

**Ba blocking finding không nằm trong Report_v2 nhưng chặn P3:**

1. **B1 — Mock KHÔNG đọc prompt.** `orchestrator.py:274-275`: mode mock dựng prompt giả
   `f"[mock 1-to-1] id={aid} tick={w.tick}"`, PersonaBot quyết từ `ctx`. `MockProvider` không có
   `goi_agentic` (gateway.py:76-86) và `dung_cong_cu` yêu cầu `not self._tuan_tu`
   (orchestrator.py:280-282) ⇒ **mock chưa bao giờ chạy vòng công cụ, chưa bao giờ đọc fact card**.
   Report_v2 P3.5 ("benchmark LLM interface only with mock/FakeTransport fixtures") **không thể
   thực hiện** với MindMock hiện tại. Cần `ScriptedPromptBot` (§7.0).
2. **B2 — Transcript replay MÙ với tool layer.** `transcript.py:20-26` tự khai: vòng công cụ ghi
   **1 entry/agent** (prompt khởi đầu + quyết định cuối); `TranscriptProvider.goi_agentic`
   (transcript.py:134-136) trả thẳng quyết định theo `prompt_hash`. ⇒ Nếu ai đó sửa
   `minds/world_tools.py`, replay **vẫn ra đúng world-hash** và gate `--verify` vẫn XANH, dù
   information set của agent đã khác. Cổng tái lập hiện KHÔNG phủ information set.
3. **B3 — Nhãn giai cấp quay ngược vào prompt.** `GIAI_CAP_VN` (prompts.py:362-375) +
   `_cau_can_tinh` (prompts.py:384-397) render "Bạn là **địa chủ** 34 tuổi", nguồn là
   `w.phan_loai` do observatory nạp (`tick.py:320-322`). Report_v2 P3 acceptance đòi
   "select at least two distinct feasible livelihood paths ... **without any job label being
   assigned**". Charter §3 (dòng 69-71): "Nhãn KHÔNG được quay lại điều khiển engine". Prompt là
   input của Lớp-4 ⇒ đây là kênh Lớp-5 → Lớp-4. **Phải gate off cho `spatial_livelihood_v2`**,
   giữ như một treatment arm có ablation.

---

## 1. Runtime prompt ngắn gọn (Report_v2 §5 P3.1)

### 1.1 Nguyên tắc (3 dòng, không hơn)

Khối `[NGUYÊN TẮC]` thay toàn bộ `LUAT_VAT_LY` mớm động cơ + `VI_DU_QUYET_DINH`:

```text
[NGUYÊN TẮC]
Bạn còn sống thì bạn tự quyết. Không ai chấm điểm bạn.
Giữ cho mình còn lựa chọn ở kỳ sau.
Chọn MỘT hoặc NHIỀU hành động khả thi trong danh mục dưới, hoặc không làm gì.
```

Không có câu nào nói lựa chọn nào tốt hơn. Không có thứ tự nhu cầu. Không có ví dụ chiến lược.

### 1.2 Câu "được phép" — sinh TỪ CATALOG, không viết tay

Report_v2 P3.1 đòi nói rõ agent được phép: không làm gì, hợp tác, trao đổi, cho/đi thuê, làm thuê,
canh tác, đánh cá, đốn gỗ, chở đò, xây, chăm trẻ, thăm dò — **CHỈ KHI ràng buộc hiển thị cho phép**.

Cách cài đúng: câu này **không được hard-code**. Nó là `render()` của catalog P0.1, lọc theo
`availability_predicate(w, aid)`:

```text
[BẠN CÓ THỂ LÚC NÀY] không làm gì · canh tác (2 thửa đủ điều kiện) · đốn gỗ · đánh cá ·
chăm trẻ (1 trẻ trong hộ) · đề nghị/trả lời giao kèo · đặt lệnh chợ · đăng/nhận báo giá ·
nhắn tin. (Các việc khác không hiện vì ràng buộc hiện tại không cho phép — xem [CƠ HỘI].)
```

INVARIANT **P3-I1 (parity)**: một hành động chỉ được hiện trong câu này khi có ĐỦ
`schema → translate → engine handler → outcome codes`; và mọi engine handler public phải hoặc ở
trong catalog, hoặc nằm trong danh sách `AN_HANH_DONG` khai báo lý do. Test ở §7.1.
(Hôm nay điều này SAI: prompts.py:128 quảng cáo `khai_hoang` nhưng `MUC_HANH_DONG` không có mục
JSON nào cho nó; `MUC_HANH_DONG` cũng thiếu `buon_chuyen`, `bao_huy`, `khai_hoang`.)

### 1.3 Cấm tuyệt đối (điều kiện gate)

1. Không nói lựa chọn nào tối đa hóa welfare / lợi hơn / đáng làm.
2. Không gợi ý phát minh, tiền tệ, chính phủ, ngân hàng, công ty là đáng mong muốn hay sẽ xuất hiện.
3. Không xếp hạng nghề, không gán nhãn nghề/giai cấp cho agent.
4. Không mô tả cơ chế **đang TẮT** trong scenario (nói dối về vật lý).
5. Không kể "bạn đã làm X" khi X mới chỉ là intent (§5.3).

### 1.4 Checklist từ cấm — mở rộng `tests/test_prompt_ky_luat.py:22`

Hiện tại: `TU_MOM = ("nên ", "hãy", "khôn ngoan", "đáng")`.

**Cảnh báo về blacklist chuỗi con** (phải ghi vào test, nếu không sẽ có false positive và người ta
sẽ nới test): `"tối đa"` KHÔNG được cấm — nó là **dữ kiện trần cứng** ("Tự canh tối đa 3 thửa",
prompts.py:246; "≤200 chữ", prompts.py:163). Chỉ cấm dạng chuẩn tắc hóa.

```python
# nhóm A — mớm ưu tiên / chuẩn tắc (áp cho scaffolding engine-authored)
TU_MOM = (
    "nên ", "hãy", "khôn ngoan", "đáng",                      # đã có
    "tối đa hóa", "tối ưu", "hiệu quả nhất", "tốt nhất",      # NEW
    "ưu tiên", "có lợi", "lợi nhất", "lãi hơn", "tốt hơn",
    "hơn hẳn", "cần phải", "phải lo", "khuyên", "lời khuyên",
)
# nhóm B — teleology (định chế/đường phát triển là đích)
TU_TELEO = (
    "làm giàu", "thịnh vượng", "phát triển kinh tế", "tiến bộ", "văn minh",
    "phát minh ra tiền", "nên phát minh", "cần một chính phủ", "cần nhà nước",
    "tất yếu", "quy luật lịch sử",
)
# nhóm C — gán nhãn nghề/giai cấp (kể cả gián tiếp qua GIAI_CAP_VN)
TU_NHAN_NGHE = tuple(GIAI_CAP_VN.values()) + (
    "nghề của bạn", "bạn là nông dân", "bạn là lái đò", "bạn là thợ", "nghề tốt",
)
# nhóm D — liệt kê động cơ (khối [BẠN LÀ NGƯỜI SỐNG] hiện tại)
TU_DONG_CO = ("nhu cầu như mọi con người", "vị thế", "tiếng thơm", "an toàn ngày mai")
```

**Ba assertion cấu trúc mà blacklist từ không bắt được** (bắt buộc, §7.1):

- `test_prompt_khong_co_vi_du_chien_luoc`: khối định dạng không được chứa hành động domain nào
  ngoài `"hanh_dong":[]`; cấm xuất hiện `chia_san_luong`, `ty_le`, `cau_hon` trong ví dụ.
- `test_co_hoi_khong_xep_hang`: mọi opportunity card dict không có key trong
  `{"ev","gia_tri_ky_vong","loi_nhuan","xep_hang","diem","score","rank","tot_nhat"}`; và thứ tự card
  KHÁC nhau giữa ≥2 cặp (aid, tick).
- `test_prompt_khong_mo_ta_co_che_dang_tat`: `chinh_tri.bat=false` ⇒ prompt không chứa "trưởng làng",
  "công quỹ", "gini", "sung công", "nghiệp đoàn", "đình công".

**Ranh giới áp dụng checklist (quan trọng — nếu bỏ qua, test sẽ tự vỡ):** blacklist áp cho
**scaffolding do engine viết** (nguyên tắc, luật vật lý render từ config, fact card, opportunity
card, mô tả tool, catalog, khối định dạng). KHÔNG áp cho **văn bản do agent tự viết** đang được
quote lại: `hoi_ky`, `gia_huan`, `niem_tin`, `du_dinh`, nội dung `nhan_tin`, `ky_uc`. Lý do: LLM có
thể viết "đáng tin" vào `a.niem_tin` (real.py:295 chính là prompt yêu cầu "ai **đáng** tin, ai
**phải** đề phòng") rồi nó tái nhập prompt ở prompts.py:538-539 ⇒ gate sẽ đỏ vì chính output của
agent. Kiểm duyệt lời agent còn tệ hơn. Do đó renderer phải **tách được** `scaffolding_only(w, aid)`
để test băm/soi riêng, và các khối agent-authored nằm trong delimiter rõ ràng.

Hệ quả: `test_prompt_ky_luat` hiện chỉ render fixture với `niem_tin/hoi_ky` rỗng ⇒ **gate đang
xanh giả**. Test mới phải render fixture có `niem_tin` bẩn để chứng minh việc tách khối hoạt động.

### 1.5 Chỗ mớm/stale CỤ THỂ trong `minds/prompts.py` và phải cắt gì

| file:line | Nội dung | Phán quyết |
|---|---|---|
| 241-296 `LUAT_VAT_LY` | Hard-code `1 tick = 6 tháng`, `90kg`, `180 công`, `60kg giống`, `~650kg`, `nhà = 8 gỗ + 240 công`, `~4.5 công/kg cá`, mùa lẻ/chẵn | **STALE** với overlay spatial (4 tháng/60kg/120 công, `lua_1→lua_2→dong`) — Report_v2:76. Thay bằng renderer từ `w.cfg` (P0.1). Không phải việc của P3 nhưng P3 **không được nghiệm thu** khi nó còn |
| **293-296** `[BẠN LÀ NGƯỜI SỐNG]` | "Bạn có nhu cầu như mọi con người: no bụng hôm nay; an toàn ngày mai (dự trữ, nhà cửa); gia đình…; và **vị thế** (đất đai, của cải, chữ nghĩa, **tiếng thơm**)" | **MỚM ĐỘNG CƠ — CẮT.** Đây KHÔNG phải fact: nó là một **thang nhu cầu có thứ tự** (sinh tồn → an toàn → gia đình → địa vị) và nó **xếp hạng tài sản thành hàng địa vị**. Vật lý đã nói đói thì chết; nói thêm "bạn muốn gì" là viết hộ hàm mục tiêu. Nó lọt lưới `TU_MOM` vì không chứa token cấm ⇒ chính là ví dụ vì sao cần nhóm D |
| **298-304** `VI_DU_QUYET_DINH` | Ví dụ "quyết định" đầy đủ: canh 2 thửa + cho **cấy rẽ 40%** (`chia_san_luong 0.4`) + **cầu hôn**, kèm lý do biện minh: "Canh 2 thửa đủ ăn, thửa xa cho cấy rẽ lấy 4 phần, và đến tuổi phải tính chuyện gia đình." | **MỚM CHIẾN LƯỢC — CẮT.** Đây là one-shot priming một chiến lược địa-tô + hôn nhân, kèm justification. Khối prescriptive mạnh nhất trong prompt và cũng lọt lưới `TU_MOM`. Thay bằng ví dụ **chỉ về định dạng**, hành động rỗng |
| 13-25 `MAU_KHOI_DAU_THEO_TEN` | 2 mô-típ mồi, trong đó `cho_muon_co_hoan_tra` = **template tín dụng** | Mồi định chế. Docstring đã thừa nhận là điều kiện phản chứng C1. `spatial_livelihood_v2` đặt `hop_dong.mau_khoi_dau: []`; arm có mồi là **treatment riêng có nhãn** (charter §4 đk 4) |
| 65-68 `mo_ta_the_gioi` | "**Mọi trao đổi tính bằng thóc**; ai thất hứa sẽ bị cả làng nhớ mặt." | (a) SAI SỰ THẬT: `Lenh.thanh_toan` cho phép mọi tài sản (market.py:5, market.py:24) ⇒ câu này mồi thóc-là-tiền. (b) "cả làng nhớ mặt" là câu cảnh cáo; cơ chế thật là `w.quan_he` giảm. **Viết lại thuần dữ kiện**: "Tài sản thanh toán mặc định là thóc; lệnh/giao kèo có thể ghi tài sản thanh toán khác. Vi phạm giao kèo làm giảm quan hệ với các bên liên quan." |
| 55-68 `mo_ta_the_gioi` (thân) | `dan`, `so_hd`, `cac_tai_san()` đều tính **TOÀN THẾ GIỚI** | Thủng boundary (§2.2 L1) trong khi dòng 77 và 313-314 tuyên bố "chỉ biết những gì làng bạn biết" |
| 86-89 | `gia = {ts: w.gia_gan_nhat(ts) for ts in ("go","cong_cu","dat")}` | Hard-code 3 mặt hàng; thiếu `ngo/khoai/ga/thit/ca/thuyen` (Report_v2:82). `gia_gan_nhat` là **lịch sử giá TOÀN CỤC** (world.py:328-336) ⇒ thủng boundary |
| 100 | `dat_cong_con` đếm **mọi** thửa ruộng vô chủ toàn thế giới | Thủng boundary |
| 125-131 `[BẠN CÓ THỂ]` | Danh sách hành động **thứ tự cố định**, viết tay | Mâu thuẫn với chính cơ chế chống thiên vị vị trí ở 320-321 (menu được XÁO). Xóa; sinh từ catalog (§1.2) |
| 180 | `tra_loi_hop_dong` chỉ quảng cáo `"chap_nhan"|"tu_choi"` | **`mac_ca` là năng lực đã có** (translate.py:245-248 → board.py:147-150, trần `hop_dong.mac_ca_toi_da_vong`) nhưng **vô hình với LLM** ⇒ vòng mặc cả A2A coi như chết. Thêm `"mac_ca"` + `sua_doi` vào mục |
| 285-291 (trong `LUAT_VAT_LY`) | Mô tả trọn bộ máy chính trị: bầu trưởng làng, thuế → công quỹ chia đều, **"khi hệ số Gini vượt ngưỡng VÀ đủ đông người bạo động → sung công nhà giàu chia lại"**, nghiệp đoàn, đình công | Render **vô điều kiện**. Trong `agrarian_transition_v1` chính trị **mặc định TẮT** (charter §6, dòng 125-126) ⇒ prompt **nói dối** về một cơ chế không tồn tại; và khi BẬT thì nó tiết lộ **ngưỡng kích hoạt** như một đòn bẩy. Gate theo `chinh_tri.bat`; giữ mô tả thuần cơ chế, không nêu ngưỡng số |
| 362-397 `GIAI_CAP_VN` / `_cau_can_tinh` | "Bạn là **địa chủ** / **thương nhân** / **tá điền** …" | **B3.** Gate off ở v2 (`prompt.nhan_giai_cap: false`), giữ arm ablation |
| 96-99 | Mô tả mật độ cá từ `w.ca_ton` (pool **toàn cục**) | Khi có 2 bờ/nhiều làng, đây phải là stock **cục bộ** (P2). P3 chỉ yêu cầu: field phải mang `nguon` (§2.3) |

Giữ nguyên (đúng nguyên tắc, dùng làm precedent): xáo menu theo `w.rng.get(f"menu_xao:{aid}", w.tick)`
(320-321); "ƯỚC GIÁ RIÊNG (kinh nghiệm của bạn, **không phải giá bắt buộc**)" (526-530); nhiễu hàng
xóm ±30% seeded (606-629); rao vặt cùng làng + nhiễu (630-643).

---

## 2. Fact cards + information boundary (Report_v2 §4.5.2)

### 2.1 Nội dung fact card (mỗi agent CHỈ thấy)

| Card | Nguồn | Ràng buộc |
|---|---|---|
| `TAI_SAN_CHUYEN_DUOC` | `ledger.tai_san_cua(aid)` trừ `vi_the:*`, trừ `KY_QUY:*` | + dòng **"đang khóa trong báo giá: {asset: qty}"** (§6) — nếu không hiện, agent sẽ tưởng mình còn hàng |
| `KHO_HO` | `w.ho_cua(aid)` + `household_food_equivalent` | Đơn vị hộ theo P1; **không** cộng escrow |
| `GIAO_DICH_DIA_PHUONG` | `w.gia_lich_su[ts]` lọc theo sổ lệnh mà agent quan sát được | kèm `n_quan_sat`, `coverage`, `tick_gan_nhat` |
| `SO_BAO_GIA` (bid/ask/depth) | **`w.bao_gia`** (§6) — quote book | **Đây là nơi DUY NHẤT bid/ask/depth tồn tại thật** (xem 2.4) |
| `CHI_PHI_DI_LAI` | `spatial`: phí đò đang rao, có thuyền không, đã qua bờ chưa | `null` khi `khong_gian.bat=false` |
| `UOC_GIA_RIENG` | `a.gia_ky_vong` + độ bất định | Đã có (prompts.py:526-530); **không bao giờ trộn với market evidence thành một số** |
| `CO_HOI` | §3 | |
| `KET_QUA` | §5 | |

### 2.2 Boundary hiện tại — xác minh và 5 chỗ thủng

Tuyên bố hiện hành: prompts.py:77 "Bạn chỉ biết những gì làng bạn biết"; prompts.py:313-314 "KHÔNG
biết ví tiền hay ý định của người khác".

**Đúng như tuyên bố:**
- bảng rao: chỉ đề nghị **cùng làng** hoặc đích danh (prompts.py:436-447);
- hàng xóm: `w.hang_xom_cua` theo bán kính + **nhiễu ±30% seeded** (prompts.py:606-629);
- rao vặt: **cùng làng** + nhiễu `thuong_mai.nhieu_tin_don_gia` (prompts.py:630-643);
- ứng viên hôn nhân: `b.lang == a.lang` (prompts.py:484-492).

**Thủng (5):**
- **L1** `mo_ta_the_gioi` (prompts.py:55-68): dân số, số hợp đồng hiệu lực, danh mục tài sản — **toàn thế giới**.
- **L2** giá chợ (prompts.py:86-87 + world.py:328-336): `gia_lich_su` **không có khóa làng/bờ** ⇒ agent làng 0 thấy giá khớp ở làng 2.
- **L3** `_gia_cho` tool (world_tools.py:91-93): cùng lỗi L2, không auth.
- **L4** `_nghe_ve` tool (world_tools.py:119-136): nghe ngóng **bất kỳ agent nào trên đời**, không kiểm hàng xóm/cùng làng — trong khi prompt bảo chỉ biết hàng xóm.
- **L5** `_get_phan_bo_cua_cai` tool (world_tools.py:152-189): trả **p10/p50/p90 + Gini + số hộ thiếu ăn của TOÀN BỘ agent còn sống** cho **bất kỳ ai gọi**. Docstring nói "để Trưởng làng RAG lập pháp" nhưng `thuc_thi` (world_tools.py:203-211) **không kiểm chức vụ**.
- **L6 (behavior, ngoài prompt)** `pricing.cap_nhat_gia_ky_vong` (pricing.py:88-104): **mọi agent còn sống** cập nhật prior từ **mọi giá khớp** trong tick, bất kể làng/bờ ⇒ kênh thông tin toàn cục ngầm đi thẳng vào hành vi (và `gia_ky_vong` nằm trong `Agent` ⇒ trong world_hash).

### 2.3 Boundary chốt cho `spatial_livelihood_v2` (5 tier + provenance tag)

Mọi field trong fact card/tool output mang `nguon ∈ {cong_khai, lang:<i>, hang_xom, song_phuong, chuc_vu}`.

| Tier | Được biết | Ví dụ |
|---|---|---|
| T0 `cong_khai` | Mùa, thời tiết, hệ số; luật vật lý đang áp dụng; trạng thái của chính mình | `w.thoi_tiet`, `w.mua()` |
| T1 `lang:<i>` | Dân số làng mình; sổ giá **của chợ làng mình** (và chợ làng khác **chỉ khi tới được**, `market._toi_duoc_cho` market.py:146-160); bảng rao công khai trong làng; **quote book công khai trong làng/bờ**; tin đồn (nhiễu) | |
| T2 `hang_xom` | Ước lượng mờ tài sản hàng xóm trong `quan_he.ban_kinh_lang_gieng`; thửa/tài nguyên gần | nhiễu giữ nguyên |
| T3 `song_phuong` | Tin nhắn gửi mình; báo giá/đề nghị đích danh; hợp đồng mình là một bên; quan hệ của chính mình | |
| T4 `chuc_vu` | Phân bố của cải — **chỉ trưởng làng đương nhiệm**, **chỉ trong phạm vi làng mình quản**, **chỉ khi `chinh_tri.bat`** | sửa L5 |
| — | **KHÔNG BAO GIỜ**: số dư chính xác của người khác, ý định của người khác, prior riêng của người khác, sổ lệnh của chợ mình không tới được | |

Sửa L1/L2 ⇒ đổi world state (khóa `gia_lich_su` theo làng) ⇒ **đổi world_hash** ⇒ phải version hóa
qua scenario gate (ADR 0005 §11.4, dòng 361-366): giữ nguyên đường legacy, chỉ đổi khi
`thuong_mai.gia_theo_lang: true` (mặc định OFF ở legacy, ON ở v2).
Sửa L6 tương tự: `hanh_vi.gia_ky_vong.hoc_theo_lang: true` (OFF ở legacy).

### 2.4 Ba INVARIANT của fact card

- **P3-I2 (evidence ≠ giá đúng):** mọi field giá đi kèm `n_quan_sat` + `coverage` +
  `tick_gan_nhat`. `n_quan_sat == 0` ⇒ field là `null` và card nói "chưa có phiên khớp nào" —
  **KHÔNG được rơi về prior**. `pricing.gia_ky_vong()` (pricing.py:58-77) **có** fallback sang prior
  (dòng 68) — hàm đó hợp lệ cho **policy limit price**, nhưng **cấm** dùng để render fact card.
- **P3-I3 (private prior ≠ settlement price):** `a.gia_ky_vong` chỉ hiện dưới nhãn "ƯỚC GIÁ RIÊNG…
  không phải giá bắt buộc" (đã đúng, prompts.py:526-530) và **không bao giờ** được gộp với market
  evidence thành một con số duy nhất.
- **P3-I4 (không có bid/ask từ call auction):** `phien_cho` là **call auction sealed** — sổ lệnh chỉ
  tồn tại **bên trong** tick, dựng từ `lenh_tick` rồi khớp và biến mất (market.py:163-186). Agent
  **không thể** quan sát bid/ask/depth của phiên chưa xảy ra. Do đó fact card chỉ được nêu:
  (a) giá khớp gần nhất + khối lượng + coverage (post-trade), và
  (b) **bid/ask/depth của quote book** (§6) — nơi lệnh **treo qua tick** và **có escrow bảo chứng**.
  Bịa ra một "bid/ask" cho call auction sẽ là engine tự phát tín hiệu giá ⇒ vi phạm CLAUDE.md §2(7).

---

## 3. Opportunity card (Report_v2 §4.5.3)

### 3.1 Schema (pydantic v2, `minds/cards.py` — NEW, thuần đọc)

```python
class CoHoi(BaseModel):
    ma: str                       # "canh:lua" | "canh:ngo" | "canh:khoai" | "khai_go" |
                                  # "danh_ca" | "bat_ga" | "nuoi_ga" | "khai_hoang" |
                                  # "dong_thuyen" | "cho_do" | "qua_song" | "xay:nha" |
                                  # "cham_tre" | "gop_cong" | "cho_thue_dat" | "thue_dat"
    doi_tuong: str | None         # parcel id / child id / thread id nếu cơ hội gắn với một đối tượng
    labor_can: float              # công
    input_can: dict[str, float]   # {"thoc": 60, "go": 8}
    output_ky_vong: dict[str, float]        # ĐƠN VỊ VẬT LÝ (kg thóc, kg cá, con gà...)
    output_khoang: tuple[float, float] | None   # (p10, p90) khi vật lý ngẫu nhiên — độ bất định
    food_equivalent: float        # quy đổi dinh dưỡng công bố ở config (nhu_cau.quy_doi)
    ton_kho_reserve: dict[str, float]       # phải chừa lại (giống, thóc nuôi gà) — KHÔNG bị tiêu
    time_to_completion: int       # tick (1 = xong trong tick; N = project nhiều tick)
    resource_impact: dict[str, float] | None  # {"ca_ton": -12.0, "canopy": -0.02}
    chi_phi_di_lai: dict | None   # {"phi_do": 5.0, "tai_san": "thoc"} nếu phải qua sông
    market_evidence: MarketEvidence | None    # xem dưới
    feasible: bool
    thieu: list[str]              # reason codes khi không feasible / gần feasible
    nguon: str                    # provenance tag (§2.3)

class MarketEvidence(BaseModel):
    gia_khop_gan_nhat: float | None
    tick_gan_nhat: int | None
    n_quan_sat: int               # số phiên có khớp trong cửa sổ thuong_mai.cua_so_gia_tick
    coverage: float               # n_quan_sat / cửa_sổ  ∈ [0,1]
    bid: float | None             # từ QUOTE BOOK (§6), không phải call auction
    ask: float | None
    depth: float | None
    nguon: str
```

**Cấm tuyệt đối trong schema** (test §7.3): không có `ev`, `gia_tri_ky_vong`, `loi_nhuan`, `xep_hang`,
`diem`, `score`, `rank`, `tot_nhat`. Card **không** cộng labor + input + risk thành một scalar.

### 3.2 Điều kiện hiển thị

- `feasible = True` ⇒ hiện.
- `gan_feasible` ⇒ hiện, kèm `thieu`. Định nghĩa **cơ học, không phải phán đoán**: mọi thứ thiếu đều
  có thể lấy được **trong tick này bằng một hành động đang hiển thị khác** (ví dụ thiếu 8 gỗ nhưng có
  ask gỗ trong quote book và đủ thóc để mua). Ngưỡng ở `minds.co_hoi.gan_feasible_nguong`.
- Không feasible và không gần feasible ⇒ **ẩn** (giữ prompt ngắn), nhưng vẫn hỏi được qua tool
  `xem_co_hoi_san_xuat(ma=...)` → trả card với `feasible:false` + `thieu`. Ẩn ≠ giấu.

### 3.3 Không xếp hạng — cơ chế đảm bảo (CHỐT)

**Chọn: XÁO theo seed × agent × tick**, tái dùng đúng precedent `MUC_HANH_DONG` (prompts.py:320-321):

```python
g = w.rng.get(f"co_hoi_xao:{aid}", w.tick)
cards = [cards[i] for i in g.permutation(len(cards))]
```

Lý do **không** chọn "sort theo id/ma": sort ổn định tạo **thiên vị vị trí bền vững** — `canh:lua`
đứng đầu ở **mọi** agent, **mọi** tick trong suốt 600 tick; LLM có position bias mạnh ⇒ đó chính là
"mớm nghề" bằng thứ tự. Xáo seeded vẫn tất định (replay được), vẫn vào transcript, mà phá bias.

Test §7.3: với 2 crop có vật lý **giống hệt nhau**, thứ tự xuất hiện phải khác nhau ở ≥1 cặp
(aid, tick) trong fixture; và tần suất "đứng đầu" của mỗi card không lệch quá `tol` trên N=200 lượt.

### 3.4 "Card nói sự thật" nghĩa là gì

`output_ky_vong` phải là **kỳ vọng vật lý dưới trạng thái hiện tại** (màu mỡ thửa `p.mau_mo`, tay
nghề `a.tay_nghe`, hệ số thời tiết `w.thoi_tiet`, mật độ cá `ca_ton/K` ⇒ CPUE), tính bằng **cùng
công thức mà engine sẽ dùng khi thực thi** — không phải một bảng riêng. Nếu công thức card và công
thức production lệch nhau, agent bị lừa. INVARIANT **P3-I5**: card gọi đúng hàm dự báo mà
`engine/production.py` dùng (refactor: tách `du_bao_san_luong(w, aid, pid, cay)` thuần đọc, gọi từ
cả hai). Test: `card.output_ky_vong` == sản lượng thực tế khi thời tiết = kỳ vọng (± hệ số ngẫu nhiên).

---

## 4. Bounded deterministic local tools (Report_v2 §4.5.4)

### 4.1 Hiện trạng (`minds/world_tools.py`)

7 tool (world_tools.py:192-200): `xem_thoi_tiet`, `gia_cho`, `tai_san_cua_toi`, `dat_cong_gan`,
`uy_tin_voi`, `nghe_ve`, `get_phan_bo_cua_cai`.

| Vấn đề | Bằng chứng |
|---|---|
| **Không authorization** | `thuc_thi` (world_tools.py:203-211) chỉ tra dict tên hàm rồi gọi. `nghe_ve` nhận id bất kỳ (L4); `get_phan_bo_cua_cai` không kiểm chức vụ (L5) |
| **Quota sai đơn vị** | `minds.cong_cu_max_luot: 10` (config/world.yaml:271) là trần **LƯỢT MODEL** (`for luot in range(max_luot + 1)`, providers_real.py:115), KHÔNG phải trần **số lần gọi tool**. Một lượt có thể chứa **nhiều** `functionCall` (providers_real.py:147, thực thi hết ở 154-161) ⇒ số lần chạm world **không có trần**. Không có quota per-tool |
| **Không transcript** | transcript.py:20-26 (tự khai): vòng công cụ ghi **1 entry/agent** = prompt khởi đầu + quyết định cuối. Các lượt tool trung gian **không có vết** ⇒ B2 |
| **Error không mã** | `{"loi": "không có công cụ tên 'x'"}` (world_tools.py:206) — free text, không parse được, không phân biệt được `E_QUOTA` vs `E_NOT_AUTHORIZED` |
| **Telemetry lẫn lộn** | `self.so_luot_cong_cu += max(0, resp.retries)` (orchestrator.py:103): `retries` là **số lần retry JSON** ở đường không-tool và **số lượt tool** ở đường agentic ⇒ metric trộn hai thứ |
| **Mock không chạy tool** | B1 — `dung_cong_cu` đòi `not self._tuan_tu` (orchestrator.py:280-282) mà mock là `_tuan_tu=True` (orchestrator.py:68); `MockProvider` không có `goi_agentic` (gateway.py:76-86). Vòng tool **chỉ** được test qua `httpx.MockTransport` ở tests/test_world_tools.py:82-103 |

### 4.2 Catalog chốt (5 NEW + 3 GIỮ + 1 SỬA + 1 GATE + 2 BỎ)

Mọi tool: **read-only**, có JSON Schema, có authorization, có quota, có transcript, **không network/MCP từ xa**.

| Tool | Inputs | Authorization | Output (tóm tắt) | Error codes | Quota/tick | Trạng thái |
|---|---|---|---|---|---|---|
| `xem_thi_truong_local` | `tai_san?`, `lang?` | Mặc định làng mình. Làng khác **chỉ khi** `market._toi_duoc_cho(w, aid, lang)` (market.py:146-160) | Mỗi sổ: giá khớp gần nhất, tick, khối lượng, `n_quan_sat`, `coverage`; bid/ask/depth **từ quote book**; `nguon` | `E_UNKNOWN_ASSET`, `E_NOT_REACHABLE` | 2 | **NEW** (thay `gia_cho`) |
| `xem_co_hoi_san_xuat` | `ma?` | self | `list[CoHoi]` đã xáo (§3.3) | `E_UNKNOWN_OPTION` | 1 | **NEW** |
| `xem_du_an` | `du_an_id?` | Dự án mình sở hữu / mình đang góp công / work-order công khai trong làng | recipe, vật liệu đã escrow, công đã góp theo người/tick, deadline, state | `E_NOT_FOUND`, `E_NOT_AUTHORIZED` | 2 | **NEW** (phụ thuộc P1 project primitive) |
| `xem_bao_gia` | `tai_san?`, `chieu?` | Báo giá đích danh mình + báo giá công khai trong làng/bờ mình | list thread: `id, chieu, tai_san, sl_con_lai, don_gia, thanh_toan, het_han_tick, trang_thai, doi_tac` | `E_UNKNOWN_ASSET` | 2 | **NEW** |
| `xem_tai_nguyen_gan_day` | `ban_kinh?` | Trong `quan_he.ban_kinh_lang_gieng`, **cùng bờ** trừ khi đã qua sông | Thửa (id, loai, chu?, mau_mo, `reachable`, `bo`); mật độ cá (band + stock/K); gà rừng stock/K; biomass rừng | — | 2 | **NEW** (gộp `dat_cong_gan`) |
| `tai_san_cua_toi` | — | self | + **`dang_khoa_bao_gia`** (escrow) | — | 1 | GIỮ (bổ sung field) |
| `xem_thoi_tiet` | — | công khai | mùa/thời tiết/hệ số | — | 1 | GIỮ |
| `uy_tin_voi` | `nguoi` | self ↔ target | trọng số quan hệ | `E_UNKNOWN_AGENT` | 3 | GIỮ |
| `nghe_ve` | `nguoi` | **PHẢI là hàng xóm (`w.hang_xom_cua`) hoặc cùng làng** | ước lượng mờ (giữ nguyên nhiễu seeded) | `E_NOT_AUTHORIZED` | 3 | **SỬA** (L4) |
| `get_phan_bo_cua_cai` | — | **CHỈ trưởng làng đương nhiệm** (`w.chinh_quyen.truong_lang == aid`), **chỉ phạm vi làng quản**, **chỉ khi `chinh_tri.bat`** | như cũ | `E_NOT_AUTHORIZED` | 1 | **GATE** (L5) |
| `gia_cho` | | | | | | **BỎ** → `xem_thi_truong_local` (rò giá toàn cục, L3) |
| `dat_cong_gan` | | | | | | **BỎ** → gộp vào `xem_tai_nguyen_gan_day` (thiếu cờ `reachable`) |

Trần tổng: `minds.cong_cu.quota_tong_moi_agent_tick: 12` (số **lần gọi tool**), song song với trần
lượt model `cong_cu_max_luot: 10`. Vượt ⇒ trả `E_QUOTA` như một **kết quả tool bình thường** (không
raise) để model vẫn ra được quyết định.

### 4.3 Envelope kết quả (single source)

```json
{"cong_cu":"xem_bao_gia","tick":12,"aid":"A0007","luot":3,
 "ok":true,"du_lieu":{...},"ma_loi":null,"loi":null,"nguon":"lang:1"}
```
Lỗi ⇒ `{"ok":false,"du_lieu":null,"ma_loi":"E_NOT_AUTHORIZED","loi":"..."}`.
Mã lỗi: `E_UNKNOWN_TOOL`, `E_BAD_ARGS`, `E_UNKNOWN_ASSET`, `E_UNKNOWN_AGENT`, `E_UNKNOWN_OPTION`,
`E_NOT_FOUND`, `E_NOT_AUTHORIZED`, `E_NOT_REACHABLE`, `E_QUOTA`, `E_TOOL_ERROR`.

### 4.4 Transcript đầy đủ (vá B2)

Thêm loại record vào `transcript.jsonl`:

```json
{"kind":"tool_turn","call_id":n,"tick":12,"aid":"A0007","luot":2,
 "cong_cu":"xem_bao_gia","args":{"tai_san":"go"},"args_hash":"…",
 "ket_qua":{...},"ket_qua_hash":"…","ma_loi":null,"tool_catalog_hash":"…"}
```
Record quyết định hiện có được gắn `"kind":"decision"`, `"so_luot_tool":k`, `"tool_catalog_hash"`.

`tools.replay --from-transcript --verify` phải **thêm 2 assertion**:
1. Mỗi `tool_turn` khi **chạy lại** trên world đang replay tại đúng `(tick, aid)` phải cho
   `ket_qua_hash` **giống hệt**. Đây là thứ biến câu "cùng prompt + cùng tool transcript ⇒ cùng
   quyết định" từ **docstring** (transcript.py:8-26) thành **định lý được kiểm**.
2. `tool_catalog_hash` trong manifest == hash của `KHAI_BAO_CONG_CU` + digest source `world_tools.py`.
   Không khớp ⇒ **fail closed**. Hôm nay: sửa `world_tools.py` xong replay **vẫn xanh** (B2).

### 4.5 INVARIANT tool

- **P3-I6 (read-only):** không tool nào chạm `w.ledger/w.agents/w.parcels/...`. Test đã có
  (tests/test_world_tools.py:25-41) nhưng **chỉ tuần tự** — bổ sung: snapshot `world_hash` trước/sau
  **toàn bộ pha gather song song** (real fan-out chạy tool trong thread pool,
  orchestrator.py:252-266) để loại race read-modify.
- **P3-I7 (mutation chỉ qua action JSON):** tool không tạo intent. Mọi thay đổi state đi qua
  `QuyetDinh → translate → KeHoach → engine handler` (charter §3 Lớp-4; ADR 0002 §A.1).
- **P3-I8 (tất định):** tool đọc `w` tại thời điểm **gather** (trước mọi apply) — world_tools.py:8-10
  đã đúng; giữ. RNG trong tool chỉ qua `w.rng.get(<key>, <period>)` (đã đúng: `nghe_ve`
  world_tools.py:125 seeded theo `(aid, nguoi, năm)`).
- **P3-I9 (không network/MCP từ xa):** catalog là hàm Python thuần cục bộ; test chặn
  `THOC_BLOCK_NETWORK=1` phải xanh khi chạy toàn bộ fixture tool.

---

## 5. Action outcome cards / memory (Report_v2 §4.5.5)

### 5.1 `a.su_co` đã tồn tại — ĐỦ hay THIẾU?

**Có mầm, KHÔNG đủ.**

Tồn tại: `Agent.su_co: list` (types.py:59); `_ghi_su_co` (production.py:103-107, cap 3); render
"Chuyện vừa rồi KHÔNG THÀNH (rút kinh nghiệm): …" (prompts.py:651-652); orchestrator xóa sau gather
(orchestrator.py:156-160). Nằm trong `behavioral_state` qua `"population": self.agents`
(world.py:515) ⇒ **đã vào world_hash** — precedent tốt, `KetQua` thừa hưởng.

**Sáu thiếu sót:**

1. **Free text, không reason code** ⇒ không dựng được funnel `prompted→…→executed` theo mã lý do
   (Report_v2 P4 đòi đúng thứ này). Không assert được trong test.
2. **Không có số lượng thực hiện, đối tác, giá thực, tiến độ project.**
3. **Chỉ ghi THẤT BẠI.** Không có card "đã bán 40 gỗ @11.2 cho A0031" ⇒ agent **không phân biệt được
   "tôi định bán" với "tôi đã bán"**. Kho tài sản trong prompt cho thấy *tồn*, không cho thấy *fill*.
4. **Không có tick stamp.** Agent chỉ được hỏi mỗi `nghi_dinh_ky_moi_n_tick = 4` tick
   (config/world.yaml:272) ⇒ sự cố có thể cũ 3 tick mà agent không biết.
5. **Xóa chỉ cho thinker** (orchestrator.py:156-160) ⇒ người chạy thẻ tích `su_co` vô thời hạn.
6. **Cap 3** (production.py:107) ⇒ tick nhiều việc hỏng thì mất bớt.

**Nghiêm trọng nhất — không phủ hết đường từ chối.** `translate.py` bỏ intent lạ và **chỉ**
`ghi_unrecognized` (translate.py:159, 190, 378): event journal có, **agent KHÔNG nhận phản hồi**.
Một LLM bịa `{"loai":"ban_go"}` có thể lặp lại **mãi mãi** mà không bao giờ biết vì sao im lặng.

### 5.2 Bản đồ "từ chối im lặng" → reason code (đầy đủ, file:line)

| reason code | Ý nghĩa | Engine từ chối ở đâu | Agent thấy? |
|---|---|---|---|
| `unknown_action` | `loai` ngoài `LOAI_HANH_DONG` | translate.py:188-190 | **KHÔNG** (chỉ event) |
| `bad_params:<field>` | ép kiểu/validate hỏng | translate.py:155-159 | **KHÔNG** |
| `unopened_action` | nguyên tố chưa mở ở phase | translate.py:374-378 | **KHÔNG** |
| `unknown_item` | `xay` món lạ | translate.py:235-237 | **KHÔNG** |
| `insufficient_labor` | thiếu công | production.py:247, 316 | có (su_co, không mã) |
| `insufficient_input` | thiếu nguyên liệu recipe | production.py:387, 396, 418, 439, 476 (+`_thieu_gi` 110-116) | có (su_co, không mã) |
| `no_right` | không có blueprint / không có quyền dùng | production.py:427, 447, **465** | 427 có; **465 KHÔNG** |
| `no_inventory` | số dư 0 | market.py:119-122 (`LoiSoKep` → chỉ `settlement_fail_tick += 1`) | **KHÔNG** |
| `insufficient_inventory` | có nhưng < số lượng | market.py:119-122; board.py:144 (`_ky_hop_dong` False) | **KHÔNG** |
| `insufficient_payment` | thiếu tài sản thanh toán | market.py:119-122; market.py:222-225 (`phien_dat`) | **KHÔNG** |
| `bad_order` | NaN/inf, `sl<=0`, `gia<=0`, `tai_san == thanh_toan` | market.py:171-174 | **KHÔNG** |
| `market_unreachable` / `no_boat` | chợ bờ kia, không đò / chưa qua sông | market.py:178 (`_toi_duoc_cho` False) | **KHÔNG** |
| `wrong_market` | `lang` ngoài phạm vi | market.py:176-177 | **KHÔNG** |
| `not_on_bank` | chưa qua sông tới thửa | production.py:150-151, 240 | có (su_co) |
| `parcel_taken` | thửa đã có người canh tick này | production.py:211 (`da_canh_tick_nay`) | **KHÔNG** |
| `parcel_not_public` | `khai_hoang` thửa có chủ / sai loại | production.py:148 | **KHÔNG** |
| `listing_not_found` | `tra_gia_dat` thửa chưa niêm yết | market.py:212-213 | **KHÔNG** |
| `bid_below_ask` | bid < ask | market.py:220-221 (`break`) | **KHÔNG** |
| `listing_expired` | niêm yết quá hạn / đổi chủ | market.py:206-209 | **KHÔNG** |
| `offer_not_found` | `tra_loi_hop_dong` ref lạ / không dành cho mình / của chính mình | tick.py:99-101 | **KHÔNG** |
| `not_a_party` | đăng hợp đồng mà mình không là một bên | board.py:28-32 | event, không su_co |
| `contract_invalid:<ly_do>` | `validate_hop_dong` từ chối (17 nhánh, contracts.py:110-167) | board.py:33-36 | event, không su_co |
| `counterparty_unavailable` | bên kia chết/giải thể | board.py:103-106; tick.py:83-84 (`nhan_tin` bỏ) | **KHÔNG** |
| `offer_expired` | đề nghị hết hạn | board.py:107-113 (chỉ `ghi_ky_uc` cho **người đăng**, và **chỉ khi không ai trả lời**) | người trả lời: **KHÔNG** |
| `offer_taken` | người khác nhận trước / ký hụt | board.py:144, 151-154 (`dn.tra_loi.clear()`) | **KHÔNG** |
| `mailbox_full` | hòm thư người nhận đầy | tick.py:85-86 | **KHÔNG** |
| `not_authorized` | `ban_hanh_luat` không phải trưởng làng; `quyet_dinh_entity` không điều hành | tick.py:66-71 | event, không su_co |
| `not_in_season` | canh sai mùa | production.py:294-316 | một phần (316) |
| `over_capacity` | đò quá tải | `engine/spatial.py` (ADR 0005 §2.3) | **KHÔNG** |
| `expired_quote`, `quote_already_taken`, `quote_exhausted`, `escrow_failed` | §6 | NEW | NEW |
| `budget_stop` | run dừng êm, agent rơi về thẻ cũ | orchestrator.py:316-321 | **KHÔNG** |

⇒ **~20 đường từ chối im lặng**, phần lớn ở **chợ và bảng rao** — đúng khu vực mà `real60_spatial`
"không thấy giao dịch". **Không thể kết luận "LLM không biết buôn bán" khi engine không bao giờ nói
vì sao lệnh của nó biến mất.**

### 5.3 Schema `KetQua` (thay `su_co`)

```python
@dataclass
class KetQua:                     # engine/types.py — action outcome card
    tick: int
    action: str                   # "dat_lenh" | "bao_gia.accept" | "phan_bo_cong" | "xay:nha" ...
    ref: str                      # thread/contract/parcel id; "" nếu không có
    trang_thai: str               # "executed" | "partial" | "rejected"
    yeu_cau: dict[str, float]     # số lượng ĐÃ ĐỀ NGHỊ
    thuc_hien: dict[str, float]   # số lượng ĐÃ THỰC HIỆN — lấy TỪ Transaction đã ap_dung
    doi_tac: str                  # counterparty; "" nếu không có
    gia_thuc: float | None        # đơn giá THỰC khi settle; None nếu không phải giao dịch
    thanh_toan: str | None
    tien_do: tuple[float, float] | None   # (đã góp, cần) cho project nhiều tick
    ly_do: str                    # reason_code; "" khi executed
    thieu: dict[str, float]       # {"cong": 180.0, "go": 8.0} — RÀNG BUỘC còn thiếu
```

Lưu `Agent.ket_qua: list[KetQua]`, cap `minds.ket_qua_toi_da` (mặc định 8), rolling.
**Không xóa sau gather** (khác `su_co`): đánh dấu `da_doc`, giữ 2 card đã đọc gần nhất — vì chỉ ~40%
agent được hỏi mỗi tick (config/world.yaml:272), xóa sớm = mất phản hồi.
Vào world_hash tự động (world.py:515). Migration: `su_co` giữ 1 release như **view** của
`[k for k in ket_qua if k.trang_thai == "rejected"]`; `nap_checkpoint` dùng `getattr(a, "ket_qua", [])`.

Render:

```text
[KẾT QUẢ HÀNH ĐỘNG GẦN ĐÂY]
✔ tick 11 — bán 40 gỗ cho A0031 @ 11.2 thóc (đã vào kho).
◐ tick 11 — đặt bán 60 gỗ: khớp 40/60.
✘ tick 11 — xây nhà: rejected [insufficient_labor] — thiếu 180 công.
✘ tick 10 và 11 — xây nhà: rejected [insufficient_labor] (2 lần liên tiếp).
```

### 5.4 INVARIANT

- **P3-I10 (không kể intent là fact):** chỉ ghi `trang_thai="executed"` khi đã có `Transaction`
  `ledger.ap_dung` hoặc một `event`. `thuc_hien` lấy **từ transaction**, không từ `KeHoach`.
  **Vi phạm hiện có:** `w.rao_vat` (tick.py:203-212) dựng từ `lenh_tick` — các lệnh **đã nộp nhưng
  chưa khớp**, kể cả lệnh sẽ bị `phien_cho` loại (market.py:171-179: NaN, chợ không tới được…).
  Cả làng "nghe phong thanh" (prompts.py:630-643) về một lời rao **chưa từng vào sổ nào**.
  Sửa: `phien_cho` trả danh sách lệnh **đã vào sổ**; `w.rao_vat` lấy từ đó; nhãn rõ "đang rao / hỏi
  mua" (một quote, không phải một giao dịch).
- **P3-I11 (chống lặp vô hạn KHÔNG bằng gợi ý):** card mang `ly_do` + `thieu` (**ràng buộc còn
  thiếu**) và **đếm số lần lặp liên tiếp** của cùng `(action, ly_do)` — dẫn xuất **thuần hàm** từ N
  card gần nhất lúc build prompt (không thêm state). **CẤM** card gợi ý hành động thay thế ("thử
  đánh cá đi") — đó là mớm. Đường thoát hợp lệ: `xem_co_hoi_san_xuat` cho phép **kiểm tra trước khi
  làm**, nên agent tự tìm được ràng buộc mà không ai chỉ đường.

---

## 6. A2A commerce thread (Report_v2 §4.5.6)

### 6.1 Đánh giá TRUNG THỰC: `bang_rao` + `HopDong` đã làm được bao nhiêu phần trăm

| Yêu cầu §4.5.6 | Đã có? | Bằng chứng |
|---|---|---|
| thread ID | **CÓ** | `DeNghi.id = f"DN{w._next_dn:05d}"` (board.py:37-38); `w.bang_rao` trong `behavioral_state` (world.py:525) |
| parties | **CÓ** | `dn.tu`, `dn.den`, `hd.cac_ben` (+ placeholder `"?"` cho rao công khai, board.py:128-143) |
| request_quote → quote → counteroffer → accept/reject | **CÓ ~90%** | `de_nghi_hop_dong` (translate.py:238-241) → `dang_de_nghi` (board.py:25-43); trả lời `chap_nhan`/`tu_choi`/**`mac_ca`** (translate.py:242-248) → `khop_bang_rao` (board.py:93-158); mặc cả tái đăng ngược chiều với `vong_mac_ca+1`, trần `hop_dong.mac_ca_toi_da_vong` (board.py:96, 147-150). **NHƯNG `mac_ca` không có trong menu prompt (prompts.py:180) ⇒ vô hình với LLM** |
| settlement **đúng một lần**, nguyên tử | **CÓ** | `_ky_hop_dong` (board.py:51-90): mọi clause `chuyen_giao_mot_lan @ ky_ket` chuyển nguyên tử, **rollback** khi hụt (board.py:60-68); ký xong `del w.bang_rao[dn_id]` (board.py:151-152) ⇒ không ký hai lần. Sổ kép chặn số dư âm |
| chat **không** tự tạo trade | **CÓ (đã đúng)** | `nhan_tin` (tick.py:73-89): chỉ vào `hom_thu`, **không chạm ledger**, trễ 1 tick. Lỗi ở `real60_spatial` (Report_v2:83) **không phải** chat settle bậy, mà là **không có kênh nào khác để chốt** |
| asset / quantity / **unit_price** / payment_asset khai báo | **KHÔNG** | Quote đổi hàng phải biểu diễn bằng 2 clause `chuyen_giao_mot_lan`; **đơn giá không phải field** ⇒ không index được ⇒ `xem_bao_gia`/sổ depth **không thể tồn tại** |
| expiry **theo thread** | **KHÔNG** | Chỉ có hằng số toàn cục `hop_dong.de_nghi_het_han_tick` (board.py:97, 156) |
| delivery / location | **KHÔNG** | `DeNghi` không có làng/bờ; `_toi_duoc_cho` chỉ áp cho lệnh chợ (market.py:146-160) |
| **state machine tường minh** | **KHÔNG** | `DeNghi` không có field `trang_thai`; trạng thái là ngầm; `dn.tra_loi.clear()` (board.py:154) xóa câm |
| **reservation / escrow** | **KHÔNG — ZERO** | grep `reserve|escrow|khoa|giu_cho|ky_quy|dat_coc|lock` trên `engine/` chỉ ra false-positive (`dieu_khoan`, `khoai`, `khoảng`, `block`). **NEW thật sự** |
| cancel (rút lời rao của chính mình) | **KHÔNG** | `bao_huy`/`don_phuong_pha_vo` chỉ áp cho `HopDong` **đã ký**. **Agent không có cách nào gỡ một `DeNghi` đã đăng** |

**Kết luận: ~60%.** Xương sống request→(counter)offer→accept→settle-nguyên-tử **đã có và đã đúng**.
Thiếu: (1) kinh tế khai báo được, (2) expiry per-thread, (3) delivery/location, (4) state tường minh
+ cancel, (5) **escrow/reservation**, (6) reason code cho mọi transition hỏng, (7) phơi `mac_ca` ra menu.

**Double-spend hôm nay:** *ledger* không double-spend (`LoiSoKep` chặn). Nhưng *protocol* có lỗ:
cùng 100kg gỗ **bảo chứng được N đề nghị treo cùng lúc**; ai chấp nhận trước thì `_ky_hop_dong` của
người sau trả **`False` — im lặng** (board.py:144). Người mua đã "đồng ý" thấy giao kèo **bốc hơi
không lý do**. Đây chính là phiên bản engine của "đồng ý mua gỗ nhưng không có trade" (Report_v2:83).

### 6.2 Phương án NHỎ NHẤT: module mới `engine/quotes.py` (KHÔNG mở rộng `DeNghi`)

Vì sao **không** mở rộng `DeNghi`: `w.bang_rao` nằm trong `behavioral_state` (world.py:525). Thêm
field vào `DeNghi` ⇒ canonical dict đổi ⇒ **world_hash legacy đổi** ⇒ vi phạm ADR 0005 §11.4 (dòng
361-366). Ngoài ra `DeNghi` là **đề nghị hợp đồng** (văn phạm 9 clause, tùy ý), còn quote là **chào
giá thương mại** (kinh tế khai báo) — trộn hai thứ làm `bang_rao` đa hình và làm hỏng
`mau_hop_dong_luu_hanh` (prompts.py:28-52) lẫn metric `so_mo_tip` (tick.py:285).

**Module NEW `engine/quotes.py`**; state `w.bao_gia: dict[str, BaoGia]`; gate
`thuong_mai.bao_gia.bat` (**mặc định OFF**). Vào `behavioral_state()` dưới khóa mới
`"commerce": {"quotes": self.bao_gia}`, và **khóa này bị OMIT hoàn toàn khi gate OFF** — đúng
precedent `two_bank` (world.py:470-493) + `_behavioral_config` (world.py:497-499) ⇒ **hash legacy
bit-for-bit không đổi**. Migration `nap_checkpoint`: `getattr(w, "bao_gia", {})`.

**Tái dùng, không viết lại:** ledger `Transaction` 4 chân (hình dạng market.py:85-94); tie-break
người trả lời (board.py:114-118); `w.ghi_gia` (world.py:328-332); `events.ghi`.

### 6.3 Schema thread

```python
@dataclass
class BaoGia:
    id: str                  # "BG00042" — w._next_bg
    nguoi_dang: str
    doi_tac: str | None      # None = công khai; != None = đích danh
    chieu: str               # "ban" (ask) | "mua" (bid)
    tai_san: str
    so_luong: float          # tổng
    con_lai: float           # chưa khớp
    don_gia: float           # đơn giá tính theo `thanh_toan`
    thanh_toan: str          # "thoc" | "xu" | <mã hàng> — KHÔNG mặc định là tiền
    het_han_tick: int        # PER-THREAD
    giao_tai: str            # "ngay" (spot) | "tick:T" (forward)
    lang: int
    bo: str | None           # bờ sông (spatial); None khi khong_gian tắt
    trang_thai: str          # dang_treo | da_khop | hoan_thanh | het_han | da_huy | tu_choi
    ref_cha: str | None      # counteroffer → thread cha
    tick_dang: int
    tick_settle: int | None  # != None ⇒ ĐÃ settle (guard exactly-once)
    escrow: dict[str, float] # {asset: qty} đang nằm ở KY_QUY:<id>
```

### 6.4 State machine, ownership, quyền nhìn

```text
  post ──validate──► dang_treo ──accept(q ≤ con_lai)──► da_khop ──delivery──► hoan_thanh
    │  (từ chối: tu_choi)  │  │                              │
    │                      │  └─counteroffer──► thread MỚI (ref_cha); thread cũ vẫn treo
    │                      ├─huy_bao_gia───────► da_huy   (escrow trả người đăng)
    │                      └─tick > het_han_tick► het_han  (escrow trả người đăng)
    └─ reject codes: insufficient_inventory | insufficient_payment | bad_params |
                     counterparty_unavailable | not_reachable
```

- `giao_tai="ngay"` ⇒ `da_khop → hoan_thanh` **trong cùng tick** (bước 6b).
- `giao_tai="tick:T"` ⇒ ở `da_khop` qua nhiều tick; escrow **cả hai bên** giữ tới T.
- **Ownership:** thread thuộc `nguoi_dang`; chỉ `nguoi_dang` `huy_bao_gia` được.
- **Quyền nhìn = quyền accept:** chỉ agent thấy được thread (đích danh, hoặc công khai **cùng làng /
  cùng bờ / tới được chợ đó**) mới `accept`/`mac_ca` được; ngoài ra ⇒ `offer_not_visible`.
- **Vào `world_hash`: CÓ.** Thread ảnh hưởng lựa chọn tick sau và dòng ledger tương lai ⇒ phải nằm
  trong `behavioral_state()` (§6.2). Escrow nằm sẵn trong `ledger._so_du` (world.py:510) ⇒ được băm
  tự động khi ON, không tồn tại khi OFF.

### 6.5 Escrow — CHỐT: **tài khoản ledger riêng**, KHÔNG "khóa mềm"

**Chọn (A): `KY_QUY:<thread_id>` là một holder ledger bình thường** (như `CONG_QUY`).

Vì sao **không** chọn (B) khóa mềm (giữ balance, giảm `available`): khóa mềm chỉ đúng nếu **mọi**
đường tiêu thụ đều nhớ trừ khóa — ăn (`consumption.an_va_suc_khoe`), gieo giống (`production`), lệnh
chợ (`market.phien_cho`), clause hợp đồng (`contracts`), thuế (`politics.thu_thue_va_chia`), trộm
(`xa_hoi.trom`), gà ăn thóc (`chan_nuoi`), thanh lý entity… Bỏ sót **một** đường ⇒ khóa là lời nói
dối ⇒ accept xong không giao được hàng — **đúng cái bug ta đang đi sửa**.
Với (A), hàng **đã rời tài khoản** ⇒ không đường nào tiêu được nó; double-spend là **bất khả về cấu
trúc**: escrow lần hai cùng số hàng ⇒ `LoiSoKep` ⇒ `reject[insufficient_inventory]`.

**Bảo toàn:** mọi chân escrow là `ledger.chuyen`/`Transaction` (sổ kép, có đối ứng) ⇒ tổng tài sản
**không đổi** ⇒ `audit.kiem_toan_the_gioi` (tick.py:260) xanh **không cần sửa công thức**.

**Đối ứng ledger từng transition:**

| Transition | Transaction (sổ kép) | Event |
|---|---|---|
| post(ask) | `nguoi_dang −sl asset` / `KY_QUY:<id> +sl asset` | `bao_gia_dang{id, ai, chieu, tai_san, sl, don_gia, thanh_toan, het_han}` |
| post(bid) | `nguoi_dang −(sl×don_gia) thanh_toan` / `KY_QUY:<id> +…` | `bao_gia_dang{…}` |
| accept(q) | bên nhận escrow phần đối ứng: `nguoi_nhan −… / KY_QUY:<id> +…` | `bao_gia_khop{id, ben_nhan, sl}` |
| settle | **MỘT** `Transaction` 4 chân: `KY_QUY −q asset / mua +q asset` **và** `KY_QUY −q×p thanh_toan / ban +q×p` | `bao_gia_thanh_toan{id, mua, ban, sl, gia}` + `w.ghi_gia(tai_san, don_gia, q, thanh_toan)` |
| het_han / da_huy | `KY_QUY −… / chủ cũ +…` | `bao_gia_het_han{id}` / `bao_gia_huy{id}` |

**Audit assertion NEW (chống sinh ra một `VO_THUA_NHAN` mới — Report_v2:80):** cuối mỗi tick
`Σ số dư mọi KY_QUY:* == Σ escrow khai báo bởi thread còn sống`, **và** không `KY_QUY:*` nào còn số
dư ≠ 0 khi thread đã `hoan_thanh|het_han|da_huy|tu_choi`. Sai ⇒ raise (điều luật #1).

**Escrow phải bị LOẠI khỏi:** danh mục tài sản trong `mo_ta_the_gioi` (lọc như `vi_the:`,
prompts.py:59-61), Gini/wealth metrics, `tai_san_quy_thoc`, `household_food_equivalent`, nhãn giai
cấp observatory. Nếu không, escrow hiện ra như "một agent giàu ma".

**Escrow lúc POST hay lúc ACCEPT? CHỐT:** ask escrow **hàng** lúc POST; bid escrow **tiền** lúc POST;
bên chấp nhận escrow phần đối ứng lúc ACCEPT. Hệ quả (nói thẳng, không né):

- mọi báo giá treo đều **có bảo chứng** ⇒ `xem_bao_gia` là **depth thật**, không phải ask ma;
- **đăng báo giá có chi phí cơ hội thật** (hàng bị khóa tới khi hết hạn/tự hủy) ⇒ thỏa charter §5
  điều kiện 2 (Cost) và 1 (Alternative: barter qua `HopDong`/chợ vẫn chạy khi module OFF);
- **rủi ro phải nêu:** agent khóa hết thóc vào một ask rồi **chết đói**. **CẤM** hard-code "engine từ
  chối escrow thóc ăn" — đó là engine áp đặt sở thích. Thay vào đó: (a) fact card hiện "đang khóa
  trong báo giá: X"; (b) có `huy_bao_gia` để rút; (c) `household_food_equivalent` **không** đếm escrow
  ⇒ cảnh báo đói (prompts.py:599-605) nổ đúng lúc. Chết vì tự khóa lương thực là **kết quả hợp lệ**
  (Report_v2:22-23).
- **Ablation bắt buộc:** `thuong_mai.bao_gia.escrow_khi_dang: true|false`. `false` ⇒ chỉ escrow lúc
  accept (báo giá không bảo chứng, accept có thể fail). Đây là cần cẩu đo "báo giá có bảo chứng có
  làm tăng quote→settlement conversion không" (metric P4).

### 6.6 Settlement ĐÚNG MỘT LẦN — hai lớp guard độc lập

1. **State guard:** `buoc_giao_hang` chỉ đụng thread `trang_thai == "da_khop"`, và đặt
   `trang_thai="hoan_thanh"` + `tick_settle = w.tick` **trong cùng hàm trước khi thoát**.
2. **Ledger guard:** settlement **rút cạn** `KY_QUY:<id>`. Gọi lần hai ⇒ số dư 0 ⇒ `LoiSoKep`.

Test: gọi `buoc_giao_hang` **hai lần** trong một tick ⇒ số dư ledger và `world_hash` **y hệt** một lần.

### 6.7 Thứ tự tất định (deterministic ordering)

Chèn vào `engine/tick.py`:

- **6a `quotes.buoc_bao_gia(w, ke_hoach)`** — ngay sau `board.khop_bang_rao(w)` (tick.py:102), **TRƯỚC**
  sản xuất/chợ: escrow phải khóa hàng trước khi production/consumption/`phien_cho` tiêu cùng số hàng.
- **6b `quotes.buoc_giao_hang(w)`** — ngay sau `contracts.thi_hanh_hop_dong_tick` (tick.py:222).

Thứ tự pha **cố định** trong 6a: `huy → het_han → post → accept → settle(spot)`.
Trong mỗi pha: duyệt `sorted(ke_hoach)` rồi `sorted(thread_id)`.
Nhiều người cùng accept một thread ⇒ **tái dùng tie-break của board** (board.py:114-118):
`key = (-w.uy_tin(nguoi_dang, ai), g.random(), ai)` với `g = w.rng.get("bao_gia", w.tick)`.
Fill theo thứ tự đó tới khi `con_lai == 0`; người còn lại nhận `quote_exhausted`.

**Partial fill:** `accept` mang `sl ≤ con_lai`; khớp một phần ⇒ thread vẫn `dang_treo` với `con_lai`
giảm, escrow giải phóng theo phần đã giao. Đây là nguồn outcome `partial` mà Report_v2 P3.3/P3.5 đòi.

### 6.8 Hệ quả tương tác với chợ (không giấu)

Escrow-khi-post lấy hàng **ra khỏi** tài khoản trước phiên chợ (tick.py:213). Agent vừa post ask 100
gỗ vừa `dat_lenh ban 100 go` ⇒ lệnh chợ **thiếu hàng**. Hôm nay `LoiSoKep` bị nuốt câm
(market.py:119-122); sau P3 phải phát `KetQua[rejected, insufficient_inventory]`. Hai kênh giờ tương
tác **trung thực**.

Giá quote **có** vào `w.gia_lich_su` (như giá khớp chợ) với tag `nguon="bao_gia"` để phân tích tách
được giá đấu-giá vs giá song-phương. Gate `thuong_mai.bao_gia.ghi_gia_lich_su` (ablatable) vì nó nuôi
`cap_nhat_gia_ky_vong` (pricing.py:80-104) ⇒ ảnh hưởng hành vi.
**Không vi phạm** CLAUDE.md §2(7) "engine không tự đặt giá": `don_gia` do **hai bên** thỏa thuận;
engine chỉ thi hành và ghi nhận.

### 6.9 Intent/schema mới (đi qua catalog P0.1)

```json
{"loai":"dang_bao_gia","chieu":"ban","tai_san":"go","sl":40,"don_gia":11.5,
 "thanh_toan":"thoc","het_han":3,"giao_tai":"ngay","den":null}
{"loai":"tra_loi_bao_gia","ref":"BG00042","tra_loi":"chap_nhan","sl":20}
{"loai":"tra_loi_bao_gia","ref":"BG00042","tra_loi":"tu_choi"}
{"loai":"tra_loi_bao_gia","ref":"BG00042","tra_loi":"mac_ca","don_gia":10.0,"sl":40}
{"loai":"huy_bao_gia","ref":"BG00042"}
```

`mac_ca` ⇒ tạo thread mới `ref_cha="BG00042"`, đích danh ngược lại, trần vòng
`thuong_mai.bao_gia.mac_ca_toi_da_vong` (đối xứng board.py:96).

- **INVARIANT P3-I12:** một `nhan_tin` "tôi đồng ý mua gỗ" **KHÔNG** tạo trade — chat vẫn
  non-binding (tick.py:73-89 giữ nguyên). Muốn chốt phải qua `dang_bao_gia`/`tra_loi_bao_gia` hoặc
  `de_nghi_hop_dong`/`tra_loi_hop_dong`.
- **INVARIANT P3-I13:** một quote **không** chi tiêu cùng một inventory hai lần — bảo đảm bằng
  escrow-tại-post (§6.5), **không** bằng "kiểm tra số dư lúc accept".
- **INVARIANT P3-I14:** `mac_ca` phải xuất hiện trong catalog cho **cả** `tra_loi_hop_dong`
  (vá prompts.py:180) **và** `tra_loi_bao_gia`.

---

## 7. Test matrix P3 (tên + assert — để `test-engineer` viết, không phải người implement)

### 7.0 Harness bắt buộc TRƯỚC mọi test (hệ quả của B1)

`MindMock` **không đọc prompt** (orchestrator.py:274-275) và **không chạy tool** (orchestrator.py:68,
280-282; `MockProvider` không có `goi_agentic`, gateway.py:76-86). Nếu viết test P3 trên MindMock,
mọi assertion "agent khám phá được hành động qua catalog/tool" là **rỗng**.

**NEW (test-only, `tests/fixtures/prompt_bot.py`):** `ScriptedPromptBot` — provider tất định implement
`goi(req)` + `goi_agentic(req, w, aid)`, **quyết định CHỈ từ nội dung `req.prompt` và output tool**:

1. parse khối `[DANH MỤC HÀNH ĐỘNG]` + `[CƠ HỘI]` + `[BÁO GIÁ ĐANG TREO]` ra khỏi prompt;
2. (tùy kịch bản) gọi tool qua `thuc_thi` với args lấy từ prompt;
3. phát JSON `QuyetDinh` **chỉ dùng id/tham số đã xuất hiện** trong prompt/tool output.

Kịch bản (`kb=`) cấu hình được: `first_feasible`, `always_invalid_json`, `bad_tool_args`,
`spam_tools`, `accept_quote`, `stale_accept`, `chat_only`. Không mạng, không LLM.

### 7.1 `tests/test_p3_prompt_runtime.py`

| Test | Assert |
|---|---|
| `test_prompt_khong_mom_chien_luoc_mo_rong` | scaffolding (engine-authored) không chứa token nào trong `TU_MOM ∪ TU_TELEO ∪ TU_NHAN_NGHE ∪ TU_DONG_CO` (§1.4) |
| `test_khoi_agent_authored_duoc_mien_tru` | render fixture có `niem_tin="A đáng tin, B phải đề phòng"`, `gia_huan` bẩn ⇒ gate vẫn XANH; và `scaffolding_only(w, aid)` **không chứa** các chuỗi đó (chứng minh tách khối được) |
| `test_prompt_khong_co_vi_du_chien_luoc` | khối định dạng không chứa `chia_san_luong`, `ty_le`, `cau_hon`; `hanh_dong` trong ví dụ là `[]` |
| `test_prompt_khong_gan_nhan_nghe` | `prompt.nhan_giai_cap=false` ⇒ không token nào trong `GIAI_CAP_VN.values()` xuất hiện |
| `test_prompt_khong_mo_ta_co_che_dang_tat` | `chinh_tri.bat=false` ⇒ không có "trưởng làng", "công quỹ", "gini", "sung công", "nghiệp đoàn", "đình công" (vá prompts.py:285-291) |
| `test_cau_duoc_phep_sinh_tu_catalog` | mọi hành động trong `[BẠN CÓ THỂ LÚC NÀY]` có `availability_predicate(w,aid) == True`; và ∀ entry catalog: có schema + translate + handler (P3-I1) |
| `test_khong_action_nao_mo_coi` | mọi handler public trong engine hoặc ở catalog, hoặc ở `AN_HANH_DONG` có lý do khai báo (bắt `dong_thuyen`/`rao_do`/`qua_song`, intents.py:50-52) |
| `test_luat_vat_ly_theo_config` | render với overlay spatial ⇒ prompt nói `4 tháng`, `60kg`, `120 công`, 3 mùa; base ⇒ nói đúng hằng base (đồng-sở-hữu với P0.1) |

### 7.2 `tests/test_p3_fact_cards.py`

| Test | Assert |
|---|---|
| `test_boundary_lang` | Agent làng 0 **không** thấy giá khớp chỉ xảy ra ở làng 2 (vá L2); không thấy dân số/hợp đồng toàn thế giới (vá L1) |
| `test_boundary_hang_xom` | Ước lượng tài sản chỉ có cho id ∈ `w.hang_xom_cua(aid)`; giá trị **có nhiễu** và **tất định theo seed** |
| `test_provenance_tag` | Mọi field fact card/tool output có `nguon` ∈ tier được phép của caller (§2.3); không field nào vượt tier |
| `test_gia_la_evidence_khong_phai_gia_dung` | `n_quan_sat==0` ⇒ field giá là `null` + câu "chưa có phiên khớp nào"; **không** rơi về `a.gia_ky_vong` (P3-I2) |
| `test_prior_khong_tron_voi_market` | prompt chứa **hai** dòng tách bạch (ƯỚC GIÁ RIÊNG vs giá khớp); không có dòng "giá" hợp nhất (P3-I3) |
| `test_khong_bid_ask_tu_call_auction` | Khi `bao_gia.bat=false`, fact card **không** có `bid/ask/depth` (P3-I4) |
| `test_escrow_khong_hien_nhu_cua_cai` | Tài sản trong `KY_QUY:*` không xuất hiện ở `mo_ta_the_gioi`, Gini, `household_food_equivalent` |

### 7.3 `tests/test_p3_opportunity_cards.py`

| Test | Assert |
|---|---|
| `test_card_khong_xep_hang` | ∀ card: không key ∈ `{ev, gia_tri_ky_vong, loi_nhuan, xep_hang, diem, score, rank, tot_nhat}` |
| `test_thu_tu_card_duoc_xao_theo_seed` | 2 crop vật lý **giống hệt** ⇒ thứ tự khác nhau ở ≥1 cặp (aid,tick); tần suất đứng đầu cân bằng trong `tol` trên N=200; **và** cùng seed ⇒ cùng thứ tự (tất định) |
| `test_card_chi_hien_khi_feasible_hoac_gan` | Agent không thuyền + thửa bờ kia ⇒ card `khai_hoang` **ẩn** khỏi prompt, nhưng `xem_co_hoi_san_xuat(ma="khai_hoang")` trả `feasible:false, thieu:["no_boat"]` |
| `test_card_dung_cong_thuc_engine` | `card.output_ky_vong` == sản lượng thực tế khi hệ số thời tiết = kỳ vọng (P3-I5) |
| `test_card_neu_resource_impact` | card `danh_ca` mang `resource_impact["ca_ton"] < 0` khớp lượng engine thực trừ |

### 7.4 `tests/test_p3_tools.py`

| Test | Assert |
|---|---|
| `test_tool_read_only_ca_pha_gather` | `world_hash` bất biến trước/sau **toàn bộ** pha gather song song 50 agent (mở rộng tests/test_world_tools.py:25-41) — P3-I6 |
| `test_tool_authorization_nghe_ve` | `nghe_ve` với id **không** phải hàng xóm/cùng làng ⇒ `E_NOT_AUTHORIZED` (vá L4) |
| `test_tool_authorization_phan_bo_cua_cai` | Agent thường ⇒ `E_NOT_AUTHORIZED`; trưởng làng đương nhiệm ⇒ `ok:true` và **chỉ** phạm vi làng mình (vá L5) |
| `test_tool_khong_toi_duoc_cho` | `xem_thi_truong_local(lang=<bờ kia>)` khi chưa qua sông ⇒ `E_NOT_REACHABLE` |
| `test_tool_args_sai` | `xem_thi_truong_local(tai_san="vang")` ⇒ `E_UNKNOWN_ASSET`; tên tool bịa ⇒ `E_UNKNOWN_TOOL`; **không raise**, vòng vẫn ra quyết định |
| `test_tool_quota` | `ScriptedPromptBot(kb="spam_tools")` gọi 30 lần ⇒ từ lần 13 trả `E_QUOTA`; agent **vẫn** ra được `QuyetDinh` hợp lệ; `so_luot_tool` đếm đúng 12 |
| `test_tool_quota_dem_lan_goi_khong_phai_luot_model` | 1 lượt model chứa 5 `functionCall` ⇒ tính **5** lần gọi (vá providers_real.py:147, 154-161) |
| `test_tool_khong_mang` | `THOC_BLOCK_NETWORK=1` ⇒ toàn bộ fixture tool xanh |

### 7.5 `tests/test_p3_outcomes.py`

| Test | Assert |
|---|---|
| `test_moi_duong_tu_choi_sinh_ket_qua` | **Bảng §5.2 là bảng test**: mỗi reason code có ≥1 test dựng đúng tình huống ⇒ `a.ket_qua[-1].ly_do == <code>` và `thieu` đúng lượng. Đặc biệt: `unknown_action` (translate.py:190), `insufficient_inventory` ở chợ (market.py:119-122), `offer_taken` (board.py:144) |
| `test_khong_ghi_da_lam_khi_chi_la_intent` | Intent `dat_lenh ban 60 go` nhưng khớp 40 ⇒ card `partial`, `thuc_hien={"go":40}`; **không** card nào nói "đã bán 60" (P3-I10) |
| `test_rao_vat_chi_gom_lenh_da_vao_so` | Lệnh bị `phien_cho` loại (NaN / chợ không tới được) ⇒ **không** xuất hiện trong `w.rao_vat` ⇒ không vào "NGHE PHONG THANH" của ai (vá tick.py:203-212) |
| `test_agent_phan_ung_voi_that_bai` | `ScriptedPromptBot(kb="first_feasible")`: tick 1 `xay nha` ⇒ `rejected[insufficient_labor]`; tick 2 bot đọc card ⇒ **không** phát lại `xay nha` mà chọn card feasible khác. **Assert giao diện**: card chứa `ly_do`+`thieu`; **không** assert "LLM sẽ khôn hơn" |
| `test_ket_qua_khong_bi_xoa_cho_nguoi_khong_nghi` | Agent thất bại ở tick 7, được hỏi ở tick 11 ⇒ vẫn thấy card **có tick stamp** (vá orchestrator.py:156-160) |
| `test_dem_lap_lai_la_ham_thuan` | Lặp 2 lần cùng `(action, ly_do)` ⇒ dòng "(2 lần liên tiếp)"; **không** thêm state mới vào world_hash |

### 7.6 `tests/test_p3_quotes.py`

| Test | Assert |
|---|---|
| `test_quote_settle_dung_mot_lan` | post ask 40 gỗ → accept 40 → settle ⇒ ledger: seller `+448 thóc`, buyer `+40 gỗ`, `KY_QUY:BG…` = 0; gọi `buoc_giao_hang` **lần hai** ⇒ số dư và `world_hash` **y hệt** (§6.6) |
| `test_chat_khong_the_settle` | A `nhan_tin` "tôi đồng ý mua 40 gỗ giá 11" → B `nhan_tin` "đồng ý" ⇒ **0** transaction, **0** thay đổi số dư (P3-I12) |
| `test_double_spend_bi_chan` | Có 100 gỗ, post 2 ask × 100 gỗ ⇒ ask thứ hai `rejected[insufficient_inventory]`; tổng escrow = 100 (P3-I13) |
| `test_accept_khoa_du_hoac_reject_ro` | Buyer thiếu thóc ⇒ `rejected[insufficient_payment]`, **không** chân ledger nào chạy, thread vẫn `dang_treo` |
| `test_stale_quote` | accept thread đã quá `het_han_tick` ⇒ `rejected[expired_quote]`; escrow **đã** trả người đăng ở pha `het_han` |
| `test_expiry_giai_phong_escrow` | Hết hạn ⇒ số dư người đăng khôi phục **chính xác**; `KY_QUY` = 0; event `bao_gia_het_han` |
| `test_cancel_giai_phong_escrow` | `huy_bao_gia` bởi người khác ⇒ `E_NOT_AUTHORIZED`; bởi chủ ⇒ escrow trả về |
| `test_partial_fill` | ask 60, accept 20 + accept 30 ⇒ 2 settlement, `con_lai=10`, escrow còn 10; 2 card `partial` |
| `test_quote_exhausted_va_tie_break` | 3 người accept ask 40 cùng tick ⇒ fill theo `(-uy_tin, g.random(), id)`; người còn lại `quote_exhausted`; **hoán vị thứ tự agent đầu vào ⇒ cùng kết quả** |
| `test_counteroffer_thread` | `mac_ca` ⇒ thread mới `ref_cha` đúng; trần vòng chặn vòng thứ N+1 |
| `test_bao_toan_va_audit` | Sau 20 tick có quote/escrow/expiry/cancel ⇒ `audit.kiem_toan_the_gioi` xanh mọi tick; assertion escrow §6.5 xanh |
| `test_hash_legacy_bat_bien` | `bao_gia.bat=false` ⇒ `world_hash` của run legacy **bit-for-bit y hệt** trước khi thêm module (ADR 0005 §11.4) |
| `test_quote_hash_khi_bat` | `bao_gia.bat=true` ⇒ thread vào `behavioral_state`; đổi 1 thread ⇒ hash đổi (chứng minh không phải state ma) |

### 7.7 `tests/test_p3_transcript_tools.py`

| Test | Assert |
|---|---|
| `test_tool_turn_vao_transcript` | Vòng agentic 3 lượt tool ⇒ transcript có **3** record `kind="tool_turn"` + 1 `kind="decision"` (vá B2) |
| `test_replay_khong_provider` | Replay từ transcript, provider = `TranscriptProvider` ⇒ `misses==0`, `unused==0`, `world_hash` khớp manifest; **không** gọi mạng |
| `test_replay_phat_hien_tool_drift` | Sửa output của một tool (fixture monkeypatch) ⇒ replay **FAIL** vì `ket_qua_hash` lệch / `tool_catalog_hash` lệch. **Hôm nay test này ĐỎ** (replay sẽ xanh giả) — đó là mục đích |
| `test_cung_prompt_cung_tool_transcript_cung_quyet_dinh` | Chạy 2 lần cùng seed ⇒ chuỗi `(prompt_hash, tool args_hash, ket_qua_hash, decision)` **giống hệt** |
| `test_malformed_json` | `ScriptedPromptBot(kb="always_invalid_json")` với `p_malformed` cao ⇒ pipeline `repair` cứu ≥95%; phần không cứu ⇒ fallback thẻ cũ, **có** `KetQua[budget_stop/bad_json]`, run **không** chết |

### 7.8 Test acceptance P3 (đúng câu chữ Report_v2:319-323)

| Test | Assert |
|---|---|
| `test_fixture_agent_kham_pha_moi_hanh_dong` | Với mỗi entry catalog khả dụng, `ScriptedPromptBot` dựng được action **hợp lệ chỉ từ prompt/tool output** ⇒ qua `translate` ⇒ tới handler engine ⇒ sinh `KetQua` (executed **hoặc** rejected có mã). **Không** action nào biến mất im lặng |
| `test_hai_sinh_ke_khac_nhau_khong_gan_nhan_nghe` | 2 world **chỉ khác factual state**: W_A = 2 thửa màu mỡ, không sông, rừng xa; W_B = 0 thửa, ở sát bến, có ask thuyền trên quote book, rừng kề. Cùng seed, cùng bot `first_feasible`. **Assert:** (1) tập action **đã thực thi** (từ ledger/event, không phải intent) KHÁC nhau giữa W_A và W_B; (2) cả hai đều có ≥1 sinh kế executed; (3) prompt + mọi tool output ở cả hai world **không** chứa token nào trong `GIAI_CAP_VN.values() ∪ {"nông dân","lái đò","ngư dân","thợ mộc","thương nhân"}` |

**Cảnh báo chống tautology:** test 7.8 **không** được viết bằng cách cho bot một bảng ưu tiên nghề.
Bot chỉ được: đọc `[CƠ HỘI]` (đã xáo), lấy card `feasible:true` **đầu tiên theo thứ tự đã xáo**, phát
action tương ứng. Sự khác biệt kết quả phải đến **hoàn toàn từ tập card khả thi khác nhau**, tức từ
vật lý — nếu bot có logic chọn nghề, test vô nghĩa.

---

## 8. Claim boundary (bắt buộc trích nguyên văn vào mọi report dùng P3)

- Toàn bộ §7 chứng minh **interface capability**: engine phơi được mọi hành động; agent nhận được
  dữ kiện, tập lựa chọn khả thi và phản hồi; quote settle đúng một lần; chat không settle được.
- **KHÔNG chứng minh** LLM thật sẽ sáng tạo, sẽ chuyên môn hóa, sẽ phát minh tiền/nghề/chính phủ,
  hay sẽ hành xử như người. `ScriptedPromptBot` là **fixture**, không phải mô hình hành vi.
- Nhãn claim: **`design_assumption`** cho mọi tham số mới (quota tool, escrow, expiry);
  **`mechanism_result`** cho kết quả test cơ chế. **Không** `calibrated_fact`, **không**
  `validated_result` (MODEL_CHARTER §2, dòng 41-49).
- Trạng thái đạt được nếu §7 xanh: **`technical-ready`** cho lớp giao diện P3. **Không** phải
  `mechanism-ready` (cần ablation escrow/tool trên nhiều seed) và tuyệt đối **không**
  `empirically-validated`.
- P3 **không** hợp lệ nếu P0 chưa xanh: prompt vẫn nói `6 tháng/90kg/180 công` (prompts.py:241-296)
  trong khi overlay spatial dùng `4 tháng/60kg/120 công` ⇒ mọi fact card/opportunity card dựng trên
  luật sai ⇒ mọi kết luận vô giá trị (Report_v2:76).

---

## 9. Findings (severity / owner / fix bắt buộc)

| # | Severity | Finding | Owner | Fix |
|---|---|---|---|---|
| F1 | **BLOCKING** | Mock không đọc prompt, không chạy tool ⇒ không thể benchmark interface bằng mock (orchestrator.py:68, 274-275, 280-282; gateway.py:76-86) | `test-engineer` + `minds-engineer` | `ScriptedPromptBot` (§7.0) |
| F2 | **BLOCKING** | Transcript replay mù với tool layer ⇒ gate reproducibility xanh giả (transcript.py:20-26, 134-136) | `reproducibility-steward` | `tool_turn` records + `tool_catalog_hash` (§4.4) |
| F3 | **BLOCKING** | Nhãn giai cấp Lớp-5 quay lại prompt Lớp-4 (prompts.py:362-397, tick.py:320-322) — mâu thuẫn trực tiếp acceptance P3 "no job label assigned" | `spec-governor` | Gate `prompt.nhan_giai_cap=false` ở v2 + ADR |
| F4 | **BLOCKING** | ~20 đường từ chối im lặng, tập trung ở chợ/bảng rao (§5.2) ⇒ không được diễn giải "LLM không buôn bán" từ `real60_spatial` | `engine-surgeon` | `KetQua` + reason codes |
| F5 | **HIGH** | `escrow/reservation` = ZERO trong engine ⇒ quote không bảo chứng, accept có thể bốc hơi im lặng (board.py:144) | `engine-surgeon` | `engine/quotes.py` + `KY_QUY:<id>` (§6) |
| F6 | **HIGH** | Tool không authorization: `nghe_ve` bất kỳ ai (world_tools.py:119-136); `get_phan_bo_cua_cai` toàn thế giới cho bất kỳ ai (world_tools.py:152-189) — mâu thuẫn chính tuyên bố boundary ở prompts.py:77 | `minds-engineer` | §4.2 |
| F7 | **HIGH** | Quota tool sai đơn vị: `cong_cu_max_luot` giới hạn **lượt model**, không giới hạn số lần chạm world (providers_real.py:115, 147, 154-161) | `minds-engineer` | quota theo **lần gọi** (§4.2) |
| F8 | **HIGH** | Prompt mớm động cơ (prompts.py:293-296) và mớm chiến lược có biện minh (prompts.py:298-304) — cả hai **lọt lưới** `TU_MOM` hiện tại | `minds-engineer` | cắt; mở rộng checklist (§1.4) |
| F9 | **HIGH** | `mac_ca` là năng lực **đã cài** nhưng **không quảng cáo** (prompts.py:180 vs translate.py:245-248 + board.py:147-150) ⇒ vòng mặc cả A2A coi như không tồn tại | `minds-engineer` | thêm vào catalog |
| F10 | **MEDIUM** | Boundary thủng: dân số/hợp đồng/giá toàn cục (prompts.py:55-68, 86-87; world.py:328-336); `cap_nhat_gia_ky_vong` học giá toàn cục (pricing.py:88-104) | `engine-surgeon` | tier + scenario gate (§2.3) |
| F11 | **MEDIUM** | `LUAT_VAT_LY` mô tả bộ máy chính trị **vô điều kiện** kể cả khi `chinh_tri.bat=false` (prompts.py:285-291) — prompt nói dối về cơ chế không tồn tại; và tiết lộ ngưỡng Gini như một đòn bẩy | `minds-engineer` | gate theo config |
| F12 | **MEDIUM** | `w.rao_vat` phát tán **intent chưa khớp** như tin chợ, kể cả lệnh bị loại (tick.py:203-212 vs market.py:171-179) | `engine-surgeon` | lấy từ lệnh đã vào sổ |
| F13 | **MEDIUM** | Prompt discipline gate render fixture rỗng ⇒ xanh giả; LLM viết "đáng tin" vào `niem_tin` (real.py:295) sẽ tái nhập prompt (prompts.py:538-539) | `test-engineer` | tách scaffolding vs agent-authored (§1.4) |
| F14 | **LOW** | `so_luot_cong_cu` trộn retry-JSON với lượt-tool (orchestrator.py:103) | `minds-engineer` | tách counter |
| F15 | **LOW** | `MAU_KHOI_DAU_THEO_TEN` mồi template **tín dụng** (prompts.py:19-24) | `spec-governor` | `mau_khoi_dau: []` ở v2; arm mồi là treatment có nhãn |

---

## 10. Handoff

- **Verdict:** DESIGN ONLY. Không file production nào bị sửa. File duy nhất được ghi:
  `docs/reviews/P3-autonomy-protocol-design.md`.
- **Không chạy:** LLM/API/mode `real`/`--smoke`/WebSearch/MCP từ xa/`.env`. Không lệnh git thay đổi
  trạng thái. Không đụng `reports/**`, `data/runs/**`.
- **Thứ tự thực hiện bắt buộc:** P0 (prompt/config parity + capability catalog + transcript replay)
  → F1/F2/F3 → §5 (`KetQua`) → §2/§3 (fact + opportunity cards) → §4 (tools) → §6 (`engine/quotes.py`).
  Làm §6 trước §5 sẽ tạo thêm đường từ chối im lặng mới.
- **Next handoff:**
  - `spec-governor`: ADR cho (a) `prompt.nhan_giai_cap` (F3), (b) state ownership + hash gate của
    `w.bao_gia`/`KY_QUY:*` (§6.2, §6.5), (c) boundary tier + scenario gate `thuong_mai.gia_theo_lang`
    (§2.3).
  - `engine-surgeon`: `engine/quotes.py`, `KetQua`, reason codes (§5.2 là danh sách công việc).
  - `minds-engineer`: prompt renderer từ catalog, fact/opportunity cards, tool catalog + quota +
    envelope + authorization.
  - `test-engineer`: `ScriptedPromptBot` (§7.0) **trước**, rồi §7.1–§7.8.
  - `reproducibility-steward`: `tool_turn` transcript + `tool_catalog_hash` + assertion replay (§4.4).
  - `sim-economist` / `adversarial-reviewer` / `qa-verifier`: gate độc lập; đặc biệt phản biện
    quyết định **escrow-khi-post** (§6.5) và cơ chế **xáo card** (§3.3).

---

## 11. Reconciliation — P0.1 đã LANDED giữa chừng (đọc phần này TRƯỚC khi dùng file:line ở trên)

Memo §0–§10 được viết trên cây làm việc **trước** khi P0.1 hạ cánh. Trong lúc soạn memo, các agent
khác đã commit/ghi: `minds/capabilities.py` (**NEW** — capability registry, ADR 0006 §A, bất biến
CAP-1…CAP-4 + `catalog_hash()`), `docs/adr/0006-capability-catalog-and-run-journal.md`,
`engine/journal.py`, và viết lại lớn `minds/prompts.py` (+375/−…), `minds/translate.py` (−352),
`minds/schemas.py`, `minds/transcript.py`.

**Quy tắc dùng memo này:** mọi `file:line` ở §0–§10 tham chiếu cây **trước P0.1**. Bảng dưới là bản
đối chiếu đã **xác minh lại trên cây hiện tại**. Khi hai bên lệch, bảng này thắng.

| Finding | Trạng thái sau P0.1 | Bằng chứng trên cây HIỆN TẠI |
|---|---|---|
| §4.5.1 capability catalog "chưa có" | **SUPERSEDED — đã có** | `minds/capabilities.py`: descriptor một-lần (KeHoach field, schema, to/from_kehoach, engine handler, `kha_dung` scenario gate, `mau_prompt` render từ `World.cfg`, tập mã kết quả) + CAP-1 (bốn chân đủ), CAP-2 (không field mồ côi), CAP-3 (không quảng cáo hàng không có), CAP-4 (anti-teleology), `catalog_hash()` băm nội dung khai báo. **§1.2 (câu "được phép" sinh từ catalog) và P3-I1 giờ là *mở rộng* của CAP-1/CAP-3, không phải phát minh mới** |
| **F9** — `mac_ca` không quảng cáo | **ĐÃ SỬA** | `minds/capabilities.py:1233` `schema_fields=(("ref","str"),("tra_loi",'"chap_nhan"|"tu_choi"|"mac_ca"'),…)`; `:1240` render `\|"mac_ca","sua_doi":{...}} (mặc cả tối đa $vong vòng)`; `:1243` `vong` đọc từ `hop_dong.mac_ca_toi_da_vong`. **Đóng F9.** (Yêu cầu P3-I14 với `tra_loi_bao_gia` vẫn còn hiệu lực khi §6 được cài) |
| **F8** — mớm động cơ + mớm chiến lược | **CÒN NGUYÊN** | `minds/prompts.py:416-418` `[BẠN LÀ NGƯỜI SỐNG] … no bụng hôm nay; an toàn ngày mai …; và vị thế (đất đai, của cải, chữ nghĩa, tiếng thơm)`; `minds/prompts.py:423-429` `VI_DU_QUYET_DINH` vẫn là **chiến lược có biện minh** (`chia_san_luong ty_le 0.4` + `cau_hon`, lý do "…thửa xa cho cấy rẽ lấy 4 phần, và đến tuổi phải tính chuyện gia đình."), và vẫn được ghép vào prompt ở `:451`. **P0.1 đã sửa parity nhưng KHÔNG sửa priming.** F8 là việc của P3.1 |
| **F3** — nhãn giai cấp vào prompt | **CÒN NGUYÊN** | `minds/prompts.py:490` `GIAI_CAP_VN`; `:512-518` `_cau_can_tinh` đọc `w.phan_loai` |
| **F4** — outcome/reason codes | **CÒN NGUYÊN** | `minds/prompts.py:778-780` vẫn render `a.su_co` free-text. Catalog có "tập mã kết quả" trong descriptor ⇒ **điểm bám tốt**: `KetQua.ly_do` phải lấy mã **từ descriptor**, và test §7.5 nên khẳng định mọi mã khai báo trong catalog đều có ≥1 đường sinh ra nó (CAP-5 đề xuất) |
| **F1/F2/F6/F7** — mock không đọc prompt; transcript mù tool; tool không authorization; quota sai đơn vị | **CÒN NGUYÊN** | `minds/capabilities.py` **không** khai báo tool nào (grep `cong_cu` trong file chỉ ra `che_tao_cong_cu`/recipe, không phải world tool). ⇒ **Tool vẫn nằm NGOÀI catalog**: không descriptor, không `catalog_hash`, không authorization, không quota theo lần-gọi, không transcript |
| **F5** — escrow/reservation | **CÒN NGUYÊN — vẫn ZERO** | Không có `engine/quotes.py`; `w.bao_gia` chưa tồn tại |
| **F10/F11/F12/F13/F14/F15** | Cần **xác minh lại line** trên `minds/prompts.py` mới trước khi implement (nội dung finding không đổi) | — |

**Việc P3 phải làm thêm vì P0.1 đã có catalog (cơ hội, không phải xung đột):**

1. **Đưa world tool vào chính `minds/capabilities.py`** (hoặc một registry song sinh cùng khuôn):
   mỗi tool là một descriptor với `ten`, `schema_args`, `authorization(w, aid, args) -> bool`,
   `quota`, `ma_loi`, `nguon` (tier §2.3), `read_only=True`. Khi đó `catalog_hash()` **tự động** phủ
   luôn tool ⇒ **F2 được vá gần như miễn phí** (`tool_catalog_hash` = `catalog_hash()`), và CAP-3
   ("không quảng cáo hàng không có") áp luôn cho tool.
2. **Đề xuất CAP-5 (NEW invariant):** mọi `outcome code` khai báo trong descriptor phải có ≥1 đường
   engine sinh ra nó, **và** mọi đường từ chối trong engine phải phát một code **có trong**
   descriptor. Đây chính là §5.2 dưới dạng bất biến cưỡng chế bằng test — nó biến bảng ~20 "từ chối
   im lặng" thành một gate không thể lách.
3. **Đề xuất CAP-6 (NEW invariant):** descriptor của `dang_bao_gia`/`tra_loi_bao_gia`/`huy_bao_gia`
   phải có `kha_dung(w) = thuong_mai.bao_gia.bat` ⇒ scenario gate của §6 đi qua đúng cơ chế P0.1,
   không đẻ cổng riêng.
4. **`ScriptedPromptBot` (§7.0) nên parse catalog, không parse prompt bằng regex**: bot đọc
   `capabilities` để biết action nào `kha_dung`, rồi **chỉ dùng dữ kiện xuất hiện trong prompt/tool
   output** để điền tham số. Như vậy test 7.8 vẫn không tautology mà lại bền với thay đổi render.
