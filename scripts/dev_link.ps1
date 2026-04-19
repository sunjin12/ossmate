<#
.SYNOPSIS
  Prepare a local development environment for Ossmate (Windows / PowerShell).

.DESCRIPTION
  Installs both Ossmate packages in editable mode into the active Python
  environment. Twin of scripts/dev_link.sh — keep them in lockstep.
  Does not create a venv; run inside whichever env you want Ossmate attached to.

.PARAMETER Mcp
  Install only the MCP package, skip the CLI.

.PARAMETER Cli
  Install only the CLI package, skip the MCP server.

.EXAMPLE
  PS> .\scripts\dev_link.ps1
  PS> .\scripts\dev_link.ps1 -Mcp
#>

param(
  [switch]$Mcp,
  [switch]$Cli
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $RepoRoot

python -c "import sys; print(f'dev_link: using Python {sys.version.split()[0]} at {sys.executable}')"

if (-not $Cli) {
  Write-Host ">>> installing ossmate-mcp (editable)"
  python -m pip install -e "./mcp/ossmate_mcp[dev]"
}

if (-not $Mcp) {
  Write-Host ">>> installing ossmate CLI (editable)"
  python -m pip install -e "./cli/ossmate[dev]" --no-deps
}

Write-Host ">>> verifying version sync"
python scripts/bump_version.py --check

Write-Host ">>> done. Try:  ossmate --help   |   python -m ossmate_mcp --help"
