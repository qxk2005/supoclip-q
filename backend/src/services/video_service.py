"""
Video service - handles video processing business logic.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, Awaitable
import logging
import json
import subprocess

from ..utils.async_helpers import run_in_thread
from ..youtube_utils import (
    async_download_youtube_video,
    async_get_youtube_video_info,
    async_get_youtube_video_title,
    get_youtube_video_id,
)
from ..video_utils import (
    get_video_transcript,
    create_clips_with_transitions,
    create_optimized_clip,
    parse_timestamp_to_seconds,
    load_cached_transcript_data,
    should_use_bilingual_subtitles,
)
from ..subtitle_translation import (
    apply_bilingual_phrase_translations,
    fill_missing_segment_text_translations_zh,
)
from ..ai import (
    TranscriptSegment,
    _virality_dict_from_segment_json,
    get_most_relevant_parts_by_transcript,
)
from ..config import Config

logger = logging.getLogger(__name__)
config = Config()
UPLOAD_URL_PREFIX = "upload://"


class VideoService:
    """Service for video processing operations."""

    @staticmethod
    def _get_file_duration(path: Path) -> Optional[float]:
        """Return video duration in seconds via ffprobe, or None on failure."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(path),
                ],
                capture_output=True, text=True, check=True,
            )
            return float(result.stdout.strip())
        except Exception:
            return None

    @staticmethod
    def resolve_local_video_path(url: str) -> Path:
        """Resolve uploaded-video references without exposing server filesystem paths."""
        if url.startswith(UPLOAD_URL_PREFIX):
            filename = Path(url.removeprefix(UPLOAD_URL_PREFIX)).name
            return Path(config.temp_dir) / "uploads" / filename
        return Path(url)

    @staticmethod
    async def download_video(url: str, task_id: Optional[str] = None) -> Optional[Path]:
        """
        Download a YouTube video asynchronously.
        """
        logger.info(f"Starting video download: {url}")
        video_path = await async_download_youtube_video(url, 3, task_id)

        if not video_path:
            logger.error(f"Failed to download video: {url}")
            return None

        logger.info(f"Video downloaded successfully: {video_path}")
        return video_path

    @staticmethod
    async def get_video_title(url: str) -> str:
        """
        Get video title asynchronously.
        Returns a default title if retrieval fails.
        """
        try:
            title = await async_get_youtube_video_title(url)
            return title or "YouTube Video"
        except Exception as e:
            logger.warning(f"Failed to get video title: {e}")
            return "YouTube Video"

    @staticmethod
    async def generate_transcript(
        video_path: Path,
        processing_mode: str = "balanced",
        professional_hotwords: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Generate transcript from video using faster-whisper.
        Runs in thread pool to avoid blocking.
        Returns a tuple of (transcript_text, language_code).
        """
        logger.info(f"Generating transcript for: {video_path}")
        if processing_mode == "fast":
            speech_model = config.fast_mode_transcript_model
        elif processing_mode == "balanced":
            speech_model = config.balanced_mode_transcript_model
        elif processing_mode == "quality":
            speech_model = config.quality_mode_transcript_model
        else:
            speech_model = config.whisper_model

        whisper_prompt: Optional[str] = None
        if professional_hotwords and professional_hotwords.strip():
            whisper_prompt = professional_hotwords.replace("\n", ", ").strip()[:2000]

        transcript, language = await run_in_thread(
            get_video_transcript, video_path, speech_model, whisper_prompt
        )
        logger.info(
            f"Transcript generated: {len(transcript)} characters, language: {language}"
        )
        return transcript, language

    @staticmethod
    async def analyze_transcript(
        transcript: str,
        chunk_size: int,
        language: str = "en",
        include_broll: bool = False,
        professional_hotwords: Optional[str] = None,
    ) -> Any:
        """
        Analyze transcript with AI to find relevant segments.
        This is already async, no need to wrap.
        """
        logger.info("Starting AI analysis of transcript")
        relevant_parts = await get_most_relevant_parts_by_transcript(
            transcript,
            include_broll=include_broll,
            chunk_size=chunk_size,
            language=language,
            professional_hotwords=professional_hotwords,
        )
        logger.info(
            f"AI analysis complete: {len(relevant_parts.most_relevant_segments)} segments found"
        )
        return relevant_parts

    @staticmethod
    async def create_video_clips(
        video_path: Path,
        segments: List[Dict[str, Any]],
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        caption_template: str = "default",
        output_format: str = "vertical",
        add_subtitles: bool = True,
        audio_fade_in: bool = False,
        audio_fade_out: bool = False,
        processing_mode: str = "fast",
        bilingual_subtitles: bool = False,
        burn_clip_title_zh: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Create standalone video clips from segments with optional subtitles.
        Runs in thread pool as video processing is CPU-intensive.
        output_format: 'vertical' (9:16) or 'original' (keep source size, faster).
        add_subtitles: False skips subtitles; with original format uses ffmpeg stream copy (no re-encode).
        """
        logger.info(
            f"Creating {len(segments)} video clips subtitles={add_subtitles} "
            f"burn_title_zh={burn_clip_title_zh}"
        )
        clips_output_dir = Path(config.temp_dir) / "clips"
        clips_output_dir.mkdir(parents=True, exist_ok=True)

        clips_info = await run_in_thread(
            create_clips_with_transitions,
            video_path,
            segments,
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
            bilingual_subtitles,
            burn_clip_title_zh,
        )

        logger.info(f"Successfully created {len(clips_info)} clips")
        return clips_info

    @staticmethod
    async def create_single_clip(
        video_path: Path,
        segment: Dict[str, Any],
        clip_index: int,
        output_dir: Path,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        caption_template: str = "default",
        output_format: str = "vertical",
        add_subtitles: bool = True,
        audio_fade_in: bool = False,
        audio_fade_out: bool = False,
        processing_mode: str = "fast",
        bilingual_subtitles: bool = False,
        burn_clip_title_zh: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Render a single clip in the thread pool and return clip_info dict, or None on failure."""
        try:
            start_seconds = parse_timestamp_to_seconds(segment["start_time"])
            end_seconds = parse_timestamp_to_seconds(segment["end_time"])
            duration = end_seconds - start_seconds

            if duration <= 0:
                logger.warning(
                    f"Skipping clip {clip_index + 1}: invalid duration {duration:.1f}s"
                )
                return None

            clip_filename = (
                f"clip_{clip_index + 1}_"
                f"{segment['start_time'].replace(':', '')}-"
                f"{segment['end_time'].replace(':', '')}.mp4"
            )
            clip_path = output_dir / clip_filename

            seg_text = (segment.get("text") or "").strip() or None
            title_zh = (segment.get("title_zh") or "").strip() or None
            golden_q = (segment.get("golden_quote_zh") or "").strip() or None
            success = await run_in_thread(
                create_optimized_clip,
                video_path,
                start_seconds,
                end_seconds,
                clip_path,
                add_subtitles,
                font_family,
                font_size,
                font_color,
                caption_template,
                output_format,
                audio_fade_in,
                audio_fade_out,
                processing_mode,
                bilingual_subtitles,
                seg_text,
                title_zh,
                golden_q,
                burn_clip_title_zh,
            )

            if not success:
                logger.error(f"Failed to create clip {clip_index + 1}")
                return None

            logger.info(f"Created clip {clip_index + 1}: {duration:.1f}s")
            return {
                "clip_id": clip_index + 1,
                "filename": clip_filename,
                "path": str(clip_path),
                "start_time": segment["start_time"],
                "end_time": segment["end_time"],
                "duration": duration,
                "text": segment.get("text", ""),
                "text_translation": segment.get("text_translation")
                or segment.get("text_zh"),
                "title_zh": segment.get("title_zh"),
                "golden_quote_zh": segment.get("golden_quote_zh"),
                "relevance_score": segment.get("relevance_score", 0.0),
                "reasoning": segment.get("reasoning", ""),
                "virality_score": segment.get("virality_score", 0),
                "hook_score": segment.get("hook_score", 0),
                "engagement_score": segment.get("engagement_score", 0),
                "value_score": segment.get("value_score", 0),
                "shareability_score": segment.get("shareability_score", 0),
                "hook_type": segment.get("hook_type"),
            }
        except Exception as e:
            logger.error(f"Error creating clip {clip_index + 1}: {e}")
            return None

    @staticmethod
    async def apply_single_transition(
        prev_clip_path: Path,
        current_clip_info: Dict[str, Any],
        clip_index: int,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Return the original clip info.

        Standalone exports intentionally do not depend on adjacent clips.
        """
        logger.info(
            "Skipping inter-clip transition for clip %s to preserve standalone exports",
            clip_index + 1,
        )
        return current_clip_info

    @staticmethod
    def determine_source_type(url: str) -> str:
        """Determine if source is YouTube or uploaded file."""
        video_id = get_youtube_video_id(url)
        return "youtube" if video_id else "video_url"

    @staticmethod
    def build_segments_json(relevant_parts: Any, processing_mode: str) -> List[Dict[str, Any]]:
        """Turn AI analysis into render-ready segment dicts."""
        raw_segments = relevant_parts.most_relevant_segments
        segments_json: List[Dict[str, Any]] = []
        allowed_hooks = (
            "question",
            "statement",
            "statistic",
            "story",
            "contrast",
            "none",
        )

        for segment in raw_segments:
            if isinstance(segment, dict):
                v = _virality_dict_from_segment_json(segment)
                raw_ht = segment.get("hook_type")
                hook_type = (
                    raw_ht if isinstance(raw_ht, str) and raw_ht in allowed_hooks else None
                )
                tz = segment.get("text_zh") or segment.get("text_translation")
                tz = (tz or "").strip() or None
                segments_json.append(
                    {
                        "start_time": segment.get("start_time"),
                        "end_time": segment.get("end_time"),
                        "text": segment.get("text", ""),
                        "text_translation": tz,
                        "title_zh": (segment.get("title_zh") or "").strip()[:80],
                        "golden_quote_zh": (segment.get("golden_quote_zh") or "").strip()[
                            :120
                        ],
                        "relevance_score": segment.get("relevance_score", 0.0),
                        "reasoning": segment.get("reasoning", ""),
                        "virality_score": v["total_score"],
                        "hook_score": v["hook_score"],
                        "engagement_score": v["engagement_score"],
                        "value_score": v["value_score"],
                        "shareability_score": v["shareability_score"],
                        "hook_type": hook_type,
                    }
                )
            elif isinstance(segment, TranscriptSegment):
                vir = segment.virality
                tz = (getattr(segment, "text_zh", None) or "").strip() or None
                hook_type = None
                if vir:
                    hook_type = (
                        vir.hook_type
                        if vir.hook_type in allowed_hooks
                        else "none"
                    )
                segments_json.append(
                    {
                        "start_time": segment.start_time,
                        "end_time": segment.end_time,
                        "text": segment.text,
                        "text_translation": tz,
                        "title_zh": (getattr(segment, "title_zh", None) or "").strip()[
                            :80
                        ],
                        "golden_quote_zh": (getattr(segment, "golden_quote_zh", None) or "").strip()[
                            :120
                        ],
                        "relevance_score": segment.relevance_score,
                        "reasoning": segment.reasoning,
                        "virality_score": vir.total_score if vir else 0,
                        "hook_score": vir.hook_score if vir else 0,
                        "engagement_score": vir.engagement_score if vir else 0,
                        "value_score": vir.value_score if vir else 0,
                        "shareability_score": vir.shareability_score if vir else 0,
                        "hook_type": hook_type,
                    }
                )
            else:
                vir = getattr(segment, "virality", None)
                text_zh = getattr(segment, "text_zh", None)
                tz = (text_zh or "").strip() or None
                hook_type = None
                if vir and getattr(vir, "hook_type", None) in allowed_hooks:
                    hook_type = vir.hook_type
                segments_json.append(
                    {
                        "start_time": getattr(segment, "start_time", ""),
                        "end_time": getattr(segment, "end_time", ""),
                        "text": getattr(segment, "text", "") or "",
                        "text_translation": tz,
                        "title_zh": (getattr(segment, "title_zh", None) or "").strip()[
                            :80
                        ],
                        "golden_quote_zh": (getattr(segment, "golden_quote_zh", None) or "").strip()[
                            :120
                        ],
                        "relevance_score": float(
                            getattr(segment, "relevance_score", 0.0) or 0.0
                        ),
                        "reasoning": getattr(segment, "reasoning", "") or "",
                        "virality_score": vir.total_score if vir else 0,
                        "hook_score": vir.hook_score if vir else 0,
                        "engagement_score": vir.engagement_score if vir else 0,
                        "value_score": vir.value_score if vir else 0,
                        "shareability_score": vir.shareability_score if vir else 0,
                        "hook_type": hook_type,
                    }
                )

        def _ensure_title_zh(seg: Dict[str, Any]) -> None:
            tz = (seg.get("title_zh") or "").strip()
            if tz:
                seg["title_zh"] = tz[:80]
                return
            r = (seg.get("reasoning") or "").strip()
            if r:
                line = r.split("。")[0].split(".")[0].split("\n")[0].strip()
                seg["title_zh"] = (line[:28] if line else "")[:80]
            else:
                seg["title_zh"] = ""

        def _ensure_golden_quote_zh(seg: Dict[str, Any]) -> None:
            g = (seg.get("golden_quote_zh") or "").strip()
            if g:
                seg["golden_quote_zh"] = g[:120]
                return
            t = (seg.get("title_zh") or "").strip()
            seg["golden_quote_zh"] = (t[:120] if t else "")

        for seg in segments_json:
            _ensure_title_zh(seg)
            _ensure_golden_quote_zh(seg)

        if processing_mode == "fast":
            segments_json = segments_json[: config.fast_mode_max_clips]
        return segments_json

    @staticmethod
    async def process_video_complete(
        url: str,
        source_type: str,
        task_id: Optional[str] = None,
        font_family: str = "TikTokSans-Regular",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        caption_template: str = "default",
        processing_mode: str = "fast",
        output_format: str = "vertical",
        add_subtitles: bool = True,
        chunk_size: int = 15000,
        language: str = "auto",
        cached_transcript: Optional[str] = None,
        cached_analysis_json: Optional[str] = None,
        progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
        should_cancel: Optional[Callable[[], Awaitable[bool]]] = None,
        professional_hotwords: Optional[str] = None,
        include_broll: bool = False,
        bilingual_subtitles_mode: str = "auto",
    ) -> Dict[str, Any]:
        """
        Complete video processing pipeline.
        Returns dict with segments and clips info.

        progress_callback: Optional function to call with progress updates
                          Signature: async def callback(progress: int, message: str, status: str)
        """
        try:
            # Step 1: Get video path (download or use existing)
            if should_cancel and await should_cancel():
                raise Exception("Task cancelled")

            if progress_callback:
                await progress_callback(10, "Downloading video...", "processing")

            if source_type == "youtube":
                video_info = await async_get_youtube_video_info(url, task_id=task_id)
                if video_info:
                    duration = video_info.get("duration", 0)
                    if duration and duration > config.max_video_duration:
                        mins = config.max_video_duration // 60
                        raise Exception(
                            f"Video is too long ({duration // 60} min). "
                            f"Maximum allowed duration is {mins} minutes."
                        )

                video_path = await VideoService.download_video(url, task_id=task_id)
                if not video_path:
                    raise Exception("Failed to download video")
            else:
                video_path = VideoService.resolve_local_video_path(url)
                if not video_path.exists():
                    raise Exception("Video file not found")

            # Post-download duration guard (catches cases where preflight info was unavailable)
            file_duration = VideoService._get_file_duration(video_path)
            if file_duration and file_duration > config.max_video_duration:
                mins = config.max_video_duration // 60
                raise Exception(
                    f"Video is too long ({int(file_duration) // 60} min). "
                    f"Maximum allowed duration is {mins} minutes."
                )

            # Step 2: Generate transcript
            if should_cancel and await should_cancel():
                raise Exception("Task cancelled")

            if progress_callback:
                await progress_callback(30, "Generating transcript...", "processing")

            need_word_timestamps = add_subtitles or (
                (bilingual_subtitles_mode or "auto").strip().lower() != "off"
            )

            transcript = cached_transcript
            detected_lang = "en"  # Default language
            if not transcript:
                logger.info("No cached transcript found, generating new one.")
                transcript, detected_lang = await VideoService.generate_transcript(
                    video_path,
                    processing_mode=processing_mode,
                    professional_hotwords=professional_hotwords,
                )
                logger.info(f"Transcript generated with length: {len(transcript)}")
            elif need_word_timestamps:
                td_check = load_cached_transcript_data(video_path)
                if not td_check or not td_check.get("segments"):
                    logger.info(
                        "Cached transcript text without word timings; re-running speech-to-text."
                    )
                    transcript, detected_lang = await VideoService.generate_transcript(
                        video_path,
                        processing_mode=processing_mode,
                        professional_hotwords=professional_hotwords,
                    )

            transcript_data = load_cached_transcript_data(video_path)
            if transcript_data and transcript_data.get("language"):
                detected_lang = transcript_data.get("language") or detected_lang

            use_bilingual_subtitles = should_use_bilingual_subtitles(
                bilingual_subtitles_mode,
                transcript_data,
                add_subtitles,
            )

            # Step 3: AI analysis
            if should_cancel and await should_cancel():
                raise Exception("Task cancelled")

            if progress_callback:
                await progress_callback(
                    50, "Analyzing content with AI...", "processing"
                )

            logger.info("Before AI analysis")
            relevant_parts = None
            if cached_analysis_json:
                try:
                    cached_analysis = json.loads(cached_analysis_json)
                    segments = cached_analysis.get("most_relevant_segments", [])

                    class _SimpleResult:
                        def __init__(self, payload: Dict[str, Any]):
                            self.summary = payload.get("summary")
                            self.key_topics = payload.get("key_topics")
                            self.most_relevant_segments = payload.get(
                                "most_relevant_segments", []
                            )

                    relevant_parts = _SimpleResult(
                        {
                            "summary": cached_analysis.get("summary"),
                            "key_topics": cached_analysis.get("key_topics", []),
                            "most_relevant_segments": segments,
                        }
                    )
                except Exception:
                    relevant_parts = None

            if relevant_parts is None:
                # "auto" is truthy and would incorrectly skip detected_lang
                lang_raw = (language or "").strip().lower()
                final_lang = (
                    language
                    if language and lang_raw not in ("auto", "unknown", "")
                    else (detected_lang or "en")
                )
                relevant_parts = await VideoService.analyze_transcript(
                    transcript,
                    chunk_size=chunk_size,
                    language=final_lang,
                    include_broll=include_broll,
                    professional_hotwords=professional_hotwords,
                )

            # Step 4: segment list + optional bilingual translation
            if should_cancel and await should_cancel():
                raise Exception("Task cancelled")

            segments_json = VideoService.build_segments_json(
                relevant_parts, processing_mode
            )

            if (
                use_bilingual_subtitles
                and transcript_data
                and segments_json
            ):
                if progress_callback:
                    await progress_callback(
                        62, "Translating bilingual subtitles...", "processing"
                    )
                try:
                    await apply_bilingual_phrase_translations(
                        video_path, transcript_data, segments_json
                    )
                except Exception as e:
                    logger.warning("Bilingual translation skipped: %s", e)

            if segments_json:
                if progress_callback:
                    await progress_callback(
                        64,
                        "Translating clip transcripts to Chinese...",
                        "processing",
                    )
                try:
                    await fill_missing_segment_text_translations_zh(segments_json)
                except Exception as e:
                    logger.warning("Clip transcript zh translation fill skipped: %s", e)

            if progress_callback:
                await progress_callback(70, "Creating video clips...", "processing")

            return {
                "segments": segments_json,
                "segments_to_render": segments_json,
                "video_path": str(video_path),
                "clips": [],
                "summary": relevant_parts.summary if relevant_parts else None,
                "key_topics": relevant_parts.key_topics if relevant_parts else None,
                "transcript": transcript,
                "use_bilingual_subtitles": use_bilingual_subtitles,
                "analysis_json": json.dumps(
                    {
                        "summary": relevant_parts.summary if relevant_parts else None,
                        "key_topics": relevant_parts.key_topics
                        if relevant_parts
                        else [],
                        "most_relevant_segments": segments_json,
                    }
                ),
            }

        except Exception as e:
            logger.error(f"Error in video processing pipeline: {e}")
            raise
