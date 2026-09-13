"""Waltz application: wires config, the wallpaper backend, the tray helper
process, and the DBus control surface together."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import autostart
from .backends import BackendUnavailable, UnsupportedBackend, select_backend
from .config import Config
from .dbus_service import WaltzDBusService
from .monitors import Monitor, get_primary_monitor
from .window import WaltzWindow

APP_ID = "com.waltz.Waltz"

# Stored in config for record-keeping only — no backend reads it back on
# restore (each backend decides its own options internally), and
# waltzer-white has no options to record in the first place.
_NO_OPTIONS = ""


class WaltzApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.config = Config.load()
        self.backend = select_backend()
        self.dbus_service = WaltzDBusService(self)
        self.window: Optional[WaltzWindow] = None
        self._tray_proc = None
        self._restored_once = False
        # Every wallpaper change runs here, one at a time, off the GTK main
        # thread: killing the renderer still costs real GPU-teardown time,
        # and a single worker means rapid clicks queue in order instead of
        # racing each other over the same output.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="waltz-backend")

    def do_activate(self) -> None:
        if self.window is None:
            self._load_css()
            self._register_icon_theme()
            self.window = WaltzWindow(application=self, waltz_app=self)
            self.dbus_service.start()
            self._start_tray()
            if isinstance(self.backend, UnsupportedBackend):
                self._notify(self.backend.reason, error=True)
        if not self._restored_once:
            self._restored_once = True
            self._worker.submit(self._restore_saved_wallpaper)
        self.window.present()

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).parent / "style.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _register_icon_theme(self) -> None:
        """GTK4 windows have no per-window set-icon call — the compositor
        looks up an icon named after the app-id (APP_ID) in the icon theme
        search paths. This adds our bundled icons/ dir (standard hicolor
        layout) so that lookup succeeds even running straight from the
        checkout, not just once actually installed (install.sh copies the
        same file into ~/.local/share/icons/hicolor for that case)."""
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_theme.add_search_path(str(Path(__file__).parent / "icons"))

    def _start_tray(self) -> None:
        try:
            self._tray_proc = subprocess.Popen(
                [sys.executable, "-m", "waltz.tray_process"],
                start_new_session=True,
            )
        except Exception as e:
            print(f"waltz: failed to start tray icon: {e}", file=sys.stderr)

    def _notify(self, message: str, error: bool = False) -> None:
        def _update():
            if self.window:
                self.window.show_error(message) if error else self.window.set_status(message)
            return False

        GLib.idle_add(_update)

    def _with_hint(self, message: str) -> str:
        return message + self.backend.hint if self.backend.hint else message

    def _refresh_indicators(self) -> None:
        def _update():
            if self.window:
                self.window.refresh_active_indicators()
            return False

        GLib.idle_add(_update)

    # -- startup persistence ----------------------------------------------

    def _restore_saved_wallpaper(self) -> None:
        """Relaunch whatever was saved last, if anything. Runs once, off
        the main thread — it shells out to the backend and monitor IPC,
        same as any other apply."""
        monitors_cfg = self.config.monitors
        if not monitors_cfg:
            return
        mode = self.config.display_mode
        source = self.config.source_path
        detected = {m.name: m for m in self.backend.list_outputs()}

        try:
            if mode == "clone" and source and Path(source).exists():
                self.backend.apply_clone(source, list(detected.values()))
                self._notify(f"Restored clone: {Path(source).name}")
            elif mode == "span" and source and Path(source).exists() and len(detected) >= 2:
                self.backend.apply_span(source, list(detected.values()))
                self._notify(f"Restored span: {Path(source).name}")
            else:
                restored = 0
                for name, entry in monitors_cfg.items():
                    if name not in detected:
                        continue  # that output isn't connected this session
                    path = entry.get("path")
                    if not path or not Path(path).exists():
                        continue
                    self.backend.apply_singular(name, path, list(detected.values()))
                    restored += 1
                if restored:
                    self._notify(f"Restored {restored} saved wallpaper(s)")
            self._refresh_indicators()
        except BackendUnavailable:
            pass  # already surfaced once at startup; no need to repeat it here

    # -- actions shared between the GUI and the tray/DBus surface -------

    def list_monitors(self) -> List[Monitor]:
        return self.backend.list_outputs()

    def apply_wallpaper(self, path, output: Optional[str] = None) -> None:
        """Singular mode: assign one file to one monitor, independent of the rest."""
        self._worker.submit(self._apply_wallpaper_worker, path, output)

    def _apply_wallpaper_worker(self, path, output: Optional[str]) -> None:
        monitors = self.backend.list_outputs()
        target = None
        if output:
            target = next((m for m in monitors if m.name == output), None)
        if target is None:
            target = get_primary_monitor(monitors)
        if target is None:
            self._notify("No monitor detected for this session.", error=True)
            return
        try:
            self.backend.apply_singular(target.name, path, monitors)
        except BackendUnavailable as e:
            self._notify(str(e), error=True)
            return
        self.config.set_monitor_wallpaper(target.name, path, _NO_OPTIONS)
        self._refresh_indicators()
        self._notify(self._with_hint(f"Playing on {target.name}: {Path(path).name}"))

    def apply_clone(self, path) -> None:
        """Clone mode: the same file on every monitor."""
        self._worker.submit(self._apply_clone_worker, path)

    def _apply_clone_worker(self, path) -> None:
        monitors = self.backend.list_outputs()
        if not monitors:
            self._notify("No monitor detected for this session.", error=True)
            return
        try:
            self.backend.apply_clone(path, monitors)
        except BackendUnavailable as e:
            self._notify(str(e), error=True)
            return
        assignments = {
            m.name: {"path": str(path), "mpv_options": _NO_OPTIONS} for m in monitors
        }
        self.config.set_all_monitors(assignments, mode="clone", source_path=path)
        self._refresh_indicators()
        self._notify(self._with_hint(f"Cloned to {len(monitors)} monitor(s): {Path(path).name}"))

    def apply_span(self, path) -> None:
        """Span mode: one video stretched across the combined desktop."""
        self._worker.submit(self._apply_span_worker, path)

    def _apply_span_worker(self, path) -> None:
        monitors = self.backend.list_outputs()
        if len(monitors) < 2:
            self._notify("Span mode needs at least two detected monitors.", error=True)
            return
        try:
            self.backend.apply_span(path, monitors)
        except BackendUnavailable as e:
            self._notify(str(e), error=True)
            return
        assignments = {
            m.name: {"path": str(path), "mpv_options": _NO_OPTIONS} for m in monitors
        }
        self.config.set_all_monitors(assignments, mode="span", source_path=path)
        self._refresh_indicators()
        self._notify(
            self._with_hint(f"Spanned across {len(monitors)} monitors: {Path(path).name}")
        )

    def stop_wallpaper(self) -> None:
        self._worker.submit(self._stop_wallpaper_worker)

    def _stop_wallpaper_worker(self) -> None:
        self.backend.stop_all()
        self._refresh_indicators()
        self._notify("Wallpaper stopped")

    def show_main_window(self) -> None:
        if self.window is not None:
            self.window.present()
        else:
            self.activate()

    def is_autostart_enabled(self) -> bool:
        return autostart.is_enabled()

    def set_autostart(self, enabled: bool) -> None:
        """Toggle launching Waltz at login via a standard XDG autostart
        .desktop entry. Opt-in only, flipped from the GUI switch — never
        applied automatically, and never touches the compositor's own
        config file."""
        if enabled:
            autostart.enable()
        else:
            autostart.disable()

    def quit_app(self) -> None:
        self.backend.stop_all()
        if self._tray_proc is not None and self._tray_proc.poll() is None:
            self._tray_proc.terminate()
        self.dbus_service.stop()
        self._worker.shutdown(wait=False)
        self.quit()


def main() -> int:
    app = WaltzApplication()
    return app.run(sys.argv)
