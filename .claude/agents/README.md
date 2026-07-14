# THÓC agent team — vận hành tự chủ, kiểm chứng được

Các agent trong thư mục này là một nhóm phản biện–triển khai cho THÓC. Mục tiêu không phải
làm mô phỏng “trông như một nền kinh tế phát triển”, mà là xây một mechanism benchmark trong
đó mọi kết quả truy ngược được về vật lý, quyền, hạch toán, thông tin và quyết định đã thực
thi. Kết quả không hình thành tiền, chính phủ, nghề mới hoặc sụp đổ dân số vẫn là kết quả hợp
lệ.

## Thứ tự quyền lực và phạm vi

Đọc trước mọi thay đổi lớn theo thứ tự:

1. yêu cầu hiện tại của người dùng;
2. `Report_v2.md` cho chương trình sau `real60_spatial`;
3. `CLAUDE.md`, `docs/MODEL_CHARTER.md`, ADR 0001–0005;
4. `TASKS.md`, `REVIEW.md`, scenario/run artifact và code/tests liên quan.

Nếu tài liệu mâu thuẫn, `spec-governor` phải ghi một ADR/decision với file:line, tác động và
migration. Không agent nào tự chọn văn bản có lợi cho implementation. `Report_v2.md` có ưu
tiên đối với những task cũ còn mở khi chúng cùng nói về real60, autonomy, household, ecology
hoặc reproducibility.

## Luật chung bắt buộc

- Không gọi provider/API/LLM thật, mode `real`, `--smoke`, WebSearch, MCP từ xa hay đọc `.env`.
  Chỉ dùng local rulebot/mock, FakeTransport/MockTransport và transcript fixture. Mọi Python
  command dùng `conda run -n thoc-env python ...`; bật `THOC_BLOCK_NETWORK=1` cho test/run.
- Không reset, checkout, clean, stash, stage, commit, push hay ghi đè artifact người dùng nếu
  chưa được yêu cầu rõ. Không sửa file ngoài work package.
- LLM/policy không được mutate `World`; mọi flow tài sản/nợ/tài nguyên/công quỹ dùng ledger +
  FlowRegistry và có đối ứng. Mọi RNG đi qua `w.rng`; mọi replay cần seed/config/prompt/catalog
  identity và thứ tự deterministic.
- Không hard-code đường phát triển, nghề, giá, wage, outcome, seed hay threshold để tạo kết quả
  mong muốn. Một fact card cho agent là dữ kiện quan sát được, không phải lời khuyên phải làm gì.
- Không giảm assertion, skip test, nới tolerance, đổi nhãn report hoặc bỏ replay để biến fail
  thành pass. Artifact resume không replay được phải ghi `diagnostic_only_unreplayable`.
- Claim luôn có nhãn `design assumption`, `mechanism result`, `calibrated fact`, hoặc
  `validated result`. Mock/rulebot/one seed là technical/mechanism evidence, không phải
  empirical validation.
- Reviewer/QA/reproducibility auditor không sửa code hoặc test để finding biến mất. Người viết
  code không tự phê duyệt code/test/report của mình.

## Vòng thực thi tự chủ

Claude Code không hỏi người dùng về chi tiết nhỏ. Nếu chưa được chỉ rõ, chọn phương án nhỏ
nhất bảo toàn invariants, ghi ADR/`DECISIONS.md`, rồi tiếp tục. Chỉ dừng khi không thể bảo toàn
thay đổi người dùng hoặc không thể thực hiện một hành động không phá hủy mà thiếu quyền.

1. `integration-manager` đọc `Report_v2.md`, chụp `git status`, tạo dependency/evidence ledger
   và khóa P0 trước P1–P4.
2. `spec-governor`, `research-planner`, economist phù hợp và `model-architect` viết scope,
   state ownership, accounting identities, alternatives, failure cases và acceptance matrix.
3. Một implementer duy nhất sở hữu từng module tại một thời điểm (`engine-surgeon`,
   `minds-engineer`, `graph-architect`, hoặc `implementation-engineer`). Không để hai agent sửa
   cùng một file tùy tiện.
4. `test-engineer` thiết kế regression/property/negative/replay test độc lập. Test là contract,
   không là màu áo cho code đã có.
5. `qa-verifier`, `reproducibility-steward`, `reality-auditor` và `adversarial-reviewer` kiểm
   diff/artifact độc lập. Blocking finding phải có owner + sửa + evidence, hoặc package chưa xong.
6. `integration-manager` chỉ tổng hợp fact: file thay đổi, command/output, verdict và rủi ro.

Với mỗi package, lưu memo ngắn tại `docs/reviews/<package>-<role>.md` (hoặc đường dẫn đã có)
gồm: phạm vi, input evidence `file:line`, assumption, invariant/identity, command, raw result,
verdict, finding còn mở. Không đánh dấu done chỉ vì đã viết một kế hoạch.

## Gates không được đảo thứ tự

| Gate | Điều kiện tối thiểu | Không được suy ra |
|---|---|---|
| P0 interface/artifact | prompt đúng config; engine↔schema↔translate↔menu parity; resume/transcript replay khép kín | LLM đã hành xử hợp lý |
| P1 social/feasibility | residence/estate/project/labor có ledger, deterministic test | mortality/welfare đã thực tế |
| P2 spatial ecology | stock-flow rừng/gà/đò/crop có ablation và audit | nghề sẽ tự xuất hiện |
| P3 autonomy | local fact/tool/action-result/A2A settlement coverage qua fixture | LLM sẽ sáng tạo trong real run |
| P4 research artifact | metrics/executed outcomes, replay, manifest, uncertainty protocol | empirical validation |

`real60_spatial` cũ không qua transcript-resume gate nên chỉ là artifact chẩn đoán. Không dùng nó
để kết luận về tuổi thọ, collapse, money hay provider trước khi P0 pass và có một artifact mới
replay được.

## Chọn agent nhanh

| Nhu cầu | Owner chính | Reviewer/gate độc lập |
|---|---|---|
| Mâu thuẫn charter/scenario/code | `spec-governor` | `adversarial-reviewer` |
| Plan/giả thuyết/ablation | `research-planner` | `sim-economist` |
| Residence, lifecycle, estate, mortality | `household-demography-specialist` | `agrarian-economist` + `engine-surgeon` |
| Land, season, crop, labor, rent | `agrarian-economist` | `sim-economist` |
| Forest, common-pool, river/ferry | `spatial-ecology-specialist` | `reality-auditor` |
| World state, ledger, project, resume mutation | `engine-surgeon` | `test-engineer` |
| Prompt, catalog, local tools, A2A protocol | `minds-engineer` + `agent-autonomy-protocol-designer` | `qa-verifier` |
| Module boundary/API/migration | `model-architect` | `engine-surgeon` |
| Money/credit/fiscal extension | `monetary-fiscal-economist` | `reality-auditor` |
| Tests | `test-engineer` | `qa-verifier` |
| Artifact/replay/provenance | `research-artifact-integrity-auditor` | `reproducibility-steward` |
| Calibration/empirical claim | `empirical-validation` | `adversarial-reviewer` |
| Release/status | `integration-manager` | all gate verdicts required |

## Handoff format

Mỗi agent trả đúng các phần sau, ngắn nhưng kiểm chứng được:

```text
Verdict: PASS | PASS WITH RISKS | FAIL | DESIGN ONLY
Scope / files examined or changed:
Evidence: file:line, command và output chính
Invariants / acceptance criteria:
Findings: severity, reproduction, owner, required fix
Claim boundary: điều gì kết quả chứng minh và không chứng minh
Next handoff: agent + input cần thiết
```

`technical-ready`, `mechanism-ready`, `research-ready` và `empirically-validated` là bốn trạng
thái khác nhau. Không gọi trạng thái nào cao hơn nếu evidence không có.
