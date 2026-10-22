"""arq WorkerSettings. Chạy: `arq book_review_worker.main.WorkerSettings`."""

from typing import Any, ClassVar

from arq.connections import RedisSettings

from book_review_worker.jobs import compose, images, motion, package, subtitles, timeline, tts
from book_review_worker.providers.tts_edge import EdgeTTS
from book_review_worker.settings import WorkerConfig


async def startup(ctx: dict[str, Any]) -> None:
    config = WorkerConfig()
    ctx["media_dir"] = config.media_dir
    ctx["tts"] = EdgeTTS(voice=config.tts_voice, concurrency=config.tts_concurrency)


async def shutdown(ctx: dict[str, Any]) -> None:
    return None


class WorkerSettings:
    functions: ClassVar[list[Any]] = [tts, timeline, subtitles, images, motion, compose, package]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(WorkerConfig().redis_url)
    # Render nặng: mỗi worker một job một lúc, job TTS cả video tối đa 10 phút.
    max_jobs = 2
    # API huỷ job đang chạy khi người dùng bấm Huỷ (`ArqJobRunner`).
    allow_abort_jobs = True
    job_timeout = 600
    max_tries = 2
    keep_result = 3600
