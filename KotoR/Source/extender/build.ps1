# Builds the merged binkw32.dll (32-bit): this project's own extender
# (socket bridge, log-tailer, orchestrator shell-out) merged with K1SE's
# dispatcher-hook code (feats, skills, saves, and this project's own
# SetCreatureField addition), forwarding bink calls directly to the real
# Bink DLL. See src_k1se/ for the merged source and
# kotor_engine_constraints.md / kotor_project_status.md (project memory)
# for why this replaced the old three-layer proxy-chain-to-a-separately-
# installed-K1SE architecture.
#
# Must be run where vswhere.exe can find a VC++ toolchain (VS Build Tools or VS).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$src = Join-Path $root "src_k1se"

$vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    throw "vswhere.exe not found -- is a Visual Studio / Build Tools install present?"
}

$vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vsPath) {
    throw "No VS install with the C++ (VC.Tools.x86.x64) component found."
}

$vcvars = Join-Path $vsPath "VC\Auxiliary\Build\vcvars32.bat"
if (-not (Test-Path $vcvars)) {
    throw "vcvars32.bat not found at $vcvars"
}

$outDir = Join-Path $root "build_new"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$def = Join-Path $outDir "proxy.def"
if (-not (Test-Path $def)) {
    throw "Forwarder .def not found at $def -- generate it first:`n" +
          "  python tools\generate_forwarders.py --dll <path-to-binkw32_real.dll> --target binkw32_real --out build_new\proxy.def"
}

$minhookInc = Join-Path $root "third_party\minhook\include"
$minhookSrc = Join-Path $root "third_party\minhook\src"
if (-not (Test-Path $minhookInc)) {
    throw "MinHook not found at third_party\minhook. Fetch the pinned release:`n" +
          "  git clone --branch v1.3.4 --depth 1 https://github.com/TsudaKageyu/minhook third_party\minhook"
}

$out = Join-Path $outDir "binkw32.dll"

# Our own extender (C) + K1SE's merged dispatcher-hook code (C++) + MinHook
# (C, 32-bit disassembler only -- hde64.c is for the 64-bit build we don't need).
$sources = (@(
    (Join-Path $src "ap_extender.c"),
    (Join-Path $src "dllmain.cpp"),
    (Join-Path $src "kse_hook.cpp"),
    (Join-Path $src "log.cpp"),
    (Join-Path $minhookSrc "buffer.c"),
    (Join-Path $minhookSrc "hook.c"),
    (Join-Path $minhookSrc "trampoline.c"),
    (Join-Path $minhookSrc "hde\hde32.c")
) | ForEach-Object { "`"$_`"" }) -join " "

$includes = "/I `"$minhookInc`" /I `"$src`""

# KSE_STAGE=19 is the shipping unified build (see src_k1se/hook.cpp). Static
# CRT (/MT) so the DLL is a clean drop-in with no VC++ runtime dependency,
# matching K1SE's own CMakeLists.txt choice.
$cmd = "call `"$vcvars`" && cl.exe /nologo /LD /MT /W3 /EHsc /D_CRT_SECURE_NO_WARNINGS /DKSE_STAGE=19 $includes $sources /Fe:`"$out`" /Fo:`"$outDir\\`" /link /DEF:`"$def`" ws2_32.lib"
Write-Output "Running: $cmd"
cmd.exe /c $cmd
if ($LASTEXITCODE -ne 0) {
    throw "Build failed with exit code $LASTEXITCODE"
}

Write-Output ""
Write-Output "Built: $out"
Get-Item $out | Select-Object Name, Length, LastWriteTime
