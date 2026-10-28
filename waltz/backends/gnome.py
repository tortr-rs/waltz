"""GNOME Wayland backend: drives the Hanabi GNOME Shell extension
(github.com/jeffshee/gnome-ext-hanabi), which plays video inside Mutter's own
scene. Waltz can't install a Shell extension for you, so without Hanabi this
backend says what to install and stops there.

Hanabi shows one video on every monitor, so Singular and Clone both set
that one video. It already pauses on fullscreen and on battery by itself.
"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ..monitors import Monitor
from .base import BackendUnavailable, WallpaperBackend

UUID = "hanabi-extension@jeffshee.github.io"
SCHEMA = "io.github.jeffshee.hanabi-extension"
DIRS = [
    Path.home() / ".local/share/gnome-shell/extensions" / UUID,
    Path("/usr/share/gnome-shell/extensions") / UUID,
]

NEED_HANABI = (
    "On GNOME, Waltz plays videos through the Hanabi extension. Install it from "
    "extensions.gnome.org (search \"Hanabi\") or github.com/jeffshee/gnome-ext-hanabi, "
    "log out and back in, then try again."
)


def _ext_dir() -> Optional[Path]:
    return next((d for d in DIRS if (d / "metadata.json").exists()), None)


class GnomeBackend(WallpaperBackend):
    name = "Hanabi (GNOME Shell extension)"

    def __init__(self):
        self._dir = _ext_dir()
        if not self._dir or not shutil.which("gsettings"):
            raise BackendUnavailable(NEED_HANABI)

    def _gs(self, *args) -> str:
        cmd = ["gsettings"]
        if (self._dir / "schemas" / "gschemas.compiled").exists():
            cmd += ["--schemadir", str(self._dir / "schemas")]
        r = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            raise BackendUnavailable(f"Hanabi's settings didn't take it: {r.stderr.strip()}")
        return r.stdout.strip()

    def _enable(self, on: bool) -> None:
        if shutil.which("gnome-extensions"):
            subprocess.run(["gnome-extensions", "enable" if on else "disable", UUID],
                           capture_output=True, timeout=5)

    def list_outputs(self) -> List[Monitor]:
        # one video for all of them: a single entry stands for every monitor
        return [Monitor("All monitors", 0, 0, 0, 0, True)]

    def _play(self, path) -> None:
        path = Path(path).expanduser().resolve()
        # a folder: Hanabi's own rotation, every 5 minutes
        self._gs("set", SCHEMA, "change-wallpaper", "true" if path.is_dir() else "false")
        if path.is_dir():
            self._gs("set", SCHEMA, "change-wallpaper-directory-path", str(path))
            self._gs("set", SCHEMA, "change-wallpaper-interval", "5")
        else:
            self._gs("set", SCHEMA, "video-path", str(path))
        self._gs("set", SCHEMA, "mute", "true")
        self._enable(True)

    def apply_singular(self, output, path, monitors) -> None:
        self._play(path)

    def apply_clone(self, path, monitors) -> None:
        self._play(path)

    def apply_span(self, path, monitors) -> None:
        raise BackendUnavailable("Span mode isn't possible with Hanabi.")

    def stop(self, output: str) -> None:
        self._enable(False)

    def stop_all(self) -> None:
        self._enable(False)

    def is_running(self, output: str) -> bool:
        if not shutil.which("gnome-extensions"):
            return False
        r = subprocess.run(["gnome-extensions", "info", UUID], capture_output=True, text=True, timeout=5)
        return "ACTIVE" in r.stdout
