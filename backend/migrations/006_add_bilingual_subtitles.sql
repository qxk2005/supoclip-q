-- Bilingual subtitle preference: auto (English-only videos default on), on, off
ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS bilingual_subtitles_mode VARCHAR(10) NOT NULL DEFAULT 'auto';

COMMENT ON COLUMN tasks.bilingual_subtitles_mode IS 'auto | on | off — bilingual CN/EN subtitles for clips';
