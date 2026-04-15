-- Optional per-task glossary for speech recognition + segment text correction
ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS professional_hotwords TEXT;
