"""tools/verify_research_run — kiểm toán tái lập một run nghiên cứu (chỉ đọc).

Tool này KHÔNG chạy provider/LLM thật, KHÔNG chạm mạng và KHÔNG sửa run (kể cả run hỏng —
artifact giữ nguyên từng byte). Nó xác nhận một run trong ``data/runs/<name>/`` đủ bằng
chứng để tái lập:

  1. manifest schema + trường bắt buộc;
  2. đồng nhất giữa manifest và run_meta (name/seed/config_sha256/world_hash);
  3. config digest tái dựng từ overlay của manifest khớp digest đã ghi;
  4. scenario files chưa trôi (sha256 khớp) nếu run gắn scenario;
  5. metrics.jsonl liên tục tới tick cuối; events.jsonl tồn tại;
  5b. **journal_continuity** (ADR 0006 §C.4, HARD): event ``seq`` duy nhất/liên tục, không
      tick lùi trong thứ tự file, transcript ``call_id`` duy nhất, metric tick duy nhất —
      tính TỪ NỘI DUNG FILE nên bắt được cả artifact legacy không có manifest;
  6. replay:
     - rulebot / mock-không-transcript → seed replay → world-hash TRÙNG (HARD, như cũ);
     - **real** và mock-có-transcript → ``tools.replay.replay_from_transcript`` (HARD).
       Nhánh SKIP cũ (`mode not in (rulebot, mock)` ⇒ ok=None ⇒ ``failed()`` bỏ qua) đã bị
       **XÓA HẲN**: nó là một cổng phát false-green trên artifact không replay được.

``artifact_status`` ∈ {replay_verified, diagnostic_only_unreplayable, pending_verification,
skipped_version_mismatch} được **tính tại chỗ**, KHÔNG ghi vào run dir.

**Exit code (A-03 — F-06 tái phát ở chỗ khác).** Trước đây exit code nghe theo ``Ket.failed()``
(chỉ FAIL khi có hard-check ``ok is False``) trong khi ``artifact_status`` được tính RIÊNG ⇒ hai
kết luận BẤT ĐỒNG và exit code nghe theo cái sai: ``--quick`` (mọi replay ⇒ SKIP ⇒ ``ok=None``)
in "ĐỦ BẰNG CHỨNG ✅" + exit 0, và mock có ``p_malformed>0`` in ``diagnostic_only_unreplayable``
+ "ĐỦ BẰNG CHỨNG ✅" + exit 0 trên artifact mà transcript replay ra thế giới KHÁC. Nay chỉ còn
MỘT nguồn sự thật — ``artifact_status``:

  * ``0``  ⟺ ``artifact_status == replay_verified`` **và** không hard-check nào FAIL;
  * ``2``  ⟺ ``pending_verification`` — CHƯA CHỨNG MINH (``--quick``, overlay thiếu). Không phải
    bằng chứng, cũng không phải kết tội. ``--quick`` là tiện ích dev, **không** phát tín hiệu xanh;
  * ``1``  ⟺ thiếu bằng chứng (hard-check FAIL / ``diagnostic_only_unreplayable`` /
    ``skipped_version_mismatch``).

Ví dụ:

  python -m tools.verify_research_run rb300
  python -m tools.verify_research_run rb300 --quick   # bỏ replay ⇒ exit 2 (pending)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from engine.config import load_config
from engine.journal import RunJournals, kiem_lien_tuc
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi
from tools.experiments import ROOT, sha256_file

DATA_DIR = ROOT / "data" / "runs"

# Nhãn artifact — tính on-the-fly, KHÔNG BAO GIỜ ghi vào data/runs/<run>/
REPLAY_VERIFIED = "replay_verified"
DIAGNOSTIC_ONLY = "diagnostic_only_unreplayable"
PENDING = "pending_verification"
VERSION_MISMATCH = "skipped_version_mismatch"

# Exit code: 0 = replay_verified; 2 = chưa chứng minh (pending); 1 = thiếu bằng chứng.
EXIT_OK = 0
EXIT_THIEU_BANG_CHUNG = 1
EXIT_CHUA_CHUNG_MINH = 2


class Ket:
    """Gom kết quả kiểm tra; mỗi mục là (tên, ok, chi_tiet, hard).

    `hard=True` (mặc định): sai → toàn cục FAIL (evidence thiếu). `hard=False`: sai chỉ là
    WARN (ví dụ config base trôi sau run — replay hash mới là bằng chứng tái lập quyết định).

    ``failed()`` chỉ nói "có hard-check nào sai không"; nó **KHÔNG** phải kết luận của tool.
    Kết luận là ``du_bang_chung()``/``ma_thoat()`` — chúng đọc ``artifact_status``, nên một
    check SKIP (``ok=None``) không bao giờ còn được phép nuốt một kết luận (F-06/A-03).
    """

    def __init__(self) -> None:
        self.items: list[tuple[str, bool | None, str, bool]] = []
        # nhãn artifact tính tại chỗ; mặc định "chưa đủ bằng chứng" chứ không phải "xanh"
        self.artifact_status: str = PENDING

    def add(self, name: str, ok: bool | None, detail: str = "", hard: bool = True) -> None:
        self.items.append((name, ok, detail, hard))

    def failed(self) -> bool:
        return any(ok is False and hard for _, ok, _, hard in self.items)

    def du_bang_chung(self) -> bool:
        """ĐỦ BẰNG CHỨNG ⟺ artifact đã replay được VÀ không hard-check nào FAIL."""
        return self.artifact_status == REPLAY_VERIFIED and not self.failed()

    def ma_thoat(self) -> int:
        if self.du_bang_chung():
            return EXIT_OK
        if not self.failed() and self.artifact_status == PENDING:
            return EXIT_CHUA_CHUNG_MINH  # --quick / overlay thiếu: chưa chạy cổng replay
        return EXIT_THIEU_BANG_CHUNG

    def lay(self, name: str) -> tuple[bool | None, str, bool] | None:
        for n, ok, detail, hard in self.items:
            if n == name:
                return ok, detail, hard
        return None

    def render(self) -> str:
        lines = []
        for name, ok, detail, hard in self.items:
            if ok is True:
                mark = "PASS"
            elif ok is None:
                mark = "SKIP"
            else:
                mark = "FAIL" if hard else "WARN"
            lines.append(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
        return "\n".join(lines)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_metrics(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _reconstruct_config(manifest: dict[str, Any], ket: Ket):
    """Dựng lại config từ overlay ghi trong manifest (đã gồm scenario overlay ở index 0)."""
    repro = manifest.get("reproducibility", {})
    overlay_items = repro.get("config_overlays", [])
    overlays: list[Path] = []
    missing: list[str] = []
    drifted: list[str] = []
    for item in overlay_items:
        p = Path(item["path"])
        if not p.exists():
            missing.append(str(p))
            continue
        if item.get("sha256") and sha256_file(p) != item["sha256"]:
            drifted.append(str(p))
        overlays.append(p)
    if missing:
        ket.add("overlay_files_present", False, f"thiếu: {missing}", hard=False)
    if drifted:
        ket.add("overlay_files_unchanged", False, f"sha256 lệch: {drifted}", hard=False)
    cfg = load_config(overlays=overlays)
    return cfg, bool(missing)


def verify_run(run_name: str, quick: bool = False) -> Ket:
    ket = Ket()
    run_dir = DATA_DIR / run_name
    if not run_dir.is_dir():
        ket.add("run_dir_exists", False, str(run_dir))
        return ket

    # 1. manifest schema + trường bắt buộc
    manifest_path = run_dir / "experiment_manifest.json"
    if not manifest_path.exists():
        ket.add("manifest_present", False, "thiếu experiment_manifest.json")
        return ket
    manifest = _load_json(manifest_path)
    schema_ok = manifest.get("schema_version") is not None
    run_block = manifest.get("run", {})
    repro = manifest.get("reproducibility", {})
    required_run = {"name", "mode", "seed", "ticks_requested"}
    missing_run = sorted(required_run - set(run_block))
    manifest_ok = (schema_ok and not missing_run
                   and repro.get("config_sha256") is not None)
    ket.add("manifest_schema", manifest_ok,
            f"schema={manifest.get('schema_version')} missing_run={missing_run}")

    # 2. run_meta + đồng nhất manifest↔meta
    meta_path = run_dir / "run_meta.json"
    if not meta_path.exists():
        ket.add("run_meta_present", False, "thiếu run_meta.json")
        return ket
    meta = _load_json(meta_path)
    same_name = meta.get("run_name") == run_block.get("name") == run_name
    same_seed = meta.get("seed") == run_block.get("seed")
    same_digest = (meta.get("config_sha256") == repro.get("config_sha256"))
    ket.add("manifest_meta_consistent", bool(same_name and same_seed and same_digest),
            f"name={same_name} seed={same_seed} digest={same_digest}")
    outcome = manifest.get("outcome", {})
    if outcome:
        hash_ok = outcome.get("world_hash") == meta.get("world_hash")
        ket.add("outcome_hash_matches_meta", bool(hash_ok),
                f"{outcome.get('world_hash', '')[:12]} vs {meta.get('world_hash', '')[:12]}")

    # 3. config digest tái dựng
    cfg, overlays_missing = _reconstruct_config(manifest, ket)
    if not overlays_missing:
        digest_ok = cfg.digest() == repro.get("config_sha256")
        # SOFT: base config có thể trôi ở khóa không ảnh hưởng run này; replay hash mới là
        # bằng chứng tái lập quyết định. Digest lệch = cảnh báo provenance, không phải FAIL.
        ket.add("config_digest_reproduced", bool(digest_ok),
                f"{cfg.digest()[:12]} vs {str(repro.get('config_sha256'))[:12]}"
                + ("" if digest_ok else " (base config trôi sau run — xem replay_world_hash)"),
                hard=False)
    else:
        ket.add("config_digest_reproduced", None, "overlay thiếu — không tái dựng được digest")

    # Calendar phải được manifest ghi rõ khi run có seasonal overlay; thiếu ở manifest cũ
    # chỉ là metadata legacy (soft), còn manifest mới mà lệch config thì không thể diễn giải
    # horizon/tuổi/hazard theo năm một cách kiểm toán được.
    calendar = repro.get("calendar")
    if calendar is None:
        ket.add("calendar_consistent", None, "manifest legacy chưa ghi calendar", hard=False)
    elif overlays_missing:
        ket.add("calendar_consistent", None, "overlay thiếu — không kiểm calendar", hard=False)
    else:
        thang = float(cfg.get("thoi_gian.thang_moi_tick"))
        so_tick = int(round(12.0 / thang))
        ok_calendar = (
            float(calendar.get("months_per_tick", -1)) == thang
            and int(calendar.get("ticks_per_year", -1)) == so_tick
            and calendar.get("seasons") == cfg.raw().get("thoi_gian", {}).get("lich_mua")
        )
        ket.add("calendar_consistent", ok_calendar,
                f"months/ticks/seasons={thang}/{so_tick}/{cfg.raw().get('thoi_gian', {}).get('lich_mua')}")

    # 4. scenario files chưa trôi
    scenario = repro.get("scenario")
    if scenario:
        recorded = repro.get("scenario_files_sha256", {})
        drift = []
        for rel, digest in recorded.items():
            p = ROOT / rel
            if not p.exists() or sha256_file(p) != digest:
                drift.append(rel)
        ket.add("scenario_files_unchanged", not drift,
                f"trôi: {drift}" if drift else f"{len(recorded)} file khớp", hard=False)

    # 5. metrics/events consistency
    metrics_path = run_dir / "metrics.jsonl"
    events_path = run_dir / "events.jsonl"
    tick_cuoi = int(meta.get("tick_cuoi", 0))
    if metrics_path.exists():
        rows = _read_metrics(metrics_path)
        ticks = [int(r["tick"]) for r in rows if "tick" in r]
        contiguous = ticks == list(range(1, len(ticks) + 1))
        last_ok = bool(ticks) and ticks[-1] == tick_cuoi
        ket.add("metrics_contiguous_to_final", bool(contiguous and last_ok),
                f"n={len(ticks)} last={ticks[-1] if ticks else None} tick_cuoi={tick_cuoi}")
    else:
        ket.add("metrics_present", False, "thiếu metrics.jsonl")
    ket.add("events_present", events_path.exists(),
            "" if events_path.exists() else "thiếu events.jsonl")

    # 5b. journal continuity (HARD) — tính TỪ NỘI DUNG FILE, không cần manifest, nên bắt được
    # cả artifact legacy: event seq/tick, transcript call_id, llm_calls call_id, metric tick.
    jc = kiem_lien_tuc(run_dir)
    jm = RunJournals.doc_manifest(run_dir)
    ket.add("journal_continuity", bool(jc["ok"]),
            "; ".join(jc["loi"]) if jc["loi"] else
            (f"events={jc.get('events_records', '-')} "
             f"transcript={jc.get('transcript_records', '-')} "
             f"metrics={jc.get('metrics_records', '-')} "
             f"call_burned={jc.get('llm_calls_burned', '-')} "
             f"call_effective={jc.get('llm_calls_effective', '-')}"))
    ket.add("journal_manifest_present", jm is not None,
            "" if jm is not None else "run legacy (trước ADR 0006 §C) — không resume được",
            hard=False)
    for cb in jc.get("canh_bao", []):
        if "trùng khít" in cb:
            ket.add("events_dup_lines_legacy", False, cb, hard=False)
    if jm is not None and not jm.replay_complete:
        ket.add("journal_replay_complete", False,
                f"--recover-journal đã quarantine journal (segment {jm.segment_id}); "
                "prefix transcript đã mất ⇒ replay-from-t0 BẤT KHẢ THI")
    # Sổ chi phí: KHÔNG row llm_calls nào bị DELETE (ADR 0006 §C.1).
    # A-11: check cũ (`call_burned >= call_effective`) là TAUTOLOGY — burned=COUNT(*),
    # effective=COUNT(superseded=0) ⇒ luôn đúng theo định nghĩa, không bao giờ fail được, mà
    # vẫn được in ra như bằng chứng ở mọi block PASS. Thay bằng identity THẬT, có đối ứng:
    #   (1) burned == effective + superseded          — phân hoạch kín;
    #   (2) superseded == Σ journal_recovery.rows_superseded — sổ recovery là bên ĐỐI ỨNG:
    #       mỗi lần resume tuyên bố nó vừa đánh dấu bao nhiêu row; cột `superseded` phải
    #       khớp con số đã tuyên bố;
    #   (3) MAX(call_id) == burned — call_id là AUTOINCREMENT (minds/gateway.py:57) nên
    #       max == count ⟺ CHƯA từng có row nào bị xóa. Đây là check duy nhất trong ba cái
    #       thực sự bắt được hành vi "xóa row cho chi phí đẹp".
    burned, eff = jc.get("llm_calls_burned"), jc.get("llm_calls_effective")
    sup, rec = jc.get("llm_calls_superseded"), jc.get("llm_recovery_rows")
    mx = jc.get("llm_calls_max_id")
    if burned is not None and eff is not None and sup is not None:
        loi = []
        if burned != eff + sup:
            loi.append(f"burned({burned}) ≠ effective({eff}) + superseded({sup})")
        if rec is not None and sup != rec:
            loi.append(f"superseded({sup}) ≠ Σ journal_recovery.rows_superseded({rec})")
        if mx is not None and mx != burned:
            loi.append(f"MAX(call_id)={mx} ≠ COUNT(*)={burned} ⇒ ĐÃ CÓ ROW BỊ XÓA")
        ket.add("cost_accounting_identity", not loi,
                "; ".join(loi) if loi else
                f"call_burned={burned} = call_effective={eff} + superseded={sup}; "
                f"Σrecovery={rec}; MAX(call_id)={mx}")

    # 6. replay — KHÔNG còn nhánh SKIP cho mode real (đó là cổng phát false-green: SKIP lưu
    # ok=None và Ket.failed() chỉ fail khi ok is False ⇒ in "ĐỦ BẰNG CHỨNG ✅" + exit 0).
    mode = meta.get("mode")
    co_transcript = (run_dir / "transcript.jsonl").exists()
    dung_transcript = co_transcript and mode in ("mock", "real")
    if mode == "real" and not co_transcript:
        ket.add("transcript_present", False,
                "run real BẮT BUỘC có transcript.jsonl (run.py luôn ghi) — artifact hỏng")

    if quick:
        ket.add("replay_world_hash", None, "bỏ qua (--quick)")
        if dung_transcript:
            ket.add("replay_from_transcript", None, "bỏ qua (--quick)")
    elif overlays_missing:
        ket.add("replay_world_hash", None, "overlay thiếu — không replay đúng config")
    else:
        if mode in ("rulebot", "mock"):
            _replay_seed(ket, cfg, meta, repro, mode, tick_cuoi, manifest)
        if dung_transcript:
            # A-03: carve-out cũ (`mock` + `p_malformed>0` ⇒ hard=False) đã bị BỎ. Nó tạo ra
            # đúng cái bất đồng của F-06: `replay_from_transcript` ok=False (WARN) nhưng
            # `artifact_status` = diagnostic_only ⇒ `failed()` False ⇒ exit 0 trên artifact mà
            # transcript replay ra thế giới KHÁC. Nay: CÓ transcript = CÓ tuyên bố
            # "transcript này tái dựng được run" ⇒ cổng cưỡng chế tuyên bố đó, mọi mode.
            #
            # Giới hạn của mock adversarial VẪN CÒN THẬT (đo lại 2026-07-13, xem
            # docs/reviews/P0.2-engine-surgeon.md §A-03): mock `p_malformed>0` cho
            # misses=0/unused=0 nhưng world_hash LỆCH ở seed 3 (PersonaBot nhắm thửa vào
            # `da_nham` dùng chung TRƯỚC khi text bị làm hỏng — side-effect ở thì SINH, nằm
            # ngoài transcript). Cách xử lý đúng không phải hạ cổng xuống WARN mà là: mock
            # muốn có bằng chứng transcript thì chạy `--p-malformed 0.0`; muốn adversarial thì
            # bỏ `--transcript` và dựa vào seed-replay (mock tất định từ seed).
            if not jc["ok"]:
                ket.add("replay_from_transcript", False,
                        "KHÔNG chạy — điều kiện tiên quyết journal_continuity FAIL "
                        f"({'; '.join(jc['loi'])}). Transcript chứa bản ghi của một quỹ đạo "
                        "đã bị vứt bỏ ⇒ không thể là bằng chứng replay.")
            else:
                from tools.replay import replay_from_transcript

                kq = replay_from_transcript(run_dir)
                ket.add("replay_from_transcript", kq.ok,
                        f"hash {str(kq.hash_replay)[:12]} vs {str(kq.hash_goc)[:12]} · "
                        f"{kq.total} call, {kq.misses} miss, {kq.unused} chưa dùng · "
                        f"identity {'khớp' if kq.identity_ok else 'LỆCH'}"
                        + (f" · {kq.reason}" if kq.reason else ""))
                if not kq.identity_ok:
                    ket.artifact_status = VERSION_MISMATCH
    ket.artifact_status = _tinh_nhan(ket, jc, jm, quick, dung_transcript)
    return ket


def _replay_seed(ket: Ket, cfg, meta: dict, repro: dict, mode: str, tick_cuoi: int,
                 manifest: dict | None = None) -> None:
    """Replay từ seed (rulebot/mock) — đồng thời chạy lại audit bảo toàn mỗi tick.

    Identity được kiểm TRƯỚC: một artifact chạy trên interface cũ hơn (vd trước khi
    `qua_song`/`rao_do`/`dong_thuyen` được nối dây) hợp lệ mà vẫn cho hash khác. Báo nó là
    ``skipped_version_mismatch`` chứ không phải một hash-FAIL trần — nếu không, người đọc sẽ
    kết luận nhầm rằng mô phỏng mất tất định.
    """
    from tools.replay import _kiem_identity

    if manifest is not None:
        identity_ok, detail = _kiem_identity(manifest, cfg)
        if not identity_ok:
            ket.artifact_status = VERSION_MISMATCH
            ket.add("replay_world_hash", False,
                    f"skipped_version_mismatch — code hiện tại khác manifest: {detail}. "
                    "Artifact này KHÔNG replay được bằng code này (KHÔNG phải bằng chứng mất "
                    "tất định).")
            return
    w = tao_the_gioi(cfg, int(meta["seed"]), events_path=None)
    if "permute_personas" in repro.get("treatments", []):
        from tools.experiments import permute_personas
        permute_personas(w)
    if mode == "rulebot":
        # Tái dựng policy Lớp-4 từ manifest (như replay.py) — run tạo bằng --policy khác
        # rulebot phải replay đúng world-hash, không hardcode rulebot.
        from minds.policies import tao_policy
        ten_policy = (repro.get("policy") or {}).get("name") or "rulebot"
        mind_fn = tao_policy(ten_policy)
    else:
        from minds.orchestrator import tao_mind_mock
        mind_fn = tao_mind_mock(w, fast=True, p_malformed=meta.get("p_malformed"))
    tong_thua = len(w.parcels)
    try:
        while w.tick < tick_cuoi:
            chay_mot_tick(w, mind_fn, tong_thua)
        h = w.world_hash()
        ket.add("replay_world_hash", h == meta.get("world_hash"),
                f"{h[:12]} vs {str(meta.get('world_hash'))[:12]} (audit xanh mỗi tick)")
    except Exception as exc:  # noqa: BLE001 — báo cáo mọi lỗi replay/audit
        ket.add("replay_world_hash", False, f"{type(exc).__name__}: {exc}")


def _tinh_nhan(ket: Ket, jc: dict, jm, quick: bool, dung_transcript: bool) -> str:
    """Nhãn artifact — tính TẠI CHỖ từ bằng chứng, KHÔNG ghi vào run dir (ADR 0006 §C.6).

    Thứ tự ưu tiên: nhãn bị ép (``--recover-journal``) > journal không liên tục (sự thật về
    chính artifact) > identity mismatch > kết quả replay > chưa verify."""
    if jm is not None and jm.artifact_status_forced:
        return jm.artifact_status_forced
    if jm is not None and not jm.replay_complete:
        return DIAGNOSTIC_ONLY
    if not jc["ok"]:
        return DIAGNOSTIC_ONLY
    if ket.artifact_status == VERSION_MISMATCH:
        return VERSION_MISMATCH
    if quick:
        return PENDING
    tr = ket.lay("replay_from_transcript")
    seed = ket.lay("replay_world_hash")
    if dung_transcript:
        if tr is None or tr[0] is None:
            return PENDING
        return REPLAY_VERIFIED if tr[0] else DIAGNOSTIC_ONLY
    if seed is None or seed[0] is None:
        return PENDING
    return REPLAY_VERIFIED if seed[0] else DIAGNOSTIC_ONLY


def _ket_luan(ket: Ket, quick: bool) -> str:
    """Một dòng kết luận — phải KHỚP với ``artifact_status`` và exit code (A-03)."""
    ma = ket.ma_thoat()
    if ma == EXIT_OK:
        return "KẾT QUẢ: ĐỦ BẰNG CHỨNG ✅ (replay_verified)"
    if ma == EXIT_CHUA_CHUNG_MINH:
        vi = " (--quick bỏ qua replay)" if quick else ""
        return (f"KẾT QUẢ: CHƯA CHỨNG MINH ⏸ ({ket.artifact_status}){vi} — cổng replay CHƯA "
                "chạy ⇒ đây KHÔNG phải bằng chứng tái lập. Chạy lại không có --quick.")
    return f"KẾT QUẢ: THIẾU BẰNG CHỨNG ❌ ({ket.artifact_status})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm toán tái lập một run nghiên cứu (chỉ đọc)")
    ap.add_argument("run_name")
    ap.add_argument("--quick", action="store_true",
                    help="bỏ replay (tiện ích dev) — artifact_status=pending_verification, "
                         "exit 2; KHÔNG BAO GIỜ phát tín hiệu 'đủ bằng chứng'")
    ap.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    args = ap.parse_args(argv)
    ket = verify_run(args.run_name, quick=args.quick)
    ma = ket.ma_thoat()
    if args.json:
        # F-07: `Ket.add` đẩy 4-tuple (name, ok, detail, hard); code cũ unpack 3 ⇒ --json
        # LUÔN ValueError ⇒ output máy-đọc-được của gate đã chết. Unpack đủ 4 + phát `hard`.
        # A-03: `ok` là KẾT LUẬN của tool (du_bang_chung), không phải `not failed()` — nếu
        # không, consumer máy đọc `ok=true` trên một artifact `pending`/`diagnostic_only`.
        print(json.dumps(
            {"run": args.run_name, "ok": ket.du_bang_chung(), "exit_code": ma,
             "artifact_status": ket.artifact_status,
             "hard_failures": [n for n, ok, _d, hard in ket.items if ok is False and hard],
             "checks": [{"name": n, "ok": ok, "detail": d, "hard": hard}
                        for n, ok, d, hard in ket.items]},
            ensure_ascii=False, indent=2))
    else:
        print(ket.render())
        print(f"artifact_status: {ket.artifact_status}")
        print(_ket_luan(ket, args.quick))
    return ma


if __name__ == "__main__":
    sys.exit(main())
