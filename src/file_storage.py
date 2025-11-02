"""
File storage utilities for secure file attachment handling.
"""
import os
import uuid
import hashlib
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Allowed file types (MIME types)
ALLOWED_CONTENT_TYPES = {
    # Text files
    "text/plain", "text/csv", "text/html", "text/css", "text/javascript",
    # Documents
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Images
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    # Archives
    "application/zip", "application/x-tar", "application/gzip",
    "application/x-compressed", "application/x-zip-compressed",
    # Data formats
    "application/json", "application/xml", "text/xml",
    # Code files
    "text/x-python", "text/x-java", "text/x-c++", "text/x-c",
    "application/javascript", "application/x-sh", "text/x-shellscript",
}

# Blocked executable types
BLOCKED_CONTENT_TYPES = {
    "application/x-msdownload",  # .exe
    "application/x-executable",
    "application/x-sharedlib",
    "application/x-elf",
    "application/x-mach-binary",
    "application/x-dosexec",
}

# Default max file size: 10MB
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024


def get_attachments_directory() -> str:
    """Get the attachments storage directory, creating it if needed."""
    attachments_dir = os.getenv("TODO_ATTACHMENTS_DIR", "/app/data/attachments")
    os.makedirs(attachments_dir, exist_ok=True)
    return attachments_dir


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent directory traversal and other security issues.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove path components
    filename = os.path.basename(filename)
    
    # Remove or replace dangerous characters
    dangerous_chars = ['/', '\\', '..', '\x00']
    for char in dangerous_chars:
        filename = filename.replace(char, '_')
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:250] + ext
    
    return filename


def generate_unique_filename(original_filename: str, task_id: int) -> Tuple[str, str]:
    """
    Generate a unique filename for storage.
    
    Args:
        original_filename: Original filename from upload
        task_id: Task ID this file belongs to
        
    Returns:
        Tuple of (storage_filename, file_path)
    """
    # Sanitize the original filename
    safe_filename = sanitize_filename(original_filename)
    
    # Generate unique identifier
    unique_id = str(uuid.uuid4())
    name, ext = os.path.splitext(safe_filename)
    
    # Create storage filename: {task_id}_{unique_id}{ext}
    storage_filename = f"{task_id}_{unique_id}{ext}"
    
    # Create file path
    attachments_dir = get_attachments_directory()
    file_path = os.path.join(attachments_dir, storage_filename)
    
    return storage_filename, file_path


def validate_file_type(content_type: str) -> bool:
    """
    Validate that file type is allowed.
    
    Args:
        content_type: MIME content type
        
    Returns:
        True if allowed, False otherwise
    """
    if not content_type:
        return False
    
    # Check blocked types first
    if content_type in BLOCKED_CONTENT_TYPES:
        return False
    
    # Check allowed types
    if content_type in ALLOWED_CONTENT_TYPES:
        return True
    
    # Allow types that start with known safe prefixes
    safe_prefixes = ["text/", "image/", "application/json", "application/pdf"]
    for prefix in safe_prefixes:
        if content_type.startswith(prefix):
            # Additional validation for application/* - only allow specific ones
            if prefix == "application/" and content_type not in ALLOWED_CONTENT_TYPES:
                continue
            return True
    
    return False


def validate_file_size(file_size: int, max_size: Optional[int] = None) -> bool:
    """
    Validate that file size is within limits.
    
    Args:
        file_size: File size in bytes
        max_size: Maximum allowed size (defaults to DEFAULT_MAX_FILE_SIZE)
        
    Returns:
        True if within limit, False otherwise
    """
    if max_size is None:
        max_size = int(os.getenv("TODO_MAX_ATTACHMENT_SIZE", DEFAULT_MAX_FILE_SIZE))
    
    return file_size <= max_size


def save_file(file_content: bytes, file_path: str) -> None:
    """
    Save file content to disk securely.
    
    Args:
        file_content: File content as bytes
        file_path: Path where to save the file
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Write file
    with open(file_path, 'wb') as f:
        f.write(file_content)
    
    # Set secure permissions (read/write for owner only)
    os.chmod(file_path, 0o600)
    
    logger.info(f"Saved file to {file_path} ({len(file_content)} bytes)")


def read_file(file_path: str) -> bytes:
    """
    Read file content from disk.
    
    Args:
        file_path: Path to file
        
    Returns:
        File content as bytes
        
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    with open(file_path, 'rb') as f:
        return f.read()


def delete_file(file_path: str) -> bool:
    """
    Delete file from disk.
    
    Args:
        file_path: Path to file
        
    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to delete file {file_path}: {e}")
        return False
