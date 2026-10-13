<#
.SYNOPSIS
    Launcher script for claw-cli in PowerShell
#>
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clawExe = Join-Path $scriptDir ".venv\Scripts\claw.exe"

if (-not (Test-Path $clawExe)) {
    Write-Error "Không tìm thấy claw.exe tại '$clawExe'."
    exit 1
}

& $clawExe @args
