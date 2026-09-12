"""Crop math for 'span' mode: one video stretched across the combined
desktop, with each monitor's mpvpaper instance rendering only its own slice.

mpvpaper binds one process to one output, so spanning is done by scaling
the source to the bounding box of all monitors and having each output's
mpv instance crop out its own region via mpv's native crop filter — no
separate ffmpeg pre-processing needed, it's forwarded through the same
free-form mpv_options string play() already accepts.
"""

from typing import Dict, List

from .monitors import Monitor

BASE_SPAN_MPV_OPTIONS = "loop no-audio hwdec=auto"


def compute_span_options(monitors: List[Monitor]) -> Dict[str, str]:
    """output name -> mpv_options string that scales+crops the shared source
    to that output's slice of the combined bounding box of all monitors."""
    if not monitors:
        return {}

    min_x = min(m.x for m in monitors)
    min_y = min(m.y for m in monitors)
    max_x = max(m.x + m.width for m in monitors)
    max_y = max(m.y + m.height for m in monitors)
    total_w = max_x - min_x
    total_h = max_y - min_y

    options = {}
    for m in monitors:
        crop_x = m.x - min_x
        crop_y = m.y - min_y
        # setdar is required: mpv keeps the *source* stream's aspect ratio as
        # display-size metadata even after scale+crop change the actual pixel
        # aspect, which silently squeezes the picture instead of showing the
        # intended stretch. Stamping the crop's own W:H as the DAR is what
        # makes mpv actually render the cropped pixels as-is.
        vf = (
            f"vf=scale={total_w}:{total_h},"
            f"crop={m.width}:{m.height}:{crop_x}:{crop_y},"
            f"setdar={m.width}/{m.height}"
        )
        options[m.name] = f"{BASE_SPAN_MPV_OPTIONS} {vf}"
    return options


def has_mismatched_geometry(monitors: List[Monitor]) -> bool:
    """True when monitors differ enough in resolution that a naive span
    (one scaled canvas, sliced by logical position) is likely to look
    misaligned or distorted — worth warning about rather than silently
    producing a bad result."""
    if len(monitors) < 2:
        return False
    heights = {m.height for m in monitors}
    widths = {m.width for m in monitors}
    return len(heights) > 1 or len(widths) > 1
