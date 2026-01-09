"""Local filesystem storage driver."""

import shutil
from pathlib import Path
from typing import List, Dict, Any
import tempfile

from .base import StorageDriver
from ..core.exceptions import StorageError
from ..utils.logging import get_logger
from ..config import get_config

logger = get_logger(__name__)


class LocalStorageDriver(StorageDriver):
    """Local filesystem storage driver."""
    
    def __init__(self, base_path: Path = None):
        """Initialize local storage driver.
        
        Args:
            base_path: Base storage path (defaults to config)
        """
        config = get_config()
        self.base_path = base_path or config.storage_local_base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized local storage at {self.base_path}")
    
    def upload(self, local_path: Path, remote_key: str) -> str:
        """Upload file to local storage (atomic copy).
        
        Args:
            local_path: Local file path
            remote_key: Remote storage key/path
        
        Returns:
            Full path to stored file
        """
        try:
            dest_path = self.base_path / remote_key
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Atomic write using temporary file
            temp_path = dest_path.with_suffix(dest_path.suffix + '.tmp')
            shutil.copy2(local_path, temp_path)
            temp_path.rename(dest_path)
            
            logger.debug(f"Uploaded {local_path} to {dest_path}")
            return str(dest_path)
        except Exception as e:
            raise StorageError(f"Failed to upload file: {e}")
    
    def download(self, remote_key: str, local_path: Path) -> None:
        """Download file from local storage.
        
        Args:
            remote_key: Remote storage key/path
            local_path: Local destination path
        """
        try:
            source_path = self.base_path / remote_key
            if not source_path.exists():
                raise StorageError(f"File not found: {remote_key}")
            
            local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, local_path)
            
            logger.debug(f"Downloaded {remote_key} to {local_path}")
        except Exception as e:
            raise StorageError(f"Failed to download file: {e}")
    
    def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List files in local storage.
        
        Args:
            prefix: Optional prefix filter
        
        Returns:
            List of file info dictionaries
        """
        try:
            prefix_path = self.base_path / prefix if prefix else self.base_path
            if not prefix_path.exists():
                return []
            
            files = []
            for file_path in prefix_path.rglob('*'):
                if file_path.is_file():
                    rel_path = file_path.relative_to(self.base_path)
                    files.append({
                        'key': str(rel_path),
                        'size': file_path.stat().st_size,
                        'modified': file_path.stat().st_mtime
                    })
            
            return files
        except Exception as e:
            raise StorageError(f"Failed to list files: {e}")
    
    def delete(self, remote_key: str) -> None:
        """Delete file from local storage.
        
        Args:
            remote_key: Remote storage key/path
        """
        try:
            file_path = self.base_path / remote_key
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Deleted {remote_key}")
            else:
                logger.warning(f"File not found for deletion: {remote_key}")
        except Exception as e:
            raise StorageError(f"Failed to delete file: {e}")
    
    def exists(self, remote_key: str) -> bool:
        """Check if file exists in local storage.
        
        Args:
            remote_key: Remote storage key/path
        
        Returns:
            True if file exists
        """
        file_path = self.base_path / remote_key
        return file_path.exists()
