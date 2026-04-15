-- Per-task glossary for ASR + segment text (backend reads this column)
ALTER TABLE "tasks" ADD COLUMN IF NOT EXISTS "professional_hotwords" TEXT;
