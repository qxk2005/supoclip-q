-- Create generated_clips for deployments that only ran Prisma migrations (no full init.sql).
-- Safe to re-run: uses IF NOT EXISTS / OR REPLACE where applicable.
-- FK: tasks.id is TEXT in current Prisma schema.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS generated_clips (
    id VARCHAR(36) PRIMARY KEY DEFAULT (uuid_generate_v4()::text),
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    start_time VARCHAR(20) NOT NULL,
    end_time VARCHAR(20) NOT NULL,
    duration DOUBLE PRECISION NOT NULL,
    text TEXT,
    text_translation TEXT,
    relevance_score DOUBLE PRECISION NOT NULL,
    reasoning TEXT,
    clip_order INTEGER NOT NULL,
    virality_score INTEGER DEFAULT 0,
    hook_score INTEGER DEFAULT 0,
    engagement_score INTEGER DEFAULT 0,
    value_score INTEGER DEFAULT 0,
    shareability_score INTEGER DEFAULT 0,
    hook_type VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_generated_clips_task_id ON generated_clips(task_id);
CREATE INDEX IF NOT EXISTS idx_generated_clips_clip_order ON generated_clips(clip_order);
CREATE INDEX IF NOT EXISTS idx_generated_clips_created_at ON generated_clips(created_at);

DROP TRIGGER IF EXISTS update_generated_clips_updated_at ON generated_clips;
CREATE TRIGGER update_generated_clips_updated_at
    BEFORE UPDATE ON generated_clips
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();
