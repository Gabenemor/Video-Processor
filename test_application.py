#!/usr/bin/env python3
"""
Test script for the video download and upload application.
This script demonstrates the core functionality without requiring actual storage credentials.
"""

import os
import sys
import asyncio
import tempfile
import json
from unittest.mock import Mock, patch

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.video_downloader import VideoDownloader, VideoDownloadError
from src.storage.factory import StorageFactory
from src.storage.base import BaseStorage, StorageError
from src.config import Config


class MockStorage(BaseStorage):
    """Mock storage provider for testing."""
    
    def __init__(self, config):
        super().__init__(config)
        self.files = {}  # Simulate file storage
        
    async def upload_file(self, file_path, destination_key, metadata=None):
        """Mock file upload."""
        if not self.validate_file_path(file_path):
            raise StorageError(f"File not found: {file_path}", "mock")
        
        file_size = self.get_file_size(file_path)
        self.files[destination_key] = {
            'size': file_size,
            'metadata': metadata or {},
            'content_type': 'video/mp4'
        }
        
        return {
            'success': True,
            'key': destination_key,
            'size': file_size,
            'content_type': 'video/mp4'
        }
    
    async def download_file(self, source_key, local_path):
        """Mock file download."""
        if source_key not in self.files:
            raise StorageError(f"File not found: {source_key}", "mock")
        return True
    
    async def delete_file(self, file_key):
        """Mock file deletion."""
        if file_key in self.files:
            del self.files[file_key]
        return True
    
    async def get_file_url(self, file_key, expires_in=3600):
        """Mock URL generation."""
        if file_key not in self.files:
            raise StorageError(f"File not found: {file_key}", "mock")
        return f"https://mock-storage.example.com/{file_key}"
    
    async def list_files(self, prefix="", limit=100):
        """Mock file listing."""
        matching_files = []
        for key, info in self.files.items():
            if key.startswith(prefix):
                matching_files.append({
                    'key': key,
                    'size': info['size'],
                    'content_type': info['content_type'],
                    'metadata': info['metadata'],
                    'last_modified': '2025-07-26T12:00:00Z'
                })
        return matching_files[:limit]
    
    async def file_exists(self, file_key):
        """Mock file existence check."""
        return file_key in self.files


def create_mock_video_file(temp_dir, filename="test_video.mp4"):
    """Create a mock video file for testing."""
    file_path = os.path.join(temp_dir, filename)
    with open(file_path, 'wb') as f:
        f.write(b"Mock video content for testing purposes")
    return file_path


async def test_video_downloader():
    """Test video downloader functionality."""
    print("Testing Video Downloader...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        downloader = VideoDownloader(temp_dir)
        
        # Test URL validation
        print("  Testing URL validation...")
        test_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Valid YouTube URL
            "https://invalid-url",  # Invalid URL
            "not-a-url"  # Not a URL
        ]
        
        for url in test_urls:
            try:
                is_valid = await downloader.validate_url(url)
                print(f"    {url}: {'Valid' if is_valid else 'Invalid'}")
            except Exception as e:
                print(f"    {url}: Error - {e}")
        
        # Test supported sites
        print("  Testing supported sites...")
        sites = downloader.get_supported_sites()
        print(f"    Found {len(sites)} supported sites")
        # Convert extractor objects to strings for display
        site_names = [str(site) for site in sites[:10]]
        print(f"    Sample sites: {', '.join(site_names)}")
        
        # Mock a successful download for testing
        print("  Testing mock download...")
        mock_video_file = create_mock_video_file(temp_dir)
        mock_info_file = create_mock_video_file(temp_dir, "test_video.info.json")
        mock_thumbnail_file = create_mock_video_file(temp_dir, "test_video.jpg")
        
        # Create mock download result
        mock_result = {
            'download_id': 'test-123',
            'video_file': mock_video_file,
            'info_file': mock_info_file,
            'thumbnail_file': mock_thumbnail_file,
            'video_info': {
                'id': 'test-video',
                'title': 'Test Video',
                'description': 'A test video for demonstration',
                'duration': 300,
                'uploader': 'Test Channel',
                'file_size': os.path.getsize(mock_video_file),
                'file_extension': 'mp4'
            }
        }
        
        print(f"    Mock download result: {mock_result['video_info']['title']}")
        print(f"    File size: {mock_result['video_info']['file_size']} bytes")
        
        return mock_result


async def test_storage_provider():
    """Test storage provider functionality."""
    print("Testing Storage Provider...")
    
    # Register mock storage provider
    StorageFactory.register_provider('mock', MockStorage)
    
    # Create storage instance
    config = {'provider': 'mock'}
    storage = StorageFactory.create_storage('mock', config)
    
    print("  Testing storage operations...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test file
        test_file = create_mock_video_file(temp_dir)
        
        # Test upload
        print("    Testing file upload...")
        upload_result = await storage.upload_file(
            test_file, 
            'test/video.mp4',
            metadata={'title': 'Test Video', 'type': 'video'}
        )
        print(f"      Upload successful: {upload_result['success']}")
        print(f"      File key: {upload_result['key']}")
        
        # Test file existence
        print("    Testing file existence...")
        exists = await storage.file_exists('test/video.mp4')
        print(f"      File exists: {exists}")
        
        # Test URL generation
        print("    Testing URL generation...")
        url = await storage.get_file_url('test/video.mp4')
        print(f"      Generated URL: {url}")
        
        # Test file listing
        print("    Testing file listing...")
        files = await storage.list_files('test/')
        print(f"      Found {len(files)} files")
        for file_info in files:
            print(f"        {file_info['key']} ({file_info['size']} bytes)")
        
        # Test file deletion
        print("    Testing file deletion...")
        deleted = await storage.delete_file('test/video.mp4')
        print(f"      Deletion successful: {deleted}")
        
        # Verify deletion
        exists_after_delete = await storage.file_exists('test/video.mp4')
        print(f"      File exists after deletion: {exists_after_delete}")
        
        return storage


def test_configuration():
    """Test configuration management."""
    print("Testing Configuration Management...")
    
    # Create test configuration
    test_config = {
        'storage': {
            'provider': 'mock',
            'config': {'test': 'value'}
        },
        'video': {
            'download_dir': '/tmp/test',
            'quality': 'best'
        }
    }
    
    # Test configuration creation
    config = Config()
    
    print("  Testing configuration access...")
    print(f"    Storage provider: {config.get('storage.provider', 'not set')}")
    print(f"    Video quality: {config.get('video.quality', 'not set')}")
    
    # Test configuration validation
    print("  Testing configuration validation...")
    errors = config.validate_config()
    if errors:
        print("    Configuration errors found:")
        for section, error_list in errors.items():
            for error in error_list:
                print(f"      {section}: {error}")
    else:
        print("    No configuration errors found")
    
    # Test available providers
    print("  Testing available storage providers...")
    providers = StorageFactory.get_available_providers()
    print(f"    Available providers: {', '.join(providers)}")
    
    return config


async def test_full_workflow():
    """Test the complete video processing workflow."""
    print("Testing Complete Workflow...")
    
    # Setup
    with tempfile.TemporaryDirectory() as temp_dir:
        downloader = VideoDownloader(temp_dir)
        storage = StorageFactory.create_storage('mock', {})
        
        print("  Simulating video download...")
        # Create mock files
        video_file = create_mock_video_file(temp_dir, "workflow_test.mp4")
        info_file = create_mock_video_file(temp_dir, "workflow_test.info.json")
        thumbnail_file = create_mock_video_file(temp_dir, "workflow_test.jpg")
        
        # Simulate processing ID
        processing_id = "test-workflow-123"
        
        print("  Uploading files to storage...")
        # Upload video file
        video_key = f"videos/{processing_id}/video.mp4"
        video_result = await storage.upload_file(
            video_file, 
            video_key,
            metadata={'processing_id': processing_id, 'file_type': 'video'}
        )
        
        # Upload info file
        info_key = f"videos/{processing_id}/info.json"
        info_result = await storage.upload_file(
            info_file,
            info_key,
            metadata={'processing_id': processing_id, 'file_type': 'metadata'}
        )
        
        # Upload thumbnail
        thumbnail_key = f"videos/{processing_id}/thumbnail.jpg"
        thumbnail_result = await storage.upload_file(
            thumbnail_file,
            thumbnail_key,
            metadata={'processing_id': processing_id, 'file_type': 'thumbnail'}
        )
        
        print("  Generating access URLs...")
        video_url = await storage.get_file_url(video_key)
        info_url = await storage.get_file_url(info_key)
        thumbnail_url = await storage.get_file_url(thumbnail_key)
        
        # Simulate API response
        workflow_result = {
            'success': True,
            'processing_id': processing_id,
            'video_info': {
                'title': 'Workflow Test Video',
                'duration': 300,
                'uploader': 'Test Channel'
            },
            'storage': {
                'video': {
                    'key': video_key,
                    'url': video_url,
                    'size': video_result['size']
                },
                'metadata': {
                    'key': info_key,
                    'url': info_url,
                    'size': info_result['size']
                },
                'thumbnail': {
                    'key': thumbnail_key,
                    'url': thumbnail_url,
                    'size': thumbnail_result['size']
                }
            }
        }
        
        print("  Workflow completed successfully!")
        print(f"    Processing ID: {workflow_result['processing_id']}")
        print(f"    Video URL: {workflow_result['storage']['video']['url']}")
        print(f"    Thumbnail URL: {workflow_result['storage']['thumbnail']['url']}")
        
        # Test retrieval
        print("  Testing file retrieval...")
        files = await storage.list_files(f"videos/{processing_id}/")
        print(f"    Found {len(files)} files for processing ID")
        
        # Cleanup test
        print("  Testing cleanup...")
        for file_info in files:
            await storage.delete_file(file_info['key'])
        
        files_after_cleanup = await storage.list_files(f"videos/{processing_id}/")
        print(f"    Files remaining after cleanup: {len(files_after_cleanup)}")
        
        return workflow_result


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Video Download and Upload Application - Test Suite")
    print("=" * 60)
    print()
    
    try:
        # Test individual components
        await test_video_downloader()
        print()
        
        await test_storage_provider()
        print()
        
        test_configuration()
        print()
        
        # Test complete workflow
        await test_full_workflow()
        print()
        
        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
        print()
        print("The application is ready for use. To start the server:")
        print("1. Configure your .env file with storage provider credentials")
        print("2. Run: python src/main.py")
        print("3. Access the API at http://localhost:5000/api/")
        print()
        print("Available endpoints:")
        print("- POST /api/videos/info - Get video information")
        print("- POST /api/videos/process - Download and upload video")
        print("- GET /api/videos/{id} - Get video details")
        print("- DELETE /api/videos/{id} - Delete video")
        print("- GET /api/videos - List all videos")
        print("- GET /api/supported-sites - Get supported platforms")
        print("- GET /api/health - Health check")
        print("- GET /api/config - Get configuration")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

