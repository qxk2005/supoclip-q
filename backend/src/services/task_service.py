"""
Task service - orchestrates task creation and processing workflow.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional, Callable
import logging
from datetime import datetime
from pathlib import Path
import json
import hashlib
from time import perf_counter

import redis.asyncio as redis

from ..repositories.task_repository import TaskRepository
from ..repositories.source_repository import SourceRepository
from ..repositories.clip_repository import ClipRepository
from ..repositories.cache_repository import CacheRepository
from .video_service import VideoService
from .task_completion_email_service import (
    TaskCompletionEmailService,
    TaskCompletionRecipient,
)
from ..config import Config, get_config
from ..clip_editor import (
    trim_clip_file,
    split_clip_file,
    merge_clip_files,
    overlay_custom_captions,
)
from ..video_utils import (
    parse_timestamp_to_seconds,
    load_cached_transcript_data,
    should_use_bilingual_subtitles,
)
from ..subtitle_translation import (
    apply_bilingual_phrase_translations,
    fill_missing_segment_text_translations_zh,
)

logger = logging.getLogger(__name__)


def _burn_clip_title_zh_from_db(value: Any) -> bool:
    """Explicit False disables burn; missing/NULL means on (legacy rows)."""
    if value is None:
        return True
    return bool(value)


class TaskService:
    """Service for task workflow orchestration."""

    def __init__(self, db: AsyncSession, config: Config | None = None):
        self.db = db
        self.task_repo = TaskRepository()
        self.source_repo = SourceRepository()
        self.clip_repo = ClipRepository()
        self.cache_repo = CacheRepository()
        self.video_service = VideoService()
        self.config = config or get_config()

    @staticmethod
    def _build_cache_key(
        url: str,
        source_type: str,
        processing_mode: str,
        professional_hotwords: Optional[str] = None,
        target_clip_count: Optional[int] = None,
        clip_theme: Optional[str] = None,
    ) -> str:
        hw = (professional_hotwords or "").strip()
        th = (clip_theme or "").strip()
        tc = "" if target_clip_count is None else str(int(target_clip_count))
        payload = f"{source_type}|{processing_mode}|{hw}|{tc}|{th}|{url.strip()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _is_stale_queued_task(self, task: Dict[str, Any]) -> bool:
        """Detect queued tasks that have likely stalled due to worker issues."""
        if task.get("status") != "queued":
            return False

        created_at = task.get("created_at")
        updated_at = task.get("updated_at") or created_at

        if not created_at or not updated_at:
            return False

        now = (
            datetime.now(updated_at.tzinfo)
            if getattr(updated_at, "tzinfo", None)
            else datetime.utcnow()
        )
        age_seconds = (now - updated_at).total_seconds()
        return age_seconds >= self.config.queued_task_timeout_seconds

    async def create_task_with_source(
        self,
        user_id: str,
        url: str,
        title: Optional[str] = None,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        caption_template: str = "default",
        include_broll: bool = False,
        processing_mode: str = "fast",
        chunk_size: int = 15000,
        language: str = "auto",
        audio_fade_in: bool = False,
        audio_fade_out: bool = False,
        professional_hotwords: Optional[str] = None,
        bilingual_subtitles_mode: str = "auto",
        burn_clip_title_zh: bool = True,
        target_clip_count: Optional[int] = None,
        clip_theme: Optional[str] = None,
        clip_subtitle_rewhisper: bool = True,
        clip_subtitle_llm_refine: bool = True,
        clip_zh_subtitle_polish: bool = True,
    ) -> str:
        """
        Create a new task with associated source.
        Returns the task ID.
        """
        # Validate user exists
        if not await self.task_repo.user_exists(self.db, user_id):
            raise ValueError(f"User {user_id} not found")

        # Determine source type
        source_type = self.video_service.determine_source_type(url)

        # Get or generate title
        if not title:
            if source_type == "youtube":
                title = await self.video_service.get_video_title(url)
            else:
                title = "Uploaded Video"

        # Create source
        source_id = await self.source_repo.create_source(
            self.db, source_type=source_type, title=title, url=url
        )

        # Create task
        task_id = await self.task_repo.create_task(
            self.db,
            user_id=user_id,
            source_id=source_id,
            status="queued",  # Changed from "processing" to "queued"
            font_family=font_family,
            font_size=font_size,
            font_color=font_color,
            caption_template=caption_template,
            include_broll=include_broll,
            processing_mode=processing_mode,
            chunk_size=chunk_size,
            language=language,
            audio_fade_in=audio_fade_in,
            audio_fade_out=audio_fade_out,
            professional_hotwords=professional_hotwords,
            bilingual_subtitles_mode=bilingual_subtitles_mode,
            burn_clip_title_zh=burn_clip_title_zh,
            target_clip_count=target_clip_count,
            clip_theme=clip_theme,
            clip_subtitle_rewhisper=clip_subtitle_rewhisper,
            clip_subtitle_llm_refine=clip_subtitle_llm_refine,
            clip_zh_subtitle_polish=clip_zh_subtitle_polish,
        )

        logger.info(f"Created task {task_id} for user {user_id}")
        return task_id

    async def process_task(
        self,
        task_id: str,
        url: str,
        source_type: str,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        caption_template: str = "default",
        processing_mode: str = "fast",
        output_format: str = "vertical",
        add_subtitles: bool = True,
        progress_callback: Optional[Callable] = None,
        should_cancel: Optional[Callable] = None,
        clip_ready_callback: Optional[Callable] = None,
        cleanup_settings: Dict[str, Any] | None = None,
        language: str = "auto",
        job_audio_fade_in: Optional[bool] = None,
        job_audio_fade_out: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Process a task: download video, analyze, create clips.
        Returns processing results.
        """
        try:
            logger.info(f"Starting processing for task {task_id}")
            started_at = datetime.utcnow()
            stage_timings: Dict[str, float] = {}
            task_details = await self.task_repo.get_task_by_id(self.db, task_id)
            if not task_details:
                logger.error(f"Task details not found for task_id: {task_id}")
                raise ValueError(f"Task details not found for task_id: {task_id}")

            hotwords = (task_details.get("professional_hotwords") or "").strip() or None
            tcc = task_details.get("target_clip_count")
            cth = (task_details.get("clip_theme") or "").strip() or None
            cache_key = self._build_cache_key(
                url,
                source_type,
                processing_mode,
                hotwords,
                int(tcc) if tcc is not None else None,
                cth,
            )

            cache_entry = await self.cache_repo.get_cache(self.db, cache_key)
            cached_transcript = (
                cache_entry.get("transcript_text") if cache_entry else None
            )
            cached_analysis_json = (
                cache_entry.get("analysis_json") if cache_entry else None
            )
            cache_hit = bool(cached_transcript and cached_analysis_json)

            await self.task_repo.update_task_runtime_metadata(
                self.db,
                task_id,
                started_at=started_at,
                cache_hit=cache_hit,
            )

            # Update status to processing
            await self.task_repo.update_task_status(
                self.db,
                task_id,
                "processing",
                progress=0,
                progress_message="Starting...",
            )

            # Progress callback wrapper
            async def update_progress(
                progress: int, message: str, status: str = "processing"
            ):
                await self.task_repo.update_task_status(
                    self.db,
                    task_id,
                    status,
                    progress=progress,
                    progress_message=message,
                )
                if progress_callback:
                    await progress_callback(progress, message, status)

            chunk_size = task_details.get("chunk_size") if task_details else 15000
            language = task_details.get("language") if task_details else "auto"

            # Process video with progress updates
            pipeline_start = perf_counter()
            bilingual_mode = (
                task_details.get("bilingual_subtitles_mode") or "auto"
            ).strip().lower()
            if bilingual_mode not in ("auto", "on", "off"):
                bilingual_mode = "auto"

            result = await self.video_service.process_video_complete(
                url=url,
                source_type=source_type,
                task_id=task_id,
                font_family=font_family,
                font_size=font_size,
                font_color=font_color,
                caption_template=caption_template,
                processing_mode=processing_mode,
                output_format=output_format,
                add_subtitles=add_subtitles,
                chunk_size=chunk_size,
                language=language,
                cached_transcript=cached_transcript,
                cached_analysis_json=cached_analysis_json,
                progress_callback=update_progress,
                should_cancel=should_cancel,
                professional_hotwords=hotwords,
                include_broll=bool(task_details.get("include_broll", False)),
                bilingual_subtitles_mode=bilingual_mode,
                clip_theme=cth,
                target_clip_count=int(tcc) if tcc is not None else None,
            )
            stage_timings["pipeline_seconds"] = round(
                perf_counter() - pipeline_start, 3
            )

            use_bilingual_subtitles = bool(
                result.get("use_bilingual_subtitles", False)
            )

            # Re-fetch task so audio fade / style flags changed during analysis match clip encode
            task_details = await self.task_repo.get_task_by_id(self.db, task_id)
            if not task_details:
                logger.error(f"Task details not found for task_id: {task_id}")
                raise ValueError(f"Task details not found for task_id: {task_id}")
            db_fade_in = bool(task_details.get("audio_fade_in", False))
            db_fade_out = bool(task_details.get("audio_fade_out", False))
            audio_fade_in = db_fade_in
            audio_fade_out = db_fade_out
            if job_audio_fade_in is not None:
                audio_fade_in = audio_fade_in or bool(job_audio_fade_in)
            if job_audio_fade_out is not None:
                audio_fade_out = audio_fade_out or bool(job_audio_fade_out)
            burn_clip_title_zh = _burn_clip_title_zh_from_db(
                task_details.get("burn_clip_title_zh")
            )
            if (audio_fade_in != db_fade_in) or (audio_fade_out != db_fade_out):
                logger.info(
                    "Merged worker audio fade flags into task %s: db in/out=%s/%s "
                    "→ effective in/out=%s/%s (job in/out=%s/%s)",
                    task_id,
                    db_fade_in,
                    db_fade_out,
                    audio_fade_in,
                    audio_fade_out,
                    job_audio_fade_in,
                    job_audio_fade_out,
                )
            await self.task_repo.update_task_audio_fade(
                self.db, task_id, audio_fade_in, audio_fade_out
            )

            await self.cache_repo.upsert_cache(
                self.db,
                cache_key=cache_key,
                source_url=url,
                source_type=source_type,
                transcript_text=result.get("transcript"),
                analysis_json=result.get("analysis_json"),
            )

            # Render clips incrementally: render, save, notify one at a time
            segments_to_render = result.get("segments_to_render", [])
            video_path = Path(result["video_path"])
            total_clips = len(segments_to_render)
            clips_output_dir = Path(self.config.temp_dir) / "clips"
            clips_output_dir.mkdir(parents=True, exist_ok=True)

            clip_ids = []
            render_start = perf_counter()

            for i, segment in enumerate(segments_to_render):
                # Check cancellation
                if should_cancel and await should_cancel():
                    raise Exception("Task cancelled")

                # Latest task row (user may update audio fades / style while earlier clips render)
                td_refresh = await self.task_repo.get_task_by_id(self.db, task_id)
                if td_refresh:
                    audio_fade_in = bool(td_refresh.get("audio_fade_in", False))
                    audio_fade_out = bool(td_refresh.get("audio_fade_out", False))
                    burn_clip_title_zh = _burn_clip_title_zh_from_db(
                        td_refresh.get("burn_clip_title_zh")
                    )
                if job_audio_fade_in is not None:
                    audio_fade_in = audio_fade_in or bool(job_audio_fade_in)
                if job_audio_fade_out is not None:
                    audio_fade_out = audio_fade_out or bool(job_audio_fade_out)

                # Update progress: 70-95% spread across clips
                clip_progress = 70 + int(
                    ((i + 1) / total_clips) * 25
                ) if total_clips > 0 else 95
                await update_progress(
                    clip_progress,
                    f"Creating clip {i + 1}/{total_clips}...",
                )

                # Render single clip in thread pool
                clip_info = await self.video_service.create_single_clip(
                    video_path,
                    segment,
                    i,
                    clips_output_dir,
                    font_family,
                    font_size,
                    font_color,
                    caption_template,
                    output_format,
                    add_subtitles,
                    audio_fade_in,
                    audio_fade_out,
                    processing_mode,
                    use_bilingual_subtitles,
                    burn_clip_title_zh,
                    hotwords,
                    clip_subtitle_rewhisper=bool(
                        td_refresh.get("clip_subtitle_rewhisper", True)
                    )
                    if td_refresh
                    else bool(task_details.get("clip_subtitle_rewhisper", True)),
                    clip_subtitle_llm_refine=bool(
                        td_refresh.get("clip_subtitle_llm_refine", True)
                    )
                    if td_refresh
                    else bool(task_details.get("clip_subtitle_llm_refine", True)),
                    clip_zh_subtitle_polish=bool(
                        td_refresh.get("clip_zh_subtitle_polish", True)
                    )
                    if td_refresh
                    else bool(task_details.get("clip_zh_subtitle_polish", True)),
                )
                if clip_info is None:
                    continue  # Skip failed clip

                # Save to DB immediately
                clip_id = await self.clip_repo.create_clip(
                    self.db,
                    task_id=task_id,
                    filename=clip_info["filename"],
                    file_path=clip_info["path"],
                    start_time=clip_info["start_time"],
                    end_time=clip_info["end_time"],
                    duration=clip_info["duration"],
                    text=clip_info.get("text", ""),
                    relevance_score=clip_info.get("relevance_score", 0.0),
                    reasoning=clip_info.get("reasoning", ""),
                    clip_order=i + 1,
                    virality_score=clip_info.get("virality_score", 0),
                    hook_score=clip_info.get("hook_score", 0),
                    engagement_score=clip_info.get("engagement_score", 0),
                    value_score=clip_info.get("value_score", 0),
                    shareability_score=clip_info.get("shareability_score", 0),
                    hook_type=clip_info.get("hook_type"),
                    text_translation=clip_info.get("text_translation")
                    or clip_info.get("text_zh"),
                    title_zh=clip_info.get("title_zh"),
                    golden_quote_zh=clip_info.get("golden_quote_zh"),
                )
                await self.db.commit()
                clip_ids.append(clip_id)

                # Update task's clip IDs array
                await self.task_repo.update_task_clips(self.db, task_id, clip_ids)

                # Notify frontend via SSE
                if clip_ready_callback:
                    clip_record = await self.clip_repo.get_clip_by_id(
                        self.db, clip_id
                    )
                    if clip_record:
                        await clip_ready_callback(i, total_clips, clip_record)

            stage_timings["render_seconds"] = round(
                perf_counter() - render_start, 3
            )

            # Mark as completed
            await self.task_repo.update_task_status(
                self.db,
                task_id,
                "completed",
                progress=100,
                progress_message="Complete!",
            )

            if progress_callback:
                await progress_callback(100, "Complete!", "completed")

            await self.task_repo.update_task_runtime_metadata(
                self.db,
                task_id,
                completed_at=datetime.utcnow(),
                stage_timings_json=json.dumps(stage_timings),
                error_code="",
            )
            await self._send_completion_notification_if_needed(
                task_id=task_id,
                clips_count=len(clip_ids),
            )

            logger.info(
                f"Task {task_id} completed successfully with {len(clip_ids)} clips"
            )

            return {
                "task_id": task_id,
                "clips_count": len(clip_ids),
                "segments": result["segments"],
                "summary": result.get("summary"),
                "key_topics": result.get("key_topics"),
            }

        except Exception as e:
            logger.error(f"Error processing task {task_id}: {e}")
            # Any DB error may have put the session transaction in "aborted"; clear it
            # before writing error/cancelled status (avoids InFailedSQLTransactionError).
            await self.db.rollback()
            if str(e) == "Task cancelled":
                await self.task_repo.update_task_status(
                    self.db,
                    task_id,
                    "cancelled",
                    progress=0,
                    progress_message="Cancelled by user",
                )
                raise
            await self.task_repo.update_task_status(
                self.db, task_id, "error", progress_message=str(e)
            )
            error_code = "task_error"
            message = str(e).lower()
            if "download" in message or "youtube" in message:
                error_code = "download_error"
            elif "transcript" in message:
                error_code = "transcription_error"
            elif "analysis" in message:
                error_code = "analysis_error"
            elif "cancelled" in message:
                error_code = "cancelled"

            await self.task_repo.update_task_runtime_metadata(
                self.db,
                task_id,
                completed_at=datetime.utcnow(),
                error_code=error_code,
            )
            raise

    async def _send_completion_notification_if_needed(
        self, *, task_id: str, clips_count: int
    ) -> None:
        context = await self.task_repo.get_task_notification_context(self.db, task_id)
        if not context:
            logger.warning("Task %s missing notification context; skipping email", task_id)
            return

        if not context.get("notify_on_completion"):
            return

        if context.get("completion_notification_sent_at"):
            logger.info(
                "Completion notification already sent for task %s; skipping", task_id
            )
            return

        user_email = context.get("user_email")
        if not user_email:
            logger.warning(
                "Task %s has notify_on_completion enabled but user email is missing",
                task_id,
            )
            return

        email_service = TaskCompletionEmailService(self.config)
        if not email_service.is_configured:
            logger.warning(
                "Skipping completion notification for task %s because Resend is not configured",
                task_id,
            )
            return

        try:
            await email_service.send_task_completed_email(
                recipient=TaskCompletionRecipient(
                    email=user_email,
                    name=context.get("user_name"),
                    first_name=context.get("user_first_name"),
                ),
                task_id=task_id,
                source_title=context.get("source_title"),
                clips_count=clips_count,
            )
            stamped = await self.task_repo.mark_completion_notification_sent(
                self.db, task_id
            )
            if not stamped:
                logger.info(
                    "Completion notification stamp already existed for task %s",
                    task_id,
                )
        except Exception:
            logger.exception(
                "Failed to send completion notification for task %s",
                task_id,
            )

    async def get_task_with_clips(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task details with all clips."""
        task = await self.task_repo.get_task_by_id(self.db, task_id)

        if not task:
            return None

        if self._is_stale_queued_task(task):
            timeout_seconds = self.config.queued_task_timeout_seconds
            logger.warning(
                f"Task {task_id} stuck in queued status for over {timeout_seconds}s; marking as error"
            )
            await self.task_repo.update_task_status(
                self.db,
                task_id,
                "error",
                progress=0,
                progress_message=(
                    "Task timed out while waiting in queue. "
                    "Ensure the ARQ worker is running (e.g. `arq src.workers.tasks.WorkerSettings` from backend/)."
                ),
            )
            task = await self.task_repo.get_task_by_id(self.db, task_id)
            if not task:
                return None

        # Get clips
        clips = await self.clip_repo.get_clips_by_task(self.db, task_id)
        task["clips"] = clips
        task["clips_count"] = len(clips)

        return task

    async def get_user_tasks(
        self, user_id: str, limit: int = 50
    ) -> list[Dict[str, Any]]:
        """Get all tasks for a user."""
        return await self.task_repo.get_user_tasks(self.db, user_id, limit)

    async def delete_task(self, task_id: str) -> None:
        """Delete a task and all its associated clips."""
        # Delete all clips for this task
        await self.clip_repo.delete_clips_by_task(self.db, task_id)

        # Delete the task
        await self.task_repo.delete_task(self.db, task_id)

        logger.info(f"Deleted task {task_id} and all associated clips")

    async def update_task_settings(
        self,
        task_id: str,
        font_family: str,
        font_size: int,
        font_color: str,
        caption_template: str,
        include_broll: bool,
        audio_fade_in: bool,
        audio_fade_out: bool,
        processing_mode: str,
        apply_to_existing: bool,
        burn_clip_title_zh: bool = True,
        clip_subtitle_rewhisper: bool = True,
        clip_subtitle_llm_refine: bool = True,
        clip_zh_subtitle_polish: bool = True,
    ) -> Dict[str, Any]:
        """Update task-level settings and optionally regenerate all clips."""
        await self.task_repo.update_task_settings(
            self.db,
            task_id,
            font_family,
            font_size,
            font_color,
            caption_template,
            include_broll,
            audio_fade_in,
            audio_fade_out,
            processing_mode,
            burn_clip_title_zh=burn_clip_title_zh,
            clip_subtitle_rewhisper=clip_subtitle_rewhisper,
            clip_subtitle_llm_refine=clip_subtitle_llm_refine,
            clip_zh_subtitle_polish=clip_zh_subtitle_polish,
        )

        if apply_to_existing:
            await self.regenerate_all_clips_for_task(
                task_id,
                font_family,
                font_size,
                font_color,
                caption_template,
                audio_fade_in,
                audio_fade_out,
                processing_mode,
            )

        return await self.get_task_with_clips(task_id) or {}

    async def regenerate_all_clips_for_task(
        self,
        task_id: str,
        font_family: str,
        font_size: int,
        font_color: str,
        caption_template: str,
        audio_fade_in: bool,
        audio_fade_out: bool,
        processing_mode: str,
    ) -> None:
        """Regenerate all clips in a task using existing segment boundaries."""
        task = await self.task_repo.get_task_by_id(self.db, task_id)
        if not task:
            raise ValueError("Task not found")

        source_url = task.get("source_url")
        source_type = task.get("source_type")

        # If source_url is not directly available on the task, fetch it from the source table
        if not source_url and task.get("source_id"):
            source = await self.source_repo.get_source_by_id(self.db, task["source_id"])
            if source:
                source_url = source.get("url")

        output_format = "vertical"
        add_subtitles = True

        # Preserve original output_format and add_subtitles from task creation (stored in Redis)
        redis_client = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            password=self.config.redis_password,
            decode_responses=True,
        )
        try:
            source_payload = await redis_client.get(f"task_source:{task_id}")
            if source_payload:
                parsed = json.loads(source_payload)
                of = parsed.get("output_format", output_format)
                if of in ("vertical", "original"):
                    output_format = of
                asub = parsed.get("add_subtitles", add_subtitles)
                if isinstance(asub, bool):
                    add_subtitles = asub
        finally:
            await redis_client.close()

        if not source_url or not source_type:
            raise ValueError("Task source URL is missing; cannot regenerate clips")

        clips = await self.clip_repo.get_clips_by_task(self.db, task_id)
        if not clips:
            return

        video_path: Path
        if source_type == "youtube":
            downloaded = await self.video_service.download_video(source_url, task_id=task_id)
            if not downloaded:
                raise ValueError("Failed to download source video for regeneration")
            video_path = Path(downloaded)
        else:
            video_path = self.video_service.resolve_local_video_path(source_url)
            if not video_path.exists():
                raise ValueError("Source video file no longer exists")

        hotwords = (task.get("professional_hotwords") or "").strip() or None
        chunk_size = task.get("chunk_size") or 15000
        lang = task.get("language") or "auto"

        transcript, detected_lang = await self.video_service.generate_transcript(
            video_path,
            processing_mode=processing_mode,
            professional_hotwords=hotwords,
        )
        final_lang = lang if lang and lang != "auto" else (detected_lang or "en")
        tcc = task.get("target_clip_count")
        theme_val = (task.get("clip_theme") or "").strip() or None
        relevant = await self.video_service.analyze_transcript(
            transcript,
            chunk_size=chunk_size,
            language=final_lang,
            include_broll=bool(task.get("include_broll", False)),
            professional_hotwords=hotwords,
            clip_theme=theme_val,
            target_clip_count=int(tcc) if tcc is not None else None,
            processing_mode=processing_mode,
        )
        segments = self.video_service.build_segments_json(
            relevant,
            processing_mode,
            target_clip_count=int(tcc) if tcc is not None else None,
        )

        transcript_data = load_cached_transcript_data(video_path)
        bilingual_mode = (task.get("bilingual_subtitles_mode") or "auto").strip().lower()
        use_bilingual = should_use_bilingual_subtitles(
            bilingual_mode,
            transcript_data,
            add_subtitles,
        )
        if use_bilingual and transcript_data and segments:
            try:
                await apply_bilingual_phrase_translations(
                    video_path, transcript_data, segments
                )
            except Exception as e:
                logger.warning("Regenerate: bilingual translation skipped: %s", e)

        if segments:
            try:
                await fill_missing_segment_text_translations_zh(segments)
            except Exception as e:
                logger.warning(
                    "Regenerate: clip transcript zh translation fill skipped: %s", e
                )

        burn_clip_title_zh = _burn_clip_title_zh_from_db(task.get("burn_clip_title_zh"))
        clips_info = await self.video_service.create_video_clips(
            video_path,
            segments,
            font_family,
            font_size,
            font_color,
            caption_template,
            output_format,
            add_subtitles,
            audio_fade_in,
            audio_fade_out,
            processing_mode,
            use_bilingual,
            burn_clip_title_zh=burn_clip_title_zh,
            professional_hotwords=hotwords,
            clip_subtitle_rewhisper=bool(task.get("clip_subtitle_rewhisper", True)),
            clip_subtitle_llm_refine=bool(task.get("clip_subtitle_llm_refine", True)),
            clip_zh_subtitle_polish=bool(task.get("clip_zh_subtitle_polish", True)),
        )

        await self.clip_repo.delete_clips_by_task(self.db, task_id)

        clip_ids = []
        for i, clip_info in enumerate(clips_info):
            clip_id = await self.clip_repo.create_clip(
                self.db,
                task_id=task_id,
                filename=clip_info["filename"],
                file_path=clip_info["path"],
                start_time=clip_info["start_time"],
                end_time=clip_info["end_time"],
                duration=clip_info["duration"],
                text=clip_info.get("text") or "",
                relevance_score=clip_info.get("relevance_score", 0.5),
                reasoning=clip_info.get("reasoning")
                or "Regenerated with updated settings",
                clip_order=i + 1,
                virality_score=clip_info.get("virality_score", 0),
                hook_score=clip_info.get("hook_score", 0),
                engagement_score=clip_info.get("engagement_score", 0),
                value_score=clip_info.get("value_score", 0),
                shareability_score=clip_info.get("shareability_score", 0),
                hook_type=clip_info.get("hook_type"),
                text_translation=clip_info.get("text_translation")
                or clip_info.get("text_zh"),
                title_zh=clip_info.get("title_zh"),
                golden_quote_zh=clip_info.get("golden_quote_zh"),
            )
            clip_ids.append(clip_id)

        await self.task_repo.update_task_clips(self.db, task_id, clip_ids)

    async def trim_clip(
        self,
        task_id: str,
        clip_id: str,
        start_offset: float,
        end_offset: float,
    ) -> Dict[str, Any]:
        clip = await self.clip_repo.get_clip_by_id(self.db, clip_id)
        if not clip or clip["task_id"] != task_id:
            raise ValueError("Clip not found")

        input_path = Path(clip["file_path"])
        if not input_path.exists():
            raise ValueError("Clip file not found")

        output_path = trim_clip_file(
            input_path, Path(self.config.temp_dir) / "clips", start_offset, end_offset
        )
        clip_duration = max(0.1, clip["duration"] - start_offset - end_offset)

        start_seconds = parse_timestamp_to_seconds(clip["start_time"]) + start_offset
        end_seconds = start_seconds + clip_duration

        new_start = self._seconds_to_mmss(start_seconds)
        new_end = self._seconds_to_mmss(end_seconds)

        await self.clip_repo.update_clip(
            self.db,
            clip_id,
            output_path.name,
            str(output_path),
            new_start,
            new_end,
            clip_duration,
            clip.get("text") or "",
        )
        return (await self.clip_repo.get_clip_by_id(self.db, clip_id)) or {}

    async def split_clip(
        self, task_id: str, clip_id: str, split_time: float
    ) -> Dict[str, Any]:
        clip = await self.clip_repo.get_clip_by_id(self.db, clip_id)
        if not clip or clip["task_id"] != task_id:
            raise ValueError("Clip not found")

        input_path = Path(clip["file_path"])
        if not input_path.exists():
            raise ValueError("Clip file not found")

        first_path, second_path = split_clip_file(
            input_path, Path(self.config.temp_dir) / "clips", split_time
        )

        start_seconds = parse_timestamp_to_seconds(clip["start_time"])
        clamped_split = max(0.2, min(split_time, float(clip["duration"]) - 0.2))
        split_abs = start_seconds + clamped_split
        end_seconds = parse_timestamp_to_seconds(clip["end_time"])

        await self.clip_repo.update_clip(
            self.db,
            clip_id,
            first_path.name,
            str(first_path),
            clip["start_time"],
            self._seconds_to_mmss(split_abs),
            clamped_split,
            clip.get("text") or "",
        )

        await self.clip_repo.create_clip(
            self.db,
            task_id=task_id,
            filename=second_path.name,
            file_path=str(second_path),
            start_time=self._seconds_to_mmss(split_abs),
            end_time=self._seconds_to_mmss(end_seconds),
            duration=max(0.1, end_seconds - split_abs),
            text=clip.get("text") or "",
            relevance_score=clip.get("relevance_score", 0.5),
            reasoning=clip.get("reasoning") or "Split from original clip",
            clip_order=clip.get("clip_order", 1) + 1,
            virality_score=clip.get("virality_score", 0),
            hook_score=clip.get("hook_score", 0),
            engagement_score=clip.get("engagement_score", 0),
            value_score=clip.get("value_score", 0),
            shareability_score=clip.get("shareability_score", 0),
            hook_type=clip.get("hook_type"),
            text_translation=clip.get("text_translation"),
            title_zh=clip.get("title_zh"),
            golden_quote_zh=clip.get("golden_quote_zh"),
        )

        await self.clip_repo.reorder_task_clips(self.db, task_id)
        return {"message": "Clip split successfully"}

    async def merge_clips(self, task_id: str, clip_ids: list[str]) -> Dict[str, Any]:
        if len(clip_ids) < 2:
            raise ValueError("At least two clips are required to merge")

        clips = []
        for clip_id in clip_ids:
            clip = await self.clip_repo.get_clip_by_id(self.db, clip_id)
            if not clip or clip["task_id"] != task_id:
                raise ValueError("One or more clips not found")
            clips.append(clip)

        ordered = sorted(clips, key=lambda c: c.get("clip_order", 0))
        merged_path = merge_clip_files(
            [Path(c["file_path"]) for c in ordered],
            Path(self.config.temp_dir) / "clips",
        )

        start_time = ordered[0]["start_time"]
        end_time = ordered[-1]["end_time"]
        duration = sum(float(c.get("duration", 0.0)) for c in ordered)
        text = " ".join((c.get("text") or "").strip() for c in ordered if c.get("text"))
        zh_parts = [
            (c.get("text_translation") or "").strip()
            for c in ordered
            if (c.get("text_translation") or "").strip()
        ]
        merged_zh = "\n".join(zh_parts) if zh_parts else None
        title_parts = [
            (c.get("title_zh") or "").strip()
            for c in ordered
            if (c.get("title_zh") or "").strip()
        ]
        merged_title = " · ".join(title_parts)[:120] if title_parts else None
        g_parts = [
            (c.get("golden_quote_zh") or "").strip()
            for c in ordered
            if (c.get("golden_quote_zh") or "").strip()
        ]
        merged_golden = "\n".join(g_parts)[:200] if g_parts else None

        first = ordered[0]
        await self.clip_repo.update_clip(
            self.db,
            first["id"],
            merged_path.name,
            str(merged_path),
            start_time,
            end_time,
            duration,
            text,
            text_translation=merged_zh,
            title_zh=merged_title,
            golden_quote_zh=merged_golden,
        )

        for clip in ordered[1:]:
            await self.clip_repo.delete_clip(self.db, clip["id"])

        await self.clip_repo.reorder_task_clips(self.db, task_id)
        return {"message": "Clips merged successfully", "clip_id": first["id"]}

    async def update_clip_captions(
        self,
        task_id: str,
        clip_id: str,
        caption_text: str,
        position: str,
        highlight_words: list[str],
    ) -> Dict[str, Any]:
        clip = await self.clip_repo.get_clip_by_id(self.db, clip_id)
        if not clip or clip["task_id"] != task_id:
            raise ValueError("Clip not found")

        input_path = Path(clip["file_path"])
        if not input_path.exists():
            raise ValueError("Clip file not found")

        output_path = overlay_custom_captions(
            input_path,
            Path(self.config.temp_dir) / "clips",
            caption_text,
            position,
            highlight_words,
        )

        await self.clip_repo.update_clip(
            self.db,
            clip_id,
            output_path.name,
            str(output_path),
            clip["start_time"],
            clip["end_time"],
            clip["duration"],
            caption_text,
        )
        return (await self.clip_repo.get_clip_by_id(self.db, clip_id)) or {}

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Return aggregate processing performance metrics."""
        return await self.task_repo.get_performance_metrics(self.db)

    @staticmethod
    def _seconds_to_mmss(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        minutes = total // 60
        secs = total % 60
        return f"{minutes:02d}:{secs:02d}"
