# Shared packaging/update contracts. Dot-sourcing this file performs no I/O.
function ConvertTo-ArciumVersion {
    param([Parameter(Mandatory)][string]$Value)
    $m = [regex]::Match($Value, '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$')
    if (-not $m.Success) { throw "Unsupported release version: $Value" }
    $numbers = @()
    foreach ($i in 1..3) {
        $n = 0
        if (-not [int]::TryParse($m.Groups[$i].Value, [ref]$n) -or $n -gt 65535) {
            throw "Release version component is outside 0..65535: $Value"
        }
        $numbers += $n
    }
    $pre = @()
    if ($m.Groups[4].Success) { $pre = @($m.Groups[4].Value.Split('.')) }
    foreach ($part in $pre) {
        if ($part -match '^[0-9]+$' -and $part.Length -gt 1 -and $part.StartsWith('0')) {
            throw "Leading zero in prerelease version: $Value"
        }
    }
    [pscustomobject]@{ Value=$Value; Numbers=$numbers; Pre=$pre }
}

function Compare-ArciumVersion {
    param([string]$Left, [string]$Right)
    $a = ConvertTo-ArciumVersion $Left
    $b = ConvertTo-ArciumVersion $Right
    foreach ($i in 0..2) {
        if ($a.Numbers[$i] -ne $b.Numbers[$i]) { return [Math]::Sign($a.Numbers[$i] - $b.Numbers[$i]) }
    }
    if ($a.Pre.Count -eq 0 -and $b.Pre.Count -eq 0) { return 0 }
    if ($a.Pre.Count -eq 0) { return 1 }
    if ($b.Pre.Count -eq 0) { return -1 }
    for ($i=0; $i -lt [Math]::Min($a.Pre.Count, $b.Pre.Count); $i++) {
        $x=$a.Pre[$i]; $y=$b.Pre[$i]
        $xn=$x -match '^[0-9]+$'; $yn=$y -match '^[0-9]+$'
        if ($xn -and -not $yn) { return -1 }
        if ($yn -and -not $xn) { return 1 }
        if ($xn -and $yn -and $x.Length -ne $y.Length) { return [Math]::Sign($x.Length-$y.Length) }
        $cmp=[string]::CompareOrdinal($x,$y)
        if ($cmp -ne 0) { return [Math]::Sign($cmp) }
    }
    return [Math]::Sign($a.Pre.Count-$b.Pre.Count)
}

function Get-ArciumSha256 {
    param([string]$Path)
    $algorithm=[System.Security.Cryptography.SHA256]::Create()
    try {
        $stream=[System.IO.File]::OpenRead($Path)
        try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
        finally { $stream.Dispose() }
    }
    finally { $algorithm.Dispose() }
}

function Assert-ArciumChecksum {
    param([string]$File, [string]$ChecksumFile, [string]$ExpectedName, [string]$ApiDigest='')
    if ((Get-Item -LiteralPath $ChecksumFile).Length -gt 4096) { throw 'Checksum file is too large.' }
    $text=[System.IO.File]::ReadAllText($ChecksumFile).Trim()
    $m=[regex]::Match($text, '^([a-fA-F0-9]{64})  ' + [regex]::Escape($ExpectedName) + '$')
    if (-not $m.Success) { throw 'Checksum must name exactly the requested release asset.' }
    $actual=Get-ArciumSha256 $File
    if ($actual -ne $m.Groups[1].Value.ToLowerInvariant()) { throw 'SHA256 checksum mismatch.' }
    if ($ApiDigest -and $ApiDigest -cne ('sha256:'+$actual)) { throw 'GitHub asset digest mismatch.' }
    return $actual
}

function Get-ArciumField {
    param($Object,[string]$Name,$Default=$null)
    if ($null -eq $Object) { return $Default }
    $p=$Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $Default }
    return $p.Value
}

function Get-ArciumAsset {
    param($Release,[string]$Name,[long]$MaximumSize=2147483648)
    $assets=@((Get-ArciumField $Release 'assets' @()) | Where-Object { (Get-ArciumField $_ 'name') -ceq $Name })
    if ($assets.Count -eq 0) { return $null }
    if ($assets.Count -ne 1) { throw "Duplicate release asset: $Name" }
    $asset=$assets[0]
    if ((Get-ArciumField $asset 'state') -ne 'uploaded') { return $null }
    $size=[long](Get-ArciumField $asset 'size' 0)
    if ($size -le 0 -or $size -gt $MaximumSize) { throw "Invalid release asset size: $Name" }
    $tag=Get-ArciumField $Release 'tag_name'
    $expected="https://github.com/Metoku/Arcium-Windows/releases/download/$tag/$Name"
    if ((Get-ArciumField $asset 'browser_download_url') -cne $expected) {
        throw "Release asset is outside the Arcium repository: $Name"
    }
    $digest=[string](Get-ArciumField $asset 'digest' '')
    if ($digest -and $digest -cnotmatch '^sha256:[0-9a-f]{64}$') { throw 'Invalid GitHub asset digest.' }
    [pscustomobject]@{ Name=$Name; Url=$expected; Digest=$digest; Size=$size }
}

function Find-ArciumInstallerUpdate {
    param([object[]]$Releases,[string]$CurrentVersion,[ValidateSet('stable','preview')][string]$Channel)
    $null=ConvertTo-ArciumVersion $CurrentVersion
    $best=$null
    foreach ($release in $Releases) {
        if (Get-ArciumField $release 'draft' $true) { continue }
        $tag=[string](Get-ArciumField $release 'tag_name' '')
        if (-not $tag.StartsWith('v')) { continue }
        try { $v=ConvertTo-ArciumVersion $tag.Substring(1) } catch { continue }
        if ($Channel -eq 'stable' -and ((Get-ArciumField $release 'prerelease' $true) -or $v.Pre.Count -gt 0)) { continue }
        if ((Compare-ArciumVersion $v.Value $CurrentVersion) -le 0) { continue }
        $name="Arcium-Windows-$($v.Value)-Setup.exe"
        $installer=Get-ArciumAsset $release $name
        $checksum=Get-ArciumAsset $release ($name+'.sha256') 4096
        if ($null -eq $installer -or $null -eq $checksum) { continue }
        if ($null -eq $best -or (Compare-ArciumVersion $v.Value $best.Version) -gt 0) {
            $best=[pscustomobject]@{ Version=$v.Value; Installer=$installer; Checksum=$checksum }
        }
    }
    return $best
}

function Read-ArciumInstall {
    param([string]$Root)
    $path=Join-Path $Root 'arcium-install.ini'
    $values=@{}; $section=''
    foreach ($line in [System.IO.File]::ReadAllLines($path)) {
        $s=$line.Trim()
        if ($s.StartsWith('[') -and $s.EndsWith(']')) { $section=$s.Substring(1,$s.Length-2); continue }
        if ($section -ne 'Install' -or -not $s -or $s.StartsWith(';')) { continue }
        $i=$s.IndexOf('=')
        if ($i -lt 1) { throw 'Invalid installation metadata.' }
        $key=$s.Substring(0,$i).Trim()
        if ($values.ContainsKey($key)) { throw 'Duplicate installation metadata.' }
        $values[$key]=$s.Substring($i+1).Trim()
    }
    if ($values.Schema -ne '1' -or $values.Repository -cne 'Metoku/Arcium-Windows' -or
        $values.Channel -notin @('stable','preview')) { throw 'Unrecognized Arcium installation.' }
    $null=ConvertTo-ArciumVersion $values.Version
    [pscustomobject]@{ Version=$values.Version; Channel=$values.Channel; Root=[IO.Path]::GetFullPath($Root) }
}

function New-ArciumWebClient {
    if (-not ('ArciumDistributionWebClient' -as [type])) {
        # Windows PowerShell 5.1 uses .NET Framework's WebClient. Newer hosts
        # retain this API but mark it obsolete.
        Add-Type -IgnoreWarnings -WarningAction SilentlyContinue -TypeDefinition @'
using System;
using System.Net;
public sealed class ArciumDistributionWebClient : WebClient {
    protected override WebRequest GetWebRequest(Uri address) {
        WebRequest request = base.GetWebRequest(address);
        request.Timeout = 60000;
        HttpWebRequest http = request as HttpWebRequest;
        if (http != null) http.ReadWriteTimeout = 600000;
        return request;
    }
}
'@
    }
    [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $client=New-Object ArciumDistributionWebClient
    $client.Headers.Add('User-Agent','Arcium-Windows-Distribution')
    $client.Headers.Add('Accept','application/vnd.github+json')
    return $client
}

function Get-ArciumReleases {
    $client=New-ArciumWebClient
    try {
        $all=@()
        for ($page=1; $page -le 10; $page++) {
            $batch=@(ConvertFrom-Json ($client.DownloadString("https://api.github.com/repos/Metoku/Arcium-Windows/releases?per_page=100&page=$page")))
            $all += $batch
            if ($batch.Count -lt 100) { return $all }
        }
        throw 'Release listing exceeded its limit; visit the repository releases page.'
    }
    finally { $client.Dispose() }
}

function Receive-ArciumInstaller {
    param($Candidate,[string]$Directory)
    $null=[IO.Directory]::CreateDirectory($Directory)
    $file=Join-Path $Directory $Candidate.Installer.Name
    $checksum=Join-Path $Directory $Candidate.Checksum.Name
    if ((Test-Path -LiteralPath $file) -or (Test-Path -LiteralPath $checksum)) { throw 'Download destination already exists.' }
    $client=New-ArciumWebClient
    try {
        $client.DownloadFile($Candidate.Checksum.Url,$checksum)
        if ((Get-Item -LiteralPath $checksum).Length -ne $Candidate.Checksum.Size) { throw 'Checksum download size mismatch.' }
        if ($Candidate.Checksum.Digest -and ('sha256:'+(Get-ArciumSha256 $checksum)) -cne $Candidate.Checksum.Digest) { throw 'Checksum asset digest mismatch.' }
        $client.DownloadFile($Candidate.Installer.Url,$file)
        if ((Get-Item -LiteralPath $file).Length -ne $Candidate.Installer.Size) { throw 'Installer download size mismatch.' }
        $null=Assert-ArciumChecksum $file $checksum $Candidate.Installer.Name $Candidate.Installer.Digest
        return $file
    }
    finally { $client.Dispose() }
}

function Test-ArciumRuntimeName {
    param([string]$Name)
    if ($Name -match '\.(pdb|obj|lib|log|csv)$') { return $false }
    $parts=$Name.Split('/')
    if ($parts.Count -gt 1) { return $parts[0] -in @('locales','MEIPreload','IwaKeyDistribution','WidevineCdm','Extensions','VisualElements') }
    return $Name -match '(?i)\.(dll|pak|manifest)$' -or
        $Name -like 'LICENSE*' -or $Name -like 'COPYING*' -or $Name -like 'NOTICE*' -or
        $Name -in @('chrome.exe','chrome_proxy.exe','chrome_pwa_launcher.exe','notification_helper.exe',
            'elevation_service.exe','elevated_tracing_service.exe','icudtl.dat','v8_context_snapshot.bin',
            'snapshot_blob.bin','vk_swiftshader_icd.json','chrome.VisualElementsManifest.xml','credits.html')
}

function Expand-ArciumRuntime {
    param([string]$Zip,[string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $m=[regex]::Match([IO.Path]::GetFileName($Zip),'^Arcium-Windows-(.+)\.zip$')
    if (-not $m.Success) { throw 'Expected an Arcium portable ZIP filename.' }
    $version=(ConvertTo-ArciumVersion $m.Groups[1].Value).Value
    $prefix="Arcium-Windows-$version/"
    if (Test-Path -LiteralPath $Destination) { throw 'Extraction destination already exists.' }
    $archive=[IO.Compression.ZipFile]::OpenRead($Zip)
    try {
        if ($archive.Entries.Count -gt 20000) { throw 'Runtime archive has too many entries.' }
        $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $plan=@(); [long]$total=0
        foreach ($entry in $archive.Entries) {
            $name=$entry.FullName.Replace('\','/')
            if (-not $name.StartsWith($prefix,[StringComparison]::Ordinal)) { throw 'Unexpected archive root.' }
            if ($name -match '(^|/)\.\.?(/|$)|[:\x00-\x1f]' -or $name.StartsWith('/')) { throw 'Unsafe archive path.' }
            foreach ($part in $name.TrimEnd('/').Split('/')) {
                if (-not $part -or $part -match '[. ]$|^(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)') { throw 'Unsafe Windows archive path.' }
            }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'Archive links are not supported.' }
            if (-not $seen.Add($name.TrimEnd('/'))) { throw 'Duplicate archive path.' }
            if ($name.EndsWith('/')) { continue }
            $relative=$name.Substring($prefix.Length)
            if (-not (Test-ArciumRuntimeName $relative)) { throw "Unexpected runtime file: $relative" }
            $total += $entry.Length
            if ($seen.Count -gt 20000 -or $total -gt 8589934592) { throw 'Runtime archive exceeds extraction limits.' }
            $plan += [pscustomobject]@{ Entry=$entry; Relative=$relative }
        }
        $null=[IO.Directory]::CreateDirectory($Destination)
        foreach ($item in $plan) {
            $path=Join-Path $Destination $item.Relative
            $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
            $inputStream=$item.Entry.Open()
            try {
                $outputStream=[IO.File]::Open($path,[IO.FileMode]::CreateNew)
                try { $inputStream.CopyTo($outputStream) } finally { $outputStream.Dispose() }
            }
            finally { $inputStream.Dispose() }
        }
    }
    finally { $archive.Dispose() }
    foreach ($required in @('chrome.exe','chrome.dll','chrome_elf.dll','resources.pak','chrome_100_percent.pak','locales/en-US.pak','LICENSE.Arcium.txt')) {
        $file=Join-Path $Destination $required
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item -LiteralPath $file).Length -eq 0) { throw "Missing runtime file: $required" }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Destination 'v8_context_snapshot.bin')) -and
        -not (Test-Path -LiteralPath (Join-Path $Destination 'snapshot_blob.bin'))) { throw 'Missing V8 snapshot.' }
    return $version
}

function Assert-ArciumX64Executable {
    param([string]$Path)
    $stream=[IO.File]::OpenRead($Path)
    $reader=[IO.BinaryReader]::new($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5A4D) { throw 'Runtime executable is not a Windows PE file.' }
        $stream.Position=0x3C
        $pe=$reader.ReadUInt32()
        if ($pe -lt 0x40 -or $pe -gt ($stream.Length-6)) { throw 'Invalid PE header.' }
        $stream.Position=$pe
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw 'This installer requires an x64 browser runtime.' }
    }
    finally { $reader.Dispose() }
}
