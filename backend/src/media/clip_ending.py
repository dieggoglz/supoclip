"""Soft clip endings: fade out from the last chosen word and hold the final frame to black."""

import logging
from pathlib import Path

from .common import AUDIO_BITRATE
from .ffmpeg import build_final_video_encode_args, ffprobe_duration, ffprobe_has_audio, run_ffmpeg_command

logger = logging.getLogger(__name__)

# Even with no tail, fade the last instant so the cut does not click.
MIN_AUDIO_FADE_SECONDS = 0.06


def apply_clip_ending(video_path: Path, tail_seconds: float, hold_seconds: float) -> float:
    """Rewrite a rendered clip in place and return its new duration.

    The clip's last ``tail_seconds`` come after the chosen final word: picture and
    sound start fading exactly where that word ends, the sound reaches silence at
    the end of the tail, and the last frame is held ``hold_seconds`` (silent) while
    the picture finishes fading to black.
    """
    duration = ffprobe_duration(video_path)
    fade_start = max(0.0, duration - max(0.0, tail_seconds))
    audio_fade = min(duration, max(duration - fade_start, MIN_AUDIO_FADE_SECONDS))
    video_filter = (
        f"tpad=stop_mode=clone:stop_duration={hold_seconds:.3f},"
        f"fade=t=out:st={fade_start:.3f}:d={duration - fade_start + hold_seconds:.3f}"
    )
    audio_args = []
    if ffprobe_has_audio(video_path):
        audio_args = [
            "-af", f"afade=t=out:st={duration - audio_fade:.3f}:d={audio_fade:.3f},apad=pad_dur={hold_seconds:.3f}",
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000",
        ]
    ended_path = video_path.with_name(f".{video_path.stem}.ending{video_path.suffix}")
    command = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(video_path),
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", video_filter,
        *build_final_video_encode_args(),
        *audio_args,
        "-t", f"{duration + hold_seconds:.3f}",
        "-movflags", "+faststart",
        str(ended_path),
    ]
    result = run_ffmpeg_command(command)
    if result.returncode != 0 or not ended_path.exists():
        ended_path.unlink(missing_ok=True)
        raise RuntimeError(f"Unable to apply the clip ending to {video_path}: {result.stderr[-500:]}")
    ended_path.replace(video_path)
    logger.info("Applied ending to %s: fade from %.2fs, hold %.2fs", video_path.name, fade_start, hold_seconds)
    return duration + hold_seconds
