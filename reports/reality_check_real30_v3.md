# Reality check — real30_v3

Mục kiểm: S,P,D,E. Điểm tự phát (S+P+D, 16 mục): **62%**.
C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| S1 | pass | 0 hit trong code engine/. 12 hit chỉ nằm trong comment/docstring (whitelist): engine\action_journal.py:329: return "parcel_unreachable", "actor has not reached this bank"; engine\action_journal.py:368: return "parcel_unreachable", f"actor has not reached {parcel_id}'s bank"; engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\entities.py:1: """PHÁP NHÂN + cổ phần (SPEC 3.3) — nguyên tố thứ hai, không phải 'công ty' có tên. (+7 hit nữa) |
| S2 | pass | Không có config/tech_tree.yaml; grep tech_tree\|unlock_list → 0 (research.yaml chỉ chứa lĩnh vực + phân phối). |
| S3 | pass | Không nhánh if/elif/while nào theo nhãn giai cấp. |
| S4 | fail | 'price =' ngoài market.py: engine\quotes.py:154: price = float(raw.get("don_gia", raw.get("gia", 0.0))) |
| S5 | fail | 11 hằng số ngoài whitelist (check.md đòi danh sách RỖNG — dồn về config/*.yaml): engine\action_journal.py:74=8; engine\action_journal.py:72=8; engine\estate.py:160=3; engine\journal.py:200=20; engine\journal.py:214=20; engine\journal.py:734=20; engine\metrics_demography.py:244=100000.0; engine\metrics_demography.py:262=100000.0; engine\world.py:1014=12.0; engine\world.py:329=12.0; engine\world.py:330=12.0 |
| S6 | fail | Điểm RNG lạ: engine\world.py:842: subsystem 'gia_ky_vong' NGOÀI danh mục; engine\world.py:1069: subsystem 'gia_ky_vong' NGOÀI danh mục. Toàn bộ điểm: engine\board.py:105:bang_rao; engine\chan_nuoi.py:21:chan_nuoi; engine\demography.py:118:sinh_con; engine\demography.py:228:tu_vong; engine\research.py:100:blueprint; engine\tick.py:266:rao_vat; engine\world.py:380:thoi_tiet; engine\world.py:403:dich_benh; engine\world.py:842:gia_ky_vong; engine\world.py:1032:khoi_tao; engine\world.py:1069:gia_ky_vong; engine\xa_hoi.py:67:xa_hoi; minds\prompts.py:437:menu_xao; minds\prompts.py:838:nhin_hx; minds\prompts.py:857:tin_don |
| S7 | fail | Điều kiện hẹn giờ tuyệt đối: engine\estate.py:194: if ds.mo_tick == w.tick:; engine\journal.py:439: khop = [e for e in self.manifest.checkpoints if e.tick == int(tick)] |
| S8 | pass | mau_khoi_dau = ['doi_cong_lay_thoc_mot_lan', 'cho_muon_co_hoan_tra'] (2 mẫu ≤ 2, đều trao đổi nguyên thủy). |
| P1 | pass | grep ngân hàng\|công ty\|bảo hiểm\|xưởng ngoài ví dụ JSON → 0 (cả nguồn lẫn bản render seed 42). |
| P2 | pass | Run mới tinh (seed 42, tick 0): 2 mẫu (yêu cầu ≤2). Checkpoint checkpoint_0090.pkl: 0 HĐ hiệu lực → 2 mẫu (top-k=5) rút từ mô-típ thật. |
| P3 | pass | Không có 'thời sơ khai/kỷ nguyên/thời đại' trong prompt render — mô tả thế giới sinh từ trạng thái. |
| P4 | fail | 4 câu mớm ý chiến lược trong prompt render (seed 42): render:68 ('đầu tư'): (đầu tư mở, quy ra ĐIỂM tích lũy riêng cho từng lĩnh vực: 30 công = 1 điểm, 20 kg thóc = 1 điểm, nhâ; render:68 ('càng'): (đầu tư mở, quy ra ĐIỂM tích lũy riêng cho từng lĩnh vực: 30 công = 1 điểm, 20 kg thóc = 1 điểm, nhâ; render:183 ('đầu tư'): (đầu tư mở, quy ra ĐIỂM tích lũy riêng cho từng lĩnh vực: 30 công = 1 điểm, 20 kg thóc = 1 điểm, nhâ; render:183 ('càng'): (đầu tư mở, quy ra ĐIỂM tích lũy riêng cho từng lĩnh vực: 30 công = 1 điểm, 20 kg thóc = 1 điểm, nhâ |
| P5 | pass | prompts.py có cơ chế xáo menu theo seed (menu_xao/shuffle). |
| D1 | fail | mode=real, ngưỡng 10%; theo model: : 1/1 = 100.00%; gc/gemini-2.5-flash-lite: 0/3 = 0.00%; gc/gemini-3.1-flash-lite-preview: 0/100 = 0.00%; gemini-3.1-flash-lite: 0/305 = 0.00%. run_meta: fallback_rate=0.0053 |
| D3 | pass | pytest tests/test_batch_heterogeneity.py -q → 1 passed in 1.09s |
| D4 | pass | 2/409 = 0.49% quyết định có intent lạ; top loại: ['phan_bo_cong×2']. Không loại nào ≥5%. |
| E1 | khong_du_du_lieu | Chỉ 0 người lớn còn sống. |
| E4 | lech | corr(dân số, thóc/người) = +0.000 trên 45 tick (đất công chưa cạn — dùng nửa sau của run (tham khảo)) — chưa nghịch chiều. Quy luật không được mã hóa: engine/demography.py chỉ có sinh học vi mô (p_sinh × an ninh hộ × ý định), không phương trình vĩ mô nào nối dân số với lương thực. |
| E6 | khong_du_du_lieu | Chỉ 0 entity từng ký HĐ gop_cong (<5). |
| E7 | khong_du_du_lieu | Chỉ 0 giao dịch/niêm yết đất (<8). |

## Giới hạn quyết định của artifact `real30_v3`

Artifact này **không được dùng làm bằng chứng cho treatment “tự chủ LLM mọi người”**. Đây là
chẩn đoán của scheduler cũ, không phải một thất bại kinh tế có thể so trực tiếp với phiên bản
mới:

- `llm_calls.sqlite` có 189 logical call trên chỉ 22/90 tick có call; tick 1 chỉ có 8 call và
  mỗi tick dao động 1–16. Nó không hề thỏa điều kiện mỗi người trưởng thành có lượt suy nghĩ
  riêng. Tick 22 không có call; tick 23 còn 1 call trước khi người cuối cùng chết; tick 24–90
  chỉ là đuôi dữ liệu 0-actor.
- Dân số về 0 ở tick 23 nhưng driver cũ vẫn ghi tới tick 90. Vì vậy các chỉ số E1/E4/E6/E7 sau
  đó là không có mẫu, không phải quan sát kinh tế dài hạn.
- Toàn bộ 50 tử vong xảy ra trước 40 tuổi (tuổi chết trung bình 28.10): 44 `benh_tat`, 5
  `kiet_suc`, 1 `tu_vong_co_ban`. Trace state cho thấy 50/50 người vô gia cư từ tick 1; health
  trung bình giảm 91.0 → 26.0 ở tick 16 dù thóc/người tăng. Đây là một vòng phơi nhiễm–sức khỏe,
  không phải bằng chứng rằng khan hiếm lương thực tự nhiên đã giết quần thể.

Treatment kế tiếp là `spatial_livelihood_v4.yaml` và phải được ghi provenance riêng:

1. Mỗi người trưởng thành còn sống có **tối thiểu 1, tối đa 10 HTTP request LLM/tick**; retry,
   fail-over và mỗi vòng MCP đều tiêu cùng quota của đúng người đó. Không có batch nhiều agent
   trong một request.
2. Trước tick, gateway kiểm tra headroom RPM theo mạng tier→route (không double-count route T0/T1
   dùng chung). Không đủ cho lượt bắt buộc của toàn cohort thì run dừng **trước khi world time
   tăng**, không chạy nửa làng bằng policy card.
3. Nén hồi ký và reflection mặc định dùng fallback local trong treatment này để 50 decision call
   không vô tình biến thành burst 100 call. Muốn bật chúng phải là ablation riêng và vẫn chịu trần
   10 request của từng agent.
4. Driver mới dừng khi dân số tuyệt chủng; không sản xuất phần đuôi zero-actor.

Các kiểm thử offline phải chứng minh ít nhất: 50 người đầu kỳ → 50 request độc lập, không batch;
không agent nào vượt 10; MCP không tạo request thứ 11; và preflight RPM không tiêu một cohort dở
dang. Chỉ một real run mới, có `metrics.jsonl` audit PASS và không tuyệt chủng sớm, mới có thể thay
thế artifact này trong các bảng đánh giá E.

```
[C] PHẢN CHỨNG COUNTERFACTUAL — đã có runner không sửa config gốc.
  C1–C4 (rulebot, không gọi LLM thật):
     python -m tools.counterfactual --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  Kiểm toàn pipeline mock cục bộ (không gọi provider):
     python -m tools.counterfactual --mode mock --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  C5 so policy cùng seed dùng tools.compare sau khi chạy rulebot/mock cùng horizon.
  Không overwrite run cũ: dùng --prefix mới cho mỗi ensemble.
```
