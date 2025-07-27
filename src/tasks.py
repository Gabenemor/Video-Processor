import os
import time
import logging
import requests
import psycopg2
import psycopg2.extras
import asyncio
import traceback
from typing import Dict, Any

from src.config import get_config
from src.video_downloader import VideoDownloader, VideoDownloadError
from src.factory import StorageFactory
from src.base import StorageError
from src.direct_processor import DirectProcessor

# Initialize configuration
config = get_config()
logger = logging.getLogger(__name__)

class TaskProcessor:
    """Processes video download tasks from the database with timeout and retry logic."""

    def __init__(self):
        """Initialize the task processor."""
        self.db_url = config.get_database_config().get('url')
        self.video_downloader = self._init_video_downloader()
        self.storage_provider = self._init_storage_provider()
        
        # Initialize direct processor
        self.direct_processor = DirectProcessor()
        self.use_direct_processing = config.get('video.use_direct_processing', True)
        
        # Timeout configurations from config
        timeout_config = config.get('timeout', {})
        self.info_extraction_timeout = timeout_config.get('info_extraction', 300)
        self.download_timeout = timeout_config.get('download', 900)
        self.upload_timeout = timeout_config.get('upload', 600)
        self.max_retries = timeout_config.get('max_retries', 2)

    def _init_video_downloader(self):
        """Initialize the video downloader."""
        download_dir = config.get('video.download_dir', '/tmp/video_downloads')
        os.makedirs(download_dir, exist_ok=True)
        proxy_config = config.get('proxy', {})
        return VideoDownloader(download_dir, proxy_config)

    def _init_storage_provider(self):
        """Initialize the storage provider."""
        storage_config = config.get('storage', {})
        provider_name = storage_config.get('provider', 'supabase')
        provider_config = storage_config.get('config', {})
        return StorageFactory.create_storage(provider_name, provider_config)

    def _get_db_connection(self):
        """Establish a direct database connection."""
        try:
            return psycopg2.connect(self.db_url)
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            return None

    def _send_webhook(self, url: str, payload: Dict[str, Any], max_retries: int = 3):
        """Send a webhook notification with retry logic."""
        for attempt in range(max_retries):
            try:
                # Add authorization header for Supabase Edge Functions
                headers = {
                    'Content-Type': 'application/json',
                    'User-Agent': 'Video-Processor/1.0'
                }
                
                # Add Authorization header if it's a Supabase function
                if 'supabase.co/functions' in url:
                    supabase_anon_key = config.get('storage.config.key')
                    if supabase_anon_key:
                        headers['Authorization'] = f'Bearer {supabase_anon_key}'
                
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                response.raise_for_status()
                logger.info(f"Webhook sent successfully to {url} (attempt {attempt + 1})")
                return True
                
            except requests.RequestException as e:
                logger.warning(f"Webhook attempt {attempt + 1} failed to {url}: {e}")
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying webhook in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All webhook attempts failed to {url}: {e}")
                    # Don't raise exception - webhook failure shouldn't fail the task
                    return False
        
        return False

    def _update_task_status(self, task_id: str, status: str, error_details: str = None, result: Dict[str, Any] = None):
        """Update task status in database."""
        conn = self._get_db_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                if status == 'failed':
                    cur.execute("""
                        UPDATE tasks
                        SET status = %s, error_details = %s, updated_at = NOW()
                        WHERE id = %s;
                    """, (status, error_details, task_id))
                elif status == 'completed':
                    cur.execute("""
                        UPDATE tasks
                        SET status = %s, result = %s, updated_at = NOW()
                        WHERE id = %s;
                    """, (status, psycopg2.extras.Json(result), task_id))
                else:
                    cur.execute("""
                        UPDATE tasks
                        SET status = %s, updated_at = NOW()
                        WHERE id = %s;
                    """, (status, task_id))
                conn.commit()
                return True
        except psycopg2.Error as e:
            logger.error(f"Failed to update task {task_id} status: {e}")
            return False
        finally:
            conn.close()

    def _should_retry_task(self, task_id: str, error: Exception) -> bool:
        """Determine if a task should be retried based on error type."""
        # Check if task has been retried too many times
        conn = self._get_db_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                # Count number of times this task has been processed
                cur.execute("""
                    SELECT COUNT(*) FROM tasks 
                    WHERE id = %s AND (status = 'failed' OR status = 'processing')
                """, (task_id,))
                retry_count = cur.fetchone()[0]
                
                # Retry on timeout or network errors, but not on validation errors
                if retry_count < self.max_retries:
                    if isinstance(error, VideoDownloadError):
                        # Retry on timeout or network errors
                        return error.error_code in ['TIMEOUT', 'NETWORK_ERROR'] or 'timeout' in str(error).lower()
                    elif isinstance(error, StorageError):
                        # Retry on storage errors
                        return True
                    elif 'timeout' in str(error).lower() or 'network' in str(error).lower():
                        return True
                
                return False
        except psycopg2.Error as e:
            logger.error(f"Failed to check retry count for task {task_id}: {e}")
            return False
        finally:
            conn.close()

    def process_single_task(self):
        """Fetch and process a single queued task with timeout and retry logic."""
        conn = self._get_db_connection()
        if not conn:
            return

        try:
            with conn.cursor() as cur:
                # Atomically fetch and update a task to 'processing'
                cur.execute("""
                    UPDATE tasks
                    SET status = 'processing', updated_at = NOW()
                    WHERE id = (
                        SELECT id FROM tasks
                        WHERE status = 'queued'
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING id, video_url, webhook_url;
                """)
                task = cur.fetchone()
                conn.commit()

            if task:
                task_id, video_url, webhook_url = task
                
                # Extract base UUID from composite task ID for processing
                processing_id = self._extract_processing_id(task_id)
                
                logger.info(f"Processing task {task_id} (processing_id: {processing_id}) for URL: {video_url}")
                
                # Validate that the task URL matches the composite ID
                if not self._validate_task_url_match(task_id, video_url):
                    logger.warning(f"Task {task_id} URL mismatch detected. Expected URL hash in task ID.")
                
                try:
                    # Run the async processing logic with timeout
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Set overall timeout for the entire task
                    total_timeout = self.info_extraction_timeout + self.download_timeout + self.upload_timeout
                    
                    result_payload = loop.run_until_complete(
                        asyncio.wait_for(
                            self._process_video_async(video_url, str(task_id)),
                            timeout=total_timeout
                        )
                    )
                    loop.close()

                    # Update task as completed
                    self._update_task_status(task_id, 'completed', result=result_payload)
                    
                    logger.info(f"Task {task_id} completed successfully.")
                    if webhook_url:
                        self._send_webhook(webhook_url, result_payload)

                except asyncio.TimeoutError:
                    error_details = f"Task timed out after {total_timeout} seconds"
                    logger.error(f"Task {task_id} timed out: {error_details}")
                    
                    # Check if we should retry
                    timeout_error = VideoDownloadError(error_details, video_url, "TIMEOUT")
                    if self._should_retry_task(task_id, timeout_error):
                        logger.info(f"Retrying task {task_id} due to timeout")
                        self._update_task_status(task_id, 'queued')
                    else:
                        self._update_task_status(task_id, 'failed', error_details=error_details)
                        
                        if webhook_url:
                            failure_payload = {
                                "success": False,
                                "processing_id": str(task_id),
                                "error": "Task timed out",
                                "error_details": error_details
                            }
                            self._send_webhook(webhook_url, failure_payload)

                except (VideoDownloadError, StorageError, Exception) as e:
                    error_details = str(e)
                    error_traceback = traceback.format_exc()
                    logger.error(f"Task {task_id} failed: {error_details}")
                    logger.error(f"Error traceback: {error_traceback}")
                    
                    # Check if we should retry
                    if self._should_retry_task(task_id, e):
                        logger.info(f"Retrying task {task_id} due to: {type(e).__name__}")
                        self._update_task_status(task_id, 'queued')
                    else:
                        self._update_task_status(task_id, 'failed', error_details=error_details)
                        
                        if webhook_url:
                            failure_payload = {
                                "success": False,
                                "processing_id": str(task_id),
                                "error": "Failed to process video",
                                "error_details": error_details
                            }
                            self._send_webhook(webhook_url, failure_payload)
        finally:
            if conn:
                conn.close()

    async def _process_video_async(self, url: str, processing_id: str):
        """Process video with enhanced timeout handling and comprehensive fallback."""
        downloaded_files = []
        warnings = []
        partial_success = False
        
        # Check if direct processing is enabled
        if self.use_direct_processing:
            logger.info(f"[{processing_id}] Using direct streaming processor for URL: {url}")
            try:
                # Use direct processor for streaming upload
                return await asyncio.wait_for(
                    self.direct_processor.process_url(url, processing_id),
                    timeout=self.download_timeout + self.upload_timeout + 60
                )
            except Exception as e:
                logger.warning(f"[{processing_id}] Direct processing failed, falling back to standard method: {str(e)}")
                warnings.append("direct_processing_failed")
                # Fall through to standard processing
        
        try:
            logger.info(f"[{processing_id}] Starting standard video processing for URL: {url}")
            
            # Stage 1: Download video with timeout
            logger.info(f"[{processing_id}] Stage 1: Downloading video")
            download_result = await asyncio.wait_for(
                self.video_downloader.download_video(url, {}, timeout=self.download_timeout),
                timeout=self.download_timeout + 60  # Add buffer for async overhead
            )
            
            video_file = download_result['video_file']
            info_file = download_result.get('info_file')
            thumbnail_file = download_result.get('thumbnail_file')
            video_info = download_result['video_info']
            
            downloaded_files = [f for f in [video_file, info_file, thumbnail_file] if f]
            logger.info(f"[{processing_id}] Downloaded {len(downloaded_files)} files")

            # URL validation - check if processed URL matches requested URL
            processed_url = video_info.get('webpage_url', '')
            url_match = self._validate_url_match(url, processed_url)
            if not url_match:
                warning_msg = f"URL mismatch: requested {url}, processed {processed_url}"
                warnings.append("url_mismatch")
                logger.warning(f"[{processing_id}] {warning_msg}")

            # Stage 2: Upload files with timeout and fallback handling
            logger.info(f"[{processing_id}] Stage 2: Uploading files to storage")
            
            # Upload video file (required)
            video_key = f"videos/{processing_id}/{os.path.basename(video_file)}"
            video_upload_result = await asyncio.wait_for(
                self.storage_provider.upload_file(video_file, video_key, {
                    'processing_id': processing_id,
                    'file_type': 'video',
                    'original_url': url,
                    'processed_url': processed_url
                }),
                timeout=self.upload_timeout
            )
            logger.info(f"[{processing_id}] Video uploaded: {video_key}")
            
            # Upload info file with fallback
            info_key, info_upload_result = None, None
            if info_file:
                try:
                    info_key = f"videos/{processing_id}/{os.path.basename(info_file)}"
                    info_upload_result = await asyncio.wait_for(
                        self.storage_provider.upload_file(info_file, info_key, {
                            'processing_id': processing_id,
                            'file_type': 'metadata'
                        }),
                        timeout=60  # Shorter timeout for small files
                    )
                    logger.info(f"[{processing_id}] Metadata uploaded: {info_key}")
                except Exception as e:
                    logger.warning(f"[{processing_id}] Metadata upload failed: {str(e)}")
                    warnings.append("metadata_upload_failed")
                    partial_success = True

            # Upload thumbnail with fallback
            thumbnail_key, thumbnail_upload_result = None, None
            if thumbnail_file:
                try:
                    thumbnail_key = f"videos/{processing_id}/{os.path.basename(thumbnail_file)}"
                    thumbnail_upload_result = await asyncio.wait_for(
                        self.storage_provider.upload_file(thumbnail_file, thumbnail_key, {
                            'processing_id': processing_id,
                            'file_type': 'thumbnail'
                        }),
                        timeout=60  # Shorter timeout for small files
                    )
                    logger.info(f"[{processing_id}] Thumbnail uploaded: {thumbnail_key}")
                except Exception as e:
                    logger.warning(f"[{processing_id}] Thumbnail upload failed: {str(e)}")
                    warnings.append("thumbnail_upload_failed")
                    partial_success = True

            # Stage 3: Generate file URLs with fallback
            logger.info(f"[{processing_id}] Stage 3: Generating file URLs")
            video_url = await asyncio.wait_for(
                self.storage_provider.get_file_url(video_key),
                timeout=30
            )
            
            info_url = None
            if info_key:
                try:
                    info_url = await asyncio.wait_for(
                        self.storage_provider.get_file_url(info_key),
                        timeout=30
                    )
                except Exception as e:
                    logger.warning(f"[{processing_id}] Info URL generation failed: {str(e)}")
                    warnings.append("info_url_generation_failed")

            thumbnail_url = None
            if thumbnail_key:
                try:
                    thumbnail_url = await asyncio.wait_for(
                        self.storage_provider.get_file_url(thumbnail_key),
                        timeout=30
                    )
                except Exception as e:
                    logger.warning(f"[{processing_id}] Thumbnail URL generation failed: {str(e)}")
                    warnings.append("thumbnail_url_generation_failed")

            # Extract the original base ID from the composite task ID
            base_id = self._extract_base_id(processing_id)
            
            # Enhanced result with fallback information
            result = {
                'success': True,
                'processing_id': processing_id,
                'original_id': base_id,  # Add the original ID
                'original_url': url,
                'processed_url': processed_url,
                'url_match': url_match,
                'video_info': video_info,
                'storage': {
                    'video': {'key': video_key, 'url': video_url, 'size': video_upload_result.get('size')},
                    'metadata': {'key': info_key, 'url': info_url, 'size': info_upload_result.get('size')} if info_key else None,
                    'thumbnail': {'key': thumbnail_key, 'url': thumbnail_url, 'size': thumbnail_upload_result.get('size')} if thumbnail_key else None,
                },
                'warnings': warnings,
                'partial_success': partial_success
            }
            
            logger.info(f"[{processing_id}] Processing completed successfully (warnings: {len(warnings)})")
            return result
            
        except asyncio.TimeoutError as e:
            logger.error(f"[{processing_id}] Timeout during video processing: {str(e)}")
            raise VideoDownloadError(f"Processing timed out: {str(e)}", url, "TIMEOUT")
        except Exception as e:
            logger.error(f"[{processing_id}] Error during video processing: {str(e)}")
            raise e
        finally:
            if downloaded_files:
                logger.info(f"[{processing_id}] Cleaning up {len(downloaded_files)} downloaded files")
                self.video_downloader.cleanup_files(downloaded_files)

    def _validate_url_match(self, original_url: str, processed_url: str) -> bool:
        """Validate if the processed URL matches the original request."""
        if not original_url or not processed_url:
            return False
        
        # Normalize URLs for comparison
        original_clean = original_url.lower().strip()
        processed_clean = processed_url.lower().strip()
        
        # Extract video IDs for comparison
        original_id = self._extract_video_id(original_clean)
        processed_id = self._extract_video_id(processed_clean)
        
        # If we can extract IDs, compare them
        if original_id and processed_id:
            return original_id == processed_id
        
        # Fallback to domain comparison
        return self._extract_domain(original_clean) == self._extract_domain(processed_clean)
    
    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from URL."""
        import re
        
        # YouTube patterns
        youtube_patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)',
            r'youtube\.com/v/([a-zA-Z0-9_-]+)'
        ]
        
        # TikTok patterns
        tiktok_patterns = [
            r'tiktok\.com/@[^/]+/video/(\d+)',
            r'tiktok\.com/t/([a-zA-Z0-9]+)'
        ]
        
        for pattern in youtube_patterns + tiktok_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        import re
        
        match = re.search(r'://([^/]+)', url)
        if match:
            domain = match.group(1)
            # Remove 'www.' and 'm.' prefixes
            domain = re.sub(r'^(www\.|m\.)', '', domain)
            return domain
        
        return url
    
    def _extract_processing_id(self, task_id: str) -> str:
        """Extract the base processing ID from a composite task ID."""
        # Split composite ID: {uuid}-{url_hash} -> {uuid}
        parts = task_id.split('-')
        if len(parts) >= 5:  # UUID has 4 hyphens, plus our added hash
            # Rejoin all parts except the last one (url hash)
            return '-'.join(parts[:-1])
        else:
            # Fallback for non-composite IDs
            return task_id
            
    def _extract_base_id(self, task_id: str) -> str:
        """Extract the original base ID from task ID or database.
        
        This gets the raw ID that was originally provided with the URL request.
        For composite IDs, it removes the URL hash component.
        """
        # First check if this is a composite ID
        parts = task_id.split('-')
        if len(parts) >= 5:  # UUID has 4 hyphens, plus our added hash
            # Check if we can get more information from the database
            conn = self._get_db_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        cur.execute("SELECT result FROM tasks WHERE id = %s", (task_id,))
                        row = cur.fetchone()
                        if row and row['result']:
                            # Try to get base_id from the stored result
                            if isinstance(row['result'], dict) and 'base_id' in row['result']:
                                return row['result']['base_id']
                finally:
                    conn.close()
            
            # If we couldn't get it from DB, just return the ID without hash
            return '-'.join(parts[:-1])
        else:
            # Not a composite ID, return as is
            return task_id
    
    def _validate_task_url_match(self, task_id: str, url: str) -> bool:
        """Validate that the URL matches the hash in the composite task ID."""
        # Extract expected URL hash from task ID
        parts = task_id.split('-')
        if len(parts) < 5:  # Not a composite ID
            return True  # Skip validation for old format
        
        expected_hash = parts[-1]  # Last part is the URL hash
        
        # Generate hash from current URL
        actual_hash = self._generate_url_hash(url)
        
        return expected_hash == actual_hash
    
    def _generate_url_hash(self, url: str) -> str:
        """Generate a short hash from URL for task ID uniqueness."""
        import hashlib
        
        # Normalize URL for consistent hashing
        normalized_url = url.lower().strip()
        
        # Create MD5 hash and take first 8 characters
        url_hash = hashlib.md5(normalized_url.encode()).hexdigest()[:8]
        return url_hash

def run_worker():
    """Main worker loop."""
    logger.info("Starting background worker...")
    processor = TaskProcessor()
    while True:
        try:
            processor.process_single_task()
        except Exception as e:
            logger.error(f"An unexpected error occurred in the worker loop: {e}")
        # Sleep for a short interval to prevent busy-waiting
        time.sleep(1)  # Reduced from 5s for faster task pickup

if __name__ == "__main__":
    # This allows running the worker directly for testing
    run_worker()
