; Inno Setup Script for Offline OMR Evaluation System
; Modern Windows Installer with Shortcut Selection and Complete Clean Uninstaller

#define MyAppName "Offline OMR Evaluation System"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Syam Evaluation Systems"
#define MyAppExeName "OMREvaluationSystem.exe"

[Setup]
AppId={{8B3E4241-7A65-4F58-9A78-3F7195F9C110}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\OMREvaluationSystem
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=
OutputDir=c:\Projects\PC\Syam\installer_output
OutputBaseFilename=OMREvaluationSystem_Setup
SetupIconFile=c:\Projects\PC\Syam\Application\resources\app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog commandline
UninstallDisplayIcon={app}\resources\app_icon.ico
DisableProgramGroupPage=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Main application binaries and libraries
Source: "c:\Projects\PC\Syam\Application\dist\OMREvaluationSystem\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Application icon
Source: "c:\Projects\PC\Syam\Application\resources\app_icon.ico"; DestDir: "{app}\resources"; Flags: ignoreversion
Source: "c:\Projects\PC\Syam\Application\resources\app_icon.png"; DestDir: "{app}\resources"; Flags: ignoreversion
; License key generation utility
Source: "c:\Projects\PC\Syam\generate_key.py"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\app_icon.ico"
Name: "{autoprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\app_icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\resources\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\exports"
Type: files; Name: "{app}\crash.log"
Type: dirifempty; Name: "{app}"
