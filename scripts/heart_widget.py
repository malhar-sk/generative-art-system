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
it within about a second. This was chosen over reparenting into
Explorer's WorkerW window (the technique interactive-wallpaper tools
use for true desktop-layer attachment) after testing showed WorkerW
discovery is unreliable across Windows sessions -- lower()/SetWindowPos
is a plain, fully-supported window-stacking operation with no
dependency on Explorer's undocumented internals, so it works the same
everywhere.

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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART_DIR = ROOT / "data" / "art"
LOCK_PATH = ROOT / "data" / "heart_widget.lock"
LOG_PATH = ROOT / "data" / "heart_widget.log"
FAVORITES_DIR = Path.home() / "Pictures" / "GenerativeArtFavorites"

SIZE = 56
MARGIN = 16
REFRESH_MS = 60 * 1000     # recheck which render is current, once a minute
LOWER_MS = 1000            # re-assert bottom-of-stack, once a second
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

        self.refresh()
        self.keep_lowered()

    def keep_lowered(self):
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
