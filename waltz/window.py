"""Main Waltz window: folder picker + thumbnail grid."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gtk, GLib, Pango

from .thumbnails import ensure_thumbnail, list_media_files

THUMB_DISPLAY_WIDTH = 200
THUMB_DISPLAY_HEIGHT = THUMB_DISPLAY_WIDTH * 9 // 16

# One entry per segment in the target strip: ("monitor", output_name) for a
# real monitor, or ("clone", None) / ("span", None) for the two quick actions.
Target = Tuple[str, Optional[str]]


class WaltzWindow(Adw.ApplicationWindow):
    def __init__(self, waltz_app, **kwargs):
        super().__init__(**kwargs)
        self.waltz_app = waltz_app
        self.set_title("Waltz")
        self.set_default_size(960, 680)

        self._executor = ThreadPoolExecutor(max_workers=4)
        self._current_folder: Optional[Path] = None

        # path (resolved, as str) -> (card button, badge label), for the
        # "currently playing" indicator
        self._tiles: Dict[str, Tuple[Gtk.Button, Gtk.Label]] = {}
        # button -> target it selects, for the segmented strip
        self._target_buttons: List[Tuple[Gtk.ToggleButton, Target]] = []
        # output name -> its subtitle label, updated on refresh
        self._monitor_subtitles: Dict[str, Gtk.Label] = {}

        self._pointer_cursor = self._load_custom_cursor()

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._build_header())
        toolbar_view.add_top_bar(self._build_target_strip(waltz_app))

        self._toast_overlay = Adw.ToastOverlay()

        self._status_label = Gtk.Label(label="Open a folder to browse wallpapers")
        self._status_label.add_css_class("dim-label")
        self._status_label.set_margin_top(6)
        self._status_label.set_margin_bottom(6)
        self._status_label.set_xalign(0)
        self._status_label.set_margin_start(12)

        self._flowbox = Gtk.FlowBox()
        self._flowbox.set_valign(Gtk.Align.START)
        self._flowbox.set_max_children_per_line(6)
        self._flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flowbox.set_row_spacing(12)
        self._flowbox.set_column_spacing(12)
        self._flowbox.set_margin_top(12)
        self._flowbox.set_margin_bottom(12)
        self._flowbox.set_margin_start(12)
        self._flowbox.set_margin_end(12)
        self._flowbox.set_homogeneous(True)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self._flowbox)
        scroller.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self._status_label)
        box.append(scroller)

        self._toast_overlay.set_child(box)
        toolbar_view.set_content(self._toast_overlay)
        self.set_content(toolbar_view)

        self.connect("close-request", self._on_close_request)

        folders = waltz_app.config.folders
        if folders:
            self._load_folder(Path(folders[-1]))
        self.refresh_active_indicators()

    # -- header / target strip construction --------------------------------

    def _load_custom_cursor(self):
        try:
            texture = Gdk.Texture.new_from_filename(str(Path(__file__).parent / "cursor.svg"))
            return Gdk.Cursor.new_from_texture(texture, 4, 3, Gdk.Cursor.new_from_name("pointer"))
        except GLib.Error:
            return None  # fall back to the default cursor rather than fail to open

    def _apply_pointer_cursor(self, widget: Gtk.Widget) -> None:
        if self._pointer_cursor is not None:
            widget.set_cursor(self._pointer_cursor)

    def _build_header(self) -> Adw.HeaderBar:
        header = Adw.HeaderBar()

        open_button = Gtk.Button(label="Open Folder")
        open_button.add_css_class("suggested-action")
        open_button.add_css_class("waltz-primary-action")
        open_button.connect("clicked", self._on_open_folder_clicked)
        header.pack_start(open_button)

        stop_button = Gtk.Button(label="Stop Wallpaper")
        stop_button.add_css_class("destructive-action")
        stop_button.connect("clicked", self._on_stop_clicked)
        header.pack_end(stop_button)

        autostart_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        autostart_box.set_valign(Gtk.Align.CENTER)
        autostart_label = Gtk.Label(label="Start at login")
        autostart_label.add_css_class("dim-label")
        self._autostart_switch = Gtk.Switch()
        self._autostart_switch.set_active(self.waltz_app.is_autostart_enabled())
        self._autostart_switch.set_tooltip_text(
            "Launch Waltz automatically at login via a standard XDG autostart\n"
            "entry (~/.config/autostart) — never touches your compositor config."
        )
        self._autostart_switch.connect("notify::active", self._on_autostart_toggled)
        autostart_box.append(autostart_label)
        autostart_box.append(self._autostart_switch)
        header.pack_end(autostart_box)

        return header

    def _build_target_strip(self, waltz_app) -> Gtk.Box:
        """One segmented control: a toggle per monitor (assign to just that
        output), plus Clone (same file everywhere) and Span (stretched
        across all of them) as two more segments. Whichever is active
        decides what clicking a thumbnail does."""
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.add_css_class("target-strip")

        label = Gtk.Label(label="Assign to:")
        label.add_css_class("dim-label")
        outer.append(label)

        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        strip.add_css_class("linked")

        first_button: Optional[Gtk.ToggleButton] = None
        monitors = waltz_app.list_monitors()

        for monitor in monitors:
            button = Gtk.ToggleButton()
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            name_label = Gtk.Label(label=monitor.name)
            subtitle = Gtk.Label(label="—")
            subtitle.add_css_class("target-subtitle")
            subtitle.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle.set_max_width_chars(14)
            content.append(name_label)
            content.append(subtitle)
            button.set_child(content)

            if first_button is None:
                first_button = button
                button.set_active(True)
            else:
                button.set_group(first_button)

            self._apply_pointer_cursor(button)
            strip.append(button)
            self._target_buttons.append((button, ("monitor", monitor.name)))
            self._monitor_subtitles[monitor.name] = subtitle

        clone_button = Gtk.ToggleButton(label="Clone")
        clone_button.set_tooltip_text("The same file, mirrored on every monitor")
        if first_button is None:
            first_button = clone_button
            clone_button.set_active(True)
        else:
            clone_button.set_group(first_button)
        self._apply_pointer_cursor(clone_button)
        strip.append(clone_button)
        self._target_buttons.append((clone_button, ("clone", None)))

        span_button = Gtk.ToggleButton(label="Span")
        span_button.set_tooltip_text("One file, stretched across every monitor combined")
        if first_button is not None:
            span_button.set_group(first_button)
        self._apply_pointer_cursor(span_button)
        strip.append(span_button)
        self._target_buttons.append((span_button, ("span", None)))

        outer.append(strip)
        return outer

    # -- window lifecycle -------------------------------------------------

    def _on_close_request(self, _window) -> bool:
        # Hide instead of quitting: the backend and tray icon should keep
        # running even if the browser window is closed.
        self.set_visible(False)
        return True

    # -- folder browsing ----------------------------------------------------

    def _on_open_folder_clicked(self, _button) -> None:
        dialog = Gtk.FileDialog(title="Choose a wallpaper folder")
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result) -> None:
        try:
            gfile = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if gfile is None or gfile.get_path() is None:
            return
        folder = Path(gfile.get_path())
        self.waltz_app.config.add_folder(folder)
        self._load_folder(folder)

    def _on_stop_clicked(self, _button) -> None:
        self.waltz_app.stop_wallpaper()

    def _on_autostart_toggled(self, switch, _pspec) -> None:
        enabled = switch.get_active()
        self.waltz_app.set_autostart(enabled)
        self.set_status("Waltz will now launch at login" if enabled else "Autostart disabled")

    def _load_folder(self, folder: Path) -> None:
        self._current_folder = folder
        child = self._flowbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._flowbox.remove(child)
            child = nxt
        self._tiles.clear()

        files = list_media_files(folder)
        if not files:
            self.set_status(f"No supported video/gif files found in {folder}")
            return
        self.set_status(f"{len(files)} file(s) in {folder}")
        for path in files:
            self._add_tile(path)
        self.refresh_active_indicators()

    # -- thumbnail grid -----------------------------------------------------

    def _add_tile(self, path: Path) -> None:
        placeholder = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        placeholder.set_pixel_size(48)
        placeholder.set_size_request(THUMB_DISPLAY_WIDTH, THUMB_DISPLAY_HEIGHT)
        placeholder.set_halign(Gtk.Align.CENTER)
        placeholder.set_valign(Gtk.Align.CENTER)

        frame = Gtk.Frame()
        frame.set_child(placeholder)

        badge = Gtk.Label()
        badge.add_css_class("wallpaper-badge")
        badge.set_halign(Gtk.Align.END)
        badge.set_valign(Gtk.Align.START)
        badge.set_visible(False)

        overlay = Gtk.Overlay()
        overlay.set_child(frame)
        overlay.add_overlay(badge)

        label = Gtk.Label(label=path.name)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(20)
        label.set_wrap(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.append(overlay)
        inner.append(label)

        button = Gtk.Button()
        button.set_has_frame(False)
        button.add_css_class("wallpaper-card")
        button.set_child(inner)
        button.connect("clicked", lambda _b, p=path: self._on_thumbnail_clicked(p))
        self._apply_pointer_cursor(button)

        self._flowbox.append(button)
        self._tiles[str(path.resolve())] = (button, badge)
        self._executor.submit(self._generate_thumbnail, path, frame)

    def _generate_thumbnail(self, path: Path, frame: Gtk.Frame) -> None:
        thumb_path = ensure_thumbnail(path)
        GLib.idle_add(self._apply_thumbnail, frame, thumb_path)

    def _apply_thumbnail(self, frame: Gtk.Frame, thumb_path) -> bool:
        if thumb_path is not None:
            try:
                picture = Gtk.Picture.new_for_filename(str(thumb_path))
                picture.set_content_fit(Gtk.ContentFit.COVER)
                picture.set_size_request(THUMB_DISPLAY_WIDTH, THUMB_DISPLAY_HEIGHT)
                frame.set_child(picture)
            except GLib.Error:
                pass
        return False  # one-shot idle callback

    def _on_thumbnail_clicked(self, path: Path) -> None:
        target = self._active_target()
        kind, value = target
        if kind == "clone":
            self.waltz_app.apply_clone(path)
        elif kind == "span":
            self.waltz_app.apply_span(path)
        else:
            self.waltz_app.apply_wallpaper(path, output=value)

    def _active_target(self) -> Target:
        for button, target in self._target_buttons:
            if button.get_active():
                return target
        return ("clone", None)  # shouldn't happen — the group always has one active

    # -- currently-playing indicators ----------------------------------

    def refresh_active_indicators(self) -> None:
        """Re-check what's actually running (not just what's saved — a
        stopped wallpaper shouldn't still show as playing) and update each
        thumbnail's badge/border plus each monitor segment's subtitle."""
        app = self.waltz_app
        monitors_cfg = app.config.monitors
        mode = app.config.display_mode

        path_to_outputs: Dict[str, List[str]] = {}
        running_paths: Dict[str, str] = {}  # output -> path, only if actually running
        for output, entry in monitors_cfg.items():
            path = entry.get("path")
            if not path or not app.backend.is_running(output):
                continue
            key = str(Path(path).resolve())
            path_to_outputs.setdefault(key, []).append(output)
            running_paths[output] = Path(path).name

        for output, subtitle in self._monitor_subtitles.items():
            subtitle.set_label(running_paths.get(output, "—"))

        for path_key, (button, badge) in self._tiles.items():
            outputs = path_to_outputs.get(path_key)
            if not outputs:
                button.remove_css_class("wallpaper-card-active")
                badge.set_visible(False)
                continue
            button.add_css_class("wallpaper-card-active")
            if mode == "clone" and len(outputs) > 1:
                text = "Clone"
            elif mode == "span" and len(outputs) > 1:
                text = "Span"
            elif len(outputs) == 1:
                text = outputs[0]
            else:
                text = ", ".join(outputs)
            badge.set_label(text)
            badge.set_visible(True)

    # -- status / errors ------------------------------------------------

    def set_status(self, text: str) -> None:
        self._status_label.set_label(text)

    def show_error(self, text: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast(title=text, timeout=5))
        self.set_status(text)
