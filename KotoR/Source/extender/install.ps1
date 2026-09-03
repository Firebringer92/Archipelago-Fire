# Installs / uninstalls this project's merged binkw32.dll.
#
# K1SE (KOTOR Script Extender)'s dispatcher-hook source is merged directly
# into this project's own build -- there is no separate K1SE install step
# any more, and no K1SE_HOST.dll chain. The full chain is now just:
#
#   swkotor.exe -> binkw32.dll (this project's merged proxy, K1SE included)
#               -> binkw32_real.dll (the true original Bink codec, captured
#                  once from whatever was already in the game folder)
#
# binkw32_proxy.def hardcodes every forwarded export as "binkw32_real.<func>",
# so this script's job is: capture the real binkw32.dll already in the game
# folder as binkw32_real.dll (only the first time), then install the merged
# proxy as the new binkw32.dll. Getting this order wrong (or using the wrong
# target filename) leaves the exports unresolvable and the game unable to
# start.
#
# Also writes ap_repo_root.txt into the game folder -- a one-line text file
# holding this checkout's own root path, which the compiled DLL reads at
# runtime (see ap_extender.c's ap_get_orchestrator_path) to find
# scripts\arm_orchestrator.py. Without it, the DLL has no way to know where
# a given player's checkout of this repo actually lives.
#
# Usage:
#   .\install.ps1 -GameDir "C:\...\swkotor" -Install
#   .\install.ps1 -GameDir "C:\...\swkotor" -Uninstall

param(
    [Parameter(Mandatory = $true)][string]$GameDir,
    [switch]$Install,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$realDll = Join-Path $GameDir "binkw32.dll"
$realBackup = Join-Path $GameDir "binkw32_real.dll"
$realBackupCopy = Join-Path $root "backup\binkw32_real_captured.dll"
$proxyDll = Join-Path $root "build_new\binkw32.dll"

if ($Install) {
    if (-not (Test-Path $realDll)) {
        throw "No binkw32.dll found at $realDll -- wrong game dir, or already broken."
    }
    if (-not (Test-Path $proxyDll)) {
        throw "Merged DLL not built yet -- run build.ps1 first. Expected $proxyDll"
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $root "backup") | Out-Null

    $alreadyOurs = (Test-Path $realBackup) -and
        ((Get-FileHash $realDll).Hash -eq (Get-FileHash $proxyDll).Hash)
    if ($alreadyOurs) {
        Write-Output "Already installed (binkw32.dll is already our merged proxy, binkw32_real.dll present) -- nothing to do."
        exit 0
    }

    if (Test-Path $realBackup) {
        Write-Output "$realBackup already exists (not overwriting -- assuming a previous install captured it)"
    } else {
        Copy-Item $realDll $realBackupCopy
        Copy-Item $realDll $realBackup
        Write-Output "Captured original binkw32.dll -> $realBackup (our merged proxy forwards here)"
    }

    Copy-Item $proxyDll $realDll -Force
    Write-Output "Installed merged proxy -> $realDll"

    $repoRoot = Split-Path -Parent $root
    $repoRootFile = Join-Path $GameDir "ap_repo_root.txt"
    Set-Content -Path $repoRootFile -Value $repoRoot -NoNewline -Encoding ascii
    Write-Output "Wrote $repoRootFile -> $repoRoot"

    Write-Output ""
    Write-Output "Done. Launch the game normally to test."
    exit 0
}

if ($Uninstall) {
    if (Test-Path $realBackupCopy) {
        Copy-Item $realBackupCopy $realDll -Force
        Write-Output "Restored original binkw32.dll from $realBackupCopy"
    } elseif (Test-Path $realBackup) {
        Copy-Item $realBackup $realDll -Force
        Write-Output "Restored original binkw32.dll from $realBackup"
    } else {
        throw "No backup found anywhere -- cannot safely uninstall automatically."
    }
    if (Test-Path $realBackup) {
        Remove-Item $realBackup
        Write-Output "Removed $realBackup"
    }
    Write-Output "Uninstalled our merged proxy. Game folder is back to the original binkw32.dll."
    exit 0
}

Write-Output "Specify -Install or -Uninstall."
exit 1
