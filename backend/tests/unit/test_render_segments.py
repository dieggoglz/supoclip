"""Explicit-range renders: POST /tasks/{id}/clips, the worker job and the service."""

import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.routes import tasks
from src.config import Config
from src.render_segments import segment_text, transcript_cache_payload, validate_render_segments
from src.services.task_service import TaskService
from src.workers import tasks as worker_tasks

TRANSCRIPT = {
    "language_code": "en",
    "words": [
        {"text": "Hello", "start": 0, "end": 400, "confidence": 0.98, "speaker": "A"},
        {"text": "there.", "start": 400, "end": 900, "confidence": 0.95, "speaker": "A"},
        {"text": "Hi.", "start": 1200, "end": 1500, "confidence": None, "speaker": "B"},
    ],
    "utterances": [
        {"speaker": "A", "start": 0, "end": 900, "text": "Hello there."},
        {"speaker": "B", "start": 1200, "end": 1500, "text": "Hi."},
    ],
}
SOURCE_URL = "https://www.youtube.com/watch?v=abcdefghijk"


# ---------------------------------------------------------------- validation

def test_valid_segments_are_normalized():
    segments = validate_render_segments(
        [{"start": 1, "end": 20.5, "hook_title": "  A title  "}, {"start": 30, "end": 45}], 60
    )
    assert segments == [
        {"start": 1.0, "end": 20.5, "hook_title": "A title", "ending": None},
        {"start": 30.0, "end": 45.0, "hook_title": None, "ending": None},
    ]


def test_blank_hook_title_means_no_title():
    assert validate_render_segments([{"start": 0, "end": 10, "hook_title": "   "}], 60)[0]["hook_title"] is None


@pytest.mark.parametrize("segments, message", [
    (None, "non-empty list"),
    ([], "non-empty list"),
    ([{"start": "1", "end": 10}], "numbers of seconds"),
    ([{"start": True, "end": 10}], "numbers of seconds"),
    ([{"start": 5, "end": 5}], "greater than start"),
    ([{"start": -1, "end": 5}], "at least 0"),
    ([{"start": 50, "end": 70}], "ends after the source"),
    ([{"start": 0, "end": 0.5}], "must last"),
    ([{"start": 0, "end": 10, "hook_title": 3}], "hook_title"),
    ([{"start": 0, "end": 10, "hook_title": "x" * 201}], "at most 200"),
    ([{"start": 0, "end": 10}] * 21, "At most 20"),
])
def test_invalid_segments_are_rejected(segments, message):
    with pytest.raises(ValueError, match=message):
        validate_render_segments(segments, 60)


def test_overlong_segment_is_rejected():
    with pytest.raises(ValueError, match="must last"):
        validate_render_segments([{"start": 0, "end": 200}], 3600)


def test_source_duration_rounding_is_tolerated():
    assert validate_render_segments([{"start": 0, "end": 60.8}], 60)


def test_segment_text_uses_words_inside_the_range():
    assert segment_text(TRANSCRIPT, 0, 1.0) == "Hello there."
    assert segment_text(TRANSCRIPT, 1.0, 2.0) == "Hi."


def test_subtitle_sidecar_is_rebuilt_from_the_stored_transcript():
    payload = transcript_cache_payload(TRANSCRIPT)
    assert payload["version"] == 2 and payload["language_code"] == "en"
    assert payload["words"][2] == {"text": "Hi.", "start": 1200, "end": 1500, "confidence": 1.0, "speaker": "B"}
    assert [w["text"] for w in payload["utterances"][0]["words"]] == ["Hello", "there."]
    assert payload["text"] == "Hello there. Hi."


# ---------------------------------------------------------------- the route

def route_service(monkeypatch, task, transcript=TRANSCRIPT, reserved=True):
    monkeypatch.setattr(tasks, "_get_user_id_from_headers", AsyncMock(return_value="owner"))
    monkeypatch.setattr(tasks, "_read_json_object", AsyncMock(return_value={"segments": [{"start": 0, "end": 10}]}))
    service = SimpleNamespace(task_repo=SimpleNamespace(
        get_task_by_id=AsyncMock(return_value=task),
        get_task_transcript=AsyncMock(return_value=transcript),
        update_task_status=AsyncMock(return_value=reserved),
    ))
    monkeypatch.setattr(tasks, "TaskService", lambda _db: service)
    enqueue = AsyncMock(return_value="job-1")
    monkeypatch.setattr(tasks.JobQueue, "enqueue_job", enqueue)
    return service, enqueue


def owned(**extra):
    return {"user_id": "owner", "status": "completed", "source_duration_seconds": 60, **extra}


@pytest.mark.asyncio
async def test_render_is_queued_and_the_task_reserved(monkeypatch):
    service, enqueue = route_service(monkeypatch, owned())
    response = await tasks.render_task_clips("task-1", request=object(), db=object())
    assert response == {"task_id": "task-1", "job_id": "job-1", "segments": 1}
    args, kwargs = service.task_repo.update_task_status.await_args
    assert args[1:] == ("task-1", "processing")
    assert kwargs == {"progress": 0, "progress_message": "Rendering 1 clips", "expected_statuses": ["completed"]}
    enqueue.assert_awaited_once_with(
        "render_task_segments", "task-1", [{"start": 0.0, "end": 10.0, "hook_title": None, "ending": None}])


@pytest.mark.asyncio
@pytest.mark.parametrize("task, transcript, reserved, status", [
    (owned(status="processing"), TRANSCRIPT, True, 409),   # busy
    (owned(), None, True, 409),                            # a normal task: no stored transcript
    (owned(), TRANSCRIPT, False, 409),                     # lost the race to another edit
    ({"user_id": "someone-else", "status": "completed"}, TRANSCRIPT, True, 403),
])
async def test_render_is_refused_without_queueing(monkeypatch, task, transcript, reserved, status):
    _, enqueue = route_service(monkeypatch, task, transcript, reserved)
    monkeypatch.setattr(tasks, "user_is_admin", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as error:
        await tasks.render_task_clips("task-1", request=object(), db=object())
    assert error.value.status_code == status
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_segments_are_a_422_before_reserving(monkeypatch):
    service, enqueue = route_service(monkeypatch, owned())
    monkeypatch.setattr(tasks, "_read_json_object", AsyncMock(return_value={"segments": [{"start": 50, "end": 90}]}))
    with pytest.raises(HTTPException) as error:
        await tasks.render_task_clips("task-1", request=object(), db=object())
    assert error.value.status_code == 422
    service.task_repo.update_task_status.assert_not_awaited()
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_enqueue_releases_the_task(monkeypatch):
    service, enqueue = route_service(monkeypatch, owned())
    enqueue.side_effect = RuntimeError("redis down")
    with pytest.raises(HTTPException) as error:
        await tasks.render_task_clips("task-1", request=object(), db=object())
    assert error.value.status_code == 500
    last = service.task_repo.update_task_status.await_args
    assert last.args[2] == "completed" and last.kwargs["expected_statuses"] == ["processing"]


# ---------------------------------------------------------------- the service

def render_service(tmp_path, monkeypatch, existing_orders=(1, 2), sidecar=True):
    config = Config()
    config.temp_dir = str(tmp_path)
    monkeypatch.setattr("src.config.get_config", lambda: config)
    monkeypatch.setattr("src.youtube_utils.get_config", lambda: config)
    source = tmp_path / "work" / "abcdefghijk.mp4"
    source.parent.mkdir()
    source.write_bytes(b"source")
    if sidecar:
        source.with_suffix(".transcript_cache.json").write_text(json.dumps({"words": [{"text": "x"}]}))
    service = TaskService(db=None, config=config)
    service._processing_transaction = lambda _task_id: nullcontext()
    service.task_repo.get_task_by_id = AsyncMock(return_value={
        "source_url": SOURCE_URL, "source_type": "youtube", "user_id": "owner",
        "font_family": "Inter", "font_size": 40, "font_color": "#FFFFFF", "caption_template": "bold",
    })
    service.task_repo.get_task_transcript = AsyncMock(return_value=TRANSCRIPT)
    service.task_repo.update_task_clips = AsyncMock()
    service.clip_repo.get_clips_by_task = AsyncMock(
        return_value=[{"id": f"old-{n}", "clip_order": n} for n in existing_orders])
    service.clip_repo.create_clip = AsyncMock(side_effect=["new-1", "new-2"])
    service._media_limits = AsyncMock(return_value=(None, None))
    service._load_task_source_settings = AsyncMock(return_value={"output_format": "vertical", "add_subtitles": True})
    service._cleanup_source_video = lambda *_: None
    service.video_service.download_video = AsyncMock(return_value=str(source))
    service.video_service.prepare_source = AsyncMock(side_effect=lambda path: path)

    async def render(video_path, segments, *args, **kwargs):
        render.segments, render.args, render.kwargs = segments, args, kwargs
        return [
            {"clip_id": i + 1, "filename": f"c{i}.mp4", "path": str(tmp_path / f"c{i}.mp4"),
             "start_time": s["start_time"], "end_time": s["end_time"], "duration": 9.5,
             "text": s["text"], "relevance_score": 0.5, "reasoning": s["reasoning"], "hook_title": s["hook_title"]}
            for i, s in enumerate(segments)
        ]

    service.video_service.create_video_clips = render
    return service, render, source


SEGMENTS = [{"start": 0.0, "end": 1.0, "hook_title": "Exact title"}, {"start": 1.1, "end": 1.6, "hook_title": None}]


@pytest.mark.asyncio
async def test_render_appends_clips_after_the_existing_ones(tmp_path, monkeypatch):
    service, render, _ = render_service(tmp_path, monkeypatch)
    created = await service.render_segments("task", SEGMENTS)

    assert [c["id"] for c in created] == ["new-1", "new-2"]
    orders = [call.kwargs["clip_order"] for call in service.clip_repo.create_clip.await_args_list]
    assert orders == [3, 4]                       # never overwrite clips 1 and 2
    titles = [call.kwargs["hook_title"] for call in service.clip_repo.create_clip.await_args_list]
    assert titles == ["Exact title", None]
    service.task_repo.update_task_clips.assert_awaited_once_with(None, "task", ["old-1", "old-2", "new-1", "new-2"])
    assert render.segments[0]["source_ranges"] == [(0.0, 1.0)]
    assert render.segments[0]["text"] == "Hello there."
    assert render.args[:4] == ("Inter", 40, "#FFFFFF", "bold")   # the task's styling
    assert render.kwargs["max_clip_seconds"] == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_missing_subtitle_sidecar_is_rebuilt(tmp_path, monkeypatch):
    service, _, source = render_service(tmp_path, monkeypatch, sidecar=False)
    await service.render_segments("task", SEGMENTS)
    rebuilt = json.loads(source.with_suffix(".transcript_cache.json").read_text())
    assert [w["text"] for w in rebuilt["words"]] == ["Hello", "there.", "Hi."]


@pytest.mark.asyncio
async def test_task_without_stored_transcript_cannot_render(tmp_path, monkeypatch):
    service, _, _ = render_service(tmp_path, monkeypatch)
    service.task_repo.get_task_transcript = AsyncMock(return_value=None)
    with pytest.raises(ValueError, match="no stored transcript"):
        await service.render_segments("task", SEGMENTS)
    service.video_service.download_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_render_holds_the_processing_lock(tmp_path, monkeypatch):
    service, _, _ = render_service(tmp_path, monkeypatch)
    locked = []
    service._processing_transaction = lambda task_id: locked.append(task_id) or nullcontext()
    await service.render_segments("task", SEGMENTS)
    assert locked == ["task"]


# ---------------------------------------------------------------- the worker job

def worker_service(monkeypatch, render):
    repo = SimpleNamespace(update_task_status=AsyncMock())
    service = SimpleNamespace(task_repo=repo, render_segments=render)

    class Session:
        async def __aenter__(self):
            return "db"

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr("src.database.AsyncSessionLocal", lambda: Session())
    monkeypatch.setattr("src.services.task_service.TaskService", lambda _db: service)
    return repo


@pytest.mark.asyncio
async def test_worker_completes_the_task_with_the_count(monkeypatch):
    repo = worker_service(monkeypatch, AsyncMock(return_value=[{"id": "a"}]))
    result = await worker_tasks.render_task_segments({}, "task", SEGMENTS)
    assert result["rendered"] == 1 and result["requested"] == 2
    repo.update_task_status.assert_awaited_once_with(
        "db", "task", "completed", progress=100,
        progress_message="Rendered 1 of 2 clips", expected_statuses=["processing"],
    )


@pytest.mark.asyncio
async def test_worker_failure_leaves_the_task_usable(monkeypatch):
    repo = worker_service(monkeypatch, AsyncMock(side_effect=ValueError("Failed to download source video")))
    result = await worker_tasks.render_task_segments({}, "task", SEGMENTS)
    assert result["rendered"] == 0 and "download" in result["error"]
    args, kwargs = repo.update_task_status.await_args
    assert args[2] == "completed" and kwargs["progress_message"].startswith("Render failed:")


# ---------------------------------------------------------------- endings (ticket 27 of clip-ops)

def test_ending_is_optional_and_validated():
    plain = validate_render_segments([{"start": 0, "end": 10}], 60)[0]
    assert plain["ending"] is None
    ended = validate_render_segments([{"start": 0, "end": 10, "ending": {"tail_s": 0.3, "hold_s": 0.6}}], 60)[0]
    assert ended["ending"] == {"tail_s": 0.3, "hold_s": 0.6}
    assert validate_render_segments([{"start": 0, "end": 10, "ending": {"tail_s": 0, "hold_s": 0}}], 60)[0]["ending"] is None


@pytest.mark.parametrize("ending, message", [
    ("soft", "must be an object"),
    ({"tail_s": 0.3, "fade": 1}, "must be an object"),
    ({"tail_s": "0.3"}, "numbers of seconds"),
    ({"tail_s": 1.5}, "tail_s must be"),
    ({"hold_s": -1}, "tail_s must be"),
    ({"hold_s": 4}, "tail_s must be"),
])
def test_invalid_endings_are_rejected(ending, message):
    with pytest.raises(ValueError, match=message):
        validate_render_segments([{"start": 0, "end": 10, "ending": ending}], 60)


def test_ending_tail_cannot_run_past_the_source():
    with pytest.raises(ValueError, match="past the source"):
        validate_render_segments([{"start": 50, "end": 60.5, "ending": {"tail_s": 0.9}}], 60)


@pytest.mark.asyncio
async def test_ending_renders_end_plus_tail_exactly_and_applies_the_fade(tmp_path, monkeypatch):
    service, render, _ = render_service(tmp_path, monkeypatch)
    applied = []
    monkeypatch.setattr("src.services.clip_service.apply_clip_ending",
                        lambda path, tail, hold: applied.append((path.name, tail, hold)) or 9.5 + hold)
    segments = [{"start": 0.0, "end": 1.0, "hook_title": None, "ending": {"tail_s": 0.25, "hold_s": 0.6}},
                {"start": 1.1, "end": 1.6, "hook_title": None, "ending": None}]
    await service.render_segments("task", segments)

    ended, plain = render.segments
    assert ended["source_ranges"] == [(0.0, 1.25)] and ended["exact_end"] is True
    assert ended["text"] == "Hello there."            # the tail adds no words
    assert "exact_end" not in plain and plain["source_ranges"] == [(1.1, 1.6)]
    assert applied == [("c0.mp4", 0.25, 0.6)]
    durations = [call.kwargs["duration"] for call in service.clip_repo.create_clip.await_args_list]
    assert durations == [pytest.approx(10.1), 9.5]     # the hold counts in the stored duration
    assert render.kwargs["max_clip_seconds"] == pytest.approx(6.25)


def test_exact_end_skips_the_sentence_extension(tmp_path, monkeypatch):
    from src import video_utils

    source = tmp_path / "source.mp4"
    source.touch()
    extended = []
    monkeypatch.setattr(video_utils, "extend_keep_ranges_to_sentence_boundary",
                        lambda _path, ranges: extended.append(ranges) or ranges)
    monkeypatch.setattr(video_utils, "build_keep_ranges_from_source_ranges", lambda _p, ranges, _c: list(ranges))

    def render(*args, **kwargs):
        args[3].touch()
        return True

    monkeypatch.setattr(video_utils, "create_optimized_clip", render)
    base = {"start_time": "00:00", "end_time": "00:10", "text": "x", "relevance_score": 0.5, "reasoning": "r",
            "source_ranges": [(0.0, 10.0)]}
    video_utils.create_clips_from_segments(source, [base | {"exact_end": True}], tmp_path)
    assert extended == []
    video_utils.create_clips_from_segments(source, [base], tmp_path)
    assert len(extended) == 1
