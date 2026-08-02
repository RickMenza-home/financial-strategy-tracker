; Inno Setup script for Financial Strategy Tracker
; Build with: iscc installer.iss
; Output: Output\FinancialStrategyTracker-Setup-<version>.exe

#define MyAppName "Financial Strategy Tracker"
#define MyAppPublisher "Financial Strategy Tracker"
#define MyAppExeName "financial_tracker.exe"
#define MyAppVersion ReadIni(SourcePath + "\VERSION", "", "", "0.0.0")

; Read version from VERSION file (plain text, one line)
#define FileHandle FileOpen(SourcePath + "\VERSION")
#if FileHandle
  #define MyAppVersion Trim(FileRead(FileHandle))
  #expr FileClose(FileHandle)
#endif

[Setup]
AppId={{B8F3A2D1-7C4E-4A9B-8D6F-1E5C3A7B9D2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\FinancialStrategyTracker
DefaultGroupName={#MyAppName}
OutputDir=Output
OutputBaseFilename=FinancialStrategyTracker-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Do NOT touch user data directory on uninstall
UninstallFilesDir={app}\uninstall

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Include the entire PyInstaller onedir output
Source: "dist\financial_tracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Desktop shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
; Start Menu entry
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Optionally launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only remove the install directory — NEVER touch {userappdata}\FinancialStrategyTracker
Type: filesandordirs; Name: "{app}"
