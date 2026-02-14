"""Verify admin key comparison uses constant-time algorithm."""
import inspect
from api.auth import require_admin

def test_admin_key_uses_constant_time_comparison():
    """The require_admin function must use hmac.compare_digest, not == or !=."""
    source = inspect.getsource(require_admin)
    assert "hmac.compare_digest" in source, (
        "require_admin must use hmac.compare_digest for constant-time comparison"
    )
    assert "api_key != expected" not in source, (
        "require_admin must not use != for secret comparison (timing attack)"
    )
