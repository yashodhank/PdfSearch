"""Pydantic models for Web API."""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class BackupResponse(BaseModel):
    """Backup response model."""
    backup_id: str
    environment: str
    container_name: str
    volume_name: str
    storage_backend: str
    storage_key: str
    created_at: str
    size_raw: int
    size_compressed: int
    duration_seconds: float
    checksum_sha256: str
    file_count: int
    status: str
    metadata: Optional[Dict[str, Any]] = None


class ContainerResponse(BaseModel):
    """Container response model."""
    id: str
    name: str
    image: str
    status: str
    environment: str
    orchestration: str
    volumes: List[Dict[str, Any]]


class RestoreRequest(BaseModel):
    """Restore request model."""
    container_id: Optional[str] = None
    environment: Optional[str] = None
    container_name: Optional[str] = None
    selective_paths: Optional[List[str]] = None
    dry_run: bool = False


class RestoreResponse(BaseModel):
    """Restore response model."""
    backup_id: str
    container_id: str
    status: str
    duration_seconds: float
    snapshot_backup_id: Optional[str] = None


class StatsResponse(BaseModel):
    """Statistics response model."""
    total_backups: int
    total_size: int
    environments: List[str]
