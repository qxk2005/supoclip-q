"""
Translate English subtitle phrases to Simplified Chinese for bilingual captions.
"""

from __future__ import annotations

import logging
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
                "You translate on-screen subtitle phrases from English to natural Simplified Chinese. "
                "Keep translations concise and suitable for short social video captions. "
                "Do not add quotes or numbering. Preserve meaning; you may omit filler words if needed for brevity."
            ),
            output_type=PhraseTranslationBatch,
        )
    return _phrase_agent


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
        "Translate each English phrase to Simplified Chinese. "
        f"There are exactly {n} lines in format: index<TAB>phrase.\n\n"
        f"{lines}\n\n"
        "Return structured output with one item per index i (0..n-1) and field zh."
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


async def apply_bilingual_phrase_translations(
    video_path,
    transcript_data: Dict[str, Any],
    segments: List[Dict[str, Any]],
) -> None:
    """
    Fill transcript_data['phrase_translations'] for 3-word subtitle groups used in clips.
    Persists updated JSON next to the video file.
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

    phrases = [en for _, en in to_translate]
    zh_by_en = await translate_phrases_batched(phrases)
    merged = dict(existing)
    for (key, en), zh in zip(
        to_translate, [zh_by_en.get(en, "").strip() for en in phrases]
    ):
        if zh:
            merged[key] = zh
    transcript_data["phrase_translations"] = merged
    cache_transcript_data(Path(video_path), transcript_data)
