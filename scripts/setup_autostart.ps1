# Registers both background helpers (heart widget, resume watchdog) to
# auto-start at logon via the Windows Startup folder.
#
# Run this yourself (not automated) -- auto-start at logon is a form of
# persistent auto-start, and setting it up is a decision that should be
# made explicitly by you, not silently by a script.
#
# Uses the Startup folder rather than a Scheduled Task: Register-ScheduledTask
# -AtLogOn returns "Access is denied" in this environment -- confirmed even
# run directly from an interactive session, not just from automation -- while
# plain daily-trigger tasks (the ones the main pipeline uses) register fine.
# The Startup folder is a different, equally standard Windows mechanism
# that isn't gated by whatever's blocking that specific Task Scheduler
# trigger type. Since a Startup-folder shortcut launches immediately at
# logon with no built-in delay option, this generates small VBScript
# launchers that sleep 45 seconds before actually starting each program,
# so neither ever adds to the startup rush.
#
# Until you run this, launch these manually whenever you want them:
#   pythonw scripts\heart_widget.py
#   pythonw scripts\resume_watchdog.py

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pythonw = (Get-Command pythonw).Source
$dataDir = Join-Path $root "data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$startupFolder = [Environment]::GetFolderPath("Startup")
$delayMs = 45000

function Register-StartupLauncher {
    param(
        [string]$Name,
        [string]$TargetScript
    )

    $vbsPath = Join-Path $dataDir "$Name-launcher.vbs"
    $vbsLines = @(
        "WScript.Sleep $delayMs",
        "Set objShell = CreateObject(""WScript.Shell"")",
        "objShell.Run """"""$pythonw"""" """"$TargetScript"""""", 0, False"
    )
    Set-Content -Path $vbsPath -Value $vbsLines -Encoding ASCII

    $shortcutPath = Join-Path $startupFolder "$Name.lnk"
    $WshShell = New-Object -ComObject WScript.Shell
    $shortcut = $WshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbsPath`""
    $shortcut.WorkingDirectory = $root
    $shortcut.Save()

    if (-not (Test-Path $shortcutPath)) {
        Write-Error "Failed to create the Startup shortcut at $shortcutPath"
        exit 1
    }
    Write-Output "Registered: $shortcutPath"
}

Register-StartupLauncher -Name "GenerativeArtSystem-HeartWidget" -TargetScript (Join-Path $root "scripts\heart_widget.py")
Register-StartupLauncher -Name "GenerativeArtSystem-ResumeWatchdog" -TargetScript (Join-Path $root "scripts\resume_watchdog.py")

Write-Output "Both will start automatically ~45s after every logon."
Write-Output "To start them right now without logging out:"
Write-Output "  pythonw `"$(Join-Path $root 'scripts\heart_widget.py')`""
Write-Output "  pythonw `"$(Join-Path $root 'scripts\resume_watchdog.py')`""
