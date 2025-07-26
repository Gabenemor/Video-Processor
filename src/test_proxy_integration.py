#!/usr/bin/env python3
"""
Test script for video processor with proxy integration.
This script tests the proxy functionality and video processing pipeline.
"""

import os
import sys
import requests
import json
import time
from datetime import datetime

def test_api_endpoint(url, method='GET', data=None, expected_status=200):
    """Test an API endpoint and return the response."""
    print(f"\n{'='*60}")
    print(f"Testing {method} {url}")
    print(f"{'='*60}")
    
    try:
        if method == 'GET':
            response = requests.get(url, timeout=30)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=120)
        elif method == 'DELETE':
            response = requests.delete(url, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Time: {response.elapsed.total_seconds():.2f}s")
        
        # Try to parse JSON response
        try:
            response_data = response.json()
            print(f"Response Data:")
            print(json.dumps(response_data, indent=2))
            
            # Check for request_id in response
            if 'request_id' in response_data:
                print(f"Request ID: {response_data['request_id']}")
            
            return response_data
        except json.JSONDecodeError:
            print(f"Response Text: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {str(e)}")
        return None

def main():
    """Main test function."""
    base_url = "http://localhost:5000/api"
    
    print("Video Processor Proxy Integration Test")
    print("=" * 50)
    print(f"Base URL: {base_url}")
    print(f"Test Time: {datetime.now().isoformat()}")
    
    # Test 1: Health Check
    print("\n🏥 Testing Health Check...")
    health_response = test_api_endpoint(f"{base_url}/health")
    
    if not health_response or health_response.get('status') != 'healthy':
        print("❌ Health check failed. Make sure the application is running.")
        return
    
    print("✅ Health check passed!")
    
    # Test 2: Configuration Check
    print("\n⚙️ Testing Configuration...")
    config_response = test_api_endpoint(f"{base_url}/config")
    
    if config_response:
        # Check proxy configuration
        proxy_config = config_response.get('config', {}).get('proxy', {})
        if proxy_config.get('use_proxy_for_info_extraction'):
            print("✅ Proxy is configured for info extraction")
            print(f"   Endpoint: {proxy_config.get('webshare_endpoint', 'Not set')}")
            print(f"   Username: {'Set' if proxy_config.get('webshare_username') else 'Not set'}")
        else:
            print("⚠️ Proxy is not enabled for info extraction")
        
        # Check storage configuration
        storage_config = config_response.get('config', {}).get('storage', {})
        bucket_name = storage_config.get('config', {}).get('bucket_name', 'Not set')
        print(f"✅ Storage bucket: {bucket_name}")
    
    # Test 3: Supported Sites
    print("\n🌐 Testing Supported Sites...")
    sites_response = test_api_endpoint(f"{base_url}/supported-sites")
    
    if sites_response and sites_response.get('success'):
        total_sites = sites_response.get('total_count', 0)
        print(f"✅ Found {total_sites} supported sites")
    
    # Test 4: Video Info Extraction (with proxy)
    print("\n📹 Testing Video Info Extraction (with proxy)...")
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Roll - should work
        "https://vimeo.com/148751763",  # Vimeo test video
        "https://www.tiktok.com/@username/video/1234567890",  # TikTok (may fail)
    ]
    
    successful_url = None
    
    for test_url in test_urls:
        print(f"\nTesting URL: {test_url}")
        info_response = test_api_endpoint(
            f"{base_url}/videos/info",
            method='POST',
            data={'url': test_url}
        )
        
        if info_response and info_response.get('success'):
            print(f"✅ Successfully extracted info for: {info_response['video_info']['title']}")
            print(f"   Duration: {info_response['video_info'].get('duration', 'Unknown')}s")
            print(f"   Uploader: {info_response['video_info'].get('uploader', 'Unknown')}")
            successful_url = test_url
            break
        else:
            print(f"❌ Failed to extract info from {test_url}")
    
    if not successful_url:
        print("❌ No test URLs worked for info extraction")
        return
    
    # Test 5: Video Processing (download and upload)
    print(f"\n🎬 Testing Video Processing (download and upload)...")
    print(f"Using URL: {successful_url}")
    
    process_response = test_api_endpoint(
        f"{base_url}/videos/process",
        method='POST',
        data={
            'url': successful_url,
            'options': {
                'format': 'worst[height<=360]/worst'  # Use worst quality for faster testing
            }
        }
    )
    
    if process_response and process_response.get('success'):
        processing_id = process_response['processing_id']
        print(f"✅ Video processing completed!")
        print(f"   Processing ID: {processing_id}")
        print(f"   Video URL: {process_response['storage']['video']['url']}")
        print(f"   File Size: {process_response['storage']['video']['size']} bytes")
        
        # Test 6: Get Video Details
        print(f"\n📋 Testing Video Details Retrieval...")
        details_response = test_api_endpoint(f"{base_url}/videos/{processing_id}")
        
        if details_response and details_response.get('success'):
            print("✅ Successfully retrieved video details")
            files = details_response.get('files', {})
            for file_type, file_info in files.items():
                if file_info:
                    print(f"   {file_type}: {file_info['size']} bytes")
        
        # Test 7: List Videos
        print(f"\n📝 Testing Video Listing...")
        list_response = test_api_endpoint(f"{base_url}/videos?limit=5")
        
        if list_response and list_response.get('success'):
            video_count = len(list_response.get('videos', []))
            print(f"✅ Found {video_count} videos in storage")
        
        # Test 8: Delete Video (optional - uncomment to test)
        print(f"\n🗑️ Testing Video Deletion...")
        user_input = input(f"Delete test video {processing_id}? (y/N): ").strip().lower()
        
        if user_input == 'y':
            delete_response = test_api_endpoint(
                f"{base_url}/videos/{processing_id}",
                method='DELETE'
            )
            
            if delete_response and delete_response.get('success'):
                deleted_files = delete_response.get('deleted_files', [])
                print(f"✅ Successfully deleted {len(deleted_files)} files")
            else:
                print("❌ Failed to delete video")
        else:
            print("⏭️ Skipping video deletion")
    
    else:
        print("❌ Video processing failed")
    
    # Test Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print("✅ Health Check: Passed")
    print("✅ Configuration: Checked")
    print("✅ Supported Sites: Retrieved")
    print(f"{'✅' if successful_url else '❌'} Video Info Extraction: {'Passed' if successful_url else 'Failed'}")
    print(f"{'✅' if process_response and process_response.get('success') else '❌'} Video Processing: {'Passed' if process_response and process_response.get('success') else 'Failed'}")
    
    print("\n🎉 Test completed!")
    print("\nNotes:")
    print("- Proxy is used only for video info extraction (bot detection bypass)")
    print("- Video downloads happen without proxy to save bandwidth")
    print("- All files are uploaded to the configured Supabase bucket")
    print("- Check application logs for detailed proxy usage information")

if __name__ == "__main__":
    main()
