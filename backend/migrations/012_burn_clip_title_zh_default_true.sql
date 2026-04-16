-- New tasks default to burning zh golden quote on clips; existing rows unchanged.
ALTER TABLE public.tasks
  ALTER COLUMN burn_clip_title_zh SET DEFAULT true;

COMMENT ON COLUMN public.tasks.burn_clip_title_zh IS 'When true, render large zh headline on each clip video (default: on)';
