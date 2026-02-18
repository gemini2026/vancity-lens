"""Knowledge2 Python SDK."""

from ._base import ClientLimits
from ._logging import set_debug
from .client import Knowledge2
from .errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    ConflictError,
    Knowledge2Error,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)

__version__ = "0.1.0"

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "AuthenticationError",
    "ClientLimits",
    "ConflictError",
    "Knowledge2",
    "Knowledge2Error",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "ValidationError",
    "__version__",
    "set_debug",
]
