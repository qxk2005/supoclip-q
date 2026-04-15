-- Align `tasks` with backend + Prisma: Prisma-only or partial DBs may miss these columns.
-- Without them, full INSERT fails → minimal INSERT → extended UPDATE fails → audio/template never persist.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS caption_template VARCHAR(50) DEFAULT 'default';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS include_broll BOOLEAN DEFAULT false;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS chunk_size INTEGER DEFAULT 15000;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'auto';
