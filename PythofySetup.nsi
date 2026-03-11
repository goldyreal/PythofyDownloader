; ============================================================
;  Pythofy Downloader — Setup
; ============================================================

Unicode True
!include "MUI2.nsh"
!include "WinMessages.nsh"
!include "LogicLib.nsh"

!define APP_NAME    "Pythofy Downloader"
!define APP_EXE     "Pythofy.exe"
!define APP_VERSION "1.0.0"
!define PUBLISHER   "Pythofy"
!define UNINST_KEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\Pythofy"

Name            "${APP_NAME}"
OutFile         "PythofySetup.exe"
InstallDir      "$PROGRAMFILES64\Pythofy"
InstallDirRegKey HKLM "Software\Pythofy" "InstallDir"
RequestExecutionLevel admin
SetCompressor   zlib

; Metadati PE — riducono i falsi positivi AV
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName"     "${APP_NAME}"
VIAddVersionKey "ProductVersion"  "${APP_VERSION}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion"     "${APP_VERSION}"
VIAddVersionKey "LegalCopyright"  "© 2025 ${PUBLISHER}"

; ---- UI ----
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Italian"

; ============================================================
Section "Install"
    SetOutPath "$INSTDIR"
    File "dist\youtube_downloader_gui.exe"
    Rename "$INSTDIR\youtube_downloader_gui.exe" "$INSTDIR\${APP_EXE}"

    ; Copia yt-dlp e ffmpeg dal bundle — nessun download, nessun PowerShell
    SetOutPath "$INSTDIR\pythofy_tools"
    File "dist\pythofy_tools\yt-dlp.exe"
    File "dist\pythofy_tools\ffmpeg.exe"

    ; --- PATH ---
    EnVar::SetHKLM
    EnVar::AddValue "Path" "$INSTDIR\pythofy_tools"
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000

    ; --- Scorciatoie ---
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk"                "$INSTDIR\${APP_EXE}"
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Disinstalla.lnk" "$INSTDIR\Uninstall.exe"

    ; --- Chiave Add/Remove Programs ---
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayVersion"  "${APP_VERSION}"
    WriteRegStr   HKLM "${UNINST_KEY}" "Publisher"       "${PUBLISHER}"
    WriteRegStr   HKLM "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr   HKLM "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify"        1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair"        1

    WriteUninstaller "$INSTDIR\Uninstall.exe"

    MessageBox MB_OK "Installazione completata!"
SectionEnd

; ============================================================
Section "Uninstall"
    EnVar::SetHKLM
    EnVar::DeleteValue "Path" "$INSTDIR\pythofy_tools"
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000

    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR\pythofy_tools"
    RMDir "$INSTDIR"

    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    DeleteRegKey HKLM "${UNINST_KEY}"
    DeleteRegKey HKLM "Software\Pythofy"
SectionEnd
