# T13 — Kế hoạch chia việc & trạng thái (spatial livelihood economy)

Ngày: 2026-07-12. Owner: integration-manager. Design: `docs/adr/0005-spatial-livelihood-economy.md`
(model-architect). Audit nền: Explore agent.

## Quyết định thiết kế chốt (ADR 0005)
- Calendar: **GIỮ 2 tick/năm**; vụ đông = lựa chọn canh mùa khô (không đổi đơn vị thời gian → không
  phá hash/replay legacy). Phương án 3-mùa/tick BỊ BÁC.
- Toàn bộ cơ chế mới **scenario-gated OFF** qua overlay tùy chọn `spatial_v1.yaml`
  (`cfg.get("khong_gian.*", False)`) — KHÔNG thêm key base world.yaml → config-digest + world-hash
  legacy bất biến khi TẮT. State mới ở ledger/parcels + pool ngoài-hash (tiền lệ `ca_ton`).

## Audit: ĐÃ CÓ vs MỚI (không code lại cái đã có)
| Nhóm | Trạng thái | Ghi chú |
|---|---|---|
| Thuê đất (clause) | ✅ ĐỦ | `quyen_su_dung`/`chia_san_luong`/tô/đổi công; chủ không tự thu tô (`production.py:190`) |
| Work order | ✅ = `gop_cong`+payment | không cần primitive mới (ADR) |
| Cá (renewable) | ✅ ĐỦ | stock/K/logistic regen/CPUE/depletion/event |
| Homestead khai hoang | ✅ | canh 2 mùa mưa đất công → sở hữu |
| Xây nhà + thuê thợ | ✅ = `xay`+`gop_cong` | |
| Sông trên map | ✅ (parcel `song`) | nhưng KHÔNG có 2-bờ/reachability |
| Gà rừng | ⚠️ MỘT PHẦN | bắt được nhưng KHÔNG có commons stock/regen (mint theo công) |
| Endowment | ⚠️ | 200kg thóc cứng, chưa food-equivalent |
| Vụ đông | ❌ | chỉ cây "thoc" |

## MỚI cần code (qua cổng §5, gated OFF)
Two-bank topology + ferry-service (flagship), cross-river clearing, wild-chicken commons stock,
food-equiv endowment, winter crop, childcare, policy-awareness, spatial metrics, tests.

## Phân pha theo file-ownership (tránh đụng world.py/tick.py)
- **A (PARALLEL-safe, đang chạy)**: `engine/spatial.py`+`Parcel.bo`(types.py)+two-bank(worldmap.py)
  +overlay `spatial_v1.yaml`+test. KHÔNG đụng world.py/tick.py.
- **Serial engine (một engine-surgeon mỗi lần, đụng world.py/tick.py/production.py/intents.py)**:
  ferry+topology-movement (flagship) → clearing → winter crop → wild-chicken stock → childcare.
- **PARALLEL sau engine**: policy (minds/policies.py), metrics (metrics_research.py/observatory), tests.

## Ưu tiên thực thi (nhanh nhất + an toàn) — TRẠNG THÁI
1. ✅ A (nền spatial.py + Parcel.bo + two-bank + overlay) — 247 passed, OFF=legacy hash.
2. ✅ **Ferry + topology-movement** (flagship) — 261 passed, OFF=legacy hash chứng minh trực tiếp,
   ON hoạt động (no-ferry→kẹt bờ, fare-thóc-trước-tiền, capacity, hao mòn, determinism).
3. 🔄 PARALLEL: clearing bờ kia + endowment food-equiv (engine) · spatial-aware policy (minds) ·
   spatial metrics (observation).
4. Kế tiếp: mock test (pytest) + rulebot-spatial 50y trial + evaluate.
5. **HOÃN có chủ đích (ADR-designed PENDING, không bịa hoàn thành)**: vụ đông (E), gà rừng commons
   (F), chăm trẻ (G) — depth bổ sung, KHÔNG thiết yếu cho trial spatial+ferry+clearing hay cho mục
   tiêu xuất bản; ưu tiên budget cho evaluate + design re-eval + cải tiến hướng bài báo.

## Sau T13: đánh giá + cải tiến hướng xuất bản (goal mới của user)
Chạy mock test + 50y trial → đánh giá kết quả spatial economy → đánh giá lại thiết kế toàn dự án
(dùng `REVIEW.md` + `reports/world_class_readiness.md`) → cải tiến hướng bài phương pháp LLM-ABM
(hạt nhân: phát hiện **real50 ≠ mock50** đã có) + robustness ensemble (paired-seed + sensitivity
runner đã có) + siết benchmark/reproducibility. KHÔNG overclaim empirical khi chưa có data/holdout.

## Ràng buộc
No-network (rulebot/mock only per TASKS §1); scenario-gated OFF giữ legacy hash; conservation/replay
/anti-teleology; observation không điều khiển engine; agent vẫn có thể suy kiệt. §14 ADR: xung đột
CLAUDE #7 (định chế có tên) — ferry/rent/hire là asset+contract combo, nhãn chỉ ở observatory; ghi
DECISIONS.md có chủ ý.
