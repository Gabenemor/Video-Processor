# Video Processor Timeout and Stuck Task Fixes

## Overview
This document summarizes the comprehensive fixes implemented to resolve the stuck task issue where video processing tasks would hang indefinitely during YouTube metadata extraction.

## Root Cause Analysis
The original issue occurred because:
1. **YouTube Bot Detection**: Tasks were getting stuck during metadata extraction due to YouTube's anti-bot measures
2. **Missing Timeout Controls**: No timeout mechanisms were in place, causing infinite hangs
3. **Ineffective Proxy Usage**: Proxy was not being used consistently for YouTube URLs
4. **No Retry Logic**: Failed tasks had no retry mechanisms
5. **Insufficient Server Timeouts**: Gunicorn timeout was too short for long-running tasks

## Implemented Solutions

### 1. Enhanced Video Downloader (`src/video_downloader.py`)

#### Anti-Bot Detection Improvements:
- **User Agent Rotation**: Added 5 different user agents that rotate on each request
- **Forced YouTube Proxy**: Automatically uses proxy for all YouTube URLs regardless of global proxy setting
- **Sleep Intervals**: Added randomized delays between requests (1-3 seconds)
- **YouTube-Specific Options**: Enhanced extractor arguments for better YouTube compatibility

#### Timeout Controls:
- **Socket Timeout**: 30 seconds for network operations
- **Info Extraction Timeout**: 300 seconds (5 minutes) with configurable override
- **Download Timeout**: 600 seconds (10 minutes) with configurable override
- **Fragment Retries**: 3 attempts for partial download failures
- **Overall Retries**: 3 attempts with exponential backoff

#### Proxy Enhancements:
- **Smart Proxy Detection**: Automatically determines when to use proxy based on URL
- **Proxy Health Checks**: Validates proxy configuration before use
- **Enhanced Error Handling**: Better error messages and fallback mechanisms

### 2. Enhanced Task Processing (`src/tasks.py`)

#### Timeout Management:
- **Stage-by-Stage Timeouts**: Separate timeouts for download, upload, and URL generation
- **Configurable Timeouts**: All timeouts can be set via environment variables
- **Timeout Hierarchy**: Overall task timeout with per-stage granular controls

#### Retry Logic:
- **Smart Retry**: Only retries on timeout, network, or storage errors
- **Exponential Backoff**: Increasing delays between retry attempts
- **Retry Limits**: Maximum 2 retries per task (configurable)
- **Error Classification**: Different handling for different error types

#### Enhanced Logging:
- **Request Tracking**: Unique processing IDs for each task
- **Stage Logging**: Detailed logs for each processing stage
- **Error Tracebacks**: Full stack traces for debugging
- **Performance Metrics**: Timing information for each stage

### 3. Configuration Enhancements (`src/config.py`)

#### New Timeout Configuration Section:
```python
'timeout': {
    'info_extraction': 300,  # 5 minutes
    'download': 900,         # 15 minutes  
    'upload': 600,           # 10 minutes
    'socket': 30,            # 30 seconds
    'max_retries': 2,        # Maximum retries
}
```

#### Environment Variable Support:
- `INFO_EXTRACTION_TIMEOUT`: Info extraction timeout in seconds
- `DOWNLOAD_TIMEOUT`: Download timeout in seconds
- `UPLOAD_TIMEOUT`: Upload timeout in seconds
- `SOCKET_TIMEOUT`: Socket timeout in seconds
- `MAX_RETRIES`: Maximum retry attempts

### 4. Server Configuration (`start.sh`)

#### Gunicorn Improvements:
- **Increased Timeout**: From 300 to 1800 seconds (30 minutes)
- **Worker Configuration**: 2 workers with sync worker class
- **Better Resource Management**: Improved handling of long-running requests

## Key Features Added

### 1. Comprehensive Timeout System
- **Multi-Level Timeouts**: Socket, stage, and overall task timeouts
- **Configurable Limits**: All timeouts can be adjusted via environment variables
- **Graceful Handling**: Proper cleanup on timeout with clear error messages

### 2. Intelligent Retry Mechanism
- **Error-Based Retries**: Only retries on recoverable errors (timeouts, network issues)
- **Exponential Backoff**: Prevents overwhelming services with immediate retries
- **Retry Tracking**: Database tracking of retry attempts

### 3. Enhanced Proxy System
- **YouTube-Specific**: Automatically uses proxy for YouTube URLs
- **Health Validation**: Checks proxy configuration before use
- **Fallback Handling**: Graceful degradation when proxy fails

### 4. Improved Error Handling
- **Detailed Logging**: Comprehensive error tracking with stack traces
- **Error Classification**: Different handling for different error types
- **Webhook Notifications**: Proper error reporting to webhook endpoints

## Environment Variables

### Required for Proxy (if using):
```bash
WEBSHARE_USERNAME=your_username
WEBSHARE_PASSWORD=your_password
WEBSHARE_ENDPOINT=p.webshare.io:80
USE_PROXY=true
```

### Optional Timeout Configuration:
```bash
INFO_EXTRACTION_TIMEOUT=300
DOWNLOAD_TIMEOUT=900
UPLOAD_TIMEOUT=600
SOCKET_TIMEOUT=30
MAX_RETRIES=2
```

## Testing Recommendations

### 1. Test with Problematic YouTube URLs
- Use the Rick Roll URL that was failing: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
- Monitor logs for proxy usage and timeout handling

### 2. Monitor Task Processing
- Check task status endpoints regularly
- Verify retry logic is working correctly
- Ensure webhooks are called on both success and failure

### 3. Load Testing
- Test with multiple concurrent tasks
- Verify timeout handling under load
- Check resource cleanup after failures

## Expected Behavior

### 1. YouTube URL Processing
- Should automatically use proxy for YouTube URLs
- Should complete within configured timeouts
- Should retry on timeout/network errors

### 2. Task Status Transitions
- `queued` → `processing` → `completed` (success path)
- `queued` → `processing` → `queued` (retry path)
- `queued` → `processing` → `failed` (final failure)

### 3. Logging Output
- Should see proxy usage logs for YouTube URLs
- Should see stage-by-stage progress logs
- Should see retry attempts with backoff delays

## Monitoring

### Key Metrics to Watch:
- Task completion rates
- Average processing times
- Retry frequencies
- Timeout occurrences
- Proxy usage statistics

### Log Patterns to Monitor:
- `[processing_id] Stage X: ...` - Progress tracking
- `Using proxy for request` - Proxy usage
- `Retrying in X seconds...` - Retry attempts
- `Timeout during video processing` - Timeout occurrences

## Deployment Notes

1. **Environment Variables**: Ensure all proxy and timeout variables are set
2. **Resource Allocation**: Increase Cloud Run timeout and memory if needed
3. **Monitoring**: Set up alerts for high failure rates or timeout frequencies
4. **Testing**: Run test jobs after deployment to verify fixes

This comprehensive solution addresses the root causes of stuck tasks while adding robust error handling, retry logic, and monitoring capabilities.
