"""Manages mpvpaper as a subprocess: one instance per output.

Waltz never renders video itself — mpvpaper already does that reliably via
wlr-layer-shell. This module just launches/tracks/tears it down per output.

Stopping/replacing is done by scanning /proc for *any* running mpvpaper
process bound to a given output, not just ones this particular manager
instance launched. That matters in practice: mpvpaper may already be
running from a previous Waltz session that didn't exit cleanly, or from a
manual exec-once — without this, play() would stack a new video on top
instead of replacing it.
"""

import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_MPV_OPTIONS = "loop no-audio panscan=1.0 hwdec=auto"
DEFAULT_LAYER = "background"

# mpvpaper accepts the literal output name "ALL" to mean every connected
# output, handled as a single process rather than one per monitor.
ALL_OUTPUTS = "ALL"


def _all_mpvpaper_processes() -> List[Tuple[int, str, str]]:
    """(pid, output, path) for every running mpvpaper process on the system.

    mpvpaper's usage is `mpvpaper [options] <output> <path>` — output and
    path are always the final two positional args, regardless of which
    options preceded them, so args[-2]/args[-1] is reliable.

    This runs on every play/stop/is_running call, so it's worth keeping
    cheap: a desktop session can easily have a few hundred processes, and
    reading /proc/<pid>/cmdline for every one of them is real I/O. /proc/
    <pid>/comm is a much shorter read (just the executable name, kernel-
    truncated to 15 chars — "mpvpaper" fits well within that), so it acts
    as a fast filter before paying for the full cmdline read.
    """
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
        if comm != "mpvpaper":
            continue
        try:
            raw = (p / "cmdline").read_bytes()
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
        if len(args) < 3 or Path(args[0]).name != "mpvpaper":
            continue
        results.append((int(p.name), args[-2], args[-1]))
    return results


def _pids_for_output(output: str) -> List[int]:
    return [pid for pid, out, _ in _all_mpvpaper_processes() if out == output]


def _kill_pid(pid: int) -> None:
    """SIGKILL, not SIGTERM: mpvpaper registers a SIGTERM handler but doesn't
    actually exit on it in practice (confirmed: a cleanly-running, uncontested
    instance was still alive 10s after SIGTERM). SIGKILL can't be caught or
    delayed, so unlike SIGTERM there's nothing to wait out here — no polling
    needed (polling for the pid to disappear from /proc is actually wrong
    anyway: a killed-but-not-yet-reaped process still shows up as a zombie,
    so it would just time out every time regardless of how fast it died)."""
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class MpvpaperManager:
    def __init__(self):
        self._procs: Dict[str, subprocess.Popen] = {}

    def is_running(self, output: str) -> bool:
        # an ALL process covers every output, this one included
        return bool(_pids_for_output(output)) or bool(_pids_for_output(ALL_OUTPUTS))

    def outputs(self) -> List[str]:
        return sorted({out for _, out, _ in _all_mpvpaper_processes()})

    def play(
        self,
        output: str,
        path,
        mpv_options: str = DEFAULT_MPV_OPTIONS,
        layer: str = DEFAULT_LAYER,
    ) -> None:
        """Launch on a single output (singular mode)."""
        resolved = str(Path(path).expanduser().resolve())
        self.stop(output)
        cmd = ["mpvpaper", "-o", mpv_options, "-l", layer, output, resolved]
        self._procs[output] = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def play_all(
        self,
        path,
        mpv_options: str = DEFAULT_MPV_OPTIONS,
        layer: str = DEFAULT_LAYER,
    ) -> None:
        """Launch one mpvpaper process bound to every connected output at
        once (clone mode) via mpvpaper's own 'ALL' output name, instead of
        one process per monitor. Since it claims every output, it needs a
        clean slate first — any existing per-output or ALL process would
        otherwise conflict with it."""
        resolved = str(Path(path).expanduser().resolve())
        self.stop_all()
        cmd = ["mpvpaper", "-o", mpv_options, "-l", layer, ALL_OUTPUTS, resolved]
        self._procs[ALL_OUTPUTS] = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def stop(self, output: str) -> None:
        tracked = [
            proc
            for proc in (self._procs.pop(output, None), self._procs.pop(ALL_OUTPUTS, None))
            if proc is not None
        ]
        for pid in _pids_for_output(output) + _pids_for_output(ALL_OUTPUTS):
            _kill_pid(pid)
        # reap our own children so they don't linger as zombies; SIGKILL
        # already killed them, so this returns essentially instantly
        for proc in tracked:
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    def stop_all(self) -> None:
        for pid, _output, _path in _all_mpvpaper_processes():
            _kill_pid(pid)
        for proc in self._procs.values():
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        self._procs.clear()
