"""Waltz application: wires config, monitor detection, the mpvpaper backend,
the tray helper process, and the DBus control surface together."""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib

from . import autostart
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
        self._restored_once = False
        # Every wallpaper change runs here, one at a time, off the GTK main
        # thread: killing mpvpaper still costs real GPU-teardown time (see
        # mpv_backend), and a single worker means rapid clicks queue in
        # order instead of racing each other over the same output.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="waltz-mpv")

    def do_activate(self) -> None:
        if self.window is None:
            self.window = WaltzWindow(application=self, waltz_app=self)
            self.dbus_service.start()
            self._start_tray()
        if not self._restored_once:
            self._restored_once = True
            self._worker.submit(self._restore_saved_wallpaper)
        self.window.present()

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

    # -- startup persistence ----------------------------------------------

    def _restore_saved_wallpaper(self) -> None:
        """Relaunch whatever was saved last, if anything. Runs once, off
        the main thread — it shells out to mpvpaper and the compositor's
        monitor IPC, same as any other apply."""
        monitors_cfg = self.config.monitors
        if not monitors_cfg:
            return
        mode = self.config.display_mode
        source = self.config.source_path
        detected = {m.name: m for m in detect_monitors()}

        try:
            if mode == "clone" and source and Path(source).exists():
                opts = next(iter(monitors_cfg.values())).get("mpv_options", DEFAULT_MPV_OPTIONS)
                self.mpv.play_all(source, mpv_options=opts)
                self._notify(f"Restored clone: {Path(source).name}")
            elif mode == "span" and source and Path(source).exists() and len(detected) >= 2:
                # recomputed fresh, in case monitor geometry changed since last save
                per_output = compute_span_options(list(detected.values()))
                for name, options in per_output.items():
                    self.mpv.play(name, source, mpv_options=options)
                self._notify(f"Restored span: {Path(source).name}")
            else:
                restored = 0
                for name, entry in monitors_cfg.items():
                    if name not in detected:
                        continue  # that output isn't connected this session
                    path = entry.get("path")
                    if not path or not Path(path).exists():
                        continue
                    self.mpv.play(name, path, mpv_options=entry.get("mpv_options", DEFAULT_MPV_OPTIONS))
                    restored += 1
                if restored:
                    self._notify(f"Restored {restored} saved wallpaper(s)")
        except FileNotFoundError:
            self._notify("mpvpaper not found on PATH — couldn't restore saved wallpaper.", error=True)

    # -- actions shared between the GUI and the tray/DBus surface -------

    def list_monitors(self) -> List[Monitor]:
        return detect_monitors()

    def apply_wallpaper(self, path, output: Optional[str] = None) -> None:
        """Singular mode: assign one file to one monitor, independent of the rest."""
        self._worker.submit(self._apply_wallpaper_worker, path, output)

    def _apply_wallpaper_worker(self, path, output: Optional[str]) -> None:
        monitors = detect_monitors()
        target = None
        if output:
            target = next((m for m in monitors if m.name == output), None)
        if target is None:
            target = get_primary_monitor(monitors)
        if target is None:
            self._notify("No monitor detected (no niri/Hyprland/Sway IPC responded).", error=True)
            return
        try:
            self.mpv.play(target.name, path, mpv_options=DEFAULT_MPV_OPTIONS)
        except FileNotFoundError:
            self._notify("mpvpaper not found on PATH — install it first.", error=True)
            return
        self.config.set_monitor_wallpaper(target.name, path, DEFAULT_MPV_OPTIONS)
        self._notify(f"Playing on {target.name}: {Path(path).name}")

    def apply_clone(self, path) -> None:
        """Clone mode: the same file on every monitor, via mpvpaper's own
        'ALL' output — a single process rather than one per monitor."""
        self._worker.submit(self._apply_clone_worker, path)

    def _apply_clone_worker(self, path) -> None:
        monitors = detect_monitors()
        if not monitors:
            self._notify("No monitor detected (no niri/Hyprland/Sway IPC responded).", error=True)
            return
        try:
            self.mpv.play_all(path, mpv_options=DEFAULT_MPV_OPTIONS)
        except FileNotFoundError:
            self._notify("mpvpaper not found on PATH — install it first.", error=True)
            return
        assignments = {
            m.name: {"path": str(path), "mpv_options": DEFAULT_MPV_OPTIONS} for m in monitors
        }
        self.config.set_all_monitors(assignments, mode="clone", source_path=path)
        self._notify(f"Cloned to {len(monitors)} monitor(s): {Path(path).name}")

    def apply_span(self, path) -> None:
        """Span mode: one video stretched across the combined desktop, each
        monitor cropping out its own slice via mpv's native crop filter."""
        self._worker.submit(self._apply_span_worker, path)

    def _apply_span_worker(self, path) -> None:
        monitors = detect_monitors()
        if len(monitors) < 2:
            self._notify("Span mode needs at least two detected monitors.", error=True)
            return
        per_output_options = compute_span_options(monitors)
        assignments = {}
        for m in monitors:
            options = per_output_options[m.name]
            try:
                self.mpv.play(m.name, path, mpv_options=options)
            except FileNotFoundError:
                self._notify("mpvpaper not found on PATH — install it first.", error=True)
                return
            assignments[m.name] = {"path": str(path), "mpv_options": options}
        self.config.set_all_monitors(assignments, mode="span", source_path=path)
        status = f"Spanned across {len(monitors)} monitors: {Path(path).name}"
        if has_mismatched_geometry(monitors):
            self._notify(status + " — monitors differ in resolution, alignment may be off", error=True)
        else:
            self._notify(status)

    def stop_wallpaper(self) -> None:
        self._worker.submit(self._stop_wallpaper_worker)

    def _stop_wallpaper_worker(self) -> None:
        self.mpv.stop_all()
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
        self.mpv.stop_all()
        if self._tray_proc is not None and self._tray_proc.poll() is None:
            self._tray_proc.terminate()
        self.dbus_service.stop()
        self._worker.shutdown(wait=False)
        self.quit()


def main() -> int:
    app = WaltzApplication()
    return app.run(sys.argv)
