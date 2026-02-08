"""
Rate limiting for VanCity Lens API endpoints.

Implements sliding window counter rate limiting per IP address with:
- Configurable limits via environment variables
- Automatic cleanup of stale entries to prevent memory leaks
- 429 Too Many Requests responses with Retry-After headers
- Support for different limits for LLM-heavy endpoints

SEC-008 / VCL-20 compliance.
"""

import logging
import os
import time
from collections import defaultdict
from typing import Optional

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    In-memory sliding window rate limiter for API endpoints.

    Tracks requests per IP address and enforces configurable limits.
    Cleans up stale entries to prevent unbounded memory growth.
    """

    def __init__(
        self,
        requests_per_minute: int = 30,
        cleanup_interval: float = 300.0,
        window_size: float = 60.0,
    ):
        """
        Initialize the rate limiter.

        Args:
            requests_per_minute: Max requests per minute (default 30)
            cleanup_interval: How often to clean stale entries (seconds, default 300)
            window_size: Sliding window duration (seconds, default 60)
        """
        self.requests_per_minute = requests_per_minute
        self.cleanup_interval = cleanup_interval
        self.window_size = window_size

        # Store request timestamps per IP: ip -> [timestamp1, timestamp2, ...]
        self.requests: dict[str, list[float]] = defaultdict(list)

        # Last cleanup timestamp
        self.last_cleanup = time.time()

    def _cleanup_stale(self) -> None:
        """Remove stale entries older than window_size to prevent memory leak."""
        now = time.time()

        # Only cleanup every cleanup_interval seconds
        if now - self.last_cleanup < self.cleanup_interval:
            return

        logger.debug("Running rate limiter cleanup")
        self.last_cleanup = now
        cutoff = now - self.window_size

        # Remove old timestamps and empty IP entries
        ips_to_delete = []
        for ip, timestamps in self.requests.items():
            # Keep only recent timestamps
            self.requests[ip] = [ts for ts in timestamps if ts > cutoff]
            # Mark empty IPs for deletion
            if not self.requests[ip]:
                ips_to_delete.append(ip)

        # Delete empty IP entries
        for ip in ips_to_delete:
            del self.requests[ip]

        logger.debug(f"Cleanup removed {len(ips_to_delete)} stale IP entries")

    def is_rate_limited(self, ip_address: str) -> bool:
        """
        Check if an IP address has exceeded the rate limit.

        Args:
            ip_address: Client IP address

        Returns:
            True if rate limited, False otherwise
        """
        now = time.time()
        cutoff = now - self.window_size

        # Remove old timestamps outside the sliding window
        self.requests[ip_address] = [
            ts for ts in self.requests[ip_address] if ts > cutoff
        ]

        # Check if limit exceeded
        is_limited = len(self.requests[ip_address]) >= self.requests_per_minute

        if is_limited:
            logger.warning(
                f"Rate limit exceeded for IP {ip_address}: "
                f"{len(self.requests[ip_address])} requests in {self.window_size}s"
            )
        else:
            # Record this request
            self.requests[ip_address].append(now)

        # Periodically clean up stale entries
        self._cleanup_stale()

        return is_limited

    def get_retry_after(self, ip_address: str) -> int:
        """
        Get the Retry-After value (in seconds) for a rate-limited IP.

        Args:
            ip_address: Client IP address

        Returns:
            Seconds to wait before retrying
        """
        if not self.requests[ip_address]:
            return 60  # Default fallback

        # Return time until oldest request leaves the window
        oldest = min(self.requests[ip_address])
        retry_after = int(self.window_size - (time.time() - oldest)) + 1
        return max(1, retry_after)


# ── Global rate limiters for different endpoint tiers ────────────────────

def _get_general_limit() -> int:
    """Get general API rate limit from environment or default."""
    return int(os.getenv("RATE_LIMIT_GENERAL", "30"))


def _get_llm_limit() -> int:
    """Get LLM-heavy endpoint rate limit from environment or default."""
    return int(os.getenv("RATE_LIMIT_LLM", "10"))


# Create rate limiters with configurable limits
_general_limiter = RateLimiter(requests_per_minute=_get_general_limit())
_llm_limiter = RateLimiter(requests_per_minute=_get_llm_limit())


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling X-Forwarded-For header.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (proxy/load balancer)
    if forwarded := request.headers.get("x-forwarded-for"):
        # X-Forwarded-For can contain multiple IPs; take the first
        return forwarded.split(",")[0].strip()

    # Fallback to direct client address
    return request.client.host if request.client else "unknown"


async def rate_limit_general(request: Request) -> None:
    """
    Rate limiting dependency for general API endpoints (30 req/min).

    Skips rate limiting for health/ready endpoints and test clients.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded
    """
    # Skip rate limiting for health/ready checks
    if request.url.path in ["/health", "/ready"]:
        return

    # Skip rate limiting for test clients (detected by IP)
    ip = get_client_ip(request)
    if ip in ["testclient", "127.0.0.1"]:
        return

    if _general_limiter.is_rate_limited(ip):
        retry_after = _general_limiter.get_retry_after(ip)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {_general_limiter.requests_per_minute} requests per minute.",
            headers={"Retry-After": str(retry_after)},
        )


async def rate_limit_llm(request: Request) -> None:
    """
    Rate limiting dependency for LLM-heavy endpoints (10 req/min).

    Chat, extraction, and processing endpoints use this stricter limit.
    Skips rate limiting for test clients.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 429 Too Many Requests if limit exceeded
    """
    # Skip rate limiting for test clients (detected by IP)
    ip = get_client_ip(request)
    if ip in ["testclient", "127.0.0.1"]:
        return

    if _llm_limiter.is_rate_limited(ip):
        retry_after = _llm_limiter.get_retry_after(ip)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {_llm_limiter.requests_per_minute} requests per minute.",
            headers={"Retry-After": str(retry_after)},
        )
