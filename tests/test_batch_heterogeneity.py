"""8 persona khác nhau, CÙNG hoàn cảnh → ≥4 khác biệt thực chất (SPEC 4.4)."""

from __future__ import annotations

from engine.types import Persona
from minds.personabot import sinh_quyet_dinh
from tests.helpers import the_gioi_test

PERSONAS = [
    Persona(1, 1, 1, 1, 1),
    Persona(9, 9, 9, 9, 9),
    Persona(9, 2, 3, 8, 2),
    Persona(2, 9, 2, 3, 8),
    Persona(5, 5, 9, 5, 3),
    Persona(3, 7, 1, 9, 9),
    Persona(8, 3, 7, 2, 5),
    Persona(1, 6, 5, 7, 1),
]


def _dau_van(qd: dict) -> tuple:
    """Dấu vân hành vi: tập loại hành động + các tham số số chính."""
    loai = tuple(sorted(h["loai"] for h in qd["hanh_dong"]))
    so = []
    for h in qd["hanh_dong"]:
        for k in ("gia", "sl", "so_luong", "khai_go_cong"):
            if k in h and isinstance(h[k], int | float):
                so.append((h["loai"], k, float(h[k])))
    the = qd.get("the_chinh_sach") or {}
    return loai, tuple(sorted(so)), the.get("du_tru_muc_tieu"), the.get("y_dinh_sinh_con")


def khac_biet_thuc_chat(v1: tuple, v2: tuple) -> bool:
    """Hành động khác HOẶC tham số số lệch >15%."""
    if v1[0] != v2[0]:
        return True
    so1, so2 = dict(((a, b), c) for a, b, c in v1[1]), dict(((a, b), c) for a, b, c in v2[1])
    for k in so1.keys() & so2.keys():
        a, b = so1[k], so2[k]
        if max(abs(a), abs(b)) > 0 and abs(a - b) / max(abs(a), abs(b)) > 0.15:
            return True
    if so1.keys() != so2.keys():
        return True
    for truong in (2, 3):
        a, b = v1[truong], v2[truong]
        if a is not None and b is not None and max(a, b) > 0:
            if abs(a - b) / max(a, b) > 0.15:
                return True
    return False


def test_8_persona_it_nhat_4_khac_biet():
    from minds.rulebot import _BoiCanhTick

    w = the_gioi_test(seed=31, giu_lai=8, thoc_moi_nguoi=1500)
    ids = sorted(a for a, ag in w.agents.items() if ag.con_song)
    # CÙNG hoàn cảnh: cùng tuổi, giới, không đất, cùng thóc — chỉ persona khác
    for aid, p in zip(ids, PERSONAS, strict=True):
        a = w.agents[aid]
        a.persona = p
        a.tuoi_tick = 50
        a.gioi_tinh = "nam"
        a.e_bac = 1
    w.tick = 7  # mùa mưa
    bc = _BoiCanhTick(w)
    quyet_dinh = [
        sinh_quyet_dinh(w, aid, bc, set(), {}) for aid in ids
    ]
    van = [_dau_van(qd) for qd in quyet_dinh]
    # đếm số người khác biệt thực chất so với người ĐẦU TIÊN + đôi một
    khac = set()
    for i in range(len(van)):
        for j in range(i + 1, len(van)):
            if khac_biet_thuc_chat(van[i], van[j]):
                khac.add(i)
                khac.add(j)
    assert len(khac) >= 4, f"chỉ {len(khac)} người khác biệt thực chất: {van}"
