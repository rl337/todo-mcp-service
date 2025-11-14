"""
Repository for GitHub link operations.

This module extracts GitHub-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import json
import logging
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class GitHubRepository:
    """Repository for GitHub link operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_with_logging: Callable[[Any, str, tuple], Any],
        get_task: Callable[[int], Optional[Dict[str, Any]]]
    ):
        """
        Initialize GitHubRepository.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            get_connection: Function to get database connection
            adapter: Database adapter (for closing connections)
            execute_with_logging: Function to execute queries with logging
            get_task: Function to get a task by ID (for validation)
        """
        self.db_type = db_type
        self._get_connection = get_connection
        self.adapter = adapter
        self._execute_with_logging = execute_with_logging
        self._get_task = get_task
    
    def _validate_github_url(self, url: str) -> bool:
        """
        Validate that URL is a valid GitHub issue or PR URL.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid GitHub URL, False otherwise
        """
        if not url or not isinstance(url, str):
            return False
        # Check for GitHub domain and either /issues/ or /pull/
        return "github.com" in url.lower() and ("/issues/" in url.lower() or "/pull/" in url.lower())
    
    def _get_task_metadata(self, task_id: int) -> Dict[str, Any]:
        """
        Get task metadata as a dictionary.
        
        Args:
            task_id: Task ID
            
        Returns:
            Dictionary of task metadata
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT metadata FROM tasks WHERE id = ?"
            params = (task_id,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    return {}
            return {}
        finally:
            self.adapter.close(conn)
    
    def _set_task_metadata(self, task_id: int, metadata: Dict[str, Any]) -> None:
        """
        Set task metadata.
        
        Args:
            task_id: Task ID
            metadata: Metadata dictionary to set
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            metadata_json = json.dumps(metadata) if metadata else None
            query = """
                UPDATE tasks 
                SET metadata = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (metadata_json, task_id)
            self._execute_with_logging(cursor, query, params)
            conn.commit()
            logger.info(f"Updated metadata for task {task_id}")
        finally:
            self.adapter.close(conn)
    
    def link_issue(self, task_id: int, github_url: str) -> None:
        """
        Link a GitHub issue to a task.
        
        Args:
            task_id: Task ID
            github_url: GitHub issue URL (e.g., https://github.com/owner/repo/issues/123)
            
        Raises:
            ValueError: If task not found or URL is invalid
        """
        if not self._get_task(task_id):
            raise ValueError(f"Task {task_id} not found")
        
        if not self._validate_github_url(github_url):
            raise ValueError("Invalid GitHub URL: must be a valid GitHub URL")
        if "/pull/" in github_url.lower():
            raise ValueError("Invalid GitHub URL: must be an issue URL (not PR)")
        
        metadata = self._get_task_metadata(task_id)
        metadata["github_issue_url"] = github_url
        self._set_task_metadata(task_id, metadata)
        logger.info(f"Linked GitHub issue {github_url} to task {task_id}")
    
    def link_pr(self, task_id: int, github_url: str) -> None:
        """
        Link a GitHub PR to a task.
        
        Args:
            task_id: Task ID
            github_url: GitHub PR URL (e.g., https://github.com/owner/repo/pull/456)
            
        Raises:
            ValueError: If task not found or URL is invalid
        """
        if not self._get_task(task_id):
            raise ValueError(f"Task {task_id} not found")
        
        if not self._validate_github_url(github_url):
            raise ValueError("Invalid GitHub URL: must be a valid GitHub URL")
        if "/issues/" in github_url.lower() and "/pull/" not in github_url.lower():
            raise ValueError("Invalid GitHub URL: must be a PR URL (not issue)")
        
        metadata = self._get_task_metadata(task_id)
        metadata["github_pr_url"] = github_url
        self._set_task_metadata(task_id, metadata)
        logger.info(f"Linked GitHub PR {github_url} to task {task_id}")
    
    def unlink_issue(self, task_id: int) -> None:
        """
        Unlink a GitHub issue from a task.
        
        Args:
            task_id: Task ID
            
        Raises:
            ValueError: If task not found
        """
        if not self._get_task(task_id):
            raise ValueError(f"Task {task_id} not found")
        
        metadata = self._get_task_metadata(task_id)
        metadata.pop("github_issue_url", None)
        self._set_task_metadata(task_id, metadata)
        logger.info(f"Unlinked GitHub issue from task {task_id}")
    
    def unlink_pr(self, task_id: int) -> None:
        """
        Unlink a GitHub PR from a task.
        
        Args:
            task_id: Task ID
            
        Raises:
            ValueError: If task not found
        """
        if not self._get_task(task_id):
            raise ValueError(f"Task {task_id} not found")
        
        metadata = self._get_task_metadata(task_id)
        metadata.pop("github_pr_url", None)
        self._set_task_metadata(task_id, metadata)
        logger.info(f"Unlinked GitHub PR from task {task_id}")
    
    def get_links(self, task_id: int) -> Dict[str, Optional[str]]:
        """
        Get GitHub issue and PR links for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Dictionary with github_issue_url and github_pr_url keys
            
        Raises:
            ValueError: If task not found
        """
        if not self._get_task(task_id):
            raise ValueError(f"Task {task_id} not found")
        
        metadata = self._get_task_metadata(task_id)
        return {
            "github_issue_url": metadata.get("github_issue_url"),
            "github_pr_url": metadata.get("github_pr_url")
        }
