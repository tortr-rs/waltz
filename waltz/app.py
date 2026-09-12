"""Waltz application: wires config, monitor detection, the mpvpaper backend,
the tray helper process, and the DBus control surface together."""

import sys
from pathlib import Path
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio

from .config import Config
from .dbus_service import WaltzDBusService
from .monitors import Monitor, detect_monitors, get_primary_monitor
from .mpv_backend import DEFAULT_MPV_OPTIONS, MpvpaperManager
from .span import compute_span_options, has_mismatched_geometry
from .window import WaltzWindow

APP_ID = "com.waltz.Waltz"


class WaltzApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.config = Config.load()
        self.mpv = MpvpaperManager()
        self.dbus_service = WaltzDBusService(self)
        self.window: Optional[WaltzWindow] = None
        self._tray_proc = None

    def do_activate(self) -> None:
        if self.window is None:
            self.window = WaltzWindow(application=self, waltz_app=self)
            self.dbus_service.start()
            self._start_tray()
        self.window.present()

    def _start_tray(self) -> None:
        import subprocess

        try:
            self._tray_proc = subprocess.Popen(
                [sys.executable, "-m", "waltz.tray_process"],
                start_new_session=True,
            )
        except Exception as e:
            print(f"waltz: failed to start tray icon: {e}", file=sys.stderr)

    # -- actions shared between the GUI and the tray/DBus surface -------

    def list_monitors(self) -> List[Monitor]:
        return detect_monitors()

    def apply_wallpaper(self, path, output: Optional[str] = None) -> None:
        """Singular mode: assign one file to one monitor, independent of the rest."""
        monitors = detect_monitors()
        target = None
        if output:
            target = next((m for m in monitors if m.name == output), None)
        if target is None:
            target = get_primary_monitor(monitors)
        if target is None:
            if self.window:
                self.window.show_error(
                    "No monitor detected (no niri/Hyprland/Sway IPC responded)."
                )
            return
        try:
            self.mpv.play(target.name, path, mpv_options=DEFAULT_MPV_OPTIONS)
        except FileNotFoundError:
            if self.window:
                self.window.show_error("mpvpaper not found on PATH — install it first.")
            return
        self.config.set_monitor_wallpaper(target.name, path, DEFAULT_MPV_OPTIONS)
        if self.window:
            self.window.set_status(f"Playing on {target.name}: {Path(path).name}")

    def apply_clone(self, path) -> None:
        """Clone mode: the same file on every monitor, via mpvpaper's own
        'ALL' output — a single process rather than one per monitor."""
        monitors = detect_monitors()
        if not monitors:
            if self.window:
                self.window.show_error(
                    "No monitor detected (no niri/Hyprland/Sway IPC responded)."
                )
            return
        try:
            self.mpv.play_all(path, mpv_options=DEFAULT_MPV_OPTIONS)
        except FileNotFoundError:
            if self.window:
                self.window.show_error("mpvpaper not found on PATH — install it first.")
            return
        assignments = {
            m.name: {"path": str(path), "mpv_options": DEFAULT_MPV_OPTIONS} for m in monitors
        }
        self.config.set_all_monitors(assignments, mode="clone", source_path=path)
        if self.window:
            self.window.set_status(f"Cloned to {len(monitors)} monitor(s): {Path(path).name}")

    def apply_span(self, path) -> None:
        """Span mode: one video stretched across the combined desktop, each
        monitor cropping out its own slice via mpv's native crop filter."""
        monitors = detect_monitors()
        if len(monitors) < 2:
            if self.window:
                self.window.show_error("Span mode needs at least two detected monitors.")
            return
        per_output_options = compute_span_options(monitors)
        assignments = {}
        for m in monitors:
            options = per_output_options[m.name]
            try:
                self.mpv.play(m.name, path, mpv_options=options)
            except FileNotFoundError:
                if self.window:
                    self.window.show_error("mpvpaper not found on PATH — install it first.")
                return
            assignments[m.name] = {"path": str(path), "mpv_options": options}
        self.config.set_all_monitors(assignments, mode="span", source_path=path)
        if self.window:
            status = f"Spanned across {len(monitors)} monitors: {Path(path).name}"
            if has_mismatched_geometry(monitors):
                self.window.show_error(
                    status + " — monitors differ in resolution, alignment may be off"
                )
            else:
                self.window.set_status(status)

    def stop_wallpaper(self) -> None:
        self.mpv.stop_all()
        if self.window:
            self.window.set_status("Wallpaper stopped")

    def show_main_window(self) -> None:
        if self.window is not None:
            self.window.present()
        else:
            self.activate()

    def quit_app(self) -> None:
        self.mpv.stop_all()
        if self._tray_proc is not None and self._tray_proc.poll() is None:
            self._tray_proc.terminate()
        self.dbus_service.stop()
        self.quit()


def main() -> int:
    app = WaltzApplication()
    return app.run(sys.argv)
