# Runs the full export pipeline: copy Brave's History DB, then parse it to CSV.
# This is the script Task Scheduler calls.

$root = Split-Path -Parent $PSScriptRoot
& "$root\scripts\export_brave_history.ps1"
python "$root\scripts\parse_brave_history.py"
