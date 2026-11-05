[CmdletBinding()]
param([Parameter(Mandatory)][string]$ReleaseTag,[Parameter(Mandatory)][string]$OutputDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../installer/windows/Distribution.ps1')
if (-not $ReleaseTag.StartsWith('v')) { throw 'ReleaseTag must start with v.' }
$version=(ConvertTo-ArciumVersion $ReleaseTag.Substring(1)).Value
$name="Arcium-Windows-$version.zip"
$client=New-ArciumWebClient
try {
    $release=ConvertFrom-Json ($client.DownloadString("https://api.github.com/repos/Metoku/Arcium-Windows/releases/tags/$ReleaseTag"))
    if ((Get-ArciumField $release 'draft' $true) -or (Get-ArciumField $release 'tag_name') -cne $ReleaseTag) { throw 'A published matching release is required.' }
    $asset=Get-ArciumAsset $release $name
    $checksum=Get-ArciumAsset $release ($name+'.sha256') 4096
    if ($null -eq $asset -or $null -eq $checksum) { throw 'Portable ZIP/checksum assets are missing.' }
    $root=$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
    $root=[IO.Path]::GetFullPath($root)
    $null=[IO.Directory]::CreateDirectory($root)
    $file=Join-Path $root $name; $sum=Join-Path $root ($name+'.sha256')
    if ((Test-Path -LiteralPath $file) -or (Test-Path -LiteralPath $sum)) { throw 'Portable download output already exists.' }
    $client.DownloadFile($checksum.Url,$sum)
    if ((Get-Item -LiteralPath $sum).Length -ne $checksum.Size) { throw 'Checksum download size mismatch.' }
    if ($checksum.Digest -and ('sha256:'+(Get-ArciumSha256 $sum)) -cne $checksum.Digest) { throw 'Checksum asset digest mismatch.' }
    $client.DownloadFile($asset.Url,$file)
    if ((Get-Item -LiteralPath $file).Length -ne $asset.Size) { throw 'Portable download size mismatch.' }
    $hash=Assert-ArciumChecksum $file $sum $name $asset.Digest
    Write-Host "Verified portable release: $ReleaseTag ($hash)"
}
finally { $client.Dispose() }
