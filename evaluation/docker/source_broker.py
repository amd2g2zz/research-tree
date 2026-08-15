"""Capture public HTTPS sources without granting a runner arbitrary egress."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from http import HTTPStatus
from http.client import HTTPException, HTTPResponse, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4


ALLOWED_METHODS = frozenset({"GET", "HEAD"})
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
FORBIDDEN_HOSTNAMES = frozenset({"localhost", "localhost.localdomain", "metadata", "metadata.google.internal"})
SENSITIVE_QUERY_MARKERS = ("auth", "credential", "key", "password", "secret", "sig", "signature", "token")
SOURCE_CAPTURE_DIR = Path("/var/lib/research-tree/source-captures")
CAPTURE_METADATA_KEYS = ("captured_at", "final_url", "content_sha256", "content_ref", "status", "bytes")
MAX_URL_LENGTH = 4096
MAX_REDIRECTS = 4
MAX_CAPTURE_BYTES = 1 * 1024 * 1024
MAX_CONCURRENT_CAPTURES = 4
MAX_CAPTURE_REQUESTS = 64
REQUEST_TIMEOUT_SECONDS = 10
READ_CHUNK_BYTES = 64 * 1024


class SourceCaptureError(Exception):
    """Base error for a source request that cannot be safely captured."""


class InvalidSourceRequest(SourceCaptureError):
    """Raised when a runner request does not select one allowed public URL."""


class BlockedSource(SourceCaptureError):
    """Raised when a URL or resolved address is not public HTTPS."""


class CaptureLimitExceeded(SourceCaptureError):
    """Raised after the evaluator-configured capture count or size limit."""


class UpstreamUnavailable(SourceCaptureError):
    """Raised when no validated public address can serve the source."""


@dataclass(frozen=True)
class PublicHTTPSURL:
    """A normalized HTTPS destination with a host that must still be resolved."""

    raw_url: str
    host: str
    port: int
    request_target: str


@dataclass
class UpstreamCapture:
    """An open response and the connection pinned to a validated address."""

    connection: HTTPSConnection
    response: HTTPResponse
    final_url: str


class PinnedHTTPSConnection(HTTPSConnection):
    """Connect to one prevalidated address while preserving TLS hostname checks."""

    def __init__(self, host: str, port: int, pinned_address: str, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = pinned_address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_address, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class CaptureMetadataStore:
    """Persist evaluator-only source bytes plus a redacted, content-addressed receipt."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def record(self, metadata: dict[str, object], body: bytes) -> None:
        content_digest = f"sha256:{sha256(body).hexdigest()}"
        if metadata.get("content_sha256") != content_digest:
            raise OSError("capture content digest does not match body")
        content_root = self._root / "content"
        metadata_root = self._root / "metadata"
        content_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        metadata_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        content_name = f"{content_digest.removeprefix('sha256:')}.body"
        content_path = content_root / content_name
        if not content_path.exists():
            self._atomic_write(content_path, body)
        filtered = {**metadata, "content_ref": f"content/{content_name}"}
        filtered = {key: filtered[key] for key in CAPTURE_METADATA_KEYS}
        self._atomic_write(
            metadata_root / f"capture-{uuid4().hex}.json",
            json.dumps(filtered, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )

    def _atomic_write(self, path: Path, content: bytes) -> None:
        temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        file_descriptor = os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(file_descriptor, "wb") as output_file:
                output_file.write(content)
            os.replace(temporary_path, path)
            path.chmod(0o600)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def _normalize_public_https_url(value: str) -> PublicHTTPSURL:
    if not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH:
        raise InvalidSourceRequest("source URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise InvalidSourceRequest("source URL is invalid") from error
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise BlockedSource("only unauthenticated public HTTPS URLs are allowed")
    if port not in {None, 443}:
        raise BlockedSource("only HTTPS port 443 is allowed")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise InvalidSourceRequest("source URL host is invalid") from error
    if not host or _is_forbidden_hostname(host):
        raise BlockedSource("source host is not public")
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return PublicHTTPSURL(raw_url=value, host=host, port=443, request_target=request_target)


def _is_forbidden_hostname(host: str) -> bool:
    return host in FORBIDDEN_HOSTNAMES or host.endswith((".localhost", ".local"))


def _resolve_public_addresses(host: str) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise UpstreamUnavailable("source hostname could not be resolved") from error
    resolved: list[str] = []
    for _family, _socket_type, _protocol, _canonical_name, socket_address in records:
        try:
            address = ipaddress.ip_address(socket_address[0])
        except ValueError as error:
            raise BlockedSource("source hostname resolved to an invalid address") from error
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if not address.is_global:
            raise BlockedSource("source hostname resolved to a non-public address")
        rendered = str(address)
        if rendered not in resolved:
            resolved.append(rendered)
    if not resolved:
        raise UpstreamUnavailable("source hostname had no usable addresses")
    return tuple(resolved)


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("source request timed out")
    return remaining


def _open_pinned_request(
    method: str,
    target: PublicHTTPSURL,
    addresses: tuple[str, ...],
    deadline: float,
) -> tuple[HTTPSConnection, HTTPResponse]:
    last_error: BaseException | None = None
    for address in addresses:
        connection = PinnedHTTPSConnection(target.host, target.port, address, _remaining_seconds(deadline))
        try:
            connection.request(
                method,
                target.request_target,
                headers={"User-Agent": "ResearchTreeSourceBroker/1.0", "Accept": "*/*"},
            )
            return connection, connection.getresponse()
        except (HTTPException, OSError, ssl.SSLError) as error:
            last_error = error
            connection.close()
    raise UpstreamUnavailable("validated public source was unavailable") from last_error


def _open_public_capture(method: str, requested_url: str, deadline: float) -> UpstreamCapture:
    current_url = requested_url
    for redirect_count in range(MAX_REDIRECTS + 1):
        _remaining_seconds(deadline)
        target = _normalize_public_https_url(current_url)
        addresses = _resolve_public_addresses(target.host)
        connection, response = _open_pinned_request(method, target, addresses, deadline)
        if response.status not in REDIRECT_STATUS_CODES:
            return UpstreamCapture(connection=connection, response=response, final_url=current_url)
        location = response.getheader("Location")
        response.close()
        connection.close()
        if not location or redirect_count >= MAX_REDIRECTS:
            raise CaptureLimitExceeded("source redirect limit exceeded")
        current_url = urljoin(current_url, location)
    raise CaptureLimitExceeded("source redirect limit exceeded")


def _read_bounded_body(response: HTTPResponse, connection: HTTPSConnection, method: str, deadline: float) -> bytes:
    if method == "HEAD":
        return b""
    declared_size = response.getheader("Content-Length")
    if declared_size is not None:
        try:
            if int(declared_size) > MAX_CAPTURE_BYTES:
                raise CaptureLimitExceeded("source response exceeds byte limit")
        except ValueError as error:
            raise UpstreamUnavailable("source response length is invalid") from error
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        if connection.sock is not None:
            connection.sock.settimeout(_remaining_seconds(deadline))
        chunk = response.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > MAX_CAPTURE_BYTES:
            raise CaptureLimitExceeded("source response exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _metadata_url(value: str) -> str:
    parsed = urlsplit(value)
    redacted_query = [
        (key, "REDACTED" if any(marker in key.lower() for marker in SENSITIVE_QUERY_MARKERS) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(redacted_query), ""))


def _safe_content_type(value: str | None) -> str:
    if value is None or "\r" in value or "\n" in value:
        return "application/octet-stream"
    return value


class SourceCaptureHandler(BaseHTTPRequestHandler):
    """Expose one GET/HEAD capture endpoint and no evaluator metadata endpoint."""

    capture_slots = BoundedSemaphore(MAX_CONCURRENT_CAPTURES)
    capture_count = 0
    capture_count_lock = Lock()
    metadata_store = CaptureMetadataStore(SOURCE_CAPTURE_DIR)
    protocol_version = "HTTP/1.1"
    server_version = "ResearchTreeSourceBroker"
    sys_version = ""

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/healthz":
            self._respond(HTTPStatus.OK, b'{"status":"ready"}')
            return
        self._capture("GET")

    def do_HEAD(self) -> None:
        if urlsplit(self.path).path == "/healthz":
            self._respond(HTTPStatus.OK, b"", head_only=True)
            return
        self._capture("HEAD")

    def do_POST(self) -> None:
        self._respond(HTTPStatus.METHOD_NOT_ALLOWED, b'{"error":"method not allowed"}')

    def _capture(self, method: str) -> None:
        if method not in ALLOWED_METHODS:
            self._respond(HTTPStatus.METHOD_NOT_ALLOWED, b'{"error":"method not allowed"}')
            return
        requested_url = self._capture_url()
        if requested_url is None:
            return
        if not self.capture_slots.acquire(blocking=False):
            self._respond(HTTPStatus.TOO_MANY_REQUESTS, b'{"error":"capture concurrency limit reached"}')
            return
        try:
            if not self._claim_capture():
                self._respond(HTTPStatus.TOO_MANY_REQUESTS, b'{"error":"capture count limit reached"}')
                return
            deadline = monotonic() + REQUEST_TIMEOUT_SECONDS
            capture = _open_public_capture(method, requested_url, deadline)
            try:
                body = _read_bounded_body(capture.response, capture.connection, method, deadline)
                self._record_capture(capture.final_url, capture.response.status, body)
                self._respond(
                    HTTPStatus(capture.response.status),
                    body,
                    content_type=_safe_content_type(capture.response.getheader("Content-Type")),
                    head_only=method == "HEAD",
                )
            finally:
                capture.response.close()
                capture.connection.close()
        except InvalidSourceRequest:
            self._respond(HTTPStatus.BAD_REQUEST, b'{"error":"invalid source request"}')
        except BlockedSource:
            self._respond(HTTPStatus.FORBIDDEN, b'{"error":"source is not public HTTPS"}')
        except CaptureLimitExceeded:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b'{"error":"source capture limit reached"}')
        except (TimeoutError, socket.timeout):
            self._respond(HTTPStatus.GATEWAY_TIMEOUT, b'{"error":"source request timed out"}')
        except UpstreamUnavailable:
            self._respond(HTTPStatus.BAD_GATEWAY, b'{"error":"source unavailable"}')
        except OSError:
            self._respond(HTTPStatus.INTERNAL_SERVER_ERROR, b'{"error":"capture receipt unavailable"}')
        finally:
            self.capture_slots.release()

    def _capture_url(self) -> str | None:
        try:
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, strict_parsing=True, keep_blank_values=True)
        except ValueError:
            self._respond(HTTPStatus.BAD_REQUEST, b'{"error":"invalid source request"}')
            return None
        values = query.get("url")
        if parsed.path != "/capture" or set(query) != {"url"} or values is None or len(values) != 1:
            self._respond(HTTPStatus.BAD_REQUEST, b'{"error":"invalid source request"}')
            return None
        return values[0]

    def _claim_capture(self) -> bool:
        with self.capture_count_lock:
            if self.capture_count >= MAX_CAPTURE_REQUESTS:
                return False
            type(self).capture_count += 1
            return True

    def _record_capture(self, final_url: str, status: int, body: bytes) -> None:
        self.metadata_store.record(
            {
                "captured_at": datetime.now(UTC).isoformat(),
                "final_url": _metadata_url(final_url),
                "content_sha256": f"sha256:{sha256(body).hexdigest()}",
                "status": status,
                "bytes": len(body),
            },
            body,
        )

    def _respond(
        self,
        status: HTTPStatus,
        body: bytes,
        *,
        content_type: str = "application/json",
        head_only: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def log_message(self, message_format: str, *arguments: object) -> None:
        return


class SourceBrokerServer(ThreadingHTTPServer):
    """Use daemon request workers and a bounded listening queue."""

    daemon_threads = True
    request_queue_size = MAX_CONCURRENT_CAPTURES


def main() -> None:
    server = SourceBrokerServer(("0.0.0.0", 8081), SourceCaptureHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
