"""Transcript-replay (P1 reproducibility): ghi mọi call → replay KHÔNG mạng → cùng hash.

Chứng minh cổng REPRODUCIBILITY reviewer đòi bằng MOCK + REAL(FakeTransport) — không một
call API thật nào (điều luật #5). Xác nhận: replay-from-transcript == world-hash gốc,
prompt_hash tất định, che key, manifest có 3 field mới.
"""

from __future__ import annotations

import pytest

from minds.gateway import LLMRequest
from minds.providers_real import LoiHetQuota
from minds.transcript import (
    TranscriptProvider,
    TranscriptReader,
    TranscriptWriter,
    bam_prompt,
    tao_mind_replay,
)
from tests.helpers import chay_tick, the_gioi_test
from tools.experiments import build_manifest


# ---------- prompt_hash tất định ----------
def test_prompt_hash_tat_dinh():
    assert bam_prompt("abc") == bam_prompt("abc")
    assert bam_prompt("abc") != bam_prompt("abd")
    assert len(bam_prompt("abc")) == 64  # sha256 hex


# ---------- che key (transcript không chứa secret) ----------
def test_transcript_khong_lo_key(tmp_path):
    w = TranscriptWriter(tmp_path / "transcript.jsonl")
    w.ghi(1, "T0", "aistudio", "m", 0.9,
          prompt="hỏi model key=SECRET123abc xem sao",
          response_raw="ừ Bearer TOKENxyz789 đây", tok_in=1, tok_out=1)
    w.dong()
    txt = (tmp_path / "transcript.jsonl").read_text(encoding="utf-8")
    assert "SECRET123abc" not in txt
    assert "TOKENxyz789" not in txt
    assert "key=***" in txt and "Bearer ***" in txt


def test_transcript_ghi_va_replay_loi_provider_khong_tao_miss(tmp_path):
    """Lỗi terminal là outcome có thể replay, không phải một transcript miss giả."""
    path = tmp_path / "transcript.jsonl"
    writer = TranscriptWriter(path)
    writer.ghi(
        3, "T1", "loi", "", 0.9, "prompt có quota", "[LOI] hết quota", 0, 0,
        error_type="LoiHetQuota", error_message="hết quota",
    )
    writer.dong()

    reader = TranscriptReader(path)
    provider = TranscriptProvider(reader)
    with pytest.raises(LoiHetQuota, match="hết quota"):
        provider.goi(LLMRequest(prompt="prompt có quota", ctx={}, tier="T1", batch_ids=["A0001"]))
    assert reader.misses == 0
    assert reader.con_lai() == 0


# ---------- manifest có 3 field mới (không phá chữ ký cũ) ----------
def test_manifest_co_3_field_moi():
    m = build_manifest(
        run_name="r", mode="mock", seed=1, ticks_requested=2, config_digest="deadbeef",
        config_overlays=[], scenario=None, prompt_template_hash="ph42",
        model_snapshot=["mock/personabot"], temperature={"mock": None},
    )
    repro = m["reproducibility"]
    assert repro["prompt_template_hash"] == "ph42"
    assert repro["model_snapshot"] == ["mock/personabot"]
    assert repro["temperature"] == {"mock": None}


def test_manifest_khong_field_moi_giu_none():
    m = build_manifest(run_name="r", mode="rulebot", seed=1, ticks_requested=2,
                       config_digest="x", config_overlays=[], scenario=None)
    repro = m["reproducibility"]
    assert repro["prompt_template_hash"] is None
    assert repro["model_snapshot"] is None
    assert repro["temperature"] is None


# ---------- MOCK: ghi transcript → replay → world-hash TRÙNG ----------
def _the_gioi_mock():
    return the_gioi_test(seed=73, giu_lai=10, thoc_moi_nguoi=2000)


def test_mock_replay_tu_transcript_trung_hash(tmp_path):
    from minds.orchestrator import tao_mind_mock

    # p_malformed=0: mock chia sẻ da_nham (side-effect NGOÀI transcript) — với malformed,
    # PersonaBot vẫn nhắm thửa rồi mới hỏng text, phần nhắm đó không tái dựng được từ
    # transcript. p=0 ⇒ mọi thinker parse được ⇒ da_nham tái dựng đủ từ canh_thua. (Đường
    # repair fence-markdown được test_real_replay_* phủ qua transport_ngoan.)
    w = _the_gioi_mock()
    orig = tmp_path / "orig"
    mind = tao_mind_mock(w, fast=True, run_dir=orig, p_malformed=0.0,
                         transcript_path=orig / "transcript.jsonl")
    chay_tick(w, mind, 6)
    mind.log.dong()
    mind.transcript.dong()
    h_goc = w.world_hash()

    reader = TranscriptReader(orig / "transcript.jsonl")
    assert reader.tong > 0, "phải có call được ghi (nếu không thì test vô nghĩa)"

    # replay: KHÔNG dùng MockProvider (PersonaBot) — response chỉ đến từ transcript
    w2 = _the_gioi_mock()
    mind2 = tao_mind_replay(w2, w2.cfg, "mock", reader, p_malformed=0.0)
    chay_tick(w2, mind2, 6)

    assert w2.world_hash() == h_goc, "replay-from-transcript phải trùng world-hash gốc"
    assert reader.misses == 0, "mọi prompt phải tìm được trong transcript"
    assert reader.con_lai() == 0, "mọi response ghi phải được tiêu thụ đúng một lần"


# ---------- REAL (FakeTransport): ghi transcript → replay → world-hash TRÙNG ----------
def _the_gioi_real():
    w = the_gioi_test(seed=71, giu_lai=6, thoc_moi_nguoi=2000)
    w.cfg.raw()["minds"]["dung_cong_cu_the_gioi"] = False  # MCP tắt (test đường base)
    return w


def test_real_replay_tu_transcript_trung_hash(tmp_path):
    from minds.real import MindReal
    from tests.test_real_mind import lam_env, transport_ngoan

    w = _the_gioi_real()
    orig = tmp_path / "orig"
    mind = MindReal(w, orig, w.cfg, lam_env(), tmp_path / "quota.sqlite",
                    transport=transport_ngoan(), cho_toi_s=2.0,
                    transcript_path=orig / "transcript.jsonl")
    chay_tick(w, mind, 4)
    mind.log.dong()
    mind.transcript.dong()
    h_goc = w.world_hash()
    assert not mind.het_ngan_sach and mind.so_call > 0

    reader = TranscriptReader(orig / "transcript.jsonl")
    w2 = _the_gioi_real()
    mind2 = tao_mind_replay(w2, w2.cfg, "real", reader)
    chay_tick(w2, mind2, 4)

    assert w2.world_hash() == h_goc, "replay real-from-transcript phải trùng world-hash"
    assert reader.misses == 0
    assert reader.con_lai() == 0
