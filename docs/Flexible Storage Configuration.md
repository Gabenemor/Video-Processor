# Flexible Storage Configuration

This application is designed with a flexible storage backend, allowing you to easily switch between different cloud storage providers like Supabase, AWS S3, or Google Cloud Storage. This is achieved through a combination of a **Storage Abstraction Layer** and a **Configuration Management System**.

## 1. Storage Abstraction Layer (`src/storage/base.py` and `src/storage/factory.py`)

The core of the flexible storage is the `BaseStorage` abstract class defined in `src/storage/base.py`. This class defines a common interface that all storage providers must implement. This ensures that the rest of the application interacts with storage in a consistent way, regardless of the underlying technology.

```python
# src/storage/base.py (excerpt)

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

class BaseStorage(ABC):
    """Abstract base class for storage providers."""
    
    @abstractmethod
    async def upload_file(self, file_path: str, destination_key: str, 
                         metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def download_file(self, source_key: str, local_path: str) -> bool:
        pass
    
    @abstractmethod
    async def delete_file(self, file_key: str) -> bool:
        pass
    
    @abstractmethod
    async def get_file_url(self, file_key: str, expires_in: int = 3600) -> str:
        pass
    
    @abstractmethod
    async def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def file_exists(self, file_key: str) -> bool:
        pass
```

Each specific storage provider (e.g., Supabase) then implements this `BaseStorage` interface. For example, the Supabase implementation is in `src/storage/supabase_storage.py`.

To manage these different implementations, a `StorageFactory` (defined in `src/storage/factory.py`) is used. This factory is responsible for creating the correct storage provider instance based on the configuration. It maintains a registry of available storage providers.

```python
# src/storage/factory.py (excerpt)

from typing import Dict, Any, Type
from .base import BaseStorage, StorageError
from .supabase_storage import SupabaseStorage

class StorageFactory:
    """Factory class for creating storage provider instances."""
    
    _providers: Dict[str, Type[BaseStorage]] = {
        'supabase': SupabaseStorage,
    }
    
    @classmethod
    def create_storage(cls, provider: str, config: Dict[str, Any]) -> BaseStorage:
        # ... (logic to create provider instance)
        pass
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseStorage]) -> None:
        # ... (logic to register new provider)
        pass
```

This design means that if you want to add a new storage provider (e.g., Google Cloud Storage), you only need to:
1. Create a new Python class that inherits from `BaseStorage` and implements all its abstract methods.
2. Register this new class with the `StorageFactory`.

The rest of the application code that uses the `BaseStorage` interface will continue to work without modification.

## 2. Configuration Management System (`src/config.py` and `.env.example`)

The application uses a centralized configuration system to manage settings, including the choice of storage provider and its credentials. This system loads configurations from environment variables (via a `.env` file) and can also load from a JSON configuration file.

### `src/config.py`
This file defines the `Config` class, which is responsible for loading, validating, and providing access to all application settings. It reads environment variables and constructs a comprehensive configuration dictionary.

```python
# src/config.py (excerpt)

import os
from dotenv import load_dotenv

load_dotenv() # Loads environment variables from .env file

class Config:
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        config = {
            # ... other configurations ...
            'storage': {
                'provider': os.getenv('STORAGE_PROVIDER', 'supabase'),
                'config': self._get_storage_config()
            },
            # ...
        }
        return config

    def _get_storage_config(self) -> Dict[str, Any]:
        provider = os.getenv('STORAGE_PROVIDER', 'supabase')
        
        if provider == 'supabase':
            return {
                'url': os.getenv('SUPABASE_URL'),
                'key': os.getenv('SUPABASE_SERVICE_ROLE_KEY'),
                'bucket_name': os.getenv('SUPABASE_BUCKET_NAME', 'videos'),
            }
        elif provider == 's3':
            return {
                'access_key': os.getenv('AWS_ACCESS_KEY_ID'),
                'secret_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
                'bucket_name': os.getenv('S3_BUCKET_NAME'),
                'region': os.getenv('AWS_REGION', 'us-east-1'),
            }
        elif provider == 'gcs':
            return {
                'project_id': os.getenv('GCS_PROJECT_ID'),
                'credentials_path': os.getenv('GCS_CREDENTIALS_PATH'),
                'bucket_name': os.getenv('GCS_BUCKET_NAME'),
            }
        else:
            return {}

    # ... (methods for getting and setting config values, validation, etc.)
```

### `.env.example`
This file serves as a template for your `.env` file, where you will define the actual environment variables for your deployment. To switch storage providers, you simply change the `STORAGE_PROVIDER` variable and provide the corresponding credentials.

```ini
# .env.example (excerpt)

# Storage Provider Configuration
# Options: supabase, s3, gcs
STORAGE_PROVIDER=supabase

# Supabase Configuration (if using Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_BUCKET_NAME=videos

# AWS S3 Configuration (if using S3)
# AWS_ACCESS_KEY_ID=your-access-key
# AWS_SECRET_ACCESS_KEY=your-secret-key
# S3_BUCKET_NAME=your-bucket-name
# AWS_REGION=us-east-1

# Google Cloud Storage Configuration (if using GCS)
# GCS_PROJECT_ID=your-project-id
# GCS_CREDENTIALS_PATH=/path/to/credentials.json
# GCS_BUCKET_NAME=your-bucket-name
```

To use a different storage provider:
1. **Copy `.env.example` to `.env`**: `cp .env.example .env`
2. **Edit `.env`**: Set `STORAGE_PROVIDER` to your desired provider (e.g., `s3`).
3. **Provide Credentials**: Fill in the relevant credentials for the chosen provider (e.g., `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME` for S3).

When the Flask application starts (`src/main.py`), it initializes the `Config` object, which in turn loads these environment variables. The `init_video_services` function then uses this configuration to create the appropriate storage provider instance via the `StorageFactory`.

This setup ensures that the application is highly configurable and adaptable to different storage needs without requiring any code changes.



## 3. Video Download and Upload to Backend

The application handles the entire workflow of downloading a video from a given URL and then uploading it to the configured backend storage (Supabase in the current setup). This process is orchestrated by the `/api/videos/process` endpoint in `src/routes/video.py`.

### `src/routes/video.py` (`process_video` endpoint and `_process_video_async` function)

When a `POST` request is made to `/api/videos/process` with a video URL, the `process_video` function is triggered. This function then calls the asynchronous `_process_video_async` function, which handles the core logic:

1.  **Video Download**: The `video_downloader.download_video(url, custom_options)` call initiates the download using `yt-dlp`. The downloaded video, along with its metadata (info.json) and thumbnail, are saved to a temporary local directory.

2.  **File Upload to Storage**: After successful download, the `storage_provider.upload_file()` method is called for each of the downloaded files (video, info.json, thumbnail). This method, which is part of the `BaseStorage` interface and implemented by `SupabaseStorage`, handles the actual transfer of the files to the Supabase bucket.

3.  **URL Generation**: Once uploaded, public or signed URLs for the stored files are generated using `storage_provider.get_file_url()`. These URLs are then returned in the API response, allowing access to the uploaded content.

4.  **Local Cleanup**: Finally, the temporary local files are cleaned up using `video_downloader.cleanup_files()` to free up disk space.

Here's a simplified flow of the `_process_video_async` function:

```python
# src/routes/video.py (simplified excerpt)

async def _process_video_async(url: str, processing_id: str, custom_options: dict):
    downloaded_files = []
    try:
        # Step 1: Download video to a temporary local directory
        download_result = await video_downloader.download_video(url, custom_options)
        
        video_file = download_result["video_file"]
        info_file = download_result["info_file"]
        thumbnail_file = download_result["thumbnail_file"]
        video_info = download_result["video_info"]
        
        downloaded_files = [f for f in [video_file, info_file, thumbnail_file] if f]
        
        # Step 2: Upload files to the configured storage provider (e.g., Supabase)
        video_key = f"videos/{processing_id}/{os.path.basename(video_file)}"
        video_upload_result = await storage_provider.upload_file(
            video_file, 
            video_key,
            metadata={ # ... metadata for video ... }
        )
        
        if info_file:
            info_key = f"videos/{processing_id}/{os.path.basename(info_file)}"
            await storage_provider.upload_file(info_file, info_key, metadata={ # ... metadata for info ... })
        
        if thumbnail_file:
            thumbnail_key = f"videos/{processing_id}/{os.path.basename(thumbnail_file)}"
            await storage_provider.upload_file(thumbnail_file, thumbnail_key, metadata={ # ... metadata for thumbnail ... })
        
        # Step 3: Generate access URLs for the uploaded files
        video_url = await storage_provider.get_file_url(video_key)
        # ... generate URLs for info and thumbnail ...
        
        # Step 4: Clean up temporary local files
        video_downloader.cleanup_files(downloaded_files)
        
        return { # ... API response with uploaded file details and URLs ... }
            
    except Exception as e:
        # Ensure cleanup on error
        if downloaded_files:
            video_downloader.cleanup_files(downloaded_files)
        raise e
```

### Supabase Implementation (`src/storage/supabase_storage.py`)

The `SupabaseStorage` class contains the concrete implementation of the `upload_file` method (and others) that interacts directly with the Supabase Storage API. It handles reading the local file, preparing it for upload, and sending it to your specified Supabase bucket.

```python
# src/storage/supabase_storage.py (excerpt)

import os
import asyncio
from typing import Dict, Any, Optional
from supabase import create_client, Client
from .base import BaseStorage, StorageError

class SupabaseStorage(BaseStorage):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client: Client = create_client(config["url"], config["key"])
        self.storage = self.client.storage
        self.bucket_name = config["bucket_name"]

    async def upload_file(self, file_path: str, destination_key: str, 
                         metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        if not self.validate_file_path(file_path):
            raise StorageError(f"File not found or not readable: {file_path}", "supabase")
        
        try:
            with open(file_path, "rb") as file:
                file_content = file.read()
            
            file_options = {}
            if metadata:
                file_options["metadata"] = metadata
            
            # Determine content type based on file extension
            file_ext = os.path.splitext(file_path)[1].lower()
            # ... (content type mapping logic) ...
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.storage.from_(self.bucket_name).upload,
                path=destination_key,
                file=file_content,
                file_options=file_options
            )
            
            return {
                "success": True,
                "key": destination_key,
                "bucket": self.bucket_name,
                "size": len(file_content),
                "content_type": file_options.get("content_type"),
                "metadata": metadata,
                "supabase_result": result
            }
            
        except Exception as e:
            raise StorageError(f"Upload failed: {str(e)}", "supabase")
```

This detailed breakdown shows how the application downloads the video locally and then seamlessly uploads it to your configured Supabase backend, leveraging the flexible storage architecture.



## 4. Usage Examples and Configuration Guide

To demonstrate the video download and upload functionality, you can use the provided API endpoints. Before running the application, ensure you have configured your `.env` file with the correct Supabase credentials.

### Configuration (`.env` file)

First, create a `.env` file in the root directory of the `video_processor` project by copying `.env.example`:

```bash
cp video_processor/.env.example video_processor/.env
```

Then, open `video_processor/.env` and fill in your Supabase details:

```ini
# .env

# Storage Provider Configuration
STORAGE_PROVIDER=supabase

# Supabase Configuration
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_BUCKET_NAME=videos

# Other optional configurations
FLASK_DEBUG=True
VIDEO_DOWNLOAD_DIR=/tmp/video_downloads
LOG_LEVEL=DEBUG
```

Replace `your-project-ref.supabase.co` with your actual Supabase project URL and `your_supabase_service_role_key` with your Supabase service role key. The `SUPABASE_BUCKET_NAME` can be left as `videos` or changed to your preferred bucket name.

### Running the Application

Navigate to the `video_processor` directory and start the Flask application:

```bash
cd video_processor
source venv/bin/activate
python src/main.py
```

The application will start and listen on `http://0.0.0.0:5000` (or the port configured in your `.env` file).

### API Usage Examples

You can interact with the API using `curl` or any API client (like Postman or Insomnia).

#### 1. Get Video Information (without downloading)

This endpoint allows you to retrieve metadata about a video from a given URL without actually downloading the video content.

**Endpoint**: `POST /api/videos/info`

**Example Request**:

```bash
curl -X POST http://localhost:5000/api/videos/info \
  -H "Content-Type: application/json" \
  -d 
```

**Example Response** (truncated for brevity):

```json
{
  "success": true,
  "video_info": {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
    "description": "The official video for “Never Gonna Give You Up” by Rick Astley...",
    "duration": 212,
    "uploader": "Rick Astley",
    "upload_date": "20091025",
    "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "extractor": "youtube",
    "formats": [
      {
        "format_id": "248",
        "ext": "webm",
        "width": 1920,
        "height": 1080,
        "filesize": 10000000,
        "vcodec": "vp9",
        "acodec": "opus"
      }
      // ... more formats
    ]
  }
}
```

#### 2. Process Video (Download and Upload to Supabase)

This is the main endpoint to trigger the video download and upload process. The video will be downloaded locally and then uploaded to your configured Supabase bucket.

**Endpoint**: `POST /api/videos/process`

**Example Request**:

```bash
curl -X POST http://localhost:5000/api/videos/process \
  -H "Content-Type: application/json" \
  -d 
```

**Example Response** (truncated for brevity):

```json
{
  "success": true,
  "processing_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "video_info": {
    "id": "dQw4w9WgXcQ",
    "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
    "duration": 212,
    "uploader": "Rick Astley",
    "file_size": 25000000,
    "file_extension": "mp4"
  },
  "storage": {
    "video": {
      "key": "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.mp4",
      "url": "https://your-project-ref.supabase.co/storage/v1/object/public/videos/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.mp4",
      "size": 25000000,
      "content_type": "video/mp4"
    },
    "metadata": {
      "key": "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.info.json",
      "url": "https://your-project-ref.supabase.co/storage/v1/object/public/videos/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.info.json",
      "size": 5000
    },
    "thumbnail": {
      "key": "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.jpg",
      "url": "https://your-project-ref.supabase.co/storage/v1/object/public/videos/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.jpg",
      "size": 15000
    }
  },
  "processed_at": "2025-07-26T12:34:56.789Z"
}
```

The `url` fields in the response will provide direct links to the video, metadata, and thumbnail files stored in your Supabase bucket.

#### 3. Get Details of a Processed Video

Retrieve all stored information about a specific video using its `processing_id`.

**Endpoint**: `GET /api/videos/{processing_id}`

**Example Request**:

```bash
curl http://localhost:5000/api/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef
```

**Example Response** (similar to the `process` endpoint response, focusing on `files`):

```json
{
  "success": true,
  "processing_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "files": {
    "video": {
      "key": "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.mp4",
      "url": "https://your-project-ref.supabase.co/storage/v1/object/public/videos/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.mp4",
      "size": 25000000,
      "last_modified": "2025-07-26T12:34:56.789Z",
      "content_type": "video/mp4"
    },
    "metadata": {
      "key": "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.info.json",
      "url": "https://your-project-ref.supabase.co/storage/v1/object/public/videos/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.info.json",
      "size": 5000,
      "last_modified": "2025-07-26T12:34:56.789Z",
      "content_type": "application/json"
    },
    "thumbnail": {
      "key": "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.jpg",
      "url": "https://your-project-ref.supabase.co/storage/v1/object/public/videos/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.jpg",
      "size": 15000,
      "last_modified": "2025-07-26T12:34:56.789Z",
      "content_type": "image/jpeg"
    }
  }
}
```

#### 4. Delete a Processed Video

This endpoint will delete the video and all associated files (metadata, thumbnail) from your Supabase bucket.

**Endpoint**: `DELETE /api/videos/{processing_id}`

**Example Request**:

```bash
curl -X DELETE http://localhost:5000/api/videos/a1b2c3d4-e5f6-7890-1234-567890abcdef
```

**Example Response**:

```json
{
  "success": true,
  "processing_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "deleted_files": [
    "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.mp4",
    "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.info.json",
    "videos/a1b2c3d4-e5f6-7890-1234-567890abcdef/dQw4w9WgXcQ.jpg"
  ]
}
```

This guide, along with the `README.md` and `DEPLOYMENT.md` files, provides a complete overview of how to configure, run, and interact with the application, demonstrating its flexible storage and video upload capabilities.

