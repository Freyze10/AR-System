; MyAppName: shown in the installer and shortcuts.
; MyAppId: must be unique per program. If two programs share an ID, installing one will uninstall the other.
; MyAppExe: the exe name
; MySourceDir: the folder containing that exe and its _internal.

#define MyAppName "MBPI AR"
#define MyAppVersion "1.0.0"
#define MyAppId "MBPI_AR_System"
#define MyAppExe "main.exe"
#define MySourceDir "output\main"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UsePreviousAppDir=yes
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExe}
OutputDir=installer_output
OutputBaseFilename={#MyAppName}_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes

; Wipes the old version's files before copying the new ones (does nothing on a fresh install)
[InstallDelete]
Type: filesandordirs; Name: "{app}\*"

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1';

var
  IsUpdateInstall: Boolean;

function GetUninstallString: String;
var
  S: String;
begin
  Result := '';
  if RegQueryStringValue(HKLM, UninstKey, 'UninstallString', S) or
     RegQueryStringValue(HKCU, UninstKey, 'UninstallString', S) then
    Result := RemoveQuotes(S);
end;

procedure InitializeWizard;
begin
  IsUpdateInstall := GetUninstallString <> '';

  if IsUpdateInstall then
  begin
    WizardForm.Caption := '{#MyAppName} Update';
    WizardForm.WelcomeLabel1.Caption := 'Update {#MyAppName}';
    WizardForm.WelcomeLabel2.Caption :=
      'An existing installation was found.' + #13#10 +
      'Setup will replace it with version {#MyAppVersion}.';
  end
  else
  begin
    WizardForm.Caption := '{#MyAppName} Setup';
    WizardForm.WelcomeLabel1.Caption := 'Welcome to {#MyAppName}';
    WizardForm.WelcomeLabel2.Caption :=
      'Setup will install {#MyAppName} version {#MyAppVersion} on your computer.';
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then
  begin
    if IsUpdateInstall then
      WizardForm.NextButton.Caption := 'Update'
    else
      WizardForm.NextButton.Caption := 'Install';
  end;

  if CurPageID = wpFinished then
  begin
    if IsUpdateInstall then
      WizardForm.FinishedHeadingLabel.Caption := 'Update Complete'
    else
      WizardForm.FinishedHeadingLabel.Caption := 'Installation Complete';
  end;
end;

{ Closes the app if it is running, so its files aren't locked }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM {#MyAppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;