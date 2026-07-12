# Reality check — review_mock_30y

Mục kiểm: S,P,D,E. Điểm tự phát (S+P+D, 16 mục): **75%**.
C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| S1 | pass | 0 hit trong code engine/. 4 hit chỉ nằm trong comment/docstring (whitelist): engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\entities.py:1: """PHÁP NHÂN + cổ phần (SPEC 3.3) — nguyên tố thứ hai, không phải 'công ty' có tên.; engine\politics.py:217: bạo động ≥ tỷ lệ số đông. Khi đó sung công ty_le_sung_cong thóc của nhóm giàu nhất |
| S2 | pass | Không có config/tech_tree.yaml; grep tech_tree\|unlock_list → 0 (research.yaml chỉ chứa lĩnh vực + phân phối). |
| S3 | pass | Không nhánh if/elif/while nào theo nhãn giai cấp. |
| S4 | pass | Không thấy engine đặt giá: không 'price =' ngoài market, không fallback giá hằng số, không giao dịch lượng cứng qua ledger.chuyen. |
| S5 | fail | 4 hằng số ngoài whitelist (check.md đòi danh sách RỖNG — dồn về config/*.yaml): engine\metrics.py:121=3.0; engine\metrics.py:122=5; engine\metrics.py:159=8; engine\politics.py:237=10 |
| S6 | pass | 12 điểm RNG, tất cả thuộc danh mục cho phép (thời tiết, tie-break, sinh-tử, chăn nuôi, trộm, blueprint, tin đồn, khởi tạo t0, xáo menu): engine\board.py:95:bang_rao; engine\chan_nuoi.py:21:chan_nuoi; engine\demography.py:197:tu_vong; engine\demography.py:97:sinh_con; engine\research.py:89:blueprint; engine\tick.py:183:rao_vat; engine\world.py:128:thoi_tiet; engine\world.py:438:khoi_tao; engine\xa_hoi.py:62:xa_hoi; minds\prompts.py:298:menu_xao; minds\prompts.py:583:nhin_hx; minds\prompts.py:602:tin_don |
| S7 | pass | 0 sự kiện hẹn giờ tuyệt đối. 1 hit đều là chu kỳ tương đối (chứa %): engine\contracts.py:365: if tuoi > 0 and tuoi % ck.moi_n_tick == 0 and _hoat_dong_ca_hai(tu_r, den_r): |
| S8 | pass | mau_khoi_dau = ['doi_cong_lay_thoc_mot_lan', 'cho_muon_co_hoan_tra'] (2 mẫu ≤ 2, đều trao đổi nguyên thủy). |
| P1 | fail | Danh mục định chế trong prompt (ngoài ví dụ JSON): prompts.py:339 ('ngân hàng'): # đúng chữ định chế bị check.md P1 cấm (ngân hàng/công ty/bảo hiểm/xưởng).; prompts.py:339 ('công ty'): # đúng chữ định chế bị check.md P1 cấm (ngân hàng/công ty/bảo hiểm/xưởng).; prompts.py:339 ('bảo hiểm'): # đúng chữ định chế bị check.md P1 cấm (ngân hàng/công ty/bảo hiểm/xưởng).; prompts.py:339 ('xưởng'): # đúng chữ định chế bị check.md P1 cấm (ngân hàng/công ty/bảo hiểm/xưởng). |
| P2 | loi | Không render được: ImportError: cannot import name 'build_batch_prompt' from 'minds.prompts' (C:\Users\nguye\Documents\thoc\minds\prompts.py) |
| P3 | pass | Không có 'thời sơ khai/kỷ nguyên/thời đại' trong prompt render — mô tả thế giới sinh từ trạng thái. |
| P4 | loi | Không render được: ImportError: cannot import name 'build_batch_prompt' from 'minds.prompts' (C:\Users\nguye\Documents\thoc\minds\prompts.py) |
| P5 | pass | prompts.py có cơ chế xáo menu theo seed (menu_xao/shuffle). |
| D1 | pass | mode=mock, ngưỡng 5%; theo model: personabot-T0: 0/910 = 0.00%; personabot-T1: 0/461 = 0.00%; personabot-T2: 0/546 = 0.00%; personabot-T3: 0/72 = 0.00%. run_meta: fallback_rate=0.0 |
| D3 | pass | pytest tests/test_batch_heterogeneity.py -q → 1 passed in 1.12s |
| D4 | pass | Không có unrecognized_intents.jsonl (0 intent lạ). |
| E1 | khop | n=81 người lớn (tick 60); mean=5023 > median=4325: lệch phải; top 20% giữ 52.5%; Hill α=4.45 (n đuôi=17). Quy luật này KHÔNG được mã hóa trong engine: engine/metrics.py chỉ ĐO gini; giá duy nhất từ khớp lệnh cung–cầu (engine/market.py) và sealed-bid đất; không cơ chế phân phối/tái phân phối hay hành vi theo giai cấp nào trong engine/. |
| E4 | lech | corr(dân số, thóc/người) = +0.862 trên 30 tick (đất công chưa cạn — dùng nửa sau của run (tham khảo)) — chưa nghịch chiều. Quy luật không được mã hóa: engine/demography.py chỉ có sinh học vi mô (p_sinh × an ninh hộ × ý định), không phương trình vĩ mô nào nối dân số với lương thực. |
| E6 | khong_du_du_lieu | Chỉ 0 entity từng ký HĐ gop_cong (<5). |
| E7 | khong_du_du_lieu | Chỉ 0 giao dịch/niêm yết đất (<8). |

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
