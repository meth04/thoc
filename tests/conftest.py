"""Cấu hình pytest dùng chung.

Guard mạng OPT-IN: khi biến môi trường ``THOC_BLOCK_NETWORK=1`` (CI hoặc phiên nghiên cứu
không-mạng đặt), mọi kết nối socket ra ngoài bị chặn. Bộ test THÓC chạy hoàn toàn ở chế độ
rulebot/mock/FakeTransport nên guard không được phép làm hỏng test nào — nếu một test cần
mạng thật, nó SAI (test phải dùng mock).

Guard mặc định TẮT để không đổi hành vi chạy test cục bộ thông thường.
"""

from __future__ import annotations

import os
import socket


def _chan_mang() -> None:
    loopback = {"127.0.0.1", "::1", "localhost"}

    def _guard(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError(
            "THOC_BLOCK_NETWORK=1: kết nối mạng bị chặn trong test. "
            "Test phải dùng rulebot/mock/FakeTransport, không gọi provider/API thật."
        )

    orig_connect = socket.socket.connect

    def _connect(self, address, *a, **k):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else None
        if host in loopback:
            return orig_connect(self, address, *a, **k)
        _guard()

    socket.socket.connect = _connect  # type: ignore[assignment]
    socket.create_connection = _guard  # type: ignore[assignment]


if os.environ.get("THOC_BLOCK_NETWORK") == "1":
    _chan_mang()
