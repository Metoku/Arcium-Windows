# Resume a pinned Arcium-Windows Chromium build without reapplying patches.
# Run AFTER windows_port.py stage and gn_smoke.py --execute. PowerShell only.
[CmdletBinding()]
param(
    [ValidateSet('check', 'resume')]
    [string]$Mode = 'resume',
    [ValidateRange(1, 12)]
    [int]$Jobs = 5
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$platform = Join-Path $repo 'work\windows-platform'
$source = Join-Path $platform 'build\src'
$expectedSdk = '10.0.28000.0'
$gnMarker = Join-Path $platform 'ARCIUM_GN_GENERATED.marker'
$programFilesX86 = [Environment]::GetFolderPath('ProgramFilesX86')

function Require-File {
    param([string]$Path, [string]$Description)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing $Description at '$Path'. See docs/local-windows-incremental-build.md for one-time preparation."
    }
}

Require-File (Join-Path $platform 'build.py') 'staged Windows builder'
Require-File (Join-Path $source 'BUILD.gn') 'prepared Chromium source'
Require-File (Join-Path $source 'out\Default\args.gn') 'GN flags'
Require-File (Join-Path $source 'out\Default\build.ninja') 'GN build graph'
Require-File $gnMarker 'verified GN preparation marker'

if ((Get-Content -LiteralPath $gnMarker -Raw).Trim() -ne 'PINNED_WINDOWS_GN_GENERATED') {
    throw 'Unrecognized GN preparation marker; refusing to compile a potentially unpatched Chromium tree.'
}
$autoninja = Join-Path $source 'third_party\depot_tools\autoninja.py'
$siso = Join-Path $source 'third_party\siso\cipd\siso.exe'
Require-File $autoninja 'pinned Chromium autoninja.py'
Require-File $siso 'pinned Siso scheduler'

$python = (Get-Command python -ErrorAction Stop).Source
if ($python -match '(?i)WindowsApps') {
    throw 'Python resolves to the Windows Store alias; install/use a real python.exe before compiling.'
}
Push-Location $repo
try {
    # Audit pinned platform/core commits and patch inventory without modifying
    # Chromium sources. Never restage or reapply all 551 patches on resume.
    & $python 'scripts\windows_port.py' audit
    if ($LASTEXITCODE -ne 0) {
        throw 'Pinned Windows/Arcium source audit failed; do not resume this build.'
    }

    # A read-only SDK verification. -Install is intended for disposable CI.
    & (Join-Path $repo 'scripts\provision_chromium_sdk.ps1')
    if ($LASTEXITCODE -ne 0) { throw "Windows SDK $expectedSdk is incomplete." }

    $kitHeader = Join-Path $programFilesX86 "Windows Kits\10\Include\$expectedSdk\shared\sdkddkver.h"
    Require-File $kitHeader "required SDK $expectedSdk version header"
    if (-not (Select-String -LiteralPath $kitHeader -Pattern '^\s*#\s*define\s+NTDDI_WIN11_BR\b' -Quiet)) {
        throw "The installed SDK $expectedSdk does not declare NTDDI_WIN11_BR."
    }

    $vswhere = Join-Path $programFilesX86 'Microsoft Visual Studio\Installer\vswhere.exe'
    Require-File $vswhere 'Visual Studio vswhere.exe'
    $vsCandidates = @(& $vswhere -latest -prerelease -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)
    if ($LASTEXITCODE -ne 0 -or $vsCandidates.Count -eq 0 -or -not $vsCandidates[0]) {
        throw 'Install Visual Studio Desktop development with C++ (x64 MSVC tools and ATL/MFC).'
    }
    $vcvarsall = Join-Path $vsCandidates[0] 'VC\Auxiliary\Build\vcvarsall.bat'
    Require-File $vcvarsall 'Visual Studio vcvarsall.bat'

    $argsFile = Join-Path $source 'out\Default\args.gn'
    $argsText = Get-Content -LiteralPath $argsFile -Raw
    if ($argsText -notmatch '(?m)^\s*target_cpu\s*=\s*"x64"\s*$') {
        throw 'GN output is not configured for Windows x64; refusing to reuse it.'
    }
    Write-Host "Prepared Chromium tree: $source"
    Write-Host "Visual Studio toolchain: $($vsCandidates[0])"
    Write-Host "Windows SDK: $expectedSdk"
    Write-Host "Parallel C++ jobs: $Jobs"
    Write-Host 'Existing Ninja outputs WILL be retained. No patches will be applied again.'

    if ($Mode -eq 'check') {
        Write-Host 'ARCIUM_LOCAL_RESUME_PREREQUISITES_PASSED'
        return
    }

    # Invoke Ninja from an explicit MSVC / SDK environment using a temporary
    # command file so quoting with Program Files paths works reliably.
    $tempCmd = Join-Path $repo 'work\local-arcium-resume.cmd'
    if (Test-Path -LiteralPath $tempCmd) {
        throw "Temporary resume command already exists: $tempCmd"
    }
    # Chromium 156's protoc-gen-ts_proto.bat invokes "python3", while official
    # python.org Windows installs may only provide "python.exe". Route both
    # commands to the same verified interpreter without modifying Chromium.
    $shimDir = Join-Path $repo ('work\local-python-shim-' + [guid]::NewGuid().ToString('N'))
    $shimCmd = Join-Path $shimDir 'python3.cmd'
    $commands = @(
        '@echo off',
        ('call "' + $vcvarsall + '" amd64 ' + $expectedSdk + ' >nul'),
        'if errorlevel 1 exit /b %errorlevel%',
        'set "DEPOT_TOOLS_WIN_TOOLCHAIN=0"',
        ('set "ARCIUM_WINDOWS_SDK=' + $expectedSdk + '"'),
        ('set "SISO_PATH=' + $siso + '"'),
        'set "NINJA_SUMMARIZE_BUILD=1"',
        ('set "PATH=' + $shimDir + ';%PATH%"'),
        'where python3',
        'if errorlevel 1 exit /b %errorlevel%',
        'call python3 --version',
        'if errorlevel 1 exit /b %errorlevel%',
        ('cd /d "' + $source + '"'),
        'if errorlevel 1 exit /b %errorlevel%',
        ('"' + $python + '" "third_party\depot_tools\autoninja.py" -j ' + $Jobs + ' -C out\Default chrome'),
        'exit /b %errorlevel%'
    )
    # cmd.exe is code-page-sensitive. Keep this temporary file ASCII and
    # guide users to short ASCII installation paths such as C:\src\Arcium-Windows.
    foreach ($entry in @($repo, $python, $source, $vcvarsall, $siso, $shimDir)) {
        if ($entry -match '[^\x20-\x7e]') {
            throw 'Place build tools under ASCII-only paths, e.g. C:\src\Arcium-Windows.'
        }
    }
    try {
        New-Item -ItemType Directory -Path $shimDir -ErrorAction Stop | Out-Null
        $shimLines = @('@echo off', ('"' + $python + '" %*'), 'exit /b %errorlevel%')
        [System.IO.File]::WriteAllLines($shimCmd, [string[]]$shimLines, [System.Text.Encoding]::ASCII)
        [System.IO.File]::WriteAllLines($tempCmd, [string[]]$commands, [System.Text.Encoding]::ASCII)
        & $env:ComSpec '/d' '/c' $tempCmd
        $buildExit = $LASTEXITCODE
    }
    finally {
        Remove-Item -LiteralPath $tempCmd -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $shimDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($buildExit -ne 0) {
        throw "Native Chrome build returned $buildExit. Existing output was NOT deleted. Fix the compiler error or rerun to continue."
    }
    $browser = Join-Path $source 'out\Default\chrome.exe'
    Require-File $browser 'compiled chrome.exe'
    Write-Host "ARCIUM_LOCAL_CHROME_COMPILED: $browser"
    Write-Host 'Run python scripts\windows_browser_smoke.py --timeout 60 for isolated headless testing.'
}
finally {
    Pop-Location
}
