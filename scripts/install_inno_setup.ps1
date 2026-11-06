# Explicit Windows CI tool bootstrap shared by installer and release candidates.
[CmdletBinding()]
param([string]$OutputDirectory='')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Inno Setup requires Windows.' }
. (Join-Path $PSScriptRoot '../installer/windows/Distribution.ps1')
if (-not $OutputDirectory) { $OutputDirectory=Join-Path ([IO.Path]::GetTempPath()) 'Arcium-Inno' }
$tool=[IO.Path]::GetFullPath($OutputDirectory)
$download=Join-Path ([IO.Path]::GetTempPath()) ('Arcium-Inno-'+[guid]::NewGuid().ToString('N')+'.exe')
try {
    $client=New-ArciumWebClient
    try {
        $client.DownloadFile('https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe',$download)
    } finally { $client.Dispose() }
    if ((Get-ArciumSha256 $download) -cne '8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0') {
        throw 'Inno Setup digest mismatch.'
    }
    $process=Start-Process -FilePath $download -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="'+$tool+'"')) -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Inno Setup installation failed: $($process.ExitCode)" }
    $compiler=Join-Path $tool 'ISCC.exe'
    if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'ISCC.exe was not installed.' }
    if ($env:GITHUB_ENV) { "ARCIUM_ISCC=$compiler" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8 }
    Write-Host "Inno Setup compiler: $compiler"
} finally { Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue }
