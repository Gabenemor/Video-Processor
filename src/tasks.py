import os
import time
import logging
import requests
import psycopg2
import asyncio
from typing import Dict, Any

from src.config import get_config
from src.video_downloader import VideoDownloader, VideoDownloadError
from src.factory import StorageFactory
from src.base import StorageError

# Initialize configuration
config = get_config()
logger = logging.getLogger(__name__)

class TaskProcessor:
    """Processes video download tasks from the database."""

    def __init__(self):
        """Initialize the task processor."""
        self.db_url = config.get_database_config().get('url')
        self.video_downloader = self._init_video_downloader()
        self.storage_provider = self._init_storage_provider()

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

    def process_single_task(self):
        """Fetch and process a single queued task."""
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
                    # Run the async processing logic
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result_payload = loop.run_until_complete(
                        self._process_video_async(video_url, str(task_id))
                    )
                    loop.close()

                    # Update task as completed
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE tasks
                            SET status = 'completed', result = %s, updated_at = NOW()
                            WHERE id = %s;
                        """, (psycopg2.extras.Json(result_payload), task_id))
                        conn.commit()
                    
                    logger.info(f"Task {task_id} completed successfully.")
                    if webhook_url:
                        self._send_webhook(webhook_url, result_payload)

                except (VideoDownloadError, StorageError, Exception) as e:
                    error_details = str(e)
                    logger.error(f"Task {task_id} failed: {error_details}")
                    
                    # Update task as failed
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE tasks
                            SET status = 'failed', error_details = %s, updated_at = NOW()
                            WHERE id = %s;
                        """, (error_details, task_id))
                        conn.commit()

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
        """Re-purposed async processing logic from video.py."""
        downloaded_files = []
        try:
            download_result = await self.video_downloader.download_video(url, {})
            video_file = download_result['video_file']
            info_file = download_result.get('info_file')
            thumbnail_file = download_result.get('thumbnail_file')
            video_info = download_result['video_info']
            
            downloaded_files = [f for f in [video_file, info_file, thumbnail_file] if f]

            video_key = f"videos/{processing_id}/{os.path.basename(video_file)}"
            video_upload_result = await self.storage_provider.upload_file(video_file, video_key, {'processing_id': processing_id})
            
            info_key, info_upload_result = None, None
            if info_file:
                info_key = f"videos/{processing_id}/{os.path.basename(info_file)}"
                info_upload_result = await self.storage_provider.upload_file(info_file, info_key, {'processing_id': processing_id})

            thumbnail_key, thumbnail_upload_result = None, None
            if thumbnail_file:
                thumbnail_key = f"videos/{processing_id}/{os.path.basename(thumbnail_file)}"
                thumbnail_upload_result = await self.storage_provider.upload_file(thumbnail_file, thumbnail_key, {'processing_id': processing_id})

            video_url = await self.storage_provider.get_file_url(video_key)
            info_url = await self.storage_provider.get_file_url(info_key) if info_key else None
            thumbnail_url = await self.storage_provider.get_file_url(thumbnail_key) if thumbnail_key else None

            return {
                'success': True,
                'processing_id': processing_id,
                'video_info': video_info,
                'storage': {
                    'video': {'key': video_key, 'url': video_url, 'size': video_upload_result.get('size')},
                    'metadata': {'key': info_key, 'url': info_url, 'size': info_upload_result.get('size')} if info_key else None,
                    'thumbnail': {'key': thumbnail_key, 'url': thumbnail_url, 'size': thumbnail_upload_result.get('size')} if thumbnail_key else None,
                }
            }
        finally:
            if downloaded_files:
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
