param(
    [string]$Python = "python",
    [string]$ComsolRoot = "",
    [string]$McpHome = ""
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)

if ($ComsolRoot) {
    $env:COMSOL_ROOT = $ComsolRoot
}

if ($McpHome) {
    $env:COMSOL_SERVER_MCP_HOME = $McpHome
}

Write-Host "Starting COMSOL MCP"
Write-Host "COMSOL_ROOT=$env:COMSOL_ROOT"
Write-Host "COMSOL_SERVER_MCP_HOME=$env:COMSOL_SERVER_MCP_HOME"

& $Python -m comsol_mcp.mcp_server
