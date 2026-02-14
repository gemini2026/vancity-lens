"""Verify all report endpoints require authentication."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("api.db.db") as mock_db:
        mock_db.pool = MagicMock()
        from api.main import app
        # Set app.state.pool so get_current_user_from_request finds a pool
        # and proceeds to the actual credential check (which returns 401).
        app.state.pool = MagicMock()
        yield TestClient(app, raise_server_exceptions=False)
        # Clean up
        app.state.pool = None


def test_report_pdf_requires_auth(client):
    resp = client.get("/api/v1/parcels/123-456-789/report.pdf")
    assert resp.status_code in (401, 403), f"got {resp.status_code}"


def test_report_preview_requires_auth(client):
    resp = client.get("/api/v1/parcels/123-456-789/report/preview")
    assert resp.status_code in (401, 403), f"got {resp.status_code}"


def test_investor_memo_requires_auth(client):
    resp = client.get("/api/v1/parcels/123-456-789/memo.pdf")
    assert resp.status_code in (401, 403), f"got {resp.status_code}"


def test_batch_report_create_requires_auth(client):
    resp = client.post("/api/v1/reports/batch?pids=123")
    assert resp.status_code in (401, 403), f"got {resp.status_code}"
