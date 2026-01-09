"""Docker Swarm detection utilities."""

from typing import Dict, Optional


def detect_swarm_service(container_labels: Dict[str, str]) -> Optional[str]:
    """Detect Docker Swarm service name from container labels.
    
    Args:
        container_labels: Container labels dictionary
    
    Returns:
        Service name or None
    """
    # Docker Swarm sets these labels
    service = container_labels.get('com.docker.swarm.service.name')
    if service:
        return service
    
    # Alternative detection
    for key in container_labels:
        if key.startswith('com.docker.swarm.service.'):
            return container_labels[key]
    
    return None


def is_swarm_container(container_labels: Dict[str, str]) -> bool:
    """Check if container is managed by Docker Swarm.
    
    Args:
        container_labels: Container labels dictionary
    
    Returns:
        True if Swarm-managed
    """
    return 'com.docker.swarm.service.name' in container_labels
