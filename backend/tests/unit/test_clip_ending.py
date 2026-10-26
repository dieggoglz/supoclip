"""Soft endings rewrite the clip with a fade from the chosen word and a held, silent last frame."""

import json
import shutil
import subprocess

import pytest

from src.media import clip_ending
from src.media.ffmpeg import ffprobe_duration


def make_clip(path, seconds=2.0):
    """A bright test pattern with a loud tone, like a clip that ends mid-speech."""
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=white:s=270x480:r=30:d={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True)


def last_frame_brightness(path):
    out = subprocess.run([
        "ffmpeg", "-v", "error", "-sseof", "-0.1", "-i", str(path), "-vf", "scale=8:8,format=gray",
        "-f", "rawvideo", "-",
    ], check=True, capture_output=True).stdout
    return sum(out[-64:]) / 64


def tail_loudness(path, seconds):
    out = subprocess.run([
        "ffmpeg", "-sseof", f"-{seconds}", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-",
    ], capture_output=True, text=True).stderr
    return float(out.split("max_volume:")[1].split("dB")[0])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_ending_lengthens_the_clip_and_fades_to_black_and_silence(tmp_path):
    clip = tmp_path / "clip.mp4"
    make_clip(clip)
    before = ffprobe_duration(clip)
    assert last_frame_brightness(clip) > 200

    duration = clip_ending.apply_clip_ending(clip, tail_seconds=0.3, hold_seconds=0.6)

    assert duration == pytest.approx(before + 0.6, abs=0.01)
    assert ffprobe_duration(clip) == pytest.approx(before + 0.6, abs=0.1)
    assert last_frame_brightness(clip) < 30          # black at the end
    assert tail_loudness(clip, 0.4) < -60             # the held part is silent


def test_fade_starts_where_the_chosen_word_ends(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.touch()
    seen = {}
    monkeypatch.setattr(clip_ending, "ffprobe_duration", lambda _p: 10.0)
    monkeypatch.setattr(clip_ending, "ffprobe_has_audio", lambda _p: True)

    def run(command):
        seen["command"] = command
        (tmp_path / ".clip.ending.mp4").touch()
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(clip_ending, "run_ffmpeg_command", run)
    clip_ending.apply_clip_ending(clip, tail_seconds=0.25, hold_seconds=0.6)
    command = " ".join(seen["command"])
    assert "fade=t=out:st=9.750:d=0.850" in command                  # picture: from the word end to black
    assert "afade=t=out:st=9.750:d=0.250,apad=pad_dur=0.600" in command  # sound: silent by the tail end
    assert "tpad=stop_mode=clone:stop_duration=0.600" in command
    assert "-t 10.600" in command


def test_no_tail_still_fades_the_last_instant(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.touch()
    seen = {}
    monkeypatch.setattr(clip_ending, "ffprobe_duration", lambda _p: 10.0)
    monkeypatch.setattr(clip_ending, "ffprobe_has_audio", lambda _p: True)
    monkeypatch.setattr(clip_ending, "run_ffmpeg_command",
                        lambda c: seen.setdefault("c", c) and ((tmp_path / ".clip.ending.mp4").touch()
                                                               or subprocess.CompletedProcess(c, 0, "", "")))
    clip_ending.apply_clip_ending(clip, tail_seconds=0, hold_seconds=0.6)
    assert "afade=t=out:st=9.940:d=0.060" in " ".join(seen["c"])
