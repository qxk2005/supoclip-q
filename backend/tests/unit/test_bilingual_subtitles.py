from src.video_utils import (
    normalize_subtitle_phrase_key,
    should_use_bilingual_subtitles,
)


def test_normalize_subtitle_phrase_key_collapses_case_and_space():
    assert (
        normalize_subtitle_phrase_key([" Hello,", " WORLD "])
        == "hello, world"
    )


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
