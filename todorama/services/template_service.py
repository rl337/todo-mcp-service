"""
Template service - business logic for template operations.
This layer contains no HTTP framework dependencies.
Handles all business logic including validation and error handling.
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from todorama.database import TodoDatabase

logger = logging.getLogger(__name__)


class TemplateService:
    """Service for template business logic."""
    
    def __init__(self, db: TodoDatabase):
        """Initialize template service with database dependency."""
        self.db = db
    
    def create_template(
        self,
        name: str,
        task_type: str,
        task_instruction: str,
        verification_instruction: str,
        description: Optional[str] = None,
        priority: Optional[str] = None,
        estimated_hours: Optional[float] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new task template.
        
        Args:
            name: Template name (must be unique)
            task_type: Task type (concrete, abstract, epic)
            task_instruction: Template instruction text
            verification_instruction: Template verification steps
            description: Optional template description
            priority: Optional default priority
            estimated_hours: Optional default estimated hours
            notes: Optional additional template notes
            
        Returns:
            Created template data as dictionary
            
        Raises:
            ValueError: If validation fails (missing required fields, invalid priority, etc.)
            Exception: If template creation fails
        """
        # Validate required fields
        if not name or not name.strip():
            raise ValueError("Template name cannot be empty")
        
        if not task_type:
            raise ValueError("Task type is required")
        
        if task_type not in ["concrete", "abstract", "epic"]:
            raise ValueError(f"Invalid task_type: {task_type}. Must be one of: concrete, abstract, epic")
        
        if not task_instruction or not task_instruction.strip():
            raise ValueError("Task instruction is required")
        
        if not verification_instruction or not verification_instruction.strip():
            raise ValueError("Verification instruction is required")
        
        # Create template
        try:
            template_id = self.db.create_template(
                name=name.strip(),
                task_type=task_type,
                task_instruction=task_instruction.strip(),
                verification_instruction=verification_instruction.strip(),
                description=description.strip() if description else None,
                priority=priority,
                estimated_hours=estimated_hours,
                notes=notes.strip() if notes else None
            )
        except ValueError as e:
            # Re-raise ValueError as-is (validation errors)
            raise
        except Exception as e:
            logger.error(f"Failed to create template: {str(e)}", exc_info=True)
            raise Exception("Failed to create template. Please try again or contact support if the issue persists.")
        
        # Retrieve created template
        template = self.db.get_template(template_id)
        if not template:
            logger.error(f"Template {template_id} was created but could not be retrieved")
            raise Exception("Template was created but could not be retrieved. Please check template status.")
        
        return dict(template)
    
    def get_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a template by ID.
        
        Args:
            template_id: Template ID
            
        Returns:
            Template data as dictionary, or None if not found
        """
        template = self.db.get_template(template_id)
        return dict(template) if template else None
    
    def list_templates(self, task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all templates, optionally filtered by task_type.
        
        Args:
            task_type: Optional filter by task type (concrete, abstract, epic)
            
        Returns:
            List of template dictionaries
        """
        # Validate task_type if provided
        if task_type and task_type not in ["concrete", "abstract", "epic"]:
            raise ValueError(f"Invalid task_type: {task_type}. Must be one of: concrete, abstract, epic")
        
        templates = self.db.list_templates(task_type=task_type)
        return [dict(template) for template in templates]
    
    def create_task_from_template(
        self,
        template_id: int,
        agent_id: str,
        title: Optional[str] = None,
        project_id: Optional[int] = None,
        notes: Optional[str] = None,
        priority: Optional[str] = None,
        estimated_hours: Optional[float] = None,
        due_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a task from a template with pre-filled instructions.
        
        Args:
            template_id: Template ID to use
            agent_id: Agent ID creating the task
            title: Optional task title (defaults to template name if not provided)
            project_id: Optional project ID
            notes: Optional notes (combined with template notes)
            priority: Optional priority (overrides template priority if provided)
            estimated_hours: Optional estimated hours (overrides template if provided)
            due_date: Optional due date in ISO format string
            
        Returns:
            Created task data as dictionary
            
        Raises:
            ValueError: If template not found, invalid date format, or validation fails
            Exception: If task creation fails
        """
        # Verify template exists
        template = self.db.get_template(template_id)
        if not template:
            raise ValueError(f"Template {template_id} not found. Please verify the template_id is correct.")
        
        # Determine task title: use provided title if given, otherwise use template name
        # Only use template name if title is explicitly None or empty string
        task_title = title if title and title.strip() else template["name"]
        
        # Parse due_date if provided
        due_date_obj = None
        if due_date:
            try:
                # Handle ISO format with 'Z' suffix (UTC)
                if due_date.endswith('Z'):
                    due_date_obj = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                else:
                    due_date_obj = datetime.fromisoformat(due_date)
            except ValueError as e:
                # Invalid date format - ignore silently (as per original route behavior)
                logger.warning(f"Invalid due_date format '{due_date}', ignoring: {str(e)}")
                due_date_obj = None
        
        # Use template values as defaults, but allow overrides
        task_priority = priority if priority is not None else template.get("priority")
        task_estimated_hours = estimated_hours if estimated_hours is not None else template.get("estimated_hours")
        
        # Combine template notes with provided notes
        combined_notes = None
        if template.get("notes") and notes:
            combined_notes = f"{template['notes']}\n\n{notes}"
        elif template.get("notes"):
            combined_notes = template["notes"]
        elif notes:
            combined_notes = notes
        
        # Create task from template
        try:
            task_id = self.db.create_task_from_template(
                template_id=template_id,
                agent_id=agent_id,
                title=task_title,
                project_id=project_id,
                notes=combined_notes,
                priority=task_priority,
                estimated_hours=task_estimated_hours,
                due_date=due_date_obj
            )
        except ValueError as e:
            # Re-raise ValueError as-is (validation errors)
            raise
        except Exception as e:
            logger.error(f"Failed to create task from template: {str(e)}", exc_info=True)
            raise Exception("Failed to create task from template. Please try again or contact support if the issue persists.")
        
        # Retrieve created task
        task = self.db.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} was created but could not be retrieved")
            raise Exception("Task was created but could not be retrieved. Please check task status.")
        
        return dict(task)
