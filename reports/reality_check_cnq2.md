# Reality check — cnq2

Mục kiểm: S,P,D,E. Điểm tự phát (S+P+D, 16 mục): **56%**.
C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.

| Mục | Kết luận | Bằng chứng |
|---|---|---|
| S1 | pass | 0 hit trong code engine/. 4 hit chỉ nằm trong comment/docstring (whitelist): engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\contracts.py:3: Engine KHÔNG biết "ngân hàng", "làm thuê", "bảo hiểm"... — chỉ thi hành MỌI tổ hợp; engine\entities.py:1: """PHÁP NHÂN + cổ phần (SPEC 3.3) — nguyên tố thứ hai, không phải 'công ty' có tên.; engine\entities.py:167: # gồm cả hợp đồng VỪA vi phạm trong tick (bank-run): chủ nợ đó vẫn được chia |
| S2 | pass | Không có config/tech_tree.yaml; grep tech_tree\|unlock_list → 0 (research.yaml chỉ chứa lĩnh vực + phân phối). |
| S3 | pass | Không nhánh if/elif/while nào theo nhãn giai cấp. |
| S4 | fail | engine\demography.py:133: ledger.chuyen(..., 20.0, ...) — lượng chuyển hằng cứng; engine\demography.py:257: ledger.chuyen(..., 1.0, ...) — lượng chuyển hằng cứng; engine\entities.py:119: gia_gan_nhat(...) or 300.0 — engine bịa giá |
| S5 | fail | 104 hằng số ngoài whitelist (check.md đòi danh sách RỖNG — dồn về config/*.yaml): engine\audit.py:14=1e-05; engine\board.py:12=4; engine\chan_nuoi.py:38=0.5; engine\chan_nuoi.py:47=0.05; engine\chan_nuoi.py:38=0.5; engine\consumption.py:88=60; engine\consumption.py:24=0.1; engine\consumption.py:92=100.0; engine\consumption.py:96=100.0; engine\consumption.py:101=0.75; engine\consumption.py:83=10.0; engine\contracts.py:291=0.5; engine\contracts.py:263=0.2; engine\demography.py:166=20; engine\demography.py:168=60 (+89 nữa) |
| S6 | fail | Điểm RNG lạ: minds\orchestrator.py:77: subsystem 'batch_xao' NGOÀI danh mục. Toàn bộ điểm: engine\board.py:97:bang_rao; engine\chan_nuoi.py:20:chan_nuoi; engine\demography.py:97:sinh_con; engine\demography.py:181:tu_vong; engine\market.py:142:cho; engine\research.py:76:blueprint; engine\world.py:97:thoi_tiet; engine\world.py:323:khoi_tao; engine\xa_hoi.py:59:xa_hoi; minds\prompts.py:440:nhin_hx; minds\prompts.py:459:tin_don; minds\orchestrator.py:77:batch_xao |
| S7 | pass | 0 sự kiện hẹn giờ tuyệt đối. 1 hit đều là chu kỳ tương đối (chứa %): engine\contracts.py:346: if tuoi > 0 and tuoi % ck.moi_n_tick == 0: |
| S8 | pass | mau_khoi_dau = ['doi_cong_lay_thoc_mot_lan', 'cho_muon_co_hoan_tra'] (2 mẫu ≤ 2, đều trao đổi nguyên thủy). |
| P1 | fail | Danh mục định chế trong prompt (ngoài ví dụ JSON): prompts.py:225 ('xưởng'): - Chủ trại/chủ xưởng: lập pháp nhân, thuê người, sắm máy, bán cổ phần gọi vốn.; render:58 ('xưởng'): - Chủ trại/chủ xưởng: lập pháp nhân, thuê người, sắm máy, bán cổ phần gọi vốn. |
| P2 | pass | Run mới tinh (seed 42, tick 0): 2 mẫu (yêu cầu ≤2). Checkpoint checkpoint_0200.pkl: 395 HĐ hiệu lực → 5 mẫu (top-k=5) rút từ mô-típ thật. |
| P3 | fail | Nhãn thời đại gán sẵn: dòng 1: Bạn sẽ đóng vai TỪNG NGƯỜI dưới đây trong một làng khép kín thời sơ khai (1 tick = 6 tháng). Mỗi ngư |
| P4 | fail | 10 câu mớm ý chiến lược trong prompt render (seed 42): render:18 ('khôn ngoan'): Nhà nhiều thóc nuôi đàn gà là một nguồn thu nhập khôn ngoan.; render:19 ('đầu tư'): - TUỔI TÁC: trẻ dưới 15 KHÔNG làm đồng — cho đi học (day_cho + hoc) là đầu tư đời; render:24 ('nên'): màu gốc); BỎ HOANG thì hồi dần. Nhà nhiều ruộng nên LUÂN CANH cho đất nghỉ.; render:31 ('vốn liếng'): quý mến; quan hệ tốt là vốn liếng khi cần vay mượn, cưới hỏi, làm ăn.; render:38 ('đừng'): - SẮP ĐÓI thì đừng ngồi chờ chết: đi VAY (đề nghị hợp đồng: nhận thóc ngay ký kết,; render:51 ('nên'): - Người chăn nuôi: gây đàn gà, bán gà sống/thịt cho làng — nhà dư thóc càng nên nuôi.; render:51 ('càng'): - Người chăn nuôi: gây đàn gà, bán gà sống/thịt cho làng — nhà dư thóc càng nên nuôi.; render:60 ('quyền lực'): Biết chữ (E1+) mới soạn được VĂN BẢN có thế chấp/cưỡng chế — chữ nghĩa là quyền lực. |
| P5 | fail | prompts.py không xáo thứ tự nguyên tố trong menu theo seed (grep menu_xao\|shuffle\|permutation → 0) — thiên vị vị trí. |
| D1 | pass | mode=mock, ngưỡng 5%; theo model: personabot-T0: 0/899 = 0.00%; personabot-T1: 0/1254 = 0.00%; personabot-T2: 0/7111 = 0.00%; personabot-T3: 0/410 = 0.00%; personabot-T4: 0/305 = 0.00%. run_meta: fallback_rate=0.0 |
| D3 | pass | pytest tests/test_batch_heterogeneity.py -q → 1 passed in 1.06s |
| D4 | pass | 8/9938 = 0.08% quyết định có intent lạ; top loại: ['de_nghi_hop_dong×8']. Không loại nào ≥5%. |
| E1 | khop | n=114 người lớn (tick 200); mean=9786 > median=7906: lệch phải; top 20% giữ 52.7%; Hill α=4.21 (n đuôi=23). Quy luật này KHÔNG được mã hóa trong engine: engine/metrics.py chỉ ĐO gini; giá duy nhất từ khớp lệnh cung–cầu (engine/market.py) và sealed-bid đất; không cơ chế phân phối/tái phân phối hay hành vi theo giai cấp nào trong engine/. |
| E4 | khop | corr(dân số, thóc/người) = -0.020 trên 100 tick (đất công chưa cạn — dùng nửa sau của run (tham khảo)) — nghịch chiều Malthus. Quy luật không được mã hóa: engine/demography.py chỉ có sinh học vi mô (p_sinh × an ninh hộ × ý định), không phương trình vĩ mô nào nối dân số với lương thực. |
| E6 | khop | 11 entity; số HĐ gop_cong/entity: mean=5.6, median=4, max=23, top1 chiếm 37.1% — lệch phải. Quy luật không được mã hóa: engine/entities.py không giới hạn hay khuyến khích quy mô thuê mướn nào. |
| E7 | lech | corr(giá đất, màu mỡ gốc) = -0.298 trên n=55 (ban_dat + niem_yet) — giá đất KHÔNG vốn hóa địa tô. Quy luật không được mã hóa: engine/market.py bán đất bằng sealed-bid first-price, engine không định giá thửa nào. |

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
