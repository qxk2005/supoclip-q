"""
Translate English subtitle phrases to Simplified Chinese for bilingual captions.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .config import Config

logger = logging.getLogger(__name__)
config = Config()


class PhraseItem(BaseModel):
    i: int = Field(ge=0, description="0-based index into the batch phrase list")
    zh: str = Field(description="Simplified Chinese translation for that phrase")


class PhraseTranslationBatch(BaseModel):
    items: List[PhraseItem]


_phrase_agent: Optional[Agent] = None
_clip_body_agent: Optional[Agent] = None


def _missing_llm_key_error() -> Optional[str]:
    model_name = config.llm
    provider = model_name.split(":", 1)[0].strip().lower()
    if provider in {"google", "google-gla"} and not config.google_api_key:
        return "GOOGLE_API_KEY missing"
    if provider == "openai" and not config.openai_api_key:
        return "OPENAI_API_KEY missing"
    if provider == "anthropic" and not config.anthropic_api_key:
        return "ANTHROPIC_API_KEY missing"
    return None


def _get_phrase_agent() -> Agent:
    global _phrase_agent
    if _phrase_agent is None:
        err = _missing_llm_key_error()
        if err:
            raise RuntimeError(err)
        _phrase_agent = Agent(
            model=config.llm,
            system_prompt=(
                "You translate English subtitle lines into Simplified Chinese for short vertical videos. "
                "Requirements: natural spoken Chinese (口语化、地道), not translationese; keep each line "
                "short enough to read at a glance. Preserve facts and tone; you may compress or reorder "
                "slightly inside the line if it reads more natively in Chinese. "
                "Do not add quotes, labels, or numbering. Never return an empty zh for a non-empty English phrase."
            ),
            output_type=PhraseTranslationBatch,
        )
    return _phrase_agent


def _get_clip_body_agent() -> Agent:
    """Agent for full clip transcript paragraphs (not one-line subtitles)."""
    global _clip_body_agent
    if _clip_body_agent is None:
        err = _missing_llm_key_error()
        if err:
            raise RuntimeError(err)
        _clip_body_agent = Agent(
            model=config.llm,
            system_prompt=(
                "You translate English spoken transcript excerpts into Simplified Chinese for video editors. "
                "Each numbered item may be several sentences. Produce a faithful, complete translation in "
                "natural informational or spoken Chinese; do not summarize away facts or numbers. "
                "Do not add quotes, labels, or meta commentary. Never return an empty zh for a non-empty English item."
            ),
            output_type=PhraseTranslationBatch,
        )
    return _clip_body_agent


def clip_segment_text_should_fill_zh_translation(text: str) -> bool:
    """
    Heuristic: English-like clip body that should get a zh-CN translation in the UI.
    Skips when the text already contains CJK characters.
    """
    t = (text or "").strip()
    if len(t) < 12:
        return False
    if re.search(r"[\u3000-\u9fff\u3400-\u4dbf\uf900-\ufaff]", t):
        return False
    letters = sum(1 for c in t if c.isalpha())
    if letters < 12:
        return False
    latin = sum(1 for c in t if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    return latin / letters >= 0.82


async def translate_clip_transcript_batch(texts: List[str]) -> List[str]:
    """
    Translate clip-length English transcript strings to zh-CN, same length as input.
    """
    if not texts:
        return []
    n = len(texts)
    try:
        agent = _get_clip_body_agent()
    except Exception as e:
        logger.warning("Clip body translation agent unavailable: %s", e)
        return [""] * n

    flat = [" ".join(s.split()) for s in texts]
    lines = "\n".join(f"{i}\t{flat[i]}" for i in range(n))
    user_msg = (
        "Translate each English excerpt to Simplified Chinese. "
        f"There are exactly {n} items in format: index<TAB>excerpt.\n\n"
        f"{lines}\n\n"
        "Return structured output with one item per index i (0..n-1) and field zh. "
        "Each zh must be non-empty for a non-blank English excerpt."
    )
    try:
        result = await agent.run(user_msg)
        out = getattr(result, "output", None)
        if not isinstance(out, PhraseTranslationBatch) or not out.items:
            logger.warning("Unexpected clip body translation output type: %s", type(out))
            return [""] * n
        by_i: Dict[int, str] = {}
        for it in out.items:
            if 0 <= it.i < n:
                by_i[it.i] = (it.zh or "").strip()
        return [by_i.get(i, "") for i in range(n)]
    except Exception as e:
        logger.error("Clip body translation batch failed: %s", e, exc_info=True)
        return [""] * n


async def fill_missing_segment_text_translations_zh(
    segments: List[Dict[str, Any]],
) -> None:
    """
    Mutates segments in place: sets text_translation when missing and the body looks English.
    Uses the configured LLM (same as bilingual subtitles).
    """
    if not segments:
        return

    need_idx: List[int] = []
    texts: List[str] = []
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        existing = (seg.get("text_translation") or seg.get("text_zh") or "").strip()
        if existing:
            continue
        raw = (seg.get("text") or "").strip()
        if not clip_segment_text_should_fill_zh_translation(raw):
            continue
        need_idx.append(i)
        texts.append(raw)

    if not texts:
        return

    batch_size = 4
    zh_all: List[str] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        zh_all.extend(await translate_clip_transcript_batch(chunk))

    for idx, zh in zip(need_idx, zh_all):
        if zh.strip():
            segments[idx]["text_translation"] = zh.strip()

    # Retry any that stayed empty (model miss / length)
    still: List[tuple[int, str]] = []
    for idx, zh in zip(need_idx, zh_all):
        if not zh.strip() and clip_segment_text_should_fill_zh_translation(
            (segments[idx].get("text") or "").strip()
        ):
            still.append((idx, (segments[idx].get("text") or "").strip()))
    if still:
        logger.info("Clip transcript zh retry for %s empty slot(s)", len(still))
        chunk = [t for _, t in still]
        zh2 = await translate_clip_transcript_batch(chunk)
        for (idx, _), zh in zip(still, zh2):
            if zh.strip():
                segments[idx]["text_translation"] = zh.strip()


async def translate_phrase_batch(phrases: List[str]) -> List[str]:
    """
    Translate a batch of English phrases to zh-CN, same length as input.
    On total failure returns list of empty strings matching length.
    """
    if not phrases:
        return []
    n = len(phrases)
    try:
        agent = _get_phrase_agent()
    except Exception as e:
        logger.warning("Phrase translation agent unavailable: %s", e)
        return [""] * n

    lines = "\n".join(f"{i}\t{phrases[i]}" for i in range(n))
    user_msg = (
        "Translate each English line to one Simplified Chinese subtitle line. "
        f"There are exactly {n} lines in format: index<TAB>phrase.\n\n"
        f"{lines}\n\n"
        "Return structured output with one item per index i (0..n-1) and field zh. "
        "Every zh must be non-empty for non-blank English."
    )
    try:
        result = await agent.run(user_msg)
        out = getattr(result, "output", None)
        if not isinstance(out, PhraseTranslationBatch) or not out.items:
            logger.warning("Unexpected phrase translation output type: %s", type(out))
            return [""] * n
        by_i: Dict[int, str] = {}
        for it in out.items:
            if 0 <= it.i < n:
                by_i[it.i] = (it.zh or "").strip()
        return [by_i.get(i, "") for i in range(n)]
    except Exception as e:
        logger.error("Phrase translation batch failed: %s", e, exc_info=True)
        return [""] * n


async def translate_phrases_batched(
    phrases: List[str],
    batch_size: int = 18,
) -> Dict[str, str]:
    """
    phrases: list of English display strings (order preserved for batching).
    Returns map phrase_en -> zh (empty string if untranslated).
    """
    out: Dict[str, str] = {}
    if not phrases:
        return out
    bs = max(5, min(30, batch_size))
    for start in range(0, len(phrases), bs):
        chunk = phrases[start : start + bs]
        zh_list = await translate_phrase_batch(chunk)
        for en, zh in zip(chunk, zh_list):
            out[en] = zh
    return out


def _store_phrase_translation(
    merged: Dict[str, str],
    key: str,
    en: str,
    zh: str,
) -> None:
    """Store under normalized key and legacy key when they differ (cache compatibility)."""
    from .video_utils import normalize_subtitle_phrase_key_legacy

    z = (zh or "").strip()
    if not z:
        return
    merged[key] = z
    toks = [x for x in re.split(r"\s+", (en or "").strip()) if x]
    if toks:
        leg = normalize_subtitle_phrase_key_legacy(toks)
        if leg and leg != key:
            merged[leg] = z


async def apply_bilingual_phrase_translations(
    video_path,
    transcript_data: Dict[str, Any],
    segments: List[Dict[str, Any]],
) -> None:
    """
    Fill transcript_data['phrase_translations'] for bilingual subtitle cards (same
    grouping as clip rendering). Persists updated JSON next to the video file.
    """
    from pathlib import Path

    from .video_utils import cache_transcript_data, collect_bilingual_phrase_pairs

    pairs = collect_bilingual_phrase_pairs(transcript_data, segments)
    if not pairs:
        return

    existing: Dict[str, str] = dict(transcript_data.get("phrase_translations") or {})
    to_translate: List[tuple[str, str]] = []
    for key, en in pairs:
        if not (existing.get(key) or "").strip():
            to_translate.append((key, en))
    if not to_translate:
        transcript_data["phrase_translations"] = existing
        return

    merged = dict(existing)

    async def _run_batches(pairs_in: List[tuple[str, str]]) -> None:
        if not pairs_in:
            return
        phrases = [en for _, en in pairs_in]
        zh_by_en = await translate_phrases_batched(phrases)
        for (key, en), zh in zip(
            pairs_in, [zh_by_en.get(en, "").strip() for en in phrases]
        ):
            _store_phrase_translation(merged, key, en, zh)

    await _run_batches(to_translate)

    # Second pass: lines that stayed empty (model miss or parse glitch).
    still_missing = [(key, en) for key, en in to_translate if not (merged.get(key) or "").strip()]
    if still_missing:
        logger.info(
            "Bilingual phrase translation retry for %s empty lines", len(still_missing)
        )
        await _run_batches(still_missing)

    transcript_data["phrase_translations"] = merged
    cache_transcript_data(Path(video_path), transcript_data)
