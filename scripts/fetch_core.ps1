# Retrieves only the pinned shared Arcium source. It does NOT compile a Windows browser.
[CmdletBinding()]
param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pinFile = Join-Path $projectRoot "upstream/arcium-core.sha"
$revision = (Get-Content -Raw -Path $pinFile).Trim()
if ($revision -cnotmatch '^[0-9a-f]{40}$') {
    throw "Invalid upstream Arcium SHA in $pinFile"
}
if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Join-Path $projectRoot "arcium-core"
}
if (Test-Path $Destination) {
    throw "Destination already exists: $Destination"
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null

git -C $Destination init
if ($LASTEXITCODE -ne 0) { throw "git init failed" }
git -C $Destination remote add origin https://github.com/dr-baker/Arcium.git
if ($LASTEXITCODE -ne 0) { throw "Adding remote failed" }
git -C $Destination -c protocol.version=2 fetch --depth=1 --filter=blob:none origin $revision
if ($LASTEXITCODE -ne 0) { throw "Fetching pinned Arcium revision failed" }
git -C $Destination checkout --detach FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw "Checking out pinned Arcium revision failed" }

$actual = (git -C $Destination rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $actual -cne $revision) {
    throw "Source checkout SHA mismatch: expected $revision; received $actual"
}
if (-not (Test-Path (Join-Path $Destination "patches"))) {
    throw "Pinned Arcium source does not contain expected patches directory"
}
Write-Host "Fetched exact Arcium core revision $actual"
Write-Host "Source bootstrap succeeded. No Chromium or Windows browser was compiled."
