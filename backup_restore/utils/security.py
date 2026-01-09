"""Security utilities for validation and secret handling."""

import re
from typing import List, Optional
from pathlib import Path


def validate_backup_id(backup_id: str) -> bool:
    """Validate backup ID format.
    
    Args:
        backup_id: Backup ID to validate
    
    Returns:
        True if valid format
    """
    # Format: {env}-{container}-{volume}-{timestamp}-{hash}
    pattern = r'^[a-z0-9]+-[a-z0-9\-]+-[a-z0-9\-]+-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z-[a-f0-9]+$'
    return bool(re.match(pattern, backup_id))


def sanitize_path(path: str) -> Path:
    """Sanitize file path to prevent directory traversal.
    
    Args:
        path: Path to sanitize
    
    Returns:
        Sanitized Path object
    
    Raises:
        ValueError: If path contains dangerous patterns
    """
    # Resolve to absolute path and check for traversal
    resolved = Path(path).resolve()
    
    # Check for dangerous patterns
    path_str = str(resolved)
    if '..' in path_str or path_str.startswith('/etc') or path_str.startswith('/root'):
        raise ValueError(f"Potentially dangerous path: {path}")
    
    return resolved


def redact_secrets(text: str) -> str:
    """Redact secrets from text.
    
    Args:
        text: Text that may contain secrets
    
    Returns:
        Text with secrets redacted
    """
    patterns = [
        (r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'password": "***REDACTED***"'),
        (r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'secret": "***REDACTED***"'),
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'api_key": "***REDACTED***"'),
        (r'access[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'access_key": "***REDACTED***"'),
        (r'sk-[a-zA-Z0-9]+', 'sk-***REDACTED***'),
        (r'AKIA[0-9A-Z]{16}', 'AKIA***REDACTED***'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result


def validate_container_name(name: str) -> bool:
    """Validate Docker container name format.
    
    Args:
        name: Container name to validate
    
    Returns:
        True if valid
    """
    # Docker container names: [a-zA-Z0-9][a-zA-Z0-9_.-]*
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$'
    return bool(re.match(pattern, name)) and len(name) <= 253


def validate_volume_name(name: str) -> bool:
    """Validate Docker volume name format.
    
    Args:
        name: Volume name to validate
    
    Returns:
        True if valid
    """
    # Similar to container names
    return validate_container_name(name)
