"""Streaming uploader implementation for direct upload from memory."""

import os
import io
import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, BinaryIO, Callable

from src.base import StorageError
from src.config import get_config

logger = logging.getLogger(__name__)

class StreamingUploader:
    """Base class for streaming upload implementations."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the streaming uploader."""
        self.config = config
        self.chunk_size = config.get('chunk_size', 5 * 1024 * 1024)  # 5MB chunks by default
    
    async def upload_stream(self, 
                           file_stream: BinaryIO, 
                           destination_key: str,
                           content_type: str,
                           metadata: Optional[Dict[str, str]] = None,
                           progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
        """Upload a file stream to storage.
        
        Args:
            file_stream: File-like object to read from
            destination_key: Key/path where the file will be stored
            content_type: Content type of the file
            metadata: Optional metadata to associate with the file
            progress_callback: Optional callback function (bytes_uploaded, total_bytes)
            
        Returns:
            Dictionary containing upload result information
            
        Raises:
            StorageError: If upload fails
        """
        raise NotImplementedError("Subclasses must implement upload_stream")

class SupabaseStreamingUploader(StreamingUploader):
    """Supabase streaming upload implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Supabase streaming uploader."""
        super().__init__(config)
        self.url = config.get('url')
        self.key = config.get('key')
        self.bucket_name = config.get('bucket_name')
        
        if not self.url or not self.key or not self.bucket_name:
            raise StorageError("Missing required Supabase configuration", "supabase_stream")
    
    async def upload_stream(self, 
                           file_stream: BinaryIO, 
                           destination_key: str,
                           content_type: str,
                           metadata: Optional[Dict[str, str]] = None,
                           progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
        """Upload a file stream to Supabase storage.
        
        Args:
            file_stream: File-like object to read from
            destination_key: Key/path where the file will be stored
            content_type: Content type of the file
            metadata: Optional metadata to associate with the file
            progress_callback: Optional callback function (bytes_uploaded, total_bytes)
            
        Returns:
            Dictionary containing upload result information
            
        Raises:
            StorageError: If upload fails
        """
        try:
            # Determine content length if possible
            content_length = None
            if hasattr(file_stream, 'seek') and hasattr(file_stream, 'tell'):
                try:
                    current_pos = file_stream.tell()
                    file_stream.seek(0, os.SEEK_END)
                    content_length = file_stream.tell()
                    file_stream.seek(current_pos)
                except (OSError, IOError):
                    # Stream doesn't support seeking
                    pass
            
            # Prepare headers
            headers = {
                'Authorization': f'Bearer {self.key}',
                'Content-Type': content_type,
                'x-upsert': 'true'  # Overwrite if exists
            }
            
            # Add metadata headers if provided
            if metadata:
                for key, value in metadata.items():
                    headers[f'x-amz-meta-{key}'] = str(value)
            
            # Set content length if known
            if content_length is not None:
                headers['Content-Length'] = str(content_length)
            
            # Prepare upload URL
            upload_url = f"{self.url}/storage/v1/object/{self.bucket_name}/{destination_key}"
            
            # Create a buffer for streaming data
            bytes_uploaded = 0
            
            async with aiohttp.ClientSession() as session:
                async with session.put(upload_url, headers=headers) as response:
                    # Create a StreamReader from the file stream
                    reader = aiohttp.StreamReader(protocol=None)
                    
                    # Read in chunks and write to the request
                    chunk = file_stream.read(self.chunk_size)
                    while chunk:
                        reader.feed_data(chunk)
                        await response.write(chunk)
                        
                        # Update progress
                        bytes_uploaded += len(chunk)
                        if progress_callback:
                            progress_callback(bytes_uploaded, content_length)
                        
                        # Read next chunk
                        chunk = file_stream.read(self.chunk_size)
                    
                    # Mark end of stream
                    reader.feed_eof()
                    await response.write_eof()
                    
                    # Check response
                    if response.status not in (200, 201):
                        response_text = await response.text()
                        raise StorageError(f"Upload failed with status {response.status}: {response_text}", "supabase_stream")
                    
                    result = await response.json()
                
                # Return upload result
                return {
                    'success': True,
                    'key': destination_key,
                    'bucket': self.bucket_name,
                    'size': bytes_uploaded,
                    'content_type': content_type,
                    'metadata': metadata,
                    'result': result
                }
                
        except Exception as e:
            logger.error(f"Failed to stream upload to Supabase: {str(e)}")
            raise StorageError(f"Streaming upload failed: {str(e)}", "supabase_stream")


def create_streaming_uploader(provider: str = None) -> StreamingUploader:
    """Factory function to create a streaming uploader.
    
    Args:
        provider: Storage provider name. If None, uses the configured provider.
        
    Returns:
        StreamingUploader instance
    """
    config = get_config()
    storage_config = config.get_storage_config()
    provider = provider or storage_config.get('provider', 'supabase')
    provider_config = storage_config.get('config', {})
    
    if provider == 'supabase':
        return SupabaseStreamingUploader(provider_config)
    else:
        raise ValueError(f"Unsupported storage provider for streaming: {provider}")
