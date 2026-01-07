; Inno Setup Script for Transcoder
; Creates a Windows installer that registers the application in Control Panel
; and adds it to the system PATH
; Supports both full and lightweight builds

#ifndef BUILD_MODE
  #define BUILD_MODE "lightweight"
#endif

#if BUILD_MODE == "full"
  #define BUILD_DIR "dist\transcode"
  #define InstallerName "transcoder-setup-full"
  #define BuildDescription "Full build with all OCR dependencies included"
#else
  #define BUILD_DIR "dist\transcode-lightweight"
  #define InstallerName "transcoder-setup"
  #define BuildDescription "Lightweight build (OCR dependencies loaded on-demand)"
#endif

#ifndef LZMA_THREADS
  #define LZMA_THREADS 4  ; Default fallback
#endif

#define MyAppName "One Shot Transcoder"
#define MyAppFolder "oneShotTranscoder"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "oneShotTranscoder Contributors"
#define MyAppURL "https://github.com/the-real-p3tr1c0r/oneShotTranscoder"
#define MyAppExeName "transcode.exe"

[Setup]
; Basic installer information
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation directory
DefaultDirName={autopf}\{#MyAppFolder}
DefaultGroupName={#MyAppName}

; License file
LicenseFile=LICENSE

; Output settings
OutputDir=dist
OutputBaseFilename={#InstallerName}

; Compression - LZMA2 with parallel processing (7zip-style)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads={#LZMA_THREADS}
LZMADictionarySize=65536
LZMANumFastBytes=273

; Installer appearance
WizardStyle=modern
SetupIconFile=compiler:SetupClassicIcon.ico

; Privileges
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

; Misc
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Uninstaller
UninstallDisplayIcon={app}\transcode.exe
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath"; Description: "Add to system PATH (allows running 'transcode' from any command prompt)"; GroupDescription: "Additional options:"; Flags: checkedonce

[Files]
; Copy the entire build directory
Source: "{#BUILD_DIR}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Copy batch wrapper
Source: "transcode.bat"; DestDir: "{app}"; Flags: ignoreversion

; Copy license files
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "NOTICE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Store installation info
Root: HKLM; Subkey: "Software\{#MyAppFolder}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\{#MyAppFolder}"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekey

[Code]
const
  EnvironmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

procedure AddToPath();
var
  CurrentPath: string;
  NewPath: string;
begin
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', CurrentPath) then
  begin
    // Check if already in PATH
    if Pos(ExpandConstant('{app}'), CurrentPath) = 0 then
    begin
      // Add to PATH
      NewPath := CurrentPath + ';' + ExpandConstant('{app}');
      RegWriteStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', NewPath);
    end;
  end;
end;

procedure RemoveFromPath();
var
  CurrentPath: string;
  AppPath: string;
  NewPath: string;
  P: Integer;
begin
  if RegQueryStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', CurrentPath) then
  begin
    AppPath := ExpandConstant('{app}');
    
    // Remove with trailing semicolon
    P := Pos(AppPath + ';', CurrentPath);
    if P > 0 then
    begin
      NewPath := Copy(CurrentPath, 1, P - 1) + Copy(CurrentPath, P + Length(AppPath) + 1, MaxInt);
      RegWriteStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', NewPath);
      Exit;
    end;
    
    // Remove with leading semicolon
    P := Pos(';' + AppPath, CurrentPath);
    if P > 0 then
    begin
      NewPath := Copy(CurrentPath, 1, P - 1) + Copy(CurrentPath, P + Length(AppPath) + 1, MaxInt);
      RegWriteStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', NewPath);
      Exit;
    end;
    
    // Remove standalone (only entry)
    if CurrentPath = AppPath then
    begin
      RegWriteStringValue(HKEY_LOCAL_MACHINE, EnvironmentKey, 'Path', '');
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if WizardIsTaskSelected('addtopath') then
      AddToPath();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RemoveFromPath();
  end;
end;

