from src.video_utils import (
    _cjk_caption_interline_and_margin,
    _group_words_by_pause_boundaries,
    _text_contains_cjk,
    group_words_for_bilingual_captions,
    group_words_for_cjk_caption_cards,
    lookup_phrase_translation,
    normalize_subtitle_phrase_key,
    normalize_subtitle_phrase_key_legacy,
    should_use_bilingual_subtitles,
)


def test_normalize_subtitle_phrase_key_strips_outer_punct_and_case():
    assert normalize_subtitle_phrase_key([" Hello,", " WORLD "]) == "hello world"


def test_normalize_legacy_keeps_inner_comma():
    assert (
        normalize_subtitle_phrase_key_legacy([" Hello,", " WORLD "]) == "hello, world"
    )


def test_group_words_prefers_clause_break():
    words = [
        {"text": "Is", "start": 0.0, "end": 0.1},
        {"text": "that", "start": 0.1, "end": 0.2},
        {"text": "right?", "start": 0.2, "end": 0.3},
        {"text": "Next", "start": 0.3, "end": 0.4},
    ]
    g = group_words_for_bilingual_captions(words)
    assert len(g) == 2
    assert [w["text"] for w in g[0]] == ["Is", "that", "right?"]
    assert [w["text"] for w in g[1]] == ["Next"]


def test_lookup_phrase_translation_hits_modern_key():
    td = {"hello world": "你好世界"}
    z = lookup_phrase_translation(td, ["Hello,", "world"], "Hello, world")
    assert z == "你好世界"


def test_lookup_phrase_translation_falls_back_to_legacy_cache_key():
    td = {"hello, world": "你好世界"}
    z = lookup_phrase_translation(td, ["Hello,", "world"], "Hello, world")
    assert z == "你好世界"


def test_should_use_bilingual_auto_english_no_cjk():
    td = {
        "language": "en",
        "language_probability": 0.92,
        "text": "hello world",
        "segments": [{"words": []}],
    }
    assert should_use_bilingual_subtitles("auto", td, True) is True


def test_should_use_bilingual_auto_rejects_non_english():
    td = {
        "language": "zh",
        "language_probability": 0.9,
        "text": "你好",
        "segments": [{"words": []}],
    }
    assert should_use_bilingual_subtitles("auto", td, True) is False


def test_should_use_bilingual_off():
    td = {
        "language": "en",
        "text": "x",
        "segments": [{"words": []}],
    }
    assert should_use_bilingual_subtitles("off", td, True) is False


def test_should_use_bilingual_requires_subtitles():
    td = {"language": "en", "text": "x", "segments": [{"words": []}]}
    assert should_use_bilingual_subtitles("on", td, False) is False


def test_text_contains_cjk_detects_han():
    assert _text_contains_cjk("你好") is True
    assert _text_contains_cjk("hello") is False
    assert _text_contains_cjk("mix 中文") is True


def test_cjk_caption_interline_and_margin_scales_with_font():
    interline, margin = _cjk_caption_interline_and_margin(40, 2)
    assert interline >= 10
    assert margin[3] >= 14 + 2


def test_cjk_pause_boundary_prefers_sentence_end():
    words = [
        {"text": "我们", "start": 0.0, "end": 0.1},
        {"text": "走吧。", "start": 0.1, "end": 0.2},
        {"text": "明天", "start": 0.2, "end": 0.3},
        {"text": "见", "start": 0.3, "end": 0.4},
    ]
    g = _group_words_by_pause_boundaries(words, default_chunk=8, max_window=24)
    assert len(g) == 2
    assert [w["text"] for w in g[0]] == ["我们", "走吧。"]
    assert [w["text"] for w in g[1]] == ["明天", "见"]


def test_group_words_for_cjk_splits_when_line_too_wide():
    words = [{"text": "字", "start": float(i), "end": float(i) + 0.1} for i in range(40)]
    groups = group_words_for_cjk_caption_cards(
        words,
        max_line_width_px=120,
        font_path="Arial",
        font_size=32,
        stroke_width=0,
    )
    assert len(groups) >= 2
    assert sum(len(g) for g in groups) == 40
