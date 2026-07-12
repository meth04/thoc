# Reality check — static

Mục kiểm: S. Điểm tự phát (S+P+D, 8 mục): **100%**.
C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| S1 | pass | 0 hit trong code engine/. 4 hit chỉ nằm trong comment/docstring (whitelist): engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\entities.py:1: """PHÁP NHÂN + cổ phần (SPEC 3.3) — nguyên tố thứ hai, không phải 'công ty' có tên.; engine\politics.py:217: bạo động ≥ tỷ lệ số đông. Khi đó sung công ty_le_sung_cong thóc của nhóm giàu nhất |
| S2 | pass | Không có config/tech_tree.yaml; grep tech_tree\|unlock_list → 0 (research.yaml chỉ chứa lĩnh vực + phân phối). |
| S3 | pass | Không nhánh if/elif/while nào theo nhãn giai cấp. |
| S4 | pass | Không thấy engine đặt giá: không 'price =' ngoài market, không fallback giá hằng số, không giao dịch lượng cứng qua ledger.chuyen. |
| S5 | pass | AST-scan engine/: 0 hằng số kinh tế ngoài whitelist. |
| S6 | pass | 13 điểm RNG, tất cả thuộc danh mục cho phép (thời tiết, tie-break, sinh-tử, chăn nuôi, trộm, blueprint, tin đồn, khởi tạo t0, xáo menu): engine\board.py:95:bang_rao; engine\chan_nuoi.py:21:chan_nuoi; engine\demography.py:197:tu_vong; engine\demography.py:97:sinh_con; engine\research.py:89:blueprint; engine\tick.py:183:rao_vat; engine\world.py:130:thoi_tiet; engine\world.py:154:dich_benh; engine\world.py:461:khoi_tao; engine\xa_hoi.py:62:xa_hoi; minds\prompts.py:298:menu_xao; minds\prompts.py:583:nhin_hx; minds\prompts.py:602:tin_don |
| S7 | pass | 0 sự kiện hẹn giờ tuyệt đối. 1 hit đều là chu kỳ tương đối (chứa %): engine\contracts.py:365: if tuoi > 0 and tuoi % ck.moi_n_tick == 0 and _hoat_dong_ca_hai(tu_r, den_r): |
| S8 | pass | mau_khoi_dau = ['doi_cong_lay_thoc_mot_lan', 'cho_muon_co_hoan_tra'] (2 mẫu ≤ 2, đều trao đổi nguyên thủy). |

```
[C] PHẢN CHỨNG COUNTERFACTUAL — đã có runner không sửa config gốc.
  C1–C4 (rulebot, không gọi LLM thật):
     python -m tools.counterfactual --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  Kiểm toàn pipeline mock cục bộ (không gọi provider):
     python -m tools.counterfactual --mode mock --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  C5 so policy cùng seed dùng tools.compare sau khi chạy rulebot/mock cùng horizon.
  Không overwrite run cũ: dùng --prefix mới cho mỗi ensemble.
```
