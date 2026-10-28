"""Wallpaper backend selection.

Picks the right backend for the current desktop session instead of
assuming wlr-layer-shell works everywhere — it doesn't: GNOME's Mutter and
KDE's KWin don't implement that protocol, so Plasma gets Waltz's own
wallpaper plugin (kde.py) and GNOME goes through the Hanabi extension
(gnome.py).
"""

from ..environment import Environment, SessionInfo, detect_session
from .base import BackendUnavailable, WallpaperBackend
from .gnome import GnomeBackend
from .kde import KdeBackend
from .unsupported import UnsupportedBackend
from .waltzer_white import WaltzerWhiteBackend
from .x11 import X11Backend

# GNOME on Xorg: xwinwrap does work here, but it's a long-documented,
# still-current conflict with Nautilus's desktop-icons layer — icons can
# get obscured and drag-and-drop breaks. Not blocking it, just warning.
_GNOME_X11_HINT = (
    " (Note: GNOME's desktop icons can conflict with this — if drag-and-drop "
    "or icon visibility breaks, disable Nautilus's desktop icons.)"
)


def select_backend(session: SessionInfo = None) -> WallpaperBackend:
    session = session or detect_session()
    env = session.environment

    if env == Environment.WLROOTS:
        return _try(WaltzerWhiteBackend)

    if env == Environment.X11_GENERIC:
        return _try(X11Backend)

    if env == Environment.GNOME_X11:
        backend = _try(X11Backend)
        if isinstance(backend, UnsupportedBackend):
            return backend
        backend.hint = _GNOME_X11_HINT
        return backend

    if env == Environment.GNOME_WAYLAND:
        return _try(GnomeBackend)

    if env in (Environment.KDE_WAYLAND, Environment.KDE_X11):
        return _try(KdeBackend)

    return UnsupportedBackend(
        "Couldn't determine a supported wallpaper backend for this session "
        f"(XDG_SESSION_TYPE={session.session_type!r}, "
        f"XDG_CURRENT_DESKTOP={session.current_desktop!r})."
    )


def _try(backend_cls) -> WallpaperBackend:
    try:
        return backend_cls()
    except BackendUnavailable as e:
        return UnsupportedBackend(str(e))


__all__ = [
    "select_backend",
    "WallpaperBackend",
    "BackendUnavailable",
    "WaltzerWhiteBackend",
    "X11Backend",
    "KdeBackend",
    "GnomeBackend",
    "UnsupportedBackend",
    "Environment",
    "SessionInfo",
    "detect_session",
]
