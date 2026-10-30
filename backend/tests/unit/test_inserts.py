import shutil
import subprocess
from pathlib import Path

import pytest

from src.media.inserts import apply_inserts, build_inserts_filter, clip_time, inserts_on_timeline, validate_inserts
from src.render_segments import validate_render_segments


def test_inserts_are_validated_and_ordered():
    raw = [{"file": "b.mp4", "start": 5, "end": 6}, {"file": "a.mp4", "kind": "fundido", "start": 1, "end": 2, "from": 3}]
    clean = validate_inserts(raw, 10)
    assert [i["file"] for i in clean] == ["a.mp4", "b.mp4"]
    assert clean[0]["kind"] == "fundido" and clean[0]["from"] == 3 and clean[1]["kind"] == "pantalla"
    assert validate_inserts(None, 10) == []


@pytest.mark.parametrize("bad", [
    [{"file": "../secret.mp4", "start": 1, "end": 2}],                   # never a path
    [{"file": "a.exe", "start": 1, "end": 2}],
    [{"file": "a.mp4", "start": 3, "end": 2}],
    [{"file": "a.mp4", "start": 1, "end": 20}],                          # past the clip
    [{"file": "a.mp4", "kind": "otro", "start": 1, "end": 2}],
    [{"file": "a.mp4", "start": 1, "end": 3}, {"file": "b.mp4", "start": 2, "end": 4}],   # overlap
])
def test_bad_inserts_are_refused(bad):
    with pytest.raises(ValueError):
        validate_inserts(bad, 10)


def test_a_segment_carries_its_inserts_and_measures_them_against_the_clip():
    seg = validate_render_segments(
        [{"start": 100, "end": 110, "hook_title": None, "inserts": [{"file": "a.mp4", "start": 1, "end": 2}]}], None
    )[0]
    assert seg["inserts"][0]["file"] == "a.mp4"
    with pytest.raises(ValueError):       # 100-110 is a 10 s clip: times are the clip's, not the source's
        validate_render_segments([{"start": 100, "end": 110, "inserts": [{"file": "a.mp4", "start": 50, "end": 51}]}], None)


def test_an_insert_lands_on_its_word_after_the_pauses_are_cut():
    # Segment from 100 s; 3 s of pause gone between 110 and 113
    ranges = [(100.0, 110.0), (113.0, 120.0)]
    assert clip_time(5, 100, ranges) == 5
    assert clip_time(15, 100, ranges) == 12          # 115 in the source: 2 s after the cut
    assert clip_time(11, 100, ranges) == 10          # inside the pause: what follows
    assert clip_time(15, 100, ranges, 0.1) == pytest.approx(11.9)
    assert clip_time(99, 100, ranges) == 17          # past the end
    placed = inserts_on_timeline(
        [{"file": "a.mp4", "start": 14.0, "end": 16.0}, {"file": "b.mp4", "start": 10.5, "end": 12.0}], 100, ranges
    )
    assert [(i["file"], i["start"], i["end"]) for i in placed] == [("a.mp4", 11.0, 13.0)]   # b fell in the pause


def test_a_face_card_sits_in_its_corner_for_its_time():
    chain = build_inserts_filter([{"file": "d.mp4", "kind": "cara", "start": 2.0, "end": 4.0, "from": 0.0}], None)
    assert "overlay=x=60:y=1090" in chain and "setpts=PTS+2.000/TB" in chain and "fade=t=out:st=1.880" in chain


def test_the_filter_blends_or_cuts_and_burns_captions_last():
    chain = build_inserts_filter(
        [{"file": "r.mp4", "kind": "fundido", "start": 1.0, "end": 2.0, "from": 0.0},
         {"file": "t.mp4", "kind": "pantalla", "start": 3.0, "end": 4.0, "from": 8.0}], "subtitles=filename=c.ass")
    assert "blend=all_mode=screen" in chain and "tpad=start_duration=1.000" in chain
    assert "trim=start=8.000:duration=1.000" in chain and "setpts=PTS+3.000/TB" in chain
    assert chain.index("overlay=") < chain.index("subtitles=") and chain.endswith("[v]")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_real_render_puts_the_insert_at_its_time_and_keeps_length_and_audio(tmp_path):
    def make(path, color, seconds=4, audio=False):
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:r=30:d={seconds}"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=f=440:d={seconds}", "-shortest"]
        subprocess.run([*cmd, "-pix_fmt", "yuv420p", str(path)], check=True)

    clip, insert, out = tmp_path / "clip.mp4", tmp_path / "ins.mp4", tmp_path / "out.mp4"
    make(clip, "blue", audio=True)
    make(insert, "red", 2)
    inserts = validate_inserts([{"file": "ins.mp4", "start": 1, "end": 2}], 4)
    assert apply_inserts(clip, out, inserts, inserts_dir=tmp_path)

    def pixel(t):
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", str(t), "-i", str(out), "-frames:v", "1", "-vf", "scale=1:1",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        return raw[0], raw[2]

    assert pixel(0.5)[1] > 150 and pixel(1.5)[0] > 150 and pixel(3.0)[1] > 150      # blue, red, blue
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,r_frame_rate:format=duration", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True).stdout
    assert "audio" in probe and "60/1" in probe
    assert abs(float(probe.strip().splitlines()[-1]) - 4.0) < 0.2
