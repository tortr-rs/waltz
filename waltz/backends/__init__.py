"""Wallpaper backend selection.

Picks the right backend for the current desktop session instead of
assuming wlr-layer-shell works everywhere — it doesn't: GNOME's Mutter and
KDE's KWin don't implement that protocol at all, so both need a different
approach, and neither has one Waltz can drive cleanly today (see the
research notes below).
"""

from ..environment import Environment, SessionInfo, detect_session
from .base import BackendUnavailable, WallpaperBackend
from .unsupported import UnsupportedBackend
from .waltzer_white import WaltzerWhiteBackend
from .x11 import X11Backend

# GNOME Wayland: Mutter has no wlr-layer-shell support (an open GNOME
# feature request with no completion date). The one real, actively
# maintained option is the Hanabi GNOME Shell extension
# (github.com/jeffshee/gnome-ext-hanabi), which renders video inside
# Mutter's own actor scene graph and is genuinely scriptable via
# `gsettings set io.github.jeffshee.hanabi-extension video-path '<path>'`.
# Not wired up yet: it requires the user to already have the extension
# installed and enabled (Waltz can't silently install a GNOME Shell
# extension), and it doesn't support multiple monitors yet either. This is
# a real path forward, just a follow-up phase rather than done here.
_GNOME_WAYLAND_MESSAGE = (
    "Video wallpapers aren't supported on GNOME Wayland yet — Mutter doesn't "
    "implement the protocol Waltz needs (wlr-layer-shell), and there's no "
    "timeline for that changing. The GNOME Shell extension \"Hanabi\" "
    "(github.com/jeffshee/gnome-ext-hanabi) can genuinely do video wallpapers "
    "here, but Waltz doesn't drive it yet — install and enable it yourself for now."
)

# KDE Plasma (Wayland or X11): Plasma has its own wallpaper plugin system.
# The closest thing to what Waltz does is the third-party "Smart Video
# Wallpaper Reborn" plugin (github.com/luisbocanegra/plasma-smart-video-
# wallpaper-reborn, also on KDE Store/AUR/Fedora) — but changing its video
# has no DBus or CLI control, only a config file
# (~/.config/plasma-org.kde.plasma.desktop-appletsrc, VideoUrls key) that
# needs plasmashell restarted to take effect: a disruptive full-shell
# reload, not the clean per-process swap mpvpaper does. Not worth Waltz
# driving that today.
_KDE_MESSAGE = (
    "Video wallpapers aren't supported on KDE Plasma yet — Plasma uses its own "
    "wallpaper plugin system rather than wlr-layer-shell. The \"Smart Video "
    "Wallpaper Reborn\" plugin (github.com/luisbocanegra/plasma-smart-video-"
    "wallpaper-reborn, also on the KDE Store) does this well; install and "
    "configure it through Plasma's own wallpaper settings for now."
)

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
        return UnsupportedBackend(_GNOME_WAYLAND_MESSAGE)

    if env in (Environment.KDE_WAYLAND, Environment.KDE_X11):
        return UnsupportedBackend(_KDE_MESSAGE)

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
    "UnsupportedBackend",
    "Environment",
    "SessionInfo",
    "detect_session",
]
