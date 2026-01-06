; NSIS Installer Script for Transcoder
; Creates a Windows installer that registers the application in Control Panel
; and adds it to the system PATH
; Supports both full and lightweight builds

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

;--------------------------------
; Build Mode Configuration
; Default to lightweight if not specified via /DBUILD_MODE

!ifndef BUILD_MODE
    !define BUILD_MODE "lightweight"
!endif

; Set build-specific variables
!if "${BUILD_MODE}" == "full"
    !define BUILD_DIR "dist\transcode"
    !define INSTALLER_NAME "transcoder-setup-full.exe"
    !define BUILD_DESCRIPTION "Full build with all OCR dependencies included"
!else
    !define BUILD_DIR "dist\transcode-lightweight"
    !define INSTALLER_NAME "transcoder-setup.exe"
    !define BUILD_DESCRIPTION "Lightweight build (OCR dependencies loaded on-demand)"
!endif

;--------------------------------
; General Information

Name "Transcoder"
OutFile "dist\${INSTALLER_NAME}"
Unicode True

; Version information
!define VERSION "0.1.0"
!define PUBLISHER "oneShotTranscoder Contributors"
!define URL "https://github.com/the-real-p3tr1c0r/oneShotTranscoder"
!define APPNAME "Transcoder"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "${APPNAME}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "CompanyName" "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APPNAME} - Video transcoding tool with OCR subtitle support (${BUILD_DESCRIPTION})"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "Copyright (C) 2025 ${PUBLISHER}"
VIAddVersionKey "URLInfoAbout" "${URL}"

; Use solid LZMA compression for large files (better than default for large builds)
; This prevents memory mapping errors while still compressing
SetCompressor /SOLID lzma
SetCompressorDictSize 64

; Default installation directory
InstallDir "$PROGRAMFILES\Transcoder"

; Request admin privileges
RequestExecutionLevel admin

;--------------------------------
; Interface Settings

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

;--------------------------------
; Pages

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

;--------------------------------
; Languages

!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Installer Sections

Section "Core Application" SecCore
    SectionIn RO  ; Read-only, always installed
    
    SetOutPath "$INSTDIR"
    
    ; Copy the build directory contents
    ; The build creates dist/transcode/ (full) or dist/transcode-lightweight/ (lightweight)
    ; Use /nonfatal to handle large files better and SetOverwrite for better error handling
    SetOverwrite on
    File /nonfatal /r "${BUILD_DIR}\*.*"
    
    ; Create batch wrapper in root for PATH access
    File "transcode.bat"
    
    ; Copy license files
    File "LICENSE"
    File "NOTICE.md"
    File "THIRD_PARTY_LICENSES.md"
    
    ; Create uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    ; Write registry keys for Control Panel
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "Publisher" "${PUBLISHER}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "URLInfoAbout" "${URL}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "NoRepair" 1
    
    ; Get estimated size
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder" "EstimatedSize" "$0"
SectionEnd

Section "Add to PATH" SecPath
    ; Add to system PATH using registry
    ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
    
    ; Check if already in PATH (simple string search)
    Push "$0"
    Push "$INSTDIR"
    Call StrStr
    Pop $1
    ${If} $1 != ""
        ; Already in PATH, skip
        Goto PathDone
    ${EndIf}
    
    ; Append to PATH
    StrCpy $0 "$0;$INSTDIR"
    WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
    
    ; Broadcast environment change
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
    
PathDone:
SectionEnd

; String search function
Function StrStr
    Exch $R1 ; st=haystack,old$R1, $R1=needle
    Exch    ; st=old$R1,haystack, $R1=needle
    Exch $R2 ; st=old$R1,old$R2, $R2=haystack, $R1=needle
    Push $R3
    Push $R4
    Push $R5
    StrLen $R3 $R1
    StrCpy $R4 0
    loop:
        StrCpy $R5 $R2 $R3 $R4
        StrCmp $R5 $R1 done
        StrCmp $R5 "" done
        IntOp $R4 $R4 + 1
        Goto loop
    done:
        StrCpy $R1 $R2 "" $R4
        Pop $R5
        Pop $R4
        Pop $R3
        Pop $R2
        Exch $R1
FunctionEnd

Section "Start Menu Shortcuts" SecShortcuts
    CreateDirectory "$SMPROGRAMS\Transcoder"
    ; Find the actual executable (could be in subdirectory for onedir build)
    IfFileExists "$INSTDIR\transcode.exe" 0 CheckSubdir
        CreateShortcut "$SMPROGRAMS\Transcoder\Transcoder.lnk" "$INSTDIR\transcode.exe"
        Goto ShortcutDone
    CheckSubdir:
        IfFileExists "$INSTDIR\transcode\transcode.exe" 0 NoExe
            CreateShortcut "$SMPROGRAMS\Transcoder\Transcoder.lnk" "$INSTDIR\transcode\transcode.exe"
    NoExe:
    ShortcutDone:
    CreateShortcut "$SMPROGRAMS\Transcoder\Uninstall.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

;--------------------------------
; Section Descriptions

LangString DESC_SecCore ${LANG_ENGLISH} "Core transcoder application (required)"
LangString DESC_SecPath ${LANG_ENGLISH} "Add Transcoder to system PATH for command-line access"
LangString DESC_SecShortcuts ${LANG_ENGLISH} "Create Start Menu shortcuts"

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecCore} $(DESC_SecCore)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecPath} $(DESC_SecPath)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecShortcuts} $(DESC_SecShortcuts)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Uninstaller Section

Section "Uninstall"
    ; Remove files
    RMDir /r "$INSTDIR"
    
    ; Remove Start Menu shortcuts
    RMDir /r "$SMPROGRAMS\Transcoder"
    
    ; Remove from PATH
    ReadRegStr $0 HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path"
    Push "$0"
    Push "$INSTDIR"
    Call un.StrStr
    Pop $1
    ${If} $1 != ""
        ; Remove the directory from PATH (handle different positions)
        Push "$0"
        Push "$INSTDIR;"
        Call un.StrStr
        Pop $2
        ${If} $2 != ""
            ; Remove with trailing semicolon
            Push "$0"
            Push "$INSTDIR;"
            Call un.StrRep
            Pop $0
        ${Else}
            Push "$0"
            Push ";$INSTDIR"
            Call un.StrStr
            Pop $2
            ${If} $2 != ""
                ; Remove with leading semicolon
                Push "$0"
                Push ";$INSTDIR"
                Call un.StrRep
                Pop $0
            ${Else}
                ; Remove standalone (only entry in PATH)
                StrCpy $0 ""
            ${EndIf}
        ${EndIf}
        WriteRegExpandStr HKLM "SYSTEM\CurrentControlSet\Control\Session Manager\Environment" "Path" "$0"
        ; Broadcast environment change
        SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
    ${EndIf}
    
    ; Remove registry keys
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Transcoder"
SectionEnd

; Uninstaller string functions
Function un.StrStr
    Exch $R1
    Exch
    Exch $R2
    Push $R3
    Push $R4
    Push $R5
    StrLen $R3 $R1
    StrCpy $R4 0
    loop:
        StrCpy $R5 $R2 $R3 $R4
        StrCmp $R5 $R1 done
        StrCmp $R5 "" done
        IntOp $R4 $R4 + 1
        Goto loop
    done:
        StrCpy $R1 $R2 "" $R4
        Pop $R5
        Pop $R4
        Pop $R3
        Pop $R2
        Exch $R1
FunctionEnd

Function un.StrRep
    Exch $R4
    Exch
    Exch $R3
    Exch 2
    Exch $R1
    Exch 2
    Exch $R2
    Push $R5
    Push $R6
    StrCpy $R6 ""
    StrLen $R5 $R3
    loop:
        StrCpy $R4 $R1 $R5
        StrCmp $R4 $R3 found
        StrCpy $R4 $R1 1
        StrCpy $R1 $R1 $R5 1
        StrCmp $R1 "" done loop
    found:
        StrCpy $R6 "$R6$R2"
        StrCpy $R1 $R1 $R5 1
        StrCmp $R1 "" done loop
    done:
        StrCpy $R4 $R6
        Pop $R6
        Pop $R5
        Pop $R2
        Pop $R1
        Pop $R3
        Exch $R4
FunctionEnd

