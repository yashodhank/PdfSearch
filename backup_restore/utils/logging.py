"""Structured logging setup with secret redaction."""

import logging
import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any
import re

from ..config import get_config


class SecretRedactionFilter(logging.Filter):
    """Filter to redact secrets from log messages."""
    
    # Common secret patterns
    SECRET_PATTERNS = [
        (r'password["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'password": "***REDACTED***"'),
        (r'secret["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'secret": "***REDACTED***"'),
        (r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'api_key": "***REDACTED***"'),
        (r'access[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'access_key": "***REDACTED***"'),
        (r'secret[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'secret_key": "***REDACTED***"'),
        (r'token["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'token": "***REDACTED***"'),
        (r'sk-[a-zA-Z0-9]+', 'sk-***REDACTED***'),
        (r'AKIA[0-9A-Z]{16}', 'AKIA***REDACTED***'),
    ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Redact secrets from log record."""
        if hasattr(record, 'msg') and record.msg:
            msg = str(record.msg)
            for pattern, replacement in self.SECRET_PATTERNS:
                msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)
            record.msg = msg
        
        if hasattr(record, 'args') and record.args:
            args = list(record.args)
            for i, arg in enumerate(args):
                if isinstance(arg, str):
                    for pattern, replacement in self.SECRET_PATTERNS:
                        args[i] = re.sub(pattern, replacement, arg, flags=re.IGNORECASE)
            record.args = tuple(args)
        
        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            'timestamp': self.formatTime(record, self.datefmt),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName', 'relativeCreated',
                          'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info']:
                log_data[key] = value
        
        return json.dumps(log_data)


def setup_logging(
    level: Optional[str] = None,
    format_type: Optional[str] = None,
    log_file: Optional[Path] = None
) -> None:
    """Setup logging configuration.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format_type: Format type ('json' or 'text')
        log_file: Optional log file path
    """
    config = get_config()
    
    log_level = level or config.logging_level
    fmt_type = format_type or config.logging_format
    log_path = log_file or config.logging_file
    
    # Get root logger
    logger = logging.getLogger('backup_restore')
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create formatter
    if fmt_type == 'json':
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Add secret redaction filter
    secret_filter = SecretRedactionFilter()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(secret_filter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(secret_filter)
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get logger instance for a module.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(f'backup_restore.{name}')
