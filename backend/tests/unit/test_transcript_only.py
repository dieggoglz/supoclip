from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.routes import tasks
from src.services import video_service as video_service_module
from src.services.video_service import VideoService
from src.task_transcript import (
    build_task_transcript,
    normalize_transcript_only,
    validate_transcript_only,
)
from tests.unit.test_task_duration_preflight import creation  # noqa: F401  (fixture)
from tests.unit.test_task_service import build_task_service

TRANSCRIPT_DATA = {
    "version": 2,
    "language_code": "en",
    "text": "Hello there. Hi.",
    "words": [
        {"text": "Hello", "start": 0, "end": 400, "confidence": 0.98, "speaker": "A"},
        {"text": "there.", "start": 400, "end": 900, "confidence": 0.95, "speaker": "A"},
        {"text": "Hi.", "start": 1200, "end": 1500, "confidence": 0.99, "speaker": "B"},
    ],
    "utterances": [
        {"text": "Hello there.", "start": 0, "end": 900, "speaker": "A", "words": [{"text": "Hello"}]},
        {"text": "Hi.", "start": 1200, "end": 1500, "speaker": "B", "words": [{"text": "Hi."}]},
    ],
}


# ---------------------------------------------------------------- the option itself

def test_transcript_only_is_an_optional_boolean():
    assert validate_transcript_only(None) is False
    assert validate_transcript_only(True) is True
    assert validate_transcript_only(False) is False
    with pytest.raises(ValueError):
        validate_transcript_only("true")
    assert normalize_transcript_only("true") is False
    assert normalize_transcript_only(True) is True


def test_transcript_payload_keeps_timed_words_and_speaker_turns():
    payload = build_task_transcript(TRANSCRIPT_DATA)
    assert payload["language_code"] == "en"
    assert payload["words"][2] == {"text": "Hi.", "start": 1200, "end": 1500, "confidence": 0.99, "speaker": "B"}
    assert payload["utterances"] == [
        {"speaker": "A", "start": 0, "end": 900, "text": "Hello there."},
        {"speaker": "B", "start": 1200, "end": 1500, "text": "Hi."},
    ]


@pytest.mark.parametrize("data", [None, {"words": []}, {"text": "captions only"}])
def test_transcript_without_word_timings_is_an_error(data):
    with pytest.raises(ValueError, match="no word timings"):
        build_task_transcript(data)


# ---------------------------------------------------------------- task creation

@pytest.mark.asyncio
async def test_transcript_only_is_persisted_for_resume_and_queued(monkeypatch, creation):  # noqa: F811
    request, _, queue, _ = creation
    request.json.return_value.update(transcript_only=True)
    monkeypatch.setattr(tasks, "async_get_youtube_video_info", AsyncMock(return_value={"duration": 300}))
    await tasks.create_task(request, db=None)
    assert tasks._save_task_source_metadata.await_args.args[1]["transcript_only"] is True
    assert queue.enqueue_processing_job.await_args.kwargs["transcript_only"] is True


@pytest.mark.asyncio
async def test_normal_tasks_are_not_transcript_only(monkeypatch, creation):  # noqa: F811
    request, _, queue, _ = creation
    monkeypatch.setattr(tasks, "async_get_youtube_video_info", AsyncMock(return_value={"duration": 300}))
    await tasks.create_task(request, db=None)
    assert queue.enqueue_processing_job.await_args.kwargs["transcript_only"] is False


@pytest.mark.asyncio
async def test_invalid_transcript_only_rejected_before_billing(monkeypatch, creation):  # noqa: F811
    request, _, queue, _ = creation
    request.json.return_value.update(transcript_only="yes")
    monkeypatch.setattr(tasks, "async_get_youtube_video_info", AsyncMock())
    with pytest.raises(HTTPException) as error:
        await tasks.create_task(request, db=None)
    assert error.value.status_code == 422
    tasks.BillingService.assert_can_create_task.assert_not_awaited()
    queue.enqueue_processing_job.assert_not_awaited()


# ---------------------------------------------------------------- pipeline

@pytest.mark.asyncio
async def test_pipeline_stops_after_transcription(monkeypatch, tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"placeholder")
    config = SimpleNamespace(max_video_duration=5400, clip_duration=30, max_clips=10, fast_mode_max_clips=4)
    monkeypatch.setattr(video_service_module, "get_config", lambda: config)
    monkeypatch.setattr(VideoService, "resolve_local_video_path", staticmethod(lambda _url: video_path))
    monkeypatch.setattr(VideoService, "_get_file_duration", staticmethod(lambda _path: 42.0))
    monkeypatch.setattr(VideoService, "generate_transcript", AsyncMock(return_value="[00:00 - 00:01] Hello there."))
    analyze = AsyncMock(side_effect=AssertionError("transcript-only tasks must not call the LLM"))
    monkeypatch.setattr(VideoService, "analyze_transcript", analyze)
    monkeypatch.setattr(video_service_module, "load_cached_transcript_data", lambda _path: TRANSCRIPT_DATA)

    async def fake_run_in_thread(_func, *_args, **_kwargs):
        return None

    monkeypatch.setattr(video_service_module, "run_in_thread", fake_run_in_thread)

    result = await VideoService.process_video_complete(
        url="upload://source.mp4", source_type="video_url", transcript_only=True
    )

    analyze.assert_not_awaited()
    assert result["segments_to_render"] == [] and result["analysis_json"] is None
    assert result["transcript_data"] is TRANSCRIPT_DATA


def transcript_only_service():
    service = build_task_service()
    service.task_repo.save_task_transcript = AsyncMock()
    service.video_service.process_video_complete = AsyncMock(
        return_value={
            "video_path": "/tmp/source.mp4",
            "transcript": "[00:00 - 00:01] Hello there.",
            "transcript_data": TRANSCRIPT_DATA,
            "segments_to_render": [],
            "segments": [],
            "analysis_json": None,
        }
    )
    return service


@pytest.mark.asyncio
async def test_task_stores_transcript_and_completes_without_clips_or_email():
    service = transcript_only_service()

    result = await service.process_task(
        task_id="task-1", url="https://www.youtube.com/watch?v=demo", source_type="youtube", transcript_only=True
    )

    assert result == {"task_id": "task-1", "clips_count": 0, "transcript_only": True, "words_count": 3}
    assert service.video_service.process_video_complete.await_args.kwargs["transcript_only"] is True
    stored = service.task_repo.save_task_transcript.await_args.args[2]
    assert [w["text"] for w in stored["words"]] == ["Hello", "there.", "Hi."]
    assert service.cache_repo.upsert_cache.await_args.kwargs["analysis_json"] is None
    service.task_repo.update_task_status.assert_any_await(
        service.db, "task-1", "completed", progress=100,
        progress_message="Transcript ready", expected_statuses=["processing"],
    )
    service.clip_repo.create_clip.assert_not_awaited()
    service.clip_repo.delete_clips_by_task.assert_not_awaited()
    service.task_repo.get_task_notification_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_without_word_timings_fails_clearly():
    service = transcript_only_service()
    service.video_service.process_video_complete.return_value["transcript_data"] = {"words": []}

    with pytest.raises(ValueError, match="no word timings"):
        await service.process_task(
            task_id="task-1", url="https://www.youtube.com/watch?v=demo", source_type="youtube", transcript_only=True
        )

    service.task_repo.save_task_transcript.assert_not_awaited()
    service.task_repo.update_task_status.assert_any_await(
        service.db, "task-1", "error", progress=0,
        progress_message="Transcript has no word timings for this source",
        expected_statuses=["queued", "processing"],
    )


# ---------------------------------------------------------------- reading it back

def reader(monkeypatch, user_id, task, transcript):
    monkeypatch.setattr(tasks, "_get_user_id_from_headers", AsyncMock(return_value=user_id))
    monkeypatch.setattr(tasks, "user_is_admin", AsyncMock(return_value=False))
    service = SimpleNamespace(
        task_repo=SimpleNamespace(
            get_task_by_id=AsyncMock(return_value=task),
            get_task_transcript=AsyncMock(return_value=transcript),
        )
    )
    monkeypatch.setattr(tasks, "TaskService", lambda _db: service)
    return service


@pytest.mark.asyncio
async def test_owner_reads_the_transcript(monkeypatch):
    stored = build_task_transcript(TRANSCRIPT_DATA)
    reader(monkeypatch, "owner", {"user_id": "owner", "status": "completed"}, stored)

    response = await tasks.get_task_transcript("task-1", request=object(), db=object())

    assert response["task_id"] == "task-1"
    assert response["words"] == stored["words"] and response["utterances"] == stored["utterances"]


@pytest.mark.asyncio
async def test_other_users_cannot_read_the_transcript(monkeypatch):
    service = reader(monkeypatch, "intruder", {"user_id": "owner", "status": "completed"}, {"words": []})

    with pytest.raises(HTTPException) as error:
        await tasks.get_task_transcript("task-1", request=object(), db=object())

    assert error.value.status_code == 403
    service.task_repo.get_task_transcript.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("task, transcript", [
    (None, None),                                            # no such task
    ({"user_id": "owner", "status": "completed"}, None),     # a normal task: no stored transcript
])
async def test_missing_task_or_transcript_is_not_found(monkeypatch, task, transcript):
    reader(monkeypatch, "owner", task, transcript)

    with pytest.raises(HTTPException) as error:
        await tasks.get_task_transcript("task-1", request=object(), db=object())

    assert error.value.status_code == 404
