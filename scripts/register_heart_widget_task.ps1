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
# Delayed start so this never competes with the burst of other apps
# launching right at logon -- by the time it starts, the boot storm has
# settled and it won't add to that contention.
$trigger.Delay = "PT45S"
Register-ScheduledTask -TaskName "GenerativeArtSystem-HeartWidget" -Action $action -Trigger $trigger -Description "Top-right heart button to favorite the current generative art wallpaper" -Force

Write-Output "Registered. The heart widget will start automatically ~45s after logon (delayed on purpose to avoid the startup rush)."
Write-Output "To start it right now without logging out: pythonw `"$script`""
