"""So sánh phải dùng mốc chung và output riêng của thí nghiệm."""

from __future__ import annotations

import json

import tools.compare as compare


def test_ticks_chung_chon_moc_tren_horizon_thuc():
    ma = [{"tick": i} for i in range(1, 13)]
    mb = [{"tick": i} for i in range(3, 15)]
    assert compare.ticks_chung(ma, mb, toi_da=4) == [3, 6, 9, 12]


def test_compare_runs_ghi_output_duoc_chi_dinh(tmp_path, monkeypatch):
    data = tmp_path / "runs"
    for name, population in (("a", 10), ("b", 12)):
        run = data / name
        run.mkdir(parents=True)
        (run / "metrics.jsonl").write_text(
            "\n".join(json.dumps({"tick": tick, "dan_so": population + tick,
                                    "thoc_moi_nguoi": 1, "gini_dat": 0,
                                    "gini_thoc": 0, "ty_le_biet_chu": 0,
                                    "hd_hieu_luc": 0, "so_mo_tip": 0,
                                    "kl_giao_dich": 0, "vo_gia_cu": 0})
                      for tick in (1, 2)) + "\n", encoding="utf-8"
        )
        (run / "run_meta.json").write_text(
            json.dumps({"mode": "rulebot", "seed": 1, "tick_cuoi": 2, "thoi_gian_s": 1}),
            encoding="utf-8",
        )
    monkeypatch.setattr(compare, "DATA_DIR", data)
    output = tmp_path / "result" / "compare.md"
    assert compare.compare_runs("a", "b", output) == output
    content = output.read_text(encoding="utf-8")
    assert "| dan_so | 1 | 11 | 13 |" in content
