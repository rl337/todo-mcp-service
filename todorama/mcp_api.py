"""
Minimal MCP (Model Context Protocol) API for TODO service.

Provides 4-5 core functions for agent interaction:
1. list_available_tasks - Get tasks available for agent type
2. reserve_task - Lock and reserve a task for an agent
3. complete_task - Mark task as complete and optionally add followup
4. create_task - Create a new task (for breakdown agents)
5. get_agent_performance - Get agent statistics
"""
import os
from typing import Optional, List, Dict, Any, Literal
from fastapi import HTTPException

from todorama.database import TodoDatabase
from todorama.config import get_database_path
from todorama.tracing import trace_span, add_span_attribute
from todorama.services.project_service import ProjectService
from todorama.models.project_models import ProjectCreate

# Database instance (set by set_db)
_db_instance: Optional[TodoDatabase] = None


def set_db(db: TodoDatabase):
    """Set the database instance for MCP API."""
    global _db_instance
    _db_instance = db


def get_db() -> TodoDatabase:
    """Get the database instance."""
    global _db_instance
    if _db_instance is None:
        # Fallback: create default instance
        db_path = get_database_path()
        _db_instance = TodoDatabase(db_path)
    return _db_instance


# Import helper function from handlers module
from todorama.mcp.helpers import add_computed_status_fields as _add_computed_status_fields


# Import handlers
from todorama.mcp.handlers import (
    task_handlers,
    query_handlers,
    project_handlers,
    analytics_handlers,
    tag_handlers,
    template_handlers,
    comment_handlers,
    recurring_handlers,
    version_handlers,
    github_handlers,
)


class MCPTodoAPI:
    """Minimal MCP API for TODO service - Facade that delegates to specialized handlers."""
    
    @staticmethod
    def list_available_tasks(
        agent_type: Literal["breakdown", "implementation"],
        project_id: Optional[int] = None,
        limit: int = 10,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List available tasks for an agent type."""
        return task_handlers.handle_list_available_tasks(
            agent_type=agent_type,
            project_id=project_id,
            limit=limit,
            organization_id=organization_id
        )
    
    @staticmethod
    def reserve_task(task_id: int, agent_id: str) -> Dict[str, Any]:
        """Reserve (lock) a task for an agent."""
        return task_handlers.handle_reserve_task(task_id=task_id, agent_id=agent_id)
    
    @staticmethod
    def complete_task(
        task_id: int,
        agent_id: str,
        notes: Optional[str] = None,
        actual_hours: Optional[float] = None,
        followup_title: Optional[str] = None,
        followup_task_type: Optional[str] = None,
        followup_instruction: Optional[str] = None,
        followup_verification: Optional[str] = None
    ) -> Dict[str, Any]:
        """Complete a task and optionally create a followup task."""
        return task_handlers.handle_complete_task(
            task_id=task_id,
            agent_id=agent_id,
            notes=notes,
            actual_hours=actual_hours,
            followup_title=followup_title,
            followup_task_type=followup_task_type,
            followup_instruction=followup_instruction,
            followup_verification=followup_verification
        )
    
    @staticmethod
    def create_task(
        title: str,
        task_type: Literal["concrete", "abstract", "epic"],
        task_instruction: str,
        verification_instruction: str,
        agent_id: str,
        project_id: Optional[int] = None,
        parent_task_id: Optional[int] = None,
        relationship_type: Optional[Literal["subtask", "blocking", "blocked_by", "related"]] = None,
        notes: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        estimated_hours: Optional[float] = None,
        due_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new task, optionally linked to a parent task."""
        return task_handlers.handle_create_task(
            title=title,
            task_type=task_type,
            task_instruction=task_instruction,
            verification_instruction=verification_instruction,
            agent_id=agent_id,
            project_id=project_id,
            parent_task_id=parent_task_id,
            relationship_type=relationship_type,
            notes=notes,
            priority=priority,
            estimated_hours=estimated_hours,
            due_date=due_date
        )
    
    @staticmethod
    def get_agent_performance(
        agent_id: str,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None
    ) -> Dict[str, Any]:
        """Get performance statistics for an agent."""
        return analytics_handlers.handle_get_agent_performance(agent_id=agent_id, task_type=task_type)
    
    @staticmethod
    def unlock_task(task_id: int, agent_id: str) -> Dict[str, Any]:
        """Unlock (release) a reserved task."""
        return task_handlers.handle_unlock_task(task_id=task_id, agent_id=agent_id)
    
    @staticmethod
    def verify_task(task_id: int, agent_id: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Verify a task's completion."""
        return task_handlers.handle_verify_task(task_id=task_id, agent_id=agent_id, notes=notes)
    
    @staticmethod
    def query_tasks(
        project_id: Optional[int] = None,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None,
        task_status: Optional[Literal["available", "in_progress", "complete", "blocked", "cancelled"]] = None,
        agent_id: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        tag_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None,
        order_by: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query tasks by various criteria."""
        return query_handlers.handle_query_tasks(
            project_id=project_id,
            task_type=task_type,
            task_status=task_status,
            agent_id=agent_id,
            priority=priority,
            tag_id=tag_id,
            tag_ids=tag_ids,
            order_by=order_by,
            limit=limit
        )
    
    @staticmethod
    def query_stale_tasks(hours: Optional[int] = None) -> Dict[str, Any]:
        """Query stale tasks (tasks in_progress longer than timeout)."""
        return query_handlers.handle_query_stale_tasks(hours=hours)
    
    @staticmethod
    def add_task_update(
        task_id: int,
        agent_id: str,
        content: str,
        update_type: Literal["progress", "note", "blocker", "question", "finding"],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add a task update (progress, note, blocker, question, finding)."""
        return task_handlers.handle_add_task_update(
            task_id=task_id,
            agent_id=agent_id,
            content=content,
            update_type=update_type,
            metadata=metadata
        )
    
    @staticmethod
    def get_task_context(task_id: int) -> Dict[str, Any]:
        """Get full context for a task including project, ancestry, and updates."""
        return task_handlers.handle_get_task_context(task_id=task_id)
    
    @staticmethod
    def search_tasks(query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search tasks using full-text search."""
        return query_handlers.handle_search_tasks(query=query, limit=limit)
    
    @staticmethod
    def get_activity_feed(
        task_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Get activity feed showing all task updates, completions, and relationship changes."""
        return query_handlers.handle_get_activity_feed(
            task_id=task_id,
            agent_id=agent_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
    
    @staticmethod
    def get_tasks_approaching_deadline(
        days_ahead: int = 3,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get tasks that are approaching their deadline."""
        return query_handlers.handle_get_tasks_approaching_deadline(days_ahead=days_ahead, limit=limit)
    
    @staticmethod
    def create_tag(name: str) -> Dict[str, Any]:
        """Create a tag (or return existing tag ID if name already exists)."""
        return tag_handlers.handle_create_tag(name=name)
    
    @staticmethod
    def list_tags() -> Dict[str, Any]:
        """List all tags."""
        return tag_handlers.handle_list_tags()
    
    @staticmethod
    def assign_tag_to_task(task_id: int, tag_id: int) -> Dict[str, Any]:
        """Assign a tag to a task."""
        return tag_handlers.handle_assign_tag_to_task(task_id=task_id, tag_id=tag_id)
    
    @staticmethod
    def remove_tag_from_task(task_id: int, tag_id: int) -> Dict[str, Any]:
        """Remove a tag from a task."""
        return tag_handlers.handle_remove_tag_from_task(task_id=task_id, tag_id=tag_id)
    
    @staticmethod
    def get_task_tags(task_id: int) -> Dict[str, Any]:
        """Get all tags assigned to a task."""
        return tag_handlers.handle_get_task_tags(task_id=task_id)
    
    @staticmethod
    def create_template(
        name: str,
        task_type: Literal["concrete", "abstract", "epic"],
        task_instruction: str,
        verification_instruction: str,
        description: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        estimated_hours: Optional[float] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a task template."""
        return template_handlers.handle_create_template(
            name=name,
            task_type=task_type,
            task_instruction=task_instruction,
            verification_instruction=verification_instruction,
            description=description,
            priority=priority,
            estimated_hours=estimated_hours,
            notes=notes
        )
    
    @staticmethod
    def list_templates(task_type: Optional[Literal["concrete", "abstract", "epic"]] = None) -> Dict[str, Any]:
        """List all templates, optionally filtered by task type."""
        return template_handlers.handle_list_templates(task_type=task_type)
    
    @staticmethod
    def get_template(template_id: int) -> Dict[str, Any]:
        """Get a template by ID."""
        return template_handlers.handle_get_template(template_id=template_id)
    
    @staticmethod
    def create_task_from_template(
        template_id: int,
        agent_id: str,
        title: Optional[str] = None,
        project_id: Optional[int] = None,
        notes: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        estimated_hours: Optional[float] = None,
        due_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a task from a template with pre-filled instructions."""
        return template_handlers.handle_create_task_from_template(
            template_id=template_id,
            agent_id=agent_id,
            title=title,
            project_id=project_id,
            notes=notes,
            priority=priority,
            estimated_hours=estimated_hours,
            due_date=due_date
        )
    
    @staticmethod
    def create_comment(
        task_id: int,
        agent_id: str,
        content: str,
        parent_comment_id: Optional[int] = None,
        mentions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a comment on a task."""
        return comment_handlers.handle_create_comment(
            task_id=task_id,
            agent_id=agent_id,
            content=content,
            parent_comment_id=parent_comment_id,
            mentions=mentions
        )
    
    @staticmethod
    def get_task_comments(
        task_id: int,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get all comments for a task."""
        return comment_handlers.handle_get_task_comments(task_id=task_id, limit=limit)
    
    @staticmethod
    def get_comment_thread(
        comment_id: int
    ) -> Dict[str, Any]:
        """Get a comment thread (parent comment and all replies)."""
        return comment_handlers.handle_get_comment_thread(comment_id=comment_id)
    
    @staticmethod
    def update_comment(
        comment_id: int,
        agent_id: str,
        content: str
    ) -> Dict[str, Any]:
        """Update a comment."""
        return comment_handlers.handle_update_comment(
            comment_id=comment_id,
            agent_id=agent_id,
            content=content
        )
    
    @staticmethod
    def delete_comment(
        comment_id: int,
        agent_id: str
    ) -> Dict[str, Any]:
        """Delete a comment (cascades to replies)."""
        return comment_handlers.handle_delete_comment(comment_id=comment_id, agent_id=agent_id)

    @staticmethod
    def create_recurring_task(
        task_id: int,
        recurrence_type: Literal["daily", "weekly", "monthly"],
        next_occurrence: str,
        recurrence_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a recurring task pattern."""
        return recurring_handlers.handle_create_recurring_task(
            task_id=task_id,
            recurrence_type=recurrence_type,
            next_occurrence=next_occurrence,
            recurrence_config=recurrence_config
        )
    
    @staticmethod
    def list_recurring_tasks(
        active_only: bool = False
    ) -> Dict[str, Any]:
        """List all recurring tasks."""
        return recurring_handlers.handle_list_recurring_tasks(active_only=active_only)
    
    @staticmethod
    def get_recurring_task(recurring_id: int) -> Dict[str, Any]:
        """Get a recurring task by ID."""
        return recurring_handlers.handle_get_recurring_task(recurring_id=recurring_id)
    
    @staticmethod
    def get_task_statistics(
        project_id: Optional[int] = None,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get aggregated statistics about tasks."""
        return analytics_handlers.handle_get_task_statistics(
            project_id=project_id,
            task_type=task_type,
            start_date=start_date,
            end_date=end_date
        )
    
    @staticmethod
    def get_recent_completions(
        limit: int = 10,
        project_id: Optional[int] = None,
        hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get recently completed tasks sorted by completion time."""
        return analytics_handlers.handle_get_recent_completions(
            limit=limit,
            project_id=project_id,
            hours=hours
        )
    
    @staticmethod
    def get_task_summary(
        project_id: Optional[int] = None,
        task_type: Optional[Literal["concrete", "abstract", "epic"]] = None,
        task_status: Optional[Literal["available", "in_progress", "complete", "blocked", "cancelled"]] = None,
        assigned_agent: Optional[str] = None,
        priority: Optional[Literal["low", "medium", "high", "critical"]] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get lightweight task summaries (key fields only)."""
        return analytics_handlers.handle_get_task_summary(
            project_id=project_id,
            task_type=task_type,
            task_status=task_status,
            assigned_agent=assigned_agent,
            priority=priority,
            limit=limit
        )
    
    @staticmethod
    def bulk_unlock_tasks(
        task_ids: List[int],
        agent_id: str
    ) -> Dict[str, Any]:
        """Unlock multiple tasks atomically in a single operation."""
        return analytics_handlers.handle_bulk_unlock_tasks(task_ids=task_ids, agent_id=agent_id)
    
    @staticmethod
    def update_recurring_task(
        recurring_id: int,
        recurrence_type: Optional[Literal["daily", "weekly", "monthly"]] = None,
        recurrence_config: Optional[Dict[str, Any]] = None,
        next_occurrence: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update a recurring task."""
        return recurring_handlers.handle_update_recurring_task(
            recurring_id=recurring_id,
            recurrence_type=recurrence_type,
            recurrence_config=recurrence_config,
            next_occurrence=next_occurrence
        )
    
    @staticmethod
    def deactivate_recurring_task(recurring_id: int) -> Dict[str, Any]:
        """Deactivate a recurring task (stop creating new instances)."""
        return recurring_handlers.handle_deactivate_recurring_task(recurring_id=recurring_id)
    
    @staticmethod
    def get_task_versions(task_id: int) -> Dict[str, Any]:
        """Get all versions for a task."""
        return version_handlers.handle_get_task_versions(task_id=task_id)
    
    @staticmethod
    def get_task_version(task_id: int, version_number: int) -> Dict[str, Any]:
        """Get a specific version of a task."""
        return version_handlers.handle_get_task_version(task_id=task_id, version_number=version_number)
    
    @staticmethod
    def get_latest_task_version(task_id: int) -> Dict[str, Any]:
        """Get the latest version of a task."""
        return version_handlers.handle_get_latest_task_version(task_id=task_id)
    
    @staticmethod
    def diff_task_versions(
        task_id: int,
        version_number_1: int,
        version_number_2: int
    ) -> Dict[str, Any]:
        """Diff two task versions and return changed fields."""
        return version_handlers.handle_diff_task_versions(
            task_id=task_id,
            version_number_1=version_number_1,
            version_number_2=version_number_2
        )
    
    @staticmethod
    def create_recurring_instance(recurring_id: int) -> Dict[str, Any]:
        """Manually create the next instance from a recurring task."""
        return recurring_handlers.handle_create_recurring_instance(recurring_id=recurring_id)
    
    @staticmethod
    def link_github_issue(task_id: int, github_url: str) -> Dict[str, Any]:
        """Link a GitHub issue to a task."""
        return github_handlers.handle_link_github_issue(task_id=task_id, github_url=github_url)
    
    @staticmethod
    def link_github_pr(task_id: int, github_url: str) -> Dict[str, Any]:
        """Link a GitHub PR to a task."""
        return github_handlers.handle_link_github_pr(task_id=task_id, github_url=github_url)
    
    @staticmethod
    def get_github_links(task_id: int) -> Dict[str, Any]:
        """Get GitHub issue and PR links for a task."""
        return github_handlers.handle_get_github_links(task_id=task_id)
    
    @staticmethod
    def list_projects() -> Dict[str, Any]:
        """List all available projects."""
        return project_handlers.handle_list_projects()
    
    @staticmethod
    def get_project(project_id: int) -> Dict[str, Any]:
        """Get project details by ID."""
        return project_handlers.handle_get_project(project_id=project_id)
    
    @staticmethod
    def get_project_by_name(name: str) -> Dict[str, Any]:
        """Get project by name (helpful for looking up project_id)."""
        return project_handlers.handle_get_project_by_name(name=name)
    
    @staticmethod
    def create_project(
        name: str,
        local_path: str,
        origin_url: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new project."""
        return project_handlers.handle_create_project(
            name=name,
            local_path=local_path,
            origin_url=origin_url,
            description=description
        )


# Import MCP functions and request handlers
from todorama.mcp.functions import MCP_FUNCTIONS
from todorama.mcp.request_handlers import handle_jsonrpc_request, handle_sse_request

# Re-export for backward compatibility
__all__ = ["MCPTodoAPI", "set_db", "get_db", "MCP_FUNCTIONS", "handle_jsonrpc_request", "handle_sse_request"]
