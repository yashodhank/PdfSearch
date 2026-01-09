"""S3-compatible storage driver (AWS S3, Wasabi, MinIO)."""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base import StorageDriver
from ..core.exceptions import StorageError
from ..utils.logging import get_logger
from ..config import get_config

logger = get_logger(__name__)


class S3StorageDriver(StorageDriver):
    """S3-compatible storage driver."""
    
    def __init__(
        self,
        bucket: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        region: Optional[str] = None
    ):
        """Initialize S3 storage driver.
        
        Args:
            bucket: S3 bucket name
            endpoint_url: Custom endpoint URL (for Wasabi, MinIO)
            access_key_id: Access key ID
            secret_access_key: Secret access key
            region: AWS region
        """
        config = get_config()
        
        self.bucket = bucket or config.storage_s3_bucket
        self.endpoint_url = endpoint_url or config.storage_s3_endpoint_url
        self.region = region or config.storage_s3_region
        
        access_key = access_key_id or config.storage_s3_access_key_id
        secret_key = secret_access_key or config.storage_s3_secret_access_key
        
        if not access_key or not secret_key:
            raise StorageError("S3 credentials not configured")
        
        # Initialize S3 client
        s3_config = {
            'aws_access_key_id': access_key,
            'aws_secret_access_key': secret_key,
            'region_name': self.region
        }
        
        if self.endpoint_url:
            s3_config['endpoint_url'] = self.endpoint_url
        
        try:
            self.s3_client = boto3.client('s3', **s3_config)
            # Test connection
            self.s3_client.head_bucket(Bucket=self.bucket)
            logger.info(f"Initialized S3 storage: bucket={self.bucket}, endpoint={self.endpoint_url}")
        except ClientError as e:
            raise StorageError(f"Failed to connect to S3: {e}")
        except NoCredentialsError:
            raise StorageError("S3 credentials not found")
    
    def upload(self, local_path: Path, remote_key: str) -> str:
        """Upload file to S3.
        
        Args:
            local_path: Local file path
            remote_key: S3 object key
        
        Returns:
            S3 object URL
        """
        try:
            # Use multipart upload for large files (>100MB)
            file_size = local_path.stat().st_size
            if file_size > 100 * 1024 * 1024:  # 100MB
                self._upload_multipart(local_path, remote_key)
            else:
                self.s3_client.upload_file(
                    str(local_path),
                    self.bucket,
                    remote_key
                )
            
            logger.debug(f"Uploaded {local_path} to s3://{self.bucket}/{remote_key}")
            return f"s3://{self.bucket}/{remote_key}"
        except ClientError as e:
            raise StorageError(f"Failed to upload file to S3: {e}")
    
    def _upload_multipart(self, local_path: Path, remote_key: str) -> None:
        """Upload large file using multipart upload.
        
        Args:
            local_path: Local file path
            remote_key: S3 object key
        """
        try:
            # Create multipart upload
            mpu = self.s3_client.create_multipart_upload(
                Bucket=self.bucket,
                Key=remote_key
            )
            upload_id = mpu['UploadId']
            
            # Upload parts
            part_number = 1
            parts = []
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            
            with open(local_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    part = self.s3_client.upload_part(
                        Bucket=self.bucket,
                        Key=remote_key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk
                    )
                    parts.append({
                        'ETag': part['ETag'],
                        'PartNumber': part_number
                    })
                    part_number += 1
            
            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=remote_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
        except Exception as e:
            # Abort on error
            try:
                self.s3_client.abort_multipart_upload(
                    Bucket=self.bucket,
                    Key=remote_key,
                    UploadId=upload_id
                )
            except:
                pass
            raise StorageError(f"Multipart upload failed: {e}")
    
    def download(self, remote_key: str, local_path: Path) -> None:
        """Download file from S3.
        
        Args:
            remote_key: S3 object key
            local_path: Local destination path
        """
        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            self.s3_client.download_file(
                self.bucket,
                remote_key,
                str(local_path)
            )
            logger.debug(f"Downloaded s3://{self.bucket}/{remote_key} to {local_path}")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                raise StorageError(f"File not found: {remote_key}")
            raise StorageError(f"Failed to download file from S3: {e}")
    
    def list(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List files in S3 bucket.
        
        Args:
            prefix: Optional prefix filter
        
        Returns:
            List of file info dictionaries
        """
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            
            files = []
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'modified': obj['LastModified'].timestamp()
                        })
            
            return files
        except ClientError as e:
            raise StorageError(f"Failed to list files in S3: {e}")
    
    def delete(self, remote_key: str) -> None:
        """Delete file from S3.
        
        Args:
            remote_key: S3 object key
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket,
                Key=remote_key
            )
            logger.debug(f"Deleted s3://{self.bucket}/{remote_key}")
        except ClientError as e:
            raise StorageError(f"Failed to delete file from S3: {e}")
    
    def exists(self, remote_key: str) -> bool:
        """Check if file exists in S3.
        
        Args:
            remote_key: S3 object key
        
        Returns:
            True if file exists
        """
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=remote_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise StorageError(f"Failed to check file existence: {e}")
