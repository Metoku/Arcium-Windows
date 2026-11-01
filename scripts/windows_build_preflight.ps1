# Read-only preflight of the Windows build machine.
# No Chromium source is compiled, installed, or executed by this script.
[CmdletBinding()]
param(
    [string]$OutputPath = "work/windows-toolchain-preflight.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Try-RegistryNumber {
    param([string]$Path, [string]$Name)
    try {
        return [int](Get-ItemPropertyValue -Path $Path -Name $Name -ErrorAction Stop)
    } catch {
        return $null
    }
}

function Try-Command {
    param([string]$Name)
    $command = Get-Command -Name $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    return $null
}

$workspace = (Get-Location).Path
$volumeRoot = [System.IO.Path]::GetPathRoot($workspace)
$drive = [System.IO.DriveInfo]::new($volumeRoot)
$freeGiB = [Math]::Round(($drive.AvailableFreeSpace / 1GB), 2)
$totalGiB = [Math]::Round(($drive.TotalSize / 1GB), 2)

$os = Get-CimInstance -ClassName Win32_OperatingSystem
$ramGiB = [Math]::Round(([double]$os.TotalVisibleMemorySize / 1MB), 2)

$vsRoot = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio/Installer/vswhere.exe'
$vsPath = $null
if (Test-Path -LiteralPath $vsRoot) {
    $result = & $vsRoot '-latest' '-products' '*' '-property' 'installationPath' 2>$null
    if ($LASTEXITCODE -eq 0 -and $result) {
        $vsPath = ($result | Select-Object -First 1).Trim()
    }
}
$windowsSdkRoot = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Windows Kits/10/Include'
$sdkFound = Test-Path -LiteralPath $windowsSdkRoot
$sevenZip = Try-Command '7z'
if (-not $sevenZip) {
    $candidate7z = Join-Path $env:ProgramFiles '7-Zip/7z.exe'
    if (Test-Path -LiteralPath $candidate7z) { $sevenZip = $candidate7z }
}
$gitPath = Try-Command 'git'
$pythonPath = Try-Command 'python'
$longPaths = Try-RegistryNumber -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name 'LongPathsEnabled'
$devMode = Try-RegistryNumber -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock' -Name 'AllowDevelopmentWithoutDevLicense'

# Minimum 100 GiB free and 16 GiB RAM are preflight heuristics, not
# guarantees that a large Chromium build will complete on this machine.
$resourcesSufficient = ($freeGiB -ge 100 -and $ramGiB -ge 16)
$toolchainPresent = [bool]($vsPath -and $sdkFound -and $gitPath -and $pythonPath)
$goodToAttempt = ($resourcesSufficient -and $toolchainPresent)

$report = [ordered]@{
    status = 'READ_ONLY_PREFLIGHT'
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    runner_name = $env:RUNNER_NAME
    os = $os.Caption
    os_version = $os.Version
    architecture = $env:PROCESSOR_ARCHITECTURE
    workspace_drive = $volumeRoot
    workspace_drive_free_gib = $freeGiB
    workspace_drive_total_gib = $totalGiB
    total_ram_gib = $ramGiB
    visual_studio_path = $vsPath
    windows_sdk_present = [bool]$sdkFound
    sevenzip_path = $sevenZip
    git_path = $gitPath
    python_path = $pythonPath
    long_paths_enabled = ($longPaths -eq 1)
    developer_mode_enabled = ($devMode -eq 1)
    resources_appear_sufficient = [bool]$resourcesSufficient
    toolchain_appears_present = [bool]$toolchainPresent
    recommended_for_first_compilation_attempt = [bool]$goodToAttempt
    chromium_build_executed = $false
    browser_runtime_test_executed = $false
    caveat = 'Heuristic hardware and tool availability check only; not proof of successful Chromium compilation.'
}

$destination = [System.IO.Path]::GetFullPath($OutputPath)
$parent = [System.IO.Path]::GetDirectoryName($destination)
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}
$json = $report | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($destination, $json + [Environment]::NewLine,
                               [System.Text.UTF8Encoding]::new($false))
Write-Host $json
if (-not $goodToAttempt) {
    Write-Warning 'Runner is not recommended for a full Chromium build based on this read-only preflight.'
}
