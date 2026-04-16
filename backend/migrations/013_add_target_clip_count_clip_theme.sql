-- Optional user-controlled clip count and theme for AI segment selection.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS target_clip_count integer;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS clip_theme text;

COMMENT ON COLUMN tasks.target_clip_count IS 'Desired number of clips; NULL falls back to per-mode defaults.';
COMMENT ON COLUMN tasks.clip_theme IS 'Optional topic/theme to bias segment relevance.';
