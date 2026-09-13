"""Login autostart via the standard XDG autostart mechanism.

This is deliberately opt-in (flipped from a switch in the GUI, never
applied on its own) and deliberately never touches the compositor's own
config file — writing a niri/Hyprland/Sway config's exec line yourself is
exactly the manual step Waltz is meant to replace, but doing it by editing
someone else's config file unasked is a worse trade than a login switch.
~/.config/autostart/*.desktop is picked up by most session managers
(GNOME, KDE, and, on systemd-based distros, xdg-desktop-autostart.service)
regardless of which Wayland compositor is running.
"""

import os
from pathlib import Path

APP_ID = "com.waltz.Waltz"


def _autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = Path(base) / "autostart"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _desktop_file() -> Path:
    return _autostart_dir() / f"{APP_ID}.desktop"


def _bin_path() -> Path:
    # waltz/autostart.py -> <project root>/bin/waltz
    return Path(__file__).resolve().parent.parent / "bin" / "waltz"


def is_enabled() -> bool:
    return _desktop_file().exists()


def enable() -> None:
    exec_path = _bin_path()
    contents = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Waltz\n"
        "Comment=Video wallpaper engine\n"
        f"Exec={exec_path}\n"
        f"Path={exec_path.parent.parent}\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=false\n"
    )
    _desktop_file().write_text(contents)


def disable() -> None:
    try:
        _desktop_file().unlink()
    except FileNotFoundError:
        pass
