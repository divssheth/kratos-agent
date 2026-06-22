"""Authentication Configuration & Security Guide

TLDR:
- Default: Agent Service Principal (ENABLE_USER_AUTH_OBO=false) - keyless via Managed Identity
- Optional: User OBO (ENABLE_USER_AUTH_OBO=true) - delegated via Entra ID
- Easy config switch; zero secrets in code/git
- All credentials from environment or Managed Identity
"""

# ═══════════════════════════════════════════════════════════════════════════════
# QUICK START: SWITCH BETWEEN AUTH MODES
# ═══════════════════════════════════════════════════════════════════════════════

# DEFAULT: Agent Service Principal (Keyless via Managed Identity)
# Set in your .env or Azure Container Apps environment:
ENABLE_USER_AUTH_OBO=false

# OPTIONAL: User OBO (Delegated via Entra ID)
# Set in your .env or Azure Container Apps environment:
ENABLE_USER_AUTH_OBO=true

# That's it! No code changes needed. No secrets to rotate.


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH MODE 1: Agent Service Principal (DEFAULT)
# ═══════════════════════════════════════════════════════════════════════════════

# WHAT IT IS:
# - Backend acts as the agent (service principal) to Power BI/Fabric
# - All users query data through the same service principal identity
# - Authentication: Azure Managed Identity (keyless, no credentials in code)
# - Scope: Agent owns all data access policies

# WHEN TO USE:
# - Default mode; no configuration required
# - All users okay with agent-scoped access
# - Organizational queries, reports shared by agent
# - Development/testing (local mode forces this)

# CREDENTIALS:
# - No secrets in code or git
# - Managed by Azure Container Apps / AKS via system-assigned managed identity
# - Automatically rotated by Azure platform
# - Backend requests tokens from local metadata service (keyless)

# ENVIRONMENT VARIABLES:
ENABLE_USER_AUTH_OBO=false  # Default; can be omitted

# SECURITY POSTURE:
✓ No secrets in git
✓ No hardcoded credentials
✓ Automatic rotation via Azure
✓ Least privilege via Managed Identity scope


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH MODE 2: User OBO (On-Behalf-Of) - OPTIONAL FEATURE
# ═══════════════════════════════════════════════════════════════════════════════

# WHAT IT IS:
# - Backend acts on behalf of logged-in user to Power BI/Fabric
# - Each user queries their own data (or data they have access to)
# - Authentication: Entra ID OBO (On-Behalf-Of) token exchange
# - Scope: User-scoped RBAC via Power BI/Fabric permissions

# WHEN TO USE:
# - Users need row-level security (RLS) or column-level security (CLS)
# - Multi-tenant scenarios where users see only their data
# - Regulated environments (HIPAA, finance) requiring per-user audit trails
# - Canary rollout of user-scoped queries

# CREDENTIALS:
# - User refresh token obtained by frontend via MSAL (OAuth 2.0)
# - Frontend sends refresh_token to POST /api/token/obo-exchange
# - Backend exchanges refresh_token for delegated access_token via Entra ID
# - Access token is short-lived (~1h), never persisted, never logged
# - Backend itself uses Managed Identity to reach Entra ID token endpoint (keyless)

# ENVIRONMENT VARIABLES:
ENABLE_USER_AUTH_OBO=true                           # Enable OBO feature
AZURE_TENANT_ID=<your-tenant-uuid>                 # Entra ID tenant
AZURE_CLIENT_ID=<backend-app-registration-id>      # Backend app ID in Entra ID
AZURE_CLIENT_SECRET=<backend-client-secret>        # Backend client secret

# ⚠️  IMPORTANT:
# - Backend client secret MUST be in Azure Key Vault or environment, NOT in git
# - Use GitHub Secrets or Azure Key Vault for CI/CD pipelines
# - Rotate client secret regularly (annual minimum)
# - Never commit .env files with AZURE_CLIENT_SECRET

# SECURITY POSTURE:
✓ User refresh tokens never persisted
✓ Access tokens never logged or cached
✓ Short-lived tokens (~1h TTL)
✓ Backend uses Managed Identity to call Entra ID (keyless)
✓ Per-user audit trail (who queried what, when)


# ═══════════════════════════════════════════════════════════════════════════════
# SWITCHING BETWEEN MODES: Easy & Safe
# ═══════════════════════════════════════════════════════════════════════════════

# SCENARIO: You want to test OBO but keep Agent SP as fallback

# Step 1: Update environment variable
ENABLE_USER_AUTH_OBO=true

# Step 2: Configure Entra ID (if not already done)
# - Register backend app in Entra ID
# - Create client secret
# - Set API permissions: Power BI/Fabric (Fabric.ReadWrite.All)

# Step 3: Set environment variables
AZURE_TENANT_ID=<from Entra ID>
AZURE_CLIENT_ID=<from Entra ID app registration>
AZURE_CLIENT_SECRET=<from Key Vault or GitHub Secrets>

# Step 4: Frontend obtains refresh token via MSAL
# - User logs in
# - Token stored securely (HTTP-only cookie or encrypted storage)

# Step 5: Call POST /api/token/obo-exchange
POST /api/token/obo-exchange
{
  "user_refresh_token": "...",
  "user_id": "user@example.com"
}

# Step 6: Backend exchanges and returns delegated token
{
  "access_token": "eyJ0eXAi...",  // short-lived, scoped to Power BI
  "expires_in": 3600,               // 1 hour
  "user_id": "user@example.com"     // context only, never logged
}

# ROLLBACK: Just flip the flag back
ENABLE_USER_AUTH_OBO=false


# ═══════════════════════════════════════════════════════════════════════════════
# NO SECRETS IN GIT: Best Practices
# ═══════════════════════════════════════════════════════════════════════════════

# ✓ DO:
✓ Use .env.example with placeholder values (committed to git)
✓ Store secrets in Azure Key Vault / GitHub Secrets (not git)
✓ Set secrets via CI/CD pipeline (GitHub Actions, Azure DevOps)
✓ Rotate secrets regularly (every 90 days minimum)
✓ Use Managed Identity for backend → Entra ID calls (keyless)

# ✗ DON'T:
✗ Commit .env files with real secrets
✗ Hardcode credentials in Python code
✗ Share secrets via email or chat
✗ Use same secret in dev, staging, and production

# EXAMPLE .env.example (safe to commit):
ENABLE_USER_AUTH_OBO=false
AZURE_TENANT_ID=<placeholder>
AZURE_CLIENT_ID=<placeholder>
AZURE_CLIENT_SECRET=<use Azure Key Vault, not this file>


# ═══════════════════════════════════════════════════════════════════════════════
# CREDENTIAL FLOW DIAGRAMS
# ═══════════════════════════════════════════════════════════════════════════════

# AGENT SP MODE (Default)
# ┌─────────────────────────────────────────────────────────────────┐
# │ User Request                                                    │
# └────────────────────────┬────────────────────────────────────────┘
#                          │
#                          ▼
#                  ┌──────────────────┐
#                  │  Backend Service │
#                  └────────┬─────────┘
#                           │
#                    (No secrets in code)
#                           │
#              (Managed Identity: keyless auth)
#                           │
#                           ▼
#              ┌──────────────────────────┐
#              │ Azure Metadata Service   │
#              │ (localhost token issuer) │
#              └────────────┬─────────────┘
#                           │
#            (Automatic credential rotation)
#                           │
#                           ▼
#              ┌──────────────────────────┐
#              │  Power BI / Fabric API   │
#              │ (as agent service principal)
#              └──────────────────────────┘

# USER OBO MODE (Optional, Feature-Flagged)
# ┌────────────────────────────────────────────────────────────────┐
# │ User logs in via MSAL → gets refresh_token (stored securely)  │
# └────────────────────┬───────────────────────────────────────────┘
#                      │
#                      ▼
# ┌────────────────────────────────────────────────────────────────┐
# │ Frontend: POST /api/token/obo-exchange                         │
# │ { "user_refresh_token": "...", "user_id": "..." }            │
# └────────────────────┬───────────────────────────────────────────┘
#                      │
#                      ▼
#            ┌──────────────────────────┐
#            │  Backend (no secrets in  │
#            │   code; Managed Identity)│
#            └────────────┬─────────────┘
#                         │
#              (OBO token exchange, never logs tokens)
#                         │
#                         ▼
#          ┌───────────────────────────────┐
#          │ Entra ID Token Endpoint       │
#          │ grant_type=refresh_token      │
#          │ (backend uses Managed Identity)
#          └────────────┬──────────────────┘
#                       │
#               (Short-lived access token)
#                       │
#                       ▼
#          ┌───────────────────────────────┐
#          │ Backend returns access_token  │
#          │ (never persisted, request-scoped)
#          └────────────┬──────────────────┘
#                       │
#                       ▼
#          ┌───────────────────────────────┐
#          │ Frontend: use token with MCP  │
#          │ Power BI / Fabric API         │
#          │ (as user, not agent)          │
#          └───────────────────────────────┘


# ═══════════════════════════════════════════════════════════════════════════════
# TESTING AUTH MODES LOCALLY
# ═══════════════════════════════════════════════════════════════════════════════

# LOCAL MODE (no Azure services)
# In local mode (COSMOS_DB_ENDPOINT not set), the backend uses:
# - SQLite for persistence
# - GitHub OAuth token for Copilot SDK (via COPILOT_GITHUB_TOKEN)
# - Local stub for hosted agent
# - FORCED Agent SP mode (OBO disabled even if flag=true)

# Example .env for local development:
COPILOT_GITHUB_TOKEN=<your-github-token>
ENABLE_USER_AUTH_OBO=false  # Optional; local mode forces this anyway
# (No AZURE_* vars needed in local mode)

# HYBRID: Local backend + Azure Entra ID testing
# If you want to test OBO flow locally:
# 1. Set COSMOS_DB_ENDPOINT or another Azure service endpoint
#    (this disables local_mode)
# 2. Set AZURE_* vars for Entra ID
# 3. Set ENABLE_USER_AUTH_OBO=true
# 4. Run: python -m pytest tests/test_auth_service.py


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY CHECKLIST
# ═══════════════════════════════════════════════════════════════════════════════

BEFORE PRODUCTION DEPLOYMENT:

Agent SP Mode (Default):
☐ Verify ENABLE_USER_AUTH_OBO=false (or omitted)
☐ Confirm backend has Managed Identity (system-assigned)
☐ Test: backend can reach Power BI/Fabric APIs
☐ Verify: no AZURE_CLIENT_SECRET in environment
☐ Check: logs never contain credentials

User OBO Mode:
☐ ENABLE_USER_AUTH_OBO=true
☐ AZURE_TENANT_ID set from Entra ID
☐ AZURE_CLIENT_ID set from backend app registration
☐ AZURE_CLIENT_SECRET in Azure Key Vault (NOT in .env or git)
☐ Backend app has Power BI/Fabric API permissions (admin consent)
☐ Refresh token lifetime configured (90 days recommended)
☐ Client secret expiry monitored (set reminder to rotate)
☐ Test: OBO token exchange works end-to-end
☐ Audit: verify per-user access trails in Power BI

Both Modes:
☐ .env file NOT committed to git (use .env.example instead)
☐ .gitignore includes .env, .env.local, etc.
☐ Secrets in GitHub Secrets or Azure Key Vault
☐ CI/CD pipeline sets secrets (not via .env files)
☐ Review: no credentials in Docker images
☐ Scan: git history for accidentally committed secrets
☐ Test: easy switching between modes (flip config flag)


# ═══════════════════════════════════════════════════════════════════════════════
# TROUBLESHOOTING
# ═══════════════════════════════════════════════════════════════════════════════

ISSUE: Backend can't reach Power BI/Fabric (Agent SP mode)
FIX: 1. Verify backend has Managed Identity assigned
     2. Confirm Managed Identity has Power BI contributor role
     3. Check firewall/network access to api.powerbi.com

ISSUE: OBO token exchange returns 401 Unauthorized
FIX: 1. Verify AZURE_TENANT_ID, AZURE_CLIENT_ID are correct
     2. Confirm AZURE_CLIENT_SECRET is valid (not expired)
     3. Check backend app has Power BI API permissions (admin consent)
     4. Verify user refresh token is valid (hasn't expired)

ISSUE: Tokens appearing in logs/traces
FIX: 1. Review logging configuration (remove sensitive fields)
     2. Verify AuthService doesn't log access/refresh tokens
     3. Check OpenTelemetry sanitization in span attributes

ISSUE: Can't switch from OBO back to Agent SP
FIX: 1. Set ENABLE_USER_AUTH_OBO=false
     2. Restart backend
     3. Verify auth_context is stripped in requests
     4. Monitor logs: should see "Auth mode: AGENT_APP"

ISSUE: Development PC can't authenticate to Entra ID (OBO mode)
FIX: 1. Ensure Azure CLI is authenticated: `az login`
     2. Or set AZURE_CLIENT_ID + AZURE_CLIENT_SECRET (not recommended for dev)
     3. Or use local mode (COSMOS_DB_ENDPOINT not set)
"""

# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT ENDS — For code integration, see:
# - app/config.py: Feature flag definition
# - app/services/auth_service.py: OBO token exchange
# - app/services/auth_mode_controller.py: Auth mode management
# - app/routers/token.py: OBO endpoint
# - tests/test_auth_mode_controller.py: Test scenarios
# ═══════════════════════════════════════════════════════════════════════════════
