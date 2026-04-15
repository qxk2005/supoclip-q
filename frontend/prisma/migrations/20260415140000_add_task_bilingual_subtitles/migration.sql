-- Bilingual subtitle mode (backend reads this column; Prisma schema sync)
ALTER TABLE "tasks" ADD COLUMN IF NOT EXISTS "bilingual_subtitles_mode" VARCHAR(10) NOT NULL DEFAULT 'auto';
