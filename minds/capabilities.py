"""Capability registry — khai báo MỘT LẦN mỗi hành động agent gọi được (ADR 0006 §A).

Đây là NGUỒN SỰ THẬT DUY NHẤT cho một action: field `KeHoach` bị ghi, tham số JSON hợp lệ,
dịch hai chiều (`to_kehoach` / `from_kehoach`), bước engine tiêu thụ field, cổng scenario
(`kha_dung`), dòng menu render từ `World.cfg` (`mau_prompt`) và tập mã kết quả.

Hướng import (KHÔNG vòng): module này chỉ import `engine.*` + stdlib.
`minds/schemas.py`, `minds/translate.py`, `minds/prompts.py` import TỪ đây.

Bất biến được test cưỡng chế (ADR 0006 §A.3):

- **CAP-1 (bốn chân đủ):** mọi descriptor `cong_khai=True` có đồng thời tên trong
  `LOAI_HANH_DONG`, `to_kehoach` + chiều ngược (`from_kehoach` hoặc `nguoi_phat_nguoc`),
  `mau_prompt` render được, `engine_handler` import được bằng tên.
- **CAP-2 (không field mồ côi):** mọi field của `engine.intents.KeHoach` hoặc được một
  descriptor khai báo qua `kehoach_field`, hoặc nằm trong `FIELD_KHONG_PHAI_ACTION` kèm lý do.
- **CAP-3 (không quảng cáo hàng không có):** menu chỉ chứa action `kha_dung(w) == True`, và
  mọi action `kha_dung(w) == True` đều có mặt trong menu.
- **CAP-4 (anti-teleology):** text descriptor thuần dữ kiện — khả thi, chi phí, điều kiện, mã
  kết quả. KHÔNG xếp hạng sinh kế, không tên định chế, không từ mớm ý.
- **CAP-5 (không quảng cáo mà giấu kinh tế học):** mọi thứ menu chào — action VÀ từng *món*
  bên trong một action (`xay.mon`) — phải được công bố CHI PHÍ ĐẦU VÀO và SẢN PHẨM ĐẦU RA,
  đọc từ config đang chạy. Món mà công thức chỉ có trong state (hàng mới từ blueprint) phải
  nêu rõ nó phụ thuộc blueprint VÀ chỉ ra nơi agent đọc được công thức đó (khối "BÍ QUYẾT
  BẠN NẮM" trong `minds/prompts.build_user_rieng`). Đây là bất biến chống confound đo lường:
  một cơ chế bị giấu kinh tế học thì tần suất nó không-được-dùng nói về INTERFACE, không nói
  về hành vi agent. (Vụ `duc_xu`: menu chào `mon:"xu"` suốt nhiều run trong khi prompt chưa
  bao giờ nói đúc xu tốn gì / ra bao nhiêu — mọi kết luận "agent không đúc tiền" từ những
  run đó đều interface-confounded.) Nêu chi phí + sản phẩm là DỮ KIỆN; CẤM kèm bất kỳ lời
  bình, xếp hạng, gợi ý dùng hay tên định chế nào (CAP-4 vẫn trùm lên CAP-5).

`catalog_hash()` băm NỘI DUNG KHAI BÁO (không băm file): đổi thứ tự khai báo hay sửa docstring
KHÔNG đổi hash; thêm/bớt action, đổi tham số, đổi câu render, đổi cổng scenario thì ĐỔI hash.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from string import Template
from typing import Any

from engine.contracts import HopDong
from engine.forest import _trong_rung_bat
from engine.intents import KeHoach
from engine.market import Lenh
from engine.projects import _du_an_bat
from engine.quotes import _bao_gia_bat
from engine.settlement import _dat_o_bat
from engine.spatial import (
    _cham_tre_bat,
    _ga_rung_bat,
    _hai_bo_bat,
    _khong_gian_bat,
    _vu_dong_bat,
)

# --------------------------------------------------------------------------- #
#  Field KeHoach KHÔNG phải action (allowlist tường minh — CAP-2)               #
# --------------------------------------------------------------------------- #
# Mỗi mục PHẢI có lý do. Thêm field mới vào KeHoach mà không khai báo ở CATALOG và cũng
# không nằm ở đây ⇒ test CAP-2 FAIL (đó chính là cái đã bắt được dong_thuyen/rao_do/qua_song).
FIELD_KHONG_PHAI_ACTION: dict[str, str] = {
    "id": "định danh chủ thể của kế hoạch, không phải hành động",
    "y_dinh_sinh_con": (
        "do THẺ CHÍNH SÁCH điều khiển (the_chinh_sach.y_dinh_sinh_con), engine đọc qua "
        "policy card ở minds/policy_cards.py + minds/orchestrator.py — không có action rời"
    ),
}


# --------------------------------------------------------------------------- #
#  Tiện ích render số từ config (KHÔNG hằng số vật lý trong code — ADR 0006 §B) #
# --------------------------------------------------------------------------- #
def so(x: Any) -> str:
    """Số đọc được cho người: 600.0 → '600', 4.5 → '4.5', 0.0336 → '0.0336'."""
    return f"{float(x):g}"


def phan_tram(x: Any) -> str:
    """Tỷ lệ → phần trăm: 0.03 → '3%', 0.0201 → '2.01%'."""
    return f"{float(x) * 100:g}%"


def _cfg(w: Any) -> Any:
    return getattr(w, "cfg", w)


def _recipe(w: Any, mon: str) -> dict[str, Any]:
    r = _cfg(w).get(f"san_xuat.recipe.{mon}", {})
    return dict(r) if isinstance(r, dict) else {}


def _chinh_tri_bat(w: Any) -> bool:
    """Cổng tầng chính trị (giống engine.politics._chinh_tri_bat; mặc định BẬT)."""
    return bool(_cfg(w).get("chinh_tri.bat", True))


def _khai_hoang_bat(w: Any) -> bool:
    return _khong_gian_bat(w) and bool(_cfg(w).get("khong_gian.khai_hoang.bat", False))


def _tach_ho_bat(w: Any) -> bool:
    return bool(_cfg(w).get("ho.cu_tru_ben_vung", False)) and bool(
        _cfg(w).get("ho.tach_ho.bat", False)
    )


def _di_san_bat(w: Any) -> bool:
    return bool(_cfg(w).get("ho.di_san.bat", False))


def _co_thuyen(w: Any) -> bool:
    """Thế giới này ĐÓNG được thuyền? (recipe khai báo trong config)."""
    return bool(_recipe(w, "thuyen"))


def lich_mua(w: Any) -> tuple[str, ...]:
    """Vòng mùa THẬT của một năm, hỏi thẳng World (nguồn duy nhất: `World.mua`).

    Base (không khai báo `thoi_gian.lich_mua`) → ('lua', 'kho'); overlay spatial_v1 →
    ('lua_1', 'lua_2', 'dong'). Không hardcode "tick lẻ/chẵn" ở bất kỳ đâu.
    """
    n = int(w.tick_moi_nam())
    return tuple(str(w.mua(t)) for t in range(1, n + 1))


def mua_gieo_cay(w: Any) -> tuple[str, ...]:
    """Các mùa gieo+gặt lúa (World.mua_mua là trọng tài)."""
    n = int(w.tick_moi_nam())
    return tuple(str(w.mua(t)) for t in range(1, n + 1) if w.mua_mua(t))


def mua_kho(w: Any) -> tuple[str, ...]:
    n = int(w.tick_moi_nam())
    return tuple(str(w.mua(t)) for t in range(1, n + 1) if not w.mua_mua(t))


def cay_vu_dong(w: Any) -> dict[str, dict[str, Any]]:
    """Cây vụ khô mà scenario này cho phép (rỗng khi cổng tắt)."""
    if not _vu_dong_bat(w):
        return {}
    cay = _cfg(w).get("khong_gian.vu_dong.cay", {})
    return {str(k): dict(v) for k, v in sorted(dict(cay).items()) if isinstance(v, dict)}


def linh_vuc_nghien_cuu(w: Any) -> tuple[str, ...]:
    """Lĩnh vực R&D mở — đọc `config/research.yaml`, không phải cây công nghệ định sẵn."""
    lv = _cfg(w).raw().get("research", {}).get("linh_vuc", {})
    return tuple(sorted(str(k) for k in dict(lv)))


def dinh_muc_bat_ga(w: Any) -> float:
    """Công/con mà ENGINE cưỡng chế khi bắt gà rừng, DƯỚI SCENARIO ĐANG CHẠY (F-CAP5-1).

    GƯƠNG của nhánh rẽ trong `engine.chan_nuoi.bat_ga`:

    - pool gà rừng BẬT (`_ga_rung_bat`) ⇒ định mức là `khong_gian.ga_rung.cong_moi_con`
      (ở mật độ đầy; CPUE giảm theo mật độ tồn/sức_chứa);
    - pool TẮT (legacy) ⇒ định mức là `chan_nuoi.bat_ga_cong_moi_con` (chia nguyên).

    Render CỨNG khóa legacy như trước là số ĐÚNG do MAY MẮN (hôm nay cả hai đều 30): một
    ablation trên `khong_gian.ga_rung.cong_moi_con` sẽ khiến prompt nói một con số mà engine
    không hề dùng — prompt NÓI DỐI agent (CAP-5). Hai khóa là hai luật, không phải hai tên
    của một luật.
    """
    if _ga_rung_bat(w):
        return float(_cfg(w).get("khong_gian.ga_rung.cong_moi_con"))
    return float(_cfg(w).raw()["chan_nuoi"]["bat_ga_cong_moi_con"])


def he_so_E_nghien_cuu(w: Any) -> str:
    """'E1 ×1, E2 ×1.5, …' — hệ số bậc chữ nhân vào điểm nghiên cứu (engine.research:36)."""
    hs = _cfg(w).raw().get("research", {}).get("diem_nghien_cuu", {}).get("he_so_E", {})
    return ", ".join(f"{k} ×{so(v)}" for k, v in sorted(dict(hs).items()))


# Tài sản KHÔNG rao ở chợ hàng hóa — kèm lý do (không phải hàng tồn của một người).
TAI_SAN_KHONG_RAO: dict[str, str] = {
    "cong": "ngày công là dòng chảy trong tick (bốc hơi cuối tick), không phải hàng tồn kho",
    "thuy_loi": "công trình của công quỹ (fiscal), không nằm trong tay một người",
    "dat": "đất đi qua niem_yet + tra_gia_dat (đấu giá kín), không qua lệnh mua/bán",
}


def tai_san_giao_dich(w: Any) -> tuple[str, ...]:
    """Tài sản đặt lệnh mua/bán được TRONG THẾ GIỚI NÀY — sinh từ sổ + config, không hardcode.

    Gồm: (a) tài sản đang có mặt trong sổ cái, (b) tài sản mà thế giới này SINH RA ĐƯỢC qua
    một cơ chế đã khai báo trong config (gặt, khai thác, recipe, chăn nuôi, đánh cá, vụ đông,
    máy), (c) hàng mới do sáng chế đẻ ra (`w.ten_hang`). Trừ `TAI_SAN_KHONG_RAO`, vị thế hợp
    đồng `vi_the:*` và cổ phần (cổ phần vào menu dưới dạng văn phạm `co_phan:<mã pháp nhân>`).
    """
    cfg = _cfg(w)
    ra: set[str] = set()
    for ts in w.ledger.cac_tai_san():
        if ts.startswith(("vi_the:", "co_phan:")):
            continue
        ra.add(str(ts))
    sx = cfg.raw().get("san_xuat", {})
    ra.add("thoc")  # gat — mọi thế giới đều gặt
    kt = sx.get("khai_thac", {}) or {}
    if "cong_moi_go" in kt:
        ra.add("go")
    if "cong_moi_quang" in kt:
        ra.add("quang_dong")
    for mon in (sx.get("recipe", {}) or {}):
        ra.add(str(mon))  # khóa recipe CHÍNH LÀ mã hàng ra (cong_cu/nha/xu/thuyen)
    if cfg.raw().get("research", {}).get("may", {}).get("recipe"):
        ra.add("may")
    if cfg.raw().get("chan_nuoi"):
        ra.update(("ga", "ga_con", "thit"))
    if cfg.raw().get("danh_ca"):
        ra.add("ca")
    ra.update(cay_vu_dong(w))
    ra.update(str(k) for k in getattr(w, "ten_hang", {}))
    ra -= set(TAI_SAN_KHONG_RAO)
    return tuple(sorted(ra))


# --------------------------------------------------------------------------- #
#  CAP-5 — món của action `xay`: danh sách quảng cáo VÀ kinh tế học cùng một nguồn #
# --------------------------------------------------------------------------- #
# Món `xay` mà ENGINE thi hành được → (field KeHoach nhận nó, đường dẫn config chứa recipe).
# Đây là GƯƠNG của `_tk_xay` + `engine.production.thi_hanh_san_xuat`. Danh sách món hiện trong
# menu VÀ chi phí/sản phẩm của từng món đều rút từ bảng này ⇒ không thể lệch nhau (CAP-5).
MON_XAY: dict[str, tuple[str, str]] = {
    "cong_cu": ("che_tao_cong_cu", "san_xuat.recipe.cong_cu"),
    "nha": ("xay_nha", "san_xuat.recipe.nha"),
    "xu": ("duc_xu", "san_xuat.recipe.xu"),
    "may": ("xay_may", "research.may.recipe"),
}

# Bí danh LLM được phép gửi ở `mon` → món thật (giữ đúng `_tk_xay`).
BI_DANH_MON_XAY: dict[str, str] = {"che_tac": "cong_cu"}

# Món CÓ recipe trong config nhưng KHÔNG chế qua `xay` — kèm lý do + action thay thế.
# Món recipe nào không nằm ở MON_XAY lẫn đây ⇒ config hứa một công thức không ai gọi được.
MON_NGOAI_XAY: dict[str, str] = {
    "thuyen": "đóng thuyền đi qua action riêng `dong_thuyen` (engine.spatial), không qua `xay`",
}

# Khóa recipe KHÔNG phải nguyên liệu đầu vào — kèm lý do. Mọi khóa KHÁC bị coi là nguyên liệu
# và ĐƯỢC NÊU trong menu ⇒ thêm nguyên liệu mới vào config thì prompt tự nói, không phải sửa
# code (đó là điều kiện để CAP-5 không mục ra theo thời gian).
KHOA_RECIPE_KHONG_PHAI_NGUYEN_LIEU: dict[str, str] = {
    "ra": "số sản phẩm mỗi lần chế (mặc định 1) — đầu RA, không phải đầu vào",
    "tang_nang_suat": "thuộc tính của sản phẩm khi đem dùng, không phải chi phí chế",
    "hao_mon_moi_tick_dung": "thuộc tính hao mòn của sản phẩm, không phải chi phí chế",
}

# Nhãn tiếng Việt cho mã nguyên liệu — chỉ ĐẶT TÊN, không xếp hạng. Mã lạ → in nguyên mã.
NHAN_NGUYEN_LIEU: dict[str, str] = {
    "cong": "công",
    "go": "gỗ",
    "quang_dong": "quặng đồng",
    "thoc": "thóc",
    "quang_hoac_xu": "quặng đồng (hoặc xu)",  # engine.production: có quặng thì dùng quặng
}

# Điều kiện NGOÀI nguyên liệu (nằm ở state, không ở config) — nêu để agent khỏi đoán mò.
DIEU_KIEN_MON_XAY: dict[str, str] = {
    "may": "cần blueprint cong_cu_may_moc — tự nghiên cứu ra hoặc được cấp quyen_su_dung",
}


def cong_thuc_xay(w: Any) -> dict[str, dict[str, Any]]:
    """Món `xay` chế được TRONG THẾ GIỚI NÀY → recipe của nó (đọc config, sort theo tên).

    NGUỒN DUY NHẤT cho cả (a) danh sách món quảng cáo ở `mon` và (b) chi phí/sản phẩm nêu
    trong cùng dòng menu. Recipe rỗng/thiếu ⇒ món KHÔNG được chào (CAP-3 + CAP-5).
    """
    ra: dict[str, dict[str, Any]] = {}
    for mon, (_field, duong_dan) in MON_XAY.items():
        r = _cfg(w).get(duong_dan, {})
        if isinstance(r, dict) and r:
            ra[mon] = dict(r)
    return dict(sorted(ra.items()))


def mon_recipe_khong_co_duong_che(w: Any) -> tuple[str, ...]:
    """Món có recipe trong `san_xuat.recipe` mà KHÔNG ở `MON_XAY` lẫn `MON_NGOAI_XAY`.

    Rỗng là bất biến: khác rỗng ⇒ config khai một công thức mà không action nào gọi được
    (hoặc engine đã mọc đường chế mới mà registry chưa biết). Hook cho test CAP-5.
    """
    r = _cfg(w).raw().get("san_xuat", {}).get("recipe", {}) or {}
    return tuple(sorted(m for m in r if m not in MON_XAY and m not in MON_NGOAI_XAY))


def mo_ta_cong_thuc(mon: str, r: dict[str, Any]) -> str:
    """'xu: 5 công + 1 quặng đồng → 10 xu' — THUẦN chi phí đầu vào và sản phẩm đầu ra.

    Không một tính từ, không một lời gợi ý, không tên định chế (CAP-4 trùm CAP-5).
    """
    vao = " + ".join(
        f"{so(v)} {NHAN_NGUYEN_LIEU.get(k, k)}"
        for k, v in sorted(r.items())
        if k not in KHOA_RECIPE_KHONG_PHAI_NGUYEN_LIEU
    )
    dong = f"{mon}: {vao or '(không tốn gì)'} → {so(r.get('ra', 1))} {mon}"
    dk = DIEU_KIEN_MON_XAY.get(mon)
    return f"{dong} [{dk}]" if dk else dong


# --------------------------------------------------------------------------- #
#  Descriptor                                                                   #
# --------------------------------------------------------------------------- #
ToKeHoach = Callable[[Any, KeHoach, dict[str, Any], list | None], None]
FromKeHoach = Callable[[KeHoach], list[dict[str, Any]]]


@dataclass(frozen=True)
class HanhDongCapability:
    """Khai báo bất biến của MỘT action (ADR 0006 §A.1)."""

    ten: str
    # field(s) trên engine.intents.KeHoach mà action này ghi vào (một action có thể ghi
    # nhiều field — vd phan_bo_cong; một field có thể do nhiều action ghi — vd dat_lenh)
    kehoach_field: tuple[str, ...]
    # tham số JSON LLM được phép gửi: (tên, kiểu)
    schema_fields: tuple[tuple[str, str], ...]
    to_kehoach: ToKeHoach
    from_kehoach: FromKeHoach
    # tên (dotted) bước engine tiêu thụ field — test import bằng tên, KHÔNG import ngược
    engine_handler: tuple[str, ...]
    kha_dung_fn: Callable[[Any], bool]
    kha_dung_key: str  # mô tả ổn định của cổng (vào catalog_hash)
    mau_prompt_template: str  # string.Template ($ten) — JSON braces an toàn
    mau_prompt_gia_tri: Callable[[Any], dict[str, Any]]
    ma_ket_qua: tuple[str, ...]
    thu_tu_phat: int  # thứ tự phát JSON (wire contract: đổi = đổi thứ tự lệnh chợ)
    cong_khai: bool = True
    # chiều ngược do descriptor khác phát (chung field, phải giữ thứ tự trong list)
    nguoi_phat_nguoc: str | None = None

    def kha_dung(self, w: Any) -> bool:
        return bool(self.kha_dung_fn(w))

    def mau_prompt(self, w: Any) -> str:
        return Template(self.mau_prompt_template).substitute(self.mau_prompt_gia_tri(w))

    def khai_bao(self) -> dict[str, Any]:
        """Nội dung khai báo được băm (KHÔNG gồm hàm, KHÔNG gồm docstring/thứ tự file)."""
        return {
            "ten": self.ten,
            "kehoach_field": list(self.kehoach_field),
            "schema_fields": [list(f) for f in self.schema_fields],
            "engine_handler": list(self.engine_handler),
            "kha_dung_key": self.kha_dung_key,
            "mau_prompt_template": self.mau_prompt_template,
            "ma_ket_qua": list(self.ma_ket_qua),
            "thu_tu_phat": self.thu_tu_phat,
            "cong_khai": self.cong_khai,
            "nguoi_phat_nguoc": self.nguoi_phat_nguoc,
        }


# --------------------------------------------------------------------------- #
#  to_kehoach / from_kehoach — hành vi GIỮ NGUYÊN y hệt bản elif cũ             #
# --------------------------------------------------------------------------- #
def _tk_phan_bo_cong(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # NGUYÊN TỬ: parse hết vào biến cục bộ trước, chỉ mutate kh khi mọi conversion thành
    # công (tránh áp nửa vời rồi lại bị dịch-intent áp lần hai)
    canh_thua = [str(x) for x in d.get("canh_thua", [])][:10]
    gop_cong_cho = str(d["gop_cong_cho"]) if d.get("gop_cong_cho") else None
    cong_khai_go = max(0.0, float(d.get("khai_go_cong", 0) or 0))
    cong_khai_quang = max(0.0, float(d.get("khai_quang_cong", 0) or 0))
    hoc = bool(d.get("hoc", False))
    day_cho = [str(x) for x in d.get("day_cho", [])]
    kh.canh_thua = canh_thua
    if gop_cong_cho is not None:
        kh.gop_cong_cho = gop_cong_cho
    kh.cong_khai_go = cong_khai_go
    kh.cong_khai_quang = cong_khai_quang
    kh.hoc = hoc
    kh.day_cho = day_cho


def _fk_phan_bo_cong(kh: KeHoach) -> list[dict]:
    pbc: dict[str, Any] = {}
    if kh.canh_thua:
        pbc["canh_thua"] = list(kh.canh_thua)
    if kh.gop_cong_cho:
        pbc["gop_cong_cho"] = kh.gop_cong_cho
    if kh.cong_khai_go:
        pbc["khai_go_cong"] = kh.cong_khai_go
    if kh.cong_khai_quang:
        pbc["khai_quang_cong"] = kh.cong_khai_quang
    if kh.hoc:
        pbc["hoc"] = True
    if kh.day_cho:
        pbc["day_cho"] = list(kh.day_cho)
    return [{"loai": "phan_bo_cong", **pbc}] if pbc else []


def _tk_xay(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    mon = d.get("mon", d.get("nha", "nha"))
    sl = int(d.get("so_luong", 1))
    if mon in ("che_tac", "cong_cu"):
        kh.che_tao_cong_cu += max(0, sl)
    elif mon == "nha":
        kh.xay_nha += max(0, sl)
    elif mon == "may":
        kh.xay_may += max(0, sl)
    elif mon == "xu":
        kh.duc_xu += max(0, sl)
    elif isinstance(mon, str) and mon in w.ten_hang:
        kh.che_hang[mon] = kh.che_hang.get(mon, 0) + max(0, sl)
    elif thung is not None:
        thung.append((kh.id, d, f"món lạ: {mon}"))
    else:
        w.ghi_unrecognized(kh.id, "xay", f"món lạ: {mon}")


def _fk_xay(kh: KeHoach) -> list[dict]:
    ra: list[dict] = []
    if kh.che_tao_cong_cu:
        ra.append({"loai": "xay", "mon": "che_tac", "so_luong": kh.che_tao_cong_cu})
    if kh.xay_nha:
        ra.append({"loai": "xay", "mon": "nha", "so_luong": kh.xay_nha})
    if kh.xay_may:
        ra.append({"loai": "xay", "mon": "may", "so_luong": kh.xay_may})
    if kh.duc_xu:
        ra.append({"loai": "xay", "mon": "xu", "so_luong": kh.duc_xu})
    for ma, sl in sorted(kh.che_hang.items()):
        ra.append({"loai": "xay", "mon": ma, "so_luong": sl})
    return ra


def _tk_nghien_cuu(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.nghien_cuu = (str(d["linh_vuc"]), float(d.get("cong", 0)), float(d.get("thoc", 0)))


def _fk_nghien_cuu(kh: KeHoach) -> list[dict]:
    if not kh.nghien_cuu:
        return []
    lv, cong, thoc = kh.nghien_cuu
    return [{"loai": "nghien_cuu", "linh_vuc": lv, "cong": cong, "thoc": thoc}]


def _tk_canh_vu_dong(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    thua = str(d.get("thua", ""))
    cay = str(d.get("cay", ""))
    if thua and cay and (thua, cay) not in kh.canh_vu_dong:
        kh.canh_vu_dong.append((thua, cay))


def _fk_canh_vu_dong(kh: KeHoach) -> list[dict]:
    return [{"loai": "canh_vu_dong", "thua": t, "cay": c} for t, c in kh.canh_vu_dong]


def _tk_cham_tre(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    tre = str(d.get("tre", ""))
    if tre and tre not in kh.cham_tre_cho:
        kh.cham_tre_cho.append(tre)


def _fk_cham_tre(kh: KeHoach) -> list[dict]:
    return [{"loai": "cham_tre", "tre": t} for t in kh.cham_tre_cho]


def _tk_lap_phap_nhan(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.lap_phap_nhan = {
        "ten": str(d.get("ten", "")),
        "co_phan": {str(k): float(v) for k, v in dict(d.get("co_phan", {})).items()},
        "von_gop": {
            str(k): {str(t): float(s) for t, s in dict(v).items()}
            for k, v in dict(d.get("von_gop", {})).items()
        },
    }


def _fk_lap_phap_nhan(kh: KeHoach) -> list[dict]:
    return [{"loai": "lap_phap_nhan", **kh.lap_phap_nhan}] if kh.lap_phap_nhan else []


def _chuan_hoa_hanh_dong_con(x: Any) -> dict[str, Any]:
    """Kiểm tra tối thiểu như schema HanhDong (loai: str + trường tự do).

    Không import `minds.schemas` (tránh vòng import); sai hình dạng ⇒ raise để rơi đúng
    nhánh "hành động con hỏng" như trước.
    """
    if not isinstance(x, dict) or not isinstance(x.get("loai"), str):
        raise ValueError("hành động con thiếu 'loai'")
    return dict(x)


def _tk_quyet_dinh_entity(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    eid = str(d["entity"])
    con = d.get("hanh_dong_con", [])
    kh_con = KeHoach(id=eid)
    for hd_con in con if isinstance(con, list) else []:
        try:
            ap_dung_hanh_dong(w, kh_con, _chuan_hoa_hanh_dong_con(hd_con), None)
        except Exception:  # noqa: BLE001 — hành động con hỏng thì bỏ riêng nó
            w.ghi_unrecognized(eid, "hanh_dong_con", "hành động con hỏng")
    kh.quyet_dinh_entity.append((eid, kh_con))


def _fk_quyet_dinh_entity(kh: KeHoach) -> list[dict]:
    ra: list[dict] = []
    for eid, kh_con in kh.quyet_dinh_entity:
        ra.append({"loai": "quyet_dinh_entity", "entity": eid,
                   "hanh_dong_con": hanh_dong_tu_ke_hoach(kh_con)})
    return ra


def _tk_viet_di_chuc(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.viet_di_chuc = {
        "phan_bo": {str(k): float(v) for k, v in dict(d.get("phan_bo", {})).items()},
        "gia_huan": str(d.get("gia_huan", ""))[:400],
    }


def _fk_viet_di_chuc(kh: KeHoach) -> list[dict]:
    return [{"loai": "viet_di_chuc", **kh.viet_di_chuc}] if kh.viet_di_chuc else []


def _tk_di_cu(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.di_cu = True


def _fk_di_cu(kh: KeHoach) -> list[dict]:
    return [{"loai": "di_cu"}] if kh.di_cu else []


# ---- residence/estate: mọi đường LLM đi cùng field KeHoach (ADR 0007, F-P1-2) ---- #
def _tk_tach_ho(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.tach_ho = True


def _fk_tach_ho(kh: KeHoach) -> list[dict]:
    return [{"loai": "tach_ho"}] if kh.tach_ho else []


def _tk_yeu_cau_di_san(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    ds_id = str(d.get("di_san", ""))
    if ds_id and ds_id not in kh.yeu_cau_di_san:
        kh.yeu_cau_di_san.append(ds_id)


def _fk_yeu_cau_di_san(kh: KeHoach) -> list[dict]:
    return [{"loai": "yeu_cau_di_san", "di_san": ds_id}
            for ds_id in sorted(kh.yeu_cau_di_san)]


def _gt_di_san(w: Any) -> dict[str, Any]:
    return {"han": so(_cfg(w).get("ho.di_san.claim_han_tick", 0))}


def _tk_chon_dat_o(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    """Keep a bounded, ordered list; the engine resolves simultaneous requests."""
    cfg_limit = max(1, int(w.cfg.get("khong_gian.dat_o.toi_da_uu_tien", 3)))
    fallback = d.get("du_phong", [])
    if not isinstance(fallback, list | tuple):
        fallback = []
    rows = [d.get("thua"), *fallback]
    seen: set[str] = set()
    ranked: list[str] = []
    for raw in rows:
        site = str(raw or "")
        if not site or site in seen:
            continue
        seen.add(site)
        ranked.append(site)
        if len(ranked) >= cfg_limit:
            break
    kh.chon_dat_o = ranked


def _fk_chon_dat_o(kh: KeHoach) -> list[dict]:
    if not kh.chon_dat_o:
        return []
    return [{"loai": "chon_dat_o", "thua": kh.chon_dat_o[0],
             "du_phong": list(kh.chon_dat_o[1:])}]


def _gt_chon_dat_o(w: Any) -> dict[str, Any]:
    return {"uu_tien": so(_cfg(w).get("khong_gian.dat_o.toi_da_uu_tien", 0))}


# ---- không gian: đóng thuyền / rao đò / qua sông (ADR 0005 §2.3) ---- #
def _tk_dong_thuyen(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.dong_thuyen += max(0, int(d.get("so_luong", 1) or 0))


def _fk_dong_thuyen(kh: KeHoach) -> list[dict]:
    n = int(getattr(kh, "dong_thuyen", 0) or 0)
    return [{"loai": "dong_thuyen", "so_luong": n}] if n > 0 else []


def _tk_rao_do(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # engine.spatial.buoc_qua_song đọc (phi, tai_san_tra) — giữ ĐÚNG shape
    phi = max(0.0, float(d["phi"]))
    tai_san = str(d.get("tai_san", "thoc"))
    kh.rao_do = (phi, tai_san)


def _fk_rao_do(kh: KeHoach) -> list[dict]:
    rd = getattr(kh, "rao_do", None)
    if not rd:
        return []
    return [{"loai": "rao_do", "phi": float(rd[0]), "tai_san": str(rd[1])}]


def _tk_qua_song(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # engine.spatial.buoc_qua_song đọc (den_bo, tai_san_tra, phi_chap_nhan)
    den_bo = str(d["den_bo"])
    if den_bo not in ("dan_cu", "hoang"):
        raise ValueError(f"bờ lạ: {den_bo}")
    tai_san = str(d.get("tai_san", "thoc"))
    phi = max(0.0, float(d.get("phi_chap_nhan", 0) or 0))
    kh.qua_song = (den_bo, tai_san, phi)


def _fk_qua_song(kh: KeHoach) -> list[dict]:
    qs = getattr(kh, "qua_song", None)
    if not qs:
        return []
    return [{"loai": "qua_song", "den_bo": str(qs[0]), "tai_san": str(qs[1]),
             "phi_chap_nhan": float(qs[2])}]


def _tk_khai_hoang(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    thua = str(d.get("thua", ""))
    if thua and thua not in kh.khai_hoang:
        kh.khai_hoang.append(thua)


def _fk_khai_hoang(kh: KeHoach) -> list[dict]:
    return [{"loai": "khai_hoang", "thua": t} for t in kh.khai_hoang]


def _tk_trong_rung(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    thua = str(d.get("thua", ""))
    if thua and thua not in kh.trong_rung:
        kh.trong_rung.append(thua)


def _fk_trong_rung(kh: KeHoach) -> list[dict]:
    return [{"loai": "trong_rung", "thua": t} for t in kh.trong_rung]


def _tk_chan_nuoi(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # NGUYÊN TỬ: parse cả hai trước rồi mới cộng dồn
    bat_ga_cong = max(0.0, float(d.get("bat_ga_cong", 0) or 0))
    giet_ga = max(0, int(d.get("giet_ga", 0) or 0))
    kh.bat_ga_cong += bat_ga_cong
    kh.giet_ga += giet_ga


def _fk_chan_nuoi(kh: KeHoach) -> list[dict]:
    if not (kh.bat_ga_cong or kh.giet_ga):
        return []
    return [{"loai": "chan_nuoi", "bat_ga_cong": kh.bat_ga_cong, "giet_ga": kh.giet_ga}]


def _tk_bieu(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.bieu.append((str(d["den"]), str(d.get("tai_san", "thoc")), float(d["so_luong"])))


def _fk_bieu(kh: KeHoach) -> list[dict]:
    return [{"loai": "bieu", "den": den, "tai_san": ts, "so_luong": sl}
            for den, ts, sl in kh.bieu]


def _tk_danh_ca(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.danh_ca_cong += max(0.0, float(d.get("cong", d.get("so_cong", 0)) or 0))


def _fk_danh_ca(kh: KeHoach) -> list[dict]:
    return [{"loai": "danh_ca", "cong": kh.danh_ca_cong}] if kh.danh_ca_cong else []


def _tk_mo_tiec(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.mo_tiec = (max(0.0, float(d.get("thoc", 0) or 0)),
                  max(0.0, float(d.get("thit", 0) or 0)))


def _fk_mo_tiec(kh: KeHoach) -> list[dict]:
    if not kh.mo_tiec:
        return []
    return [{"loai": "mo_tiec", "thoc": kh.mo_tiec[0], "thit": kh.mo_tiec[1]}]


def _tk_trom(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.trom = (str(d["muc_tieu"]), str(d.get("tai_san", "thoc")),
               max(0.0, float(d.get("so_luong", 50) or 0)))


def _fk_trom(kh: KeHoach) -> list[dict]:
    if not kh.trom:
        return []
    return [{"loai": "trom", "muc_tieu": kh.trom[0], "tai_san": kh.trom[1],
             "so_luong": kh.trom[2]}]


def _tk_nhan_tin(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    den = str(d.get("den", ""))
    noi = str(d.get("noi_dung", d.get("noi_dong", "")))[:300]
    if den and noi:
        kh.nhan_tin.append((den, noi))


def _fk_nhan_tin(kh: KeHoach) -> list[dict]:
    return [{"loai": "nhan_tin", "den": den, "noi_dung": noi} for den, noi in kh.nhan_tin]


def _tk_de_nghi_hop_dong(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    hop_dong = HopDong(**d["hop_dong"])
    den = d.get("den")
    kh.de_nghi_hop_dong.append((hop_dong, str(den) if den else None))


def _fk_de_nghi_hop_dong(kh: KeHoach) -> list[dict]:
    return [
        {"loai": "de_nghi_hop_dong", "den": den,
         "hop_dong": hd.model_dump(exclude={"id", "trang_thai", "tick_ky",
                                            "huy_bao_truoc_tu"})}
        for hd, den in kh.de_nghi_hop_dong
    ]


def _tk_tra_loi_hop_dong(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    ref = str(d["ref"])
    tl = d.get("tra_loi", "tu_choi")
    if tl == "mac_ca" and d.get("sua_doi"):
        kh.tra_loi_de_nghi[ref] = HopDong(**d["sua_doi"])
    elif tl in ("chap_nhan", "tu_choi"):
        kh.tra_loi_de_nghi[ref] = tl


def _fk_tra_loi_hop_dong(kh: KeHoach) -> list[dict]:
    ra: list[dict] = []
    for ref, tl in kh.tra_loi_de_nghi.items():
        muc: dict[str, Any] = {"loai": "tra_loi_hop_dong", "ref": ref}
        if tl == "chap_nhan" or tl == "tu_choi":
            muc["tra_loi"] = tl
        elif isinstance(tl, HopDong):
            muc["tra_loi"] = "mac_ca"
            muc["sua_doi"] = tl.model_dump(exclude={"id", "trang_thai", "tick_ky"})
        ra.append(muc)
    return ra


def _tk_don_phuong_pha_vo(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.don_phuong_pha_vo.append(str(d["ref"]))


def _fk_don_phuong_pha_vo(kh: KeHoach) -> list[dict]:
    return [{"loai": "don_phuong_pha_vo", "ref": r} for r in kh.don_phuong_pha_vo]


def _tk_bao_huy(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # báo trước để thoát hợp đồng vô hạn KHÔNG chịu phạt (khác don_phuong_pha_vo)
    ref = str(d["ref"])
    hien_co = getattr(kh, "bao_huy", None)
    if hien_co is None:
        kh.bao_huy = hien_co = []  # engine chưa có field → gắn động, tick đọc getattr
    if ref not in hien_co:
        hien_co.append(ref)


def _fk_bao_huy(kh: KeHoach) -> list[dict]:
    return [{"loai": "bao_huy", "ref": r} for r in (getattr(kh, "bao_huy", None) or [])]


def _tk_dat_lenh(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    chieu = d.get("chieu", d.get("mua_ban"))
    if chieu not in ("mua", "ban"):
        raise ValueError(f"chiều lạ: {chieu}")
    tai_san = str(d["tai_san"])
    thanh_toan = str(d.get("thanh_toan", "thoc"))
    if tai_san == thanh_toan:
        raise ValueError(f"lệnh {chieu} {tai_san} trả bằng chính {thanh_toan} "
                         f"là vô nghĩa — hãy thanh toán bằng tài sản khác")
    kh.dat_lenh.append(Lenh(kh.id, chieu, tai_san, float(d["sl"]),
                            float(d["gia"]), thanh_toan))


def _fk_dat_lenh(kh: KeHoach) -> list[dict]:
    """Phát CẢ dat_lenh lẫn buon_chuyen theo ĐÚNG thứ tự trong `kh.dat_lenh`.

    Hai action chia sẻ một field; thứ tự lệnh là wire contract (chợ khớp theo thứ tự
    danh sách khi giá bằng nhau) ⇒ không tách thành hai vòng lặp.
    """
    ra: list[dict] = []
    for le in kh.dat_lenh:
        if le.lang is not None:  # lệnh gửi chợ làng khác = buôn chuyến (giữ lang)
            ra.append({"loai": "buon_chuyen", "chieu": le.chieu, "tai_san": le.tai_san,
                       "sl": le.so_luong, "gia": le.gia, "thanh_toan": le.thanh_toan,
                       "lang": le.lang})
        else:
            ra.append({"loai": "dat_lenh", "chieu": le.chieu, "tai_san": le.tai_san,
                       "sl": le.so_luong, "gia": le.gia, "thanh_toan": le.thanh_toan})
    return ra


def _tk_dang_bao_gia(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # Engine is the final validator because stock and counterpart availability can change
    # between decision and execution. Translator only preserves a bounded declarative intent.
    kh.dang_bao_gia.append({
        "chieu": d.get("chieu"),
        "tai_san": d.get("tai_san"),
        "so_luong": d.get("so_luong", d.get("sl")),
        "don_gia": d.get("don_gia", d.get("gia")),
        "thanh_toan": d.get("thanh_toan", "thoc"),
        "doi_tac": d.get("doi_tac"),
        "het_han_tick": d.get("het_han_tick"),
        "giao_tai": d.get("giao_tai", "ngay"),
    })


def _fk_dang_bao_gia(kh: KeHoach) -> list[dict]:
    return [{"loai": "dang_bao_gia", **dict(q)} for q in kh.dang_bao_gia]


def _tk_chap_nhan_bao_gia(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.chap_nhan_bao_gia.append({
        "ref": d.get("ref", d.get("id")),
        "so_luong": d.get("so_luong", d.get("sl")),
    })


def _fk_chap_nhan_bao_gia(kh: KeHoach) -> list[dict]:
    return [{"loai": "chap_nhan_bao_gia", **dict(q)} for q in kh.chap_nhan_bao_gia]


def _tk_huy_bao_gia(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    ref = str(d.get("ref", d.get("id", "")))
    if ref and ref not in kh.huy_bao_gia:
        kh.huy_bao_gia.append(ref)


def _fk_huy_bao_gia(kh: KeHoach) -> list[dict]:
    return [{"loai": "huy_bao_gia", "ref": ref} for ref in kh.huy_bao_gia]


def _tk_tao_du_an(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    loai = str(d.get("loai_du_an", d.get("cong_trinh", d.get("mon", ""))))
    if loai:
        kh.tao_du_an.append({"loai_du_an": loai, "thua": d.get("thua")})


def _fk_tao_du_an(kh: KeHoach) -> list[dict]:
    return [{"loai": "tao_du_an", **dict(project)} for project in kh.tao_du_an]


def _tk_gop_vat_lieu_du_an(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.gop_vat_lieu_du_an.append({
        "ref": d.get("ref", d.get("id")),
        "tai_san": d.get("tai_san"),
        "so_luong": d.get("so_luong", d.get("sl")),
    })


def _fk_gop_vat_lieu_du_an(kh: KeHoach) -> list[dict]:
    return [{"loai": "gop_vat_lieu_du_an", **dict(item)}
            for item in kh.gop_vat_lieu_du_an]


def _tk_gop_cong_du_an(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.gop_cong_du_an.append({
        "ref": d.get("ref", d.get("id")),
        "so_cong": d.get("so_cong", d.get("cong")),
    })


def _fk_gop_cong_du_an(kh: KeHoach) -> list[dict]:
    return [{"loai": "gop_cong_du_an", **dict(item)} for item in kh.gop_cong_du_an]


def _tk_huy_du_an(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    ref = str(d.get("ref", d.get("id", "")))
    if ref and ref not in kh.huy_du_an:
        kh.huy_du_an.append(ref)


def _fk_huy_du_an(kh: KeHoach) -> list[dict]:
    return [{"loai": "huy_du_an", "ref": ref} for ref in kh.huy_du_an]


def _tk_buon_chuyen(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    chieu = d.get("chieu", "ban")
    if chieu in ("mua", "ban"):
        tai_san = str(d["tai_san"])
        thanh_toan = str(d.get("thanh_toan", "thoc"))
        if tai_san == thanh_toan:
            raise ValueError(f"buôn chuyến {chieu} {tai_san} trả bằng chính "
                             f"{thanh_toan} là vô nghĩa")
        # thiếu "lang" → mặc định chợ làng mình (không raise mất cả chuyến hàng)
        lang = d.get("lang")
        if lang is None:
            a = w.agents.get(kh.id)
            lang = a.lang if a is not None else 0
        kh.dat_lenh.append(Lenh(kh.id, chieu, tai_san, float(d["sl"]),
                                float(d["gia"]), thanh_toan, lang=int(lang)))


def _fk_uy_quyen(kh: KeHoach) -> list[dict]:
    """Chiều ngược do descriptor khác phát (xem `nguoi_phat_nguoc`)."""
    return []


def _tk_niem_yet(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    ts = str(d["tai_san"])
    if ts.startswith("thua:"):
        kh.niem_yet_dat.append((ts.split(":", 1)[1], float(d["gia"])))
    else:
        kh.dat_lenh.append(Lenh(kh.id, "ban", ts, float(d.get("sl", 1)), float(d["gia"])))


def _fk_niem_yet(kh: KeHoach) -> list[dict]:
    return [{"loai": "niem_yet", "tai_san": f"thua:{thua}", "gia": gia}
            for thua, gia in kh.niem_yet_dat]


def _tk_tra_gia_dat(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.tra_gia_dat.append((str(d["thua"]), float(d["gia"])))


def _fk_tra_gia_dat(kh: KeHoach) -> list[dict]:
    return [{"loai": "tra_gia_dat", "thua": t, "gia": g} for t, g in kh.tra_gia_dat]


def _tk_yeu_cau_hoan_tra(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.yeu_cau_rut[str(d["ref"])] = float(d["so_luong"])


def _fk_yeu_cau_hoan_tra(kh: KeHoach) -> list[dict]:
    return [{"loai": "yeu_cau_hoan_tra", "ref": ref, "so_luong": sl}
            for ref, sl in kh.yeu_cau_rut.items()]


def _tk_cau_hon(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.cau_hon = str(d["den"])


def _fk_cau_hon(kh: KeHoach) -> list[dict]:
    return [{"loai": "cau_hon", "den": kh.cau_hon}] if kh.cau_hon else []


def _tk_tra_loi_cau_hon(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.tra_loi_cau_hon[str(d["cua"])] = bool(d["dong_y"])


def _fk_tra_loi_cau_hon(kh: KeHoach) -> list[dict]:
    return [{"loai": "tra_loi_cau_hon", "cua": tu, "dong_y": dy}
            for tu, dy in kh.tra_loi_cau_hon.items()]


def _chuan_hoa_luat(luat: Any) -> dict[str, Any]:
    """Chuẩn hóa AN TOÀN một đạo luật do agent đề xuất (điều luật #3 — input LLM không tin
    được). Bắt buộc là dict; tham số số ép về float ≥0, còn lại ép về str. Không phải dict
    → raise để rơi thùng intent lạ."""
    if not isinstance(luat, dict):
        raise ValueError("luật phải là dict")
    ra: dict[str, Any] = {}
    for k, v in luat.items():
        if isinstance(v, bool):
            ra[str(k)] = v
        elif isinstance(v, int | float):
            ra[str(k)] = max(0.0, float(v))
        else:
            ra[str(k)] = str(v)
    return ra


def _tk_ung_cu(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.ung_cu = True


def _fk_ung_cu(kh: KeHoach) -> list[dict]:
    return [{"loai": "ung_cu"}] if getattr(kh, "ung_cu", False) else []


def _tk_bo_phieu(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    cho = str(d["cho"])  # thiếu ứng viên → KeyError → rơi thùng (điều luật #3)
    if cho:
        kh.bo_phieu = cho


def _fk_bo_phieu(kh: KeHoach) -> list[dict]:
    return [{"loai": "bo_phieu", "cho": kh.bo_phieu}] if getattr(kh, "bo_phieu", None) else []


def _tk_ban_hanh_luat(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    # luat PHẢI là dict; tham số số bị ép về float ≥0 (không tin dữ liệu LLM)
    kh.ban_hanh_luat = _chuan_hoa_luat(d.get("luat"))


def _fk_ban_hanh_luat(kh: KeHoach) -> list[dict]:
    luat = getattr(kh, "ban_hanh_luat", None)
    return [{"loai": "ban_hanh_luat", "luat": luat}] if luat else []


def _tk_hoi_lo(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    den = str(d["den"])
    thoc = max(0.0, float(d.get("thoc", 0) or 0))
    if den:
        kh.hoi_lo = (den, thoc)


def _fk_hoi_lo(kh: KeHoach) -> list[dict]:
    hl = getattr(kh, "hoi_lo", None)
    if not hl:
        return []
    den, thoc = hl
    return [{"loai": "hoi_lo", "den": den, "thoc": thoc}]


def _tk_nghiep_doan(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.gia_nhap_nghiep_doan = bool(d.get("gia_nhap", True))


def _fk_nghiep_doan(kh: KeHoach) -> list[dict]:
    return ([{"loai": "nghiep_doan", "gia_nhap": True}]
            if getattr(kh, "gia_nhap_nghiep_doan", False) else [])


def _tk_dinh_cong(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.dinh_cong = True


def _fk_dinh_cong(kh: KeHoach) -> list[dict]:
    return [{"loai": "dinh_cong"}] if getattr(kh, "dinh_cong", False) else []


def _tk_bao_dong(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    kh.bao_dong = True


def _fk_bao_dong(kh: KeHoach) -> list[dict]:
    return [{"loai": "bao_dong"}] if getattr(kh, "bao_dong", False) else []


def _tk_keu_goi(w: Any, kh: KeHoach, d: dict, thung: list | None) -> None:
    noi = str(d.get("noi_dung", d.get("noi_dong", "")))[:300]
    if noi:
        kh.keu_goi = noi


def _fk_keu_goi(kh: KeHoach) -> list[dict]:
    kg = getattr(kh, "keu_goi", None)
    return [{"loai": "keu_goi", "noi_dung": kg}] if kg else []


# --------------------------------------------------------------------------- #
#  Giá trị render cho mau_prompt (đọc cfg — CẤM hằng số vật lý trong template)  #
# --------------------------------------------------------------------------- #
def _gt_rong(w: Any) -> dict[str, Any]:
    return {}


def _gt_phan_bo_cong(w: Any) -> dict[str, Any]:
    sx = _cfg(w).raw()["san_xuat"]
    kt = sx["khai_thac"]
    return {
        "cong_thua": so(sx["cong_moi_thua"]),
        "giong": so(sx["giong_kg_moi_thua"]),
        "thua_max": so(sx["thua_toi_da_tu_canh"]),
        "cong_go": so(kt["cong_moi_go"]),
        "cong_quang": so(kt["cong_moi_quang"]),
        "ruong_cong": (
            "; với ruộng công trùng yêu cầu, lottery seeded phân bổ theo mùa"
            if bool(_cfg(w).get("khong_gian.phan_bo_ruong_cong.bat", False)) else ""
        ),
    }


def _gt_xay(w: Any) -> dict[str, Any]:
    """CAP-5: món quảng cáo VÀ kinh tế học của nó cùng rút từ `cong_thuc_xay(w)`.

    Trước đây `mon` liệt kê cả `"xu"` nhưng dòng menu chỉ nói chi phí của `cong_cu` và
    `nha` ⇒ đúc xu — kênh DUY NHẤT sinh ra `xu` — bị chào mà giấu công thức. Giờ mỗi món
    chào ra đều kèm chi phí + sản phẩm đọc từ config đang chạy.
    """
    ct = cong_thuc_xay(w)
    mon = [f'"{m}"' for m in ct]
    mon += [f'"{b}"' for b in sorted(BI_DANH_MON_XAY)]
    mon.append('"<mã hàng mới>"')
    chi_tiet = [mo_ta_cong_thuc(m, r) for m, r in ct.items()]
    chi_tiet += [
        f"{b}: tên gọi khác của {goc} (cùng công thức)"
        for b, goc in sorted(BI_DANH_MON_XAY.items())
    ]
    chi_tiet.append(
        "<mã hàng mới>: hàng do một blueprint che_bien đẻ ra — công thức nằm trong CHÍNH "
        "blueprint đó, liệt kê ở khối BÍ QUYẾT BẠN NẮM trong phần riêng của bạn; không nắm "
        "blueprint nào thì không có mã hàng mới nào để chế"
    )
    return {"mon": "|".join(mon), "cong_thuc": "; ".join(chi_tiet)}


def _gt_thuyen(w: Any) -> dict[str, Any]:
    r = _recipe(w, "thuyen")
    return {"cong": so(r.get("cong", 0)), "go": so(r.get("go", 0))}


def _gt_do(w: Any) -> dict[str, Any]:
    cfg = _cfg(w)
    return {
        "cap": so(cfg.get("khong_gian.do.khach_toi_da_moi_tick", 0)),
        "hao_mon": so(cfg.get("khong_gian.do.hao_mon_moi_tick_dung", 0.0)),
    }


def _gt_khai_hoang(w: Any) -> dict[str, Any]:
    cfg = _cfg(w)
    return {
        "cong": so(cfg.get("khong_gian.khai_hoang.cong_moi_thua", 0)),
        "mau_mo": so(cfg.get("khong_gian.khai_hoang.mau_mo_khai_hoang", 0)),
    }


def _gt_trong_rung(w: Any) -> dict[str, Any]:
    cfg = _cfg(w)
    return {
        "cong": so(cfg.get("khong_gian.rung.trong_rung.cong_moi_thua", 0)),
        "stock": so(
            float(cfg.get("khong_gian.rung.sinh_khoi_toi_da_moi_o", 0))
            * float(cfg.get("khong_gian.rung.trong_rung.ty_le_sinh_khoi_khoi_dau", 0))
        ),
    }


def _gt_bao_gia(w: Any) -> dict[str, Any]:
    return {"han": so(_cfg(w).get("thuong_mai.bao_gia.het_han_tick", 0))}


def _gt_du_an(w: Any) -> dict[str, Any]:
    cfg = _cfg(w)
    registry = cfg.get("du_an.cong_trinh", {})
    details: list[str] = []
    names: list[str] = []
    if isinstance(registry, dict):
        for kind, spec in sorted(registry.items()):
            if not isinstance(spec, dict):
                continue
            recipe = _recipe(w, str(spec.get("recipe", "")))
            labour = so(recipe.get("cong", 0))
            materials = "+".join(
                f"{so(amount)} {asset}" for asset, amount in sorted(recipe.items())
                if asset not in {"cong", "ra"}
            ) or "không có vật liệu"
            output = f"{so(spec.get('so_luong_ra', 1))} {spec.get('tai_san_ra', kind)}"
            site = "; cần thửa của chủ" if bool(spec.get("can_thua", False)) else ""
            names.append(f'"{kind}"')
            details.append(f"{kind}: {labour} công + {materials} → {output}{site}")
    return {
        "loai": "|".join(names) or '"<chưa có công trình>"',
        "chi_tiet": "; ".join(details) or "không có registry công trình",
        "han": so(cfg.get("du_an.han_tick", 0)),
        "toi_da": so(cfg.get("du_an.toi_da_moi_chu", 0)),
    }


def _gt_vu_dong(w: Any) -> dict[str, Any]:
    cay = cay_vu_dong(w)
    return {
        "cay": "|".join(f'"{ten}"' for ten in cay) or '"<chưa có cây vụ khô>"',
        "chi_tiet": "; ".join(
            f"{ten}: {so(spec.get('cong', 0))} công → ~{so(spec.get('san_luong_kg', 0))}kg"
            for ten, spec in cay.items()
        ),
        "mua_kho": ", ".join(mua_kho(w)),
    }


def _gt_cham_tre(w: Any) -> dict[str, Any]:
    cfg = _cfg(w)
    return {
        "tuoi": so(cfg.get("khong_gian.cham_tre.tuoi_can_cham", 0)),
        "cong": so(cfg.get("khong_gian.cham_tre.cong_cham_moi_tre", 0)),
    }


def _gt_chan_nuoi(w: Any) -> dict[str, Any]:
    """CAP-5: `cong_bat` là định mức ENGINE ĐANG DÙNG (`dinh_muc_bat_ga`), không phải khóa
    legacy cố định. Câu mật độ chỉ hiện khi pool gà rừng bật — nói đúng thế giới đang chạy."""
    cn = _cfg(w).raw()["chan_nuoi"]
    return {
        "cong_bat": so(dinh_muc_bat_ga(w)),
        "mat_do": (" ở mật độ đầy (đàn thưa thì cùng số công bắt được ít con hơn)"
                   if _ga_rung_bat(w) else ""),
        "thit_ga": so(cn["thit_moi_ga_kg"]),
        "thit_ga_con": so(cn["thit_moi_ga_con_kg"]),
    }


def _gt_danh_ca(w: Any) -> dict[str, Any]:
    dc = _cfg(w).raw()["danh_ca"]
    return {"cong_kg": so(dc["cong_moi_kg_ca"])}


def _gt_mo_tiec(w: Any) -> dict[str, Any]:
    return {"toi_thieu": so(_cfg(w).raw()["tiec"]["chi_phi_toi_thieu_thoc"])}


def _gt_trom(w: Any) -> dict[str, Any]:
    t = _cfg(w).raw()["trom"]
    return {"toi_da": phan_tram(t["ty_le_lay_toi_da"]),
            "p_bat": phan_tram(1.0 - float(t["p_thanh_cong"]))}


def _gt_nghien_cuu(w: Any) -> dict[str, Any]:
    """CAP-5 (F-CAP5-2): GIÁ CỦA MỘT ĐIỂM nghiên cứu (`engine.research.diem_nghien_cuu`).

    Không công bố hai con số này thì agent không tính nổi cái nó bỏ ra đổi được bao nhiêu —
    và "agent không đầu tư nghiên cứu" trở thành phép đo INTERFACE, không phải phép đo hành vi
    (đúng lớp confound `duc_xu`, và nó chạm thẳng câu hỏi phát minh có tự phát sinh không).
    """
    dnc = _cfg(w).raw()["research"]["diem_nghien_cuu"]
    return {
        "linh_vuc": "|".join(linh_vuc_nghien_cuu(w)),
        "cong_diem": so(dnc["cong_moi_diem"]),
        "thoc_diem": so(dnc["thoc_moi_diem"]),
        "he_so_E": he_so_E_nghien_cuu(w),
    }


def _gt_di_cu(w: Any) -> dict[str, Any]:
    """CAP-5 (F-CAP5-3): ba con số của cổng khả thi trong `engine.tick._di_cu`
    (`khong_du_cum_ruong` / `qua_gan_lang_cu`)."""
    dc = _cfg(w).raw()["di_cu"]
    return {
        "so_thua": so(dc["so_thua_toi_thieu"]),
        "cach_lang": so(dc["cach_lang_toi_thieu"]),
        "ban_kinh": so(dc["ban_kinh_cum"]),
    }


def _gt_cau_hon(w: Any) -> dict[str, Any]:
    """CAP-5 (F-CAP5-4): tuổi engine cưỡng chế ở `engine.demography.xu_ly_cau_hon`
    (cổng `chua_du_tuoi`, áp cho CẢ HAI bên)."""
    return {"tuoi": so(_cfg(w).get("nhan_khau.tuoi_truong_thanh"))}


def _gt_don_phuong_pha_vo(w: Any) -> dict[str, Any]:
    """CAP-5 (F-CAP5-5): ĐỘ LỚN của chi phí duy nhất mà action này phải trả.

    `engine.contracts.phat_vi_pham`: cộng `phat_vi_pham_mieng` vào quan hệ với mỗi bên bị hại,
    và `phat_vi_pham_mieng × he_so_lan_tin_don` vào quan hệ với người quen của họ (tin đồn lan
    một bước). Nói "mất uy tín" mà không nêu độ lớn thì agent không so được nó với cái nó
    nhận từ việc phá vỡ.
    """
    cfg = _cfg(w)
    phat = float(cfg.get("hop_dong.uy_tin.phat_vi_pham_mieng"))
    lan = float(cfg.get("hop_dong.uy_tin.he_so_lan_tin_don"))
    return {"phat": so(phat), "phat_lan": so(phat * lan)}


def _gt_dat_lenh(w: Any) -> dict[str, Any]:
    return {"tai_san": "|".join(tai_san_giao_dich(w))}


def _gt_ban_hanh_luat(w: Any) -> dict[str, Any]:
    return {"tran_thue": phan_tram(_cfg(w).get("chinh_tri.thue_suat_toi_da", 0.0))}


def _gt_bao_dong(w: Any) -> dict[str, Any]:
    cfg = _cfg(w)
    return {
        "gini": so(cfg.get("chinh_tri.gini_nguong_bao_dong", 0.0)),
        "so_dong": phan_tram(cfg.get("chinh_tri.ty_le_so_dong_bao_dong", 0.0)),
    }


def _gt_nhan_tin(w: Any) -> dict[str, Any]:
    """CAP-5 (F-CAP5-7): cap GỬI đã công bố từ trước; cap NHẬN (`minds.p2p_hom_thu_toi_da`,
    `engine.tick`) thì chưa — mà chính nó làm tin rơi IM LẶNG (`hom_thu_day`)."""
    cfg = _cfg(w)
    return {
        "toi_da": so(cfg.get("minds.p2p_gui_toi_da")),
        "hom_thu": so(cfg.get("minds.p2p_hom_thu_toi_da")),
    }


def _gt_bau_cu(w: Any) -> dict[str, Any]:
    return {"chu_ky": so(_cfg(w).get("chinh_tri.bau_cu_moi_n_tick", 0))}


# --------------------------------------------------------------------------- #
#  Cổng scenario                                                                #
# --------------------------------------------------------------------------- #
def _luon(w: Any) -> bool:
    return True


# --------------------------------------------------------------------------- #
#  CATALOG                                                                      #
# --------------------------------------------------------------------------- #
CATALOG: tuple[HanhDongCapability, ...] = (
    HanhDongCapability(
        ten="phan_bo_cong",
        kehoach_field=("canh_thua", "gop_cong_cho", "cong_khai_go", "cong_khai_quang",
                       "hoc", "day_cho"),
        schema_fields=(("canh_thua", "list[str]"), ("gop_cong_cho", "str|null"),
                       ("khai_go_cong", "float"), ("khai_quang_cong", "float"),
                       ("hoc", "bool"), ("day_cho", "list[str]")),
        to_kehoach=_tk_phan_bo_cong, from_kehoach=_fk_phan_bo_cong,
        engine_handler=("engine.production.thi_hanh_san_xuat",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"phan_bo_cong","canh_thua":["P15_04"],"khai_go_cong":$cong_go,'
            '"khai_quang_cong":0,\n'
            '   "hoc":true,"day_cho":["A0012"],"gop_cong_cho":null}   (canh thửa mình/thửa '
            'công/thửa có quyền dùng: $cong_thua công + $giong kg giống mỗi thửa, tự canh '
            'tối đa $thua_max thửa; gỗ $cong_go công/cây, quặng $cong_quang công$ruong_cong)'
        ),
        mau_prompt_gia_tri=_gt_phan_bo_cong,
        ma_ket_qua=("ok", "thieu_cong", "thieu_giong", "khong_co_quyen_dung",
                    "thua_khong_hop_le", "chua_qua_song", "homestead_reserved",
                    "common_land_lottery_lost"),
        thu_tu_phat=10,
    ),
    HanhDongCapability(
        ten="xay",
        kehoach_field=("che_tao_cong_cu", "xay_nha", "xay_may", "duc_xu", "che_hang"),
        schema_fields=(("mon", "str"), ("so_luong", "int")),
        to_kehoach=_tk_xay, from_kehoach=_fk_xay,
        engine_handler=("engine.production.thi_hanh_san_xuat",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"xay","mon":$mon,"so_luong":1}\n'
            '   (chi phí đầu vào → sản phẩm đầu ra MỖI LẦN chế: $cong_thuc)'
        ),
        mau_prompt_gia_tri=_gt_xay,
        ma_ket_qua=("ok", "thieu_cong", "thieu_vat_lieu", "chua_co_blueprint", "mon_la"),
        thu_tu_phat=20,
    ),
    HanhDongCapability(
        ten="nghien_cuu",
        kehoach_field=("nghien_cuu",),
        schema_fields=(("linh_vuc", "str"), ("cong", "float"), ("thoc", "float")),
        to_kehoach=_tk_nghien_cuu, from_kehoach=_fk_nghien_cuu,
        engine_handler=("engine.research.thi_hanh_nghien_cuu",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"nghien_cuu","linh_vuc":"$linh_vuc","cong":60,"thoc":50}\n'
            '   (đầu tư mở, quy ra ĐIỂM tích lũy riêng cho từng lĩnh vực: $cong_diem công = '
            '1 điểm, $thoc_diem kg thóc = 1 điểm, nhân hệ số bậc chữ của người nghiên cứu '
            '($he_so_E). Điểm càng nhiều thì xác suất mỗi tick ra một blueprint càng cao '
            '(mức tăng nhỏ dần); kết quả rút từ phân phối, không có danh sách phát minh sẵn)'
        ),
        mau_prompt_gia_tri=_gt_nghien_cuu,
        ma_ket_qua=("ok", "thieu_cong", "thieu_thoc", "linh_vuc_la"),
        thu_tu_phat=30,
    ),
    HanhDongCapability(
        ten="canh_vu_dong",
        kehoach_field=("canh_vu_dong",),
        schema_fields=(("thua", "str"), ("cay", "str")),
        to_kehoach=_tk_canh_vu_dong, from_kehoach=_fk_canh_vu_dong,
        engine_handler=("engine.production.thi_hanh_san_xuat",),
        kha_dung_fn=_vu_dong_bat, kha_dung_key="khong_gian.bat+khong_gian.vu_dong.bat",
        mau_prompt_template=(
            '- {"loai":"canh_vu_dong","thua":"P15_04","cay":$cay}  (chỉ mùa $mua_kho, '
            'mỗi thửa một cây — $chi_tiet)'
        ),
        mau_prompt_gia_tri=_gt_vu_dong,
        ma_ket_qua=("ok", "thieu_cong", "sai_mua", "thua_khong_hop_le", "cay_la",
                    "chua_qua_song"),
        thu_tu_phat=40,
    ),
    HanhDongCapability(
        ten="cham_tre",
        kehoach_field=("cham_tre_cho",),
        schema_fields=(("tre", "str"),),
        to_kehoach=_tk_cham_tre, from_kehoach=_fk_cham_tre,
        engine_handler=("engine.care.buoc_cham_tre",),
        kha_dung_fn=_cham_tre_bat, kha_dung_key="khong_gian.bat+khong_gian.cham_tre.bat",
        mau_prompt_template=(
            '- {"loai":"cham_tre","tre":"A0012"}  (trẻ dưới $tuoi tuổi cần $cong công chăm '
            'mỗi tick; người chăm dùng công của chính mình — thân nhân hoặc người đã nhận '
            'hợp đồng góp công của cha/mẹ)'
        ),
        mau_prompt_gia_tri=_gt_cham_tre,
        ma_ket_qua=("ok", "thieu_cong", "tre_khong_hop_le", "khong_co_lien_ket_tra_cong"),
        thu_tu_phat=50,
    ),
    HanhDongCapability(
        ten="lap_phap_nhan",
        kehoach_field=("lap_phap_nhan",),
        schema_fields=(("ten", "str"), ("co_phan", "dict[str,float]"),
                       ("von_gop", "dict[str,dict[str,float]]")),
        to_kehoach=_tk_lap_phap_nhan, from_kehoach=_fk_lap_phap_nhan,
        engine_handler=("engine.entities.lap_phap_nhan",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"lap_phap_nhan","ten":"...","co_phan":{"<id bạn>":100},\n'
            '   "von_gop":{"<id bạn>":{"thoc":1500}}}   (vốn góp chỉ từ túi bạn)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "thieu_von", "co_phan_khong_hop_le"),
        thu_tu_phat=60,
    ),
    HanhDongCapability(
        ten="quyet_dinh_entity",
        kehoach_field=("quyet_dinh_entity",),
        schema_fields=(("entity", "str"), ("hanh_dong_con", "list[HanhDong]")),
        to_kehoach=_tk_quyet_dinh_entity, from_kehoach=_fk_quyet_dinh_entity,
        engine_handler=("engine.tick.chay_mot_tick", "engine.entities.nguoi_dieu_hanh"),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"quyet_dinh_entity","entity":"E0001","hanh_dong_con":'
            '[<các hành động trên>]}  (chỉ người nắm >50% cổ phần điều hành được)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_dieu_hanh", "hanh_dong_con_hong"),
        thu_tu_phat=70,
    ),
    HanhDongCapability(
        ten="viet_di_chuc",
        kehoach_field=("viet_di_chuc",),
        schema_fields=(("phan_bo", "dict[str,float]"), ("gia_huan", "str")),
        to_kehoach=_tk_viet_di_chuc, from_kehoach=_fk_viet_di_chuc,
        engine_handler=("engine.demography.thua_ke_mac_dinh",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"viet_di_chuc","phan_bo":{"A0051":60,"A0052":40},'
            '"gia_huan":"≤100 từ"}'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "phan_bo_khong_hop_le"),
        thu_tu_phat=80,
    ),
    HanhDongCapability(
        ten="di_cu",
        kehoach_field=("di_cu",),
        schema_fields=(),
        to_kehoach=_tk_di_cu, from_kehoach=_fk_di_cu,
        engine_handler=("engine.tick._di_cu",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"di_cu"}  (bỏ làng, lập làng mới trên một cụm ruộng công: cần '
            '≥$so_thua thửa ruộng công chưa ai sở hữu nằm trong bán kính $ban_kinh ô quanh '
            'thửa tâm, và cụm đó cách MỌI làng hiện có ≥$cach_lang ô; không đủ thì không đi '
            'được, không mất gì)'
        ),
        mau_prompt_gia_tri=_gt_di_cu,
        ma_ket_qua=("ok", "khong_du_cum_ruong", "qua_gan_lang_cu"),
        thu_tu_phat=90,
    ),
    HanhDongCapability(
        ten="tach_ho",
        kehoach_field=("tach_ho",),
        schema_fields=(),
        to_kehoach=_tk_tach_ho, from_kehoach=_fk_tach_ho,
        engine_handler=("engine.household.buoc_cu_tru",),
        kha_dung_fn=_tach_ho_bat,
        kha_dung_key="ho.cu_tru_ben_vung+ho.tach_ho.bat",
        mau_prompt_template=(
            '- {"loai":"tach_ho"}  (rời hộ cư trú hiện tại để lập hộ mới; chỉ người đã '
            'trưởng thành, hộ cũ vẫn phải còn ít nhất một người lớn; phụ thuộc trực hệ đi '
            'cùng, tài sản không tự chuyển)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_hoat_dong", "chua_truong_thanh", "khong_can_tach",
                    "no_adult_left"),
        thu_tu_phat=91,
    ),
    HanhDongCapability(
        ten="yeu_cau_di_san",
        kehoach_field=("yeu_cau_di_san",),
        schema_fields=(("di_san", "str"),),
        to_kehoach=_tk_yeu_cau_di_san, from_kehoach=_fk_yeu_cau_di_san,
        engine_handler=("engine.estate.yeu_cau_di_san",),
        kha_dung_fn=_di_san_bat,
        kha_dung_key="ho.di_san.bat",
        mau_prompt_template=(
            '- {"loai":"yeu_cau_di_san","di_san":"DI_SAN:A0051"}  (ghi yêu cầu nhận '
            'một di sản đang mở nếu bạn là thân nhân hoặc được nêu trong di chúc; cửa yêu cầu '
            'kéo dài $han tick sau khi người đó mất)'
        ),
        mau_prompt_gia_tri=_gt_di_san,
        ma_ket_qua=("ok", "tinh_nang_tat", "khong_ton_tai", "het_han",
                    "khong_hoat_dong", "no_right"),
        thu_tu_phat=92,
    ),
    HanhDongCapability(
        ten="chon_dat_o",
        kehoach_field=("chon_dat_o",),
        schema_fields=(("thua", "str"), ("du_phong", "list[str]")),
        to_kehoach=_tk_chon_dat_o, from_kehoach=_fk_chon_dat_o,
        engine_handler=("engine.settlement.giai_quyet_chon_dat_o",),
        kha_dung_fn=_dat_o_bat, kha_dung_key="khong_gian.dat_o.bat",
        mau_prompt_template=(
            '- {"loai":"chon_dat_o","thua":"O0001","du_phong":["O0002","O0003"]} '
            '(đăng tối đa $uu_tien lô cư trú công theo thứ tự; nếu trùng người khác, '
            'lottery seeded chọn một người và xét lô dự phòng. Quyền này chỉ cho đặt dự án '
            'nhà, không cấp ruộng, gỗ, công hoặc nhà)'
        ),
        mau_prompt_gia_tri=_gt_chon_dat_o,
        ma_ket_qua=("ok", "actor_ineligible", "already_has_residence",
                    "invalid_residential_site", "residential_sites_unavailable"),
        thu_tu_phat=93,
    ),
    # ---- không gian: đò là DỊCH VỤ (ADR 0005 §2.3) ---- #
    HanhDongCapability(
        ten="dong_thuyen",
        kehoach_field=("dong_thuyen",),
        schema_fields=(("so_luong", "int"),),
        to_kehoach=_tk_dong_thuyen, from_kehoach=_fk_dong_thuyen,
        engine_handler=("engine.spatial.buoc_qua_song", "engine.spatial._dong_thuyen"),
        kha_dung_fn=lambda w: _hai_bo_bat(w) and _co_thuyen(w),
        kha_dung_key="khong_gian.hai_bo+san_xuat.recipe.thuyen",
        mau_prompt_template=(
            '- {"loai":"dong_thuyen","so_luong":1}  (mỗi chiếc: $cong công + $go gỗ; '
            'thiếu thì không đóng được, không mất gì)'
        ),
        mau_prompt_gia_tri=_gt_thuyen,
        ma_ket_qua=("ok", "thieu_cong", "thieu_go", "khong_co_recipe"),
        thu_tu_phat=95,
    ),
    HanhDongCapability(
        ten="rao_do",
        kehoach_field=("rao_do",),
        schema_fields=(("phi", "float"), ("tai_san", "str")),
        to_kehoach=_tk_rao_do, from_kehoach=_fk_rao_do,
        engine_handler=("engine.spatial.buoc_qua_song",),
        kha_dung_fn=_hai_bo_bat, kha_dung_key="khong_gian.hai_bo",
        mau_prompt_template=(
            '- {"loai":"rao_do","phi":5,"tai_san":"thoc"}  (có thuyền thì niêm yết phí chở '
            'khách qua sông mỗi chuyến; tối đa $cap khách/tick, thuyền hao $hao_mon mỗi tick '
            'vận hành; phí do bạn đặt)'
        ),
        mau_prompt_gia_tri=_gt_do,
        ma_ket_qua=("ok", "khong_co_thuyen", "khong_co_khach"),
        thu_tu_phat=96,
    ),
    HanhDongCapability(
        ten="qua_song",
        kehoach_field=("qua_song",),
        schema_fields=(("den_bo", '"dan_cu"|"hoang"'), ("tai_san", "str"),
                       ("phi_chap_nhan", "float")),
        to_kehoach=_tk_qua_song, from_kehoach=_fk_qua_song,
        engine_handler=("engine.spatial.buoc_qua_song",),
        kha_dung_fn=_hai_bo_bat, kha_dung_key="khong_gian.hai_bo",
        mau_prompt_template=(
            '- {"loai":"qua_song","den_bo":"dan_cu"|"hoang","tai_san":"thoc",'
            '"phi_chap_nhan":6}  (xin qua bờ đối diện: tự có thuyền thì không mất phí, '
            'không thì trả phí cho một chủ đò đang rao ≤ mức bạn chấp nhận; không ai chở '
            'thì bạn kẹt lại bờ mình)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_co_do", "phi_khong_du", "het_cho", "sai_bo",
                    "khong_du_tai_san_tra"),
        thu_tu_phat=97,
    ),
    HanhDongCapability(
        ten="khai_hoang",
        kehoach_field=("khai_hoang",),
        schema_fields=(("thua", "str"),),
        to_kehoach=_tk_khai_hoang, from_kehoach=_fk_khai_hoang,
        engine_handler=("engine.production.khai_hoang_dat",),
        kha_dung_fn=_khai_hoang_bat,
        kha_dung_key="khong_gian.bat+khong_gian.khai_hoang.bat",
        mau_prompt_template=(
            '- {"loai":"khai_hoang","thua":"P15_04"}  (vỡ thửa rừng/đồi CÔNG thành ruộng: '
            '$cong công, độ màu đất mới $mau_mo; đất vỡ xong vẫn là đất công tới khi canh '
            'đủ số mùa homestead)'
        ),
        mau_prompt_gia_tri=_gt_khai_hoang,
        ma_ket_qua=("ok", "thieu_cong", "thua_khong_hop_le", "da_co_chu", "chua_qua_song"),
        thu_tu_phat=98,
    ),
    HanhDongCapability(
        ten="trong_rung",
        kehoach_field=("trong_rung",),
        schema_fields=(("thua", "str"),),
        to_kehoach=_tk_trong_rung, from_kehoach=_fk_trong_rung,
        engine_handler=("engine.forest.trong_rung_dat",),
        kha_dung_fn=_trong_rung_bat,
        kha_dung_key="khong_gian.rung.bat+khong_gian.rung.trong_rung.bat",
        mau_prompt_template=(
            '- {"loai":"trong_rung","thua":"P15_04"}  (trồng lại một thửa đồi có thể '
            'tới: tốn $cong công, thành rừng non có $stock sinh khối ban đầu; không tạo gỗ ngay)'
        ),
        mau_prompt_gia_tri=_gt_trong_rung,
        ma_ket_qua=("ok", "thieu_cong", "thua_khong_hop_le", "chua_qua_song"),
        thu_tu_phat=99,
    ),
    HanhDongCapability(
        ten="chan_nuoi",
        kehoach_field=("bat_ga_cong", "giet_ga"),
        schema_fields=(("bat_ga_cong", "float"), ("giet_ga", "int")),
        to_kehoach=_tk_chan_nuoi, from_kehoach=_fk_chan_nuoi,
        engine_handler=("engine.chan_nuoi.bat_ga", "engine.chan_nuoi.giet_ga"),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"chan_nuoi","bat_ga_cong":$cong_bat,"giet_ga":2}  (bắt gà rừng: '
            '$cong_bat công/con$mat_do, cần ô rừng trong làng; giết 1 gà lớn → '
            '$thit_ga kg thịt, gà con → $thit_ga_con kg)'
        ),
        mau_prompt_gia_tri=_gt_chan_nuoi,
        ma_ket_qua=("ok", "thieu_cong", "khong_co_rung", "dan_ga_khong_du"),
        thu_tu_phat=100,
    ),
    HanhDongCapability(
        ten="bieu",
        kehoach_field=("bieu",),
        schema_fields=(("den", "str"), ("tai_san", "str"), ("so_luong", "float")),
        to_kehoach=_tk_bieu, from_kehoach=_fk_bieu,
        engine_handler=("engine.production.thi_hanh_san_xuat",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"bieu","den":"A0002","tai_san":"thoc","so_luong":90}  (biếu tặng — '
            'không cần hợp đồng)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_du_tai_san", "nguoi_nhan_khong_hop_le"),
        thu_tu_phat=110,
    ),
    HanhDongCapability(
        ten="danh_ca",
        kehoach_field=("danh_ca_cong",),
        schema_fields=(("cong", "float"),),
        to_kehoach=_tk_danh_ca, from_kehoach=_fk_danh_ca,
        engine_handler=("engine.chan_nuoi.danh_ca",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"danh_ca","cong":120}  (sông là của chung, không cần ruộng: '
            '~$cong_kg công/kg ở mật độ đầy; cá thưa thì cùng công bắt được ít hơn)'
        ),
        mau_prompt_gia_tri=_gt_danh_ca,
        ma_ket_qua=("ok", "thieu_cong", "song_can_ca"),
        thu_tu_phat=120,
    ),
    HanhDongCapability(
        ten="mo_tiec",
        kehoach_field=("mo_tiec",),
        schema_fields=(("thoc", "float"), ("thit", "float")),
        to_kehoach=_tk_mo_tiec, from_kehoach=_fk_mo_tiec,
        engine_handler=("engine.xa_hoi.mo_tiec",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"mo_tiec","thoc":150,"thit":10}  (mời hàng xóm; dưới $toi_thieu kg '
            'quy thóc thì không ai tới)'
        ),
        mau_prompt_gia_tri=_gt_mo_tiec,
        ma_ket_qua=("ok", "khong_du_chi_phi", "khong_co_khach"),
        thu_tu_phat=130,
    ),
    HanhDongCapability(
        ten="trom",
        kehoach_field=("trom",),
        schema_fields=(("muc_tieu", "str"), ("tai_san", "str"), ("so_luong", "float")),
        to_kehoach=_tk_trom, from_kehoach=_fk_trom,
        engine_handler=("engine.xa_hoi.trom",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"trom","muc_tieu":"A0002","tai_san":"thoc","so_luong":100}  '
            '(lấy trộm tối đa $toi_da kho nạn nhân; $p_bat số lần bị bắt quả tang)'
        ),
        mau_prompt_gia_tri=_gt_trom,
        ma_ket_qua=("ok", "bi_bat_qua_tang", "nan_nhan_khong_hop_le"),
        thu_tu_phat=140,
    ),
    HanhDongCapability(
        ten="nhan_tin",
        kehoach_field=("nhan_tin",),
        schema_fields=(("den", "str"), ("noi_dung", "str")),
        to_kehoach=_tk_nhan_tin, from_kehoach=_fk_nhan_tin,
        engine_handler=("engine.tick.chay_mot_tick",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"nhan_tin","den":"A0002","noi_dung":"..."}  (nhắn riêng 1 người: '
            'mặc cả giá, hỏi mua, rủ hùn hạp, vận động... — họ đọc được ở lượt sau và có '
            'thể nhắn lại; bạn gửi tối đa $toi_da tin/tick, và hòm thư MỖI NGƯỜI NHẬN chỉ '
            'chứa $hom_thu tin/tick — người ta đã nhận đủ $hom_thu tin thì tin của bạn rơi '
            'mất, họ không đọc được)'
        ),
        mau_prompt_gia_tri=_gt_nhan_tin,
        ma_ket_qua=("ok", "hom_thu_day", "nguoi_nhan_khong_hop_le"),
        thu_tu_phat=150,
    ),
    HanhDongCapability(
        ten="de_nghi_hop_dong",
        kehoach_field=("de_nghi_hop_dong",),
        schema_fields=(("den", "str|null"), ("hop_dong", "HopDong")),
        to_kehoach=_tk_de_nghi_hop_dong, from_kehoach=_fk_de_nghi_hop_dong,
        engine_handler=("engine.board.dang_de_nghi",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"de_nghi_hop_dong","den":"A0031"|null,"hop_dong":{"cac_ben":'
            '["<id bạn>","?"],\n'
            '   "hinh_thuc":"mieng"|"van_ban","thoi_han":8,"the_chap":["thua:P15_04"],'
            '"dieu_khoan":[...]}}\n'
            '  ("?" = bên chưa biết, người nhận lời sẽ thế chỗ; bạn PHẢI là một bên; '
            'văn bản cần E$e_van_ban; đề nghị treo trên bảng rao mà không ai trả lời thì tự '
            'gỡ sau $het_han tick)'
        ),
        mau_prompt_gia_tri=lambda w: {
            "e_van_ban": so(_cfg(w).get("hop_dong.van_ban_can_E_nguoi_soan")),
            # CAP-5 (F-CAP5-6): `niem_yet` ĐÃ công bố hạn của nó; hạn đề nghị (engine.board:97)
            # thì chưa — tiền lệ không nhất quán, và hạn hết thì đề nghị biến mất lặng lẽ.
            "het_han": so(_cfg(w).get("hop_dong.de_nghi_het_han_tick")),
        },
        ma_ket_qua=("ok", "khong_du_chu", "the_chap_khong_hop_le", "ben_khong_hop_le"),
        thu_tu_phat=160,
    ),
    HanhDongCapability(
        ten="tra_loi_hop_dong",
        kehoach_field=("tra_loi_de_nghi",),
        schema_fields=(("ref", "str"), ("tra_loi", '"chap_nhan"|"tu_choi"|"mac_ca"'),
                       ("sua_doi", "HopDong|null")),
        to_kehoach=_tk_tra_loi_hop_dong, from_kehoach=_fk_tra_loi_hop_dong,
        engine_handler=("engine.board.khop_bang_rao",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"tra_loi_hop_dong","ref":"DN00012","tra_loi":"chap_nhan"|"tu_choi"'
            '|"mac_ca","sua_doi":{...}}  (mặc cả tối đa $vong vòng)'
        ),
        mau_prompt_gia_tri=lambda w: {
            "vong": so(_cfg(w).get("hop_dong.mac_ca_toi_da_vong")),
        },
        ma_ket_qua=("ok", "de_nghi_khong_ton_tai", "het_vong_mac_ca", "khong_du_dieu_kien"),
        thu_tu_phat=170,
    ),
    HanhDongCapability(
        ten="don_phuong_pha_vo",
        kehoach_field=("don_phuong_pha_vo",),
        schema_fields=(("ref", "str"),),
        to_kehoach=_tk_don_phuong_pha_vo, from_kehoach=_fk_don_phuong_pha_vo,
        engine_handler=("engine.contracts.phat_vi_pham",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"don_phuong_pha_vo","ref":"HD00003"}  (bỏ giao kèo giữa chừng: quan hệ '
            'của bạn với MỖI bên bị hại cộng $phat điểm (số âm = oán), với người quen của họ '
            'cộng $phat_lan điểm — tin đồn lan một bước; giao kèo văn bản có thế chấp thì bị '
            'xiết)'
        ),
        mau_prompt_gia_tri=_gt_don_phuong_pha_vo,
        ma_ket_qua=("ok", "hop_dong_khong_hieu_luc", "khong_phai_ben"),
        thu_tu_phat=180,
    ),
    HanhDongCapability(
        ten="bao_huy",
        kehoach_field=("bao_huy",),
        schema_fields=(("ref", "str"),),
        to_kehoach=_tk_bao_huy, from_kehoach=_fk_bao_huy,
        engine_handler=("engine.tick.chay_mot_tick",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"bao_huy","ref":"HD00003"}  (báo trước để chấm dứt một giao kèo vô '
            'thời hạn ĐÚNG LUẬT — không mất uy tín, khác don_phuong_pha_vo)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "hop_dong_khong_hieu_luc", "khong_phai_ben", "da_bao_huy"),
        thu_tu_phat=190,
    ),
    HanhDongCapability(
        ten="dat_lenh",
        kehoach_field=("dat_lenh",),
        schema_fields=(("chieu", '"mua"|"ban"'), ("tai_san", "str"), ("sl", "float"),
                       ("gia", "float"), ("thanh_toan", "str")),
        to_kehoach=_tk_dat_lenh, from_kehoach=_fk_dat_lenh,
        engine_handler=("engine.market.phien_cho",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"dat_lenh","chieu":"mua"|"ban","tai_san":"$tai_san|\n'
            '   co_phan:<mã pháp nhân>|<mã hàng mới>","sl":4,"gia":12.5,'
            '"thanh_toan":"thoc"}\n'
            '  (giá do khớp lệnh cung-cầu quyết, không ai áp giá; thanh_toan là tài sản '
            'khác tai_san)'
        ),
        mau_prompt_gia_tri=_gt_dat_lenh,
        ma_ket_qua=("ok", "khong_khop", "khong_du_tai_san", "khong_toi_duoc_cho",
                    "lenh_vo_nghia"),
        thu_tu_phat=200,
    ),
    HanhDongCapability(
        ten="buon_chuyen",
        kehoach_field=("dat_lenh",),
        schema_fields=(("chieu", '"mua"|"ban"'), ("tai_san", "str"), ("sl", "float"),
                       ("gia", "float"), ("thanh_toan", "str"), ("lang", "int")),
        to_kehoach=_tk_buon_chuyen, from_kehoach=_fk_uy_quyen,
        nguoi_phat_nguoc="dat_lenh",  # chung field dat_lenh ⇒ phát chung để giữ thứ tự lệnh
        engine_handler=("engine.market.phien_cho", "engine.market._phi_buon_chuyen"),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"buon_chuyen","chieu":"ban","tai_san":"go","sl":4,"gia":14,'
            '"thanh_toan":"thoc","lang":1}\n'
            '  (gửi lệnh sang chợ làng khác; phí vận chuyển $phi mỗi khoảng cách trên giá '
            'trị khớp)'
        ),
        mau_prompt_gia_tri=lambda w: {
            "phi": phan_tram(_cfg(w).get("thuong_mai.phi_van_chuyen_moi_khoang_cach")),
        },
        ma_ket_qua=("ok", "khong_khop", "lang_khong_ton_tai", "khong_toi_duoc_cho"),
        thu_tu_phat=205,
    ),
    HanhDongCapability(
        ten="dang_bao_gia",
        kehoach_field=("dang_bao_gia",),
        schema_fields=(("chieu", '"ban"|"mua"'), ("tai_san", "str"),
                       ("so_luong", "float"), ("don_gia", "float"),
                       ("thanh_toan", "str"), ("doi_tac", "str|null"),
                       ("het_han_tick", "int|null"), ("giao_tai", '"ngay"|"tick:N"')),
        to_kehoach=_tk_dang_bao_gia, from_kehoach=_fk_dang_bao_gia,
        engine_handler=("engine.quotes.buoc_bao_gia",),
        kha_dung_fn=_bao_gia_bat, kha_dung_key="thuong_mai.bao_gia.bat",
        mau_prompt_template=(
            '- {"loai":"dang_bao_gia","chieu":"ban"|"mua","tai_san":"go",'
            '"so_luong":4,"don_gia":12,"thanh_toan":"thoc","doi_tac":null,'
            '"het_han_tick":null,"giao_tai":"ngay"}  (tạo báo giá song phương; tài sản '
            'bạn hứa giao bị ký quỹ ngay, hạn mặc định $han tick; đơn giá và tài sản thanh '
            'toán do bạn tự nêu)'
        ),
        mau_prompt_gia_tri=_gt_bao_gia,
        ma_ket_qua=("ok", "bad_params", "insufficient_inventory", "counterparty_unavailable",
                    "expired_quote"),
        thu_tu_phat=206,
    ),
    HanhDongCapability(
        ten="chap_nhan_bao_gia",
        kehoach_field=("chap_nhan_bao_gia",),
        schema_fields=(("ref", "str"), ("so_luong", "float|null")),
        to_kehoach=_tk_chap_nhan_bao_gia, from_kehoach=_fk_chap_nhan_bao_gia,
        engine_handler=("engine.quotes.buoc_bao_gia",),
        kha_dung_fn=_bao_gia_bat, kha_dung_key="thuong_mai.bao_gia.bat",
        mau_prompt_template=(
            '- {"loai":"chap_nhan_bao_gia","ref":"BG00001","so_luong":2}  (chấp nhận '
            'toàn bộ hoặc một phần báo giá bạn nhìn thấy; phần đối ứng của bạn cũng bị ký quỹ, '
            'nên một báo giá không thể bị dùng hai lần)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "offer_not_found", "offer_not_visible", "quote_exhausted",
                    "expired_quote", "insufficient_payment", "bad_params"),
        thu_tu_phat=207,
    ),
    HanhDongCapability(
        ten="huy_bao_gia",
        kehoach_field=("huy_bao_gia",),
        schema_fields=(("ref", "str"),),
        to_kehoach=_tk_huy_bao_gia, from_kehoach=_fk_huy_bao_gia,
        engine_handler=("engine.quotes.buoc_bao_gia",),
        kha_dung_fn=_bao_gia_bat, kha_dung_key="thuong_mai.bao_gia.bat",
        mau_prompt_template=(
            '- {"loai":"huy_bao_gia","ref":"BG00001"}  (chỉ người đã đăng mới rút được '
            'phần báo giá chưa khớp; ký quỹ chưa dùng được hoàn lại)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "offer_not_found", "not_authorized", "quote_closed"),
        thu_tu_phat=208,
    ),
    HanhDongCapability(
        ten="tao_du_an",
        kehoach_field=("tao_du_an",),
        schema_fields=(("loai_du_an", "str"), ("thua", "str|null")),
        to_kehoach=_tk_tao_du_an, from_kehoach=_fk_tao_du_an,
        engine_handler=("engine.projects.dang_ky_du_an",),
        kha_dung_fn=_du_an_bat, kha_dung_key="du_an.bat",
        mau_prompt_template=(
            '- {"loai":"tao_du_an","loai_du_an":$loai,"thua":"P15_04"}  '
            '(mở một work-order; $chi_tiet; mỗi chủ tối đa $toi_da dự án đang mở, hạn $han tick; '
            'mở dự án chưa làm mất vật liệu hay công)'
        ),
        mau_prompt_gia_tri=_gt_du_an,
        ma_ket_qua=("ok", "unknown_project", "project_capacity", "no_site", "no_right",
                    "bad_project_spec"),
        thu_tu_phat=2081,
    ),
    HanhDongCapability(
        ten="gop_vat_lieu_du_an",
        kehoach_field=("gop_vat_lieu_du_an",),
        schema_fields=(("ref", "str"), ("tai_san", "str"), ("so_luong", "float")),
        to_kehoach=_tk_gop_vat_lieu_du_an, from_kehoach=_fk_gop_vat_lieu_du_an,
        engine_handler=("engine.projects.buoc_du_an",),
        kha_dung_fn=_du_an_bat, kha_dung_key="du_an.bat",
        mau_prompt_template=(
            '- {"loai":"gop_vat_lieu_du_an","ref":"DA00001","tai_san":"go",'
            '"so_luong":10}  (chuyển vật liệu của bạn vào ký quỹ dự án; chỉ phần recipe còn thiếu '
            'được giữ, hủy/hết hạn trả phần còn trong ký quỹ về người đã góp)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "project_not_found", "project_closed", "no_access", "no_inventory",
                    "material_complete", "bad_params"),
        thu_tu_phat=2082,
    ),
    HanhDongCapability(
        ten="gop_cong_du_an",
        kehoach_field=("gop_cong_du_an",),
        schema_fields=(("ref", "str"), ("so_cong", "float")),
        to_kehoach=_tk_gop_cong_du_an, from_kehoach=_fk_gop_cong_du_an,
        engine_handler=("engine.projects.buoc_du_an",),
        kha_dung_fn=_du_an_bat, kha_dung_key="du_an.bat",
        mau_prompt_template=(
            '- {"loai":"gop_cong_du_an","ref":"DA00001","so_cong":20}  '
            '(công bị dùng trong tick này và được ghi theo người; chỉ công còn lại sau các action '
            'trước đó mới góp được, không có trả công tự động)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "project_not_found", "project_closed", "no_access",
                    "insufficient_labor", "labor_complete", "bad_params"),
        thu_tu_phat=2083,
    ),
    HanhDongCapability(
        ten="huy_du_an",
        kehoach_field=("huy_du_an",),
        schema_fields=(("ref", "str"),),
        to_kehoach=_tk_huy_du_an, from_kehoach=_fk_huy_du_an,
        engine_handler=("engine.projects.buoc_du_an",),
        kha_dung_fn=_du_an_bat, kha_dung_key="du_an.bat",
        mau_prompt_template=(
            '- {"loai":"huy_du_an","ref":"DA00001"}  (chỉ chủ dự án hủy được; vật liệu còn '
            'trong ký quỹ hoàn về đúng người đã góp, công đã dùng không hoàn lại)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "project_not_found", "not_authorized", "project_closed"),
        thu_tu_phat=2084,
    ),
    HanhDongCapability(
        ten="niem_yet",
        kehoach_field=("niem_yet_dat", "dat_lenh"),
        schema_fields=(("tai_san", "str"), ("gia", "float"), ("sl", "float")),
        to_kehoach=_tk_niem_yet, from_kehoach=_fk_niem_yet,
        engine_handler=("engine.market.phien_dat", "engine.market.phien_cho"),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"niem_yet","tai_san":"thua:P15_04","gia":600}   (rao bán đất của '
            'mình; niêm yết không ai mua thì tự gỡ sau $het_han tick)'
        ),
        mau_prompt_gia_tri=lambda w: {
            "het_han": so(_cfg(w).get("thuong_mai.niem_yet_het_han_tick")),
        },
        ma_ket_qua=("ok", "khong_phai_chu_dat", "gia_khong_hop_le"),
        thu_tu_phat=210,
    ),
    HanhDongCapability(
        ten="tra_gia_dat",
        kehoach_field=("tra_gia_dat",),
        schema_fields=(("thua", "str"), ("gia", "float")),
        to_kehoach=_tk_tra_gia_dat, from_kehoach=_fk_tra_gia_dat,
        engine_handler=("engine.market.phien_dat",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"tra_gia_dat","thua":"P15_04","gia":650}        (trả giá đất đang '
            'niêm yết — đấu giá KÍN, không thấy giá người khác)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "thua_khong_niem_yet", "gia_duoi_ask", "thua_gia_nguoi_khac",
                    "khong_du_thoc"),
        thu_tu_phat=220,
    ),
    HanhDongCapability(
        ten="yeu_cau_hoan_tra",
        kehoach_field=("yeu_cau_rut",),
        schema_fields=(("ref", "str"), ("so_luong", "float")),
        to_kehoach=_tk_yeu_cau_hoan_tra, from_kehoach=_fk_yeu_cau_hoan_tra,
        engine_handler=("engine.contracts.thi_hanh_hop_dong_tick",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"yeu_cau_hoan_tra","ref":"HD00007","so_luong":200}  (rút tài sản đã '
            'gửi theo điều khoản hoan_tra_theo_yeu_cau; trần rút mỗi tick ghi trong giao kèo)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "vuot_tran_rut", "ben_giu_khong_du", "hop_dong_khong_hieu_luc"),
        thu_tu_phat=230,
    ),
    HanhDongCapability(
        ten="cau_hon",
        kehoach_field=("cau_hon",),
        schema_fields=(("den", "str"),),
        to_kehoach=_tk_cau_hon, from_kehoach=_fk_cau_hon,
        engine_handler=("engine.demography.xu_ly_cau_hon",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template=(
            '- {"loai":"cau_hon","den":"A0042"}  (CẢ HAI bên phải từ $tuoi tuổi trở lên; '
            'người kia trả lời ở tick sau; cận huyết không thành)'
        ),
        mau_prompt_gia_tri=_gt_cau_hon,
        ma_ket_qua=("ok", "can_huyet", "da_co_gia_dinh", "chua_du_tuoi"),
        thu_tu_phat=240,
    ),
    HanhDongCapability(
        ten="tra_loi_cau_hon",
        kehoach_field=("tra_loi_cau_hon",),
        schema_fields=(("cua", "str"), ("dong_y", "bool")),
        to_kehoach=_tk_tra_loi_cau_hon, from_kehoach=_fk_tra_loi_cau_hon,
        engine_handler=("engine.demography.xu_ly_cau_hon",),
        kha_dung_fn=_luon, kha_dung_key="luon",
        mau_prompt_template='- {"loai":"tra_loi_cau_hon","cua":"A0042","dong_y":true}',
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_co_loi_cau_hon", "da_co_gia_dinh"),
        thu_tu_phat=250,
    ),
    # ---- việc làng: bầu bán, thuế khóa, đấu tranh (mọi thứ tự phát từ ý dân) ---- #
    HanhDongCapability(
        ten="ung_cu",
        kehoach_field=("ung_cu",),
        schema_fields=(),
        to_kehoach=_tk_ung_cu, from_kehoach=_fk_ung_cu,
        engine_handler=("engine.politics.buoc_chinh_quyen",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"ung_cu"}  (tự ra ứng cử làm Trưởng làng ở kỳ bầu tới; cả làng bầu '
            'mỗi $chu_ky tick)'
        ),
        mau_prompt_gia_tri=_gt_bau_cu,
        ma_ket_qua=("ok", "chua_truong_thanh", "khong_phai_ky_bau"),
        thu_tu_phat=260,
    ),
    HanhDongCapability(
        ten="bo_phieu",
        kehoach_field=("bo_phieu",),
        schema_fields=(("cho", "str"),),
        to_kehoach=_tk_bo_phieu, from_kehoach=_fk_bo_phieu,
        engine_handler=("engine.politics.buoc_chinh_quyen",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"bo_phieu","cho":"A0001"}  (bỏ lá phiếu cho một người đang ứng cử '
            'Trưởng làng)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "ung_vien_khong_ton_tai", "khong_phai_ky_bau"),
        thu_tu_phat=270,
    ),
    HanhDongCapability(
        ten="ban_hanh_luat",
        kehoach_field=("ban_hanh_luat",),
        schema_fields=(("luat", "dict"),),
        to_kehoach=_tk_ban_hanh_luat, from_kehoach=_fk_ban_hanh_luat,
        engine_handler=("engine.politics.buoc_chinh_quyen", "engine.politics.thu_thue_va_chia"),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"ban_hanh_luat","luat":{"loai":"thue","suat":0.1}}  hoặc\n'
            '  {"loai":"ban_hanh_luat","luat":{"loai":"luong_toi_thieu","muc":2.0}}\n'
            '  (chỉ Trưởng làng đương nhiệm: thuế suất trên thu hoạch nộp CÔNG QUỸ — trần '
            '$tran_thue; hoặc mức lương tối thiểu mỗi công làm thuê)'
        ),
        mau_prompt_gia_tri=_gt_ban_hanh_luat,
        ma_ket_qua=("ok", "khong_phai_truong_lang", "vuot_tran_thue", "luat_la"),
        thu_tu_phat=280,
    ),
    HanhDongCapability(
        ten="hoi_lo",
        kehoach_field=("hoi_lo",),
        schema_fields=(("den", "str"), ("thoc", "float")),
        to_kehoach=_tk_hoi_lo, from_kehoach=_fk_hoi_lo,
        engine_handler=("engine.politics.buoc_chinh_quyen",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"hoi_lo","den":"A0001","thoc":100}  (đưa riêng thóc cho một người để '
            'đổi lấy lá phiếu hoặc ân huệ — người kia nhận hay không là tùy họ)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_du_thoc", "nguoi_nhan_tu_choi"),
        thu_tu_phat=290,
    ),
    HanhDongCapability(
        ten="nghiep_doan",
        kehoach_field=("gia_nhap_nghiep_doan",),
        schema_fields=(("gia_nhap", "bool"),),
        to_kehoach=_tk_nghiep_doan, from_kehoach=_fk_nghiep_doan,
        engine_handler=("engine.politics.buoc_chinh_quyen",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"nghiep_doan","gia_nhap":true}  (gia nhập nhóm người làm công cùng '
            'thương lượng điều kiện; đặt false để rời nhóm)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "da_trong_nhom", "khong_trong_nhom"),
        thu_tu_phat=300,
    ),
    HanhDongCapability(
        ten="dinh_cong",
        kehoach_field=("dinh_cong",),
        schema_fields=(),
        to_kehoach=_tk_dinh_cong, from_kehoach=_fk_dinh_cong,
        engine_handler=("engine.politics.buoc_chinh_quyen",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"dinh_cong"}  (ngừng góp công theo giao kèo làm thuê để gây sức ép; '
            'chỉ người trong nghiệp đoàn)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "khong_trong_nghiep_doan", "khong_co_giao_keo_gop_cong"),
        thu_tu_phat=310,
    ),
    HanhDongCapability(
        ten="bao_dong",
        kehoach_field=("bao_dong",),
        schema_fields=(),
        to_kehoach=_tk_bao_dong, from_kehoach=_fk_bao_dong,
        engine_handler=("engine.politics.buoc_bao_dong",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"bao_dong"}  (cùng nhiều người nổi dậy sung công của cải nhà giàu '
            'chia lại — chỉ thành khi hệ số Gini thóc vượt $gini VÀ ≥$so_dong người lớn '
            'cùng nổi dậy)'
        ),
        mau_prompt_gia_tri=_gt_bao_dong,
        ma_ket_qua=("ok", "gini_duoi_nguong", "khong_du_so_dong"),
        thu_tu_phat=320,
    ),
    HanhDongCapability(
        ten="keu_goi",
        kehoach_field=("keu_goi",),
        schema_fields=(("noi_dung", "str"),),
        to_kehoach=_tk_keu_goi, from_kehoach=_fk_keu_goi,
        engine_handler=("engine.politics.buoc_chinh_quyen",),
        kha_dung_fn=_chinh_tri_bat, kha_dung_key="chinh_tri.bat",
        mau_prompt_template=(
            '- {"loai":"keu_goi","noi_dung":"..."}  (nói trước cả làng ở buổi họp — lời '
            'vận động thuần, tự nó không dịch chuyển của cải)'
        ),
        mau_prompt_gia_tri=_gt_rong,
        ma_ket_qua=("ok", "noi_dung_rong"),
        thu_tu_phat=330,
    ),
)

TU_TEN: dict[str, HanhDongCapability] = {c.ten: c for c in CATALOG}


# --------------------------------------------------------------------------- #
#  API dùng bởi schemas / translate / prompts                                   #
# --------------------------------------------------------------------------- #
def cac_ten_cong_khai() -> frozenset[str]:
    """Whitelist tên action agent gọi được (nguồn của `minds.schemas.LOAI_HANH_DONG`)."""
    return frozenset(c.ten for c in CATALOG if c.cong_khai)


def kha_dung_trong(w: Any) -> tuple[HanhDongCapability, ...]:
    """Descriptor CÔNG KHAI + khả dụng trong thế giới `w` (thứ tự khai báo)."""
    return tuple(c for c in CATALOG if c.cong_khai and c.kha_dung(w))


def ap_dung_hanh_dong(w: Any, kh: KeHoach, d: dict[str, Any],
                      thung: list | None = None) -> None:
    """Dispatch MỘT hành động (dict đã validate schema) → mutate `KeHoach`.

    Loại lạ / tham số sai → thùng intent lạ hoặc `ghi_unrecognized`, KHÔNG raise ra ngoài
    trừ lỗi tham số (caller bắt) — giữ đúng điều luật #3.
    """
    loai = d.get("loai")
    cap = TU_TEN.get(str(loai)) if isinstance(loai, str) else None
    if cap is None or not cap.cong_khai:
        if thung is not None:
            thung.append((kh.id, d, "loại hành động lạ"))
        else:
            w.ghi_unrecognized(kh.id, str(loai), "loại hành động lạ")
        return
    cap.to_kehoach(w, kh, d, thung)


def hanh_dong_tu_ke_hoach(kh: KeHoach) -> list[dict[str, Any]]:
    """KeHoach → danh sách hành động JSON, ĐÚNG thứ tự wire (`thu_tu_phat`)."""
    ra: list[dict[str, Any]] = []
    for cap in sorted(CATALOG, key=lambda c: (c.thu_tu_phat, c.ten)):
        ra.extend(cap.from_kehoach(kh))
    return ra


def catalog_hash() -> str:
    """SHA256 của NỘI DUNG KHAI BÁO catalog (sort theo `ten` ⇒ reorder file không đổi hash).

    Vào `experiment_manifest.reproducibility.capability_catalog_hash` (ADR 0006 §A.2) —
    KHÔNG vào `world_hash` (catalog là interface, không phải state của thế giới).

    Băm CẢ các BẢNG RENDER (CAP-5): danh sách món `xay`, bí danh, khóa-không-phải-nguyên-liệu,
    nhãn nguyên liệu, điều kiện ngoài-nguyên-liệu, tài sản không rao, field không-phải-action.
    Chúng KHÔNG phải chi tiết cài đặt: chúng quyết định action/món nào được CHÀO và kinh tế học
    nào được CÔNG BỐ — tức chính bề mặt mà agent nhìn thấy. Không băm thì đổi "quặng đồng"
    thành mã khác, hay bỏ điều kiện blueprint của `may`, sẽ đổi prompt của MỌI agent mà
    `capability_catalog_hash` đứng yên (và `prompt_template_hash` cũng đứng yên vì nó chỉ băm
    `minds/prompts.py`) ⇒ hai run khác interface trông y hệt nhau trong manifest.

    CÒN HỞ (không đóng được từ file này): THÂN các hàm render `_gt_*` và `mo_ta_cong_thuc` nằm
    ở module này nhưng KHÔNG vào hash nào — `prompt_template_hash` (run.py `_repro_llm_meta`)
    chỉ sha256 `minds/prompts.py`. Xem handoff: nó cần băm cả `minds/capabilities.py`.
    """
    khai_bao: dict[str, Any] = {
        "actions": [c.khai_bao() for c in sorted(CATALOG, key=lambda c: c.ten)],
        "bang_render": {
            "MON_XAY": {k: list(v) for k, v in sorted(MON_XAY.items())},
            "BI_DANH_MON_XAY": dict(sorted(BI_DANH_MON_XAY.items())),
            "MON_NGOAI_XAY": sorted(MON_NGOAI_XAY),
            "KHOA_RECIPE_KHONG_PHAI_NGUYEN_LIEU": sorted(
                KHOA_RECIPE_KHONG_PHAI_NGUYEN_LIEU),
            "NHAN_NGUYEN_LIEU": dict(sorted(NHAN_NGUYEN_LIEU.items())),
            "DIEU_KIEN_MON_XAY": dict(sorted(DIEU_KIEN_MON_XAY.items())),
            "TAI_SAN_KHONG_RAO": sorted(TAI_SAN_KHONG_RAO),
            "FIELD_KHONG_PHAI_ACTION": sorted(FIELD_KHONG_PHAI_ACTION),
        },
    }
    blob = json.dumps(khai_bao, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def handler_ton_tai(ten_day_du: str) -> bool:
    """`engine_handler` có import được bằng tên không (CAP-1) — không import ngược minds."""
    mod, _, attr = ten_day_du.rpartition(".")
    try:
        return hasattr(importlib.import_module(mod), attr)
    except ImportError:
        return False
