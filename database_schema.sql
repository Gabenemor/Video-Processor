-- Database schema for Video Processor application

-- Create the tasks table if not exists
CREATE TABLE IF NOT EXISTS tasks (
    id VARCHAR(255) PRIMARY KEY,
    video_url TEXT NOT NULL,
    webhook_url TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    error_details TEXT,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create optimized indexes for the tasks table

-- Index for status filtering and ordering by creation date (for queue processing)
CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at);

-- Index for task ID lookups (already exists implicitly as primary key, but adding for completeness)
CREATE INDEX IF NOT EXISTS idx_tasks_id ON tasks(id);

-- Index for video_url to speed up duplicate detection
CREATE INDEX IF NOT EXISTS idx_tasks_video_url ON tasks(video_url);

-- Index for updated_at to help with cleanup and maintenance queries
CREATE INDEX IF NOT EXISTS idx_tasks_updated_at ON tasks(updated_at);

-- Add composite index for status and updated_at for maintenance queries
CREATE INDEX IF NOT EXISTS idx_tasks_status_updated_at ON tasks(status, updated_at);

-- Add database comments for documentation
COMMENT ON TABLE tasks IS 'Stores video processing tasks with their statuses and results';
COMMENT ON COLUMN tasks.id IS 'Task ID, unique identifier for the task';
COMMENT ON COLUMN tasks.video_url IS 'URL of the video to be processed';
COMMENT ON COLUMN tasks.webhook_url IS 'Optional URL to notify when task is completed';
COMMENT ON COLUMN tasks.status IS 'Task status: queued, processing, completed, or failed';
COMMENT ON COLUMN tasks.error_details IS 'Error details if task failed';
COMMENT ON COLUMN tasks.result IS 'JSON result data with processing information';
COMMENT ON COLUMN tasks.created_at IS 'Timestamp when task was created';
COMMENT ON COLUMN tasks.updated_at IS 'Timestamp when task was last updated';
