"""Task-specific clip length presets shared by selection and rendering."""

import re
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ClipDuration:
    minimum: int
    maximum: int
    ideal_minimum: int
    ideal_maximum: int


CLIP_DURATIONS = {
    "auto": ClipDuration(15, 60, 25, 50),
    # Ideal maxima leave room for the sentence rewind/extension before the cap.
    "short": ClipDuration(15, 30, 18, 25),
    "medium": ClipDuration(30, 60, 35, 55),
    "long": ClipDuration(60, 120, 75, 110),
}

# A per-task range ("custom:MIN-MAX") travels through the same clip_length
# string as the presets, so caching, rendering and resume need no extra fields.
CUSTOM_CLIP_LENGTH_RE = re.compile(r"^custom:(?P<minimum>\d{1,3})-(?P<maximum>\d{1,3})$")
CUSTOM_CLIP_MIN_SECONDS = 5
CUSTOM_CLIP_MAX_SECONDS = 180
CUSTOM_CLIP_MIN_SPAN_SECONDS = 10


def _custom_clip_duration(value: str) -> ClipDuration | None:
    match = CUSTOM_CLIP_LENGTH_RE.match(value)
    if not match:
        return None
    minimum, maximum = int(match["minimum"]), int(match["maximum"])
    if not (
        CUSTOM_CLIP_MIN_SECONDS <= minimum
        and maximum <= CUSTOM_CLIP_MAX_SECONDS
        and maximum - minimum >= CUSTOM_CLIP_MIN_SPAN_SECONDS
    ):
        return None
    span = maximum - minimum
    # Same shape as the presets: aim inside the range, keeping at least 5s
    # below the cap so the renderer can finish a sentence.
    return ClipDuration(minimum, maximum, minimum + span // 5, maximum - max(5, span // 5))


def custom_clip_length(minimum: Any, maximum: Any) -> str:
    """Encode a per-task range, raising ValueError when it is out of bounds."""
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in (minimum, maximum)):
        raise ValueError("min_clip_seconds and max_clip_seconds must be integers")
    value = f"custom:{minimum}-{maximum}"
    if _custom_clip_duration(value) is None:
        raise ValueError(
            f"Clip range must be {CUSTOM_CLIP_MIN_SECONDS}-{CUSTOM_CLIP_MAX_SECONDS} seconds "
            f"with at least {CUSTOM_CLIP_MIN_SPAN_SECONDS} seconds between minimum and maximum"
        )
    return value


def requested_clip_length(data: Mapping[str, Any]) -> str:
    """Resolve a task request to a preset or, with min/max_clip_seconds, a custom range.

    A missing bound comes from the requested preset (Auto by default).
    """
    preset = validate_clip_length(data.get("clip_length", "auto"))
    minimum = data.get("min_clip_seconds")
    maximum = data.get("max_clip_seconds")
    if minimum is None and maximum is None:
        return preset
    bounds = clip_duration(preset)
    return custom_clip_length(
        bounds.minimum if minimum is None else minimum,
        bounds.maximum if maximum is None else maximum,
    )


def validate_clip_length(value: Any) -> str:
    if not isinstance(value, str) or (
        value not in CLIP_DURATIONS and _custom_clip_duration(value) is None
    ):
        raise ValueError("clip_length must be auto, short, medium, or long")
    return value


def normalize_clip_length(value: Any) -> str:
    """Stored task settings fall back to Auto instead of failing the job."""
    try:
        return validate_clip_length(value)
    except ValueError:
        return "auto"


def clip_duration(value: str = "auto") -> ClipDuration:
    value = validate_clip_length(value)
    return CLIP_DURATIONS.get(value) or _custom_clip_duration(value)
