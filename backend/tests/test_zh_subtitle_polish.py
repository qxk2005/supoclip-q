"""Tests for VideoLingo-style CJK clip subtitle line merge."""

from src.subtitle_translation import (
    calc_zh_display_weight,
    merge_whisper_words_into_zh_weighted_lines,
    strip_obvious_zh_oral_redundancy,
    _zh_line_soft_match_ratio,
    _zh_polish_candidate_acceptable,
)


def test_calc_zh_display_weight_counts_cjk_heavier_than_ascii():
    assert calc_zh_display_weight("ab") < calc_zh_display_weight("中文")


def test_merge_respects_weight_budget_and_pause():
    words = [
        {"text": "这", "start": 0.0, "end": 0.1},
        {"text": "是", "start": 0.1, "end": 0.2},
        {"text": "第", "start": 0.2, "end": 0.3},
        {"text": "一", "start": 0.3, "end": 0.4},
        {"text": "行", "start": 0.4, "end": 0.5},
        # long pause → new line even if weight still low
        {"text": "新", "start": 2.0, "end": 2.1},
        {"text": "句", "start": 2.1, "end": 2.2},
    ]
    lines = merge_whisper_words_into_zh_weighted_lines(
        words, max_weight=50.0, pause_break_s=0.5, min_weight_before_pause_break=1.0
    )
    assert len(lines) == 2
    assert lines[0]["text"] == "这是第一行"
    assert lines[1]["text"] == "新句"
    assert lines[0]["start"] == 0.0
    assert lines[1]["start"] == 2.0


def test_zh_line_soft_match_ratio_ignores_punctuation():
    a = "你好世界"
    b = "你好，世界。"
    assert _zh_line_soft_match_ratio(a, b) >= 0.95


def test_strip_obvious_zh_oral_redundancy_collapses_oral_and_discourse():
    assert strip_obvious_zh_oral_redundancy("啊啊啊你好") == "啊你好"
    assert strip_obvious_zh_oral_redundancy("然后然后我们开始") == "然后我们开始"
    assert strip_obvious_zh_oral_redundancy("对对对没错") == "对没错"


def test_zh_polish_accepts_shorter_line_after_filler_removal():
    base = "嗯其实呢就是说这个事情吧它其实挺重要的"
    cand = "其实这个事情挺重要的。"
    assert _zh_polish_candidate_acceptable(base, cand) is True
