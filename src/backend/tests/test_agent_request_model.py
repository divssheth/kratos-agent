"""Tests for AgentRequest compatibility and optional auth context."""

from app.models import AgentRequest


def test_agent_request_without_auth_context_is_valid():
    payload = {
        "conversationId": "conv-1",
        "message": "hello",
        "useCase": "generic",
        "attachments": [],
    }
    req = AgentRequest(**payload)
    assert req.authContext is None


def test_agent_request_with_auth_context_is_valid():
    payload = {
        "conversationId": "conv-2",
        "message": "hello",
        "useCase": "generic",
        "attachments": [],
        "authContext": {
            "mode": "obo",
            "userId": "alice@contoso.com",
            "tenantId": "tenant-123",
            "oboEnabled": True,
        },
    }
    req = AgentRequest(**payload)
    assert req.authContext is not None
    assert req.authContext.mode == "obo"
    assert req.authContext.oboEnabled is True
