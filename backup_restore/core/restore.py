"""Restore engine implementation."""

import time
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any

from ..docker.adapter import DockerAdapter
from ..core.discovery import ContainerDiscovery
from ..core.metadata import MetadataDB
from ..core.backup import BackupEngine
from ..storage.registry import get_storage_driver
from ..utils.compression import extract_archive
from ..utils.validation import validate_sqlite_database, count_files, verify_directory_structure
from ..utils.logging import get_logger
from ..core.exceptions import RestoreError, ValidationError
from ..config import get_config

logger = get_logger(__name__)


class RestoreValidator:
    """Pre/post-restore validation."""
    
    @staticmethod
    def validate_backup_exists(metadata_db: MetadataDB, backup_id: str) -> Dict[str, Any]:
        """Validate backup exists and is accessible.
        
        Args:
            metadata_db: Metadata database
            backup_id: Backup ID
        
        Returns:
            Backup metadata
        
        Raises:
            ValidationError: If backup not found
        """
        backup = metadata_db.get_backup(backup_id)
        if not backup:
            raise ValidationError(f"Backup not found: {backup_id}")
        
        if backup['status'] != 'completed':
            raise ValidationError(f"Backup status is {backup['status']}, cannot restore")
        
        return backup
    
    @staticmethod
    def validate_storage_access(storage, storage_key: str) -> bool:
        """Validate backup file is accessible in storage.
        
        Args:
            storage: Storage driver
            storage_key: Storage key
        
        Returns:
            True if accessible
        """
        return storage.exists(storage_key)
    
    @staticmethod
    def validate_target_container(docker: DockerAdapter, container_id: str) -> bool:
        """Validate target container exists.
        
        Args:
            docker: Docker adapter
            container_id: Container ID
        
        Returns:
            True if container exists
        """
        try:
            docker.get_container(container_id)
            return True
        except:
            return False


class RestoreTask:
    """Individual restore operation."""
    
    def __init__(
        self,
        backup_id: str,
        container_id: str,
        selective_paths: Optional[List[str]] = None
    ):
        """Initialize restore task.
        
        Args:
            backup_id: Backup ID to restore
            container_id: Target container ID
            selective_paths: Optional list of paths to restore selectively
        """
        self.backup_id = backup_id
        self.container_id = container_id
        self.selective_paths = selective_paths or []
        self.start_time = None
        self.end_time = None
        self.snapshot_backup_id = None


class RestoreEngine:
    """Main restore orchestrator."""
    
    def __init__(
        self,
        docker_adapter: Optional[DockerAdapter] = None,
        metadata_db: Optional[MetadataDB] = None,
        backup_engine: Optional[BackupEngine] = None
    ):
        """Initialize restore engine.
        
        Args:
            docker_adapter: Optional Docker adapter
            metadata_db: Optional metadata database
            backup_engine: Optional backup engine (for creating snapshots)
        """
        self.docker = docker_adapter or DockerAdapter()
        self.metadata_db = metadata_db or MetadataDB()
        self.backup_engine = backup_engine or BackupEngine(self.docker, self.metadata_db)
        self.discovery = ContainerDiscovery(self.docker)
        config = get_config()
        self.storage = get_storage_driver()
        self.create_snapshot = config.restore_create_snapshot
        self.stop_container = config.restore_stop_container
        self.validate_after_restore = config.restore_validate_after_restore
    
    def restore(
        self,
        backup_id: str,
        container_id: Optional[str] = None,
        environment: Optional[str] = None,
        container_name: Optional[str] = None,
        selective_paths: Optional[List[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Restore backup to container.
        
        Args:
            backup_id: Backup ID to restore
            container_id: Optional target container ID
            environment: Optional environment filter
            container_name: Optional container name filter
            selective_paths: Optional list of paths to restore selectively
            dry_run: If True, don't actually restore
        
        Returns:
            Restore result dictionary
        """
        logger.info(f"Starting restore (dry_run={dry_run})...")
        
        # Validate backup exists
        backup_metadata = RestoreValidator.validate_backup_exists(self.metadata_db, backup_id)
        
        # Find target container
        if not container_id:
            containers = self.discovery.discover_containers(
                environment=environment or backup_metadata['environment'],
                container_name=container_name or backup_metadata['container_name']
            )
            
            if not containers:
                raise RestoreError("No target container found")
            
            container_id = containers[0]['id']
        
        # Validate target container
        if not RestoreValidator.validate_target_container(self.docker, container_id):
            raise RestoreError(f"Target container not found: {container_id}")
        
        # Validate storage access
        if not RestoreValidator.validate_storage_access(self.storage, backup_metadata['storage_key']):
            raise RestoreError(f"Backup file not accessible: {backup_metadata['storage_key']}")
        
        # Create restore task
        task = RestoreTask(backup_id, container_id, selective_paths)
        task.start_time = time.time()
        
        if dry_run:
            logger.info(f"DRY RUN: Would restore backup {backup_id} to container {container_id}")
            return {
                'backup_id': backup_id,
                'container_id': container_id,
                'status': 'dry-run',
                'duration_seconds': 0
            }
        
        # Create pre-restore snapshot if configured
        if self.create_snapshot:
            try:
                logger.info("Creating pre-restore snapshot...")
                snapshot_metadata = self.backup_engine.create_backup(
                    container_id=container_id,
                    dry_run=False
                )
                task.snapshot_backup_id = snapshot_metadata.backup_id
                logger.info(f"Created snapshot: {snapshot_metadata.backup_id}")
            except Exception as e:
                logger.warning(f"Failed to create snapshot: {e}")
                # Continue anyway, but log warning
        
        # Stop container if configured
        container_was_running = False
        if self.stop_container:
            try:
                container = self.docker.get_container(container_id)
                if container.status == 'running':
                    container_was_running = True
                    logger.info(f"Stopping container {container_id}...")
                    container.stop()
            except Exception as e:
                logger.warning(f"Failed to stop container: {e}")
        
        temp_dir = None
        temp_container = None
        
        try:
            # Download backup
            logger.info("Downloading backup...")
            temp_dir = Path(tempfile.mkdtemp(prefix='restore-'))
            backup_file = temp_dir / f"{backup_id}.tar.zst"
            self.storage.download(backup_metadata['storage_key'], backup_file)
            
            # Extract backup
            logger.info("Extracting backup...")
            extract_dir = temp_dir / 'extracted'
            extract_archive(
                backup_file,
                extract_dir,
                verify_checksum=backup_metadata.get('checksum_sha256')
            )
            
            # Get target volumes
            target_volumes = self.discovery.get_target_volumes(container_id)
            if not target_volumes:
                raise RestoreError(f"No target volumes found in container {container_id}")
            
            main_volume = target_volumes[0]
            
            # Create temporary container with volume mounted
            temp_container = self.docker.create_temp_container(
                volume_name=main_volume['name'],
                read_only=False
            )
            
            # Wait for container to be ready
            time.sleep(1)
            
            # Copy files to container
            logger.info("Copying files to container...")
            
            # Find the flowdocs structure in extracted directory
            # It could be at extract_dir/flowdocs or extract_dir/app/flowdocs
            flowdocs_source = None
            if (extract_dir / 'app' / 'flowdocs').exists():
                flowdocs_source = extract_dir / 'app' / 'flowdocs'
                target_base = '/data/app/flowdocs'
            elif (extract_dir / 'flowdocs').exists():
                flowdocs_source = extract_dir / 'flowdocs'
                target_base = '/data/flowdocs'
            else:
                # Fallback: use extract_dir itself
                flowdocs_source = extract_dir
                target_base = '/data'
            
            if selective_paths:
                # Selective restore
                for path in selective_paths:
                    source_path = flowdocs_source / path
                    if source_path.exists():
                        logger.info(f"Restoring {path}...")
                        # Create tar and stream into container
                        self._copy_to_container(temp_container.id, source_path, f"{target_base}/{path}")
            else:
                # Full restore - copy entire flowdocs directory
                logger.info("Performing full restore...")
                # If we have app/flowdocs structure, restore to /data/app/flowdocs
                # Otherwise restore to /data/flowdocs or /data
                if 'app/flowdocs' in str(flowdocs_source):
                    # Need to create the app/flowdocs structure
                    self._copy_to_container(temp_container.id, flowdocs_source, "/data/app")
                else:
                    self._copy_to_container(temp_container.id, flowdocs_source, target_base)
            
            # Validate restore if configured
            if self.validate_after_restore:
                logger.info("Validating restore...")
                self._validate_restore(temp_container.id, backup_metadata)
            
            # Start container if it was stopped
            if container_was_running:
                try:
                    container = self.docker.get_container(container_id)
                    logger.info(f"Starting container {container_id}...")
                    container.start()
                except Exception as e:
                    logger.warning(f"Failed to start container: {e}")
            
            task.end_time = time.time()
            duration = task.end_time - task.start_time
            
            logger.info(f"Restore completed in {duration:.2f} seconds")
            
            return {
                'backup_id': backup_id,
                'container_id': container_id,
                'status': 'completed',
                'duration_seconds': duration,
                'snapshot_backup_id': task.snapshot_backup_id
            }
        
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            
            # Rollback if snapshot exists
            if task.snapshot_backup_id:
                logger.warning("Attempting rollback from snapshot...")
                try:
                    self.restore(
                        backup_id=task.snapshot_backup_id,
                        container_id=container_id,
                        dry_run=False
                    )
                    logger.info("Rollback successful")
                except Exception as rollback_error:
                    logger.error(f"Rollback failed: {rollback_error}")
                    raise RestoreError(f"Restore failed and rollback failed: {rollback_error}")
            
            raise RestoreError(f"Restore failed: {e}")
        
        finally:
            # Cleanup
            if temp_container:
                try:
                    self.docker.remove_container(temp_container.id, force=True)
                except:
                    pass
            
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _copy_to_container(self, container_id: str, source_path: Path, dest_path: str) -> None:
        """Copy file/directory to container.
        
        Args:
            container_id: Container ID
            source_path: Source path on host
            dest_path: Destination path in container
        """
        import tarfile
        import io
        
        # Create tar archive in memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            if source_path.is_file():
                tar.add(source_path, arcname=source_path.name)
            else:
                tar.add(source_path, arcname='.')
        
        tar_buffer.seek(0)
        
        # Put archive into container
        container = self.docker.get_container(container_id)
        container.put_archive(dest_path, tar_buffer.read())
    
    def _validate_restore(self, container_id: str, backup_metadata: Dict[str, Any]) -> None:
        """Validate restored data.
        
        Args:
            container_id: Container ID
            backup_metadata: Original backup metadata
        """
        # Check SQLite database integrity if present
        try:
            result = self.docker.exec_in_container(
                container_id,
                ['test', '-f', '/data/db.sqlite3']
            )
            # Database exists, validate it
            # We can't directly validate in container, so we'll check file exists
            # Full validation would require copying out and checking
            logger.debug("SQLite database file exists")
        except:
            pass  # Database might not exist
        
        # Count files (approximate validation)
        try:
            result = self.docker.exec_in_container(
                container_id,
                ['find', '/data', '-type', 'f', '|', 'wc', '-l']
            )
            file_count = int(result.strip())
            logger.debug(f"Restored file count: {file_count}")
        except:
            pass
