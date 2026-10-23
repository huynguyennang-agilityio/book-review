"""Chạy thật tts_align → build_timeline → subtitles → scene_images → motion → compose_render
qua worker arq + Redis + edge-tts + ffmpeg, ra video mp4.

    docker compose up -d redis
    uv run arq book_review_worker.main.WorkerSettings     # terminal khác (hoặc service worker)
    uv run python scripts/run_media.py [storyboard.json]

Không truyền file thì dựng storyboard từ `spikes/media/samples/*.txt` (mỗi file một cảnh).
In timeline tóm tắt và so độ dài lời đọc với ffprobe của từng file mp3.
"""

import json
import sys
from pathlib import Path
from typing import Any

from book_review_api.config import get_settings
from book_review_api.graph.nodes.media import (
    make_build_timeline_node,
    make_compose_render_node,
    make_motion_node,
    make_scene_images_node,
    make_subtitles_node,
    make_tts_align_node,
)
from book_review_api.graph.state import BookReviewState
from book_review_api.queue import ArqJobRunner
from book_review_api.storyboard.duration import estimate_seconds, scene_seconds
from book_review_api.storyboard.images import image_plan
from book_review_api.storyboard.schema import Storyboard
from book_review_worker.media.ffmpeg import probe_duration

SAMPLES = Path(__file__).resolve().parent.parent / "spikes" / "media" / "samples"


def sample_storyboard() -> dict[str, Any]:
    scenes = [
        {
            "id": i + 1,
            "section": "body",
            "narration_vi": p.read_text(encoding="utf-8").strip(),
            "scene_type": "title",
            "mood": "warm",
        }
        for i, p in enumerate(sorted(SAMPLES.glob("*.txt")))
    ]
    return {
        "book": {"title": "Mẫu spike"},
        "book_category": "non_fiction",
        "spoiler_free": True,
        "hook_vi": "",
        "style_prompt_en": "",
        "caption_vi": "",
        "scenes": scenes,
    }


def main(args: list[str]) -> None:
    settings = get_settings()
    storyboard = (
        json.loads(Path(args[0]).read_text(encoding="utf-8")) if args else sample_storyboard()
    )
    # Số ảnh mỗi cảnh phải khớp `image_plan` (node tts_align dùng nó để chia `image_ref`).
    counts = image_plan(Storyboard.model_validate(storyboard), settings)
    for scene in storyboard["scenes"]:
        if not scene.get("images"):
            scene["images"] = [{"prompt_en": ""}] * counts[scene["id"]]
    runner = ArqJobRunner(settings.redis_url, settings.job_timeout_s)
    state: BookReviewState = {"storyboard": storyboard}
    out = make_tts_align_node(runner, settings)(state)
    if out.get("status") == "failed":
        sys.exit(f"tts_align lỗi: {out.get('error_code')}")
    out2 = make_build_timeline_node(runner, settings)({**state, **out})  # type: ignore[typeddict-item]
    if out2.get("status") == "failed":
        sys.exit(f"build_timeline lỗi: {out2.get('error_code')}")
    tl = out2["timeline"]
    narrations = {s["id"]: s["narration_vi"] for s in storyboard["scenes"]}
    for scene in tl["scenes"]:
        probed = probe_duration(Path(settings.media_dir) / scene["audio_path"])
        shots = [round(s["end_s"] - s["start_s"], 2) for s in scene["shots"]]
        print(
            f"cảnh {scene['scene_id']}: {scene['start_s']:.2f}–{scene['end_s']:.2f}s, "
            f"{len(scene['words'])} từ, file {probed:.2f}s, lời {scene['narration_s']:.2f}s, "
            f"ước tính {scene_seconds(narrations.get(scene['scene_id'], '')):.2f}s, shot {shots}"
        )
    estimated = estimate_seconds(narrations.values())
    total = tl["total_duration_s"]
    print(
        f"tổng {total:.2f}s, ước tính {estimated:.2f}s (lệch {(total - estimated) / total:+.1%}), "
        f"{out['cost']['tts_chars']:.0f} ký tự TTS"
    )

    state = {**state, **out, "timeline": tl, "asset_refs": {**out["asset_refs"]}}  # type: ignore[typeddict-item]
    for name, make in (
        ("subtitles", make_subtitles_node),
        ("scene_images", make_scene_images_node),
        ("motion", make_motion_node),
        ("compose_render", make_compose_render_node),
    ):
        upd = make(runner)(state)  # type: ignore[arg-type]
        if upd.get("status") == "failed":
            sys.exit(f"{name} lỗi: {upd.get('error_code')}")
        if "asset_refs" in upd:
            state["asset_refs"] = {**state["asset_refs"], **upd["asset_refs"]}
        if "timeline" in upd:
            state["timeline"] = upd["timeline"]
        print(f"{name}: xong")
    refs = state["asset_refs"]
    media = Path(settings.media_dir)
    video = (media / refs["video:final"]).resolve()
    print(f"video {probe_duration(video):.2f}s (timeline {tl['total_duration_s']:.2f}s): {video}")
    for key in ("video:voice_only", "cover", "caption", "sources", "project"):
        print(f"{key}: {(media / refs[key]).resolve()}")


if __name__ == "__main__":
    main(sys.argv[1:])
