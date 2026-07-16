"""tools/replay — chạy lại run từ seed và so world-hash (điều luật #4).

  python -m tools.replay rb300 --verify
  python -m tools.replay real50 --from-transcript --verify   # replay real KHÔNG mạng

``replay_from_transcript`` là **implementation DUY NHẤT** của cổng replay-from-transcript;
``tools.verify_research_run`` IMPORT nó (không copy-paste) để gate và tool không thể trôi
khỏi nhau.

Cổng (ADR 0006 §C.4) — PASS ⟺ **tất cả**:
  ``misses == 0``  AND  ``unused (con_lai()) == 0``  AND  hash == manifest.outcome.world_hash
  AND identity khớp (``config_sha256``, ``prompt_template_hash``).

Identity mismatch ⇒ ``skipped_version_mismatch`` = **FAIL** (không im lặng PASS, cũng không
giả vờ FAIL nội dung): transcript khóa theo ``prompt_hash``, đổi prompt template ⇒ transcript
cũ KHÔNG replay được bằng code mới. Đó là sự thật cần nói ra, không phải lỗi nội dung.

KHÔNG MẠNG: ``minds.transcript.tao_mind_replay(mode="real")`` đóng client httpx của gateway
thật rồi thay provider bằng ``TranscriptProvider`` (``minds/transcript.py:120-151``) — không
key, không client sống, không call.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from engine.config import load_config
from engine.tick import chay_mot_tick
from engine.world import tao_the_gioi

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "runs"
ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ReplayResult:
    """Kết quả cổng replay-from-transcript. ``ok`` là điều kiện DUY NHẤT để PASS."""

    ok: bool
    hash_replay: str | None
    hash_goc: str | None
    hash_match: bool
    total: int
    misses: int
    unused: int
    identity_ok: bool
    identity_detail: dict[str, list] = field(default_factory=dict)
    ticks: int = 0
    reason: str = ""
    terminal_total: int = 0
    terminal_consumed: int = 0


def _nap_overlays(manifest: dict) -> list[Path]:
    """Overlay (gồm scenario) từ manifest để replay dùng đúng config đã ghép."""
    overlays: list[Path] = []
    for item in manifest.get("reproducibility", {}).get("config_overlays", []):
        p = Path(item["path"])
        if p.exists():
            overlays.append(p)
    return overlays


def prompt_template_hash_hien_tai() -> str | None:
    """Một nguồn sự thật với ``run.py`` (`tools.experiments.prompt_template_hash`): phủ CẢ
    ``minds/prompts.py`` lẫn ``minds/capabilities.py`` (thân hàm render sống ở file thứ hai)."""
    from tools.experiments import prompt_template_hash

    return prompt_template_hash()


def catalog_hash_hien_tai() -> str | None:
    """Hash NỘI DUNG KHAI BÁO của capability catalog (ADR 0006 §A.2), không phải hash file."""
    from minds.capabilities import catalog_hash

    return catalog_hash()


def runtime_source_identity_hien_tai() -> dict:
    """Exact versioned Python runtime inventory, shared with manifest creation."""
    from tools.experiments import runtime_source_identity

    return runtime_source_identity()


def _kiem_identity(manifest: dict, cfg) -> tuple[bool, dict[str, list]]:
    """So identity của CODE/CONFIG hiện tại với manifest. ``None`` ở manifest (run legacy)
    ⇒ không kết luận được ⇒ coi là khớp (không bịa bằng chứng), nhưng ghi vào detail.

    ``capability_catalog_hash`` là mảnh còn thiếu để "prompt identity" thành một phép so hash:
    một run cũ chạy khi engine chưa nối dây `qua_song`/`rao_do`/`dong_thuyen` quảng cáo một tập
    action KHÁC, nên transcript của nó không thể là bằng chứng replay cho code hôm nay. Không có
    trường này, hash lệch trông như "mô phỏng mất tất định" thay vì "artifact cũ hơn interface".
    """
    repro = manifest.get("reproducibility", {})
    hien_tai = {
        "config_sha256": cfg.digest(),
        "prompt_template_hash": prompt_template_hash_hien_tai(),
        "capability_catalog_hash": catalog_hash_hien_tai(),
        "runtime_source_identity": runtime_source_identity_hien_tai(),
    }
    detail: dict[str, list] = {}
    ok = True
    for truong, gia_tri in hien_tai.items():
        cu = repro.get(truong)
        detail[truong] = [cu, gia_tri]
        # runtime_source_identity is mandatory for every artifact created under the v2
        # contract.  Its absence is unknown executable law, not legacy compatibility.
        if truong == "runtime_source_identity" and (cu is None or gia_tri is None):
            ok = False
        elif cu is not None and gia_tri is not None and cu != gia_tri:
            ok = False
    return ok, detail


def replay_from_transcript(run_dir: Path) -> ReplayResult:
    """Nạp response từ transcript.jsonl (thay vì gọi API) → replay real/mock KHÔNG mạng →
    so world-hash gốc. Determinism: xem ``minds/transcript.py`` docstring.

    The physical transcript is evidence before it is input.  Validate its stream continuity
    before constructing ``TranscriptReader`` so a gap, duplicate, or reversal can never be
    silently rearranged into prompt-hash queues and replayed as if it were legitimate history.
    """
    from engine.journal import kiem_lien_tuc

    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    mpath = run_dir / "experiment_manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}

    tp = run_dir / "transcript.jsonl"
    if not tp.exists():
        return ReplayResult(ok=False, hash_replay=None, hash_goc=meta.get("world_hash"),
                            hash_match=False, total=0, misses=0, unused=0, identity_ok=False,
                            reason=f"không có transcript để replay: {tp}")
    continuity = kiem_lien_tuc(run_dir)
    if not continuity["ok"]:
        return ReplayResult(
            ok=False, hash_replay=None, hash_goc=meta.get("world_hash"), hash_match=False,
            total=int(continuity.get("transcript_records", 0)), misses=0, unused=0,
            identity_ok=False,
            reason="journal_continuity FAIL trước TranscriptReader: "
                   + "; ".join(continuity["loi"]),
        )

    from minds.transcript import TranscriptReader, tao_mind_replay

    cfg = load_config(overlays=_nap_overlays(manifest))
    identity_ok, identity_detail = _kiem_identity(manifest, cfg)

    hash_goc = (manifest.get("outcome", {}) or {}).get("world_hash") or meta.get("world_hash")
    if not identity_ok:
        return ReplayResult(
            ok=False, hash_replay=None, hash_goc=hash_goc, hash_match=False, total=0,
            misses=0, unused=0, identity_ok=False, identity_detail=identity_detail,
            reason="skipped_version_mismatch: config/prompt identity của code hiện tại khác "
                   "manifest ⇒ transcript cũ KHÔNG replay được bằng code mới (khóa replay là "
                   "prompt_hash). Đây là FAIL, không phải SKIP.",
        )

    reader = TranscriptReader(tp)
    w = tao_the_gioi(cfg, meta["seed"], events_path=None)
    if "permute_personas" in manifest.get("reproducibility", {}).get("treatments", []):
        from tools.experiments import permute_personas

        permute_personas(w)
    mind_fn = tao_mind_replay(w, cfg, meta["mode"], reader, p_malformed=meta.get("p_malformed"))
    tong_thua = len(w.parcels)
    try:
        while w.tick < int(meta["tick_cuoi"]):
            chay_mot_tick(w, mind_fn, tong_thua)
    except Exception as exc:  # noqa: BLE001 — mọi lỗi replay/audit là bằng chứng FAIL
        return ReplayResult(
            ok=False, hash_replay=None, hash_goc=hash_goc, hash_match=False,
            total=reader.tong, misses=reader.misses, unused=reader.con_lai(),
            identity_ok=identity_ok, identity_detail=identity_detail, ticks=w.tick,
            reason=f"{type(exc).__name__}: {exc}",
            terminal_total=reader.terminal_total,
            terminal_consumed=reader.terminal_consumed,
        )
    h = w.world_hash()
    unused = reader.con_lai()
    hash_match = h == hash_goc
    ok = bool(hash_match and reader.misses == 0 and unused == 0 and identity_ok)
    ly_do = ""
    if not ok:
        phan = []
        if not hash_match:
            phan.append("world_hash LỆCH")
        if reader.misses:
            phan.append(f"{reader.misses} miss")
        if unused:
            phan.append(f"{unused} response chưa tiêu thụ")
        ly_do = "; ".join(phan)
    return ReplayResult(
        ok=ok, hash_replay=h, hash_goc=hash_goc, hash_match=hash_match, total=reader.tong,
        misses=reader.misses, unused=unused, identity_ok=identity_ok,
        identity_detail=identity_detail, ticks=w.tick, reason=ly_do,
        terminal_total=reader.terminal_total,
        terminal_consumed=reader.terminal_consumed,
    )


def _in_ket_qua(kq: ReplayResult) -> None:
    print(f"transcript  : {kq.total} record, {kq.misses} miss, {kq.unused} chưa dùng")
    print(f"terminal    : {kq.terminal_consumed}/{kq.terminal_total} decision đã tiêu thụ")
    print(f"identity    : {'KHỚP' if kq.identity_ok else 'LỆCH'} {kq.identity_detail}")
    print(f"hash replay : {kq.hash_replay}")
    print(f"hash gốc    : {kq.hash_goc}")
    print("KẾT QUẢ     : " + ("TRÙNG ✅" if kq.ok else "LỆCH ❌"))
    if kq.reason:
        print(f"LỖI: {kq.reason}")
    if kq.misses or kq.unused:
        print("LỖI: transcript không được tiêu thụ khép kín — artifact replay không đầy đủ.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--from-transcript", action="store_true",
                    help="nạp response từ transcript.jsonl thay vì gọi API (replay real/mock "
                         "không mạng)")
    args = ap.parse_args(argv)

    run_dir = DATA_DIR / args.run_name
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))

    if args.from_transcript:
        kq = replay_from_transcript(run_dir)
        if args.json:
            print(json.dumps(asdict(kq), ensure_ascii=False, indent=2))
        else:
            _in_ket_qua(kq)
        # Source identity is an execution precondition, not an optional assertion requested by
        # --verify.  A mismatched/unknown runtime must never look like a successful replay.
        if not kq.identity_ok:
            return 1
        return 0 if (kq.ok or not args.verify) else 1

    manifest_path = run_dir / "experiment_manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if meta["mode"] not in ("rulebot", "mock"):
        raise SystemExit("replay seed chỉ hỗ trợ rulebot/mock; real dùng --from-transcript")

    # Tái dựng config ĐÚNG như run: nếu có manifest, áp lại overlay (gồm scenario) để run
    # dùng scenario/counterfactual replay cùng hash. Không manifest (run cũ) → config gốc.
    overlays = _nap_overlays(manifest)
    cfg = load_config(overlays=overlays)

    # Identity TRƯỚC khi chạy (ADR 0006 §C.4). Không có bước này, một artifact chạy trên
    # interface CŨ hơn sẽ in "LỆCH ❌" — đọc như "mô phỏng mất tất định" trong khi sự thật là
    # "code hôm nay quảng cáo một tập action khác". Fail loud, không im lặng PASS, cũng không
    # giả vờ FAIL nội dung.
    identity_ok, identity_detail = _kiem_identity(manifest, cfg)
    if not identity_ok:
        print(f"identity    : LỆCH {identity_detail}")
        print("KẾT QUẢ     : skipped_version_mismatch ❌")
        print("LỖI: config/prompt/catalog của code hiện tại khác manifest ⇒ artifact này KHÔNG "
              "replay được bằng code này. Đây KHÔNG phải bằng chứng mô phỏng mất tất định.")
        return 1

    w = tao_the_gioi(cfg, meta["seed"], events_path=None)
    repro = manifest.get("reproducibility", {})
    if "permute_personas" in repro.get("treatments", []):
        from tools.experiments import permute_personas
        permute_personas(w)
    if meta["mode"] == "rulebot":
        # Tái dựng policy Lớp-4 từ manifest (như overlay/treatment) để run có --policy
        # khác rulebot replay đúng world-hash. Không manifest → baseline rulebot.
        from minds.policies import tao_policy

        ten_policy = (repro.get("policy") or {}).get("name") or "rulebot"
        mind_fn = tao_policy(ten_policy)
    else:
        from minds.orchestrator import tao_mind_mock

        mind_fn = tao_mind_mock(w, fast=True, p_malformed=meta.get("p_malformed"))
    tong_thua = len(w.parcels)
    while w.tick < meta["tick_cuoi"]:
        chay_mot_tick(w, mind_fn, tong_thua)
    h = w.world_hash()
    trung = h == meta["world_hash"]
    print(f"hash replay : {h}")
    print(f"hash gốc    : {meta['world_hash']}")
    print("KẾT QUẢ     : " + ("TRÙNG ✅" if trung else "LỆCH ❌"))
    if args.verify and not trung:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
