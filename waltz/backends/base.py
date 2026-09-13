"""Common interface every wallpaper backend implements, so the GUI/tray
layer doesn't need to know whether it's driving mpvpaper, xwinwrap+mpv, or
something else underneath.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..monitors import Monitor


class BackendUnavailable(Exception):
    """Raised when a backend can't run here — the message is user-facing."""


class WallpaperBackend(ABC):
    name: str = "unknown"

    # Optional extra line appended to success messages — used for caveats
    # that don't block the backend from working (e.g. GNOME-on-Xorg's
    # Nautilus desktop-icon conflict with xwinwrap).
    hint: Optional[str] = None

    @abstractmethod
    def list_outputs(self) -> List[Monitor]:
        """Detect currently connected monitors, in whatever way this
        backend's environment exposes them (compositor IPC, xrandr, ...)."""

    @abstractmethod
    def apply_singular(self, output: str, path, monitors: List[Monitor]) -> None:
        """Assign one file to one output, independent of the rest."""

    @abstractmethod
    def apply_clone(self, path, monitors: List[Monitor]) -> None:
        """Show the same file on every output."""

    @abstractmethod
    def apply_span(self, path, monitors: List[Monitor]) -> None:
        """Stretch one file across the combined desktop, one slice per output."""

    @abstractmethod
    def stop(self, output: str) -> None:
        """Stop whatever is showing on one output."""

    @abstractmethod
    def stop_all(self) -> None:
        """Stop every wallpaper this backend is currently showing."""

    @abstractmethod
    def is_running(self, output: str) -> bool:
        ...
