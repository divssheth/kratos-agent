"""Authentication mode controller for Agent SP vs OBO (On-Behalf-Of) auth.

This module provides a unified interface for switching between two auth strategies:

1. **Agent Service Principal (agent_app)** - DEFAULT
   - Uses Azure Managed Identity (keyless auth)
   - Service principal scope: acts as the agent to all Power BI/Fabric APIs
   - Enabled by default (ENABLE_USER_AUTH_OBO=false)
   - No secrets in code or git; credentials from Azure environment

2. **User OBO (user_obo)** - OPTIONAL, FEATURE-FLAGGED
   - Uses delegated user tokens (Entra ID OBO flow)
   - User scope: acts as the user to query their own Power BI/Fabric data
   - Enabled by flag (ENABLE_USER_AUTH_OBO=true)
   - Refresh token from frontend, exchanged for access token at backend
   - Never persists or logs tokens; request-scoped only

Switching between modes is purely config-driven via ENABLE_USER_AUTH_OBO.
Zero hardcoded secrets; all credentials from environment or Managed Identity.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

import logging

logger = logging.getLogger(__name__)


class AuthMode(str, Enum):
    """Supported authentication modes."""

    AGENT_APP = "agent_app"  # Service principal (default, keyless via Managed Identity)
    USER_OBO = "user_obo"  # User on-behalf-of (delegated via Entra ID)


@dataclass
class AuthModeConfig:
    """Configuration for auth mode selection and behavior."""

    enabled_mode: AuthMode
    obo_enabled: bool  # Whether OBO feature flag is true
    is_local_mode: bool  # Whether backend is in local (no Azure services) mode

    @property
    def active_mode(self) -> AuthMode:
        """Returns the currently active auth mode.

        Priority:
        1. local_mode → force agent_app (OBO not available locally)
        2. obo_enabled=true → user_obo (delegated user tokens)
        3. default → agent_app (managed identity, keyless)
        """
        if self.is_local_mode:
            return AuthMode.AGENT_APP
        if self.obo_enabled:
            return AuthMode.USER_OBO
        return AuthMode.AGENT_APP

    def supports_user_delegation(self) -> bool:
        """True if the active mode supports per-user auth context."""
        return self.active_mode == AuthMode.USER_OBO and not self.is_local_mode

    def supports_agent_principal(self) -> bool:
        """True if the active mode uses agent service principal (Managed Identity)."""
        return self.active_mode == AuthMode.AGENT_APP


class AuthModeController:
    """Manages authentication mode selection and switching.

    This controller implements the core logic for switching between:
    - Agent Service Principal (default): uses Azure Managed Identity (keyless)
    - User OBO (optional): uses delegated user tokens via Entra ID OBO flow

    Switching is entirely config-driven via the ENABLE_USER_AUTH_OBO flag.
    No secrets are hardcoded; all credentials come from:
    - Azure Managed Identity (agent_app mode)
    - Entra ID token exchange (user_obo mode)
    """

    def __init__(self, settings: Any) -> None:
        """Initialize auth mode controller.

        Args:
            settings: Application settings containing:
                - enable_user_auth_obo: Feature flag for OBO mode (bool, default False)
                - is_local_mode: Whether running locally (bool, default auto-detect)
        """
        self.obo_enabled = getattr(settings, "enable_user_auth_obo", False)
        self.is_local_mode = getattr(settings, "is_local_mode", False)

        self.config = AuthModeConfig(
            enabled_mode=AuthMode.AGENT_APP,  # default
            obo_enabled=self.obo_enabled,
            is_local_mode=self.is_local_mode,
        )

        self._log_mode_info()

    def _log_mode_info(self) -> None:
        """Log authentication mode information at startup."""
        active = self.config.active_mode
        if self.config.is_local_mode:
            logger.info(
                "Auth mode: AGENT_APP (forced by local_mode). "
                "OBO disabled in local mode."
            )
        elif self.config.obo_enabled:
            logger.info(
                "Auth mode: USER_OBO (ENABLE_USER_AUTH_OBO=true). "
                "Using delegated user tokens via Entra ID OBO flow. "
                "No service principal secrets; credentials from Entra ID."
            )
        else:
            logger.info(
                "Auth mode: AGENT_APP (default, ENABLE_USER_AUTH_OBO=false). "
                "Using Azure Managed Identity (keyless auth). "
                "Agent acts as service principal to Power BI/Fabric."
            )

    def get_mode(self) -> AuthMode:
        """Get the currently active authentication mode."""
        return self.config.active_mode

    def get_mode_name(self) -> str:
        """Get human-readable name of the active mode."""
        mode = self.config.active_mode
        if mode == AuthMode.AGENT_APP:
            return "Agent Service Principal (Managed Identity)"
        elif mode == AuthMode.USER_OBO:
            return "User OBO (Delegated)"
        return str(mode)

    def is_obo_mode(self) -> bool:
        """True if currently in user OBO mode."""
        return self.config.active_mode == AuthMode.USER_OBO

    def is_agent_app_mode(self) -> bool:
        """True if currently in agent service principal mode."""
        return self.config.active_mode == AuthMode.AGENT_APP

    def can_use_auth_context(self) -> bool:
        """True if the current mode accepts user auth context.

        Only OBO mode supports per-user auth context (delegated tokens).
        Agent SP mode ignores auth context and uses Managed Identity.
        """
        return self.config.supports_user_delegation()

    def should_strip_auth_context(self) -> bool:
        """True if auth context should be stripped for this request.

        Auth context (refresh tokens, user IDs) should be stripped when:
        - Mode is agent_app (doesn't support delegation)
        - Mode is local (no Entra ID)
        - Feature is disabled
        """
        return not self.can_use_auth_context()

    def get_auth_mode_string(self) -> str:
        """Get the auth mode as a string for headers/tracing."""
        return self.config.active_mode.value

    def get_security_summary(self) -> dict[str, Any]:
        """Return security posture information for logging/debugging.

        Never includes secrets; only configuration state.
        """
        return {
            "mode": self.config.active_mode.value,
            "obo_enabled": self.config.obo_enabled,
            "is_local_mode": self.config.is_local_mode,
            "supports_user_delegation": self.config.supports_user_delegation(),
            "supports_agent_principal": self.config.supports_agent_principal(),
            "credentials_source": (
                "Azure Managed Identity (keyless)"
                if self.is_agent_app_mode()
                else "Entra ID OBO (delegated)"
            ),
            "secrets_in_code": False,  # always false by design
            "secrets_in_git": False,  # always false by design
        }


def get_auth_mode_controller(settings: Any) -> AuthModeController:
    """Factory function for auth mode controller."""
    return AuthModeController(settings)
