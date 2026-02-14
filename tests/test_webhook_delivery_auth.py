"""Verify webhook delivery status requires authentication."""
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


def test_delivery_status_requires_auth(client):
    resp = client.get("/api/v1/webhooks/deliveries/fake-id")
    assert resp.status_code in (401, 403), f"got {resp.status_code}"
