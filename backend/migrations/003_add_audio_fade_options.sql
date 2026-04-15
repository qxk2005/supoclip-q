-- Migration: Add audio fade options to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS audio_fade_in BOOLEAN DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS audio_fade_out BOOLEAN DEFAULT false;
