"""Container and volume discovery layer."""

from typing import List, Dict, Optional, Any
from pathlib import Path

from ..docker.adapter import DockerAdapter
from ..docker.compose import detect_compose_project, is_compose_container
from ..docker.swarm import detect_swarm_service, is_swarm_container
from ..core.exceptions import DiscoveryError
from ..utils.logging import get_logger
from ..utils.security import validate_container_name, validate_volume_name

logger = get_logger(__name__)


class EnvironmentDetector:
    """Detects environment (dev/prod) from container/volume names."""
    
    @staticmethod
    def detect(container_name: str, volume_name: Optional[str] = None) -> str:
        """Detect environment from naming patterns.
        
        Args:
            container_name: Container name
            volume_name: Optional volume name
        
        Returns:
            Environment string ('dev', 'prod', or 'unknown')
        """
        name_lower = container_name.lower()
        volume_lower = (volume_name or '').lower()
        
        # Check for explicit environment indicators
        if 'prod' in name_lower or 'prod' in volume_lower:
            return 'prod'
        if 'production' in name_lower or 'production' in volume_lower:
            return 'prod'
        if 'dev' in name_lower or 'dev' in volume_lower:
            return 'dev'
        if 'development' in name_lower or 'development' in volume_lower:
            return 'dev'
        if 'staging' in name_lower or 'staging' in volume_lower:
            return 'staging'
        if 'test' in name_lower or 'test' in volume_lower:
            return 'test'
        
        return 'unknown'


class VolumeMapper:
    """Maps volumes to containers and mountpoints."""
    
    def __init__(self, docker_adapter: DockerAdapter):
        """Initialize volume mapper.
        
        Args:
            docker_adapter: Docker adapter instance
        """
        self.docker = docker_adapter
    
    def get_volumes_for_container(self, container_id: str) -> List[Dict[str, Any]]:
        """Get volumes mounted in container.
        
        Args:
            container_id: Container ID or name
        
        Returns:
            List of volume mount dictionaries
        """
        try:
            container = self.docker.get_container(container_id)
            mounts = self.docker._get_mounts(container)
            
            # Filter for volumes (not bind mounts)
            volumes = []
            for mount in mounts:
                if mount['type'] == 'volume':
                    volumes.append({
                        'name': mount['name'],
                        'destination': mount['destination'],
                        'read_only': mount['read_only']
                    })
            
            return volumes
        except Exception as e:
            raise DiscoveryError(f"Failed to get volumes for container: {e}")
    
    def find_containers_with_volume(self, volume_name: str) -> List[str]:
        """Find containers that have a specific volume mounted.
        
        Args:
            volume_name: Volume name to search for
        
        Returns:
            List of container IDs
        """
        containers = []
        all_containers = self.docker.list_containers()
        
        for container_info in all_containers:
            for mount in container_info['mounts']:
                if mount.get('name') == volume_name:
                    containers.append(container_info['id'])
                    break
        
        return containers


class ContainerDiscovery:
    """Main discovery orchestrator."""
    
    def __init__(self, docker_adapter: Optional[DockerAdapter] = None):
        """Initialize container discovery.
        
        Args:
            docker_adapter: Optional Docker adapter (creates new if not provided)
        """
        self.docker = docker_adapter or DockerAdapter()
        self.env_detector = EnvironmentDetector()
        self.volume_mapper = VolumeMapper(self.docker)
    
    def discover_containers(
        self,
        environment: Optional[str] = None,
        container_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Discover containers with flowdocs volumes.
        
        Args:
            environment: Optional environment filter ('dev', 'prod')
            container_name: Optional container name filter
        
        Returns:
            List of container info dictionaries with volume mappings
        """
        logger.info("Discovering containers...")
        
        # Build filters
        filters = {}
        if container_name:
            filters['name'] = container_name
        
        # Get all containers
        containers = self.docker.list_containers(filters=filters)
        
        result = []
        for container_info in containers:
            # Get volumes
            volumes = self.volume_mapper.get_volumes_for_container(container_info['id'])
            
            # Filter for flowdocs-related volumes
            flowdocs_volumes = [
                v for v in volumes
                if 'flowdocs' in v['name'].lower() or '/app/flowdocs' in v['destination']
            ]
            
            if not flowdocs_volumes:
                continue
            
            # Detect environment
            env = self.env_detector.detect(
                container_info['name'],
                flowdocs_volumes[0]['name'] if flowdocs_volumes else None
            )
            
            # Apply environment filter
            if environment and env != environment:
                continue
            
            # Detect orchestration type
            is_swarm = is_swarm_container(container_info['labels'])
            is_compose = is_compose_container(container_info['labels'])
            
            orchestration = 'swarm' if is_swarm else ('compose' if is_compose else 'standalone')
            
            result.append({
                'id': container_info['id'],
                'name': container_info['name'],
                'image': container_info['image'],
                'status': container_info['status'],
                'environment': env,
                'orchestration': orchestration,
                'volumes': flowdocs_volumes,
                'labels': container_info['labels']
            })
        
        logger.info(f"Discovered {len(result)} containers with flowdocs volumes")
        return result
    
    def validate_flowdocs_path(self, container_id: str) -> bool:
        """Validate that /app/flowdocs exists in container.
        
        Args:
            container_id: Container ID or name
        
        Returns:
            True if path exists
        """
        try:
            result = self.docker.exec_in_container(
                container_id,
                ['test', '-d', '/app/flowdocs']
            )
            return True
        except DiscoveryError:
            return False
    
    def get_target_volumes(self, container_id: str) -> List[Dict[str, Any]]:
        """Get target volumes for backup (unified /app/flowdocs structure).
        
        Args:
            container_id: Container ID or name
        
        Returns:
            List of volume info dictionaries
        """
        volumes = self.volume_mapper.get_volumes_for_container(container_id)
        
        # Filter and organize volumes that contribute to /app/flowdocs
        target_volumes = []
        for vol in volumes:
            dest = vol['destination']
            # Check if this volume is part of flowdocs structure
            if dest.startswith('/app/flowdocs') or 'flowdocs' in vol['name'].lower():
                target_volumes.append({
                    'name': vol['name'],
                    'mount_point': dest,
                    'read_only': vol['read_only']
                })
        
        return target_volumes
