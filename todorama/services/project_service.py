"""
Project service - business logic for project operations.
This layer contains no HTTP framework dependencies.
Handles all business logic including notifications (webhooks, Slack, etc.).
"""
import logging
import asyncio
import sqlite3
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC

from todorama.database import TodoDatabase
from todorama.storage import ProjectRepository, OrganizationRepository
from todorama.models.project_models import ProjectCreate

logger = logging.getLogger(__name__)


class ProjectService:
    """Service for project business logic."""
    
    def __init__(
        self,
        project_repository: Optional[ProjectRepository] = None,
        organization_repository: Optional[OrganizationRepository] = None,
        db: Optional[TodoDatabase] = None,
    ):
        """
        Initialize project service with repository dependencies.
        
        Args:
            project_repository: ProjectRepository instance for project operations
            organization_repository: OrganizationRepository instance for organization operations
            db: TodoDatabase instance (optional, for backward compatibility and complex operations)
            
        Note: For backward compatibility, if repositories are not provided, db is required.
        If db is provided, repositories will be created from it.
        """
        if project_repository is None or organization_repository is None:
            if db is None:
                raise ValueError("Either repositories or db must be provided")
            # Create repositories from db for backward compatibility
            self.project_repository = ProjectRepository(db)
            self.organization_repository = OrganizationRepository(db)
            self.db = db
        else:
            self.project_repository = project_repository
            self.organization_repository = organization_repository
            # Keep db reference for complex operations not yet in repositories
            # (webhooks, etc.)
            self.db = db if db is not None else project_repository.db
    
    def create_project(self, project_data: ProjectCreate, organization_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a new project and dispatch all related notifications.
        
        Args:
            project_data: Project creation data
            organization_id: Organization ID (required for multi-tenancy)
            
        Returns:
            Created project data as dictionary
            
        Raises:
            ValueError: If project name already exists or organization_id is missing
            Exception: If project creation fails
        """
        if organization_id is None:
            raise ValueError("organization_id is required for project creation")
        
        # Check if project with same name already exists (within organization)
        existing = self.project_repository.get_by_name(project_data.name)
        if existing:
            # Verify it's not in the same organization
            if existing.get("organization_id") == organization_id:
                raise ValueError(f"Project with name '{project_data.name}' already exists in this organization")
        
        # Create project
        try:
            project_id = self.project_repository.create(
                name=project_data.name,
                local_path=project_data.local_path,
                origin_url=project_data.origin_url,
                description=project_data.description,
                organization_id=organization_id
            )
        except sqlite3.IntegrityError as e:
            error_msg = str(e).lower()
            if "unique constraint" in error_msg and "projects.name" in error_msg:
                raise ValueError(f"Project with name '{project_data.name}' already exists")
            logger.error(f"Database integrity error creating project: {str(e)}", exc_info=True)
            raise Exception("Failed to create project due to database constraint violation")
        except Exception as e:
            logger.error(f"Failed to create project: {str(e)}", exc_info=True)
            raise Exception("Failed to create project. Please try again or contact support if the issue persists.")
        
        # Retrieve created project
        created_project = self.project_repository.get_by_id(project_id)
        if not created_project:
            logger.error(f"Project {project_id} was created but could not be retrieved")
            raise Exception("Project was created but could not be retrieved. Please check project status.")
        
        created_project_dict = dict(created_project)
        
        # Dispatch notifications (webhooks, Slack, etc.)
        self._dispatch_project_created_notifications(created_project_dict, project_id)
        
        return created_project_dict
    
    def _dispatch_project_created_notifications(self, project_data: Dict[str, Any], project_id: int):
        """Dispatch all notifications for project creation (webhooks, Slack, etc.)."""
        # Send webhook notifications
        try:
            from webhooks import notify_webhooks
            asyncio.create_task(notify_webhooks(
                self.db,
                project_id=project_id,
                event_type="project.created",
                payload={
                    "event": "project.created",
                    "project": project_data,
                    "timestamp": datetime.now(UTC).isoformat()
                }
            ))
        except Exception as e:
            logger.warning(f"Failed to dispatch webhook notification: {e}")
        
        # Send Slack notification
        try:
            from slack import send_task_notification
            # Note: send_task_notification is designed for tasks, but we can reuse it
            # or create a project-specific notification function later
            
            async def send_slack_notif():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    send_task_notification,
                    None,  # Use default channel from env
                    "project.created",
                    project_data,
                    project_data  # Pass project as both task and project data
                )
            asyncio.create_task(send_slack_notif())
        except Exception as e:
            logger.warning(f"Failed to dispatch Slack notification: {e}")
    
    def get_project(self, project_id: int, organization_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Get a project by ID with tenant isolation.
        
        Args:
            project_id: Project ID
            organization_id: Optional organization ID for tenant isolation
        
        Returns:
            Project dictionary if found and accessible, None otherwise
        """
        project = self.project_repository.get_by_id(project_id, organization_id=organization_id)
        return dict(project) if project else None
    
    def get_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a project by name."""
        project = self.project_repository.get_by_name(name.strip())
        return dict(project) if project else None
    
    def list_projects(self, filters: Optional[Dict[str, Any]] = None, organization_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List all projects with tenant isolation.
        
        Args:
            filters: Optional filters (currently not used, reserved for future use)
            organization_id: Optional organization ID to filter projects by tenant
            
        Returns:
            List of project dictionaries
        """
        projects = self.project_repository.list(organization_id=organization_id)
        return [dict(project) for project in projects]
