"""Supabase storage implementation."""

import os
import asyncio
from typing import Dict, Any, Optional, List
from supabase import create_client, Client
from .base import BaseStorage, StorageError
import logging

logger = logging.getLogger(__name__)


class SupabaseStorage(BaseStorage):
    """Supabase storage provider implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize Supabase storage.
        
        Args:
            config: Configuration dictionary containing:
                - url: Supabase project URL
                - key: Supabase service role key
                - bucket_name: Storage bucket name
        """
        super().__init__(config)
        
        # Validate required configuration
        required_keys = ['url', 'key', 'bucket_name']
        for key in required_keys:
            if key not in config:
                raise StorageError(f"Missing required configuration: {key}", "supabase")
        
        self.url = config['url']
        self.key = config['key']
        self.bucket_name = config['bucket_name']
        
        # Initialize Supabase client
        try:
            self.client: Client = create_client(self.url, self.key)
            self.storage = self.client.storage
        except Exception as e:
            raise StorageError(f"Failed to initialize Supabase client: {str(e)}", "supabase")
    
    async def upload_file(self, file_path: str, destination_key: str, 
                         metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload a local file to Supabase storage.
        
        Args:
            file_path: Path to the local file to upload
            destination_key: Key/path where the file will be stored
            metadata: Optional metadata to associate with the file
            
        Returns:
            Dictionary containing upload result information
            
        Raises:
            StorageError: If upload fails
        """
        if not self.validate_file_path(file_path):
            raise StorageError(f"File not found or not readable: {file_path}", "supabase")
        
        try:
            # Read file content
            with open(file_path, 'rb') as file:
                file_content = file.read()
            
            # Prepare upload options
            file_options = {}
            if metadata:
                file_options['metadata'] = metadata
            
            # Determine content type based on file extension
            file_ext = os.path.splitext(file_path)[1].lower()
            content_type_map = {
                '.mp4': 'video/mp4',
                '.avi': 'video/x-msvideo',
                '.mov': 'video/quicktime',
                '.wmv': 'video/x-ms-wmv',
                '.flv': 'video/x-flv',
                '.webm': 'video/webm',
                '.mkv': 'video/x-matroska',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.json': 'application/json',
            }
            
            if file_ext in content_type_map:
                file_options['content_type'] = content_type_map[file_ext]
            
            # Upload file to Supabase storage
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._upload_sync,
                file_content,
                destination_key,
                file_options
            )
            
            return {
                'success': True,
                'key': destination_key,
                'bucket': self.bucket_name,
                'size': len(file_content),
                'content_type': file_options.get('content_type'),
                'metadata': metadata,
                'supabase_result': result
            }
            
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} to Supabase: {str(e)}")
            raise StorageError(f"Upload failed: {str(e)}", "supabase")
    
    def _upload_sync(self, file_content: bytes, destination_key: str, file_options: Dict[str, Any]):
        """Synchronous file upload to Supabase."""
        return self.storage.from_(self.bucket_name).upload(
            path=destination_key,
            file=file_content,
            file_options=file_options
        )
    
    async def download_file(self, source_key: str, local_path: str) -> bool:
        """Download a file from Supabase storage to local filesystem.
        
        Args:
            source_key: Key/path of the file in storage
            local_path: Local path where the file will be saved
            
        Returns:
            True if download successful, False otherwise
            
        Raises:
            StorageError: If download fails
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Download file from Supabase
            loop = asyncio.get_event_loop()
            file_content = await loop.run_in_executor(
                None,
                self._download_sync,
                source_key
            )
            
            # Write to local file
            with open(local_path, 'wb') as file:
                file.write(file_content)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to download file {source_key} from Supabase: {str(e)}")
            raise StorageError(f"Download failed: {str(e)}", "supabase")
    
    def _download_sync(self, source_key: str) -> bytes:
        """Synchronous file download from Supabase."""
        response = self.storage.from_(self.bucket_name).download(source_key)
        return response
    
    async def delete_file(self, file_key: str) -> bool:
        """Delete a file from Supabase storage.
        
        Args:
            file_key: Key/path of the file to delete
            
        Returns:
            True if deletion successful, False otherwise
            
        Raises:
            StorageError: If deletion fails
        """
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._delete_sync,
                file_key
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_key} from Supabase: {str(e)}")
            raise StorageError(f"Delete failed: {str(e)}", "supabase")
    
    def _delete_sync(self, file_key: str):
        """Synchronous file deletion from Supabase."""
        return self.storage.from_(self.bucket_name).remove([file_key])
    
    async def get_file_url(self, file_key: str, expires_in: int = 3600) -> str:
        """Get a public or signed URL for file access.
        
        Args:
            file_key: Key/path of the file
            expires_in: URL expiration time in seconds (for signed URLs)
            
        Returns:
            Public or signed URL for the file
            
        Raises:
            StorageError: If URL generation fails
        """
        try:
            loop = asyncio.get_event_loop()
            url = await loop.run_in_executor(
                None,
                self._get_url_sync,
                file_key,
                expires_in
            )
            
            return url
            
        except Exception as e:
            logger.error(f"Failed to get URL for file {file_key} from Supabase: {str(e)}")
            raise StorageError(f"URL generation failed: {str(e)}", "supabase")
    
    def _get_url_sync(self, file_key: str, expires_in: int) -> str:
        """Synchronous URL generation from Supabase."""
        # Try to get public URL first
        try:
            public_url = self.storage.from_(self.bucket_name).get_public_url(file_key)
            return public_url
        except:
            # Fall back to signed URL if public URL fails
            signed_url = self.storage.from_(self.bucket_name).create_signed_url(
                file_key, expires_in
            )
            return signed_url['signedURL']
    
    async def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """List files in Supabase storage with optional prefix filtering.
        
        Args:
            prefix: Optional prefix to filter files
            limit: Maximum number of files to return
            
        Returns:
            List of dictionaries containing file information
            
        Raises:
            StorageError: If listing fails
        """
        try:
            loop = asyncio.get_event_loop()
            files = await loop.run_in_executor(
                None,
                self._list_sync,
                prefix,
                limit
            )
            
            # Format file information
            formatted_files = []
            for file_info in files:
                formatted_files.append({
                    'key': file_info.get('name'),
                    'size': file_info.get('metadata', {}).get('size'),
                    'last_modified': file_info.get('updated_at'),
                    'content_type': file_info.get('metadata', {}).get('mimetype'),
                    'metadata': file_info.get('metadata', {}),
                })
            
            return formatted_files
            
        except Exception as e:
            logger.error(f"Failed to list files from Supabase: {str(e)}")
            raise StorageError(f"List failed: {str(e)}", "supabase")
    
    def _list_sync(self, prefix: str, limit: int):
        """Synchronous file listing from Supabase."""
        options = {'limit': limit}
        if prefix:
            options['prefix'] = prefix
        
        return self.storage.from_(self.bucket_name).list(
            path=prefix if prefix else None,
            options=options
        )
    
    async def file_exists(self, file_key: str) -> bool:
        """Check if a file exists in Supabase storage.
        
        Args:
            file_key: Key/path of the file to check
            
        Returns:
            True if file exists, False otherwise
            
        Raises:
            StorageError: If check fails
        """
        try:
            # Try to get file info to check existence
            files = await self.list_files(prefix=file_key, limit=1)
            return any(f['key'] == file_key for f in files)
            
        except Exception as e:
            logger.error(f"Failed to check file existence {file_key} in Supabase: {str(e)}")
            raise StorageError(f"Existence check failed: {str(e)}", "supabase")
    
    async def create_bucket_if_not_exists(self) -> bool:
        """Create the storage bucket if it doesn't exist.
        
        Returns:
            True if bucket was created or already exists, False otherwise
        """
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._create_bucket_sync
            )
            return True
            
        except Exception as e:
            logger.warning(f"Failed to create bucket {self.bucket_name}: {str(e)}")
            return False
    
    def _create_bucket_sync(self):
        """Synchronous bucket creation."""
        return self.storage.create_bucket(self.bucket_name, options={'public': False})

