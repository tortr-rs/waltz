"""wlr-layer-shell backend, backed by waltzer-white (Waltz's own minimal
Rust renderer) instead of mpvpaper — the sole renderer for wlroots-based
compositors now.

waltzer-white deliberately has no option passthrough (by design — see
waltzer-white/src/main.rs), so it can't do the mpv filter-chain tricks
Span mode needs. Clone doesn't need that: one process renders the same
decoded video to every monitor's own surface, so N monitors cost roughly
the same as one, not N times as much.
"""

from ..monitors import detect_monitors
from ..waltzerwhite_backend import BINARY_PATH, WaltzerWhiteManager
from .base import BackendUnavailable, WallpaperBackend


class WaltzerWhiteBackend(WallpaperBackend):
    name = "waltzer-white (wlr-layer-shell)"

    def __init__(self):
        if not BINARY_PATH.exists():
            raise BackendUnavailable(
                f"waltzer-white isn't built — run `cargo build --release` in "
                f"{BINARY_PATH.parent.parent.parent}."
            )
        self._renderer = WaltzerWhiteManager()

    def list_outputs(self):
        return detect_monitors()

    def apply_singular(self, output, path, monitors) -> None:
        self._renderer.play([output], path)

    def apply_clone(self, path, monitors) -> None:
        self._renderer.play([m.name for m in monitors], path)

    def apply_span(self, path, monitors) -> None:
        raise BackendUnavailable(
            "Span mode isn't supported yet — waltzer-white has no option "
            "passthrough, which is what the per-monitor crop math needs."
        )

    def stop(self, output: str) -> None:
        self._renderer.stop(output)

    def stop_all(self) -> None:
        self._renderer.stop_all()

    def is_running(self, output: str) -> bool:
        return self._renderer.is_running(output)
