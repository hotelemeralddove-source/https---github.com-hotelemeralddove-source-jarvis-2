; Arc Desk - Inno Setup script (Inno Setup 6, free).
;
; ONE file to double-click. It carries everything: the app, its own Python (frozen into
; ArcDesk.exe by PyInstaller), ffmpeg + ffprobe, and - if ticked - Node for the MCP tool
; servers. The person installing never downloads anything, never edits PATH, never opens
; a terminal. Finished screen says: "Arc Desk installed successfully."
;
; Choices, each of them about not surprising the user:
;   * PrivilegesRequired=lowest  -> per-user install, NO admin prompt, ever.
;   * No service, no scheduled task, no shell extension, no PATH edit. Bundled tools are
;     added to the *process* PATH by the app itself (paths.activate_runtime()).
;   * The "start with Windows" entry is owned by the APP (Settings / first-run), not by
;     the installer, so the two can never disagree. This script only removes a leftover.
;   * Uninstall ASKS before deleting the user's vault (notes, projects, journal).
;   * Compression=lzma2/ultra64 + SolidCompression: the ffmpeg DLLs shrink to ~29% of
;     their size (measured in tools/sizecheck.py), which is what keeps this a ~85 MB
;     download instead of a 250 MB one.

#define AppName "Arc Desk"
#define AppVersion "1.0"
#define AppExe "ArcDesk.exe"
#define HaveFFmpeg FileExists(AddBackslash(SourcePath) + "..\runtime\ffmpeg\ffmpeg.exe")
#define HaveNode FileExists(AddBackslash(SourcePath) + "..\runtime\node\node.exe")

[Setup]
AppId={{7C1B9F42-3A2E-4B7A-9E0C-ARC0DE5C0DE1}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Arc Desk
DefaultDirName={localappdata}\Programs\ArcDesk
DefaultGroupName=Arc Desk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ArcDeskSetup
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\arc_icon.ico
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; Shown before anything is written: what this program refuses to do.
InfoBeforeFile=..\docs\REFUSED.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; The last thing the user reads. It says "installed" because it IS installed - and it
; tells them the one thing they need to know next.
FinishedLabel=Arc Desk is installed successfully.%n%nSay "hey jarvis" (or open it from the Start Menu) to begin. Your work is saved in the Vault - ask it "where do my files save?"  anytime.

[Types]
; The first type is the one Inno pre-selects. Disk space is a real constraint on a
; laptop, and the optional pieces are genuinely large: ffmpeg is 195 MB installed and the
; Node runtime 85 MB. So the default installs Arc Desk and nothing else, and one click on
; "full" brings the rest. Everything can be added later by running this installer again.
Name: "compact"; Description: "Arc Desk only - smallest ({#AppName}, no extras)"
Name: "full"; Description: "Arc Desk + media engine (ffmpeg) + Node runtime - about 280 MB more"
Name: "custom"; Description: "Let me choose"; Flags: iscustom

[Components]
Name: "core"; Description: "Arc Desk application (required)"; Types: compact full custom; Flags: fixed
#if HaveFFmpeg
Name: "media"; Description: "Media engine - ffmpeg + ffprobe (video, audio, waveforms, reels): 195 MB installed, 58 MB in this installer"; Types: full custom
#endif
#if HaveNode
Name: "mcp"; Description: "Node runtime - only for MCP tool servers over npx: 85 MB installed, 30 MB in this installer"; Types: full custom
#endif

[Tasks]
; The two ways to open it, exactly as the app asks on first run. Both are pre-ticked
; because "already running and listening" is what makes "hey jarvis" work; untick
; either one here, or change your mind later in Settings -> Voice.
Name: "desktopicon"; Description: "Put a shortcut on the Desktop (double-click to open)"; GroupDescription: "How should it open?:"; Flags: checkedonce
Name: "startup"; Description: "Start with Windows, silently, so ""hey jarvis"" always works (microphone stays off until you enable the wake word)"; GroupDescription: "How should it open?:"; Flags: checkedonce

[Files]
Source: "..\dist\ArcDesk\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: core
#if HaveFFmpeg
Source: "..\runtime\ffmpeg\*"; DestDir: "{app}\runtime\ffmpeg"; Flags: ignoreversion; Components: media
#endif
#if HaveNode
Source: "..\runtime\node\*"; DestDir: "{app}\runtime\node"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: mcp
#endif

[Icons]
; --show on purpose. The app may be configured to start hidden (that is what the
; Run-key entry below does, with --shadow, every boot). A person double-clicking the
; icon is not a boot: they are asking to see it. Without this parameter the shortcut
; started a process with no window and no card, which is the report "it installs but
; does not work".
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--show"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: "--show"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--show"; Description: "Open Arc Desk now"; Flags: nowait postinstall skipifsilent
; The speech models are the one thing a fresh machine cannot do without: 40 MB for
; Vosk (commands) and 30 MB for the speaker model (voice lock). Downloading them here,
; visibly, is why "hey jarvis" works on the first try instead of failing mysteriously.
Filename: "{app}\{#AppExe}"; Parameters: "--download-voice-model --shadow"; \
    Description: "Download the speech models now (70 MB) so ""hey jarvis"" works"; \
    Flags: postinstall runhidden skipifsilent unchecked

[Registry]
; Only when the user ticked "start with Windows". HKCU, per-user, one value - exactly
; what the app writes itself, so uninstall and the app agree.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "ArcDesk"; ValueData: """{app}\{#AppExe}"" --shadow"; \
    Flags: uninsdeletevalue; Tasks: startup

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
Type: filesandordirs; Name: "{app}\runtime"

[Code]
function InitializeUninstall(): Boolean;
var
  Answer: Integer;
begin
  Result := True;
  { The vault holds the user's own notes, project files and progress. Deleting that by
    default would be the worst thing this installer could do, so it is a question with
    NO as the default answer. }
  Answer := MsgBox('Also delete your Arc Desk VAULT?' + #13#10 +
                   'That is your own work: notes, project files and progress logs. ' +
                   'Choose No to keep it (it lives in %APPDATA%\ArcDesk\vault).',
                   mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
  if Answer = IDYES then
  begin
    DelTree(ExpandConstant('{userappdata}\ArcDesk\vault'), True, True, True);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Never leave a dangling startup entry behind. }
    RegDeleteValue(HKEY_CURRENT_USER,
      'Software\Microsoft\Windows\CurrentVersion\Run', 'ArcDesk');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    { Tell the user, in the log, exactly what landed - the same thing the app will report
      in Settings - so "installed" is never a guess. }
    Log('Arc Desk ' + '{#AppVersion}' + ' installed to ' + ExpandConstant('{app}'));
    if FileExists(ExpandConstant('{app}\runtime\ffmpeg\ffmpeg.exe')) then
      Log('media engine: bundled ffmpeg')
    else
      Log('media engine: not bundled (media tools will report it as missing, honestly)');
    if FileExists(ExpandConstant('{app}\runtime\node\node.exe')) then
      Log('node runtime: bundled');
  end;
end;
