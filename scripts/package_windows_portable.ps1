# Package an existing browser build. No compilation, installer or browser launch.
[CmdletBinding()]
param(
    [string]$BuildDirectory = '',
    [string]$OutputDirectory = '',
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?$')]
    [string]$Version = '0.1.0-alpha.1',
    [switch]$ListOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).ProviderPath
if (-not $BuildDirectory) {
    $BuildDirectory = Join-Path $repo 'work/windows-platform/build/src/out/Default'
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repo 'dist' }
$buildItem = Get-Item -LiteralPath $BuildDirectory -Force
if ($buildItem -isnot [System.IO.DirectoryInfo]) { throw 'BuildDirectory must be a directory.' }
$buildRoot = $buildItem.FullName.TrimEnd([System.IO.Path]::DirectorySeparatorChar)
$outputRoot = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDirectory)
$outputRoot = [System.IO.Path]::GetFullPath($outputRoot).TrimEnd([System.IO.Path]::DirectorySeparatorChar)
$sourcePrefix = $buildRoot + [System.IO.Path]::DirectorySeparatorChar
if ($outputRoot.Equals($buildRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $outputRoot.StartsWith($sourcePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDirectory must be outside the build directory.'
}

$files = [System.Collections.Generic.Dictionary[string,string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase)

function Assert-RegularEntry {
    param([System.IO.FileSystemInfo]$Entry)
    if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Refusing to package a symbolic link or junction: $($Entry.FullName)"
    }
}

function Add-RuntimeFile {
    param([System.IO.FileInfo]$Entry)
    Assert-RegularEntry $Entry
    if ($Entry.Extension.ToLowerInvariant() -in @('.pdb', '.obj', '.lib', '.log', '.csv')) { return }
    $relative = $Entry.FullName.Substring($sourcePrefix.Length)
    if ($relative.Equals('LICENSE.Arcium.txt', [System.StringComparison]::OrdinalIgnoreCase)) { return }
    $files.Add($relative, $Entry.FullName)
}

Assert-RegularEntry $buildItem
foreach ($required in @('chrome.exe', 'chrome.dll', 'chrome_elf.dll', 'resources.pak',
                        'chrome_100_percent.pak', 'locales/en-US.pak')) {
    $path = Join-Path $buildRoot $required
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required runtime file: $required"
    }
    if ((Get-Item -LiteralPath $path).Length -eq 0) {
        throw "Required runtime file is empty: $required"
    }
}
$snapshots = @(@('v8_context_snapshot.bin', 'snapshot_blob.bin') | Where-Object {
    $path = Join-Path $buildRoot $_
    (Test-Path -LiteralPath $path -PathType Leaf) -and (Get-Item -LiteralPath $path).Length -gt 0
})
if ($snapshots.Count -eq 0) {
    throw 'Missing the external V8 snapshot for this browser build.'
}
$license = Join-Path $repo 'LICENSE'
if (-not (Test-Path -LiteralPath $license -PathType Leaf)) { throw 'Project LICENSE is missing.' }

$namedFiles = @(
    'chrome.exe', 'chrome_proxy.exe', 'chrome_pwa_launcher.exe', 'notification_helper.exe',
    'elevation_service.exe', 'elevated_tracing_service.exe',
    'icudtl.dat', 'v8_context_snapshot.bin', 'snapshot_blob.bin',
    'vk_swiftshader_icd.json', 'chrome.VisualElementsManifest.xml', 'credits.html'
)
foreach ($entry in Get-ChildItem -LiteralPath $buildRoot -File -Force) {
    $extension = $entry.Extension.ToLowerInvariant()
    if ($extension -in @('.dll', '.pak', '.manifest') -or
        $entry.Name -in $namedFiles -or
        $entry.Name -like 'LICENSE*' -or $entry.Name -like 'COPYING*' -or $entry.Name -like 'NOTICE*') {
        Add-RuntimeFile $entry
    }
}

# Walk only known runtime folders. Inspect links before descending; never
# recursively traverse a profile, build cache or arbitrary build-output folder.
foreach ($name in @('locales', 'MEIPreload', 'IwaKeyDistribution', 'WidevineCdm',
                    'Extensions', 'VisualElements')) {
    $path = Join-Path $buildRoot $name
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $directory = Get-Item -LiteralPath $path -Force
    Assert-RegularEntry $directory
    if ($directory -isnot [System.IO.DirectoryInfo]) { throw "Expected runtime directory: $name" }
    $pending = [System.Collections.Generic.Stack[System.IO.DirectoryInfo]]::new()
    $pending.Push($directory)
    while ($pending.Count -gt 0) {
        $current = $pending.Pop()
        foreach ($entry in Get-ChildItem -LiteralPath $current.FullName -Force) {
            Assert-RegularEntry $entry
            if ($entry -is [System.IO.DirectoryInfo]) { $pending.Push($entry) }
            else { Add-RuntimeFile $entry }
        }
    }
}
$relativeFiles = @($files.Keys | Sort-Object)
if ($ListOnly) {
    $relativeFiles
    'LICENSE.Arcium.txt (from the project LICENSE)'
    Write-Host "Read-only package plan: $($relativeFiles.Count) runtime files."
    return
}

$packageName = "Arcium-Windows-$Version"
$packageRoot = Join-Path $outputRoot $packageName
$zipPath = Join-Path $outputRoot ($packageName + '.zip')
$checksumPath = $zipPath + '.sha256'
foreach ($path in @($packageRoot, $zipPath, $checksumPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Output already exists: $path. Use a new Version or OutputDirectory."
    }
}
[System.IO.Directory]::CreateDirectory($packageRoot) | Out-Null
foreach ($relative in $relativeFiles) {
    $destination = Join-Path $packageRoot $relative
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($destination)) | Out-Null
    [System.IO.File]::Copy($files[$relative], $destination, $false)
}
[System.IO.File]::Copy($license, (Join-Path $packageRoot 'LICENSE.Arcium.txt'), $false)

# ZipFile streams the archive and supports Zip64. It avoids Compress-Archive's
# per-file size limit and leaves the staged folder available for inspection.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $packageRoot, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $true)
$sha256 = [System.Security.Cryptography.SHA256]::Create()
$archiveStream = [System.IO.File]::OpenRead($zipPath)
try {
    $hash = [System.BitConverter]::ToString($sha256.ComputeHash($archiveStream)).Replace('-', '').ToLowerInvariant()
}
finally {
    $archiveStream.Dispose()
    $sha256.Dispose()
}
[System.IO.File]::WriteAllText($checksumPath,
    $hash + '  ' + [System.IO.Path]::GetFileName($zipPath) + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false))

Write-Host 'ARCIUM_PORTABLE_ZIP_CREATED'
Write-Host "Folder: $packageRoot"
Write-Host "ZIP: $zipPath"
Write-Host "SHA256: $hash"
Write-Host 'Build output was retained. Extract and test the ZIP before publishing it.'
