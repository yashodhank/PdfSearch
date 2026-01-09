"""FastAPI routes for Web UI."""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
from ..core.discovery import ContainerDiscovery
from ..core.backup import BackupEngine
from ..core.restore import RestoreEngine
from ..core.metadata import MetadataDB
from ..utils.logging import get_logger
from .models import (
    BackupResponse, ContainerResponse, RestoreRequest,
    RestoreResponse, StatsResponse
)

logger = get_logger(__name__)
router = APIRouter()


@router.get("/api/containers", response_model=List[ContainerResponse])
async def list_containers(env: Optional[str] = None):
    """List containers with flowdocs volumes."""
    try:
        discovery = ContainerDiscovery()
        containers = discovery.discover_containers(environment=env)
        return [ContainerResponse(**c) for c in containers]
    except Exception as e:
        logger.error(f"Failed to list containers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/backups", response_model=List[BackupResponse])
async def list_backups(
    env: Optional[str] = None,
    container: Optional[str] = None,
    limit: Optional[int] = None
):
    """List backups."""
    try:
        metadata_db = MetadataDB()
        backups = metadata_db.list_backups(
            environment=env,
            container_name=container,
            limit=limit
        )
        return [BackupResponse(**b) for b in backups]
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/backups/{backup_id}", response_model=BackupResponse)
async def get_backup(backup_id: str):
    """Get backup details."""
    try:
        metadata_db = MetadataDB()
        backup = metadata_db.get_backup(backup_id)
        if not backup:
            raise HTTPException(status_code=404, detail="Backup not found")
        return BackupResponse(**backup)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/backups/create", response_model=BackupResponse)
async def create_backup(
    env: Optional[str] = None,
    container: Optional[str] = None,
    container_id: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None
):
    """Create backup."""
    try:
        backup_engine = BackupEngine()
        
        # Run backup in background
        def run_backup():
            return backup_engine.create_backup(
                container_id=container_id,
                environment=env,
                container_name=container
            )
        
        if background_tasks:
            # For async, we'll run it synchronously for now
            # In production, use proper task queue
            metadata = run_backup()
        else:
            metadata = run_backup()
        
        backup_dict = metadata.to_dict()
        return BackupResponse(**backup_dict)
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/backups/{backup_id}/restore", response_model=RestoreResponse)
async def restore_backup(backup_id: str, request: RestoreRequest):
    """Restore backup."""
    """Restore backup."""
    try:
        restore_engine = RestoreEngine()
        result = restore_engine.restore(
            backup_id=backup_id,
            container_id=request.container_id,
            environment=request.environment,
            container_name=request.container_name,
            selective_paths=request.selective_paths,
            dry_run=request.dry_run
        )
        return RestoreResponse(**result)
    except Exception as e:
        logger.error(f"Failed to restore: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/stats", response_model=StatsResponse)
async def get_stats(env: Optional[str] = None):
    """Get backup statistics."""
    try:
        metadata_db = MetadataDB()
        backups = metadata_db.list_backups(environment=env)
        
        total_size = sum(b['size_compressed'] for b in backups)
        environments = list(set(b['environment'] for b in backups))
        
        return StatsResponse(
            total_backups=len(backups),
            total_size=total_size,
            environments=environments
        )
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
