# SPEC.md — THÓC v3 (bản chốt)
*Mô phỏng 300 năm của một nền kinh tế khép kín bằng agent LLM. Nguồn chân lý duy nhất về
thiết kế. Code mâu thuẫn SPEC → SPEC thắng. SPEC im lặng → chọn phương án đơn giản nhất đúng
nguyên tắc tự phát, ghi DECISIONS.md.*

> **⚠️ SUPERSEDED một phần (2026-07-12).** Xem `docs/MODEL_CHARTER.md` + `docs/adr/0001`.
> Các quyết định §0 bị điều chỉnh: row 1 ("không nhà nước") và row 9 ("engine không chứa định
> chế có tên") → nay là *cổng định chế minh bạch* + scenario-gate (ADR §B/§C); row 10 (hiệu
> chỉnh tới nhãn công-nghiệp-hóa 160–280) → **không còn là tiêu chí khoa học** (ADR §E). Phần
> vật lý/hợp đồng/ledger/replay/observatory vẫn hiệu lực. `preindustrial_closed_v1` giữ SPEC
> này làm legacy; `agrarian_transition_v1` theo charter.

## 0. Quyết định đã chốt

| # | Quyết định |
|---|---|
| 1 | Không nhà nước, không ngân hàng trung ương. |
| 2 | Bản vị thóc từ t0. Tiền kim loại KHÔNG được cài sẵn: quặng đồng là tài nguyên vật lý, "xu" là hàng chế tác; việc xã hội có dùng xu làm tiền hay không là kết quả tự phát. |
| 3 | Đất khởi đầu công hữu; homestead (canh tác 2 tick liên tiếp → sở hữu). Tổng đất cố định. |
| 4 | 600 tick × 6 tháng = 300 năm. Dân số tự kìm hãm bởi kinh tế (không trần cứng). Có thị trường bất động sản. |
| 5 | Kiến trúc lai: thẻ chính sách + trigger. |
| 6 | Mọi tier trả JSON tự do theo schema; pipeline sửa JSON phải rất chắc. |
| 7 | Run đối chứng rule-bot cùng seed. |
| 8 | `.env`: `GEMINI-API-KEY-1..n` + `NINE_ROUTER_*`. `LLM_MODE=mock` mặc định; mock hoàn hảo trước khi call thật. |
| 9 | **Nguyên tắc tự phát triệt để**: engine chỉ có VẬT LÝ + 3 NGUYÊN TỐ (hợp đồng, pháp nhân, sáng chế). Mọi định chế — ngân hàng, doanh nghiệp, bảo hiểm, thị trường cổ phần, "công nghiệp hóa" — chỉ tồn tại như NHÃN do đài quan sát dán lên cấu trúc đo được. Engine không được chứa định chế có tên. |
| 10 | Công nghiệp hóa là kết quả MONG ĐỢI chứ không bảo đảm: ~~hiệu chỉnh `research.yaml` bằng mock để seed trung vị đạt nhãn trong khoảng năm 160–280~~ **(SUPERSEDED — ADR 0001 §E: KHÔNG còn là tiêu chí khoa học; chỉ là legacy regression label trên `preindustrial_closed_v1`, không áp cho `agrarian_transition_v1`)**. Xã hội thất bại công nghiệp hóa là một phát hiện hợp lệ. |
| 11 | Model routes thật (mục 4.1): T0 gemma-4-31b-it (key); T1 gemini-3.1-flash-lite (key, tràn sang gc/…-preview qua 9router); T2 gc/gemini-2.5-flash; T3 gc/gemini-2.5-pro; T4 gc/gemini-3-flash-preview. |

Sản phẩm: (a) thống kê phân bố tài sản theo giai cấp qua 300 năm (giai cấp = nhãn tính từ số
liệu); (b) video timelapse từ log; (c) open source, mọi tham số trong YAML.

---

## 1. Kiến trúc

```
run.py
  ▼
ENGINE (thuần Python, tất định, không biết LLM là gì)
  world • ledger(sổ kép) • parcels • market(chợ generic mọi tài sản)
  board(bảng rao hợp đồng) • contracts(văn phạm + thi hành + cưỡng chế)
  entities(pháp nhân + cổ phần) • research(sáng chế + khuếch tán)
  production • demography • health • education • audit(FlowRegistry)
  ▲ intents đã validate                 │ WorldView + triggers
MINDS: triggers → batching → prompts → GATEWAY → repair → validate → intents
  GATEWAY: aistudio | ninerouter | mock | replay ; keypool ; token-bucket ; budget guard
TOOLS: audit, replay, analyze, session_report      VIZ: dashboard, render_video
OBSERVATORY: dán nhãn định chế + milestones + chronicle (chỉ ĐỌC log, không chạm world)
```

Engine chạy hoàn chỉnh không cần minds (mode rulebot). Observatory/viz chỉ đọc.

---

## 2. Thế giới (vật lý — phần DUY NHẤT được phép scripted)

### 2.1 Không gian
Map 30×30 = 900 ô, sinh theo seed: `ruong` (~350, màu mỡ 0.6–1.4, ven sông +0.2), `rung`
(gỗ), `doi` (trong đó 2 ô `mo_dong` chứa quặng), `song`. Làng = cụm dân cư; t0 có 1 làng;
`di_cu` cho phép lập làng mới khi còn đất công xa (dân tự quyết, không ngưỡng kịch bản —
chỉ ràng buộc vật lý: phải có đất trống). Mỗi làng có 1 chợ + 1 bảng rao.
**Đồ thị xã hội**: gia đình, láng giềng ≤3 ô, từng-giao-dịch, đồng-hợp-đồng, ân oán
(vi phạm hợp đồng → trọng số âm). Dùng cho: thứ tự tiếp cận bảng rao/chợ, danh sách ứng viên
hôn nhân, lan tin đồn giá (làng khác chỉ biết qua tin đồn nhiễu ±15%).

### 2.2 Thời gian & thời tiết
Tick 6 tháng; lẻ = mùa mưa (gieo–gặt), chẵn = mùa khô (nông nhàn). 600 tick.
Thời tiết/năm seeded: được mùa (p .2, ×1.25) / thường (.6, ×1.0) / hạn–lũ (.2, ×0.55).
Đây là ngẫu nhiên ngoại sinh DUY NHẤT.

### 2.3 Tài sản
`thoc(kg)`, `cong(ngày công — sinh mỗi tick theo health, không tích trữ)`, `dat(thửa)`,
`nha`, `cong_cu` (hao mòn 5%/tick dùng), `go`, `quang_dong`, `xu` (chế tác từ quặng),
`hang chế tác` (template sinh từ blueprint — 2.5), `co_phan(entity)` (token chuyển nhượng),
`vi_the_hop_dong` (bên có của một hợp đồng — chuyển nhượng được), `dich_vu` (dạy, chữa bệnh).
Mọi metrics quy giá về kg thóc (theo giá chợ gần nhất).

### 2.4 Bảo toàn — FlowRegistry (điều luật #1)
Mọi luồng sinh/hủy tài sản phải đăng ký nguồn: thóc {+gặt, −ăn, −hao_kho 3%/tick, −giống};
gỗ {+khai_thác, −xây/chế_tác}; quặng {+khai_mỏ, −chế_tác}; xu {+đúc(1 quặng+công→10 xu),
−không có sink}; công {+sinh_mỗi_tick, −dùng, −bốc_hơi_cuối_tick}; hàng chế tác {+recipe,
−tiêu_dùng/hao_mòn}. `audit` đối chiếu tổng từng tài sản với registry SAU MỖI TICK; đất:
tổng thửa const, mỗi thửa đúng 1 chủ (người/pháp nhân) hoặc công. Lệch → raise, dừng.

### 2.5 Sản xuất
- Nông: gieo 60kg giống/thửa mùa mưa; gặt = 600kg × màu_mỡ × thời_tiết × tool_mult ×
  health_mult × skill(E). Một người tự canh tối đa 3 thửa (hiệu suất 1 / .85 / .7 — tạo nhu
  cầu thuê lao động tự nhiên).
- Khai thác: gỗ (ô rừng), quặng (ô mỏ) — tốn công, cần công cụ.
- Chế tác: recipe vật lý cố định cho hàng cơ bản (công_cụ = 60 công + 2 gỗ; nhà = 120 công +
  6 gỗ; xu = 1 quặng + 5 công → 10 xu). Hàng MỚI: chỉ qua blueprint (2.5-R&D, mục 3.5).
- Máy: một loại công cụ lớn (recipe: 10 gỗ + 8 quặng/xu + 200 công + cần blueprint lĩnh vực
  `cong_cu_may_moc`), gắn vào thửa/xưởng, nhân năng suất CÔNG của những người làm cho cùng
  chủ sở hữu máy — hạt giống vật lý của xưởng, nhưng "xưởng" không phải khái niệm engine.
- Ngày công/tick = 180 × health/100; phân bổ (ruộng nhà / hợp đồng góp công / học / xây /
  khai thác / nghiên cứu / buôn chuyến) từ thẻ chính sách + intents.

### 2.6 Nhu cầu, sức khỏe, vô gia cư
Người lớn 90 kg thóc/tick, trẻ em 45. Đói → health −(tối đa 25)/tick; đủ → +10 (trần 100);
health<20 → p chết 35%/tick. Không nhà (không sở hữu/thuê/ở nhờ) → mùa mưa −10 health +
cờ `vo_gia_cu`. Hàng "tiện nghi" (blueprint) cộng health nhỏ khi tiêu dùng.

### 2.7 Nhân khẩu & vòng đời
t0: 50 người lớn độc thân 16–28 tuổi (52% nữ), persona seeded, mỗi người 200kg thóc, 0 đất.
Trưởng thành 16. Cầu hôn = intent, bên kia trả lời tick sau; engine chặn cận huyết; ứng viên
đưa vào prompt theo đồ thị xã hội. Sinh: p = 0.22 × an_ninh_lương_thực × ý_định(0/.5/1, LLM).
Tử vong Gompertz (q20 .005, q60 .03, q75 .12 nội suy) + đói + sinh nở 2% (giảm nếu mua dịch
vụ chữa bệnh từ người có blueprint y tế). Trẻ 10 tuổi góp 30% công. Dân số nổi hoàn toàn.

### 2.8 Thừa kế
Trigger `viet_di_chuc` ở 50 tuổi & khi health<30: LLM phân bổ tự do (%, quy tắc, mô tả người
nhận). Không di chúc → chia đều con → vợ/chồng → đất về công. Thi hành đúng sổ (nợ thừa kế
tối đa bằng tài sản nhận). Chuẩn mực thừa kế của xã hội là một output.

### 2.9 Giáo dục (vật lý của việc học)
Bậc E1–E4. Tiến độ: mỗi tick "được dạy" cần (a) người dạy E ≥ bậc mục tiêu phân bổ công dạy
cho mình (qua hợp đồng dịch vụ — không có "trường" cài sẵn; trường là thứ ai đó tự tổ chức),
hoặc (b) cha mẹ E≥1 dạy E1 tại nhà; + học viên mất 50% công. Hoàn tất K tick (E1:2, E2:4,
E3:6, E4:8) → thăng bậc. Biết chữ (E1) là điều kiện vật lý để SOẠN hợp đồng văn bản (3.2).

---

## 3. Ba nguyên tố (toàn bộ "kinh tế" của engine — không định chế có tên)

### 3.1 Chợ generic + bảng rao
- **Chợ** (mỗi làng, mỗi tick): call auction cho MỌI tài sản chuẩn hóa được (thóc, gỗ, quặng,
  xu, công cụ, hàng chế tác, cổ phần của bất kỳ entity, vị thế hợp đồng): sắp bid giảm/ask
  tăng, giá p* tối đa hóa khối lượng, khớp một phần, pro-rata tại biên, tie-break seeded.
  Engine không bao giờ can thiệp giá. Đất/nhà (dị biệt): niêm yết ask từng thửa + sealed bid,
  cao nhất ≥ ask thắng; thấp hơn → trigger chủ hạ giá/rút.
- **Bảng rao**: nơi đăng ĐỀ NGHỊ HỢP ĐỒNG công khai (hoặc gửi đích danh). Người khác thấy
  trên prompt (thứ tự theo quan hệ), trả lời chấp nhận / từ chối / mặc cả (sửa tham số, gửi
  lại). Khớp đầu tiên thắng (seeded theo quan hệ). Buôn chuyến giữa làng: intent
  `buon_chuyen` — mua làng A bán làng B tick sau, phí 2%/khoảng cách.

### 3.2 HỢP ĐỒNG — văn phạm điều khoản (executor phải thi hành được MỌI tổ hợp hợp lệ)
```
HopDong {
  cac_ben: [id...]            # 2..N (người hoặc pháp nhân)
  hinh_thuc: mieng | van_ban  # văn bản: người soạn cần E≥1
  thoi_han: K tick | den_khi_huy(bao_truoc j tick)
  the_chap: [tai_san...]      # CHỈ hiệu lực với văn bản
  dieu_khoan: [Clause...]
}
Clause (9 loại):
 1 chuyen_giao_dinh_ky   {tu, den, tai_san, so_luong, moi_n_tick}
 2 chuyen_giao_mot_lan   {tu, den, tai_san, so_luong, tai: ky_ket|dao_han|tick_T}
 3 quyen_su_dung         {tai_san: thua|nha|cong_cu|may|blueprint, tu, den}
 4 gop_cong              {tu, den, so_cong_moi_tick}
 5 chia_san_luong        {nguon: thua|hoat_dong_cua_ben, ty_le, den}
 6 chia_loi_nhuan        {entity, theo_co_phan | ty_le: {ben: %}}
 7 dieu_kien_su_kien     {neu: han_lu|chet(X)|vo_no(X)|gia(tai_san)≷nguong, thi: clause 1|2}
 8 hoan_tra_theo_yeu_cau {tu, den, tai_san, tran_rut_moi_tick}
 9 khi_pha_vo            {phat: clause 2 | xiet_the_chap | khong}
```
- **Thi hành**: engine chạy clause định kỳ mỗi tick (bước 7 pipeline); bên thiếu tài sản để
  thực hiện nghĩa vụ = VI PHẠM.
- **Cưỡng chế**: hợp đồng miệng — vi phạm chỉ bị trừ uy tín (cạnh đồ thị xã hội âm, tin đồn
  lan); văn bản — engine thi hành `khi_pha_vo` (xiết thế chấp theo giá chợ gần nhất, thừa
  hoàn lại). → Sức mạnh của "pháp luật" trong xã hội này tăng theo tỷ lệ biết chữ, hoàn toàn
  nội sinh.
- **Từ văn phạm này ghép ra** (không cái nào là mã riêng): làm thuê (4+1), tá điền (3+5 hoặc
  3+1), vay (2+2+9), gửi-tiền-kiểu-ngân-hàng (2+8+1), bảo hiểm mùa màng (1+7), hùn hạp
  (4+4+6), li-xăng sáng chế (3+1), niên kim dưỡng già (2+1), của hồi môn, v.v. Engine KHÔNG
  biết các tên này.
- **Bắt chước**: prompt mục "các dạng hợp đồng đang lưu hành trong làng" = mẫu THẬT rút từ
  hợp đồng đang hiệu lực (ẩn danh hóa, top-k theo tần suất). Khởi đầu chỉ 2 mẫu tối giản
  (đổi công lấy thóc một lần; cho mượn có hoàn trả). Chuẩn mực lan như văn hóa.

### 3.3 PHÁP NHÂN (entity)
- `lap_phap_nhan {ten (LLM đặt), co_phan: {id: %}, von_gop: [tài sản], dieu_le: quy tắc chia
  lợi nhuận/giải thể}`. Entity có ledger riêng; sở hữu được đất/máy/blueprint; ký hợp đồng;
  bị xiết như người.
- Quản trị: quyết định nhân danh entity do LLM của (nhóm) cổ đông giữ >50% đưa ra — prompt
  đóng vai "với tư cách người điều hành X"; entity là một "agent phái sinh" dùng tier của
  người điều hành, có trigger riêng (đến hạn nghĩa vụ, thua lỗ, bị rút...).
- Cổ phần = token: bán trên chợ, thế chấp, thừa kế. Phá sản (nghĩa vụ > tài sản khả thi) →
  engine thanh lý: bán tài sản, trả theo thứ tự nghĩa vụ, cổ đông nhận phần còn (trách nhiệm
  hữu hạn trong vốn góp — ghi rõ trong README như MỘT lựa chọn thiết kế của luật chơi).

### 3.4 (đã gộp vào 3.1–3.3 — mục để trống có chủ đích: KHÔNG có cơ chế tín dụng/ngân hàng riêng)

### 3.5 SÁNG CHẾ — R&D, blueprint, khuếch tán (`config/research.yaml`)
- Hành động `nghien_cuu {linh_vuc, cong, thoc}` (cá nhân hoặc entity). 7 lĩnh vực:
  `nong_nghiep, cong_cu_may_moc, luu_kho, van_chuyen, y_te, vat_lieu, che_bien`.
- Điểm nghiên cứu = f(công, thóc, E của người nghiên cứu). Mỗi tick có điểm:
  `p_thanh_cong = 1 − exp(−điểm_tích_lũy / (k0 × (1+mức_hiện_tại_lĩnh_vực)^d))` — lợi suất
  giảm dần, KHÔNG có danh sách phát minh định sẵn, KHÔNG có thứ tự bắt buộc.
- Thành công → **blueprint** {lĩnh_vực, độ_lớn ~ LogNormal(config) — ENGINE rút, LLM không tự
  đặt số, tên do LLM đặt, chủ sở hữu}. Hiệu ứng: nhân (1+độ_lớn) vào tham số vật lý lĩnh vực
  đó CHO NGƯỜI ÁP DỤNG (li-xăng qua clause quyền_sử_dụng, hoặc mua đứt).
- Lĩnh vực `che_bien` sinh **hàng mới**: engine rút recipe (inputs từ {thóc, gỗ, quặng, vải…})
  + hiệu ứng từ menu {tiện_nghi(+health nhỏ) | công_cụ(+năng suất) | lưu_kho(−hao hụt) |
  vật_liệu}; LLM đặt tên và tự tiếp thị — cầu hoàn toàn do agent khác quyết định mua.
- **Khuếch tán**: chi phí nghiên cứu cùng lĩnh vực giảm 0.9^n theo số blueprint đang lưu hành
  (sàn 0.4) — tri thức rò rỉ; sao chép rẻ hơn phát minh.
- **Không có "kỷ nguyên"**: `tri_thuc = Σ log(1+độ_lớn blueprint) + a × tỷ_lệ_biết_chữ`;
  vượt ngưỡng config → **sàn tier model toàn dân tăng** (T0→T1→T2). Xã hội không đầu tư thì
  sàn không tăng — "loài người khôn lên" giờ là nội sinh.

---

## 4. Tầng trí tuệ

### 4.1 Thang model — routes thật (`config/models.yaml`; gateway hỗ trợ nhiều route/tier)
| Tier | Điều kiện | Routes (ưu tiên trước → sau) |
|---|---|---|
| T0 | mặc định (mù chữ) | aistudio `gemma-4-31b-it` |
| T1 | E1 | aistudio `gemini-3.1-flash-lite` → ninerouter `gc/gemini-3.1-flash-lite-preview` |
| T2 | E2 | ninerouter `gc/gemini-2.5-flash` |
| T3 | E3 | ninerouter `gc/gemini-2.5-pro` |
| T4 | E4 | ninerouter `gc/gemini-3-flash-preview` |
`tier(agent) = max(sàn_tri_thức, tier_theo_E)`. Việc nền: nén hồi ký = gemma-4-31b-it;
chronicle = gemini-3.1-flash-lite. Hoán đổi T3/T4 = sửa 2 dòng yaml (ghi chú sẵn trong file).

### 4.2 Thẻ chính sách
Pydantic patch-able, engine thi hành mỗi tick tới khi thay. Trường: bán/mua (tài sản → tỷ lệ,
giá sàn/trần), du_tru_muc_tieu, phan_bo_cong mặc định, điều kiện tự động trả lời hợp đồng
quen thuộc (vd "nhận làm công nếu ≥ 4kg thóc/công"), ý_định_sinh_con, ưu tiên học cho con,
ngưỡng rao đất/nhà. Thẻ KHÔNG được tự ký hợp đồng mới phức tạp — cái đó cần LLM (trigger).

### 4.3 Trigger
Sắp đói (dự trữ < 1 tick); giá thóc lệch >±30% TB 4 tick; nhận đề nghị hợp đồng/mặc cả;
đối tác vi phạm; nghĩa vụ đáo hạn; nhận thừa kế/tang; được cầu hôn; tuổi 16/30/50; entity
mình điều hành có sự kiện; blueprint mới xuất hiện trong làng; đất công trống kề bên;
thất nghiệp 2 tick; **định kỳ 1 lần/4 tick**. Kỳ vọng 30–40% dân/tick.

### 4.4 Batching & chống đồng nhất
≤8 agent cùng tier cùng làng/call; khối chung + khối riêng; mảng JSON theo id, validate độc
lập. Chống bầy đàn: xáo batch mỗi tick, temperature 0.9, chỉ thị persona, nhiễu seeded ±10%
vào tham số số, không cho thấy quyết định người cùng batch. Test heterogeneity bắt buộc.

### 4.5 Persona & ký ức
Persona 5 trục 1–9 bất biến, thừa hưởng TB cha mẹ ± đột biến 2 (seeded) — rulebot/mock dùng
chung. Hồi ký ≤250 token nén mỗi 4 tick; gia huấn ≤100 token viết lúc lập di chúc, truyền đời.

### 4.6 Prompt (tiếng Việt — Phụ lục A)
System: nhân thân + persona + hồi ký + gia huấn + **mô tả thế giới SINH ĐỘNG TỪ TRẠNG THÁI
THẬT** (tài sản đang tồn tại, các dạng hợp đồng đang lưu hành, mức tri thức) — không còn
"kỷ nguyên" kịch bản; luật: "chỉ biết những gì làng bạn biết"; schema; "chỉ trả JSON".
User: tình hình chung (giá 4 tick, thời tiết, bảng rao, tin đồn) + riêng (tài sản, hợp đồng
hiệu lực, quan hệ, trigger) + **menu nguyên tố** (đề nghị/trả lời hợp đồng kèm văn phạm 9
clause + mẫu đang lưu hành, lập pháp nhân, chợ, phân bổ công, nghiên cứu, cầu hôn, di chúc,
di cư) — menu là NGỮ PHÁP, không phải danh mục định chế.

---

## 5. Schema quyết định v3

```python
class QuyetDinh(BaseModel):
    id: str
    the_chinh_sach: PolicyPatch | None = None
    hanh_dong: list[HanhDong] = []
    ly_do: str = ""
    model_config = ConfigDict(extra="allow")   # trường lạ → unrecognized log
```
`HanhDong.loai` ∈ (15 nguyên tố): `de_nghi_hop_dong{hop_dong, cong_khai|den:id}`,
`tra_loi_hop_dong{ref, chap_nhan|tu_choi|mac_ca:{sua_doi}}`, `don_phuong_pha_vo{ref}`,
`lap_phap_nhan{...}`, `quyet_dinh_entity{entity, hanh_dong_con}`, `niem_yet{tai_san, gia}`,
`dat_lenh{mua|ban, tai_san, sl, gia}`, `tra_gia_dat{thua, gia}`, `phan_bo_cong{...}`,
`khai_hoang{thua}`, `xay{nha|che_tac|may}`, `nghien_cuu{linh_vuc, cong, thoc}`,
`buon_chuyen{...}`, `cau_hon/tra_loi_cau_hon`, `viet_di_chuc{...}`, `di_cu{lang}`.
Tham số sai/loai lạ → bỏ + ghi `unrecognized_intents.jsonl` (mỏ "ý định mới lạ" — đọc định kỳ,
nếu nhiều agent cùng muốn một nguyên tố còn thiếu thì đó là phát hiện thiết kế, KHÔNG tự thêm
cơ chế giữa run).

---

## 6. Pipeline một tick (thứ tự chuẩn)
1 `bat_dau`: tuổi+1, thời tiết. 2 `trigger_scan`. 3 `quyet_dinh`: batch → gateway → repair →
validate → intents (không nghĩ → thẻ). 4 `bang_rao`: khớp đề nghị/trả lời/mặc cả hợp đồng.
5 `san_xuat`: phân bổ công, gieo/gặt, khai thác, chế tác, xây, R&D (roll blueprint), buôn.
6 `cho`: auction mọi tài sản + sealed bid đất/nhà. 7 `thi_hanh_hop_dong`: clause định kỳ,
đáo hạn, phát hiện vi phạm, cưỡng chế/xiết, uy tín; entity: chia lợi nhuận, kiểm tra mất khả
năng thanh toán → thanh lý. 8 `tieu_dung_suc_khoe`: ăn, hao kho, health, vô gia cư.
9 `nhan_khau`: cưới, sinh, chết, di chúc/thừa kế. 10 `giao_duc_tri_thuc`: tiến độ E, thăng
tier, cập nhật tri_thuc & sàn model. 11 `ket_toan`: **audit FlowRegistry (assert)** → metrics
→ observatory (nhãn + milestones) → chronicle (mỗi 20 tick) → checkpoint (mỗi 10) → budget.

---

## 7. Gateway LLM

### 7.1 Nạp key — parse `.env` trực tiếp bằng regex (tên biến có gạch ngang):
`^\s*(GEMINI[-_]API[-_]KEY[-_](\d+))\s*=\s*(.+)$` (i) → pool AI Studio;
`NINE[-_]?ROUTER[-_]API[-_]KEY`, `NINE[-_]?ROUTER[-_]BASE[-_]URL`; `LLM_MODE`. Log chỉ hiện
sha256[:8] của key.

### 7.2 Provider & routes
- aistudio: `POST …/v1beta/models/{model}:generateContent?key=…` (httpx), token từ
  `usageMetadata`. — ninerouter: `POST {BASE_URL}/chat/completions` chuẩn OpenAI, Bearer;
  model id GIỮ NGUYÊN tiền tố `gc/`; token từ `usage`; health-check `{BASE_URL}/models` khi
  vào mode real. — mock (7.5) — replay (đọc response theo call_id).
- **Routes/tier** (models.yaml): thử route 1 (còn ngân sách) → tràn route 2. T1 nhờ vậy gộp
  ~4.000 (key) + ~2.700 (9router) call/ngày.

### 7.3 Key pool & rate limit
Token-bucket RPM + đếm RPD theo (provider, model, key), persist SQLite `quota_counters`,
reset theo `reset_hour_local`. 429 → cooldown key 60s lũy tiến, thử key khác; hết key →
model coi như cạn. asyncio + semaphore theo provider. tenacity retry ≤2 (mạng/5xx/429).

### 7.4 Budget guard (real)
Trước bước 3: `need[model] = ceil(thinkers_tier/batch)`. Bất kỳ model nào
`remaining × safety_margin < need` → checkpoint, báo cáo, **dừng** (không degrade tier —
không đánh tráo trí thông minh giữa chừng).

### 7.5 MockLLM — PersonaBot (mock phải hoàn hảo trước khi call thật)
- Cùng interface (`LLMRequest{prompt, ctx, tier, schema}` → `LLMResponse`); mock dùng `ctx`
  máy-đọc-được, không parse prompt.
- PersonaBot: heuristic theo persona 5 trục + trạng thái; biết dùng **8 công thức hợp đồng**
  (đổi công–thóc; thuê đất chia sản; thuê đất tô cố định; vay thế chấp; gửi-rút theo yêu cầu;
  hùn hạp lập entity; bảo hiểm mùa màng; li-xăng blueprint) + tham số theo persona; đầu tư
  R&D khi dư dả × trọng_học; lập entity khi cần vốn > tài sản; mua cổ phần khi liều lĩnh;
  p=0.02 hành động "ngẫu hứng" hợp lệ. Seeded (run, agent, tick).
- **Adversarial** `p_malformed` (0.05 chạy thường / 0.15 test): fence, cắt 15% cuối, phẩy
  thừa, quote cong, lời dẫn tiếng Việt, đổi hoa thường key, số "1.000" — áp cả lên JSON hợp
  đồng lồng nhau.
- Token giả lập len/4; latency N(1.2, 0.3) tắt bằng `--fast`.
- **Pipeline sửa JSON (chung mock & real)**: strip fence/văn dẫn → json_repair → pydantic →
  retry 1 lần kèm lỗi validator → fallback (giữ thẻ cũ, không hành động, `fallback=true`).
  Chỉ tiêu: p_malformed=0.15 → fallback_rate < 5%. Metric theo tier trên dashboard.

### 7.6 Ngân sách tham chiếu (số thật ở quotas.yaml)
aistudio/key: gemma-4-31b-it (điền theo trang quota Gemma của bạn — dòng Gemma trước đây rất
rộng), gemini-3.1-flash-lite ~4 RPM / 450 RPD. ninerouter: mỗi model ~2.700/ngày (3 tài
khoản × 1.000 × 0.9). Toàn run ~8–12k call → 4–7 phiên tối.

---

## 8. Dữ liệu
`world.sqlite`: agents, parcels, entities, shares, contracts(+clauses, trạng thái),
blueprints, policy_cards, quota_counters, checkpoints(rng blob), metrics_tick.
`events.jsonl`: sinh, chet, cuoi, gieo, gat, an_doi, khop_cho, niem_yet, ban_dat, homestead,
de_nghi_hd, ky_hd, mac_ca, vi_pham, cuong_che, xiet, huy_hd, lap_entity, chia_loi_nhuan,
pha_san_entity, chuyen_nhuong_co_phan, nghien_cuu, blueprint_moi, hang_moi, li_xang, duc_xu,
di_hoc, thang_E, thang_tier, san_tri_thuc_tang, di_cu, di_chuc, thua_ke, nhan_dinh_che(observatory),
milestone, chronicle. `llm_calls.sqlite`: call_id, tick, tier, provider, model, key_hash,
batch_size, tok_in/out, latency, retries, fallback, raw. Checkpoint mỗi 10 tick;
`tools/replay --verify` so world-hash.

---

## 9. Metrics, giai cấp, Observatory

### 9.1 Classifier giai cấp (mỗi tick, ưu tiên trên xuống; ngưỡng ở world.yaml)
1 `phu_thuoc` (<16 | ≥70 không lao động). 2 `vo_gia_cu`. 3 `chu_xuong` (cổ phần chi phối
entity có ≥3 hợp đồng góp công). 4 `dia_chu` (đất ≥p90 & ≥50% thu nhập 4-tick từ clause
quyền_sử_dụng/chia_sản đất). 5 `phu_nong` (đất ≥p75 & mua công người khác). 6 `thuong_nhan`.
7 `tho_thu_cong` (thu nhập chính từ chế tác). 8 `gioi_dich_vu` (dạy/chữa). 9 `cong_nhan`
(≥60% thu nhập từ góp công cho entity/người khác, có việc). 10 `ta_dien` (≥50% diện tích
canh là đất người khác). 11 `co_nong` (không đất, làm thuê bấp bênh). 12 `trung_nong`.
Không ai "sinh ra là" gì — nhãn tính lại từ sổ sách.

### 9.2 Nhãn ĐỊNH CHẾ (observatory — tách khỏi giai cấp; một người/entity có thể mang nhiều nhãn)
`ngan_hang`: tổng nghĩa vụ hoàn_tra_theo_yeu_cau ≥ ngưỡng từ ≥5 chủ nợ. `bao_hiem`: bán ≥5
hợp đồng dieu_kien_su_kien đang hiệu lực. `xuong/doanh_nghiep`: entity ≥3 góp công.
`thi_truong_co_phan`: ≥k giao dịch cổ phần/năm trên chợ. `tien_te_hoa`: ≥50% giá trị khớp
chợ thanh toán bằng xu. **`cong_nghiep_hoa`** (cột mốc đo được, KHÔNG phải giai đoạn): tỷ
trọng công phi nông >40% VÀ ≥5 máy hoạt động VÀ ≥25% lao động làm cho entity ≥5 người —
observatory TUYÊN BỐ khi và chỉ khi số liệu chạm. Mọi ngưỡng ở world.yaml.

### 9.3 Metrics mỗi tick
Gini (của cải/đất/thu nhập); % của cải theo giai cấp & decile; top-10%; HHI đất; giá &
lương thực tế (kg thóc/công); lãi suất ngầm (từ clause vay đang lưu hành); kg thóc/người;
dân số & tháp tuổi; % biết chữ; phân bố tier; vô gia cư; tổng giá trị hợp đồng hiệu lực theo
mô-típ (auto-cluster theo tổ hợp clause!); số entity & tổng vốn hóa cổ phần; tri_thuc;
fallback_rate; call/token theo model.

### 9.4 Chỉ số thế hệ (`tools/analyze`)
Ma trận dịch chuyển giai cấp cha→con (cha lúc con 16 × con lúc 40; 12×12; xuất mỗi 50 năm) —
kết quả đinh. β thừa kế tài sản; tương quan tier cha–con; thu nhập theo tier (kiểm soát đất).

### 9.5 Milestones & chronicle
Lần-đầu: hợp đồng văn bản đầu, vi phạm–cưỡng chế đầu, mô-típ gửi-rút đầu (→ nhãn ngân hàng),
entity đầu, cổ phần đổi chủ đầu, blueprint đầu, hàng mới đầu (kèm tên LLM đặt), máy đầu,
nhãn xưởng đầu, bảo hiểm đầu, xu dùng >50%, làng mới, sàn tri thức tăng, NHÃN CÔNG NGHIỆP
HÓA, người mất hết đất đầu, gia tộc giàu nhất bị soán. Regime-shift: |z|>3 Gini/giá cửa sổ
20 tick. Kỷ lục: giàu nhất mọi thời, phá sản lớn nhất, dòng họ bền nhất, entity thọ nhất.
Chronicle: mỗi 20 tick, model chronicle đọc top sự kiện + delta metrics → đoạn sử ký ≤120 từ.

---

## 10. Dashboard & Video
Dashboard (streamlit): Bản đồ (parcel màu giai cấp chủ, chấm agent theo tài sản, icon máy) —
Kinh tế (Gini, stacked wealth-share, giá, lương thực tế, vốn hóa cổ phần) — Xã hội (dân số,
tháp tuổi, biết chữ, tier, tri_thuc) — Hợp đồng (mô-típ đang lưu hành + khối lượng — cửa sổ
nhìn định chế tự phát) — Token/Quota — Dòng sự kiện.
Video (`viz/render_video.py`, offline từ events.jsonl): pygame headless 1080×1920, bản đồ
giữa, "Năm N", panel stacked wealth-share + dân số, caption milestones/chronicle; 2 frame/tick,
ffmpeg 30fps; flags `--last-years --fps --out`. Cuối phiên tự render clip đoạn vừa chạy.

## 11. Vận hành
Như v2: `run.py --mode {rulebot|mock|real} --years/--ticks --seed --run-name --fast
--until-budget --i-am-sure --smoke`; SIGINT → checkpoint sạch; resume theo run-name;
`reports/session_<n>.md` + clip; `--smoke` = 1 call/route (≤12 call).
`tools/{audit,replay --verify,analyze}`; `streamlit run thoc/viz/dashboard.py`.

## Phụ lục A — khung prompt
System: `Bạn là {ten}, {tuoi} tuổi, làng {lang}, năm {nam}. Tính cách: {persona}. Gia huấn:
"{gia_huan}". Hồi ký: {hoi_ky}. Thế giới bạn biết: {mo_ta_sinh_tu_trang_thai: tài sản tồn
tại, các kiểu thỏa thuận đang lưu hành, hiểu biết chung}. Bạn chỉ biết những gì làng bạn
biết. Hãy quyết định như CHÍNH BẠN, nhất quán với tính cách và ký ức riêng, kể cả khi khác
mọi người. Chỉ trả về DUY NHẤT một JSON đúng schema: {schema}`
User: `[TÌNH HÌNH CHUNG] giá, thời tiết, bảng rao, tin đồn… [CỦA BẠN] tài sản, hợp đồng hiệu
lực, quan hệ, trigger… [BẠN CÓ THỂ] 15 nguyên tố + văn phạm hợp đồng + mẫu đang lưu hành…`
Batch: N khối `[NGƯỜI i]`, trả mảng JSON, "mỗi người quyết định độc lập".

## Phụ lục B — ví dụ quyết định (đề nghị hợp đồng thuê đất chia sản)
```json
{"id":"A017",
 "hanh_dong":[{"loai":"de_nghi_hop_dong","den":"A031",
   "hop_dong":{"cac_ben":["A017","A031"],"hinh_thuc":"van_ban","thoi_han":8,
     "the_chap":[],
     "dieu_khoan":[{"loai":"quyen_su_dung","tai_san":"thua:D4","tu":"A017","den":"A031"},
                   {"loai":"chia_san_luong","nguon":"thua:D4","ty_le":0.4,"den":"A017"},
                   {"loai":"khi_pha_vo","phat":"huy_quyen_su_dung"}]}},
  {"loai":"phan_bo_cong","ruong_nha":0.7,"nghien_cuu":{"linh_vuc":"luu_kho","ty_le":0.3}}],
 "ly_do":"Đất D4 xa nhà, cho A031 cấy rẽ lấy 4 phần, còn công dồn tìm cách chống mọt kho."}
```
