param(
    [string]$OfflineModelsDir = $env:SONICINPUT_OFFLINE_MODELS_DIR,
    [switch]$NoOffline,
    [switch]$SkipBuild,
    [switch]$Build7z,
    [string]$SevenZipPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$uvCacheDir = Join-Path $repoRoot ".uv_cache"

if (-not $SkipBuild) {
    if (-not $NoOffline -and $OfflineModelsDir) {
        if (-not (Test-Path $OfflineModelsDir -PathType Container)) {
            throw "Offline models dir not found: $OfflineModelsDir"
        }
        $OfflineModelsDir = (Resolve-Path $OfflineModelsDir).Path
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

    uv run --cache-dir $uvCacheDir --extra local --group dev python build_nuitka.py
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed (uv exit code: $LASTEXITCODE)"
    }
}

$distDir = Join-Path $repoRoot "dist"
if (Test-Path $distDir) {
    $exe = Get-ChildItem -Path $distDir -Filter "SonicInput-v*-win64.exe" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($exe) {
        Write-Output "[OUTPUT] $($exe.FullName)"
    }

    $offlineZip = $null
    if ($exe) {
        $expectedOfflineZip = Join-Path $distDir "$($exe.BaseName)-offline.zip"
        if (Test-Path $expectedOfflineZip -PathType Leaf) {
            $offlineZip = Get-Item $expectedOfflineZip
        }
    }
    if (-not $offlineZip) {
        $offlineZip = Get-ChildItem -Path $distDir -Filter "SonicInput-v*-win64-offline.zip" |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }

    if ($offlineZip -and -not $NoOffline) {
        Write-Output "[OUTPUT] $($offlineZip.FullName)"

        if ($Build7z) {
            $sevenZipExe = $SevenZipPath
            if (-not $sevenZipExe) {
                $sevenZipExe = (Get-Command 7z -ErrorAction SilentlyContinue | Select-Object -First 1)?.Source
            }
            if ($sevenZipExe) {
                $tmpDir = Join-Path $distDir ("offline_pack_" + [guid]::NewGuid())
                if (Test-Path $tmpDir) { Remove-Item $tmpDir -Recurse -Force }
                New-Item -ItemType Directory -Path $tmpDir | Out-Null

                # Stage exe + models for better compression than re-zipping the zip
                if ($exe) {
                    Copy-Item $exe.FullName (Join-Path $tmpDir $exe.Name)
                }
                if (-not $NoOffline -and $OfflineModelsDir) {
                    Copy-Item $OfflineModelsDir (Join-Path $tmpDir "models") -Recurse
                }

                $sevenOut = ($offlineZip.FullName -replace "\\.zip$", "-lzma.7z")
                if (Test-Path $sevenOut) { Remove-Item $sevenOut -Force }
                Push-Location $tmpDir
                & $sevenZipExe a -t7z -mx=9 -ms=on -mmt=on $sevenOut "." *> $null
                Pop-Location
                Remove-Item $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
                if (Test-Path $sevenOut) {
                    Write-Output "[OUTPUT] $sevenOut"
                } else {
                    Write-Warning "7z compression failed."
                }
            } else {
                Write-Warning "7z not found in PATH; skipped 7z offline bundle."
            }
        }
    } elseif (-not $NoOffline -and $OfflineModelsDir) {
        Write-Warning "Offline zip not found. Check that the models dir has required folders."
    }
}
