#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Complete setup for testing Power BI OBO feature locally
    
.DESCRIPTION
    Automates the entire setup process:
    1. Checks prerequisites
    2. Creates .env.local
    3. Prompts for GitHub token
    4. Starts all Docker services
    5. Waits for services to be healthy
    6. Provides next steps

.EXAMPLE
    ./setup-local-complete.ps1
    
.NOTES
    Requires Docker, Docker Compose, Node.js, and Python 3.12+
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ROOT = $PSScriptRoot

Write-Host "`n" + ("="*70) -ForegroundColor Cyan
Write-Host "  Power BI OBO Feature - Complete Local Setup" -ForegroundColor Cyan
Write-Host ("="*70) + "`n" -ForegroundColor Cyan

# ─────────────────────────────────────────────────────────────
# 1. CHECK PREREQUISITES
# ─────────────────────────────────────────────────────────────

Write-Host "📋 Checking prerequisites..." -ForegroundColor Yellow

$missing = @()

# Check Docker
try {
    $dockerVersion = docker --version
    Write-Host "  ✅ Docker: $dockerVersion" -ForegroundColor Green
} catch {
    $missing += "Docker"
    Write-Host "  ❌ Docker not found" -ForegroundColor Red
}

# Check Docker Compose
try {
    $composeVersion = docker compose version
    Write-Host "  ✅ Docker Compose: $composeVersion" -ForegroundColor Green
} catch {
    $missing += "Docker Compose"
    Write-Host "  ❌ Docker Compose not found" -ForegroundColor Red
}

# Check Node.js (optional for now, needed for frontend)
try {
    $nodeVersion = node --version
    Write-Host "  ✅ Node.js: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  ⚠️  Node.js not found (needed for frontend dev)" -ForegroundColor Yellow
}

# Check Git
try {
    $gitVersion = git --version
    Write-Host "  ✅ Git: $gitVersion" -ForegroundColor Green
} catch {
    $missing += "Git"
    Write-Host "  ❌ Git not found" -ForegroundColor Red
}

if ($missing.Count -gt 0) {
    Write-Host "`n❌ Missing prerequisites: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "   Install from: https://docs.docker.com/get-docker/" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# ─────────────────────────────────────────────────────────────
# 2. SETUP ENVIRONMENT
# ─────────────────────────────────────────────────────────────

Write-Host "🔧 Setting up environment..." -ForegroundColor Yellow

$envFile = Join-Path $ROOT ".env.local"

if (-not (Test-Path $envFile)) {
    Write-Host "   Creating .env.local from template..." -ForegroundColor Green
    Copy-Item (Join-Path $ROOT ".env.local.example") $envFile -ErrorAction Stop
    Write-Host "   ✅ Created .env.local" -ForegroundColor Green
} else {
    Write-Host "   ✅ .env.local exists" -ForegroundColor Green
}

Write-Host ""

# ─────────────────────────────────────────────────────────────
# 3. GITHUB TOKEN
# ─────────────────────────────────────────────────────────────

Write-Host "🔐 GitHub Token Setup" -ForegroundColor Yellow

# Check if token already in env file
$existingToken = Select-String -Path $envFile -Pattern 'COPILOT_GITHUB_TOKEN' -ErrorAction SilentlyContinue
if ($existingToken -and $existingToken.Line -notlike "*COPILOT_GITHUB_TOKEN=*$*") {
    Write-Host "   ✅ GitHub token already configured" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  GitHub token not configured" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "   To get a token:" -ForegroundColor Cyan
    Write-Host "   1. Go to: https://github.com/settings/tokens/new" -ForegroundColor Cyan
    Write-Host "   2. Name: 'Kratos Agent Local Development'" -ForegroundColor Cyan
    Write-Host "   3. Select scopes: (none required - can be empty)" -ForegroundColor Cyan
    Write-Host "   4. Generate and copy the token" -ForegroundColor Cyan
    Write-Host ""
    
    $token = Read-Host "   Paste your GitHub token (or press Enter to skip)"
    
    if ($token) {
        # Update .env.local
        $envContent = Get-Content $envFile
        $envContent = $envContent -replace 'COPILOT_GITHUB_TOKEN=.*', "COPILOT_GITHUB_TOKEN=$token"
        Set-Content -Path $envFile -Value $envContent
        Write-Host "   ✅ Token saved to .env.local" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Skipping token setup (may be needed for some features)" -ForegroundColor Yellow
    }
}

Write-Host ""

# ─────────────────────────────────────────────────────────────
# 4. START SERVICES
# ─────────────────────────────────────────────────────────────

Write-Host "🚀 Starting Docker services..." -ForegroundColor Yellow
Write-Host ""

# Change to root directory
Push-Location $ROOT

try {
    # Build and start
    Write-Host "   Building and starting services..." -ForegroundColor Green
    docker compose --env-file .env.local up -d --build
    
    Write-Host ""
    Write-Host "   ✅ Services started" -ForegroundColor Green
    Write-Host ""
    
    # ─────────────────────────────────────────────────────────────
    # 5. WAIT FOR SERVICES
    # ─────────────────────────────────────────────────────────────
    
    Write-Host "⏳ Waiting for services to be healthy..." -ForegroundColor Yellow
    
    $maxAttempts = 30
    $attempt = 0
    $allHealthy = $false
    
    while ($attempt -lt $maxAttempts -and -not $allHealthy) {
        $attempt++
        Start-Sleep -Seconds 2
        
        Write-Host "   Checking health (attempt $attempt/$maxAttempts)..." -NoNewline -ForegroundColor Green
        
        try {
            $backendHealth = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -ErrorAction SilentlyContinue
            $backendOk = $backendHealth.StatusCode -eq 200
        } catch {
            $backendOk = $false
        }
        
        try {
            $agentHealth = Invoke-WebRequest -Uri "http://localhost:8088/health" -ErrorAction SilentlyContinue
            $agentOk = $agentHealth.StatusCode -eq 200
        } catch {
            $agentOk = $false
        }
        
        if ($backendOk -and $agentOk) {
            $allHealthy = $true
            Write-Host " ✅" -ForegroundColor Green
        } else {
            Write-Host ""
        }
    }
    
    if ($allHealthy) {
        Write-Host "   ✅ All services are healthy" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Services may still be starting" -ForegroundColor Yellow
        Write-Host "   Try accessing them in a moment..." -ForegroundColor Yellow
    }
    
    Write-Host ""
    
    # ─────────────────────────────────────────────────────────────
    # 6. DISPLAY ENDPOINTS
    # ─────────────────────────────────────────────────────────────
    
    Write-Host "✨ Services Ready!" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Available Endpoints:" -ForegroundColor Cyan
    Write-Host "  ├─ Backend API:      http://localhost:8000" -ForegroundColor Cyan
    Write-Host "  ├─ API Docs (Swagger): http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "  ├─ Hosted Agent:     http://localhost:8088" -ForegroundColor Cyan
    Write-Host "  ├─ Azurite Storage:  http://localhost:10000" -ForegroundColor Cyan
    Write-Host "  └─ Frontend (dev):   Run in separate terminal" -ForegroundColor Cyan
    Write-Host ""
    
    # ─────────────────────────────────────────────────────────────
    # 7. NEXT STEPS
    # ─────────────────────────────────────────────────────────────
    
    Write-Host "📝 Next Steps:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1️⃣  Start frontend (in new terminal):" -ForegroundColor Green
    Write-Host "      cd src/frontend" -ForegroundColor Cyan
    Write-Host "      npm install  # First time only" -ForegroundColor Cyan
    Write-Host "      npm run dev" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  2️⃣  Open frontend:" -ForegroundColor Green
    Write-Host "      http://localhost:3000" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  3️⃣  Test API (optional):" -ForegroundColor Green
    Write-Host "      curl http://localhost:8000/api/health" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  4️⃣  View logs:" -ForegroundColor Green
    Write-Host "      docker compose logs -f backend" -ForegroundColor Cyan
    Write-Host "      docker compose logs -f hosted-agent" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  5️⃣  Run demo (validates feature):" -ForegroundColor Green
    Write-Host "      python scripts/demo_local_auth_flow.py" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  6️⃣  Run auth tests:" -ForegroundColor Green
    Write-Host "      cd src/backend" -ForegroundColor Cyan
    Write-Host "      python -m pytest tests/test_auth*.py -v" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "📖 Documentation:" -ForegroundColor Yellow
    Write-Host "   • LOCAL_SETUP.md          - Complete setup guide" -ForegroundColor Cyan
    Write-Host "   • TESTING_LOCAL.md        - Testing & validation" -ForegroundColor Cyan
    Write-Host "   • IMPLEMENTATION_COMPLETE.md - Feature details & PR template" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "⚡ Stop services:" -ForegroundColor Yellow
    Write-Host "   docker compose down" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host ("="*70) -ForegroundColor Cyan
    Write-Host "  Setup Complete! 🎉" -ForegroundColor Green
    Write-Host ("="*70) -ForegroundColor Cyan
    Write-Host ""
    
} finally {
    Pop-Location
}
