"""Manages waltzer-white (Waltz's own minimal Rust renderer) as a
subprocess. A single process can now cover multiple outputs at once (one
shared decode, rendered to each output's own surface) — used for Clone, so
N monitors showing the same file cost one process instead of N.

CLI contract: `waltzer-white <video-path> <output1> [output2] ...` — path
first, then one or more output names. Singular mode is just the
single-output case of the same interface.

Also treats leftover mpvpaper processes as strays to clean up: mpvpaper is
fully retired as a backend, so any mpvpaper process still running is a
leftover from before that migration, not something to coexist with.
"""

import os
import signal
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

# waltz/waltzerwhite_backend.py -> <project root>/waltzer-white/target/release/waltzer-white
BINARY_PATH = (
    Path(__file__).resolve().parent.parent
    / "waltzer-white"
    / "target"
    / "release"
    / "waltzer-white"
)


def _all_waltzerwhite_processes() -> List[Tuple[int, str, List[str]]]:
    """(pid, path, outputs) for every running waltzer-white process."""
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
        if comm != "waltzer-white":
            continue
        try:
            raw = (p / "cmdline").read_bytes()
        except OSError:
            continue
        args = [a.decode(errors="replace") for a in raw.split(b"\0") if a]
        if len(args) < 3:
            continue  # not a fully-formed invocation (path + >=1 output)
        results.append((int(p.name), args[1], args[2:]))
    return results


def _mpvpaper_processes() -> List[Tuple[int, str]]:
    """(pid, output) for any leftover mpvpaper process — see module docstring."""
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
        if len(args) < 3:
            continue
        results.append((int(p.name), args[-2]))
    return results


def _pids_for_output(output: str) -> List[int]:
    """Any waltzer-white OR leftover mpvpaper process bound to this output."""
    pids = [pid for pid, _path, outs in _all_waltzerwhite_processes() if output in outs]
    pids += [pid for pid, out in _mpvpaper_processes() if out == output]
    return pids


def _kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class WaltzerWhiteManager:
    def __init__(self):
        self._procs: Dict[Tuple[str, ...], subprocess.Popen] = {}

    def is_running(self, output: str) -> bool:
        return bool(_pids_for_output(output))

    def outputs(self) -> List[str]:
        names = set()
        for _pid, _path, outs in _all_waltzerwhite_processes():
            names.update(outs)
        names.update(out for _pid, out in _mpvpaper_processes())
        return sorted(names)

    def play(self, outputs: List[str], path) -> None:
        """Launch one process rendering `path` to every output in `outputs`
        (a single output is the Singular case; several is Clone)."""
        if not BINARY_PATH.exists():
            raise FileNotFoundError(str(BINARY_PATH))
        resolved = str(Path(path).expanduser().resolve())
        for output in outputs:
            self.stop(output)
        key = tuple(sorted(outputs))
        self._procs[key] = subprocess.Popen(
            [str(BINARY_PATH), resolved, *outputs],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def stop(self, output: str) -> None:
        # Drop any tracked entry whose output set includes this one — a
        # multi-output (Clone) process only has one Popen to reap, but it
        # may be tracked under a key alongside other outputs.
        for key in [k for k in self._procs if output in k]:
            tracked = self._procs.pop(key)
            try:
                tracked.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        for pid in _pids_for_output(output):
            _kill_pid(pid)

    def stop_all(self) -> None:
        for pid, _path, _outs in _all_waltzerwhite_processes():
            _kill_pid(pid)
        for pid, _output in _mpvpaper_processes():
            _kill_pid(pid)
        for proc in self._procs.values():
            try:
                proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        self._procs.clear()
