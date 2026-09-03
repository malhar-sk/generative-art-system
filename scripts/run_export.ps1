# Full daily pipeline: export Brave history -> parse -> categorize -> render art -> set wallpaper.
# This is the script Task Scheduler calls.

$root = Split-Path -Parent $PSScriptRoot
& "$root\scripts\export_brave_history.ps1"
python "$root\scripts\parse_brave_history.py"
python "$root\scripts\categorize.py"
python "$root\scripts\generate_art.py"
& "$root\scripts\set_wallpaper.ps1"
