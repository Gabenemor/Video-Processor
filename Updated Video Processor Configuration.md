# Updated Video Processor Configuration

## Overview

This document provides the complete configuration guide for the updated video processing application with Webshare.io proxy integration and enhanced error logging. The application now supports:

- **Webshare.io Residential Proxies**: For bypassing bot detection during initial link processing
- **Direct Supabase Upload**: Videos are uploaded directly to the `processed-videos` bucket
- **Enhanced Error Logging**: Detailed error tracking with request IDs and full stack traces
- **Flexible Storage Configuration**: Easy switching between storage providers

## Environment Variables

Create a `.env` file in the root directory of your project with the following configuration:

```bash
# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here-make-it-random-and-secure
FLASK_DEBUG=False
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Storage Provider Configuration
STORAGE_PROVIDER=supabase

# Supabase Configuration
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key_here
SUPABASE_BUCKET_NAME=processed-videos

# Webshare.io Proxy Configuration
WEBSHARE_USERNAME=your-webshare-username
WEBSHARE_PASSWORD=your-webshare-password
WEBSHARE_ENDPOINT=rotating-residential.webshare.io:9000
USE_PROXY_FOR_INFO_EXTRACTION=true

# Video Processing Configuration
VIDEO_DOWNLOAD_DIR=/tmp/video_downloads
MAX_FILE_SIZE=1073741824
ALLOWED_FORMATS=mp4,avi,mov,wmv,flv,webm,mkv
VIDEO_QUALITY=best[height<=720]/best

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
LOG_FILE=/var/log/video-processor.log
```

### Required Environment Variables

#### Supabase Configuration
- **SUPABASE_URL**: Your Supabase project URL (found in Project Settings > API)
- **SUPABASE_SERVICE_ROLE_KEY**: Your service role key (found in Project Settings > API)
- **SUPABASE_BUCKET_NAME**: Set to `processed-videos` (this is the bucket where videos will be stored)

#### Webshare.io Configuration
- **WEBSHARE_USERNAME**: Your Webshare.io username
- **WEBSHARE_PASSWORD**: Your Webshare.io password
- **WEBSHARE_ENDPOINT**: The rotating residential proxy endpoint (default: `rotating-residential.webshare.io:9000`)
- **USE_PROXY_FOR_INFO_EXTRACTION**: Set to `true` to enable proxy usage for bot detection bypass

### Optional Environment Variables

#### Flask Configuration
- **FLASK_SECRET_KEY**: Secret key for Flask sessions (generate a random string)
- **FLASK_DEBUG**: Set to `true` for development, `false` for production
- **FLASK_HOST**: Host to bind to (default: `0.0.0.0`)
- **FLASK_PORT**: Port to listen on (default: `5000`)

#### Video Processing
- **VIDEO_DOWNLOAD_DIR**: Temporary directory for downloads (default: `/tmp/video_downloads`)
- **MAX_FILE_SIZE**: Maximum file size in bytes (default: 1GB)
- **ALLOWED_FORMATS**: Comma-separated list of allowed video formats
- **VIDEO_QUALITY**: yt-dlp quality selector (default: `best[height<=720]/best`)

#### Logging
- **LOG_LEVEL**: Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)
- **LOG_FORMAT**: Log message format
- **LOG_FILE**: Path to log file (optional, logs to console if not set)

## Supabase Setup

### 1. Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project
2. Note your project URL and service role key from Project Settings > API

### 2. Create Storage Bucket

Execute the following SQL in your Supabase SQL Editor:

```sql
-- Create the processed-videos bucket
INSERT INTO storage.buckets (id, name, public) 
VALUES ('processed-videos', 'processed-videos', true);

-- Set up RLS policies for the bucket
CREATE POLICY "Allow public uploads to processed-videos" 
ON storage.objects FOR INSERT 
WITH CHECK (bucket_id = 'processed-videos');

CREATE POLICY "Allow public downloads from processed-videos" 
ON storage.objects FOR SELECT 
USING (bucket_id = 'processed-videos');

CREATE POLICY "Allow public deletes from processed-videos" 
ON storage.objects FOR DELETE 
USING (bucket_id = 'processed-videos');
```

### 3. Verify Bucket Configuration

You can verify your bucket is properly configured by checking the Storage section in your Supabase dashboard. The `processed-videos` bucket should be visible and set to public access.

## Webshare.io Setup

### 1. Create Webshare.io Account

1. Go to [webshare.io](https://webshare.io) and create an account
2. Purchase a residential proxy plan
3. Note your username and password from the dashboard

### 2. Proxy Configuration

The application is configured to use rotating residential proxies with the following settings:

- **Endpoint**: `rotating-residential.webshare.io:9000`
- **Protocol**: HTTP with authentication
- **Usage**: Only for initial video info extraction (bot detection bypass)
- **Bandwidth Optimization**: Proxies are NOT used for actual video downloads to save bandwidth

### 3. Proxy Usage Flow

1. **Info Extraction**: When getting video information, the application uses the proxy to bypass bot detection
2. **Video Download**: The actual video download happens without proxy to save bandwidth and improve speed
3. **Upload to Supabase**: Files are uploaded directly to your Supabase bucket

## Application Flow

### 1. Request Processing

```
User Request → Flask App → Video Info Extraction (with proxy) → Video Download (without proxy) → Upload to Supabase → Response
```

### 2. Error Handling

Each request gets a unique request ID for tracking. All errors are logged with:

- Request ID for correlation
- Full error details and stack traces
- URL and processing information
- Timestamp and context

### 3. File Organization

Files are organized in Supabase storage as follows:

```
processed-videos/
├── videos/
│   ├── {processing-id}/
│   │   ├── {video-id}.mp4          # Main video file
│   │   ├── {video-id}.info.json    # Video metadata
│   │   └── {video-id}.jpg          # Thumbnail image
```

## API Endpoints

### POST /api/videos/process

Process a video URL (download and upload to Supabase):

```bash
curl -X POST http://localhost:5000/api/videos/process \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=example",
    "options": {
      "format": "best[height<=720]/best"
    }
  }'
```

### POST /api/videos/info

Get video information without downloading:

```bash
curl -X POST http://localhost:5000/api/videos/info \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=example"
  }'
```

### GET /api/videos/{processing_id}

Get details of a processed video:

```bash
curl http://localhost:5000/api/videos/{processing-id}
```

### DELETE /api/videos/{processing_id}

Delete a processed video:

```bash
curl -X DELETE http://localhost:5000/api/videos/{processing-id}
```

### GET /api/videos

List all processed videos:

```bash
curl http://localhost:5000/api/videos?page=1&limit=10
```

### GET /api/health

Health check:

```bash
curl http://localhost:5000/api/health
```

## Running the Application

### 1. Install Dependencies

```bash
cd video_processor
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your actual credentials
```

### 3. Start the Application

```bash
python src/main.py
```

The application will start on `http://0.0.0.0:5000`

## Error Logging and Monitoring

### Log Levels

- **DEBUG**: Detailed information for debugging
- **INFO**: General information about application flow
- **WARNING**: Warning messages for non-critical issues
- **ERROR**: Error messages with full stack traces

### Request Tracking

Each API request gets a unique 8-character request ID that appears in all related log messages. This makes it easy to trace the complete flow of a request through the system.

### Error Response Format

All error responses include:

```json
{
  "error": "Error description",
  "details": "Detailed error message",
  "request_id": "abc12345",
  "url": "original_url_if_applicable",
  "error_code": "specific_error_code_if_available"
}
```

### Common Error Scenarios

1. **Bot Detection**: If a video platform blocks the request, the proxy will automatically retry
2. **Storage Errors**: Detailed Supabase error messages with provider information
3. **Download Failures**: Specific yt-dlp error messages with URL context
4. **Configuration Issues**: Validation errors with specific missing configuration details

## Troubleshooting

### Proxy Issues

If proxy authentication fails:

1. Verify your Webshare.io credentials
2. Check your account status and remaining bandwidth
3. Test proxy connectivity manually
4. Review proxy configuration in logs

### Storage Issues

If Supabase uploads fail:

1. Verify your service role key has storage permissions
2. Check bucket policies and RLS settings
3. Ensure the `processed-videos` bucket exists
4. Review Supabase project settings

### Video Download Issues

If video downloads fail:

1. Check if the URL is supported by yt-dlp
2. Verify internet connectivity
3. Check for platform-specific restrictions
4. Review video quality settings

### Configuration Validation

The application validates configuration on startup and provides detailed error messages for any missing or invalid settings. Check the startup logs for configuration issues.

## Security Considerations

### Production Deployment

1. **Environment Variables**: Never commit `.env` files to version control
2. **Secret Keys**: Use strong, random secret keys
3. **Proxy Credentials**: Secure your Webshare.io credentials
4. **Supabase Keys**: Use service role keys, not anon keys for server-side operations
5. **HTTPS**: Use HTTPS in production
6. **Rate Limiting**: Consider implementing rate limiting for public APIs

### File Security

1. **Bucket Policies**: Configure appropriate RLS policies for your use case
2. **File Access**: Use signed URLs for private content
3. **Cleanup**: Implement cleanup policies for temporary files
4. **Size Limits**: Configure appropriate file size limits

This configuration provides a robust, scalable video processing system with proxy support for bot detection bypass and comprehensive error logging.

