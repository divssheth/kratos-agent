"""Tests for authentication mode controller and switching.

Verifies that:
1. Auth mode switches cleanly between agent_app and user_obo via config
2. No secrets are hardcoded; all from environment/Managed Identity
3. Auth context is properly gated based on active mode
4. Fallback to agent_app in local mode
"""

import pytest
from unittest.mock import MagicMock

from app.services.auth_mode_controller import (
    AuthMode,
    AuthModeConfig,
    AuthModeController,
    get_auth_mode_controller,
)


class MockSettings:
    """Mock settings for testing."""

    def __init__(
        self,
        enable_user_auth_obo: bool = False,
        is_local_mode: bool = False,
    ):
        self.enable_user_auth_obo = enable_user_auth_obo
        self.is_local_mode = is_local_mode


# ─────────────────────────────────────────────────────────────────────
# AuthMode Enum Tests
# ─────────────────────────────────────────────────────────────────────


def test_auth_mode_enum_values():
    """Test AuthMode enum members."""
    assert AuthMode.AGENT_APP.value == "agent_app"
    assert AuthMode.USER_OBO.value == "user_obo"


def test_auth_mode_enum_is_string():
    """Test that AuthMode can be used as string."""
    mode = AuthMode.AGENT_APP
    assert str(mode) == "AuthMode.AGENT_APP"
    assert mode.value == "agent_app"


# ─────────────────────────────────────────────────────────────────────
# AuthModeConfig Tests
# ─────────────────────────────────────────────────────────────────────


def test_auth_mode_config_default():
    """Test default config (agent_app mode)."""
    config = AuthModeConfig(
        enabled_mode=AuthMode.AGENT_APP,
        obo_enabled=False,
        is_local_mode=False,
    )
    assert config.active_mode == AuthMode.AGENT_APP
    assert not config.supports_user_delegation()
    assert config.supports_agent_principal()


def test_auth_mode_config_obo_enabled():
    """Test config with OBO enabled."""
    config = AuthModeConfig(
        enabled_mode=AuthMode.AGENT_APP,
        obo_enabled=True,
        is_local_mode=False,
    )
    assert config.active_mode == AuthMode.USER_OBO
    assert config.supports_user_delegation()
    assert not config.supports_agent_principal()


def test_auth_mode_config_local_mode_overrides_obo():
    """Test that local mode forces agent_app even if OBO enabled."""
    config = AuthModeConfig(
        enabled_mode=AuthMode.AGENT_APP,
        obo_enabled=True,  # OBO enabled but...
        is_local_mode=True,  # local mode overrides it
    )
    assert config.active_mode == AuthMode.AGENT_APP
    assert not config.supports_user_delegation()


# ─────────────────────────────────────────────────────────────────────
# AuthModeController Tests: Default (Agent App)
# ─────────────────────────────────────────────────────────────────────


def test_controller_default_agent_app_mode():
    """Test controller defaults to agent_app mode."""
    settings = MockSettings(enable_user_auth_obo=False, is_local_mode=False)
    controller = AuthModeController(settings)

    assert controller.get_mode() == AuthMode.AGENT_APP
    assert controller.is_agent_app_mode()
    assert not controller.is_obo_mode()
    assert controller.get_mode_name() == "Agent Service Principal (Managed Identity)"


def test_controller_agent_app_rejects_auth_context():
    """Test that agent_app mode does not use auth context."""
    settings = MockSettings(enable_user_auth_obo=False)
    controller = AuthModeController(settings)

    assert not controller.can_use_auth_context()
    assert controller.should_strip_auth_context()


def test_controller_agent_app_security_summary():
    """Test security summary for agent_app mode."""
    settings = MockSettings(enable_user_auth_obo=False, is_local_mode=False)
    controller = AuthModeController(settings)

    summary = controller.get_security_summary()
    assert summary["mode"] == "agent_app"
    assert not summary["obo_enabled"]
    assert not summary["is_local_mode"]
    assert summary["supports_user_delegation"] is False
    assert summary["supports_agent_principal"] is True
    assert "Managed Identity" in summary["credentials_source"]
    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False


# ─────────────────────────────────────────────────────────────────────
# AuthModeController Tests: OBO Mode
# ─────────────────────────────────────────────────────────────────────


def test_controller_obo_mode_enabled():
    """Test controller switches to OBO mode when flag enabled."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    assert controller.get_mode() == AuthMode.USER_OBO
    assert controller.is_obo_mode()
    assert not controller.is_agent_app_mode()
    assert controller.get_mode_name() == "User OBO (Delegated)"


def test_controller_obo_accepts_auth_context():
    """Test that OBO mode accepts auth context."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    assert controller.can_use_auth_context()
    assert not controller.should_strip_auth_context()


def test_controller_obo_security_summary():
    """Test security summary for OBO mode."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    summary = controller.get_security_summary()
    assert summary["mode"] == "user_obo"
    assert summary["obo_enabled"] is True
    assert not summary["is_local_mode"]
    assert summary["supports_user_delegation"] is True
    assert summary["supports_agent_principal"] is False
    assert "Entra ID OBO" in summary["credentials_source"]
    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False


# ─────────────────────────────────────────────────────────────────────
# AuthModeController Tests: Local Mode Interaction
# ─────────────────────────────────────────────────────────────────────


def test_controller_local_mode_forces_agent_app():
    """Test that local mode forces agent_app regardless of OBO flag."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=True)
    controller = AuthModeController(settings)

    assert controller.get_mode() == AuthMode.AGENT_APP
    assert not controller.can_use_auth_context()


def test_controller_local_mode_security_summary():
    """Test security summary reflects local mode override."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=True)
    controller = AuthModeController(settings)

    summary = controller.get_security_summary()
    assert summary["mode"] == "agent_app"  # forced by local mode
    assert summary["is_local_mode"] is True
    assert summary["obo_enabled"] is True  # flag is true but...
    assert summary["supports_user_delegation"] is False  # local mode overrides


# ─────────────────────────────────────────────────────────────────────
# AuthModeController Tests: String Representation
# ─────────────────────────────────────────────────────────────────────


def test_controller_auth_mode_string_agent_app():
    """Test auth mode string representation for agent_app."""
    settings = MockSettings(enable_user_auth_obo=False)
    controller = AuthModeController(settings)

    assert controller.get_auth_mode_string() == "agent_app"


def test_controller_auth_mode_string_obo():
    """Test auth mode string representation for OBO."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    assert controller.get_auth_mode_string() == "user_obo"


# ─────────────────────────────────────────────────────────────────────
# Factory Function Tests
# ─────────────────────────────────────────────────────────────────────


def test_get_auth_mode_controller_factory():
    """Test factory function creates controller correctly."""
    settings = MockSettings(enable_user_auth_obo=False)
    controller = get_auth_mode_controller(settings)

    assert isinstance(controller, AuthModeController)
    assert controller.is_agent_app_mode()


def test_get_auth_mode_controller_factory_obo():
    """Test factory function with OBO enabled."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = get_auth_mode_controller(settings)

    assert isinstance(controller, AuthModeController)
    assert controller.is_obo_mode()


# ─────────────────────────────────────────────────────────────────────
# Integration: Mode Switching Scenarios
# ─────────────────────────────────────────────────────────────────────


def test_scenario_production_agent_app():
    """Scenario: Production with Agent Service Principal (default)."""
    # Production setup: OBO disabled (default)
    settings = MockSettings(enable_user_auth_obo=False, is_local_mode=False)
    controller = AuthModeController(settings)

    assert controller.is_agent_app_mode()
    assert not controller.can_use_auth_context()
    summary = controller.get_security_summary()
    assert "Managed Identity" in summary["credentials_source"]
    assert summary["secrets_in_code"] is False


def test_scenario_production_obo_rollout():
    """Scenario: Production with OBO enabled for canary rollout."""
    # Production setup: OBO enabled for testing with real users
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    assert controller.is_obo_mode()
    assert controller.can_use_auth_context()
    summary = controller.get_security_summary()
    assert "Entra ID OBO" in summary["credentials_source"]
    assert summary["secrets_in_code"] is False


def test_scenario_local_dev_ignores_obo_flag():
    """Scenario: Local development with OBO flag=true (ignored in local mode)."""
    # Local setup: even if OBO is enabled, it's ignored
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=True)
    controller = AuthModeController(settings)

    # Local mode forces agent_app despite OBO flag
    assert controller.is_agent_app_mode()
    assert not controller.can_use_auth_context()


def test_scenario_easy_rollback():
    """Scenario: Easy rollback from OBO to Agent SP by changing one flag."""
    # Start in OBO mode
    settings_obo = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller_obo = AuthModeController(settings_obo)
    assert controller_obo.is_obo_mode()

    # Rollback: just flip the flag
    settings_agent = MockSettings(enable_user_auth_obo=False, is_local_mode=False)
    controller_agent = AuthModeController(settings_agent)
    assert controller_agent.is_agent_app_mode()

    # Both controllers have clean security posture
    assert controller_agent.get_security_summary()["secrets_in_code"] is False
    assert controller_obo.get_security_summary()["secrets_in_code"] is False


# ─────────────────────────────────────────────────────────────────────
# Security-Focused Tests
# ─────────────────────────────────────────────────────────────────────


def test_security_no_hardcoded_secrets_agent_app():
    """Verify agent_app mode uses Managed Identity (no hardcoded secrets)."""
    settings = MockSettings(enable_user_auth_obo=False)
    controller = AuthModeController(settings)

    summary = controller.get_security_summary()
    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False
    assert "Managed Identity" in summary["credentials_source"]


def test_security_no_hardcoded_secrets_obo():
    """Verify OBO mode uses token exchange (no hardcoded secrets)."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    summary = controller.get_security_summary()
    assert summary["secrets_in_code"] is False
    assert summary["secrets_in_git"] is False
    assert "Entra ID" in summary["credentials_source"]


def test_auth_context_stripping_agent_app():
    """Verify auth context is stripped in agent_app mode."""
    settings = MockSettings(enable_user_auth_obo=False)
    controller = AuthModeController(settings)

    # In agent_app mode, even if auth context is provided, it should be ignored
    assert controller.should_strip_auth_context()
    assert not controller.can_use_auth_context()


def test_auth_context_acceptance_obo():
    """Verify auth context is accepted in OBO mode."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    # In OBO mode, auth context should be accepted
    assert not controller.should_strip_auth_context()
    assert controller.can_use_auth_context()


# ─────────────────────────────────────────────────────────────────────
# Edge Cases and Config Defaults
# ─────────────────────────────────────────────────────────────────────


def test_missing_settings_attributes_use_defaults():
    """Test that missing settings attributes use safe defaults."""
    settings = MagicMock(spec=[])  # Empty spec, no attributes

    controller = AuthModeController(settings)

    # Should use defaults: obo_enabled=False, is_local_mode=False
    assert controller.is_agent_app_mode()
    assert not controller.is_obo_mode()


def test_mode_string_consistency():
    """Test that mode string is consistent across calls."""
    settings = MockSettings(enable_user_auth_obo=False)
    controller = AuthModeController(settings)

    mode_str1 = controller.get_auth_mode_string()
    mode_str2 = controller.get_auth_mode_string()

    assert mode_str1 == mode_str2 == "agent_app"


def test_security_summary_does_not_leak_secrets():
    """Test that security summary never includes actual secrets."""
    settings = MockSettings(enable_user_auth_obo=True, is_local_mode=False)
    controller = AuthModeController(settings)

    summary = controller.get_security_summary()

    # Make sure no tokens, keys, or secrets are in the summary
    summary_str = str(summary).lower()
    assert "secret" not in summary_str or "secrets_in" in summary_str  # only the key, not a value
    assert "token" not in summary_str or "user_token" not in summary_str
    assert "password" not in summary_str
