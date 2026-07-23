param(
    [string]$OfflineModelsDir = $env:SONICINPUT_OFFLINE_MODELS_DIR,
    [switch]$NoOffline,
    [switch]$SkipChecks,
    [switch]$SkipSmoke,
    [switch]$SkipBuild,
    [switch]$Build7z,
    [string]$SevenZipPath,
    [string]$ModelSmokeDir = $env:SONICINPUT_PACKAGE_SMOKE_MODEL_DIR,
    [string]$ModelSmokeName = "zipformer-small"
)

$ErrorActionPreference = "Stop"

function Invoke-Uv {
    param(
        [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
        [string[]]$Arguments
    )

    & uv @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv $($Arguments -join ' ') failed (exit code: $LASTEXITCODE)"
    }
}

function Invoke-PackagedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExecutablePath,
        [Parameter(Mandatory = $true)]
        [string]$Argument,
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [int]$TimeoutSeconds = 180
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $ExecutablePath
    $startInfo.Arguments = $Argument
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Could not start $Description"
    }

    # Start draining both redirected streams before waiting so a noisy child cannot block.
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $completed = $process.WaitForExit($TimeoutSeconds * 1000)
    if (-not $completed) {
        & taskkill /PID $process.Id /T /F *> $null
        $process.WaitForExit()
    }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()

    $diagnostics = @()
    if (-not [string]::IsNullOrWhiteSpace($stdout)) {
        $diagnostics += "stdout:`n$($stdout.TrimEnd())"
    }
    if (-not [string]::IsNullOrWhiteSpace($stderr)) {
        $diagnostics += "stderr:`n$($stderr.TrimEnd())"
    }
    $diagnosticText = if ($diagnostics.Count -gt 0) {
        "`n$($diagnostics -join "`n")"
    } else {
        ""
    }

    if (-not $completed) {
        throw "$Description timed out after $TimeoutSeconds seconds$diagnosticText"
    }
    $exitCode = $process.ExitCode
    if ($exitCode -ne 0) {
        throw "$Description failed (exit code: $exitCode)$diagnosticText"
    }
}

function Invoke-ReleaseSmoke {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExecutablePath
    )

    $hadAppData = Test-Path Env:APPDATA
    $previousAppData = $env:APPDATA
    $hadQpaPlatform = Test-Path Env:QT_QPA_PLATFORM
    $previousQpaPlatform = $env:QT_QPA_PLATFORM
    $smokeAppData = Join-Path ([System.IO.Path]::GetTempPath()) ("sonicinput-release-smoke-" + [guid]::NewGuid())
    $guiProcess = $null

    try {
        New-Item -ItemType Directory -Path $smokeAppData | Out-Null
        $env:APPDATA = $smokeAppData
        $env:QT_QPA_PLATFORM = "offscreen"

        Write-Output "[SMOKE] CLI help"
        Invoke-PackagedCommand -ExecutablePath $ExecutablePath -Argument "--help" -Description "Packaged --help"

        Write-Output "[SMOKE] Environment validation"
        Invoke-PackagedCommand -ExecutablePath $ExecutablePath -Argument "--validate" -Description "Packaged --validate"

        Write-Output "[SMOKE] Packaged resources, native ASR, and QML surfaces"
        Invoke-PackagedCommand -ExecutablePath $ExecutablePath -Argument "--package-smoke" -Description "Packaged runtime smoke"

        Write-Output "[SMOKE] Offscreen GUI startup"
        $guiProcess = Start-Process -FilePath $ExecutablePath -ArgumentList "--gui" -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 12
        $guiProcess.Refresh()
        if ($guiProcess.HasExited) {
            throw "Packaged offscreen GUI exited during startup (exit code: $($guiProcess.ExitCode))"
        }
    } finally {
        if ($guiProcess -and -not $guiProcess.HasExited) {
            & taskkill /PID $guiProcess.Id /T /F *> $null
        }
        Remove-Item -LiteralPath $smokeAppData -Recurse -Force -ErrorAction SilentlyContinue
        if ($hadAppData) {
            $env:APPDATA = $previousAppData
        } else {
            Remove-Item Env:APPDATA -ErrorAction SilentlyContinue
        }
        if ($hadQpaPlatform) {
            $env:QT_QPA_PLATFORM = $previousQpaPlatform
        } else {
            Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        }
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pyproject = Get-Content -LiteralPath (Join-Path $repoRoot "pyproject.toml") -Raw
if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not determine the package version from pyproject.toml"
}

$version = $Matches[1]
$releaseDir = Join-Path $repoRoot "dist\release\v$version"
$exePath = Join-Path $releaseDir "SonicInput-v$version-win64.exe"
$hashPath = "$exePath.sha256"
$offlineZipPath = Join-Path $releaseDir "SonicInput-v$version-win64-offline.zip"
$offline7zPath = Join-Path $releaseDir "SonicInput-v$version-win64-offline-lzma.7z"
$env:SONICINPUT_RELEASE_DIR = $releaseDir
$env:SONICINPUT_NUITKA_WORK_DIR = Join-Path $repoRoot "build\nuitka"

if (-not $SkipChecks) {
    Write-Output "[CHECK] Lockfile"
    Invoke-Uv lock --check

    Write-Output "[CHECK] Syncing the locked release environment"
    Invoke-Uv sync --locked --extra local --extra dev --group dev

    Write-Output "[CHECK] Ruff"
    Invoke-Uv run --locked --extra local --extra dev --group dev ruff check src tests app.py build_nuitka.py scripts
    Invoke-Uv run --locked --extra local --extra dev --group dev ruff format --check src tests app.py build_nuitka.py scripts

    Write-Output "[CHECK] Mypy"
    Invoke-Uv run --locked --extra local --extra dev --group dev mypy src app.py build_nuitka.py scripts

    Write-Output "[CHECK] Non-GUI regression suite"
    Invoke-Uv run --locked --extra local --extra dev --group dev pytest -m "not gui and not gpu and not e2e" -v

    Write-Output "[CHECK] Offscreen GUI/QML suite"
    $hadQpaPlatform = Test-Path Env:QT_QPA_PLATFORM
    $previousQpaPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        Invoke-Uv run --locked --extra local --extra dev --group dev pytest tests/ui -m gui -v
    } finally {
        if ($hadQpaPlatform) {
            $env:QT_QPA_PLATFORM = $previousQpaPlatform
        } else {
            Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
        }
    }

    Write-Output "[CHECK] Bandit"
    $banditReport = Join-Path $repoRoot "bandit-report.json"
    Remove-Item -LiteralPath $banditReport -Force -ErrorAction SilentlyContinue
    Invoke-Uv run --locked --extra local --extra dev --group dev bandit -r src -ll -ii -f json --output $banditReport

    Write-Output "[CHECK] Python package build"
    Invoke-Uv build
} else {
    Write-Warning "Source validation was skipped. Use -SkipChecks only for iteration."
}

if (-not $NoOffline -and $OfflineModelsDir) {
    if (-not (Test-Path -LiteralPath $OfflineModelsDir -PathType Container)) {
        throw "Offline models dir not found: $OfflineModelsDir"
    }
    $OfflineModelsDir = (Resolve-Path -LiteralPath $OfflineModelsDir).Path
    $env:SONICINPUT_OFFLINE_MODELS_DIR = $OfflineModelsDir
    Write-Output "[INFO] Offline models dir: $OfflineModelsDir"
} else {
    Remove-Item Env:SONICINPUT_OFFLINE_MODELS_DIR -ErrorAction SilentlyContinue
    if ($NoOffline) {
        Write-Output "[INFO] Offline bundle disabled."
    } else {
        Write-Output "[INFO] Offline models dir not provided; skipping offline bundle."
    }
}

if ($ModelSmokeDir) {
    if (-not (Test-Path -LiteralPath $ModelSmokeDir -PathType Container)) {
        throw "Model smoke dir not found: $ModelSmokeDir"
    }
    $env:SONICINPUT_PACKAGE_SMOKE_MODEL_DIR = (Resolve-Path -LiteralPath $ModelSmokeDir).Path
    $env:SONICINPUT_PACKAGE_SMOKE_MODEL = $ModelSmokeName
    Write-Output "[INFO] Packaged model decode smoke: $ModelSmokeName from $($env:SONICINPUT_PACKAGE_SMOKE_MODEL_DIR)"
} else {
    Remove-Item Env:SONICINPUT_PACKAGE_SMOKE_MODEL_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:SONICINPUT_PACKAGE_SMOKE_MODEL -ErrorAction SilentlyContinue
}

if (-not $SkipBuild) {
    foreach ($staleArtifact in @($exePath, $hashPath, $offlineZipPath, $offline7zPath)) {
        if (Test-Path -LiteralPath $staleArtifact -PathType Leaf) {
            Remove-Item -LiteralPath $staleArtifact -Force
        }
    }
    Write-Output "[BUILD] SonicInput v$version"
    Invoke-Uv run --locked --extra local --extra dev --group dev python build_nuitka.py
}

if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
    throw "Expected release executable was not created: $exePath"
}

$exe = Get-Item -LiteralPath $exePath
if (-not $SkipSmoke) {
    Invoke-ReleaseSmoke -ExecutablePath $exe.FullName
} else {
    Write-Warning "Packaged executable smoke checks were skipped."
}

$hash = (Get-FileHash -LiteralPath $exe.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $hashPath -Value "$hash *$($exe.Name)" -Encoding ascii

Write-Output "[OUTPUT] $($exe.FullName)"
Write-Output "[SIZE] $([Math]::Round($exe.Length / 1MB, 2)) MiB"
Write-Output "[SHA256] $hash"
Write-Output "[OUTPUT] $hashPath"

if (Test-Path -LiteralPath $offlineZipPath -PathType Leaf) {
    Write-Output "[OUTPUT] $offlineZipPath"

    if ($Build7z) {
        if (-not $OfflineModelsDir) {
            throw "-Build7z requires -OfflineModelsDir and an offline bundle."
        }

        $sevenZipExe = $SevenZipPath
        if (-not $sevenZipExe) {
            $sevenZipExe = (Get-Command 7z -ErrorAction SilentlyContinue | Select-Object -First 1).Source
        }
        if (-not $sevenZipExe) {
            throw "7z was not found. Provide -SevenZipPath or add it to PATH."
        }

        $tempDir = Join-Path $releaseDir ("offline_pack_" + [guid]::NewGuid())
        $sevenOut = Join-Path $releaseDir "$($exe.BaseName)-offline-lzma.7z"
        try {
            New-Item -ItemType Directory -Path $tempDir | Out-Null
            Copy-Item -LiteralPath $exe.FullName -Destination (Join-Path $tempDir $exe.Name)
            Copy-Item -LiteralPath $OfflineModelsDir -Destination (Join-Path $tempDir "models") -Recurse
            Remove-Item -LiteralPath $sevenOut -Force -ErrorAction SilentlyContinue

            Push-Location $tempDir
            try {
                & $sevenZipExe a -t7z -mx=9 -ms=on -mmt=on $sevenOut "." *> $null
                if ($LASTEXITCODE -ne 0) {
                    throw "7z compression failed (exit code: $LASTEXITCODE)"
                }
            } finally {
                Pop-Location
            }
        } finally {
            Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Output "[OUTPUT] $sevenOut"
    }
} elseif (-not $NoOffline -and $OfflineModelsDir) {
    throw "Offline zip was not created. Check that the models directory contains both required model folders."
}
