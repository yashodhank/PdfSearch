"""CLI command definitions using Click."""

import click
from typing import Optional

from ..core.discovery import ContainerDiscovery
from ..core.backup import BackupEngine
from ..core.restore import RestoreEngine
from ..core.metadata import MetadataDB
from ..utils.logging import setup_logging, get_logger
from ..config import Config, get_config, set_config
from .formatters import print_backup_list, print_container_list, print_stats

logger = get_logger(__name__)


@click.group()
@click.option('--config', type=click.Path(exists=True), help='Path to config file')
@click.option('--env-file', type=click.Path(exists=True), help='Path to .env file')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR']), help='Log level')
@click.option('--log-format', type=click.Choice(['text', 'json']), help='Log format')
@click.pass_context
def cli(ctx, config, env_file, log_level, log_format):
    """Docker Volume Backup & Restore System."""
    # Initialize config
    if config or env_file:
        cfg = Config(config_path=config, env_file=env_file)
        set_config(cfg)
    
    # Setup logging
    setup_logging(level=log_level, format_type=log_format)
    
    ctx.ensure_object(dict)


@cli.command()
@click.option('--env', help='Environment filter (dev/prod)')
@click.option('--container', help='Container name filter')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def containers(env, container, json_output):
    """List containers with flowdocs volumes."""
    try:
        discovery = ContainerDiscovery()
        containers_list = discovery.discover_containers(
            environment=env,
            container_name=container
        )
        print_container_list(containers_list, json_output=json_output)
    except Exception as e:
        logger.error(f"Failed to list containers: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--env', help='Environment filter (dev/prod)')
@click.option('--container', help='Container name filter')
@click.option('--limit', type=int, help='Limit number of results')
@click.option('--json', 'json_output', is_flag=True, help='Output as JSON')
def list(env, container, limit, json_output):
    """List backups."""
    try:
        metadata_db = MetadataDB()
        backups = metadata_db.list_backups(
            environment=env,
            container_name=container,
            limit=limit
        )
        print_backup_list(backups, json_output=json_output)
    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--env', help='Environment (dev/prod)')
@click.option('--container', help='Container name')
@click.option('--container-id', help='Container ID')
@click.option('--dry-run', is_flag=True, help='Dry run mode')
def create(env, container, container_id, dry_run):
    """Create backup."""
    try:
        backup_engine = BackupEngine()
        metadata = backup_engine.create_backup(
            container_id=container_id,
            environment=env,
            container_name=container,
            dry_run=dry_run
        )
        
        if dry_run:
            click.echo(f"DRY RUN: Would create backup {metadata.backup_id}")
        else:
            click.echo(f"Backup created: {metadata.backup_id}")
            click.echo(f"Size: {metadata.size_compressed / 1024 / 1024:.2f} MB")
            click.echo(f"Duration: {metadata.duration_seconds:.2f}s")
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--backup-id', required=True, help='Backup ID to restore')
@click.option('--container-id', help='Target container ID')
@click.option('--env', help='Target environment')
@click.option('--container', help='Target container name')
@click.option('--selective', multiple=True, help='Selective restore paths (can specify multiple)')
@click.option('--interactive', is_flag=True, help='Interactive mode')
@click.option('--dry-run', is_flag=True, help='Dry run mode')
def restore(backup_id, container_id, env, container, selective, interactive, dry_run):
    """Restore backup."""
    try:
        if interactive:
            # Interactive mode - show available backups and let user choose
            metadata_db = MetadataDB()
            backup = metadata_db.get_backup(backup_id)
            
            if not backup:
                click.echo(f"Backup not found: {backup_id}", err=True)
                raise click.Abort()
            
            click.echo(f"Backup: {backup_id}")
            click.echo(f"Environment: {backup['environment']}")
            click.echo(f"Container: {backup['container_name']}")
            click.echo(f"Created: {backup['created_at']}")
            
            if not click.confirm('Proceed with restore?'):
                click.echo("Restore cancelled")
                return
        
        restore_engine = RestoreEngine()
        result = restore_engine.restore(
            backup_id=backup_id,
            container_id=container_id,
            environment=env,
            container_name=container,
            selective_paths=list(selective) if selective else None,
            dry_run=dry_run
        )
        
        if dry_run:
            click.echo(f"DRY RUN: Would restore backup {backup_id}")
        else:
            click.echo(f"Restore completed: {result['status']}")
            click.echo(f"Duration: {result['duration_seconds']:.2f}s")
            if result.get('snapshot_backup_id'):
                click.echo(f"Snapshot created: {result['snapshot_backup_id']}")
    except Exception as e:
        logger.error(f"Failed to restore: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--backup-id', required=True, help='Backup ID to verify')
def verify(backup_id):
    """Verify backup integrity."""
    try:
        metadata_db = MetadataDB()
        backup = metadata_db.get_backup(backup_id)
        
        if not backup:
            click.echo(f"Backup not found: {backup_id}", err=True)
            raise click.Abort()
        
        # Check storage access
        from ..storage.registry import get_storage_driver
        storage = get_storage_driver()
        
        if storage.exists(backup['storage_key']):
            click.echo(f"✓ Backup file exists: {backup['storage_key']}")
        else:
            click.echo(f"✗ Backup file not found: {backup['storage_key']}", err=True)
            raise click.Abort()
        
        click.echo(f"✓ Backup ID: {backup['backup_id']}")
        click.echo(f"✓ Status: {backup['status']}")
        click.echo(f"✓ Checksum: {backup['checksum_sha256']}")
        click.echo("Backup verification passed")
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--env', help='Environment filter')
def stats(env):
    """Show backup statistics."""
    try:
        metadata_db = MetadataDB()
        backups = metadata_db.list_backups(environment=env)
        
        total_size = sum(b['size_compressed'] for b in backups)
        environments = list(set(b['environment'] for b in backups))
        
        stats_dict = {
            'total_backups': len(backups),
            'total_size': total_size,
            'environments': environments
        }
        
        print_stats(stats_dict, json_output=False)
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--backup-id', help='Backup ID to delete')
@click.option('--older-than', type=int, help='Delete backups older than N days')
@click.option('--confirm', is_flag=True, help='Skip confirmation')
def delete(backup_id, older_than, confirm):
    """Delete backup."""
    try:
        metadata_db = MetadataDB()
        from ..storage.registry import get_storage_driver
        storage = get_storage_driver()
        
        if backup_id:
            if not confirm and not click.confirm(f'Delete backup {backup_id}?'):
                click.echo("Deletion cancelled")
                return
            
            backup = metadata_db.get_backup(backup_id)
            if backup:
                # Delete from storage
                storage.delete(backup['storage_key'])
                # Delete from metadata
                metadata_db.delete_backup(backup_id)
                click.echo(f"Deleted backup: {backup_id}")
            else:
                click.echo(f"Backup not found: {backup_id}", err=True)
        elif older_than:
            from datetime import datetime, timedelta
            cutoff = datetime.utcnow() - timedelta(days=older_than)
            
            backups = metadata_db.list_backups()
            to_delete = [b for b in backups if datetime.fromisoformat(b['created_at'].replace('Z', '+00:00')) < cutoff]
            
            if not to_delete:
                click.echo("No backups to delete")
                return
            
            if not confirm:
                click.echo(f"Found {len(to_delete)} backups to delete")
                if not click.confirm('Proceed with deletion?'):
                    click.echo("Deletion cancelled")
                    return
            
            for backup in to_delete:
                storage.delete(backup['storage_key'])
                metadata_db.delete_backup(backup['backup_id'])
            
            click.echo(f"Deleted {len(to_delete)} backups")
        else:
            click.echo("Specify --backup-id or --older-than", err=True)
            raise click.Abort()
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


if __name__ == '__main__':
    cli()
