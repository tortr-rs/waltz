"""KDE Plasma backend: Waltz's own Plasma wallpaper plugin
(plasma/com.waltz.wallpaper, QtMultimedia), switched to through
plasmashell's scripting interface (org.kde.PlasmaShell.evaluateScript) — the
same thing Plasma's own wallpaper dialog does, so changes apply live, no
plasmashell restart.

Screens are named "Screen 1", "Screen 2"... in Plasma's own order: the
scripting API knows screens by number, not by connector name.
"""

import ast
import json
import shutil
import subprocess
from pathlib import Path
from typing import List

from ..monitors import Monitor
from .base import BackendUnavailable, WallpaperBackend

PLUGIN = "com.waltz.wallpaper"
# waltz/backends/kde.py -> <project root>/plasma/com.waltz.wallpaper
PLUGIN_SRC = Path(__file__).resolve().parent.parent.parent / "plasma" / PLUGIN
PLUGIN_DST = Path.home() / ".local/share/plasma/wallpapers" / PLUGIN


def _script(js: str) -> str:
    try:
        r = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.kde.plasmashell",
             "--object-path", "/PlasmaShell", "--method",
             "org.kde.PlasmaShell.evaluateScript", js],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise BackendUnavailable(f"Couldn't talk to plasmashell: {e}")
    if r.returncode != 0:
        raise BackendUnavailable(f"plasmashell refused the change: {r.stderr.strip()}")
    # gdbus prints ('what the script printed\n',)
    try:
        return ast.literal_eval(r.stdout.strip())[0].strip()
    except (ValueError, SyntaxError, IndexError):
        return ""


def _screen(name: str) -> int:
    return int(name.rsplit(" ", 1)[-1]) - 1


class KdeBackend(WallpaperBackend):
    name = "Plasma wallpaper plugin"

    def __init__(self):
        if not shutil.which("gdbus"):
            raise BackendUnavailable("gdbus is missing (it comes with glib).")
        if not PLUGIN_SRC.is_dir():
            raise BackendUnavailable(f"Waltz's Plasma plugin is missing from {PLUGIN_SRC}.")
        self._install_plugin()

    def _install_plugin(self) -> None:
        # a copy in the user's plasma dir, refreshed when waltz's own changes
        src = (PLUGIN_SRC / "metadata.json").read_text()
        dst = PLUGIN_DST / "metadata.json"
        if dst.exists() and dst.read_text() == src and \
                (PLUGIN_DST / "contents/ui/main.qml").read_text() == (PLUGIN_SRC / "contents/ui/main.qml").read_text():
            return
        shutil.rmtree(PLUGIN_DST, ignore_errors=True)
        PLUGIN_DST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(PLUGIN_SRC, PLUGIN_DST)

    def list_outputs(self) -> List[Monitor]:
        out = _script(
            "var o = []; for (var i = 0; i < screenCount; i++) { var g = screenGeometry(i);"
            " o.push([i, g.width, g.height, g.x, g.y]); } print(JSON.stringify(o));"
        )
        try:
            screens = json.loads(out)
        except json.JSONDecodeError:
            return []
        return [Monitor(f"Screen {i + 1}", int(w), int(h), int(x), int(y)) for i, w, h, x, y in screens]

    def _set(self, screens: List[int], plugin: str, url: str = "") -> None:
        js = (
            "var want = %s; var ds = desktops();"
            "for (var i = 0; i < ds.length; i++) { var d = ds[i];"
            " if (want.length && want.indexOf(d.screen) < 0) continue;"
            " d.wallpaperPlugin = %s;"
            " if (%s) { d.currentConfigGroup = ['Wallpaper', %s, 'General']; d.writeConfig('Video', %s); } }"
        ) % (json.dumps(screens), json.dumps(plugin), json.dumps(bool(url)), json.dumps(PLUGIN), json.dumps(url))
        _script(js)

    def _check(self, path) -> None:
        p = Path(path)
        if p.is_dir():
            raise BackendUnavailable("Shuffling a folder isn't supported on Plasma yet.")
        if p.suffix.lower() in (".frag", ".glsl", ".shader"):
            raise BackendUnavailable("Shader wallpapers aren't supported on Plasma yet.")

    def apply_singular(self, output, path, monitors) -> None:
        self._check(path)
        self._set([_screen(output)], PLUGIN, Path(path).expanduser().resolve().as_uri())

    def apply_clone(self, path, monitors) -> None:
        self._check(path)
        self._set([], PLUGIN, Path(path).expanduser().resolve().as_uri())

    def apply_span(self, path, monitors) -> None:
        raise BackendUnavailable("Span mode isn't supported on Plasma yet.")

    def stop(self, output: str) -> None:
        # back to Plasma's picture wallpaper, which still has its own settings
        if self.is_running(output):
            self._set([_screen(output)], "org.kde.image")

    def stop_all(self) -> None:
        for m in self.list_outputs():
            self.stop(m.name)

    def is_running(self, output: str) -> bool:
        out = _script(
            "var ds = desktops(); for (var i = 0; i < ds.length; i++)"
            " if (ds[i].screen == %d) print(ds[i].wallpaperPlugin);" % _screen(output)
        )
        return out.strip() == PLUGIN
