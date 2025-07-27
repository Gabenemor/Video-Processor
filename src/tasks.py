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
        """Establish a database connection."""
        try:
            return psycopg2.connect(self.db_url)
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            return None

    def _send_webhook(self, url: str, payload: Dict[str, Any]):
        """Send a webhook notification."""
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Webhook sent successfully to {url}")
        except requests.RequestException as e:
            logger.error(f"Failed to send webhook to {url}: {e}")

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
                logger.info(f"Processing task {task_id} for URL: {video_url}")
                
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
        """Process video with enhanced timeout handling for each stage."""
        downloaded_files = []
        try:
            logger.info(f"[{processing_id}] Starting video processing for URL: {url}")
            
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

            # Stage 2: Upload files with timeout
            logger.info(f"[{processing_id}] Stage 2: Uploading files to storage")
            
            # Upload video file
            video_key = f"videos/{processing_id}/{os.path.basename(video_file)}"
            video_upload_result = await asyncio.wait_for(
                self.storage_provider.upload_file(video_file, video_key, {
                    'processing_id': processing_id,
                    'file_type': 'video'
                }),
                timeout=self.upload_timeout
            )
            logger.info(f"[{processing_id}] Video uploaded: {video_key}")
            
            # Upload info file if available
            info_key, info_upload_result = None, None
            if info_file:
                info_key = f"videos/{processing_id}/{os.path.basename(info_file)}"
                info_upload_result = await asyncio.wait_for(
                    self.storage_provider.upload_file(info_file, info_key, {
                        'processing_id': processing_id,
                        'file_type': 'metadata'
                    }),
                    timeout=60  # Shorter timeout for small files
                )
                logger.info(f"[{processing_id}] Metadata uploaded: {info_key}")

            # Upload thumbnail if available
            thumbnail_key, thumbnail_upload_result = None, None
            if thumbnail_file:
                thumbnail_key = f"videos/{processing_id}/{os.path.basename(thumbnail_file)}"
                thumbnail_upload_result = await asyncio.wait_for(
                    self.storage_provider.upload_file(thumbnail_file, thumbnail_key, {
                        'processing_id': processing_id,
                        'file_type': 'thumbnail'
                    }),
                    timeout=60  # Shorter timeout for small files
                )
                logger.info(f"[{processing_id}] Thumbnail uploaded: {thumbnail_key}")

            # Stage 3: Generate file URLs
            logger.info(f"[{processing_id}] Stage 3: Generating file URLs")
            video_url = await asyncio.wait_for(
                self.storage_provider.get_file_url(video_key),
                timeout=30
            )
            info_url = await asyncio.wait_for(
                self.storage_provider.get_file_url(info_key),
                timeout=30
            ) if info_key else None
            thumbnail_url = await asyncio.wait_for(
                self.storage_provider.get_file_url(thumbnail_key),
                timeout=30
            ) if thumbnail_key else None

            result = {
                'success': True,
                'processing_id': processing_id,
                'video_info': video_info,
                'storage': {
                    'video': {'key': video_key, 'url': video_url, 'size': video_upload_result.get('size')},
                    'metadata': {'key': info_key, 'url': info_url, 'size': info_upload_result.get('size')} if info_key else None,
                    'thumbnail': {'key': thumbnail_key, 'url': thumbnail_url, 'size': thumbnail_upload_result.get('size')} if thumbnail_key else None,
                }
            }
            
            logger.info(f"[{processing_id}] Processing completed successfully")
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
        time.sleep(5)

if __name__ == "__main__":
    # This allows running the worker directly for testing
    run_worker()
