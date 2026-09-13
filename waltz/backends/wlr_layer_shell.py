"""wlr-layer-shell backend: mpvpaper, for Hyprland, Sway, niri, and other
wlroots-based compositors. This is Waltz's original backend, unchanged
underneath — just wrapped behind the common interface.
"""

import shutil
from typing import List

from ..monitors import detect_monitors
from ..mpv_backend import DEFAULT_MPV_OPTIONS, MpvpaperManager
from ..span import compute_span_options
from .base import BackendUnavailable, WallpaperBackend


class WlrLayerShellBackend(WallpaperBackend):
    name = "mpvpaper (wlr-layer-shell)"

    def __init__(self):
        if not shutil.which("mpvpaper"):
            raise BackendUnavailable("mpvpaper isn't installed.")
        self._mpv = MpvpaperManager()

    def list_outputs(self):
        return detect_monitors()

    def apply_singular(self, output, path, monitors) -> None:
        self._mpv.play(output, path, mpv_options=DEFAULT_MPV_OPTIONS)

    def apply_clone(self, path, monitors) -> None:
        self._mpv.play_all(path, mpv_options=DEFAULT_MPV_OPTIONS)

    def apply_span(self, path, monitors) -> None:
        per_output = compute_span_options(monitors)
        for m in monitors:
            self._mpv.play(m.name, path, mpv_options=per_output[m.name])

    def stop(self, output: str) -> None:
        self._mpv.stop(output)

    def stop_all(self) -> None:
        self._mpv.stop_all()

    def is_running(self, output: str) -> bool:
        return self._mpv.is_running(output)
