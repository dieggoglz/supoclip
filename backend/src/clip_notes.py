"""Optional per-task operator notes (campaign rules, style) for clip selection."""

from typing import Any, Optional

CLIP_NOTES_MAX_CHARS = 2000


def validate_clip_notes(value: Any) -> Optional[str]:
    """Blank or missing notes mean none; anything else must be a short string."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("clip_notes must be a string")
    notes = value.strip()
    if len(notes) > CLIP_NOTES_MAX_CHARS:
        raise ValueError(f"clip_notes must be at most {CLIP_NOTES_MAX_CHARS} characters")
    return notes or None


def normalize_clip_notes(value: Any) -> Optional[str]:
    """Stored task settings drop unusable notes instead of failing the job."""
    try:
        return validate_clip_notes(value)
    except ValueError:
        return None
