"""
Attachment service - business logic for file attachment operations.
This layer contains no HTTP framework dependencies.
Handles file validation, size limits, type checking, storage, and metadata management.
"""
import logging
import os
from typing import Optional, Dict, Any, List

from todorama.database import TodoDatabase
from todorama.file_storage import (
    validate_file_type,
    validate_file_size,
    generate_unique_filename,
    save_file,
    read_file,
    delete_file,
    DEFAULT_MAX_FILE_SIZE,
    get_attachments_directory,
)

logger = logging.getLogger(__name__)


class AttachmentService:
    """Service for attachment business logic."""
    
    def __init__(self, db: TodoDatabase):
        """Initialize attachment service with database dependency."""
        self.db = db
    
    def upload_attachment(
        self,
        task_id: int,
        file_content: bytes,
        original_filename: str,
        content_type: str,
        uploaded_by: str,
        description: Optional[str] = None,
        max_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Upload a file attachment to a task.
        
        Args:
            task_id: Task ID to attach file to
            file_content: File content as bytes
            original_filename: Original filename from upload
            content_type: MIME content type
            uploaded_by: Agent/user ID who uploaded the file
            description: Optional file description
            max_size: Optional maximum file size (defaults to DEFAULT_MAX_FILE_SIZE)
            
        Returns:
            Created attachment data as dictionary
            
        Raises:
            ValueError: If validation fails (task doesn't exist, invalid file type, file too large)
            FileNotFoundError: If task doesn't exist
        """
        # Verify task exists
        task = self.db.get_task(task_id)
        if not task:
            raise ValueError(f"Task with ID {task_id} not found")
        
        # Validate file type
        if not validate_file_type(content_type):
            raise ValueError(f"File type '{content_type}' is not allowed")
        
        # Validate file size
        file_size = len(file_content)
        if max_size is None:
            max_size = int(os.getenv("TODO_MAX_ATTACHMENT_SIZE", DEFAULT_MAX_FILE_SIZE))
        
        if not validate_file_size(file_size, max_size):
            raise ValueError(
                f"File size {file_size} bytes exceeds maximum allowed size of {max_size} bytes"
            )
        
        # Generate unique filename and file path
        storage_filename, file_path = generate_unique_filename(original_filename, task_id)
        
        # Save file to disk
        try:
            save_file(file_content, file_path)
        except Exception as e:
            logger.error(f"Failed to save attachment file: {str(e)}", exc_info=True)
            raise Exception("Failed to save attachment file. Please try again.")
        
        # Create attachment record in database
        try:
            attachment_id = self.db.create_attachment(
                task_id=task_id,
                filename=storage_filename,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                content_type=content_type,
                uploaded_by=uploaded_by,
                description=description
            )
        except Exception as e:
            # If database insert fails, clean up the saved file
            try:
                delete_file(file_path)
            except Exception:
                pass  # Ignore cleanup errors
            
            logger.error(f"Failed to create attachment record: {str(e)}", exc_info=True)
            raise Exception("Failed to create attachment record. Please try again.")
        
        # Retrieve created attachment
        attachment = self.db.get_attachment(attachment_id)
        if not attachment:
            logger.error(f"Attachment {attachment_id} was created but could not be retrieved")
            raise Exception("Attachment was created but could not be retrieved.")
        
        logger.info(f"Uploaded attachment {attachment_id} for task {task_id}")
        return dict(attachment)
    
    def get_attachment(self, attachment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get an attachment by ID.
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            Attachment data as dictionary, or None if not found
        """
        attachment = self.db.get_attachment(attachment_id)
        if attachment:
            return dict(attachment)
        return None
    
    def list_attachments(self, task_id: int) -> List[Dict[str, Any]]:
        """
        List all attachments for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of attachment data dictionaries
        """
        attachments = self.db.get_task_attachments(task_id)
        return [dict(attachment) for attachment in attachments]
    
    def delete_attachment(self, attachment_id: int) -> bool:
        """
        Delete an attachment (both record and file).
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            True if deleted successfully, False if attachment not found
            
        Raises:
            Exception: If file deletion fails (record is still deleted)
        """
        # Get attachment to retrieve file path
        attachment = self.db.get_attachment(attachment_id)
        if not attachment:
            return False
        
        attachment_dict = dict(attachment)
        file_path = attachment_dict.get("file_path")
        
        # Delete database record (this also attempts to delete the file)
        success = self.db.delete_attachment(attachment_id)
        
        if not success:
            return False
        
        # Ensure file is deleted from disk (database method may have failed)
        if file_path:
            try:
                delete_file(file_path)
            except Exception as e:
                logger.warning(f"Failed to delete attachment file {file_path}: {e}")
                # Don't raise - record is already deleted
        
        logger.info(f"Deleted attachment {attachment_id}")
        return True
    
    def download_attachment(self, attachment_id: int) -> Optional[Dict[str, Any]]:
        """
        Download an attachment (returns file content and metadata).
        
        Args:
            attachment_id: Attachment ID
            
        Returns:
            Dictionary with 'content' (bytes) and 'metadata' (dict), or None if not found
            
        Raises:
            FileNotFoundError: If attachment file doesn't exist on disk
            Exception: If file read fails
        """
        attachment = self.db.get_attachment(attachment_id)
        if not attachment:
            return None
        
        attachment_dict = dict(attachment)
        file_path = attachment_dict.get("file_path")
        
        if not file_path:
            logger.error(f"Attachment {attachment_id} has no file_path")
            raise Exception("Attachment file path is missing")
        
        # Read file content
        try:
            file_content = read_file(file_path)
        except FileNotFoundError:
            logger.error(f"Attachment file not found: {file_path}")
            raise FileNotFoundError(f"Attachment file not found: {file_path}")
        except Exception as e:
            logger.error(f"Failed to read attachment file {file_path}: {str(e)}", exc_info=True)
            raise Exception(f"Failed to read attachment file: {str(e)}")
        
        return {
            "content": file_content,
            "metadata": attachment_dict
        }
    
    def get_attachment_by_task_and_id(
        self,
        task_id: int,
        attachment_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get an attachment by task ID and attachment ID (for security validation).
        
        Args:
            task_id: Task ID
            attachment_id: Attachment ID
            
        Returns:
            Attachment data as dictionary, or None if not found or doesn't belong to task
        """
        attachment = self.db.get_attachment_by_task_and_id(task_id, attachment_id)
        if attachment:
            return dict(attachment)
        return None
