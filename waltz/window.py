"""Main Waltz window: folder picker + thumbnail grid."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Pango

from .thumbnails import ensure_thumbnail, list_media_files

THUMB_DISPLAY_WIDTH = 200
THUMB_DISPLAY_HEIGHT = THUMB_DISPLAY_WIDTH * 9 // 16


class WaltzWindow(Adw.ApplicationWindow):
    def __init__(self, waltz_app, **kwargs):
        super().__init__(**kwargs)
        self.waltz_app = waltz_app
        self.set_title("Waltz")
        self.set_default_size(900, 650)

        self._executor = ThreadPoolExecutor(max_workers=4)
        self._current_folder: Path | None = None

        toolbar_view = Adw.ToolbarView()
        header = Adw.HeaderBar()

        open_button = Gtk.Button(label="Open Folder")
        open_button.connect("clicked", self._on_open_folder_clicked)
        header.pack_start(open_button)

        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self._monitor_names = [m.name for m in waltz_app.list_monitors()]
        self._mode_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new(["Singular", "Clone", "Span"])
        )
        self._mode_dropdown.set_selected(0)
        self._mode_dropdown.set_tooltip_text(
            "Singular: one video per monitor\n"
            "Clone: the same video mirrored on every monitor\n"
            "Span: one video stretched across all monitors combined"
        )
        self._mode_dropdown.connect("notify::selected", self._on_mode_changed)
        mode_box.append(self._mode_dropdown)

        monitor_labels = self._monitor_names or ["(auto)"]
        self._monitor_dropdown = Gtk.DropDown(model=Gtk.StringList.new(monitor_labels))
        self._monitor_dropdown.set_selected(0)
        self._monitor_dropdown.set_tooltip_text("Target monitor for Singular mode")
        mode_box.append(self._monitor_dropdown)

        header.pack_start(mode_box)

        stop_button = Gtk.Button(label="Stop Wallpaper")
        stop_button.add_css_class("destructive-action")
        stop_button.connect("clicked", self._on_stop_clicked)
        header.pack_end(stop_button)

        toolbar_view.add_top_bar(header)

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

    # -- window lifecycle -------------------------------------------------

    def _on_close_request(self, _window) -> bool:
        # Hide instead of quitting: mpvpaper and the tray icon should keep
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

    def _on_mode_changed(self, dropdown, _pspec) -> None:
        self._monitor_dropdown.set_visible(dropdown.get_selected() == 0)

    def _load_folder(self, folder: Path) -> None:
        self._current_folder = folder
        child = self._flowbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._flowbox.remove(child)
            child = nxt

        files = list_media_files(folder)
        if not files:
            self.set_status(f"No supported video/gif files found in {folder}")
            return
        self.set_status(f"{len(files)} file(s) in {folder}")
        for path in files:
            self._add_tile(path)

    # -- thumbnail grid -----------------------------------------------------

    def _add_tile(self, path: Path) -> None:
        placeholder = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
        placeholder.set_pixel_size(48)
        placeholder.set_size_request(THUMB_DISPLAY_WIDTH, THUMB_DISPLAY_HEIGHT)
        placeholder.set_halign(Gtk.Align.CENTER)
        placeholder.set_valign(Gtk.Align.CENTER)

        frame = Gtk.Frame()
        frame.set_child(placeholder)

        label = Gtk.Label(label=path.name)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(20)
        label.set_wrap(False)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.append(frame)
        inner.append(label)

        button = Gtk.Button()
        button.set_has_frame(False)
        button.set_child(inner)
        button.connect("clicked", lambda _b, p=path: self._on_thumbnail_clicked(p))

        self._flowbox.append(button)
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
        mode = self._mode_dropdown.get_selected()
        if mode == 1:
            self.waltz_app.apply_clone(path)
        elif mode == 2:
            self.waltz_app.apply_span(path)
        else:
            self.waltz_app.apply_wallpaper(path, output=self._selected_monitor_name())

    def _selected_monitor_name(self) -> str | None:
        if not self._monitor_names:
            return None
        idx = self._monitor_dropdown.get_selected()
        if idx < 0 or idx >= len(self._monitor_names):
            return None
        return self._monitor_names[idx]

    # -- status / errors ------------------------------------------------

    def set_status(self, text: str) -> None:
        self._status_label.set_label(text)

    def show_error(self, text: str) -> None:
        self._toast_overlay.add_toast(Adw.Toast(title=text, timeout=5))
        self.set_status(text)
