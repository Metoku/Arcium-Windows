#ifndef PackageVersion
  #error PackageVersion is required
#endif
[Setup]
AppId={{5E3517F3-854A-4D0D-A495-2912C5C7D936}
AppName=Arcium
AppVersion={#PackageVersion}
AppPublisher=Arcium Windows contributors
AppPublisherURL=https://github.com/Metoku/Arcium-Windows
AppSupportURL=https://github.com/Metoku/Arcium-Windows/issues
AppUpdatesURL=https://github.com/Metoku/Arcium-Windows/releases
DefaultDirName={localappdata}\Programs\Arcium
DefaultGroupName=Arcium
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
AppMutex=Local\Arcium.Windows.Running
SetupMutex=Local\Arcium.Windows.Setup
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\Arcium.exe
SetupIconFile={#Stage}\Arcium.ico
LicenseFile={#Stage}\payload\LICENSE.Arcium.txt
OutputDir={#Output}
OutputBaseFilename=Arcium-Windows-{#PackageVersion}-Setup
VersionInfoVersion={#NumericVersion}
VersionInfoTextVersion={#PackageVersion}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
UninstallDisplayName=Arcium

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
#if PreviewDefault == "yes"
Name: previewupdates; Description: "Include alpha, beta and other preview updates"
#else
Name: previewupdates; Description: "Include alpha, beta and other preview updates"; Flags: unchecked
#endif

[Files]
Source: "{#Stage}\payload\*"; DestDir: "{app}\versions\{#PackageVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Stage}\Arcium.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\Arcium.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Stage}\provenance.json"; DestDir: "{app}\versions\{#PackageVersion}"; Flags: ignoreversion
Source: "{#Distribution}\Distribution.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#Distribution}\Update-Arcium.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion

[INI]
Filename: "{app}\arcium-install.ini"; Section: Install; Key: Schema; String: "1"
Filename: "{app}\arcium-install.ini"; Section: Install; Key: Repository; String: "Metoku/Arcium-Windows"
Filename: "{app}\arcium-install.ini"; Section: Install; Key: Version; String: "{#PackageVersion}"
Filename: "{app}\arcium-install.ini"; Section: Install; Key: RuntimeVersion; String: "{#RuntimeVersion}"
Filename: "{app}\arcium-install.ini"; Section: Install; Key: Channel; String: "{code:UpdateChannel}"

[Icons]
Name: "{group}\Arcium"; Filename: "{app}\Arcium.exe"; IconFilename: "{app}\Arcium.ico"
Name: "{group}\Check for Arcium updates"; Filename: "{app}\Arcium.exe"; Parameters: "--check-for-updates"; IconFilename: "{app}\Arcium.ico"
Name: "{autodesktop}\Arcium"; Filename: "{app}\Arcium.exe"; IconFilename: "{app}\Arcium.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Arcium.Windows"; ValueData: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows"; ValueType: string; ValueData: "Arcium"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\DefaultIcon"; ValueType: string; ValueData: "{app}\Arcium.ico"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\shell\open\command"; ValueType: string; ValueData: """{app}\Arcium.exe"""
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities"; ValueType: string; ValueName: ApplicationName; ValueData: "Arcium"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities"; ValueType: string; ValueName: ApplicationDescription; ValueData: "Arcium web browser"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities"; ValueType: string; ValueName: ApplicationIcon; ValueData: "{app}\Arcium.ico"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities\URLAssociations"; ValueType: string; ValueName: http; ValueData: "Arcium.WindowsHTML"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities\URLAssociations"; ValueType: string; ValueName: https; ValueData: "Arcium.WindowsHTML"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities\FileAssociations"; ValueType: string; ValueName: ".htm"; ValueData: "Arcium.WindowsHTML"
Root: HKCU; Subkey: "Software\Clients\StartMenuInternet\Arcium.Windows\Capabilities\FileAssociations"; ValueType: string; ValueName: ".html"; ValueData: "Arcium.WindowsHTML"
Root: HKCU; Subkey: "Software\Classes\Arcium.WindowsHTML"; ValueType: string; ValueData: "Arcium HTML Document"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Arcium.WindowsHTML\DefaultIcon"; ValueType: string; ValueData: "{app}\Arcium.ico"
Root: HKCU; Subkey: "Software\Classes\Arcium.WindowsHTML\shell\open\command"; ValueType: string; ValueData: """{app}\Arcium.exe"" ""%1"""

[Run]
Filename: "{app}\Arcium.exe"; Description: "Open Arcium"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\arcium-install.ini"
Type: filesandordirs; Name: "{app}\versions"
Type: dirifempty; Name: "{app}\tools"
Type: dirifempty; Name: "{app}"

[Code]
function Part(var Text: String; Separator: String): String;
var P: Integer;
begin
  P := Pos(Separator, Text);
  if P = 0 then begin Result := Text; Text := ''; end
  else begin Result := Copy(Text, 1, P-1); Delete(Text, 1, P); end;
end;

function OrdinalCompare(A, B: String): Integer;
var I, Count: Integer;
begin
  Count := Length(A);
  if Length(B) < Count then Count := Length(B);
  for I := 1 to Count do
    if Ord(A[I]) <> Ord(B[I]) then begin Result := Ord(A[I])-Ord(B[I]); Exit; end;
  Result := Length(A)-Length(B);
end;

function Digits(Text: String): Boolean;
var I: Integer;
begin
  Result := Text <> '';
  for I := 1 to Length(Text) do
    if (Text[I] < '0') or (Text[I] > '9') then Result := False;
end;

function CompareVersions(A, B: String): Integer;
var AC, BC, AP, BP, X, Y: String; I, N, M: Integer; XD, YD: Boolean;
begin
  AC := Part(A, '-'); AP := A;
  BC := Part(B, '-'); BP := B;
  for I := 1 to 3 do begin
    X := Part(AC, '.'); Y := Part(BC, '.');
    N := StrToIntDef(X, -1); M := StrToIntDef(Y, -1);
    if (N < 0) or (M < 0) then RaiseException('Invalid installed release version.');
    if N <> M then begin Result := N-M; Exit; end;
  end;
  if (AP = '') and (BP = '') then begin Result := 0; Exit; end;
  if AP = '' then begin Result := 1; Exit; end;
  if BP = '' then begin Result := -1; Exit; end;
  while (AP <> '') and (BP <> '') do begin
    X := Part(AP, '.'); Y := Part(BP, '.'); XD := Digits(X); YD := Digits(Y);
    if XD and not YD then begin Result := -1; Exit; end;
    if YD and not XD then begin Result := 1; Exit; end;
    if XD and YD and (Length(X) <> Length(Y)) then begin Result := Length(X)-Length(Y); Exit; end;
    Result := OrdinalCompare(X, Y);
    if Result <> 0 then Exit;
  end;
  Result := Length(AP)-Length(BP);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Root, Marker, Previous: String;
begin
  Result := '';
  Root := ExpandConstant('{app}'); Marker := Root + '\arcium-install.ini';
  if DirExists(Root) then begin
    if (GetIniString('Install', 'Schema', '', Marker) <> '1') or
       (GetIniString('Install', 'Repository', '', Marker) <> 'Metoku/Arcium-Windows') then begin
      Result := 'Choose a new folder. This folder is not a managed Arcium installation.'; Exit;
    end;
    Previous := GetIniString('Install', 'Version', '', Marker);
    if CompareVersions('{#PackageVersion}', Previous) < 0 then
      Result := 'A newer Arcium release is installed. Setup will not downgrade it.';
  end;
end;

function UpdateChannel(Param: String): String;
begin
  if WizardIsTaskSelected('previewupdates') then Result := 'preview' else Result := 'stable';
end;
