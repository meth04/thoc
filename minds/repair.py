"""Pipeline sửa JSON (SPEC 7.5) — chung cho mock lẫn real.

strip fence/lời dẫn → json_repair → pydantic → (caller retry 1 lần) → fallback.
Chỉ tiêu: p_malformed=0.15 → fallback_rate < 5%.
"""

from __future__ import annotations

import json
import re
from typing import Any

from json_repair import repair_json
from pydantic import ValidationError

from minds.schemas import QuyetDinh


def _strip_van_ban(text: str) -> str:
    """Bỏ markdown fence + lời dẫn: lấy đoạn từ '[' hoặc '{' đầu tới ']'/'}' cuối."""
    text = re.sub(r"```(?:json)?", "", text)
    # chuẩn hóa quote cong
    text = (text.replace("“", '"').replace("”", '"')
                .replace("‘", "'").replace("’", "'"))
    dau = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if dau < 0:
        return text.strip()
    cuoi = max(text.rfind("]"), text.rfind("}"))
    if cuoi <= dau:
        return text[dau:].strip()  # bị cắt cuối — để json_repair vá
    return text[dau:cuoi + 1].strip()


def _chuan_hoa_phan_tu(d: dict[str, Any]) -> dict[str, Any]:
    """Sửa lỗi mềm: key viết hoa, số kiểu Việt '1.000' trong chuỗi."""
    ra: dict[str, Any] = {}
    for k, v in d.items():
        k2 = k.lower() if isinstance(k, str) else k
        ra[k2] = _chuan_hoa_gia_tri(v)
    return ra


def _chuan_hoa_gia_tri(v: Any) -> Any:
    if isinstance(v, dict):
        return _chuan_hoa_phan_tu(v)
    if isinstance(v, list):
        return [_chuan_hoa_gia_tri(x) for x in v]
    if isinstance(v, str) and re.fullmatch(r"\d{1,3}(\.\d{3})+", v):
        return float(v.replace(".", ""))  # "1.000" → 1000
    return v


def sua_va_parse(text: str) -> list[dict[str, Any]]:
    """Text thô → list dict quyết định (mỗi phần tử validate riêng ở bước sau).

    Raise ValueError nếu không cứu nổi cấu trúc.
    """
    sach = _strip_van_ban(text)
    try:
        du_lieu = json.loads(sach)
    except json.JSONDecodeError:
        vau = repair_json(sach, return_objects=True)
        if vau in ("", None):
            raise ValueError("json_repair không cứu được") from None
        du_lieu = vau
    if isinstance(du_lieu, dict):
        du_lieu = [du_lieu]
    if not isinstance(du_lieu, list):
        raise ValueError(f"cấu trúc lạ sau repair: {type(du_lieu)}")
    return [_chuan_hoa_phan_tu(x) for x in du_lieu if isinstance(x, dict)]


def validate_quyet_dinh(phan_tu: dict[str, Any]) -> QuyetDinh:
    """Validate một phần tử; raise ValidationError nếu hỏng."""
    return QuyetDinh.model_validate(phan_tu)


def parse_batch(text: str, ids_mong_doi: list[str]) -> tuple[dict[str, QuyetDinh], list[str]]:
    """Parse text batch → {id: QuyetDinh hợp lệ}, danh sách id hỏng (cần retry/fallback)."""
    hong: list[str] = []
    ket_qua: dict[str, QuyetDinh] = {}
    try:
        cac_phan_tu = sua_va_parse(text)
    except ValueError:
        return {}, list(ids_mong_doi)
    theo_id = {}
    for pt in cac_phan_tu:
        pid = pt.get("id")
        if isinstance(pid, str):
            theo_id[pid] = pt
    for aid in ids_mong_doi:
        pt = theo_id.get(aid)
        if pt is None:
            hong.append(aid)
            continue
        try:
            ket_qua[aid] = validate_quyet_dinh(pt)
        except ValidationError:
            hong.append(aid)
    return ket_qua, hong
