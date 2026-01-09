"""Metadata database operations for backup tracking."""

import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime
import json

from ..core.exceptions import MetadataError
from ..utils.logging import get_logger
from ..config import get_config

logger = get_logger(__name__)


class MetadataDB:
    """SQLite database for backup metadata."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize metadata database.
        
        Args:
            db_path: Path to SQLite database (defaults to config)
        """
        config = get_config()
        self.db_path = db_path or config.metadata_db_path
        
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize database schema."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Create backups table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    id TEXT PRIMARY KEY,
                    backup_id TEXT UNIQUE NOT NULL,
                    environment TEXT NOT NULL,
                    container_name TEXT NOT NULL,
                    volume_name TEXT NOT NULL,
                    storage_backend TEXT NOT NULL,
                    storage_key TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    size_raw INTEGER NOT NULL,
                    size_compressed INTEGER NOT NULL,
                    duration_seconds REAL NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    file_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    metadata_json TEXT
                )
            """)
            
            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backups_env_container 
                ON backups(environment, container_name)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backups_created_at 
                ON backups(created_at DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_backups_backup_id 
                ON backups(backup_id)
            """)
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Initialized metadata database at {self.db_path}")
        except Exception as e:
            raise MetadataError(f"Failed to initialize metadata database: {e}")
    
    def record_backup(
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
    ) -> str:
        """Record backup metadata.
        
        Args:
            backup_id: Unique backup ID
            environment: Environment (dev/prod)
            container_name: Container name
            volume_name: Volume name
            storage_backend: Storage backend type
            storage_key: Storage key/path
            size_raw: Raw size in bytes
            size_compressed: Compressed size in bytes
            duration_seconds: Backup duration
            checksum_sha256: SHA256 checksum
            file_count: Number of files backed up
            status: Backup status
            metadata: Optional additional metadata
        
        Returns:
            Database record ID
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            record_id = f"{backup_id}-{int(datetime.utcnow().timestamp())}"
            
            cursor.execute("""
                INSERT INTO backups (
                    id, backup_id, environment, container_name, volume_name,
                    storage_backend, storage_key, created_at, size_raw,
                    size_compressed, duration_seconds, checksum_sha256,
                    file_count, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id,
                backup_id,
                environment,
                container_name,
                volume_name,
                storage_backend,
                storage_key,
                datetime.utcnow().isoformat(),
                size_raw,
                size_compressed,
                duration_seconds,
                checksum_sha256,
                file_count,
                status,
                json.dumps(metadata) if metadata else None
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Recorded backup metadata: {backup_id}")
            return record_id
        except sqlite3.IntegrityError as e:
            raise MetadataError(f"Backup ID already exists: {backup_id}")
        except Exception as e:
            raise MetadataError(f"Failed to record backup: {e}")
    
    def list_backups(
        self,
        environment: Optional[str] = None,
        container_name: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List backups with optional filters.
        
        Args:
            environment: Optional environment filter
            container_name: Optional container name filter
            limit: Optional result limit
        
        Returns:
            List of backup metadata dictionaries
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM backups WHERE 1=1"
            params = []
            
            if environment:
                query += " AND environment = ?"
                params.append(environment)
            
            if container_name:
                query += " AND container_name = ?"
                params.append(container_name)
            
            query += " ORDER BY created_at DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            conn.close()
            
            # Convert rows to dictionaries
            backups = []
            for row in rows:
                backup = dict(row)
                if backup.get('metadata_json'):
                    backup['metadata'] = json.loads(backup['metadata_json'])
                del backup['metadata_json']
                backups.append(backup)
            
            return backups
        except Exception as e:
            raise MetadataError(f"Failed to list backups: {e}")
    
    def get_backup(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Get backup metadata by ID.
        
        Args:
            backup_id: Backup ID
        
        Returns:
            Backup metadata dictionary or None
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM backups WHERE backup_id = ?", (backup_id,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                backup = dict(row)
                if backup.get('metadata_json'):
                    backup['metadata'] = json.loads(backup['metadata_json'])
                del backup['metadata_json']
                return backup
            
            return None
        except Exception as e:
            raise MetadataError(f"Failed to get backup: {e}")
    
    def update_backup_status(self, backup_id: str, status: str) -> None:
        """Update backup status.
        
        Args:
            backup_id: Backup ID
            status: New status
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE backups SET status = ? WHERE backup_id = ?",
                (status, backup_id)
            )
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Updated backup {backup_id} status to {status}")
        except Exception as e:
            raise MetadataError(f"Failed to update backup status: {e}")
    
    def delete_backup(self, backup_id: str) -> None:
        """Delete backup metadata.
        
        Args:
            backup_id: Backup ID
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM backups WHERE backup_id = ?", (backup_id,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Deleted backup metadata: {backup_id}")
        except Exception as e:
            raise MetadataError(f"Failed to delete backup: {e}")
