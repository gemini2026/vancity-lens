"""
Prometheus metrics instrumentation for VanCity Lens (VCL-49 / INFRA-007)

Provides:
- PrometheusMetrics class with counters, histograms, and gauges
- PrometheusMiddleware for automatic request tracking
- Helper functions to update pool and cache metrics
- /metrics endpoint using prometheus_client

Metrics tracked:
- request_duration_seconds: Request latency histogram (method, endpoint, status)
- api_calls_total: API call counter (method, endpoint, status)
- db_pool_size: Database pool gauge (pool_name, state)
- cache_hit_ratio: Cache hit ratio gauge
- active_requests: Active request count gauge
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
)

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Prometheus Metrics Definitions
# ────────────────────────────────────────────────────────────────────────────


class PrometheusMetrics:
    """
    Prometheus metrics singleton for VanCity Lens.

    Provides request tracking, pool monitoring, and cache metrics.
    """

    _instance: Optional[PrometheusMetrics] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize Prometheus metrics (singleton pattern)."""
        if self._initialized:
            return

        # Request duration histogram (seconds)
        # Labels: method (GET, POST, etc.), endpoint (path), status (200, 404, etc.)
        self.request_duration_seconds = Histogram(
            name="request_duration_seconds",
            documentation="HTTP request duration in seconds",
            labelnames=["method", "endpoint", "status"],
            buckets=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.075,
                0.1,
                0.25,
                0.5,
                0.75,
                1.0,
                2.5,
                5.0,
            ),
        )

        # API calls counter
        # Labels: method, endpoint, status
        self.api_calls_total = Counter(
            name="api_calls_total",
            documentation="Total number of API calls",
            labelnames=["method", "endpoint", "status"],
        )

        # Active requests gauge
        self.active_requests = Gauge(
            name="active_requests",
            documentation="Number of currently active requests",
        )

        # Database pool size gauge
        # Labels: pool_name (e.g., "main"), state (active, idle, total)
        self.db_pool_size = Gauge(
            name="db_pool_size",
            documentation="Database connection pool size",
            labelnames=["pool_name", "state"],
        )

        # Cache hit ratio gauge
        self.cache_hit_ratio = Gauge(
            name="cache_hit_ratio",
            documentation="Cache hit ratio (0.0-1.0)",
        )

        # Cache metrics
        self.cache_hits_total = Counter(
            name="cache_hits_total",
            documentation="Total number of cache hits",
        )

        self.cache_misses_total = Counter(
            name="cache_misses_total",
            documentation="Total number of cache misses",
        )

        # Error metrics
        self.errors_total = Counter(
            name="errors_total",
            documentation="Total number of errors",
            labelnames=["endpoint", "status"],
        )

        self._initialized = True
        logger.info("PrometheusMetrics initialized")

    def update_pool_metrics(
        self,
        pool_name: str = "main",
        active: int = 0,
        idle: int = 0,
        total: int = 0,
    ):
        """
        Update database pool metrics.

        Args:
            pool_name: Name of the pool (default: "main")
            active: Number of active connections
            idle: Number of idle connections
            total: Total pool size
        """
        self.db_pool_size.labels(pool_name=pool_name, state="active").set(active)
        self.db_pool_size.labels(pool_name=pool_name, state="idle").set(idle)
        self.db_pool_size.labels(pool_name=pool_name, state="total").set(total)

    def update_cache_metrics(self, hits: int = 0, misses: int = 0):
        """
        Update cache metrics.

        Args:
            hits: Number of cache hits
            misses: Number of cache misses
        """
        total = hits + misses
        ratio = hits / total if total > 0 else 0.0
        self.cache_hit_ratio.set(ratio)

    def record_request(
        self,
        method: str,
        endpoint: str,
        status: int,
        duration: float,
    ):
        """
        Record a request in metrics.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Endpoint path
            status: HTTP status code
            duration: Request duration in seconds
        """
        self.request_duration_seconds.labels(
            method=method, endpoint=endpoint, status=str(status)
        ).observe(duration)
        self.api_calls_total.labels(
            method=method, endpoint=endpoint, status=str(status)
        ).inc()

        # Track errors separately
        if status >= 400:
            self.errors_total.labels(endpoint=endpoint, status=str(status)).inc()

    def increment_active_requests(self):
        """Increment active request counter."""
        self.active_requests.inc()

    def decrement_active_requests(self):
        """Decrement active request counter."""
        self.active_requests.dec()

    def get_metrics(self) -> bytes:
        """
        Get Prometheus metrics in text format.

        Returns:
            Metrics in Prometheus exposition format
        """
        return generate_latest()


# ────────────────────────────────────────────────────────────────────────────
# Prometheus Middleware
# ────────────────────────────────────────────────────────────────────────────


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically track request metrics.

    Tracks:
    - Request duration (histogram)
    - Request count (counter)
    - Active requests (gauge)
    - Error rate (counter)
    """

    # Exclude certain endpoints from metrics (health checks, metrics endpoint itself)
    EXCLUDED_PATHS = {"/health", "/ready", "/metrics"}

    def __init__(self, app):
        super().__init__(app)
        self.metrics = PrometheusMetrics()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through middleware.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from handler
        """
        # Skip metrics for excluded endpoints
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        # Track active requests
        self.metrics.increment_active_requests()
        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Track error
            self.metrics.decrement_active_requests()
            raise
        finally:
            # Always decrement active requests
            self.metrics.decrement_active_requests()

        # Record request metrics
        duration = time.time() - start_time
        endpoint = request.url.path
        method = request.method

        self.metrics.record_request(
            method=method,
            endpoint=endpoint,
            status=status_code,
            duration=duration,
        )

        return response


# ────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────────────────


def get_metrics() -> PrometheusMetrics:
    """Get the global PrometheusMetrics instance."""
    return PrometheusMetrics()
