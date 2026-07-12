# Reality check — static

Mục kiểm: S,P. Điểm tự phát (S+P+D, 13 mục): **100%**.
C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| S1 | pass | 0 hit trong code engine/. 3 hit chỉ nằm trong comment/docstring (whitelist): engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\entities.py:1: """PHÁP NHÂN + cổ phần (SPEC 3.3) — nguyên tố thứ hai, không phải 'công ty' có tên. |
| S2 | pass | Không có config/tech_tree.yaml; grep tech_tree\|unlock_list → 0 (research.yaml chỉ chứa lĩnh vực + phân phối). |
| S3 | pass | Không nhánh if/elif/while nào theo nhãn giai cấp. |
| S4 | pass | Không thấy engine đặt giá: không 'price =' ngoài market, không fallback giá hằng số, không giao dịch lượng cứng qua ledger.chuyen. |
| S5 | pass | AST-scan engine/: 0 hằng số kinh tế ngoài whitelist. |
| S6 | pass | 13 điểm RNG, tất cả thuộc danh mục cho phép (thời tiết, tie-break, sinh-tử, chăn nuôi, trộm, blueprint, tin đồn, khởi tạo t0, xáo menu): engine\board.py:95:bang_rao; engine\chan_nuoi.py:21:chan_nuoi; engine\demography.py:197:tu_vong; engine\demography.py:97:sinh_con; engine\research.py:89:blueprint; engine\tick.py:157:rao_vat; engine\world.py:392:khoi_tao; engine\world.py:99:thoi_tiet; engine\xa_hoi.py:62:xa_hoi; minds\orchestrator.py:107:batch_xao; minds\prompts.py:252:menu_xao; minds\prompts.py:495:nhin_hx; minds\prompts.py:514:tin_don |
| S7 | pass | 0 sự kiện hẹn giờ tuyệt đối. 1 hit đều là chu kỳ tương đối (chứa %): engine\contracts.py:365: if tuoi > 0 and tuoi % ck.moi_n_tick == 0 and _hoat_dong_ca_hai(tu_r, den_r): |
| S8 | pass | mau_khoi_dau = ['doi_cong_lay_thoc_mot_lan', 'cho_muon_co_hoan_tra'] (2 mẫu ≤ 2, đều trao đổi nguyên thủy). |
| P1 | pass | grep ngân hàng\|công ty\|bảo hiểm\|xưởng ngoài ví dụ JSON → 0 (cả nguồn lẫn bản render seed 42). |
| P2 | pass | Run mới tinh (seed 42, tick 0): 2 mẫu (yêu cầu ≤2). |
| P3 | pass | Không có 'thời sơ khai/kỷ nguyên/thời đại' trong prompt render — mô tả thế giới sinh từ trạng thái. |
| P4 | pass | Prompt render seed 42 không chứa từ mớm ý (nên/khôn ngoan/đầu tư/quyền lực/vốn liếng/đừng/hãy/càng) ngoài ví dụ JSON. |
| P5 | pass | prompts.py có cơ chế xáo menu theo seed (menu_xao/shuffle). |

```
[C] PHẢN CHỨNG COUNTERFACTUAL — chưa tự động hóa. Chạy tay theo check.md mục 3
(mỗi bài 3 seed 41/42/43, 300 năm, --fast; sửa config TẠM rồi hoàn nguyên; so bằng tools/analyze):
  C1 Rút mẫu khởi đầu — sửa config/world.yaml: hop_dong.mau_khoi_dau: [] rồi
     python run.py --mode mock --years 300 --fast --seed 41 --run-name c1_s41
     Đạt: ≥3 mô-típ hợp đồng xuất hiện trước năm 80 dù không có mẫu mồi.
  C2 Đảo persona — patch tạm engine/world.py (xáo persona giữa agent, giữ nguyên bản đồ) rồi
     python run.py --mode mock --years 300 --fast --seed 42 --run-name c2_s42
     Đạt: quỹ đạo vĩ mô (Gini, năm milestones) KHÁC đáng kể bản gốc cùng seed.
  C3 Tắt nhiễu tham số — config minds: nhieu_tham_so = 0 rồi chạy như trên (c3_s4x).
     Đạt: kết quả không đổi về CHẤT (nhiễu chỉ là gia vị, không phải động cơ bất bình đẳng).
  C4 Đổi phân phối thời tiết — world.yaml: tăng p của han_lu rồi chạy (c4_s4x).
     Đạt: kinh tế phản ứng CÓ HƯỚNG (giá thóc cao hơn, dân số thấp hơn).
  C5 Rulebot vs Mock cùng seed —
     python run.py --mode rulebot --years 300 --seed 42 --run-name c5_rb
     python run.py --mode mock --years 300 --fast --seed 42 --run-name c5_mock
     Đạt: quỹ đạo phân kỳ rõ sau ~năm 30 (python -m tools.compare c5_rb c5_mock).
```
