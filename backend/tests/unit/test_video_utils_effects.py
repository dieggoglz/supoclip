from unittest.mock import patch
from pathlib import Path

import pytest

from src import video_utils
from src.media import timeline


def test_get_scaled_font_size_preserves_visible_ui_range():
    sizes = [
        video_utils.get_scaled_font_size(size, 1080)
        for size in (12, 24, 32, 48, 72)
    ]

    assert sizes == [26, 46, 62, 93, 132]
    assert sizes == sorted(sizes)


def test_build_ass_subtitles_preserves_background_template(tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.with_suffix(".transcript_cache.json").write_text(
        """
        {
          "version": 2,
          "words": [
            {"text": "quiet", "start": 0, "end": 400, "confidence": 0.99},
            {"text": "caption", "start": 400, "end": 900, "confidence": 0.99}
          ],
          "utterances": [],
          "text": "quiet caption"
        }
        """,
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"

    success = video_utils.build_assemblyai_ass_subtitles(
        video_path,
        clip_start=0.0,
        clip_end=1.0,
        video_width=1080,
        video_height=1920,
        output_ass_path=ass_path,
        caption_template="minimal",
        keep_ranges=[(0.0, 1.0)],
    )

    content = ass_path.read_text(encoding="utf-8")
    assert success is True
    assert "Style: Default" in content
    assert ",3," in content
    assert "\\fad(120,120)" in content


def test_prepare_audio_for_transcription_extracts_compact_mp3(tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.write_bytes(b"video")
    commands = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, timeout=900):
        commands.append(command)
        Path(command[-1]).write_bytes(b"audio")
        return Result()

    with patch("src.media.transcription.run_ffmpeg_command", side_effect=fake_run), patch(
        "src.media.transcription.select_audio_stream_index", return_value=1
    ):
        audio_path = video_utils._prepare_audio_for_transcription(video_path)

    assert audio_path.name == "source.transcription.mp3"
    assert audio_path.read_bytes() == b"audio"
    assert commands[0][0] == "ffmpeg"
    assert commands[0][commands[0].index("-map") + 1] == "0:a:1"
    assert "-vn" in commands[0]
    assert "64k" in commands[0]


def test_apply_transition_effect_builds_ffmpeg_xfade_command(tmp_path):
    commands = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, timeout=900):
        commands.append(command)
        return Result()

    with (
        patch("src.video_utils.ffprobe_duration", side_effect=[4.0, 4.0]),
        patch("src.video_utils.ffprobe_video_size", return_value=(1080, 1920)),
        patch("src.video_utils.run_ffmpeg_command", side_effect=fake_run),
    ):
        success = video_utils.apply_transition_effect(
            tmp_path / "clip1.mp4",
            tmp_path / "clip2.mp4",
            tmp_path / "transition.mp4",
            tmp_path / "out.mp4",
        )

    assert success is True
    command = commands[0]
    filter_graph = command[command.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=1.500:offset=0" in filter_graph
    assert "trim=start=2.500:end=4.000" in filter_graph
    assert "trim=start=1.500:end=4.000" in filter_graph
    assert "-map" in command


def test_create_clips_with_transitions_keeps_standalone_clip_exports(tmp_path):
    clips_info = [{"filename": "clip-1.mp4", "path": str(tmp_path / "clip-1.mp4")}]

    with (
        patch(
            "src.video_utils.create_clips_from_segments", return_value=clips_info
        ) as mock_create,
        patch(
            "src.video_utils.get_available_transitions",
            side_effect=AssertionError("should not load transitions"),
        ),
    ):
        result = video_utils.create_clips_with_transitions(
            tmp_path / "source.mp4",
            [{"start_time": "00:00", "end_time": "00:10", "text": "hook"}],
            tmp_path,
            font_family="TikTokSans-Regular",
            font_size=24,
            font_color="#FFFFFF",
            caption_template="default",
            output_format="vertical",
            add_subtitles=True,
        )

    assert result == clips_info
    mock_create.assert_called_once()


def test_build_assemblyai_ass_subtitles_uses_cached_word_timings(tmp_path):
    video_path = tmp_path / "source.mp4"
    cache_path = video_path.with_suffix(".transcript_cache.json")
    cache_path.write_text(
        """
        {
          "version": 2,
          "words": [
            {"text": "hello", "start": 1000, "end": 1300, "confidence": 0.99},
            {"text": "world", "start": 1300, "end": 1800, "confidence": 0.99}
          ],
          "utterances": [],
          "text": "hello world"
        }
        """,
        encoding="utf-8",
    )

    ass_path = tmp_path / "captions.ass"
    success = video_utils.build_assemblyai_ass_subtitles(
        video_path,
        clip_start=1.0,
        clip_end=2.0,
        video_width=1080,
        video_height=1920,
        output_ass_path=ass_path,
        font_family="TikTokSans-Regular",
        font_size=32,
        font_color="#FFFFFF",
        caption_template="default",
        keep_ranges=[(1.0, 2.0)],
    )

    content = ass_path.read_text(encoding="utf-8")
    assert success is True
    assert "PlayResX: 1080" in content
    # Words are now each wrapped in their own font/colour span for per-word
    # karaoke highlighting, so check the cached words are rendered individually.
    assert "hello" in content
    assert "world" in content
    assert "Dialogue:" in content


def test_ass_font_name_uses_internal_font_family():
    assert video_utils.ass_font_name("THEBOLDFONT") == "THE BOLD FONT FREE VERSION"


def test_extend_keep_ranges_finishes_nearby_sentence(tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.with_suffix(".transcript_cache.json").write_text(
        """
        {
          "version": 2,
          "words": [
            {"text": "One", "start": 15440, "end": 15760, "confidence": 0.99},
            {"text": "has", "start": 15760, "end": 16040, "confidence": 0.99},
            {"text": "depression", "start": 16040, "end": 16520, "confidence": 0.99},
            {"text": "and", "start": 16520, "end": 16680, "confidence": 0.99},
            {"text": "the", "start": 16680, "end": 16840, "confidence": 0.99},
            {"text": "other", "start": 16840, "end": 17080, "confidence": 0.99},
            {"text": "has", "start": 17080, "end": 17320, "confidence": 0.99},
            {"text": "anger", "start": 17320, "end": 17680, "confidence": 0.99},
            {"text": "issues.", "start": 17680, "end": 18000, "confidence": 0.99}
          ],
          "utterances": [],
          "text": "One has depression and the other has anger issues."
        }
        """,
        encoding="utf-8",
    )

    with patch("src.media.timeline.ffprobe_duration", return_value=60.0):
        ranges = video_utils.extend_keep_ranges_to_sentence_boundary(
            video_path,
            [(0.0, 16.0)],
        )

    assert ranges[0][0] == 0.0
    assert ranges[0][1] == pytest.approx(18.35)


def test_burn_ass_subtitles_passes_fontsdir_to_ffmpeg(tmp_path):
    commands = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, timeout=900):
        commands.append(command)
        return Result()

    with patch("src.media.ffmpeg.run_ffmpeg_command", side_effect=fake_run):
        success = video_utils.burn_ass_subtitles_ffmpeg(
            tmp_path / "input.mp4",
            tmp_path / "captions.ass",
            tmp_path / "output.mp4",
            fonts_dir=tmp_path / "fonts",
        )

    assert success is True
    video_filter = commands[0][commands[0].index("-vf") + 1]
    assert "fontsdir=" in video_filter
    assert video_filter.endswith(",setsar=1")


def test_ass_font_name_uses_internal_font_family_for_libass():
    assert video_utils.ass_font_name("THEBOLDFONT") == "THE BOLD FONT FREE VERSION"


def test_burn_ass_subtitles_passes_selected_fonts_dir(tmp_path):
    commands = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, timeout=900):
        commands.append(command)
        return Result()

    with patch("src.media.ffmpeg.run_ffmpeg_command", side_effect=fake_run):
        success = video_utils.burn_ass_subtitles_ffmpeg(
            tmp_path / "input.mp4",
            tmp_path / "captions.ass",
            tmp_path / "output.mp4",
            tmp_path / "fonts",
        )

    assert success is True
    video_filter = commands[0][commands[0].index("-vf") + 1]
    assert f"fontsdir={tmp_path / 'fonts'}" in video_filter
    assert video_filter.endswith(",setsar=1")


def test_build_clip_signal_summary_surfaces_hook_and_audio_peak(monkeypatch, tmp_path):
    transcript = "\n".join(
        [
            "[00:00 - 00:04] Speaker A: This is normal setup",
            "[00:05 - 00:08] Speaker B: Wait what happened?",
            "[00:08 - 00:12] Speaker A: Nobody expected the result!",
        ]
    )
    monkeypatch.setattr(timeline, "detect_audio_peak_times", lambda _path: [6.0])

    summary = video_utils.build_clip_signal_summary(tmp_path / "source.mp4", transcript)

    assert "Wait what happened?" in summary
    assert "audio energy peak" in summary
    assert "question/hook" in summary


def test_static_text_renders_plain_captions_and_a_held_title(tmp_path):
    video_path = tmp_path / "source.mp4"
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": ['
        '{"text": "we", "start": 1000, "end": 1200, "confidence": 0.99},'
        '{"text": "raised", "start": 1200, "end": 1600, "confidence": 0.99},'
        '{"text": "money", "start": 1600, "end": 2000, "confidence": 0.99}],'
        ' "utterances": [], "text": "we raised money"}',
        encoding="utf-8",
    )

    def build(static_text):
        ass_path = tmp_path / f"captions-{static_text}.ass"
        assert video_utils.build_assemblyai_ass_subtitles(
            video_path, clip_start=1.0, clip_end=2.0, video_width=1080, video_height=1920,
            output_ass_path=ass_path, caption_template="default", keep_ranges=[(1.0, 2.0)],
            hook_title="A plain headline", static_text=static_text,
        )
        return [line for line in ass_path.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")]

    animated, static = build(False), build(True)
    captions = [line for line in static if ",Default," in line]
    assert len(captions) == 1                                   # one plain line, not one event per word
    assert r"\t(" not in captions[0] and r"\fsc" not in captions[0]
    title = next(line for line in static if ",Hook," in line)
    assert title.startswith("Dialogue: 1,0:00:00.00,0:00:01.00,Hook") and r"\fad" not in title
    assert len([line for line in animated if ",Default," in line]) == 3   # default karaoke unchanged


def test_caption_chunks_never_run_wider_than_the_frame():
    from src.media.captions import caption_chunk_starts

    words = "regular, whether it's restaurants, manufacturers and the like".split()
    # 1080 px frame, 77 px font: four of these words (~48 chars) would be ~2000 px wide
    starts = caption_chunk_starts(words, 4, 950, 77)
    chunks = [words[a:b] for a, b in zip(starts, starts[1:] + [len(words)])]
    assert all(len(" ".join(c)) * 77 * 0.56 <= 950 or len(c) == 1 for c in chunks)
    assert caption_chunk_starts("a b c d e f".split(), 4, 10_000, 40) == [0, 4]   # short words: by count as before
    assert caption_chunk_starts([], 4, 950, 77) == []


def test_long_words_with_a_big_font_are_split_into_more_caption_lines(tmp_path):
    video_path = tmp_path / "source.mp4"
    words = "regular, whether it's restaurants, manufacturers".split()
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": [' + ",".join(
            f'{{"text": "{w}", "start": {1000 + i * 400}, "end": {1350 + i * 400}, "confidence": 0.99}}'
            for i, w in enumerate(words)) + '], "utterances": [], "text": ""}',
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"
    assert video_utils.build_assemblyai_ass_subtitles(
        video_path, clip_start=1.0, clip_end=3.0, video_width=1080, video_height=1920, output_ass_path=ass_path,
        font_size=40, caption_template="podcast", keep_ranges=[(1.0, 3.0)], static_text=True,
    )
    captions = [l for l in ass_path.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue:")]
    assert len(captions) >= 2                    # one 4-word chunk would have been one line off both edges


def test_the_clipper_template_shows_two_bold_uppercase_words_without_emojis(tmp_path):
    video_path = tmp_path / "source.mp4"
    words = ["we", "raised", "fifty", "million", "dollars", "today"]
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": [' + ",".join(
            f'{{"text": "{w}", "start": {1000 + i * 300}, "end": {1250 + i * 300}, "confidence": 0.99}}'
            for i, w in enumerate(words)) + '], "utterances": [], "text": ""}',
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"
    assert video_utils.build_assemblyai_ass_subtitles(
        video_path, clip_start=1.0, clip_end=3.0, video_width=1080, video_height=1920, output_ass_path=ass_path,
        caption_template="clipper", keep_ranges=[(1.0, 3.0)],
    )
    captions = [l for l in ass_path.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue:")]
    assert len(captions) == 3                                   # 6 words, 2 per line, one event per line ("pop")
    assert "WE" in captions[0] and "RAISED" in captions[0]


def test_the_glow_template_draws_a_halo_layer_under_sharp_text_with_one_neon_word(tmp_path):
    video_path = tmp_path / "source.mp4"
    words = ["you", "never", "make", "money", "doing", "that"]
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": [' + ",".join(
            f'{{"text": "{w}", "start": {1000 + i * 300}, "end": {1250 + i * 300}, "confidence": 0.99}}'
            for i, w in enumerate(words)) + '], "utterances": [], "text": ""}',
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"
    assert video_utils.build_assemblyai_ass_subtitles(
        video_path, clip_start=1.0, clip_end=3.0, video_width=1080, video_height=1920, output_ass_path=ass_path,
        caption_template="glow", keep_ranges=[(1.0, 3.0)],
    )
    lines = [l for l in ass_path.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue:")]
    under = [l for l in lines if l.startswith("Dialogue: 0,")]
    texts = [l for l in lines if l.startswith("Dialogue: 1,")]
    assert 2 <= len(texts) <= 3                                 # 6 words, up to 4 per line and as wide as the frame
    halos = [l for l in under if r"\3c&H000000&" in l]
    glows = [l for l in under if r"\3a&H88&" in l]
    assert len(halos) == len(texts) and 1 <= len(glows) <= len(texts)   # a dark halo per line, a glow on a neon word
    assert all(r"\1a&HFF&" in l and r"\blur" in l for l in under)    # invisible fill, blurred border
    assert all(r"\t(0,140,\blur0)" in l for l in texts)              # each line blurs in
    assert "MONEY" in texts[0] or "MONEY" in texts[1]


def test_a_glow_line_without_power_words_lights_up_its_longest_real_word(tmp_path):
    video_path = tmp_path / "source.mp4"
    words = ["kids", "were", "bullying", "you"]
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": [' + ",".join(
            f'{{"text": "{w}", "start": {1000 + i * 300}, "end": {1250 + i * 300}, "confidence": 0.99}}'
            for i, w in enumerate(words)) + '], "utterances": [], "text": ""}',
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"
    assert video_utils.build_assemblyai_ass_subtitles(
        video_path, clip_start=1.0, clip_end=2.5, video_width=1080, video_height=1920, output_ass_path=ass_path,
        caption_template="glow", keep_ranges=[(1.0, 2.5)],
    )
    texts = [l for l in ass_path.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue: 1,")]
    line = next(l for l in texts if "BULLYING" in l)              # the big font splits it into two lines
    neon = line.split("BULLYING")[0].rsplit("\c", 1)[1]
    assert not neon.startswith("&H00FFFFFF")                      # BULLYING in the neon colour, not white


def _timed(*items):
    """(text, start, end) in seconds, as the caption builder gets them."""
    return [{"text": t, "start": s, "end": e} for t, s, e in items]


def test_phrase_lines_follow_speech_with_a_varying_number_of_words():
    from src.media.captions import caption_phrase_starts

    def lines(*texts, pause_after=()):
        words, clock = [], 0.0
        for i, text in enumerate(texts):
            words.append({"text": text, "start": clock, "end": clock + 0.2})
            clock += 0.2 + (0.4 if i in pause_after else 0.02)
        starts = caption_phrase_starts(words, 4, 950, 77 // 2)
        return [" ".join(texts[a:b]) for a, b in zip(starts, starts[1:] + [len(texts)])]

    assert lines("Look", "up.", "Bro", "got", "the", "gun") == ["Look up.", "Bro got the gun"]
    assert lines("Lou?", "I", "don't", "know", "why") == ["Lou?", "I don't know why"]      # punctuation
    assert lines("somebody", "knock", "he", "looked", "at", "me", pause_after=(1,)) == ["somebody knock", "he looked at me"]
    assert lines("but", "I", "rolled", "the", "window", "down") == ["but I rolled", "the window down"]     # determiner
    assert lines("building", "a", "bomb", "in", "my", "bedroom") == ["building a bomb", "in my bedroom"]   # not "in / my"
    assert lines("I", "said", "and", "he", "left") == ["I said", "and he left"]            # new clause
    assert lines("one", "two", "three", "four", "five") == ["one two three four", "five"]  # never more than 4
    assert lines("one", "two", "three", "to", "five") == ["one two three", "to five"]      # no dangling weak word
    assert lines("a", "bomb", "in", "my", "bedroom") == ["a bomb", "in my bedroom"]        # every weak word moves
    assert caption_phrase_starts([], 4, 950, 40) == []


def test_phrase_lines_never_run_wider_than_the_frame():
    from src.media.captions import caption_phrase_starts

    words = _timed(*[(w, i * 0.3, i * 0.3 + 0.28) for i, w in enumerate(["extraordinarily", "uncomfortable", "conversations", "everywhere"])])
    assert caption_phrase_starts(words, 4, 950, 77, uppercase=True) == [0, 1, 2, 3]


def test_the_glow_template_changes_colour_every_line_and_lights_a_word_on_each(tmp_path):
    from src.caption_templates import get_template
    from src.media.captions import hex_to_ass_color

    video_path = tmp_path / "source.mp4"
    words = ["Look", "up.", "On", "me.", "Why?", "Bro", "got", "guns."]
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": [' + ",".join(
            f'{{"text": "{w}", "start": {1000 + i * 300}, "end": {1250 + i * 300}, "confidence": 0.99}}'
            for i, w in enumerate(words)) + '], "utterances": [], "text": ""}',
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"
    assert video_utils.build_assemblyai_ass_subtitles(
        video_path, clip_start=1.0, clip_end=3.5, video_width=1080, video_height=1920, output_ass_path=ass_path,
        caption_template="glow", keep_ranges=[(1.0, 3.5)],
    )
    texts = [l for l in ass_path.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue: 1,")]
    assert len(texts) == 3                                      # Look up. / On me. / Why? Bro got guns.
    palette = [hex_to_ass_color(c) for c in get_template("glow")["emphasis_palette"]]
    used = [next(c for c in palette if c in line) for line in texts]
    assert all(a != b for a, b in zip(used, used[1:]))          # a new colour every line
    assert all(r"\blur7" in line for line in texts)             # a soft blur in and out


def test_glow_lines_cross_fade_with_a_shrink_and_a_blur_and_no_empty_gap(tmp_path):
    video_path = tmp_path / "source.mp4"
    timed = [("Look", 1000, 1300), ("up.", 1320, 1600), ("Bro", 1700, 2000), ("got", 2020, 2300), ("guns.", 2320, 2800)]
    video_path.with_suffix(".transcript_cache.json").write_text(
        '{"version": 2, "words": [' + ",".join(
            f'{{"text": "{w}", "start": {s}, "end": {e}, "confidence": 0.99}}' for w, s, e in timed
        ) + '], "utterances": [], "text": ""}',
        encoding="utf-8",
    )
    ass_path = tmp_path / "captions.ass"
    assert video_utils.build_assemblyai_ass_subtitles(
        video_path, clip_start=1.0, clip_end=3.0, video_width=1080, video_height=1920, output_ass_path=ass_path,
        caption_template="glow", keep_ranges=[(1.0, 3.0)],
    )
    content = ass_path.read_text(encoding="utf-8")
    assert "Nunito Black" in content.split("[Events]")[0]
    lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
    texts = [l for l in lines if l.startswith("Dialogue: 1,")]
    assert len(texts) == 2
    assert all(r"\fscx91" in l and r"\t(0,140,\fscx100\fscy100)" in l and r"\fad(140,140)" in l for l in texts)
    assert all(r"\shad5" in l for l in texts)                     # the hard shadow of the reference
    assert not [l for l in lines if l.startswith("Dialogue: 2,")]    # no ghost copies
    # the old line is still fading out when the new one fades in
    assert texts[0].split(",")[2] > texts[1].split(",")[1]


def test_line_width_is_measured_with_the_real_font_when_it_can_be():
    from src.media.captions import caption_phrase_starts

    words = [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.45} for i, t in enumerate(["It's", "so", "annoying."])]
    assert caption_phrase_starts(words, 4, 950, 93, True, measure=lambda text: 800.0) == [0]        # fits
    assert caption_phrase_starts(words, 4, 950, 93, True, measure=lambda text: 1000.0) != [0]       # does not


def test_a_line_too_brief_to_read_joins_a_neighbour_when_they_fit():
    from src.media.captions import caption_phrase_starts

    def lines(*timed):
        words = [{"text": t, "start": s, "end": e} for t, s, e in timed]
        starts = caption_phrase_starts(words, 4, 950, 40)
        return [" ".join(w["text"] for w in words[a:b]) for a, b in zip(starts, starts[1:] + [len(words)])]

    # "Yeah," lasts 0.2 s: it goes with the next line
    assert lines(("Yeah,", 0, 0.15), ("what", 0.2, 0.4), ("is", 0.42, 0.9), ("it?", 0.92, 1.4)) == ["Yeah, what is it?"]
    # the last line, too brief, goes back to the previous one
    assert lines(("I", 0, 0.5), ("know", 0.52, 1.1), ("it.", 1.12, 1.3)) == ["I know it."]
    # if they do not fit, each keeps its own line
    assert len(lines(("one", 0, 0.1), ("two", 0.11, 0.2), ("three", 0.21, 0.3), ("four,", 0.31, 0.4),
                     ("five", 0.5, 0.6), ("six", 0.61, 0.7), ("seven", 0.71, 0.8), ("eight", 0.81, 0.9))) == 2
