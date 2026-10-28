"""Render requests: explicit source ranges chosen outside SupoClip's own AI analysis."""

import math
from typing import Any, Dict, List, Optional

from .media.common import TRANSCRIPT_CACHE_SCHEMA_VERSION

MAX_RENDER_SEGMENTS = 20
MIN_RENDER_SEGMENT_SECONDS = 1.0
MAX_RENDER_SEGMENT_SECONDS = 180.0
RENDER_HOOK_TITLE_MAX_CHARS = 200
# Sources are measured in whole seconds at creation; allow the rounding.
DURATION_TOLERANCE_SECONDS = 1.0
# Optional ending: keep tail_s after the requested end (the last word finishes sounding while
# everything fades), then hold the last frame hold_s in silence until black.
MAX_ENDING_TAIL_SECONDS = 1.0
MAX_ENDING_HOLD_SECONDS = 3.0


def _seconds(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def validate_render_segments(value: Any, source_duration_seconds: Optional[float]) -> List[Dict[str, Any]]:
    """[{start, end, hook_title, ending?, static_text?}] in source seconds. Raises ValueError with the first problem."""
    if not isinstance(value, list) or not value:
        raise ValueError("segments must be a non-empty list")
    if len(value) > MAX_RENDER_SEGMENTS:
        raise ValueError(f"At most {MAX_RENDER_SEGMENTS} segments per request")
    segments = []
    for number, item in enumerate(value, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Segment {number} must be an object")
        start, end = _seconds(item.get("start")), _seconds(item.get("end"))
        if start is None or end is None:
            raise ValueError(f"Segment {number}: start and end must be numbers of seconds")
        if start < 0 or end <= start:
            raise ValueError(f"Segment {number}: end must be greater than start, and start must be at least 0")
        if source_duration_seconds and end > source_duration_seconds + DURATION_TOLERANCE_SECONDS:
            raise ValueError(f"Segment {number} ends after the source video ({source_duration_seconds:g}s)")
        if not MIN_RENDER_SEGMENT_SECONDS <= end - start <= MAX_RENDER_SEGMENT_SECONDS:
            raise ValueError(
                f"Segment {number} must last {MIN_RENDER_SEGMENT_SECONDS:g}-{MAX_RENDER_SEGMENT_SECONDS:g} seconds"
            )
        hook_title = item.get("hook_title")
        if hook_title is not None and not isinstance(hook_title, str):
            raise ValueError(f"Segment {number}: hook_title must be a string or null")
        hook_title = (hook_title or "").strip() or None
        if hook_title and len(hook_title) > RENDER_HOOK_TITLE_MAX_CHARS:
            raise ValueError(f"Segment {number}: hook_title must be at most {RENDER_HOOK_TITLE_MAX_CHARS} characters")
        ending = _validate_ending(item.get("ending"), number)
        if ending and source_duration_seconds and end + ending["tail_s"] > source_duration_seconds + DURATION_TOLERANCE_SECONDS:
            raise ValueError(f"Segment {number}: end plus ending tail runs past the source video")
        static_text = item.get("static_text", False)
        if not isinstance(static_text, bool):
            raise ValueError(f"Segment {number}: static_text must be true or false")
        segment = {"start": start, "end": end, "hook_title": hook_title, "ending": ending}
        if static_text:
            # Brand briefs that forbid animated text: the hook title stays up for the whole
            # clip with no entrance, and the captions render without per-word effects.
            segment["static_text"] = True
        segments.append(segment)
    return segments


def _validate_ending(value: Any, number: int) -> Optional[Dict[str, float]]:
    """None, or {tail_s, hold_s} within limits (both optional, default 0; both 0 means no ending)."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"tail_s", "hold_s"}:
        raise ValueError(f"Segment {number}: ending must be an object with tail_s and/or hold_s")
    tail, hold = _seconds(value.get("tail_s", 0)), _seconds(value.get("hold_s", 0))
    if tail is None or hold is None:
        raise ValueError(f"Segment {number}: ending tail_s and hold_s must be numbers of seconds")
    if not 0 <= tail <= MAX_ENDING_TAIL_SECONDS or not 0 <= hold <= MAX_ENDING_HOLD_SECONDS:
        raise ValueError(
            f"Segment {number}: ending tail_s must be 0-{MAX_ENDING_TAIL_SECONDS:g} s "
            f"and hold_s 0-{MAX_ENDING_HOLD_SECONDS:g} s"
        )
    return {"tail_s": tail, "hold_s": hold} if tail or hold else None


def segment_text(transcript: Dict[str, Any], start: float, end: float) -> str:
    """Spoken words whose midpoint falls inside [start, end] seconds (transcript times are ms)."""
    words = []
    for word in transcript.get("words") or []:
        if word.get("start") is None or word.get("end") is None:
            continue
        midpoint = (float(word["start"]) + float(word["end"])) / 2000.0
        if start <= midpoint <= end and word.get("text"):
            words.append(word["text"])
    return " ".join(words)


def transcript_cache_payload(transcript: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild a subtitle sidecar from a stored task transcript (source timeline).

    Used when the media cache that held the original sidecar has been swept.
    """
    words = [
        {
            "text": w.get("text", ""),
            "start": int(w["start"]),
            "end": int(w["end"]),
            "confidence": w.get("confidence") if w.get("confidence") is not None else 1.0,
            "speaker": w.get("speaker"),
        }
        for w in transcript.get("words") or []
        if w.get("start") is not None and w.get("end") is not None
    ]
    utterances = []
    for utterance in transcript.get("utterances") or []:
        if utterance.get("start") is None or utterance.get("end") is None:
            continue
        inside = [w for w in words if utterance["start"] <= w["start"] < utterance["end"]]
        utterances.append({
            "text": utterance.get("text", ""),
            "start": int(utterance["start"]),
            "end": int(utterance["end"]),
            "speaker": utterance.get("speaker"),
            "words": inside,
        })
    return {
        "version": TRANSCRIPT_CACHE_SCHEMA_VERSION,
        "words": words,
        "utterances": utterances,
        "text": " ".join(w["text"] for w in words),
        "language_code": transcript.get("language_code"),
    }
