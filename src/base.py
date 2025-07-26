"""Base storage interface for all storage providers."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import os


class BaseStorage(ABC):
    """Abstract base class for storage providers."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize storage provider with configuration.
        
        Args:
            config: Configuration dictionary containing provider-specific settings
        """
        self.config = config
    
    @abstractmethod
    async def upload_file(self, file_path: str, destination_key: str, 
                         metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Upload a local file to storage.
        
        Args:
            file_path: Path to the local file to upload
            destination_key: Key/path where the file will be stored
            metadata: Optional metadata to associate with the file
            
        Returns:
            Dictionary containing upload result information
            
        Raises:
            StorageError: If upload fails
        """
        pass
    
    @abstractmethod
    async def download_file(self, source_key: str, local_path: str) -> bool:
        """Download a file from storage to local filesystem.
        
        Args:
            source_key: Key/path of the file in storage
            local_path: Local path where the file will be saved
            
        Returns:
            True if download successful, False otherwise
            
        Raises:
            StorageError: If download fails
        """
        pass
    
    @abstractmethod
    async def delete_file(self, file_key: str) -> bool:
        """Delete a file from storage.
        
        Args:
            file_key: Key/path of the file to delete
            
        Returns:
            True if deletion successful, False otherwise
            
        Raises:
            StorageError: If deletion fails
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def list_files(self, prefix: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """List files in storage with optional prefix filtering.
        
        Args:
            prefix: Optional prefix to filter files
            limit: Maximum number of files to return
            
        Returns:
            List of dictionaries containing file information
            
        Raises:
            StorageError: If listing fails
        """
        pass
    
    @abstractmethod
    async def file_exists(self, file_key: str) -> bool:
        """Check if a file exists in storage.
        
        Args:
            file_key: Key/path of the file to check
            
        Returns:
            True if file exists, False otherwise
            
        Raises:
            StorageError: If check fails
        """
        pass
    
    def get_file_size(self, file_path: str) -> int:
        """Get the size of a local file in bytes.
        
        Args:
            file_path: Path to the local file
            
        Returns:
            File size in bytes
        """
        return os.path.getsize(file_path)
    
    def validate_file_path(self, file_path: str) -> bool:
        """Validate that a file path exists and is readable.
        
        Args:
            file_path: Path to validate
            
        Returns:
            True if file exists and is readable, False otherwise
        """
        return os.path.exists(file_path) and os.path.isfile(file_path)


class StorageError(Exception):
    """Custom exception for storage-related errors."""
    
    def __init__(self, message: str, provider: str = None, error_code: str = None):
        """Initialize storage error.
        
        Args:
            message: Error message
            provider: Storage provider name
            error_code: Provider-specific error code
        """
        super().__init__(message)
        self.provider = provider
        self.error_code = error_code
        
    def __str__(self):
        """Return string representation of the error."""
        parts = [self.args[0]]
        if self.provider:
            parts.append(f"Provider: {self.provider}")
        if self.error_code:
            parts.append(f"Code: {self.error_code}")
        return " | ".join(parts)

