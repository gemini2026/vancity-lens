"""Verify no hardcoded API keys in admin module."""
from pathlib import Path

def test_no_hardcoded_rapidapi_key():
    """RAPIDAPI_KEY must not be a string literal in source code."""
    source_path = Path(__file__).parent.parent / "api" / "admin.py"
    source = source_path.read_text()
    assert "7b25957278msh" not in source, (
        "Hardcoded RapidAPI key found in admin.py -- must use os.environ.get()"
    )

def test_rapidapi_key_loaded_from_env():
    """RAPIDAPI_KEY must be loaded from environment variable."""
    source_path = Path(__file__).parent.parent / "api" / "admin.py"
    source = source_path.read_text()
    assert 'os.environ.get("RAPIDAPI_KEY"' in source or "os.environ.get('RAPIDAPI_KEY'" in source, (
        "RAPIDAPI_KEY must be loaded via os.environ.get()"
    )
