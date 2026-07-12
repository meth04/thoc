"""Công cụ thế giới CHỈ ĐỌC cho vòng agentic (PART 5.2/5.3, REPORTS.md — MCP active).

LLM chủ động "hỏi" thế giới trước khi quyết định: check_weather, get_market_price...
thay vì bị nhồi mọi thứ vào prompt. Hai bất biến sắt:

1. TUYỆT ĐỐI CHỈ ĐỌC (điều luật #1): không hàm nào chạm w.ledger/w.agents/... — chỉ
   đọc và trả JSON. Có test snapshot world_hash trước/sau khi gọi mọi công cụ để chứng minh.
2. TẤT ĐỊNH (điều luật #4): công cụ đọc w tại thời điểm GATHER (trước mọi apply); vòng
   nhiều lượt chỉ ảnh hưởng pha gather, quyết định vẫn apply sorted-id. Replay lại đúng
   transcript nhiều lượt → cùng world-hash.

Tên hàm/tham số bằng tiếng Việt không dấu (LLM gọi được), mô tả tiếng Việt.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from engine.world import World

# Khai báo công cụ theo lược đồ functionDeclarations của Gemini (OpenAI tools tương tự).
# Mỗi mục: {name, description, parameters(JSON Schema)}.
KHAI_BAO_CONG_CU: list[dict[str, Any]] = [
    {
        "name": "xem_thoi_tiet",
        "description": "Xem mùa và thời tiết tick hiện tại (ảnh hưởng năng suất mùa màng).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "gia_cho",
        "description": "Giá khớp gần nhất của một mặt hàng trên chợ làng (kg thóc/đơn vị). "
                       "Trả null nếu chưa từng có phiên chợ cho mặt hàng đó.",
        "parameters": {
            "type": "object",
            "properties": {"tai_san": {"type": "string",
                                       "description": "vd: go, cong_cu, quang_dong, ga, ca, dat"}},
            "required": ["tai_san"],
        },
    },
    {
        "name": "tai_san_cua_toi",
        "description": "Kho tài sản của chính bạn (thóc, gỗ, gà, số thửa ruộng...).",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "dat_cong_gan",
        "description": "Danh sách thửa ruộng công CHƯA ai sở hữu gần làng (id + độ màu mỡ) "
                       "— nơi có thể khai hoang.",
        "parameters": {
            "type": "object",
            "properties": {"toi_da": {"type": "integer", "description": "số thửa tối đa trả về"}},
        },
    },
    {
        "name": "uy_tin_voi",
        "description": "Mức độ thân/oán giữa bạn và một người (số dương = thân, âm = oán).",
        "parameters": {
            "type": "object",
            "properties": {"nguoi": {"type": "string", "description": "id người cần hỏi"}},
            "required": ["nguoi"],
        },
    },
    {
        "name": "nghe_ve",
        "description": "Nghe ngóng ƯỚC LƯỢNG (không chính xác) về của cải/nghề của một người "
                       "khác qua tai nghe mắt thấy — như dân làng đồn đoán nhau.",
        "parameters": {
            "type": "object",
            "properties": {"nguoi": {"type": "string", "description": "id người cần nghe ngóng"}},
            "required": ["nguoi"],
        },
    },
]


def _xem_thoi_tiet(w: World, aid: str, args: dict) -> dict:
    loai, he_so = w.thoi_tiet(w.tick)
    return {"mua": "mưa" if w.mua_mua() else "khô", "thoi_tiet": loai, "he_so_nang_suat": he_so}


def _gia_cho(w: World, aid: str, args: dict) -> dict:
    ts = str(args.get("tai_san", ""))
    return {"tai_san": ts, "gia_gan_nhat": w.gia_gan_nhat(ts)}


def _tai_san_cua_toi(w: World, aid: str, args: dict) -> dict:
    ts = {k: round(v, 1) for k, v in w.ledger.tai_san_cua(aid).items()
          if not k.startswith("vi_the:") and abs(v) > 1e-9}
    so_thua = sum(1 for p in w.parcels.values() if p.chu == aid)
    return {"tai_san": ts, "so_thua_ruong": so_thua}


def _dat_cong_gan(w: World, aid: str, args: dict) -> dict:
    toi_da = int(args.get("toi_da", 5) or 5)
    a = w.agents.get(aid)
    lang = w.villages[a.lang if a and a.lang < len(w.villages) else 0]
    cong = sorted(
        (p for p in w.parcels.values() if p.loai == "ruong" and p.chu is None),
        key=lambda p: (abs(p.r - lang.r) + abs(p.c - lang.c), p.id),
    )[:max(0, toi_da)]
    return {"thua": [{"id": p.id, "mau_mo": round(p.mau_mo, 2)} for p in cong]}


def _uy_tin_voi(w: World, aid: str, args: dict) -> dict:
    nguoi = str(args.get("nguoi", ""))
    return {"nguoi": nguoi, "uy_tin": round(w.uy_tin(aid, nguoi), 2)}


def _nghe_ve(w: World, aid: str, args: dict) -> dict:
    """Ước lượng MỜ (nhiễu seeded theo (người hỏi, người bị hỏi, năm)) — không chính xác."""
    nguoi = str(args.get("nguoi", ""))
    b = w.agents.get(nguoi)
    if b is None or not b.con_song:
        return {"nguoi": nguoi, "biet": "không rõ người này"}
    g = w.rng.get(f"nghe_ve:{aid}:{nguoi}", w.tick // 2)  # ổn định trong năm
    thoc = w.ledger.so_du(nguoi, "thoc")
    ruong = sum(1 for p in w.parcels.values() if p.chu == nguoi)
    ga = w.ledger.so_du(nguoi, "ga") + w.ledger.so_du(nguoi, "ga_con")
    muc = ("khá giả" if thoc > 2000 else "tạm đủ ăn" if thoc > 500 else "nghèo túng")
    chi_tiet = [f"nhà cửa {muc}"]
    if ruong:
        chi_tiet.append(f"~{max(1, round(ruong * float(g.uniform(0.6, 1.4))))} thửa ruộng")
    if ga >= 1:
        chi_tiet.append(f"có nuôi gà (~{max(1, round(ga * float(g.uniform(0.5, 1.5))))} con)")
    return {"nguoi": nguoi, "ten": b.ten, "tuoi": round(b.tuoi_nam),
            "nghe_ngong": "; ".join(chi_tiet)}


CONG_CU: dict[str, Callable[[World, str, dict], dict]] = {
    "xem_thoi_tiet": _xem_thoi_tiet,
    "gia_cho": _gia_cho,
    "tai_san_cua_toi": _tai_san_cua_toi,
    "dat_cong_gan": _dat_cong_gan,
    "uy_tin_voi": _uy_tin_voi,
    "nghe_ve": _nghe_ve,
}


def thuc_thi(w: World, aid: str, ten: str, args: dict | None) -> dict:
    """Thực thi một công cụ CHỈ ĐỌC. Tên lạ → trả lỗi (không raise, không chạm state)."""
    ham = CONG_CU.get(ten)
    if ham is None:
        return {"loi": f"không có công cụ tên '{ten}'"}
    try:
        return ham(w, aid, args or {})
    except Exception as e:  # noqa: BLE001 — công cụ hỏng thì báo lỗi, KHÔNG làm chết vòng
        return {"loi": f"công cụ '{ten}' lỗi: {type(e).__name__}"}
