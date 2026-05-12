-- FILE: src/db/migrations/002_image_quality_flag.sql
ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS image_quality_flag TEXT DEFAULT 'ok';
ALTER TABLE raw_items ADD COLUMN IF NOT EXISTS vision_analysis_json TEXT DEFAULT NULL;
ALTER TABLE story_clusters ADD COLUMN IF NOT EXISTS pipeline_stage TEXT DEFAULT 'grouped';
ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS pipeline_stage TEXT DEFAULT 'draft';
ALTER TABLE draft_articles ADD COLUMN IF NOT EXISTS vision_analysis_json TEXT DEFAULT NULL;
