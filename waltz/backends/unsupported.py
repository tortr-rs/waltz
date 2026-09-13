"""Placeholder backend for sessions where Waltz doesn't (yet, or possibly
ever) have a real way to show a video wallpaper. Every action fails with
the same clear, honest reason — set once, at selection time — instead of
silently doing nothing or pretending a wallpaper is showing when it isn't.
"""

from typing import List

from ..monitors import Monitor
from .base import BackendUnavailable, WallpaperBackend


class UnsupportedBackend(WallpaperBackend):
    name = "unsupported"

    def __init__(self, reason: str):
        self.reason = reason

    def list_outputs(self) -> List[Monitor]:
        return []

    def _fail(self) -> None:
        raise BackendUnavailable(self.reason)

    def apply_singular(self, output, path, monitors) -> None:
        self._fail()

    def apply_clone(self, path, monitors) -> None:
        self._fail()

    def apply_span(self, path, monitors) -> None:
        self._fail()

    def stop(self, output: str) -> None:
        pass

    def stop_all(self) -> None:
        pass

    def is_running(self, output: str) -> bool:
        return False
