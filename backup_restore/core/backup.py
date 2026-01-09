"""Backup engine implementation."""

import time
import hashlib
import tempfile
import tarfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from ..docker.adapter import DockerAdapter
from ..core.discovery import ContainerDiscovery
from ..core.metadata import MetadataDB
from ..storage.registry import get_storage_driver
from ..utils.compression import compress_directory
from ..utils.logging import get_logger
from ..core.exceptions import BackupError, DiscoveryError
from ..config import get_config

logger = get_logger(__name__)


class BackupMetadata:
    """Backup metadata structure."""
    
    def __init__(
        self,
        backup_id: str,
        environment: str,
        container_name: str,
        volume_name: str,
        storage_backend: str,
        storage_key: str,
        size_raw: int,
        size_compressed: int,
        duration_seconds: float,
        checksum_sha256: str,
        file_count: int,
        status: str = 'completed',
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.backup_id = backup_id
        self.environment = environment
        self.container_name = container_name
        self.volume_name = volume_name
        self.storage_backend = storage_backend
        self.storage_key = storage_key
        self.size_raw = size_raw
        self.size_compressed = size_compressed
        self.duration_seconds = duration_seconds
        self.checksum_sha256 = checksum_sha256
        self.file_count = file_count
        self.status = status
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'backup_id': self.backup_id,
            'environment': self.environment,
            'container_name': self.container_name,
            'volume_name': self.volume_name,
            'storage_backend': self.storage_backend,
            'storage_key': self.storage_key,
            'size_raw': self.size_raw,
            'size_compressed': self.size_compressed,
            'duration_seconds': self.duration_seconds,
            'checksum_sha256': self.checksum_sha256,
            'file_count': self.file_count,
            'status': self.status,
            'metadata': self.metadata
        }


class BackupTask:
    """Individual backup operation."""
    
    def __init__(
        self,
        container_id: str,
        volume_name: str,
        environment: str,
        container_name: str
    ):
        """Initialize backup task.
        
        Args:
            container_id: Container ID
            volume_name: Volume name
            environment: Environment (dev/prod)
            container_name: Container name
        """
        self.container_id = container_id
        self.volume_name = volume_name
        self.environment = environment
        self.container_name = container_name
        self.start_time = None
        self.end_time = None
    
    def generate_backup_id(self) -> str:
        """Generate unique backup ID.
        
        Returns:
            Backup ID string
        """
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%SZ')
        hash_input = f"{self.environment}-{self.container_name}-{self.volume_name}-{timestamp}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        
        return f"{self.environment}-{self.container_name}-{self.volume_name}-{timestamp}-{short_hash}"


class BackupEngine:
    """Main backup orchestrator."""
    
    def __init__(
        self,
        docker_adapter: Optional[DockerAdapter] = None,
        metadata_db: Optional[MetadataDB] = None
    ):
        """Initialize backup engine.
        
        Args:
            docker_adapter: Optional Docker adapter
            metadata_db: Optional metadata database
        """
        self.docker = docker_adapter or DockerAdapter()
        self.metadata_db = metadata_db or MetadataDB()
        self.discovery = ContainerDiscovery(self.docker)
        config = get_config()
        self.storage = get_storage_driver()
        self.compression = config.backup_compression
        self.compression_level = config.backup_compression_level
        self.exclude_patterns = config.backup_exclude_patterns
    
    def create_backup(
        self,
        container_id: Optional[str] = None,
        environment: Optional[str] = None,
        container_name: Optional[str] = None,
        dry_run: bool = False
    ) -> BackupMetadata:
        """Create backup for container.
        
        Args:
            container_id: Optional container ID
            environment: Optional environment filter
            container_name: Optional container name filter
            dry_run: If True, don't actually create backup
        
        Returns:
            Backup metadata
        """
        logger.info(f"Starting backup (dry_run={dry_run})...")
        
        # Discover containers
        containers = self.discovery.discover_containers(
            environment=environment,
            container_name=container_name
        )
        
        if not containers:
            raise BackupError("No containers found matching criteria")
        
        # Use first matching container if not specified
        if not container_id:
            container_id = containers[0]['id']
        
        # Find container info
        container_info = next(c for c in containers if c['id'] == container_id)
        
        # Get target volumes (unified /app/flowdocs structure)
        target_volumes = self.discovery.get_target_volumes(container_id)
        
        if not target_volumes:
            raise BackupError(f"No flowdocs volumes found in container {container_id}")
        
        # For unified backup, we'll backup the main volume that contains /app/flowdocs
        # In practice, we'll create a temp container and copy from /app/flowdocs
        main_volume = target_volumes[0]
        
        # Create backup task
        task = BackupTask(
            container_id=container_id,
            volume_name=main_volume['name'],
            environment=container_info['environment'],
            container_name=container_info['name']
        )
        
        backup_id = task.generate_backup_id()
        
        if dry_run:
            logger.info(f"DRY RUN: Would create backup {backup_id}")
            return BackupMetadata(
                backup_id=backup_id,
                environment=task.environment,
                container_name=task.container_name,
                volume_name=task.volume_name,
                storage_backend='dry-run',
                storage_key='',
                size_raw=0,
                size_compressed=0,
                duration_seconds=0,
                checksum_sha256='',
                file_count=0,
                status='dry-run'
            )
        
        # Start backup
        task.start_time = time.time()
        
        try:
            # Create temporary container with volume mounted
            temp_container = None
            temp_dir = None
            
            try:
                # Create temp container
                temp_container = self.docker.create_temp_container(
                    volume_name=main_volume['name'],
                    read_only=True
                )
                
                # Wait for container to be ready
                time.sleep(1)
                
                # Create temporary directory for extraction
                temp_dir = Path(tempfile.mkdtemp(prefix='backup-'))
                extract_dir = temp_dir / 'flowdocs'
                extract_dir.mkdir()
                
                # Copy /app/flowdocs from temp container
                # The volume is mounted at /data in temp container
                # We need to find the flowdocs structure within the volume
                logger.info(f"Copying data from container {temp_container.name}...")
                
                # Check if /data/app/flowdocs exists, or if flowdocs is directly in /data
                # Try to find the flowdocs directory structure
                flowdocs_path = None
                try:
                    # Check for /data/app/flowdocs structure
                    result = self.docker.exec_in_container(
                        temp_container.id,
                        ['test', '-d', '/data/app/flowdocs']
                    )
                    flowdocs_path = '/data/app/flowdocs'
                except:
                    try:
                        # Check for /data/flowdocs structure
                        result = self.docker.exec_in_container(
                            temp_container.id,
                            ['test', '-d', '/data/flowdocs']
                        )
                        flowdocs_path = '/data/flowdocs'
                    except:
                        # Fallback: use /data and look for flowdocs structure
                        flowdocs_path = '/data'
                
                # Use docker exec to create tar archive in container
                # Archive the flowdocs directory structure
                if flowdocs_path == '/data/app/flowdocs':
                    # Archive the app/flowdocs structure
                    self.docker.exec_in_container(
                        temp_container.id,
                        ['tar', 'czf', '/tmp/flowdocs-backup.tar.gz', '-C', '/data', 'app/flowdocs']
                    )
                elif flowdocs_path == '/data/flowdocs':
                    # Archive the flowdocs directory
                    self.docker.exec_in_container(
                        temp_container.id,
                        ['tar', 'czf', '/tmp/flowdocs-backup.tar.gz', '-C', '/data', 'flowdocs']
                    )
                else:
                    # Archive everything in /data (fallback)
                    self.docker.exec_in_container(
                        temp_container.id,
                        ['tar', 'czf', '/tmp/flowdocs-backup.tar.gz', '-C', '/data', '.']
                    )
                
                # Copy archive from container
                archive_path = temp_dir / 'backup.tar.gz'
                self.docker.copy_from_container(
                    temp_container.id,
                    '/tmp/flowdocs-backup.tar.gz',
                    archive_path
                )
                
                # Extract to get file count and prepare for compression
                with tarfile.open(archive_path, 'r:gz') as tar:
                    tar.extractall(extract_dir)
                
                # Count files and calculate raw size (uncompressed size of all files)
                file_count = 0
                raw_size = 0
                for f in extract_dir.rglob('*'):
                    if f.is_file():
                        file_count += 1
                        try:
                            raw_size += f.stat().st_size
                        except (OSError, PermissionError):
                            # Skip files we can't stat
                            pass
                
                # Compress for storage
                logger.info("Compressing backup...")
                compressed_path = temp_dir / f"{backup_id}.tar.zst"
                calculated_raw_size, size_compressed, checksum = compress_directory(
                    extract_dir,
                    compressed_path,
                    compression=self.compression,
                    compression_level=self.compression_level,
                    exclude_patterns=self.exclude_patterns
                )
                # Use the calculated raw_size if our traversal didn't work
                if raw_size == 0:
                    raw_size = calculated_raw_size
                
                # Upload to storage
                logger.info("Uploading to storage...")
                storage_key = f"{task.environment}/{task.container_name}/{backup_id}.tar.zst"
                storage_url = self.storage.upload(compressed_path, storage_key)
                
                # Record metadata
                task.end_time = time.time()
                duration = task.end_time - task.start_time
                
                backup_metadata = BackupMetadata(
                    backup_id=backup_id,
                    environment=task.environment,
                    container_name=task.container_name,
                    volume_name=task.volume_name,
                    storage_backend=self.storage.__class__.__name__,
                    storage_key=storage_key,
                    size_raw=size_raw,
                    size_compressed=size_compressed,
                    duration_seconds=duration,
                    checksum_sha256=checksum,
                    file_count=file_count,
                    status='completed'
                )
                
                # Save to metadata database
                self.metadata_db.record_backup(
                    backup_id=backup_metadata.backup_id,
                    environment=backup_metadata.environment,
                    container_name=backup_metadata.container_name,
                    volume_name=backup_metadata.volume_name,
                    storage_backend=backup_metadata.storage_backend,
                    storage_key=backup_metadata.storage_key,
                    size_raw=backup_metadata.size_raw,
                    size_compressed=backup_metadata.size_compressed,
                    duration_seconds=backup_metadata.duration_seconds,
                    checksum_sha256=backup_metadata.checksum_sha256,
                    file_count=backup_metadata.file_count,
                    status=backup_metadata.status
                )
                
                logger.info(f"Backup completed: {backup_id} ({size_compressed / 1024 / 1024:.2f} MB)")
                
                return backup_metadata
                
            finally:
                # Cleanup
                if temp_container:
                    try:
                        self.docker.remove_container(temp_container.id, force=True)
                    except:
                        pass
                
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
        
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            # Record failed backup
            try:
                self.metadata_db.record_backup(
                    backup_id=backup_id,
                    environment=task.environment,
                    container_name=task.container_name,
                    volume_name=task.volume_name,
                    storage_backend='',
                    storage_key='',
                    size_raw=0,
                    size_compressed=0,
                    duration_seconds=time.time() - task.start_time if task.start_time else 0,
                    checksum_sha256='',
                    file_count=0,
                    status='failed'
                )
            except:
                pass
            
            raise BackupError(f"Backup failed: {e}")
