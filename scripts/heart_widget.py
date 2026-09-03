"""Small always-on-top heart button, pinned to the top-right of the screen.

Click it to save the *current* wallpaper (whatever generate_art.py most
recently rendered) into a dedicated Pictures folder -- separate from the
automatic data/art/ archive, which keeps everything regardless. This
folder only holds what you deliberately hearted. Click again to un-heart
(removes it from that folder).

Runs continuously in the background. Auto-start at logon is opt-in --
run scripts/register_heart_widget_task.ps1 yourself to set that up
(logon-triggered tasks are a form of persistent auto-start, so that's a
decision you make explicitly, not something this script does on its
own); until then, launch it manually with `pythonw scripts/heart_widget.py`.
Rechecks which render is "current" every few minutes, so it stays
correct across the daily 9am refresh without needing a restart.
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
REFRESH_MS = 5 * 60 * 1000  # recheck the current render every 5 minutes
# Deliberately matches generate_art.py's BACKGROUND -- true window
# transparency (-transparentcolor) breaks on anti-aliased/color-emoji
# glyphs (any single chroma key ends up matching some of the glyph's own
# blended edge pixels, producing a hatched artifact), so instead this
# just blends in by being the same solid color as the wallpaper's own
# background. Works especially well in the top-right corner specifically
# because that's also the last area the mosaic's left-to-right fill
# order ever reaches.
BACKGROUND = (0, 0, 0)

# Plain Unicode symbols (not modern color emoji -- those either aren't
# supported by the installed font or render as fixed-color glyphs that
# ignore fg=, depending on codepoint and Windows version). These are old,
# universally supported, and render as simple colorable outline/fill shapes.
HEART_EMPTY = "♡"  # white heart suit (outline)
HEART_FULL = "♥"   # black heart suit (solid fill)


def log(message: str) -> None:
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


def already_running() -> bool:
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
    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_path = None

        bg_hex = "#%02x%02x%02x" % BACKGROUND
        root.overrideredirect(True)
        root.attributes("-topmost", True)
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
        self.label.bind("<Button-3>", lambda e: root.destroy())  # right-click to quit

        self.refresh()

    def refresh(self):
        self.current_path = current_render_path()
        self.update_glyph()
        self.root.after(REFRESH_MS, self.refresh)

    def is_favorited(self) -> bool:
        if not self.current_path:
            return False
        return (FAVORITES_DIR / self.current_path.name).exists()

    def update_glyph(self):
        if self.is_favorited():
            self.label.config(text=HEART_FULL, fg="#ff4d5e")
        else:
            self.label.config(text=HEART_EMPTY, fg="white")

    def on_click(self, _event):
        self.current_path = current_render_path()
        if not self.current_path:
            return
        try:
            FAVORITES_DIR.mkdir(parents=True, exist_ok=True)
            dest = FAVORITES_DIR / self.current_path.name
            if dest.exists():
                dest.unlink()
                log(f"un-hearted {self.current_path.name}")
            else:
                shutil.copy2(self.current_path, dest)
                log(f"hearted {self.current_path.name} -> {dest}")
        except OSError as e:
            log(f"heart toggle failed for {self.current_path}: {e}")
        self.update_glyph()


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
