# Deployment Guide

## Quick Start

### 1. Environment Setup

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Edit `.env` with your storage provider credentials:

```bash
# For Supabase (recommended for getting started)
STORAGE_PROVIDER=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_BUCKET_NAME=videos

# Optional: Customize other settings
VIDEO_DOWNLOAD_DIR=/tmp/video_downloads
VIDEO_QUALITY=best[height<=720]/best
LOG_LEVEL=INFO
```

### 2. Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Install additional dependencies if needed
pip install -r requirements.txt
```

### 3. Start the Application

```bash
python src/main.py
```

The application will start on `http://localhost:5000`

### 4. Test the API

```bash
# Health check
curl http://localhost:5000/api/health

# Get configuration
curl http://localhost:5000/api/config

# Get supported sites
curl http://localhost:5000/api/supported-sites
```

## Supabase Setup

### 1. Create Supabase Project

1. Go to [supabase.com](https://supabase.com)
2. Create a new project
3. Note your project URL and service role key

### 2. Create Storage Bucket

```sql
-- Create the videos bucket
INSERT INTO storage.buckets (id, name, public) 
VALUES ('videos', 'videos', false);

-- Set up RLS policies (adjust as needed)
CREATE POLICY "Allow authenticated uploads" ON storage.objects
FOR INSERT WITH CHECK (bucket_id = 'videos' AND auth.role() = 'authenticated');

CREATE POLICY "Allow authenticated downloads" ON storage.objects
FOR SELECT USING (bucket_id = 'videos' AND auth.role() = 'authenticated');
```

### 3. Configure Environment

```bash
STORAGE_PROVIDER=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_BUCKET_NAME=videos
```

## Production Deployment

### Using Docker (Recommended)

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY .env .env

# Create download directory
RUN mkdir -p /tmp/video_downloads

EXPOSE 5000

CMD ["python", "src/main.py"]
```

Build and run:

```bash
docker build -t video-processor .
docker run -p 5000:5000 --env-file .env video-processor
```

### Using Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  video-processor:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_HOST=0.0.0.0
      - FLASK_PORT=5000
    env_file:
      - .env
    volumes:
      - ./downloads:/tmp/video_downloads
    restart: unless-stopped
```

Run with:

```bash
docker-compose up -d
```

### Cloud Deployment

#### Heroku

1. Create `Procfile`:
```
web: python src/main.py
```

2. Configure environment variables in Heroku dashboard

3. Deploy:
```bash
git add .
git commit -m "Deploy video processor"
git push heroku main
```

#### Railway

1. Connect your GitHub repository
2. Configure environment variables
3. Deploy automatically on push

#### DigitalOcean App Platform

1. Create app from GitHub repository
2. Configure environment variables
3. Set build command: `pip install -r requirements.txt`
4. Set run command: `python src/main.py`

## API Usage Examples

### Process a Video

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

### Get Video Information

```bash
curl -X POST http://localhost:5000/api/videos/info \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=example"
  }'
```

### List Processed Videos

```bash
curl http://localhost:5000/api/videos?page=1&limit=10
```

### Get Video Details

```bash
curl http://localhost:5000/api/videos/{processing_id}
```

### Delete Video

```bash
curl -X DELETE http://localhost:5000/api/videos/{processing_id}
```

## Monitoring and Logging

### Health Monitoring

Set up health checks:

```bash
# Simple health check
curl http://localhost:5000/api/health

# Detailed configuration check
curl http://localhost:5000/api/config
```

### Log Configuration

Configure logging in `.env`:

```bash
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - %(message)s
LOG_FILE=/var/log/video-processor.log
```

### Metrics and Monitoring

For production deployments, consider:

- Application Performance Monitoring (APM) tools
- Log aggregation services
- Health check endpoints for load balancers
- Resource usage monitoring

## Troubleshooting

### Common Issues

1. **Storage Authentication Errors**
   - Verify credentials in `.env`
   - Check bucket permissions
   - Ensure service role has storage access

2. **Video Download Failures**
   - Check internet connectivity
   - Verify URL is supported
   - Check for platform-specific restrictions

3. **Permission Errors**
   - Ensure download directory is writable
   - Check file system permissions
   - Verify storage bucket policies

4. **Memory/Disk Issues**
   - Monitor disk space in download directory
   - Implement cleanup policies
   - Consider streaming uploads for large files

### Debug Mode

Enable debug mode for development:

```bash
FLASK_DEBUG=True
LOG_LEVEL=DEBUG
```

### Configuration Validation

Check configuration issues:

```bash
curl http://localhost:5000/api/config
```

Look for `validation_errors` in the response.

## Security Considerations

### Production Security

1. **Environment Variables**
   - Never commit `.env` files
   - Use secure secret management
   - Rotate credentials regularly

2. **Network Security**
   - Use HTTPS in production
   - Implement rate limiting
   - Consider API authentication

3. **Storage Security**
   - Use signed URLs for file access
   - Implement proper bucket policies
   - Monitor access logs

4. **Input Validation**
   - Validate all URLs
   - Sanitize file names
   - Implement size limits

### Rate Limiting

Consider implementing rate limiting:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["100 per hour"]
)

@app.route('/api/videos/process')
@limiter.limit("10 per minute")
def process_video():
    # ... existing code
```

## Scaling Considerations

### Horizontal Scaling

- Use load balancers
- Implement session affinity if needed
- Consider message queues for async processing

### Performance Optimization

- Implement caching for metadata
- Use CDN for file delivery
- Optimize video quality settings
- Consider parallel processing

### Resource Management

- Monitor CPU and memory usage
- Implement disk cleanup policies
- Use cloud storage for scalability
- Consider auto-scaling groups

