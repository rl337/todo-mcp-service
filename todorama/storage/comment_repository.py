"""
Repository for comment operations.

This module extracts comment-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import json
import logging
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class CommentRepository:
    """Repository for comment operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_insert: Callable[[Any, str, tuple], int],
        execute_with_logging: Callable[[Any, str, tuple], Any]
    ):
        """
        Initialize CommentRepository.
        
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
    
    def _parse_mentions(self, comment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse mentions JSON from comment.
        
        Args:
            comment: Comment dictionary
            
        Returns:
            Comment dictionary with parsed mentions
        """
        if comment.get("mentions"):
            try:
                comment["mentions"] = json.loads(comment["mentions"])
            except (json.JSONDecodeError, TypeError):
                comment["mentions"] = []
        else:
            comment["mentions"] = []
        return comment
    
    def create(
        self,
        task_id: int,
        agent_id: str,
        content: str,
        parent_comment_id: Optional[int] = None,
        mentions: Optional[List[str]] = None
    ) -> int:
        """
        Create a comment on a task and return its ID.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID creating the comment
            content: Comment content
            parent_comment_id: Optional parent comment ID for threaded replies
            mentions: Optional list of agent IDs to mention
        
        Returns:
            Comment ID
        
        Raises:
            ValueError: If agent_id or content is missing, or task/parent not found
        """
        if not agent_id:
            raise ValueError("agent_id is required for creating comments")
        if not content or not content.strip():
            raise ValueError("comment content cannot be empty")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Verify task exists
            query = "SELECT id FROM tasks WHERE id = ?"
            params = (task_id,)
            self._execute_with_logging(cursor, query, params)
            if not cursor.fetchone():
                raise ValueError(f"Task {task_id} not found")
            
            # Verify parent comment exists if provided
            if parent_comment_id:
                query = "SELECT id FROM task_comments WHERE id = ?"
                params = (parent_comment_id,)
                self._execute_with_logging(cursor, query, params)
                if not cursor.fetchone():
                    raise ValueError(f"Parent comment {parent_comment_id} not found")
            
            # Store mentions as JSON
            mentions_json = None
            if mentions:
                mentions_json = json.dumps(mentions)
            
            comment_id = self._execute_insert(cursor, """
                INSERT INTO task_comments (task_id, agent_id, content, parent_comment_id, mentions)
                VALUES (?, ?, ?, ?, ?)
            """, (task_id, agent_id, content.strip(), parent_comment_id, mentions_json))
            conn.commit()
            logger.info(f"Created comment {comment_id} on task {task_id} by agent {agent_id}")
            return comment_id
        finally:
            self.adapter.close(conn)
    
    def get_by_id(self, comment_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a comment by ID.
        
        Args:
            comment_id: Comment ID
        
        Returns:
            Comment dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM task_comments WHERE id = ?"
            params = (comment_id,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if row:
                comment = dict(row)
                return self._parse_mentions(comment)
            return None
        finally:
            self.adapter.close(conn)
    
    def get_task_comments(self, task_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all top-level comments for a task (not replies).
        
        Args:
            task_id: Task ID
            limit: Maximum number of comments to return
        
        Returns:
            List of comment dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT * FROM task_comments
                WHERE task_id = ? AND parent_comment_id IS NULL
                ORDER BY created_at DESC
                LIMIT ?
            """
            params = (task_id, limit)
            self._execute_with_logging(cursor, query, params)
            comments = []
            for row in cursor.fetchall():
                comment = dict(row)
                comments.append(self._parse_mentions(comment))
            return comments
        finally:
            self.adapter.close(conn)
    
    def get_thread(self, parent_comment_id: int) -> List[Dict[str, Any]]:
        """
        Get a comment thread (parent comment and all its replies).
        
        Args:
            parent_comment_id: Parent comment ID
        
        Returns:
            List of comment dictionaries (parent first, then replies in chronological order)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Get parent
            query = "SELECT * FROM task_comments WHERE id = ?"
            params = (parent_comment_id,)
            self._execute_with_logging(cursor, query, params)
            parent_row = cursor.fetchone()
            if not parent_row:
                return []
            
            # Get all replies
            query = """
                SELECT * FROM task_comments
                WHERE parent_comment_id = ?
                ORDER BY created_at ASC
            """
            params = (parent_comment_id,)
            self._execute_with_logging(cursor, query, params)
            
            thread = [self._parse_mentions(dict(parent_row))]
            for row in cursor.fetchall():
                comment = dict(row)
                thread.append(self._parse_mentions(comment))
            
            return thread
        finally:
            self.adapter.close(conn)
    
    def update(
        self,
        comment_id: int,
        agent_id: str,
        content: str
    ) -> bool:
        """
        Update a comment.
        
        Args:
            comment_id: Comment ID
            agent_id: Agent ID (must match comment owner)
            content: New comment content
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            ValueError: If agent_id or content is missing, comment not found, or ownership mismatch
        """
        if not agent_id:
            raise ValueError("agent_id is required for updating comments")
        if not content or not content.strip():
            raise ValueError("comment content cannot be empty")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Verify comment exists and is owned by agent
            query = "SELECT agent_id FROM task_comments WHERE id = ?"
            params = (comment_id,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Comment {comment_id} not found")
            if row[0] != agent_id:
                raise ValueError(f"Comment {comment_id} is owned by {row[0]}, not {agent_id}")
            
            query = """
                UPDATE task_comments
                SET content = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (content.strip(), comment_id)
            self._execute_with_logging(cursor, query, params)
            
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Updated comment {comment_id} by agent {agent_id}")
            return success
        finally:
            self.adapter.close(conn)
    
    def delete(self, comment_id: int, agent_id: str) -> bool:
        """
        Delete a comment. Cascades to replies.
        
        Args:
            comment_id: Comment ID
            agent_id: Agent ID (must match comment owner)
        
        Returns:
            True if successful, False otherwise
        
        Raises:
            ValueError: If agent_id is missing or ownership mismatch
        """
        if not agent_id:
            raise ValueError("agent_id is required for deleting comments")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # Verify comment exists and is owned by agent
            query = "SELECT agent_id FROM task_comments WHERE id = ?"
            params = (comment_id,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if not row:
                return False
            if row[0] != agent_id:
                raise ValueError(f"Comment {comment_id} is owned by {row[0]}, not {agent_id}")
            
            # Delete comment (cascade will delete replies)
            query = "DELETE FROM task_comments WHERE id = ?"
            params = (comment_id,)
            self._execute_with_logging(cursor, query, params)
            success = cursor.rowcount > 0
            conn.commit()
            if success:
                logger.info(f"Deleted comment {comment_id} by agent {agent_id}")
            return success
        finally:
            self.adapter.close(conn)
