-- Align with backend/migrations/010_add_clip_title_zh.sql
ALTER TABLE "tasks" ADD COLUMN IF NOT EXISTS "burn_clip_title_zh" BOOLEAN NOT NULL DEFAULT false;
