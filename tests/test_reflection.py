"""PART 5.3 — tự phản tư: niềm tin cốt lõi tự phát từ ký ức + ân oán (uy tín xã hội)."""

from __future__ import annotations

from tests.helpers import chay_tick, the_gioi_test


def test_reflection_sinh_niem_tin_tu_an_oan():
    """Kẻ bị nhiều người oán → các nạn nhân ghi 'đề phòng X' trong niềm tin (heuristic)."""
    from minds.orchestrator import tao_mind_mock

    w = the_gioi_test(seed=7, giu_lai=6, thoc_moi_nguoi=2000.0)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    ke_gian = ids[0]
    # ke_gian bị mọi người còn lại oán (mô phỏng đã bội tín/trộm nhiều lần)
    for nn in ids[1:]:
        w.cong_quan_he(ke_gian, nn, -4.0)
    # một cặp thân nhau
    w.cong_quan_he(ids[1], ids[2], 3.0)
    mind = tao_mind_mock(w, fast=True)
    n = int(w.cfg.get("minds.reflection_moi_n_tick"))
    mind._reflection(w)  # gọi trực tiếp phản tư
    # nạn nhân phải "đề phòng" kẻ gian (uy tín xấu tự phát từ trí nhớ tập thể)
    ten_gian = w.agents[ke_gian].ten
    de_phong = [nn for nn in ids[1:] if ten_gian in (w.agents[nn].niem_tin or "")
                and "đề phòng" in w.agents[nn].niem_tin]
    assert len(de_phong) >= 3
    # người được thương thì xuất hiện trong "tin cậy"
    assert "tin cậy" in (w.agents[ids[1]].niem_tin or "")
    assert n >= 1


def test_reflection_khong_pha_tat_dinh():
    """Reflection heuristic tất định: cùng seed → cùng niềm tin sau khi chạy tick."""
    from minds.orchestrator import tao_mind_mock

    def chay():
        w = the_gioi_test(seed=13, giu_lai=8, thoc_moi_nguoi=1500.0)
        mind = tao_mind_mock(w, fast=True)
        n = int(w.cfg.get("minds.reflection_moi_n_tick"))
        chay_tick(w, mind, n)  # tới đúng tick reflection chạy
        return {aid: w.agents[aid].niem_tin for aid in sorted(w.agents)
                if w.agents[aid].con_song}

    assert chay() == chay()  # tất định


def test_niem_tin_khong_lam_dan_so_sup():
    """Chạy mock ngắn với reflection bật — audit xanh, thế giới vẫn chạy."""
    from minds.orchestrator import tao_mind_mock

    w = the_gioi_test(seed=9, giu_lai=10, thoc_moi_nguoi=1500.0)
    mind = tao_mind_mock(w, fast=True)
    chay_tick(w, mind, 12)  # audit assert bên trong mỗi tick
    assert any(w.agents[a].niem_tin for a in w.agents if w.agents[a].con_song)
