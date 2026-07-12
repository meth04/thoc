# THÓC agent team — workflow khách quan

Các agent ở đây là các subagent của Claude Code. Mục tiêu là xây THÓC thành môi trường
mô phỏng kinh tế phát triển từ nông nghiệp, trao đổi và tín dụng tới tiền tệ, năng lực
tài khóa và chính phủ — **không** biến một kết quả được lập trình sẵn thành "sự hình
thành tự phát".

## Nguyên tắc chung

- Không agent nào được tự phê duyệt code, test, claim kinh tế hoặc report do chính nó
  tạo. Người làm khác người kiểm; reviewer không sửa để làm finding biến mất.
- Mọi claim ghi một nhãn: `design assumption`, `mechanism result`, `calibrated fact`,
  hoặc `validated result`. Không được nâng nhãn khi không có bằng chứng tương ứng.
- Chạy Python duy nhất qua `conda run -n thoc-env python ...`. Mặc định `rulebot` hoặc
  `mock`; tuyệt đối không chạy mode real, không gọi provider/API, không đọc `.env`.
- Bảo toàn, sổ kép, feasibility, seed/replay và provenance quan trọng hơn biểu đồ đẹp.
  Một kết quả âm, sụp đổ hay không hình thành tiền/chính phủ vẫn là kết quả hợp lệ.
- Không dùng dữ liệu đầu ra của mô hình làm bằng chứng hiệu chuẩn cho chính mô hình.
  Các mục tiêu in-sample, holdout, prior và source phải tách riêng.
- Không thay đổi file không thuộc nhiệm vụ; không reset/revert thay đổi của người khác;
  không commit hoặc gọi mạng trừ khi người dùng yêu cầu rõ.

## Workflow bắt buộc cho một thay đổi nghiên cứu

1. `spec-governor` kiểm mâu thuẫn giữa charter, SPEC, phase plan, code và scenario; chỉ
   sau ADR rõ ràng mới thay đổi luật nền. `research-planner` mở issue/plan có câu hỏi,
   phạm vi, outcome, baseline, giả thuyết
   có thể bác bỏ, seed list và tiêu chí thành công/thất bại.
2. `agrarian-economist` và/hoặc `monetary-fiscal-economist` phản biện cơ chế. Với thay
   đổi lớn, `model-architect` viết interface, state ownership và accounting identities.
3. `implementation-engineer` hoặc agent chuyên môn hiện có (`engine-surgeon`,
   `minds-engineer`, `graph-architect`) triển khai phần đã chốt.
4. `test-engineer` bổ sung test invariant/negative test độc lập với implementation.
5. `qa-verifier` chạy kiểm thử và chỉ báo bằng chứng, không sửa code/test.
6. `reproducibility-steward` kiểm manifest, seed, config hash, output isolation và
   provenance. `adversarial-reviewer` tìm claim quá mức, hard-code và alternative
   explanation. Chỉ khi cả hai không có finding blocking, `integration-manager` mới
   tóm tắt trạng thái cho người dùng.

## Chọn agent nhanh

| Nhu cầu | Agent chính | Agent độc lập phải gọi tiếp |
|---|---|---|
| Mâu thuẫn tài liệu/phạm vi | `spec-governor` | `adversarial-reviewer` |
| Kế hoạch nghiên cứu/scenario | `research-planner` | `adversarial-reviewer` |
| Hộ nông nghiệp, đất, thị trường | `agrarian-economist` | `sim-economist` |
| Tín dụng, tiền, ngân sách, chính phủ | `monetary-fiscal-economist` | `reality-auditor` |
| Thiết kế module/state | `model-architect` | `engine-surgeon` |
| Viết code | `implementation-engineer` | `test-engineer` + `qa-verifier` |
| Calibration/holdout/dữ liệu | `empirical-validation` | `reproducibility-steward` |
| Phản biện bài báo/claim | `adversarial-reviewer` | `qa-verifier` |

`CLAUDE.md`, `SPEC.md`, `PHASES.md` và `REVIEW.md` là tài liệu gốc phải đọc trước khi
đề xuất thay đổi lớn. Nếu chúng mâu thuẫn, agent ghi rõ mâu thuẫn, tác động và đề xuất
một ADR/decision; không lặng lẽ chọn bên thuận tiện.
