# Waltz

A GUI wallpaper engine for Linux. Point it at a folder of your own video/gif
files, browse thumbnails, click one to set it as your wallpaper — per
monitor, or cloned to every monitor at once.

**[Download the latest release](https://github.com/tortr-rs/waltz/releases/latest)**
— extract the tarball and run `./scripts/install.sh`.

## Status

Working: folder browsing with cached thumbnails, per-monitor assignment via
a segmented target strip (Singular/Clone/Span), a "currently playing"
indicator on the grid, startup persistence (relaunches your saved wallpaper
automatically), opt-in autostart at login, and a tray icon (open/stop/quit).

Not yet implemented: GNOME and KDE support (see below — researched, not
wired up), and Span mode on the new Rust backend (see below).

## Backends

Waltz detects the session (`$XDG_SESSION_TYPE`/`$XDG_CURRENT_DESKTOP`) and
picks a backend behind a common interface (`waltz/backends/`) — it doesn't
assume one approach works everywhere:

- **wlroots compositors (niri, Hyprland, Sway, ...)** — **waltzer-white**
  (`waltzer-white/`), Waltz's own minimal Rust renderer: libmpv's render API
  for decode, raw `wayland-client` + `wayland-protocols-wlr` for
  wlr-layer-shell-unstable-v1 background surfaces, EGL for the GL context.
  Deliberately has **no option passthrough** — CLI is just
  `waltzer-white <path> <output1> [output2 ...]`, hardware decode/loop/mute
  hardcoded. A single process shares one decode across every output it's
  given, so Clone mode costs about the same memory for N monitors as for
  one. That no-passthrough tradeoff means it can't yet do Span mode's
  per-monitor crop filters; Singular and Clone work fully.
- **Generic X11 (i3, bspwm, Openbox, ...)** — `xwinwrap` + `mpv`, embedding
  into the root window, `xrandr` for monitor geometry. Implemented from
  xwinwrap's documented usage; not verified against a live X server (this
  project was built on a Wayland-only machine).
- **GNOME** — not supported yet. Mutter doesn't implement wlr-layer-shell
  (an open GNOME feature request with no timeline). The real path forward
  is the [Hanabi](https://github.com/jeffshee/gnome-ext-hanabi) GNOME Shell
  extension (genuinely does video wallpapers on GNOME Wayland, scriptable
  via `gsettings`) — not wired up, since it requires the user to already
  have it installed/enabled and doesn't support multiple monitors yet.
- **KDE Plasma** — not supported yet. The closest option is the
  [Smart Video Wallpaper Reborn](https://github.com/luisbocanegra/plasma-smart-video-wallpaper-reborn)
  plugin, but it has no DBus/CLI control — only a config file that needs
  `plasmashell` restarted (a disruptive full-shell reload) to pick up
  changes. Waltz tells GNOME/KDE users this directly rather than silently
  failing.

## Why this stack

- **Python + GTK4 + libadwaita** for the GUI: native Wayland integration,
  modern widgets, fast iteration speed for a project this size.
- **waltzer-white** (Rust) instead of shelling out to `mpvpaper` for
  wlroots compositors: full control over the process without depending on
  a third-party tool, at the cost of writing (and re-verifying) the
  Wayland/EGL/mpv integration ourselves. `mpvpaper` was the original
  backend and proved the approach; waltzer-white replaces it now that it's
  built and tested. It also tunes software-decode fallback
  (`vd-lavc-threads=1`, a no-op when hardware decode actually works) —
  measured ~28% lower memory versus default multi-threaded software
  decode on hardware without a working `hwdec` path.
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

- `ffmpeg` — thumbnail extraction
- `python-gobject`, `gtk4`, `libadwaita` — the GUI
- `libayatana-appindicator` (or `libappindicator-gtk3` as a fallback) — the tray icon
- `rust` (`cargo`/`rustc`) — to build `waltzer-white`; not needed once it's built
- `xwinwrap`, `xrandr` — only if you're on generic X11, not a wlroots compositor

`mpvpaper` is no longer a dependency — waltzer-white replaced it on
wlroots compositors.

## Running

From a [release tarball](https://github.com/tortr-rs/waltz/releases/latest):

```sh
tar xzf waltz-*.tar.gz && cd waltz-*/
./scripts/install.sh
```

From this checkout, without installing anywhere:

```sh
cd waltzer-white && cargo build --release && cd ..
./bin/waltz
```

No installation step needed beyond building waltzer-white once — Waltz
runs directly out of this checkout. Config lives at
`~/.config/waltz/config.json`; thumbnail cache at
`~/.cache/waltz/thumbnails/`.


[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/L6N725GI1V)
