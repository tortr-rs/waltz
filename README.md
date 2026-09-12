# Waltz

A GUI wallpaper engine for Linux Wayland compositors (niri, Hyprland, Sway),
using [mpvpaper](https://github.com/GhostNaN/mpvpaper) as the rendering
backend. Point it at a folder of your own video/gif files, browse thumbnails,
click one to set it as your wallpaper.

Waltz does not render video itself — it shells out to mpvpaper (which uses
wlr-layer-shell + mpv) and just manages that process per monitor.

## Status

Core loop only, for now: open the GUI, browse a folder's thumbnails, click
one to apply it to your focused/primary monitor, stop it from the tray icon.

Not yet implemented: per-monitor assignment UI, persistence across reboots
(auto-relaunching saved wallpapers on startup), and autostart registration.

## Why this stack

- **Python + GTK4 + libadwaita** for the GUI: native Wayland integration,
  modern widgets (`Gtk.FileDialog`, `Adw.ToolbarView`/`Adw.Toast`) without
  deprecated APIs, and fast iteration speed for a project this size.
- **mpvpaper** as the rendering backend, run as a subprocess — it already
  solves video-as-wallpaper via wlr-layer-shell reliably; reimplementing
  that would be pure risk for no benefit.
- **niri / Hyprland / Sway** monitor detection via each compositor's own
  IPC (`niri msg -j outputs`, `hyprctl -j monitors`, `swaymsg -t
  get_outputs`), auto-detected by whichever responds.
- **AyatanaAppIndicator3** for the tray icon (StatusNotifierItem under the
  hood — the standard approach on Wayland, since classic XEmbed tray icons
  don't work there). It runs in **its own subprocess**, not the main GTK4
  process: AyatanaAppIndicator3 builds its menu with GTK3's `Gtk.Menu`, and
  PyGObject can only load one GTK major version per process. The tray
  helper (`waltz/tray_process.py`) is a small standalone GTK3 script that
  talks to the main app over a session DBus interface
  (`com.waltz.Waltz`, see `waltz/dbus_service.py`) rather than sharing
  memory with it.

## Requirements

System packages (Arch package names shown; adjust for your distro):

- `mpvpaper`
- `ffmpeg`
- `python-gobject`, `gtk4`, `libadwaita`
- `libayatana-appindicator` (or `libappindicator-gtk3` as a fallback)

## Running

```sh
./bin/waltz
```

No installation step needed — it runs directly out of this checkout.
Config lives at `~/.config/waltz/config.json`; thumbnail cache at
`~/.cache/waltz/thumbnails/`.


[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/L6N725GI1V)
