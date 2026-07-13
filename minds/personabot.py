"""MockLLM PersonaBot (SPEC 7.5) — heuristic persona + trạng thái, trả JSON như LLM thật.

- Dùng ctx MÁY-ĐỌC-ĐƯỢC (không parse prompt).
- Biết 8 công thức hợp đồng (qua lõi rulebot dùng chung), p=0.02 hành động ngẫu hứng.
- Adversarial: p_malformed cố tình phá JSON theo 7 kiểu — áp cả lên hợp đồng lồng nhau.
- Seeded (run seed, agent, tick, attempt) — tất định tuyệt đối.
"""

from __future__ import annotations

import json

import numpy as np

from engine.market import Lenh
from engine.pricing import gia_ky_vong
from engine.world import World
from minds.translate import ke_hoach_thanh_quyet_dinh


def _nhieu(gia_tri: float, g: np.random.Generator, muc: float) -> float:
    """Nhiễu seeded ±muc% vào tham số số (chống bầy đàn, SPEC 4.4)."""
    return round(gia_tri * (1.0 + float(g.uniform(-muc, muc))), 4)


def sinh_quyet_dinh(w: World, aid: str, bc, da_nham: set[str],
                    cau_hon_den: dict[str, list[str]], attempt: int = 0) -> dict:
    """Quyết định của PersonaBot cho một agent — dict QuyetDinh (chưa serialize)."""
    from minds.rulebot import ke_hoach_mot_nguoi

    g = w.rng.get(f"personabot:{aid}:{attempt}", w.tick)
    muc_nhieu = float(w.cfg.get("minds.nhieu_tham_so_so"))
    kh = ke_hoach_mot_nguoi(w, aid, bc, da_nham, cau_hon_den)

    # nhiễu tham số số theo persona-seed
    kh.dat_lenh = [
        Lenh(le.ai, le.chieu, le.tai_san, le.so_luong, _nhieu(le.gia, g, muc_nhieu),
             le.thanh_toan)
        for le in kh.dat_lenh
    ]
    kh.niem_yet_dat = [(t, _nhieu(gia, g, muc_nhieu)) for t, gia in kh.niem_yet_dat]
    kh.tra_gia_dat = [(t, _nhieu(gia, g, muc_nhieu)) for t, gia in kh.tra_gia_dat]

    # p=0.02 hành động "ngẫu hứng" hợp lệ
    if g.random() < 0.02:
        a = w.agents[aid]
        lua = int(g.integers(0, 3))
        if lua == 0 and w.ledger.so_du(aid, "thoc") > 300:
            gia_go = gia_ky_vong(w, aid, "go")
            kh.dat_lenh.append(Lenh(aid, "mua", "go", 1.0, _nhieu(gia_go * 1.2, g, 0.2)))
        elif lua == 1 and w.ledger.so_du(aid, "go") > 1:
            gia_go = gia_ky_vong(w, aid, "go")
            kh.dat_lenh.append(Lenh(aid, "ban", "go", 1.0, _nhieu(gia_go * 0.8, g, 0.2)))
        elif lua == 2 and a.e_bac < 4:
            kh.hoc = True

    # patch thẻ chính sách theo trạng thái hiện tại (để tick không-nghĩ chạy đúng ý)
    p5 = w.agents[aid].persona
    patch = {
        "du_tru_muc_tieu": round(1.5 + p5.tiet_kiem / 3.0, 2),
        "canh_toi_da": 3,
        "khai_go_khi_ranh": p5.cham_chi >= 5,
        "hoc_khi_du_an": p5.trong_hoc >= 7,
        "y_dinh_sinh_con": kh.y_dinh_sinh_con,
        "nhan_lam_cong_gia_toi_thieu": round(3.0 + 0.35 * p5.hop_tac, 2),
        "nhan_gui_thoc": p5.hop_tac >= 6,
        "ban_go_nguong": 4.0 if p5.cham_chi >= 5 else None,
        "mua_cong_cu_khi_hong": True,
        "nguong_rao_dat": 0.3,
    }
    ly_do = f"Tính {p5.as_dict()}, an cư lạc nghiệp theo mùa."
    return ke_hoach_thanh_quyet_dinh(kh, patch=patch, ly_do=ly_do)


# ------------------------------------------------------------------ adversarial

KIEU_PHA = ["fence", "cat_cuoi", "phay_thua", "quote_cong", "loi_dan", "doi_hoa_thuong",
            "so_kieu_viet"]


def pha_json(text: str, g: np.random.Generator, so_kieu: int = 1) -> str:
    """Cố tình phá JSON theo các kiểu thật gặp ở LLM (SPEC 7.5)."""
    kieu_chon = list(g.choice(KIEU_PHA, size=min(so_kieu, len(KIEU_PHA)), replace=False))
    for kieu in kieu_chon:
        if kieu == "fence":
            text = f"```json\n{text}\n```"
        elif kieu == "cat_cuoi":
            giu = max(1, int(len(text) * 0.85))
            text = text[:giu]
        elif kieu == "phay_thua":
            text = text.replace("}", ",}", 1).replace("]", ",]", 1)
        elif kieu == "quote_cong":
            text = text.replace('"', "“", 3)
        elif kieu == "loi_dan":
            text = "Dạ, đây là quyết định của tôi ạ:\n" + text + "\nMong làng xét cho."
        elif kieu == "doi_hoa_thuong":
            for key in ("loai", "hanh_dong", "tai_san", "so_luong"):
                if g.random() < 0.7:
                    text = text.replace(f'"{key}"', f'"{key.upper()}"', 1)
        elif kieu == "so_kieu_viet":
            import re

            # đổi vài SỐ GIÁ TRỊ ≥1000 thành chuỗi kiểu Việt "1.000" (như LLM hay nhầm);
            # không đụng chữ số nằm trong chuỗi/id
            text = re.sub(
                r"(?<=: )\d{4,6}(?=[,\s}\]])",
                lambda m: '"' + f"{int(m.group(0)):,}".replace(",", ".") + '"',
                text, count=2,
            )
    return text


def tra_loi_mock(w: World, batch: list[dict], p_malformed: float,
                 attempt: int = 0) -> str:
    """Sinh text trả lời cho một batch (mảng JSON theo id), có thể bị phá."""
    g = w.rng.get(f"mock_pha:{batch[0]['id']}:{attempt}", w.tick)
    text = json.dumps(batch, ensure_ascii=False, indent=1)
    if g.random() < p_malformed:
        text = pha_json(text, g, so_kieu=int(g.integers(1, 3)))
    return text
