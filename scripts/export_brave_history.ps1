# Copies Brave's History SQLite DB into the project's data folder.
# Safe to run while Brave is open -- copies the file rather than opening
# it directly, which sidesteps Chromium's SQLite locking.

$braveHistory = "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data\Default\History"
$destDir = Join-Path $PSScriptRoot "..\data\brave_history"
$destFile = Join-Path $destDir "History.sqlite"

if (-not (Test-Path $braveHistory)) {
    Write-Error "Brave History file not found at $braveHistory"
    exit 1
}

New-Item -ItemType Directory -Force -Path $destDir | Out-Null
Copy-Item -Path $braveHistory -Destination $destFile -Force

# Copy the WAL file too, if present, so the copy reflects the latest
# unflushed visits rather than only what's been checkpointed to History.
$walFile = "$braveHistory-wal"
if (Test-Path $walFile) {
    Copy-Item -Path $walFile -Destination "$destFile-wal" -Force
}

Write-Output "Exported Brave history to $destFile at $(Get-Date)"
