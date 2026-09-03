# Registers the heart-widget to auto-start at logon via the Windows Startup
# folder, with a built-in delay so it never competes with the burst of
# other apps launching right at logon.
#
# Run this yourself (not automated) -- auto-start at logon is a form of
# persistent auto-start, and setting it up is a decision that should be
# made explicitly by you, not silently by a script.
#
# Uses the Startup folder rather than a Scheduled Task: Register-ScheduledTask
# -AtLogOn returns "Access is denied" in this environment -- confirmed even
# run directly from an interactive session, not just from automation -- so
# this uses a different, equally standard Windows autostart mechanism that
# isn't gated by that restriction.
#
# Until you run this, launch the widget manually whenever you want it:
#   pythonw scripts\heart_widget.py

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pythonw = (Get-Command pythonw).Source
$targetScript = Join-Path $root "scripts\heart_widget.py"

$dataDir = Join-Path $root "data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$vbsPath = Join-Path $dataDir "heart_widget_startup_launcher.vbs"

$delayMs = 45000
$vbsLines = @(
    "WScript.Sleep $delayMs",
    "Set objShell = CreateObject(""WScript.Shell"")",
    "objShell.Run """"""$pythonw"""" """"$targetScript"""""", 0, False"
)
Set-Content -Path $vbsPath -Value $vbsLines -Encoding ASCII

$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "GenerativeArtSystem-HeartWidget.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$vbsPath`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Top-right heart button to favorite the current generative art wallpaper"
$shortcut.Save()

if (-not (Test-Path $shortcutPath)) {
    Write-Error "Failed to create the Startup shortcut at $shortcutPath"
    exit 1
}

Write-Output "Registered via Startup folder shortcut: $shortcutPath"
Write-Output "The heart widget will start automatically ~45s after every logon."
Write-Output "To start it right now without logging out: pythonw `"$targetScript`""
