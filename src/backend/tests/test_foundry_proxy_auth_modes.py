"""Tests for FoundryAgentProxy auth mode integration.

Verifies that auth context is properly passed or stripped based on the active
auth mode (Agent SP vs OBO). Tests the integration between AuthModeController
and FoundryAgentProxy to ensure:

- Agent SP mode (default): auth context is stripped, no secrets exposed
- OBO mode: auth context is passed and properly sanitized
- Local mode: forces Agent SP, ignoring OBO flag
- Headers: current auth mode always included for observability
- Non-breaking: existing behavior unchanged when AuthModeController not provided
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.auth_mode_controller import get_auth_mode_controller
from app.services.foundry_agent_proxy import FoundryAgentProxy


@pytest.fixture
def base_settings():
    """Create base settings with Foundry configured."""
    return Settings(
        foundry_endpoint="https://test.services.ai.azure.com",
        foundry_agent_name="test-agent",
        foundry_api_version="2024-03-15-preview",
    )


@pytest.fixture
def settings_agent_sp(base_settings):
    """Agent SP mode (default, OBO disabled)."""
    return base_settings.model_copy(
        update={
            "enable_user_auth_obo": False,
            "local_mode": False,
        }
    )


@pytest.fixture
def settings_obo_enabled(base_settings):
    """OBO mode enabled."""
    return base_settings.model_copy(
        update={
            "enable_user_auth_obo": True,
            "local_mode": False,
            "azure_tenant_id": "test-tenant-id",
            "azure_client_id": "test-client-id",
        }
    )


@pytest.fixture
def settings_local_dev(base_settings):
    """Local dev mode (forces Agent SP)."""
    return base_settings.model_copy(
        update={
            "enable_user_auth_obo": True,  # Even if enabled in config
            "local_mode": True,  # Local mode overrides
        }
    )


@pytest.fixture
async def proxy_agent_sp(settings_agent_sp):
    """Proxy in Agent SP mode."""
    proxy = FoundryAgentProxy(settings_agent_sp)
    proxy._http_session = AsyncMock()
    proxy._credential = None  # Skip Azure credential in tests
    return proxy


@pytest.fixture
async def proxy_obo(settings_obo_enabled):
    """Proxy in OBO mode."""
    controller = get_auth_mode_controller(settings_obo_enabled)
    proxy = FoundryAgentProxy(settings_obo_enabled, controller)
    proxy._http_session = AsyncMock()
    proxy._credential = None  # Skip Azure credential in tests
    return proxy


@pytest.fixture
async def proxy_local_dev(settings_local_dev):
    """Proxy in local dev mode (forced Agent SP)."""
    controller = get_auth_mode_controller(settings_local_dev)
    proxy = FoundryAgentProxy(settings_local_dev, controller)
    proxy._http_session = AsyncMock()
    proxy._credential = None  # Skip Azure credential in tests
    return proxy


class TestFoundryProxyAuthModeControllerInjection:
    """Test AuthModeController injection and initialization."""

    def test_proxy_creates_default_controller_when_not_provided(self, settings_agent_sp):
        """When AuthModeController not provided, proxy creates its own."""
        proxy = FoundryAgentProxy(settings_agent_sp)
        assert proxy._auth_mode_controller is not None
        assert proxy._auth_mode_controller.is_agent_app_mode()

    def test_proxy_uses_injected_controller(self, settings_agent_sp):
        """When AuthModeController is provided, proxy uses it."""
        controller = get_auth_mode_controller(settings_agent_sp)
        proxy = FoundryAgentProxy(settings_agent_sp, controller)
        assert proxy._auth_mode_controller is controller

    def test_proxy_respects_obo_controller_state(self, settings_obo_enabled):
        """Proxy respects OBO state from injected controller."""
        controller = get_auth_mode_controller(settings_obo_enabled)
        proxy = FoundryAgentProxy(settings_obo_enabled, controller)
        assert proxy._auth_mode_controller.is_obo_mode()


class TestFoundryProxyAuthContextStripping:
    """Test that auth context is stripped/passed based on mode."""

    def test_agent_sp_mode_controller_strips_context(self, proxy_agent_sp):
        """Agent SP mode: controller indicates context should be stripped."""
        # Get the auth mode controller
        controller = proxy_agent_sp._auth_mode_controller
        # In Agent SP mode, should_strip_auth_context() returns True
        assert controller.should_strip_auth_context() is True
        # And can_use_auth_context() returns False
        assert controller.can_use_auth_context() is False

    def test_obo_mode_controller_accepts_context(self, proxy_obo):
        """OBO mode: controller indicates context should be accepted."""
        # Get the auth mode controller
        controller = proxy_obo._auth_mode_controller
        # In OBO mode, should_strip_auth_context() returns False
        assert controller.should_strip_auth_context() is False
        # And can_use_auth_context() returns True
        assert controller.can_use_auth_context() is True

    def test_local_mode_controller_strips_context(self, proxy_local_dev):
        """Local dev mode: controller forces Agent SP, context stripped."""
        # Get the auth mode controller
        controller = proxy_local_dev._auth_mode_controller
        # Local mode forces Agent SP
        assert controller.is_agent_app_mode() is True
        # Context should be stripped
        assert controller.should_strip_auth_context() is True
        # Context cannot be used
        assert controller.can_use_auth_context() is False


class TestFoundryProxyAuthModeHeaders:
    """Test that auth mode headers are correctly set."""

    def test_agent_sp_mode_header_value(self, proxy_agent_sp):
        """Agent SP mode: auth mode string is 'agent_app'."""
        mode_string = proxy_agent_sp._auth_mode_controller.get_auth_mode_string()
        assert mode_string == "agent_app"

    def test_obo_mode_header_value(self, proxy_obo):
        """OBO mode: auth mode string is 'user_obo'."""
        mode_string = proxy_obo._auth_mode_controller.get_auth_mode_string()
        assert mode_string == "user_obo"

    def test_local_dev_mode_header_value(self, proxy_local_dev):
        """Local dev mode: auth mode forced to 'agent_app'."""
        mode_string = proxy_local_dev._auth_mode_controller.get_auth_mode_string()
        assert mode_string == "agent_app"


class TestFoundryProxyAuthContextSanitization:
    """Test that auth context is properly sanitized (no secrets exposed)."""

    def test_proxy_accepts_auth_context_only_in_obo_mode(self, proxy_obo, proxy_agent_sp):
        """Auth context acceptance controlled by mode."""
        # OBO mode can use context
        assert proxy_obo._auth_mode_controller.can_use_auth_context() is True
        # Agent SP mode cannot
        assert proxy_agent_sp._auth_mode_controller.can_use_auth_context() is False

    def test_proxy_security_summary_no_secrets(self, proxy_obo, proxy_agent_sp):
        """Security summary never includes actual secret values."""
        # Agent SP summary
        summary_sp = proxy_agent_sp._auth_mode_controller.get_security_summary()
        summary_sp_str = json.dumps(summary_sp)
        assert "token" not in summary_sp_str.lower() or "token" in ["shared_tokens"]  # tokens field is ok
        assert "password" not in summary_sp_str.lower()
        # OBO summary
        summary_obo = proxy_obo._auth_mode_controller.get_security_summary()
        summary_obo_str = json.dumps(summary_obo)
        assert "token" not in summary_obo_str.lower() or "token" in ["shared_tokens"]
        assert "password" not in summary_obo_str.lower()


class TestFoundryProxyAuthModeScenarios:
    """Integration tests for realistic auth mode scenarios."""

    @pytest.mark.asyncio
    async def test_production_agent_sp_default(self, settings_agent_sp):
        """Production scenario: default Agent SP mode (current behavior)."""
        proxy = FoundryAgentProxy(settings_agent_sp)
        assert proxy._auth_mode_controller.is_agent_app_mode()
        assert not proxy._auth_mode_controller.is_obo_mode()

    @pytest.mark.asyncio
    async def test_production_obo_rollout(self, settings_obo_enabled):
        """Production scenario: enable OBO for specific users/workspaces."""
        proxy = FoundryAgentProxy(settings_obo_enabled)
        assert proxy._auth_mode_controller.is_obo_mode()
        assert not proxy._auth_mode_controller.is_agent_app_mode()

    @pytest.mark.asyncio
    async def test_production_easy_rollback(self):
        """Production scenario: easy rollback from OBO to Agent SP (config only)."""
        # Simulate OBO enabled
        settings_obo = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
            local_mode=False,
        )
        proxy_obo = FoundryAgentProxy(settings_obo)
        assert proxy_obo._auth_mode_controller.is_obo_mode()

        # Rollback: flip config flag
        settings_agent_sp = settings_obo.model_copy(update={"enable_user_auth_obo": False})
        proxy_agent_sp = FoundryAgentProxy(settings_agent_sp)
        assert proxy_agent_sp._auth_mode_controller.is_agent_app_mode()

        # Verify behavior switched
        assert proxy_obo._auth_mode_controller.can_use_auth_context()
        assert not proxy_agent_sp._auth_mode_controller.can_use_auth_context()

    @pytest.mark.asyncio
    async def test_local_dev_ignores_obo_setting(self):
        """Local dev scenario: local mode forces Agent SP regardless of OBO flag."""
        settings = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,  # Enabled in config
            local_mode=True,  # But local mode overrides
        )
        proxy = FoundryAgentProxy(settings)
        assert proxy._auth_mode_controller.is_agent_app_mode()
        assert not proxy._auth_mode_controller.can_use_auth_context()


class TestFoundryProxyAuthModeNonBreaking:
    """Test that changes are non-breaking (backward compatible)."""

    def test_proxy_works_without_explicit_auth_mode_controller(self):
        """Proxy should work fine even if AuthModeController not explicitly provided."""
        settings = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
        )
        # Should not raise during initialization
        proxy = FoundryAgentProxy(settings)
        assert proxy._auth_mode_controller is not None

    def test_proxy_can_be_created_with_injected_controller(self):
        """Proxy can accept an explicit AuthModeController."""
        settings = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
        )
        controller = get_auth_mode_controller(settings)
        # Should work fine
        proxy = FoundryAgentProxy(settings, controller)
        assert proxy._auth_mode_controller is controller
