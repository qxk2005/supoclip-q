"""
AI-related functions for transcript analysis with enhanced precision and virality scoring.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Mapping
import asyncio
import logging
import re

from pydantic_ai import Agent
from pydantic import BaseModel, Field, ValidationError

from .config import Config

logger = logging.getLogger(__name__)
config = Config()


class ViralityAnalysis(BaseModel):
    """Detailed virality breakdown for a segment."""

    hook_score: int = Field(
        description="How strong is the opening hook (0-25)", ge=0, le=25
    )
    engagement_score: int = Field(
        description="How engaging/entertaining is the content (0-25)", ge=0, le=25
    )
    value_score: int = Field(
        description="Educational/informational value (0-25)", ge=0, le=25
    )
    shareability_score: int = Field(
        description="Likelihood of being shared (0-25)", ge=0, le=25
    )
    total_score: int = Field(
        description="Combined virality score (0-100)", ge=0, le=100
    )
    hook_type: Optional[
        Literal["question", "statement", "statistic", "story", "contrast", "none"]
    ] = Field(
        default="none",
        description="Type of hook: question, statement, statistic, story, contrast, or none",
    )
    virality_reasoning: str = Field(
        description="Short explanation of the virality subscores (Simplified Chinese in practice)."
    )


class TranscriptSegment(BaseModel):
    """Represents a relevant segment of transcript with precise timing and virality analysis."""

    start_time: str = Field(description="Start timestamp in MM:SS format")
    end_time: str = Field(description="End timestamp in MM:SS format")
    text: str = Field(
        description=(
            "Transcript text taken only from the selected timestamp range. "
            "Keep it verbatim or near-verbatim, and do not paraphrase or merge non-contiguous lines."
        )
    )
    title_zh: str = Field(
        default="",
        max_length=80,
        description=(
            "One short Simplified Chinese headline (about 8–18 characters) capturing the single most important hook."
        ),
    )
    golden_quote_zh: str = Field(
        default="",
        max_length=120,
        description=(
            "One memorable Simplified Chinese 'golden quote' summarizing the clip's core idea for a persistent on-video title. "
            "Prefer a SINGLE line (~10–22 characters). Use a second line only if truly necessary; never pad or split into two on purpose."
        ),
    )
    relevance_score: float = Field(
        description="Relevance score from 0.0 to 1.0", ge=0.0, le=1.0
    )
    reasoning: str = Field(
        description=(
            "Brief factual explanation in Simplified Chinese: why this segment works as a clip."
        )
    )
    virality: ViralityAnalysis = Field(description="Detailed virality score breakdown")


class LeanTranscriptSegment(BaseModel):
    """
    Compact segment shape for the first LLM pass only.

    Avoids large per-segment JSON (no four subscores + long virality_reasoning). Those are derived
    in code. Verbatim clip text stays in English (or source language); zh-CN for the UI is filled
    later by subtitle_translation.fill_missing_segment_text_translations_zh.
    """

    start_time: str = Field(description="Start timestamp in MM:SS format")
    end_time: str = Field(description="End timestamp in MM:SS format")
    text: str = Field(
        description="Verbatim transcript wording for the selected time range only (do not translate)."
    )
    relevance_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(
        description=(
            "One or two short sentences in Simplified Chinese (under ~120 characters): "
            "what the clip contains and how prior lines in the same range set up the payoff."
        )
    )
    virality_score: int = Field(
        ge=0,
        le=100,
        description="Single overall virality score 0-100 (no subscores in this step).",
    )
    hook_type: Optional[
        Literal["question", "statement", "statistic", "story", "contrast", "none"]
    ] = Field(default="none")
    title_zh: str = Field(
        default="",
        max_length=80,
        description=(
            "One short Simplified Chinese headline (about 8–18 characters) for UI and optional on-video title; "
            "must highlight the single strongest reason to watch this clip."
        ),
    )
    golden_quote_zh: str = Field(
        default="",
        max_length=120,
        description=(
            "Golden quote in Simplified Chinese: the most representative phrase for this clip's central idea (persistent in-video title). "
            "Prefer ONE line (~10–22 characters). A second line only if the idea cannot fit one line; do not force two lines."
        ),
    )


class LeanBRollOpportunity(BaseModel):
    """B-roll hint with minimal fields for the lean analysis pass."""

    timestamp: str = Field(description="MM:SS")
    duration: float = Field(ge=2.0, le=5.0)
    search_term: str = Field(description="Short English keyword for stock search")
    context: str = Field(description="Brief Simplified Chinese (one short phrase)")


class LeanTranscriptAnalysis(BaseModel):
    """First-pass analysis: small JSON footprint to reduce truncation and invalid output."""

    most_relevant_segments: List[LeanTranscriptSegment]
    summary: str = Field(description="Brief summary in Simplified Chinese (under ~300 characters).")
    key_topics: List[str] = Field(
        description="Short Simplified Chinese topic labels (each under ~20 characters)."
    )
    broll_opportunities: Optional[List[LeanBRollOpportunity]] = Field(
        default=None,
        description="Only when B-roll is requested in the user task.",
    )


class BRollOpportunity(BaseModel):
    """Identifies an opportunity to insert B-roll footage."""

    timestamp: str = Field(description="When to insert B-roll (MM:SS format)")
    duration: float = Field(
        description="How long to show B-roll (2-5 seconds)", ge=2.0, le=5.0
    )
    search_term: str = Field(description="Keyword to search for B-roll footage")
    context: str = Field(description="What is discussed (Simplified Chinese in practice).")


class TranscriptAnalysis(BaseModel):
    """Analysis result for transcript segments with virality and B-roll opportunities."""

    most_relevant_segments: List[TranscriptSegment]
    summary: str = Field(description="Brief summary in Simplified Chinese.")
    key_topics: List[str] = Field(description="Main topics as short phrases in Simplified Chinese.")
    broll_opportunities: Optional[List[BRollOpportunity]] = Field(
        default=None, description="Opportunities to insert B-roll footage"
    )


# First-pass prompt: compact JSON only (full subscores are derived in code; zh transcript lines later).
transcript_analysis_system_prompt = """You are an expert transcript analyst for short-form video editing.

Your job is to identify the best clip candidates from the transcript. Output must stay SMALL: one overall virality_score per segment (0-100), not four sub-scores and not long scoring prose.

OUTPUT LANGUAGE:
- reasoning, summary, key_topics, B-roll context: Simplified Chinese, short.
- segment.text: verbatim from the transcript only (same language as the audio). Never translate segment.text into Chinese in this step.

FORBIDDEN:
- Do not output chain-of-thought, "Thinking Process", step-by-step analysis, or preambles.
- Do not echo long excerpts of the transcript outside JSON.
- The first non-whitespace character of your entire reply MUST be `{` or `[` starting the JSON value.

CORE OBJECTIVES:
1. Pick moments that work as standalone short clips: a viewer who did not watch the full video must understand *what is being said and why it matters*.
2. Prefer a **complete narrative beat**: enough **prior context** (problem, premise, definition, or story setup) so the **highlight / punchline / takeaway** is not a non sequitur. Do not optimize only for a dense “quote” if that quote depends on earlier explanation in the same contiguous stretch.
3. Each segment must be a contiguous range from the transcript timestamps.

GROUNDING RULES:
1. Use only provided transcript lines and timestamps.
2. Do not invent facts. segment.text must match the transcript in that time range.
3. If the user message includes a DOMAIN GLOSSARY, you may fix clear ASR mis-hearings inside segment.text only when the transcript clearly refers to that term. Do not merge non-contiguous spans.

SEGMENT FIELDS (per segment):
- start_time, end_time, text, relevance_score (0-1), reasoning (short Chinese), virality_score (0-100 integer), hook_type.
- title_zh: one punchy Simplified Chinese headline (about 8–18 characters) for the clip card; not a full sentence.
- golden_quote_zh: the best "golden quote" in Simplified Chinese for a persistent on-video title (core idea). Prefer ONE line (~10–22 characters). Second line only if necessary; never pad to fill two lines.

TIMING:
- Default to **~25–90 seconds** per segment when the topic needs setup; include earlier contiguous lines until the clip feels whole.
- Use **~15–45 seconds** only when the selected span is already self-contained (question + answer, or a full mini-story) without missing prerequisites.
- Avoid ultra-tight cuts whose main “value” line only makes sense after prior sentences you did not include—**extend `start_time` backward** on the transcript until the setup is present (still one contiguous range).

Quality over quantity.
"""

# Second-chance prompt when the model returns prose / thinking but no parseable JSON.
_JSON_RETRY_PREFIX = (
    "Your previous reply was NOT valid JSON. Output ONE JSON object only: no thinking, "
    "no 'Thinking Process', no markdown fences, no commentary. First character must be '{'.\n"
    'Schema: {"summary": string (zh-CN), "key_topics": string[] (zh-CN), '
    '"most_relevant_segments": object[]}.\n'
    "Each segment object: start_time, end_time, text (verbatim from transcript), "
    "relevance_score (number 0-1), reasoning (short zh-CN), virality_score (integer 0-100), "
    "optional hook_type, title_zh (short zh-CN headline, ~8-18 characters), "
    "golden_quote_zh (zh-CN, prefer ONE line ~10-22 chars; second line only if needed).\n\n"
    "Follow the full task below (including transcript and any theme/count constraints).\n\n"
)

# Lazy-loaded agent to avoid import-time failures when API keys aren't set
_transcript_agent: Optional[Agent[None, LeanTranscriptAnalysis]] = None


def _get_missing_llm_key_error(model_name: str) -> Optional[str]:
    """Return a clear configuration error when the selected LLM key is missing."""
    provider = model_name.split(":", 1)[0].strip().lower()

    if provider in {"google", "google-gla"} and not config.google_api_key:
        return (
            "Selected LLM provider is Google, but GOOGLE_API_KEY is not set. "
            "Set GOOGLE_API_KEY or set LLM to openai:* / anthropic:* / ollama:* with the matching API key."
        )

    if provider == "openai" and not config.openai_api_key:
        return (
            "Selected LLM provider is OpenAI, but OPENAI_API_KEY is not set. "
            "Set OPENAI_API_KEY or choose another provider with a matching API key."
        )

    if provider == "anthropic" and not config.anthropic_api_key:
        return (
            "Selected LLM provider is Anthropic, but ANTHROPIC_API_KEY is not set. "
            "Set ANTHROPIC_API_KEY or choose another provider with a matching API key."
        )

    if provider == "ollama":
        # Ollama can run locally without an API key. OLLAMA_BASE_URL/OLLAMA_API_KEY
        # are optional and passed through as environment variables.
        return None

    return None


def get_transcript_agent() -> Agent[None, LeanTranscriptAnalysis]:
    """Get or create the transcript analysis agent (lazy initialization)."""
    global _transcript_agent
    if _transcript_agent is None:
        config_error = _get_missing_llm_key_error(config.llm)
        if config_error:
            raise RuntimeError(config_error)

        agent_args = {
            "model": config.llm,
            "system_prompt": transcript_analysis_system_prompt,
        }

        # The base_url should be configured via environment variables (e.g., OPENAI_BASE_URL)
        # and is automatically picked up by the underlying LLM client.
        # We no longer pass it directly to the Agent constructor.

        _transcript_agent = Agent[None, LeanTranscriptAnalysis](**agent_args)
    return _transcript_agent


def build_transcript_analysis_prompt(
    transcript: str,
    include_broll: bool = False,
    language: str = "en",
    professional_hotwords: Optional[str] = None,
    clip_theme: Optional[str] = None,
    target_clip_count: Optional[int] = None,
    chunk_index: int = 0,
    total_chunks: int = 1,
) -> str:
    """Build the grounded task prompt for transcript analysis."""
    broll_instruction = ""
    if include_broll:
        broll_instruction = (
            "\n5. Also identify B-roll opportunities for each chosen segment where stock footage could enhance the visual appeal."
        )

    lang_instruction = "The transcript is in English."
    lang_norm = (language or "").strip().lower()
    if language == "zh" or lang_norm in ("zh-cn", "zh_cn", "chinese"):
        lang_instruction = "The transcript is in Chinese (zh-CN)."
    elif lang_norm in ("auto", "unknown", ""):
        lang_instruction = (
            "Infer the transcript's spoken language from the lines; "
            "segment.text must match the transcript wording in that language."
        )
    elif language and lang_norm != "en":
        lang_instruction = f"The transcript is in the language: {language}."

    zh_format_block = ""
    if language == "zh" or lang_norm in ("zh-cn", "zh_cn", "chinese"):
        zh_format_block = """
Chinese segment.text readability:
- Add natural Simplified Chinese punctuation (，。！？、；：) at appropriate clause or sentence boundaries so each clip excerpt is easy to read and parse. Do not change or add words; punctuation only. If the transcript line has no punctuation, infer minimal marks from grammar and natural pauses (do not wrap the whole segment in decorative quotes unless the speech itself implies them).
"""

    glossary_block = ""
    hw = (professional_hotwords or "").strip()
    if hw:
        glossary_block = f"""
DOMAIN GLOSSARY (professional / product terms; one entry per line or comma-separated):
{hw}

Use these exact spellings in segment.text when the transcript wording is a likely automatic-speech-recognition error for the same term or concept. Keep segment boundaries and timestamps strictly aligned with the transcript; do not paraphrase for style.
"""

    theme_block = ""
    th = (clip_theme or "").strip()
    if th:
        theme_block = f"""
CLIP THEME (user request; language may vary):
"{th}"

When ranking and selecting segments:
- Strongly prefer moments that clearly discuss, illustrate, or relate to this theme.
- Set relevance_score higher when the spoken content matches the theme; lower when only weakly related.
- If this excerpt barely touches the theme, return fewer strong segments rather than stretching weak matches.
"""

    count_block = ""
    tc = target_clip_count
    if tc is not None:
        tc = max(1, min(tc, config.max_clips))
        parts = max(1, total_chunks)
        idx = max(0, chunk_index)
        # Enough candidates per chunk for a global top-N after merging; capped to control JSON size.
        per_chunk_budget = max(
            1, min(14, (tc + parts - 1) // parts + 2)
        )
        count_block = f"""
USER TARGET FOR THE FULL VIDEO: about {tc} clips after all transcript parts are merged.
This transcript is excerpt {idx + 1} of {parts} (non-overlapping segments of the full video).
For THIS excerpt only, include at most {per_chunk_budget} objects in most_relevant_segments.
Prefer diverse, non-overlapping moments with strong hooks; do not pad with weak filler.
"""

    return f"""Analyze this video transcript and identify the most engaging segments for short-form content.

{lang_instruction}
{zh_format_block}
{glossary_block}
{theme_block}
{count_block}
- Explanations (reasoning, virality_reasoning, summary, key_topics): Simplified Chinese.
- segment.text: exact transcript wording only (do not translate segment.text into Chinese here).

The transcript is formatted as one line per timestamped span, for example:
[00:12 - 00:21] Spoken text here
[00:21 - 00:35] More spoken text here

Follow this workflow:
1. Read the transcript as a sequence of timestamped spans.
2. Select only contiguous ranges that already exist in the transcript.
3. For each candidate “highlight”, check whether a **first-time viewer** would miss **who/what/why** without earlier lines; if yes, widen the range **backward** (and forward if the payoff continues) so the clip includes that setup—still one contiguous block.
4. Prefer moments with a clear arc: setup → tension or question → insight, payoff, or emotional beat (not an isolated fragment).
5. For each chosen segment, use the earliest timestamp in the selected range as start_time and the latest timestamp in the selected range as end_time.{broll_instruction}

Critical accuracy requirements:
- Do not fabricate or embellish content.
- Do not use timestamps that are not present in the transcript.
- Do not merge separate non-contiguous moments into one segment.
- segment.text must reflect only the spoken content inside the selected time range.
- If a span lacks enough context to stand alone, **expand start_time backward** (and end_time if needed) along contiguous transcript lines until the idea is self-contained; never invent bridging text.
- If there is a tradeoff between "viral" and "accurate", choose accuracy.
- Do not reject or penalize a segment simply because of the subject matter; stay content-neutral and assess clip quality only.

Transcript:
{transcript}

OUTPUT FORMAT (critical):
- Do not output thinking steps, chain-of-thought, or a "Thinking Process" section. Respond with JSON only.
- Output ONE JSON value only (no markdown fences required). Either a JSON array of segment objects, OR an object with key "most_relevant_segments" (array).
- Each segment object MUST include: "start_time", "end_time", "text" (verbatim transcript only), "relevance_score" (number 0-1), "reasoning" (short Simplified Chinese), "virality_score" (integer 0-100), and optionally "hook_type".
- Do NOT include a "virality" object or per-field subscores; use only "virality_score".
- Valid UTF-8 JSON: use double quotes for all keys and string values; escape internal double quotes as \\".
- Do not wrap the JSON in markdown code blocks. Do not add commentary before or after the JSON.
- Do not use ### headings. Avoid putting raw [MM:SS] timestamps outside JSON strings."""


def _strip_model_reasoning_prefix(text: str) -> str:
    """Drop trailing thinking/reasoning wrappers some providers emit before the real answer."""
    t = text.strip()
    for sep in ("</think>", "`</think>`", "</think>", "<|im_end|>"):
        pos = t.rfind(sep)
        if pos != -1:
            t = t[pos + len(sep) :].strip()
    return t


def _strip_llm_think_blocks(text: str) -> str:
    """Remove thinking blocks that precede JSON (Qwen / OpenAI-compat)."""
    t = text
    for pat in (
        r"`<redacted_thinking>`[\s\S]*?`</redacted_thinking>`",
        r"`<redacted_thinking>`[\s\S]*?`</think>`",
        r"`<think>`[\s\S]*?`</think>`",
        r"`<think>`[\s\S]*?`</think>`",
    ):
        t = re.sub(pat, "", t, flags=re.IGNORECASE)
    return t


def _try_raw_decode_at_json_starts(cleaned: str) -> Optional[Any]:
    """Try json.JSONDecoder.raw_decode from plausible JSON value starts."""
    decoder = json.JSONDecoder()
    patterns = (
        r'\{\s*"most_relevant_segments"\s*:',
        r'\{\s*"segments"\s*:',
        r"\[\s*\{",
        r'\{\s*"start_time"\s*:',
    )
    for pat in patterns:
        for m in re.finditer(pat, cleaned):
            try:
                obj, _ = decoder.raw_decode(cleaned, m.start())
                return obj
            except json.JSONDecodeError:
                continue
    return None


def _extract_json_envelope_by_brace_scan(text: str) -> Optional[Any]:
    """
    When models emit long 'Thinking Process' then valid JSON, or JSON whose first key is not
    most_relevant_segments (e.g. summary first), find a top-level dict/array by trying raw_decode
    from each '{' position. Prefer dicts that contain most_relevant_segments / segments; do not stop
    at inner '{' that opens a segment object inside the array (that would decode to a fragment).
    """
    decoder = json.JSONDecoder()
    max_tries = 450

    brace_starts = [m.start() for m in re.finditer(r"\{", text)]
    window = brace_starts[-max_tries:]

    last_envelope: Optional[dict[str, Any]] = None
    for pos in window:
        try:
            obj, _ = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and (
            "most_relevant_segments" in obj or "segments" in obj
        ):
            last_envelope = obj
    if last_envelope is not None:
        return last_envelope

    for pos in reversed(window):
        try:
            obj, _ = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(obj, dict)
            and "start_time" in obj
            and "end_time" in obj
            and _segment_spoken_text_from_dict(obj)
        ):
            return [obj]

    bracket_starts = [m.start() for m in re.finditer(r"\[\s*\{", text)]
    for pos in reversed(bracket_starts[-max_tries:]):
        try:
            obj, _ = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(obj, list)
            and obj
            and isinstance(obj[0], dict)
            and ("start_time" in obj[0] or "text" in obj[0])
        ):
            return obj
    return None


def _strip_thinking_prose_before_final_json(text: str) -> str:
    """
    Models often emit 'Thinking Process' first, then JSON. The JSON object may list summary or
    key_topics *before* most_relevant_segments, so we cannot require '\\{\"most_relevant_segments\"'.
    Prefer the last parseable envelope dict by scanning '{' positions from the end.
    """
    extracted = _extract_json_envelope_by_brace_scan(text)
    if extracted is not None:
        try:
            return json.dumps(extracted, ensure_ascii=False)
        except (TypeError, ValueError):
            pass

    best_start: Optional[int] = None
    for pat in (
        r'\{\s*"most_relevant_segments"\s*:\s*\[',
        r'\{\s*"segments"\s*:\s*\[',
        r'"most_relevant_segments"\s*:\s*\[',
        r'"segments"\s*:\s*\[',
    ):
        for m in re.finditer(pat, text):
            best_start = m.start()
    if best_start is not None:
        # If match started at ", walk back to the object '{' for a clean cut (best effort).
        if best_start < len(text) and text[best_start] != "{":
            decoder = json.JSONDecoder()
            prefix = text[:best_start]
            for pos in reversed([m.start() for m in re.finditer(r"\{", prefix)][-120:]):
                try:
                    obj, _ = decoder.raw_decode(text, pos)
                    if isinstance(obj, dict) and (
                        "most_relevant_segments" in obj or "segments" in obj
                    ):
                        return text[pos:]
                except json.JSONDecodeError:
                    continue
        return text[best_start:]
    return text


def _trim_to_first_json_value(text: str) -> str:
    """Drop leading prose so the first character is `{` or `[` starting a JSON value."""
    m = re.search(
        r'(\{\s*"(?:most_relevant_segments|segments|summary|key_topics)"|\[\s*\{)',
        text,
    )
    if m:
        return text[m.start() :]
    return text


def _segment_spoken_text_from_dict(segment: Mapping[str, Any]) -> str:
    """Normalize segment body: models may use text, transcript, body, or leave text null."""
    for key in (
        "text",
        "transcript",
        "body",
        "content",
        "spoken_text",
        "segment_text",
        "quote",
    ):
        val = segment.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _segments_from_markdown_style_output(text: str) -> list[dict[str, Any]]:
    """
    When the model returns Markdown reports (### Segment / **Timestamps:**) instead of JSON,
    extract segment dicts compatible with _transcript_analysis_from_parsed_json.
    """
    segments: list[dict[str, Any]] = []
    parts = re.split(r"\n###\s+Segment\s+\d+\s*:", text, flags=re.IGNORECASE)
    for chunk in parts[1:]:
        ts_m = re.search(r"\[(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\]", chunk)
        if not ts_m:
            continue
        start_time, end_time = ts_m.group(1), ts_m.group(2)
        text_m = re.search(
            r"(?:\*\*)?Text(?:\*\*)?\s*:\s*\n(.+?)(?=\n\*\*Virality|\n---|\Z)",
            chunk,
            re.DOTALL | re.IGNORECASE,
        )
        body = text_m.group(1).strip() if text_m else ""
        body = re.sub(r"\s+", " ", body).strip()
        if len(body.split()) < 3:
            continue
        segments.append(
            {
                "start_time": start_time,
                "end_time": end_time,
                "text": body,
                "reasoning": "从模型 Markdown 输出解析的片段。",
                "virality_score": 76,
                "virality_breakdown": {
                    "hook_strength": 19,
                    "engagement": 19,
                    "value": 19,
                    "shareability": 19,
                },
            }
        )
    return segments


def _normalize_json_candidate(s: str) -> str:
    """Reduce common LLM JSON issues (smart quotes, BOM) before parsing."""
    t = s.replace("\ufeff", "")
    return (
        t.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _parse_json_payload_from_llm_text(text: str) -> Optional[Any]:
    """
    Extract JSON array or object from model output without mistaking Markdown timestamps
    like [15:21 - 15:45] for the start of a JSON array.
    """
    raw = _strip_model_reasoning_prefix(text)
    raw = _strip_llm_think_blocks(raw)
    raw = _strip_thinking_prose_before_final_json(raw)
    raw = _trim_to_first_json_value(raw)
    cleaned = _normalize_json_candidate(raw)
    decoder = json.JSONDecoder()

    # 0) Skip prose before the analysis object. Only match envelope keys — NOT "start_time"
    # (that also appears on each segment object and would make "last match" cut to a fragment).
    first_obj_matches = list(
        re.finditer(
            r'\{\s*"(?:most_relevant_segments|segments|summary|key_topics)"',
            cleaned,
        )
    )
    if first_obj_matches:
        cut = first_obj_matches[-1].start()
        if cut > 0:
            cleaned = cleaned[cut:]

    # 1) Fenced ```json ... ``` blocks
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE):
        chunk = m.group(1).strip()
        if not chunk:
            continue
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            try:
                return decoder.raw_decode(chunk, 0)[0]
            except json.JSONDecodeError:
                continue

    # 2) Object with most_relevant_segments or segments (key may appear after summary/key_topics)
    for key in ("most_relevant_segments", "segments"):
        matches = list(re.finditer(rf'"{key}"\s*:', cleaned))
        if not matches:
            continue
        m_key = matches[-1]
        brace_before = [x.start() for x in re.finditer(r"\{", cleaned[: m_key.start() + 1])]
        for pos in reversed(brace_before[-150:]):
            try:
                obj, _ = decoder.raw_decode(cleaned, pos)
                if isinstance(obj, dict) and key in obj:
                    return obj
            except json.JSONDecodeError:
                continue

    # 3) JSON array of objects — require `[` then `{` (not `[15:` timestamp)
    for m in re.finditer(r"\[\s*\{", cleaned):
        try:
            return decoder.raw_decode(cleaned, m.start())[0]
        except json.JSONDecodeError:
            continue

    # 4) Single segment object (legacy) — only when there is no analysis envelope in the string,
    # otherwise step 4 would match the first segment inside most_relevant_segments and truncate.
    if "most_relevant_segments" not in cleaned and "segments" not in cleaned:
        m_seg = re.search(r"\{\s*\"start_time\"\s*:", cleaned)
        if m_seg:
            try:
                return decoder.raw_decode(cleaned, m_seg.start())[0]
            except json.JSONDecodeError:
                pass

    md_segments = _segments_from_markdown_style_output(cleaned)
    if md_segments:
        logger.info(
            "Recovered %s segment(s) from Markdown-style model output (no JSON array found).",
            len(md_segments),
        )
        return md_segments

    scanned = _try_raw_decode_at_json_starts(cleaned)
    if scanned is not None:
        return scanned

    brace_guess = _extract_json_envelope_by_brace_scan(cleaned)
    if brace_guess is not None:
        return brace_guess
    brace_guess = _extract_json_envelope_by_brace_scan(_normalize_json_candidate(text))
    if brace_guess is not None:
        return brace_guess

    return None


def _safe_int_score(value: Any, default: int = 0) -> int:
    """Coerce LLM numeric fields (may be str/float) to int; ignore dict/list."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(float(s))
        except ValueError:
            return default
    return default


def _virality_dict_from_segment_json(segment: Mapping[str, Any]) -> dict[str, int]:
    """
    Normalize virality fields from heterogeneous model JSON.

    Some models emit a numeric ``virality_score``; others nest subscores under
    ``virality_score`` as an object (instead of ``virality_breakdown``). Both are supported.
    """
    breakdown = segment.get("virality_breakdown")
    if not isinstance(breakdown, dict):
        breakdown = {}

    raw_vs = segment.get("virality_score")
    merged: dict[str, Any] = dict(breakdown)
    if isinstance(raw_vs, dict):
        merged = {**merged, **raw_vs}

    hook = _safe_int_score(merged.get("hook_strength", merged.get("hook_score")))
    engagement = _safe_int_score(
        merged.get("engagement", merged.get("engagement_score"))
    )
    value = _safe_int_score(merged.get("value", merged.get("value_score")))
    share = _safe_int_score(
        merged.get("shareability", merged.get("shareability_score"))
    )

    hook = max(0, min(25, hook))
    engagement = max(0, min(25, engagement))
    value = max(0, min(25, value))
    share = max(0, min(25, share))

    total_score = hook + engagement + value + share
    if total_score == 0:
        t = _safe_int_score(merged.get("total", merged.get("total_score")))
        if t:
            total_score = max(0, min(100, t))
    else:
        total_score = max(0, min(100, total_score))

    return {
        "hook_score": hook,
        "engagement_score": engagement,
        "value_score": value,
        "shareability_score": share,
        "total_score": total_score,
    }


def _distribute_virality_total(total: int) -> tuple[int, int, int, int]:
    """Map a single 0-100 score to four 0-25 subscores that sum to total (for downstream compatibility)."""
    t = max(0, min(100, int(total)))
    base, rem = divmod(t, 4)
    parts = [base + (1 if i < rem else 0) for i in range(4)]
    return (parts[0], parts[1], parts[2], parts[3])


def lean_transcript_analysis_to_full(lean: LeanTranscriptAnalysis) -> TranscriptAnalysis:
    """Expand first-pass lean analysis into the full TranscriptAnalysis used by the rest of the pipeline."""
    segments_out: List[TranscriptSegment] = []
    allowed_hooks = (
        "question",
        "statement",
        "statistic",
        "story",
        "contrast",
        "none",
    )
    for seg in lean.most_relevant_segments:
        hook_type = seg.hook_type or "none"
        if hook_type not in allowed_hooks:
            hook_type = "none"
        h, e, v, s = _distribute_virality_total(seg.virality_score)
        vr = f"综合传播潜力 {seg.virality_score}/100（由单分拆解为四项子分供系统使用）。"
        vir = ViralityAnalysis(
            hook_score=h,
            engagement_score=e,
            value_score=v,
            shareability_score=s,
            total_score=seg.virality_score,
            hook_type=hook_type,
            virality_reasoning=vr,
        )
        tz = (getattr(seg, "title_zh", None) or "").strip()
        gq = (getattr(seg, "golden_quote_zh", None) or "").strip()
        segments_out.append(
            TranscriptSegment(
                start_time=seg.start_time,
                end_time=seg.end_time,
                text=seg.text,
                title_zh=tz,
                golden_quote_zh=gq,
                relevance_score=seg.relevance_score,
                reasoning=seg.reasoning,
                virality=vir,
            )
        )

    broll: Optional[List[BRollOpportunity]] = None
    if lean.broll_opportunities:
        broll = [
            BRollOpportunity(
                timestamp=x.timestamp,
                duration=x.duration,
                search_term=x.search_term,
                context=x.context,
            )
            for x in lean.broll_opportunities
        ]

    return TranscriptAnalysis(
        most_relevant_segments=segments_out,
        summary=lean.summary,
        key_topics=lean.key_topics,
        broll_opportunities=broll,
    )


def _transcript_analysis_from_parsed_json(parsed: Any) -> Optional[TranscriptAnalysis]:
    """Build TranscriptAnalysis from parsed JSON (list of segments or full envelope dict)."""
    if parsed is None:
        return None
    if isinstance(parsed, list):
        envelope = {
            "most_relevant_segments": parsed,
            "summary": "Summary not generated by model.",
            "key_topics": [],
        }
    elif isinstance(parsed, dict):
        segs = parsed.get("most_relevant_segments")
        if segs is None:
            segs = parsed.get("segments")
        if segs is not None:
            envelope = {
                "most_relevant_segments": segs,
                "summary": parsed.get("summary", "Summary not generated by model."),
                "key_topics": parsed.get("key_topics", []) or [],
            }
        else:
            return None
    else:
        return None

    envelope_for_lean = dict(envelope)
    if isinstance(parsed, dict) and "broll_opportunities" in parsed:
        envelope_for_lean["broll_opportunities"] = parsed.get("broll_opportunities")
    try:
        lean = LeanTranscriptAnalysis.model_validate(envelope_for_lean)
        return lean_transcript_analysis_to_full(lean)
    except ValidationError:
        pass

    segments_raw = envelope.get("most_relevant_segments") or []
    adapted_segments = []
    for segment in segments_raw:
        if not isinstance(segment, dict):
            continue
        raw_vir = segment.get("virality")
        if isinstance(raw_vir, dict):
            merged_for_scores = {**segment, **raw_vir}
            v = _virality_dict_from_segment_json(merged_for_scores)
            hook_type = raw_vir.get("hook_type") or segment.get("hook_type") or "none"
            vir_reason = (
                raw_vir.get("virality_reasoning")
                or segment.get("virality_reasoning")
                or raw_vir.get("reasoning")
                or segment.get("reasoning", "AI generated clip.")
            )
        else:
            v = _virality_dict_from_segment_json(segment)
            hook_type = segment.get("hook_type") or "none"
            vir_reason = segment.get("virality_reasoning") or segment.get(
                "reasoning", "AI generated clip."
            )

        allowed_hooks = (
            "question",
            "statement",
            "statistic",
            "story",
            "contrast",
            "none",
        )
        if hook_type not in allowed_hooks:
            hook_type = "none"

        seg_text = _segment_spoken_text_from_dict(segment)
        if not seg_text:
            logger.info(
                "Skipping segment with empty text (no text/transcript/body); keys=%s",
                list(segment.keys())[:20],
            )
            continue
        st = segment.get("start_time")
        et = segment.get("end_time")
        if not st or not et:
            continue

        adapted_segment = {
            "start_time": st,
            "end_time": et,
            "text": seg_text,
            "title_zh": (segment.get("title_zh") or "").strip(),
            "golden_quote_zh": (segment.get("golden_quote_zh") or "").strip(),
            "relevance_score": float(segment.get("relevance_score", 0.9) or 0.9),
            "reasoning": segment.get("reasoning") or "AI generated clip.",
            "virality": {
                "hook_score": v["hook_score"],
                "engagement_score": v["engagement_score"],
                "value_score": v["value_score"],
                "shareability_score": v["shareability_score"],
                "total_score": v["total_score"],
                "hook_type": hook_type,
                "virality_reasoning": vir_reason,
            },
        }
        adapted_segments.append(adapted_segment)

    if not adapted_segments and segments_raw:
        logger.warning(
            "Dropped all %s parsed segment(s): missing non-empty text or timestamps",
            len(segments_raw),
        )

    analysis_obj = {
        "most_relevant_segments": adapted_segments,
        "summary": envelope.get("summary", "Summary not generated by model."),
        "key_topics": envelope.get("key_topics", []),
    }
    try:
        return TranscriptAnalysis.model_validate(analysis_obj)
    except ValidationError as exc:
        logger.warning("TranscriptAnalysis validation failed after JSON parse: %s", exc)
        return None


async def get_most_relevant_parts_by_transcript(
    transcript: str,
    include_broll: bool = False,
    chunk_size: int = 15000,
    language: str = "en",
    professional_hotwords: Optional[str] = None,
    clip_theme: Optional[str] = None,
    target_clip_count: Optional[int] = None,
    max_output_segments: Optional[int] = None,
) -> TranscriptAnalysis:
    """
    Get the most relevant parts of a transcript by processing it in chunks to handle long inputs.
    """
    logger.info(
        "Starting AI analysis of transcript (%s chars), include_broll=%s, chunk_size=%s, "
        "language=%s, has_hotwords=%s, has_theme=%s, target_clip_count=%s, max_output_segments=%s",
        len(transcript),
        include_broll,
        chunk_size,
        language,
        bool((professional_hotwords or "").strip()),
        bool((clip_theme or "").strip()),
        target_clip_count,
        max_output_segments,
    )

    # Chunking strategy to handle long transcripts
    max_chunk_size = chunk_size  # Use the provided chunk_size
    transcript_chunks = []
    current_chunk = ""
    for line in transcript.splitlines():
        if len(current_chunk) + len(line) + 1 > max_chunk_size:
            if current_chunk:
                transcript_chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += "\n" + line
    if current_chunk:
        transcript_chunks.append(current_chunk)

    num_chunks = len(transcript_chunks)
    logger.info(f"Split transcript into {num_chunks} chunks for analysis.")

    all_segments = []
    all_summaries = []
    all_key_topics = set()
    all_broll_opps = []

    try:
        agent = get_transcript_agent()

        for i, chunk in enumerate(transcript_chunks):
            logger.info(f"Analyzing chunk {i + 1}/{num_chunks}...")
            analysis = None
            try:
                user_prompt = build_transcript_analysis_prompt(
                    transcript=chunk,
                    include_broll=include_broll,
                    language=language,
                    professional_hotwords=professional_hotwords,
                    clip_theme=clip_theme,
                    target_clip_count=target_clip_count,
                    chunk_index=i,
                    total_chunks=num_chunks,
                )
                result = await agent.run(user_prompt)

                if hasattr(result, "output"):
                    out = result.output
                    if isinstance(out, LeanTranscriptAnalysis):
                        analysis = lean_transcript_analysis_to_full(out)
                    elif isinstance(out, TranscriptAnalysis):
                        analysis = out
                    elif isinstance(out, str):
                        parsed = _parse_json_payload_from_llm_text(out)
                        analysis = _transcript_analysis_from_parsed_json(parsed)
                        if analysis is None:
                            snippet = (out or "")[:4000]
                            logger.warning(
                                "Could not parse JSON segments from AI output for chunk %s. "
                                "First ~4k chars of raw model text: %r",
                                i + 1,
                                snippet,
                            )
                            try:
                                result_fix = await agent.run(
                                    _JSON_RETRY_PREFIX + user_prompt
                                )
                                out_fix = getattr(result_fix, "output", None)
                                if isinstance(out_fix, LeanTranscriptAnalysis):
                                    analysis = lean_transcript_analysis_to_full(out_fix)
                                elif isinstance(out_fix, str):
                                    p2 = _parse_json_payload_from_llm_text(out_fix)
                                    analysis = _transcript_analysis_from_parsed_json(p2)
                                if analysis is not None:
                                    logger.info(
                                        "Chunk %s: recovered segments after JSON-only retry",
                                        i + 1,
                                    )
                            except Exception as retry_exc:
                                logger.warning(
                                    "JSON-only retry failed for chunk %s: %s",
                                    i + 1,
                                    retry_exc,
                                )
                    else:
                        logger.warning(
                            "AI result for chunk %s is unexpected type: %s",
                            i + 1,
                            type(out),
                        )
                else:
                    logger.warning(
                        "AI result for chunk %s has no output attribute",
                        i + 1,
                    )

            except Exception as e:
                logger.error(f"Error analyzing chunk {i + 1} with pydantic-ai: {e}", exc_info=True)
                if 'result' in locals() and hasattr(result, 'output'):
                    logger.error(f"Raw AI output for failed chunk {i+1}: {result.output}")
                continue

            if not isinstance(analysis, TranscriptAnalysis):
                 logger.warning(f"Chunk {i+1} analysis result is not a valid TranscriptAnalysis object. Skipping.")
                 continue
            
            all_segments.extend(analysis.most_relevant_segments)
            if analysis.summary:
                all_summaries.append(analysis.summary)
            if analysis.key_topics:
                all_key_topics.update(analysis.key_topics)
            if include_broll and analysis.broll_opportunities:
                all_broll_opps.extend(analysis.broll_opportunities)

        # Combine results from all chunks
        final_summary = " ".join(all_summaries)
        final_key_topics = sorted(list(all_key_topics))

        logger.info(
            f"AI analysis found a total of {len(all_segments)} segments across all chunks."
        )

        # Validation logic remains the same, applied to the combined list of segments
        validated_segments = []
        for segment in all_segments:
            # (Validation logic from the original function is preserved here)
            if not segment.text.strip() or len(segment.text.split()) < 3:
                continue
            if segment.start_time == segment.end_time:
                continue
            try:
                start_parts = segment.start_time.split(":")
                end_parts = segment.end_time.split(":")
                start_seconds = int(start_parts[0]) * 60 + int(start_parts[1])
                end_seconds = int(end_parts[0]) * 60 + int(end_parts[1])
                duration = end_seconds - start_seconds
                # Reject fragments that are too short to plausibly include setup + payoff (prompts ask for context).
                if duration <= 0 or duration < 12:
                    continue
                if segment.virality:
                    calculated_total = (
                        segment.virality.hook_score
                        + segment.virality.engagement_score
                        + segment.virality.value_score
                        + segment.virality.shareability_score
                    )
                    if segment.virality.total_score != calculated_total:
                        segment.virality.total_score = calculated_total
                validated_segments.append(segment)
            except (ValueError, IndexError):
                continue

        validated_segments.sort(
            key=lambda x: (
                x.virality.total_score if x.virality else 0,
                x.relevance_score,
            ),
            reverse=True,
        )

        if max_output_segments is not None:
            cap = max(1, min(int(max_output_segments), config.max_clips))
            validated_segments = validated_segments[:cap]

        final_analysis = TranscriptAnalysis(
            most_relevant_segments=validated_segments,
            summary=final_summary,
            key_topics=final_key_topics,
            broll_opportunities=all_broll_opps if include_broll else None,
        )

        logger.info(f"Selected {len(validated_segments)} segments for processing")
        if validated_segments:
            top = validated_segments[0]
            logger.info(
                f"Top segment - relevance: {top.relevance_score:.2f}, virality: {top.virality.total_score if top.virality else 'N/A'}"
            )

        return final_analysis

    except Exception as e:
        logger.error(f"Error in transcript analysis: {e}", exc_info=True)
        raise RuntimeError(f"Transcript analysis failed: {str(e)}") from e


def get_most_relevant_parts_sync(transcript: str) -> TranscriptAnalysis:
    """Synchronous wrapper for the async function."""
    return asyncio.run(get_most_relevant_parts_by_transcript(transcript))
