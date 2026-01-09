"""Docker API adapter for unified Compose/Swarm interface."""

import docker
from typing import List, Dict, Optional, Any
from pathlib import Path

from ..core.exceptions import DiscoveryError
from ..utils.logging import get_logger
from ..config import get_config

logger = get_logger(__name__)


class DockerAdapter:
    """Unified Docker API adapter for Compose and Swarm."""
    
    def __init__(self, docker_host: Optional[str] = None):
        """Initialize Docker adapter.
        
        Args:
            docker_host: Docker daemon URL (defaults to config)
        """
        config = get_config()
        host = docker_host or config.docker_host
        
        try:
            self.client = docker.DockerClient(base_url=host)
            # Test connection
            self.client.ping()
            logger.info(f"Connected to Docker daemon at {host}")
        except Exception as e:
            raise DiscoveryError(f"Failed to connect to Docker daemon: {e}")
    
    def list_containers(self, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """List containers with metadata.
        
        Args:
            filters: Optional Docker filters
        
        Returns:
            List of container info dictionaries
        """
        try:
            containers = self.client.containers.list(filters=filters or {})
            result = []
            for container in containers:
                result.append({
                    'id': container.id,
                    'name': container.name,
                    'image': container.image.tags[0] if container.image.tags else 'unknown',
                    'status': container.status,
                    'labels': container.labels,
                    'mounts': self._get_mounts(container)
                })
            return result
        except Exception as e:
            raise DiscoveryError(f"Failed to list containers: {e}")
    
    def _get_mounts(self, container) -> List[Dict[str, Any]]:
        """Extract volume mounts from container.
        
        Args:
            container: Docker container object
        
        Returns:
            List of mount dictionaries
        """
        mounts = []
        try:
            container_info = container.attrs
            for mount in container_info.get('Mounts', []):
                mounts.append({
                    'type': mount.get('Type'),  # 'volume' or 'bind'
                    'source': mount.get('Source'),
                    'destination': mount.get('Destination'),
                    'name': mount.get('Name'),
                    'read_only': mount.get('ReadOnly', False)
                })
        except Exception as e:
            logger.warning(f"Failed to get mounts for container {container.name}: {e}")
        return mounts
    
    def get_container(self, container_id_or_name: str):
        """Get container object by ID or name.
        
        Args:
            container_id_or_name: Container ID or name
        
        Returns:
            Container object
        """
        try:
            return self.client.containers.get(container_id_or_name)
        except docker.errors.NotFound:
            raise DiscoveryError(f"Container not found: {container_id_or_name}")
        except Exception as e:
            raise DiscoveryError(f"Failed to get container: {e}")
    
    def create_temp_container(
        self,
        volume_name: str,
        image: str = 'alpine:latest',
        read_only: bool = True,
        command: str = 'sleep infinity'
    ):
        """Create temporary container with volume mounted.
        
        Args:
            volume_name: Volume name to mount
            image: Base image to use
            read_only: Mount volume as read-only
            command: Command to run in container
        
        Returns:
            Container object
        """
        try:
            container = self.client.containers.run(
                image,
                command=command,
                volumes={volume_name: {'bind': '/data', 'mode': 'ro' if read_only else 'rw'}},
                detach=True,
                remove=False,
                name=f'backup-temp-{volume_name[:20]}-{id(self)}'
            )
            logger.debug(f"Created temporary container {container.name} for volume {volume_name}")
            return container
        except Exception as e:
            raise DiscoveryError(f"Failed to create temporary container: {e}")
    
    def exec_in_container(self, container_id: str, command: List[str]) -> str:
        """Execute command in container.
        
        Args:
            container_id: Container ID or name
            command: Command to execute (as list)
        
        Returns:
            Command output
        """
        try:
            container = self.get_container(container_id)
            result = container.exec_run(command)
            if result.exit_code != 0:
                raise DiscoveryError(f"Command failed: {result.output.decode()}")
            return result.output.decode()
        except Exception as e:
            raise DiscoveryError(f"Failed to exec in container: {e}")
    
    def copy_from_container(
        self,
        container_id: str,
        src_path: str,
        dest_path: Path
    ) -> None:
        """Copy file/directory from container.
        
        Args:
            container_id: Container ID or name
            src_path: Source path in container
            dest_path: Destination path on host
        """
        try:
            container = self.get_container(container_id)
            bits, stat = container.get_archive(src_path)
            
            # Extract tar archive
            import tarfile
            import io
            
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            tar_stream = io.BytesIO(bits.read())
            with tarfile.open(fileobj=tar_stream) as tar:
                tar.extractall(dest_path.parent)
        except Exception as e:
            raise DiscoveryError(f"Failed to copy from container: {e}")
    
    def remove_container(self, container_id: str, force: bool = False) -> None:
        """Remove container.
        
        Args:
            container_id: Container ID or name
            force: Force removal if running
        """
        try:
            container = self.get_container(container_id)
            container.remove(force=force)
            logger.debug(f"Removed container {container_id}")
        except Exception as e:
            logger.warning(f"Failed to remove container {container_id}: {e}")
    
    def is_swarm_mode(self) -> bool:
        """Check if Docker is in Swarm mode.
        
        Returns:
            True if Swarm mode is active
        """
        try:
            info = self.client.info()
            return info.get('Swarm', {}).get('LocalNodeState') == 'active'
        except Exception:
            return False
    
    def get_volume_path(self, volume_name: str) -> Optional[str]:
        """Get host path for named volume (if accessible).
        
        Args:
            volume_name: Volume name
        
        Returns:
            Host path or None if not accessible
        """
        try:
            volume = self.client.volumes.get(volume_name)
            # Docker volumes don't expose host path directly
            # We need to use a container to access it
            return None
        except docker.errors.NotFound:
            raise DiscoveryError(f"Volume not found: {volume_name}")
        except Exception as e:
            logger.warning(f"Failed to get volume path: {e}")
            return None
