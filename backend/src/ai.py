"""
AI-related functions for transcript analysis with enhanced precision and virality scoring.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
import asyncio
import logging
import re

from pydantic_ai import Agent
from pydantic import BaseModel, Field, ValidationError, ValidationError

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
    virality_reasoning: str = Field(description="Explanation of the virality score")


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
    relevance_score: float = Field(
        description="Relevance score from 0.0 to 1.0", ge=0.0, le=1.0
    )
    reasoning: str = Field(
        description=(
            "Brief factual explanation of why this exact segment works as a clip. "
            "Base it only on the provided transcript content."
        )
    )
    virality: ViralityAnalysis = Field(description="Detailed virality score breakdown")


class BRollOpportunity(BaseModel):
    """Identifies an opportunity to insert B-roll footage."""

    timestamp: str = Field(description="When to insert B-roll (MM:SS format)")
    duration: float = Field(
        description="How long to show B-roll (2-5 seconds)", ge=2.0, le=5.0
    )
    search_term: str = Field(description="Keyword to search for B-roll footage")
    context: str = Field(description="What's being discussed at this point")


class TranscriptAnalysis(BaseModel):
    """Analysis result for transcript segments with virality and B-roll opportunities."""

    most_relevant_segments: List[TranscriptSegment]
    summary: str = Field(description="Brief summary of the video content")
    key_topics: List[str] = Field(description="List of main topics discussed")
    broll_opportunities: Optional[List[BRollOpportunity]] = Field(
        default=None, description="Opportunities to insert B-roll footage"
    )


# Enhanced system prompt with virality scoring and B-roll detection
transcript_analysis_system_prompt = """You are an expert transcript analyst for short-form video editing.

Your job is to identify and extract the best clip candidates from the provided transcript. Focus on moments that are engaging, informative, or entertaining.

CORE OBJECTIVES:
1.  Identify segments that would be compelling on social media.
2.  Focus on complete thoughts, insights, or entertaining moments.
3.  Prioritize content with strong hooks, emotional moments, or valuable information.
4.  Score each segment's viral potential.

GROUNDING RULES:
1.  Use only the provided transcript lines and timestamps.
2.  Do not invent facts, tone, or context.
3.  Each segment must correspond to a contiguous block of text in the transcript.
4.  The text of the segment must closely match the transcript.

SEGMENT SELECTION CRITERIA:
1.  STRONG HOOKS: Attention-grabbing opening lines.
2.  VALUABLE CONTENT: Tips, insights, interesting facts, stories.
3.  EMOTIONAL MOMENTS: Excitement, surprise, humor, inspiration.
4.  COMPLETE THOUGHTS: Self-contained ideas that make sense on their own.
5.  ENTERTAINING: Content that people would want to share.

VIRALITY SCORING (0-100 total, from four 0-25 subscores):
For each segment, provide a detailed virality breakdown:

1.  HOOK STRENGTH (0-25): How well does it grab attention?
2.  ENGAGEMENT (0-25): Is it entertaining or emotionally resonant?
3.  VALUE (0-25): Is it educational or informative?
4.  SHAREABILITY (0-25): Would someone be compelled to share it?

TIMING GUIDELINES:
-   Segments should ideally be between 10-60 seconds.
-   Focus on natural content boundaries.
-   Ensure there's enough context for the segment to be understandable.

Find all compelling segments that would work well as standalone clips. Quality over quantity.
"""

# Lazy-loaded agent to avoid import-time failures when API keys aren't set
_transcript_agent: Optional[Agent[None, TranscriptAnalysis]] = None


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


def get_transcript_agent() -> Agent[None, TranscriptAnalysis]:
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

        _transcript_agent = Agent[None, TranscriptAnalysis](**agent_args)
    return _transcript_agent


def build_transcript_analysis_prompt(
    transcript: str, include_broll: bool = False, language: str = "en"
) -> str:
    """Build the grounded task prompt for transcript analysis."""
    broll_instruction = ""
    if include_broll:
        broll_instruction = (
            "\n5. Also identify B-roll opportunities for each chosen segment where stock footage could enhance the visual appeal."
        )

    lang_instruction = "The transcript is in English."
    if language == "zh":
        lang_instruction = "The transcript is in Chinese (zh-CN)."
    elif language and language != "en":
        lang_instruction = f"The transcript is in the language: {language}."

    return f"""Analyze this video transcript and identify the most engaging segments for short-form content.

{lang_instruction}

The transcript is formatted as one line per timestamped span, for example:
[00:12 - 00:21] Spoken text here
[00:21 - 00:35] More spoken text here

Follow this workflow:
1. Read the transcript as a sequence of timestamped spans.
2. Select only contiguous ranges that already exist in the transcript.
3. Prefer moments with a strong hook, clear payoff, emotional charge, or concrete value.
4. For each chosen segment, use the earliest timestamp in the selected range as start_time and the latest timestamp in the selected range as end_time.{broll_instruction}

Critical accuracy requirements:
- Do not fabricate or embellish content.
- Do not use timestamps that are not present in the transcript.
- Do not merge separate non-contiguous moments into one segment.
- segment.text must reflect only the spoken content inside the selected time range.
- If a span lacks enough context to stand alone, expand to nearby contiguous lines rather than guessing.
- If there is a tradeoff between "viral" and "accurate", choose accuracy.
- Do not reject or penalize a segment simply because of the subject matter; stay content-neutral and assess clip quality only.

Transcript:
{transcript}"""


async def get_most_relevant_parts_by_transcript(
    transcript: str,
    include_broll: bool = False,
    chunk_size: int = 15000,
    language: str = "en",
) -> TranscriptAnalysis:
    """
    Get the most relevant parts of a transcript by processing it in chunks to handle long inputs.
    """
    logger.info(
        f"Starting AI analysis of transcript ({len(transcript)} chars), include_broll={include_broll}, chunk_size={chunk_size}, language={language}"
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

    logger.info(f"Split transcript into {len(transcript_chunks)} chunks for analysis.")

    all_segments = []
    all_summaries = []
    all_key_topics = set()
    all_broll_opps = []

    try:
        agent = get_transcript_agent()

        for i, chunk in enumerate(transcript_chunks):
            logger.info(f"Analyzing chunk {i + 1}/{len(transcript_chunks)}...")
            analysis = None
            try:
                result = await agent.run(
                    build_transcript_analysis_prompt(
                        transcript=chunk, include_broll=include_broll, language=language
                    )
                )
                
                if hasattr(result, 'output') and isinstance(result.output, str):
                    output_str = result.output
                    
                    # --- Final, Simplified JSON Extraction ---
                    think_end_pos = output_str.rfind('</think>')
                    search_start_pos = think_end_pos + len('</think>') if think_end_pos != -1 else 0
                    
                    json_start_pos = -1
                    first_bracket = output_str.find('[', search_start_pos)
                    if first_bracket != -1:
                        json_start_pos = first_bracket
                        
                    if json_start_pos != -1:
                        # The AI returns a list of segments, but our model expects an object.
                        # We need to wrap the list in an object.
                        json_str = output_str[json_start_pos:].strip()
                        segments_list = json.loads(json_str)

                        # --- Data Transformation Step ---
                        adapted_segments = []
                        for segment in segments_list:
                            virality_breakdown = segment.get("virality_breakdown", {})
                            adapted_segment = {
                                "start_time": segment.get("start_time"),
                                "end_time": segment.get("end_time"),
                                "text": segment.get("text"),
                                "relevance_score": 0.9,  # Provide a default value
                                "reasoning": segment.get("reasoning", "AI generated clip."),
                                "virality": {
                                    "hook_score": int(virality_breakdown.get("hook_strength", 0)),
                                    "engagement_score": int(virality_breakdown.get("engagement", 0)),
                                    "value_score": int(virality_breakdown.get("value", 0)),
                                    "shareability_score": int(virality_breakdown.get("shareability", 0)),
                                    "total_score": int(segment.get("virality_score", 0)),
                                    "hook_type": "none", # Provide a default
                                    "virality_reasoning": segment.get("reasoning", "AI generated clip.")
                                }
                            }
                            adapted_segments.append(adapted_segment)
                        
                        analysis_obj = {
                            "most_relevant_segments": adapted_segments,
                            "summary": "Summary not generated by model.",
                            "key_topics": []
                        }
                        analysis = TranscriptAnalysis.model_validate(analysis_obj)
                    else:
                        logger.warning(f"Could not find JSON array start in AI output for chunk {i+1}")
                else:
                    logger.warning(f"AI result for chunk {i+1} is not in the expected format. Got: {type(result)}")

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
                if duration <= 0 or duration < 5:
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
