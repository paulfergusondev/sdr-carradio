#define AppName "PyRadio SDR"
#define AppVersion "1.0.0"
#define AppExeName "PyRadioSDR.exe"
#define AppPublisher "PyRadio SDR"
#define AppUserModelID "PyRadioSDR.App"
#define ProjectRoot ".."
#define DistDir ProjectRoot + "\\dist"
#define DistAppDir DistDir + "\\PyRadioSDR"
#define OutputDir DistDir + "\\installer"
#define SetupIcon ProjectRoot + "\\assets\\icons\\pyradio_sdr.ico"

[Setup]
AppId={{20BB577D-5F38-48E6-9365-AB0FD7EDB071}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=PyRadioSDRSetup
SetupIconFile={#SetupIcon}
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#DistAppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "{#AppUserModelID}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent