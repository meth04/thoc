# ADR 0002 — BehaviorPolicy interface (tách hành vi khỏi LLM)

- Status: **Accepted** (2026-07-12)
- Context: `docs/MODEL_CHARTER.md` §3 Lớp-4 (hành vi thay thế được), `TASKS.md` T09, `REVIEW.md`
  §4.3, §7.2 (LLM là treatment, không phải lõi).
- Deciders: research-planner + model-architect (design), minds-engineer (impl), reviewed by
  sim-economist + test-engineer + adversarial-reviewer.

## Context

Hiện `mind_fn` truyền vào `chay_mot_tick(w, mind_fn, ...)` là một callable `(World) ->
dict[str, KeHoach]`. Ba mode hiện có (`rulebot.quyet_dinh_tat_ca`, `orchestrator.tao_mind_mock`,
`real.tao_mind_real`) đều khớp chữ ký này nhưng không có contract chung, không khai báo
version/params vào manifest, và `rulebot` là một heuristic khổng lồ khó tách thành chiến lược.

Kết luận cơ chế chính của một mechanism benchmark KHÔNG được phụ thuộc LLM (charter §3). Do đó
cần một interface hành vi thuần, tất định, thay thế được, với các baseline không-mạng làm nền.

## Decision

### A. Interface

Định nghĩa `minds/policies.py`:

```python
class BehaviorPolicy(Protocol):
    name: str            # định danh ổn định (vào manifest)
    version: str         # đổi khi logic đổi
    params: dict         # tham số khai báo (vào manifest)
    def __call__(self, w: World) -> dict[str, KeHoach]: ...
```

Ràng buộc contract (INVARIANT, có test):
1. **Không mutate World**: policy chỉ ĐỌC `w` và trả `{aid: KeHoach}` (intent). Mọi thay đổi
   state do engine thực hiện sau khi validate (charter Lớp-2/3). Test: snapshot world-hash trước
   và sau khi gọi policy → không đổi.
2. **Tất định/replayable**: mọi ngẫu nhiên qua `w.rng.get(<subsystem>, w.tick)`; cùng seed +
   cùng policy → cùng chuỗi intent → cùng world-hash.
3. **Feasible**: intent phát ra phải khả thi theo observation contract (không đề xuất canh thửa
   không sở hữu/không trống, không bán tài sản không có). Engine vẫn validate lần cuối; policy
   không được dựa vào engine để "lọc rác".
4. **Observation contract**: policy chỉ dùng thông tin công khai của `w` (không đọc state
   "tương lai"/của người khác vượt quyền — giữ bất đối xứng thông tin ở Lớp-4).

### B. Đăng ký & lựa chọn

- `minds/policies.py: REGISTRY: dict[str, Callable[[World], BehaviorPolicy]]`.
- `run.py --policy <name>` (mode rulebot): chọn policy; ghi `policy = {name, version, params}` vào
  manifest (`build_manifest`) để paired-seed swap tái lập được.
- `rulebot` giữ nguyên là baseline hợp lệ, bọc thành `RulebotPolicy` (name="rulebot").

### C. Baseline không-mạng tối thiểu (T09)

1. `feasible_random` — **negative baseline**: mỗi agent chọn NGẪU NHIÊN (seeded) trong tập hành
   động khả thi tối thiểu (canh một thửa sở hữu/trống nếu đủ giống+công; hoặc nghỉ). Không ký hợp
   đồng phức tạp. Dùng để chứng minh kết quả không do "policy thông minh" mà do cơ chế.
2. `subsistence` — luôn ưu tiên canh đủ ăn (tương tự survival-floor nhưng là policy đầy đủ, không
   phải hook). Không đầu tư/không hợp đồng.
3. `adaptive` (PENDING nếu compute/độ phức tạp vượt phiên): kỳ vọng giá thích nghi
   `E_t[p] = α p_t + (1-α) E_{t-1}` + quy tắc tiết kiệm phòng ngừa (REVIEW §4.4). Tham số vào
   manifest. Nếu chưa cài đủ, ghi PENDING với spec, KHÔNG giả là đã có.

### D. LLM là treatment sau cùng

`mock`/`real` chỉ được so sánh SAU khi baseline không-mạng chạy được. Yêu cầu cache/transcript,
hash prompt/model/provider, báo cost/fallback phải có TRƯỚC bất kỳ thí nghiệm real nào (không chạy
trong phiên này). Kết luận cơ chế báo cáo theo policy, paired across seeds, không gộp thầm vào
"kinh tế".

## Consequences

- Cho phép T10 chạy ensemble paired-seed với policy swap (rulebot vs feasible_random vs
  subsistence) để tách "cơ chế" khỏi "policy".
- Chi phí: cần refactor nhẹ `run.py`/`replay.py` để chọn + ghi policy; `replay.py` phải tái tạo
  policy từ manifest (như đã làm với overlay/treatment).
- Rủi ro: `feasible_random` phải THỰC SỰ feasible để không bị engine lọc thành "no-op" (làm hỏng
  ý nghĩa negative baseline). Test phân phối hành động bắt buộc.

## Test (test-engineer, độc lập)
- feasible: intent của mỗi policy khả thi (engine không phải bỏ >X% intent).
- policy swap: cùng scenario + seed, đổi policy → world-hash KHÁC nhau (chứng minh có tác động)
  nhưng accounting/audit vẫn xanh.
- permutation/ordering invariance: xáo thứ tự id đầu vào không đổi kết quả (apply theo sorted-id).
- no-mutation: world-hash trước/sau khi gọi policy không đổi.
- distribution: `feasible_random` tạo phân phối hành động khác `rulebot` (không phải cùng một
  chuỗi).
