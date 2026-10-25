"""Operator notes reach the analysis prompt and keep a separate analysis cache."""

from types import SimpleNamespace

import pytest

from src import ai
from src.clip_notes import normalize_clip_notes, validate_clip_notes
from src.services.task_service import TaskService


@pytest.mark.parametrize("value,expected", [(None, None), ("", None), ("   ", None), (" Keep it clean. ", "Keep it clean.")])
def test_blank_notes_mean_none(value, expected):
    assert validate_clip_notes(value) == expected


@pytest.mark.parametrize("value", [42, ["a"], {"a": 1}, "x" * 2001])
def test_invalid_notes_are_rejected_but_stored_ones_are_dropped(value):
    with pytest.raises(ValueError):
        validate_clip_notes(value)
    assert normalize_clip_notes(value) is None


def test_notes_are_injected_only_when_present():
    with_notes = ai.build_transcript_analysis_prompt("transcript", clip_notes="Mention the product name.")
    without = ai.build_transcript_analysis_prompt("transcript")
    assert "Operator notes for this task" in with_notes
    assert "Mention the product name." in with_notes
    assert "Operator notes" not in without
    assert with_notes.rstrip().endswith("transcript")


@pytest.mark.asyncio
async def test_windowed_analysis_passes_notes_to_every_window(monkeypatch):
    prompts = []
    async def analyze(_agent, prompt):
        prompts.append(prompt)
        return SimpleNamespace(output=ai.TranscriptAnalysis(most_relevant_segments=[], summary="", key_topics=[]))
    monkeypatch.setattr(ai, "_run_transcript_analysis", analyze)
    windows = [{"transcript": "a", "start": 0, "end": 720}, {"transcript": "b", "start": 600, "end": 1320}]
    await ai._analyze_transcript_windows(object(), windows, False, None, None, "auto", "No sponsor reads.")
    assert len(prompts) == 2
    assert all("No sponsor reads." in prompt for prompt in prompts)


def test_notes_get_their_own_analysis_cache():
    source_key = TaskService._build_cache_key("upload://talk.mp4", "video_url", "fast")
    assert TaskService._build_analysis_cache_key(source_key, "auto", None) == source_key
    first = TaskService._build_analysis_cache_key(source_key, "auto", "Style A")
    second = TaskService._build_analysis_cache_key(source_key, "auto", "Style B")
    assert len({source_key, first, second}) == 3
