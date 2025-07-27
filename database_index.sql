-- Database indexes for improved task processing performance

-- Index for status filtering and ordering by creation date
CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at);

-- Index for task ID lookups (already exists implicitly as primary key, but adding for completeness)
CREATE INDEX IF NOT EXISTS idx_tasks_id ON tasks(id);

-- Index for webhook_url to speed up webhook filtering
CREATE INDEX IF NOT EXISTS idx_tasks_webhook_url ON tasks(webhook_url) WHERE webhook_url IS NOT NULL;

-- Index for video_url to speed up duplicate detection
CREATE INDEX IF NOT EXISTS idx_tasks_video_url ON tasks(video_url);

-- Index for updated_at to help with cleanup and maintenance queries
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);

-- Index for result as JSONB if your database supports it (PostgreSQL specific)
-- This helps with JSON field searches if your database supports JSONB
-- Uncomment if using PostgreSQL 9.4+
-- CREATE INDEX IF NOT EXISTS idx_tasks_result ON tasks USING GIN (result);

-- Add composite index for status and updated_at for maintenance queries
CREATE INDEX IF NOT EXISTS idx_tasks_status_updated_at ON tasks(status, updated_at);
