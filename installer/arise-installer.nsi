!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

; ARISE Installer Script
; Builds a Windows installer for the ARISE Personal Digital Operator AI System

Name "ARISE"
OutFile "ARISE_Setup_${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES64\ARISE"
InstallDirRegKey HKLM "Software\ARISE" "InstallDir"
RequestExecutionLevel admin
CRCCheck on
WindowIcon "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
UninstallIcon "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"
BrandingText "ARISE Personal Digital Operator AI System"

; Version
!define PRODUCT_VERSION "1.0.0"
!define PRODUCT_PUBLISHER "ARISE Team"
!define PRODUCT_WEB_SITE "https://arise.example.com"
!define PRODUCT_DIR_REGKEY "Software\ARISE"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ARISE"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"

; Modern UI
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\arise-tauri.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

; Reserve files
ReserveFile "arise-tauri.exe"
ReserveFile "core\*.pyd"
ReserveFile "core\*.dll"
ReserveFile "config\*.yaml"
ReserveFile "config\*.example"
ReserveFile "LICENSE.txt"

; Sections
Section "MainFiles" SEC_MAIN
  SetOutPath "$INSTDIR"

  ; Main executable
  File "arise-tauri.exe"

  ; Core Python runtime (embedded)
  File /r "core\*"

  ; Configuration files
  File /r "config\*"

  ; License
  File "LICENSE.txt"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"

  ; Registry entries
  WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayName" "ARISE"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\arise-tauri.exe"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "NoModify" "1"
  WriteRegStr HKLM "${PRODUCT_UNINST_KEY}" "NoRepair" "1"
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "StartMenu" SEC_STARTMENU
  CreateDirectory "$SMPROGRAMS\ARISE"
  CreateShortCut "$SMPROGRAMS\ARISE\ARISE.lnk" "$INSTDIR\arise-tauri.exe" "" "$INSTDIR\arise-tauri.exe" 0
  CreateShortCut "$SMPROGRAMS\ARISE\Uninstall.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
  CreateShortCut "$SMPROGRAMS\ARISE\ARISE (Dev Mode).lnk" "$INSTDIR\arise-tauri.exe" "--dev" "$INSTDIR\arise-tauri.exe" 0
SectionEnd

Section "DesktopShortcut" SEC_DESKTOP
  CreateShortCut "$DESKTOP\ARISE.lnk" "$INSTDIR\arise-tauri.exe" "" "$INSTDIR\arise-tauri.exe" 0
SectionEnd

Section "PathEnvironment" SEC_PATH
  ; Add to system PATH
  ReadEnvStr $0 "PATH"
  StrCmp $0 "" 0 +2
  StrCpy $0 "$INSTDIR"
  goto +2
  StrCpy $0 "$0;$INSTDIR"
  System::Call 'kernel32::SetEnvironmentVariable(t "PATH", t "$0")'
  ; Notify system of environment change
  SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
SectionEnd

Section "Firewall" SEC_FIREWALL
  ; Add firewall rule for core API server
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="ARISE Core API" dir=in action=allow protocol=TCP localport=8000 profile=private'
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="ARISE Frontend" dir=in action=allow protocol=TCP localport=5173 profile=private'
SectionEnd

Section "AutoStart" SEC_AUTOSTART
  ; Add to Windows startup (optional, user can enable in settings)
  ; WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "ARISE" '"$INSTDIR\arise-tauri.exe" --minimized'
SectionEnd

; Uninstaller
Section "Uninstall"
  ; Remove firewall rules
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="ARISE Core API"'
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="ARISE Frontend"'

  ; Remove start menu
  RMDir /r "$SMPROGRAMS\ARISE"

  ; Remove desktop shortcut
  Delete "$DESKTOP\ARISE.lnk"

  ; Remove installation directory
  RMDir /r "$INSTDIR"

  ; Remove registry entries
  DeleteRegKey HKLM "${PRODUCT_DIR_REGKEY}"
  DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"

  ; Remove from PATH (best effort)
  ReadEnvStr $0 "PATH"
  StrReplace $0 "$0" "$INSTDIR;" ""
  StrReplace $0 "$0" ";$INSTDIR" ""
  StrReplace $0 "$0" "$INSTDIR" ""
  System::Call 'kernel32::SetEnvironmentVariable(t "PATH", t "$0")'
  SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
SectionEnd

; Functions
Function .onInit
  ; Check for admin rights
  UserInfo::GetAccountType
  Pop $0
  StrCmp $0 "Admin" 0 +2
  MessageBox MB_ICONSTOP "Administrator privileges required to install ARISE." IDOK
  Quit
FunctionEnd

Function .onInstSuccess
  ; Show success message
  MessageBox MB_ICONINFORMATION "ARISE has been successfully installed!$n$nYou can launch it from the Start Menu or Desktop."
FunctionEnd

; Custom pages
; !insertmacro MUI_PAGE_CUSTOM CustomPageCreate CustomPageLeave
; Function CustomPageCreate
; FunctionEnd
; Function CustomPageLeave
; FunctionEnd