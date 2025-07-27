# Quick Start Guide

## 🚀 Get Started in 5 Minutes

### 1. Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with your credentials
nano .env
```

**Required Configuration:**

```bash
# Supabase Configuration
# Important: Use the API URL from Project Settings > API, not the dashboard URL
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_BUCKET_NAME=processed-videos

# Webshare.io Proxy Configuration
WEBSHARE_USERNAME=your-webshare-username
WEBSHARE_PASSWORD=your-webshare-password
USE_PROXY_FOR_INFO_EXTRACTION=true

# Download Optimization Settings
USE_ARIA2C=true                         # Enable aria2c external downloader
ARIA2C_ARGS="--max-connection-per-server=8 --split=8 --min-split-size=1M"
CONCURRENT_FRAGMENTS=8                  # For yt-dlp internal downloader
HTTP_CHUNK_SIZE=52428800               # 50MB chunks (default)
```

### 2. Set Up Supabase Storage

Create the storage bucket in your Supabase SQL Editor:

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

### 3. Start the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies (if not already done)
pip install -r requirements.txt

# Start the application
python src/main.py
```

### 4. Test the Application

```bash
# Run the test script
python test_proxy_integration.py
```

### 5. Process Your First Video

```bash
# Process a video
curl -X POST http://localhost:5000/api/videos/process \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  }'
```

## 🔧 Key Features

### ✅ Proxy Integration
- **Webshare.io residential proxies** for bot detection bypass
- **Smart usage**: Proxy only for info extraction, not for downloads
- **Bandwidth optimization**: Direct downloads without proxy

### ✅ Supabase Storage
- **Direct upload** to `processed-videos` bucket
- **Organized structure**: `videos/{processing-id}/filename`
- **Public URLs** for easy access

### ✅ Enhanced Logging
- **Request tracking** with unique IDs
- **Detailed error messages** with stack traces
- **Comprehensive monitoring** of all operations

### ✅ Optimized Download System
- **aria2c integration** for faster multi-connection downloads
- **Adaptive fallback** to optimized yt-dlp when aria2c unavailable
- **Configurable parameters** via environment variables

### ✅ Flexible Configuration
- **Environment-based** configuration
- **Easy provider switching** (Supabase, S3, GCS)
- **Validation and error reporting**

## 📋 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/videos/process` | POST | Download and upload video |
| `/api/videos/info` | POST | Get video info (with proxy) |
| `/api/videos/{id}` | GET | Get video details |
| `/api/videos/{id}` | DELETE | Delete video |
| `/api/videos` | GET | List all videos |
| `/api/health` | GET | Health check |

## 🔍 Troubleshooting

### Common Issues

1. **Proxy Authentication Failed**
   - Check Webshare.io credentials
   - Verify account status and bandwidth

2. **Supabase Upload Failed**
   - Verify service role key permissions
   - Check bucket exists and policies are set

3. **Video Download Failed**
   - Check if URL is supported
   - Verify internet connectivity

### Debug Mode

Enable debug logging:

```bash
# In .env file
LOG_LEVEL=DEBUG
FLASK_DEBUG=True
```

## 📁 File Structure

```
video_processor/
├── src/
│   ├── storage/           # Storage abstraction layer
│   ├── routes/            # API endpoints
│   ├── video_downloader.py # Video download with proxy
│   ├── config.py          # Configuration management
│   └── main.py           # Flask application
├── .env.example          # Environment template
├── requirements.txt      # Python dependencies
├── test_proxy_integration.py # Test script
└── README.md            # Full documentation
```

## 🎯 Next Steps

1. **Production Deployment**: See `DEPLOYMENT.md` for deployment options
2. **Custom Storage**: Add new storage providers using the abstraction layer
3. **Monitoring**: Set up logging and monitoring for production use
4. **Scaling**: Consider load balancing and horizontal scaling

## 📞 Support

- Check logs for detailed error information
- Use request IDs to track specific requests
- Review configuration validation on startup
- Test with the included test script

---

**Ready to process videos with proxy support and direct Supabase upload!** 🎬
