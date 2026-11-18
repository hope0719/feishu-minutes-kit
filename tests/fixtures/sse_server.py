"""Local SSE server used to exercise the StepFun ASR client offline."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _event(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()


class _Handler(BaseHTTPRequestHandler):
    mode = "normal"

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        if self.mode == "error":
            self._write(_event({"type": "error", "message": "boom"}))
            return
        if self.mode == "truncated":
            self._write(_event({"type": "transcript.text.delta", "delta": "部分"}))
            return
        self._write(_event({"type": "transcript.text.delta", "delta": "你好"}))
        self._write(_event({"type": "transcript.text.delta", "delta": "世界"}))
        self._write(_event({"type": "transcript.text.done", "text": "你好世界"}))

    def _write(self, chunk: bytes) -> None:
        self.wfile.write(chunk)
        self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def sse_server(mode: str = "normal") -> Iterator[str]:
    handler = type("ModeHandler", (_Handler,), {"mode": mode})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}/asr"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
