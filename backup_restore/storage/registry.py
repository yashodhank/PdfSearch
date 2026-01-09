"""Storage driver registry."""

from typing import Optional

from .base import StorageDriver
from .local import LocalStorageDriver
from .s3 import S3StorageDriver
from ..core.exceptions import StorageError
from ..config import get_config

_registry = {
    'local': LocalStorageDriver,
    's3': S3StorageDriver,
}


def get_storage_driver(driver_type: Optional[str] = None) -> StorageDriver:
    """Get storage driver instance.
    
    Args:
        driver_type: Driver type ('local' or 's3'), defaults to config
    
    Returns:
        Storage driver instance
    """
    config = get_config()
    driver_name = driver_type or config.storage_backend
    
    if driver_name not in _registry:
        raise StorageError(f"Unknown storage driver: {driver_name}")
    
    driver_class = _registry[driver_name]
    
    if driver_name == 'local':
        return driver_class()
    elif driver_name == 's3':
        return driver_class()
    else:
        raise StorageError(f"Failed to initialize storage driver: {driver_name}")
