"""OBO (On-Behalf-Of) token exchange and management for delegated auth.

Handles silent token refresh using delegated user context without persisting
refresh tokens. All tokens are short-lived, request-scoped, and never logged.
"""

import asyncio
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import httpx
from azure.identity.aio import DefaultAzureCredential

logger = logging.getLogger(__name__)

# Never logged or persisted; per-request scope only
_ctx_user_access_token: ContextVar[str] = ContextVar("user_access_token", default="")
_ctx_user_id: ContextVar[str] = ContextVar("user_id", default="")


@dataclass
class DelegatedAccessToken:
    """Short-lived delegated access token for user-scoped Fabric queries."""

    access_token: str
    expires_at: float  # Unix timestamp
    user_id: str = ""
    tenant_id: str = ""

    @property
    def is_expired(self) -> bool:
        """True if token has expired or will expire in the next 60s (refresh buffer)."""
        return time.time() >= (self.expires_at - 60)

    @property
    def ttl_seconds(self) -> int:
        """Remaining seconds before expiry."""
        return max(0, int(self.expires_at - time.time()))


class AuthService:
    """Manage OBO token exchange and per-request token lifecycle.

    This service exchanges user refresh tokens for short-lived Fabric access
    tokens via the Entra ID OBO (On-Behalf-Of) flow. Tokens are stored in
    context vars (per-request scope) and never persisted to DB/cache.
    """

    def __init__(self, settings: Any) -> None:
        self.obo_enabled = getattr(settings, "enable_user_auth_obo", False)
        self.tenant_id = getattr(settings, "azure_tenant_id", "")
        self.client_id = getattr(settings, "azure_client_id", "")
        self.client_secret = getattr(settings, "azure_client_secret", "")
        self.token_endpoint = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.credential: DefaultAzureCredential | None = None
        self._http_session: httpx.AsyncClient | None = None

        if not self.obo_enabled:
            logger.info("OBO auth is disabled (ENABLE_USER_AUTH_OBO=false)")
            return

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            logger.warning(
                "OBO auth enabled but incomplete config: tenant_id=%s, client_id=%s",
                bool(self.tenant_id),
                bool(self.client_id),
            )

    async def start(self) -> None:
        """Initialize HTTP session and credentials."""
        self._http_session = httpx.AsyncClient(timeout=30.0)
        self.credential = DefaultAzureCredential()

    async def stop(self) -> None:
        """Cleanup resources."""
        if self._http_session:
            await self._http_session.aclose()
        if self.credential is not None:
            await self.credential.close()

    async def exchange_obo_token(
        self,
        user_refresh_token: str,
        scope: str = "https://analysis.windows.net/.default",
        user_id: str = "",
    ) -> DelegatedAccessToken | None:
        """Exchange user refresh token for delegated Fabric access token via OBO flow.

        Args:
            user_refresh_token: User's Entra ID refresh token from frontend
            scope: Resource scope (default: Power BI/Fabric)
            user_id: User's email or UPN for audit purposes (never persisted)

        Returns:
            DelegatedAccessToken with access_token + expiry, or None on failure
        """
        if not self.obo_enabled:
            logger.warning("OBO exchange requested but feature is disabled")
            return None

        if not user_refresh_token or not user_refresh_token.strip():
            logger.warning("OBO exchange: empty refresh token")
            return None

        if not self._http_session:
            logger.error("OBO exchange: HTTP session not initialized")
            return None

        try:
            # Exchange user refresh token for delegated access token
            # See: https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-on-behalf-of-flow
            response = await self._http_session.post(
                self.token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": user_refresh_token,
                    "scope": scope,
                    "requested_token_use": "access",
                },
            )
            response.raise_for_status()
            body = await response.json()

            access_token = body.get("access_token")
            expires_in = int(body.get("expires_in", 3600))
            expires_at = time.time() + expires_in

            if not access_token:
                logger.warning("OBO exchange: no access_token in response")
                return None

            token = DelegatedAccessToken(
                access_token=access_token,
                expires_at=expires_at,
                user_id=user_id,
            )

            logger.info(
                "OBO token exchanged: ttl=%ds user=%s (non-logged context)",
                token.ttl_seconds,
                "***" if user_id else "unknown",
            )

            # Store in request context (never logged, never persisted)
            _ctx_user_access_token.set(access_token)
            _ctx_user_id.set(user_id)

            return token

        except httpx.HTTPError as e:
            logger.warning("OBO token exchange failed: %s", type(e).__name__)
            return None
        except Exception:
            logger.exception("OBO token exchange error")
            return None

    async def refresh_obo_token_if_expired(
        self, token: DelegatedAccessToken, user_refresh_token: str, user_id: str = ""
    ) -> DelegatedAccessToken | None:
        """Refresh token if expired or expiring soon (60s buffer).

        Args:
            token: Current token to check
            user_refresh_token: User's refresh token for re-exchange
            user_id: User identifier for audit

        Returns:
            Same token if still valid, new token if refreshed, or None on failure
        """
        if not token.is_expired:
            return token

        logger.debug("OBO token expired or expiring: ttl=%ds", token.ttl_seconds)
        return await self.exchange_obo_token(user_refresh_token, user_id=user_id)

    def get_current_access_token(self) -> str:
        """Retrieve the current request-scoped access token from context.

        This is never persisted and is cleared when the request ends.
        """
        return _ctx_user_access_token.get()

    def get_current_user_id(self) -> str:
        """Retrieve the current request-scoped user identifier from context."""
        return _ctx_user_id.get()

    def clear_context(self) -> None:
        """Clear request-scoped token and user context.

        Call this at the end of request handling to ensure tokens are not
        carried over to unrelated requests.
        """
        _ctx_user_access_token.set("")
        _ctx_user_id.set("")


async def get_auth_service() -> AuthService:
    """Dependency for FastAPI to inject AuthService."""
    from app.config import get_settings

    settings = get_settings()
    return AuthService(settings)
