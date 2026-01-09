"""Output formatting utilities."""

from typing import List, Dict, Any, Optional
from datetime import datetime
import json

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size.
    
    Args:
        size_bytes: Size in bytes
    
    Returns:
        Formatted size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: float) -> str:
    """Format duration to human-readable string.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp to human-readable string.
    
    Args:
        timestamp_str: ISO timestamp string
    
    Returns:
        Formatted timestamp string
    """
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.utcnow()
        diff = now - dt.replace(tzinfo=None)
        
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "just now"
    except:
        return timestamp_str


def print_backup_list(backups: List[Dict[str, Any]], json_output: bool = False) -> None:
    """Print backup list in table or JSON format.
    
    Args:
        backups: List of backup dictionaries
        json_output: If True, output as JSON
    """
    if json_output:
        print(json.dumps(backups, indent=2, default=str))
        return
    
    if not RICH_AVAILABLE:
        # Fallback to simple text output
        for backup in backups:
            print(f"{backup['backup_id']} | {backup['container_name']} | "
                  f"{format_timestamp(backup['created_at'])} | "
                  f"{format_size(backup['size_compressed'])}")
        return
    
    # Rich table output
    console = Console()
    table = Table(title="Backups", box=box.ROUNDED)
    
    table.add_column("Backup ID", style="cyan", no_wrap=False)
    table.add_column("Container", style="magenta")
    table.add_column("Environment", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Size", style="blue", justify="right")
    table.add_column("Status", style="red" if any(b['status'] != 'completed' for b in backups) else "green")
    
    for backup in backups:
        table.add_row(
            backup['backup_id'][:50] + '...' if len(backup['backup_id']) > 50 else backup['backup_id'],
            backup['container_name'],
            backup['environment'],
            format_timestamp(backup['created_at']),
            format_size(backup['size_compressed']),
            backup['status']
        )
    
    console.print(table)


def print_container_list(containers: List[Dict[str, Any]], json_output: bool = False) -> None:
    """Print container list in table or JSON format.
    
    Args:
        containers: List of container dictionaries
        json_output: If True, output as JSON
    """
    if json_output:
        print(json.dumps(containers, indent=2, default=str))
        return
    
    if not RICH_AVAILABLE:
        # Fallback to simple text output
        for container in containers:
            print(f"{container['name']} | {container['environment']} | {container['status']}")
        return
    
    # Rich table output
    console = Console()
    table = Table(title="Containers", box=box.ROUNDED)
    
    table.add_column("Name", style="cyan")
    table.add_column("Environment", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Orchestration", style="magenta")
    table.add_column("Volumes", style="blue")
    
    for container in containers:
        volumes_str = ', '.join([v['name'] for v in container.get('volumes', [])[:2]])
        if len(container.get('volumes', [])) > 2:
            volumes_str += '...'
        
        table.add_row(
            container['name'],
            container['environment'],
            container['status'],
            container.get('orchestration', 'unknown'),
            volumes_str
        )
    
    console.print(table)


def print_stats(stats: Dict[str, Any], json_output: bool = False) -> None:
    """Print statistics in table or JSON format.
    
    Args:
        stats: Statistics dictionary
        json_output: If True, output as JSON
    """
    if json_output:
        print(json.dumps(stats, indent=2, default=str))
        return
    
    if not RICH_AVAILABLE:
        # Fallback to simple text output
        print(f"Total backups: {stats.get('total_backups', 0)}")
        print(f"Total size: {format_size(stats.get('total_size', 0))}")
        return
    
    # Rich output
    console = Console()
    console.print(f"[bold]Total Backups:[/bold] {stats.get('total_backups', 0)}")
    console.print(f"[bold]Total Size:[/bold] {format_size(stats.get('total_size', 0))}")
    console.print(f"[bold]Environments:[/bold] {', '.join(stats.get('environments', []))}")
