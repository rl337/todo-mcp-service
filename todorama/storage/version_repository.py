"""
Repository for task version operations.

This module extracts version-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import logging
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class VersionRepository:
    """Repository for task version operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_with_logging: Callable[[Any, str, tuple], Any]
    ):
        """
        Initialize VersionRepository.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            get_connection: Function to get database connection
            adapter: Database adapter (for closing connections)
            execute_with_logging: Function to execute queries with logging
        """
        self.db_type = db_type
        self._get_connection = get_connection
        self.adapter = adapter
        self._execute_with_logging = execute_with_logging
    
    def get_task_versions(self, task_id: int) -> List[Dict[str, Any]]:
        """
        Get all versions for a task, ordered by version number (newest first).
        
        Args:
            task_id: Task ID
            
        Returns:
            List of version dictionaries, ordered by version_number DESC
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT * FROM task_versions
                WHERE task_id = ?
                ORDER BY version_number DESC
            """
            params = (task_id,)
            self._execute_with_logging(cursor, query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            self.adapter.close(conn)
    
    def get_task_version(
        self,
        task_id: int,
        version_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific version of a task.
        
        Args:
            task_id: Task ID
            version_number: Version number to retrieve
            
        Returns:
            Version dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT * FROM task_versions
                WHERE task_id = ? AND version_number = ?
            """
            params = (task_id, version_number)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            self.adapter.close(conn)
    
    def get_latest_task_version(self, task_id: int) -> Optional[Dict[str, Any]]:
        """
        Get the latest version of a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Latest version dictionary or None if no versions exist
        """
        versions = self.get_task_versions(task_id)
        return versions[0] if versions else None
    
    def diff_task_versions(
        self,
        task_id: int,
        version_number_1: int,
        version_number_2: int
    ) -> Dict[str, Dict[str, Any]]:
        """
        Diff two task versions and return changed fields.
        
        Args:
            task_id: Task ID
            version_number_1: First version number (older, used as baseline)
            version_number_2: Second version number (newer, compared against baseline)
            
        Returns:
            Dictionary mapping field names to {old_value, new_value} dictionaries.
            Only includes fields that differ between versions.
            
        Raises:
            ValueError: If one or both versions not found
        """
        version1 = self.get_task_version(task_id, version_number_1)
        version2 = self.get_task_version(task_id, version_number_2)
        
        if not version1 or not version2:
            raise ValueError(f"One or both versions not found: v{version_number_1}, v{version_number_2}")
        
        # Fields to compare
        fields_to_compare = [
            "title", "task_type", "task_instruction", "verification_instruction",
            "task_status", "verification_status", "priority", "assigned_agent",
            "notes", "estimated_hours", "actual_hours", "time_delta_hours",
            "due_date", "started_at", "completed_at"
        ]
        
        diff = {}
        for field in fields_to_compare:
            old_value = version1.get(field)
            new_value = version2.get(field)
            
            # Compare values (handle None cases)
            if old_value != new_value:
                diff[field] = {
                    "old_value": old_value,
                    "new_value": new_value
                }
        
        return diff
