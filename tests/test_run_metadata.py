"""Hồi quy cho metadata run/resume: telemetry append-only là nguồn số tổng."""

from __future__ import annotations

import sqlite3

from tools.telemetry import phan_tich


def test_telemetry_tong_hop_moi_phien_tu_mot_log(tmp_path):
    path = tmp_path / "llm_calls.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE llm_calls (tick INTEGER, tier TEXT, provider TEXT, model TEXT, "
        "key_hash TEXT, tok_in INTEGER, tok_out INTEGER, latency_ms INTEGER, "
        "retries INTEGER, fallback INTEGER)"
    )
    con.executemany(
        "INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "T0", "x", "m", "a", 10, 5, 100, 0, 0),
            (2, "T0", "x", "m", "a", 20, 7, 200, 1, 1),
        ],
    )
    con.commit()
    con.close()
    data = phan_tich(path)
    assert data["tong_call"] == 2
    assert data["tok_in"] == 30
    assert data["tok_out"] == 12
    assert data["fallback"] == 1
