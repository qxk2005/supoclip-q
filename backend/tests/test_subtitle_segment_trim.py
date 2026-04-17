"""Tests for trimming ASR subtitle words to AI segment reference text."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import video_utils


class SubtitleSegmentTrimTests(unittest.TestCase):
    def test_trims_latin_edge_filler_words(self):
        words = [
            {"text": "Um", "start": 0.0, "end": 0.1},
            {"text": "the", "start": 0.1, "end": 0.2},
            {"text": "core", "start": 0.2, "end": 0.3},
            {"text": "idea", "start": 0.3, "end": 0.4},
            {"text": "okay", "start": 0.4, "end": 0.5},
        ]
        ref = "the core idea"
        out = video_utils.trim_subtitle_words_to_segment_text(words, ref)
        self.assertEqual(len(out), 3)
        self.assertEqual([w["text"] for w in out], ["the", "core", "idea"])

    def test_no_reference_returns_unchanged(self):
        words = [{"text": "a", "start": 0.0, "end": 0.1}]
        self.assertEqual(
            video_utils.trim_subtitle_words_to_segment_text(words, None),
            words,
        )

    def test_cjk_substring_trim(self):
        words = [
            {"text": "嗯", "start": 0.0, "end": 0.1},
            {"text": "关键是", "start": 0.1, "end": 0.3},
            {"text": "效率", "start": 0.3, "end": 0.4},
        ]
        ref = "关键是效率"
        out = video_utils.trim_subtitle_words_to_segment_text(words, ref)
        self.assertEqual(len(out), 2)
        self.assertEqual([w["text"] for w in out], ["关键是", "效率"])

    def test_cjk_reference_replaces_asr_tokens_for_display(self):
        """AI/hotword-corrected segment text must override Whisper spellings on screen."""
        words = [
            {"text": "科原", "start": 0.0, "end": 0.15},
            {"text": "网络", "start": 0.15, "end": 0.35},
        ]
        ref = "Kubernetes网络"
        out = video_utils.apply_segment_reference_text_to_words(words, ref)
        joined = "".join(w["text"] for w in out)
        self.assertEqual(joined, ref)
        self.assertEqual(len(out), 2)

    def test_mixed_zh_en_reference_replaces_asr_tokens(self):
        """Mixed CN+EN: same-length glossary fix maps cleanly onto Whisper tokens."""
        words = [
            {"text": "使用", "start": 0.0, "end": 0.12},
            {"text": "docker", "start": 0.12, "end": 0.35},
            {"text": "部署", "start": 0.35, "end": 0.5},
        ]
        ref = "使用 Docker 部署"
        out = video_utils.apply_segment_reference_text_to_words(words, ref)
        self.assertEqual(
            "".join(w["text"] for w in out),
            video_utils._subtitle_chars_no_whitespace(ref),
        )
        self.assertEqual([w["text"] for w in out], ["使用", "Docker", "部署"])

    def test_cjk_punctuation_only_diff_uses_aligned_distribution(self):
        words = [
            {"text": "关键", "start": 0.0, "end": 0.15},
            {"text": "是效率", "start": 0.15, "end": 0.4},
        ]
        ref = "关键，是效率。"
        out = video_utils.apply_segment_reference_text_to_words(words, ref)
        self.assertEqual([w["text"] for w in out], ["关键，", "是效率。"])

    def test_trim_cjk_ignores_punctuation_in_reference(self):
        words = [
            {"text": "嗯", "start": 0.0, "end": 0.1},
            {"text": "关键是", "start": 0.1, "end": 0.3},
            {"text": "效率", "start": 0.3, "end": 0.4},
        ]
        ref = "关键是效率。"
        out = video_utils.trim_subtitle_words_to_segment_text(words, ref)
        self.assertEqual(len(out), 2)
        self.assertEqual([w["text"] for w in out], ["关键是", "效率"])

    def test_retime_spans_first_to_last_by_char_weight(self):
        words = [
            {"text": "ab", "start": 0.0, "end": 0.5},
            {"text": "cdef", "start": 0.5, "end": 0.6},
        ]
        out = video_utils._retime_subtitle_words_by_char_weights(words)
        self.assertAlmostEqual(out[0]["start"], 0.0)
        self.assertAlmostEqual(out[1]["end"], 0.6)
        self.assertAlmostEqual(out[0]["end"], out[1]["start"])

    def test_static_card_times_align_to_next_phrase_start(self):
        """End extends to next card's first token (ASR), not a reading-speed average."""
        g1 = [
            {"text": "hello", "start": 0.0, "end": 0.2},
            {"text": "world", "start": 0.2, "end": 0.35},
        ]
        g2 = [{"text": "next", "start": 1.0, "end": 1.2}]
        times = video_utils._resolve_static_card_time_ranges(
            [g1, g2],
            timeline_end=10.0,
            gap_between=0.04,
        )
        self.assertEqual(times[0][0], 0.0)
        self.assertAlmostEqual(times[0][1], 1.0 - 0.04)
        self.assertEqual(times[1][0], 1.0)
        self.assertAlmostEqual(times[1][1], 1.2)


if __name__ == "__main__":
    unittest.main()
