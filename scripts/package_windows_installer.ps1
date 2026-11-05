[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$PortableZip,
    [string]$Version='',
    [string]$ChecksumFile='',
    [string]$OutputDirectory='',
    [string]$InnoCompiler=''
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).ProviderPath
$distribution=Join-Path $repo 'installer/windows'
. (Join-Path $distribution 'Distribution.ps1')
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Installer creation requires Windows.' }
$zip=(Get-Item -LiteralPath $PortableZip).FullName
if (-not $ChecksumFile) { $ChecksumFile=$zip+'.sha256' }
$hash=Assert-ArciumChecksum $zip $ChecksumFile ([IO.Path]::GetFileName($zip))
$filename=[regex]::Match([IO.Path]::GetFileName($zip),'^Arcium-Windows-(.+)\.zip$')
if (-not $filename.Success) { throw 'Expected an Arcium portable ZIP filename.' }
$runtimeVersion=(ConvertTo-ArciumVersion $filename.Groups[1].Value).Value
if (-not $Version) { $Version=$runtimeVersion }
$parsed=ConvertTo-ArciumVersion $Version
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $repo 'dist' }
$output=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$output=[IO.Path]::GetFullPath($output)
$name="Arcium-Windows-$Version-Setup.exe"
foreach ($suffix in @('','.sha256','.json')) {
    if (Test-Path -LiteralPath (Join-Path $output ($name+$suffix))) { throw "Output already exists: $name$suffix" }
}
if (-not $InnoCompiler) { $InnoCompiler=$env:ARCIUM_ISCC }
if (-not $InnoCompiler) {
    foreach ($folder in @(${env:ProgramFiles(x86)},$env:ProgramFiles)) {
        foreach ($edition in @('Inno Setup 7','Inno Setup 6')) {
            if (-not $folder) { continue }
            $path=Join-Path (Join-Path $folder $edition) 'ISCC.exe'
            if (Test-Path -LiteralPath $path -PathType Leaf) { $InnoCompiler=$path; break }
        }
        if ($InnoCompiler) { break }
    }
}
if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler -PathType Leaf)) {
    throw 'Inno Setup is required. Set ARCIUM_ISCC to ISCC.exe, or use the GitHub installer workflow.'
}
$csc=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $csc)) { throw '.NET Framework 4 compiler is missing.' }
$stage=Join-Path ([IO.Path]::GetTempPath()) ('Arcium-Installer-'+[guid]::NewGuid().ToString('N'))
$null=[IO.Directory]::CreateDirectory($stage)
try {
    $payload=Join-Path $stage 'payload'
    $extractedVersion=Expand-ArciumRuntime $zip $payload
    if ($extractedVersion -cne $runtimeVersion) { throw 'Portable version changed during extraction.' }
    Assert-ArciumX64Executable (Join-Path $payload 'chrome.exe')
    Add-Type -AssemblyName System.Drawing
    $icon=[Drawing.Icon]::ExtractAssociatedIcon((Join-Path $payload 'chrome.exe'))
    if ($null -eq $icon) { $icon=[Drawing.SystemIcons]::Application.Clone() }
    try {
        $stream=[IO.File]::Create((Join-Path $stage 'Arcium.ico'))
        try { $icon.Save($stream) } finally { $stream.Dispose() }
    }
    finally { $icon.Dispose() }
    & $csc /nologo /target:winexe /platform:x64 /reference:System.Windows.Forms.dll ("/win32icon:"+(Join-Path $stage 'Arcium.ico')) ("/out:"+(Join-Path $stage 'Arcium.exe')) (Join-Path $distribution 'Launcher.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Arcium launcher compilation failed.' }
    $provenance=[ordered]@{
        Schema=1; PackageVersion=$Version; RuntimeVersion=$runtimeVersion
        PortableFile=[IO.Path]::GetFileName($zip); PortableSha256=$hash
        DistributionCommit=$env:GITHUB_SHA; Repository='Metoku/Arcium-Windows'
    }
    [IO.File]::WriteAllText((Join-Path $stage 'provenance.json'),($provenance|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    $null=[IO.Directory]::CreateDirectory($output)
    $preview='no'; if ($parsed.Pre.Count -gt 0) { $preview='yes' }
    $numeric=($parsed.Numbers -join '.')+'.0'
    & $InnoCompiler /Qp "/DPackageVersion=$Version" "/DRuntimeVersion=$runtimeVersion" "/DNumericVersion=$numeric" "/DPreviewDefault=$preview" "/DStage=$stage" "/DDistribution=$distribution" "/DOutput=$output" (Join-Path $distribution 'Arcium.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compilation failed.' }
    $setup=Join-Path $output $name
    $setupHash=Get-ArciumSha256 $setup
    [IO.File]::WriteAllText(($setup+'.sha256'),($setupHash+'  '+$name+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
    $provenance.InstallerSha256=$setupHash
    [IO.File]::WriteAllText(($setup+'.json'),($provenance|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    Write-Host 'ARCIUM_WINDOWS_INSTALLER_CREATED'
    Write-Host "Installer: $setup"
    Write-Host "SHA256: $setupHash"
}
finally { Remove-Item -LiteralPath $stage -Recurse -Force }
