"""Loopback-only web UI and JSON API. No authentication or remote exposure."""
from __future__ import annotations

import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .benchmark import (BenchmarkError, DEMO_QUERY, DEMO_QUERY_COMPARISON,
                        benchmark_query, compare_queries)
from .plans import PlanError, analyze_plan, compare_plans

RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WEB = RESOURCE_ROOT / "web"
EXAMPLES = RESOURCE_ROOT / "examples"
MAX_POST_BYTES = 2_250_000
WORK_LIMIT = threading.BoundedSemaphore(3)
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/logo.svg": ("logo.svg", "image/svg+xml"),
}
LOG = logging.getLogger(__name__)


class APIError(ValueError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def make_handler():
    class Handler(BaseHTTPRequestHandler):
        server_version = "KTNS-SQLBench/0.1"
        sys_version = ""

        def log_message(self, fmt: str, *args: Any) -> None:
            # Do not log SQL payloads or plan text.
            LOG.info("%s %s", self.address_string(), fmt % args)

        def _headers(self, status: int, mime: str, size: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'self'; "
                             "script-src 'self'; style-src 'self'; img-src 'self' data:; "
                             "connect-src 'self'; base-uri 'none'; object-src 'none'; "
                             "frame-ancestors 'none'")
            self.end_headers()

        def _send_json(self, status: int, data: dict[str, Any]) -> None:
            payload = json.dumps(data, allow_nan=False).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(payload))
            self.wfile.write(payload)

        def _is_local_request(self) -> bool:
            port = self.server.server_port
            hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
            host = (self.headers.get("Host") or "").lower()
            origin = (self.headers.get("Origin") or "").lower()
            return host in hosts and (not origin or origin in {f"http://{h}" for h in hosts})

        def _post_body(self) -> dict[str, Any]:
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                raise APIError(415, "content_type", "Send application/json.")
            if self.headers.get("X-SqlBench-Request") != "1":
                raise APIError(403, "request_header", "Missing local application request header.")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError as exc:
                raise APIError(411, "content_length", "Content-Length is required.") from exc
            if length <= 0 or length > MAX_POST_BYTES:
                raise APIError(413, "payload_limit", "Invalid or excessive request size.")
            try:
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError) as exc:
                raise APIError(400, "invalid_json", "Body must contain valid JSON.") from exc
            if not isinstance(body, dict):
                raise APIError(400, "invalid_body", "Expected a JSON object.")
            return body

        def _route(self, method: str) -> None:
            if not self._is_local_request():
                raise APIError(403, "loopback_only", "This application only accepts local requests.")
            route = urlsplit(self.path).path
            if method == "GET":
                if route in STATIC:
                    filename, mime = STATIC[route]
                    payload = (WEB / filename).read_bytes()
                    self._headers(200, mime, len(payload))
                    self.wfile.write(payload)
                    return
                if route == "/api/health":
                    self._send_json(200, {"ok": True, "mode": "offline-local"})
                    return
                if route == "/api/demo":
                    self._send_json(200, {
                        "before": DEMO_QUERY, "after": DEMO_QUERY_COMPARISON,
                        "plan_before": (EXAMPLES / "sample-scan.sqlplan").read_text(encoding="utf-8"),
                        "plan_after": (EXAMPLES / "sample-seek.sqlplan").read_text(encoding="utf-8"),
                    })
                    return
                raise APIError(404, "not_found", "Route not found.")

            if method != "POST":
                raise APIError(405, "method", "Method not allowed.")
            body = self._post_body()
            if not WORK_LIMIT.acquire(blocking=False):
                raise APIError(429, "busy", "Too many concurrent benchmark requests.")
            try:
                if route == "/api/plan":
                    result = analyze_plan(body.get("xml"))
                elif route == "/api/plan/compare":
                    result = compare_plans(body.get("before"), body.get("after"))
                elif route == "/api/benchmark":
                    result = benchmark_query(body.get("sql"),
                        iterations=body.get("iterations", 7), warmups=body.get("warmups", 2))
                elif route == "/api/benchmark/compare":
                    result = compare_queries(body.get("before"), body.get("after"),
                        iterations=body.get("iterations", 7), warmups=body.get("warmups", 2))
                else:
                    raise APIError(404, "not_found", "Route not found.")
                self._send_json(200, {"ok": True, "result": result})
            finally:
                WORK_LIMIT.release()

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_PUT(self) -> None:
            self._handle("PUT")

        def do_DELETE(self) -> None:
            self._handle("DELETE")

        def _handle(self, method: str) -> None:
            try:
                self._route(method)
            except APIError as exc:
                self._send_json(exc.status, {"ok": False, "error": {"code": exc.code, "message": str(exc)}})
            except (BenchmarkError, PlanError) as exc:
                self._send_json(422, {"ok": False, "error": {"code": "input_error", "message": str(exc)}})
            except Exception:
                LOG.exception("Unhandled request exception")
                self._send_json(500, {"ok": False, "error": {"code": "internal", "message": "An unexpected error occurred."}})
    return Handler


def start_server(port: int = 8765) -> ThreadingHTTPServer:
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Use a local port from 1024 to 65535.")
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler())
    server.daemon_threads = True
    return server
