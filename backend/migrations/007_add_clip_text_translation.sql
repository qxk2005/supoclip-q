-- Optional Simplified Chinese translation for English (or other) clip transcripts
ALTER TABLE generated_clips
    ADD COLUMN IF NOT EXISTS text_translation TEXT;
