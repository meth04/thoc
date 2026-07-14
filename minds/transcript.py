"""Transcript-replay cho LLM THẬT (P1 — reports/publication_roadmap.md §2).

Một run ghi MỌI call vào ``data/runs/<run>/transcript.jsonl`` (append-only); replay nạp
lại response theo ``prompt_hash`` thay vì gọi API → chạy lại nguyên pipeline
(repair → validate → intent → apply) → CÙNG world-hash. Đây là cổng REPRODUCIBILITY
reviewer đòi: "kết luận real tái lập được từ artifact".

Vì sao tất định (điều luật #4):
- Prompt là hàm THUẦN của trạng thái thế giới; ``RngTree.get`` spawn Generator riêng theo
  (subsystem × tick) — KHÔNG có stream chia sẻ — nên bỏ qua call sinh-quyết-định lúc
  replay không hề động vào RNG engine. Cùng transcript ⇒ cùng chuỗi prompt ⇒ cùng
  response ⇒ cùng world-hash (quy nạp theo tick).
- Tra cứu bằng ``prompt_hash`` (không bằng call_id): fan-out song song real ghi call theo
  thứ tự HOÀN TẤT không tất định, nhưng prompt mỗi agent là duy nhất (chứa id) nên khóa
  theo nội dung prompt loại bỏ phụ thuộc thứ tự. Trùng prompt hiếm (nén hồi ký) xử lý FIFO.

Che key: prompt/response đi qua ``che_key`` trước khi ghi (điều luật #4 mục 4 — key không
bao giờ lộ). ``prompt_hash`` băm prompt GỐC nên replay (băm ``req.prompt`` gốc) vẫn khớp.

GIỚI HẠN (không overclaim):
- Vòng công cụ MCP (``goi_agentic``) ghi 1 entry/agent: prompt khởi đầu + QUYẾT ĐỊNH cuối.
  Công cụ CHỈ ĐỌC (điều luật #1) không chạm state ⇒ chỉ quyết định cuối vào world-hash ⇒
  replay quyết định cuối là đủ; KHÔNG tái diễn các lượt công cụ trung gian.
- Hồi ký/niềm tin (``a.hoi_ky``, ``a.niem_tin``) KHÔNG vào world_hash nhưng CÓ trong prompt
  tick sau; nên mọi call (kể cả nén/phản tư) đều được ghi + phục vụ từ transcript để prompt
  các tick sau trùng khít.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from pathlib import Path

from minds.gateway import LLMRequest, LLMResponse
from minds.providers_real import LoiHetQuota, che_key


def bam_prompt(prompt: str) -> str:
    """sha256 hex của prompt — khóa tra cứu transcript, tất định (điều luật #4)."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class TranscriptWriter:
    """Ghi transcript.jsonl append-only: mỗi call một dòng JSON đã che key.

    ``call_id`` phải DUY NHẤT TOÀN RUN. Trước P0.2, writer mở ``"a"`` nhưng đặt ``_n = 0``
    ⇒ mỗi process mới đếm lại từ 1 ⇒ ``real60_spatial`` có **403 call_id bị dùng lại**
    (`docs/reviews/Report_v2-ledger.md` F-05). ``start_call_id`` được gieo lại từ
    ``record_count`` của checkpoint đang nạp (``engine/journal.py``).

    ``run_uuid``/``segment_id`` là metadata forensic (phân biệt bản ghi giữa file live và
    file quarantine). **Khóa replay VẪN là ``prompt_hash``** — không đổi.
    """

    def __init__(self, path: Path, *, start_call_id: int = 0,
                 run_uuid: str | None = None, segment_id: int = 0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a", encoding="utf-8")  # noqa: SIM115 — giữ mở suốt run
        self._n = int(start_call_id)
        self.run_uuid = run_uuid
        self.segment_id = int(segment_id)

    def rebase(self, *, start_call_id: int, run_uuid: str | None = None,
               segment_id: int = 0) -> None:
        """Gieo lại counter/identity sau khi run.py nạp journal manifest (mind được dựng
        trước khi biết segment). Chỉ hợp lệ trước call đầu tiên của phiên."""
        self._n = int(start_call_id)
        self.run_uuid = run_uuid
        self.segment_id = int(segment_id)

    @property
    def so_ghi(self) -> int:
        """call_id cao nhất đã ghi (toàn run)."""
        return self._n

    def ghi(self, tick: int, tier: str, provider: str, model: str, temperature,
            prompt: str, response_raw: str, tok_in: int, tok_out: int,
            *, error_type: str | None = None, error_message: str | None = None) -> None:
        """Ghi cả response thành công lẫn lỗi terminal.

        Một lỗi provider là một nhánh điều khiển có tác dụng lên run (fallback/dừng êm),
        không phải ``missing data``. Ghi nó vào transcript để replay tái hiện đúng nhánh
        thay vì cố ý tạo một miss giả ở lần chạy sau.
        """
        self._n += 1
        is_error = error_type is not None or provider == "loi"
        self._f.write(json.dumps({
            "call_id": self._n,
            "run_uuid": self.run_uuid,
            "segment_id": self.segment_id,
            "tick": int(tick),
            "tier": tier,
            "provider": provider,
            "model": model,
            "temperature": temperature,
            "prompt_hash": bam_prompt(prompt),  # băm prompt GỐC (khớp lúc replay)
            "request": che_key(prompt),         # lưu bản đã che để người đọc/kiểm tra
            "response_raw": che_key(response_raw or ""),
            "outcome": "error" if is_error else "response",
            "error_type": error_type,
            "error_message": che_key(error_message or "") if is_error else "",
            "tok_in": int(tok_in),
            "tok_out": int(tok_out),
        }, ensure_ascii=False) + "\n")

    # ``flush``/``fsync``/``dong`` là IDEMPOTENT (như ``EventLog`` và ``LLMCallLog``): trên
    # đường crash, ``run.chay_run`` đóng writer để không có handle mồ côi nào flush buffer ĐÈ
    # vào journal vừa bị truncate lúc resume; caller (test seam, driver) có thể đóng lần nữa.
    # Đóng hai lần phải là no-op, không phải ``ValueError: I/O operation on closed file``.
    def flush(self) -> None:
        if not self._f.closed:
            self._f.flush()

    def fsync(self) -> None:
        if not self._f.closed:
            self._f.flush()
            os.fsync(self._f.fileno())

    def dong(self) -> None:
        if not self._f.closed:
            self._f.flush()
            self._f.close()


class TranscriptReader:
    """Nạp transcript.jsonl → hàng đợi FIFO response theo prompt_hash (tiêu thụ 1 lần)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._theo_hash: dict[str, deque] = {}
        self.tong = 0
        self.misses = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                self._theo_hash.setdefault(d["prompt_hash"], deque()).append(d)
                self.tong += 1

    def lay(self, prompt: str) -> dict:
        """Rút (pop FIFO) response đã ghi cho prompt; thiếu → KeyError + đếm miss."""
        dq = self._theo_hash.get(bam_prompt(prompt))
        if not dq:
            self.misses += 1
            raise KeyError("transcript miss")
        return dq.popleft()

    def con_lai(self) -> int:
        """Số response CHƯA được tiêu thụ (replay đúng ⇒ 0 sau khi chạy hết)."""
        return sum(len(dq) for dq in self._theo_hash.values())


class TranscriptProvider:
    """Provider thay mạng: trả response đã ghi theo prompt_hash (không call API).

    Thiếu response (prompt lệch, hoặc tick GỐC đã dừng vì cạn ngân sách) → ``LoiHetQuota``
    để khớp đúng đường fallback/dừng-êm của orchestrator (điều luật #7)."""

    ten = "transcript"

    def __init__(self, reader: TranscriptReader):
        self.reader = reader

    def goi(self, req: LLMRequest, attempt: int = 0) -> LLMResponse:
        return self._tra(req)

    def goi_agentic(self, req: LLMRequest, w, aid: str) -> LLMResponse:
        # MCP: chỉ QUYẾT ĐỊNH cuối được ghi (công cụ chỉ đọc, không chạm state)
        return self._tra(req)

    def _tra(self, req: LLMRequest) -> LLMResponse:
        try:
            d = self.reader.lay(req.prompt)
        except KeyError:
            raise LoiHetQuota("transcript thiếu response cho prompt") from None
        if d.get("outcome") == "error" or d.get("provider") == "loi":
            message = str(d.get("error_message") or d.get("response_raw")
                          or "provider error recorded in transcript")
            raise LoiHetQuota(message)
        return LLMResponse(
            text=d.get("response_raw", ""), provider=d.get("provider", "transcript"),
            model=d.get("model", ""), tok_in=int(d.get("tok_in", 0)),
            tok_out=int(d.get("tok_out", 0)), key_hash="transcript",
        )


def tao_mind_replay(w, cfg, mode: str, reader: TranscriptReader, p_malformed=None):
    """Dựng mind replay-from-transcript cho mock/real: pipeline y hệt run gốc nhưng provider
    = TranscriptProvider (không mạng, không quota, không kiểm ngân sách). KHÔNG ghi file
    (run_dir/quota_db = None) nên không đụng artifact của run gốc."""
    prov = TranscriptProvider(reader)
    if mode == "mock":
        from minds.orchestrator import tao_mind_mock

        mind = tao_mind_mock(w, fast=True, run_dir=None, p_malformed=p_malformed)
        mind.provider = prov  # nén/phản tư mock là heuristic → không cần transcript
        return mind
    if mode == "real":
        from minds.keypool import EnvKeys
        from minds.real import MindReal

        env = EnvKeys(gemini_keys=[], nine_key="", nine_base="", llm_mode="real")
        mind = MindReal(w, None, cfg, env, None, transport=None)  # run_dir/quota_db=None
        # đóng client httpx của gateway thật (bị vứt bỏ) để khỏi rò tài nguyên
        for p in (mind.gateway.aistudio, mind.gateway.ninerouter):
            try:
                p.client.close()
            except Exception:  # noqa: BLE001
                pass
        mind.provider = prov  # quyết định agent: từ transcript (thay GatewayCoPacing)
        mind.gateway = _GatewayReplay()  # route nền: ghi_call no-op, không mạng
        mind._goi_nen_co_cho = lambda req, route: prov.goi(req)  # nén/phản tư/dịch intent
        mind._du_ngan_sach = lambda w, thinkers: True  # miss transcript tự tái hiện dừng-êm
        return mind
    raise ValueError(f"mode replay không hỗ trợ: {mode}")


class _GatewayReplay:
    """Gateway giả cho replay real: chỉ giữ quota.ghi_call no-op (route nền gọi tới)."""

    class _Quota:
        def ghi_call(self, *a, **k) -> None:  # noqa: ANN002, ANN003
            pass

    def __init__(self):
        self.quota = _GatewayReplay._Quota()
