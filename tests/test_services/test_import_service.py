"""
Unit tests for ImportService.
Tests business logic in isolation without HTTP framework dependencies.
"""
import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from todorama.services.import_service import ImportService


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    return db


@pytest.fixture
def import_service(mock_db):
    """Create an ImportService instance with mocked database."""
    return ImportService(mock_db)


class TestImportJSON:
    """Tests for import_json method."""
    
    def test_import_json_success(self, import_service, mock_db):
        """Test successful JSON import."""
        # Setup
        tasks = [
            {
                "title": "Task 1",
                "task_type": "concrete",
                "task_instruction": "Do something",
                "verification_instruction": "Verify it"
            },
            {
                "title": "Task 2",
                "task_type": "concrete",
                "task_instruction": "Do something else",
                "verification_instruction": "Verify it too"
            }
        ]
        mock_db.query_tasks.return_value = []  # No duplicates
        mock_db.create_task.side_effect = [1, 2]  # Return task IDs
        
        # Execute
        result = import_service.import_json(
            tasks=tasks,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error"
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 2
        assert result["created"] == 2
        assert result["task_ids"] == [1, 2]
        assert len(result["errors"]) == 0
        assert len(result["skipped_tasks"]) == 0
        assert mock_db.create_task.call_count == 2
    
    def test_import_json_with_duplicates_skip(self, import_service, mock_db):
        """Test JSON import with duplicate skipping."""
        # Setup
        tasks = [
            {
                "title": "Task 1",
                "task_type": "concrete",
                "task_instruction": "Do something",
                "verification_instruction": "Verify it"
            },
            {
                "title": "Task 1",  # Duplicate in batch
                "task_type": "concrete",
                "task_instruction": "Do something",
                "verification_instruction": "Verify it"
            }
        ]
        mock_db.query_tasks.return_value = []  # No existing duplicates
        mock_db.create_task.return_value = 1
        
        # Execute
        result = import_service.import_json(
            tasks=tasks,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="skip"
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 1
        assert result["created"] == 1
        assert len(result["skipped_tasks"]) == 1
        assert result["skipped_tasks"][0]["reason"] == "duplicate in batch"
        assert mock_db.create_task.call_count == 1
    
    def test_import_json_with_existing_duplicate(self, import_service, mock_db):
        """Test JSON import skipping existing duplicate."""
        # Setup
        tasks = [
            {
                "title": "Existing Task",
                "task_type": "concrete",
                "task_instruction": "Do something",
                "verification_instruction": "Verify it"
            }
        ]
        # Return existing task with same title
        mock_db.query_tasks.return_value = [
            {"id": 99, "title": "Existing Task", "task_type": "concrete"}
        ]
        
        # Execute
        result = import_service.import_json(
            tasks=tasks,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="skip"
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 0
        assert len(result["skipped_tasks"]) == 1
        assert result["skipped_tasks"][0]["reason"] == "duplicate"
        assert mock_db.create_task.call_count == 0
    
    def test_import_json_with_relationships(self, import_service, mock_db):
        """Test JSON import with parent-child relationships."""
        # Setup
        tasks = [
            {
                "title": "Parent Task",
                "task_type": "concrete",
                "task_instruction": "Parent instruction",
                "verification_instruction": "Verify parent",
                "import_id": "parent-1"
            },
            {
                "title": "Child Task",
                "task_type": "concrete",
                "task_instruction": "Child instruction",
                "verification_instruction": "Verify child",
                "import_id": "child-1",
                "parent_import_id": "parent-1",
                "relationship_type": "subtask"
            }
        ]
        mock_db.query_tasks.return_value = []
        mock_db.create_task.side_effect = [1, 2]  # Parent=1, Child=2
        
        # Execute
        result = import_service.import_json(
            tasks=tasks,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error"
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 2
        assert mock_db.create_task.call_count == 2
        # Verify relationship was created
        mock_db.create_relationship.assert_called_once_with(
            parent_task_id=1,
            child_task_id=2,
            relationship_type="subtask",
            agent_id="test-agent"
        )
    
    def test_import_json_with_due_date(self, import_service, mock_db):
        """Test JSON import with due date parsing."""
        # Setup
        tasks = [
            {
                "title": "Task with Due Date",
                "task_type": "concrete",
                "task_instruction": "Do something",
                "verification_instruction": "Verify it",
                "due_date": "2024-12-31T23:59:59Z"
            }
        ]
        mock_db.query_tasks.return_value = []
        mock_db.create_task.return_value = 1
        
        # Execute
        result = import_service.import_json(
            tasks=tasks,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error"
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 1
        # Verify due_date was parsed correctly
        call_args = mock_db.create_task.call_args
        assert call_args[1]["due_date"] is not None
        assert isinstance(call_args[1]["due_date"], datetime)
    
    def test_import_json_with_errors(self, import_service, mock_db):
        """Test JSON import handling errors gracefully."""
        # Setup
        tasks = [
            {
                "title": "Valid Task",
                "task_type": "concrete",
                "task_instruction": "Do something",
                "verification_instruction": "Verify it"
            },
            {
                "title": "Invalid Task",
                # Missing required fields
            }
        ]
        mock_db.query_tasks.return_value = []
        mock_db.create_task.side_effect = [1, Exception("Missing required field")]
        
        # Execute
        result = import_service.import_json(
            tasks=tasks,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error"
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 1
        assert result["error_count"] == 1
        assert len(result["errors"]) == 1


class TestImportCSV:
    """Tests for import_csv method."""
    
    def test_import_csv_success(self, import_service, mock_db):
        """Test successful CSV import."""
        # Setup
        csv_content = """title,task_type,task_instruction,verification_instruction
Task 1,concrete,Do something,Verify it
Task 2,concrete,Do something else,Verify it too"""
        mock_db.query_tasks.return_value = []
        mock_db.create_task.side_effect = [1, 2]
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error",
            field_mapping=None
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 2
        assert result["created"] == 2
        assert result["task_ids"] == [1, 2]
        assert len(result["errors"]) == 0
        assert mock_db.create_task.call_count == 2
    
    def test_import_csv_with_field_mapping(self, import_service, mock_db):
        """Test CSV import with field mapping."""
        # Setup
        csv_content = """Task Title,Type,Instruction,Verification
Task 1,concrete,Do something,Verify it"""
        field_mapping = {
            "title": "Task Title",
            "task_type": "Type",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.query_tasks.return_value = []
        mock_db.create_task.return_value = 1
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error",
            field_mapping=field_mapping
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 1
        # Verify correct fields were used
        call_args = mock_db.create_task.call_args
        assert call_args[1]["title"] == "Task 1"
        assert call_args[1]["task_type"] == "concrete"
        assert call_args[1]["task_instruction"] == "Do something"
    
    def test_import_csv_missing_required_fields(self, import_service, mock_db):
        """Test CSV import with missing required fields."""
        # Setup
        csv_content = """title,task_type
Task 1,concrete"""
        # Missing task_instruction and verification_instruction
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error",
            field_mapping=None
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 0
        assert result["error_count"] == 1
        assert len(result["errors"]) == 1
        assert "Missing required field" in result["errors"][0]["error"]
        assert mock_db.create_task.call_count == 0
    
    def test_import_csv_with_duplicates_skip(self, import_service, mock_db):
        """Test CSV import skipping duplicates."""
        # Setup
        csv_content = """title,task_type,task_instruction,verification_instruction
Existing Task,concrete,Do something,Verify it"""
        # Return existing task
        mock_db.query_tasks.return_value = [
            {"id": 99, "title": "Existing Task", "task_type": "concrete"}
        ]
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="skip",
            field_mapping=None
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 0
        assert len(result["skipped_tasks"]) == 1
        assert result["skipped_tasks"][0]["reason"] == "duplicate"
        assert mock_db.create_task.call_count == 0
    
    def test_import_csv_with_optional_fields(self, import_service, mock_db):
        """Test CSV import with optional fields (project_id, estimated_hours, due_date)."""
        # Setup
        csv_content = """title,task_type,task_instruction,verification_instruction,project_id,estimated_hours,due_date,priority,notes
Task 1,concrete,Do something,Verify it,1,2.5,2024-12-31T23:59:59,high,Test notes"""
        mock_db.query_tasks.return_value = []
        mock_db.create_task.return_value = 1
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error",
            field_mapping=None
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 1
        call_args = mock_db.create_task.call_args
        assert call_args[1]["project_id"] == 1
        assert call_args[1]["estimated_hours"] == 2.5
        assert call_args[1]["priority"] == "high"
        assert call_args[1]["notes"] == "Test notes"
        assert call_args[1]["due_date"] is not None
    
    def test_import_csv_invalid_due_date(self, import_service, mock_db):
        """Test CSV import with invalid due date (should skip parsing, not fail)."""
        # Setup
        csv_content = """title,task_type,task_instruction,verification_instruction,due_date
Task 1,concrete,Do something,Verify it,invalid-date"""
        mock_db.query_tasks.return_value = []
        mock_db.create_task.return_value = 1
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error",
            field_mapping=None
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 1
        # Invalid due_date should be None, not cause an error
        call_args = mock_db.create_task.call_args
        assert call_args[1]["due_date"] is None
    
    def test_import_csv_with_errors(self, import_service, mock_db):
        """Test CSV import handling errors gracefully."""
        # Setup
        csv_content = """title,task_type,task_instruction,verification_instruction
Task 1,concrete,Do something,Verify it"""
        mock_db.query_tasks.return_value = []
        mock_db.create_task.side_effect = Exception("Database error")
        
        # Execute
        result = import_service.import_csv(
            csv_content=csv_content,
            agent_id="test-agent",
            project_id=None,
            handle_duplicates="error",
            field_mapping=None
        )
        
        # Verify
        assert result["success"] is True
        assert result["imported_count"] == 0
        assert result["error_count"] == 1
        assert len(result["errors"]) == 1
