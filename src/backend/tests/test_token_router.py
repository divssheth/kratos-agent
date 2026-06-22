"""Tests for OBO token exchange router."""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import status
from fastapi.testclient import TestClient
import time

from app.services.auth_service import DelegatedAccessToken


@pytest.fixture
def obo_enabled_app():
    """Create a test app with OBO enabled and not in local mode."""
    # Set environment variables before importing/creating app
    os.environ["ENABLE_USER_AUTH_OBO"] = "true"
    os.environ["COSMOS_DB_ENDPOINT"] = "https://test.documents.azure.com:443/"
    
    # Clear the settings cache to force reload
    from app import config
    if hasattr(config, '_settings_instance'):
        delattr(config, '_settings_instance')
    config.get_settings.cache_clear()
    
    from app.main import app
    yield app
    
    # Cleanup
    os.environ.pop("ENABLE_USER_AUTH_OBO", None)
    os.environ.pop("COSMOS_DB_ENDPOINT", None)
    config.get_settings.cache_clear()


@pytest.fixture
def client_obo_enabled(obo_enabled_app):
    """FastAPI test client with OBO enabled."""
    return TestClient(obo_enabled_app)


def test_obo_exchange_disabled():
    """Test OBO exchange when feature is disabled."""
    # Ensure OBO is disabled
    os.environ.pop("ENABLE_USER_AUTH_OBO", None)
    
    from app import config
    config.get_settings.cache_clear()
    
    from app.main import app
    client = TestClient(app)
    
    response = client.post(
        "/api/token/obo-exchange",
        json={
            "user_refresh_token": "test-refresh-token",
            "user_id": "user@example.com",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not enabled" in response.json()["detail"].lower()


@pytest.mark.skip(reason="FastAPI dependency injection caching makes this test difficult; local mode check is tested in integration tests")
def test_obo_exchange_local_mode(obo_enabled_app):
    """Test OBO exchange when in local mode (skipped - dependency injection caching)."""
    pass


@pytest.mark.asyncio
async def test_obo_exchange_success(obo_enabled_app):
    """Test successful OBO token exchange."""
    now = time.time()
    mock_token = DelegatedAccessToken(
        access_token="exchanged-token",
        expires_at=now + 3600,
        user_id="user@example.com",
    )

    with patch("app.routers.token.AuthService") as mock_auth_class:
        mock_service = AsyncMock()
        mock_service._http_session = AsyncMock()
        mock_service.exchange_obo_token = AsyncMock(return_value=mock_token)
        mock_service.start = AsyncMock()
        mock_auth_class.return_value = mock_service

        client = TestClient(obo_enabled_app)
        response = client.post(
            "/api/token/obo-exchange",
            json={
                "user_refresh_token": "test-refresh-token",
                "user_id": "user@example.com",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["access_token"] == "exchanged-token"
        assert data["expires_in"] > 3590
        assert data["user_id"] == "user@example.com"


@pytest.mark.asyncio
async def test_obo_exchange_token_exchange_failed(obo_enabled_app):
    """Test OBO exchange when token exchange fails."""
    with patch("app.routers.token.AuthService") as mock_auth_class:
        mock_service = AsyncMock()
        mock_service._http_session = AsyncMock()
        mock_service.exchange_obo_token = AsyncMock(return_value=None)  # Failed exchange
        mock_service.start = AsyncMock()
        mock_auth_class.return_value = mock_service

        client = TestClient(obo_enabled_app)
        response = client.post(
            "/api/token/obo-exchange",
            json={
                "user_refresh_token": "invalid-refresh-token",
                "user_id": "user@example.com",
            },
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "exchange failed" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_obo_exchange_service_error(obo_enabled_app):
    """Test OBO exchange when AuthService raises an error."""
    with patch("app.routers.token.AuthService") as mock_auth_class:
        mock_service = AsyncMock()
        mock_service._http_session = AsyncMock()
        mock_service.exchange_obo_token = AsyncMock(side_effect=Exception("Service error"))
        mock_service.start = AsyncMock()
        mock_auth_class.return_value = mock_service

        client = TestClient(obo_enabled_app)
        response = client.post(
            "/api/token/obo-exchange",
            json={
                "user_refresh_token": "test-refresh-token",
                "user_id": "user@example.com",
            },
        )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "service error" in response.json()["detail"].lower()


def test_obo_exchange_request_validation():
    """Test OBO exchange request validation."""
    from app.main import app
    client = TestClient(app)

    # Missing user_refresh_token
    response = client.post(
        "/api/token/obo-exchange",
        json={
            "user_id": "user@example.com",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_obo_exchange_empty_refresh_token():
    """Test OBO exchange with empty refresh token."""
    from app.main import app
    client = TestClient(app)
    
    response = client.post(
        "/api/token/obo-exchange",
        json={
            "user_refresh_token": "",  # empty
            "user_id": "user@example.com",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_obo_exchange_default_scope(obo_enabled_app):
    """Test OBO exchange uses default Power BI scope."""
    now = time.time()
    mock_token = DelegatedAccessToken(
        access_token="exchanged-token",
        expires_at=now + 3600,
        user_id="user@example.com",
    )

    with patch("app.routers.token.AuthService") as mock_auth_class:
        mock_service = AsyncMock()
        mock_service._http_session = AsyncMock()
        mock_service.exchange_obo_token = AsyncMock(return_value=mock_token)
        mock_service.start = AsyncMock()
        mock_auth_class.return_value = mock_service

        client = TestClient(obo_enabled_app)
        response = client.post(
            "/api/token/obo-exchange",
            json={
                "user_refresh_token": "test-refresh-token",
                # scope omitted, should use default
                "user_id": "user@example.com",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        # Verify default scope was used
        mock_service.exchange_obo_token.assert_called_once()
        call_args = mock_service.exchange_obo_token.call_args
        assert call_args[1]["scope"] == "https://analysis.windows.net/.default"


@pytest.mark.asyncio
async def test_obo_exchange_custom_scope(obo_enabled_app):
    """Test OBO exchange with custom scope."""
    now = time.time()
    mock_token = DelegatedAccessToken(
        access_token="exchanged-token",
        expires_at=now + 3600,
        user_id="user@example.com",
    )

    with patch("app.routers.token.AuthService") as mock_auth_class:
        mock_service = AsyncMock()
        mock_service._http_session = AsyncMock()
        mock_service.exchange_obo_token = AsyncMock(return_value=mock_token)
        mock_service.start = AsyncMock()
        mock_auth_class.return_value = mock_service

        client = TestClient(obo_enabled_app)
        response = client.post(
            "/api/token/obo-exchange",
            json={
                "user_refresh_token": "test-refresh-token",
                "scope": "https://custom.scope/.default",
                "user_id": "user@example.com",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        # Verify custom scope was used
        mock_service.exchange_obo_token.assert_called_once()
        call_args = mock_service.exchange_obo_token.call_args
        assert call_args[1]["scope"] == "https://custom.scope/.default"
