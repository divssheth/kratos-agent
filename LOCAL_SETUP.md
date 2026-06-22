# Complete Local Development Setup - Power BI OBO Feature

This guide helps you run the entire solution locally (frontend + backend + mocks) to validate the Power BI OBO feature end-to-end.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (Next.js)                                          │
│ http://localhost:3000                                       │
│ • User login (mock MSAL)                                    │
│ • Token exchange endpoint                                   │
│ • Chat interface                                            │
└────────────────────┬────────────────────────────────────────┘
                     │ API calls + tokens
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ BACKEND (FastAPI)                                           │
│ http://localhost:8000                                       │
│ • POST /api/token/obo-exchange (NEW - OBO flow)            │
│ • POST /api/agent/invoke (agent invocations)               │
│ • GET /api/health                                          │
└────────────────────┬────────────────────────────────────────┘
                     │ agent requests
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ FOUNDRY AGENT (Local)                                       │
│ http://localhost:8088                                       │
│ • Processes agent logic                                    │
│ • Routes to MCPs (Power BI, etc.)                         │
└────────────────────┬────────────────────────────────────────┘
                     │ tool calls
         ┌───────────┼───────────┐
         ↓           ↓           ↓
    ┌────────┐  ┌──────────┐  ┌─────────────┐
    │Azurite │  │Power BI  │  │Other MCPs   │
    │Storage │  │MCP Mock  │  │(Salesforce, │
    │10000   │  │5173      │  │etc)         │
    └────────┘  └──────────┘  └─────────────┘
```

## Prerequisites

### Required
- Docker & Docker Compose
- Node.js 18+ (for frontend)
- Python 3.12+ (optional, for direct backend run)
- Git

### Optional
- Azure CLI (for cloud deployment)
- VS Code (recommended)

## Quick Start (3 commands)

### 1. Prerequisites Check & Setup

```bash
# Clone the feature branch (if not already there)
git clone -b feature/powerbi-obo-mcp https://github.com/divssheth/kratos-agent.git
cd kratos-agent

# Install Node dependencies for frontend
cd src/frontend
npm install
cd ../..

# Get GitHub token (required for Copilot SDK)
# Generate at: https://github.com/settings/tokens/new
# Permissions: only needs read access to public repos
```

### 2. Backend + Services (Docker Compose)

```bash
# Copy environment template
cp .env.local.example .env.local

# Edit .env.local and add your COPILOT_GITHUB_TOKEN
# Then run:
./run-local.ps1  # Windows PowerShell
# OR
./run-local.sh   # Mac/Linux
```

Expected output:
```
✅ azurite running on http://localhost:10000
✅ hosted-agent running on http://localhost:8088
✅ backend running on http://localhost:8000
```

### 3. Frontend (Separate Terminal)

```bash
cd src/frontend
npm run dev
```

Expected output:
```
▲ Next.js 14.2.0
- ready started server on 0.0.0.0:3000
```

Then open: **http://localhost:3000**

---

## Complete Setup Guide

### Step 1: Environment Configuration

Create `.env.local`:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` and add:

```env
# Required: Get from https://github.com/settings/tokens
COPILOT_GITHUB_TOKEN=ghp_xxxxx

# Optional: For advanced OBO testing (when not in local mode)
# ENABLE_USER_AUTH_OBO=false  (default)
# AZURE_TENANT_ID=your-tenant-id
# AZURE_CLIENT_ID=your-client-id
# AZURE_CLIENT_SECRET=your-secret
```

**Important**: For local testing, all OBO will be skipped automatically (local_mode=true).

### Step 2: Start Backend Services

**Option A: Docker Compose (Recommended)**

```bash
# Terminal 1: Start all backend services
./run-local.ps1  # Windows
./run-local.sh   # Mac/Linux

# Wait for output:
# ✅ Azurite: http://localhost:10000
# ✅ Hosted Agent: http://localhost:8088
# ✅ Backend: http://localhost:8000/docs
```

**Option B: Manual (for development)**

If you prefer to run services individually:

```bash
# Terminal 1: Azurite (Azure Storage mock)
docker run -it -p 10000:10000 mcr.microsoft.com/azure-storage/azurite:latest azurite --blobHost 0.0.0.0 --loose --skipApiVersionCheck

# Terminal 2: Backend
cd src/backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Hosted Agent
cd src/hosted-agent
python main.py  # or: gunicorn -b 0.0.0.0:8088 main:app
```

### Step 3: Start Frontend

```bash
# Terminal (new): Frontend
cd src/frontend
npm run dev
```

### Step 4: Access the Application

```
Frontend: http://localhost:3000
Backend API: http://localhost:8000/docs (Swagger UI)
Storage: http://localhost:10000 (Azurite)
Hosted Agent: http://localhost:8088
```

---

## Testing the Power BI OBO Feature Locally

### Test 1: Default Mode (Agent SP - Service Principal)

In local mode, everything uses the service principal (Agent SP mode):

**Steps:**
1. Open http://localhost:3000
2. Click "Login" (mock login in local mode)
3. Send message: "Query Power BI workspace list"
4. Expected: Works, uses service account access

**What's happening:**
- Backend receives request in local mode
- `ENABLE_USER_AUTH_OBO=false` (default)
- Auth context is stripped
- Power BI MCP uses service account

### Test 2: Auth Context Flow (Local Mode)

**Steps:**
1. Backend running in local mode
2. Send chat request
3. Verify auth context is NOT passed (local mode override)

**Verification:**
```bash
# Check backend logs for:
# "Auth Mode: agent_app" 
# "Auth context stripped: true"
```

### Test 3: Backend API Directly (Advanced)

Test the OBO endpoint directly:

```bash
# Test health check
curl http://localhost:8000/api/health

# Test agent invocation
curl -X POST http://localhost:8000/api/agent/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-conv-1",
    "message": "List Power BI workspaces",
    "useCase": "generic"
  }' | jq .

# Test OBO token exchange (will fail gracefully in local mode)
curl -X POST http://localhost:8000/api/token/obo-exchange \
  -H "Content-Type: application/json" \
  -d '{
    "user_refresh_token": "mock-token",
    "scope": "https://analysis.windows.net/.default"
  }' | jq .
```

---

## Docker Compose Breakdown

The `docker-compose.yml` includes:

### Service 1: Azurite (Azure Storage)
```yaml
azurite:
  image: mcr.microsoft.com/azure-storage/azurite:latest
  ports:
    - "10000:10000"  # Blob Storage port
```
- Mocks Azure Blob Storage
- Data persisted in `./.local/azurite/`
- Used for blob skills storage

### Service 2: Hosted Agent (Foundry)
```yaml
hosted-agent:
  build: src/hosted-agent/Dockerfile
  ports:
    - "8088:8088"
```
- Runs the Foundry agent runtime
- Routes to MCPs (Power BI, Salesforce, etc.)
- Data in `./.local/hosted-agent/`

### Service 3: Backend (FastAPI)
```yaml
backend:
  build: src/backend/Dockerfile
  ports:
    - "8000:8000"
```
- REST API for frontend
- OBO token exchange
- Agent invocation proxy
- Data in `./.local/backend/`

---

## Troubleshooting Local Setup

### Issue: "Docker not found"
**Solution:**
```bash
# Install Docker Desktop from:
# https://www.docker.com/products/docker-desktop

# Verify installation:
docker --version
docker compose version
```

### Issue: Port already in use (e.g., 3000, 8000, 8088)
**Solution:**
```bash
# Find what's using the port (Mac/Linux):
lsof -i :3000

# Windows PowerShell:
Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue

# Kill the process or use different ports:
# Frontend: PORT=3001 npm run dev
# Backend: --port 8001
# Hosted Agent: PORT=8089
```

### Issue: "COPILOT_GITHUB_TOKEN" not set
**Solution:**
1. Get token: https://github.com/settings/tokens/new
2. Add to `.env.local`:
   ```env
   COPILOT_GITHUB_TOKEN=ghp_xxxxx
   ```
3. Restart Docker Compose

### Issue: Backend can't connect to hosted-agent
**Solution:**
```bash
# Verify hosted-agent is healthy:
curl http://localhost:8088/health

# Check Docker logs:
docker logs kratos-agent-hosted-agent-1
docker logs kratos-agent-backend-1

# Ensure depends_on in docker-compose.yml is correct
```

### Issue: Frontend won't connect to backend
**Solution:**
```bash
# Verify backend is running:
curl http://localhost:8000/docs

# Check if CORS is configured (usually enabled in dev mode)
# Frontend should use: http://localhost:8000/api/...
```

---

## Advanced: Cloud Deployment

### Option 1: Azure Container Instances (ACI)

```bash
# Push images to ACR
az acr build --registry <your-acr> --image kratos-agent:latest .

# Deploy with Azure Container Instances
az container create \
  --resource-group <your-rg> \
  --name kratos-agent \
  --image <your-acr>.azurecr.io/kratos-agent:latest \
  --ports 80 8000 3000 \
  --environment-variables COPILOT_GITHUB_TOKEN=$COPILOT_GITHUB_TOKEN
```

### Option 2: Docker Compose on VM

```bash
# On Azure VM:
git clone -b feature/powerbi-obo-mcp https://github.com/divssheth/kratos-agent.git
cd kratos-agent
./run-local.sh
```

### Option 3: Kubernetes (AKS)

```bash
# Create deployment manifest:
cat <<EOF > kratos-agent-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kratos-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kratos-agent
  template:
    metadata:
      labels:
        app: kratos-agent
    spec:
      containers:
      - name: backend
        image: <your-acr>.azurecr.io/kratos-agent-backend:latest
        ports:
        - containerPort: 8000
      - name: frontend
        image: <your-acr>.azurecr.io/kratos-agent-frontend:latest
        ports:
        - containerPort: 3000
EOF

kubectl apply -f kratos-agent-deployment.yaml
```

---

## Testing End-to-End OBO Flow

### Setup: Enable OBO Mode (if using Entra ID)

**Note**: Local mode forces Agent SP. To test OBO:

1. Disable local mode:
   ```env
   LOCAL_MODE=false
   ```

2. Configure Entra ID:
   ```env
   AZURE_TENANT_ID=your-tenant
   AZURE_CLIENT_ID=your-client-id
   AZURE_CLIENT_SECRET=your-secret
   ```

3. Create mock Entra ID endpoint (optional):
   See `scripts/mock_entra_server.py`

### Test Flow: OBO Mode

```bash
# 1. Frontend logs in (real or mock MSAL)
# User gets refresh token

# 2. Frontend calls token exchange
curl -X POST http://localhost:8000/api/token/obo-exchange \
  -H "Content-Type: application/json" \
  -d '{
    "user_refresh_token": "eyJ...",
    "scope": "https://analysis.windows.net/.default",
    "user_id": "user@company.com"
  }'

# Response:
# {
#   "access_token": "eyJ...",
#   "expires_in": 3600,
#   "user_id": "user@company.com"
# }

# 3. Frontend uses access token in agent request
# 4. Backend routes to Power BI MCP with user context
# 5. Power BI MCP queries semantics models as user
# 6. User sees only data they can access
```

---

## File Structure

```
kratos-agent/
├── .env.local              ← Edit with your settings
├── docker-compose.yml      ← Services definition
├── run-local.ps1          ← Start everything (Windows)
├── run-local.sh           ← Start everything (Mac/Linux)
│
├── src/
│   ├── backend/
│   │   ├── Dockerfile
│   │   ├── app/
│   │   │   ├── config.py      ← Settings/flags
│   │   │   ├── main.py         ← FastAPI app
│   │   │   ├── services/
│   │   │   │   ├── auth_mode_controller.py   ← OBO switching
│   │   │   │   ├── auth_service.py           ← OBO tokens
│   │   │   │   └── foundry_agent_proxy.py    ← Proxy
│   │   │   └── routers/
│   │   │       └── token.py    ← OBO endpoint
│   │   └── tests/
│   │       ├── test_auth*.py   ← 76 tests
│   │       └── test_end_to_end*.py
│   │
│   ├── frontend/            ← Next.js app
│   │   ├── package.json
│   │   ├── src/
│   │   │   └── pages/
│   │   │       ├── index.tsx ← Main chat UI
│   │   │       └── api/
│   │   │           └── token-exchange.ts (optional - for mock)
│   │   └── public/
│   │
│   └── hosted-agent/
│       ├── Dockerfile
│       ├── main.py
│       └── agent.yaml
│
├── use-cases/generic/
│   ├── apm.yml              ← MCP registration (includes Power BI)
│   └── skills/
│
├── scripts/
│   ├── demo_local_auth_flow.py    ← Local demo (no server needed)
│   └── mock_entra_server.py       ← Mock Entra ID (optional)
│
├── TESTING_LOCAL.md         ← Testing guide
├── IMPLEMENTATION_COMPLETE.md ← PR info
└── LOCAL_SETUP.md           ← This file
```

---

## Quick Validation Checklist

After starting all services:

- [ ] Backend responds: `curl http://localhost:8000/docs`
- [ ] Frontend loads: `open http://localhost:3000`
- [ ] Can send chat message
- [ ] Backend shows auth mode: `docker logs kratos-agent-backend-1 | grep "Auth Mode"`
- [ ] No errors in console

---

## Next: Test Power BI OBO Feature

Once everything is running:

1. **View the demo** (no server needed):
   ```bash
   python scripts/demo_local_auth_flow.py
   ```

2. **Run auth tests**:
   ```bash
   cd src/backend
   python -m pytest tests/test_auth*.py -v
   ```

3. **Send test requests** to backend:
   ```bash
   curl http://localhost:8000/api/health
   curl -X POST http://localhost:8000/api/agent/invoke -d '{...}'
   ```

---

**Ready to test the complete solution!** 🚀

For issues, check the troubleshooting section or read `TESTING_LOCAL.md` for comprehensive validation steps.
