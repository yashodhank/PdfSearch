# Docker Volume Backup & Restore System

A production-grade backup and restore system for Docker volumes that supports both Docker Compose and Docker Swarm, with local and S3-compatible storage backends.

## Features

- **Automatic Discovery**: Discovers running containers and attached volumes
- **Unified Backups**: Creates single backup of `/app/flowdocs/` structure
- **Multiple Storage Backends**: Local filesystem and S3-compatible (Wasabi, MinIO, AWS S3)
- **Safe Restores**: Atomic restore operations with automatic rollback on failure
- **CLI Interface**: Powerful command-line interface with rich output
- **Web UI**: FastAPI-based web dashboard for backup management
- **Metadata Tracking**: SQLite database for backup metadata and fast queries

## Installation

1. Install dependencies:
```bash
pip install -r backup_restore/requirements.txt
```

2. Configure the system (see Configuration section)

3. Make CLI executable:
```bash
chmod +x backup_restore/main.py
```

## Configuration

Configuration can be provided via:
1. CLI flags (highest priority)
2. Environment variables
3. YAML config file (`config/config.yaml`)
4. Defaults

### Example Configuration

See `config/config.yaml.example` and `config/.env.example` for full configuration options.

### Quick Start

1. Copy example config:
```bash
cp backup_restore/config/config.yaml.example backup_restore/config/config.yaml
```

2. Edit `config.yaml` with your settings

3. Or set environment variables:
```bash
export STORAGE_BACKEND=local
export STORAGE_LOCAL_BASE_PATH=/var/backups/flowdocs
```

## Usage

### CLI Commands

#### List Containers
```bash
python -m backup_restore.main containers
python -m backup_restore.main containers --env prod --json
```

#### List Backups
```bash
python -m backup_restore.main list
python -m backup_restore.main list --env prod --limit 10
```

#### Create Backup
```bash
python -m backup_restore.main create --env prod
python -m backup_restore.main create --container sahakar-prod-frontend-abc123
python -m backup_restore.main create --dry-run  # Test without creating backup
```

#### Restore Backup
```bash
python -m backup_restore.main restore --backup-id <backup-id>
python -m backup_restore.main restore --backup-id <backup-id> --selective db.sqlite3
python -m backup_restore.main restore --backup-id <backup-id> --interactive
python -m backup_restore.main restore --backup-id <backup-id> --dry-run
```

#### Verify Backup
```bash
python -m backup_restore.main verify --backup-id <backup-id>
```

#### Statistics
```bash
python -m backup_restore.main stats
python -m backup_restore.main stats --env prod
```

#### Delete Backup
```bash
python -m backup_restore.main delete --backup-id <backup-id> --confirm
python -m backup_restore.main delete --older-than 30 --confirm
```

### Web UI

Start the web server:
```bash
python -m backup_restore.web.app
```

Or using uvicorn directly:
```bash
uvicorn backup_restore.web.app:app --host 0.0.0.0 --port 8080
```

Access the dashboard at `http://localhost:8080`

## Architecture

The system consists of:

- **Discovery Layer**: Detects containers and volumes
- **Backup Engine**: Creates compressed backups with metadata
- **Restore Engine**: Safe restore with rollback capability
- **Storage Drivers**: Pluggable storage backends (local, S3)
- **Metadata Database**: SQLite database for backup tracking
- **CLI Interface**: Command-line interface with rich formatting
- **Web UI**: FastAPI dashboard for backup management

## Backup Format

Backups are stored as compressed tar archives:
- Format: `.tar.zst` (Zstandard) or `.tar.gz` (fallback)
- Contains: Unified `/app/flowdocs/` structure
- Metadata: Stored in SQLite database

## Restore Safety

All restore operations:
1. Create pre-restore snapshot automatically
2. Validate backup integrity before restore
3. Perform atomic file operations
4. Rollback automatically on failure
5. Support dry-run mode for testing

## Storage Backends

### Local Storage
Stores backups in configurable directory structure:
```
{base_path}/{env}/{container}/{backup_id}.tar.zst
```

### S3-Compatible Storage
Supports:
- AWS S3
- Wasabi
- MinIO

Configure via:
- `storage.s3.endpoint_url`
- `storage.s3.bucket`
- `storage.s3.access_key_id`
- `storage.s3.secret_access_key`

## Environment Detection

The system automatically detects environment (dev/prod) from:
- Container names
- Volume names
- Docker Compose project names
- Docker Swarm service names

## Error Handling

The system handles:
- Container not running during backup (creates temp container)
- Backup interruptions (marks as partial, allows retry)
- Storage backend failures (retries with exponential backoff)
- Restore failures (automatic rollback from snapshot)
- Corrupted backups (checksum validation)

## Security

- No shell injection (uses subprocess with list args)
- Secret redaction in logs
- Read-only operations where possible
- TLS support for remote Docker connections
- Encrypted storage options

## License

See project license file.
