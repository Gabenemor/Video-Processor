"""Direct streaming processor for video downloads to storage."""

import os
import io
import asyncio
import tempfile
import logging
import time
import mimetypes
from typing import Dict, Any, Optional, BinaryIO, Callable, Tuple

from src.video_downloader import VideoDownloader, VideoDownloadError
from src.streaming_uploader import create_streaming_uploader, StreamingUploader
from src.base import StorageError
from src.config import get_config

logger = logging.getLogger(__name__)

class DirectProcessor:
    """Process videos directly from source to storage without disk storage."""
    
    def __init__(self):
        """Initialize the direct processor."""
        config = get_config()
        proxy_config = config.get('proxy', {})
        timeout_config = config.get('timeout', {})
        
        # Set up temporary directory for downloads
        self.temp_dir = tempfile.gettempdir()
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Initialize video downloader
        self.video_downloader = VideoDownloader(self.temp_dir, proxy_config)
        
        # Initialize streaming uploader
        storage_config = config.get('storage', {})
        provider_name = storage_config.get('provider', 'supabase')
        self.streaming_uploader = create_streaming_uploader(provider_name)
        
        # Configure timeouts
        self.info_extraction_timeout = timeout_config.get('info_extraction', 300)
        self.download_timeout = timeout_config.get('download', 900)
        self.upload_timeout = timeout_config.get('upload', 600)
        
        # Chunk size for reading/writing
        self.chunk_size = 8 * 1024 * 1024  # 8MB default chunk size
    
    async def process_url(self, url: str, processing_id: str) -> Dict[str, Any]:
        """Process a video URL directly from source to storage.
        
        Args:
            url: Video URL to process
            processing_id: Unique ID for this processing task
            
        Returns:
            Dictionary containing processing result
            
        Raises:
            VideoDownloadError: If video download fails
            StorageError: If upload fails
        """
        logger.info(f"[{processing_id}] Starting direct video processing for URL: {url}")
        warnings = []
        partial_success = False
        
        try:
            # Step 1: Extract video info
            logger.info(f"[{processing_id}] Step 1: Extracting video info")
            video_info = await asyncio.wait_for(
                self.video_downloader.get_video_info(url),
                timeout=self.info_extraction_timeout
            )
            
            logger.info(f"[{processing_id}] Video info extracted for: {video_info.get('title', 'Unknown')}")
            
            # Step 2: Setup the direct download
            logger.info(f"[{processing_id}] Step 2: Setting up direct download")
            yt_dlp_args = self._prepare_direct_download_args(processing_id)
            
            # Track uploaded files
            uploaded_files = {}
            metadata_file = None
            thumbnail_file = None
            
            # Step 3: Direct process main video file
            logger.info(f"[{processing_id}] Step 3: Direct processing video")
            
            # Get the destination key for the video
            video_filename = f"{processing_id}_{video_info['id']}.mp4"
            video_key = f"videos/{processing_id}/{video_filename}"
            
            # Get video formats
            best_format = self._get_best_format(video_info)
            
            if best_format:
                # Stream video directly to storage
                video_result = await self._stream_video_directly(
                    url=url,
                    format_id=best_format['format_id'],
                    destination_key=video_key,
                    processing_id=processing_id,
                    yt_dlp_args=yt_dlp_args,
                    video_info=video_info
                )
                
                uploaded_files['video'] = {
                    'key': video_key,
                    'url': None,  # Will be set later
                    'size': video_result.get('size', 0)
                }
                
                # Step 4: Create and upload metadata file
                try:
                    logger.info(f"[{processing_id}] Step 4: Creating metadata file")
                    metadata_key = f"videos/{processing_id}/{processing_id}_info.json"
                    
                    # Convert to JSON and upload directly
                    import json
                    metadata_json = json.dumps(video_info, indent=2)
                    metadata_stream = io.BytesIO(metadata_json.encode('utf-8'))
                    
                    metadata_result = await asyncio.wait_for(
                        self.streaming_uploader.upload_stream(
                            file_stream=metadata_stream,
                            destination_key=metadata_key,
                            content_type='application/json',
                            metadata={'processing_id': processing_id, 'file_type': 'metadata'}
                        ),
                        timeout=60
                    )
                    
                    uploaded_files['metadata'] = {
                        'key': metadata_key,
                        'url': None,  # Will be set later
                        'size': metadata_result.get('size', 0)
                    }
                    
                    logger.info(f"[{processing_id}] Metadata uploaded: {metadata_key}")
                except Exception as e:
                    logger.warning(f"[{processing_id}] Metadata creation failed: {str(e)}")
                    warnings.append("metadata_creation_failed")
                    partial_success = True
                
                # Step 5: Download and upload thumbnail if available
                try:
                    if video_info.get('thumbnail'):
                        logger.info(f"[{processing_id}] Step 5: Processing thumbnail")
                        thumbnail_url = video_info['thumbnail']
                        thumbnail_ext = self._get_file_extension_from_url(thumbnail_url) or 'jpg'
                        thumbnail_key = f"videos/{processing_id}/{processing_id}_thumbnail.{thumbnail_ext}"
                        
                        # Download and upload thumbnail
                        thumbnail_result = await self._download_and_upload_file(
                            url=thumbnail_url,
                            destination_key=thumbnail_key,
                            processing_id=processing_id,
                            metadata={'processing_id': processing_id, 'file_type': 'thumbnail'}
                        )
                        
                        uploaded_files['thumbnail'] = {
                            'key': thumbnail_key,
                            'url': None,  # Will be set later
                            'size': thumbnail_result.get('size', 0)
                        }
                        
                        logger.info(f"[{processing_id}] Thumbnail uploaded: {thumbnail_key}")
                except Exception as e:
                    logger.warning(f"[{processing_id}] Thumbnail processing failed: {str(e)}")
                    warnings.append("thumbnail_processing_failed")
                    partial_success = True
                
                # Step 6: Generate file URLs
                logger.info(f"[{processing_id}] Step 6: Generating file URLs")
                
                # Generate URL for video
                from src.supabase_storage import SupabaseStorage
                storage_config = get_config().get('storage', {})
                storage = SupabaseStorage(storage_config.get('config', {}))
                
                video_url = await asyncio.wait_for(
                    storage.get_file_url(video_key),
                    timeout=30
                )
                uploaded_files['video']['url'] = video_url
                
                # Generate URLs for metadata and thumbnail if they exist
                if 'metadata' in uploaded_files:
                    try:
                        metadata_url = await asyncio.wait_for(
                            storage.get_file_url(uploaded_files['metadata']['key']),
                            timeout=30
                        )
                        uploaded_files['metadata']['url'] = metadata_url
                    except Exception as e:
                        logger.warning(f"[{processing_id}] Metadata URL generation failed: {str(e)}")
                        warnings.append("metadata_url_generation_failed")
                
                if 'thumbnail' in uploaded_files:
                    try:
                        thumbnail_url = await asyncio.wait_for(
                            storage.get_file_url(uploaded_files['thumbnail']['key']),
                            timeout=30
                        )
                        uploaded_files['thumbnail']['url'] = thumbnail_url
                    except Exception as e:
                        logger.warning(f"[{processing_id}] Thumbnail URL generation failed: {str(e)}")
                        warnings.append("thumbnail_url_generation_failed")
                
                # Prepare result
                processed_url = video_info.get('webpage_url', '')
                url_match = self._validate_url_match(url, processed_url)
                if not url_match:
                    warnings.append("url_mismatch")
                
                # Extract the original base ID
                base_id = self._extract_base_id(processing_id)
                
                result = {
                    'success': True,
                    'processing_id': processing_id,
                    'original_id': base_id,  # Add the original ID
                    'original_url': url,
                    'processed_url': processed_url,
                    'url_match': url_match,
                    'video_info': video_info,
                    'storage': uploaded_files,
                    'warnings': warnings,
                    'partial_success': partial_success,
                    'direct_processing': True
                }
                
                logger.info(f"[{processing_id}] Direct processing completed successfully")
                return result
            else:
                raise VideoDownloadError("No suitable video format found", url, "FORMAT_ERROR")
            
        except asyncio.TimeoutError as e:
            logger.error(f"[{processing_id}] Timeout during direct processing: {str(e)}")
            raise VideoDownloadError(f"Direct processing timed out: {str(e)}", url, "TIMEOUT")
        except Exception as e:
            logger.error(f"[{processing_id}] Error during direct processing: {str(e)}")
            raise e
    
    def _prepare_direct_download_args(self, processing_id: str) -> Dict[str, Any]:
        """Prepare arguments for direct download."""
        return {
            'format': 'best[height<=720]/best',  # Consistent with main downloader
            'noplaylist': True,
            'quiet': True
        }
    
    def _get_best_format(self, video_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get the best format for direct download."""
        formats = video_info.get('formats', [])
        if not formats:
            return None
        
        # Sort formats by resolution and bitrate
        formats = sorted(
            formats,
            key=lambda f: (
                f.get('height', 0) <= 720,  # Prefer formats <= 720p
                f.get('height', 0),         # Then by height
                f.get('filesize', 0)        # Then by filesize
            ),
            reverse=True
        )
        
        # Return the best format
        if formats:
            return formats[0]
        return None
    
    async def _stream_video_directly(self, 
                                   url: str, 
                                   format_id: str,
                                   destination_key: str, 
                                   processing_id: str,
                                   yt_dlp_args: Dict[str, Any],
                                   video_info: Dict[str, Any]) -> Dict[str, Any]:
        """Stream video directly from source to storage."""
        import yt_dlp
        import subprocess
        import threading
        import queue
        
        class PipeReader(threading.Thread):
            def __init__(self, pipe, queue, chunk_size):
                threading.Thread.__init__(self)
                self.pipe = pipe
                self.queue = queue
                self.chunk_size = chunk_size
            
            def run(self):
                try:
                    while True:
                        chunk = self.pipe.read(self.chunk_size)
                        if not chunk:
                            break
                        self.queue.put(chunk)
                    self.queue.put(None)  # Signal end of data
                except Exception as e:
                    logger.error(f"Error reading from pipe: {e}")
                    self.queue.put(None)
        
        # Create a file-like object for streaming
        class StreamingBuffer(io.BufferedIOBase):
            def __init__(self, queue):
                self.queue = queue
                self.buffer = b''
                self.eof = False
            
            def read(self, size=-1):
                if self.eof and not self.buffer:
                    return b''
                
                while size < 0 or len(self.buffer) < size:
                    chunk = self.queue.get()
                    if chunk is None:
                        self.eof = True
                        break
                    self.buffer += chunk
                    if self.eof:
                        break
                
                if size < 0 or size > len(self.buffer):
                    result, self.buffer = self.buffer, b''
                else:
                    result, self.buffer = self.buffer[:size], self.buffer[size:]
                
                return result
        
        # Prepare command for yt-dlp
        cmd = [
            "yt-dlp",
            "-f", format_id,
            "-o", "-",  # Output to stdout
            "--no-playlist",
            "--no-warnings",
            "--quiet",
            url
        ]
        
        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=self.chunk_size
        )
        
        # Create queue and start reader thread
        data_queue = queue.Queue(maxsize=50)
        reader = PipeReader(process.stdout, data_queue, self.chunk_size)
        reader.start()
        
        # Create streaming buffer
        stream = StreamingBuffer(data_queue)
        
        # Determine content type
        content_type = "video/mp4"  # Default
        ext = video_info.get('ext', 'mp4')
        if ext:
            guessed_type = mimetypes.guess_type(f"file.{ext}")[0]
            if guessed_type:
                content_type = guessed_type
        
        # Progress tracking
        start_time = time.time()
        bytes_uploaded = 0
        
        def progress_callback(uploaded, total):
            nonlocal bytes_uploaded, start_time
            bytes_uploaded = uploaded
            elapsed = time.time() - start_time
            if elapsed > 0:
                speed = uploaded / elapsed / 1024  # KB/s
                logger.debug(f"[{processing_id}] Uploaded: {uploaded / 1024 / 1024:.2f} MB, Speed: {speed:.2f} KB/s")
        
        # Upload the stream
        try:
            upload_result = await self.streaming_uploader.upload_stream(
                file_stream=stream,
                destination_key=destination_key,
                content_type=content_type,
                metadata={
                    'processing_id': processing_id,
                    'file_type': 'video',
                    'format_id': format_id
                },
                progress_callback=progress_callback
            )
            
            # Wait for reader thread to finish
            reader.join()
            
            # Check process return code
            return_code = process.wait()
            if return_code != 0:
                stderr = process.stderr.read()
                logger.warning(f"[{processing_id}] yt-dlp process returned non-zero code: {return_code}")
                logger.warning(f"[{processing_id}] stderr: {stderr.decode('utf-8', errors='replace')}")
            
            return upload_result
        except Exception as e:
            # Terminate process if it's still running
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                pass
            raise e
    
    async def _download_and_upload_file(self, 
                                      url: str, 
                                      destination_key: str,
                                      processing_id: str,
                                      metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Download a file and upload it to storage."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"Failed to download file: HTTP {response.status}")
                
                # Determine content type
                content_type = response.headers.get('Content-Type', 'application/octet-stream')
                
                # Create a streaming buffer from the response body
                content_queue = asyncio.Queue(maxsize=50)
                
                # Start background task to fill the queue
                async def fill_queue():
                    while True:
                        chunk = await response.content.read(self.chunk_size)
                        if not chunk:
                            await content_queue.put(None)
                            break
                        await content_queue.put(chunk)
                
                queue_task = asyncio.create_task(fill_queue())
                
                # Create a file-like object for streaming
                class StreamingBuffer(io.BufferedIOBase):
                    def __init__(self, queue):
                        self.queue = queue
                        self.buffer = b''
                        self.eof = False
                    
                    def read(self, size=-1):
                        # This is a blocking read, used in a separate thread by the uploader
                        if self.eof and not self.buffer:
                            return b''
                        
                        loop = asyncio.get_event_loop()
                        while size < 0 or len(self.buffer) < size:
                            chunk = asyncio.run_coroutine_threadsafe(
                                self.queue.get(), loop
                            ).result()
                            
                            if chunk is None:
                                self.eof = True
                                break
                            self.buffer += chunk
                        
                        if size < 0 or size > len(self.buffer):
                            result, self.buffer = self.buffer, b''
                        else:
                            result, self.buffer = self.buffer[:size], self.buffer[size:]
                        
                        return result
                
                stream = StreamingBuffer(content_queue)
                
                # Upload the stream
                try:
                    upload_result = await self.streaming_uploader.upload_stream(
                        file_stream=stream,
                        destination_key=destination_key,
                        content_type=content_type,
                        metadata=metadata
                    )
                    
                    # Wait for queue task to complete
                    await queue_task
                    
                    return upload_result
                except Exception as e:
                    # Cancel queue task if it's still running
                    queue_task.cancel()
                    try:
                        await queue_task
                    except asyncio.CancelledError:
                        pass
                    raise e
    
    def _get_file_extension_from_url(self, url: str) -> Optional[str]:
        """Get file extension from URL."""
        if not url:
            return None
        
        # Extract filename from URL
        path = url.split('?')[0]
        filename = path.split('/')[-1]
        
        # Get extension
        if '.' in filename:
            return filename.split('.')[-1].lower()
        
        return None
    
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
        
    def _extract_base_id(self, task_id: str) -> str:
        """Extract the original base ID from task ID.
        
        For composite IDs, it removes the URL hash component.
        """
        # Check if this is a composite ID
        parts = task_id.split('-')
        if len(parts) >= 5:  # UUID has 4 hyphens, plus our added hash
            # If composite ID, return without the hash
            return '-'.join(parts[:-1])
        else:
            # Not a composite ID, return as is
            return task_id
