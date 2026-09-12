"""Thumbnail extraction via ffmpeg, cached on disk by content fingerprint.

We deliberately grab one still frame per file rather than live-previewing
every clip in the grid — cheap, and good enough to recognize a wallpaper.
"""

import hashlib
import subprocess
from pathlib import Path
from typing import List, Optional

from .paths import thumbnail_dir

THUMB_WIDTH = 320

SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".gif", ".m4v"}


def list_media_files(folder) -> List[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def _cache_key(path: Path) -> str:
    st = path.stat()
    raw = f"{path}|{st.st_size}|{st.st_mtime_ns}"
    return hashlib.sha256(raw.encode()).hexdigest()


def thumbnail_path_for(path: Path) -> Path:
    return thumbnail_dir() / f"{_cache_key(Path(path))}.jpg"


def ensure_thumbnail(path, seek: str = "00:00:01") -> Optional[Path]:
    """Extract (and cache) a thumbnail frame. Blocking — call from a worker thread."""
    path = Path(path)
    out = thumbnail_path_for(path)
    if out.exists():
        return out

    for attempt_seek in (seek, "00:00:00"):
        cmd = [
            "ffmpeg", "-y", "-ss", attempt_seek, "-i", str(path),
            "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-1",
            str(out),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
        if result.returncode == 0 and out.exists():
            return out
    return None
