# Testing OBO Without Azure - Quick Guide

## TL;DR - Test OBO in 3 Commands (No Azure Needed!)

```bash
# Terminal 1: Start mock Entra ID server
python scripts/mock_entra_server.py

# Terminal 2: Start backend services
docker compose --env-file .env.local up -d

# Terminal 3: Run OBO flow test
python scripts/test_obo_flow.py
```

**That's it!** You'll see green checkmarks confirming OBO works without real Azure. ✅

---

## What's Happening (Architecture)

### Without Azure (Local Testing):
```
User Login (Mock MSAL)
    ↓
Refresh Token (simulated)
    ↓
Backend calls Mock Entra ID (http://localhost:5555/token)
    ↓
Mock Entra ID issues JWT token with user's identity
    ↓
Backend routes to Power BI MCP with delegated token
    ↓
Power BI MCP sees user: analyst@company.com
    ↓
Query result: Only user's accessible data (RLS enforced)
```

### With Real Azure (Production):
```
User Login (Real MSAL)
    ↓
Refresh Token (from Azure Entra ID)
    ↓
Backend calls https://login.microsoftonline.com/{tenant}/token
    ↓
Azure Entra ID issues JWT token with user's identity
    ↓
Backend routes to Power BI MCP with delegated token
    ↓
Power BI sees user: analyst@company.com
    ↓
Query result: Only user's accessible data (RLS enforced)
```

**The flow is identical!** The difference is only where the token comes from.

---

## Step-by-Step: How to Test OBO Locally

### Prerequisites
- Docker running
- Python 3.12+
- Flask (`pip install flask pyjwt`)

### Step 1: Prepare Configuration

Create `.env.local`:
```env
# Enable OBO mode
LOCAL_MODE=false
ENABLE_USER_AUTH_OBO=true

# Point to mock Entra ID (localhost, not Azure)
AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012
AZURE_CLIENT_ID=87654321-4321-4321-4321-210987654321
AZURE_CLIENT_SECRET=mock-secret-key-12345
AZURE_TOKEN_ENDPOINT=http://localhost:5555/token

# GitHub token (for Copilot SDK)
COPILOT_GITHUB_TOKEN=ghp_xxxxx
```

### Step 2: Start Mock Entra ID

```bash
cd scripts
python mock_entra_server.py
```

Output:
```
========================================================================
  Mock Entra ID Server for Local OBO Testing
========================================================================

📍 Configuration:
   Tenant ID:     12345678-1234-1234-1234-123456789012
   Client ID:     87654321-4321-4321-4321-210987654321
   Client Secret: mock-secret-key-12345

🔗 Endpoints:
   Token:         http://localhost:5555/token
   Health:        http://localhost:5555/health

✅ Running on http://localhost:5555
   Press Ctrl+C to stop
```

**Leaves this running. Ctrl+C to stop.**

### Step 3: Start Backend Services

In new terminal:
```bash
docker compose --env-file .env.local up -d
```

Wait for services to be healthy:
```bash
# Check backend
curl http://localhost:8000/api/health
# Should return: 200 OK

# Check agent
curl http://localhost:8088/health
# Should return: 200 OK
```

### Step 4: Run OBO Test Script

In another new terminal:
```bash
python scripts/test_obo_flow.py
```

Expected output:
```
======================================================================
  Testing OBO Flow with Mock Entra ID
======================================================================

1️⃣  Checking Prerequisites
   ✅ Mock Entra ID is running
   ✅ Backend healthy: 200

2️⃣  Testing Mock Entra ID Token Endpoint
   ✅ Token exchange succeeded
      Access Token: eyJhbGciOiJIUzI1NiI...
      Expires In: 3600 seconds

3️⃣  Testing Backend OBO Token Exchange Endpoint
   ✅ Backend OBO token exchange succeeded
      Access Token: eyJhbGciOiJIUzI1NiI...
      User ID: analyst@company.com

4️⃣  Testing Agent Invocation with OBO Context
   ✅ Agent request successful: 202
      Agent is processing request with user's identity
      Power BI MCP will receive delegated access token
      User will see only their accessible data

5️⃣  Verifying Backend Configuration
   ✅ Backend health check passed
      To verify OBO mode, check backend logs:
      docker compose logs backend | grep 'Auth Mode'

======================================================================
✅ OBO Flow Test Complete!
======================================================================

What Happened:
1. Mock Entra ID issued delegated access token
2. Backend exchanged user's refresh token for access token
3. Agent request included user's identity (analyst@company.com)
4. Power BI MCP will use delegated token
5. User sees only data they have access to (RLS enforced)

Next Steps:
1. Check backend logs: docker compose logs backend
2. Look for 'Auth Mode: user_obo' confirmation
3. Send real messages via frontend: http://localhost:3000
4. Verify Power BI MCP receives delegated token
5. Create PR when everything works! 🚀
```

**All green checkmarks = OBO flow works!** ✅

---

## Manual Testing (With curl)

### Test 1: Mock Entra ID Token Exchange

```bash
# Simulate OBO flow through mock Entra ID
curl -X POST http://localhost:5555/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
    "client_id": "87654321-4321-4321-4321-210987654321",
    "client_secret": "mock-secret-key-12345",
    "scope": "https://analysis.windows.net/.default",
    "user_id": "analyst@company.com",
    "assertion": "mock-user-token",
    "tenant_id": "12345678-1234-1234-1234-123456789012"
  }' | jq .

# Response:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIs...",
#   "expires_in": 3600,
#   "token_type": "Bearer",
#   "scope": "https://analysis.windows.net/.default"
# }
```

### Test 2: Backend OBO Token Exchange

```bash
# Frontend sends user's refresh token to backend
# Backend exchanges it for delegated access token
curl -X POST http://localhost:8000/api/token/obo-exchange \
  -H "Content-Type: application/json" \
  -d '{
    "user_refresh_token": "mock-user-refresh-token",
    "scope": "https://analysis.windows.net/.default",
    "user_id": "analyst@company.com"
  }' | jq .

# Response:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIs...",
#   "expires_in": 3600,
#   "user_id": "analyst@company.com"
# }
```

### Test 3: Agent Invocation with User Context

```bash
# Send agent request with user's identity
curl -X POST http://localhost:8000/api/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-obo-1",
    "userId": "analyst@company.com",
    "message": "What Power BI workspaces can I access?",
    "useCase": "generic",
    "authContext": {
      "mode": "user_obo",
      "userId": "analyst@company.com",
      "tenantId": "12345678-1234-1234-1234-123456789012",
      "oboEnabled": true
    }
  }' | jq .

# Response:
# {
#   "conversationId": "test-obo-1",
#   "type": "agent_response",
#   ...
# }
```

---

## Verify in Logs

Check backend logs to confirm OBO mode is active:

```bash
# View live logs
docker compose logs -f backend

# Search for auth mode
docker compose logs backend | grep "Auth Mode"

# Expected output:
# ✅ "Auth Mode: user_obo" (OBO enabled, user delegated)
# OR
# ✅ "Auth Mode: agent_app" (Service principal, no delegation)
```

---

## How It Works (Detailed)

### The Mock Entra ID Server

Located at: `scripts/mock_entra_server.py`

What it does:
1. **Listens on** http://localhost:5555
2. **Simulates** Azure Entra ID token exchange
3. **Accepts** user credentials (in real flow, would be JWT from MSAL)
4. **Returns** JWT tokens with user's identity encoded
5. **Supports** 3 flows:
   - OBO (on-behalf-of) - user delegation
   - Client credentials - service principal
   - Refresh token - token refresh

### The OBO Flow

1. **User logs in** (frontend with MSAL or mock)
2. **Frontend gets** refresh token
3. **Frontend sends** refresh token to backend
4. **Backend calls** `/api/token/obo-exchange` endpoint
5. **Backend exchanges** refresh token → access token
   - Calls mock Entra ID at http://localhost:5555/token
   - Mock Entra ID returns JWT token with user's identity
6. **Backend injects** auth context into agent request
   - Mode: "user_obo"
   - UserId: "analyst@company.com"
   - Token: stored in ContextVars (request-scoped)
7. **Agent routes** to Power BI MCP
8. **MCP uses** delegated access token (user's identity)
9. **Power BI** applies row-level security (RLS)
10. **User sees** only their accessible data

---

## Agent Deployment Options

| Option | Setup Time | Cost | Best For |
|--------|------------|------|----------|
| **Docker Compose** | 5 min | Free | Local development |
| **Docker Images** | 10 min | Free | Custom deployments |
| **Azure Container Instances** | 15 min | Low | Serverless testing |
| **App Service** | 20 min | Medium | Traditional web apps |
| **Kubernetes (AKS)** | 45 min | High | Enterprise production |
| **Foundry Hosted** | Managed | Enterprise | Fully managed service |

---

## Quick Deployment Commands

### Local (Already Covered)
```bash
docker compose up -d
```

### Azure Container Instances
```bash
az container create \
  --resource-group my-rg \
  --name kratos-agent \
  --image myregistry.azurecr.io/kratos-agent-backend:latest \
  --ports 8000 \
  --environment-variables ENABLE_USER_AUTH_OBO='true'
```

### App Service
```bash
az appservice plan create --name my-plan --sku B1 --is-linux
az webapp create --plan my-plan --name my-app
az webapp config container set \
  --docker-custom-image-name myregistry.azurecr.io/kratos-agent:latest
```

### Kubernetes
```bash
kubectl apply -f k8s-deployment.yaml
# See OBO_TESTING_AND_DEPLOYMENT.md for full manifest
```

---

## Complete Files Reference

| File | Purpose |
|------|---------|
| `scripts/mock_entra_server.py` | Mock Azure Entra ID (run this first) |
| `scripts/test_obo_flow.py` | End-to-end OBO test (run this to validate) |
| `OBO_TESTING_AND_DEPLOYMENT.md` | Comprehensive guide (2000+ lines) |
| `.env.local` | Your local configuration |
| `docker-compose.yml` | All 4 services (frontend, backend, agent, storage) |
| `src/backend/app/services/auth_service.py` | Token exchange logic |
| `src/backend/app/routers/token.py` | OBO endpoint |

---

## Testing Checklist

- [ ] Mock Entra ID running: `python scripts/mock_entra_server.py`
- [ ] Backend services healthy: `curl http://localhost:8000/api/health`
- [ ] OBO test passes: `python scripts/test_obo_flow.py`
- [ ] Backend logs show auth mode: `docker compose logs backend | grep Auth`
- [ ] Frontend loads: http://localhost:3000
- [ ] Can send messages via frontend
- [ ] Backend requests include auth context
- [ ] Power BI MCP receives delegated token
- [ ] User sees only their data

---

## Troubleshooting

### "Mock Entra ID not running"
```bash
# Check if it's still running
curl http://localhost:5555/health

# If not, start it
python scripts/mock_entra_server.py
```

### "Backend can't connect to mock Entra ID"
```bash
# Verify endpoint in .env.local
grep AZURE_TOKEN_ENDPOINT .env.local

# Should be:
AZURE_TOKEN_ENDPOINT=http://localhost:5555/token

# Restart backend
docker compose restart backend
```

### "Token exchange fails"
```bash
# Check mock Entra ID logs
# Look for POST /token requests

# Verify credentials in .env.local match mock server:
# AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012
# AZURE_CLIENT_ID=87654321-4321-4321-4321-210987654321
# AZURE_CLIENT_SECRET=mock-secret-key-12345
```

### "OBO mode not active"
```bash
# Check if LOCAL_MODE is false
grep LOCAL_MODE .env.local
# Should be: LOCAL_MODE=false

# Check if ENABLE_USER_AUTH_OBO is true
grep ENABLE_USER_AUTH_OBO .env.local
# Should be: ENABLE_USER_AUTH_OBO=true

# Restart backend to apply changes
docker compose restart backend
```

---

## Next Steps

1. ✅ **Test OBO locally** (3 commands above)
2. ✅ **Verify all tests pass** (green checkmarks)
3. ✅ **Check backend logs** (Auth Mode: user_obo)
4. ✅ **Test via frontend** (http://localhost:3000)
5. ✅ **Create PR** when everything works

---

## Key Takeaway

**You don't need Azure to test OBO!**

The mock Entra ID server simulates the token exchange perfectly. Once you verify it works locally, the same code works with real Azure without any changes.

```
Local Testing (Mock Entra ID) → Production (Real Entra ID)
Same code path, different token source
```

---

**Ready to test? Run the 3 commands above!** 🚀
