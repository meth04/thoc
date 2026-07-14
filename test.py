from __future__ import annotations

import asyncio
import csv
import json
import math
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# =====================================================================
# CONFIG — CHỈ CẦN SỬA PHẦN NÀY
# =====================================================================

# API key của 9Router
API_KEY = "sk-da6f5da3604d3663-jp8mwo-45708b37"

# Endpoint chat completions.
# 9Router local thường có dạng:
# http://127.0.0.1:20128/v1/chat/completions
ENDPOINT = "http://127.0.0.1:20128/v1/chat/completions"

MODEL = "oc/deepseek-v4-flash-free"

# Chọn một trong ba:
# "rpm"  = chỉ test RPM
# "tpm"  = chỉ test TPM
# "both" = test RPM trước, sau đó test TPM
TEST_MODE = "both"


# =====================================================================
# TEST RPM
# =====================================================================

# Script sẽ test lần lượt các mức này.
# Khi một mức không ổn định, script sẽ dừng phần RPM.
RPM_STAGES = [
    250,
    300,
    400,
    500
]

# Mỗi mức RPM chạy bao nhiêu giây.
# Nên dùng ít nhất 70 giây để đi qua một cửa sổ 60 giây.
# Khi đã tìm được khoảng giới hạn, tăng lên 180–300 giây.
RPM_STAGE_SECONDS = 75


# =====================================================================
# TEST TPM
# =====================================================================

# Khi test TPM, giữ RPM thấp hơn đáng kể so với giới hạn RPM.
# Ví dụ RPM ổn định là 80 thì có thể đặt khoảng 10–30.
TPM_FIXED_RPM = 10

# Mức TPM mục tiêu.
# Script tính token/request = TPM / TPM_FIXED_RPM.
TPM_STAGES = [
    1_000_000,
    1_500_000,
    2_000_000,
    2_500_000,
    3_000_000,
    4_000_000,
    5_000_000,
    6_000_000
]

TPM_STAGE_SECONDS = 75


# =====================================================================
# REQUEST VÀ ĐIỀU KIỆN DỪNG
# =====================================================================

# Output càng ngắn càng dễ tách biệt giới hạn input TPM.
MAX_OUTPUT_TOKENS = 4

# Số request tối đa có thể đang chạy cùng lúc.
MAX_CONCURRENCY = 256

# Timeout cho mỗi request.
REQUEST_TIMEOUT_SECONDS = 180

# Nghỉ giữa hai stage để rate-limit window được reset.
COOLDOWN_SECONDS = 65

# Một stage chỉ được xem là ổn định khi tỷ lệ thành công đạt mức này
# và không có 429 hoặc 441/risk_control.
MIN_SUCCESS_RATE = 0.99

# Dừng sau stage đầu tiên không ổn định.
STOP_AFTER_FIRST_FAILED_STAGE = True

# Dừng ngay lập tức khi phát hiện 441/risk_control.
STOP_IMMEDIATELY_ON_441 = True

# Thư mục lưu CSV và JSON.
OUTPUT_DIR = "llm_probe_results"


# =====================================================================
# ƯỚC LƯỢNG TOKEN
# =====================================================================

# Khi API không trả trường usage, script phải ước lượng token.
# Giá trị ban đầu thường dùng là khoảng 4 ký tự/token.
#
# Nếu response có usage.prompt_tokens, script sẽ tự hiệu chỉnh
# tỷ lệ ký tự/token cho các stage tiếp theo.
INITIAL_CHARS_PER_TOKEN = 4.0

# Ngăn script vô tình tạo prompt quá lớn.
MAX_PROMPT_TOKENS_PER_REQUEST = 200_000


# =====================================================================
# BODY BỔ SUNG
# =====================================================================

# Thêm tham số tại đây khi route/provider yêu cầu.
EXTRA_BODY: dict[str, Any] = {}

# Ví dụ:
#
# EXTRA_BODY = {
#     "provider": "mmf",
# }


# =====================================================================
# TỰ CÀI HTTPX
# =====================================================================

def install_and_import_httpx():
    try:
        import httpx  # type: ignore

        return httpx

    except ImportError:
        print("Chưa có httpx. Đang tự động cài đặt...")

        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "httpx>=0.27,<1",
            ]
        )

        import httpx  # type: ignore

        return httpx


httpx = install_and_import_httpx()


# =====================================================================
# HÀM TIỆN ÍCH
# =====================================================================

def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    position = (len(ordered) - 1) * percentile_value
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    return (
        ordered[lower] * (upper - position)
        + ordered[upper] * (position - lower)
    )


def parse_usage(
    response_data: dict[str, Any],
) -> tuple[int, int, int]:
    usage = response_data.get("usage") or {}

    prompt_tokens = int(
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or 0
    )

    completion_tokens = int(
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or 0
    )

    total_tokens = int(
        usage.get("total_tokens")
        or prompt_tokens + completion_tokens
    )

    return (
        prompt_tokens,
        completion_tokens,
        total_tokens,
    )


def parse_error(
    response_data: Any,
    raw_text: str,
) -> tuple[str, str, str]:
    if isinstance(response_data, dict):
        error = response_data.get("error", response_data)

        if isinstance(error, dict):
            return (
                str(error.get("code") or ""),
                str(error.get("type") or ""),
                str(
                    error.get("message")
                    or raw_text[:500]
                ),
            )

    return "", "", raw_text[:500]


def is_risk_control(
    status: int,
    error_code: str,
    error_type: str,
    error_message: str,
) -> bool:
    combined = (
        f"{error_code} "
        f"{error_type} "
        f"{error_message}"
    ).lower()

    return (
        status == 441
        or error_code == "441"
        or "risk_control" in combined
    )


# =====================================================================
# ƯỚC LƯỢNG TOKEN
# =====================================================================

class TokenEstimator:
    def __init__(self, chars_per_token: float):
        self.chars_per_token = max(
            0.5,
            chars_per_token,
        )

    def estimate(self, text: str) -> int:
        return max(
            1,
            math.ceil(
                len(text) / self.chars_per_token
            ),
        )

    def calibrate(
        self,
        rows: list[dict[str, Any]],
    ) -> None:
        """
        Nếu response trả usage.prompt_tokens,
        tự tính lại tỷ lệ ký tự/token.
        """

        ratios: list[float] = []

        for row in rows:
            prompt_tokens = int(
                row.get("prompt_tokens") or 0
            )

            prompt_chars = int(
                row.get("prompt_chars") or 0
            )

            if prompt_tokens > 0 and prompt_chars > 0:
                ratios.append(
                    prompt_chars / prompt_tokens
                )

        if ratios:
            median_ratio = statistics.median(ratios)

            self.chars_per_token = min(
                12.0,
                max(
                    0.5,
                    median_ratio,
                ),
            )


def build_prompt(
    target_tokens: int,
    estimator: TokenEstimator,
) -> str:
    """
    Tạo prompt có số token gần với target_tokens.

    Khi không có tokenizer chính thức, số token được suy ra
    từ tỷ lệ ký tự/token.
    """

    target_tokens = max(
        1,
        min(
            target_tokens,
            MAX_PROMPT_TOKENS_PER_REQUEST,
        ),
    )

    suffix = "\nReply with only: OK"

    target_chars = max(
        8,
        int(
            target_tokens
            * estimator.chars_per_token
        )
        - len(suffix),
    )

    unit = (
        "alpha beta gamma delta "
        "epsilon zeta eta theta "
    )

    repeat_count = math.ceil(
        target_chars / len(unit)
    )

    body = (
        unit * repeat_count
    )[:target_chars]

    return body + suffix


# =====================================================================
# GỬI MỘT REQUEST
# =====================================================================

async def send_request(
    client: Any,
    semaphore: asyncio.Semaphore,
    abort_event: asyncio.Event,
    stage_name: str,
    request_number: int,
    due_at: float,
    stage_start: float,
    prompt: str,
    estimated_prompt_tokens: int,
) -> dict[str, Any] | None:
    """
    Chờ đúng thời điểm rồi gửi request.

    Request được phân bố đều theo thời gian,
    không gửi tất cả cùng một lúc.
    """

    delay = due_at - time.monotonic()

    if delay > 0:
        await asyncio.sleep(delay)

    if abort_event.is_set():
        return None

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0,
        "stream": False,
        **EXTRA_BODY,
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    async with semaphore:
        sent_at = time.monotonic()
        request_started = time.perf_counter()

        try:
            response = await client.post(
                ENDPOINT,
                headers=headers,
                json=payload,
            )

            latency = (
                time.perf_counter()
                - request_started
            )

            raw_text = response.text

            try:
                response_data = response.json()
            except Exception:
                response_data = {}

            (
                prompt_tokens,
                completion_tokens,
                total_tokens,
            ) = parse_usage(response_data)

            (
                error_code,
                error_type,
                error_message,
            ) = parse_error(
                response_data,
                raw_text,
            )

            risk_control = is_risk_control(
                status=response.status_code,
                error_code=error_code,
                error_type=error_type,
                error_message=error_message,
            )

            if (
                risk_control
                and STOP_IMMEDIATELY_ON_441
            ):
                abort_event.set()

            return {
                "timestamp": datetime.now().isoformat(
                    timespec="milliseconds"
                ),
                "stage": stage_name,
                "request_number": request_number,
                "status": response.status_code,
                "latency_seconds": round(
                    latency,
                    6,
                ),
                "send_offset_seconds": round(
                    sent_at - stage_start,
                    6,
                ),
                "prompt_chars": len(prompt),
                "estimated_prompt_tokens": (
                    estimated_prompt_tokens
                ),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "risk_control": risk_control,
                "error_code": error_code,
                "error_type": error_type,
                "error_message": error_message[:500],
            }

        except Exception as exception:
            latency = (
                time.perf_counter()
                - request_started
            )

            return {
                "timestamp": datetime.now().isoformat(
                    timespec="milliseconds"
                ),
                "stage": stage_name,
                "request_number": request_number,
                "status": 0,
                "latency_seconds": round(
                    latency,
                    6,
                ),
                "send_offset_seconds": round(
                    sent_at - stage_start,
                    6,
                ),
                "prompt_chars": len(prompt),
                "estimated_prompt_tokens": (
                    estimated_prompt_tokens
                ),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "risk_control": False,
                "error_code": "client_error",
                "error_type": type(
                    exception
                ).__name__,
                "error_message": str(
                    exception
                )[:500],
            }


# =====================================================================
# CHẠY MỘT STAGE
# =====================================================================

async def run_stage(
    client: Any,
    estimator: TokenEstimator,
    stage_name: str,
    target_rpm: float,
    duration_seconds: int,
    prompt_tokens_per_request: int,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
]:
    """
    Chạy một stage với target RPM cố định.

    Ví dụ:
        target_rpm = 60
        duration = 75 giây

    Request count:
        floor(60 * 75 / 60) = 75 request
    """

    request_count = max(
        1,
        math.floor(
            target_rpm
            * duration_seconds
            / 60
        ),
    )

    request_interval = 60 / target_rpm

    prompt = build_prompt(
        target_tokens=prompt_tokens_per_request,
        estimator=estimator,
    )

    estimated_prompt_tokens = (
        estimator.estimate(prompt)
    )

    stage_start = time.monotonic()

    semaphore = asyncio.Semaphore(
        MAX_CONCURRENCY
    )

    abort_event = asyncio.Event()

    tasks = []

    for request_index in range(request_count):
        due_at = (
            stage_start
            + request_index
            * request_interval
        )

        task = asyncio.create_task(
            send_request(
                client=client,
                semaphore=semaphore,
                abort_event=abort_event,
                stage_name=stage_name,
                request_number=request_index + 1,
                due_at=due_at,
                stage_start=stage_start,
                prompt=prompt,
                estimated_prompt_tokens=(
                    estimated_prompt_tokens
                ),
            )
        )

        tasks.append(task)

    raw_rows = await asyncio.gather(*tasks)

    rows = [
        row
        for row in raw_rows
        if row is not None
    ]

    successful_rows = [
        row
        for row in rows
        if 200 <= row["status"] < 300
    ]

    latency_values = [
        float(row["latency_seconds"])
        for row in successful_rows
    ]

    statuses: dict[str, int] = {}

    for row in rows:
        key = str(row["status"])

        statuses[key] = (
            statuses.get(key, 0) + 1
        )

    if rows:
        success_rate = (
            len(successful_rows)
            / len(rows)
        )
    else:
        success_rate = 0.0

    has_429 = any(
        row["status"] == 429
        for row in rows
    )

    has_441 = any(
        row["risk_control"]
        for row in rows
    )

    has_5xx = any(
        500 <= row["status"] <= 599
        for row in rows
    )

    usage_available = any(
        row["prompt_tokens"] > 0
        for row in successful_rows
    )

    prompt_token_sum = sum(
        row["prompt_tokens"]
        for row in successful_rows
    )

    completion_token_sum = sum(
        row["completion_tokens"]
        for row in successful_rows
    )

    total_token_sum = sum(
        row["total_tokens"]
        for row in successful_rows
    )

    estimated_prompt_token_sum = sum(
        row["estimated_prompt_tokens"]
        for row in successful_rows
    )

    prompt_tpm = (
        prompt_token_sum
        * 60
        / duration_seconds
    )

    completion_tpm = (
        completion_token_sum
        * 60
        / duration_seconds
    )

    total_tpm = (
        total_token_sum
        * 60
        / duration_seconds
    )

    estimated_prompt_tpm = (
        estimated_prompt_token_sum
        * 60
        / duration_seconds
    )

    successful_rpm = (
        len(successful_rows)
        * 60
        / duration_seconds
    )

    passed = (
        success_rate >= MIN_SUCCESS_RATE
        and not has_429
        and not has_441
    )

    summary = {
        "stage": stage_name,
        "target_rpm": target_rpm,
        "duration_seconds": duration_seconds,
        "prompt_tokens_per_request_target": (
            prompt_tokens_per_request
        ),
        "attempted": len(rows),
        "successful": len(successful_rows),
        "failed": (
            len(rows)
            - len(successful_rows)
        ),
        "success_rate": success_rate,
        "statuses": statuses,
        "has_429": has_429,
        "has_441_or_risk_control": has_441,
        "has_5xx": has_5xx,
        "passed": passed,
        "successful_rpm": successful_rpm,
        "latency_p50_seconds": (
            statistics.median(latency_values)
            if latency_values
            else 0
        ),
        "latency_p95_seconds": percentile(
            latency_values,
            0.95,
        ),
        "latency_max_seconds": (
            max(latency_values)
            if latency_values
            else 0
        ),
        "usage_available": usage_available,
        "prompt_tpm": prompt_tpm,
        "completion_tpm": completion_tpm,
        "total_tpm": total_tpm,
        "estimated_prompt_tpm": (
            estimated_prompt_tpm
        ),
        "chars_per_token_before": (
            estimator.chars_per_token
        ),
    }

    estimator.calibrate(successful_rows)

    summary["chars_per_token_after"] = (
        estimator.chars_per_token
    )

    return summary, rows


# =====================================================================
# HIỂN THỊ VÀ LƯU KẾT QUẢ
# =====================================================================

def print_summary(
    summary: dict[str, Any],
) -> None:
    print("\n" + "=" * 76)
    print(summary["stage"])
    print("=" * 76)

    print(
        f"Target RPM: {summary['target_rpm']:.2f}"
    )

    print(
        "Requests: "
        f"{summary['successful']}/"
        f"{summary['attempted']} thành công"
    )

    print(
        "Success rate: "
        f"{summary['success_rate']:.2%}"
    )

    print(
        f"HTTP status: {summary['statuses']}"
    )

    print(
        f"Stage ổn định: {summary['passed']}"
    )

    print(
        "Successful RPM: "
        f"{summary['successful_rpm']:.2f}"
    )

    print(
        "Latency: "
        f"p50={summary['latency_p50_seconds']:.3f}s | "
        f"p95={summary['latency_p95_seconds']:.3f}s | "
        f"max={summary['latency_max_seconds']:.3f}s"
    )

    if summary["usage_available"]:
        print(
            "Prompt TPM: "
            f"{summary['prompt_tpm']:.0f}"
        )

        print(
            "Completion TPM: "
            f"{summary['completion_tpm']:.0f}"
        )

        print(
            "Total TPM: "
            f"{summary['total_tpm']:.0f}"
        )

    else:
        print(
            "Estimated prompt TPM: "
            f"{summary['estimated_prompt_tpm']:.0f}"
        )

        print(
            "Cảnh báo: response không có usage; "
            "TPM hiện chỉ là ước lượng."
        )

    print(
        "Chars/token: "
        f"{summary['chars_per_token_before']:.3f}"
        " -> "
        f"{summary['chars_per_token_after']:.3f}"
    )


def append_rows_to_csv(
    csv_path: Path,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return

    is_new_file = not csv_path.exists()

    with csv_path.open(
        "a",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=list(rows[0].keys()),
        )

        if is_new_file:
            writer.writeheader()

        writer.writerows(rows)


async def cooldown() -> None:
    if COOLDOWN_SECONDS <= 0:
        return

    print(
        f"\nCooldown {COOLDOWN_SECONDS} giây..."
    )

    await asyncio.sleep(
        COOLDOWN_SECONDS
    )


# =====================================================================
# MAIN
# =====================================================================

async def main() -> None:
    if (
        not API_KEY
        or API_KEY == "PASTE_API_KEY_HERE"
    ):
        raise SystemExit(
            "Hãy dán API key vào biến API_KEY "
            "ở đầu file."
        )

    if TEST_MODE not in {
        "rpm",
        "tpm",
        "both",
    }:
        raise SystemExit(
            'TEST_MODE phải là "rpm", '
            '"tpm" hoặc "both".'
        )

    output_directory = Path(
        OUTPUT_DIR
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_id = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    csv_path = (
        output_directory
        / f"requests_{run_id}.csv"
    )

    json_path = (
        output_directory
        / f"summary_{run_id}.json"
    )

    timeout = httpx.Timeout(
        connect=30,
        read=REQUEST_TIMEOUT_SECONDS,
        write=REQUEST_TIMEOUT_SECONDS,
        pool=REQUEST_TIMEOUT_SECONDS,
    )

    connection_limits = httpx.Limits(
        max_connections=MAX_CONCURRENCY,
        max_keepalive_connections=(
            MAX_CONCURRENCY
        ),
    )

    estimator = TokenEstimator(
        INITIAL_CHARS_PER_TOKEN
    )

    all_summaries: list[
        dict[str, Any]
    ] = []

    stop_everything = False

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=connection_limits,
        http2=False,
    ) as client:

        # =============================================================
        # TEST RPM
        # =============================================================

        if TEST_MODE in {
            "rpm",
            "both",
        }:
            print(
                "\n===== BẮT ĐẦU TEST RPM ====="
            )

            for stage_index, rpm in enumerate(
                RPM_STAGES
            ):
                if stage_index > 0:
                    await cooldown()

                summary, rows = await run_stage(
                    client=client,
                    estimator=estimator,
                    stage_name=f"rpm_{rpm}",
                    target_rpm=float(rpm),
                    duration_seconds=(
                        RPM_STAGE_SECONDS
                    ),
                    prompt_tokens_per_request=8,
                )

                print_summary(summary)

                append_rows_to_csv(
                    csv_path,
                    rows,
                )

                all_summaries.append(
                    summary
                )

                if summary[
                    "has_441_or_risk_control"
                ]:
                    print(
                        "\nDừng toàn bộ vì gặp "
                        "441/risk_control."
                    )

                    stop_everything = True
                    break

                if (
                    not summary["passed"]
                    and STOP_AFTER_FIRST_FAILED_STAGE
                ):
                    print(
                        "\nStage RPM không ổn định. "
                        "Dừng phần test RPM."
                    )

                    break

        # Nghỉ giữa phần RPM và TPM
        if (
            TEST_MODE == "both"
            and not stop_everything
        ):
            await cooldown()

        # =============================================================
        # TEST TPM
        # =============================================================

        if (
            TEST_MODE in {
                "tpm",
                "both",
            }
            and not stop_everything
        ):
            print(
                "\n===== BẮT ĐẦU TEST TPM ====="
            )

            for stage_index, target_tpm in enumerate(
                TPM_STAGES
            ):
                if stage_index > 0:
                    await cooldown()

                prompt_tokens_per_request = max(
                    1,
                    round(
                        target_tpm
                        / TPM_FIXED_RPM
                    ),
                )

                summary, rows = await run_stage(
                    client=client,
                    estimator=estimator,
                    stage_name=(
                        f"tpm_{target_tpm}"
                    ),
                    target_rpm=float(
                        TPM_FIXED_RPM
                    ),
                    duration_seconds=(
                        TPM_STAGE_SECONDS
                    ),
                    prompt_tokens_per_request=(
                        prompt_tokens_per_request
                    ),
                )

                summary["target_tpm"] = (
                    target_tpm
                )

                print_summary(summary)

                append_rows_to_csv(
                    csv_path,
                    rows,
                )

                all_summaries.append(
                    summary
                )

                if summary[
                    "has_441_or_risk_control"
                ]:
                    print(
                        "\nDừng toàn bộ vì gặp "
                        "441/risk_control."
                    )

                    break

                if (
                    not summary["passed"]
                    and STOP_AFTER_FIRST_FAILED_STAGE
                ):
                    print(
                        "\nStage TPM không ổn định. "
                        "Dừng phần test TPM."
                    )

                    break

    # Lưu summary JSON
    json_path.write_text(
        json.dumps(
            all_summaries,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # =============================================================
    # TỔNG HỢP KẾT QUẢ
    # =============================================================

    stable_rpm_values = [
        summary["successful_rpm"]
        for summary in all_summaries
        if (
            summary["stage"].startswith(
                "rpm_"
            )
            and summary["passed"]
        )
    ]

    stable_tpm_values = []

    for summary in all_summaries:
        if not summary["stage"].startswith(
            "tpm_"
        ):
            continue

        if not summary["passed"]:
            continue

        if summary["usage_available"]:
            stable_tpm_values.append(
                summary["total_tpm"]
            )
        else:
            stable_tpm_values.append(
                summary[
                    "estimated_prompt_tpm"
                ]
            )

    print("\n" + "#" * 76)
    print("KẾT QUẢ TẠM TÍNH")
    print("#" * 76)

    if stable_rpm_values:
        print(
            "RPM ổn định cao nhất đã test: "
            f"{max(stable_rpm_values):.2f}"
        )
    else:
        print(
            "Chưa có stage RPM ổn định."
        )

    if stable_tpm_values:
        print(
            "TPM ổn định cao nhất đã test: "
            f"{max(stable_tpm_values):.0f}"
        )
    else:
        print(
            "Chưa có stage TPM ổn định."
        )

    print(
        f"\nChi tiết từng request: {csv_path}"
    )

    print(
        f"Tổng hợp từng stage:   {json_path}"
    )

    print(
        "\nĐể tìm sát giới hạn hơn, sửa RPM_STAGES "
        "hoặc TPM_STAGES thành các mức nằm giữa "
        "stage cuối cùng thành công và stage đầu tiên lỗi."
    )

    print(
        "\nQuan trọng: khi API không trả usage và không có "
        "tokenizer chính xác của model, TPM chỉ có thể "
        "được ước lượng. RPM vẫn được đo trực tiếp."
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print(
            "\nĐã dừng test bằng bàn phím."
        )
