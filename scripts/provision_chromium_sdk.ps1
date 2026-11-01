# Provision the exact Windows SDK required by pinned Chromium 156.
#
# SDK 10.0.28000.0 is hardcoded in Chromium's build/vs_toolchain.py and
# build/toolchain/win/setup_toolchain.py. The SDK must actually be installed:
# merely selecting the older 26100 through vcvars cannot satisfy GN.
#
# Only run -Install on an ephemeral, authorized Windows CI build machine.
[CmdletBinding()]
param(
    [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$requiredVersion = '10.0.28000.0'
$kitRoot = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Windows Kits/10'
$includeRoot = Join-Path $kitRoot ("Include/" + $requiredVersion)
$libRoot = Join-Path $kitRoot ("Lib/" + $requiredVersion)

function Test-RequiredSdk {
    $paths = @(
        (Join-Path $includeRoot 'um'),
        (Join-Path $includeRoot 'shared'),
        (Join-Path $includeRoot 'ucrt'),
        (Join-Path $libRoot 'um/x64'),
        (Join-Path $libRoot 'ucrt/x64')
    )
    $missing = @($paths | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Container) })
    if ($missing.Count -gt 0) {
        Write-Host ("Missing Windows SDK $requiredVersion components:")
        $missing | ForEach-Object { Write-Host ("  " + $_) }
        return $false
    }
    Write-Host ("Verified complete required Windows SDK: " + $requiredVersion)
    return $true
}

if (Test-RequiredSdk) {
    Write-Host 'No SDK installation needed.'
    exit 0
}

if (-not $Install) {
    throw "Required Chromium SDK $requiredVersion is incomplete or absent. Use -Install only on an ephemeral authorized build runner."
}

$downloadDir = Join-Path $env:RUNNER_TEMP 'arcium-windows-sdk-bootstrap'
New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
$installerPath = Join-Path $downloadDir 'winsdksetup.exe'

# Official Windows SDK September 2026 (10.0.28000.2957) Microsoft installer.
# Sourced from Microsoft's Windows SDK downloads page (go.microsoft.com).
$officialInstaller = 'https://go.microsoft.com/fwlink/?linkid=2382519'
Write-Host "Downloading official Microsoft Windows SDK bootstrapper..."
Invoke-WebRequest -Uri $officialInstaller -OutFile $installerPath -MaximumRedirection 10

# Windows SDK installation elevates code, so reject an unsigned or
# non-Microsoft-signed bootstrapper even if downloaded from the Microsoft link.
$signature = Get-AuthenticodeSignature -LiteralPath $installerPath
if (($signature.Status -ne 'Valid') -or
    (-not $signature.SignerCertificate) -or
    ($signature.SignerCertificate.Subject -notmatch 'Microsoft')) {
    throw "SDK setup Authenticode signature verification failed: $($signature.Status)"
}
Write-Host 'Verified Microsoft Authenticode signature on Windows SDK installer.'

# Installs just the native desktop SDK x64/x86 components needed by Chromium.
# A servicing release (28000.2957) still installs the SDK folder 10.0.28000.0.
$arguments = @(
    '/features', 'OptionId.DesktopCPPx64', 'OptionId.DesktopCPPx86',
    '/quiet', '/norestart', '/ceip', 'off'
)
Write-Host "Installing official Windows SDK $requiredVersion native desktop components..."
$process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru -NoNewWindow
if ($process.ExitCode -notin @(0, 3010)) {
    throw "Official Windows SDK installer failed with exit code $($process.ExitCode)"
}
if ($process.ExitCode -eq 3010) {
    Write-Warning 'Windows SDK installer requests a reboot; CI runner may require replacement.'
}
if (-not (Test-RequiredSdk)) {
    throw "Windows SDK installation returned successfully but required $requiredVersion SDK directories are missing."
}
Write-Host 'Windows SDK bootstrap complete; GN can use the required SDK.'
