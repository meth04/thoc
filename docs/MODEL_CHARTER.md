# MODEL_CHARTER — THÓC

Ngày: 2026-07-12. Trạng thái: **binding**. Tài liệu này định nghĩa phạm vi khoa học, cấp độ
claim và các lớp mô hình của THÓC. Khi `CLAUDE.md`/`SPEC.md`/`PHASES.md`/`REPORTS.md` mâu thuẫn
với charter này về *cấp độ claim* hoặc *định chế có tên*, **charter + ADR trong `docs/adr/`
thắng**; các phần bị thay được đánh dấu superseded tại chỗ, không xóa lịch sử.

Cơ sở: `REVIEW.md`, `TASKS.md`, và `docs/reviews/T00-spec-governor-conflict-map.md`.

---

## 1. Câu hỏi và phạm vi

THÓC là một **agent-based model (ABM)** của một cộng đồng nông nghiệp giả định, khép kín một
phần. Câu hỏi nghiên cứu hẹp:

> Trong một cộng đồng nông nghiệp có đất hữu hạn, mùa vụ, dị biệt hộ và thông tin cục bộ,
> điều kiện vật chất/thông tin/thể chế nào làm chuyên môn hóa, trao đổi, tín dụng, phương
> tiện trao đổi và năng lực công quyền **bền vững hơn** các lựa chọn thay thế — và khi nào
> quá trình đó thất bại hoặc đảo ngược?

THÓC **không** tuyên bố:
- mô phỏng đúng một nền kinh tế hay một địa phương/quốc gia lịch sử cụ thể;
- rằng nông nghiệp *tất yếu* dẫn tới tiền tệ, ngân hàng hay nhà nước hiện đại;
- rằng một run đạt "công nghiệp hóa" là bằng chứng cơ chế đó tạo ra công nghiệp hóa ngoài đời.

Đơn vị phân tích: **hộ gia đình** là chủ thể kinh tế chính (tiêu dùng, tồn kho, canh tác, nợ,
rủi ro); **cá nhân** là đơn vị nhân khẩu (tuổi, giới, kỹ năng, hôn nhân, thừa kế, lao động).
Tổ chức sản xuất (entity/pháp nhân) và khu vực công chỉ xuất hiện như tổ chức có bảng cân đối
và chi phí, không phải object quyền lực miễn phí.

## 2. Bốn cấp độ claim (mỗi phiên bản/scenario công bố rõ mình ở tầng nào)

| Tầng | Câu hỏi | Bằng chứng cần | THÓC hiện tại |
|---|---|---|---|
| 1. Nhất quán kế toán | Tài sản/nợ/hàng có bị tạo/hủy vô cớ? | audit, unit test, replay theo seed | **Mạnh ở bảo toàn/audit-mỗi-tick**; replay đầy đủ cho state chính trị/hộ/dịch bệnh/floor còn chờ T02 (ADR §D) |
| 2. Hợp lý cơ chế | Quy tắc vi mô có phù hợp kinh tế học? | mô tả hành vi, phản biện chuyên gia | **Có tiềm năng**, đang chuẩn hóa |
| 3. Khớp dữ kiện | Tái tạo stylized facts đã biết? | so nhiều chỉ tiêu theo thời gian/phân phối | **Hạn chế** (chưa có data ngoài) |
| 4. Dự báo/nhân quả | Đổi điều kiện/chính sách → dự báo đúng ngoài mẫu? | holdout, backtest, placebo, phản chứng | **Chưa có** |

Quy tắc claim tier (thuật ngữ dùng thống nhất toàn repo):
- `design_assumption`: số/luật do người thiết kế đặt, chưa có nguồn dữ liệu.
- `mechanism_result`: kết quả của tập luật đang cài (một hoặc nhiều seed) — KHÔNG phải bằng
  chứng về thế giới thật.
- `calibrated_fact`: tham số được hiệu chuẩn khớp một moment in-sample **có nguồn**.
- `validated_result`: dự báo đúng trên **holdout chưa dùng để hiệu chuẩn**.

Không được nâng nhãn khi thiếu bằng chứng tương ứng. **Mock, một-seed, hoặc legacy run KHÔNG
được gọi là empirical/causal/predictive/world-class.**

## 3. Năm lớp mô hình (ranh giới cứng)

```
Dữ liệu / tham số / cú sốc (seed)
   ▼
Lớp 1 — RÀNG BUỘC VẬT LÝ:  đất, mùa vụ, tồn kho, lao động, vận tải, dân số, thời tiết.
   • DUY NHẤT lớp này bảo toàn vật chất. Random chỉ qua w.rng. Không lớp nào tạo nguồn lực.
   ▼
Lớp 2 — KẾ TOÁN:  ledger sổ kép + FlowRegistry. Mọi dịch chuyển tài sản/nợ/tiền/công quỹ có
   đối ứng; audit mỗi tick; không số dư âm (nợ là claim, không phải số âm).
   ▼
Lớp 3 — THỂ CHẾ (bật/tắt theo scenario):  quyền đất, hợp đồng, pháp nhân, tín dụng, tiền hàng
   hóa, tài khóa/khu vực công. Mỗi module CHỈ được thêm khi thỏa "cổng định chế minh bạch" (§5).
   ▼
Lớp 4 — HÀNH VI (thay thế được):  kỳ vọng, tiêu dùng, tiết kiệm, đầu tư, vay, di cư, chọn đối
   tác. Cài qua `BehaviorPolicy` (rulebot / random khả thi / subsistence / adaptive / LLM-treatment).
   Một policy mới KHÔNG được đụng logic hạch toán. LLM là *treatment cuối cùng*, không phải lõi.
   ▼
Lớp 5 — ĐÀI QUAN SÁT (chỉ đọc):  classifier giai cấp, nhãn định chế, milestones, metrics,
   chronicle. Nhãn KHÔNG được quay lại điều khiển engine.
```

**Quy tắc bất khả xâm phạm giữ nguyên từ CLAUDE.md (là INVARIANT):**
- Bảo toàn tài nguyên + audit mỗi tick (điều luật #1).
- Sổ kép, không số dư âm (#2).
- LLM/policy chỉ trả ý định; engine validate whitelist rồi thực thi (#3).
- Tất định & tái lập: một cây RNG, cùng seed + cùng transcript → cùng world-hash (#4).
  **Mọi state ảnh hưởng hành vi phải vào world-hash/replay hoặc có artifact version rõ ràng**
  (mở rộng cho state chính trị/hộ/dịch bệnh/safety-floor mới — xem ADR 0001 §D).
- Mock trước, thật sau; ghi mọi vết tích (#5, #6).

## 4. "Tự phát nội sinh" nghĩa là gì (định nghĩa có thể kiểm chứng)

Một định chế chỉ được gọi là **hình thành nội sinh** khi thỏa ĐỦ năm điều kiện (REVIEW §D.6):

1. Không tồn tại ở tick 0 và không bị bắt buộc dùng;
2. Có ≥1 cơ chế thay thế khả thi (barter, tín dụng quan hệ, chợ tư, tự bảo vệ);
3. Tác nhân/tổ chức phải trả chi phí tạo và duy trì nó;
4. Adoption/persistence tăng qua **nhiều seed**, không phụ thuộc một prompt hay một luật kích hoạt;
5. Khi tắt lợi ích nền tảng của nó, adoption giảm theo hướng dự báo (ablation có dấu).

Cấu trúc state được thêm qua scenario overlay hoặc treatment (thuế, bạo động, tiền pháp định…)
là **`institutional_assumption`** hoặc **`experimental_treatment`**, KHÔNG được gọi là "tự
phát". Chỉ Lớp-5 mới dán nhãn; nhãn không điều khiển engine.

## 5. Cổng định chế minh bạch (giải mâu thuẫn với CLAUDE.md điều luật #7)

CLAUDE.md/SPEC.md cấm *tuyệt đối* mọi định chế có tên trong `engine/`. Thực tế code đã có
`ChinhQuyen`, thuế, bạo động, `xu`, pháp nhân. Charter này **thay thế** lệnh cấm tuyệt đối bằng
một cổng có điều kiện (chi tiết & lý do trong `docs/adr/0001-scope-and-institutional-layers.md`):

> Một module định chế có tên (`credit`, `money`, `fiscal`, `government`…) chỉ được tồn tại
> trong engine khi thỏa ĐỒNG THỜI:
> 1. **Alternative**: có cơ chế thay thế khả thi để không dùng nó;
> 2. **Cost**: tạo/duy trì nó tiêu tốn lao động/tài nguyên đo được;
> 3. **Accounting identity**: mọi flow có đối ứng, đóng phương trình bảo toàn, audit được;
> 4. **Scenario flag**: bật/tắt qua config overlay, không hardcode luôn-bật;
> 5. **Ablation**: có thí nghiệm tắt nó và outcome dự báo trước.
>
> Không thỏa đủ 5 → module không được vào engine, hoặc phải chuyển thành treatment tường minh.

**Anti-teleology (INVARIANT, không được nới):** trong `agrarian_transition_v1`, KHÔNG có năm
cố định, ngưỡng Gini, nhãn hay milestone nào *trực tiếp* gây ra tiền, chính phủ, công nghiệp
hóa, tái phân phối hay một giai cấp có tên. Các sự kiện này chỉ có thể là *outcome* của
ngưỡng/chi phí/niềm tin đã công bố và đo được.

## 6. Hai track scenario không lẫn nhau

- **`preindustrial_closed_v1`** — *legacy mechanism/regression benchmark*. Giữ nguyên để replay
  và hồi quy; **không** retcon thành lịch sử thật. Có thể giữ nhãn regression "median
  industrialization label" như một *legacy label riêng*, KHÔNG phải tiêu chí khoa học.
- **`agrarian_transition_v1`** — benchmark mới cho đường: nông nghiệp → trao đổi/chợ → tín dụng
  → tiền hàng hóa → năng lực tài khóa/công quyền. `validation_tier: mechanism_benchmark` cho
  tới khi có data + calibration + holdout thật. Các lớp hộ–chợ–tín dụng–tiền–tài khóa **bật/tắt
  theo scenario flag**; chính trị/bạo động/thuế Gini-gate **mặc định TẮT** ở track này (chỉ bật
  như treatment có action/cost/participation, ADR 0001 §C).

Không được dùng kết quả của track này làm bằng chứng cho track kia.

## 7. Giới hạn đã biết (phải nêu trong mọi report)

- Tham số phần lớn là `design_assumption`, chưa có provenance dữ liệu.
- Chưa có holdout/backtest → chưa có claim tầng 4.
- LLM policy là nguồn giả định lớn (prompt/model/temperature); kết luận cơ chế chính **không
  được phụ thuộc** LLM.
- Kiểm định phản chứng/placebo còn đang tự động hóa (T10).
- Một run = một lịch sử khả dĩ; phải báo phân phối theo seed, không báo một run "đẹp".

## 8. Cấm (checklist rút gọn, bản đầy đủ ở TASKS §5)

Không có: milestone/năm/Gini trực tiếp tạo định chế; output mô hình dùng làm calibration target
không có source/holdout; `or <giá cứng>` fallback trong quyết định kinh tế; event tạo tiền/của
công/nợ/đất/hàng không có nguồn + đối ứng; report gọi mock/one-seed/legacy là empirical; xóa âm
thầm test/scenario/report/data để gate xanh.
