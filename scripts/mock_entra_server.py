#!/usr/bin/env python3
"""
Mock Entra ID Server for Local OBO Testing

This server simulates Azure Entra ID token exchange for testing the OBO flow
without connecting to real Azure infrastructure.

Usage:
    python mock_entra_server.py

Then use in tests:
    AZURE_TOKEN_ENDPOINT=http://localhost:5555/token
    AZURE_TENANT_ID=mock-tenant
    AZURE_CLIENT_ID=mock-client-id
    AZURE_CLIENT_SECRET=mock-secret
"""

import json
import jwt
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from typing import Dict, Any

# Initialize Flask app
app = Flask(__name__)

# Mock configuration
MOCK_CONFIG = {
    "tenant_id": "12345678-1234-1234-1234-123456789012",
    "client_id": "87654321-4321-4321-4321-210987654321",
    "client_secret": "mock-secret-key-12345",
    "issuer": "https://login.microsoftonline.com/12345678-1234-1234-1234-123456789012/v2.0",
}

# Signing secret (in production, this would be a real certificate)
JWT_SECRET = "mock-jwt-secret-for-testing-only"


def create_mock_token(user_id: str, tenant_id: str, scopes: str) -> Dict[str, Any]:
    """Create a mock JWT token that simulates Entra ID access token."""
    now = datetime.utcnow()
    expires_in = 3600  # 1 hour
    exp_time = now + timedelta(seconds=expires_in)

    payload = {
        "iss": MOCK_CONFIG["issuer"],
        "aud": "https://analysis.windows.net",  # Power BI resource
        "iat": int(now.timestamp()),
        "exp": int(exp_time.timestamp()),
        "sub": user_id,
        "oid": "00000000-0000-0000-0000-000000000000",
        "tid": tenant_id,
        "upn": user_id,
        "unique_name": user_id,
        "scp": scopes,
        "appid": MOCK_CONFIG["client_id"],
        "appidacr": "1",
        "name": user_id.split("@")[0].title(),
        "given_name": user_id.split("@")[0].split(".")[0].title(),
        "family_name": user_id.split("@")[0].split(".")[1].title() if "." in user_id else "",
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return {
        "access_token": token,
        "expires_in": expires_in,
        "token_type": "Bearer",
        "scope": scopes,
    }


@app.route("/token", methods=["POST"])
def token_endpoint():
    """
    Mock Entra ID token endpoint.
    
    Accepts OBO flow requests and returns mock tokens.
    """
    try:
        data = request.get_json() or {}

        # Extract grant type
        grant_type = data.get("grant_type")

        if grant_type == "urn:ietf:params:oauth:grant-type:jwt-bearer":
            # OBO Flow (on-behalf-of)
            # This is what the backend uses for delegated access
            return handle_obo_flow(data)

        elif grant_type == "client_credentials":
            # Client credentials flow (service-to-service)
            return handle_client_credentials_flow(data)

        elif grant_type == "refresh_token":
            # Refresh token flow
            return handle_refresh_token_flow(data)

        else:
            return jsonify({"error": "unsupported_grant_type"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def handle_obo_flow(data: Dict[str, Any]) -> tuple:
    """Handle OBO (on-behalf-of) token exchange."""
    # Validate required fields
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")
    assertion = data.get("assertion")  # User's access token (in real flow)
    requested_scope = data.get("scope", "https://analysis.windows.net/.default")

    # In a real OBO flow, we'd validate the user's token
    # For mock purposes, we just verify credentials
    if client_id != MOCK_CONFIG["client_id"]:
        return jsonify({"error": "invalid_client"}), 401

    if client_secret != MOCK_CONFIG["client_secret"]:
        return jsonify({"error": "invalid_client"}), 401

    # Extract user from assertion (in real flow, this would be decoded JWT)
    # For mock, allow test values
    user_id = data.get("user_id", "user@example.com")
    tenant_id = data.get("tenant_id", MOCK_CONFIG["tenant_id"])

    # Create delegated token (as the user)
    token_response = create_mock_token(user_id, tenant_id, requested_scope)

    return jsonify(token_response), 200


def handle_client_credentials_flow(data: Dict[str, Any]) -> tuple:
    """Handle client credentials token exchange (service principal)."""
    client_id = data.get("client_id")
    client_secret = data.get("client_secret")

    if client_id != MOCK_CONFIG["client_id"]:
        return jsonify({"error": "invalid_client"}), 401

    if client_secret != MOCK_CONFIG["client_secret"]:
        return jsonify({"error": "invalid_client"}), 401

    # Create service principal token
    token_response = create_mock_token(
        user_id=f"sp:{MOCK_CONFIG['client_id']}",
        tenant_id=MOCK_CONFIG["tenant_id"],
        scopes="https://analysis.windows.net/.default",
    )

    return jsonify(token_response), 200


def handle_refresh_token_flow(data: Dict[str, Any]) -> tuple:
    """Handle refresh token exchange."""
    refresh_token = data.get("refresh_token")
    client_id = data.get("client_id")

    # In mock, we don't validate refresh token format
    # Just validate client credentials
    if client_id != MOCK_CONFIG["client_id"]:
        return jsonify({"error": "invalid_client"}), 401

    # Return new access token
    user_id = data.get("user_id", "user@example.com")
    token_response = create_mock_token(
        user_id=user_id,
        tenant_id=MOCK_CONFIG["tenant_id"],
        scopes="https://analysis.windows.net/.default",
    )

    return jsonify(token_response), 200


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "mock-entra-id"}), 200


@app.route("/.well-known/openid-configuration", methods=["GET"])
def openid_config():
    """Mock OpenID configuration endpoint."""
    return jsonify(
        {
            "issuer": MOCK_CONFIG["issuer"],
            "token_endpoint": "http://localhost:5555/token",
            "authorization_endpoint": "http://localhost:5555/authorize",
            "jwks_uri": "http://localhost:5555/.well-known/jwks.json",
        }
    ), 200


@app.route("/.well-known/jwks.json", methods=["GET"])
def jwks():
    """Mock JWKS endpoint (returns empty for local testing)."""
    return jsonify({"keys": []}), 200


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("  Mock Entra ID Server for Local OBO Testing")
    print("=" * 70)
    print("\n📍 Configuration:")
    print(f"   Tenant ID:     {MOCK_CONFIG['tenant_id']}")
    print(f"   Client ID:     {MOCK_CONFIG['client_id']}")
    print(f"   Client Secret: {MOCK_CONFIG['client_secret']}")
    print("\n🔗 Endpoints:")
    print("   Token:         http://localhost:5555/token")
    print("   Health:        http://localhost:5555/health")
    print("   OpenID Config: http://localhost:5555/.well-known/openid-configuration")
    print("\n💡 Usage:")
    print("   Set environment variables:")
    print("   export AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012")
    print("   export AZURE_CLIENT_ID=87654321-4321-4321-4321-210987654321")
    print("   export AZURE_CLIENT_SECRET=mock-secret-key-12345")
    print("   export AZURE_TOKEN_ENDPOINT=http://localhost:5555/token")
    print("\n✅ Running on http://localhost:5555")
    print("   Press Ctrl+C to stop\n")
    print("=" * 70 + "\n")

    app.run(host="0.0.0.0", port=5555, debug=True, use_reloader=False)
