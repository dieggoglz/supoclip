"""Video inserted over a clip, under its captions (Diego, 30 Oct: the montage of bettereverydayclips).

Files live in INSERTS_DIR, a folder clip-ops shares with the container, and are named, never given as paths.
Kinds: "pantalla" cuts to the insert full screen; "fundido" blends it over the picture in screen mode, so its
black background vanishes (money falling over the speaker). Both need the same size and rate as the clip.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .common import OUTPUT_FPS
from .ffmpeg import build_final_video_encode_args, run_ffmpeg_command, subtitles_filter_fragment

INSERTS_DIR = Path("/app/inserts")
INSERT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(mp4|mov|webm)$")
INSERT_KINDS = ("pantalla", "fundido")
MAX_INSERTS = 12
MIN_INSERT_SECONDS = 0.2
FILL = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,setsar=1"


def validate_inserts(raw: Any, clip_seconds: float) -> List[Dict[str, Any]]:
    """Normalised inserts in clip seconds, in order, without overlaps. Raises ValueError."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list) or len(raw) > MAX_INSERTS:
        raise ValueError(f"inserts must be a list of at most {MAX_INSERTS}")
    clean = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each insert must be an object")
        name, kind = item.get("file"), item.get("kind", "pantalla")
        if not isinstance(name, str) or not INSERT_NAME.match(name):
            raise ValueError(f"invalid insert file: {name!r}")
        if kind not in INSERT_KINDS:
            raise ValueError(f"invalid insert kind: {kind!r}")
        try:
            start, end, skip = float(item["start"]), float(item["end"]), float(item.get("from", 0))
        except (KeyError, TypeError, ValueError):
            raise ValueError("insert needs numeric start and end") from None
        if not 0 <= start < end <= clip_seconds + 0.5 or skip < 0:
            raise ValueError(f"insert out of range: {start}-{end}")
        clean.append({"file": name, "kind": kind, "start": start, "end": min(end, clip_seconds), "from": skip})
    clean.sort(key=lambda i: i["start"])
    if any(a["end"] > b["start"] for a, b in zip(clean, clean[1:])):
        raise ValueError("inserts overlap")
    return clean


def clip_time(seconds: float, start: float, ranges: Sequence[Tuple[float, float]], fade: float = 0.0) -> float:
    """Where a moment of the uncut segment plays in the final clip, which lost its long pauses and shares `fade`
    seconds at each cut. `seconds` counts from the segment's `start`; a moment in a removed pause goes to what follows."""
    moment, elapsed = start + seconds, 0.0
    for range_start, range_end in ranges:
        if moment < range_end:
            return elapsed + max(0.0, moment - range_start)
        elapsed += range_end - range_start - fade
    return elapsed + fade


def inserts_on_timeline(
    inserts: Sequence[Dict[str, Any]], start: float, ranges: Sequence[Tuple[float, float]], fade: float = 0.0
) -> List[Dict[str, Any]]:
    """Inserts come timed against the transcript, so they land on their word after the pauses are cut.
    One left with nothing to cover is dropped."""
    placed = []
    for insert in inserts:
        a, b = clip_time(insert["start"], start, ranges, fade), clip_time(insert["end"], start, ranges, fade)
        if b - a >= MIN_INSERT_SECONDS:
            placed.append({**insert, "start": a, "end": b})
    return placed


def build_inserts_filter(inserts: Sequence[Dict[str, Any]], subs: Optional[str]) -> str:
    """filter_complex over input 0 (the framed clip) and one input per insert, giving [v]."""
    chain = [f"[0:v]fps={OUTPUT_FPS}[c0]"]
    last = "c0"
    for n, insert in enumerate(inserts, 1):
        length = insert["end"] - insert["start"]
        trimmed = f"[{n}:v]trim=start={insert['from']:.3f}:duration={length:.3f},setpts=PTS-STARTPTS,{FILL},fps={OUTPUT_FPS}"
        if insert["kind"] == "fundido":
            # Black until its time and after it: the screen blend leaves the picture untouched there
            chain.append(
                f"{trimmed},format=gbrp,tpad=start_duration={insert['start']:.3f}:start_mode=add:color=black"
                f":stop_duration=3600:stop_mode=add[i{n}]"
            )
            chain.append(f"[{last}]format=gbrp[b{n}]")
            chain.append(f"[b{n}][i{n}]blend=all_mode=screen:shortest=1,format=yuv420p[c{n}]")
        else:
            chain.append(f"{trimmed},setpts=PTS+{insert['start']:.3f}/TB[i{n}]")
            chain.append(f"[{last}][i{n}]overlay=eof_action=pass[c{n}]")
        last = f"c{n}"
    tail = f",{subs}" if subs else ""
    chain.append(f"[{last}]format=yuv420p{tail}[v]")
    return ";".join(chain)


def apply_inserts(
    video: Path,
    output: Path,
    inserts: Sequence[Dict[str, Any]],
    ass_path: Optional[Path] = None,
    fonts_dir: Optional[Path] = None,
    inserts_dir: Path = INSERTS_DIR,
) -> bool:
    """Second pass of a clip with inserts: they go in before the captions are burned."""
    subs = subtitles_filter_fragment(ass_path, fonts_dir) if ass_path else None
    inputs: List[str] = []
    for insert in inserts:
        inputs += ["-i", str(inserts_dir / insert["file"])]
    command = [
        "ffmpeg", "-y", "-i", str(video), *inputs,
        "-filter_complex", build_inserts_filter(inserts, subs),
        "-map", "[v]", "-map", "0:a?",
        *build_final_video_encode_args(),
        "-c:a", "copy", "-movflags", "+faststart", str(output),
    ]
    return run_ffmpeg_command(command).returncode == 0
