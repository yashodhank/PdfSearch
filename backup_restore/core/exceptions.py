"""Custom exceptions for backup and restore operations."""


class BackupRestoreError(Exception):
    """Base exception for backup/restore operations."""
    pass


class DiscoveryError(BackupRestoreError):
    """Error during container/volume discovery."""
    pass


class BackupError(BackupRestoreError):
    """Error during backup operation."""
    pass


class RestoreError(BackupRestoreError):
    """Error during restore operation."""
    pass


class StorageError(BackupRestoreError):
    """Error with storage backend operations."""
    pass


class ValidationError(BackupRestoreError):
    """Error during backup/restore validation."""
    pass


class MetadataError(BackupRestoreError):
    """Error with metadata database operations."""
    pass
