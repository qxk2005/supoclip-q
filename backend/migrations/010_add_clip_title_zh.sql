-- Per-clip Chinese headline (AI) + optional burn-in on rendered MP4
ALTER TABLE public.generated_clips
    ADD COLUMN IF NOT EXISTS title_zh character varying(120);

COMMENT ON COLUMN public.generated_clips.title_zh IS 'Simplified Chinese headline for UI and optional on-video title';

ALTER TABLE public.tasks
    ADD COLUMN IF NOT EXISTS burn_clip_title_zh boolean DEFAULT false NOT NULL;

COMMENT ON COLUMN public.tasks.burn_clip_title_zh IS 'When true, render large zh headline on each clip video';
