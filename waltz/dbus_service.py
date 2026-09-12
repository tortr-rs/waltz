"""Session-bus control surface that the tray helper process talks to.

This exists to keep the GTK4 main process and the tray icon in separate
processes (see tray_process.py for why) while still letting the tray
control wallpaper playback. Uses Gio.DBus directly — no GTK version
dependency, so it's safe to use from the GTK4 process.
"""

from gi.repository import Gio

BUS_NAME = "com.waltz.Waltz"
OBJECT_PATH = "/com/waltz/Waltz"
INTERFACE_NAME = "com.waltz.Waltz"

INTRODUCTION_XML = """
<node>
  <interface name="com.waltz.Waltz">
    <method name="StopWallpaper"/>
    <method name="ShowWindow"/>
    <method name="Quit"/>
  </interface>
</node>
"""


class WaltzDBusService:
    def __init__(self, app):
        self._app = app
        self._registration_id = None
        self._owner_id = None
        self._connection = None

    def start(self) -> None:
        self._owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            BUS_NAME,
            Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired,
            None,
            None,
        )

    def stop(self) -> None:
        if self._connection is not None and self._registration_id is not None:
            self._connection.unregister_object(self._registration_id)
            self._registration_id = None
        if self._owner_id is not None:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = None

    def _on_bus_acquired(self, connection, name):
        self._connection = connection
        node_info = Gio.DBusNodeInfo.new_for_xml(INTRODUCTION_XML)
        iface_info = node_info.interfaces[0]
        self._registration_id = connection.register_object(
            OBJECT_PATH,
            iface_info,
            self._handle_method_call,
            None,
            None,
        )

    def _handle_method_call(
        self, connection, sender, object_path, interface_name, method_name, parameters, invocation
    ):
        if method_name == "StopWallpaper":
            self._app.stop_wallpaper()
            invocation.return_value(None)
        elif method_name == "ShowWindow":
            self._app.show_main_window()
            invocation.return_value(None)
        elif method_name == "Quit":
            invocation.return_value(None)
            self._app.quit_app()
        else:
            invocation.return_error_literal(
                Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD, "Unknown method"
            )
