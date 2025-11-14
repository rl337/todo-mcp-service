"""
Repository for tag operations.

This module extracts tag-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import logging
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class TagRepository:
    """Repository for tag operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_insert: Callable[[Any, str, tuple], int],
        execute_with_logging: Callable[[Any, str, tuple], Any]
    ):
        """
        Initialize TagRepository.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            get_connection: Function to get database connection
            adapter: Database adapter (for closing connections)
            execute_insert: Function to execute INSERT queries and return ID
            execute_with_logging: Function to execute queries with logging
        """
        self.db_type = db_type
        self._get_connection = get_connection
        self.adapter = adapter
        self._execute_insert = execute_insert
        self._execute_with_logging = execute_with_logging
    
    def create(self, name: str) -> int:
        """
        Create a tag (or return existing tag ID if name already exists).
        
        Args:
            name: Tag name
        
        Returns:
            Tag ID (existing or newly created)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Check if tag already exists
            query = "SELECT id FROM tags WHERE name = ?"
            params = (name,)
            self._execute_with_logging(cursor, query, params)
            existing = cursor.fetchone()
            if existing:
                return existing[0]
            
            # Create new tag
            tag_id = self._execute_insert(cursor, "INSERT INTO tags (name) VALUES (?)", (name,))
            conn.commit()
            logger.info(f"Created tag {tag_id}: {name}")
            return tag_id
        finally:
            self.adapter.close(conn)
    
    def get_by_id(self, tag_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a tag by ID.
        
        Args:
            tag_id: Tag ID
        
        Returns:
            Tag dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM tags WHERE id = ?"
            params = (tag_id,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            self.adapter.close(conn)
    
    def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a tag by name.
        
        Args:
            name: Tag name
        
        Returns:
            Tag dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM tags WHERE name = ?"
            params = (name,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            self.adapter.close(conn)
    
    def list(self) -> List[Dict[str, Any]]:
        """
        List all tags.
        
        Returns:
            List of tag dictionaries, ordered by name
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM tags ORDER BY name ASC"
            params = None
            self._execute_with_logging(cursor, query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            self.adapter.close(conn)
    
    def assign_to_task(self, task_id: int, tag_id: int) -> None:
        """
        Assign a tag to a task (idempotent - won't create duplicates).
        
        Args:
            task_id: Task ID
            tag_id: Tag ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Check if assignment already exists (UNIQUE constraint will prevent duplicates)
            # Use INSERT OR IGNORE for SQLite, or handle duplicate key error for PostgreSQL
            if self.db_type == "sqlite":
                query = """
                    INSERT OR IGNORE INTO task_tags (task_id, tag_id)
                    VALUES (?, ?)
                """
            else:
                # PostgreSQL: Use ON CONFLICT DO NOTHING
                query = """
                    INSERT INTO task_tags (task_id, tag_id)
                    VALUES (?, ?)
                    ON CONFLICT (task_id, tag_id) DO NOTHING
                """
            params = (task_id, tag_id)
            self._execute_with_logging(cursor, query, params)
            conn.commit()
            logger.info(f"Assigned tag {tag_id} to task {task_id}")
        finally:
            self.adapter.close(conn)
    
    def remove_from_task(self, task_id: int, tag_id: int) -> None:
        """
        Remove a tag from a task.
        
        Args:
            task_id: Task ID
            tag_id: Tag ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                DELETE FROM task_tags
                WHERE task_id = ? AND tag_id = ?
            """
            params = (task_id, tag_id)
            self._execute_with_logging(cursor, query, params)
            conn.commit()
            logger.info(f"Removed tag {tag_id} from task {task_id}")
        finally:
            self.adapter.close(conn)
    
    def get_task_tags(self, task_id: int) -> List[Dict[str, Any]]:
        """
        Get all tags assigned to a task.
        
        Args:
            task_id: Task ID
        
        Returns:
            List of tag dictionaries assigned to the task
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT t.* FROM tags t
                INNER JOIN task_tags tt ON t.id = tt.tag_id
                WHERE tt.task_id = ?
                ORDER BY t.name ASC
            """
            params = (task_id,)
            self._execute_with_logging(cursor, query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            self.adapter.close(conn)
    
    def delete(self, tag_id: int) -> None:
        """
        Delete a tag (cascades to task_tags via foreign key).
        
        Args:
            tag_id: Tag ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "DELETE FROM tags WHERE id = ?"
            params = (tag_id,)
            self._execute_with_logging(cursor, query, params)
            conn.commit()
            logger.info(f"Deleted tag {tag_id}")
        finally:
            self.adapter.close(conn)
