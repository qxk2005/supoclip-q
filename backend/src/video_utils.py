"""
Utility functions for video-related operations.
Optimized for MoviePy v2, and high-quality output.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import os
import re
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor
import json

import cv2
from moviepy import VideoFileClip, CompositeVideoClip, TextClip, ColorClip
import moviepy.audio.fx as afx
from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeIn, FadeOut
from faster_whisper import WhisperModel
import srt
from datetime import timedelta

from .config import Config
from .caption_templates import get_template, CAPTION_TEMPLATES
from .font_registry import find_font_path

logger = logging.getLogger(__name__)
config = Config()
TRANSCRIPT_CACHE_SCHEMA_VERSION = 2

# Names accepted by faster-whisper's download_model (see faster_whisper.utils).
_WHISPER_MODEL_SIZES = frozenset(
    {
        "tiny.en",
        "tiny",
        "base.en",
        "base",
        "small.en",
        "small",
        "medium.en",
        "medium",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "distil-large-v2",
        "distil-medium.en",
        "distil-small.en",
        "distil-large-v3",
        "distil-large-v3.5",
        "large-v3-turbo",
        "turbo",
    }
)
# Legacy / mistaken labels that are not valid size names.
_WHISPER_SIZE_ALIASES = {
    "best": "large",
    "nano": "tiny",
}


def resolve_whisper_model_size(raw: str) -> str:
    """Map user-facing labels to a valid faster-whisper model size name."""
    name = (raw or "base").strip().lower()
    if not name:
        name = "base"
    name = _WHISPER_SIZE_ALIASES.get(name, name)
    if name not in _WHISPER_MODEL_SIZES:
        logger.warning(
            "Unknown Whisper model size %r, falling back to base", raw
        )
        return "base"
    return name


class VideoProcessor:
    """Handles video processing operations with optimized settings."""

    def __init__(
        self,
        font_family: str = "THEBOLDFONT",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
        text_for_font_detection: str = "",
    ):
        self.font_family = font_family
        self.font_size = font_size
        self.font_color = font_color

        # Detect if text contains Chinese characters and override font
        if text_for_font_detection and any('\u4e00' <= char <= '\u9fff' for char in text_for_font_detection):
            logger.info("Chinese characters detected, switching to SourceHanSansSC-Regular font.")
            self.font_family = "SourceHanSansSC-Regular.otf"

        resolved_font = find_font_path(self.font_family, allow_all_user_fonts=True)
        if not resolved_font:
            resolved_font = find_font_path("TikTokSans-Regular")
        if not resolved_font:
            resolved_font = find_font_path("THEBOLDFONT")
        self.font_path = str(resolved_font) if resolved_font else ""
        logger.info(f"VideoProcessor using font path: {self.font_path}")

    def get_optimal_encoding_settings(
        self,
        target_quality: str = "high",
    ) -> Dict[str, Any]:
        """Get optimal encoding settings for different quality levels."""
        settings = {
            "high": {
                "codec": "libx264",
                "audio_codec": "aac",
                "audio_bitrate": "256k",
                "preset": "slow",
                "ffmpeg_params": [
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-profile:v",
                    "high",
                    "-movflags",
                    "+faststart",
                    "-sws_flags",
                    "lanczos",
                ],
            },
            "medium": {
                "codec": "libx264",
                "audio_codec": "aac",
                "bitrate": "4000k",
                "audio_bitrate": "192k",
                "preset": "fast",
                "ffmpeg_params": ["-crf", "23", "-pix_fmt", "yuv420p"],
            },
        }
        return settings.get(target_quality, settings["high"])


def get_video_transcript(
    video_path: Path,
    speech_model: str = "base",
    initial_prompt: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Get transcript using faster-whisper and return formatted text and language.
    """
    logger.info(f"Getting transcript for: {video_path}")

    try:
        resolved_model = resolve_whisper_model_size(speech_model)
        model = WhisperModel(resolved_model, device="cpu", compute_type="int8")
        transcribe_kw: Dict[str, Any] = {"word_timestamps": True}
        if initial_prompt and initial_prompt.strip():
            transcribe_kw["initial_prompt"] = initial_prompt.strip()[:2000]
        segments, info = model.transcribe(str(video_path), **transcribe_kw)

        transcript_data = {
            "segments": [],
            "text": "",
            "language": info.language,
            "language_probability": info.language_probability,
        }
        full_text = []

        for segment in segments:
            segment_data = {
                "id": segment.id,
                "seek": segment.seek,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "tokens": segment.tokens,
                "temperature": segment.temperature,
                "avg_logprob": segment.avg_logprob,
                "compression_ratio": segment.compression_ratio,
                "no_speech_prob": segment.no_speech_prob,
                "words": [],
            }
            if hasattr(segment, "words"):
                for word in segment.words:
                    segment_data["words"].append(
                        {
                            "start": word.start,
                            "end": word.end,
                            "word": word.word,
                            "probability": word.probability,
                        }
                    )
            transcript_data["segments"].append(segment_data)
            full_text.append(segment.text)

        transcript_data["text"] = "".join(full_text)
        cache_transcript_data(video_path, transcript_data)

        # Format for analysis (similar to old format)
        formatted_lines = []
        for segment in transcript_data["segments"]:
            start_time = format_s_to_timestamp(segment["start"])
            end_time = format_s_to_timestamp(segment["end"])
            formatted_lines.append(f"[{start_time} - {end_time}] {segment['text']}")

        result = "\n".join(formatted_lines)
        logger.info(
            f"Transcript formatted: {len(formatted_lines)} segments, {len(result)} chars"
        )
        return result, info.language

    except Exception as e:
        logger.error(f"Error in transcription: {e}")
        raise

def format_s_to_timestamp(s: float) -> str:
    """Format seconds to MM:SS format."""
    minutes = int(s) // 60
    seconds = int(s) % 60
    return f"{minutes:02d}:{seconds:02d}"


def cache_transcript_data(video_path: Path, transcript_data: Dict) -> None:
    """Cache faster-whisper transcript data for subtitle generation."""
    cache_path = video_path.with_suffix(".transcript_cache.json")
    with open(cache_path, "w") as f:
        json.dump(transcript_data, f)
    logger.info(f"Cached transcript data to {cache_path}")


def load_cached_transcript_data(video_path: Path) -> Optional[Dict]:
    """Load cached faster-whisper transcript data."""
    cache_path = video_path.with_suffix(".transcript_cache.json")
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load transcript cache: {e}")
        return None


def format_ms_to_timestamp(ms: int) -> str:
    """Format milliseconds to MM:SS format."""
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def round_to_even(value: int) -> int:
    """Round integer to nearest even number for H.264 compatibility."""
    return value - (value % 2)


def get_scaled_font_size(base_font_size: int, video_width: int) -> int:
    """Scale caption font size by output width with sensible bounds."""
    scaled_size = int(base_font_size * (video_width / 720))
    return max(24, min(64, scaled_size))

def get_subtitle_max_width(video_width: int) -> int:
    """Return max subtitle text width with horizontal safe margins."""
    horizontal_padding = max(40, int(video_width * 0.06))
    return max(200, video_width - (horizontal_padding * 2))

def get_safe_vertical_position(
    video_height: int,
    text_height: int,
    position_y: float,
) -> int:
    """Return subtitle y position clamped inside a top/bottom safe area."""
    min_top_padding = max(40, int(video_height * 0.05))
    min_bottom_padding = max(120, int(video_height * 0.10))

    # position_y now represents the anchor point (e.g., 0.8 means 80% from the top)
    # The final position will be the top of the text clip
    desired_y = int(video_height * position_y)

    # Ensure the entire text clip is within the safe area
    # Adjust so the bottom of the text clip does not go into the padding
    max_y = video_height - min_bottom_padding - text_height
    
    # The final y is the top of the text clip, so we clamp it between top padding and max_y
    final_y = max(min_top_padding, min(desired_y, max_y))
    
    return final_y

def detect_optimal_crop_region(
    video_clip: VideoFileClip,
    start_time: float,
    end_time: float,
    target_ratio: float = 9 / 16,
) -> Tuple[int, int, int, int]:
    """Detect optimal crop region using improved face detection."""
    try:
        original_width, original_height = video_clip.size

        # Calculate target dimensions and ensure they're even
        if original_width / original_height > target_ratio:
            new_width = round_to_even(int(original_height * target_ratio))
            new_height = round_to_even(original_height)
        else:
            new_width = round_to_even(original_width)
            new_height = round_to_even(int(original_width / target_ratio))

        # Try improved face detection
        face_centers = detect_faces_in_clip(video_clip, start_time, end_time)

        # Calculate crop position
        if face_centers:
            # Use weighted average of face centers with temporal consistency
            total_weight = sum(
                area * confidence for _, _, area, confidence in face_centers
            )
            if total_weight > 0:
                weighted_x = (
                    sum(
                        x * area * confidence for x, y, area, confidence in face_centers
                    )
                    / total_weight
                )
                weighted_y = (
                    sum(
                        y * area * confidence for x, y, area, confidence in face_centers
                    )
                    / total_weight
                )

                # Add slight bias towards upper portion for better face framing
                weighted_y = max(0, weighted_y - new_height * 0.1)

                x_offset = max(
                    0, min(int(weighted_x - new_width // 2), original_width - new_width)
                )
                y_offset = max(
                    0,
                    min(
                        int(weighted_y - new_height // 2),
                        original_height - new_height,
                    ),
                )

                logger.info(
                    f"Face-centered crop: {len(face_centers)} faces detected with improved algorithm"
                )
            else:
                # Center crop
                x_offset = (
                    (original_width - new_width) // 2
                    if original_width > new_width
                    else 0
                )
                y_offset = (
                    (original_height - new_height) // 2
                    if original_height > new_height
                    else 0
                )
        else:
            # Center crop
            x_offset = (
                (original_width - new_width) // 2 if original_width > new_width else 0
            )
            y_offset = (
                (original_height - new_height) // 2
                if original_height > new_height
                else 0
            )
            logger.info("Using center crop (no faces detected)")

        # Ensure offsets are even too
        x_offset = round_to_even(x_offset)
        y_offset = round_to_even(y_offset)

        logger.info(
            f"Crop dimensions: {new_width}x{new_height} at offset ({x_offset}, {y_offset})"
        )
        return (x_offset, y_offset, new_width, new_height)

    except Exception as e:
        logger.error(f"Error in crop detection: {e}")
        # Fallback to center crop
        original_width, original_height = video_clip.size
        if original_width / original_height > target_ratio:
            new_width = round_to_even(int(original_height * target_ratio))
            new_height = round_to_even(original_height)
        else:
            new_width = round_to_even(original_width)
            new_height = round_to_even(int(original_width / target_ratio))

        x_offset = (
            round_to_even((original_width - new_width) // 2)
            if original_width > new_width
            else 0
        )
        y_offset = (
            round_to_even((original_height - new_height) // 2)
            if original_height > new_height
            else 0
        )

        return (x_offset, y_offset, new_width, new_height)

def detect_faces_in_clip(
    video_clip: VideoFileClip,
    start_time: float,
    end_time: float,
) -> List[Tuple[int, int, int, float]]:
    """
    Improved face detection using multiple methods and temporal consistency.
    Returns list of (x, y, area, confidence) tuples.
    """
    face_centers = []

    try:
        # Try to use MediaPipe (most accurate)
        mp_face_detection = None
        try:
            import mediapipe as mp

            mp_face_detection = mp.solutions.face_detection.FaceDetection(
                model_selection=0,  # 0 for short-range (better for close faces)
                min_detection_confidence=0.5,
            )
            logger.info("Using MediaPipe face detector")
        except ImportError:
            logger.info("MediaPipe not available, falling back to OpenCV")
        except Exception as e:
            logger.warning(f"MediaPipe face detector failed to initialize: {e}")

        # Initialize OpenCV face detectors as fallback
        haar_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        # Try to load DNN face detector (more accurate than Haar)
        dnn_net = None
        try:
            # Load OpenCV's DNN face detector
            prototxt_path = cv2.data.haarcascades.replace(
                "haarcascades", "opencv_face_detector.pbtxt"
            )
            model_path = cv2.data.haarcascades.replace(
                "haarcascades", "opencv_face_detector_uint8.pb"
            )

            # If DNN model files don't exist, we'll fall back to Haar cascade
            import os

            if os.path.exists(prototxt_path) and os.path.exists(model_path):
                dnn_net = cv2.dnn.readNetFromTensorflow(model_path, prototxt_path)
                logger.info("OpenCV DNN face detector loaded as backup")
            else:
                logger.info("OpenCV DNN face detector not available")
        except Exception:
            logger.info("OpenCV DNN face detector failed to load")

        # Sample more frames for better face detection (every 0.5 seconds)
        duration = end_time - start_time
        sample_interval = min(0.5, duration / 10)  # At least 10 samples, max every 0.5s
        sample_times = []

        current_time = start_time
        while current_time < end_time:
            sample_times.append(current_time)
            current_time += sample_interval

        # Ensure we always sample the middle and end
        if duration > 1.0:
            middle_time = start_time + duration / 2
            if middle_time not in sample_times:
                sample_times.append(middle_time)

        sample_times = [t for t in sample_times if t < end_time]
        logger.info(f"Sampling {len(sample_times)} frames for face detection")

        for sample_time in sample_times:
            try:
                frame = video_clip.get_frame(sample_time)
                height, width = frame.shape[:2]
                detected_faces = []

                # Try MediaPipe first (most accurate)
                if mp_face_detection is not None:
                    try:
                        # MediaPipe expects RGB format
                        results = mp_face_detection.process(frame)

                        if results.detections:
                            for detection in results.detections:
                                bbox = detection.location_data.relative_bounding_box
                                confidence = detection.score[0]

                                # Convert relative coordinates to absolute
                                x = int(bbox.xmin * width)
                                y = int(bbox.ymin * height)
                                w = int(bbox.width * width)
                                h = int(bbox.height * height)

                                if w > 30 and h > 30:  # Minimum face size
                                    detected_faces.append((x, y, w, h, confidence))
                    except Exception as e:
                        logger.warning(
                            f"MediaPipe detection failed for frame at {sample_time}s: {e}"
                        )

                # If MediaPipe didn't find faces, try DNN detector
                if not detected_faces and dnn_net is not None:
                    try:
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        blob = cv2.dnn.blobFromImage(
                            frame_bgr, 1.0, (300, 300), [104, 117, 123]
                        )
                        dnn_net.setInput(blob)
                        detections = dnn_net.forward()

                        for i in range(detections.shape[2]):
                            confidence = detections[0, 0, i, 2]
                            if confidence > 0.5:  # Confidence threshold
                                x1 = int(detections[0, 0, i, 3] * width)
                                y1 = int(detections[0, 0, i, 4] * height)
                                x2 = int(detections[0, 0, i, 5] * width)
                                y2 = int(detections[0, 0, i, 6] * height)

                                w = x2 - x1
                                h = y2 - y1

                                if w > 30 and h > 30:  # Minimum face size
                                    detected_faces.append((x1, y1, w, h, confidence))
                    except Exception as e:
                        logger.warning(
                            f"DNN detection failed for frame at {sample_time}s: {e}"
                        )

                # If still no faces found, use Haar cascade
                if not detected_faces:
                    try:
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

                        faces = haar_cascade.detectMultiScale(
                            gray,
                            scaleFactor=1.05,  # More sensitive
                            minNeighbors=3,  # Less strict
                            minSize=(40, 40),  # Smaller minimum size
                            maxSize=(
                                int(width * 0.7),
                                int(height * 0.7),
                            ),  # Maximum size limit
                        )

                        for x, y, w, h in faces:
                            # Estimate confidence based on face size and position
                            face_area = w * h
                            relative_size = face_area / (width * height)
                            confidence = min(
                                0.9, 0.3 + relative_size * 2
                            )  # Rough confidence estimate
                            detected_faces.append((x, y, w, h, confidence))
                    except Exception as e:
                        logger.warning(
                            f"Haar cascade detection failed for frame at {sample_time}s: {e}"
                        )

                # Process detected faces
                for x, y, w, h, confidence in detected_faces:
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2
                    face_area = w * h

                    # Filter out very small or very large faces
                    frame_area = width * height
                    relative_area = face_area / frame_area

                    if (
                        0.005 < relative_area < 0.3
                    ):  # Face should be 0.5% to 30% of frame
                        face_centers.append(
                            (face_center_x, face_center_y, face_area, confidence)
                        )

            except Exception as e:
                logger.warning(f"Error detecting faces in frame at {sample_time}s: {e}")
                continue

        # Close MediaPipe detector
        if mp_face_detection is not None:
            mp_face_detection.close()

        # Remove outliers (faces that are very far from the median position)
        if len(face_centers) > 2:
            face_centers = filter_face_outliers(face_centers)

        logger.info(f"Detected {len(face_centers)} reliable face centers")
        return face_centers

    except Exception as e:
        logger.error(f"Error in face detection: {e}")
        return []

def filter_face_outliers(
    face_centers: List[Tuple[int, int, int, float]],
) -> List[Tuple[int, int, int, float]]:
    """Remove face detections that are outliers (likely false positives)."""
    if len(face_centers) < 3:
        return face_centers

    try:
        # Calculate median position
        x_positions = [x for x, y, area, conf in face_centers]
        y_positions = [y for x, y, area, conf in face_centers]

        median_x = np.median(x_positions)
        median_y = np.median(y_positions)

        # Calculate standard deviation
        std_x = np.std(x_positions)
        std_y = np.std(y_positions)

        # Filter out faces that are more than 2 standard deviations away
        filtered_faces = []
        for face in face_centers:
            x, y, area, conf = face
            if abs(x - median_x) <= 2 * std_x and abs(y - median_y) <= 2 * std_y:
                filtered_faces.append(face)

        logger.info(
            f"Filtered {len(face_centers)} -> {len(filtered_faces)} faces (removed outliers)"
        )
        return (
            filtered_faces if filtered_faces else face_centers
        )  # Return original if all filtered

    except Exception as e:
        logger.warning(f"Error filtering face outliers: {e}")
        return face_centers

def parse_timestamp_to_seconds(timestamp_str: str) -> float:
    """Parse timestamp string to seconds."""
    try:
        timestamp_str = timestamp_str.strip()
        logger.info(f"Parsing timestamp: '{timestamp_str}'")  # Debug logging

        if ":" in timestamp_str:
            parts = timestamp_str.split(":")
            if len(parts) == 2:
                minutes, seconds = map(int, parts)
                result = minutes * 60 + seconds
                logger.info(f"Parsed '{timestamp_str}' -> {result}s")
                return result
            elif len(parts) == 3:  # HH:MM:SS format
                hours, minutes, seconds = map(int, parts)
                result = hours * 3600 + minutes * 60 + seconds
                logger.info(f"Parsed '{timestamp_str}' -> {result}s")
                return result

        # Try parsing as pure seconds
        result = float(timestamp_str)
        logger.info(f"Parsed '{timestamp_str}' as seconds -> {result}s")
        return result

    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return 0.0

def get_words_in_range(
    transcript_data: Dict,
    clip_start: float,
    clip_end: float,
) -> List[Dict]:
    """Extract words that fall within a clip timerange."""
    if not transcript_data or not transcript_data.get("segments"):
        return []

    relevant_words = []
    for segment in transcript_data["segments"]:
        for word_data in segment.get("words", []):
            word_start = word_data["start"]
            word_end = word_data["end"]

            if word_start < clip_end and word_end > clip_start:
                relative_start = max(0, word_start - clip_start)
                relative_end = min(clip_end - clip_start, word_end - clip_start)

                if relative_end > relative_start:
                    relevant_words.append({
                        "text": word_data["word"],
                        "start": relative_start,
                        "end": relative_end,
                        "confidence": word_data.get("probability", 1.0),
                    })
    return relevant_words


def _norm_token_for_align(raw: str) -> str:
    """Loosen ASR vs reference equality (punctuation + light apostrophe noise)."""
    t = _strip_token_edges_for_key(raw)
    if not t:
        return ""
    return t.replace("'", "").replace("'", "").replace("`", "")


def _token_lists_match_subsequence(needle: List[str], haystack: List[str]) -> bool:
    """*needle* appears as an ordered subsequence of *haystack* (same length units)."""
    if not needle:
        return True
    i = 0
    for tok in haystack:
        if i < len(needle) and _norm_token_for_align(tok) == _norm_token_for_align(needle[i]):
            i += 1
    return i == len(needle)


def _minimal_contiguous_window_for_subsequence(
    haystack: List[str],
    needle: List[str],
) -> Optional[Tuple[int, int]]:
    """
    Smallest half-open range [left, right) into *haystack* such that *needle* matches
    as an ordered subsequence of haystack[left:right].
    """
    n, m = len(haystack), len(needle)
    if m == 0:
        return (0, n)
    if m > n or not needle:
        return None
    # Increasing width → first hit is minimal-width.
    for width in range(m, n + 1):
        for left in range(0, n - width + 1):
            right = left + width
            if _token_lists_match_subsequence(needle, haystack[left:right]):
                return (left, right)
    return None


def _trim_latin_words_to_reference_text(words: List[Dict], reference_text: str) -> List[Dict]:
    ref_toks = [
        t
        for t in (_norm_token_for_align(x) for x in reference_text.split())
        if t
    ]
    if not ref_toks:
        return words
    asr_toks = [_norm_token_for_align(w.get("text") or "") for w in words]
    span = _minimal_contiguous_window_for_subsequence(asr_toks, ref_toks)
    if span is None:
        return words
    left, right = span
    return words[left:right]


# Punctuation ignored when matching ASR words to AI segment.text (ASR has no marks).
_SUBTITLE_ALIGN_SKIP_CHARS: frozenset[str] = frozenset(
    "，。！？、；：（）【】《》…—「」『』"
    + ",.?!;:\"'()[]"
    + "\u201c\u201d\u2018\u2019"  # “”‘’
)


def _reference_cjk_chars_for_trim_match(reference_text: str) -> List[str]:
    """Content characters only — aligns transcript words with segment.text that adds 。，等."""
    return [
        c
        for c in reference_text
        if not c.isspace() and c not in _SUBTITLE_ALIGN_SKIP_CHARS
    ]


def _trim_cjk_words_to_reference_text(words: List[Dict], reference_text: str) -> List[Dict]:
    ref_chars = _reference_cjk_chars_for_trim_match(reference_text)
    if not ref_chars:
        return words
    # Map each non-space character to its word index (Whisper / ASR word units).
    char_word_idx: List[int] = []
    chars_flat: List[str] = []
    for wi, w in enumerate(words):
        for ch in w.get("text") or "":
            if ch.isspace():
                continue
            chars_flat.append(ch)
            char_word_idx.append(wi)
    if not chars_flat:
        return words
    ref_s = "".join(ref_chars)
    hay_s = "".join(chars_flat)
    if ref_s and ref_s in hay_s:
        si = hay_s.index(ref_s)
        ei = si + len(ref_s) - 1
        w0 = char_word_idx[si]
        w1 = char_word_idx[ei]
        return words[w0 : w1 + 1]
    # Minimal character window where ref is a subsequence (ordered) of window chars.
    n_ch, m_ch = len(chars_flat), len(ref_chars)
    if m_ch > n_ch:
        return words

    def _chars_subseq(needle: List[str], haystack: List[str]) -> bool:
        if not needle:
            return True
        j = 0
        for c in haystack:
            if j < len(needle) and c == needle[j]:
                j += 1
        return j == len(needle)

    for width in range(m_ch, n_ch + 1):
        for left in range(0, n_ch - width + 1):
            right = left + width
            if _chars_subseq(ref_chars, chars_flat[left:right]):
                w0 = char_word_idx[left]
                w1 = char_word_idx[right - 1]
                return words[w0 : w1 + 1]
    return words


def _subtitle_chars_no_whitespace(s: str) -> str:
    return "".join(c for c in (s or "") if not c.isspace())


def _subtitle_chars_for_core_compare(s: str) -> str:
    """Strip spaces and subtitle punctuation so ASR text matches segment.text for equality checks."""
    return "".join(
        c for c in (s or "") if not c.isspace() and c not in _SUBTITLE_ALIGN_SKIP_CHARS
    )


def _partition_int_proportional(n: int, weights: List[int]) -> List[int]:
    """Split integer *n* across len(weights) buckets proportional to *weights* (Hamilton)."""
    m = len(weights)
    if m == 0:
        return []
    if n <= 0:
        return [0] * m
    total = sum(weights)
    if total <= 0:
        base, rem = divmod(n, m)
        return [base + (1 if i < rem else 0) for i in range(m)]
    exact = [n * w / total for w in weights]
    out = [int(x) for x in exact]
    rem = n - sum(out)
    order = sorted(range(m), key=lambda i: exact[i] - out[i], reverse=True)
    for k in range(rem):
        out[order[k % m]] += 1
    return out


def _distribute_ref_to_words_punctuation_aligned(
    words: List[Dict],
    ref: str,
) -> Optional[List[Dict]]:
    """
    When reference matches ASR content character-for-character but adds Chinese/ASCII
    clause punctuation, assign each character (including marks) to Whisper tokens so
    karaoke/static lines show readable 。，等 without breaking timings.
    """
    if not ref or not words:
        return None
    asr_parts = [_subtitle_chars_no_whitespace(w.get("text") or "") for w in words]
    out_txt = ["" for _ in words]
    wi, ci = 0, 0

    for ch in ref:
        if ch.isspace():
            continue
        if ch in _SUBTITLE_ALIGN_SKIP_CHARS:
            if wi < len(words) and ci > 0:
                out_txt[wi] += ch
            elif wi > 0:
                out_txt[wi - 1] += ch
            else:
                out_txt[0] += ch
            continue
        while wi < len(asr_parts) and ci >= len(asr_parts[wi]):
            wi += 1
            ci = 0
        if wi >= len(asr_parts):
            return None
        exp = asr_parts[wi][ci]
        if ch != exp:
            return None
        out_txt[wi] += ch
        ci += 1

    while wi < len(asr_parts):
        if ci < len(asr_parts[wi]):
            return None
        wi += 1
        ci = 0

    return [{**dict(w), "text": out_txt[i] or (w.get("text") or "")} for i, w in enumerate(words)]


def apply_segment_reference_text_to_words(
    words: List[Dict],
    reference_text: Optional[str],
) -> List[Dict]:
    """
    Replace per-token subtitle strings with slices of *reference_text* (AI segment text,
    including glossary/hotword fixes) while keeping Whisper timings.

    Burned subtitles otherwise use only ASR ``word`` strings — including for pure
    Chinese, English, and mixed industry copy — so corrected ``segment['text']``
    would not appear on screen without this step.
    """
    if not words:
        return words
    ref = _subtitle_chars_no_whitespace((reference_text or "").strip())
    if not ref:
        return words
    asr_flat = _subtitle_chars_no_whitespace(
        "".join(w.get("text") or "" for w in words)
    )
    if ref == asr_flat:
        return words

    ref_core = _subtitle_chars_for_core_compare(ref)
    asr_core = _subtitle_chars_for_core_compare(asr_flat)
    if ref_core == asr_core and ref_core:
        merged = _distribute_ref_to_words_punctuation_aligned(words, ref)
        if merged is not None:
            return merged

    weights = [
        max(1, len(_subtitle_chars_no_whitespace(w.get("text") or "")))
        for w in words
    ]
    counts = _partition_int_proportional(len(ref), weights)
    out: List[Dict] = []
    pos = 0
    for w, cnt in zip(words, counts):
        nw = dict(w)
        if cnt > 0:
            nw["text"] = ref[pos : pos + cnt]
            pos += cnt
        out.append(nw)
    if pos < len(ref) and out:
        last = dict(out[-1])
        last["text"] = (last.get("text") or "") + ref[pos:]
        out[-1] = last
    return out


# Backward-compatible name (older call sites / docs).
apply_cjk_subtitle_reference_text_to_words = apply_segment_reference_text_to_words


def _retime_subtitle_words_by_char_weights(words: List[Dict]) -> List[Dict]:
    """
    After replacing token text (hotwords, punctuation), Whisper's per-token
    durations may no longer match how long each on-screen string should read.
    Redistribute [first.start, last.end] across tokens in proportion to character
    count so karaoke/static highlights track speech without cumulative lag.
    """
    if not words:
        return words
    if len(words) == 1:
        return words
    t0 = float(words[0]["start"])
    t1 = float(words[-1]["end"])
    span = t1 - t0
    if span <= 1e-6:
        return words
    weights = [
        max(1e-6, float(len(_subtitle_chars_no_whitespace(w.get("text") or ""))))
        for w in words
    ]
    tw = sum(weights)
    if tw <= 0:
        return words
    out: List[Dict] = []
    acc = 0.0
    for w, wt in zip(words, weights):
        s = t0 + span * (acc / tw)
        e = t0 + span * ((acc + wt) / tw)
        out.append({**dict(w), "start": s, "end": e})
        acc += wt
    return out


def trim_subtitle_words_to_segment_text(
    words: List[Dict],
    reference_text: Optional[str],
) -> List[Dict]:
    """
    Narrow time-window ASR words to the contiguous span that best matches the AI
    segment's verbatim *reference_text* (same wording as ``segment['text']``).

    Cuts off marginal tokens at clip edges that still fall inside the trim window
    but are outside the model-selected narrative span.
    """
    if not words or not (reference_text or "").strip():
        return words
    ref = (reference_text or "").strip()
    try:
        if _words_are_primarily_cjk(words):
            return _trim_cjk_words_to_reference_text(words, ref)
        return _trim_latin_words_to_reference_text(words, ref)
    except Exception as e:
        logger.warning("Subtitle trim to segment text failed, using full window: %s", e)
        return words


_TOKEN_EDGE_PUNCT_RE = re.compile(
    r'^[\s\"\'"“”‘’\[\({]+|[\s\"\'"“”‘’.,;:!?…，。！？）\]}\-—]+$', re.UNICODE
)


def _strip_token_edges_for_key(t: str) -> str:
    """Remove outer punctuation/spaces so ASR token variants map to one cache key."""
    s = t.strip()
    if not s:
        return ""
    s = _TOKEN_EDGE_PUNCT_RE.sub("", s)
    return s.strip().lower()


def normalize_subtitle_phrase_key(tokens: List[str]) -> str:
    """Stable cache key for a subtitle phrase built from word tokens."""
    parts: List[str] = []
    for raw in tokens:
        t = _strip_token_edges_for_key(raw)
        t = re.sub(r"\s+", " ", t)
        if t:
            parts.append(t)
    return " ".join(parts)


def normalize_subtitle_phrase_key_legacy(tokens: List[str]) -> str:
    """Previous key scheme (still tried at lookup for older transcript caches)."""
    parts: List[str] = []
    for raw in tokens:
        t = raw.strip().lower()
        t = re.sub(r"\s+", " ", t)
        if t:
            parts.append(t)
    return " ".join(parts)


def _word_ends_strong_clause_boundary(text: str) -> bool:
    t = (text or "").rstrip()
    if not t:
        return False
    return t[-1] in ".?!" or t[-1] in "。！？；…"


def _word_ends_soft_pause(text: str) -> bool:
    t = (text or "").rstrip()
    if not t:
        return False
    return t[-1] in ",;:" or t[-1] in "，、："


def _group_words_by_pause_boundaries(
    words: List[Dict],
    *,
    default_chunk: int,
    max_window: int,
) -> List[List[Dict]]:
    """
    Group ASR tokens into subtitle cards, preferring 句读 / clause boundaries.

    *default_chunk* is used when no strong/soft boundary is found in the window
    (English: ~3; CJK monolingual: larger, e.g. 8).
    """
    if not words:
        return []
    groups: List[List[Dict]] = []
    i = 0
    n = len(words)
    while i < n:
        remain = n - i
        if remain == 1:
            groups.append(words[i : i + 1])
            break
        hi = min(remain, max_window)
        best = min(default_chunk, hi)
        found = False
        for cand in range(2, hi + 1):
            if _word_ends_strong_clause_boundary(words[i + cand - 1]["text"]):
                best = cand
                found = True
                break
        if not found:
            for cand in range(3, hi + 1):
                if _word_ends_soft_pause(words[i + cand - 1]["text"]):
                    best = cand
                    found = True
                    break
        if not found:
            best = min(default_chunk, hi)
        groups.append(words[i : i + best])
        i += best
    return groups


def group_words_for_bilingual_captions(words: List[Dict]) -> List[List[Dict]]:
    """
    Split ASR words into subtitle cards for bilingual (and monolingual) rendering.

    Prefers ~3 words per card but may use 2–5 to end on a clause boundary, so
    each English card stays a coherent phrase for translation and matches render.
    """
    return _group_words_by_pause_boundaries(words, default_chunk=3, max_window=5)


def _is_cjk_char(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF


def _words_are_primarily_cjk(words: List[Dict]) -> bool:
    """Heuristic: clip words are mostly Chinese (pure-Chinese subtitle pipeline)."""
    raw = "".join((w.get("text") or "") for w in words)
    stripped = raw.replace(" ", "").replace("\n", "")
    if not stripped:
        return False
    cjk = sum(1 for ch in stripped if _is_cjk_char(ch))
    latin = sum(
        1 for ch in stripped if ("A" <= ch <= "Z") or ("a" <= ch <= "z")
    )
    if latin == 0:
        return cjk > 0
    return cjk > latin


def _format_subtitle_word_group(words: List[Dict], cjk_primary: bool) -> str:
    """Join ASR tokens for display: no spaces for CJK lines; spaced for Latin."""
    parts = [(w.get("text") or "").strip() for w in words]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if not cjk_primary:
        return " ".join(parts)
    return "".join(parts)


def _measure_subtitle_line_width_px(
    text: str,
    font_path: str,
    font_size: int,
    stroke_width: int,
) -> int:
    """Single-line width for subtitle layout (matches label-style measurement)."""
    if not (text or "").strip():
        return 0
    sw = int(stroke_width)
    try:
        kw: Dict[str, Any] = dict(
            text=text,
            font=font_path,
            font_size=font_size,
            color="#FFFFFF",
            method="label",
        )
        if sw > 0:
            kw["stroke_color"] = "#000000"
            kw["stroke_width"] = sw
        clip = TextClip(**kw)
        w = int(clip.size[0]) if clip.size else 0
        clip.close()
        return w
    except Exception:
        est = 0.0
        for ch in text:
            o = ord(ch)
            if 0x3400 <= o <= 0x9FFF:
                est += font_size * 0.95
            elif ch.isascii() and ch.isalnum():
                est += font_size * 0.52
            else:
                est += font_size * 0.45
        return int(est + sw * 2)


def _split_word_group_by_max_line_width(
    group: List[Dict],
    max_line_width_px: int,
    font_path: str,
    font_size: int,
    stroke_width: int,
) -> List[List[Dict]]:
    """Split one coarse group so each line fits *max_line_width_px* (CJK, no spaces)."""
    if not group:
        return []

    def join_g(g: List[Dict]) -> str:
        return _format_subtitle_word_group(g, True)

    if (
        _measure_subtitle_line_width_px(
            join_g(group), font_path, font_size, stroke_width
        )
        <= max_line_width_px
    ):
        return [group]

    out: List[List[Dict]] = []
    buf: List[Dict] = []
    for w in group:
        trial = buf + [w]
        line = join_g(trial)
        tw = _measure_subtitle_line_width_px(line, font_path, font_size, stroke_width)
        if tw <= max_line_width_px:
            buf = trial
            continue
        if buf:
            out.append(buf)
            buf = [w]
            one = join_g(buf)
            ow = _measure_subtitle_line_width_px(
                one, font_path, font_size, stroke_width
            )
            if ow > max_line_width_px:
                out.append(buf)
                buf = []
        else:
            out.append([w])
    if buf:
        out.append(buf)
    return out


def group_words_for_cjk_caption_cards(
    words: List[Dict],
    max_line_width_px: int,
    font_path: str,
    font_size: int,
    stroke_width: int,
) -> List[List[Dict]]:
    """
    Group ASR words into subtitle cards for primarily-Chinese clips: prefer
    punctuation / pause boundaries, then enforce max line width so caption
    does not wrap awkwardly.
    """
    if not words:
        return []
    coarse = _group_words_by_pause_boundaries(
        words, default_chunk=8, max_window=24
    )
    flat: List[List[Dict]] = []
    for g in coarse:
        flat.extend(
            _split_word_group_by_max_line_width(
                g, max_line_width_px, font_path, font_size, stroke_width
            )
        )
    return flat


def lookup_phrase_translation(
    phrase_translations: Dict[str, str],
    tokens: List[str],
    en_line: str,
) -> str:
    """Resolve Chinese line with tolerant keying (punctuation / legacy cache)."""
    if not phrase_translations:
        return ""
    key_fns = (normalize_subtitle_phrase_key, normalize_subtitle_phrase_key_legacy)
    for key_fn in key_fns:
        k = key_fn(tokens)
        z = (phrase_translations.get(k) or "").strip()
        if z:
            return z
    etoks = [x for x in re.split(r"\s+", (en_line or "").strip()) if x]
    if etoks:
        for key_fn in key_fns:
            k = key_fn(etoks)
            z = (phrase_translations.get(k) or "").strip()
            if z:
                return z
    return ""


def collect_bilingual_phrase_pairs(
    transcript_data: Dict[str, Any],
    segments: List[Dict[str, Any]],
) -> List[Tuple[str, str]]:
    """
    Unique (normalized_key, display_en) pairs for subtitle cards inside each
    clip segment's time range. Grouping matches ``create_bilingual_static_subtitles``.
    """
    seen: set[str] = set()
    out: List[Tuple[str, str]] = []
    for seg in segments:
        st = parse_timestamp_to_seconds(seg["start_time"])
        et = parse_timestamp_to_seconds(seg["end_time"])
        words = get_words_in_range(transcript_data, st, et)
        words = trim_subtitle_words_to_segment_text(
            words, (seg.get("text") or "").strip() or None
        )
        for group in group_words_for_bilingual_captions(words):
            if not group:
                continue
            tokens = [w["text"] for w in group]
            display_en = " ".join(t.strip() for t in tokens).strip()
            if not display_en:
                continue
            key = normalize_subtitle_phrase_key(tokens)
            if key in seen:
                continue
            seen.add(key)
            out.append((key, display_en))
    return out


def should_use_bilingual_subtitles(
    mode: str,
    transcript_data: Optional[Dict[str, Any]],
    add_subtitles: bool,
) -> bool:
    """Whether to render bilingual subtitles for this task."""
    if not add_subtitles:
        return False
    m = (mode or "auto").strip().lower()
    if m in ("off", "false", "0", "no"):
        return False
    if m in ("on", "true", "1", "yes"):
        return bool(transcript_data and transcript_data.get("segments"))
    if not transcript_data:
        return False
    lang = (transcript_data.get("language") or "").lower()
    if not lang.startswith("en"):
        return False
    prob = float(transcript_data.get("language_probability") or 0.0)
    if prob and prob < 0.35:
        return False
    full_text = transcript_data.get("text") or ""
    if any("\u4e00" <= c <= "\u9fff" for c in full_text):
        return False
    return bool(transcript_data.get("segments"))


def _cjk_fallback_font_path(font_path: str) -> bool:
    fp = (font_path or "").lower()
    return "sourcehan" in fp or "notosans" in fp or "noto sans" in fp


def _primary_cjk_stroke_width(font_path: str, base_stroke: int) -> int:
    """Stronger outline when rendering CJK with a regular-weight fallback font."""
    if base_stroke <= 0 or not _cjk_fallback_font_path(font_path):
        return base_stroke
    return min(12, max(base_stroke + 1, int(round(base_stroke * 1.35))))


def _text_contains_cjk(text: str) -> bool:
    """True if *text* includes CJK ideographs (e.g. Chinese subtitles)."""
    for ch in text:
        o = ord(ch)
        if 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF:
            return True
    return False


def _cjk_caption_interline_and_margin(
    font_size: int, base_stroke: int
) -> Tuple[int, Tuple[int, int, int, int]]:
    """Line spacing and padding for CJK caption TextClips (matches bilingual zh line)."""
    interline = max(10, int(round(font_size * 0.26)))
    margin = (
        max(4, int(font_size * 0.12)),
        max(6, int(font_size * 0.16)),
        max(4, int(font_size * 0.12)),
        max(14, int(font_size * 0.36) + base_stroke),
    )
    return interline, margin


def _bilingual_text_clip_from_template(
    *,
    text: str,
    font_path: str,
    font_size: int,
    style_template: Dict[str, Any],
    max_text_width: int,
    stroke_width: int,
    interline: int = 6,
    margin: Optional[Tuple[int, int, int, int]] = None,
) -> Any:
    """
    One subtitle line using caption template colors, outline, optional background,
    and optional drop shadow (same cues as non-bilingual pop/static clips).
    """
    stroke_color = style_template.get("stroke_color", "black")
    sc = stroke_color if stroke_color else None
    use_shadow = bool(style_template.get("shadow"))
    bg = None
    if style_template.get("background") and style_template.get("background_color"):
        bg = style_template["background_color"]

    base_kw: Dict[str, Any] = dict(
        text=text,
        font=font_path,
        font_size=font_size,
        color=style_template["font_color"],
        stroke_color=sc,
        stroke_width=stroke_width,
        method="caption",
        size=(max_text_width, None),
        text_align="center",
        vertical_align="bottom",
        interline=interline,
    )
    if margin is not None:
        base_kw["margin"] = margin
    if bg is not None:
        base_kw["bg_color"] = bg

    main = TextClip(**base_kw)
    if not use_shadow:
        return main

    shadow_kw = {k: v for k, v in base_kw.items() if k != "bg_color"}
    shadow_kw["color"] = "#000000"
    shadow_kw["stroke_width"] = 0
    shadow_kw["stroke_color"] = None
    shadow = TextClip(**shadow_kw)
    dx, dy = 3, 3
    w, h = main.size
    return CompositeVideoClip(
        [shadow.with_position((dx, dy)), main.with_position((0, 0))],
        size=(w + dx, h + dy),
    )


def create_bilingual_static_subtitles(
    relevant_words: List[Dict],
    video_width: int,
    video_height: int,
    style_template: Dict,
    font_family: str,
    main_font_size: int,
    secondary_font_size: int,
    phrase_translations: Dict[str, str],
    clip_timeline_end: Optional[float] = None,
) -> List[Any]:
    """
    Chinese primary (main_font_size), English secondary below (secondary_font_size).
    Uses static grouping (3 words) regardless of karaoke/pop template, but applies
    the selected template's colors, outline, background, shadow, and font family
    (with the same CJK fallback rules as VideoProcessor).
    """
    subtitle_clips: List[Any] = []
    position_y_base = float(style_template.get("position_y", 0.75))
    max_text_width = get_subtitle_max_width(video_width)
    base_stroke = int(style_template.get("stroke_width", 1))
    gap = max(6, int(video_height * 0.012))

    main_scaled = get_scaled_font_size(main_font_size, video_width)
    sub_scaled = get_scaled_font_size(secondary_font_size, video_width)

    groups = list(group_words_for_bilingual_captions(relevant_words))
    tl_end = clip_timeline_end
    if tl_end is None and relevant_words:
        tl_end = float(relevant_words[-1]["end"])
    elif tl_end is None:
        tl_end = 0.0

    eligible: List[List[Dict]] = []
    for word_group in groups:
        if not word_group:
            continue
        tokens = [w["text"] for w in word_group]
        en_line = " ".join(t.strip() for t in tokens).strip()
        if not en_line:
            continue
        eligible.append(word_group)

    card_times = _resolve_static_card_time_ranges(
        eligible,
        timeline_end=tl_end,
    )

    for word_group, (segment_start, segment_end) in zip(eligible, card_times):
        tokens = [w["text"] for w in word_group]
        en_line = " ".join(t.strip() for t in tokens).strip()
        zh_line = lookup_phrase_translation(phrase_translations, tokens, en_line)
        segment_duration = segment_end - segment_start
        if segment_duration < 0.1:
            continue

        try:
            if zh_line:
                zh_processor = VideoProcessor(
                    font_family,
                    main_font_size,
                    style_template["font_color"],
                    text_for_font_detection=zh_line,
                )
                en_processor = VideoProcessor(
                    font_family,
                    secondary_font_size,
                    style_template["font_color"],
                    text_for_font_detection=en_line,
                )
                zh_stroke = _primary_cjk_stroke_width(zh_processor.font_path, base_stroke)

                # CJK caption: extra line spacing + padding so descenders / last line
                # are not clipped by MoviePy/Pillow height (common with vertical_align=bottom).
                zh_interline = max(10, int(round(main_scaled * 0.26)))
                zh_margin = (
                    max(4, int(main_scaled * 0.12)),
                    max(6, int(main_scaled * 0.16)),
                    max(4, int(main_scaled * 0.12)),
                    max(14, int(main_scaled * 0.36) + base_stroke),
                )

                en_clip = _bilingual_text_clip_from_template(
                    text=en_line,
                    font_path=en_processor.font_path,
                    font_size=sub_scaled,
                    style_template=style_template,
                    max_text_width=max_text_width,
                    stroke_width=base_stroke,
                ).with_duration(segment_duration).with_start(segment_start)
                en_h = en_clip.size[1] if en_clip.size else 40
                en_top = get_safe_vertical_position(
                    video_height, en_h, position_y_base
                )
                en_clip = en_clip.with_position(("center", en_top))

                zh_clip = _bilingual_text_clip_from_template(
                    text=zh_line,
                    font_path=zh_processor.font_path,
                    font_size=main_scaled,
                    style_template=style_template,
                    max_text_width=max_text_width,
                    stroke_width=zh_stroke,
                    interline=zh_interline,
                    margin=zh_margin,
                ).with_duration(segment_duration).with_start(segment_start)
                zh_h = zh_clip.size[1] if zh_clip.size else 40
                zh_top_raw = en_top - gap - zh_h
                min_top_padding = max(40, int(video_height * 0.05))
                zh_top = max(min_top_padding, zh_top_raw)
                zh_clip = zh_clip.with_position(("center", zh_top))

                subtitle_clips.append(zh_clip)
                subtitle_clips.append(en_clip)
            else:
                single = create_static_subtitles(
                    word_group,
                    video_width,
                    video_height,
                    {**style_template, "font_size": main_font_size},
                    font_family,
                    clip_timeline_end=tl_end,
                )
                subtitle_clips.extend(single)

        except Exception as e:
            logger.warning("Failed bilingual subtitle for '%s': %s", en_line, e)
            continue

    logger.info("Created %s bilingual subtitle elements", len(subtitle_clips))
    return subtitle_clips


def create_faster_whisper_subtitles(
    video_path: Path,
    clip_start: float,
    clip_end: float,
    video_width: int,
    video_height: int,
    font_family: str = "THEBOLDFONT",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    caption_template: str = "default",
    bilingual_subtitles: bool = False,
    subtitle_segment_text: Optional[str] = None,
) -> List[TextClip]:
    """Create subtitles using faster-whisper's precise word timing with template support."""
    transcript_data = load_cached_transcript_data(video_path)

    if not transcript_data or not transcript_data.get("segments"):
        logger.warning("No cached transcript data available for subtitles")
        return []

    # Get template settings
    template = get_template(caption_template)
    animation_type = template.get("animation", "none")

    effective_font_family = font_family or template["font_family"]
    effective_font_size = int(font_size) if font_size else int(template["font_size"])
    effective_font_color = font_color or template["font_color"]
    effective_template = {
        **template,
        "font_size": effective_font_size,
        "font_color": effective_font_color,
        "font_family": effective_font_family,
    }

    logger.info(
        f"Creating subtitles with template '{caption_template}', animation: {animation_type}"
    )
    logger.info(f"Effective font: {effective_font_family}, size: {effective_font_size}, color: {effective_font_color}")

    # Get words in range, then trim to AI segment wording (drops edge-only ASR tokens).
    relevant_words = get_words_in_range(transcript_data, clip_start, clip_end)
    relevant_words = trim_subtitle_words_to_segment_text(
        relevant_words, subtitle_segment_text
    )

    if subtitle_segment_text and relevant_words and not bilingual_subtitles:
        # Keep Whisper per-token start/end for timing; do not redistribute by character
        # averages (that drifts away from when each phrase actually begins).
        relevant_words = apply_segment_reference_text_to_words(
            relevant_words, subtitle_segment_text
        )

    if not relevant_words:
        logger.warning("No words found in clip timerange")
        return []
    logger.info(f"Found {len(relevant_words)} relevant words for subtitles.")

    clip_span = max(0.0, float(clip_end - clip_start))

    if bilingual_subtitles:
        phrase_map: Dict[str, str] = dict(
            transcript_data.get("phrase_translations") or {}
        )
        # English secondary: two points smaller than the previous (-2) offset.
        secondary_size = max(8, effective_font_size - 4)
        return create_bilingual_static_subtitles(
            relevant_words,
            video_width,
            video_height,
            effective_template,
            effective_font_family,
            effective_font_size,
            secondary_size,
            phrase_map,
            clip_timeline_end=clip_span,
        )

    # Choose subtitle creation method based on animation type
    if animation_type == "karaoke":
        return create_karaoke_subtitles(
            relevant_words,
            video_width,
            video_height,
            effective_template,
            effective_font_family,
            clip_timeline_end=clip_span,
        )
    elif animation_type == "pop":
        return create_pop_subtitles(
            relevant_words,
            video_width,
            video_height,
            effective_template,
            effective_font_family,
            clip_timeline_end=clip_span,
        )
    elif animation_type == "fade":
        return create_fade_subtitles(
            relevant_words,
            video_width,
            video_height,
            effective_template,
            effective_font_family,
            clip_timeline_end=clip_span,
        )
    else:
        # Default static subtitles
        return create_static_subtitles(
            relevant_words,
            video_width,
            video_height,
            effective_template,
            effective_font_family,
            clip_timeline_end=clip_span,
        )

def _resolve_static_card_time_ranges(
    word_groups: List[List[Dict]],
    *,
    timeline_end: float,
    gap_between: float = 0.04,
) -> List[Tuple[float, float]]:
    """
    Align each subtitle card to ASR word timestamps only (no average reading speed).

    - *start* = first token's ``start`` in the card (when this line begins acoustically).
    - *end* = at least last token's ``end``, but if the next card exists, extend to just
      before that card's first token ``start`` so the line stays until the next phrase begins.
    """
    if not word_groups:
        return []
    tl = max(0.0, float(timeline_end))
    n = len(word_groups)
    out: List[Tuple[float, float]] = []
    for i, wg in enumerate(word_groups):
        if not wg:
            continue
        st = float(wg[0]["start"])
        last_end = float(wg[-1]["end"])
        if i + 1 < n and word_groups[i + 1]:
            nst = float(word_groups[i + 1][0]["start"])
            en = min(tl, max(last_end, nst - gap_between))
        else:
            en = min(tl, last_end)
        if en <= st:
            en = min(tl, st + 0.1)
        out.append((st, en))
    return out


def create_static_subtitles(
    relevant_words: List[Dict],
    video_width: int,
    video_height: int,
    template: Dict,
    font_family: str,
    clip_timeline_end: Optional[float] = None,
) -> List[TextClip]:
    """Create standard static subtitles (original behavior)."""
    subtitle_clips = []
    
    # Pass the full text to the processor for font detection
    full_text_for_detection = " ".join(w["text"] for w in relevant_words)
    processor = VideoProcessor(
        font_family, template["font_size"], template["font_color"],
        text_for_font_detection=full_text_for_detection
    )
    logger.info(f"Static subtitles - processor font path: {processor.font_path}")

    calculated_font_size = get_scaled_font_size(template["font_size"], video_width)
    position_y = template.get("position_y", 0.75)
    max_text_width = get_subtitle_max_width(video_width)
    logger.info(f"Static subtitles - calculated_font_size: {calculated_font_size}, position_y: {position_y}, max_text_width: {max_text_width}")

    cjk_primary = _words_are_primarily_cjk(relevant_words)
    stroke_for_layout = int(template.get("stroke_width", 1))
    if cjk_primary:
        word_groups = group_words_for_cjk_caption_cards(
            relevant_words,
            max_text_width,
            processor.font_path,
            calculated_font_size,
            stroke_for_layout,
        )
    else:
        wps = 3
        word_groups = [
            relevant_words[i : i + wps]
            for i in range(0, len(relevant_words), wps)
        ]

    word_groups = [g for g in word_groups if g]

    tl_end = clip_timeline_end
    if tl_end is None and relevant_words:
        tl_end = float(relevant_words[-1]["end"])
    elif tl_end is None:
        tl_end = 0.0

    card_times = _resolve_static_card_time_ranges(
        word_groups,
        timeline_end=tl_end,
    )

    for word_group, (segment_start, segment_end) in zip(word_groups, card_times):
        if not word_group:
            continue

        segment_duration = segment_end - segment_start

        if segment_duration < 0.1:
            continue

        text = _format_subtitle_word_group(word_group, cjk_primary)

        try:
            stroke_color = template.get("stroke_color", "black")
            stroke_width = template.get("stroke_width", 1)

            use_cjk = cjk_primary or _text_contains_cjk(text)
            interline = 6
            margin = None
            sw = stroke_width
            if use_cjk:
                interline, margin = _cjk_caption_interline_and_margin(
                    calculated_font_size, stroke_width
                )
                sw = _primary_cjk_stroke_width(processor.font_path, stroke_width)

            tc_kw: Dict[str, Any] = dict(
                text=text,
                font=processor.font_path,
                font_size=calculated_font_size,
                color=template["font_color"],
                stroke_color=stroke_color if stroke_color else None,
                stroke_width=sw,
                method="caption",
                size=(max_text_width, None),
                text_align="center",
                vertical_align="bottom",
                interline=interline,
            )
            if margin is not None:
                tc_kw["margin"] = margin

            text_clip = (
                TextClip(**tc_kw)
                .with_duration(segment_duration)
                .with_start(segment_start)
            )
            logger.info(f"Static subtitles - TextClip created: text='{text}' size={text_clip.size} start={segment_start} end={segment_end}")

            text_height = text_clip.size[1] if text_clip.size else 40
            vertical_position = get_safe_vertical_position(
                video_height, text_height, position_y
            )
            logger.info(f"Static subtitles - text_height: {text_height}, vertical_position: {vertical_position}")
            text_clip = text_clip.with_position(("center", vertical_position))

            subtitle_clips.append(text_clip)

        except Exception as e:
            logger.warning(f"Failed to create subtitle for '{text}': {e}")
            continue

    logger.info(f"Created {len(subtitle_clips)} static subtitle elements")
    return subtitle_clips

def create_karaoke_subtitles(
    relevant_words: List[Dict],
    video_width: int,
    video_height: int,
    template: Dict,
    font_family: str,
    clip_timeline_end: Optional[float] = None,
) -> List[TextClip]:
    subtitle_clips = []
    
    # Pass the full text to the processor for font detection
    full_text_for_detection = " ".join(w["text"] for w in relevant_words)
    processor = VideoProcessor(
        font_family, template["font_size"], template["font_color"],
        text_for_font_detection=full_text_for_detection
    )

    calculated_font_size = get_scaled_font_size(template["font_size"], video_width)
    position_y = template.get("position_y", 0.75)
    highlight_color = template.get("highlight_color", "#FFD700")
    normal_color = template["font_color"]
    max_text_width = get_subtitle_max_width(video_width)
    horizontal_padding = max(40, int(video_width * 0.06))

    cjk_primary = _words_are_primarily_cjk(relevant_words)
    stroke_for_layout = int(template.get("stroke_width", 1))
    if cjk_primary:
        word_groups = group_words_for_cjk_caption_cards(
            relevant_words,
            max_text_width,
            processor.font_path,
            calculated_font_size,
            stroke_for_layout,
        )
    else:
        wpg = 3
        word_groups = [
            relevant_words[i : i + wpg]
            for i in range(0, len(relevant_words), wpg)
        ]

    def measure_word_group_width(word_group: List[Dict], font_size: int) -> List[int]:
        widths: List[int] = []
        for word in word_group:
            temp_clip = TextClip(
                text=word["text"],
                font=processor.font_path,
                font_size=font_size,
                color=normal_color,
                stroke_color=template.get("stroke_color", "black"),
                stroke_width=template.get("stroke_width", 1),
                method="label",
            )
            widths.append(temp_clip.size[0] if temp_clip.size else 50)
            temp_clip.close()
        return widths

    gap_b = 0.04
    tl_k = float(clip_timeline_end) if clip_timeline_end is not None else None

    for gi, word_group in enumerate(word_groups):
        if not word_group:
            continue

        # For each word in the group, create a highlighted version
        for word_idx, current_word in enumerate(word_group):
            word_start = float(current_word["start"])
            whisper_end = float(current_word["end"])
            if word_idx + 1 < len(word_group):
                boundary_next = float(word_group[word_idx + 1]["start"])
            elif gi + 1 < len(word_groups) and word_groups[gi + 1]:
                boundary_next = float(word_groups[gi + 1][0]["start"])
            else:
                boundary_next = None
            if boundary_next is not None:
                beat_end = max(whisper_end, boundary_next - gap_b)
            else:
                beat_end = whisper_end
            if tl_k is not None:
                beat_end = min(beat_end, tl_k)
            word_duration = max(0.06, beat_end - word_start)

            if word_duration < 0.05:
                continue

            try:
                # Build the text with the current word highlighted
                # We create individual text clips for each word and composite them
                word_clips_for_composite = []
                font_size_for_group = calculated_font_size
                word_widths = measure_word_group_width(word_group, font_size_for_group)
                space_width = 0.0 if cjk_primary else font_size_for_group * 0.28
                total_width = sum(word_widths) + space_width * max(
                    0, len(word_group) - 1
                )

                if total_width > max_text_width and total_width > 0:
                    shrink_ratio = max_text_width / total_width
                    font_size_for_group = max(
                        20, int(font_size_for_group * shrink_ratio)
                    )
                    word_widths = measure_word_group_width(
                        word_group, font_size_for_group
                    )
                    space_width = 0.0 if cjk_primary else font_size_for_group * 0.28
                    total_width = sum(word_widths) + space_width * max(
                        0, len(word_group) - 1
                    )

                # Second pass: create positioned clips
                current_x = max(horizontal_padding, (video_width - total_width) / 2)
                text_height = 40

                for w_idx, word in enumerate(word_group):
                    is_current = w_idx == word_idx
                    color = highlight_color if is_current else normal_color
                    # Scale up current word slightly for pop effect
                    size_multiplier = 1.1 if is_current else 1.0

                    word_clip = (
                        TextClip(
                            text=word["text"],
                            font=processor.font_path,
                            font_size=int(font_size_for_group * size_multiplier),
                            color=color,
                            stroke_color=template.get("stroke_color", "black"),
                            stroke_width=template.get("stroke_width", 1),
                            method="label",
                        )
                        .with_duration(word_duration)
                        .with_start(word_start)
                    )

                    text_height = max(
                        text_height, word_clip.size[1] if word_clip.size else 40
                    )
                    vertical_position = get_safe_vertical_position(
                        video_height, text_height, position_y
                    )

                    word_clip = word_clip.with_position(
                        (int(current_x), vertical_position)
                    )
                    word_clips_for_composite.append(word_clip)

                    current_x += word_widths[w_idx] + space_width

                subtitle_clips.extend(word_clips_for_composite)

            except Exception as e:
                logger.warning(
                    f"Failed to create karaoke subtitle for word '{current_word['text']}': {e}"
                )
                continue

    logger.info(f"Created {len(subtitle_clips)} karaoke subtitle elements")
    return subtitle_clips

def create_pop_subtitles(
    relevant_words: List[Dict],
    video_width: int,
    video_height: int,
    template: Dict,
    font_family: str,
    clip_timeline_end: Optional[float] = None,
) -> List[TextClip]:
    subtitle_clips = []

    # Pass the full text to the processor for font detection
    full_text_for_detection = " ".join(w["text"] for w in relevant_words)
    processor = VideoProcessor(
        font_family, template["font_size"], template["font_color"],
        text_for_font_detection=full_text_for_detection
    )

    calculated_font_size = get_scaled_font_size(template["font_size"], video_width)
    position_y = template.get("position_y", 0.75)
    max_text_width = get_subtitle_max_width(video_width)

    cjk_primary = _words_are_primarily_cjk(relevant_words)
    stroke_for_layout = int(template.get("stroke_width", 2))
    if cjk_primary:
        word_groups = group_words_for_cjk_caption_cards(
            relevant_words,
            max_text_width,
            processor.font_path,
            calculated_font_size,
            stroke_for_layout,
        )
    else:
        wpg = 3
        word_groups = [
            relevant_words[i : i + wpg]
            for i in range(0, len(relevant_words), wpg)
        ]

    tl_end = clip_timeline_end
    if tl_end is None and relevant_words:
        tl_end = float(relevant_words[-1]["end"])
    elif tl_end is None:
        tl_end = 0.0
    wg_nonempty = [g for g in word_groups if g]
    pop_times = _resolve_static_card_time_ranges(
        wg_nonempty,
        timeline_end=tl_end,
    )

    for word_group, (group_start, group_end) in zip(wg_nonempty, pop_times):
        if not word_group:
            continue

        # Show the full group text
        group_text = _format_subtitle_word_group(word_group, cjk_primary)
        group_duration = group_end - group_start

        if group_duration < 0.1:
            continue

        try:
            stroke_color = template.get("stroke_color", "black")
            stroke_width = template.get("stroke_width", 2)

            use_cjk = cjk_primary or _text_contains_cjk(group_text)
            interline = 6
            margin = None
            sw = stroke_width
            if use_cjk:
                interline, margin = _cjk_caption_interline_and_margin(
                    calculated_font_size, stroke_width
                )
                sw = _primary_cjk_stroke_width(processor.font_path, stroke_width)

            logger.debug(
                f"Pop subtitles - Attempting TextClip creation: text='{group_text}', font='{processor.font_path}', size={calculated_font_size}, color='{template['font_color']}', stroke_color='{stroke_color}', stroke_width={sw}"
            )

            tc_kw: Dict[str, Any] = dict(
                text=group_text,
                font=processor.font_path,
                font_size=calculated_font_size,
                color=template["font_color"],
                stroke_color=stroke_color if stroke_color else None,
                stroke_width=sw,
                method="caption",
                size=(max_text_width, None),
                text_align="center",
                vertical_align="bottom" if use_cjk else "center",
                interline=interline,
            )
            if margin is not None:
                tc_kw["margin"] = margin

            text_clip = (
                TextClip(**tc_kw)
                .with_duration(group_duration)
                .with_start(group_start)
            )
            logger.debug(f"Pop subtitles - TextClip created: size={text_clip.size}")

            text_height = text_clip.size[1] if text_clip.size else 40
            vertical_position = get_safe_vertical_position(
                video_height, text_height, position_y
            )
            logger.debug(f"Pop subtitles - text_height: {text_height}, vertical_position: {vertical_position}")
            text_clip = text_clip.with_position(("center", vertical_position))

            subtitle_clips.append(text_clip)

        except Exception as e:
            logger.error(f"Failed to create pop subtitle for text '{group_text}': {e}", exc_info=True)
            continue

    logger.info(f"Created {len(subtitle_clips)} pop subtitle elements")
    return subtitle_clips

def create_fade_subtitles(
    relevant_words: List[Dict],
    video_width: int,
    video_height: int,
    template: Dict,
    font_family: str,
    clip_timeline_end: Optional[float] = None,
) -> List[TextClip]:
    """Create fade-style subtitles with smooth transitions."""
    subtitle_clips = []

    # Pass the full text to the processor for font detection
    full_text_for_detection = " ".join(w["text"] for w in relevant_words)
    processor = VideoProcessor(
        font_family, template["font_size"], template["font_color"],
        text_for_font_detection=full_text_for_detection
    )

    calculated_font_size = get_scaled_font_size(template["font_size"], video_width)
    position_y = template.get("position_y", 0.75)
    has_background = template.get("background", False)
    background_color = template.get("background_color", "#00000080")
    max_text_width = get_subtitle_max_width(video_width)

    cjk_primary = _words_are_primarily_cjk(relevant_words)
    stroke_for_layout = int(template.get("stroke_width", 0))
    if cjk_primary:
        word_groups = group_words_for_cjk_caption_cards(
            relevant_words,
            max_text_width,
            processor.font_path,
            calculated_font_size,
            stroke_for_layout,
        )
    else:
        wpg = 4
        word_groups = [
            relevant_words[i : i + wpg]
            for i in range(0, len(relevant_words), wpg)
        ]

    tl_fade = clip_timeline_end
    if tl_fade is None and relevant_words:
        tl_fade = float(relevant_words[-1]["end"])
    elif tl_fade is None:
        tl_fade = 0.0
    wg_fade = [g for g in word_groups if g]
    fade_times = _resolve_static_card_time_ranges(
        wg_fade,
        timeline_end=tl_fade,
    )

    for word_group, (group_start, group_end) in zip(wg_fade, fade_times):
        if not word_group:
            continue

        group_text = _format_subtitle_word_group(word_group, cjk_primary)
        group_duration = group_end - group_start

        if group_duration < 0.1:
            continue

        try:
            stroke_width = int(template.get("stroke_width", 0))
            use_cjk = cjk_primary or _text_contains_cjk(group_text)
            interline = 6
            margin = None
            sw = stroke_width
            if use_cjk:
                interline, margin = _cjk_caption_interline_and_margin(
                    calculated_font_size, stroke_width
                )
                sw = _primary_cjk_stroke_width(processor.font_path, stroke_width)

            tc_kw: Dict[str, Any] = dict(
                text=group_text,
                font=processor.font_path,
                font_size=calculated_font_size,
                color=template["font_color"],
                stroke_color=template.get("stroke_color")
                if template.get("stroke_color")
                else None,
                stroke_width=sw,
                method="caption",
                size=(max_text_width, None),
                text_align="center",
                interline=interline,
            )
            if use_cjk:
                tc_kw["vertical_align"] = "bottom"
                tc_kw["margin"] = margin

            text_clip = TextClip(**tc_kw)

            text_height = text_clip.size[1] if text_clip.size else 40
            text_width = text_clip.size[0] if text_clip.size else 200
            vertical_position = get_safe_vertical_position(
                video_height, text_height, position_y
            )

            # Add background if specified
            if has_background and background_color:
                padding = 10
                # Parse background color (handle alpha)
                bg_color_hex = (
                    background_color[:7]
                    if len(background_color) > 7
                    else background_color
                )

                bg_clip = (
                    ColorClip(
                        size=(text_width + padding * 2, text_height + padding),
                        color=tuple(
                            int(bg_color_hex[i : i + 2], 16) for i in (1, 3, 5)
                        ),
                    )
                    .with_duration(group_duration)
                    .with_start(group_start)
                )

                bg_clip = bg_clip.with_position(
                    ("center", vertical_position - padding // 2)
                )

                # Apply fade to background
                fade_duration = min(0.2, group_duration / 4)
                bg_clip = (
                    bg_clip.with_effects(
                        [CrossFadeIn(fade_duration), CrossFadeOut(fade_duration)]
                    )
                    if group_duration > 0.5
                    else bg_clip
                )

                subtitle_clips.append(bg_clip)

            # Apply timing and position to text
            text_clip = text_clip.with_duration(group_duration).with_start(group_start)
            text_clip = text_clip.with_position(("center", vertical_position))

            subtitle_clips.append(text_clip)

        except Exception as e:
            logger.warning(f"Failed to create fade subtitle: {e}")
            continue

    logger.info(f"Created {len(subtitle_clips)} fade subtitle elements")
    return subtitle_clips


def normalize_golden_quote_for_burn(
    golden_quote_zh: Optional[str],
    title_zh: Optional[str],
    *,
    max_single_line_chars: int = 26,
    max_line_chars_when_wrapped: int = 22,
) -> str:
    """
    Prefer a single line for on-video golden quote; wrap to a second line only when too long.
    Falls back to title_zh when golden quote is empty.
    """
    raw = (golden_quote_zh or "").strip()
    if not raw:
        raw = (title_zh or "").strip()
    if not raw:
        return ""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Prefer one line: join model lines with spaces (do not keep line breaks unless we overflow)
    merged = " ".join(
        " ".join(ln.split()) for ln in raw.split("\n") if ln.strip()
    ).strip()
    merged = " ".join(merged.split())
    if len(merged) <= max_single_line_chars:
        return merged
    # Second line only when content exceeds one line capacity
    line1 = merged[:max_single_line_chars]
    rest = merged[max_single_line_chars : max_single_line_chars + max_line_chars_when_wrapped].strip()
    if not rest:
        return line1
    return f"{line1}\n{rest}"


def create_zh_golden_quote_overlay_clips(
    video_width: int,
    video_height: int,
    quote_text: str,
    duration: float,
    *,
    _depth: int = 0,
) -> List[Any]:
    """
    Persistent in-video title: large Simplified Chinese golden quote fixed in the **top** safe band
    (documentary-style lower-third of the upper area), full clip duration, with a dark backing bar.
    Composited *before* word subtitles so bottom captions stay readable on top.
    """
    quote_text = (quote_text or "").strip()
    if not quote_text or duration <= 0.05:
        return []
    max_w = get_subtitle_max_width(video_width)
    # Top "title strip": avoid covering face center and bottom subtitles (~72%+)
    y_top = int(video_height * 0.045)
    two_lines = "\n" in quote_text
    # Generous top band so long one-line titles still fit on small vertical outputs
    title_strip_bottom = int(video_height * (0.40 if two_lines else 0.34))

    processor_base = VideoProcessor(
        "SourceHanSansSC-Regular.otf",
        48,
        "#FFFFFF",
        text_for_font_detection=quote_text,
    )
    if not processor_base.font_path:
        logger.warning("Golden quote overlay: no font path resolved, skipping")
        return []

    text_clip = None
    bar_clip = None
    fs = 0
    for try_fs in range(
        max(36, min(56, int(video_width * 0.068))),
        18,
        -2,
    ):
        fs = try_fs
        sw = max(3, fs // 14)
        interline, margin = _cjk_caption_interline_and_margin(fs, sw)
        try:
            tc_kw: Dict[str, Any] = dict(
                text=quote_text,
                font=processor_base.font_path,
                font_size=fs,
                color="#FFFEF8",
                stroke_color="black",
                stroke_width=sw,
                method="caption",
                size=(max_w, None),
                text_align="center",
                interline=interline,
                margin=margin,
                vertical_align="top",
            )
            candidate = TextClip(**tc_kw)
        except Exception as e:
            logger.warning("Golden quote TextClip failed at fs=%s: %s", fs, e)
            continue

        th = candidate.size[1] if candidate.size else fs * 3
        tw = candidate.size[0] if candidate.size else max_w
        pad = max(10, fs // 3)
        if y_top + th + pad > title_strip_bottom:
            try:
                candidate.close()
            except Exception:
                pass
            continue

        text_clip = (
            candidate.with_duration(duration)
            .with_start(0)
            .with_position(("center", y_top))
        )
        bar_w = min(video_width - 12, tw + pad * 2)
        bar_h = th + pad
        bar_x = (video_width - bar_w) // 2
        bar_y = max(0, y_top - pad // 2)
        try:
            bar_clip = (
                ColorClip(size=(bar_w, bar_h), color=(18, 18, 22))
                .with_duration(duration)
                .with_start(0)
                .with_position((bar_x, bar_y))
            )
        except Exception:
            bar_clip = None
        break

    if text_clip is None:
        if _depth == 0:
            first = quote_text.split("\n")[0].strip()
            short = (first[:20].rstrip() + "…") if len(first) > 20 else first[:16]
            if short and short != quote_text and len(short) >= 2:
                return create_zh_golden_quote_overlay_clips(
                    video_width,
                    video_height,
                    short,
                    duration,
                    _depth=1,
                )
        logger.warning("Golden quote overlay: could not fit text in top title strip")
        return []

    layers: List[Any] = []
    if bar_clip is not None:
        layers.append(bar_clip)
    layers.append(text_clip)
    logger.info(
        "Golden quote in-video title: fs=%s line_count=%s y_top=%s strip_bottom=%s duration=%.2fs",
        fs,
        quote_text.count("\n") + 1,
        y_top,
        title_strip_bottom,
        duration,
    )
    return layers


def create_optimized_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    add_subtitles: bool = True,
    font_family: str = "THEBOLDFONT",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    caption_template: str = "default",
    output_format: str = "vertical",
    audio_fade_in: bool = False,
    audio_fade_out: bool = False,
    processing_mode: str = "fast",
    bilingual_subtitles: bool = False,
    subtitle_segment_text: Optional[str] = None,
    clip_title_zh: Optional[str] = None,
    clip_golden_quote_zh: Optional[str] = None,
    burn_clip_title_zh: bool = True,
) -> bool:
    """Create clip with optional subtitles and audio fades."""
    try:
        # Segment end from task/AI (must match subtitle timing & composite duration).
        segment_end_exclusive = end_time
        duration = segment_end_exclusive - start_time
        if duration <= 0:
            logger.error(f"Invalid clip duration: {duration:.1f}s")
            return False

        keep_original = output_format == "original"
        burn_quote_text = normalize_golden_quote_for_burn(
            clip_golden_quote_zh,
            clip_title_zh,
        )
        need_burn_overlay = bool(burn_clip_title_zh and burn_quote_text)
        logger.info(
            f"Creating clip: {start_time:.1f}s - {end_time:.1f}s ({duration:.1f}s) "
            f"subtitles={add_subtitles} template '{caption_template}' format={'original' if keep_original else 'vertical'} "
            f"audio_fade_in={audio_fade_in} audio_fade_out={audio_fade_out} "
            f"burn_golden_quote={need_burn_overlay}"
        )

        # Fast path: no subtitles, no fades, original format = ffmpeg stream copy
        if (
            not add_subtitles
            and keep_original
            and not audio_fade_in
            and not audio_fade_out
            and not need_burn_overlay
        ):
            import subprocess
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss", str(start_time),
                    "-i", str(video_path),
                    "-t", str(duration),
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"ffmpeg stream copy failed: {result.stderr}")
                return False
            logger.info(f"Successfully created clip (stream copy): {output_path}")
            return True

        # Load and process video
        video = VideoFileClip(str(video_path))

        # Add a small safety margin to the end time to avoid cutting off audio.
        # Subtitles must use segment_end_exclusive so word times stay within [0, duration].
        end_time_padded = min(segment_end_exclusive + 0.5, video.duration)
        clip = video.subclipped(start_time, end_time_padded)

        if keep_original:
            # No face detection, no crop, no resize - use trimmed clip as-is
            processed_clip = clip
            target_width = round_to_even(processed_clip.w)
            target_height = round_to_even(processed_clip.h)
            if (target_width, target_height) != (processed_clip.w, processed_clip.h):
                processed_clip = processed_clip.resized((target_width, target_height))
            cropped_clip = None
        else:
            # Vertical 9:16: face-centered crop, preserve native resolution
            x_offset, y_offset, new_width, new_height = detect_optimal_crop_region(
                video, start_time, end_time_padded, target_ratio=9 / 16
            )
            cropped_clip = clip.cropped(
                x1=x_offset, y1=y_offset, x2=x_offset + new_width, y2=y_offset + new_height
            )
            target_width, target_height = round_to_even(new_width), round_to_even(new_height)
            processed_clip = cropped_clip

        # Apply fades on the same clip we encode / attach to CompositeVideoClip.
        # Fading `clip` before `cropped()` can be lost: the cropped clip may not keep that audio chain.
        fade_s = min(2.5, max(0.65, duration * 0.28))
        if processed_clip.audio is not None and (audio_fade_in or audio_fade_out):
            audio_effects = []
            if audio_fade_in:
                audio_effects.append(afx.AudioFadeIn(fade_s))
            if audio_fade_out:
                audio_effects.append(afx.AudioFadeOut(fade_s))
            aud = processed_clip.audio.with_effects(audio_effects)
            processed_clip = processed_clip.with_audio(aud)
            logger.info(
                f"Applied audio fades (fade_s={fade_s:.2f}s fade_in={audio_fade_in} fade_out={audio_fade_out})"
            )

        # Composite order: base → golden quote (upper safe band) → subtitles (top layer)
        final_clips = [processed_clip]

        if need_burn_overlay:
            g_layers = create_zh_golden_quote_overlay_clips(
                target_width,
                target_height,
                burn_quote_text,
                duration,
            )
            if g_layers:
                final_clips.extend(g_layers)
                logger.info(
                    "Added %s golden-quote overlay layer(s)", len(g_layers)
                )

        if add_subtitles:
            logger.info(f"Creating subtitles for clip with template: {caption_template}")
            subtitle_clips = create_faster_whisper_subtitles(
                video_path,
                start_time,
                segment_end_exclusive,
                target_width,
                target_height,
                font_family,
                font_size,
                font_color,
                caption_template,
                bilingual_subtitles=bilingual_subtitles,
                subtitle_segment_text=subtitle_segment_text,
            )
            logger.info(f"Found {len(subtitle_clips)} subtitle clips to add.")
            final_clips.extend(subtitle_clips)
        else:
            logger.info("Skipping subtitle creation because add_subtitles is False.")

        # Compose and encode — MoviePy 2 CompositeVideoClip may not keep the base layer's audio
        if len(final_clips) > 1:
            composite = CompositeVideoClip(
                final_clips,
                size=(target_width, target_height),
            ).with_duration(duration)
            if processed_clip.audio is not None:
                final_clip = composite.with_audio(processed_clip.audio)
            else:
                final_clip = composite
        else:
            final_clip = processed_clip
        source_fps = clip.fps if clip.fps and clip.fps > 0 else 30

        processor = VideoProcessor(font_family, font_size, font_color)
        encoding_settings = processor.get_optimal_encoding_settings("high")

        final_clip.write_videofile(
            str(output_path),
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            logger=None,
            fps=source_fps,
            **encoding_settings,
        )

        # Cleanup
        if final_clip is not processed_clip:
            final_clip.close()
        if processed_clip is not cropped_clip:
            processed_clip.close()
        if cropped_clip is not None:
            cropped_clip.close()
        clip.close()
        video.close()

        logger.info(f"Successfully created clip: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to create clip: {e}")
        return False

def create_clips_from_segments(
    video_path: Path,
    segments: List[Dict[str, Any]],
    output_dir: Path,
    font_family: str = "THEBOLDFONT",
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
    """Create optimized video clips from segments with template support."""
    logger.info(
        f"Creating {len(segments)} clips subtitles={add_subtitles} template '{caption_template}' "
        f"burn_title_zh={burn_clip_title_zh}"
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    clips_info = []

    for i, segment in enumerate(segments):
        try:
            # Debug log the segment data
            logger.info(
                f"Processing segment {i + 1}: start='{segment.get('start_time')}', end='{segment.get('end_time')}'"
            )

            start_seconds = parse_timestamp_to_seconds(segment["start_time"])
            end_seconds = parse_timestamp_to_seconds(segment["end_time"])

            duration = end_seconds - start_seconds
            logger.info(
                f"Segment {i + 1} duration: {duration:.1f}s (start: {start_seconds}s, end: {end_seconds}s)"
            )

            if duration <= 0:
                logger.warning(
                    f"Skipping clip {i + 1}: invalid duration {duration:.1f}s (start: {start_seconds}s, end: {end_seconds}s)"
                )
                continue

            clip_filename = f"clip_{i + 1}_{segment['start_time'].replace(':', '')}-{segment['end_time'].replace(':', '')}.mp4"
            clip_path = output_dir / clip_filename

            success = create_optimized_clip(
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
                (segment.get("text") or "").strip() or None,
                (segment.get("title_zh") or "").strip() or None,
                (segment.get("golden_quote_zh") or "").strip() or None,
                burn_clip_title_zh,
            )

            if success:
                clip_info = {
                    "clip_id": i + 1,
                    "filename": clip_filename,
                    "path": str(clip_path),
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "duration": duration,
                    "text": segment["text"],
                    "text_translation": segment.get("text_translation")
                    or segment.get("text_zh"),
                    "title_zh": segment.get("title_zh"),
                    "golden_quote_zh": segment.get("golden_quote_zh"),
                    "relevance_score": segment["relevance_score"],
                    "reasoning": segment["reasoning"],
                    # Include virality data if available
                    "virality_score": segment.get("virality_score", 0),
                    "hook_score": segment.get("hook_score", 0),
                    "engagement_score": segment.get("engagement_score", 0),
                    "value_score": segment.get("value_score", 0),
                    "shareability_score": segment.get("shareability_score", 0),
                    "hook_type": segment.get("hook_type"),
                }
                clips_info.append(clip_info)
                logger.info(f"Created clip {i + 1}: {duration:.1f}s")
            else:
                logger.error(f"Failed to create clip {i + 1}")

        except Exception as e:
            logger.error(f"Error processing clip {i + 1}: {e}")

    logger.info(f"Successfully created {len(clips_info)}/{len(segments)} clips")
    return clips_info

def get_available_transitions() -> List[str]:
    """Get list of available transition video files."""
    transitions_dir = Path(__file__).parent.parent / "transitions"
    if not transitions_dir.exists():
        logger.warning("Transitions directory not found")
        return []

    transition_files = []
    for file_path in transitions_dir.glob("*.mp4"):
        transition_files.append(str(file_path))

    logger.info(f"Found {len(transition_files)} transition files")
    return transition_files

def apply_transition_effect(
    clip1_path: Path,
    clip2_path: Path,
    transition_path: Path,
    output_path: Path,
) -> bool:
    """Apply transition effect between two clips using a transition video."""
    clip1 = None
    clip2 = None
    transition = None
    clip1_tail = None
    clip2_intro = None
    clip2_remainder = None
    intro_segment = None
    final_clip = None

    try:
        from moviepy import VideoFileClip, CompositeVideoClip, concatenate_videoclips

        # Load clips
        clip1 = VideoFileClip(str(clip1_path))
        clip2 = VideoFileClip(str(clip2_path))
        transition = VideoFileClip(str(transition_path))

        # Keep the transition window within both clips so the output still matches
        # the current clip's duration and metadata.
        transition_duration = min(1.5, transition.duration, clip1.duration, clip2.duration)
        if transition_duration <= 0:
            logger.warning("Transition duration is zero, skipping transition effect")
            return False

        transition = transition.subclipped(0, transition_duration)

        # Resize transition to match clip dimensions
        clip_size = clip2.size
        transition = transition.resized(clip_size)

        # Build a transition intro from the previous clip tail over the first
        # part of the current clip so the exported file keeps clip2's duration.
        clip1_tail_start = max(0, clip1.duration - transition_duration)
        clip1_tail = clip1.subclipped(clip1_tail_start, clip1.duration).with_effects(
            [FadeOut(transition_duration)]
        )
        clip2_intro = clip2.subclipped(0, transition_duration).with_effects(
            [FadeIn(transition_duration)]
        )

        intro_segment = CompositeVideoClip(
            [clip1_tail, clip2_intro, transition], size=clip_size
        ).with_duration(transition_duration)
        if clip2_intro.audio is not None:
            intro_segment = intro_segment.with_audio(clip2_intro.audio)

        final_segments = [intro_segment]
        if clip2.duration > transition_duration:
            clip2_remainder = clip2.subclipped(transition_duration, clip2.duration)
            final_segments.append(clip2_remainder)

        final_clip = (
            concatenate_videoclips(final_segments, method="compose")
            if len(final_segments) > 1
            else intro_segment
        )

        # Write output
        processor = VideoProcessor()
        encoding_settings = processor.get_optimal_encoding_settings("high")

        final_clip.write_videofile(
            str(output_path),
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            logger=None,
            **encoding_settings,
        )

        logger.info(f"Applied transition effect: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Error applying transition effect: {e}")
        return False
    finally:
        for clip in (
            final_clip,
            intro_segment,
            clip2_remainder,
            clip2_intro,
            clip1_tail,
            transition,
            clip2,
            clip1,
        ):
            if clip is not None:
                try:
                    clip.close()
                except Exception:
                    pass

def create_clips_with_transitions(
    video_path: Path,
    segments: List[Dict[str, Any]],
    output_dir: Path,
    font_family: str = "THEBOLDFONT",
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
    """Create standalone video clips without inter-clip transitions.

    Kept as a backward-compatible wrapper for older call sites.
    """
    logger.info(
        f"Creating {len(segments)} standalone clips subtitles={add_subtitles} template '{caption_template}'"
    )
    logger.info(
        "Inter-clip transitions are disabled for standalone SupoClip exports"
    )
    return create_clips_from_segments(
        video_path,
        segments,
        output_dir,
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


# Backward compatibility functions
def get_video_transcript_with_assemblyai(path: Path) -> str:
    """Backward compatibility wrapper."""
    return get_video_transcript(path)

def create_9_16_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    subtitle_text: str = "",
) -> bool:
    """Backward compatibility wrapper."""
    return create_optimized_clip(
        video_path, start_time, end_time, output_path, add_subtitles=bool(subtitle_text)
    )


# B-Roll compositing functions


def insert_broll_into_clip(
    main_clip_path: Path,
    broll_path: Path,
    insert_time: float,
    broll_duration: float,
    output_path: Path,
    transition_duration: float = 0.3,
) -> bool:
    """
    Insert B-roll footage into a clip at a specified timestamp.

    Args:
        main_clip_path: Path to the main video clip
        broll_path: Path to the B-roll video
        insert_time: When to insert B-roll (seconds from clip start)
        broll_duration: How long to show B-roll (seconds)
        output_path: Where to save the composited clip
        transition_duration: Crossfade duration (seconds)

    Returns:
        True if successful
    """
    try:
        from moviepy import VideoFileClip, CompositeVideoClip, concatenate_videoclips
        from moviepy.video.fx import CrossFadeIn, CrossFadeOut

        # Load clips
        main_clip = VideoFileClip(str(main_clip_path))
        broll_clip = VideoFileClip(str(broll_path))

        # Get main clip dimensions
        target_width, target_height = main_clip.size

        # Resize B-roll to match main clip (9:16 aspect ratio)
        broll_resized = resize_for_916(broll_clip, target_width, target_height)

        # Ensure B-roll doesn't exceed requested duration
        actual_broll_duration = min(broll_duration, broll_resized.duration)
        broll_trimmed = broll_resized.subclipped(0, actual_broll_duration)

        # Ensure insert_time is within clip bounds
        insert_time = max(0, min(insert_time, main_clip.duration - 0.5))

        # Calculate end time for B-roll
        broll_end_time = insert_time + actual_broll_duration

        # Don't let B-roll extend past the main clip
        if broll_end_time > main_clip.duration:
            broll_end_time = main_clip.duration
            actual_broll_duration = broll_end_time - insert_time
            broll_trimmed = broll_resized.subclipped(0, actual_broll_duration)

        # Split main clip into three parts
        part1 = main_clip.subclipped(0, insert_time) if insert_time > 0 else None
        part2_audio = main_clip.subclipped(insert_time, broll_end_time).audio
        part3 = (
            main_clip.subclipped(broll_end_time)
            if broll_end_time < main_clip.duration
            else None
        )

        # Apply crossfade to B-roll
        if transition_duration > 0:
            broll_with_audio = broll_trimmed.with_audio(part2_audio)
            broll_faded = broll_with_audio.with_effects(
                [CrossFadeIn(transition_duration), CrossFadeOut(transition_duration)]
            )
        else:
            broll_faded = broll_trimmed.with_audio(part2_audio)

        # Concatenate parts
        clips_to_concat = []
        if part1:
            clips_to_concat.append(part1)
        clips_to_concat.append(broll_faded)
        if part3:
            clips_to_concat.append(part3)

        if len(clips_to_concat) == 1:
            final_clip = clips_to_concat[0]
        else:
            final_clip = concatenate_videoclips(clips_to_concat, method="compose")

        # Write output
        processor = VideoProcessor()
        encoding_settings = processor.get_optimal_encoding_settings("high")

        final_clip.write_videofile(
            str(output_path),
            temp_audiofile="temp-audio-broll.m4a",
            remove_temp=True,
            logger=None,
            **encoding_settings,
        )

        # Cleanup
        final_clip.close()
        main_clip.close()
        broll_clip.close()
        broll_resized.close()

        logger.info(
            f"Inserted B-roll at {insert_time:.1f}s ({actual_broll_duration:.1f}s duration): {output_path}"
        )
        return True

    except Exception as e:
        logger.error(f"Error inserting B-roll: {e}")
        return False

def resize_for_916(
    clip: VideoFileClip,
    target_width: int,
    target_height: int,
) -> VideoFileClip:
    """
    Resize a video clip to fit 9:16 aspect ratio with center crop.

    Args:
        clip: Input video clip
        target_width: Target width
        target_height: Target height

    Returns:
        Resized video clip
    """
    clip_width, clip_height = clip.size
    target_aspect = target_width / target_height
    clip_aspect = clip_width / clip_height

    if clip_aspect > target_aspect:
        # Clip is wider - scale to height and crop width
        scale_factor = target_height / clip_height
        new_width = int(clip_width * scale_factor)
        new_height = target_height
        resized = clip.resized((new_width, new_height))

        # Center crop
        x_offset = (new_width - target_width) // 2
        cropped = resized.cropped(x1=x_offset, x2=x_offset + target_width)
    else:
        # Clip is taller - scale to width and crop height
        scale_factor = target_width / clip_width
        new_width = target_width
        new_height = int(clip_height * scale_factor)
        resized = clip.resized((new_width, new_height))

        # Center crop (crop from top for portrait videos)
        y_offset = (new_height - target_height) // 4  # Bias towards top
        cropped = resized.cropped(y1=y_offset, y2=y_offset + target_height)

    return cropped

def apply_broll_to_clip(
    clip_path: Path,
    broll_suggestions: List[Dict[str, Any]],
    output_path: Path,
) -> bool:
    """
    Apply multiple B-roll insertions to a clip.

    Args:
        clip_path: Path to the main clip
        broll_suggestions: List of B-roll suggestions with local_path, timestamp, duration
        output_path: Where to save the final clip

    Returns:
        True if successful
    """
    if not broll_suggestions:
        logger.info("No B-roll suggestions to apply")
        return False

    try:
        # Sort suggestions by timestamp (process from end to start to preserve timing)
        sorted_suggestions = sorted(
            broll_suggestions, key=lambda x: x.get("timestamp", 0), reverse=True
        )

        current_clip_path = clip_path
        temp_paths = []

        for i, suggestion in enumerate(sorted_suggestions):
            broll_path = suggestion.get("local_path")
            if not broll_path or not Path(broll_path).exists():
                logger.warning(f"B-roll file not found: {broll_path}")
                continue

            timestamp = suggestion.get("timestamp", 0)
            duration = suggestion.get("duration", 3.0)

            # Create temp output for intermediate clips
            if i < len(sorted_suggestions) - 1:
                temp_output = output_path.parent / f"temp_broll_{i}.mp4"
                temp_paths.append(temp_output)
            else:
                temp_output = output_path

            success = insert_broll_into_clip(
                current_clip_path,
                Path(broll_path),
                timestamp,
                duration,
                temp_output,
            )

            if success:
                current_clip_path = temp_output
            else:
                logger.warning(f"Failed to insert B-roll at {timestamp}s")

        # Cleanup temp files
        for temp_path in temp_paths:
            if temp_path.exists() and temp_path != output_path:
                try:
                    temp_path.unlink()
                except Exception:
                    pass

        return True

    except Exception as e:
        logger.error(f"Error applying B-roll to clip: {e}")
        return False
