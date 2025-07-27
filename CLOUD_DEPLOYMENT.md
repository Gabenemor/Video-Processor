# Video Processor Cloud Deployment Guide

This guide explains how to deploy the Video Processor application to Google Cloud Run, with proper database setup.

## System Architecture Overview

The Video Processor consists of two main components that run in the same container:

1. **API Server** - Handles incoming requests, provides endpoints for video processing
2. **Worker Process** - Processes queued tasks from the database

Both components share the same codebase and run in the same container, but as separate processes.

## Key Features

### Direct Streaming Processing
- Downloads videos directly from source to Supabase storage without saving to disk
- Uses streaming buffers and direct piping for memory efficiency
- Falls back to standard processing if streaming fails

### Optimized Video Downloads
- Uses aria2c external downloader when available (installed in Dockerfile)
- Configures multi-connection downloads for faster speeds
- Implements proper timeout handling and retries

### Efficient Database Usage
- Direct database connections with no connection pooling overhead
- Efficient task queue using Postgres SKIP LOCKED pattern
- Task status tracking with proper error handling

## Deployment Steps

### 1. Create a PostgreSQL Database

You can use any PostgreSQL provider, but Cloud SQL is recommended for Google Cloud:

```sql
-- Create the tasks table for task tracking
CREATE TABLE tasks (
    id VARCHAR(255) PRIMARY KEY,
    video_url TEXT NOT NULL,
    webhook_url TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    error_details TEXT,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX idx_tasks_status_created_at ON tasks(status, created_at);
CREATE INDEX idx_tasks_video_url ON tasks(video_url);
CREATE INDEX idx_tasks_status_updated_at ON tasks(status, updated_at);
```

### 2. Set Up Supabase Storage

Create the `processed-videos` bucket in your Supabase project:

```sql
-- Create the processed-videos bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('processed-videos', 'processed-videos', true);

-- Set up access policies
CREATE POLICY "Allow public uploads to processed-videos"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'processed-videos');

CREATE POLICY "Allow public downloads from processed-videos"
ON storage.objects FOR SELECT
USING (bucket_id = 'processed-videos');
```

### 3. Create a Secret for Sensitive Information

```bash
# Create a new secret
gcloud secrets create video-processor-secrets --replication-policy="automatic"

# Add secret values
echo -n "YOUR_DATABASE_URL" | gcloud secrets versions add video-processor-secrets --data-file=-
echo -n "YOUR_SUPABASE_URL" | gcloud secrets versions add video-processor-secrets --data-file=-
echo -n "YOUR_SUPABASE_SERVICE_ROLE_KEY" | gcloud secrets versions add video-processor-secrets --data-file=-
echo -n "YOUR_WEBSHARE_USERNAME" | gcloud secrets versions add video-processor-secrets --data-file=-
echo -n "YOUR_WEBSHARE_PASSWORD" | gcloud secrets versions add video-processor-secrets --data-file=-
```

### 4. Deploy to Cloud Run

1. Update the `cloud-run-config.yaml` file with your project ID:
   ```bash
   sed -i 's/gcr.io\/PROJECT_ID/gcr.io\/your-project-id/g' cloud-run-config.yaml
   ```

2. Build and push the Docker image:
   ```bash
   gcloud builds submit --tag gcr.io/your-project-id/video-processor
   ```

3. Deploy to Cloud Run:
   ```bash
   gcloud run services replace cloud-run-config.yaml
   ```

4. Allow the Cloud Run service to access your secrets:
   ```bash
   gcloud run services add-iam-policy-binding video-processor \
     --member=serviceAccount:your-service-account@your-project-id.iam.gserviceaccount.com \
     --role=roles/secretmanager.secretAccessor
   ```

## Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `USE_DIRECT_PROCESSING` | Enable direct streaming upload | `true` |
| `USE_ARIA2C` | Use aria2c for faster downloads | `true` |
| `VIDEO_QUALITY` | Video quality to download | `best[height<=720]/best` |
| `MAX_FILE_SIZE` | Maximum file size in bytes | `1073741824` (1GB) |
| `INFO_EXTRACTION_TIMEOUT` | Timeout for video info extraction | `300` (5 minutes) |
| `DOWNLOAD_TIMEOUT` | Timeout for video download | `900` (15 minutes) |
| `UPLOAD_TIMEOUT` | Timeout for video upload | `600` (10 minutes) |

## Monitoring and Maintenance

- Check Cloud Run logs for application errors
- Monitor Postgres task table for stuck tasks
- Use the `/api/health` endpoint to check system health

## Scaling Considerations

- The application is designed to scale horizontally
- Each container runs both API and worker processes
- Cloud Run automatically scales based on load
- Set `autoscaling.knative.dev/minScale` to ensure at least one instance is always running
