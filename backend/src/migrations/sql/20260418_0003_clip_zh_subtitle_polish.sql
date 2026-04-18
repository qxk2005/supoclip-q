-- Per-task: VideoLingo-style CJK line packing + optional line-level LLM polish before burn-in.
ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS clip_zh_subtitle_polish BOOLEAN NOT NULL DEFAULT TRUE;
