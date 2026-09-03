"""Small heart button pinned to the top-right corner of the desktop.

Click it to save the *current* wallpaper (whatever generate_art.py most
recently rendered) into a dedicated Pictures folder -- separate from the
automatic data/art/ archive, which keeps everything regardless. This
folder only holds what you deliberately hearted.

Once you've hearted a render, the button hides itself for the rest of
that day -- it only reappears once a new render (tomorrow's) becomes
current. This is a once-a-day action, not a toggle.

The window is reparented into Explorer's WorkerW window (the same
technique interactive-wallpaper tools use) so it lives on the desktop
layer itself: it sits behind every normal application window and only
shows through when the desktop is actually visible, rather than
floating on top of whatever you're using. Falls back to a plain
always-on-top window if that reparenting fails (e.g. a future Windows
update changes Explorer's internal window structure).

Runs continuously in the background. Auto-start at logon is opt-in --
run scripts/register_heart_widget_task.ps1 yourself to set that up
(logon-triggered tasks are a form of persistent auto-start, so that's a
decision you make explicitly, not something this script does on its
own); until then, launch it manually with pythonw scripts/heart_widget.py.
Rechecks which render is "current" every minute, so it stays correct
across the daily 9am refresh without needing a restart.
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
REFRESH_MS = 60 * 1000
CONFIRM_MS = 700
BACKGROUND = (0, 0, 0)

HEART_EMPTY = "♡"
HEART_FULL = "♥"


def log(message):
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


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


def attach_to_desktop(hwnd):
    """Reparents hwnd into Explorer's WorkerW window, the same technique
    interactive-wallpaper tools (Wallpaper Engine, Lively, etc.) use to
    live on the desktop layer -- behind every normal app window, visible
    only when the desktop itself is. Returns False (caller should fall
    back to a plain topmost window) if Explorer's window structure
    doesn't match what's expected."""
    user32 = ctypes.windll.user32

    progman = user32.FindWindowW("Progman", None)
    if not progman:
        return False

    result = wintypes.DWORD()
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0x0, 1000, ctypes.byref(result))

    workerw = wintypes.HWND(0)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_windows_proc(top_hwnd, _lparam):
        nonlocal workerw
        shell_view = user32.FindWindowExW(top_hwnd, 0, "SHELLDLL_DefView", None)
        if shell_view:
            candidate = user32.FindWindowExW(0, top_hwnd, "WorkerW", None)
            if candidate:
                workerw = wintypes.HWND(candidate)
        return True

    user32.EnumWindows(enum_windows_proc, 0)

    if not workerw.value:
        return False

    user32.SetParent(hwnd, workerw)
    return True


class HeartWidget:
    def __init__(self, root):
        self.root = root
        self.current_path = None
        self.hidden_for_today = False

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

        root.update_idletasks()
        if not attach_to_desktop(root.winfo_id()):
            log("desktop attach failed, falling back to always-on-top")
            root.attributes("-topmost", True)

        self.refresh()

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
