"""
Unit tests for TemplateService.
Tests business logic in isolation without HTTP framework dependencies.
"""
import pytest
import sys
import os
from unittest.mock import Mock, MagicMock
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from todorama.services.template_service import TemplateService


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    return db


@pytest.fixture
def template_service(mock_db):
    """Create a TemplateService instance with mocked database."""
    return TemplateService(mock_db)


class TestCreateTemplate:
    """Tests for create_template method."""
    
    def test_create_template_success(self, template_service, mock_db):
        """Test successful template creation."""
        # Setup
        mock_db.create_template.return_value = 1
        mock_db.get_template.return_value = {
            "id": 1,
            "name": "Bug Fix Template",
            "task_type": "concrete",
            "task_instruction": "Fix the bug",
            "verification_instruction": "Verify bug is fixed"
        }
        
        # Execute
        result = template_service.create_template(
            name="Bug Fix Template",
            task_type="concrete",
            task_instruction="Fix the bug",
            verification_instruction="Verify bug is fixed"
        )
        
        # Verify
        assert result["id"] == 1
        assert result["name"] == "Bug Fix Template"
        mock_db.create_template.assert_called_once()
        mock_db.get_template.assert_called_once_with(1)
    
    def test_create_template_strips_whitespace(self, template_service, mock_db):
        """Test that template fields are stripped of whitespace."""
        # Setup
        mock_db.create_template.return_value = 1
        mock_db.get_template.return_value = {
            "id": 1,
            "name": "Feature Template",
            "task_type": "concrete",
            "task_instruction": "Implement feature",
            "verification_instruction": "Verify feature works"
        }
        
        # Execute
        result = template_service.create_template(
            name="  Feature Template  ",
            task_type="concrete",
            task_instruction="  Implement feature  ",
            verification_instruction="  Verify feature works  ",
            description="  Description  ",
            notes="  Notes  "
        )
        
        # Verify
        call_args = mock_db.create_template.call_args
        assert call_args[1]["name"] == "Feature Template"
        assert call_args[1]["task_instruction"] == "Implement feature"
        assert call_args[1]["verification_instruction"] == "Verify feature works"
        assert call_args[1]["description"] == "Description"
        assert call_args[1]["notes"] == "Notes"
    
    def test_create_template_empty_name_raises_value_error(self, template_service, mock_db):
        """Test that empty template name raises ValueError."""
        # Execute & Verify
        with pytest.raises(ValueError, match="Template name cannot be empty"):
            template_service.create_template(
                name="",
                task_type="concrete",
                task_instruction="Instruction",
                verification_instruction="Verification"
            )
        
        mock_db.create_template.assert_not_called()
    
    def test_create_template_missing_task_type_raises_value_error(self, template_service, mock_db):
        """Test that missing task_type raises ValueError."""
        # Execute & Verify
        with pytest.raises(ValueError, match="Task type is required"):
            template_service.create_template(
                name="Template",
                task_type="",
                task_instruction="Instruction",
                verification_instruction="Verification"
            )
        
        mock_db.create_template.assert_not_called()
    
    def test_create_template_invalid_task_type_raises_value_error(self, template_service, mock_db):
        """Test that invalid task_type raises ValueError."""
        # Execute & Verify
        with pytest.raises(ValueError, match="Invalid task_type"):
            template_service.create_template(
                name="Template",
                task_type="invalid",
                task_instruction="Instruction",
                verification_instruction="Verification"
            )
        
        mock_db.create_template.assert_not_called()
    
    def test_create_template_missing_instruction_raises_value_error(self, template_service, mock_db):
        """Test that missing task_instruction raises ValueError."""
        # Execute & Verify
        with pytest.raises(ValueError, match="Task instruction is required"):
            template_service.create_template(
                name="Template",
                task_type="concrete",
                task_instruction="",
                verification_instruction="Verification"
            )
        
        mock_db.create_template.assert_not_called()
    
    def test_create_template_missing_verification_raises_value_error(self, template_service, mock_db):
        """Test that missing verification_instruction raises ValueError."""
        # Execute & Verify
        with pytest.raises(ValueError, match="Verification instruction is required"):
            template_service.create_template(
                name="Template",
                task_type="concrete",
                task_instruction="Instruction",
                verification_instruction=""
            )
        
        mock_db.create_template.assert_not_called()
    
    def test_create_template_database_error(self, template_service, mock_db):
        """Test template creation with database error."""
        # Setup
        mock_db.create_template.side_effect = Exception("Database connection failed")
        
        # Execute & Verify
        with pytest.raises(Exception, match="Failed to create template"):
            template_service.create_template(
                name="Template",
                task_type="concrete",
                task_instruction="Instruction",
                verification_instruction="Verification"
            )
    
    def test_create_template_retrieval_failure(self, template_service, mock_db):
        """Test template creation when retrieval fails."""
        # Setup
        mock_db.create_template.return_value = 1
        mock_db.get_template.return_value = None  # Retrieval fails
        
        # Execute & Verify
        with pytest.raises(Exception, match="Template was created but could not be retrieved"):
            template_service.create_template(
                name="Template",
                task_type="concrete",
                task_instruction="Instruction",
                verification_instruction="Verification"
            )
    
    def test_create_template_value_error_passed_through(self, template_service, mock_db):
        """Test that ValueError from database is passed through."""
        # Setup
        mock_db.create_template.side_effect = ValueError("Duplicate template name")
        
        # Execute & Verify
        with pytest.raises(ValueError, match="Duplicate template name"):
            template_service.create_template(
                name="Template",
                task_type="concrete",
                task_instruction="Instruction",
                verification_instruction="Verification"
            )


class TestGetTemplate:
    """Tests for get_template method."""
    
    def test_get_template_success(self, template_service, mock_db):
        """Test successful template retrieval."""
        # Setup
        mock_db.get_template.return_value = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete"
        }
        
        # Execute
        result = template_service.get_template(1)
        
        # Verify
        assert result["id"] == 1
        assert result["name"] == "Template"
        mock_db.get_template.assert_called_once_with(1)
    
    def test_get_template_not_found(self, template_service, mock_db):
        """Test template retrieval when not found."""
        # Setup
        mock_db.get_template.return_value = None
        
        # Execute
        result = template_service.get_template(999)
        
        # Verify
        assert result is None
        mock_db.get_template.assert_called_once_with(999)


class TestListTemplates:
    """Tests for list_templates method."""
    
    def test_list_templates_success(self, template_service, mock_db):
        """Test successful template listing."""
        # Setup
        mock_db.list_templates.return_value = [
            {"id": 1, "name": "Template 1"},
            {"id": 2, "name": "Template 2"}
        ]
        
        # Execute
        result = template_service.list_templates()
        
        # Verify
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        mock_db.list_templates.assert_called_once_with(task_type=None)
    
    def test_list_templates_with_filter(self, template_service, mock_db):
        """Test template listing with task_type filter."""
        # Setup
        mock_db.list_templates.return_value = [
            {"id": 1, "name": "Template 1", "task_type": "concrete"}
        ]
        
        # Execute
        result = template_service.list_templates(task_type="concrete")
        
        # Verify
        assert len(result) == 1
        mock_db.list_templates.assert_called_once_with(task_type="concrete")
    
    def test_list_templates_invalid_task_type_raises_value_error(self, template_service, mock_db):
        """Test that invalid task_type raises ValueError."""
        # Execute & Verify
        with pytest.raises(ValueError, match="Invalid task_type"):
            template_service.list_templates(task_type="invalid")
        
        mock_db.list_templates.assert_not_called()


class TestCreateTaskFromTemplate:
    """Tests for create_task_from_template method."""
    
    def test_create_task_from_template_success(self, template_service, mock_db):
        """Test successful task creation from template."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification",
            "priority": "medium",
            "estimated_hours": 2.0,
            "notes": "Template notes"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {
            "id": 10,
            "title": "Template",
            "task_type": "concrete"
        }
        
        # Execute
        result = template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent"
        )
        
        # Verify
        assert result["id"] == 10
        mock_db.get_template.assert_called_once_with(1)
        mock_db.create_task_from_template.assert_called_once()
        mock_db.get_task.assert_called_once_with(10)
    
    def test_create_task_from_template_uses_template_name_when_title_not_provided(self, template_service, mock_db):
        """Test that template name is used when title is not provided."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template Name",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            title=None
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["title"] == "Template Name"
    
    def test_create_task_from_template_uses_provided_title(self, template_service, mock_db):
        """Test that provided title is used instead of template name."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template Name",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            title="Custom Title"
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["title"] == "Custom Title"
    
    def test_create_task_from_template_uses_template_name_when_title_empty_string(self, template_service, mock_db):
        """Test that template name is used when title is empty string."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template Name",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            title=""
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["title"] == "Template Name"
    
    def test_create_task_from_template_parses_due_date_iso_format(self, template_service, mock_db):
        """Test that ISO format due_date is parsed correctly."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            due_date="2024-01-01T00:00:00"
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert isinstance(call_args[1]["due_date"], datetime)
    
    def test_create_task_from_template_parses_due_date_with_z_suffix(self, template_service, mock_db):
        """Test that ISO format due_date with 'Z' suffix is parsed correctly."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            due_date="2024-01-01T00:00:00Z"
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert isinstance(call_args[1]["due_date"], datetime)
    
    def test_create_task_from_template_invalid_due_date_ignored(self, template_service, mock_db):
        """Test that invalid due_date format is ignored (not raised as error)."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute (should not raise)
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            due_date="invalid-date"
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["due_date"] is None
    
    def test_create_task_from_template_priority_override(self, template_service, mock_db):
        """Test that provided priority overrides template priority."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification",
            "priority": "medium"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            priority="high"
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["priority"] == "high"
    
    def test_create_task_from_template_uses_template_priority_when_not_provided(self, template_service, mock_db):
        """Test that template priority is used when not provided."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification",
            "priority": "high"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            priority=None
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["priority"] == "high"
    
    def test_create_task_from_template_combines_notes(self, template_service, mock_db):
        """Test that template notes and provided notes are combined."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification",
            "notes": "Template notes"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = {"id": 10}
        
        # Execute
        template_service.create_task_from_template(
            template_id=1,
            agent_id="test-agent",
            notes="Additional notes"
        )
        
        # Verify
        call_args = mock_db.create_task_from_template.call_args
        assert call_args[1]["notes"] == "Template notes\n\nAdditional notes"
    
    def test_create_task_from_template_template_not_found_raises_value_error(self, template_service, mock_db):
        """Test that missing template raises ValueError."""
        # Setup
        mock_db.get_template.return_value = None
        
        # Execute & Verify
        with pytest.raises(ValueError, match="Template 999 not found"):
            template_service.create_task_from_template(
                template_id=999,
                agent_id="test-agent"
            )
        
        mock_db.create_task_from_template.assert_not_called()
    
    def test_create_task_from_template_database_error(self, template_service, mock_db):
        """Test task creation with database error."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.side_effect = Exception("Database error")
        
        # Execute & Verify
        with pytest.raises(Exception, match="Failed to create task from template"):
            template_service.create_task_from_template(
                template_id=1,
                agent_id="test-agent"
            )
    
    def test_create_task_from_template_retrieval_failure(self, template_service, mock_db):
        """Test task creation when retrieval fails."""
        # Setup
        mock_template = {
            "id": 1,
            "name": "Template",
            "task_type": "concrete",
            "task_instruction": "Instruction",
            "verification_instruction": "Verification"
        }
        mock_db.get_template.return_value = mock_template
        mock_db.create_task_from_template.return_value = 10
        mock_db.get_task.return_value = None  # Retrieval fails
        
        # Execute & Verify
        with pytest.raises(Exception, match="Task was created but could not be retrieved"):
            template_service.create_task_from_template(
                template_id=1,
                agent_id="test-agent"
            )
