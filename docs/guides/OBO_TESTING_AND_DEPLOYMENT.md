# Testing OBO Without Azure + Agent Deployment Guide

## Part 1: Testing OBO Without Azure ✅

You **don't need Azure** to test OBO! We provide a mock Entra ID server that simulates token exchange.

### What is OBO (On-Behalf-Of)?

```
User Login (Frontend)
    ↓
User's Refresh Token
    ↓
Backend exchanges for delegated access token
    ↓
Token uses user's identity, not service principal
    ↓
Power BI sees request as: user@company.com
    ↓
User sees only their data (Power BI RLS enforced)
```

### Testing OBO Locally (3 Steps)

#### Step 1: Start Mock Entra ID Server

In a terminal:
```bash
cd scripts
python mock_entra_server.py
```

Expected output:
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

#### Step 2: Configure Backend for OBO Testing

Create/edit `.env.local`:

```env
# Enable OBO mode
LOCAL_MODE=false
ENABLE_USER_AUTH_OBO=true

# Point to mock Entra ID (not real Azure)
AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012
AZURE_CLIENT_ID=87654321-4321-4321-4321-210987654321
AZURE_CLIENT_SECRET=mock-secret-key-12345
AZURE_TOKEN_ENDPOINT=http://localhost:5555/token

# GitHub token (required for Copilot SDK)
COPILOT_GITHUB_TOKEN=ghp_xxxxx
```

#### Step 3: Start Backend Services

In a new terminal:
```bash
docker compose --env-file .env.local up -d --build
```

Wait for services to be healthy:
```bash
# Check backend health
curl http://localhost:8000/api/health
# Should return 200 OK

# Check mock Entra ID health
curl http://localhost:5555/health
# Should return: {"status": "healthy", "service": "mock-entra-id"}
```

### Testing OBO Flow End-to-End

#### Option 1: Test via Backend API

```bash
# Step 1: Mock frontend gets user refresh token
USER_REFRESH_TOKEN="mock-refresh-token-from-msal"

# Step 2: Backend exchanges it for delegated access token
curl -X POST http://localhost:8000/api/token/obo-exchange \
  -H "Content-Type: application/json" \
  -d '{
    "user_refresh_token": "'$USER_REFRESH_TOKEN'",
    "scope": "https://analysis.windows.net/.default",
    "user_id": "analyst@company.com"
  }' | jq .

# Expected response:
# {
#   "access_token": "eyJ...",
#   "expires_in": 3600,
#   "user_id": "analyst@company.com"
# }

# Step 3: Use access token in agent request
curl -X POST http://localhost:8000/api/agent/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJ..." \
  -d '{
    "conversationId": "test-obo-1",
    "message": "List Power BI workspaces for my user",
    "authContext": {
      "mode": "user_obo",
      "userId": "analyst@company.com",
      "tenantId": "12345678-1234-1234-1234-123456789012",
      "oboEnabled": true
    }
  }' | jq .
```

#### Option 2: Test via Python Script

Create `test_obo_flow.py`:

```python
import requests
import json

# Configuration
BACKEND_URL = "http://localhost:8000"
MOCK_ENTRA_URL = "http://localhost:5555"

def test_obo_flow():
    """Test complete OBO flow with mock Entra ID."""
    
    print("\n" + "="*70)
    print("  Testing OBO Flow with Mock Entra ID")
    print("="*70)
    
    # Step 1: Verify mock Entra ID is running
    print("\n1️⃣  Checking mock Entra ID server...")
    try:
        resp = requests.get(f"{MOCK_ENTRA_URL}/health")
        print(f"   ✅ Mock Entra ID: {resp.json()['service']}")
    except:
        print("   ❌ Mock Entra ID not running. Start it with:")
        print("      python scripts/mock_entra_server.py")
        return
    
    # Step 2: Verify backend is running
    print("\n2️⃣  Checking backend...")
    try:
        resp = requests.get(f"{BACKEND_URL}/api/health")
        print(f"   ✅ Backend healthy: {resp.status_code}")
    except:
        print("   ❌ Backend not running. Start it with:")
        print("      docker compose up -d")
        return
    
    # Step 3: Test token exchange (OBO flow)
    print("\n3️⃣  Testing token exchange (OBO flow)...")
    token_resp = requests.post(
        f"{BACKEND_URL}/api/token/obo-exchange",
        json={
            "user_refresh_token": "mock-user-token",
            "scope": "https://analysis.windows.net/.default",
            "user_id": "analyst@company.com"
        }
    )
    
    if token_resp.status_code == 200:
        token_data = token_resp.json()
        print(f"   ✅ Token Exchange Successful!")
        print(f"      Access Token: {token_data['access_token'][:20]}...")
        print(f"      Expires In: {token_data['expires_in']} seconds")
        print(f"      User ID: {token_data['user_id']}")
    else:
        print(f"   ❌ Token Exchange Failed: {token_resp.status_code}")
        print(f"      {token_resp.text}")
        return
    
    # Step 4: Test agent invocation with auth context
    print("\n4️⃣  Testing agent invocation with user context...")
    agent_resp = requests.post(
        f"{BACKEND_URL}/api/agent/invoke",
        json={
            "conversationId": "test-obo-1",
            "message": "What data can I access?",
            "useCase": "generic",
            "authContext": {
                "mode": "user_obo",
                "userId": "analyst@company.com",
                "tenantId": "12345678-1234-1234-1234-123456789012",
                "oboEnabled": True
            }
        }
    )
    
    if agent_resp.status_code in [200, 202]:
        print(f"   ✅ Agent Request Successful: {agent_resp.status_code}")
        print(f"      Agent will use user's identity (analyst@company.com)")
        print(f"      Power BI MCP will receive delegated token")
        print(f"      User will see only their accessible data")
    else:
        print(f"   ❌ Agent Request Failed: {agent_resp.status_code}")
        print(f"      {agent_resp.text}")
        return
    
    print("\n" + "="*70)
    print("✅ OBO Flow Test Complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    test_obo_flow()
```

Run it:
```bash
pip install requests
python test_obo_flow.py
```

### What Happens in OBO Mode

```
User logs in as: analyst@company.com
    ↓
Frontend gets refresh token from MSAL (or mock)
    ↓
Backend exchanges refresh token for delegated access token
    (via mock Entra ID at http://localhost:5555/token)
    ↓
Token contains user's identity: analyst@company.com
    ↓
Backend injects auth context into agent request
    ↓
Agent routes to Power BI MCP
    ↓
Power BI MCP uses delegated token (as analyst@company.com)
    ↓
Query: "SELECT * FROM SalesData"
Result: Only rows where analyst has access (per RLS)
    ↓
User sees: Sales data for their region only
```

### Verify Auth Mode in Logs

```bash
# Check which mode backend is using
docker compose logs backend | grep "Auth Mode"

# Output options:
# ✅ "Auth Mode: user_obo" (delegated - user's identity)
# ✅ "Auth Mode: agent_app" (service principal - everyone sees same data)
```

---

## Part 2: Agent Deployment Options

The agent can be deployed in multiple ways depending on your needs:

### Option 1: Docker Compose (Local/Development)

**Best for:** Local development, quick testing

```bash
# Start everything
./setup-local-complete.ps1  # Windows
./setup-local-complete.sh   # Mac/Linux

# Or manually
docker compose --env-file .env.local up -d

# Stop
docker compose down
```

**Pros:**
- Simple, one command
- All services included
- Perfect for development

**Cons:**
- Not production-ready
- No scaling
- No auto-recovery

---

### Option 2: Docker Images Only

**Best for:** Building custom deployment solutions

```bash
# Build images
docker compose build

# Push to registry
docker tag kratos-agent-backend:latest myregistry.azurecr.io/kratos-agent-backend:latest
docker push myregistry.azurecr.io/kratos-agent-backend:latest

# Run anywhere Docker is available:
# - Local machine
# - VMs
# - Cloud providers
```

---

### Option 3: Azure Container Instances (ACI)

**Best for:** Serverless, pay-per-second, no infrastructure management

```bash
# Build and push to ACR
az acr build \
  --registry myregistry \
  --image kratos-agent-backend:latest \
  --file src/backend/Dockerfile .

# Deploy as container instance
az container create \
  --resource-group my-rg \
  --name kratos-agent-backend \
  --image myregistry.azurecr.io/kratos-agent-backend:latest \
  --cpu 2 \
  --memory 4 \
  --ports 8000 \
  --environment-variables \
    COPILOT_GITHUB_TOKEN='ghp_xxx' \
    ENABLE_USER_AUTH_OBO='true' \
    AZURE_TENANT_ID='xxx' \
  --registry-login-server myregistry.azurecr.io \
  --registry-username <username> \
  --registry-password <password>

# Get endpoint
az container show \
  --resource-group my-rg \
  --name kratos-agent-backend \
  --query ipAddress.fqdn
```

**Pros:**
- Serverless (pay per second)
- No server management
- Auto-scales
- Easy to stop/start

**Cons:**
- Cold starts (few seconds)
- Limited customization
- Not ideal for always-on services

---

### Option 4: Kubernetes (AKS)

**Best for:** Enterprise, high availability, complex deployments

```bash
# Create AKS cluster
az aks create \
  --resource-group my-rg \
  --name my-cluster \
  --node-count 2 \
  --generate-ssh-keys

# Get credentials
az aks get-credentials \
  --resource-group my-rg \
  --name my-cluster

# Deploy using Helm or kubectl
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kratos-agent-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kratos-agent-backend
  template:
    metadata:
      labels:
        app: kratos-agent-backend
    spec:
      containers:
      - name: backend
        image: myregistry.azurecr.io/kratos-agent-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: COPILOT_GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: kratos-secrets
              key: github-token
        - name: ENABLE_USER_AUTH_OBO
          value: "true"
        - name: AZURE_TENANT_ID
          value: "xxx"
---
apiVersion: v1
kind: Service
metadata:
  name: kratos-agent-backend
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 8000
  selector:
    app: kratos-agent-backend
EOF

# Check deployment
kubectl get pods
kubectl get svc
```

**Pros:**
- Auto-scaling
- Auto-recovery
- High availability
- Production-grade

**Cons:**
- Complex setup
- More expensive
- Requires K8s knowledge

---

### Option 5: Azure App Service

**Best for:** Traditional web apps, easy scaling

```bash
# Create App Service plan
az appservice plan create \
  --name my-plan \
  --resource-group my-rg \
  --sku B1 \
  --is-linux

# Create web app
az webapp create \
  --resource-group my-rg \
  --plan my-plan \
  --name my-kratos-agent \
  --deployment-container-image-name myregistry.azurecr.io/kratos-agent-backend:latest

# Configure container settings
az webapp config container set \
  --name my-kratos-agent \
  --resource-group my-rg \
  --docker-custom-image-name myregistry.azurecr.io/kratos-agent-backend:latest \
  --docker-registry-server-url https://myregistry.azurecr.io

# Set environment variables
az webapp config appsettings set \
  --resource-group my-rg \
  --name my-kratos-agent \
  --settings COPILOT_GITHUB_TOKEN='ghp_xxx' ENABLE_USER_AUTH_OBO='true'

# Access at: https://my-kratos-agent.azurewebsites.net
```

**Pros:**
- Managed service
- Auto-scaling
- Easy monitoring
- Built-in CI/CD

**Cons:**
- Container support newer
- Less flexible than VMs

---

### Option 6: Foundry Hosted Agent (Cloud)

**Best for:** Enterprise deployments with Microsoft support

This is what you're likely using now in the main codebase.

```
Your Backend (Docker/App Service/AKS)
    ↓
Foundry Hosted Agent API
    ↓
Foundry handles:
    • Agent runtime management
    • MCP orchestration
    • Scaling
    • Monitoring
```

---

## Deployment Architecture Comparison

| Option | Setup Time | Cost | Scaling | HA | Use Case |
|--------|------------|------|---------|-----|----------|
| Docker Compose | 5 min | Free | Manual | No | Local dev |
| Docker Images | 10 min | Free | Manual | No | Custom deploy |
| ACI | 15 min | Low | Auto | Yes | Serverless test |
| App Service | 20 min | Medium | Auto | Yes | Production web |
| Kubernetes/AKS | 45 min | High | Auto | Yes | Enterprise |
| Foundry Hosted | Managed | Enterprise | Auto | Yes | Managed service |

---

## Recommended Deployment Strategy

### Development
```
Local: Docker Compose
  ↓
With OBO Testing: Mock Entra ID + Docker Compose
```

### Testing/Staging
```
Azure Container Instances
  ↓
Or: App Service with single instance
```

### Production
```
Kubernetes/AKS with auto-scaling
  ↓
Or: App Service with premium plan + slots
  ↓
Or: Foundry Hosted Agent (managed)
```

---

## Complete Local OBO Testing Setup (TL;DR)

```bash
# Terminal 1: Mock Entra ID
python scripts/mock_entra_server.py

# Terminal 2: Backend services
cp .env.local.example .env.local
# Edit .env.local to:
# LOCAL_MODE=false
# ENABLE_USER_AUTH_OBO=true
# AZURE_TOKEN_ENDPOINT=http://localhost:5555/token
# AZURE_TENANT_ID=12345678-1234-1234-1234-123456789012
# AZURE_CLIENT_ID=87654321-4321-4321-4321-210987654321
# AZURE_CLIENT_SECRET=mock-secret-key-12345

docker compose --env-file .env.local up -d

# Terminal 3: Frontend
cd src/frontend
npm run dev

# Terminal 4: Test OBO
python test_obo_flow.py  # See script above
```

---

## What Gets Deployed

```
Backend Container:
  • FastAPI app with OBO endpoints
  • Connects to mock/real Entra ID
  • Routes requests to Foundry Agent

Hosted Agent:
  • Processes agent logic
  • Registers MCPs
  • Routes to Power BI MCP (if enabled)

Frontend Container (Optional):
  • Next.js app
  • Handles user login (mock or real MSAL)
  • Sends requests to backend

Storage:
  • Local: Azurite (SQLite database)
  • Cloud: Azure Blob + Cosmos DB
```

---

## Next Steps

1. **Test OBO Locally First**
   ```bash
   python scripts/mock_entra_server.py  # Terminal 1
   docker compose up -d                 # Terminal 2
   python test_obo_flow.py             # Terminal 3
   ```

2. **Verify It Works**
   - Check backend logs for "Auth Mode: user_obo"
   - Confirm token exchange succeeds
   - Verify Power BI MCP gets delegated token

3. **Deploy to Cloud**
   - Choose deployment option above
   - Push Docker image to registry
   - Configure environment variables
   - Test in cloud environment

4. **Create PR When Ready**
   - All local tests passing ✅
   - OBO flow verified ✅
   - Deployment instructions documented ✅

---

**Everything ready! Start with the Mock Entra ID server for testing OBO without Azure.** 🚀
