"""Video processing API routes with enhanced error logging."""

import os
import asyncio
import uuid
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import BadRequest
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

from .video_downloader import VideoDownloader, VideoDownloadError
from .factory import StorageFactory
from .base import StorageError
from .config import get_config

logger = logging.getLogger(__name__)

video_bp = Blueprint('video', __name__)

# Global instances (will be initialized with configuration)
video_downloader = None
storage_provider = None
db_url = None


def init_video_services(config):
    """Initialize video services with configuration."""
    global video_downloader, storage_provider, db_url

    try:
        # Initialize video downloader
        download_dir = config.get('video', {}).get('download_dir', '/tmp/video_downloads')
        os.makedirs(download_dir, exist_ok=True)
        proxy_config = config.get('proxy', {})
        video_downloader = VideoDownloader(download_dir, proxy_config)
        logger.info("Video downloader initialized.")

        # Initialize storage provider
        storage_config = config.get('storage', {})
        provider_name = storage_config.get('provider', 'supabase')
        provider_config = storage_config.get('config', {})
        storage_provider = StorageFactory.create_storage(provider_name, provider_config)
        logger.info(f"Storage provider initialized: {provider_name}")

        # Get database URL
        db_url = config.get('database', {}).get('url')
        if not db_url:
            raise ValueError("Database URL is not configured.")
        logger.info("Database URL configured.")

    except Exception as e:
        logger.error(f"Failed to initialize video services: {str(e)}")
        logger.error(f"Error traceback: {traceback.format_exc()}")
        raise e


@video_bp.route('/videos/info', methods=['POST'])
def get_video_info():
    """Get video information without downloading."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Video info request received")
    
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            logger.error(f"[{request_id}] Missing URL in request")
            return jsonify({'error': 'URL is required', 'request_id': request_id}), 400
        
        url = data['url']
        logger.info(f"[{request_id}] Processing URL: {url}")
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            logger.error(f"[{request_id}] Invalid URL format: {url}")
            return jsonify({
                'error': 'Invalid URL format', 
                'details': 'URL must start with http:// or https://',
                'request_id': request_id
            }), 400
        
        # Get video info asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            logger.info(f"[{request_id}] Extracting video info (using proxy if configured)")
            video_info = loop.run_until_complete(video_downloader.get_video_info(url))
            logger.info(f"[{request_id}] Successfully extracted info for: {video_info.get('title', 'Unknown')}")
            
            return jsonify({
                'success': True,
                'video_info': video_info,
                'request_id': request_id
            })
        finally:
            loop.close()
            
    except VideoDownloadError as e:
        logger.error(f"[{request_id}] Video info extraction failed: {str(e)}")
        logger.error(f"[{request_id}] Error details: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to extract video information',
            'details': str(e),
            'url': getattr(e, 'url', None),
            'error_code': getattr(e, 'error_code', None),
            'request_id': request_id
        }), 400
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error in get_video_info: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'request_id': request_id
        }), 500


def _generate_url_hash(url: str) -> str:
    """Generate a short hash from URL for task ID uniqueness."""
    import hashlib
    
    # Normalize URL for consistent hashing
    normalized_url = url.lower().strip()
    
    # Create MD5 hash and take first 8 characters
    url_hash = hashlib.md5(normalized_url.encode()).hexdigest()[:8]
    return url_hash

def _create_composite_task_id(base_id: str, url: str) -> str:
    """Create a composite task ID from base UUID and URL hash."""
    url_hash = _generate_url_hash(url)
    return f"{base_id}-{url_hash}"

@video_bp.route('/videos/process-async', methods=['POST'])
def process_video_async():
    """Accepts a video processing task and queues it."""
    data = request.get_json()
    if not data or 'url' not in data or 'id' not in data:
        return jsonify({'error': 'URL and id are required'}), 400

    base_id = data['id']
    video_url = data['url']
    # webhook_url parameter removed
    
    # Create composite task ID for unique tracking per URL
    composite_task_id = _create_composite_task_id(base_id, video_url)
    url_hash = _generate_url_hash(video_url)

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            # Store composite ID in database for unique tracking
            # The result field will contain the composite ID mapping
            initial_result = {
                'composite_id': composite_task_id,
                'base_id': base_id,
                'url_hash': url_hash,
                'video_url': video_url
            }
            
            cur.execute(
                "INSERT INTO tasks (id, video_url, status, result) VALUES (%s, %s, 'queued', %s)",
                (composite_task_id, video_url, psycopg2.extras.Json(initial_result))
            )
            conn.commit()
        logger.info(f"Task {composite_task_id} for URL {video_url} has been queued.")
        return jsonify({
            'status': 'accepted', 
            'task_id': composite_task_id,
            'original_id': base_id,
            'url_hash': url_hash
        }), 202
    except psycopg2.Error as e:
        # If composite ID fails due to UUID constraint, fall back to base ID
        logger.warning(f"Composite ID failed, trying base ID: {e}")
        try:
            with conn.cursor() as cur:
                # Use base ID with URL hash in result for tracking
                result_data = {
                    'composite_id': composite_task_id,
                    'base_id': base_id,
                    'url_hash': url_hash,
                    'video_url': video_url
                }
                
                cur.execute(
                    "INSERT INTO tasks (id, video_url, status, result) VALUES (%s, %s, 'queued', %s)",
                    (base_id, video_url, psycopg2.extras.Json(result_data))
                )
                conn.commit()
            logger.info(f"Task {base_id} (composite: {composite_task_id}) for URL {video_url} has been queued.")
            return jsonify({
                'status': 'accepted', 
                'task_id': composite_task_id,
                'db_id': base_id,
                'original_id': base_id,
                'url_hash': url_hash
            }), 202
        except psycopg2.Error as e2:
            logger.error(f"Database error while queueing task {base_id}: {e2}")
            return jsonify({'error': 'Failed to queue task'}), 500
    finally:
        if conn:
            conn.close()


@video_bp.route('/videos/task/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Gets the status and result of a processing task."""
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, status, result, error_details, created_at, updated_at FROM tasks WHERE id = %s", (task_id,))
            task = cur.fetchone()

        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        return jsonify(task)
    except psycopg2.Error as e:
        logger.error(f"Database error while fetching status for task {task_id}: {e}")
        return jsonify({'error': 'Failed to fetch task status'}), 500
    finally:
        if conn:
            conn.close()


@video_bp.route('/videos/<processing_id>', methods=['GET'])
def get_video_details(processing_id):
    """Get details of a processed video."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Video details request for ID: {processing_id}")
    
    try:
        # List files with the processing ID prefix
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            files = loop.run_until_complete(
                storage_provider.list_files(prefix=f"videos/{processing_id}/")
            )
            
            if not files:
                logger.warning(f"[{request_id}] Video not found: {processing_id}")
                return jsonify({
                    'error': 'Video not found',
                    'processing_id': processing_id,
                    'request_id': request_id
                }), 404
            
            logger.info(f"[{request_id}] Found {len(files)} files for processing ID")
            
            # Organize files by type
            video_files = {'video': None, 'metadata': None, 'thumbnail': None}
            
            for file_info in files:
                file_type = file_info.get('metadata', {}).get('file_type')
                if file_type in video_files:
                    file_url = loop.run_until_complete(
                        storage_provider.get_file_url(file_info['key'])
                    )
                    video_files[file_type] = {
                        'key': file_info['key'],
                        'url': file_url,
                        'size': file_info['size'],
                        'last_modified': file_info['last_modified'],
                        'content_type': file_info['content_type']
                    }
            
            return jsonify({
                'success': True,
                'processing_id': processing_id,
                'request_id': request_id,
                'files': video_files
            })
            
        finally:
            loop.close()
            
    except StorageError as e:
        logger.error(f"[{request_id}] Storage error in get_video_details: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to retrieve video details',
            'details': str(e),
            'provider': getattr(e, 'provider', None),
            'request_id': request_id
        }), 500
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error in get_video_details: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'request_id': request_id
        }), 500


@video_bp.route('/videos/<processing_id>', methods=['DELETE'])
def delete_video(processing_id):
    """Delete a processed video and its associated files."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Video deletion request for ID: {processing_id}")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # List files with the processing ID prefix
            files = loop.run_until_complete(
                storage_provider.list_files(prefix=f"videos/{processing_id}/")
            )
            
            if not files:
                logger.warning(f"[{request_id}] Video not found for deletion: {processing_id}")
                return jsonify({
                    'error': 'Video not found',
                    'processing_id': processing_id,
                    'request_id': request_id
                }), 404
            
            logger.info(f"[{request_id}] Deleting {len(files)} files")
            
            # Delete all files
            deleted_files = []
            for file_info in files:
                success = loop.run_until_complete(
                    storage_provider.delete_file(file_info['key'])
                )
                if success:
                    deleted_files.append(file_info['key'])
                    logger.info(f"[{request_id}] Deleted file: {file_info['key']}")
            
            logger.info(f"[{request_id}] Successfully deleted {len(deleted_files)} files")
            
            return jsonify({
                'success': True,
                'processing_id': processing_id,
                'request_id': request_id,
                'deleted_files': deleted_files
            })
            
        finally:
            loop.close()
            
    except StorageError as e:
        logger.error(f"[{request_id}] Storage error in delete_video: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to delete video',
            'details': str(e),
            'provider': getattr(e, 'provider', None),
            'request_id': request_id
        }), 500
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error in delete_video: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'request_id': request_id
        }), 500


@video_bp.route('/videos', methods=['GET'])
def list_videos():
    """List all processed videos."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Video list request received")
    
    try:
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 20, type=int)
        
        # Limit the maximum number of results
        limit = min(limit, 100)
        logger.info(f"[{request_id}] Listing videos: page={page}, limit={limit}")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # List all video files
            files = loop.run_until_complete(
                storage_provider.list_files(prefix="videos/", limit=limit * page)
            )
            
            logger.info(f"[{request_id}] Found {len(files)} total files")
            
            # Group files by processing ID
            videos = {}
            for file_info in files:
                # Extract processing ID from key (videos/{processing_id}/filename)
                key_parts = file_info['key'].split('/')
                if len(key_parts) >= 3 and key_parts[0] == 'videos':
                    processing_id = key_parts[1]
                    file_type = file_info.get('metadata', {}).get('file_type', 'unknown')
                    
                    if processing_id not in videos:
                        videos[processing_id] = {
                            'processing_id': processing_id,
                            'files': {},
                            'created_at': file_info['last_modified']
                        }
                    
                    videos[processing_id]['files'][file_type] = {
                        'key': file_info['key'],
                        'size': file_info['size'],
                        'content_type': file_info['content_type']
                    }
            
            # Convert to list and sort by creation date
            video_list = list(videos.values())
            video_list.sort(key=lambda x: x['created_at'], reverse=True)
            
            # Apply pagination
            start_idx = (page - 1) * limit
            end_idx = start_idx + limit
            paginated_videos = video_list[start_idx:end_idx]
            
            logger.info(f"[{request_id}] Returning {len(paginated_videos)} videos")
            
            return jsonify({
                'success': True,
                'request_id': request_id,
                'videos': paginated_videos,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': len(video_list),
                    'has_next': end_idx < len(video_list)
                }
            })
            
        finally:
            loop.close()
            
    except StorageError as e:
        logger.error(f"[{request_id}] Storage error in list_videos: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to list videos',
            'details': str(e),
            'provider': getattr(e, 'provider', None),
            'request_id': request_id
        }), 500
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error in list_videos: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'request_id': request_id
        }), 500


@video_bp.route('/supported-sites', methods=['GET'])
def get_supported_sites():
    """Get list of supported video sites."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Supported sites request")
    
    try:
        sites = video_downloader.get_supported_sites()
        # Convert extractor objects to strings for JSON serialization
        site_names = [str(site) for site in sites]
        
        logger.info(f"[{request_id}] Returning {len(site_names)} supported sites")
        
        return jsonify({
            'success': True,
            'request_id': request_id,
            'supported_sites': site_names[:100],  # Limit to first 100 for readability
            'total_count': len(site_names)
        })
    except Exception as e:
        logger.error(f"[{request_id}] Error getting supported sites: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to get supported sites',
            'details': str(e),
            'request_id': request_id
        }), 500


@video_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    request_id = str(uuid.uuid4())[:8]
    
    try:
        # Check if services are initialized
        if video_downloader is None or storage_provider is None:
            logger.warning(f"[{request_id}] Health check failed: Services not initialized")
            return jsonify({
                'status': 'unhealthy',
                'error': 'Services not initialized',
                'request_id': request_id
            }), 503
        
        logger.info(f"[{request_id}] Health check passed")
        
        return jsonify({
            'status': 'healthy',
            'request_id': request_id,
            'services': {
                'video_downloader': 'ready',
                'storage_provider': 'ready'
            },
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"[{request_id}] Health check error: {str(e)}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'request_id': request_id
        }), 503
