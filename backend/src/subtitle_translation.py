"""
Translate English subtitle phrases to Simplified Chinese for bilingual captions.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

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


class SubtitleWordRefinePatch(BaseModel):
    word_index: int = Field(ge=0, description="0-based index into the ASR word list")
    replacement: str = Field(
        description="Corrected surface form for that single token only; same language as input"
    )


class SubtitleWordRefineResult(BaseModel):
    patches: List[SubtitleWordRefinePatch] = Field(default_factory=list)


_phrase_agent: Optional[Agent] = None
_clip_body_agent: Optional[Agent] = None
_subtitle_refine_agent: Optional[Agent] = None


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


def _get_subtitle_refine_agent() -> Agent:
    """ASR token polish for clip-level re-whisper (glossary / hotwords, minimal edits)."""
    global _subtitle_refine_agent
    if _subtitle_refine_agent is None:
        err = _missing_llm_key_error()
        if err:
            raise RuntimeError(err)
        _subtitle_refine_agent = Agent(
            model=config.llm,
            system_prompt=(
                "You fix automatic-speech-recognition (ASR) token strings using a DOMAIN GLOSSARY when provided. "
                "Rules: change as little as possible; never merge or split tokens; never reorder tokens; "
                "only fix clear mis-hearings using the glossary or obvious spelling errors. "
                "Return structured output: patches with word_index and replacement for that single token only. "
                "If the ASR is already acceptable, return an empty patches list."
            ),
            output_type=SubtitleWordRefineResult,
        )
    return _subtitle_refine_agent


def clip_segment_text_should_fill_zh_translation(text: str) -> bool:
    """
    Heuristic: English-like clip body that should get a zh-CN translation in the UI.
    Skips when the text already contains CJK characters.

    The previous latin/letters ratio rejected many real transcripts (heavy digits e.g. 5G/2024,
    punctuation, or accented Latin letters), so we only require a minimum count of ASCII letters.
    """
    t = (text or "").strip()
    if len(t) < 8:
        return False
    if re.search(r"[\u3000-\u9fff\u3400-\u4dbf\uf900-\ufaff]", t):
        return False
    latin = sum(1 for c in t if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    return latin >= 8


def _coerce_phrase_batch_from_llm_output(out: Any, n: int) -> Optional[List[str]]:
    """Build per-index zh strings from structured output or raw JSON/text."""
    if isinstance(out, PhraseTranslationBatch) and out.items:
        by_i: Dict[int, str] = {}
        for it in out.items:
            if 0 <= it.i < n:
                by_i[it.i] = (it.zh or "").strip()
        return [by_i.get(i, "") for i in range(n)]

    if not isinstance(out, str) or not out.strip():
        return None

    raw = out.strip()
    for fence in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE):
        chunk = fence.group(1).strip()
        if chunk:
            raw = chunk
            break

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{\s*\"items\"\s*:\s*\[", raw)
        if m is not None:
            try:
                data, _ = json.JSONDecoder().raw_decode(raw, m.start())
            except json.JSONDecodeError:
                return None
        else:
            return None

    items_raw: Any = None
    if isinstance(data, dict):
        items_raw = data.get("items")
    elif isinstance(data, list):
        items_raw = data
    if not isinstance(items_raw, list):
        return None

    by_i: Dict[int, str] = {}
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        idx = item.get("i")
        zh = (item.get("zh") or "").strip()
        if isinstance(idx, bool) or idx is None:
            continue
        try:
            ii = int(idx)
        except (TypeError, ValueError):
            continue
        if 0 <= ii < n:
            by_i[ii] = zh
    if not by_i:
        return None
    return [by_i.get(i, "") for i in range(n)]


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
        coerced = _coerce_phrase_batch_from_llm_output(out, n)
        if coerced is not None:
            if any(z.strip() for z in coerced):
                return coerced
            logger.warning(
                "Clip body translation parsed but all zh empty (n=%s); output_type=%s",
                n,
                type(out).__name__,
            )
            return coerced
        logger.warning(
            "Could not parse clip body translation output (n=%s); output_type=%s preview=%r",
            n,
            type(out).__name__,
            (out if isinstance(out, str) else str(out))[:500],
        )
        return [""] * n
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
        sample = next(
            (
                (seg.get("text") or "")[:160]
                for seg in segments
                if isinstance(seg, dict)
                and not (seg.get("text_translation") or seg.get("text_zh") or "").strip()
                and (seg.get("text") or "").strip()
            ),
            "",
        )
        logger.info(
            "fill_missing_segment_text_translations_zh: no segments qualified for zh "
            "(count=%s). First untranslated text preview: %r",
            len(segments),
            sample,
        )
        return

    batch_size = 4
    zh_all: List[str] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        zh_all.extend(await translate_clip_transcript_batch(chunk))

    if texts and not any(z.strip() for z in zh_all):
        logger.warning(
            "fill_missing_segment_text_translations_zh: LLM returned empty translations for "
            "all %s clip(s); UI will show English only.",
            len(texts),
        )

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


async def refine_whisper_words_with_glossary_async(
    words: List[Dict[str, Any]],
    hotwords: Optional[str],
    segment_hint: Optional[str],
    llm_refine_enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    LLM: token-index patches only so Whisper start/end times stay unchanged.
    """
    if not words:
        return words
    if llm_refine_enabled is False:
        return words
    if llm_refine_enabled is None and not getattr(
        config, "clip_subtitle_llm_refine", True
    ):
        return words
    try:
        agent = _get_subtitle_refine_agent()
    except Exception as e:
        logger.warning("Subtitle refine agent unavailable: %s", e)
        return words

    lines = "\n".join(
        f"{i}\t{(w.get('text') or '').strip()}" for i, w in enumerate(words)
    )
    parts = [
        "ASR words (index TAB token). Output patches only for tokens that need correction.",
        lines,
    ]
    if hotwords and hotwords.strip():
        parts.append(
            "DOMAIN GLOSSARY / hotwords (use these spellings when the audio clearly refers to them):\n"
            + hotwords.strip()[:6000]
        )
    if segment_hint and segment_hint.strip():
        parts.append(
            "Editor segment excerpt (verbatim; disambiguation only, do not replace the whole clip):\n"
            + segment_hint.strip()[:4000]
        )
    try:
        result = await agent.run("\n\n".join(parts))
        out = getattr(result, "output", None)
        if not isinstance(out, SubtitleWordRefineResult) or not out.patches:
            return words
        merged = [dict(w) for w in words]
        for p in out.patches:
            i = int(p.word_index)
            rep = (p.replacement or "").strip()
            if 0 <= i < len(merged) and rep:
                merged[i]["text"] = rep
        return merged
    except Exception as e:
        logger.warning("Subtitle LLM refine failed: %s", e)
        return words


def refine_whisper_words_with_glossary_sync(
    words: List[Dict[str, Any]],
    hotwords: Optional[str],
    segment_hint: Optional[str],
    llm_refine_enabled: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Sync entrypoint for clip rendering (runs in a worker thread)."""
    try:
        return asyncio.run(
            refine_whisper_words_with_glossary_async(
                words, hotwords, segment_hint, llm_refine_enabled=llm_refine_enabled
            )
        )
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            logger.warning("Subtitle refine skipped (nested event loop): %s", e)
            return words
        raise


def build_clip_bilingual_phrase_translations_sync(
    words: List[Dict[str, Any]],
) -> Dict[str, str]:
    """
    Build phrase_translations for one clip from clip-local ASR words (matches on-screen grouping).
    """
    from .video_utils import group_words_for_bilingual_captions, normalize_subtitle_phrase_key

    pairs: List[tuple[str, str]] = []
    seen_keys: set[str] = set()
    for group in group_words_for_bilingual_captions(words):
        if not group:
            continue
        tokens = [w.get("text") or "" for w in group]
        display_en = " ".join(t.strip() for t in tokens if t.strip()).strip()
        if not display_en:
            continue
        key = normalize_subtitle_phrase_key(tokens)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        pairs.append((key, display_en))
    if not pairs:
        return {}

    phrases = [en for _, en in pairs]
    zh_by_en = asyncio.run(translate_phrases_batched(phrases))
    merged: Dict[str, str] = {}
    for (key, en) in pairs:
        zh = (zh_by_en.get(en) or "").strip()
        if zh:
            _store_phrase_translation(merged, key, en, zh)
    return merged


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


# --- VideoLingo-inspired CJK clip subtitles: display-weight line merge + optional LLM polish ---

_CJK_DISPLAY_WEIGHT_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]"
)


def calc_zh_display_weight(text: str) -> float:
    """
    Approximate on-screen footprint for subtitle layout (CJK-heavy clips).
    Inspired by VideoLingo ``calc_len`` / weighted character counts.
    """
    w = 0.0
    for ch in text or "":
        if _CJK_DISPLAY_WEIGHT_RE.match(ch):
            w += 1.25
        elif ch.isascii() and not ch.isspace():
            w += 0.55
        elif ch.isspace():
            w += 0.15
        else:
            w += 1.0
    return w


def _joined_cjk_line_text(words: List[Dict[str, Any]]) -> str:
    parts = [(x.get("text") or "").strip() for x in words]
    return "".join(p for p in parts if p)


def _word_confidence(w: Dict[str, Any]) -> float:
    v = w.get("probability", w.get("confidence"))
    if v is None:
        return 1.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1.0


def merge_whisper_words_into_zh_weighted_lines(
    words: List[Dict[str, Any]],
    *,
    max_weight: float = 42.0,
    pause_break_s: float = 0.42,
    min_weight_before_pause_break: float = 10.0,
) -> List[Dict[str, Any]]:
    """
    Merge adjacent Whisper tokens into fewer subtitle rows using a CJK display-weight budget
    and coarse pause boundaries (VideoLingo-style coarse split before LLM polish).
    """
    cleaned = [w for w in words if (w.get("text") or "").strip()]
    if not cleaned:
        return []

    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []

    for i, w in enumerate(cleaned):
        prev = cleaned[i - 1] if i > 0 else None
        gap = 0.0
        if prev is not None:
            try:
                gap = float(w.get("start", 0.0)) - float(prev.get("end", 0.0))
            except (TypeError, ValueError):
                gap = 0.0

        if (
            current
            and gap >= pause_break_s
            and calc_zh_display_weight(_joined_cjk_line_text(current))
            >= min_weight_before_pause_break
        ):
            groups.append(current)
            current = []

        tentative = current + [w]
        tw = calc_zh_display_weight(_joined_cjk_line_text(tentative))
        if not current:
            current = tentative
            continue
        if tw <= max_weight:
            current = tentative
        else:
            groups.append(current)
            current = [w]

    if current:
        groups.append(current)

    out: List[Dict[str, Any]] = []
    for g in groups:
        txt = _joined_cjk_line_text(g)
        if not txt:
            continue
        confs = [_word_confidence(x) for x in g]
        cmin = min(confs) if confs else 1.0
        out.append(
            {
                "text": txt,
                "start": float(g[0].get("start", 0.0)),
                "end": float(g[-1].get("end", 0.0)),
                "confidence": cmin,
            }
        )
    return out


def _normalize_for_zh_line_match(s: str) -> str:
    t = (s or "").strip()
    t = re.sub(r"[\s\u3000]+", "", t)
    t = re.sub(
        r"[，。！？、；：「」『』（）【】《》…,.!?:;\"'·（）—\[\]{}]",
        "",
        t,
    )
    return t


def _zh_line_soft_match_ratio(a: str, b: str) -> float:
    na = _normalize_for_zh_line_match(a)
    nb = _normalize_for_zh_line_match(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


# 叠字语气词、口播衔接词重复（保守规则，不碰专有名词与强调式「好好」等双字）
_SAME_ORAL_CHAR_3PLUS = re.compile(
    r"([啊嗯呃哦噢欸诶呀嘛呢吧呐哼哈嘿])\1{2,}"
)
_DISCOURSE_DUP = re.compile(
    r"(就是|然后|那个|这个|所以|但是|不过|对吧|是吧|好吧|对对)\1+"
)


def strip_obvious_zh_oral_redundancy(text: str) -> str:
    """
    Light, deterministic cleanup: collapse triple+ oral particles and doubled discourse fillers.
    Runs before/after LLM line polish so subtitles stay readable even without a model call.
    """
    t = (text or "").strip()
    if len(t) < 2:
        return t
    for _ in range(6):
        t2 = _SAME_ORAL_CHAR_3PLUS.sub(r"\1", t)
        t2 = _DISCOURSE_DUP.sub(r"\1", t2)
        # 对对对、错错错 等三连以上单字叠用（保留「对对」等两字）
        t2 = re.sub(r"([对错])\1{2,}", r"\1", t2)
        if t2 == t:
            break
        t = t2
    return t


def _zh_polish_candidate_acceptable(baseline: str, candidate: str) -> bool:
    """Allow slightly lower similarity when the line was legitimately shortened (filler removal)."""
    b = (baseline or "").strip()
    c = (candidate or "").strip()
    if not c:
        return False
    r = _zh_line_soft_match_ratio(b, c)
    if r >= 0.74:
        return True
    if len(b) >= 6 and len(c) <= int(len(b) * 0.92) and r >= 0.62:
        return True
    return False


class ZhCaptionLinePolish(BaseModel):
    i: int = Field(ge=0, description="0-based index within this batch")
    text: str = Field(description="Polished single subtitle line")


class ZhCaptionPolishBatch(BaseModel):
    items: List[ZhCaptionLinePolish]


_zh_caption_polish_agent: Optional[Agent] = None


def _get_zh_caption_polish_agent() -> Agent:
    global _zh_caption_polish_agent
    if _zh_caption_polish_agent is None:
        err = _missing_llm_key_error()
        if err:
            raise RuntimeError(err)
        _zh_caption_polish_agent = Agent(
            model=config.llm,
            system_prompt=(
                "你是中文短视频字幕编辑，面向竖屏短视频烧录字幕。输入为若干已按时间切好的字幕行（口语转写，可能缺标点或有 ASR 错字）。"
                "任务：在保留事实与核心观点的前提下，让每行更「好读、好扫」——"
                "（1）添加规范的简体中文标点（，。！？等），必要时拆成更自然的意群停顿；"
                "（2）纠正明显同音错字，尊重术语表；"
                "（3）适度删剪无信息增益的口癖与语气词（如叠用「啊」「嗯」「就是就是」「然后然后」、赘余的「那个」「这个」作拖延时）、"
                "无意义的重复词与口吃式叠字，但勿删掉有语气的强调（如「非常非常」）或关键否定；"
                "（4）若删剪后该行明显变短，须保证主干信息仍在，禁止删到语义残缺或空洞。"
                "硬性约束：本批输出行数必须等于输入行数；索引 i 必须对应输入的第 i 行；禁止合并两行、禁止拆一行为两行；"
                "禁止输出编号前缀或引号标签；除因删剪口癖/重复导致的变短外，每行字符数相对该行输入变化不超过 ±18%；"
                "因合理删剪语气词与重复而变短时，总长不宜短于原行的 45%（除非原行几乎全是赘语）。"
            ),
            output_type=ZhCaptionPolishBatch,
        )
    return _zh_caption_polish_agent


async def polish_zh_caption_lines_llm_async(
    lines: List[str],
    hotwords: Optional[str],
) -> List[str]:
    """Batch line-level polish; returns same-length list (falls back to input on failure)."""
    if not lines:
        return []
    base = [str(x) for x in lines]
    n = len(base)
    out = list(base)
    bs = 16
    for start in range(0, n, bs):
        chunk = base[start : start + bs]
        cn = len(chunk)
        try:
            agent = _get_zh_caption_polish_agent()
        except Exception as e:
            logger.warning("Zh caption polish agent unavailable: %s", e)
            return list(base)
        parts = [
            f"本批共 {cn} 行，局部索引为 0..{cn - 1}，每行格式: 索引<TAB>文本",
            "\n".join(f"{i}\t{chunk[i]}" for i in range(cn)),
            "请逐行输出润色结果：优先去掉无效语气词与无意义重复，使重点更突出；不要改变原意与事实。",
        ]
        if hotwords and hotwords.strip():
            parts.append("术语/热词（请按此书写）：\n" + hotwords.strip()[:6000])
        user_msg = "\n\n".join(parts)
        try:
            result = await agent.run(user_msg)
            batch = getattr(result, "output", None)
        except Exception as e:
            logger.warning("Zh caption polish LLM call failed: %s", e)
            continue
        if not isinstance(batch, ZhCaptionPolishBatch) or not batch.items:
            continue
        for it in batch.items:
            if not (0 <= it.i < cn):
                continue
            cand = (it.text or "").strip()
            if not cand:
                continue
            g = start + it.i
            raw = base[g]
            if _zh_polish_candidate_acceptable(raw, cand):
                out[g] = cand
            else:
                logger.info(
                    "Zh caption polish line %s rejected (low similarity to baseline)",
                    g,
                )
    return out


def polish_zh_clip_subtitles_for_burn_sync(
    words: List[Dict[str, Any]],
    *,
    hotwords: Optional[str] = None,
    use_llm: bool = True,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    For primarily-Chinese clip ASR words: merge into weighted lines, optionally LLM-polish,
    return one pseudo-token per caption card (caller should use presized static layout).

    When not applicable, returns (words, False) unchanged.
    """
    from .video_utils import _words_are_primarily_cjk

    if not words:
        return words, False
    if not _words_are_primarily_cjk(words):
        return words, False

    try:
        merged = merge_whisper_words_into_zh_weighted_lines(words)
        if not merged:
            return words, False

        raw_texts = [str(m.get("text") or "").strip() for m in merged]
        if not any(raw_texts):
            return words, False

        baseline_texts = [strip_obvious_zh_oral_redundancy(t) for t in raw_texts]
        finals = list(baseline_texts)
        if use_llm:
            try:
                polished = asyncio.run(
                    polish_zh_caption_lines_llm_async(baseline_texts, hotwords)
                )
            except RuntimeError as e:
                msg = str(e)
                if "asyncio.run() cannot be called from a running event loop" in msg:
                    logger.warning("Zh caption polish skipped (nested event loop): %s", e)
                else:
                    logger.warning("Zh caption polish asyncio.run failed: %s", e)
                polished = list(baseline_texts)
            except Exception as e:
                logger.warning("Zh caption polish failed: %s", e)
                polished = list(baseline_texts)
            if len(polished) == len(baseline_texts):
                for i, (base_line, cand) in enumerate(zip(baseline_texts, polished)):
                    c = (cand or "").strip()
                    if not c:
                        continue
                    if _zh_polish_candidate_acceptable(base_line, c):
                        finals[i] = strip_obvious_zh_oral_redundancy(c)

        out_words: List[Dict[str, Any]] = []
        for i, (m, txt) in enumerate(zip(merged, finals)):
            safe = (txt or "").strip() or raw_texts[i]
            out_words.append(
                {
                    "text": safe,
                    "start": float(m["start"]),
                    "end": float(m["end"]),
                    "confidence": float(m.get("confidence", 1.0) or 1.0),
                }
            )
        return out_words, True
    except Exception as e:
        logger.warning(
            "polish_zh_clip_subtitles_for_burn_sync failed; using original ASR words: %s",
            e,
            exc_info=True,
        )
        return words, False
