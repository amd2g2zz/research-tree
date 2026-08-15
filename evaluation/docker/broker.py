"""Serve as the only credential-bearing gateway for an evaluation runner."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_ANTHROPIC_MESSAGES_URL = "https://api.deepseek.com/anthropic/v1/messages"
ALLOWED_DESTINATIONS = {
    "/v1/chat/completions": DEEPSEEK_CHAT_COMPLETIONS_URL,
    "/anthropic/v1/messages": DEEPSEEK_ANTHROPIC_MESSAGES_URL,
}
SECRET_FILE = "/run/secrets/deepseek_api_key"
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024
REQUEST_TIMEOUT_SECONDS = 60


def _load_api_key() -> str:
    api_key = Path("/run/secrets/deepseek_api_key").read_text(encoding="utf-8").strip()
    return api_key


class BrokerRequestHandler(BaseHTTPRequestHandler):
    """Accept only one local path and forward it to one fixed upstream URL."""

    api_key = ""
    protocol_version = "HTTP/1.1"
    server_version = "ResearchTreeEvaluationBroker"
    sys_version = ""

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._respond(HTTPStatus.OK, b'{"status":"ready"}')
            return
        self._respond(HTTPStatus.NOT_FOUND, b'{"error":"not found"}')

    def do_POST(self) -> None:
        destination = ALLOWED_DESTINATIONS.get(self.path)
        if destination is None:
            self._respond(HTTPStatus.NOT_FOUND, b'{"error":"not found"}')
            return
        if not self.api_key:
            self._respond(HTTPStatus.SERVICE_UNAVAILABLE, b'{"error":"broker is not configured"}')
            return
        content_length = self._content_length()
        if content_length is None:
            return
        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self._respond(HTTPStatus.BAD_REQUEST, b'{"error":"incomplete request body"}')
            return
        request = Request(
            destination,
            data=body,
            headers=self._upstream_headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                if response.headers.get_content_type() == "text/event-stream":
                    self._stream_response(HTTPStatus(response.status), response)
                    return
                response_body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(response_body) > MAX_RESPONSE_BYTES:
                    self._respond(HTTPStatus.BAD_GATEWAY, b'{"error":"upstream response too large"}')
                    return
                self._respond(HTTPStatus(response.status), response_body)
        except HTTPError as error:
            self._respond(HTTPStatus(error.code), b'{"error":"upstream request failed"}')
        except (TimeoutError, URLError, ValueError):
            self._respond(HTTPStatus.BAD_GATEWAY, b'{"error":"upstream unavailable"}')

    def _upstream_headers(self) -> dict[str, str]:
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
        if self.path == "/anthropic/v1/messages":
            headers["x-api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _content_length(self) -> int | None:
        value = self.headers.get("Content-Length")
        try:
            content_length = int(value) if value is not None else -1
        except ValueError:
            self._respond(HTTPStatus.BAD_REQUEST, b'{"error":"invalid content length"}')
            return None
        if content_length < 0:
            self._respond(HTTPStatus.LENGTH_REQUIRED, b'{"error":"content length is required"}')
            return None
        if content_length > MAX_REQUEST_BYTES:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b'{"error":"request body too large"}')
            return None
        return content_length

    def _respond(self, status: HTTPStatus, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_response(self, status: HTTPStatus, response) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while chunk := response.read(STREAM_CHUNK_BYTES):
                self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                self.wfile.write(chunk)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, message_format: str, *arguments: object) -> None:
        return


def main() -> None:
    BrokerRequestHandler.api_key = _load_api_key()
    server = ThreadingHTTPServer(("0.0.0.0", 8080), BrokerRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
