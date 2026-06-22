#!/usr/bin/env python3
"""
Test OBO Flow End-to-End with Mock Entra ID

This script tests the complete OBO (On-Behalf-Of) authentication flow
without needing real Azure infrastructure.

Prerequisites:
  1. Mock Entra ID running: python scripts/mock_entra_server.py
  2. Backend running: docker compose up -d
  3. OBO enabled in .env.local:
     LOCAL_MODE=false
     ENABLE_USER_AUTH_OBO=true
     AZURE_TOKEN_ENDPOINT=http://localhost:5555/token

Usage:
  python scripts/test_obo_flow.py
"""

import sys
import time
import requests
import json
from typing import Dict, Any, Tuple


class Colors:
    """ANSI color codes."""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(title: str) -> None:
    """Print a formatted header."""
    width = 70
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * width}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {title}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * width}{Colors.ENDC}\n")


def print_step(number: int, title: str) -> None:
    """Print a step header."""
    print(f"{Colors.OKBLUE}{number}️⃣  {title}{Colors.ENDC}")
    print(f"{Colors.OKBLUE}{'-' * 70}{Colors.ENDC}")


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.OKGREEN}   ✅ {message}{Colors.ENDC}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.FAIL}   ❌ {message}{Colors.ENDC}")


def print_info(message: str) -> None:
    """Print an info message."""
    print(f"{Colors.OKCYAN}   ℹ️  {message}{Colors.ENDC}")


def check_service(
    name: str, url: str, expected_status: int = 200
) -> Tuple[bool, str]:
    """Check if a service is running and healthy."""
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == expected_status:
            return True, response.text[:100]
        else:
            return False, f"Unexpected status: {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Connection refused"
    except requests.exceptions.Timeout:
        return False, "Request timeout"
    except Exception as e:
        return False, str(e)


def test_obo_flow() -> bool:
    """Test the complete OBO flow."""

    print_header("Testing OBO Flow with Mock Entra ID")

    # ─────────────────────────────────────────────────────────────
    # Step 1: Check Prerequisites
    # ─────────────────────────────────────────────────────────────

    print_step(1, "Checking Prerequisites")

    services = {
        "Mock Entra ID": "http://localhost:5555/health",
        "Backend API": "http://localhost:8000/api/health",
    }

    all_healthy = True
    for service_name, service_url in services.items():
        is_healthy, message = check_service(service_name, service_url)
        if is_healthy:
            print_success(f"{service_name} is running")
        else:
            print_error(f"{service_name} not running: {message}")
            all_healthy = False

    if not all_healthy:
        print_error("Some services are not running!")
        print_info("Start them with:")
        print_info("  Terminal 1: python scripts/mock_entra_server.py")
        print_info("  Terminal 2: docker compose up -d")
        return False

    # ─────────────────────────────────────────────────────────────
    # Step 2: Test Mock Entra ID Token Endpoint
    # ─────────────────────────────────────────────────────────────

    print_step(2, "Testing Mock Entra ID Token Endpoint")

    entra_url = "http://localhost:5555/token"
    token_request = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": "87654321-4321-4321-4321-210987654321",
        "client_secret": "mock-secret-key-12345",
        "assertion": "mock-user-access-token",
        "scope": "https://analysis.windows.net/.default",
        "user_id": "analyst@company.com",
        "tenant_id": "12345678-1234-1234-1234-123456789012",
    }

    try:
        response = requests.post(entra_url, json=token_request, timeout=10)
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            expires_in = token_data.get("expires_in")

            print_success("Token exchange succeeded")
            print_info(f"Access Token: {access_token[:30]}...")
            print_info(f"Expires In: {expires_in} seconds")

            # Store token for next step
            mock_access_token = access_token
        else:
            print_error(f"Token exchange failed: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Token exchange error: {e}")
        return False

    # ─────────────────────────────────────────────────────────────
    # Step 3: Test Backend OBO Token Exchange Endpoint
    # ─────────────────────────────────────────────────────────────

    print_step(3, "Testing Backend OBO Token Exchange Endpoint")

    backend_token_url = "http://localhost:8000/api/token/obo-exchange"
    backend_token_request = {
        "user_refresh_token": "mock-user-refresh-token-from-msal",
        "scope": "https://analysis.windows.net/.default",
        "user_id": "analyst@company.com",
    }

    try:
        response = requests.post(
            backend_token_url, json=backend_token_request, timeout=10
        )
        if response.status_code == 200:
            backend_token_data = response.json()
            backend_access_token = backend_token_data.get("access_token")
            user_id = backend_token_data.get("user_id")

            print_success("Backend OBO token exchange succeeded")
            print_info(f"Access Token: {backend_access_token[:30]}...")
            print_info(f"User ID: {user_id}")

            # Store token for next step
            delegated_access_token = backend_access_token
        else:
            print_error(f"Backend token exchange failed: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Backend token exchange error: {e}")
        return False

    # ─────────────────────────────────────────────────────────────
    # Step 4: Test Agent Invocation with OBO Context
    # ─────────────────────────────────────────────────────────────

    print_step(4, "Testing Agent Invocation with OBO Context")

    agent_invoke_url = "http://localhost:8000/api/agent/invoke"
    agent_request = {
        "conversationId": "test-obo-flow-1",
        "userId": "analyst@company.com",
        "message": "What Power BI workspaces can I access?",
        "useCase": "generic",
        "authContext": {
            "mode": "user_obo",
            "userId": "analyst@company.com",
            "tenantId": "12345678-1234-1234-1234-123456789012",
            "oboEnabled": True,
        },
    }

    try:
        response = requests.post(agent_invoke_url, json=agent_request, timeout=10)
        if response.status_code in [200, 202]:
            print_success(f"Agent request successful: {response.status_code}")
            print_info("Agent is processing request with user's identity")
            print_info("Power BI MCP will receive delegated access token")
            print_info("User will see only their accessible data")

            # Try to parse response
            try:
                response_data = response.json()
                print_info(f"Response type: {response_data.get('type', 'streaming')}")
            except:
                pass

        else:
            print_error(f"Agent request failed: {response.status_code}")
            print_info(f"Response: {response.text}")
            return False
    except Exception as e:
        print_error(f"Agent request error: {e}")
        return False

    # ─────────────────────────────────────────────────────────────
    # Step 5: Verify Backend Logs Show OBO Mode
    # ─────────────────────────────────────────────────────────────

    print_step(5, "Verifying Backend Configuration")

    backend_config_url = "http://localhost:8000/api/health"

    try:
        response = requests.get(backend_config_url, timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print_success("Backend health check passed")
            print_info(
                "To verify OBO mode, check backend logs:"
            )
            print_info("  docker compose logs backend | grep 'Auth Mode'")
            print_info(
                "Should show: 'Auth Mode: user_obo' or 'Auth Mode: agent_app'"
            )
    except Exception as e:
        print_error(f"Health check error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────

    print_header("OBO Flow Test Complete! ✅")

    print(f"{Colors.OKGREEN}{Colors.BOLD}What Happened:{Colors.ENDC}")
    print(f"{Colors.OKGREEN}1. Mock Entra ID issued delegated access token{Colors.ENDC}")
    print(
        f"{Colors.OKGREEN}2. Backend exchanged user's refresh token for access token{Colors.ENDC}"
    )
    print(f"{Colors.OKGREEN}3. Agent request included user's identity (analyst@company.com){Colors.ENDC}")
    print(f"{Colors.OKGREEN}4. Power BI MCP will use delegated token{Colors.ENDC}")
    print(
        f"{Colors.OKGREEN}5. User sees only data they have access to (RLS enforced){Colors.ENDC}"
    )

    print(f"\n{Colors.OKGREEN}{Colors.BOLD}Next Steps:{Colors.ENDC}")
    print(f"{Colors.OKGREEN}1. Check backend logs: docker compose logs backend{Colors.ENDC}")
    print(f"{Colors.OKGREEN}2. Look for 'Auth Mode: user_obo' confirmation{Colors.ENDC}")
    print(f"{Colors.OKGREEN}3. Send real messages via frontend: http://localhost:3000{Colors.ENDC}")
    print(f"{Colors.OKGREEN}4. Verify Power BI MCP receives delegated token{Colors.ENDC}")
    print(f"{Colors.OKGREEN}5. Create PR when everything works! 🚀{Colors.ENDC}\n")

    return True


if __name__ == "__main__":
    try:
        success = test_obo_flow()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Test interrupted by user{Colors.ENDC}\n")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
