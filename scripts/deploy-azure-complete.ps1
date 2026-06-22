param(
    [Parameter(Mandatory = $true)]
    [string]$EnvName,

    [Parameter(Mandatory = $false)]
    [string]$Location = "eastus2",

    [Parameter(Mandatory = $false)]
    [ValidateSet("up", "deploy")]
    [string]$Mode = "deploy",

    [Parameter(Mandatory = $false)]
    [bool]$EnableUserAuthObo = $false,

    [Parameter(Mandatory = $false)]
    [bool]$EnablePowerbiFabricMcp = $false,

    [Parameter(Mandatory = $false)]
    [bool]$EnableWorkspaceSelector = $false,

    [Parameter(Mandatory = $false)]
    [string]$PowerbiFabricMcpUrl = "",

    [Parameter(Mandatory = $false)]
    [string]$AzureTenantId = "",

    [Parameter(Mandatory = $false)]
    [string]$AzureClientId = "",

    [Parameter(Mandatory = $false)]
    [string]$AzureClientSecret = "",

    [Parameter(Mandatory = $false)]
    [string]$AzureTokenEndpoint = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not installed or not on PATH."
    }
}

Write-Host "\n=== Kratos Azure Deployment ===" -ForegroundColor Cyan
Write-Host "EnvName: $EnvName"
Write-Host "Location: $Location"
Write-Host "Mode: $Mode"

Require-Command "azd"
Require-Command "az"

# Ensure we are at repo root (script lives in scripts/)
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

try {
    # Ensure azd environment exists and is selected.
    $envExists = $false
    $envListJson = azd env list --output json 2>$null
    if ($LASTEXITCODE -eq 0 -and $envListJson) {
        $envList = $envListJson | ConvertFrom-Json
        foreach ($e in $envList) {
            if ($e.Name -eq $EnvName) {
                $envExists = $true
                break
            }
        }
    }

    if ($envExists) {
        azd env select $EnvName | Out-Host
    }
    else {
        azd env new $EnvName --location $Location | Out-Host
    }

    # Non-interactive skills upload during postdeploy.
    azd env set KRATOS_AUTO_UPLOAD_USE_CASES 1 | Out-Host

    # Wire backend/container-app rollout flags into infra params.
    azd env set ENABLE_USER_AUTH_OBO ($EnableUserAuthObo.ToString().ToLower()) | Out-Host
    azd env set ENABLE_POWERBI_FABRIC_MCP ($EnablePowerbiFabricMcp.ToString().ToLower()) | Out-Host
    azd env set ENABLE_WORKSPACE_SELECTOR ($EnableWorkspaceSelector.ToString().ToLower()) | Out-Host

    if ($PowerbiFabricMcpUrl) {
        azd env set POWERBI_FABRIC_MCP_URL $PowerbiFabricMcpUrl | Out-Host
    }

    if ($AzureTenantId) {
        azd env set AZURE_TENANT_ID $AzureTenantId | Out-Host
    }
    if ($AzureClientId) {
        azd env set AZURE_CLIENT_ID $AzureClientId | Out-Host
    }
    if ($AzureClientSecret) {
        azd env set AZURE_CLIENT_SECRET $AzureClientSecret | Out-Host
    }
    if ($AzureTokenEndpoint) {
        azd env set AZURE_TOKEN_ENDPOINT $AzureTokenEndpoint | Out-Host
    }

    if ($Mode -eq "up") {
        azd up --no-prompt | Out-Host
    }
    else {
        azd deploy --no-prompt | Out-Host
    }

    Write-Host "\nDeployment complete." -ForegroundColor Green
    Write-Host "\nEffective flags:" -ForegroundColor Cyan
    azd env get-value ENABLE_USER_AUTH_OBO | ForEach-Object { Write-Host "ENABLE_USER_AUTH_OBO=$_" }
    azd env get-value ENABLE_POWERBI_FABRIC_MCP | ForEach-Object { Write-Host "ENABLE_POWERBI_FABRIC_MCP=$_" }
    azd env get-value ENABLE_WORKSPACE_SELECTOR | ForEach-Object { Write-Host "ENABLE_WORKSPACE_SELECTOR=$_" }
    azd env get-value POWERBI_FABRIC_MCP_URL | ForEach-Object { if ($_){ Write-Host "POWERBI_FABRIC_MCP_URL=$_" } }
}
finally {
    Pop-Location
}
