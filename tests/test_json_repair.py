"""Corpus ≥80 mẫu JSON hỏng đủ 7 kiểu phá, ≥30 mẫu hợp đồng lồng nhau → cứu ≥95%."""

from __future__ import annotations

import json

import numpy as np

from minds.personabot import KIEU_PHA, pha_json
from minds.repair import parse_batch


def quyet_dinh_don(i: int) -> dict:
    return {
        "id": f"A{i:04d}",
        "hanh_dong": [
            {"loai": "phan_bo_cong", "canh_thua": [f"P{i % 30:02d}_05"], "hoc": i % 2 == 0},
            {"loai": "dat_lenh", "chieu": "mua", "tai_san": "go", "sl": 4, "gia": 12.5},
        ],
        "ly_do": f"Mùa màng năm nay tạm ổn, tôi số {i} cứ thế mà làm.",
    }


def quyet_dinh_hop_dong(i: int) -> dict:
    """Quyết định chứa HỢP ĐỒNG LỒNG NHAU — adversarial áp cả lên phần lồng."""
    return {
        "id": f"A{i:04d}",
        "the_chinh_sach": {"du_tru_muc_tieu": 3.0, "y_dinh_sinh_con": 0.5},
        "hanh_dong": [
            {
                "loai": "de_nghi_hop_dong",
                "den": f"A{(i + 1) % 100:04d}",
                "hop_dong": {
                    "cac_ben": [f"A{i:04d}", f"A{(i + 1) % 100:04d}"],
                    "hinh_thuc": "van_ban" if i % 2 else "mieng",
                    "thoi_han": 8,
                    "the_chap": [f"thua:P{i % 30:02d}_04"] if i % 2 else [],
                    "dieu_khoan": [
                        {"loai": "quyen_su_dung", "tai_san": f"thua:P{i % 30:02d}_04",
                         "tu": f"A{i:04d}", "den": f"A{(i + 1) % 100:04d}"},
                        {"loai": "chia_san_luong", "nguon": f"thua:P{i % 30:02d}_04",
                         "ty_le": 0.4, "den": f"A{i:04d}"},
                        {"loai": "chuyen_giao_mot_lan", "tu": f"A{(i + 1) % 100:04d}",
                         "den": f"A{i:04d}", "tai_san": "thoc", "so_luong": 1000 + i,
                         "tai": "ky_ket"},
                        {"loai": "khi_pha_vo", "phat": "xiet_the_chap"},
                    ],
                },
            },
            {"loai": "yeu_cau_hoan_tra", "ref": f"HD{i:05d}", "so_luong": 2000 + i},
        ],
        "ly_do": "Đất xa nhà, cho cấy rẽ lấy bốn phần.",
    }


def test_corpus_80_mau_cuu_95_phan_tram():
    g = np.random.default_rng(2026)
    corpus: list[tuple[str, list[str]]] = []  # (text hỏng, ids mong đợi)

    # 40 mẫu đơn (5 mẫu × 7 kiểu đơn lẻ) + tổ hợp 2 kiểu
    idx = 0
    for kieu in KIEU_PHA:
        for _ in range(5):
            qd = quyet_dinh_don(idx)
            text = json.dumps([qd], ensure_ascii=False, indent=1)
            corpus.append((pha_json(text, g, so_kieu=1) if False else _pha_kieu(text, kieu, g),
                           [qd["id"]]))
            idx += 1
    # ≥30 mẫu hợp đồng lồng nhau, phá 1-2 kiểu ngẫu nhiên
    for _ in range(35):
        qd = quyet_dinh_hop_dong(idx)
        text = json.dumps([qd], ensure_ascii=False, indent=1)
        corpus.append((pha_json(text, g, so_kieu=int(g.integers(1, 3))), [qd["id"]]))
        idx += 1
    # 10 mẫu batch nhiều người, phá 2 kiểu
    for _ in range(10):
        batch = [quyet_dinh_don(idx + j) for j in range(4)]
        text = json.dumps(batch, ensure_ascii=False, indent=1)
        corpus.append((pha_json(text, g, so_kieu=2), [q["id"] for q in batch]))
        idx += 4

    assert len(corpus) >= 80
    tong_id = sum(len(ids) for _, ids in corpus)
    cuu_duoc = 0
    for text, ids in corpus:
        ok, _hong = parse_batch(text, ids)
        cuu_duoc += len(ok)
    ty_le = cuu_duoc / tong_id
    assert ty_le >= 0.95, f"chỉ cứu được {ty_le:.1%} ({cuu_duoc}/{tong_id})"


def _pha_kieu(text: str, kieu: str, g) -> str:
    """Ép phá đúng MỘT kiểu chỉ định (bảo đảm phủ đủ 7 kiểu)."""
    import minds.personabot as pb

    goc = pb.KIEU_PHA
    pb_kieu = [kieu]
    try:
        pb.KIEU_PHA = pb_kieu
        return pha_json(text, g, so_kieu=1)
    finally:
        pb.KIEU_PHA = goc


def test_fence_va_loi_dan_don_gian():
    qd = quyet_dinh_don(1)
    text = "Dạ thưa, đây ạ:\n```json\n" + json.dumps([qd], ensure_ascii=False) + "\n``` hết ạ."
    ok, hong = parse_batch(text, [qd["id"]])
    assert not hong and qd["id"] in ok


def test_so_kieu_viet_duoc_chuan_hoa():
    text = '[{"id":"A0001","hanh_dong":[{"loai":"yeu_cau_hoan_tra","ref":"HD1","so_luong":"2.000"}]}]'
    ok, hong = parse_batch(text, ["A0001"])
    assert not hong
    assert ok["A0001"].hanh_dong[0].model_dump()["so_luong"] == 2000.0
