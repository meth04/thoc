# Reality check — review_real_30y_v1

Mục kiểm: D. Điểm tự phát (S+P+D, 3 mục): **100%**.
C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| D1 | pass | mode=real, ngưỡng 10%; theo model: gc/gemini-2.5-flash: 0/8 = 0.00%; gc/gemini-2.5-flash-lite: 0/21 = 0.00%; gc/gemini-3.1-flash-lite-preview: 0/723 = 0.00%. run_meta: fallback_rate=0.0 |
| D3 | pass | pytest tests/test_batch_heterogeneity.py -q → 1 passed, 2 warnings in 1.03s |
| D4 | pass | 8/752 = 1.06% quyết định có intent lạ; top loại: ['de_nghi_hop_dong×3', 'xay×2', 'khai_go_cong×2', 'khai_go×1']. Không loại nào ≥5%. |

```
[C] PHẢN CHỨNG COUNTERFACTUAL — đã có runner không sửa config gốc.
  C1–C4 (rulebot, không gọi LLM thật):
     python -m tools.counterfactual --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  Kiểm toàn pipeline mock cục bộ (không gọi provider):
     python -m tools.counterfactual --mode mock --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  C5 so policy cùng seed dùng tools.compare sau khi chạy rulebot/mock cùng horizon.
  Không overwrite run cũ: dùng --prefix mới cho mỗi ensemble.
```
