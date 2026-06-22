#!/bin/bash
# Complete setup for testing Power BI OBO feature locally (Mac/Linux)

set -e

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo ""
echo "======================================================================"
echo "  Power BI OBO Feature - Complete Local Setup"
echo "======================================================================"
echo ""

# ─────────────────────────────────────────────────────────────
# 1. CHECK PREREQUISITES
# ─────────────────────────────────────────────────────────────

echo "📋 Checking prerequisites..."

missing=()

# Check Docker
if command -v docker &> /dev/null; then
    docker_version=$(docker --version)
    echo "  ✅ $docker_version"
else
    missing+=("Docker")
    echo "  ❌ Docker not found"
fi

# Check Docker Compose
if docker compose version &> /dev/null; then
    compose_version=$(docker compose version)
    echo "  ✅ $compose_version"
else
    missing+=("Docker Compose")
    echo "  ❌ Docker Compose not found"
fi

# Check Node.js (optional)
if command -v node &> /dev/null; then
    node_version=$(node --version)
    echo "  ✅ Node.js: $node_version"
else
    echo "  ⚠️  Node.js not found (needed for frontend dev)"
fi

# Check Git
if command -v git &> /dev/null; then
    git_version=$(git --version)
    echo "  ✅ $git_version"
else
    missing+=("Git")
    echo "  ❌ Git not found"
fi

if [ ${#missing[@]} -gt 0 ]; then
    echo ""
    echo "❌ Missing prerequisites: ${missing[*]}"
    echo "   Install from: https://docs.docker.com/get-docker/"
    exit 1
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 2. SETUP ENVIRONMENT
# ─────────────────────────────────────────────────────────────

echo "🔧 Setting up environment..."

env_file="$ROOT/.env.local"

if [ ! -f "$env_file" ]; then
    echo "   Creating .env.local from template..."
    cp "$ROOT/.env.local.example" "$env_file"
    echo "   ✅ Created .env.local"
else
    echo "   ✅ .env.local exists"
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 3. GITHUB TOKEN
# ─────────────────────────────────────────────────────────────

echo "🔐 GitHub Token Setup"

# Check if token is configured
if grep -q "COPILOT_GITHUB_TOKEN=ghp_\|COPILOT_GITHUB_TOKEN=ghu_\|COPILOT_GITHUB_TOKEN=ghs_" "$env_file"; then
    echo "   ✅ GitHub token already configured"
else
    echo "   ⚠️  GitHub token not configured"
    echo ""
    echo "   To get a token:"
    echo "   1. Go to: https://github.com/settings/tokens/new"
    echo "   2. Name: 'Kratos Agent Local Development'"
    echo "   3. Select scopes: (none required - can be empty)"
    echo "   4. Generate and copy the token"
    echo ""
    
    read -p "   Paste your GitHub token (or press Enter to skip): " token
    
    if [ -n "$token" ]; then
        # Update .env.local (works on both Mac and Linux)
        sed -i.bak "s/COPILOT_GITHUB_TOKEN=.*/COPILOT_GITHUB_TOKEN=$token/" "$env_file"
        rm -f "$env_file.bak"
        echo "   ✅ Token saved to .env.local"
    else
        echo "   ⚠️  Skipping token setup (may be needed for some features)"
    fi
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 4. START SERVICES
# ─────────────────────────────────────────────────────────────

echo "🚀 Starting Docker services..."
echo ""

cd "$ROOT"

echo "   Building and starting services..."
docker compose --env-file .env.local up -d --build

echo "   ✅ Services started"
echo ""

# ─────────────────────────────────────────────────────────────
# 5. WAIT FOR SERVICES
# ─────────────────────────────────────────────────────────────

echo "⏳ Waiting for services to be healthy..."

max_attempts=30
attempt=0
all_healthy=false

while [ $attempt -lt $max_attempts ] && [ "$all_healthy" = false ]; do
    attempt=$((attempt + 1))
    sleep 2
    
    echo -n "   Checking health (attempt $attempt/$max_attempts)..."
    
    backend_ok=false
    agent_ok=false
    
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        backend_ok=true
    fi
    
    if curl -s http://localhost:8088/health > /dev/null 2>&1; then
        agent_ok=true
    fi
    
    if [ "$backend_ok" = true ] && [ "$agent_ok" = true ]; then
        all_healthy=true
        echo " ✅"
    else
        echo ""
    fi
done

if [ "$all_healthy" = true ]; then
    echo "   ✅ All services are healthy"
else
    echo "   ⚠️  Services may still be starting"
    echo "   Try accessing them in a moment..."
fi

echo ""

# ─────────────────────────────────────────────────────────────
# 6. DISPLAY ENDPOINTS
# ─────────────────────────────────────────────────────────────

echo "✨ Services Ready!"
echo ""
echo "  Available Endpoints:"
echo "  ├─ Backend API:      http://localhost:8000"
echo "  ├─ API Docs (Swagger): http://localhost:8000/docs"
echo "  ├─ Hosted Agent:     http://localhost:8088"
echo "  ├─ Azurite Storage:  http://localhost:10000"
echo "  └─ Frontend (dev):   Run in separate terminal"
echo ""

# ─────────────────────────────────────────────────────────────
# 7. NEXT STEPS
# ─────────────────────────────────────────────────────────────

echo "📝 Next Steps:"
echo ""
echo "  1️⃣  Start frontend (in new terminal):"
echo "      cd src/frontend"
echo "      npm install  # First time only"
echo "      npm run dev"
echo ""
echo "  2️⃣  Open frontend:"
echo "      http://localhost:3000"
echo ""
echo "  3️⃣  Test API (optional):"
echo "      curl http://localhost:8000/api/health"
echo ""
echo "  4️⃣  View logs:"
echo "      docker compose logs -f backend"
echo "      docker compose logs -f hosted-agent"
echo ""
echo "  5️⃣  Run demo (validates feature):"
echo "      python scripts/demo_local_auth_flow.py"
echo ""
echo "  6️⃣  Run auth tests:"
echo "      cd src/backend"
echo "      python -m pytest tests/test_auth*.py -v"
echo ""

echo "📖 Documentation:"
echo "   • LOCAL_SETUP.md          - Complete setup guide"
echo "   • TESTING_LOCAL.md        - Testing & validation"
echo "   • IMPLEMENTATION_COMPLETE.md - Feature details & PR template"
echo ""

echo "⚡ Stop services:"
echo "   docker compose down"
echo ""

echo "======================================================================"
echo "  Setup Complete! 🎉"
echo "======================================================================"
echo ""
