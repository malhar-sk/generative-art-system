"""Small heart button pinned to the top-right corner of the desktop.

Click it to save the *current* wallpaper (whatever generate_art.py most
recently rendered) into a dedicated Pictures folder -- separate from the
automatic data/art/ archive, which keeps everything regardless. This
folder only holds what you deliberately hearted.

Once you've hearted a render, the button hides itself for the rest of
that day -- it only reappears once a new render (tomorrow's) becomes
current. This is a once-a-day action, not a toggle.

Stays out of the way of other apps: it's an overrideredirect window
(so it never appears in the taskbar or Alt-Tab -- there's no way to
bring it forward through normal window switching) and, instead of
-topmost, it periodically re-lowers itself to the bottom of the
window stack. Any app you open or click naturally ends up in front of
it within a couple seconds. This was chosen over reparenting into
Explorer's WorkerW window (the technique interactive-wallpaper tools
use for true desktop-layer attachment) after testing showed WorkerW
discovery is unreliable across Windows sessions -- lower()/SetWindowPos
is a plain, fully-supported window-stacking operation with no
dependency on Explorer's undocumented internals, so it works the same
everywhere.

Low resource use by design, not as a separate toggleable mode --
there's no real tradeoff to always running this way, so it's just how
the widget behaves:
  - The re-lower timer only runs while the button is actually visible.
    Once you heart a render (or the process restarts after already
    having hearted it), the button withdraws and that timer stops
    entirely -- for most of the day (typically until the next 9am
    refresh) nothing is ticking at all except the slow "did a new
    render appear" check.
  - Both timers are intentionally relaxed (2s / 5min) -- there's no
    reason for either to be tighter than that for a button reacting to
    daily-cadence events.
  - The process sets its own priority to IDLE at startup, so it never
    competes with foreground apps for CPU time.
Measured on a live instance: ~0% CPU (below measurement precision over
a 10s sample) and ~28MB working set even in the "visible" state before
these changes; the point of the changes above is reducing *wake
frequency* (which affects laptop idle power beyond what a CPU% number
captures), not chasing an already-negligible CPU number down further.

Runs continuously in the background. Auto-start at logon is opt-in --
run scripts/setup_autostart.ps1 yourself to set that up
(logon-triggered tasks are a form of persistent auto-start, so that's a
decision you make explicitly, not something this script does on its
own); until then, launch it manually with pythonw scripts/heart_widget.py.
The registration script adds a delay after logon so this never
competes with the startup rush of other apps -- see its own comments.
"""
import ctypes
import os
import shutil
import sys
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_DIR = ROOT / "data" / "art"
LOCK_PATH = ROOT / "data" / "heart_widget.lock"
LOG_PATH = ROOT / "data" / "heart_widget.log"
FAVORITES_DIR = Path.home() / "Pictures" / "GenerativeArtFavorites"

SIZE = 56
MARGIN = 16
REFRESH_MS = 5 * 60 * 1000  # recheck which render is current, once every 5 minutes
LOWER_MS = 2000             # re-assert bottom-of-stack, only while visible
CONFIRM_MS = 700
BACKGROUND = (0, 0, 0)

HEART_EMPTY = "♡"
HEART_FULL = "♥"

IDLE_PRIORITY_CLASS = 0x00000040


def log(message):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


def lower_own_priority():
    """Runs at IDLE priority so this never competes with foreground apps
    for CPU scheduling, regardless of how infrequently it actually wakes.
    GetCurrentProcess's pseudo-handle needs explicit HANDLE-width types --
    ctypes defaults to 32-bit int, which truncates it and makes
    SetPriorityClass fail with ERROR_INVALID_HANDLE on 64-bit Windows."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.SetPriorityClass.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if not kernel32.SetPriorityClass(handle, IDLE_PRIORITY_CLASS):
            log(f"SetPriorityClass failed, GetLastError={ctypes.windll.kernel32.GetLastError()}")
    except OSError as e:
        log(f"lower_own_priority failed: {e}")


def already_running():
    if not LOCK_PATH.exists():
        return False
    try:
        pid = int(LOCK_PATH.read_text().strip())
    except (ValueError, OSError):
        return False
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def current_render_path():
    pngs = sorted(ART_DIR.glob("*.png"))
    return pngs[-1] if pngs else None


class HeartWidget:
    def __init__(self, root):
        self.root = root
        self.current_path = None
        self.hidden_for_today = False
        self.lowering_active = False

        bg_hex = "#%02x%02x%02x" % BACKGROUND
        root.overrideredirect(True)
        root.configure(bg=bg_hex)

        screen_w = root.winfo_screenwidth()
        x = screen_w - SIZE - MARGIN
        y = MARGIN
        root.geometry(f"{SIZE}x{SIZE}+{x}+{y}")

        self.label = tk.Label(
            root, text=HEART_EMPTY, font=("Segoe UI Symbol", 30),
            fg="white", bg=bg_hex, cursor="hand2",
        )
        self.label.pack(expand=True, fill="both")
        self.label.bind("<Button-1>", self.on_click)
        self.label.bind("<Button-3>", lambda e: root.destroy())

        self.refresh()

    def keep_lowered(self):
        if self.hidden_for_today:
            self.lowering_active = False
            return
        try:
            self.root.lower()
        except tk.TclError:
            pass
        self.root.after(LOWER_MS, self.keep_lowered)

    def refresh(self):
        new_path = current_render_path()
        if new_path != self.current_path:
            self.current_path = new_path
            self.hidden_for_today = False

        if self.hidden_for_today or self.is_favorited():
            self.hidden_for_today = True
            self.root.withdraw()
        else:
            self.update_glyph()
            self.root.deiconify()
            self.root.lower()
            if not self.lowering_active:
                self.lowering_active = True
                self.keep_lowered()

        self.root.after(REFRESH_MS, self.refresh)

    def is_favorited(self):
        if not self.current_path:
            return False
        return (FAVORITES_DIR / self.current_path.name).exists()

    def update_glyph(self):
        self.label.config(text=HEART_FULL if self.is_favorited() else HEART_EMPTY)

    def on_click(self, _event):
        self.current_path = current_render_path()
        if not self.current_path or self.is_favorited():
            return
        try:
            FAVORITES_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.current_path, FAVORITES_DIR / self.current_path.name)
            log(f"hearted {self.current_path.name}")
        except OSError as e:
            log(f"heart failed for {self.current_path}: {e}")
            return
        self.label.config(text=HEART_FULL, fg="#ff4d5e")
        self.hidden_for_today = True
        self.root.after(CONFIRM_MS, self.root.withdraw)


def main():
    if already_running():
        sys.exit(0)
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(str(os.getpid()))
    lower_own_priority()

    try:
        root = tk.Tk()
        HeartWidget(root)
        root.mainloop()
    except Exception as e:
        log(f"crashed: {e}")
    finally:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass


if __name__ == "__main__":
    main()
