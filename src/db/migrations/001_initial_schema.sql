-- FILE: src/db/migrations/001_initial_schema.sql

CREATE TABLE IF NOT EXISTS job_registry (
  run_id TEXT PRIMARY KEY,
  triggered_at TIMESTAMP NOT NULL DEFAULT NOW(),
  trigger_type TEXT NOT NULL DEFAULT 'scheduled',
  status TEXT NOT NULL DEFAULT 'running',
  completed_at TIMESTAMP,
  items_fetched INTEGER DEFAULT 0,
  items_passed_filter INTEGER DEFAULT 0,
  articles_generated INTEGER DEFAULT 0,
  articles_published INTEGER DEFAULT 0,
  error_message TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
  item_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL UNIQUE,
  published_at TIMESTAMP,
  snippet TEXT,
  full_text TEXT,
  language TEXT DEFAULT 'en',
  full_text_available INTEGER DEFAULT 0,
  relevance_score REAL DEFAULT 0.0,
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  FOREIGN KEY (run_id) REFERENCES job_registry(run_id)
);

CREATE TABLE IF NOT EXISTS story_clusters (
  cluster_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  canonical_topic TEXT NOT NULL,
  source_count INTEGER DEFAULT 1,
  low_confidence INTEGER DEFAULT 0,
  item_ids TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  FOREIGN KEY (run_id) REFERENCES job_registry(run_id)
);

CREATE TABLE IF NOT EXISTS extracted_stories (
  story_id TEXT PRIMARY KEY,
  cluster_id TEXT NOT NULL,
  headline_summary TEXT,
  key_facts TEXT,
  entities TEXT,
  event_type TEXT,
  quoted_statements TEXT,
  field_confidences TEXT,
  validation_score REAL DEFAULT 0.0,
  hold_for_review INTEGER DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  FOREIGN KEY (cluster_id) REFERENCES story_clusters(cluster_id)
);

CREATE TABLE IF NOT EXISTS draft_articles (
  article_id TEXT PRIMARY KEY,
  story_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  title TEXT,
  meta_description TEXT,
  slug TEXT UNIQUE,
  body TEXT,
  tags TEXT,
  category TEXT,
  image_prompt TEXT,
  image_url TEXT,
  image_source TEXT,
  alt_text TEXT,
  image_status TEXT DEFAULT 'pending',
  source_urls TEXT,
  approval_status TEXT DEFAULT 'pending',
  approved_by TEXT,
  approved_at TIMESTAMP,
  rejected_by TEXT,
  rejected_reason TEXT,
  edit_count INTEGER DEFAULT 0,
  approval_expires_at TIMESTAMP,
  scheduled_publish_at TIMESTAMP,
  published_url TEXT,
  article_type TEXT,
  parent_story_id TEXT,
  seo_score REAL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  FOREIGN KEY (story_id) REFERENCES extracted_stories(story_id),
  FOREIGN KEY (run_id) REFERENCES job_registry(run_id)
);

CREATE TABLE IF NOT EXISTS published_slugs (
  slug TEXT PRIMARY KEY,
  article_id TEXT NOT NULL,
  published_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_items_run ON raw_items(run_id);
CREATE INDEX IF NOT EXISTS idx_raw_items_status ON raw_items(status);
CREATE INDEX IF NOT EXISTS idx_draft_articles_status ON draft_articles(approval_status);
CREATE INDEX IF NOT EXISTS idx_draft_articles_run ON draft_articles(run_id);
