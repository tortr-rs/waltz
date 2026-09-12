"""Persisted Waltz configuration: known folders and per-monitor wallpaper assignments.

This only persists state to disk; it does not (yet) relaunch mpvpaper on
startup or touch compositor autostart config — that's a follow-up milestone.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .paths import config_file

CONFIG_VERSION = 1

DISPLAY_MODES = ("singular", "clone", "span")


class Config:
    def __init__(self, data: dict = None):
        self._data = data if data is not None else self._defaults()

    @staticmethod
    def _defaults() -> dict:
        return {
            "version": CONFIG_VERSION,
            "folders": [],
            "display_mode": "singular",
            "source_path": None,
            "monitors": {},
        }

    @classmethod
    def load(cls) -> "Config":
        path = config_file()
        if path.exists():
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                data.setdefault("folders", [])
                data.setdefault("monitors", {})
                data.setdefault("display_mode", "singular")
                data.setdefault("source_path", None)
                data.setdefault("version", CONFIG_VERSION)
                return cls(data)
            except (json.JSONDecodeError, OSError):
                pass
        return cls()

    def save(self) -> None:
        path = config_file()
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        tmp.replace(path)

    @property
    def folders(self) -> List[str]:
        return list(self._data.get("folders", []))

    def add_folder(self, folder) -> None:
        folder = str(folder)
        folders = self._data.setdefault("folders", [])
        if folder in folders:
            folders.remove(folder)
        folders.append(folder)
        self.save()

    def remove_folder(self, folder) -> None:
        folder = str(folder)
        folders = self._data.get("folders", [])
        if folder in folders:
            folders.remove(folder)
            self.save()

    @property
    def monitors(self) -> Dict[str, dict]:
        return dict(self._data.get("monitors", {}))

    @property
    def display_mode(self) -> str:
        return self._data.get("display_mode", "singular")

    @property
    def source_path(self) -> Optional[str]:
        return self._data.get("source_path")

    def set_monitor_wallpaper(self, output: str, path, mpv_options: str) -> None:
        """Assign one output independently (singular mode). Breaks any
        previously-recorded clone/span linkage, since the outputs are no
        longer all derived from one shared source."""
        self._data.setdefault("monitors", {})[output] = {
            "path": str(path),
            "mpv_options": mpv_options,
        }
        self._data["display_mode"] = "singular"
        self._data["source_path"] = None
        self.save()

    def set_all_monitors(self, assignments: Dict[str, dict], mode: str, source_path) -> None:
        """Replace every output's assignment at once (clone/span mode), recording
        the shared source path so the linkage can be replayed/recomputed later."""
        if mode not in DISPLAY_MODES:
            raise ValueError(f"unknown display mode: {mode!r}")
        self._data["monitors"] = dict(assignments)
        self._data["display_mode"] = mode
        self._data["source_path"] = str(source_path) if source_path else None
        self.save()

    def clear_monitor_wallpaper(self, output: str) -> None:
        if output in self._data.get("monitors", {}):
            del self._data["monitors"][output]
            self.save()
