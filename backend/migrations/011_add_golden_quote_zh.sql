-- AI "golden quote" (max 2 lines) for on-video burn-in
ALTER TABLE public.generated_clips
    ADD COLUMN IF NOT EXISTS golden_quote_zh character varying(200);

COMMENT ON COLUMN public.generated_clips.golden_quote_zh IS 'Simplified Chinese golden quote (<=2 lines) for prominent burn-in';
