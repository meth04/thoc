"""Smoke test cho tools/reality_check và tools/social_graph (CHỈ ĐỌC, thế giới nhỏ)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.reality_check import chay_kiem_dinh
from tools.social_graph import dung_do_thi, tim_run_dir, xuat_do_thi

REPO = Path(__file__).resolve().parent.parent
RUN_CNQ2 = REPO / "data" / "runs" / "cnq2"


def test_reality_check_muc_s_khong_crash() -> None:
    """Mục S chạy trọn không crash, trả đủ S1-S8 với cấu trúc {muc, ket_luan, bang_chung}."""
    ket = chay_kiem_dinh(["S"])
    assert len(ket) == 8
    assert [k["muc"] for k in ket] == [f"S{i}" for i in range(1, 9)]
    hop_le = {"pass", "partial", "fail", "loi", "khong_du_du_lieu", "khop", "lech"}
    for k in ket:
        assert set(k) == {"muc", "ket_luan", "bang_chung"}
        assert k["ket_luan"] in hop_le
        assert k["bang_chung"]  # mọi kết luận phải kèm bằng chứng


@pytest.mark.skipif(not (RUN_CNQ2 / "checkpoints").is_dir(),
                    reason="thiếu run cnq2 (integration data)")
def test_social_graph_cnq2_ra_json_co_node_va_canh(tmp_path: Path) -> None:
    """social_graph trên run cnq2 xuất JSON đúng schema với ≥1 node và ≥1 cạnh."""
    do_thi, duong = xuat_do_thi(tim_run_dir("cnq2"))
    assert duong.exists()
    tren_dia = json.loads(duong.read_text(encoding="utf-8"))
    assert set(tren_dia) == {"tick", "nam", "nodes", "edges"}
    assert len(tren_dia["nodes"]) >= 1
    assert len(tren_dia["edges"]) >= 1
    node = tren_dia["nodes"][0]
    assert set(node) == {"id", "ten", "tuoi", "gioi_tinh", "lang", "e_bac", "thoc", "so_thua"}
    edge = tren_dia["edges"][0]
    assert set(edge) == {"a", "b", "w", "loai"}
    assert edge["a"] < edge["b"]  # cặp chuẩn hóa
    nhan_hop_le = {"vo_chong", "cha_con", "giam_ho", "hop_dong", "quan_he"}
    assert all(set(e["loai"]) <= nhan_hop_le for e in tren_dia["edges"])
    # tất định: dựng lại từ cùng checkpoint phải ra đúng đồ thị vừa ghi
    from engine.world import World
    from tools.social_graph import chon_checkpoint
    w = World.nap_checkpoint(chon_checkpoint(RUN_CNQ2, None))
    assert dung_do_thi(w, include_dead=False) == do_thi
