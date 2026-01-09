"""Compression utilities for backup files."""

import tarfile
import hashlib
from pathlib import Path
from typing import Optional, BinaryIO, Tuple
import io

try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    ZSTD_AVAILABLE = False


def compress_directory(
    source_dir: Path,
    output_path: Path,
    compression: str = 'zstd',
    compression_level: int = 3,
    exclude_patterns: Optional[list] = None
) -> Tuple[int, int, str]:
    """Compress directory to tar archive with compression.
    
    Args:
        source_dir: Directory to compress
        compression: Compression type ('zstd' or 'gzip')
        compression_level: Compression level (1-9 for gzip, 1-22 for zstd)
        exclude_patterns: Patterns to exclude
    
    Returns:
        Tuple of (raw_size, compressed_size, sha256_checksum)
    """
    raw_size = 0
    checksum = hashlib.sha256()
    
    # Determine compression
    if compression == 'zstd' and ZSTD_AVAILABLE:
        mode = 'w'
        ext = '.tar.zst'
        compressobj = None  # Will use tarfile's zstd support if available
    else:
        mode = 'w:gz'
        ext = '.tar.gz'
        compressobj = None
    
    # Ensure output has correct extension
    if not str(output_path).endswith(ext):
        output_path = Path(str(output_path) + ext)
    
    # Create tar archive
    if compression == 'zstd' and ZSTD_AVAILABLE:
        # Use zstandard directly for better control
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
            _add_directory_to_tar(tar, source_dir, source_dir, exclude_patterns or [])
        
        # Calculate raw size (actual tar data size)
        tar_buffer.seek(0, 2)  # Seek to end
        raw_size = tar_buffer.tell()
        tar_buffer.seek(0)  # Reset to beginning
        
        # Compress with zstd
        cctx = zstd.ZstdCompressor(level=compression_level)
        with open(output_path, 'wb') as f:
            compressed_data = cctx.compress(tar_buffer.read())
            f.write(compressed_data)
            compressed_size = len(compressed_data)
            checksum.update(compressed_data)
    else:
        # Use tarfile's built-in gzip compression
        with tarfile.open(output_path, mode=mode, compresslevel=compression_level) as tar:
            _add_directory_to_tar(tar, source_dir, source_dir, exclude_patterns or [])
            # Calculate sizes and checksum
            compressed_size = output_path.stat().st_size
            with open(output_path, 'rb') as f:
                while chunk := f.read(8192):
                    checksum.update(chunk)
                    raw_size += len(chunk)  # Approximate
    
    return raw_size, compressed_size, checksum.hexdigest()


def _add_directory_to_tar(
    tar: tarfile.TarFile,
    base_path: Path,
    current_path: Path,
    exclude_patterns: list
) -> None:
    """Recursively add directory to tar archive.
    
    Args:
        tar: TarFile object
        base_path: Base directory path
        current_path: Current directory being processed
        exclude_patterns: Patterns to exclude
    """
    import fnmatch
    
    try:
        for item in current_path.iterdir():
            # Check exclude patterns
            relative_path = item.relative_to(base_path)
            if any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in exclude_patterns):
                continue
            
            if item.is_file():
                tar.add(item, arcname=str(relative_path), recursive=False)
            elif item.is_dir():
                tar.add(item, arcname=str(relative_path), recursive=False)
                _add_directory_to_tar(tar, base_path, item, exclude_patterns)
    except PermissionError:
        # Skip files we can't read
        pass


def extract_archive(
    archive_path: Path,
    extract_to: Path,
    verify_checksum: Optional[str] = None
) -> None:
    """Extract compressed tar archive.
    
    Args:
        archive_path: Path to archive file
        extract_to: Directory to extract to
        verify_checksum: Optional SHA256 checksum to verify
    
    Raises:
        ValueError: If checksum verification fails
    """
    # Verify checksum if provided
    if verify_checksum:
        checksum = hashlib.sha256()
        with open(archive_path, 'rb') as f:
            while chunk := f.read(8192):
                checksum.update(chunk)
        if checksum.hexdigest() != verify_checksum:
            raise ValueError(f"Checksum mismatch: expected {verify_checksum}, got {checksum.hexdigest()}")
    
    # Determine compression from extension
    if str(archive_path).endswith('.tar.zst') and ZSTD_AVAILABLE:
        # Extract with zstd
        dctx = zstd.ZstdDecompressor()
        with open(archive_path, 'rb') as f:
            decompressed = dctx.decompress(f.read())
        
        tar_buffer = io.BytesIO(decompressed)
        with tarfile.open(fileobj=tar_buffer, mode='r') as tar:
            extract_to.mkdir(parents=True, exist_ok=True)
            tar.extractall(extract_to)
    else:
        # Use tarfile's built-in decompression
        mode = 'r:gz' if str(archive_path).endswith('.tar.gz') else 'r'
        with tarfile.open(archive_path, mode=mode) as tar:
            extract_to.mkdir(parents=True, exist_ok=True)
            tar.extractall(extract_to)
