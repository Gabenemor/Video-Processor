"""Video processing API routes with enhanced error logging."""

import os
import asyncio
import uuid
import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import BadRequest
import logging

from .video_downloader import VideoDownloader, VideoDownloadError
from .factory import StorageFactory
from .base import StorageError

logger = logging.getLogger(__name__)

video_bp = Blueprint('video', __name__)

# Global instances (will be initialized with configuration)
video_downloader = None
storage_provider = None


def init_video_services(config):
    """Initialize video services with configuration."""
    global video_downloader, storage_provider
    
    try:
        # Initialize video downloader with proxy configuration
        download_dir = config.get('video', {}).get('download_dir', '/tmp/video_downloads')
        os.makedirs(download_dir, exist_ok=True)
        
        proxy_config = config.get('proxy', {})
        video_downloader = VideoDownloader(download_dir, proxy_config)
        
        logger.info(f"Video downloader initialized with download dir: {download_dir}")
        if proxy_config.get('use_proxy_for_info_extraction', False):
            logger.info("Proxy configured for info extraction (bot detection bypass)")
        
        # Initialize storage provider
        storage_config = config.get('storage', {})
        provider_name = storage_config.get('provider', 'supabase')
        provider_config = storage_config.get('config', {})
        
        storage_provider = StorageFactory.create_storage(provider_name, provider_config)
        logger.info(f"Storage provider initialized: {provider_name}")
        
        # Log bucket configuration
        bucket_name = provider_config.get('bucket_name', 'unknown')
        logger.info(f"Using storage bucket: {bucket_name}")
        
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


@video_bp.route('/videos/process', methods=['POST'])
def process_video():
    """Download video and upload to storage."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Video processing request received")

    try:
        data = request.get_json()
        if not data or 'url' not in data:
            logger.error(f"[{request_id}] Missing URL in request")
            return jsonify({'error': 'URL is required', 'request_id': request_id}), 400

        url = data['url']
        custom_options = data.get('options', {})
        
        # Use user-provided ID or generate a new one
        processing_id = data.get('id', str(uuid.uuid4()))
        logger.info(f"[{request_id}] Using processing ID: {processing_id}")

        logger.info(f"[{request_id}] Processing video URL: {url}")

        # Validate URL
        if not url.startswith(('http://', 'https://')):
            logger.error(f"[{request_id}] Invalid URL format: {url}")
            return jsonify({
                'error': 'Invalid URL format',
                'details': 'URL must start with http:// or https://',
                'request_id': request_id
            }), 400

        # Process video asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _process_video_async(url, processing_id, custom_options, request_id)
            )
            logger.info(f"[{request_id}] Video processing completed successfully")
            return jsonify(result)
        finally:
            loop.close()
            
    except VideoDownloadError as e:
        logger.error(f"[{request_id}] Video download failed: {str(e)}")
        logger.error(f"[{request_id}] Error details: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to download video',
            'details': str(e),
            'url': getattr(e, 'url', None),
            'error_code': getattr(e, 'error_code', None),
            'request_id': request_id
        }), 400
    except StorageError as e:
        logger.error(f"[{request_id}] Storage upload failed: {str(e)}")
        logger.error(f"[{request_id}] Error details: {traceback.format_exc()}")
        return jsonify({
            'error': 'Failed to upload video to storage',
            'details': str(e),
            'provider': getattr(e, 'provider', None),
            'error_code': getattr(e, 'error_code', None),
            'request_id': request_id
        }), 500
    except Exception as e:
        logger.error(f"[{request_id}] Unexpected error in process_video: {str(e)}")
        logger.error(f"[{request_id}] Error traceback: {traceback.format_exc()}")
        return jsonify({
            'error': 'Internal server error',
            'details': str(e),
            'request_id': request_id
        }), 500


async def _process_video_async(url: str, processing_id: str, custom_options: dict, request_id: str):
    """Asynchronously process video download and upload."""
    downloaded_files = []
    
    try:
        # Step 1: Download video
        logger.info(f"[{request_id}] Starting video download for {url}")
        download_result = await video_downloader.download_video(url, custom_options)
        
        video_file = download_result['video_file']
        info_file = download_result['info_file']
        thumbnail_file = download_result['thumbnail_file']
        video_info = download_result['video_info']
        
        downloaded_files = [f for f in [video_file, info_file, thumbnail_file] if f]
        logger.info(f"[{request_id}] Downloaded {len(downloaded_files)} files")
        
        # Step 2: Upload files to storage
        logger.info(f"[{request_id}] Starting upload to Supabase storage")
        
        # Upload video file
        video_key = f"videos/{processing_id}/{os.path.basename(video_file)}"
        logger.info(f"[{request_id}] Uploading video file to: {video_key}")
        
        video_upload_result = await storage_provider.upload_file(
            video_file,
            video_key,
            metadata={
                'processing_id': processing_id,
                'user_id': processing_id,
                'original_url': url,
                'title': video_info.get('title', ''),
                'uploader': video_info.get('uploader', ''),
                'duration': str(video_info.get('duration', '')),
                'upload_date': video_info.get('upload_date', ''),
                'file_type': 'video',
                'request_id': request_id
            }
        )
        logger.info(f"[{request_id}] Video upload completed: {video_upload_result.get('size', 0)} bytes")
        
        # Upload info file if available
        info_upload_result = None
        if info_file:
            info_key = f"videos/{processing_id}/{os.path.basename(info_file)}"
            logger.info(f"[{request_id}] Uploading info file to: {info_key}")
            info_upload_result = await storage_provider.upload_file(
                info_file,
                info_key,
                metadata={
                    'processing_id': processing_id,
                    'file_type': 'metadata',
                    'request_id': request_id
                }
            )
            logger.info(f"[{request_id}] Info file upload completed")
        
        # Upload thumbnail if available
        thumbnail_upload_result = None
        if thumbnail_file:
            thumbnail_key = f"videos/{processing_id}/{os.path.basename(thumbnail_file)}"
            logger.info(f"[{request_id}] Uploading thumbnail to: {thumbnail_key}")
            thumbnail_upload_result = await storage_provider.upload_file(
                thumbnail_file,
                thumbnail_key,
                metadata={
                    'processing_id': processing_id,
                    'file_type': 'thumbnail',
                    'request_id': request_id
                }
            )
            logger.info(f"[{request_id}] Thumbnail upload completed")
        
        # Step 3: Generate access URLs
        logger.info(f"[{request_id}] Generating access URLs")
        video_url = await storage_provider.get_file_url(video_key)
        info_url = await storage_provider.get_file_url(info_key) if info_file else None
        thumbnail_url = await storage_provider.get_file_url(thumbnail_key) if thumbnail_file else None
        
        # Step 4: Cleanup local files
        logger.info(f"[{request_id}] Cleaning up {len(downloaded_files)} temporary files")
        video_downloader.cleanup_files(downloaded_files)
        
        result = {
            'success': True,
            'processing_id': processing_id,
            'request_id': request_id,
            'video_info': video_info,
            'storage': {
                'video': {
                    'key': video_key,
                    'url': video_url,
                    'size': video_upload_result.get('size'),
                    'content_type': video_upload_result.get('content_type')
                },
                'metadata': {
                    'key': info_key,
                    'url': info_url,
                    'size': info_upload_result.get('size') if info_upload_result else None
                } if info_file else None,
                'thumbnail': {
                    'key': thumbnail_key,
                    'url': thumbnail_url,
                    'size': thumbnail_upload_result.get('size') if thumbnail_upload_result else None
                } if thumbnail_file else None
            },
            'processed_at': datetime.utcnow().isoformat()
        }
        
        logger.info(f"[{request_id}] Video processing completed successfully")
        return result
        
    except Exception as e:
        # Cleanup files on error
        if downloaded_files:
            logger.info(f"[{request_id}] Cleaning up {len(downloaded_files)} files due to error")
            video_downloader.cleanup_files(downloaded_files)
        logger.error(f"[{request_id}] Error in _process_video_async: {str(e)}")
        raise e


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
