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

from engine.metrics import gini
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
        "name": "xem_thi_truong_local",
        "description": "Xem rao vặt và báo giá đang nhìn thấy ở làng/bờ bạn tới được, cùng niềm tin giá riêng của bạn. Không có giá nào được coi là giá đúng.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_bao_gia",
        "description": "Xem các báo giá song phương còn mở mà bạn có quyền nhìn và có thể chấp nhận.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_du_an",
        "description": "Xem tiến độ các dự án đang mở tại địa điểm bạn tới được: đầu ra, vật liệu/công còn thiếu và hạn.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_co_hoi_san_xuat",
        "description": "Xem fact card của hoạt động đang khả thi/gần khả thi: công, đầu vào, đầu ra vật lý và giới hạn tài nguyên; không xếp hạng lựa chọn.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "xem_tai_nguyen_gan_day",
        "description": "Xem tối đa một số nguồn tự nhiên và thửa đất có thể tiếp cận quanh nơi ở hiện tại.",
        "parameters": {
            "type": "object",
            "properties": {"toi_da": {"type": "integer", "description": "số mục tối đa trả về"}},
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
    {
        "name": "get_phan_bo_cua_cai",
        "description": "Phổ tài sản của cả làng để cân nhắc TRƯỚC KHI đánh thuế / trợ cấp "
                       "(Agentic RAG lập pháp): phân vị 10/50/90 của kho thóc dân làng, hệ số "
                       "Gini bất bình đẳng (0=đều, 1=lệch cực đoan), và số hộ thiếu ăn "
                       "(kho thóc dưới nhu cầu một tick). Chỉ tham khảo, không thay đổi gì.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _xem_thoi_tiet(w: World, aid: str, args: dict) -> dict:
    loai, he_so = w.thoi_tiet(w.tick)
    return {"mua": w.mua(), "thoi_tiet": loai, "he_so_nang_suat": he_so}


def _gia_cho(w: World, aid: str, args: dict) -> dict:
    ts = str(args.get("tai_san", ""))
    return {"tai_san": ts, "gia_gan_nhat": w.gia_gan_nhat(ts)}


def _xem_bao_gia(w: World, aid: str, args: dict) -> dict:
    from engine.quotes import quote_visible_to

    return {
        "bao_gia": [
            {
                "id": quote.id,
                "chieu": quote.chieu,
                "tai_san": quote.tai_san,
                "con_lai": round(quote.con_lai, 6),
                "don_gia": round(quote.don_gia, 6),
                "thanh_toan": quote.thanh_toan,
                "giao_tai": quote.giao_tai,
                "het_han_tick": quote.het_han_tick,
            }
            for quote in quote_visible_to(w, aid)
        ],
        "pham_vi": "chỉ báo giá đang mở và có thể tiếp cận",
    }


def _xem_thi_truong_local(w: World, aid: str, args: dict) -> dict:
    """Expose observed local offers, never a global planner's price vector."""
    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người hỏi không còn hoạt động", "code": "agent_unavailable"}
    ads = []
    for seller, direction, asset, amount, price in getattr(w, "rao_vat", []):
        other = w.agents.get(seller)
        if seller == aid or (other is not None and other.lang != agent.lang):
            continue
        ads.append({
            "ai": seller,
            "chieu": direction,
            "tai_san": asset,
            "so_luong": round(float(amount), 6),
            "gia_rao": round(float(price), 6),
        })
    return {
        "rao_vat_cung_lang": ads,
        "bao_gia_co_the_xem": _xem_bao_gia(w, aid, args)["bao_gia"],
        "gia_ky_vong_rieng": {
            asset: round(float(price), 6)
            for asset, price in sorted(agent.gia_ky_vong.items())
        },
        "canh_bao": "rao/niềm tin không phải giao dịch đã settlement",
    }


def _xem_du_an(w: World, aid: str, args: dict) -> dict:
    from engine.projects import visible_to

    projects = []
    for project in visible_to(w, aid):
        materials_left = {
            asset: round(max(0.0, need - project.vat_lieu_da.get(asset, 0.0)), 6)
            for asset, need in sorted(project.vat_lieu_can.items())
        }
        projects.append({
            "id": project.id,
            "chu": project.chu,
            "loai": project.loai,
            "thua": project.thua,
            "tai_san_ra": project.tai_san_ra,
            "so_luong_ra": round(project.so_luong_ra, 6),
            "cong_can": round(project.cong_can, 6),
            "cong_da": round(project.cong_da, 6),
            "cong_con_lai": round(max(0.0, project.cong_can - project.cong_da), 6),
            "vat_lieu_con_lai": materials_left,
            "han_tick": project.han_tick,
        })
    return {"du_an": projects, "pham_vi": "dự án của bạn hoặc công trường cùng làng/bờ tới được"}


def _reachable_parcels(w: World, aid: str):
    from engine.spatial import co_the_o_bo

    r0, c0 = w.vi_tri_cua(aid)
    return sorted(
        (parcel for parcel in w.parcels.values() if co_the_o_bo(w, aid, parcel.bo)),
        key=lambda parcel: (abs(parcel.r - r0) + abs(parcel.c - c0), parcel.id),
    )


def _xem_tai_nguyen_gan_day(w: World, aid: str, args: dict) -> dict:
    limit = max(0, min(20, int(args.get("toi_da", 8) or 8)))
    rows = []
    for parcel in _reachable_parcels(w, aid):
        if parcel.loai not in {"rung", "doi", "mo_dong", "ruong", "song"}:
            continue
        row: dict[str, Any] = {"thua": parcel.id, "loai": parcel.loai}
        if parcel.loai == "ruong":
            row.update({"chu": parcel.chu, "mau_mo": round(parcel.mau_mo, 4)})
        if parcel.loai == "rung":
            row.update({
                "sinh_khoi": round(float(getattr(parcel, "sinh_khoi", 0.0)), 6),
                "tan_rung": round(float(getattr(parcel, "tan_rung", 0.0)), 6),
            })
        rows.append(row)
        if len(rows) >= limit:
            break
    return {"tai_nguyen": rows, "pham_vi": "chỉ ô có thể tiếp cận ở tick hiện tại"}


def _xem_co_hoi_san_xuat(w: World, aid: str, args: dict) -> dict:
    """Physical fact cards.  They disclose constraints without choosing a livelihood."""
    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người hỏi không còn hoạt động", "code": "agent_unavailable"}
    cfg = w.cfg.raw()
    labour = round(w.ledger.so_du(aid, "cong"), 6)
    cards: list[dict[str, Any]] = []
    reachable = _reachable_parcels(w, aid)
    owned_fields = [p for p in reachable if p.loai == "ruong" and p.chu == aid]
    if w.mua_mua():
        sx = cfg["san_xuat"]
        cards.append({
            "hoat_dong": "canh_lua",
            "thua_co_the_dung": [p.id for p in owned_fields[:6]],
            "cong_moi_thua": float(sx["cong_moi_thua"]),
            "giong_thoc_moi_thua": float(sx["giong_kg_moi_thua"]),
            "san_luong_co_so_kg_moi_thua": float(sx["san_luong_goc_kg"]),
            "cong_hien_co": labour,
        })
    else:
        crops = w.cfg.get("khong_gian.vu_dong.cay", {})
        if isinstance(crops, dict):
            for crop, spec in sorted(crops.items()):
                if isinstance(spec, dict):
                    cards.append({
                        "hoat_dong": f"canh_{crop}",
                        "thua_co_the_dung": [p.id for p in owned_fields[:6]],
                        "cong_moi_thua": float(spec.get("cong", 0.0)),
                        "san_luong_co_so_kg_moi_thua": float(spec.get("san_luong_kg", 0.0)),
                        "quy_doi_luong_thuc": float(spec.get("quy_doi_dinh_duong", 0.0)),
                        "cong_hien_co": labour,
                    })
    forests = [p for p in reachable if p.loai == "rung"]
    if forests:
        cards.append({
            "hoat_dong": "khai_go",
            "cong_moi_go": float(cfg["san_xuat"]["khai_thac"]["cong_moi_go"]),
            "sinh_khoi_tiep_can": round(sum(float(getattr(p, "sinh_khoi", 0.0)) for p in forests), 6),
            "cong_hien_co": labour,
        })
    if any(p.loai == "song" for p in reachable):
        cards.append({
            "hoat_dong": "danh_ca",
            "cong_moi_kg": float(cfg["danh_ca"]["cong_moi_kg_ca"]),
            "ton_ca_chung": round(float(getattr(w, "ca_ton", 0.0)), 6),
            "cong_hien_co": labour,
        })
    return {"co_hoi": cards, "pham_vi": "thông số vật lý/nguồn lực, không phải khuyến nghị"}


def _tai_san_cua_toi(w: World, aid: str, args: dict) -> dict:
    ts = {k: round(v, 1) for k, v in w.ledger.tai_san_cua(aid).items()
          if not k.startswith("vi_the:") and abs(v) > 1e-9}
    so_thua = sum(1 for p in w.parcels.values() if p.chu == aid)
    return {"tai_san": ts, "so_thua_ruong": so_thua}


def _dat_cong_gan(w: World, aid: str, args: dict) -> dict:
    from engine.spatial import co_the_o_bo

    toi_da = int(args.get("toi_da", 5) or 5)
    a = w.agents.get(aid)
    lang = w.villages[a.lang if a and a.lang < len(w.villages) else 0]
    cong = sorted(
        (p for p in w.parcels.values()
         if p.loai == "ruong" and p.chu is None and co_the_o_bo(w, aid, p.bo)),
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
    if nguoi != aid and nguoi not in w.hang_xom_cua(aid):
        return {"loi": "người này không ở trong phạm vi hàng xóm quan sát", "code": "outside_local"}
    g = w.rng.get(f"nghe_ve:{aid}:{nguoi}", w.nam())  # ổn định trong năm
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


def _phan_vi(x_sap_xep: list[float], q: float) -> float:
    """Phân vị nearest-rank TẤT ĐỊNH trên danh sách ĐÃ sắp xếp tăng dần (không cần numpy).

    q là tỷ lệ trong [0,1]. Không nội suy → độc lập nền tảng, replay ổn định.
    """
    import math
    n = len(x_sap_xep)
    if n == 0:
        return 0.0
    k = min(n, max(1, math.ceil(q * n)))
    return x_sap_xep[k - 1]


def _get_phan_bo_cua_cai(w: World, aid: str, args: dict) -> dict:
    """Phổ tài sản làng cho Trưởng làng RAG trước khi lập pháp (REPORTS.md §4.3).

    THUẦN ĐỌC (điều luật #1): chỉ đọc ledger/agents, không chuyển/sinh/hủy gì.
    Gini dùng CHUNG công thức với engine.metrics để nhất quán với ngưỡng bạo động.
    """
    asker = w.agents.get(aid)
    if asker is None or not asker.con_song:
        return {"loi": "người gọi không còn hoạt động", "code": "agent_unavailable"}
    # Aggregate village facts are observable in a small settlement; individual
    # inventory remains private. This deliberately excludes other villages.
    lang_hoi = asker.lang
    tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
    nc = w.cfg.raw()["nhu_cau"]
    nguoi_lon_kg = float(nc["nguoi_lon_kg_tick"])
    tre_em_kg = float(nc["tre_em_kg_tick"])
    song = [a for a in w.agents.values() if a.con_song and a.lang == lang_hoi]
    thoc = sorted(w.ledger.so_du(a.id, "thoc") for a in song)
    # hộ nghèo: kho thóc cả hộ dưới nhu cầu ăn MỘT tick của hộ (dedup theo hộ)
    da_xu_ly: set[str] = set()
    so_ho = 0
    so_ho_ngheo = 0
    for aid2 in sorted(w.agents):
        a = w.agents[aid2]
        if not a.con_song or a.lang != lang_hoi or aid2 in da_xu_ly:
            continue
        ho = [m for m in w.ho_cua(aid2) if w.agents[m].con_song]
        da_xu_ly.update(ho)
        if not ho:
            continue
        so_ho += 1
        ton = sum(w.ledger.so_du(m, "thoc") for m in ho)
        nhu = sum(nguoi_lon_kg if w.agents[m].truong_thanh(tt) else tre_em_kg for m in ho)
        if ton < nhu:
            so_ho_ngheo += 1
    return {
        "so_dan": len(song),
        "so_ho": so_ho,
        "thoc_p10": round(_phan_vi(thoc, 0.1), 1),
        "thoc_p50": round(_phan_vi(thoc, 0.5), 1),
        "thoc_p90": round(_phan_vi(thoc, 0.9), 1),
        "gini_thoc": round(gini(thoc), 4),
        "so_ho_ngheo": so_ho_ngheo,
    }


CONG_CU: dict[str, Callable[[World, str, dict], dict]] = {
    "xem_thoi_tiet": _xem_thoi_tiet,
    "gia_cho": _gia_cho,
    "xem_thi_truong_local": _xem_thi_truong_local,
    "xem_bao_gia": _xem_bao_gia,
    "xem_du_an": _xem_du_an,
    "xem_co_hoi_san_xuat": _xem_co_hoi_san_xuat,
    "xem_tai_nguyen_gan_day": _xem_tai_nguyen_gan_day,
    "tai_san_cua_toi": _tai_san_cua_toi,
    "dat_cong_gan": _dat_cong_gan,
    "uy_tin_voi": _uy_tin_voi,
    "nghe_ve": _nghe_ve,
    "get_phan_bo_cua_cai": _get_phan_bo_cua_cai,
}


def thuc_thi(w: World, aid: str, ten: str, args: dict | None) -> dict:
    """Thực thi một công cụ CHỈ ĐỌC. Tên lạ → trả lỗi (không raise, không chạm state)."""
    agent = w.agents.get(aid)
    if agent is None or not agent.con_song:
        return {"loi": "người gọi không còn hoạt động", "code": "agent_unavailable"}
    ham = CONG_CU.get(ten)
    if ham is None:
        return {"loi": f"không có công cụ tên '{ten}'", "code": "unknown_tool"}
    try:
        return ham(w, aid, args or {})
    except Exception as e:  # noqa: BLE001 — công cụ hỏng thì báo lỗi, KHÔNG làm chết vòng
        return {"loi": f"công cụ '{ten}' lỗi: {type(e).__name__}", "code": "tool_error"}
