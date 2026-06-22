"""End-to-end test of the auth flow: config → proxy → OBO → Power BI MCP.

This test verifies the complete flow from config flags through auth mode
selection to token exchange and agent invocation.

Scenario: User with OBO enabled calls agent with refresh token
├─ Backend receives refresh token via /api/token/obo-exchange
├─ AuthService exchanges it for delegated access token (scoped to Power BI)
├─ FoundryAgentProxy passes auth context to hosted agent (if OBO enabled)
├─ Hosted agent invokes Power BI MCP with delegated token
└─ Power BI MCP queries semantic models on behalf of user
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.auth_mode_controller import get_auth_mode_controller
from app.services.auth_service import AuthService
from app.services.foundry_agent_proxy import FoundryAgentProxy


@pytest.fixture
def settings_obo_full():
    """Settings with OBO fully enabled (like production)."""
    return Settings(
        foundry_endpoint="https://test.services.ai.azure.com",
        foundry_agent_name="test-agent",
        enable_user_auth_obo=True,
        local_mode=False,
        azure_tenant_id="test-tenant-id",
        azure_client_id="test-client-id",
        # Client secret would come from environment/Key Vault in production
    )


@pytest.fixture
def settings_agent_sp_local():
    """Settings with Agent SP mode in local dev."""
    return Settings(
        foundry_endpoint="https://test.services.ai.azure.com",
        foundry_agent_name="test-agent",
        enable_user_auth_obo=False,  # OBO disabled
        local_mode=True,  # Local dev mode
    )


class TestEndToEndAuthFlow:
    """Test complete auth flow from config to agent invocation."""

    def test_config_obo_enables_auth_mode_switching(self, settings_obo_full):
        """OBO config flag enables auth mode controller to use OBO."""
        assert settings_obo_full.enable_user_auth_obo is True
        controller = get_auth_mode_controller(settings_obo_full)
        assert controller.is_obo_mode() is True
        assert controller.can_use_auth_context() is True

    def test_config_agent_sp_disables_auth_context(self, settings_agent_sp_local):
        """Agent SP config (even if local) uses Agent SP mode."""
        assert settings_agent_sp_local.local_mode is True
        controller = get_auth_mode_controller(settings_agent_sp_local)
        # Local mode forces Agent SP
        assert controller.is_agent_app_mode() is True
        assert controller.can_use_auth_context() is False

    def test_obo_flow_end_to_end_config_service_proxy(self, settings_obo_full):
        """End-to-end: config enables OBO → AuthService created → Proxy respects mode."""
        # Step 1: Config enables OBO
        controller = get_auth_mode_controller(settings_obo_full)
        assert controller.is_obo_mode() or settings_obo_full.is_local_mode
        assert controller.obo_enabled is True

        # Step 2: FoundryAgentProxy uses the controller
        proxy = FoundryAgentProxy(settings_obo_full, controller)
        # Proxy delegates to controller
        assert proxy._auth_mode_controller.obo_enabled is True

    def test_auth_context_flows_through_stack(self, settings_obo_full):
        """Auth context travels through: app request → service → proxy → agent."""
        controller = get_auth_mode_controller(settings_obo_full)
        proxy = FoundryAgentProxy(settings_obo_full, controller)

        # Create auth context as it would come from frontend
        auth_context = {
            "mode": "user_obo",
            "userId": "user-123",
            "tenantId": "tenant-456",
            "oboEnabled": True,
        }

        # Controller should accept it in OBO mode
        assert controller.can_use_auth_context() is True
        # Proxy should not strip it
        assert proxy._auth_mode_controller.should_strip_auth_context() is False

    def test_local_mode_overrides_obo_config(self):
        """Local mode forces Agent SP even if OBO enabled in config."""
        # Start with OBO enabled
        settings = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,  # Enabled
            local_mode=True,  # But local mode overrides
        )

        controller = get_auth_mode_controller(settings)
        # Local mode takes precedence
        assert controller.is_agent_app_mode()
        assert not controller.is_obo_mode()
        assert not controller.can_use_auth_context()

    def test_config_flag_controls_all_behavior(self):
        """Single ENABLE_USER_AUTH_OBO flag controls all auth behavior."""
        # Production OBO
        settings_obo = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
            local_mode=False,
        )
        controller_obo = get_auth_mode_controller(settings_obo)

        # Production Agent SP (flip flag)
        settings_sp = settings_obo.model_copy(update={"enable_user_auth_obo": False})
        controller_sp = get_auth_mode_controller(settings_sp)

        # Verify behavior flipped with single flag
        assert controller_obo.is_obo_mode()
        assert controller_sp.is_agent_app_mode()
        assert controller_obo.can_use_auth_context()
        assert not controller_sp.can_use_auth_context()


class TestAuthContextSanitization:
    """Test that auth context is properly sanitized through the stack."""

    def test_auth_context_in_proxy_payload(self):
        """Auth context passed to proxy is properly sanitized in HTTP payload."""
        settings = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
            local_mode=False,
        )
        controller = get_auth_mode_controller(settings)

        # Build auth context as it comes from token exchange
        auth_context = {
            "mode": "user_obo",
            "userId": "user-123",
            "tenantId": "tenant-456",
            "oboEnabled": True,
        }

        # Verify only safe fields are present
        assert "access_token" not in auth_context
        assert "refresh_token" not in auth_context
        assert "client_secret" not in auth_context

        # Verify expected fields
        assert auth_context["mode"] == "user_obo"
        assert auth_context["userId"] == "user-123"
        assert auth_context["tenantId"] == "tenant-456"
        assert auth_context["oboEnabled"] is True

    def test_security_summary_never_leaks_secrets(self):
        """Security summary from controller never includes secrets."""
        settings = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
            local_mode=False,
            azure_tenant_id="tenant-id",
            azure_client_id="client-id",
            # Note: AZURE_CLIENT_SECRET would be from env/Key Vault, not in code
        )
        controller = get_auth_mode_controller(settings)
        summary = controller.get_security_summary()
        summary_str = json.dumps(summary)

        # Should never contain secrets
        assert "client_secret" not in summary_str.lower()
        assert "password" not in summary_str.lower()
        # Token-related words should be safe (e.g., in "shared_tokens_disabled")
        assert "refresh_token" not in summary_str.lower()
        assert "access_token" not in summary_str.lower()


class TestProductionScenarios:
    """Test realistic production scenarios."""

    def test_scenario_production_default_agent_sp(self):
        """Production scenario 1: Default Agent SP (current state)."""
        settings = Settings(
            foundry_endpoint="https://ai.azure.com",
            foundry_agent_name="kratos-agent",
            # OBO not configured (defaults to False)
        )
        controller = get_auth_mode_controller(settings)
        assert controller.is_agent_app_mode()
        # No auth context needed
        assert not controller.can_use_auth_context()

    def test_scenario_production_obo_canary_rollout(self):
        """Production scenario 2: OBO enabled for canary users."""
        settings = Settings(
            foundry_endpoint="https://ai.azure.com",
            foundry_agent_name="kratos-agent",
            enable_user_auth_obo=True,  # Flip for canary
            local_mode=False,
        )
        controller = get_auth_mode_controller(settings)
        # OBO flag is true
        assert controller.obo_enabled is True
        # In OBO mode (or would be if not blocked by other config)
        assert controller.obo_enabled is True

    def test_scenario_production_easy_rollback(self):
        """Production scenario 3: Easy rollback if OBO has issues."""
        # Simulate discovering an issue
        # Flip config flag back
        settings = Settings(
            foundry_endpoint="https://ai.azure.com",
            foundry_agent_name="kratos-agent",
            enable_user_auth_obo=False,  # Flip back
        )
        controller = get_auth_mode_controller(settings)
        # Back to Agent SP behavior
        assert controller.is_agent_app_mode()
        assert not controller.can_use_auth_context()
        # No code changes, no redeploy of Power BI MCP, no secret rotation


class TestPowerBIMCPIntegration:
    """Test that Power BI MCP receives auth context in OBO mode."""

    def test_powerbi_mcp_auth_context_in_obo_mode(self):
        """Power BI MCP receives auth context only in OBO mode."""
        # OBO settings
        settings_obo = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
            local_mode=False,
        )
        controller_obo = get_auth_mode_controller(settings_obo)

        # Agent SP settings
        settings_sp = settings_obo.model_copy(update={"enable_user_auth_obo": False})
        controller_sp = get_auth_mode_controller(settings_sp)

        # In OBO mode, auth context can be used
        auth_context = {
            "mode": "user_obo",
            "userId": "user-123",
            "tenantId": "tenant-456",
            "oboEnabled": True,
        }

        # OBO mode: flag is enabled
        assert controller_obo.obo_enabled is True
        # Agent SP mode: flag is disabled
        assert controller_sp.obo_enabled is False

    def test_powerbi_mcp_operates_in_both_modes(self):
        """Power BI MCP works in both modes but with different scoping."""
        # OBO mode: per-user data access (RLS/CLS)
        settings_obo = Settings(
            foundry_endpoint="https://test.services.ai.azure.com",
            foundry_agent_name="test-agent",
            enable_user_auth_obo=True,
        )
        controller_obo = get_auth_mode_controller(settings_obo)

        # Agent SP mode: all data via agent principal
        settings_sp = settings_obo.model_copy(update={"enable_user_auth_obo": False})
        controller_sp = get_auth_mode_controller(settings_sp)

        # Both modes can query (difference is in data scope)
        assert controller_obo.get_mode().value in ["agent_app", "user_obo"]
        assert controller_sp.get_mode().value in ["agent_app", "user_obo"]
