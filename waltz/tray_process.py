"""Standalone tray-icon helper, run as its own subprocess.

Why a separate process: AyatanaAppIndicator3 (the standard StatusNotifierItem
wrapper on Linux) builds its menu out of GTK3's Gtk.Menu, but PyGObject can
only load one Gtk major version per process — and the main Waltz window
needs GTK4. So the tray runs in its own GTK3 interpreter and talks to the
main app over the session bus (see dbus_service.py) instead of sharing
memory with it. This module must never be imported by the GTK4 process.
"""

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, AyatanaAppIndicator3 as AppIndicator3, Gio, GLib

BUS_NAME = "com.waltz.Waltz"
OBJECT_PATH = "/com/waltz/Waltz"
INTERFACE_NAME = "com.waltz.Waltz"

ICON_NAME = "com.waltz.Waltz"
ICON_THEME_DIR = Path(__file__).parent / "icons"


def _call(method_name: str) -> None:
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            None,
            BUS_NAME,
            OBJECT_PATH,
            INTERFACE_NAME,
            None,
        )
        proxy.call_sync(method_name, None, Gio.DBusCallFlags.NONE, 2000, None)
    except GLib.Error as e:
        print(f"waltz-tray: DBus call {method_name!r} failed: {e}", file=sys.stderr)


def _on_open(_item):
    _call("ShowWindow")


def _on_stop(_item):
    _call("StopWallpaper")


def _on_quit(_item):
    _call("Quit")
    Gtk.main_quit()


def _build_menu() -> Gtk.Menu:
    menu = Gtk.Menu()

    open_item = Gtk.MenuItem(label="Open Waltz")
    open_item.connect("activate", _on_open)
    menu.append(open_item)

    stop_item = Gtk.MenuItem(label="Stop Wallpaper")
    stop_item.connect("activate", _on_stop)
    menu.append(stop_item)

    menu.append(Gtk.SeparatorMenuItem())

    quit_item = Gtk.MenuItem(label="Quit Waltz")
    quit_item.connect("activate", _on_quit)
    menu.append(quit_item)

    menu.show_all()
    return menu


def main() -> None:
    indicator = AppIndicator3.Indicator.new(
        "waltz",
        ICON_NAME,
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    # Same hicolor-layout directory the main GTK4 process registers with
    # Gtk.IconTheme — AyatanaAppIndicator3 resolves its icon name through
    # this search path rather than taking a raw file path directly.
    indicator.set_icon_theme_path(str(ICON_THEME_DIR))
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_title("Waltz")
    indicator.set_menu(_build_menu())
    Gtk.main()


if __name__ == "__main__":
    main()
