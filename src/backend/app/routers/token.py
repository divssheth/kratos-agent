"""Router for OBO token exchange and delegated auth management."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services.auth_service import AuthService, DelegatedAccessToken

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/token", tags=["auth"])


class OBOExchangeRequest(BaseModel):
    """Request to exchange user refresh token for delegated access token."""

    user_refresh_token: str = Field(
        ...,
        description="Entra ID refresh token obtained by frontend via MSAL",
        min_length=1,
    )
    scope: str = Field(
        default="https://analysis.windows.net/.default",
        description="Resource scope (default: Power BI/Fabric)",
    )
    user_id: str = Field(
        default="",
        description="User email/UPN for audit purposes (optional, never persisted)",
    )


class OBOExchangeResponse(BaseModel):
    """Response with delegated access token for use with Power BI/Fabric."""

    access_token: str = Field(
        ...,
        description="Short-lived access token for Power BI/Fabric API",
    )
    expires_in: int = Field(
        ...,
        description="Token lifetime in seconds (typically 3600)",
    )
    user_id: str = Field(
        default="",
        description="User identifier from request (non-sensitive context only)",
    )


@router.post("/obo-exchange", response_model=OBOExchangeResponse, status_code=200)
async def exchange_obo_token(
    request: OBOExchangeRequest,
    settings=Depends(get_settings),
    auth_service=Depends(lambda: AuthService(get_settings())),
) -> OBOExchangeResponse:
    """Exchange user refresh token for delegated Power BI access token.

    This implements the OAuth 2.0 On-Behalf-Of (OBO) flow. The frontend sends
    the user's refresh token obtained via MSAL, and the backend exchanges it
    for a short-lived delegated access token scoped to Power BI/Fabric.

    **Security:**
    - Refresh tokens are never logged, cached, or persisted
    - Access tokens are short-lived (~1h) and scoped to Power BI
    - Tokens stored in request context only (per-request scope)
    - Requires ENABLE_USER_AUTH_OBO=true to activate

    **Flow:**
    1. Frontend: User logs in via MSAL → gets refresh_token
    2. Frontend: Sends POST /api/token/obo-exchange with refresh_token
    3. Backend: AuthService exchanges refresh_token via Entra ID OBO endpoint
    4. Backend: Returns access_token (short-lived, scoped)
    5. MCP: Receives access_token via env var POWERBI_ACCESS_TOKEN
    6. MCP: Uses token to query Power BI/Fabric APIs

    Args:
        request: OBOExchangeRequest with user's refresh token
        settings: Application settings (dependency injection)
        auth_service: AuthService instance (dependency injection)

    Returns:
        OBOExchangeResponse with access_token + expires_in

    Raises:
        HTTPException(400): OBO feature disabled or invalid input
        HTTPException(401): Token exchange failed (refresh token invalid/expired)
        HTTPException(500): Entra ID or network error
    """
    if not settings.enable_user_auth_obo:
        logger.warning(
            "OBO exchange requested but feature is disabled (ENABLE_USER_AUTH_OBO=false)"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OBO token exchange is not enabled",
        )

    if settings.is_local_mode:
        logger.warning("OBO exchange requested in local mode (not supported)")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OBO is not available in local mode",
        )

    try:
        # Initialize auth service (start HTTP session if needed)
        if not auth_service._http_session:
            await auth_service.start()

        # Exchange user refresh token for delegated access token
        token = await auth_service.exchange_obo_token(
            user_refresh_token=request.user_refresh_token,
            scope=request.scope,
            user_id=request.user_id,
        )

        if token is None:
            logger.warning("OBO token exchange failed for user=%s", "***" if request.user_id else "unknown")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token exchange failed (invalid or expired refresh token)",
            )

        # Return token with TTL (never the refresh token)
        return OBOExchangeResponse(
            access_token=token.access_token,
            expires_in=token.ttl_seconds,
            user_id=request.user_id,  # non-sensitive context only
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("OBO token exchange error: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token exchange service error",
        ) from e
