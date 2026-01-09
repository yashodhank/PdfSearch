"""Docker Compose detection utilities."""

from typing import Dict, Optional


def detect_compose_project(container_labels: Dict[str, str]) -> Optional[str]:
    """Detect Docker Compose project name from container labels.
    
    Args:
        container_labels: Container labels dictionary
    
    Returns:
        Project name or None
    """
    # Docker Compose sets these labels
    project = container_labels.get('com.docker.compose.project')
    if project:
        return project
    
    # Alternative label format
    project = container_labels.get('com.docker.compose.project.working_dir')
    if project:
        return project.split('/')[-1] if '/' in project else project
    
    return None


def is_compose_container(container_labels: Dict[str, str]) -> bool:
    """Check if container is managed by Docker Compose.
    
    Args:
        container_labels: Container labels dictionary
    
    Returns:
        True if Compose-managed
    """
    return 'com.docker.compose.project' in container_labels
