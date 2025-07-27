"""Configuration management for video processor application."""

import os
import json
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for managing application settings."""
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration.
        
        Args:
            config_file: Optional path to JSON configuration file
        """
        self.config_file = config_file
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from environment variables and config file."""
        config = {
            # Flask configuration
            'flask': {
                'secret_key': os.getenv('FLASK_SECRET_KEY', 'asdf#FGSgvasgf$5$WGT'),
                'debug': os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
                'host': os.getenv('FLASK_HOST', '0.0.0.0'),
                'port': int(os.getenv('PORT', '8080')),
            },
            
            # Storage configuration
            'storage': {
                'provider': os.getenv('STORAGE_PROVIDER', 'supabase'),
                'config': self._get_storage_config()
            },
            
            # Video download configuration
            'video': {
                'download_dir': os.getenv('VIDEO_DOWNLOAD_DIR', '/tmp/video_downloads'),
                'max_file_size': int(os.getenv('MAX_FILE_SIZE', '1073741824')),  # 1GB default
                'allowed_formats': os.getenv('ALLOWED_FORMATS', 'mp4,avi,mov,wmv,flv,webm,mkv').split(','),
                'quality': os.getenv('VIDEO_QUALITY', 'best[height<=720]/best'),
            },
            
            # Proxy configuration
            'proxy': {
                'webshare_username': os.getenv('WEBSHARE_USERNAME'),
                'webshare_password': os.getenv('WEBSHARE_PASSWORD'),
                'webshare_endpoint': os.getenv('WEBSHARE_ENDPOINT', 'p.webshare.io:80'),
                'use_proxy': os.getenv('USE_PROXY', 'true').lower() == 'true',
                'youtube_po_token': os.getenv('YOUTUBE_PO_TOKEN'),  # PO token for YouTube
            },
            
            # Timeout configuration
            'timeout': {
                'info_extraction': int(os.getenv('INFO_EXTRACTION_TIMEOUT', '300')),  # 5 minutes
                'download': int(os.getenv('DOWNLOAD_TIMEOUT', '900')),  # 15 minutes
                'upload': int(os.getenv('UPLOAD_TIMEOUT', '600')),  # 10 minutes
                'socket': int(os.getenv('SOCKET_TIMEOUT', '30')),  # 30 seconds
                'max_retries': int(os.getenv('MAX_RETRIES', '2')),  # Maximum retries
            },
            
            # Logging configuration
            'logging': {
                'level': os.getenv('LOG_LEVEL', 'INFO'),
                'format': os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
                'file': os.getenv('LOG_FILE', None),
            },

            # Database configuration
            'database': {
                'url': os.getenv('DATABASE_URL', 'postgresql://postgres:M64LX!YcFtzBBx$@db.tnjpitcbpfuwtzakayat.supabase.co:5432/postgres'),
            }
        }
        
        # Load additional configuration from file if provided
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    file_config = json.load(f)
                    config = self._merge_configs(config, file_config)
            except Exception as e:
                print(f"Warning: Failed to load config file {self.config_file}: {e}")
        
        return config
    
    def _get_storage_config(self) -> Dict[str, Any]:
        """Get storage provider configuration based on selected provider."""
        provider = os.getenv('STORAGE_PROVIDER', 'supabase')
        
        if provider == 'supabase':
            return {
                'url': os.getenv('SUPABASE_URL'),
                'key': os.getenv('SUPABASE_SERVICE_ROLE_KEY'),
                'bucket_name': os.getenv('SUPABASE_BUCKET_NAME', 'videos'),
            }
        elif provider == 's3':
            return {
                'access_key': os.getenv('AWS_ACCESS_KEY_ID'),
                'secret_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
                'bucket_name': os.getenv('S3_BUCKET_NAME'),
                'region': os.getenv('AWS_REGION', 'us-east-1'),
            }
        elif provider == 'gcs':
            return {
                'project_id': os.getenv('GCS_PROJECT_ID'),
                'credentials_path': os.getenv('GCS_CREDENTIALS_PATH'),
                'bucket_name': os.getenv('GCS_BUCKET_NAME'),
            }
        else:
            return {}
    
    def _merge_configs(self, base_config: Dict[str, Any], file_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge file configuration with base configuration."""
        for key, value in file_config.items():
            if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
                base_config[key] = self._merge_configs(base_config[key], value)
            else:
                base_config[key] = value
        return base_config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key.
        
        Args:
            key: Configuration key (supports dot notation, e.g., 'storage.provider')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value by key.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def get_flask_config(self) -> Dict[str, Any]:
        """Get Flask-specific configuration."""
        return self.get('flask', {})
    
    def get_storage_config(self) -> Dict[str, Any]:
        """Get storage configuration."""
        return self.get('storage', {})
    
    def get_video_config(self) -> Dict[str, Any]:
        """Get video processing configuration."""
        return self.get('video', {})
    
    def get_proxy_config(self) -> Dict[str, Any]:
        """Get proxy configuration."""
        return self.get('proxy', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration."""
        return self.get('logging', {})

    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return self.get('database', {})
    
    def validate_config(self) -> Dict[str, list]:
        """Validate configuration and return any errors.
        
        Returns:
            Dictionary with validation errors by section
        """
        errors = {}
        
        # Validate storage configuration
        storage_errors = []
        storage_config = self.get_storage_config()
        provider = storage_config.get('provider')
        
        if not provider:
            storage_errors.append("Storage provider not specified")
        elif provider == 'supabase':
            config = storage_config.get('config', {})
            if not config.get('url') or not config['url'].strip():
                storage_errors.append("Supabase URL not configured or empty")
            if not config.get('key') or not config['key'].strip():
                storage_errors.append("Supabase service role key not configured or empty")
            if not config.get('bucket_name') or not config['bucket_name'].strip():
                storage_errors.append("Supabase bucket name not configured or empty")
        elif provider == 's3':
            config = storage_config.get('config', {})
            if not config.get('access_key'):
                storage_errors.append("AWS access key not configured")
            if not config.get('secret_key'):
                storage_errors.append("AWS secret key not configured")
            if not config.get('bucket_name'):
                storage_errors.append("S3 bucket name not configured")
        
        if storage_errors:
            errors['storage'] = storage_errors
        
        # Validate database configuration
        db_errors = []
        db_config = self.get_database_config()
        if not db_config.get('url'):
            db_errors.append("Database URL not configured")
        
        if db_errors:
            errors['database'] = db_errors

        # Validate proxy configuration
        proxy_errors = []
        proxy_config = self.get_proxy_config()
        
        if proxy_config.get('use_proxy_for_info_extraction', False):
            if not proxy_config.get('webshare_username') or not proxy_config['webshare_username'].strip():
                proxy_errors.append("Webshare username not configured or empty")
            if not proxy_config.get('webshare_password') or not proxy_config['webshare_password'].strip():
                proxy_errors.append("Webshare password not configured or empty")
            if not proxy_config.get('webshare_endpoint') or not proxy_config['webshare_endpoint'].strip():
                proxy_errors.append("Webshare endpoint not configured or empty")
        
        if proxy_errors:
            errors['proxy'] = proxy_errors
        
        # Validate video configuration
        video_errors = []
        video_config = self.get_video_config()
        download_dir = video_config.get('download_dir')
        
        if download_dir:
            try:
                os.makedirs(download_dir, exist_ok=True)
                if not os.access(download_dir, os.W_OK):
                    video_errors.append(f"Download directory not writable: {download_dir}")
            except Exception as e:
                video_errors.append(f"Cannot create download directory: {e}")
        
        if video_errors:
            errors['video'] = video_errors
        
        return errors
    
    def save_to_file(self, file_path: str) -> None:
        """Save current configuration to file.
        
        Args:
            file_path: Path to save configuration file
        """
        try:
            with open(file_path, 'w') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            raise Exception(f"Failed to save config to {file_path}: {e}")
    
    def reload(self) -> None:
        """Reload configuration from sources."""
        self._config = self._load_config()
    
    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary."""
        return self._config.copy()


# Global configuration instance
config = Config()


def get_config() -> Config:
    """Get global configuration instance."""
    return config


def init_config(config_file: Optional[str] = None) -> Config:
    """Initialize configuration with optional config file.
    
    Args:
        config_file: Optional path to JSON configuration file
        
    Returns:
        Configuration instance
    """
    global config
    config = Config(config_file)
    return config
