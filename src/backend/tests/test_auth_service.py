"""Tests for OBO token exchange and context management."""

import time
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.auth_service import AuthService, DelegatedAccessToken


class MockSettings:
    """Mock settings for testing."""

    enable_user_auth_obo = True
    azure_tenant_id = "test-tenant-id"
    azure_client_id = "test-client-id"
    azure_client_secret = "test-client-secret"


def test_delegated_access_token_ttl():
    """Test token TTL calculation."""
    now = time.time()
    token = DelegatedAccessToken(
        access_token="test-token",
        expires_at=now + 3600,
        user_id="user@example.com",
    )
    assert token.ttl_seconds > 3590
    assert token.ttl_seconds <= 3600
    assert not token.is_expired


def test_delegated_access_token_expired():
    """Test token expiration detection."""
    now = time.time()
    token = DelegatedAccessToken(
        access_token="test-token",
        expires_at=now - 100,  # already expired
        user_id="user@example.com",
    )
    assert token.is_expired
    assert token.ttl_seconds == 0


def test_delegated_access_token_expiring_soon():
    """Test token refresh buffer (60s before actual expiry)."""
    now = time.time()
    token = DelegatedAccessToken(
        access_token="test-token",
        expires_at=now + 30,  # expires in 30s, but refresh buffer is 60s
        user_id="user@example.com",
    )
    assert token.is_expired  # should trigger refresh


def test_auth_service_init_obo_disabled():
    """Test AuthService initialization with OBO disabled."""
    settings = MockSettings()
    settings.enable_user_auth_obo = False
    service = AuthService(settings)
    assert not service.obo_enabled


def test_auth_service_init_obo_enabled():
    """Test AuthService initialization with OBO enabled."""
    settings = MockSettings()
    service = AuthService(settings)
    assert service.obo_enabled
    assert service.tenant_id == "test-tenant-id"
    assert service.client_id == "test-client-id"


def test_auth_service_init_incomplete_config():
    """Test AuthService with incomplete OBO config."""
    settings = MockSettings()
    settings.azure_tenant_id = ""  # missing tenant_id
    service = AuthService(settings)
    # Should initialize but log warning
    assert service.obo_enabled


@pytest.mark.asyncio
async def test_exchange_obo_token_success():
    """Test successful token exchange via OBO flow."""
    settings = MockSettings()
    service = AuthService(settings)
    service._http_session = AsyncMock()

    mock_response = AsyncMock()
    # Mock the json() method to return a coroutine that returns the dict
    mock_response.json = AsyncMock(
        return_value={
            "access_token": "exchanged-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    mock_response.raise_for_status = AsyncMock()
    service._http_session.post = AsyncMock(return_value=mock_response)

    token = await service.exchange_obo_token(
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert token is not None
    assert token.access_token == "exchanged-access-token"
    assert token.ttl_seconds > 3590
    assert token.user_id == "user@example.com"


@pytest.mark.asyncio
async def test_exchange_obo_token_empty_refresh():
    """Test token exchange with empty refresh token."""
    settings = MockSettings()
    service = AuthService(settings)
    service._http_session = AsyncMock()

    token = await service.exchange_obo_token(
        user_refresh_token="",
        user_id="user@example.com",
    )

    assert token is None
    service._http_session.post.assert_not_called()


@pytest.mark.asyncio
async def test_exchange_obo_token_no_session():
    """Test token exchange when HTTP session not initialized."""
    settings = MockSettings()
    service = AuthService(settings)
    # Don't initialize _http_session

    token = await service.exchange_obo_token(
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert token is None


@pytest.mark.asyncio
async def test_exchange_obo_token_obo_disabled():
    """Test token exchange when OBO is disabled."""
    settings = MockSettings()
    settings.enable_user_auth_obo = False
    service = AuthService(settings)
    service._http_session = AsyncMock()

    token = await service.exchange_obo_token(
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert token is None
    service._http_session.post.assert_not_called()


@pytest.mark.asyncio
async def test_exchange_obo_token_http_error():
    """Test token exchange with HTTP error."""
    settings = MockSettings()
    service = AuthService(settings)
    service._http_session = AsyncMock()
    service._http_session.post = AsyncMock(side_effect=Exception("Connection error"))

    token = await service.exchange_obo_token(
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert token is None


@pytest.mark.asyncio
async def test_exchange_obo_token_no_access_token_in_response():
    """Test token exchange when response has no access_token."""
    settings = MockSettings()
    service = AuthService(settings)
    service._http_session = AsyncMock()

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "expires_in": 3600,
            "token_type": "Bearer",
            # missing access_token
        }
    )
    mock_response.raise_for_status = AsyncMock()
    service._http_session.post = AsyncMock(return_value=mock_response)

    token = await service.exchange_obo_token(
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert token is None


@pytest.mark.asyncio
async def test_refresh_obo_token_still_valid():
    """Test refresh when token is still valid."""
    settings = MockSettings()
    service = AuthService(settings)
    service._http_session = AsyncMock()

    now = time.time()
    token = DelegatedAccessToken(
        access_token="still-valid-token",
        expires_at=now + 3600,
        user_id="user@example.com",
    )

    result = await service.refresh_obo_token_if_expired(
        token=token,
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert result == token  # should return same token without exchanging
    service._http_session.post.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_obo_token_expired():
    """Test refresh when token is expired."""
    settings = MockSettings()
    service = AuthService(settings)
    service._http_session = AsyncMock()

    now = time.time()
    token = DelegatedAccessToken(
        access_token="expired-token",
        expires_at=now - 100,  # already expired
        user_id="user@example.com",
    )

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "access_token": "new-access-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
    )
    mock_response.raise_for_status = AsyncMock()
    service._http_session.post = AsyncMock(return_value=mock_response)

    result = await service.refresh_obo_token_if_expired(
        token=token,
        user_refresh_token="user-refresh-token",
        user_id="user@example.com",
    )

    assert result is not None
    assert result.access_token == "new-access-token"
    assert result != token  # should be a new token


def test_context_token_storage():
    """Test storing and retrieving token in context."""
    from app.services.auth_service import _ctx_user_access_token, _ctx_user_id

    settings = MockSettings()
    service = AuthService(settings)

    # Store in context
    _ctx_user_access_token.set("test-access-token")
    _ctx_user_id.set("user@example.com")

    # Retrieve from context
    assert service.get_current_access_token() == "test-access-token"
    assert service.get_current_user_id() == "user@example.com"


def test_context_clear():
    """Test clearing context."""
    from app.services.auth_service import _ctx_user_access_token, _ctx_user_id

    settings = MockSettings()
    service = AuthService(settings)

    # Store in context
    _ctx_user_access_token.set("test-access-token")
    _ctx_user_id.set("user@example.com")

    # Clear context
    service.clear_context()

    # Should be empty now
    assert service.get_current_access_token() == ""
    assert service.get_current_user_id() == ""


@pytest.mark.asyncio
async def test_auth_service_lifecycle():
    """Test start and stop lifecycle."""
    settings = MockSettings()
    service = AuthService(settings)

    # Start
    await service.start()
    assert service._http_session is not None
    assert service.credential is not None

    # Stop
    await service.stop()
    # After stop, session and credential should be cleaned up


def test_token_endpoint_construction():
    """Test token endpoint URL construction."""
    settings = MockSettings()
    settings.azure_tenant_id = "my-tenant"
    service = AuthService(settings)

    expected = "https://login.microsoftonline.com/my-tenant/oauth2/v2.0/token"
    assert service.token_endpoint == expected
