"""Configuration management with support for CLI flags, env vars, and YAML files."""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from dotenv import load_dotenv


class Config:
    """Configuration manager with priority: CLI > Env > YAML > Defaults."""
    
    def __init__(self, config_path: Optional[Path] = None, env_file: Optional[Path] = None):
        """Initialize configuration.
        
        Args:
            config_path: Path to YAML config file
            env_file: Path to .env file
        """
        # Load environment variables
        if env_file and env_file.exists():
            load_dotenv(env_file)
        else:
            # Try default locations
            for default_env in [Path(".env"), Path("config/.env")]:
                if default_env.exists():
                    load_dotenv(default_env)
                    break
        
        # Load YAML config
        self._yaml_config = {}
        if config_path and config_path.exists():
            with open(config_path, 'r') as f:
                self._yaml_config = yaml.safe_load(f) or {}
        else:
            # Try default locations
            for default_config in [Path("config/config.yaml"), Path("config.yaml")]:
                if default_config.exists():
                    with open(default_config, 'r') as f:
                        self._yaml_config = yaml.safe_load(f) or {}
                    break
        
        # CLI overrides (set via set_cli_overrides)
        self._cli_overrides: Dict[str, Any] = {}
    
    def set_cli_overrides(self, overrides: Dict[str, Any]) -> None:
        """Set CLI flag overrides (highest priority)."""
        self._cli_overrides = overrides
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with priority: CLI > Env > YAML > Default.
        
        Supports dot notation for nested keys (e.g., 'docker.host').
        """
        # Check CLI overrides first
        if key in self._cli_overrides:
            return self._cli_overrides[key]
        
        # Check environment variable
        env_key = key.upper().replace('.', '_')
        env_value = os.getenv(env_key)
        if env_value is not None:
            # Try to parse as appropriate type
            if env_value.lower() in ('true', 'false'):
                return env_value.lower() == 'true'
            try:
                return int(env_value)
            except ValueError:
                try:
                    return float(env_value)
                except ValueError:
                    return env_value
        
        # Check YAML config
        yaml_value = self._get_nested_yaml(key)
        if yaml_value is not None:
            return yaml_value
        
        # Return default
        return default
    
    def _get_nested_yaml(self, key: str) -> Any:
        """Get nested YAML value using dot notation."""
        keys = key.split('.')
        value = self._yaml_config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        return value
    
    # Docker configuration
    @property
    def docker_host(self) -> str:
        return self.get('docker.host', 'unix:///var/run/docker.sock')
    
    @property
    def docker_tls_verify(self) -> bool:
        return self.get('docker.tls_verify', False)
    
    @property
    def docker_tls_cert_path(self) -> Optional[str]:
        return self.get('docker.tls_cert_path')
    
    # Storage configuration
    @property
    def storage_backend(self) -> str:
        return self.get('storage.backend', 'local')
    
    @property
    def storage_local_base_path(self) -> Path:
        path_str = self.get('storage.local.base_path', '/var/backups/flowdocs')
        return Path(path_str)
    
    @property
    def storage_s3_endpoint_url(self) -> Optional[str]:
        return self.get('storage.s3.endpoint_url')
    
    @property
    def storage_s3_bucket(self) -> str:
        return self.get('storage.s3.bucket', 'flowdocs-backups')
    
    @property
    def storage_s3_access_key_id(self) -> Optional[str]:
        return self.get('storage.s3.access_key_id') or os.getenv('S3_ACCESS_KEY_ID')
    
    @property
    def storage_s3_secret_access_key(self) -> Optional[str]:
        return self.get('storage.s3.secret_access_key') or os.getenv('S3_SECRET_ACCESS_KEY')
    
    @property
    def storage_s3_region(self) -> str:
        return self.get('storage.s3.region', 'us-east-1')
    
    # Backup configuration
    @property
    def backup_compression(self) -> str:
        return self.get('backup.compression', 'zstd')
    
    @property
    def backup_compression_level(self) -> int:
        return self.get('backup.compression_level', 3)
    
    @property
    def backup_include_patterns(self) -> list:
        return self.get('backup.include_patterns', [
            'db.sqlite3',
            'faiss_indexes/**',
            'media/**'
        ])
    
    @property
    def backup_exclude_patterns(self) -> list:
        return self.get('backup.exclude_patterns', ['*.tmp', '*.log'])
    
    # Restore configuration
    @property
    def restore_create_snapshot(self) -> bool:
        return self.get('restore.create_snapshot', True)
    
    @property
    def restore_stop_container(self) -> bool:
        return self.get('restore.stop_container', False)
    
    @property
    def restore_validate_after_restore(self) -> bool:
        return self.get('restore.validate_after_restore', True)
    
    # Metadata configuration
    @property
    def metadata_db_path(self) -> Path:
        path_str = self.get('metadata.db_path', '/var/backups/flowdocs/metadata.db')
        return Path(path_str)
    
    # Logging configuration
    @property
    def logging_level(self) -> str:
        return self.get('logging.level', 'INFO')
    
    @property
    def logging_format(self) -> str:
        return self.get('logging.format', 'text')
    
    @property
    def logging_file(self) -> Optional[Path]:
        path_str = self.get('logging.file')
        return Path(path_str) if path_str else None


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def set_config(config: Config) -> None:
    """Set global configuration instance."""
    global _config
    _config = config
