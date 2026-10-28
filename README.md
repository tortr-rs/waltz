# Waltz

A GUI wallpaper engine for Linux. Point it at a folder of videos, gifs,
pictures or shaders, browse thumbnails, click one to set it as your
wallpaper: per monitor, cloned to every monitor, or spanned across all of
them. Or shuffle the whole folder.

**[Download the latest release](https://github.com/tortr-rs/waltz/releases/latest)**
— extract the tarball and run `./scripts/install.sh`.

## Status

Working: folder browsing with cached thumbnails, per-monitor assignment via
a segmented target strip (Singular/Clone/Span), a "currently playing"
indicator on the grid, startup persistence (relaunches your saved wallpaper
automatically), opt-in autostart at login, and a tray icon (open/stop/quit).

New in 0.3:

- **Pauses by itself** when every monitor is covered (a fullscreen game, a
  maximized window) or the laptop runs on battery. Nothing is decoded or
  drawn while paused; measured 0 CPU ticks covered vs. 14 per 5 s visible.
- **Pictures** (jpg, png, webp, avif, jxl...), cropped to fill the screen.
- **Shaders**: Shadertoy-style `.frag`/`.glsl` files, drawn live. Two come
  with Waltz in `shaders/` (aqua bubbles, aurora).
- **Shuffle Folder**: the whole folder in random order, a new one every 5
  minutes (`WALTZER_EVERY=SECONDS` changes it).
- **Span**: one video across every monitor, from a single decode.
- **GNOME** (through Hanabi) and **KDE Plasma** (Waltz's own wallpaper plugin).
- A new frutiger aero look.

## Backends

Waltz detects the session (`$XDG_SESSION_TYPE`/`$XDG_CURRENT_DESKTOP`) and
picks a backend behind a common interface (`waltz/backends/`) — it doesn't
assume one approach works everywhere:

- **wlroots compositors (niri, Hyprland, Sway, ...)** — **waltzer-white**
  (`waltzer-white/`), Waltz's own minimal Rust renderer: libmpv's render API
  for decode, raw `wayland-client` + `wayland-protocols-wlr` for
  wlr-layer-shell-unstable-v1 background surfaces, EGL for the GL context.
  Deliberately has **no option passthrough** — CLI is just
  `waltzer-white <path> <output>[@X,Y,W,H] ...`, hardware decode/loop/mute
  hardcoded. The path can be a video, picture, folder or shader. A single
  process shares one decode across every output it's given, so Clone mode
  costs about the same memory for N monitors as for one. With `@X,Y,W,H`
  on every output it draws once at desktop size and each output shows its
  slice: that's Span.
- **Generic X11 (i3, bspwm, Openbox, ...)** — `xwinwrap` + `mpv`, embedding
  into the root window, `xrandr` for monitor geometry. Implemented from
  xwinwrap's documented usage; not verified against a live X server (this
  project was built on a Wayland-only machine).
- **GNOME** — through the [Hanabi](https://github.com/jeffshee/gnome-ext-hanabi)
  Shell extension, set with `gsettings` (Mutter has no wlr-layer-shell).
  Install Hanabi first; Waltz says so if it's missing. One video on every
  monitor, no Span, no shaders. Folders use Hanabi's own rotation.
- **KDE Plasma** — Waltz's own Plasma 6 wallpaper plugin (`plasma/`), copied
  to `~/.local/share/plasma/wallpapers` and switched to live through
  plasmashell's scripting interface, no restart. Videos and pictures per
  screen or cloned; no Span, shaders or shuffle yet.

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
- `qt6-multimedia` — only on KDE Plasma, for the wallpaper plugin
- the Hanabi extension — only on GNOME
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
