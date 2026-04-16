from src.ai import build_transcript_analysis_prompt, transcript_analysis_system_prompt


def test_system_prompt_enforces_grounding_rules():
    assert "Use only provided transcript lines and timestamps" in (
        transcript_analysis_system_prompt
    )
    assert "Do not invent facts" in transcript_analysis_system_prompt
    assert "DOMAIN GLOSSARY" in transcript_analysis_system_prompt
    assert "ASR mis-hearings" in transcript_analysis_system_prompt


def test_build_transcript_analysis_prompt_requires_transcript_fidelity():
    prompt = build_transcript_analysis_prompt(
        transcript="[00:12 - 00:21] A strong opening line"
    )

    assert "Do not fabricate or embellish content." in prompt
    assert "Do not merge separate non-contiguous moments into one segment." in prompt
    assert "If there is a tradeoff between \"viral\" and \"accurate\", choose accuracy." in prompt
    assert "Do not reject or penalize a segment simply because of the subject matter" in prompt
    assert "[00:12 - 00:21] A strong opening line" in prompt


def test_build_transcript_analysis_prompt_includes_glossary_when_hotwords_set():
    prompt = build_transcript_analysis_prompt(
        transcript="[00:00 - 00:10] Kubernettes is great",
        professional_hotwords="Kubernetes\nDocker",
    )
    assert "DOMAIN GLOSSARY" in prompt
    assert "Kubernetes" in prompt
    assert "Docker" in prompt


def test_build_transcript_analysis_prompt_includes_theme_and_count_when_set():
    prompt = build_transcript_analysis_prompt(
        transcript="[00:00 - 00:10] Hello world",
        clip_theme="pricing strategy",
        target_clip_count=5,
        chunk_index=0,
        total_chunks=2,
    )
    assert "CLIP THEME" in prompt
    assert "pricing strategy" in prompt
    assert "USER TARGET FOR THE FULL VIDEO" in prompt
    assert "about 5 clips" in prompt


def test_build_transcript_analysis_prompt_mentions_broll_only_when_enabled():
    without_broll = build_transcript_analysis_prompt(
        transcript="[00:12 - 00:21] A strong opening line"
    )
    with_broll = build_transcript_analysis_prompt(
        transcript="[00:12 - 00:21] A strong opening line",
        include_broll=True,
    )

    assert "B-roll opportunities" not in without_broll
    assert "B-roll opportunities" in with_broll
