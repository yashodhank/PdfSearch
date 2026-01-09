"""Validation utilities for backup integrity checks."""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple


def validate_sqlite_database(db_path: Path) -> Tuple[bool, Optional[str]]:
    """Validate SQLite database integrity.
    
    Args:
        db_path: Path to SQLite database file
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not db_path.exists():
        return False, "Database file does not exist"
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Run integrity check
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        conn.close()
        
        if result and result[0] == 'ok':
            return True, None
        else:
            return False, result[0] if result else "Integrity check failed"
    except sqlite3.Error as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def count_files(directory: Path, pattern: Optional[str] = None) -> int:
    """Count files in directory (optionally matching pattern).
    
    Args:
        directory: Directory to count files in
        pattern: Optional glob pattern to match
    
    Returns:
        Number of files
    """
    if not directory.exists():
        return 0
    
    if pattern:
        return len(list(directory.glob(pattern)))
    else:
        count = 0
        for item in directory.rglob('*'):
            if item.is_file():
                count += 1
        return count


def verify_directory_structure(base_path: Path, expected_paths: list) -> Tuple[bool, list]:
    """Verify that expected paths exist in directory.
    
    Args:
        base_path: Base directory to check
        expected_paths: List of expected relative paths
    
    Returns:
        Tuple of (all_exist, missing_paths)
    """
    missing = []
    for rel_path in expected_paths:
        full_path = base_path / rel_path
        if not full_path.exists():
            missing.append(str(rel_path))
    
    return len(missing) == 0, missing
