# Quick Start - Running the Complete Solution Locally

This is the fastest way to get everything running and testing the Power BI OBO feature.

## 30-Second Quick Start

```bash
# 1. One-command setup (handles everything)
./setup-local-complete.ps1     # Windows PowerShell
# OR
./setup-local-complete.sh      # Mac/Linux

# 2. In a new terminal: Start frontend
cd src/frontend
npm install  # First time only
npm run dev

# 3. Open browser
# http://localhost:3000
```

That's it! Everything is running.

## Detailed Commands

### Backend Services (Docker Compose)

```bash
# Start all backend services
./run-local.ps1          # Windows
./run-local.sh           # Mac/Linux

# Or manually with Docker Compose
docker compose --env-file .env.local up -d --build

# View logs
docker compose logs -f backend
docker compose logs -f hosted-agent
docker compose logs -f azurite

# Stop services
docker compose down
```

### Frontend (Next.js)

```bash
# Terminal 2
cd src/frontend

# First time only
npm install

# Start dev server
npm run dev

# Build for production
npm run build
npm start
```

## Testing Checklist

### ✅ Backend Running?
```bash
# Should return 200
curl http://localhost:8000/api/health

# Or visit
http://localhost:8000/docs  # Swagger UI
```

### ✅ Frontend Running?
```bash
# Should load in browser
http://localhost:3000
```

### ✅ Can Send Messages?
1. Open http://localhost:3000
2. Type a message: "List available skills"
3. Should get response

### ✅ Auth Tests Passing?
```bash
cd src/backend
python -m pytest tests/test_auth*.py -v
# Should show: 76 passed
```

### ✅ Demo Script Works?
```bash
python scripts/demo_local_auth_flow.py
# Should show: 6 demos pass ✅
```

## Architecture at a Glance

```
localhost:3000 (Frontend - Next.js)
    ↓ API calls
localhost:8000 (Backend - FastAPI)
    ↓ agent requests
localhost:8088 (Hosted Agent - Foundry)
    ↓ tool calls
    ├─ localhost:10000 (Azurite - Storage)
    ├─ localhost:5173 (Power BI MCP mock)
    └─ Other MCP services
```

## Configuration

### Local Development (Default)
```env
LOCAL_MODE=true
ENABLE_USER_AUTH_OBO=false
```
- Uses service principal (Agent SP mode)
- Auth context stripped
- No Entra ID needed
- **This is the recommended local setup**

### Testing OBO Flow
```env
LOCAL_MODE=false
ENABLE_USER_AUTH_OBO=true
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_CLIENT_SECRET=your-secret
```
- Uses Entra ID OBO tokens
- Auth context flows to Power BI MCP
- Requires Azure credentials
- **For advanced testing only**

## Troubleshooting

### Port Already in Use
```bash
# Find process using port (Mac/Linux)
lsof -i :3000
lsof -i :8000
lsof -i :8088

# Kill process
kill -9 <PID>

# Or use different port
PORT=3001 npm run dev
```

### Docker Issues
```bash
# Restart Docker
docker restart

# Clear Docker volumes
docker compose down -v

# Rebuild
docker compose build --no-cache
```

### Frontend Won't Connect to Backend
```bash
# Check backend is running
curl http://localhost:8000/docs

# Check .env.local in frontend
cat src/frontend/.env.local

# Should have:
# NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

### GitHub Token Error
```bash
# Add token to .env.local
echo "COPILOT_GITHUB_TOKEN=ghp_xxxxx" >> .env.local

# Restart services
docker compose down
docker compose up -d --build
```

## Next Steps

1. **View Detailed Docs**
   - `LOCAL_SETUP.md` - Complete setup guide
   - `TESTING_LOCAL.md` - Testing & validation
   - `IMPLEMENTATION_COMPLETE.md` - Feature details

2. **Run Tests**
   - Auth tests: `cd src/backend && pytest tests/test_auth*.py -v`
   - End-to-end: `cd src/backend && pytest tests/test_end_to_end*.py -v`
   - All: `cd src/backend && pytest tests/ -q`

3. **Explore the Feature**
   - Query "List Power BI workspaces" to test Power BI MCP
   - Switch auth mode by editing `.env.local`
   - Check logs for auth mode: `docker compose logs backend | grep "Auth Mode"`

4. **Ready for PR?**
   - All tests passing ✅
   - Demo script works ✅
   - Can send messages ✅
   - No errors in logs ✅

---

**Everything ready? Let's go! 🚀**

Once verified locally, create PR to `kmavrodis/kratos-agent` with all 11 commits from your fork.
