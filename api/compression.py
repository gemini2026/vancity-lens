"""
VanCity Lens — Response Compression Middleware
Implements VCL-71 [PERF-009] — gzip compression for JSON/GeoJSON responses.

Compresses HTTP responses that:
- Have Accept-Encoding: gzip support (from client)
- Exceed COMPRESSION_MIN_SIZE (default: 1KB)
- Have compressible content types (application/json, application/geo+json)
- Are not streaming responses

Environment variables:
- COMPRESSION_ENABLED: Enable/disable middleware (default: true)
- COMPRESSION_MIN_SIZE: Minimum response size to compress in bytes (default: 1024)
- COMPRESSION_LEVEL: gzip compression level 1-9 (default: 6)
"""

import gzip
import io
import os

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send, Message


# ── Configuration ─────────────────────────────────────────────────────────

COMPRESSION_ENABLED = os.getenv("COMPRESSION_ENABLED", "true").lower() == "true"
COMPRESSION_MIN_SIZE = int(os.getenv("COMPRESSION_MIN_SIZE", "1024"))
COMPRESSION_LEVEL = int(os.getenv("COMPRESSION_LEVEL", "6"))

# Content types that should be compressed
COMPRESSIBLE_TYPES = {
    "application/json",
    "application/geo+json",
}


# ── Compression Middleware ────────────────────────────────────────────────


class CompressionMiddleware:
    """
    ASGI middleware that compresses responses using gzip.

    Proper ASGI middleware (not BaseHTTPMiddleware) that:
    - Checks Accept-Encoding header for gzip support
    - Only compresses responses > COMPRESSION_MIN_SIZE
    - Only compresses JSON and GeoJSON content types
    - Sets Content-Encoding and Vary headers
    - Skips streaming responses
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            # Pass through non-HTTP requests (WebSocket, etc.)
            await self.app(scope, receive, send)
            return

        if not COMPRESSION_ENABLED:
            # Compression disabled via environment variable
            await self.app(scope, receive, send)
            return

        # Check if client accepts gzip encoding
        headers = Headers(raw=scope.get("headers", []))
        accept_encoding = headers.get("accept-encoding", "")
        supports_gzip = "gzip" in accept_encoding.lower()

        # Always wrap send to add Vary header (indicates response could vary by Accept-Encoding)
        send = _compress_send(send, supports_gzip=supports_gzip)
        await self.app(scope, receive, send)


def _compress_send(send: Send, supports_gzip: bool = False) -> Send:
    """Create a wrapped send callable that compresses the response body."""
    send = _CachedResponder(send, supports_gzip=supports_gzip)

    async def wrapped_send(message: Message) -> None:
        if message["type"] == "http.response.start":
            # Cache the response start message for potential compression
            await send(message)
        elif message["type"] == "http.response.body":
            # Handle response body compression
            await send(message)
        else:
            # Pass through other message types
            await send(message)

    return wrapped_send


class _CachedResponder:
    """
    Caches response metadata and body to enable compression.

    Intercepts the response start and body messages to:
    1. Check if response should be compressed
    2. Buffer the body if small enough
    3. Compress and update headers if needed
    4. Send compressed or original response
    """

    def __init__(self, send: Send, supports_gzip: bool = False):
        self.send = send
        self.supports_gzip = supports_gzip
        self.status_code: int | None = None
        self.headers: dict[str, str] = {}
        self.body_parts: list[bytes] = []
        self.response_started = False
        self.stream_response = False

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.response_started = True
            self.status_code = message["status"]

            # Parse headers
            for header_name, header_value in message.get("headers", []):
                self.headers[header_name.decode().lower()] = header_value.decode()

            # Check if this is a streaming response (has Transfer-Encoding)
            if "transfer-encoding" in self.headers:
                self.stream_response = True
                # Stream responses must be sent as-is
                await self.send(message)

        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if self.stream_response or more_body:
                # Streaming response or continuation - send immediately
                if body:
                    await self.send(
                        {
                            "type": "http.response.body",
                            "body": body,
                            "more_body": more_body,
                        }
                    )
            else:
                # Final body chunk - decide on compression
                self.body_parts.append(body)
                full_body = b"".join(self.body_parts)

                if self._should_compress():
                    # Compress the response
                    compressed_body = self._compress_body(full_body)

                    # Update response headers
                    new_headers = self._get_compressed_headers()

                    # Send response start with new headers
                    await self.send(
                        {
                            "type": "http.response.start",
                            "status": self.status_code,
                            "headers": new_headers,
                        }
                    )

                    # Send compressed body
                    await self.send(
                        {
                            "type": "http.response.body",
                            "body": compressed_body,
                            "more_body": False,
                        }
                    )
                else:
                    # Send uncompressed but with Vary header
                    await self.send(
                        {
                            "type": "http.response.start",
                            "status": self.status_code,
                            "headers": self._get_uncompressed_headers(),
                        }
                    )

                    await self.send(
                        {
                            "type": "http.response.body",
                            "body": full_body,
                            "more_body": False,
                        }
                    )

    def _should_compress(self) -> bool:
        """Check if response should be compressed."""
        # Must support gzip
        if not self.supports_gzip:
            return False

        # Check status code (only compress 2xx responses)
        if self.status_code and self.status_code < 200 or self.status_code >= 300:
            return False

        # Check content type
        content_type = self.headers.get("content-type", "").lower()
        if not any(ct in content_type for ct in COMPRESSIBLE_TYPES):
            return False

        # Check body size
        body_size = sum(len(part) for part in self.body_parts)
        if body_size < COMPRESSION_MIN_SIZE:
            return False

        return True

    def _compress_body(self, body: bytes) -> bytes:
        """Compress body using gzip."""
        buf = io.BytesIO()
        with gzip.GzipFile(
            fileobj=buf, mode="wb", compresslevel=COMPRESSION_LEVEL
        ) as gz:
            gz.write(body)
        return buf.getvalue()

    def _get_compressed_headers(self) -> list[tuple[bytes, bytes]]:
        """Build response headers for compressed response."""
        headers = []

        # Add all original headers except content-length (will be different)
        for name, value in self.headers.items():
            if name not in ("content-length", "content-encoding"):
                headers.append((name.encode(), value.encode()))

        # Add compression headers
        headers.append((b"content-encoding", b"gzip"))

        # Ensure Vary header includes Accept-Encoding
        vary = None
        for name, value in headers:
            if name.lower() == b"vary":
                vary = value.decode()
                break

        if vary:
            if "Accept-Encoding" not in vary:
                vary += ", Accept-Encoding"
            # Remove old vary header
            headers = [(n, v) for n, v in headers if n.lower() != b"vary"]
            headers.append((b"vary", vary.encode()))
        else:
            headers.append((b"vary", b"Accept-Encoding"))

        return headers

    def _get_uncompressed_headers(self) -> list[tuple[bytes, bytes]]:
        """Build response headers for uncompressed response (with Vary header)."""
        headers = []

        # Add all original headers
        for name, value in self.headers.items():
            if name.lower() != "vary":
                headers.append((name.encode(), value.encode()))

        # Always add Vary: Accept-Encoding (indicates response could be compressed)
        vary = None
        for name, value in self.headers.items():
            if name.lower() == "vary":
                vary = value
                break

        if vary:
            if "Accept-Encoding" not in vary:
                vary += ", Accept-Encoding"
        else:
            vary = "Accept-Encoding"

        headers.append((b"vary", vary.encode()))
        return headers

    def _get_original_headers(self) -> list[tuple[bytes, bytes]]:
        """Build response headers for uncompressed response."""
        return [(name.encode(), value.encode()) for name, value in self.headers.items()]
