"""Timeline tuyệt đối: tổng thời lượng, không chồng lấn, shot 3–6 s."""

import pytest

from book_review_worker.media.timeline import (
    GAP_MAX_S,
    GAP_MIN_S,
    SHOT_MAX_S,
    SHOT_MIN_S,
    SceneAudio,
    build_timeline,
    narration_length,
    shot_count,
)
from book_review_worker.providers.base import Word


def audio(scene_id: int, speech_s: float, tail_s: float = 0.8, images: int = 1) -> SceneAudio:
    """Audio giống edge-tts: từ đầu bắt đầu ở 0,1 s, đuôi lặng ~0,8 s."""
    n = max(int(speech_s), 1)
    step = (speech_s - 0.1) / n
    words = [
        Word(text=f"w{i}", start_s=0.1 + i * step, end_s=0.1 + (i + 1) * step) for i in range(n)
    ]
    return SceneAudio(
        scene_id=scene_id,
        audio_path=f"scene_{scene_id}.mp3",
        duration_s=speech_s + tail_s,
        words=words,
        image_count=images,
    )


DURATIONS = [8.0, 12.5, 20.0, 5.0, 31.0, 3.2]


def test_scenes_do_not_overlap_and_total_matches() -> None:
    audios = [audio(i + 1, d) for i, d in enumerate(DURATIONS)]
    tl = build_timeline(audios, gap_s=0.2)
    assert tl.scenes[0].start_s == 0
    for prev, cur in zip(tl.scenes, tl.scenes[1:], strict=False):
        assert cur.start_s == pytest.approx(prev.end_s + prev.gap_after_s)
        assert cur.start_s >= prev.end_s
        assert GAP_MIN_S <= prev.gap_after_s <= GAP_MAX_S
    assert tl.scenes[-1].gap_after_s == 0
    expected = sum(narration_length(a) for a in audios) + 0.2 * (len(audios) - 1)
    assert tl.total_duration_s == pytest.approx(expected)
    assert tl.scenes[-1].end_s == pytest.approx(tl.total_duration_s)


def test_trailing_silence_is_trimmed_but_breath_kept() -> None:
    a = audio(1, 10.0)
    assert narration_length(a) == pytest.approx(10.0 + 0.15)
    assert narration_length(a) < a.duration_s


def test_narration_never_exceeds_audio_file() -> None:
    a = audio(1, 10.0, tail_s=0.05)
    assert narration_length(a) == pytest.approx(a.duration_s)


@pytest.mark.parametrize("speech", [3.2, 5.0, 8.0, 12.5, 20.0, 31.0, 47.3])
def test_shots_are_3_to_6_seconds_and_tile_the_scene(speech: float) -> None:
    tl = build_timeline([audio(1, speech), audio(2, speech)])
    for scene in tl.scenes:
        span_end = scene.end_s + scene.gap_after_s
        assert scene.shots[0].start_s == pytest.approx(scene.start_s)
        assert scene.shots[-1].end_s == pytest.approx(span_end)
        for shot in scene.shots:
            assert SHOT_MIN_S - 1e-9 <= shot.end_s - shot.start_s <= SHOT_MAX_S + 1e-9
        for prev, cur in zip(scene.shots, scene.shots[1:], strict=False):
            assert cur.start_s == pytest.approx(prev.end_s)


def test_short_scene_has_one_shot() -> None:
    assert shot_count(2.0) == 1
    tl = build_timeline([audio(1, 1.5)])
    assert len(tl.scenes[0].shots) == 1


def test_shot_count_range() -> None:
    for tenth in range(30, 1200):
        span = tenth / 10
        n = shot_count(span)
        assert SHOT_MIN_S <= span / n <= SHOT_MAX_S, span


def test_words_become_absolute_and_stay_ordered() -> None:
    tl = build_timeline([audio(1, 6.0), audio(2, 6.0)], gap_s=0.3)
    second = tl.scenes[1]
    assert second.words[0].start_s == pytest.approx(second.start_s + 0.1)
    flat = [w for s in tl.scenes for w in s.words]
    assert all(a.start_s <= b.start_s for a, b in zip(flat, flat[1:], strict=False))
    assert flat[-1].end_s <= tl.total_duration_s


def test_image_ref_cycles_through_scene_images() -> None:
    tl = build_timeline([audio(1, 20.0, images=2)])
    refs = [s.image_ref for s in tl.scenes[0].shots]
    assert set(refs) == {0, 1}
    assert refs[:2] == [0, 1]


@pytest.mark.parametrize("gap", [0.0, 0.1, 0.5])
def test_gap_outside_range_is_rejected(gap: float) -> None:
    with pytest.raises(ValueError):
        build_timeline([audio(1, 5.0)], gap_s=gap)


def test_empty_storyboard() -> None:
    tl = build_timeline([])
    assert tl.scenes == []
    assert tl.total_duration_s == 0
