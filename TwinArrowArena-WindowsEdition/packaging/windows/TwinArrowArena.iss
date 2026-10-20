#define AppName "Twin Arrow Arena"
#define AppVersion "1.0.0"
#define ExeName "TwinArrowArena.exe"

[Setup]
AppId={{9B98CD01-9B73-4A66-9BFA-9412913B8F61}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={userappdata}\TwinArrowArena
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=TwinArrowArena-AppData-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes

[Files]
Source: "..\..\dist\{#ExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\server_url.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Twin Arrow Arena"; Filename: "{app}\{#ExeName}"
Name: "{userdesktop}\Twin Arrow Arena"; Filename: "{app}\{#ExeName}"

[Run]
Filename: "{app}\{#ExeName}"; Description: "Launch Twin Arrow Arena"; Flags: postinstall nowait skipifsilent
