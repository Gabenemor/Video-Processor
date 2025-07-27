"""Video downloader module using yt-dlp with proxy support."""

import os
import tempfile
import uuid
import time
import random
from typing import Dict, Any, Optional, List
import yt_dlp
import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import logging

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Video downloader using yt-dlp for multiple platforms with proxy support."""
    
    def __init__(self, download_dir: Optional[str] = None, proxy_config: Optional[Dict[str, Any]] = None):
        """Initialize video downloader.
        
        Args:
            download_dir: Directory for temporary downloads. If None, uses system temp.
            proxy_config: Proxy configuration dictionary containing webshare credentials
        """
        self.download_dir = download_dir or tempfile.gettempdir()
        self.proxy_config = proxy_config or {}
        self.executor = ThreadPoolExecutor(max_workers=3)
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        
        # Default yt-dlp options with timeout and anti-bot detection
        self.default_options = {
            'format': 'best[height<=720]/best',  # Prefer 720p or lower for reasonable file sizes
            'outtmpl': os.path.join(self.download_dir, '%(id)s.%(ext)s'),
            'writeinfojson': True,  # Save metadata
            'writethumbnail': True,  # Save thumbnail
            'writesubtitles': False,  # Skip subtitles for now
            'ignoreerrors': False,
            'no_warnings': False,
            # Timeout configurations
            'socket_timeout': 30,
            'http_chunk_size': 10485760,  # 10MB chunks
            'fragment_retries': 3,
            'retries': 3,
            # Anti-bot detection
            'user_agent': random.choice(self.user_agents),
            'sleep_interval': 1,
            'max_sleep_interval': 5,
            'sleep_interval_subtitles': 0,
            # Additional options for YouTube
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_skip': ['js'],
                    'player_client': ['android', 'web']
                }
            }
        }
    
    def _get_proxy_url(self) -> Optional[str]:
        """Generate proxy URL for Webshare.io if configured."""
        if not self.proxy_config.get('use_proxy', False):
            return None
            
        username = self.proxy_config.get('webshare_username')
        password = self.proxy_config.get('webshare_password')
        endpoint = self.proxy_config.get('webshare_endpoint', 'p.webshare.io:80')
        
        if not username or not password:
            logger.warning("Proxy credentials not configured, skipping proxy usage")
            return None
        
        proxy_url = f"http://{username}:{password}@{endpoint}"
        logger.info(f"Using proxy: {endpoint}")
        return proxy_url
    
    def _should_use_proxy(self, url: str) -> bool:
        """Determine if proxy should be used based on URL and configuration."""
        # Force proxy usage for YouTube to avoid bot detection
        if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
            return True
        
        # Use proxy if configured
        return self.proxy_config.get('use_proxy', False)
    
    def _get_enhanced_options(self, url: str, use_proxy: bool = None) -> Dict[str, Any]:
        """Get enhanced yt-dlp options with proxy and timeout handling."""
        options = {**self.default_options}
        
        # Rotate user agent for each request
        options['user_agent'] = random.choice(self.user_agents)
        
        # Determine proxy usage
        should_use_proxy = use_proxy if use_proxy is not None else self._should_use_proxy(url)
        
        if should_use_proxy:
            proxy_url = self._get_proxy_url()
            if proxy_url:
                options['proxy'] = proxy_url
                logger.info("Using proxy for request")
                # Add delay when using proxy to avoid rate limiting
                options['sleep_interval'] = random.randint(1, 3)
            else:
                logger.warning("Proxy usage requested but not configured properly")
        
        # Enhanced options for YouTube
        if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
            options.update({
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_skip': ['js'],
                        'player_client': ['android', 'web'],
                        'comment_sort': ['top'],
                        'max_comments': ['0']
                    }
                },
                'sleep_interval': random.randint(1, 2),
                'max_sleep_interval': 5,
            })
        
        return options
    
    async def get_video_info(self, url: str, timeout: int = 300) -> Dict[str, Any]:
        """Extract video information without downloading.
        
        Args:
            url: Video URL to analyze
            timeout: Timeout in seconds for the operation
            
        Returns:
            Dictionary containing video metadata
            
        Raises:
            VideoDownloadError: If info extraction fails
        """
        try:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor, 
                    self._extract_info_sync, 
                    url
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout after {timeout}s extracting video info from {url}")
            raise VideoDownloadError(f"Timeout after {timeout}s extracting video info", url, "TIMEOUT")
        except Exception as e:
            logger.error(f"Failed to extract video info from {url}: {str(e)}")
            raise VideoDownloadError(f"Failed to extract video info: {str(e)}", url)
    
    def _extract_info_sync(self, url: str, max_retries: int = 3) -> Dict[str, Any]:
        """Synchronous video info extraction with retry logic."""
        for attempt in range(max_retries):
            try:
                logger.info(f"Extracting video info (attempt {attempt + 1}/{max_retries})")
                
                # Get enhanced options with proxy and timeout handling
                options = self._get_enhanced_options(url, use_proxy=True)
                options.update({
                    'quiet': True,
                    'no_warnings': True,
                })
                
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    # Extract relevant information
                    result = {
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'description': info.get('description'),
                        'duration': info.get('duration'),
                        'uploader': info.get('uploader'),
                        'upload_date': info.get('upload_date'),
                        'view_count': info.get('view_count'),
                        'like_count': info.get('like_count'),
                        'thumbnail': info.get('thumbnail'),
                        'webpage_url': info.get('webpage_url'),
                        'extractor': info.get('extractor'),
                        'formats': [
                            {
                                'format_id': f.get('format_id'),
                                'ext': f.get('ext'),
                                'width': f.get('width'),
                                'height': f.get('height'),
                                'filesize': f.get('filesize'),
                                'vcodec': f.get('vcodec'),
                                'acodec': f.get('acodec'),
                            }
                            for f in info.get('formats', [])
                            if f.get('vcodec') != 'none'  # Only video formats
                        ]
                    }
                    
                    logger.info(f"Successfully extracted info for video: {result.get('title', 'Unknown')}")
                    return result
                    
            except Exception as e:
                logger.error(f"yt-dlp error during info extraction (attempt {attempt + 1}): {str(e)}")
                if attempt == max_retries - 1:
                    raise e
                else:
                    # Wait before retry with exponential backoff
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger.info(f"Retrying in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
        
        raise Exception("Max retries exceeded")
    
    async def download_video(self, url: str, custom_options: Optional[Dict[str, Any]] = None, timeout: int = 600) -> Dict[str, Any]:
        """Download video from URL with timeout and retry logic.
        
        Args:
            url: Video URL to download
            custom_options: Optional custom yt-dlp options
            timeout: Timeout in seconds for the operation
            
        Returns:
            Dictionary containing download result information
            
        Raises:
            VideoDownloadError: If download fails
        """
        try:
            # Generate unique ID for this download
            download_id = str(uuid.uuid4())
            
            logger.info(f"Starting video download for URL: {url}")
            logger.info(f"Download ID: {download_id}")
            
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor,
                    self._download_sync,
                    url,
                    custom_options,
                    download_id
                ),
                timeout=timeout
            )
            
            logger.info(f"Successfully downloaded video: {result['video_info']['title']}")
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout after {timeout}s downloading video from {url}")
            raise VideoDownloadError(f"Timeout after {timeout}s downloading video", url, "TIMEOUT")
        except Exception as e:
            logger.error(f"Failed to download video from {url}: {str(e)}")
            raise VideoDownloadError(f"Failed to download video: {str(e)}", url)
    
    def _download_sync(self, url: str, custom_options: Optional[Dict[str, Any]], download_id: str, max_retries: int = 2) -> Dict[str, Any]:
        """Synchronous video download with retry logic."""
        for attempt in range(max_retries):
            downloaded_files = []
            
            try:
                logger.info(f"Downloading video (attempt {attempt + 1}/{max_retries})")
                
                # Get enhanced options with proxy and timeout handling
                options = self._get_enhanced_options(url, use_proxy=True)
                
                # Merge custom options if provided
                if custom_options:
                    options.update(custom_options)
                
                # Update output template with unique ID
                options['outtmpl'] = os.path.join(
                    self.download_dir, 
                    f'{download_id}_%(id)s.%(ext)s'
                )
                
                def progress_hook(d):
                    """Progress hook for yt-dlp."""
                    if d['status'] == 'finished':
                        downloaded_files.append(d['filename'])
                        logger.info(f"Downloaded: {d['filename']}")
                    elif d['status'] == 'downloading':
                        if 'total_bytes' in d and 'downloaded_bytes' in d:
                            percent = (d['downloaded_bytes'] / d['total_bytes']) * 100
                            logger.debug(f"Download progress: {percent:.1f}%")
                    elif d['status'] == 'error':
                        logger.error(f"Download error: {d.get('error', 'Unknown error')}")
                
                options['progress_hooks'] = [progress_hook]
                
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    # Find the main video file
                    video_file = None
                    info_file = None
                    thumbnail_file = None
                    
                    for file_path in downloaded_files:
                        if file_path.endswith('.info.json'):
                            info_file = file_path
                        elif file_path.endswith(('.jpg', '.png', '.webp')):
                            thumbnail_file = file_path
                        else:
                            video_file = file_path
                    
                    if not video_file:
                        raise VideoDownloadError("No video file was downloaded", url)
                    
                    file_size = os.path.getsize(video_file) if os.path.exists(video_file) else None
                    logger.info(f"Video file size: {file_size} bytes")
                    
                    return {
                        'download_id': download_id,
                        'video_file': video_file,
                        'info_file': info_file,
                        'thumbnail_file': thumbnail_file,
                        'video_info': {
                            'id': info.get('id'),
                            'title': info.get('title'),
                            'description': info.get('description'),
                            'duration': info.get('duration'),
                            'uploader': info.get('uploader'),
                            'upload_date': info.get('upload_date'),
                            'view_count': info.get('view_count'),
                            'like_count': info.get('like_count'),
                            'thumbnail': info.get('thumbnail'),
                            'webpage_url': info.get('webpage_url'),
                            'extractor': info.get('extractor'),
                            'file_size': file_size,
                            'file_extension': os.path.splitext(video_file)[1][1:] if video_file else None,
                        }
                    }
                    
            except Exception as e:
                logger.error(f"yt-dlp error during download (attempt {attempt + 1}): {str(e)}")
                
                # Clean up any partial downloads
                if downloaded_files:
                    self.cleanup_files(downloaded_files)
                
                if attempt == max_retries - 1:
                    raise e
                else:
                    # Wait before retry with exponential backoff
                    wait_time = (2 ** attempt) + random.uniform(0, 2)
                    logger.info(f"Retrying download in {wait_time:.1f} seconds...")
                    time.sleep(wait_time)
        
        raise Exception("Max retries exceeded")
    
    async def validate_url(self, url: str) -> bool:
        """Validate if URL is supported by yt-dlp.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL is supported, False otherwise
        """
        try:
            await self.get_video_info(url)
            return True
        except VideoDownloadError as e:
            logger.warning(f"URL validation failed for {url}: {str(e)}")
            return False
    
    def cleanup_files(self, file_paths: List[str]) -> None:
        """Clean up downloaded files.
        
        Args:
            file_paths: List of file paths to delete
        """
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup file {file_path}: {str(e)}")
    
    def get_supported_sites(self) -> List[str]:
        """Get list of supported sites.
        
        Returns:
            List of supported site names
        """
        return yt_dlp.list_extractors()


class VideoDownloadError(Exception):
    """Custom exception for video download errors."""
    
    def __init__(self, message: str, url: str = None, error_code: str = None):
        """Initialize video download error.
        
        Args:
            message: Error message
            url: URL that caused the error
            error_code: Specific error code
        """
        super().__init__(message)
        self.url = url
        self.error_code = error_code
        
    def __str__(self):
        """Return string representation of the error."""
        parts = [self.args[0]]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.error_code:
            parts.append(f"Code: {self.error_code}")
        return " | ".join(parts)
