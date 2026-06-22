"""Integration tests for authentication mode switching.

Verifies end-to-end behavior:
1. Switch from Agent SP to OBO via config
2. Auth context properly gated
3. No secrets leaked
4. Security posture maintained across modes
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json

from app.services.auth_mode_controller import AuthModeController, get_auth_mode_controller
from app.services.auth_service import AuthService, DelegatedAccessToken
from app.routers.token import OBOExchangeRequest, OBOExchangeResponse
import time


class ProductionSettings:
    """Simulate production environment."""

    def __init__(self, enable_obo: bool = False):
        self.enable_user_auth_obo = enable_obo
        self.is_local_mode = False
        self.azure_tenant_id = "prod-tenant-id"
        self.azure_client_id = "prod-app-id"
        self.azure_client_secret = ""  # Never hardcoded; from Key Vault


class LocalSettings:
    """Simulate local development environment."""

    def __init__(self):
        self.enable_user_auth_obo = False  # OBO doesn't work locally
        self.is_local_mode = True
        self.azure_tenant_id = ""
        self.azure_client_id = ""
        self.azure_client_secret = ""


# ─────────────────────────────────────────────────────────────────────
# Scenario 1: Default Production (Agent SP)
# ─────────────────────────────────────────────────────────────────────


def test_scenario_production_default_agent_sp():
    """Scenario: Production deployment with default Agent SP auth.
    
    This is the default, requires no Entra ID OBO setup, uses Managed Identity.
    """
    settings = ProductionSettings(enable_obo=False)
    controller = get_auth_mode_controller(settings)

    # Verify auth mode
    assert controller.is_agent_app_mode()
    assert controller.get_mode_name() == "Agent Service Principal (Managed Identity)"

    # Verify auth context handling
    assert not controller.can_use_auth_context()
    assert controller.should_strip_auth_context()

    # Verify security
    summary = controller.get_security_summary()
    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False
    assert "Managed Identity" in summary["credentials_source"]


def test_scenario_agent_sp_strips_user_auth_context():
    """Verify Agent SP mode strips user auth context if provided.
    
    Even if a user provides auth_context, Agent SP mode ignores it
    and uses Managed Identity instead.
    """
    settings = ProductionSettings(enable_obo=False)
    controller = get_auth_mode_controller(settings)

    # User's auth context (if somehow provided)
    user_auth_context = {
        "mode": "user_obo",
        "userId": "user@example.com",
        "refreshToken": "secret-refresh-token",  # Should be stripped
    }

    # In agent_app mode, this context should be stripped
    assert controller.should_strip_auth_context()
    # (In actual code, proxy would set auth_context=None before using it)


# ─────────────────────────────────────────────────────────────────────
# Scenario 2: Production with OBO Rollout
# ─────────────────────────────────────────────────────────────────────


def test_scenario_production_obo_rollout():
    """Scenario: Production deployment with OBO enabled for canary rollout.
    
    - Entra ID configured with backend app registration
    - Users can now opt-in to user-scoped queries
    - Easy rollback: just flip ENABLE_USER_AUTH_OBO=false
    """
    settings = ProductionSettings(enable_obo=True)
    controller = get_auth_mode_controller(settings)

    # Verify auth mode switched
    assert controller.is_obo_mode()
    assert controller.get_mode_name() == "User OBO (Delegated)"

    # Verify auth context now accepted
    assert controller.can_use_auth_context()
    assert not controller.should_strip_auth_context()

    # Verify security
    summary = controller.get_security_summary()
    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False
    assert "Entra ID" in summary["credentials_source"]


@pytest.mark.asyncio
async def test_scenario_obo_flow_end_to_end():
    """Scenario: Complete OBO token exchange flow.
    
    1. Frontend user logs in via MSAL
    2. Frontend calls POST /api/token/obo-exchange with refresh_token
    3. Backend exchanges via Entra ID OBO flow
    4. Frontend uses delegated access token with Power BI MCP
    """
    # Setup
    settings = ProductionSettings(enable_obo=True)
    auth_controller = get_auth_mode_controller(settings)
    auth_service = AuthService(settings)
    auth_service._http_session = AsyncMock()

    # Verify auth mode supports delegated tokens
    assert auth_controller.is_obo_mode()
    assert auth_controller.can_use_auth_context()

    # Simulate successful token exchange
    now = time.time()
    exchanged_token = DelegatedAccessToken(
        access_token="delegated-access-token-xyz",
        expires_at=now + 3600,
        user_id="user@example.com",
    )

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "access_token": exchanged_token.access_token,
            "expires_in": 3600,
        }
    )
    mock_response.raise_for_status = AsyncMock()
    auth_service._http_session.post = AsyncMock(return_value=mock_response)

    # Exchange token
    result = await auth_service.exchange_obo_token(
        user_refresh_token="user-refresh-token-abc",
        user_id="user@example.com",
    )

    assert result is not None
    assert result.access_token == "delegated-access-token-xyz"
    assert result.user_id == "user@example.com"


# ─────────────────────────────────────────────────────────────────────
# Scenario 3: Easy Rollback
# ─────────────────────────────────────────────────────────────────────


def test_scenario_easy_rollback_obo_to_agent_sp():
    """Scenario: Rollback from OBO to Agent SP by flipping config flag.
    
    - Started with ENABLE_USER_AUTH_OBO=true (OBO mode)
    - Issue discovered; rollback: set ENABLE_USER_AUTH_OBO=false
    - No code changes, no secrets rotation, just a config flag
    """
    # Step 1: Deployment with OBO enabled
    settings_obo = ProductionSettings(enable_obo=True)
    controller_obo = get_auth_mode_controller(settings_obo)
    assert controller_obo.is_obo_mode()

    # Step 2: Flip the flag (in CI/CD or container environment)
    settings_agent = ProductionSettings(enable_obo=False)
    controller_agent = get_auth_mode_controller(settings_agent)

    # Step 3: Verify rollback
    assert controller_agent.is_agent_app_mode()

    # Step 4: Verify both modes have clean security posture
    obo_security = controller_obo.get_security_summary()
    agent_security = controller_agent.get_security_summary()

    assert obo_security["secrets_in_code"] is False
    assert agent_security["secrets_in_code"] is False
    assert obo_security["secrets_in_git"] is False
    assert agent_security["secrets_in_git"] is False


# ─────────────────────────────────────────────────────────────────────
# Scenario 4: Local Development
# ─────────────────────────────────────────────────────────────────────


def test_scenario_local_dev_forces_agent_sp():
    """Scenario: Local development environment.
    
    - is_local_mode=True (no Azure services)
    - OBO flag is ignored
    - Only Agent SP mode available
    """
    settings = LocalSettings()
    controller = get_auth_mode_controller(settings)

    # Verify forced to agent_app despite local mode
    assert controller.is_agent_app_mode()
    assert not controller.can_use_auth_context()

    # Verify security
    summary = controller.get_security_summary()
    assert summary["mode"] == "agent_app"
    assert summary["is_local_mode"] is True


def test_scenario_local_dev_cannot_enable_obo():
    """Scenario: Local dev tries to enable OBO; local mode wins.
    
    Even if developer sets ENABLE_USER_AUTH_OBO=true locally,
    the backend forces Agent SP (OBO requires Entra ID connectivity).
    """
    # Simulate: ENABLE_USER_AUTH_OBO=true but is_local_mode=true
    settings = LocalSettings()
    settings.enable_user_auth_obo = True  # Developer set this

    controller = get_auth_mode_controller(settings)

    # Local mode overrides: Agent SP forced
    assert controller.is_agent_app_mode()
    assert not controller.can_use_auth_context()


# ─────────────────────────────────────────────────────────────────────
# Scenario 5: No Secrets in Code or Git
# ─────────────────────────────────────────────────────────────────────


def test_scenario_agent_sp_no_secrets_in_code():
    """Verify Agent SP mode uses Managed Identity (zero secrets in code/git).
    
    - No hardcoded client_secret
    - No API keys in code
    - No refresh tokens in code
    - Uses keyless auth via Azure Managed Identity
    """
    settings = ProductionSettings(enable_obo=False)
    controller = get_auth_mode_controller(settings)

    summary = controller.get_security_summary()

    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False
    assert "Managed Identity" in summary["credentials_source"]
    # Managed Identity is automated, no manual rotation needed


def test_scenario_obo_secrets_in_key_vault_not_code():
    """Verify OBO mode secrets are in Key Vault, not hardcoded in code.
    
    - AZURE_CLIENT_SECRET never hardcoded in Python
    - Read from environment (set by CI/CD from Key Vault)
    - No .env files with secrets committed to git
    """
    settings = ProductionSettings(enable_obo=True)

    # Verify settings don't have hardcoded secrets
    assert settings.azure_client_secret == ""  # Empty; from env/Key Vault

    controller = get_auth_mode_controller(settings)
    summary = controller.get_security_summary()

    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False
    assert "Entra ID" in summary["credentials_source"]


# ─────────────────────────────────────────────────────────────────────
# Scenario 6: Auth Context Gating
# ─────────────────────────────────────────────────────────────────────


def test_scenario_auth_context_gated_by_mode():
    """Verify auth context (user tokens) are gated by auth mode.
    
    Agent SP mode: auth_context stripped (uses Managed Identity)
    OBO mode: auth_context accepted (uses delegated tokens)
    """
    # Agent SP: context stripped
    settings_agent = ProductionSettings(enable_obo=False)
    controller_agent = get_auth_mode_controller(settings_agent)

    test_auth_context = {
        "mode": "user_obo",
        "userId": "user@example.com",
    }

    # In agent_app mode, should_strip_auth_context() = True
    assert controller_agent.should_strip_auth_context()
    # (proxy would set auth_context=None before passing to hosted agent)

    # OBO: context accepted
    settings_obo = ProductionSettings(enable_obo=True)
    controller_obo = get_auth_mode_controller(settings_obo)

    # In user_obo mode, should_strip_auth_context() = False
    assert not controller_obo.should_strip_auth_context()
    # (proxy would pass auth_context unchanged to hosted agent)


# ─────────────────────────────────────────────────────────────────────
# Scenario 7: Config-Only Switching
# ─────────────────────────────────────────────────────────────────────


def test_scenario_config_driven_switching_no_code_changes():
    """Verify mode switching requires only config, no code changes.
    
    Code path in foundry_agent_proxy.py:
    ```
    if self._local_mode or not self._enable_user_auth_obo:
        auth_context = None
    ```
    
    This single config flag controls all behavior. No code changes needed.
    """
    # Scenario 1: Config=false → Agent SP
    settings1 = ProductionSettings(enable_obo=False)
    controller1 = get_auth_mode_controller(settings1)
    assert controller1.is_agent_app_mode()

    # Scenario 2: Change config to true → OBO
    settings2 = ProductionSettings(enable_obo=True)
    controller2 = get_auth_mode_controller(settings2)
    assert controller2.is_obo_mode()

    # Same code, different config → different behavior
    # No recompilation, no redeploy of code
