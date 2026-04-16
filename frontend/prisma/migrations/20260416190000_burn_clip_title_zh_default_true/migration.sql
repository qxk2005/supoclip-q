-- Align with backend/migrations/012_burn_clip_title_zh_default_true.sql
ALTER TABLE "tasks" ALTER COLUMN "burn_clip_title_zh" SET DEFAULT true;
