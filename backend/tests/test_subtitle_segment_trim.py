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


if __name__ == "__main__":
    unittest.main()
