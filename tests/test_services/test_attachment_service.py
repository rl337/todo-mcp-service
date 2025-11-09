"""
Unit tests for AttachmentService.
Tests business logic in isolation without HTTP framework dependencies.
"""
import pytest
import sys
import os
import tempfile
from unittest.mock import Mock, MagicMock, patch

# Mock problematic imports before importing service
sys.modules['todorama.database'] = MagicMock()
sys.modules['todorama.tracing'] = MagicMock()

# Import service module directly to avoid __init__.py importing other services
import importlib.util
service_path = os.path.join(os.path.dirname(__file__), '..', '..', 'todorama', 'services', 'attachment_service.py')
spec = importlib.util.spec_from_file_location("attachment_service", service_path)
attachment_service_module = importlib.util.module_from_spec(spec)
sys.modules['todorama.services.attachment_service'] = attachment_service_module
spec.loader.exec_module(attachment_service_module)
AttachmentService = attachment_service_module.AttachmentService


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    return db


@pytest.fixture
def attachment_service(mock_db):
    """Create an AttachmentService instance with mocked database."""
    return AttachmentService(mock_db)


class TestUploadAttachment:
    """Tests for upload_attachment method."""
    
    @patch.object(attachment_service_module, 'validate_file_type')
    @patch.object(attachment_service_module, 'validate_file_size')
    @patch.object(attachment_service_module, 'generate_unique_filename')
    @patch.object(attachment_service_module, 'save_file')
    def test_upload_attachment_success(
        self,
        mock_save_file,
        mock_generate_filename,
        mock_validate_size,
        mock_validate_type,
        attachment_service,
        mock_db
    ):
        """Test successful attachment upload."""
        # Setup
        task_id = 1
        file_content = b"Test file content"
        original_filename = "test.txt"
        content_type = "text/plain"
        uploaded_by = "test-agent"
        description = "Test description"
        
        mock_db.get_task.return_value = {"id": task_id, "title": "Test Task"}
        mock_validate_type.return_value = True
        mock_validate_size.return_value = True
        mock_generate_filename.return_value = ("1_uuid.txt", "/tmp/attachments/1_uuid.txt")
        mock_db.create_attachment.return_value = 1
        mock_db.get_attachment.return_value = {
            "id": 1,
            "task_id": task_id,
            "filename": "1_uuid.txt",
            "original_filename": original_filename,
            "file_path": "/tmp/attachments/1_uuid.txt",
            "file_size": len(file_content),
            "content_type": content_type,
            "description": description,
            "uploaded_by": uploaded_by,
            "created_at": "2024-01-01T00:00:00"
        }
        
        # Execute
        result = attachment_service.upload_attachment(
            task_id=task_id,
            file_content=file_content,
            original_filename=original_filename,
            content_type=content_type,
            uploaded_by=uploaded_by,
            description=description
        )
        
        # Verify
        assert result["id"] == 1
        assert result["task_id"] == task_id
        assert result["original_filename"] == original_filename
        assert result["file_size"] == len(file_content)
        mock_db.get_task.assert_called_once_with(task_id)
        mock_validate_type.assert_called_once_with(content_type)
        mock_validate_size.assert_called_once()
        mock_generate_filename.assert_called_once_with(original_filename, task_id)
        mock_save_file.assert_called_once_with(file_content, "/tmp/attachments/1_uuid.txt")
        mock_db.create_attachment.assert_called_once()
        mock_db.get_attachment.assert_called_once_with(1)
    
    def test_upload_attachment_task_not_found(self, attachment_service, mock_db):
        """Test upload when task doesn't exist."""
        # Setup
        mock_db.get_task.return_value = None
        
        # Execute & Verify
        with pytest.raises(ValueError, match="Task with ID 999 not found"):
            attachment_service.upload_attachment(
                task_id=999,
                file_content=b"content",
                original_filename="test.txt",
                content_type="text/plain",
                uploaded_by="test-agent"
            )
        
        mock_db.get_task.assert_called_once_with(999)
        mock_db.create_attachment.assert_not_called()
    
    @patch.object(attachment_service_module, 'validate_file_type')
    def test_upload_attachment_invalid_file_type(
        self,
        mock_validate_type,
        attachment_service,
        mock_db
    ):
        """Test upload with invalid file type."""
        # Setup
        mock_db.get_task.return_value = {"id": 1, "title": "Test Task"}
        mock_validate_type.return_value = False
        
        # Execute & Verify
        with pytest.raises(ValueError, match="File type 'application/x-executable' is not allowed"):
            attachment_service.upload_attachment(
                task_id=1,
                file_content=b"content",
                original_filename="malware.exe",
                content_type="application/x-executable",
                uploaded_by="test-agent"
            )
        
        mock_validate_type.assert_called_once_with("application/x-executable")
        mock_db.create_attachment.assert_not_called()
    
    @patch.object(attachment_service_module, 'validate_file_type')
    @patch.object(attachment_service_module, 'validate_file_size')
    def test_upload_attachment_file_too_large(
        self,
        mock_validate_size,
        mock_validate_type,
        attachment_service,
        mock_db
    ):
        """Test upload with file that's too large."""
        # Setup
        mock_db.get_task.return_value = {"id": 1, "title": "Test Task"}
        mock_validate_type.return_value = True
        mock_validate_size.return_value = False
        
        # Execute & Verify
        with pytest.raises(ValueError, match="File size .* exceeds maximum allowed size"):
            attachment_service.upload_attachment(
                task_id=1,
                file_content=b"x" * (20 * 1024 * 1024),  # 20MB
                original_filename="large.txt",
                content_type="text/plain",
                uploaded_by="test-agent"
            )
        
        mock_validate_size.assert_called_once()
        mock_db.create_attachment.assert_not_called()
    
    @patch.object(attachment_service_module, 'validate_file_type')
    @patch.object(attachment_service_module, 'validate_file_size')
    @patch.object(attachment_service_module, 'generate_unique_filename')
    @patch.object(attachment_service_module, 'save_file')
    @patch.object(attachment_service_module, 'delete_file')
    def test_upload_attachment_database_failure_cleans_up_file(
        self,
        mock_delete_file,
        mock_save_file,
        mock_generate_filename,
        mock_validate_size,
        mock_validate_type,
        attachment_service,
        mock_db
    ):
        """Test that file is cleaned up if database insert fails."""
        # Setup
        mock_db.get_task.return_value = {"id": 1, "title": "Test Task"}
        mock_validate_type.return_value = True
        mock_validate_size.return_value = True
        mock_generate_filename.return_value = ("1_uuid.txt", "/tmp/attachments/1_uuid.txt")
        mock_db.create_attachment.side_effect = Exception("Database error")
        
        # Execute & Verify
        with pytest.raises(Exception, match="Failed to create attachment record"):
            attachment_service.upload_attachment(
                task_id=1,
                file_content=b"content",
                original_filename="test.txt",
                content_type="text/plain",
                uploaded_by="test-agent"
            )
        
        mock_save_file.assert_called_once()
        mock_delete_file.assert_called_once_with("/tmp/attachments/1_uuid.txt")


class TestGetAttachment:
    """Tests for get_attachment method."""
    
    def test_get_attachment_success(self, attachment_service, mock_db):
        """Test successful attachment retrieval."""
        # Setup
        mock_db.get_attachment.return_value = {
            "id": 1,
            "task_id": 1,
            "filename": "test.txt",
            "original_filename": "test.txt",
            "file_path": "/tmp/attachments/1_uuid.txt",
            "file_size": 100,
            "content_type": "text/plain",
            "uploaded_by": "test-agent",
            "created_at": "2024-01-01T00:00:00"
        }
        
        # Execute
        result = attachment_service.get_attachment(1)
        
        # Verify
        assert result is not None
        assert result["id"] == 1
        assert result["task_id"] == 1
        mock_db.get_attachment.assert_called_once_with(1)
    
    def test_get_attachment_not_found(self, attachment_service, mock_db):
        """Test attachment retrieval when attachment doesn't exist."""
        # Setup
        mock_db.get_attachment.return_value = None
        
        # Execute
        result = attachment_service.get_attachment(999)
        
        # Verify
        assert result is None
        mock_db.get_attachment.assert_called_once_with(999)


class TestListAttachments:
    """Tests for list_attachments method."""
    
    def test_list_attachments_success(self, attachment_service, mock_db):
        """Test successful attachment listing."""
        # Setup
        mock_db.get_task_attachments.return_value = [
            {
                "id": 1,
                "task_id": 1,
                "filename": "test1.txt",
                "original_filename": "test1.txt",
                "file_path": "/tmp/attachments/1_uuid1.txt",
                "file_size": 100,
                "content_type": "text/plain",
                "uploaded_by": "test-agent",
                "created_at": "2024-01-01T00:00:00"
            },
            {
                "id": 2,
                "task_id": 1,
                "filename": "test2.txt",
                "original_filename": "test2.txt",
                "file_path": "/tmp/attachments/1_uuid2.txt",
                "file_size": 200,
                "content_type": "text/plain",
                "uploaded_by": "test-agent",
                "created_at": "2024-01-02T00:00:00"
            }
        ]
        
        # Execute
        result = attachment_service.list_attachments(1)
        
        # Verify
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        mock_db.get_task_attachments.assert_called_once_with(1)
    
    def test_list_attachments_empty(self, attachment_service, mock_db):
        """Test attachment listing when no attachments exist."""
        # Setup
        mock_db.get_task_attachments.return_value = []
        
        # Execute
        result = attachment_service.list_attachments(1)
        
        # Verify
        assert result == []
        mock_db.get_task_attachments.assert_called_once_with(1)


class TestDeleteAttachment:
    """Tests for delete_attachment method."""
    
    @patch.object(attachment_service_module, 'delete_file')
    def test_delete_attachment_success(
        self,
        mock_delete_file,
        attachment_service,
        mock_db
    ):
        """Test successful attachment deletion."""
        # Setup
        attachment_id = 1
        file_path = "/tmp/attachments/1_uuid.txt"
        mock_db.get_attachment.return_value = {
            "id": attachment_id,
            "task_id": 1,
            "file_path": file_path
        }
        mock_db.delete_attachment.return_value = True
        
        # Execute
        result = attachment_service.delete_attachment(attachment_id)
        
        # Verify
        assert result is True
        mock_db.get_attachment.assert_called_once_with(attachment_id)
        mock_db.delete_attachment.assert_called_once_with(attachment_id)
        mock_delete_file.assert_called_once_with(file_path)
    
    def test_delete_attachment_not_found(self, attachment_service, mock_db):
        """Test deletion when attachment doesn't exist."""
        # Setup
        mock_db.get_attachment.return_value = None
        
        # Execute
        result = attachment_service.delete_attachment(999)
        
        # Verify
        assert result is False
        mock_db.get_attachment.assert_called_once_with(999)
        mock_db.delete_attachment.assert_not_called()
    
    @patch.object(attachment_service_module, 'delete_file')
    def test_delete_attachment_file_deletion_failure(
        self,
        mock_delete_file,
        attachment_service,
        mock_db
    ):
        """Test deletion when file deletion fails (record still deleted)."""
        # Setup
        attachment_id = 1
        file_path = "/tmp/attachments/1_uuid.txt"
        mock_db.get_attachment.return_value = {
            "id": attachment_id,
            "task_id": 1,
            "file_path": file_path
        }
        mock_db.delete_attachment.return_value = True
        mock_delete_file.side_effect = Exception("File deletion failed")
        
        # Execute - should not raise, just log warning
        result = attachment_service.delete_attachment(attachment_id)
        
        # Verify
        assert result is True
        mock_delete_file.assert_called_once_with(file_path)


class TestDownloadAttachment:
    """Tests for download_attachment method."""
    
    @patch.object(attachment_service_module, 'read_file')
    def test_download_attachment_success(
        self,
        mock_read_file,
        attachment_service,
        mock_db
    ):
        """Test successful attachment download."""
        # Setup
        attachment_id = 1
        file_content = b"Test file content"
        file_path = "/tmp/attachments/1_uuid.txt"
        
        mock_db.get_attachment.return_value = {
            "id": attachment_id,
            "task_id": 1,
            "filename": "test.txt",
            "original_filename": "test.txt",
            "file_path": file_path,
            "file_size": len(file_content),
            "content_type": "text/plain",
            "uploaded_by": "test-agent",
            "created_at": "2024-01-01T00:00:00"
        }
        mock_read_file.return_value = file_content
        
        # Execute
        result = attachment_service.download_attachment(attachment_id)
        
        # Verify
        assert result is not None
        assert result["content"] == file_content
        assert result["metadata"]["id"] == attachment_id
        mock_db.get_attachment.assert_called_once_with(attachment_id)
        mock_read_file.assert_called_once_with(file_path)
    
    def test_download_attachment_not_found(self, attachment_service, mock_db):
        """Test download when attachment doesn't exist."""
        # Setup
        mock_db.get_attachment.return_value = None
        
        # Execute
        result = attachment_service.download_attachment(999)
        
        # Verify
        assert result is None
        mock_db.get_attachment.assert_called_once_with(999)
    
    @patch.object(attachment_service_module, 'read_file')
    def test_download_attachment_file_not_found(
        self,
        mock_read_file,
        attachment_service,
        mock_db
    ):
        """Test download when file doesn't exist on disk."""
        # Setup
        attachment_id = 1
        file_path = "/tmp/attachments/1_uuid.txt"
        
        mock_db.get_attachment.return_value = {
            "id": attachment_id,
            "task_id": 1,
            "file_path": file_path
        }
        mock_read_file.side_effect = FileNotFoundError(f"File not found: {file_path}")
        
        # Execute & Verify
        with pytest.raises(FileNotFoundError):
            attachment_service.download_attachment(attachment_id)
    
    def test_download_attachment_missing_file_path(self, attachment_service, mock_db):
        """Test download when attachment has no file_path."""
        # Setup
        mock_db.get_attachment.return_value = {
            "id": 1,
            "task_id": 1,
            "file_path": None
        }
        
        # Execute & Verify
        with pytest.raises(Exception, match="Attachment file path is missing"):
            attachment_service.download_attachment(1)


class TestGetAttachmentByTaskAndId:
    """Tests for get_attachment_by_task_and_id method."""
    
    def test_get_attachment_by_task_and_id_success(self, attachment_service, mock_db):
        """Test successful attachment retrieval by task and ID."""
        # Setup
        task_id = 1
        attachment_id = 1
        mock_db.get_attachment_by_task_and_id.return_value = {
            "id": attachment_id,
            "task_id": task_id,
            "filename": "test.txt",
            "original_filename": "test.txt",
            "file_path": "/tmp/attachments/1_uuid.txt",
            "file_size": 100,
            "content_type": "text/plain",
            "uploaded_by": "test-agent",
            "created_at": "2024-01-01T00:00:00"
        }
        
        # Execute
        result = attachment_service.get_attachment_by_task_and_id(task_id, attachment_id)
        
        # Verify
        assert result is not None
        assert result["id"] == attachment_id
        assert result["task_id"] == task_id
        mock_db.get_attachment_by_task_and_id.assert_called_once_with(task_id, attachment_id)
    
    def test_get_attachment_by_task_and_id_not_found(self, attachment_service, mock_db):
        """Test retrieval when attachment doesn't belong to task."""
        # Setup
        mock_db.get_attachment_by_task_and_id.return_value = None
        
        # Execute
        result = attachment_service.get_attachment_by_task_and_id(1, 999)
        
        # Verify
        assert result is None
        mock_db.get_attachment_by_task_and_id.assert_called_once_with(1, 999)
