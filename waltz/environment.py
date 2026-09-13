"""Detects which desktop environment / session Waltz is running under, so
the right wallpaper backend gets picked instead of assuming wlr-layer-shell
works everywhere — it doesn't: GNOME's Mutter and KDE's KWin don't
implement that protocol at all.
"""

import os
from dataclasses import dataclass
from enum import Enum


class Environment(Enum):
    WLROOTS = "wlroots"  # Hyprland, Sway, niri, and other wlr-layer-shell compositors
    GNOME_WAYLAND = "gnome-wayland"
    GNOME_X11 = "gnome-x11"
    KDE_WAYLAND = "kde-wayland"
    KDE_X11 = "kde-x11"
    X11_GENERIC = "x11-generic"  # i3, bspwm, Openbox, and anything else on Xorg
    UNKNOWN = "unknown"


@dataclass
class SessionInfo:
    environment: Environment
    session_type: str  # raw $XDG_SESSION_TYPE ("wayland"/"x11"/...)
    current_desktop: str  # raw $XDG_CURRENT_DESKTOP
    session_desktop: str  # raw $XDG_SESSION_DESKTOP


def detect_session() -> SessionInfo:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    current_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session_desktop = os.environ.get("XDG_SESSION_DESKTOP", "")

    desktops = current_desktop.lower()
    session_desktop_lower = session_desktop.lower()

    is_gnome = "gnome" in desktops or session_desktop_lower == "gnome"
    is_kde = (
        "kde" in desktops
        or "plasma" in desktops
        or session_desktop_lower in ("kde", "plasma")
    )

    if session_type == "wayland":
        if is_gnome:
            env = Environment.GNOME_WAYLAND
        elif is_kde:
            env = Environment.KDE_WAYLAND
        else:
            # We don't keep an exhaustive list of wlroots compositors —
            # Hyprland, Sway, niri, Wayfire, River, LabWC, dwl, and others
            # all qualify, and new ones show up regularly. Everything
            # non-GNOME/KDE on Wayland is assumed wlroots-family; the real
            # confirmation is whether monitors.py's own IPC probing
            # (niri msg / hyprctl / swaymsg) actually gets an answer.
            env = Environment.WLROOTS
    elif session_type == "x11":
        if is_gnome:
            env = Environment.GNOME_X11
        elif is_kde:
            env = Environment.KDE_X11
        else:
            env = Environment.X11_GENERIC
    else:
        env = Environment.UNKNOWN

    return SessionInfo(
        environment=env,
        session_type=session_type,
        current_desktop=current_desktop,
        session_desktop=session_desktop,
    )
