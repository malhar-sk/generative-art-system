# Sets the most recently rendered art PNG as the desktop wallpaper.

$root = Split-Path -Parent $PSScriptRoot
$artDir = Join-Path $root "data\art"

$latest = Get-ChildItem -Path $artDir -Filter "*.png" -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
if (-not $latest) {
    Write-Error "No rendered art found in $artDir. Run generate_art.py first."
    exit 1
}

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Wallpaper {
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern int SystemParametersInfo(int uAction, int uParam, string lpvParam, int fuWinIni);
}
"@

# Fill style so the square render fits cleanly regardless of monitor aspect ratio.
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name WallpaperStyle -Value 10
Set-ItemProperty -Path "HKCU:\Control Panel\Desktop" -Name TileWallpaper -Value 0

$SPI_SETDESKWALLPAPER = 20
$SPIF_UPDATEINIFILE = 0x01
$SPIF_SENDWININICHANGE = 0x02

[Wallpaper]::SystemParametersInfo($SPI_SETDESKWALLPAPER, 0, $latest.FullName, $SPIF_UPDATEINIFILE -bor $SPIF_SENDWININICHANGE) | Out-Null

Write-Output "Set wallpaper to $($latest.FullName)"
