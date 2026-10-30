from pathlib import Path
from unittest.mock import patch

from src.media.captions import build_hook_title_ass
from src.media.reframing import build_vertical_filter_plan
from src.media.scene_context import SceneEvidence, context_scene_cuts
from src.media.talking_head_layout import (
    caption_y_below_subject,
    choose_talking_head_layout,
)


def _frames(boxes, count=12):
    return [(index / 3.0, [tuple(box) for box in boxes]) for index in range(count)]


def _crop_safe_evidence_with_one_context_cut(samples):
    """Confident close-up evidence whose only scene cut comes from context_scene_cuts."""
    cut_time = samples[len(samples) // 2][0]
    evidence = [
        SceneEvidence(
            t,
            face_area=0.05,
            face_span=0.2,
            face_count=1,
            cut=t == cut_time,
            difference=50 if t == cut_time else 8,
        )
        for t, _ in samples
    ]
    cuts = context_scene_cuts(evidence)
    assert cuts == [cut_time]
    return evidence, cuts


def _plan_with_context(samples, evidence, cuts, track_x=960.0):
    track = [(t, track_x, 0.05) for t, _ in samples]
    return patch("src.media.reframing.ffprobe_duration", return_value=8.0), patch(
        "src.media.reframing.analyze_vertical_clip",
        return_value=(track, cuts, samples, evidence),
    )


def test_low_webcam_face_is_staged_above_the_lower_half():
    # Face centre sits at 63% of a 1080p frame: the full-height 9:16 crop
    # would leave it there and scale the slice about 1.8x.
    layout = choose_talking_head_layout(
        1920, 1080, _frames([(800, 560, 280, 240)]), scene_cuts=[]
    )

    assert layout is not None
    assert layout["kind"] == "stage"
    assert layout["upscale"] <= 1.35
    assert 0.32 <= layout["face_y"] <= 0.46
    assert layout["caption_y"] > layout["video_bottom"] - 0.02
    assert "gblur" in layout["video_filter"]
    assert "[vout]" in layout["video_filter"]


def test_side_by_side_webcams_use_a_stacked_layout():
    layout = choose_talking_head_layout(
        1920,
        1080,
        _frames([(160, 480, 220, 200), (1100, 500, 220, 200)]),
        scene_cuts=[],
    )

    assert layout is not None
    assert layout["kind"] == "stack"
    assert layout["upscale"] <= 1.25
    assert layout["face_y"] < 0.40
    assert 0.48 < layout["caption_y"] < 0.62
    assert "overlay=0:168" in layout["video_filter"]
    assert "overlay=0:1120" in layout["video_filter"]


def test_gallery_is_shown_in_full_instead_of_zooming_one_tile():
    faces = [(40, 40, 140, 120), (700, 40, 140, 120), (40, 500, 140, 120), (700, 500, 140, 120)]
    layout = choose_talking_head_layout(1920, 1080, _frames(faces), scene_cuts=[])

    assert layout is not None
    assert layout["kind"] == "fit"
    assert layout["upscale"] < 1
    assert "force_original_aspect_ratio=decrease" in layout["video_filter"]


def test_high_closeup_keeps_the_tracked_crop():
    assert (
        choose_talking_head_layout(
            1920, 1080, _frames([(700, 80, 400, 360)]), scene_cuts=[]
        )
        is None
    )


def test_podcast_two_shot_with_high_faces_is_not_stacked():
    assert (
        choose_talking_head_layout(
            1920,
            1080,
            _frames([(200, 60, 300, 280), (1100, 70, 300, 280)]),
            scene_cuts=[],
        )
        is None
    )


def test_one_context_cut_still_stages_a_low_webcam(tmp_path):
    samples = _frames([(800, 560, 280, 240)])
    evidence, cuts = _crop_safe_evidence_with_one_context_cut(samples)
    expected = choose_talking_head_layout(1920, 1080, samples, cuts)
    assert expected is not None and expected["kind"] == "stage"
    duration, analyzed = _plan_with_context(samples, evidence, cuts)
    with duration, analyzed:
        video_filter, mode, caption_y = build_vertical_filter_plan(tmp_path / "clip.mp4", 1920, 1080)
    assert (video_filter, mode, caption_y) == (expected["video_filter"], "complex", expected["caption_y"])


def test_one_context_cut_still_stacks_a_call(tmp_path):
    samples = _frames([(160, 480, 220, 200), (1100, 500, 220, 200)])
    evidence, cuts = _crop_safe_evidence_with_one_context_cut(samples)
    expected = choose_talking_head_layout(1920, 1080, samples, cuts)
    assert expected is not None and expected["kind"] == "stack"
    duration, analyzed = _plan_with_context(samples, evidence, cuts, track_x=270.0)
    with duration, analyzed:
        video_filter, mode, caption_y = build_vertical_filter_plan(tmp_path / "clip.mp4", 1920, 1080)
    assert (video_filter, mode, caption_y) == (expected["video_filter"], "complex", expected["caption_y"])
    assert "overlay=0:1120" in video_filter


def test_one_context_cut_on_a_static_closeup_still_uses_ken_burns(tmp_path):
    samples = _frames([(700, 80, 400, 360)])
    evidence, cuts = _crop_safe_evidence_with_one_context_cut(samples)
    assert choose_talking_head_layout(1920, 1080, samples, cuts) is None
    duration, analyzed = _plan_with_context(samples, evidence, cuts, track_x=900.0)
    with duration, analyzed:
        video_filter, mode, _caption_y = build_vertical_filter_plan(tmp_path / "clip.mp4", 1920, 1080)
    assert mode == "vf"
    assert "zoompan" in video_filter


def test_more_than_four_cuts_skip_stage_and_stack():
    low = _frames([(800, 560, 280, 240)])
    call = _frames([(160, 480, 220, 200), (1100, 500, 220, 200)])
    assert choose_talking_head_layout(1920, 1080, low, scene_cuts=[1, 2, 3, 4])["kind"] == "stage"
    assert choose_talking_head_layout(1920, 1080, call, scene_cuts=[1, 2, 3, 4])["kind"] == "stack"
    assert choose_talking_head_layout(1920, 1080, low, scene_cuts=[1, 2, 3, 4, 5]) is None
    assert choose_talking_head_layout(1920, 1080, call, scene_cuts=[1, 2, 3, 4, 5]) is None


def test_captions_move_only_when_they_would_cover_the_face():
    assert caption_y_below_subject(0.45) == 0.80
    lowered = caption_y_below_subject(0.74)
    assert lowered > 0.80
    assert lowered <= 0.84


def test_vertical_plan_stacks_a_call_before_speaker_closeups(tmp_path):
    samples = _frames([(160, 480, 220, 200), (1100, 500, 220, 200)])
    track = [(t, 270.0, 0.03) for t, _ in samples]
    with (
        patch("src.media.reframing.ffprobe_duration", return_value=8.0),
        patch(
            "src.media.reframing.analyze_vertical_clip",
            return_value=(track, [], samples),
        ),
    ):
        video_filter, mode, caption_y = build_vertical_filter_plan(
            tmp_path / "clip.mp4",
            1920,
            1080,
            [{"speaker": "A", "start": 0, "end": 4}, {"speaker": "B", "start": 4, "end": 8}],
            [{"text": "hello", "start": 0.2, "end": 0.6, "speaker": "A"}],
        )

    assert mode == "complex"
    assert "overlay=0:1120" in video_filter
    assert 0.48 < caption_y < 0.62


def test_hook_title_is_larger_than_the_captions():
    style, events = build_hook_title_ass(
        "Somebody has to be boss of the algorithm",
        {"font_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 3, "shadow": True},
        1080,
        1920,
        30.0,
        "Arial",
        62,
    )

    size = int(style.split(",")[2])
    assert size >= 78
    assert size > 62
    assert events and "SOMEBODY" not in events[0]
    assert "boss" in events[0]


def test_long_hook_title_shrinks_below_the_preferred_size():
    word = "Donaudampfschifffahrtsgesellschaft"
    style, events = build_hook_title_ass(
        word,
        {"font_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 3, "shadow": True},
        1080,
        1920,
        30.0,
        "Arial",
        62,
    )

    size = int(style.split(",")[2])
    usable = 1080 - 2 * max(48, int(1080 * 0.07))
    assert size < 64
    assert size == max(1, int(usable / (len(word) * 0.52)))
    assert word in events[0]


def test_a_held_hook_title_covers_the_whole_clip_without_entrance():
    template = {"font_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 3, "word_pop": True}
    style, events = build_hook_title_ass(
        "He just raised $1.85B. What does he do with it?", template, 1080, 1920, 42.0, "Arial", 62,
        hold_full=True,
    )
    assert events[0].startswith("Dialogue: 1,0:00:00.00,0:00:42.00,Hook")
    assert r"\fad" not in events[0] and r"\t(" not in events[0]
    assert int(style.split(",")[-2]) == int(1920 * 0.12)               # below the platforms' top bar
    _, default_events = build_hook_title_ass("Same title", template, 1080, 1920, 42.0, "Arial", 62)
    assert r"\fad" in default_events[0] and "0:00:04.00" in default_events[0]   # default unchanged


def test_a_template_can_hold_a_bigger_boxed_headline_for_longer():
    template = {"font_color": "#FFFFFF", "stroke_color": None, "stroke_width": 0, "hook_title_seconds": 7.0,
                "hook_title_max_px": 104, "hook_title_box": "#000000D9", "hook_title_top": 0.10}
    style, events = build_hook_title_ass("Kids bullied her", template, 1080, 1920, 30.0, "Montserrat", 81)
    fields = style.split(",")
    assert int(fields[2]) == 104 and fields[15] == "3"            # size cap raised, BorderStyle 3 = box
    assert int(fields[-2]) == int(1920 * 0.10)
    assert ",0:00:07.00,Hook" in events[0]                         # 7 s on screen
    _, default = build_hook_title_ass("Kids bullied her", {"font_color": "#FFFFFF"}, 1080, 1920, 30.0, "Arial", 62)
    assert ",0:00:04.00,Hook" in default[0]


def _faces(*centres):
    return [(c - 50, 100, 100, 100) for c in centres]


def test_a_wide_shot_follows_the_mouth_that_moves_in_each_turn():
    import numpy as np
    from src.media.speaker_framing import active_face_segments

    # Two faces at x=300 and x=1500; the left mouth moves for 2 s, then the right one
    samples = [(i / 3.0, _faces(300, 1500)) for i in range(12)]
    motion = np.zeros((40, 34, 60), dtype=np.float32)
    motion[:20, :, 8:11] = 9.0      # cells around x=300 (cell = 32 px)
    motion[20:, :, 45:48] = 9.0     # cells around x=1500
    analysis = {"face_samples": samples, "motion": motion, "motion_fps": 10.0, "motion_cell": 32.0}
    turns = [{"start": 0.0, "end": 2.0, "speaker": "A"}, {"start": 2.0, "end": 4.0, "speaker": "B"}]
    segments = active_face_segments(analysis, (0.0, 4.0), turns, 607)
    assert [(a, b, round(face["cx"])) for a, b, face in segments] == [(0.0, 2.0, 300), (2.0, 4.0, 1500)]
    # the same mouth over two turns does not move the frame
    motion[:] = 0
    motion[:, :, 8:11] = 9.0
    segments = active_face_segments(analysis, (0.0, 4.0), turns, 607)
    assert [(a, b, round(face["cx"])) for a, b, face in segments] == [(0.0, 4.0, 300)]
    # one face only: not this function's job
    alone = dict(analysis, face_samples=[(i / 3.0, _faces(300)) for i in range(12)])
    assert active_face_segments(alone, (0.0, 4.0), turns, 607) == []


def test_a_vertical_video_pasted_in_the_frame_is_found_and_fills_the_screen():
    import cv2
    import numpy as np
    from src.media.reframing import build_vertical_compositor_filter, find_portrait_rectangle

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    rng = np.random.default_rng(1)
    for _ in range(300):                                   # a patterned backdrop
        x, y = int(rng.integers(0, 1800)), int(rng.integers(0, 1000))
        cv2.circle(frame, (x, y), 25, (90, 90, 90), 2)
    cv2.rectangle(frame, (690, 70), (1225, 1010), (255, 255, 255), 6)
    frame[76:1005, 696:1220] = (40, 60, 200)
    x, y, w, h = find_portrait_rectangle(frame)
    assert abs(x - 690) < 12 and abs(y - 70) < 12 and abs(w - 535) < 24 and abs(h - 940) < 24
    assert find_portrait_rectangle(np.zeros((1080, 1920, 3), dtype=np.uint8)) is None
    chain = build_vertical_compositor_filter("crop=606:1080:0:0", [(0.0, 2.0)], [], inserts=[(2.0, 4.0, (690, 70, 534, 940))])
    assert "split=4" in chain and "crop=534:940:690:70" in chain and chain.endswith("[vout]")


def test_each_speaker_is_one_face_per_angle_so_a_laugh_does_not_move_the_frame():
    import numpy as np
    from src.media.speaker_framing import active_face_segments, speaker_faces_by_angle

    samples = [(i / 3.0, _faces(300, 1500)) for i in range(18)]
    motion = np.zeros((60, 34, 60), dtype=np.float32)
    motion[:20, :, 8:11] = 9.0      # A talks on the left for 2 s
    motion[20:40, :, 45:48] = 9.0   # B talks on the right for 2 s
    motion[40:60, :, 8:11] = 2.0    # A talks again, softly...
    motion[40:60, :, 45:48] = 6.0   # ...while B laughs, moving more
    analysis = {"face_samples": samples, "motion": motion, "motion_fps": 10.0, "motion_cell": 32.0}
    turns = [{"start": 0.0, "end": 2.0, "speaker": "A"}, {"start": 2.0, "end": 4.0, "speaker": "B"},
             {"start": 4.0, "end": 6.0, "speaker": "A"}]
    shot = (0.0, 6.0)
    known = speaker_faces_by_angle(analysis, [shot], turns, 607)
    segments = active_face_segments(analysis, shot, turns, 607, known)
    assert [(a, b, round(face["cx"])) for a, b, face in segments] == [
        (0.0, 2.0, 300), (2.0, 4.0, 1500), (4.0, 6.0, 300)]


def test_a_small_face_in_a_wide_shot_gets_closer_and_a_big_one_does_not():
    from src.media.speaker_framing import zoom_box

    x, y, w, h = zoom_box({"cx": 400.0, "cy": 500.0, "w": 110.0, "h": 110.0}, 1920, 1080, 606, 1080)
    assert (w, h) == (308, 550)                                   # zoom limit                                   # zoom limit
    assert x <= 400 <= x + w and y <= 500 <= y + h
    assert zoom_box({"cx": 400.0, "cy": 300.0, "w": 300.0, "h": 300.0}, 1920, 1080, 606, 1080) is None


def test_a_pasted_article_is_shown_whole_and_a_vertical_video_fills_the_screen():
    import cv2
    import numpy as np
    from src.media.reframing import build_vertical_compositor_filter, find_portrait_rectangle

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.rectangle(frame, (500, 60), (1500, 1020), (255, 255, 255), -1)     # an article, wider than tall
    x, y, w, h = find_portrait_rectangle(frame)
    assert abs(x - 500) < 12 and abs(w - 1000) < 24
    chain = build_vertical_compositor_filter("crop=606:1080:0:0", [(0.0, 2.0)], [], inserts=[(2.0, 4.0, (500, 60, 1000, 960))])
    assert "crop=1000:960:500:60,scale=1080:-2" in chain and "overlay=(W-w)/2:(H-h)/2" in chain
    # a frame edge to edge is not something pasted in it
    full = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.rectangle(full, (20, 20), (1900, 1060), (255, 255, 255), 4)
    assert find_portrait_rectangle(full) is None


def test_saying_you_show_something_opens_the_frame_for_a_few_seconds():
    from src.media.reframing import build_vertical_compositor_filter, find_show_moments

    def said(text, start=1.0):
        return [{"text": w, "start": start + i * 0.3, "end": start + i * 0.3 + 0.25} for i, w in enumerate(text.split())]

    assert find_show_moments(said("wait, Look at THIS."), 30.0) == [(1.3, 5.3)]
    assert find_show_moments(said("this is my opinion on phones"), 30.0) == []    # generic: says nothing
    assert find_show_moments(said("look at this", 28.0), 30.0) == [(28.0, 30.0)]  # ends with the clip
    both = said("look at this") + said("check this out", 3.0)
    assert find_show_moments(both, 30.0) == [(1.0, 7.0)]                          # touching moments join
    chain = build_vertical_compositor_filter("crop=606:1080:0:0", [(0.0, 2.0)], [], inserts=[(2.0, 4.0, (500, 0, 810, 1080))])
    assert "crop=810:1080:500:0,scale=1080:-2" in chain                           # 3:4, whole, over the blur
