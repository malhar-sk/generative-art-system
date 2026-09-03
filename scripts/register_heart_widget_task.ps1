# Registers the heart-widget Scheduled Task to auto-start at logon.
#
# Run this yourself (not automated) -- logon-triggered tasks are a form of
# persistent auto-start, and registering them is a decision that should be
# made explicitly by you, not silently by a script.
#
# Until you run this, launch the widget manually whenever you want it:
#   pythonw scripts\heart_widget.py

$pythonw = (Get-Command pythonw).Source
$script = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\heart_widget.py"

$action = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "GenerativeArtSystem-HeartWidget" -Action $action -Trigger $trigger -Description "Top-right heart button to favorite the current generative art wallpaper" -Force

Write-Output "Registered. The heart widget will now start automatically at logon."
Write-Output "To start it right now without logging out: pythonw `"$script`""
