"""Monitor/output detection across wlroots-ish Wayland compositors.

Tries each compositor's own IPC in turn and uses whichever one actually
answers. Niri, Hyprland, and Sway all expose enough JSON to build a
normalized Monitor list that matches the output names mpvpaper expects.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Monitor:
    name: str
    width: int
    height: int
    x: int
    y: int
    focused: bool = False


def _run_json(cmd: List[str]):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _detect_niri() -> Optional[List[Monitor]]:
    if not shutil.which("niri"):
        return None
    data = _run_json(["niri", "msg", "-j", "outputs"])
    if not data:
        return None
    focused = _run_json(["niri", "msg", "-j", "focused-output"])
    focused_name = focused.get("name") if focused else None
    monitors = []
    for name, info in data.items():
        logical = info.get("logical") or {}
        if not logical:
            continue  # output exists but is disabled/disconnected
        monitors.append(
            Monitor(
                name=name,
                width=logical.get("width", 0),
                height=logical.get("height", 0),
                x=logical.get("x", 0),
                y=logical.get("y", 0),
                focused=(name == focused_name),
            )
        )
    return monitors or None


def _detect_hyprland() -> Optional[List[Monitor]]:
    if not shutil.which("hyprctl") or not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return None
    data = _run_json(["hyprctl", "-j", "monitors"])
    if not data:
        return None
    monitors = [
        Monitor(
            name=m.get("name", ""),
            width=m.get("width", 0),
            height=m.get("height", 0),
            x=m.get("x", 0),
            y=m.get("y", 0),
            focused=bool(m.get("focused")),
        )
        for m in data
    ]
    return monitors or None


def _detect_sway() -> Optional[List[Monitor]]:
    if not shutil.which("swaymsg") or not os.environ.get("SWAYSOCK"):
        return None
    data = _run_json(["swaymsg", "-t", "get_outputs"])
    if not data:
        return None
    monitors = []
    for m in data:
        if not m.get("active", True):
            continue
        rect = m.get("rect", {})
        monitors.append(
            Monitor(
                name=m.get("name", ""),
                width=rect.get("width", 0),
                height=rect.get("height", 0),
                x=rect.get("x", 0),
                y=rect.get("y", 0),
                focused=bool(m.get("focused")),
            )
        )
    return monitors or None


_BACKENDS = (_detect_niri, _detect_hyprland, _detect_sway)


def detect_monitors() -> List[Monitor]:
    for backend in _BACKENDS:
        monitors = backend()
        if monitors:
            return monitors
    return []


def get_primary_monitor(monitors: Optional[List[Monitor]] = None) -> Optional[Monitor]:
    monitors = detect_monitors() if monitors is None else monitors
    if not monitors:
        return None
    for m in monitors:
        if m.focused:
            return m
    return monitors[0]
