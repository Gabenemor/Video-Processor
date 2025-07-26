"""Storage factory for creating storage provider instances."""

from typing import Dict, Any, Type
from .base import BaseStorage, StorageError
from .supabase_storage import SupabaseStorage


class StorageFactory:
    """Factory class for creating storage provider instances."""
    
    # Registry of available storage providers
    _providers: Dict[str, Type[BaseStorage]] = {
        'supabase': SupabaseStorage,
    }
    
    @classmethod
    def create_storage(cls, provider: str, config: Dict[str, Any]) -> BaseStorage:
        """Create a storage provider instance.
        
        Args:
            provider: Name of the storage provider
            config: Configuration dictionary for the provider
            
        Returns:
            Storage provider instance
            
        Raises:
            StorageError: If provider is not supported or creation fails
        """
        if provider not in cls._providers:
            available_providers = ', '.join(cls._providers.keys())
            raise StorageError(
                f"Unsupported storage provider: {provider}. "
                f"Available providers: {available_providers}"
            )
        
        try:
            provider_class = cls._providers[provider]
            return provider_class(config)
        except Exception as e:
            raise StorageError(
                f"Failed to create {provider} storage instance: {str(e)}",
                provider
            )
    
    @classmethod
    def register_provider(cls, name: str, provider_class: Type[BaseStorage]) -> None:
        """Register a new storage provider.
        
        Args:
            name: Name of the provider
            provider_class: Provider class that implements BaseStorage
            
        Raises:
            StorageError: If provider class doesn't implement BaseStorage
        """
        if not issubclass(provider_class, BaseStorage):
            raise StorageError(
                f"Provider class must inherit from BaseStorage: {provider_class}"
            )
        
        cls._providers[name] = provider_class
    
    @classmethod
    def get_available_providers(cls) -> list[str]:
        """Get list of available storage providers.
        
        Returns:
            List of provider names
        """
        return list(cls._providers.keys())
    
    @classmethod
    def is_provider_supported(cls, provider: str) -> bool:
        """Check if a storage provider is supported.
        
        Args:
            provider: Name of the provider to check
            
        Returns:
            True if provider is supported, False otherwise
        """
        return provider in cls._providers


# Example of how to add a new storage provider:
# 
# class GoogleCloudStorage(BaseStorage):
#     def __init__(self, config: Dict[str, Any]):
#         super().__init__(config)
#         # Initialize Google Cloud Storage client
#         pass
#     
#     async def upload_file(self, file_path: str, destination_key: str, 
#                          metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
#         # Implement Google Cloud Storage upload
#         pass
#     
#     # ... implement other required methods
# 
# # Register the new provider
# StorageFactory.register_provider('gcs', GoogleCloudStorage)


# Example of how to add Amazon S3 storage provider:
#
# class S3Storage(BaseStorage):
#     def __init__(self, config: Dict[str, Any]):
#         super().__init__(config)
#         import boto3
#         self.s3_client = boto3.client(
#             's3',
#             aws_access_key_id=config['access_key'],
#             aws_secret_access_key=config['secret_key'],
#             region_name=config.get('region', 'us-east-1')
#         )
#         self.bucket_name = config['bucket_name']
#     
#     async def upload_file(self, file_path: str, destination_key: str, 
#                          metadata: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
#         # Implement S3 upload using boto3
#         pass
#     
#     # ... implement other required methods
#
# # Register the S3 provider
# StorageFactory.register_provider('s3', S3Storage)

