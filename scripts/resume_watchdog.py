"""Detects the system resuming from sleep and recovers the desktop state.

After certain sleep/wake cycles, explorer.exe's desktop compositing (and
Rainmeter's own desktop attachment, if running) can end up in a stale
state where the actual Windows wallpaper stops being drawn -- another
app's skin/window ends up covering the screen instead, and the heart
widget can end up hidden behind it too, even though nothing in this
pipeline is actually broken (the wallpaper registry setting and the
widget process are both still correct the whole time). Restarting
explorer.exe fixes this by forcing everything to redraw -- confirmed
manually once; this automates that same fix.

Detects resume via a simple, robust wall-clock heuristic instead of
hooking raw Windows power-event messages (WM_POWERBROADCAST): if the
elapsed time between two checks is much longer than the check interval,
this process was suspended for a while, since our own thread can't run
at all during sleep -- this works regardless of which underlying clock
does or doesn't keep ticking during suspend, because it's our *own*
execution that stalls, not a hardware counter's behavior.

Runs continuously in the background, started at logon the same way as
heart_widget.py (see setup_autostart.ps1, which sets up both).
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = ROOT / "data" / "resume_watchdog.lock"
LOG_PATH = ROOT / "data" / "resume_watchdog.log"
HEART_LOCK_PATH = ROOT / "data" / "heart_widget.lock"
HEART_SCRIPT = ROOT / "scripts" / "heart_widget.py"
SET_WALLPAPER_SCRIPT = ROOT / "scripts" / "set_wallpaper.ps1"

CHECK_INTERVAL_S = 30
JUMP_THRESHOLD_S = 90
IDLE_PRIORITY_CLASS = 0x00000040


def log(message):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def lower_own_priority():
    try:
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        kernel32.SetPriorityClass(handle, IDLE_PRIORITY_CLASS)
    except OSError as e:
        log(f"lower_own_priority failed: {e}")


def _pid_alive(pid):
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def already_running():
    if not LOCK_PATH.exists():
        return False
    try:
        pid = int(LOCK_PATH.read_text().strip())
    except (ValueError, OSError):
        return False
    return _pid_alive(pid)


def heart_widget_alive():
    if not HEART_LOCK_PATH.exists():
        return False
    try:
        pid = int(HEART_LOCK_PATH.read_text().strip())
    except (ValueError, OSError):
        return False
    return _pid_alive(pid)


def find_pythonw():
    found = shutil.which("pythonw")
    if found:
        return found
    return sys.executable.replace("python.exe", "pythonw.exe")


def recover():
    log("resume detected -- recovering desktop state")

    try:
        subprocess.run(["taskkill", "/IM", "explorer.exe", "/F"], capture_output=True)
        time.sleep(1)
        subprocess.Popen(["explorer.exe"])
        log("restarted explorer.exe")
    except OSError as e:
        log(f"failed to restart explorer.exe: {e}")

    time.sleep(3)  # give explorer a moment to reinitialize the desktop

    try:
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(SET_WALLPAPER_SCRIPT)],
            capture_output=True,
        )
        log("reapplied wallpaper")
    except OSError as e:
        log(f"failed to reapply wallpaper: {e}")

    if not heart_widget_alive():
        try:
            subprocess.Popen([find_pythonw(), str(HEART_SCRIPT)])
            log("relaunched heart_widget.py")
        except OSError as e:
            log(f"failed to relaunch heart_widget.py: {e}")


def main():
    if already_running():
        sys.exit(0)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(os.getpid()))
    lower_own_priority()

    try:
        last_check = time.time()
        while True:
            time.sleep(CHECK_INTERVAL_S)
            now = time.time()
            elapsed = now - last_check
            if elapsed > JUMP_THRESHOLD_S:
                recover()
            last_check = now
    except Exception as e:
        log(f"crashed: {e}")
    finally:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    main()
