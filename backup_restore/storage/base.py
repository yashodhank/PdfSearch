"""Abstract base class for storage drivers."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any


class StorageDriver(ABC):
    """Abstract storage driver interface."""
    
    @abstractmethod
    def upload(self, local_path: Path, remote_key: str) -> str:
        """Upload file to storage.
        
        Args:
            local_path: Local file path
            remote_key: Remote storage key/path
        
        Returns:
            Storage URL or key
        """
        pass
    
    @abstractmethod
    def download(self, remote_key: str, local_path: Path) -> None:
        """Download file from storage.
        
        Args:
            remote_key: Remote storage key/path
            local_path: Local destination path
        """
        pass
    
    @abstractmethod
    def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List files in storage.
        
        Args:
            prefix: Optional prefix filter
        
        Returns:
            List of file info dictionaries
        """
        pass
    
    @abstractmethod
    def delete(self, remote_key: str) -> None:
        """Delete file from storage.
        
        Args:
            remote_key: Remote storage key/path
        """
        pass
    
    @abstractmethod
    def exists(self, remote_key: str) -> bool:
        """Check if file exists in storage.
        
        Args:
            remote_key: Remote storage key/path
        
        Returns:
            True if file exists
        """
        pass
