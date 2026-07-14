# ADR 0005 — Không gian kinh tế, sinh kế đa dạng, tài nguyên tái tạo (T13)

- Status: **Implemented core + test-enforced** (2026-07-13; original design 2026-07-12)
- Context: `docs/MODEL_CHARTER.md` §3 (5 lớp — Lớp-1 vật lý, Lớp-2 kế toán sổ kép, Lớp-3 định
  chế bật/tắt, Lớp-4 hành vi chỉ-trả-intent, Lớp-5 quan sát chỉ-đọc), §4 (định nghĩa tự
  phát), §5 (cổng định chế minh bạch + anti-teleology); `docs/adr/0001` §A (invariant), §B
  (cổng 5 điều kiện), §C (anti-teleology), §D (determinism phủ state mới), §G (shock
  scenario-flag default OFF); `docs/adr/0002` (BehaviorPolicy chỉ trả intent); `docs/adr/0003`
  (household/market/land, homestead, rent clause, price/rent tách); `docs/adr/0004` (credit
  claim/commodity money/fiscal, cổng §5, migration không phá hash); `TASKS.md` §7 T13.
- Deciders: research-planner + agrarian-economist + model-architect (design). Core implementation
  (two-bank/ferry/clearing, winter crops, wild-chicken pool, care labor, metrics) and local QA are
  complete; empirical calibration remains PENDING.
- Scope guard: Bản thiết kế này đã được triển khai ở engine; nó
  chốt topology/ownership/state/lifecycle/serialization/event-ledger schema, thứ tự tick,
  failure/rollback, cổng scenario, migration, test matrix và phân định **IMPLEMENTED vs NEW**.
  Mọi số nêu ở đây là `design_assumption` (charter §2); không mục nào là bằng chứng thực chứng.

## 0. Nguyên tắc chi phối (không thương lượng — kế thừa charter + ADR 0001/0003/0004)

1. **Overlay tùy chọn, mặc định TẮT.** Toàn bộ cơ chế T13 là overlay của `agrarian_transition_v1`;
   một cờ scenario `khong_gian.bat` (mặc định OFF) + sub-flag. OFF ⇒ mọi code-path T13 no-op ⇒
   `preindustrial_closed_v1`, mọi run cũ, và `agrarian_transition_v1` gốc (không bật overlay)
   giữ NGUYÊN hành vi + world-hash + config-digest (§7, §8).
2. **Ledger-based + behavioral hash đầy đủ.** Asset flow đi qua ledger; mọi state có thể đổi
   tick/prompt sau (kể cả pool commons) vào `World.behavioral_state()`/`world_hash`. Chỉ event,
   metric journal và cache lười xác định từ seed/config/tick được ngoài hash.
3. **Mọi flow có counterpart + FlowRegistry.** Mọi mint/burn qua `DongSinhHuy`/`Transaction` với
   `luong` đã `dang_ky_flows` (`world.py:415`); mọi chuyển tài sản là `ledger.chuyen` cân. Không
   food-mint/xu-mint sau tick 0; không teleport người/hàng.
4. **Random qua `w.rng`; ordering tất định.** Mọi ngẫu nhiên `w.rng.get(subsystem, tick)`; mọi
   vòng lặp `sorted(...)` theo id/khóa; policy/LLM KHÔNG mutate World (Lớp-4).
5. **Anti-teleology / không nghề cố định.** KHÔNG hardcode vị trí/ID người hưởng lợi, KHÔNG gán
   nghề vĩnh viễn, KHÔNG class-based branching. "Lái đò", "địa chủ", "thợ", "người chăm trẻ" là
   NHÃN observatory (Lớp-5), không phải object/class engine (§10, cổng §5).
6. **Observation không điều khiển engine.** Metric T13 (Lớp-5) chỉ đọc; agent vẫn được phép suy
   kiệt/thất bại khi mọi lựa chọn không feasible (§9 negative tests).

---

## 1. Bản đồ nền đã khảo sát (file:line) — IMPLEMENTED, không thiết kế lại

| Chủ đề | Sự thật nền (verified) | file:line |
|---|---|---|
| Sông | Bản đồ CÓ sông: dải dọc uốn quanh trục giữa; ô `loai="song"`, `mau_mo=0` | `worldmap.py:17-20,46-47` |
| Làng | Village gán `p.lang` cho thửa trong `ban_kinh_lang=8` quanh tâm làng | `worldmap.py:62-66`; `world.yaml:6` |
| Khoảng cách | Manhattan `|Δr|+|Δc|`, **BỎ QUA sông** (sông KHÔNG chặn di chuyển) | `worldmap.py:70-71`; `world.py:194-227` |
| Homestead (khai hoang đất công *ruộng*) | Canh ô `ruong` công (`chu is None`) `homestead_tick_lien_tiep=2` mùa mưa liên tiếp ⇒ thành chủ | `production.py:229-238`; `world.yaml:27` |
| Xây nhà + thuê thợ | `nha` recipe 240 công + 8 gỗ > 180 công/người ⇒ CẦN góp công (gia đình hoặc thuê qua clause `gop_cong`) | `production.py:283-302`; `world.yaml:30` |
| Phí vận chuyển | Buôn chuyến liên-làng burn 2%/khoảng-cách qua sink `phi_van_chuyen` — **KHÔNG có người vận hành nhận phí** | `market.py:27-39` |
| Clause thuê đất | `quyen_su_dung` (quyền canh) + `chia_san_luong` (tô chia sản) + `chuyen_giao_dinh_ky` (tô cố định) + `gop_cong` (đổi công) — validate owner, executor đủ | `contracts.py:35-54,138-147,385-397,440-463` |
| Chủ không tự thu tô | Sản xuất chặn non-owner canh trừ khi có `quyen_su_dung`; chủ chỉ nhận qua clause chuyển giao | `production.py:190`, `:140-147` |
| Cá — tài nguyên tái tạo | `ca_ton` stock, `_ca_suc_chua`=Σô-sông×`suc_chua_moi_o_kg`, logistic `ΔS=r·S·(1−S/K)`, CPUE∝S/K, event `danh_ca` | `chan_nuoi.py:141-188`; `world.py:468-471`; `world.yaml:55-62` |
| Gà rừng — **KHÔNG có stock** | `bat_ga` chỉ tốn công (30/con) + cần ô `rung` ⇒ **mint `ga_con` VÔ HẠN** theo lao động; overhunting KHÔNG có hậu quả | `chan_nuoi.py:73-92` |
| Gà rừng → thịt / đàn nuôi | `bat_ga`→`ga_con` (đàn nuôi); `giet_ga`→`thit` | `chan_nuoi.py:73-111` |
| Endowment t0 | `khoi_tao.thoc_moi_nguoi=200` kg PHẲNG/người bất kể tuổi, mint qua flow `khoi_tao` tick 0 | `world.py:505-506`; `world.yaml:123` |
| Calendar | 2 tick/năm; `mua_mua()`=tick%2==1 (canh chỉ mùa mưa), thời tiết theo NĂM=tick//2, tuổi theo tick | `world.py:131-145`; `production.py:181` |
| P2P (A2A) | `nhan_tin` gửi tick này → hòm thư, **GIAO PROMPT TICK SAU** (trễ), cap chống spam, cộng nhẹ quan hệ, KHÔNG chạm ledger | `tick.py:69-85`; `world.py:66-68` |
| Policy Lớp-4 | `REGISTRY` {rulebot, feasible_random, subsistence, adaptive}; chỉ trả `{aid:KeHoach}` | `minds/policies.py:266-271` |
| Cổng scenario mẫu | `_chinh_tri_bat`/`_fiscal_bat` = `cfg.get(path, default)`; OFF ⇒ no-op ⇒ hash bất biến | `politics.py:19-35,271,306,324` |
| Overlay config | `load_config(overlays)` deep_merge; `run.py` nạp `scenario_overlay(scenario)` | `config.py:57-93`; `run.py:139-145` |

> **Đính chính giả định T13:** gate 5 nói "cá + gà rừng có stock/carrying-capacity/regeneration
> ĐÃ CÓ". Thực tế **CHỈ CÁ có**; **gà rừng KHÔNG có stock** (`bat_ga` labor-limited, mint vô hạn).
> Đây là NEW, không phải "chuẩn hóa cái đã có" (§5). Ghi rõ để không lờ mâu thuẫn.

---

## 2. Geography 2 bờ + sông + đò (T13 gate 1)

**IMPLEMENTED:** sông (ô `loai="song"`), làng/chợ ở bờ dân cư, thửa rừng/đồi/mỏ (tài nguyên).
**NEW:** (a) sông trở thành RÀO di chuyển giữa hai bờ; (b) phân biệt bờ dân cư vs bờ hoang; (c)
đò là DỊCH VỤ có người vận hành/phương tiện/capacity/phí.

### 2.1 Topology hai bờ (NEW — static, ngoài hash)
- `sinh_ban_do` (scenario-gated) tính tập cột-sông `song_cot` (đã có, `worldmap.py:19`); gán mỗi
  thửa một **`Parcel.bo: str|None`** = `"dan_cu"` (bờ chứa làng 0) hoặc `"hoang"` (bờ kia), suy
  DIỄN từ vị trí so với sông (thửa cùng phía sông với village 0 ⇒ `dan_cu`). Ô `song` ⇒ `bo=None`.
- Bờ `hoang`: khi overlay ON, map-gen **tập trung** ruộng đã khai phá + nhà + chợ ở bờ `dan_cu`,
  để bờ `hoang` chủ yếu là `rung`/`doi` công (`chu=None`) + tài nguyên (cá/gà). KHÔNG hardcode ai
  sở hữu gì; chỉ đổi PHÂN BỐ loại đất theo bờ (seeded).
- `bo` là **static** (đặt lúc map-gen, không đổi trọn run trừ khai hoang đổi `loai`, không đổi
  `bo`) ⇒ **KHÔNG vào world_hash** (giống `p.r/p.c/p.lang` vốn không hash — `world.py:319-322`).
  OFF ⇒ `bo=None` cho mọi thửa ⇒ không phân bờ ⇒ hành vi legacy y nguyên.

### 2.2 Route/crossing + phí (NEW)
- **Sông chặn di chuyển liên bờ khi overlay ON.** Định nghĩa hàm thuần `cung_bo(w, a, b) -> bool`
  và `phai_qua_song(w, aid, thua) -> bool` (thửa đích khác bờ với nơi cư trú). Khi ON, mọi hoạt
  động của `aid` trên thửa/tài nguyên bờ khác **YÊU CẦU** `aid` đã qua sông tick này (§2.3). OFF ⇒
  hai hàm trả "cùng bờ/không cần" ⇒ không ràng buộc.
- **Điểm vượt (crossing tiles):** ô sông giáp cả hai bờ = bến khả dụng (suy diễn hình học, không
  state mới). Đò chỉ chạy tại bến.

### 2.3 Đò là DỊCH VỤ (NEW — ledger + board, không class định chế)
Engine KHÔNG có khái niệm "ferry/lái đò"; đò = TỔ HỢP: **tài sản `thuyen` + rao phí + hợp đồng**.
- **Phương tiện `thuyen`:** tài sản ledger như `cong_cu`/`nha`. Recipe `san_xuat.recipe.thuyen:
  {cong, go}` (config overlay). Đóng qua `_lam_nguyen_tu` (nguyên tử). Hao mòn/duy trì mỗi tick
  dùng (`thuyen/hao_mon` sink) — "người vận hành phải DUY TRÌ phương tiện". Sở hữu `so_du(aid,
  "thuyen")>=1` + cư trú giáp bến ⇒ **có thể** offer chuyến (không bắt buộc, không gán nghề).
- **Rao phí + nhận khách:** người vận hành đăng một **đề nghị đò** trên `bang_rao` (tái dùng board)
  hoặc một `Lenh` dịch vụ: `{operator, phi, tai_san_tra, capacity}`. Khách gửi intent `qua_song:
  (operator|None, phi_chap_nhan, tai_san)`. Giá đò **do hai bên quyết** (rao/mặc cả), engine
  KHÔNG đặt giá.
- **Capacity + settlement:** mỗi chuyến chở ≤ `do.khach_toi_da_moi_tick` (config). Khách trả
  `thóc` (hoặc settlement asset operator chấp nhận) qua `ledger.chuyen(khach→operator)` — **khách
  trả thóc TRƯỚC khi có tiền tệ**; nếu chưa đủ, có thể ký hợp đồng trả sau (`chuyen_giao_mot_lan
  tai="tick_T"/"dao_han"` — tái dùng grammar) ⇒ "settlement asset hợp lệ sau". Engine KHÔNG ép xu.
- **Hiệu ứng (no teleport):** chuyến trả phí THÀNH CÔNG ⇒ thêm `aid` vào transient
  `w.ben_kia_tick: set[str]` (reset đầu tick). Chỉ khi `aid ∈ ben_kia_tick` (hoặc cư trú bờ đích)
  mới được khai hoang/đánh cá/bắt gà/giao dịch chợ bờ kia trong tick đó. Không có chuyến ⇒ không
  qua ⇒ không tác động bờ kia (T13 gate 12 test).

**Owner/state:** `thuyen` ∈ ledger (hashed qua `so_du_s`, chỉ hiện khi ON). `w.ben_kia_tick`
transient/reset-per-tick, **NGOÀI hash** (như `settlement_fail_tick` `world.py:117`; recompute từ
intent mỗi tick). **Event:** `dong_thuyen{id}`, `qua_song{operator,khach,phi,tai_san,bo}`,
`hao_mon_thuyen`. **Flow:** `thuyen/che_tac`(nguon), `thuyen/hao_mon`(sink), `cong/dung`(reuse).

---

## 3. Work order primitive (T13 gate 2)

**Quyết định:** **KHÔNG thêm engine-primitive "job" mới cho lao-động-thuê.** Work order = TỔ HỢP
clause đã có — đúng CLAUDE.md #7 (nghề emerge từ hợp đồng, không định sẵn):

- Lao động thuê = `gop_cong` (chuyển công `tu→den` mỗi tick, `contracts.py:42-46,440-463`) +
  thanh toán `chuyen_giao_dinh_ky`/`chuyen_giao_mot_lan` (công/tô/tiền). ĐÃ ĐỦ cho: ruộng vượt sức
  (thuê công cày), dựng/sửa nhà (thuê thợ), chăm trẻ có trả công (§4.3).
- **Không cần** field engine mới cho {người thuê, người làm, công, duration, payment asset,
  output}: tất cả đã biểu diễn được — người thuê=`den`, người làm=`tu` của `gop_cong`; công=
  `so_cong_moi_tick`; duration=`hop_dong.thoi_han`; payment=clause chuyển giao; địa điểm/output =
  hệ quả vật lý (công góp dùng ở thửa của `den`).

**NEW (chỉ những gì clause KHÔNG diễn đạt được):**
- **Vận chuyển qua sông:** output = "đã qua bờ" (một trạng thái không-tài-sản) ⇒ cần cơ chế §2.3
  (`qua_song` + `ben_kia_tick`), không phải `gop_cong`.
- **Khai hoang:** output = "quyền đất mới hợp lệ" ⇒ cần action `khai_hoang` (§4.1) tạo quyền qua
  đường homestead (không phải chuyển tài sản có sẵn).
- **Rao/khớp work order tự-phát-từ-nhu-cầu:** engine đã cho ký `gop_cong`; NEW là **policy** phát
  hiện nhu cầu vật lý (ruộng > 180 công/mùa, nhà thiếu công, trẻ cần chăm) và rao/nhận (Lớp-4, §8).

**Observatory (Lớp-5):** nhãn "công nhân/thợ/lái đò" suy từ log `gop_cong`/`qua_song`; **occupation
entropy** (§9) đo đa dạng sinh kế. Không class engine. Occupation KHÔNG cố định: cùng agent có thể
`gop_cong` mùa này, đóng đò mùa kia, canh ruộng mùa khác trong một năm.

---

## 4. Sinh kế đầu tiên bằng primitive (T13 gate 3)

### 4.1 Khai hoang bờ kia (NEW) — tạo quyền đất HỢP LỆ, không free-grab
- Action `khai_hoang: list[parcel_id]` (KeHoach). Điều kiện: thửa `loai ∈ {rung,doi}`, `chu=None`,
  nếu bờ `hoang` thì `aid ∈ ben_kia_tick`. Tốn công `khai_hoang.cong_moi_thua` (config), NGUYÊN TỬ
  (thiếu công ⇒ skip, không mất công — như `_lam_nguyen_tu`).
- Kết quả: `p.loai` `rung/doi → ruong`, `p.mau_mo=p.mau_mo_goc=` fertility khai hoang (config), và
  **khởi động homestead** (`p.homestead_ai=aid, homestead_dem=1`) ⇒ phải canh liên tiếp (đường
  `production.py:229-238` đã có) mới thành chủ ⇒ **quyền đất qua path hợp lệ sẵn có**, không cấp
  title miễn phí. Giảm số ô `rung` ⇒ tác động habitat gà rừng (§5).
- **Hash:** `p.loai` CÓ trong `parcels_s` (`world.py:320`). Chỉ đổi khi overlay ON ⇒ legacy/base
  không có action này ⇒ `loai` bất biến ⇒ hash bất biến. Event `khai_hoang{id,thua,tu_loai}`,
  flow `cong/dung` (reuse). Ghi `cong_dung` nhóm `phi_nong`.

### 4.2 Xây/sửa nhà + thuê thợ
- **IMPLEMENTED:** `xay_nha` (240 công > 180 ⇒ cần `gop_cong` thuê thợ hoặc góp gia đình).
- **NEW (tùy chọn, thấp ưu tiên):** "sửa nhà" = nhà hao mòn/hư hại theo tick (sink `nha/hao_mon`)
  + action `sua_nha` phục hồi bằng công+gỗ. Chỉ thêm nếu câu hỏi nghiên cứu cần (charter: không
  thêm nông-học chi tiết vô cớ). Nếu không thêm, ghi PENDING với spec, không giả là có.

### 4.3 Chăm trẻ có trả công / mạng thân tộc (NEW) — time trade-off THẬT
- Config `cham_tre: {tuoi_can_cham, cong_cham_moi_tre}`. Trẻ `tuoi_nam < tuoi_can_cham` cần công
  chăm mỗi tick.
- **Time trade-off (bảo toàn công, không tạo lao động):** một người-lớn trong hộ phải chi
  `cong_cham` (sink `cong/cham_tre`) cho mỗi trẻ nhỏ ⇒ giảm công còn lại để canh/khai thác. HOẶC
  ủy thác: (a) **thuê người** = `gop_cong` từ carer→cha/mẹ, carer chi công chăm, được trả công
  (work order §3); (b) **thân tộc** = một họ hàng còn sống tự nguyện chi `cong/cham_tre` cho hộ đó
  (policy chọn; ledger ghi công carer bị tiêu). Công KHÔNG tự sinh: người chăm mất đúng số công
  người canh được giải phóng.
- **Hash:** đổi `sinh_cong`/kế toán công ⇒ scenario-gated; OFF ⇒ không trừ ⇒ hash legacy bất biến.
  Đây là mục INVASIVE nhất (đụng lõi lao động) ⇒ pha riêng, làm sau (§8 Phase G).

### 4.4 Chở đò — §2.3. Kết hợp nhiều sinh kế trong năm: đảm bảo bởi việc mọi sinh kế là action/
clause per-tick, không lock nghề; policy (§8) chọn theo mùa + EV.

---

## 5. Thuê đất hoàn thiện (T13 gate 4)

**IMPLEMENTED (engine đủ):** rao thuê qua `quyen_su_dung` + tô (`chia_san_luong`/tô cố định
`chuyen_giao_dinh_ky`/đổi công `gop_cong`); người thuê nhận quyền thời hạn (`hop_dong.thoi_han`);
chủ KHÔNG thu sản lượng nếu không có clause (`production.py:190`). Engine KHÔNG ép chủ nhiều đất
cho thuê.

**NEW (không đụng engine luật):**
- **Policy phát hiện cơ hội (Lớp-4, §8):** rulebot/adaptive nhận diện chủ-không-canh (đất trống +
  chủ đủ ăn) ⇒ rao `quyen_su_dung`+tô; người thiếu đất/đủ công ⇒ nhận. Intent-only.
- **Metric (Lớp-5, §9):** `land_use_rate` (thửa canh/thửa canh-được), `rent_terms` (phân phối tô
  cố định vs chia-sản vs đổi-công), `vacancy` (thửa bỏ trống), `landlord_income`/`tenant_income`
  (từ `ghi_thu_nhap` nhóm `dat`), `rent_default` (hợp đồng thuê kết ở `vi_pham`). Đọc
  `hop_dong`/`giao_dich`/`thu_nhap_4`; sentinel `None` khi coverage thưa.

---

## 6. Tài nguyên tái tạo chuẩn hóa (T13 gate 5)

**IMPLEMENTED — CÁ:** stock/K/regen/CPUE/audit đầy đủ (`chan_nuoi.py:141-188`). Chuẩn để mô phỏng
gà rừng theo.

**NEW — GÀ RỪNG (không có stock hiện tại):** chuẩn hóa GIỐNG cá:
- State `w.ga_rung_ton: float` (hoặc `dict[bo, float]` nếu tách habitat theo bờ). K =
  `Σ ô rung × ga_rung.suc_chua_moi_o` (giảm khi khai hoang bớt rừng §4.1). Regen logistic
  `tai_sinh_ga_rung(w)` chạy CÙNG CHỖ `tai_sinh_ca` (đầu pha sản xuất, `tick.py:136`).
- `bat_ga` (sửa): năng suất ∝ mật độ `ton/K` (như CPUE cá); trừ `w.ga_rung_ton`; nếu bờ hoang cần
  `aid ∈ ben_kia_tick`; vượt stock ⇒ chỉ bắt phần còn lại. Bắt được ⇒ `ga_con` (đàn nuôi) — GIỮ.
  `giet_ga`→`thit` GIỮ. Overhunting ⇒ mật độ↓ ⇒ sản lượng tương lai↓ (bi kịch commons như cá);
  giảm áp lực ⇒ phục hồi (không cạn vĩnh viễn, không sinh vô hạn).
- **Owner/hash:** `w.ga_rung_ton` là **pool tự nhiên** (không sở hữu, không ledger) — theo tiền lệ
  `ca_ton`: pickled trong checkpoint + migration, **NGOÀI world_hash-struct**. Lý do đúng
  determinism: pool là HÀM TẤT ĐỊNH của (seed, tick, intent), tái lập y hệt khi replay-từ-t0; hash
  là vân tay của state chính tắc tái-lập-được nên không cần hash pool (giữ hash-struct ổn định,
  ưu tiên §0.2). **Nêu rõ (không lờ):** `ca_ton` hiện đã ngoài hash — một khe determinism nhỏ đã
  tồn tại; T13 theo cùng khuôn để nhất quán, VÀ route cho reproducibility-steward xác nhận
  charter §D ("state ảnh-hưởng-hành-vi vào hash HOẶC có artifact version") thỏa qua checkpoint
  pickle + t0-replay. Nếu steward yêu cầu chặt hơn ⇒ đưa cả `ca_ton`+`ga_rung_ton` vào một block
  hash MỚI **có version** (chỉ bật cho scenario mới) — KHÔNG sửa hash-struct legacy.
- **Resource-audit (NEW test-enforced):** `0 ≤ ton ≤ K` mỗi tick; extraction ≤ available; event
  `bat_ga`/`danh_ca` mang `mat_do`. Flow `ga_con/bat_rung` (nguon, đã có) là source bị pool giới
  hạn (như `ca/danh_ca`).

---

## 7. Endowment một-năm-food-equivalent (T13 gate 6)

**Hiện:** `thoc_moi_nguoi=200` phẳng (`world.py:505`). **NEW (scenario-gated, chỉ tick 0):**
- Flag `endowment.theo_khau_phan: true` ⇒ endowment mỗi cá nhân = **một năm khẩu phần** quy theo
  calendar+tuổi hiện hành: người lớn = `nguoi_lon_kg_tick × tick_moi_nam` (= 90×2=180), trẻ =
  `tre_em_kg_tick × tick_moi_nam` (= 45×2=90) — đọc từ `nhu_cau` + `thoi_gian`, KHÔNG hardcode kg.
  Nhãn `design_assumption` trong `provenance.csv`.
- Là tồn kho THẬT: hộ giữ/tiêu/bán/cho vay/mua công cụ/thuê người/đầu tư, vẫn chịu rủi ro cạn
  lương. **KHÔNG food-mint sau tick 0** (chỉ flow `khoi_tao` tick 0 + `gat` từ canh tác — hợp lệ).
- **Hash/migration:** đổi số dư thóc t0 ⇒ đổi world-hash **của run bật flag** (đúng — thí nghiệm
  khác). Legacy/base OFF ⇒ vẫn `thoc_moi_nguoi=200` ⇒ hash bất biến. Không đụng checkpoint cũ (t0
  đã cố định trong pickle).

---

## 8. Calendar — QUYẾT ĐỊNH (T13 gate 7)

> **SUPERSEDED (2026-07-13).** Quyết định giữ 2 tick/năm ở bản ADR đầu không đáp ứng yêu cầu
> nghĩa đen “hai vụ lúa và một vụ đông”. Nó được giữ trong `DECISIONS.md` như lịch sử thiết kế;
> calendar dưới đây là contract hiện hành của riêng overlay `spatial_v1`.

**QUYẾT ĐỊNH HIỆN HÀNH: `spatial_v1` dùng 3 mùa 4 tháng/năm.** `thoi_gian.lich_mua` là
`[lua_1, lua_2, dong]`: hai tick đầu đều canh lúa, tick thứ ba chỉ cho ngô **hoặc** khoai.
Một thửa chỉ nhận một cây trong một tick; không có mô hình hạt giống/nước/dinh dưỡng vi mô.

- **Đơn vị thời gian có chủ ý:** `World.tick_moi_nam()` suy từ `thang_moi_tick`; calendar có
  nhãn bắt buộc phải đủ đúng số mùa. `tuoi_tick` vẫn lưu theo nửa-năm nên mỗi mùa 4 tháng tăng
  `2/3`; `tuoi_nam`, trưởng thành và mọi consumer tuổi giữ cùng nghĩa. Thời tiết/dịch được rút
  một lần cho cả ba mùa; relationship decay chạy cuối năm; report/metric/manifest ghi calendar
  thực chạy thay vì mặc định `tick//2`.
- **Flow theo thời gian:** overlay quy đổi 6→4 tháng cho khẩu phần, ngày công, hao kho, sức khỏe,
  sinh sản theo tick, cá/gà/chicken feed và hao thịt. Gompertz được engine đổi từ hazard năm bằng
  `1-(1-q_nam)^(1/tick_moi_nam)`, không nhân xác suất chết theo số mùa. T0 bật endowment đúng một
  năm food-equivalent (người lớn: 60×3=180kg) — stock thật, không trợ cấp sau đó.
- **Hợp đồng:** grammar đã định nghĩa `thoi_han`/`moi_n_tick` theo tick, nên không được âm thầm
  nhân mọi hợp đồng. Các parameter có ngữ nghĩa năm trong rulebot/overlay (ví dụ tô năm, gợi ý
  childcare) được quy đổi tường minh; intent/LLM vẫn thấy đơn vị tick trong schema.
- **Legacy/replay:** khi không có `lich_mua`, code path giữ chính xác calendar 2-tick và index
  năm cũ; overlay 3 mùa có config digest/world-hash riêng. Regression test kiểm calendar
  `lua_1,lua_2,dong`, weather chung năm, tuổi +1 sau 3 tick và legacy 2-tick không đổi.
- **Hash/flows cây trồng:** vụ đông tạo asset riêng `ngo`/`khoai`, ăn được và chịu hao kho;
  tất cả nguồn/sink đăng ký FlowRegistry. Tắt overlay ⇒ không có action/asset stock mới ⇒ replay
  legacy bất biến.

---

## 9. Behavior/survival policy (T13 gate 8) — Lớp-4, intent-only

**NEW policy** (hoặc mở rộng rulebot) `SpatialSurvivalPolicy` — thứ tự ưu tiên GIẢI THÍCH ĐƯỢC,
mỗi bước chỉ phát intent feasible có EV cao:

1. **Dự trữ hộ** (đủ ăn tick này + buffer phòng ngừa — nền adaptive đã có `minds/policies.py:213`).
2. **Canh/thuê đất** (canh thửa sở hữu/công; nếu thiếu đất+đủ công ⇒ nhận `quyen_su_dung`; nếu
   dư đất+đủ ăn ⇒ rao thuê §5).
3. **Nhận/rao work order** (`gop_cong` khi ruộng>sức hoặc bán sức khi rảnh; dựng/sửa nhà; chăm trẻ).
4. **Chợ/đò/vận chuyển** (bán thặng dư; nếu tài nguyên/đất bờ kia lợi hơn ⇒ trả phí `qua_song`).
5. **A2A xin hỗ trợ/thương lượng** (`nhan_tin` — trễ 1 tick, phạm vi hàng xóm, uy tín ảnh hưởng
   khả năng được giúp; KHÔNG sửa state, `tick.py:69-85`).
6. **Tín dụng hợp lệ** (vay qua clause khi thiếu vốn — grammar đã có, ADR 0004).
7. **Khai thác trong giới hạn** (đánh cá/bắt gà theo mật độ; policy TỰ giảm khi mật độ dưới
   `nguong_mat_do_canh_bao` — không vét cạn).
8. **Di cư** (`di_cu` lập làng mới khi bế tắc — đã có `tick.py:322`).

**Ràng buộc:** MCP/world-tool read-only, giới hạn lượt (`minds.cong_cu_max_luot`, đã có); A2A trễ/
phạm vi/uy tín/không-sửa-state. KHÔNG bắt agent dùng mọi tool; chọn feasible-EV cao. Tất định qua
`w.rng`; KHÔNG mutate World. **Agent VẪN được phép suy kiệt** khi mọi bước không feasible (test §12).

---

## 10. Metrics + reports (T13 gate 9) — Lớp-5 chỉ đọc, không điều khiển engine

Module **NEW `engine/metrics_spatial.py`** (KHÔNG nhồi vào `economy.py`/`metrics_research.py` —
giữ domain tách; xem §12). Đọc `events`/`ledger`/`hop_dong`/pool; sentinel `None` khi coverage
thưa; surface qua `tick.py` (1 dòng, cạnh `m["research"]`):

| Metric | Nguồn | undefined khi |
|---|---|---|
| `seasonal_time_use` | `cong_dung_tick`/`_4` tách theo mùa (mưa/khô) + nhóm | không có công |
| `occupation_entropy` | Shannon trên phân bố nguồn thu nhập/loại-công per-agent | <2 agent hoạt động |
| `work_order_vacancy/fill/wage` | đề nghị `gop_cong` rao vs khớp; công-đổi-thóc quy đổi | 0 đề nghị |
| `childcare_burden` | Σ `cong/cham_tre` / Σ công người-lớn (nếu §4.3 bật) | flag OFF ⇒ None |
| `crop_mix` | tỷ trọng thửa lúa vs ngô/khoai (nếu §8 bật) | 0 thửa canh |
| `land_use_rate/clearance` | thửa canh/canh-được; #`khai_hoang`/tick | 0 thửa |
| `river_crossing_volume/fare/asset` | event `qua_song` đếm/phí trung vị/asset | 0 chuyến |
| `resource_stock/extraction/regen` | `ca_ton`/`ga_rung_ton`, event `danh_ca`/`bat_ga`, ΔS regen | K=0 |
| `price_wage_dispersion_by_bank` | CV giá/công-giá giữa bờ (đọc `khop_cho.bo`) | <2 bờ khớp |
| `mobility` | đổi nhãn occupation/giai-cấp qua snapshot (đã có `giai_cap_snapshot`) | <2 snapshot |

Thêm `bo` vào payload event `khop_cho` (như đã thêm `lang` — `market.py:99`) để đo dispersion hai
bờ OFFLINE, **KHÔNG** đụng `world_hash`/`Lenh`/`gia_lich_su` (events không vào hash,
`world.py:355-359`). Observatory (Lớp-5) dán nhãn "lái đò/địa chủ/tá điền/thợ" từ log — nhãn KHÔNG
quay lại engine.

---

## 11. State ownership, hash, migration, cổng scenario (tổng hợp)

### 11.1 Bảng ownership
| State | Owner | Nơi lưu | Vào world_hash? | Reset/tick |
|---|---|---|---|---|
| `Parcel.bo` (bờ) | engine (map-gen) | Parcel (static) | **KHÔNG** (như r/c/lang) | không |
| `p.loai` đổi do khai hoang | engine (production) | Parcel | **CÓ** (parcels_s) — chỉ đổi khi ON | không |
| `thuyen` (balance) | chủ sở hữu | ledger `so_du` | **CÓ** (so_du_s) — chỉ hiện khi ON | không |
| `ngo`/`khoai` (balance) | chủ | ledger `so_du` | **CÓ** — chỉ hiện khi ON | không |
| `w.ben_kia_tick` | engine | World field | **KHÔNG** (transient, như settlement_fail) | **CÓ** (đầu tick) |
| `w.ga_rung_ton` | engine | World field (pool) | **KHÔNG** (như `ca_ton`) — pickled+migrate | không (evolve) |
| endowment t0 | engine (tao_the_gioi) | ledger `so_du` (thoc) | **CÓ** — chỉ đổi khi flag ON | tick 0 |
| care-labor deduction | engine (sinh_cong) | ledger `cong` flow | **CÓ** (qua so_du/flow) — chỉ khi ON | mỗi tick |

**Kết luận:** layout tuple `world_hash()` **KHÔNG đổi**. Nội dung mới chỉ vào so_du_s/parcels_s khi
overlay ON. Pool tài nguyên + transient theo tiền lệ ca_ton/settlement_fail (ngoài hash).

### 11.2 Cổng scenario (theo khuôn `_chinh_tri_bat`)
- Đọc bằng `w.cfg.get("khong_gian.bat", False)` + sub-flags — **default OFF**, **KHÔNG thêm key
  vào base `world.yaml`** (giữ `cfg.digest()` base bất biến ⇒ không phá resume/guard checkpoint cũ,
  `run.py:171`). Bật qua **overlay TÙY CHỌN** `scenarios/agrarian_transition_v1/overlays/
  spatial_v1.yaml` (áp bằng `--config-overlay`, hoặc scenario-variant), gồm mọi tham số T13 (recipe
  thuyền, capacity đò, chi phí khai hoang, cham_tre, vụ đông, ga_rung, endowment). Sub-flags:
  `khong_gian.hai_bo` (2 bờ+đò), `.khai_hoang`, `.ga_rung`, `.vu_dong`, `.cham_tre`,
  `endowment.theo_khau_phan`. Mỗi sub-flag TẮT ⇒ path đó no-op độc lập.
- Helper `engine/spatial.py:_khong_gian_bat(w)` (+ sub) tập trung đọc cờ (một chỗ, như politics).

### 11.3 Migration `nap_checkpoint` (world.py:377)
Thêm default an-toàn cho checkpoint cũ (pattern `ca_ton` `world.py:391`):
```
if not hasattr(w, "ga_rung_ton"): w.ga_rung_ton = _ga_rung_suc_chua(w) * ty_le_ton_ban_dau   # hoặc 0 nếu OFF
if not hasattr(w, "ben_kia_tick"): w.ben_kia_tick = set()
for p in w.parcels.values():
    if not hasattr(p, "bo"): p.bo = None    # legacy: không phân bờ
```
Checkpoint cũ (OFF) nạp lại ⇒ mọi field mới = trung tính ⇒ replay + world_hash bất biến.

### 11.4 Không phá replay/hash legacy
- OFF (mọi run cũ, `preindustrial_closed_v1`, base `agrarian_transition_v1`): mọi path T13 no-op ⇒
  hash/replay **y nguyên** (test §12 replay-same-hash).
- ON: hash khác (đúng — thí nghiệm khác); 2 run cùng seed+overlay ⇒ **cùng hash** (determinism).

---

## 12. Thứ tự tick, determinism, failure/rollback, FlowRegistry

### 12.1 Chèn vào pipeline (`tick.py`) — điểm chèn CHÍNH XÁC
1. **Reset transient** (cạnh `tick.py:119-123`): `w.ben_kia_tick = set()`.
2. **Regen tài nguyên** (cạnh `tai_sinh_ca` `tick.py:136`): thêm `tai_sinh_ga_rung(w)` (regen
   TRƯỚC khai thác — người bắt sau, như cá).
3. **Care-labor** (sau `sinh_cong` `tick.py:124`): trừ `cong/cham_tre` (§4.3) TRƯỚC canh tác.
4. **Ferry crossings** (sau `gop_cong_dau_san_xuat` `:125`, TRƯỚC `thi_hanh_san_xuat` `:129`): xử
   lý `qua_song` ⇒ set `ben_kia_tick`. Đò cần công đã sinh + trước hoạt động bờ kia.
5. **Khai hoang + vụ đông**: trong/ngay trước `thi_hanh_san_xuat` (cùng pha, gate mùa+bờ).
6. **Bắt gà/đánh cá** (đã ở `tick.py:142-147`): sửa gate `ben_kia_tick` + pool ga_rung.
7. **Metrics spatial** (cạnh `m["research"]` `:240`): `m["spatial"] = metrics_spatial.spatial_metrics(w)`.
8. **Hao mòn thuyền** (cạnh `hao_mon_thuy_loi` `:231`): `hao_mon_thuyen(w)`.

### 12.2 Deterministic ordering
- Đò: `sorted` operator theo id; phân capacity cho khách chấp nhận sắp theo `(phi giảm dần,
  khach_id)` (mô phỏng willingness-to-pay, tie-break id) — deterministic.
- Khai hoang/vụ đông/bắt gà: theo `sorted(ke_hoach)` (đã là khuôn `thi_hanh_san_xuat`).
- Pool ga_rung phân bổ theo `sorted(chu)` như `danh_ca`.

### 12.3 Failure/rollback
- Đò: khách không đủ trả ⇒ `LoiSoKep` nuốt (không qua sông, không âm sổ) — như market
  `market.py:119-122`; đếm quan sát nếu cần.
- Khai hoang/vụ đông/đóng thuyền: NGUYÊN TỬ (`_lam_nguyen_tu`) — thiếu ⇒ skip, không mất công.
- Bắt gà/đánh cá: extraction ≤ pool; pool cạn ⇒ về tay không (đã có khuôn cá).
- Care: không carer ⇒ cha/mẹ tự chăm (giảm công) — không "failure", là time trade-off.
- Metric read-only KHÔNG raise; undefined ⇒ `None`.

### 12.4 FlowRegistry/ledger entries (đăng ký vô điều kiện, `world.py:415`)
`thuyen/che_tac`(nguon), `thuyen/hao_mon`(sink); `ngo/gat`,`khoai/gat`(nguon),
`ngo/an`,`khoai/an`,`ngo/hao_kho`,`khoai/hao_kho`(sink); `cong/cham_tre`(sink); khai hoang dùng
`cong/dung`(có). Phí đò = `ledger.chuyen` (không mint). Endowment = `thoc/khoi_tao`(có). Pool
ga_rung KHÔNG ledger (source `ga_con/bat_rung` đã có, bị pool giới hạn — như cá). Đăng ký thừa
KHÔNG đổi hash (registry ngoài hash; luồng không dùng ⇒ không tích lũy — tiền lệ fiscal
`world.py:459-465`).

---

## 13. Module map (domain-named, CẤM god-module)

CẤM nhồi logic T13 vào `engine/economy.py` (đó là VIEW read-only) hay một `economy.py` khổng lồ.
Tách theo domain; observatory KHÔNG trộn với engine:

| Module | Trách nhiệm | Loại |
|---|---|---|
| `engine/spatial.py` (**NEW**) | cờ `_khong_gian_bat`, `Parcel.bo`, `cung_bo`/`phai_qua_song`, vật lý đò (`thuyen`, `qua_song`, capacity, hao mòn), `ben_kia_tick` | engine Lớp-1/3 |
| `engine/worldmap.py` (sửa) | topology 2 bờ khi ON (phân bố loại đất theo bờ) | engine Lớp-1 |
| `engine/production.py` (sửa) | khai hoang (đổi loai+homestead), vụ đông (crop mùa khô), care-labor deduction | engine Lớp-1 |
| `engine/chan_nuoi.py` (sửa) | `w.ga_rung_ton` stock/K/regen, `bat_ga` theo mật độ | engine Lớp-1 |
| `engine/intents.py` (sửa) | KeHoach: `qua_song`, `khai_hoang`, `canh_dong`, `dong_thuyen`, `cham_tre_cho` | schema |
| `engine/metrics_spatial.py` (**NEW**) | metric §10 (chỉ đọc) | engine Lớp-5 |
| `observatory/` (sửa) | nhãn "lái đò/địa chủ/tá điền/thợ", occupation entropy label | observatory (chỉ đọc) |
| `minds/policies.py` (sửa) | `SpatialSurvivalPolicy` (§9) | Lớp-4 |
| `config` overlay `spatial_v1.yaml` (**NEW**) | mọi tham số T13 | scenario |

"Đò/thuê đất/thợ" KHÔNG là class engine — chỉ tổ hợp `thuyen`+rao+contract / clause thuê / gop_cong
(cổng §5: alternative=tự đi vòng/tự làm; cost=đóng+duy trì thuyền, soạn hợp đồng, chi công;
accounting=chuyển cân + source-giới-hạn-pool; scenario-flag=`khong_gian.*`; ablation=§12 counterfactual).

---

## 14. Xung đột CLAUDE.md "định chế tự phát" — nêu rõ, không hard-code im lặng

- CLAUDE.md §2 #7 cấm TUYỆT ĐỐI định chế có tên + "gán sẵn nghề/vai trò" + "sự kiện kịch bản hóa".
  Lệnh cấm tuyệt đối ĐÃ được ADR 0001 §B thay bằng **cổng định chế §5** (charter binding). T13
  KHÔNG tạo xung đột MỚI ngoài phạm vi cổng đó, VỚI ĐIỀU KIỆN:
  - Đò/thuê/work-order/chăm-trẻ đi qua cổng §5 (alternative/cost/accounting/flag/ablation) và chỉ
    mang tên định chế ở observatory (§13). **Đúng tinh thần #7** ("work order thay hard-code nghề").
  - KHÔNG hardcode ID người hưởng lợi/nghề; occupation biến thiên theo mùa (§3).
  - Bản đồ 2 bờ + vụ đông là **cấu trúc scenario/vật lý seeded**, không phải "sự kiện kịch bản hóa"
    (không có năm/ngưỡng nào TRỰC TIẾP ép một sinh kế xuất hiện — anti-teleology §0.5). Sinh kế chỉ
    là OUTCOME của chi phí/khả-năng-tiếp-cận đã công bố.
- **Đề xuất cập nhật đặc tả CÓ CHỦ Ý (không im lặng):** thêm một dòng vào `DECISIONS.md` + banner
  superseded (như ADR 0001 đã làm) rằng "gà rừng/đò/vụ đông/khai hoang là scenario-overlay qua cổng
  §5, nhãn định chế ở observatory"; và ghi rõ endowment food-equivalent là `design_assumption`.
  spec-governor xác nhận không mâu thuẫn im lặng trước khi implement.
- **KHÔNG thay đổi INVARIANT nào:** bảo toàn/audit mỗi tick, sổ kép/không-âm, LLM-chỉ-intent,
  determinism/replay, mock-trước-thật — giữ nguyên. Đây là điều kiện gate của T13.

---

## 15. Kế hoạch triển khai theo PHA + FILE-OWNERSHIP (song song/tuần tự)

**HOTSPOT SERIAL (chỉ một người/PR chạm mỗi lượt, merge tuần tự):** `engine/tick.py`,
`engine/world.py`, `engine/intents.py`, config overlay. **PARALLEL-SAFE:** file mới +
module-đơn-domain.

| Pha | Nội dung | Files (owner) | Phụ thuộc | Song song? |
|---|---|---|---|---|
| **P0** | ADR này | `docs/adr/0005` (model-architect) | — | DONE |
| **A** | Overlay scaffolding + cờ helper | `engine/spatial.py`(NEW), `overlays/spatial_v1.yaml`(NEW) | P0 | **Độc lập** (file mới) |
| **B** | Topology 2 bờ + `Parcel.bo` + migration | `types.py`, `worldmap.py`, `world.py`(nap_checkpoint) ⚠️serial | A | serial world.py |
| **C** | Đò: `thuyen`/`qua_song`/`ben_kia_tick` + flows | `spatial.py`, `intents.py`⚠️, `tick.py`⚠️, `world.py`⚠️(field+flow) | B | serial tick/world/intents |
| **D** | Khai hoang | `production.py`⚠️, `intents.py`⚠️, `tick.py`⚠️ | B | serial (đụng production/tick/intents) |
| **E** | Vụ đông (calendar) | `production.py`⚠️, `intents.py`⚠️, config, `world.py`(flows) | A | serial production/intents (coord D) |
| **F** | Gà rừng stock/regen | `chan_nuoi.py`, `world.py`⚠️(1 field+migrate), `tick.py`⚠️(1 dòng) | A | **gần độc lập** (chan_nuoi riêng) |
| **G** | Chăm trẻ (INVASIVE lõi công) | `production.py`⚠️(sinh_cong), `intents.py`⚠️, config | A | serial, **làm SAU** |
| **H** | Policy thuê-đất + SpatialSurvival | `minds/policies.py`, `minds/rulebot.py` | (đọc intent của C/D/E) | **Độc lập** (minds only) |
| **I** | Metrics + observatory + event `bo` | `metrics_spatial.py`(NEW), `observatory/*`, `market.py`(payload `bo`), `tick.py`⚠️(1 dòng) | C/D/E/F cho dữ liệu | **gần độc lập** (file mới) |
| **J** | Tests | `tests/test_spatial_*.py`(NEW) | feature tương ứng | **Độc lập** (file mới) |

**Khuyến nghị điều phối:** B→C→D→E→G phải **serial** (đều đụng tick.py/world.py/intents.py/
production.py) — một engine-surgeon giữ nhánh này, merge tuần tự. A, F, H, I, J chạy **nhánh
song song** (file mới hoặc module tách), rebase khi B-chain merge. Mỗi PR chạy
`conda run -n thoc-env python -m pytest -q --basetemp .tmp/pytest -p no:cacheprovider` +
`ruff check .` + smoke replay-same-hash (OFF) trước merge.

---

## 16. Test matrix (đúng 12 gạch T13; unit/integration/property/replay/negative)

**Unit (thế giới nhỏ 8×8, 10 agent, 20 tick — CLAUDE §3):**
1. Chủ đất KHÔNG canh CÓ THỂ cho thuê (`quyen_su_dung`+tô) NHƯNG KHÔNG tự thu tô nếu không contract
   (verify chủ nhận 0 khi không có clause; nhận tô khi có).
2. Hộ thiếu công CÓ THỂ thuê người (`gop_cong` giao công; nhà 240-công dựng được nhờ thợ).
3. Childcare đổi TIME/INCOME mà KHÔNG tạo lao động (Σ công trước=sau; carer mất đúng phần cha/mẹ
   được giải phóng).
4. Người/hàng KHÔNG qua sông khi không có route/đò/fee (không `ben_kia_tick` ⇒ khai hoang/đánh cá
   bờ kia bị chặn); có đò+phí ⇒ qua được.
5. Fare bằng THÓC trước tiền tệ (chuyến trả `thoc` thành công dù M(xu)=0; asset khác chấp nhận nếu
   operator nhận).
6. Khai hoang CẦN công + TẠO quyền đất hợp lệ (thiếu công ⇒ skip nguyên tử; đủ ⇒ loai→ruong +
   homestead khởi động; canh liên tiếp ⇒ thành chủ).

**Property / invariant (hypothesis):**
7. Khai thác cá/gà KHÔNG vượt stock (`0 ≤ ton ≤ K`; extraction ≤ available mọi tick, nhiều seed).
8. Quần thể PHỤC HỒI khi giảm áp lực (bắt/đánh = 0 vài tick ⇒ `ton` tăng đơn điệu về K).
9. Occupation KHÔNG cố định (một agent có ≥2 loại sinh kế trong một năm ở ≥1 seed — không class lock).
10. Bảo toàn: đò/khai hoang/vụ đông/chăm-trẻ đều qua counterpart; audit `kiem_toan_the_gioi` xanh
    mỗi tick; không mint/burn ngoài flow đăng ký.

**Replay:**
11. **Overlay OFF ⇒ world_hash TRÙNG legacy** (preindustrial + base agrarian): 2-run-same-seed +
    replay-from-checkpoint = cùng hash (chứng minh T13 không đụng determinism khi tắt).
12. **Overlay ON ⇒ 2-run-same-seed cùng hash** + replay-from-t0 tái lập `ga_rung_ton`/`ben_kia_tick`
    (pool/transient deterministic).

**Negative:**
13. **Agent VẪN suy kiệt** khi mọi lựa chọn không feasible (không đất/không công/không đò/không tài
    nguyên ⇒ food_security<1 kéo dài, chết đói hợp lệ — KHÔNG floor cứu trái luật).
14. Đò quá tay (khách > capacity) ⇒ chỉ chở đủ capacity theo thứ tự tất định; khách thiếu tiền ⇒ bị
    bỏ, không âm sổ, không teleport.
15. Bán/bắt nhiều hơn có ⇒ phần dư bỏ; ledger không âm.

**Integration / counterfactual (paired-seed, không mạng — T13 gate 12):**
16. có/không đò; phí đò cao/thấp; thuê đất bật/tắt; khai hoang xa/gần; resource capacity cao/thấp.
    Report cả trường hợp **KHÔNG phát sinh dịch vụ** và **tài nguyên cạn**; KHÔNG ép mọi seed có
    lái đò/thuê đất/phát minh. Dùng `tools/counterfactual.py` (paired delta, n_success/n_failed).

Không nới assertion, không hard-code seed/%, không skip để gate xanh (TASKS §1.5).

---

## 17. IMPLEMENTED vs NEW (tổng hợp)

**IMPLEMENTED (ADR chỉ chốt/đặt tên/tái dùng — KHÔNG viết lại):**
- Sông trên bản đồ (`worldmap.py`); homestead khai hoang đất *ruộng* công (`production.py`); xây
  nhà + thuê thợ qua `gop_cong` (`production.py`/`contracts.py`); phí vận chuyển liên-làng
  (`market.py`, dạng burn).
- Thuê đất ĐỦ Ở ENGINE: `quyen_su_dung`+`chia_san_luong`+`chuyen_giao_dinh_ky`+`gop_cong`; chủ
  không tự thu tô nếu không contract.
- Work-order-as-clause: `gop_cong`+payment (không cần primitive engine mới cho lao-động-thuê).
- **CÁ**: stock/K/regen logistic/CPUE/audit đầy đủ (`chan_nuoi.py`).
- Gà rừng → thịt (`giet_ga`) / đàn nuôi (`bat_ga`→`ga_con`).
- P2P/A2A trễ-1-tick, cap, uy tín (`tick.py`); MCP read-only giới hạn lượt (`minds`); policy
  Lớp-4 registry (`minds/policies.py`); cổng scenario mẫu (`_chinh_tri_bat`/`_fiscal_bat`); overlay
  deep_merge (`config.py`/`run.py`).

**NEW (cần engine/config/policy — qua cổng §5, scenario-gated, review độc lập):**
- Topology 2 bờ + `Parcel.bo` + sông-chặn-di-chuyển-khi-ON; đò-dịch-vụ (`thuyen`+rao phí+`qua_song`
  +capacity+hao mòn+`ben_kia_tick`).
- Khai hoang RỪNG/ĐỒI → ruộng (đổi `loai`+homestead) tạo quyền đất hợp lệ.
- **Gà rừng STOCK/K/regen** (`w.ga_rung_ton`) — bắt theo mật độ, overhunting có hậu quả (CHƯA CÓ).
- Endowment một-năm-food-equivalent theo tuổi/calendar (thay 200 kg phẳng), `design_assumption`.
- Vụ đông (ngô/khoai) mùa khô — GIỮ 2 tick/năm (không đổi đơn vị thời gian).
  > **SUPERSEDED (2026-07-13, ADR 0006 §D.2).** Dòng này là tàn dư của bản thiết kế đầu và mâu
  > thuẫn với §8 hiện hành. Contract đang chạy: overlay `spatial_v1` dùng **3 mùa × 4 tháng**
  > `[lua_1, lua_2, dong]` (`scenarios/agrarian_transition_v1/spatial_v1.yaml:14-16`); base/legacy
  > không nạp overlay vẫn đúng 2 tick/năm. Giữ nguyên chữ làm lịch sử thiết kế.
- Chăm trẻ có trả công / thân tộc (care-labor trade-off, INVASIVE lõi công) — pha cuối.
- Policy phát-hiện-thuê-đất + `SpatialSurvivalPolicy` thứ tự ưu tiên (Lớp-4).
- Metric §10 (`metrics_spatial.py`) + event `bo` + nhãn observatory.
- Overlay `spatial_v1.yaml` + helper cờ `engine/spatial.py`.

---

## 18. Handoff

**implementation-engineer / engine-surgeon (B–G):**
- Theo §15 file-ownership: serial-chain B→C→D→E→G trên tick.py/world.py/intents.py/production.py;
  mọi path gated `_khong_gian_bat`+sub (OFF ⇒ no-op ⇒ hash legacy bất biến — verify §16.11 TRƯỚC
  merge). Ledger-based (§11.1); flows §12.4; migration §11.3; **KHÔNG** đưa `Parcel.bo`/pool vào
  hash-struct; **KHÔNG** food/xu-mint sau t0; **KHÔNG** teleport (mọi qua-bờ qua `ben_kia_tick`).
  Policy/LLM không ghi field mới. Gà rừng theo đúng khuôn cá (§6). Vụ đông GIỮ 2 tick/năm (§8).
  > **SUPERSEDED (2026-07-13, ADR 0006 §D.2).** Câu "Vụ đông GIỮ 2 tick/năm" không còn đúng: §8 đã
  > được thay bằng calendar 3 mùa 4 tháng cho overlay `spatial_v1` (legacy giữ 2 tick/năm). Prompt
  > và mọi consumer thời gian phải đọc `thoi_gian.thang_moi_tick`/`thoi_gian.lich_mua` từ config
  > đang chạy (ADR 0006 §B), không giả định calendar nào.
- `engine/spatial.py`/`metrics_spatial.py` là file MỚI (parallel); CẤM nhồi vào `economy.py`.

**test-engineer (J, độc lập):**
- Viết đủ 16 nhóm §16 (ưu tiên: replay-same-hash OFF = legacy; property stock 0≤ton≤K + phục hồi;
  negative agent-vẫn-suy-kiệt; chủ-không-tự-thu-tô; no-crossing-no-fee; fare-bằng-thóc-trước-tiền).
  KHÔNG nới assertion, KHÔNG hard-code seed/%/horizon. Counterfactual §16.16 qua
  `tools/counterfactual.py`, report cả no-service + resource-exhaustion.

**qa-verifier / reproducibility-steward / adversarial-reviewer / spec-governor (độc lập):**
- Xác nhận: (a) OFF ⇒ world_hash + config-digest legacy BẤT BIẾN; (b) mọi flow có counterpart +
  đăng ký, audit xanh mỗi tick, không phantom/teleport/mint; (c) không ID/nghề cố định, không
  metric điều khiển engine, đò/thuê/work-order qua cổng §5 với ablation; (d) determinism: 2-run +
  replay-from-checkpoint cùng hash (OFF và ON); (e) `ga_rung_ton`/`ca_ton`-ngoài-hash thỏa charter
  §D qua checkpoint pickle + t0-replay (reproducibility-steward quyết có cần hash-block-versioned
  không); (f) spec-governor ghi cập nhật `DECISIONS.md`/banner cho §14 TRƯỚC khi implement, không
  hard-code im lặng; (g) calendar giữ 2 tick/năm — không nhân/chia ngầm tham số thời gian (§8).
