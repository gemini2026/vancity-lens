"""Verify JWT_SECRET has no insecure default fallback."""
from pathlib import Path

def test_jwt_secret_has_no_default():
    """JWT_SECRET must not have a hardcoded default value."""
    source_path = Path(__file__).parent.parent / "api" / "user_auth.py"
    source = source_path.read_text()
    assert "dev-secret-key-change-in-production" not in source, (
        "JWT_SECRET must not have a weak default fallback"
    )
