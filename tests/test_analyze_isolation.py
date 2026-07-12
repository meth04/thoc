"""Phân tích run phải nằm trong run, không còn đè báo cáo global của run trước."""

from __future__ import annotations

import json

import tools.analyze as analyze


def test_analyze_run_ghi_vao_thu_muc_duoc_chi_dinh(tmp_path, monkeypatch):
    data = tmp_path / "runs"
    run_dir = data / "sample"
    run_dir.mkdir(parents=True)
    (run_dir / "metrics.jsonl").write_text(
        json.dumps({"tick": 1, "nam": 0, "dan_so": 2, "gini_dat": 0.0,
                    "gini_thoc": 0.0, "ty_le_biet_chu": 0.0, "tri_thuc": 0.0,
                    "giai_cap": {}, "cong_nghiep_hoa": False}) + "\n", encoding="utf-8"
    )
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr(analyze, "DATA_DIR", data)
    output = tmp_path / "own-output"
    report = analyze.analyze_run("sample", output)
    assert report == output / "final_analysis.md"
    assert report.exists()
    assert (output / "sample_tong_quan.png").exists()
    assert not (tmp_path / "reports" / "final_analysis.md").exists()
