-- Run as table owner / superuser (e.g. psql -d supoclip -f ...).
-- Fixes: missing text_translation column, missing indexes/trigger, no privileges for app role supoclip.

BEGIN;

ALTER TABLE public.generated_clips
    ADD COLUMN IF NOT EXISTS text_translation TEXT;

CREATE INDEX IF NOT EXISTS idx_generated_clips_task_id ON public.generated_clips(task_id);
CREATE INDEX IF NOT EXISTS idx_generated_clips_clip_order ON public.generated_clips(clip_order);
CREATE INDEX IF NOT EXISTS idx_generated_clips_created_at ON public.generated_clips(created_at);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_generated_clips_updated_at ON public.generated_clips;
CREATE TRIGGER update_generated_clips_updated_at
    BEFORE UPDATE ON public.generated_clips
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

GRANT ALL PRIVILEGES ON TABLE public.generated_clips TO supoclip;

COMMIT;
