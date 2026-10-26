"""Transcript-only tasks: transcribe a source without analysis or rendering."""

from typing import Any, Dict, Optional


def validate_transcript_only(value: Any) -> bool:
    """Missing means a normal task; anything else must be a boolean."""
    if value is None:
        return False
    if not isinstance(value, bool):
        raise ValueError("transcript_only must be a boolean")
    return value


def normalize_transcript_only(value: Any) -> bool:
    """Stored task settings fall back to a normal task instead of failing the job."""
    return value is True


def build_task_transcript(transcript_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """API payload from the cached transcript: timed words and speaker turns, times in ms."""
    words = (transcript_data or {}).get("words") or []
    if not words:
        raise ValueError("Transcript has no word timings for this source")
    return {
        "language_code": (transcript_data or {}).get("language_code"),
        "words": [
            {
                "text": word.get("text", ""),
                "start": word.get("start"),
                "end": word.get("end"),
                "confidence": word.get("confidence"),
                "speaker": word.get("speaker"),
            }
            for word in words
        ],
        "utterances": [
            {
                "speaker": utterance.get("speaker"),
                "start": utterance.get("start"),
                "end": utterance.get("end"),
                "text": utterance.get("text", ""),
            }
            for utterance in (transcript_data or {}).get("utterances") or []
        ],
    }
