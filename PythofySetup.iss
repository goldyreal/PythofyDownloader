; ============================================================
;  Pythofy Downloader — Inno Setup Script
; ============================================================

#define AppName    "Pythofy Downloader"
#define AppExe     "Pythofy.exe"
#define AppVersion "1.0.0"
#define Publisher  "Pythofy"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
AppCopyright=© 2025 {#Publisher}

; Cartella di installazione
DefaultDirName={autopf}\Pythofy
DefaultGroupName={#AppName}

; Nome del file di output
OutputBaseFilename=PythofySetup
OutputDir=.

; Compressione
Compression=lzma2
SolidCompression=yes

; Richiede i permessi di amministratore
PrivilegesRequired=admin

; Metadati del file .exe
VersionInfoVersion=1.0.0
VersionInfoDescription=Pythofy Downloader Installer

; Lingua italiana
WizardStyle=modern

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

; ============================================================
[Files]
; Eseguibile principale
Source: "dist\Pythofy.exe"; DestDir: "{app}"; Flags: ignoreversion

; Strumenti (yt-dlp e ffmpeg)
Source: "dist\pythofy_tools\yt-dlp.exe"; DestDir: "{app}\pythofy_tools"; Flags: ignoreversion
Source: "dist\pythofy_tools\ffmpeg.exe"; DestDir: "{app}\pythofy_tools"; Flags: ignoreversion

; ============================================================
[Icons]
; Shortcut sul Desktop
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"

; Shortcut nel menu Start
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Disinstalla {#AppName}"; Filename: "{uninstallexe}"

; ============================================================
[Registry]
; Aggiunge pythofy_tools al PATH di sistema
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
  ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}\pythofy_tools"; \
  Check: NeedsAddPath(ExpandConstant('{app}\pythofy_tools'))

; ============================================================
[Code]
// Controlla se il percorso è già nel PATH prima di aggiungerlo
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(
    HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

// Rimuove pythofy_tools dal PATH durante la disinstallazione
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OldPath, NewPath, ToRemove: string;
  P: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    ToRemove := ExpandConstant('{app}\pythofy_tools');
    if RegQueryStringValue(
      HKEY_LOCAL_MACHINE,
      'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
      'Path', OldPath)
    then begin
      NewPath := OldPath;
      // Rimuove con il ; davanti
      P := Pos(';' + ToRemove, NewPath);
      if P > 0 then
        Delete(NewPath, P, Length(';' + ToRemove));
      // Rimuove senza ; davanti (caso bordo)
      P := Pos(ToRemove + ';', NewPath);
      if P > 0 then
        Delete(NewPath, P, Length(ToRemove + ';'));
      if NewPath <> OldPath then
        RegWriteStringValue(
          HKEY_LOCAL_MACHINE,
          'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
          'Path', NewPath);
    end;
  end;
end;
