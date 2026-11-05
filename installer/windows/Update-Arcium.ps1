[CmdletBinding()]
param([switch]$CheckOnly)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'Distribution.ps1')
$download=''
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'The installed updater requires Windows.' }
    $root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $install=Read-ArciumInstall $root
    $candidate=Find-ArciumInstallerUpdate @(Get-ArciumReleases) $install.Version $install.Channel
    if ($CheckOnly) {
        [pscustomobject]@{ CurrentVersion=$install.Version; Channel=$install.Channel; Update=$candidate } | ConvertTo-Json -Depth 5
        exit 0
    }
    Add-Type -AssemblyName System.Windows.Forms
    if ($null -eq $candidate) {
        [Windows.Forms.MessageBox]::Show("No newer installer is available on the $($install.Channel) channel.",'Arcium updates') | Out-Null
        exit 0
    }
    $answer=[Windows.Forms.MessageBox]::Show(
        "Arcium $($candidate.Version) is available. Download and install it? Close Arcium before continuing. Your browser data will be retained.",
        'Arcium updates',[Windows.Forms.MessageBoxButtons]::YesNo,[Windows.Forms.MessageBoxIcon]::Information)
    if ($answer -ne [Windows.Forms.DialogResult]::Yes) { exit 0 }
    $mutex=$null
    try { $mutex=[Threading.Mutex]::OpenExisting('Local\Arcium.Windows.Running') } catch [Threading.WaitHandleCannotBeOpenedException] {}
    if ($null -ne $mutex) { $mutex.Dispose(); throw 'Close all installed Arcium windows, then check for updates again.' }
    $download=Join-Path ([IO.Path]::GetTempPath()) ('Arcium-Update-'+[guid]::NewGuid().ToString('N'))
    $file=Receive-ArciumInstaller $candidate $download
    $process=Start-Process -FilePath $file -ArgumentList @('/SP-','/NORESTART',('/DIR="'+$root+'"')) -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Setup did not complete (exit code $($process.ExitCode))." }
    $updated=Read-ArciumInstall $root
    if ($updated.Version -cne $candidate.Version) { throw 'Setup did not activate the expected release.' }
    [Windows.Forms.MessageBox]::Show("Arcium $($updated.Version) is installed. Open Arcium from the Start menu.",'Arcium updates') | Out-Null
}
catch {
    if ($CheckOnly) { Write-Error $_; exit 1 }
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($_.Exception.Message,'Arcium update failed',[Windows.Forms.MessageBoxButtons]::OK,[Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
finally {
    if ($download -and (Test-Path -LiteralPath $download)) { Remove-Item -LiteralPath $download -Recurse -Force }
}
