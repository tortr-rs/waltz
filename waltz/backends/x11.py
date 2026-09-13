"""X11 generic backend: embeds mpv into the root window via xwinwrap — the
standard approach video-wallpaper tools use outside Wayland's layer-shell
world (i3, bspwm, Openbox, and any other X11 window manager).

Unlike Wayland, X11 multi-monitor is one shared root window / coordinate
space (via RandR), not one surface per output — so "span" here is just one
process covering the combined virtual-screen geometry, with mpv scaling
into it. No per-output crop math is needed the way wlr_layer_shell needs it.

NOTE: this backend is implemented from xwinwrap's documented usage, not
verified against a live X server — this development environment is
Wayland-only and xwinwrap isn't even packaged for it. Test before relying
on it.
"""

import os
import re
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from ..monitors import Monitor
from .base import BackendUnavailable, WallpaperBackend

# -b: below other windows   -s: sticky (every workspace)   -st/-sp: skip
# taskbar/pager   -nf: never take focus   -ov: override-redirect (the WM
# leaves it alone)   -fdt: force the window to a desktop-type window.
XWINWRAP_FLAGS = ["-b", "-s", "-st", "-sp", "-nf", "-ov", "-fdt"]

SPAN_KEY = "__span__"


def _detect_xrandr() -> List[Monitor]:
    if not shutil.which("xrandr"):
        return []
    try:
        result = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=3)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if result.returncode != 0:
        return []

    line_re = re.compile(
        r"^(?P<name>\S+) connected (?P<primary>primary )?"
        r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>\d+)\+(?P<y>\d+)"
    )
    monitors = []
    for line in result.stdout.splitlines():
        m = line_re.match(line)
        if not m:
            continue  # disconnected, or connected-but-inactive: no geometry
        monitors.append(
            Monitor(
                name=m.group("name"),
                width=int(m.group("w")),
                height=int(m.group("h")),
                x=int(m.group("x")),
                y=int(m.group("y")),
                focused=bool(m.group("primary")),
            )
        )
    return monitors


def _all_xwinwrap_processes() -> List[Tuple[int, str]]:
    """(pid, geometry) for every running xwinwrap process. geometry is the
    raw '-g WxH+X+Y' argument — our stand-in for an output name, since
    xwinwrap has no concept of output names the way mpvpaper does."""
    results = []
    try:
        candidates = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except OSError:
        return results
    for p in candidates:
        try:
            comm = (p / "comm").read_text().strip()
        except OSError:
            continue
        if comm != "xwinwrap":
            continue
        try:
            raw = (p / "cmdline").read_bytes()
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
        geometry = None
        if "-g" in args:
            idx = args.index("-g")
            if idx + 1 < len(args):
                geometry = args[idx + 1]
        results.append((int(p.name), geometry or ""))
    return results


def _direct_child_pids(parent_pid: int) -> List[int]:
    """Scan /proc for processes whose parent is parent_pid. Used to also
    kill the mpv child xwinwrap spawns — killing xwinwrap itself isn't
    guaranteed to take mpv down with it, and we have no way to verify that
    without a live X session to test against."""
    children = []
    try:
        candidates = [p for p in Path("/proc").iterdir() if p.name.isdigit()]
    except OSError:
        return children
    for p in candidates:
        try:
            stat = (p / "stat").read_text()
        except OSError:
            continue
        # comm is parenthesized and may itself contain ')', so split on the
        # LAST ')' to find the fixed-format fields reliably.
        rparen = stat.rfind(")")
        if rparen == -1:
            continue
        fields = stat[rparen + 2:].split()
        if len(fields) < 2:
            continue
        try:
            ppid = int(fields[1])  # fields[0] is state, fields[1] is ppid
        except ValueError:
            continue
        if ppid == parent_pid:
            children.append(int(p.name))
    return children


def _kill_pid_tree(pid: int) -> None:
    for child in _direct_child_pids(pid):
        _kill_pid_tree(child)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class X11Backend(WallpaperBackend):
    name = "xwinwrap + mpv (X11)"

    def __init__(self):
        missing = [t for t in ("xwinwrap", "mpv", "xrandr") if not shutil.which(t)]
        if missing:
            raise BackendUnavailable(
                f"Missing required tool(s) for X11 wallpapers: {', '.join(missing)}."
            )
        self._procs: Dict[str, subprocess.Popen] = {}

    def list_outputs(self) -> List[Monitor]:
        return _detect_xrandr()

    def _kill_at_geometry(self, geometry: str) -> None:
        for pid, geom in _all_xwinwrap_processes():
            if geom == geometry:
                _kill_pid_tree(pid)

    def _launch(self, key: str, geometry: str, path) -> None:
        self.stop(key)
        self._kill_at_geometry(geometry)
        resolved = str(Path(path).expanduser().resolve())
        cmd = [
            "xwinwrap", "-g", geometry, *XWINWRAP_FLAGS, "--",
            "mpv", "-wid", "WID", "--loop", "--no-audio",
            "--panscan=1.0", "--hwdec=auto", resolved,
        ]
        self._procs[key] = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def apply_singular(self, output: str, path, monitors: List[Monitor]) -> None:
        target = next((m for m in monitors if m.name == output), None)
        if target is None:
            raise BackendUnavailable(f"Output {output!r} not found.")
        geometry = f"{target.width}x{target.height}+{target.x}+{target.y}"
        self._launch(output, geometry, path)

    def apply_clone(self, path, monitors: List[Monitor]) -> None:
        # No xwinwrap equivalent of mpvpaper's "ALL" — one process per
        # monitor, each at that monitor's own geometry.
        for m in monitors:
            geometry = f"{m.width}x{m.height}+{m.x}+{m.y}"
            self._launch(m.name, geometry, path)

    def apply_span(self, path, monitors: List[Monitor]) -> None:
        if not monitors:
            raise BackendUnavailable("No monitors detected.")
        min_x = min(m.x for m in monitors)
        min_y = min(m.y for m in monitors)
        max_x = max(m.x + m.width for m in monitors)
        max_y = max(m.y + m.height for m in monitors)
        geometry = f"{max_x - min_x}x{max_y - min_y}+{min_x}+{min_y}"
        self._launch(SPAN_KEY, geometry, path)

    def stop(self, output: str) -> None:
        proc = self._procs.pop(output, None)
        if proc is not None:
            _kill_pid_tree(proc.pid)
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    def stop_all(self) -> None:
        for key in list(self._procs.keys()):
            self.stop(key)
        # also clean up anything stray from a previous unclean run
        for pid, _geometry in _all_xwinwrap_processes():
            _kill_pid_tree(pid)

    def is_running(self, output: str) -> bool:
        proc = self._procs.get(output)
        return proc is not None and proc.poll() is None
