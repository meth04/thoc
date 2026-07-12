"""tools/reality_check — đóng gói giao thức check.md thành CLI một lệnh (CHỈ ĐỌC).

  python -m tools.reality_check [--run data/runs/<ten_run>] [--muc S,P,D,E]

In bảng pass/fail + bằng chứng cho từng mục kiểm định của check.md:
  - Mục S (S1-S8): kiểm định TĨNH trên engine/ + config/ (grep + AST-scan).
  - Mục P (P1-P5): kiểm định PROMPT trên minds/prompts.py + 1 prompt render thật.
  - Mục C (C1-C5): chưa tự động — in hướng dẫn chạy counterfactual bằng tay.
  - Mục D (D1, D3, D4): nguồn gốc quyết định, từ log của run.
  - Mục E (E1, E4, E6, E7): hiện tượng nổi lên — CHỈ BÁO CÁO khớp/lệch, không nắn.

Ghi báo cáo vào reports/reality_check_<run|static>.md.
Exit code khác 0 nếu có mục S/P fail (ngưỡng gate theo check.md mục 6).
Tool này chỉ đọc code và log — không sửa bất kỳ trạng thái nào của thế giới.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sqlite3
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO / "engine"
MINDS_DIR = REPO / "minds"
CONFIG_DIR = REPO / "config"
REPORT_DIR = REPO / "reports"

KetQua = dict[str, str]  # {"muc", "ket_luan", "bang_chung"}

# kết luận hợp lệ: pass | partial | fail | loi | khong_du_du_lieu | khop | lech
KET_LUAN_GATE_FAIL = "fail"

# ---------------------------------------------------------------- tiện ích quét


def _cac_file_engine() -> list[Path]:
    return sorted(p for p in ENGINE_DIR.glob("*.py"))


def _doc(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _vung_chuoi_comment(text: str) -> list[tuple[int, int, int, int]]:
    """Các vùng (srow, scol, erow, ecol) là token STRING/COMMENT — để whitelist hit grep."""
    vung: list[tuple[int, int, int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                vung.append((tok.start[0], tok.start[1], tok.end[0], tok.end[1]))
    except (tokenize.TokenError, IndentationError):
        pass  # file đang được sửa dở — coi như không có vùng chuỗi
    return vung


def _trong_vung(vung: list[tuple[int, int, int, int]], row: int, col: int) -> bool:
    for sr, sc, er, ec in vung:
        if sr == er == row and sc <= col < ec:
            return True
        if sr < row < er:
            return True
        if sr == row < er and col >= sc:
            return True
        if er == row > sr and col < ec:
            return True
    return False


def _quet_regex(files: list[Path], pattern: str, flags: int = 0) -> list[tuple[Path, int, int, str]]:
    """Trả [(file, dòng, cột, nội_dung_dòng)] cho mọi match."""
    rx = re.compile(pattern, flags)
    hits: list[tuple[Path, int, int, str]] = []
    for f in files:
        try:
            text = _doc(f)
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for m in rx.finditer(line):
                hits.append((f, i, m.start(), line.strip()))
    return hits


def _mo_ta_hit(hits: list[tuple[Path, int, int, str]], toi_da: int = 12) -> str:
    dong = [f"{h[0].relative_to(REPO)}:{h[1]}: {h[3][:110]}" for h in hits[:toi_da]]
    them = f" (+{len(hits) - toi_da} hit nữa)" if len(hits) > toi_da else ""
    return "; ".join(dong) + them


def _phan_loai_hit(hits: list[tuple[Path, int, int, str]]) -> tuple[list, list]:
    """Tách hit thành (trong_code, trong_comment_hoac_chuoi) bằng tokenize từng file."""
    cache: dict[Path, list] = {}
    code, chu_thich = [], []
    for h in hits:
        f = h[0]
        if f not in cache:
            cache[f] = _vung_chuoi_comment(_doc(f))
        (chu_thich if _trong_vung(cache[f], h[1], h[2]) else code).append(h)
    return code, chu_thich


# ---------------------------------------------------------------- mục S (tĩnh)


def kiem_s1() -> KetQua:
    """S1: định chế có tên không được tồn tại trong engine/ (trừ comment/docstring phủ định)."""
    pat = (r"\b(bank|loan|company|firm|insurance|wage|salary)\b"
           r"|ngan_hang|ngân hàng|cong_ty|công ty|bao_hiem|bảo hiểm|lai_suat|tin_dung|lam_thue")
    hits = _quet_regex(_cac_file_engine(), pat, re.IGNORECASE)
    code, chu_thich = _phan_loai_hit(hits)
    if code:
        return {"muc": "S1", "ket_luan": "fail",
                "bang_chung": f"Định chế có tên trong CODE engine/: {_mo_ta_hit(code)}"}
    bc = "0 hit trong code engine/."
    if chu_thich:
        bc += f" {len(chu_thich)} hit chỉ nằm trong comment/docstring (whitelist): " \
              f"{_mo_ta_hit(chu_thich, 5)}"
    return {"muc": "S1", "ket_luan": "pass", "bang_chung": bc}


def kiem_s2() -> KetQua:
    """S2: không tồn tại file/bảng phát minh định sẵn (tech_tree, unlock_list)."""
    van_de: list[str] = []
    tt = CONFIG_DIR / "tech_tree.yaml"
    if tt.exists():
        van_de.append(f"{tt.relative_to(REPO)} VẪN TỒN TẠI (cây công nghệ định sẵn)")
    files = [*_cac_file_engine(), *sorted(MINDS_DIR.glob("*.py")),
             *sorted((REPO / "observatory").glob("*.py")), REPO / "run.py",
             *sorted(CONFIG_DIR.glob("*.yaml"))]
    hits = [h for h in _quet_regex([f for f in files if f.exists()],
                                   r"tech_tree|unlock_list", re.IGNORECASE)
            if h[0].name != "tech_tree.yaml"]
    if hits:
        van_de.append(f"grep tech_tree|unlock_list: {_mo_ta_hit(hits)}")
    if van_de:
        return {"muc": "S2", "ket_luan": "fail", "bang_chung": "; ".join(van_de)}
    return {"muc": "S2", "ket_luan": "pass",
            "bang_chung": "Không có config/tech_tree.yaml; grep tech_tree|unlock_list → 0 "
                          "(research.yaml chỉ chứa lĩnh vực + phân phối)."}


def kiem_s3() -> KetQua:
    """S3: không nhánh if nào trong engine rẽ theo nhãn giai cấp."""
    pat = r"class_|giai_cap|dia_chu|ta_dien|cong_nhan|phu_nong"
    hits = _quet_regex(_cac_file_engine(), pat)
    code, _ = _phan_loai_hit(hits)
    re_nhanh = [h for h in code if re.search(r"\b(if|elif|while)\b", h[3])]
    if re_nhanh:
        return {"muc": "S3", "ket_luan": "fail",
                "bang_chung": f"Nhánh rẽ theo nhãn giai cấp: {_mo_ta_hit(re_nhanh)}"}
    bc = "Không nhánh if/elif/while nào theo nhãn giai cấp."
    if code:
        bc += f" {len(code)} hit còn lại chỉ là ghi metrics/cache observatory: {_mo_ta_hit(code, 5)}"
    return {"muc": "S3", "ket_luan": "pass", "bang_chung": bc}


def _ast_engine() -> dict[Path, ast.AST]:
    cay: dict[Path, ast.AST] = {}
    for f in _cac_file_engine():
        try:
            cay[f] = ast.parse(_doc(f))
        except SyntaxError:
            continue  # file đang được sửa dở
    return cay


def kiem_s4() -> KetQua:
    """S4: engine không tự đặt giá — giá chỉ từ khớp lệnh cung–cầu."""
    van_de: list[str] = []
    # (a) check.md nguyên văn: "price =" ngoài market.py
    hits = [h for h in _quet_regex(_cac_file_engine(), r"\bprice\s*=", re.IGNORECASE)
            if h[0].name != "market.py"]
    if hits:
        van_de.append(f"'price =' ngoài market.py: {_mo_ta_hit(hits)}")
    for f, tree in _ast_engine().items():
        for node in ast.walk(tree):
            # (b) fallback giá bịa: gia_gan_nhat(...) or <hằng số>
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                co_gia = any(
                    isinstance(v, ast.Call) and "gia_gan_nhat" in ast.dump(v.func)
                    for v in node.values
                )
                hang = [v for v in node.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, int | float)
                        and not isinstance(v.value, bool) and v.value != 0]
                if co_gia and hang:
                    van_de.append(f"{f.relative_to(REPO)}:{node.lineno}: "
                                  f"gia_gan_nhat(...) or {hang[0].value} — engine bịa giá")
            # (c) ledger.chuyen với SỐ LƯỢNG là hằng số → giao dịch giá cứng do engine ép
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "chuyen" and len(node.args) >= 4):
                sl = node.args[3]
                if (isinstance(sl, ast.Constant) and isinstance(sl.value, int | float)
                        and not isinstance(sl.value, bool) and sl.value != 1.0):
                    # 1.0 = chuyển MỘT đơn vị nguyên (round-robin tài sản rời khi thừa kế)
                    # — không phải giá; hằng khác mới là engine ép lượng
                    van_de.append(f"{f.relative_to(REPO)}:{node.lineno}: "
                                  f"ledger.chuyen(..., {sl.value}, ...) — lượng chuyển hằng cứng")
    if van_de:
        return {"muc": "S4", "ket_luan": "fail", "bang_chung": "; ".join(van_de[:10])}
    return {"muc": "S4", "ket_luan": "pass",
            "bang_chung": "Không thấy engine đặt giá: không 'price =' ngoài market, không "
                          "fallback giá hằng số, không giao dịch lượng cứng qua ledger.chuyen."}


def _whitelist_s5(node: ast.Constant, parent: dict) -> bool:
    v = node.value
    if v in (0, 1, 2, -1):
        return True
    # hằng CẤU TRÚC (không phải tham số kinh tế): 0.5 = làm tròn nhị phân / căn bậc hai
    # nửa năm / trung điểm xác suất; 100.0 = chuẩn hóa % (health, cổ phần)
    if v in (0.5, 100.0):
        return True
    # dung sai số học (float drift) — luồng lậu thật luôn ≥ đơn vị nguyên
    if isinstance(v, float) and abs(v) <= 1e-4:
        return True
    # ndigits của round(x, N)
    p = parent.get(node)
    if isinstance(p, ast.UnaryOp):
        p = parent.get(p)
    if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "round":
        if len(p.args) >= 2 and (p.args[1] is node
                                 or (isinstance(p.args[1], ast.UnaryOp)
                                     and p.args[1].operand is node)):
            return True
    # index / slice
    anc, child = parent.get(node), node
    for _ in range(6):
        if anc is None:
            break
        if isinstance(anc, ast.Slice):
            return True
        if isinstance(anc, ast.Subscript) and child is anc.slice:
            return True
        anc, child = parent.get(anc), anc
    return False


def kiem_s5() -> KetQua:
    """S5: AST-scan hằng số kinh tế trong engine ngoài config.

    Whitelist: EPSILON/round/index/0/1/2/0.5/100.0 + dòng có marker "s5:" trong
    comment (hằng cấu trúc có giải trình tại chỗ — sentinel, enum bậc ưu tiên...).
    """
    danh_sach: list[str] = []
    for f, tree in _ast_engine().items():
        dong_nguon = f.read_text(encoding="utf-8").splitlines()
        parent: dict = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[child] = node
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant)
                    and isinstance(node.value, int | float)
                    and not isinstance(node.value, bool)):
                continue
            if _whitelist_s5(node, parent):
                continue
            dong = dong_nguon[node.lineno - 1] if node.lineno <= len(dong_nguon) else ""
            if "s5:" in dong:  # marker giải trình tại chỗ
                continue
            danh_sach.append(f"{f.relative_to(REPO)}:{node.lineno}={node.value}")
    if danh_sach:
        return {"muc": "S5", "ket_luan": "fail",
                "bang_chung": f"{len(danh_sach)} hằng số ngoài whitelist (check.md đòi danh sách "
                              f"RỖNG — dồn về config/*.yaml): {'; '.join(danh_sach[:15])}"
                              + (f" (+{len(danh_sach) - 15} nữa)" if len(danh_sach) > 15 else "")}
    return {"muc": "S5", "ket_luan": "pass",
            "bang_chung": "AST-scan engine/: 0 hằng số kinh tế ngoài whitelist."}


# danh mục RNG được phép — MỞ RỘNG theo gói realism (đã ghi DECISIONS.md ở lần audit)
RNG_CHO_PHEP = {
    "thoi_tiet": "thời tiết", "khoi_tao": "khởi tạo t0",
    "bang_rao": "tie-break bảng rao", "cho": "tie-break chợ",
    "trigger_rao": "tie-break trigger", "dot_bien": "đột biến persona",
    "blueprint": "rút blueprint", "nghien_cuu": "rút blueprint",
    "tin_don": "nhiễu tin đồn", "nhin_hx": "nhiễu ước lượng hàng xóm",
    "nhieu": "nhiễu tham số intents", "sinh_con": "sinh-tử", "tu_vong": "sinh-tử",
    "nhan_khau": "sinh-tử", "chan_nuoi": "chăn nuôi", "xa_hoi": "xác suất trộm",
    "menu_xao": "xáo menu prompt", "batch_xao": "xáo thứ tự agent trong batch (tie-break)",
    "rao_vat": "lấy mẫu tin đồn chợ (nhiễu tin đồn)",
    "dich_benh": "cú sốc dịch bệnh theo scenario",
}


def kiem_s6() -> KetQua:
    """S6: liệt kê mọi điểm RNG, đối chiếu danh mục cho phép (đã mở rộng)."""
    files = [*_cac_file_engine(), MINDS_DIR / "prompts.py", MINDS_DIR / "orchestrator.py",
             MINDS_DIR / "triggers.py"]
    hits = _quet_regex([f for f in files if f.exists()], r"rng\.get\(\s*f?['\"]([^'\"]+)['\"]")
    la: list[str] = []
    diem: list[str] = []
    rx = re.compile(r"rng\.get\(\s*f?['\"]([^'\"]+)['\"]")
    for f, i, _c, line in hits:
        m = rx.search(line)
        ten = m.group(1) if m else "?"
        goc = re.split(r"[:{]", ten)[0]  # 'tin_don:{aid}' → 'tin_don'
        diem.append(f"{f.relative_to(REPO)}:{i}:{goc}")
        if goc not in RNG_CHO_PHEP:
            la.append(f"{f.relative_to(REPO)}:{i}: subsystem '{goc}' NGOÀI danh mục")
    if la:
        return {"muc": "S6", "ket_luan": "fail",
                "bang_chung": f"Điểm RNG lạ: {'; '.join(la)}. Toàn bộ điểm: {'; '.join(diem)}"}
    return {"muc": "S6", "ket_luan": "pass",
            "bang_chung": f"{len(diem)} điểm RNG, tất cả thuộc danh mục cho phép "
                          f"(thời tiết, tie-break, sinh-tử, chăn nuôi, trộm, blueprint, "
                          f"tin đồn, khởi tạo t0, xáo menu): {'; '.join(sorted(set(diem)))}"}


def kiem_s7() -> KetQua:
    """S7: không sự kiện hẹn giờ theo tick/năm tuyệt đối (chu kỳ % là tương đối, được phép)."""
    hits = _quet_regex(_cac_file_engine(), r"tick ?==|nam ?==|year ?==")
    tuyet_doi = [h for h in hits if "%" not in h[3]]
    if tuyet_doi:
        return {"muc": "S7", "ket_luan": "fail",
                "bang_chung": f"Điều kiện hẹn giờ tuyệt đối: {_mo_ta_hit(tuyet_doi)}"}
    bc = "0 sự kiện hẹn giờ tuyệt đối."
    if hits:
        bc += f" {len(hits)} hit đều là chu kỳ tương đối (chứa %): {_mo_ta_hit(hits, 4)}"
    return {"muc": "S7", "ket_luan": "pass", "bang_chung": bc}


def kiem_s8() -> KetQua:
    """S8: mau_khoi_dau trong world.yaml ≤ 2 mẫu trao đổi nguyên thủy."""
    import yaml
    try:
        data = yaml.safe_load((CONFIG_DIR / "world.yaml").read_text(encoding="utf-8")) or {}
    except OSError as e:
        return {"muc": "S8", "ket_luan": "loi", "bang_chung": f"Không đọc được world.yaml: {e}"}
    mau = (data.get("hop_dong") or {}).get("mau_khoi_dau") or []
    if len(mau) > 2:
        return {"muc": "S8", "ket_luan": "fail",
                "bang_chung": f"mau_khoi_dau có {len(mau)} mẫu (>2): {mau}"}
    nghi_van = [m for m in mau if isinstance(m, str)
                and re.search(r"lai|vay|the_chap|gui_tien|tin_dung", m)]
    if nghi_van:
        return {"muc": "S8", "ket_luan": "partial",
                "bang_chung": f"≤2 mẫu nhưng tên gợi tín dụng dựng sẵn: {nghi_van}"}
    return {"muc": "S8", "ket_luan": "pass",
            "bang_chung": f"mau_khoi_dau = {mau} ({len(mau)} mẫu ≤ 2, đều trao đổi nguyên thủy)."}


# ---------------------------------------------------------------- mục P (prompt)

TU_MOM_Y = ["nên", "khôn ngoan", "đầu tư", "quyền lực", "vốn liếng", "đừng", "hãy", "càng"]
TU_DINH_CHE = ["ngân hàng", "công ty", "bảo hiểm", "xưởng"]
RX_THOI_DAI = r"thời sơ khai|kỷ nguyên|thời đại"


def _la_dong_vi_du_json(line: str) -> bool:
    """Cụm nằm trong ví dụ JSON/schema thì không tính là lời khuyên."""
    return "{" in line or "}" in line or '":' in line


def _tim_tu(text: str, tu_list: list[str]) -> list[tuple[int, str, str]]:
    """Trả [(số_dòng, từ, dòng)] cho match NGOÀI ví dụ JSON (word-boundary unicode)."""
    ket: list[tuple[int, str, str]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        # Source scan dùng để bảo vệ prompt, nên comment Python không phải nội dung agent
        # nhận được và không được coi là vi phạm. Chuỗi prompt vẫn được render kiểm tra riêng.
        if line.lstrip().startswith("#") or _la_dong_vi_du_json(line):
            continue
        for tu in tu_list:
            if re.search(rf"(?<!\w){re.escape(tu)}(?!\w)", line, re.IGNORECASE):
                ket.append((i, tu, line.strip()))
    return ket


def _render_prompt_that() -> tuple[str, Any]:
    """Render prompt 1-to-1 thật cho 2 agent, không gọi provider."""
    from engine.config import load_config
    from engine.world import tao_the_gioi
    from minds.prompts import build_agent_prompt

    cfg = load_config()
    w = tao_the_gioi(cfg, 42)
    ids = sorted(w.agents)[:2]
    triggers = {aid: ["kiem_dinh"] for aid in ids}
    return "\n\n--- AGENT ---\n\n".join(build_agent_prompt(w, aid, triggers) for aid in ids), w


def kiem_p(run_dir: Path | None) -> list[KetQua]:
    """P1-P5: quét minds/prompts.py + bản render thật bằng danh sách từ mớm ý/định chế."""
    ket: list[KetQua] = []
    src = _doc(MINDS_DIR / "prompts.py")
    try:
        prompt, w = _render_prompt_that()
        loi_render = None
    except Exception as e:  # engine đang được sửa song song — báo lỗi, không crash
        prompt, w, loi_render = "", None, f"{type(e).__name__}: {e}"

    # P1 — danh mục định chế trong prompt (nguồn + bản render)
    hit_src = _tim_tu(src, TU_DINH_CHE)
    hit_ren = _tim_tu(prompt, TU_DINH_CHE)
    if hit_src or hit_ren:
        vd = [f"prompts.py:{i} ('{tu}'): {d[:100]}" for i, tu, d in hit_src[:6]]
        vd += [f"render:{i} ('{tu}'): {d[:100]}" for i, tu, d in hit_ren[:6]]
        ket.append({"muc": "P1", "ket_luan": "fail",
                    "bang_chung": "Danh mục định chế trong prompt (ngoài ví dụ JSON): "
                                  + "; ".join(vd)})
    else:
        ket.append({"muc": "P1", "ket_luan": "pass",
                    "bang_chung": "grep ngân hàng|công ty|bảo hiểm|xưởng ngoài ví dụ JSON → 0 "
                                  "(cả nguồn lẫn bản render seed 42)."})

    # P2 — mẫu hợp đồng rút từ hợp đồng đang lưu hành thật
    if loi_render:
        ket.append({"muc": "P2", "ket_luan": "loi", "bang_chung": f"Không render được: {loi_render}"})
    else:
        from minds.prompts import mau_hop_dong_luu_hanh
        top_k = int(w.cfg.get("minds.mau_hop_dong_trong_prompt_top_k"))
        mau_moi = mau_hop_dong_luu_hanh(w, top_k)
        phan1_ok = len(mau_moi) <= 2
        bc = f"Run mới tinh (seed 42, tick 0): {len(mau_moi)} mẫu (yêu cầu ≤2)."
        phan2_ok = True
        ck = _checkpoint_cuoi(run_dir) if run_dir else None
        if ck is not None:
            try:
                from engine.world import World
                w_ck = World.nap_checkpoint(ck)
                hd_hl = [h for h in w_ck.hop_dong.values() if h.trang_thai == "hieu_luc"]
                mau_ck = mau_hop_dong_luu_hanh(w_ck, top_k)
                phan2_ok = len(mau_ck) <= top_k and (not hd_hl or len(mau_ck) >= 1)
                bc += (f" Checkpoint {ck.name}: {len(hd_hl)} HĐ hiệu lực → {len(mau_ck)} mẫu "
                       f"(top-k={top_k}) rút từ mô-típ thật.")
            except Exception as e:
                bc += f" (Không nạp được checkpoint để đối chiếu năm giữa run: {e})"
        ket.append({"muc": "P2", "ket_luan": "pass" if (phan1_ok and phan2_ok) else "fail",
                    "bang_chung": bc})

    # P3 — không nhãn thời đại gán sẵn trong prompt render
    nguon_p3 = prompt if not loi_render else src
    hit_p3 = [(i, d) for i, d in enumerate(nguon_p3.splitlines(), start=1)
              if re.search(RX_THOI_DAI, d)]
    if hit_p3:
        ket.append({"muc": "P3", "ket_luan": "fail",
                    "bang_chung": "Nhãn thời đại gán sẵn: "
                                  + "; ".join(f"dòng {i}: {d.strip()[:100]}" for i, d in hit_p3[:5])})
    else:
        ket.append({"muc": "P3", "ket_luan": "pass",
                    "bang_chung": "Không có 'thời sơ khai/kỷ nguyên/thời đại' trong prompt render "
                                  "— mô tả thế giới sinh từ trạng thái."})

    # P4 — từ mớm ý chiến lược trong bản render thật (ngoài ví dụ JSON)
    if loi_render:
        ket.append({"muc": "P4", "ket_luan": "loi", "bang_chung": f"Không render được: {loi_render}"})
    else:
        hit_p4 = _tim_tu(prompt, TU_MOM_Y)
        if hit_p4:
            vd = "; ".join(f"render:{i} ('{tu}'): {d[:100]}" for i, tu, d in hit_p4[:8])
            ket.append({"muc": "P4", "ket_luan": "fail",
                        "bang_chung": f"{len(hit_p4)} câu mớm ý chiến lược trong prompt render "
                                      f"(seed 42): {vd}"})
        else:
            ket.append({"muc": "P4", "ket_luan": "pass",
                        "bang_chung": "Prompt render seed 42 không chứa từ mớm ý "
                                      "(nên/khôn ngoan/đầu tư/quyền lực/vốn liếng/đừng/hãy/càng) "
                                      "ngoài ví dụ JSON."})

    # P5 — menu xáo theo seed mỗi call (chống thiên vị vị trí)
    if re.search(r"menu_xao|shuffle|permutation", src):
        ket.append({"muc": "P5", "ket_luan": "pass",
                    "bang_chung": "prompts.py có cơ chế xáo menu theo seed (menu_xao/shuffle)."})
    else:
        ket.append({"muc": "P5", "ket_luan": "fail",
                    "bang_chung": "prompts.py không xáo thứ tự nguyên tố trong menu theo seed "
                                  "(grep menu_xao|shuffle|permutation → 0) — thiên vị vị trí."})
    return ket


# ---------------------------------------------------------------- mục C (hướng dẫn)

HUONG_DAN_C = """[C] PHẢN CHỨNG COUNTERFACTUAL — đã có runner không sửa config gốc.
  C1–C4 (rulebot, không gọi LLM thật):
     python -m tools.counterfactual --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  Kiểm toàn pipeline mock cục bộ (không gọi provider):
     python -m tools.counterfactual --mode mock --suite baseline c1_no_contract_seeds c2_permute_personas c3_no_parameter_noise c4_adverse_weather --seeds 41 42 43 --ticks 600
  C5 so policy cùng seed dùng tools.compare sau khi chạy rulebot/mock cùng horizon.
  Không overwrite run cũ: dùng --prefix mới cho mỗi ensemble."""


# ---------------------------------------------------------------- mục D (log run)


def _checkpoint_cuoi(run_dir: Path | None) -> Path | None:
    if run_dir is None:
        return None
    cks = sorted((run_dir / "checkpoints").glob("checkpoint_*.pkl"))
    return cks[-1] if cks else None


def kiem_d1(run_dir: Path) -> KetQua:
    """D1: fallback_rate từ llm_calls.sqlite (+ run_meta), ngưỡng theo mode."""
    db = run_dir / "llm_calls.sqlite"
    if not db.exists():
        return {"muc": "D1", "ket_luan": "khong_du_du_lieu",
                "bang_chung": f"Không có {db.name} trong run."}
    meta = {}
    mp = run_dir / "run_meta.json"
    if mp.exists():
        meta = json.loads(mp.read_text(encoding="utf-8"))
    nguong = 0.05 if meta.get("mode", "mock") == "mock" else 0.10
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT COALESCE(model,'?'), COUNT(*), COALESCE(SUM(fallback),0), "
            "COALESCE(SUM(batch_size),0) FROM llm_calls GROUP BY model"
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return {"muc": "D1", "ket_luan": "khong_du_du_lieu", "bang_chung": "llm_calls rỗng."}
    xau, chi_tiet = [], []
    for model, n_call, n_fb, n_batch in rows:
        rate = n_fb / max(1, n_batch or n_call)
        chi_tiet.append(f"{model}: {n_fb}/{n_batch or n_call} = {rate:.2%}")
        if rate >= nguong:
            xau.append(model)
    bc = (f"mode={meta.get('mode', '?')}, ngưỡng {nguong:.0%}; theo model: "
          + "; ".join(chi_tiet))
    if "fallback_rate" in meta:
        bc += f". run_meta: fallback_rate={meta['fallback_rate']}"
    return {"muc": "D1", "ket_luan": "fail" if xau else "pass", "bang_chung": bc}


def kiem_d3() -> KetQua:
    """D3: heterogeneity trong batch vẫn xanh trên HEAD hiện tại (chạy pytest)."""
    cmd = [sys.executable, "-m", "pytest", "tests/test_batch_heterogeneity.py", "-q"]
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"muc": "D3", "ket_luan": "loi", "bang_chung": f"Không chạy được pytest: {e}"}
    duoi = (r.stdout or "").strip().splitlines()[-1:] or ["(không output)"]
    return {"muc": "D3", "ket_luan": "pass" if r.returncode == 0 else "fail",
            "bang_chung": f"pytest tests/test_batch_heterogeneity.py -q → {duoi[0]}"}


def kiem_d4(run_dir: Path) -> KetQua:
    """D4: đọc unrecognized_intents.jsonl, phân loại đếm; ≥5% một loại → phát hiện thiết kế."""
    f = run_dir / "unrecognized_intents.jsonl"
    if not f.exists():
        return {"muc": "D4", "ket_luan": "pass",
                "bang_chung": "Không có unrecognized_intents.jsonl (0 intent lạ)."}
    dem: dict[str, int] = {}
    tong = 0
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        tong += 1
        loai = str(e.get("intent", "?"))
        dem[loai] = dem.get(loai, 0) + 1
    # Ưu tiên log append-only: run resume có thể gồm nhiều process, còn run_meta chỉ
    # mô tả process cuối. ``batch_size`` là số agent được hỏi trên từng call.
    mau_so = None
    db = run_dir / "llm_calls.sqlite"
    if db.exists():
        con = sqlite3.connect(db)
        try:
            mau_so = con.execute(
                "SELECT COALESCE(SUM(batch_size),0) FROM llm_calls").fetchone()[0]
        finally:
            con.close()
    if not mau_so:
        mp = run_dir / "run_meta.json"
        if mp.exists():
            meta = json.loads(mp.read_text(encoding="utf-8"))
            mau_so = meta.get("so_luot_nghi_phien") or meta.get("so_luot_nghi")
    if not mau_so:
        return {"muc": "D4", "ket_luan": "khong_du_du_lieu",
                "bang_chung": f"{tong} dòng intent lạ nhưng không biết tổng số quyết định."}
    top = sorted(dem.items(), key=lambda kv: -kv[1])[:5]
    vuot = [(k, v) for k, v in dem.items() if v / mau_so >= 0.05]
    bc = (f"{tong}/{mau_so} = {tong / mau_so:.2%} quyết định có intent lạ; "
          f"top loại: {['%s×%d' % kv for kv in top]}")
    if vuot:
        return {"muc": "D4", "ket_luan": "fail",
                "bang_chung": bc + f". PHÁT HIỆN THIẾT KẾ: loại ≥5%: {vuot} — văn phạm có thể "
                                   f"thiếu một nguyên tố phổ quát (đề xuất vào DECISIONS.md, "
                                   f"chỉ thêm GIỮA các run)."}
    return {"muc": "D4", "ket_luan": "pass", "bang_chung": bc + ". Không loại nào ≥5%."}


# ---------------------------------------------------------------- mục E (nổi lên)


def _doc_metrics(run_dir: Path) -> list[dict]:
    f = run_dir / "metrics.jsonl"
    if not f.exists():
        return []
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]


def _doc_events(run_dir: Path, loai_can: set[str]) -> list[dict]:
    f = run_dir / "events.jsonl"
    if not f.exists():
        return []
    ket = []
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("loai") in loai_can:
                ket.append(e)
    return ket


KHONG_MA_HOA = ("Quy luật này KHÔNG được mã hóa trong engine: engine/metrics.py chỉ ĐO gini; "
                "giá duy nhất từ khớp lệnh cung–cầu (engine/market.py) và sealed-bid đất; "
                "không cơ chế phân phối/tái phân phối hay hành vi theo giai cấp nào trong engine/.")


def kiem_e(run_dir: Path) -> list[KetQua]:
    """E1, E4, E6, E7 — chỉ báo cáo khớp/lệch kèm số liệu (quy tắc sắt check.md mục 4)."""
    import numpy as np
    ket: list[KetQua] = []
    ck_path = _checkpoint_cuoi(run_dir)
    w = None
    if ck_path is not None:
        try:
            from engine.world import World
            w = World.nap_checkpoint(ck_path)
        except Exception as e:
            ket.append({"muc": "E?", "ket_luan": "loi",
                        "bang_chung": f"Không nạp được checkpoint {ck_path.name}: {e}"})

    # E1 — phân phối của cải lệch phải, đuôi Pareto (Hill α trên top 20%)
    if w is None:
        ket.append({"muc": "E1", "ket_luan": "khong_du_du_lieu",
                    "bang_chung": "Không có checkpoint để tính của cải."})
    else:
        try:
            from engine.entities import tai_san_quy_thoc
            tt = w.cfg.get("nhan_khau.tuoi_truong_thanh")
            cua_cai = sorted(
                tai_san_quy_thoc(w, a.id)
                for a in w.agents.values() if a.con_song and a.truong_thanh(tt)
            )
            n = len(cua_cai)
            if n < 10:
                ket.append({"muc": "E1", "ket_luan": "khong_du_du_lieu",
                            "bang_chung": f"Chỉ {n} người lớn còn sống."})
            else:
                arr = np.asarray(cua_cai, dtype=float)
                duoi = arr[int(0.8 * n):]
                xmin = max(duoi.min(), 1e-9)
                logs = np.log(np.maximum(duoi, xmin) / xmin)
                alpha = 1.0 + len(duoi) / max(logs.sum(), 1e-9)
                lech_phai = arr.mean() > np.median(arr)
                top20 = duoi.sum() / max(arr.sum(), 1e-9)
                kl = "khop" if (lech_phai and 1.0 < alpha < 6.0) else "lech"
                ket.append({"muc": "E1", "ket_luan": kl,
                            "bang_chung": f"n={n} người lớn (tick {w.tick}); mean="
                                          f"{arr.mean():.0f} > median={np.median(arr):.0f}: "
                                          f"{'lệch phải' if lech_phai else 'KHÔNG lệch phải'}; "
                                          f"top 20% giữ {top20:.1%}; Hill α={alpha:.2f} "
                                          f"(n đuôi={len(duoi)}). {KHONG_MA_HOA}"})
        except Exception as e:
            ket.append({"muc": "E1", "ket_luan": "loi", "bang_chung": f"{type(e).__name__}: {e}"})

    # E4 — Malthus: thóc/người nghịch chiều dân số trên đoạn đất công cạn
    metrics = _doc_metrics(run_dir)
    if not metrics or w is None:
        ket.append({"muc": "E4", "ket_luan": "khong_du_du_lieu",
                    "bang_chung": "Thiếu metrics.jsonl hoặc checkpoint."})
    else:
        tong_ruong = sum(1 for p in w.parcels.values() if p.loai == "ruong")
        nguong_can = max(2.0, 0.05 * tong_ruong)
        doan = [m for m in metrics
                if tong_ruong - m.get("dat_tu_huu", 0) <= nguong_can and m.get("dan_so", 0) > 0]
        ghi_chu = f"đoạn đất công cạn (còn ≤{nguong_can:.0f}/{tong_ruong} thửa)"
        if len(doan) < 10:
            doan = metrics[len(metrics) // 2:]
            ghi_chu = "đất công chưa cạn — dùng nửa sau của run (tham khảo)"
        if len(doan) < 10:
            ket.append({"muc": "E4", "ket_luan": "khong_du_du_lieu",
                        "bang_chung": f"Chỉ {len(doan)} điểm dữ liệu."})
        else:
            ds = np.asarray([m["dan_so"] for m in doan], dtype=float)
            tp = np.asarray([m["thoc_moi_nguoi"] for m in doan], dtype=float)
            r = float(np.corrcoef(ds, tp)[0, 1]) if ds.std() > 0 and tp.std() > 0 else 0.0
            kl = "khop" if r < 0 else "lech"
            ket.append({"muc": "E4", "ket_luan": kl,
                        "bang_chung": f"corr(dân số, thóc/người) = {r:+.3f} trên {len(doan)} tick "
                                      f"({ghi_chu}) — {'nghịch chiều Malthus' if r < 0 else 'chưa nghịch chiều'}. "
                                      f"Quy luật không được mã hóa: engine/demography.py chỉ có "
                                      f"sinh học vi mô (p_sinh × an ninh hộ × ý định), không "
                                      f"phương trình vĩ mô nào nối dân số với lương thực."})

    # E6 — phân phối quy mô gop_cong theo entity lệch phải
    ky_hd = _doc_events(run_dir, {"ky_hd"})
    dem_e: dict[str, int] = {}
    for e in ky_hd:
        if "gop_cong" not in (e.get("mo_tip") or ""):
            continue
        for ben in e.get("cac_ben", []):
            if isinstance(ben, str) and ben.startswith("E"):
                dem_e[ben] = dem_e.get(ben, 0) + 1
    if len(dem_e) < 5:
        ket.append({"muc": "E6", "ket_luan": "khong_du_du_lieu",
                    "bang_chung": f"Chỉ {len(dem_e)} entity từng ký HĐ gop_cong (<5)."})
    else:
        qm = np.asarray(sorted(dem_e.values()), dtype=float)
        kl = "khop" if qm.mean() > np.median(qm) else "lech"
        ket.append({"muc": "E6", "ket_luan": kl,
                    "bang_chung": f"{len(dem_e)} entity; số HĐ gop_cong/entity: mean={qm.mean():.1f}, "
                                  f"median={np.median(qm):.0f}, max={qm.max():.0f}, top1 chiếm "
                                  f"{qm.max() / qm.sum():.1%} — "
                                  f"{'lệch phải' if kl == 'khop' else 'không lệch phải'}. "
                                  f"Quy luật không được mã hóa: engine/entities.py không giới hạn "
                                  f"hay khuyến khích quy mô thuê mướn nào."})

    # E7 — giá đất vốn hóa địa tô: corr(giá, màu mỡ)
    if w is None:
        ket.append({"muc": "E7", "ket_luan": "khong_du_du_lieu", "bang_chung": "Thiếu checkpoint."})
    else:
        cap: list[tuple[float, float]] = []
        for e in _doc_events(run_dir, {"ban_dat", "niem_yet"}):
            p = w.parcels.get(e.get("thua", ""))
            if p is None or e.get("gia") is None:
                continue
            mau = p.mau_mo_goc if getattr(p, "mau_mo_goc", 0) > 0 else p.mau_mo
            cap.append((float(e["gia"]), float(mau)))
        if len(cap) < 8:
            ket.append({"muc": "E7", "ket_luan": "khong_du_du_lieu",
                        "bang_chung": f"Chỉ {len(cap)} giao dịch/niêm yết đất (<8)."})
        else:
            gia = np.asarray([c[0] for c in cap])
            mau = np.asarray([c[1] for c in cap])
            r = float(np.corrcoef(gia, mau)[0, 1]) if gia.std() > 0 and mau.std() > 0 else 0.0
            kl = "khop" if r > 0 else "lech"
            ket.append({"muc": "E7", "ket_luan": kl,
                        "bang_chung": f"corr(giá đất, màu mỡ gốc) = {r:+.3f} trên n={len(cap)} "
                                      f"(ban_dat + niem_yet) — giá đất "
                                      f"{'CÓ' if r > 0 else 'KHÔNG'} vốn hóa địa tô. "
                                      f"Quy luật không được mã hóa: engine/market.py bán đất bằng "
                                      f"sealed-bid first-price, engine không định giá thửa nào."})
    return ket


# ---------------------------------------------------------------- tổng hợp & CLI


def chay_kiem_dinh(muc: list[str], run_dir: Path | None = None) -> list[KetQua]:
    """Chạy các nhóm mục được chọn, trả danh sách kết quả có cấu trúc."""
    ket: list[KetQua] = []
    if "S" in muc:
        for ham in (kiem_s1, kiem_s2, kiem_s3, kiem_s4, kiem_s5, kiem_s6, kiem_s7, kiem_s8):
            try:
                ket.append(ham())
            except Exception as e:  # file đang được sửa song song — ghi nhận, không crash
                ket.append({"muc": ham.__name__.replace("kiem_", "").upper(),
                            "ket_luan": "loi", "bang_chung": f"{type(e).__name__}: {e}"})
    if "P" in muc:
        try:
            ket.extend(kiem_p(run_dir))
        except Exception as e:
            ket.append({"muc": "P?", "ket_luan": "loi", "bang_chung": f"{type(e).__name__}: {e}"})
    if "D" in muc:
        if run_dir is not None:
            ket.append(kiem_d1(run_dir))
        else:
            ket.append({"muc": "D1", "ket_luan": "khong_du_du_lieu",
                        "bang_chung": "Cần --run để đọc llm_calls.sqlite."})
        ket.append(kiem_d3())
        if run_dir is not None:
            ket.append(kiem_d4(run_dir))
        else:
            ket.append({"muc": "D4", "ket_luan": "khong_du_du_lieu",
                        "bang_chung": "Cần --run để đọc unrecognized_intents.jsonl."})
    if "E" in muc:
        if run_dir is not None:
            try:
                ket.extend(kiem_e(run_dir))
            except Exception as e:
                ket.append({"muc": "E?", "ket_luan": "loi",
                            "bang_chung": f"{type(e).__name__}: {e}"})
        else:
            ket.append({"muc": "E1-E7", "ket_luan": "khong_du_du_lieu",
                        "bang_chung": "Cần --run để tính hiện tượng nổi lên."})
    return ket


def diem_tu_phat(ket: list[KetQua]) -> tuple[float, int]:
    """% pass của các mục S+P+D (E chỉ báo cáo; C chưa chạy — in hướng dẫn)."""
    tinh = [k for k in ket if k["muc"][:1] in ("S", "P", "D")
            and k["ket_luan"] in ("pass", "partial", "fail", "loi")]
    if not tinh:
        return 0.0, 0
    diem = sum(1.0 if k["ket_luan"] == "pass" else 0.5 if k["ket_luan"] == "partial" else 0.0
               for k in tinh)
    return 100.0 * diem / len(tinh), len(tinh)


def viet_bao_cao(ket: list[KetQua], run_ten: str, muc: list[str]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    duong = REPORT_DIR / f"reality_check_{run_ten}.md"
    diem, n = diem_tu_phat(ket)
    dong = [f"# Reality check — {run_ten}", "",
            f"Mục kiểm: {','.join(muc)}. Điểm tự phát (S+P+D, {n} mục): **{diem:.0f}%**.",
            "C1-C5 chưa tự động — xem hướng dẫn cuối báo cáo. Mục E chỉ báo cáo, không nắn.",
            "", "| Mục | Kết luận | Bằng chứng |", "|---|---|---|"]
    for k in ket:
        bc = k["bang_chung"].replace("|", "\\|").replace("\n", " ")
        dong.append(f"| {k['muc']} | {k['ket_luan']} | {bc} |")
    dong += ["", "```", HUONG_DAN_C, "```", ""]
    duong.write_text("\n".join(dong), encoding="utf-8")
    return duong


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Tự kiểm định tính thực tế theo check.md")
    ap.add_argument("--run", default=None,
                    help="data/runs/<ten_run> (bật các mục D/E cần log)")
    ap.add_argument("--muc", default="S,P,D,E", help="các nhóm mục, vd: S,P hoặc S,P,D,E")
    args = ap.parse_args(argv)

    run_dir: Path | None = None
    run_ten = "static"
    if args.run:
        run_dir = Path(args.run)
        if not run_dir.exists():
            run_dir = REPO / "data" / "runs" / args.run
        if not run_dir.exists():
            print(f"Không tìm thấy run: {args.run}")
            return 2
        run_ten = run_dir.name
    muc = [m.strip().upper() for m in args.muc.split(",") if m.strip()]

    ket = chay_kiem_dinh(muc, run_dir)
    rong = max(len(k["muc"]) for k in ket) if ket else 4
    for k in ket:
        print(f"[{k['ket_luan']:>18}] {k['muc']:<{rong}}  {k['bang_chung'][:160]}")
    diem, n = diem_tu_phat(ket)
    print(f"\nĐiểm tự phát (S+P+D, {n} mục): {diem:.0f}%")
    print(HUONG_DAN_C)
    bao_cao = viet_bao_cao(ket, run_ten, muc)
    print(f"\nĐã ghi báo cáo: {bao_cao.relative_to(REPO)}")

    gate_fail = [k["muc"] for k in ket
                 if k["muc"][:1] in ("S", "P") and k["ket_luan"] == KET_LUAN_GATE_FAIL]
    if gate_fail:
        print(f"GATE: mục S/P fail → phải sửa trước khi qua gate (check.md mục 6): {gate_fail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
