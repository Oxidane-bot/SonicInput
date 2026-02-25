param()

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is not available in PATH."
}

if (-not (Test-Path ".githooks/pre-commit" -PathType Leaf)) {
    throw "Missing .githooks/pre-commit"
}

if (-not (Test-Path ".githooks/pre-push" -PathType Leaf)) {
    throw "Missing .githooks/pre-push"
}

git config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Failed to set core.hooksPath. Check repository permissions."
}

$current = git config --get core.hooksPath
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read core.hooksPath after installation."
}

Write-Output "[OK] Installed repository hooks."
Write-Output "[INFO] core.hooksPath=$current"
Write-Output "[TIP] To bypass once: git commit --no-verify"
