"""
Worker tasks - background jobs processed by arq workers.
"""

import logging
from typing import Dict, Any
import json

from ..observability import configure_logging, set_trace_id

configure_logging()

logger = logging.getLogger(__name__)


async def process_video_task(
    ctx: Dict[str, Any],
    task_params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Background worker task to process a video.

    Args:
        ctx: arq context (provides Redis connection and other utilities)
        task_params: A dictionary containing all parameters for the task.
    """
    from ..database import AsyncSessionLocal
    from ..services.task_service import TaskService
    from ..workers.progress import ProgressTracker

    task_id = task_params["task_id"]
    set_trace_id(f"task-{task_id}")
    logger.info(f"Worker processing task {task_id} with params: {task_params}")

    # Create progress tracker
    progress = ProgressTracker(ctx["redis"], task_id)

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)

        try:
            # Progress callback
            async def update_progress(
                percent: int, message: str, status: str = "processing"
            ):
                await progress.update(percent, message, status)
                logger.info(f"Task {task_id}: {percent}% - {message}")

            async def should_cancel() -> bool:
                cancelled = await ctx["redis"].get(f"task_cancel:{task_id}")
                return bool(cancelled)

            async def clip_ready_callback(
                clip_index: int, total_clips: int, clip_data: dict
            ):
                await progress.clip_ready(clip_index, total_clips, clip_data)

            # Process the video
            result = await task_service.process_task(
                task_id=task_id,
                url=task_params["url"],
                source_type=task_params["source_type"],
                font_family=task_params.get("font_family", "TikTokSans-Regular"),
                font_size=task_params.get("font_size", 24),
                font_color=task_params.get("font_color", "#FFFFFF"),
                caption_template=task_params.get("caption_template", "default"),
                processing_mode=task_params.get("processing_mode", "fast"),
                output_format=task_params.get("output_format", "vertical"),
                add_subtitles=task_params.get("add_subtitles", True),
                language=task_params.get("language", "auto"),
                progress_callback=update_progress,
                should_cancel=should_cancel,
                clip_ready_callback=clip_ready_callback,
                cleanup_settings=task_params.get("cleanup_settings"),
                job_audio_fade_in=(
                    task_params["audio_fade_in"]
                    if "audio_fade_in" in task_params
                    else None
                ),
                job_audio_fade_out=(
                    task_params["audio_fade_out"]
                    if "audio_fade_out" in task_params
                    else None
                ),
            )


            logger.info(f"Task {task_id} completed successfully")
            return result

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            try:
                job_try = int(ctx.get("job_try", 1))
                max_tries = int(getattr(WorkerSettings, "max_tries", 3))
                if job_try >= max_tries:
                    payload = {
                        "task_id": task_id,
                        "error": str(e),
                        "tries": job_try,
                    }
                    await ctx["redis"].set(
                        f"dead_letter:{task_id}", json.dumps(payload)
                    )
                    await ctx["redis"].sadd("tasks:dead_letter", task_id)
                    await progress.error("Task failed permanently after retries")
            except Exception:
                logger.exception("Failed to persist dead-letter payload")
            # Error will be caught by arq and task status will be updated
            raise

# Worker configuration for arq
class WorkerSettings:
    """Configuration for arq worker."""

    from ..config import Config
    from arq.connections import RedisSettings

    config = Config()

    # Functions to run
    functions = [process_video_task]
    queue_name = "supoclip_tasks"

    # Redis settings from environment
    redis_settings = RedisSettings(
        host=config.redis_host, port=config.redis_port, password=config.redis_password, database=0
    )

    # Retry settings
    max_tries = 3  # Retry failed jobs up to 3 times
    job_timeout = 10800  # 3 hour timeout for video processing

    # Worker pool settings
    max_jobs = 4  # Process up to 4 jobs simultaneously
    cron_jobs = []
