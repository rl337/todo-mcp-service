"""
Repository for bulk task operations.

This module extracts bulk operation-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import logging
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class BulkOperations:
    """Repository for bulk task operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_with_logging: Callable[[Any, str, tuple], Any],
        check_and_auto_complete_parents: Callable[[int, str], None]
    ):
        """
        Initialize BulkOperations.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            get_connection: Function to get database connection
            adapter: Database adapter (for closing connections)
            execute_with_logging: Function to execute queries with logging
            check_and_auto_complete_parents: Function to check and auto-complete parent tasks
        """
        self.db_type = db_type
        self._get_connection = get_connection
        self.adapter = adapter
        self._execute_with_logging = execute_with_logging
        self._check_and_auto_complete_parents = check_and_auto_complete_parents
    
    def complete_tasks(
        self,
        task_ids: List[int],
        agent_id: str,
        notes: Optional[str] = None,
        actual_hours: Optional[float] = None,
        require_all: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk complete multiple tasks.
        
        Args:
            task_ids: List of task IDs to complete
            agent_id: Agent ID performing the operation
            notes: Optional notes for completion
            actual_hours: Optional actual hours worked
            require_all: If True, all tasks must succeed or none will be completed (transaction)
        
        Returns:
            Dictionary with success status, completed count, and failed task IDs
        
        Raises:
            ValueError: If agent_id is missing or task_ids is empty
        """
        if not agent_id:
            raise ValueError("agent_id is required for bulk operations")
        if not task_ids:
            raise ValueError("task_ids cannot be empty")
        
        conn = self._get_connection()
        completed = []
        failed = []
        
        try:
            cursor = conn.cursor()
            
            if require_all:
                # Transaction mode: all or nothing
                query = "BEGIN TRANSACTION"
                self._execute_with_logging(cursor, query, None)
                try:
                    for task_id in task_ids:
                        try:
                            # Get current status
                            query = "SELECT task_status, estimated_hours FROM tasks WHERE id = ?"
                            params = (task_id,)
                            self._execute_with_logging(cursor, query, params)
                            current = cursor.fetchone()
                            if not current:
                                raise ValueError(f"Task {task_id} not found")
                            
                            old_status = current["task_status"]
                            estimated_hours = current["estimated_hours"]
                            
                            # Calculate time_delta_hours
                            time_delta_hours = None
                            if actual_hours is not None and estimated_hours is not None:
                                time_delta_hours = actual_hours - estimated_hours
                            
                            # Complete task
                            query = """
                                UPDATE tasks 
                                SET task_status = 'complete',
                                    completed_at = CURRENT_TIMESTAMP,
                                    updated_at = CURRENT_TIMESTAMP,
                                    notes = COALESCE(?, notes),
                                    actual_hours = COALESCE(?, actual_hours),
                                    time_delta_hours = COALESCE(?, time_delta_hours)
                                WHERE id = ?
                            """
                            params = (notes, actual_hours, time_delta_hours, task_id)
                            self._execute_with_logging(cursor, query, params)
                            
                            if cursor.rowcount == 0:
                                raise ValueError(f"Task {task_id} could not be completed")
                            
                            # Record in history
                            query = """
                                INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value, notes)
                                VALUES (?, ?, 'completed', 'task_status', ?, 'complete', ?)
                            """
                            params = (task_id, agent_id, old_status, notes)
                            self._execute_with_logging(cursor, query, params)
                            
                            completed.append(task_id)
                            
                            # Auto-complete parent tasks if all subtasks are complete
                            self._check_and_auto_complete_parents(task_id, agent_id)
                        except Exception as e:
                            conn.rollback()
                            logger.error(f"Bulk complete failed for task {task_id}: {e}")
                            raise
                    
                    conn.commit()
                    logger.info(f"Bulk completed {len(completed)} tasks by agent {agent_id}")
                    return {
                        "success": True,
                        "completed": len(completed),
                        "failed": len(failed),
                        "task_ids": completed,
                        "failed_task_ids": failed
                    }
                except Exception:
                    conn.rollback()
                    raise
            else:
                # Best-effort mode: complete as many as possible
                for task_id in task_ids:
                    try:
                        # Get current status
                        query = "SELECT task_status, estimated_hours FROM tasks WHERE id = ?"
                        params = (task_id,)
                        self._execute_with_logging(cursor, query, params)
                        current = cursor.fetchone()
                        if not current:
                            failed.append(task_id)
                            continue
                        
                        old_status = current["task_status"]
                        estimated_hours = current["estimated_hours"]
                        
                        # Calculate time_delta_hours
                        time_delta_hours = None
                        if actual_hours is not None and estimated_hours is not None:
                            time_delta_hours = actual_hours - estimated_hours
                        
                        # Complete task
                        query = """
                            UPDATE tasks 
                            SET task_status = 'complete',
                                completed_at = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP,
                                notes = COALESCE(?, notes),
                                actual_hours = COALESCE(?, actual_hours),
                                time_delta_hours = COALESCE(?, time_delta_hours)
                            WHERE id = ?
                        """
                        params = (notes, actual_hours, time_delta_hours, task_id)
                        self._execute_with_logging(cursor, query, params)
                        
                        if cursor.rowcount == 0:
                            failed.append(task_id)
                            continue
                        
                        # Record in history
                        query = """
                            INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value, notes)
                            VALUES (?, ?, 'completed', 'task_status', ?, 'complete', ?)
                        """
                        params = (task_id, agent_id, old_status, notes)
                        self._execute_with_logging(cursor, query, params)
                        
                        completed.append(task_id)
                        
                        # Auto-complete parent tasks if all subtasks are complete
                        self._check_and_auto_complete_parents(task_id, agent_id)
                    except Exception as e:
                        logger.warning(f"Failed to complete task {task_id}: {e}")
                        failed.append(task_id)
                
                conn.commit()
                logger.info(f"Bulk completed {len(completed)} tasks (failed: {len(failed)}) by agent {agent_id}")
                return {
                    "success": True,
                    "completed": len(completed),
                    "failed": len(failed),
                    "task_ids": completed,
                    "failed_task_ids": failed
                }
        finally:
            self.adapter.close(conn)
    
    def assign_tasks(
        self,
        task_ids: List[int],
        agent_id: str,
        require_all: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk assign (lock) multiple tasks to an agent.
        
        Args:
            task_ids: List of task IDs to assign
            agent_id: Agent ID to assign tasks to
            require_all: If True, all tasks must succeed or none will be assigned (transaction)
        
        Returns:
            Dictionary with success status, assigned count, and failed task IDs
        
        Raises:
            ValueError: If agent_id is missing or task_ids is empty
        """
        if not agent_id:
            raise ValueError("agent_id is required for bulk operations")
        if not task_ids:
            raise ValueError("task_ids cannot be empty")
        
        conn = self._get_connection()
        assigned = []
        failed = []
        
        try:
            cursor = conn.cursor()
            
            if require_all:
                # Transaction mode: all or nothing
                query = "BEGIN TRANSACTION"
                self._execute_with_logging(cursor, query, None)
                try:
                    for task_id in task_ids:
                        try:
                            # Get current status
                            query = "SELECT task_status, assigned_agent FROM tasks WHERE id = ?"
                            params = (task_id,)
                            self._execute_with_logging(cursor, query, params)
                            current = cursor.fetchone()
                            if not current:
                                raise ValueError(f"Task {task_id} not found")
                            
                            old_status = current["task_status"]
                            
                            # Only assign if task is available
                            query = """
                                UPDATE tasks 
                                SET task_status = 'in_progress', 
                                    assigned_agent = ?,
                                    updated_at = CURRENT_TIMESTAMP,
                                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
                                WHERE id = ? AND task_status = 'available'
                            """
                            params = (agent_id, task_id)
                            self._execute_with_logging(cursor, query, params)
                            
                            if cursor.rowcount == 0:
                                raise ValueError(f"Task {task_id} is not available for assignment")
                            
                            # Record in history
                            query = """
                                INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value)
                                VALUES (?, ?, 'locked', 'task_status', ?, 'in_progress')
                            """
                            params = (task_id, agent_id, old_status)
                            self._execute_with_logging(cursor, query, params)
                            
                            assigned.append(task_id)
                        except Exception as e:
                            conn.rollback()
                            logger.error(f"Bulk assign failed for task {task_id}: {e}")
                            raise
                    
                    conn.commit()
                    logger.info(f"Bulk assigned {len(assigned)} tasks to agent {agent_id}")
                    return {
                        "success": True,
                        "assigned": len(assigned),
                        "failed": len(failed),
                        "task_ids": assigned,
                        "failed_task_ids": failed
                    }
                except Exception:
                    conn.rollback()
                    raise
            else:
                # Best-effort mode: assign as many as possible
                for task_id in task_ids:
                    try:
                        # Get current status
                        query = "SELECT task_status, assigned_agent FROM tasks WHERE id = ?"
                        params = (task_id,)
                        self._execute_with_logging(cursor, query, params)
                        current = cursor.fetchone()
                        if not current:
                            failed.append(task_id)
                            continue
                        
                        old_status = current["task_status"]
                        
                        # Only assign if task is available
                        query = """
                            UPDATE tasks 
                            SET task_status = 'in_progress', 
                                assigned_agent = ?,
                                updated_at = CURRENT_TIMESTAMP,
                                started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
                            WHERE id = ? AND task_status = 'available'
                        """
                        params = (agent_id, task_id)
                        self._execute_with_logging(cursor, query, params)
                        
                        if cursor.rowcount == 0:
                            failed.append(task_id)
                            continue
                        
                        # Record in history
                        query = """
                            INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value)
                            VALUES (?, ?, 'locked', 'task_status', ?, 'in_progress')
                        """
                        params = (task_id, agent_id, old_status)
                        self._execute_with_logging(cursor, query, params)
                        
                        assigned.append(task_id)
                    except Exception as e:
                        logger.warning(f"Failed to assign task {task_id}: {e}")
                        failed.append(task_id)
                
                conn.commit()
                logger.info(f"Bulk assigned {len(assigned)} tasks (failed: {len(failed)}) to agent {agent_id}")
                return {
                    "success": True,
                    "assigned": len(assigned),
                    "failed": len(failed),
                    "task_ids": assigned,
                    "failed_task_ids": failed
                }
        finally:
            self.adapter.close(conn)
    
    def update_status(
        self,
        task_ids: List[int],
        task_status: str,
        agent_id: str,
        require_all: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk update status of multiple tasks.
        
        Args:
            task_ids: List of task IDs to update
            task_status: New task status
            agent_id: Agent ID performing the operation
            require_all: If True, all tasks must succeed or none will be updated (transaction)
        
        Returns:
            Dictionary with success status, updated count, and failed task IDs
        
        Raises:
            ValueError: If agent_id is missing, task_ids is empty, or invalid task_status
        """
        if not agent_id:
            raise ValueError("agent_id is required for bulk operations")
        if not task_ids:
            raise ValueError("task_ids cannot be empty")
        if task_status not in ["available", "in_progress", "complete", "blocked", "cancelled"]:
            raise ValueError(f"Invalid task_status: {task_status}")
        
        conn = self._get_connection()
        updated = []
        failed = []
        
        try:
            cursor = conn.cursor()
            
            if require_all:
                # Transaction mode: all or nothing
                query = "BEGIN TRANSACTION"
                self._execute_with_logging(cursor, query, None)
                try:
                    for task_id in task_ids:
                        try:
                            # Get current status
                            query = "SELECT task_status FROM tasks WHERE id = ?"
                            params = (task_id,)
                            self._execute_with_logging(cursor, query, params)
                            current = cursor.fetchone()
                            if not current:
                                raise ValueError(f"Task {task_id} not found")
                            
                            old_status = current["task_status"]
                            
                            # Update status
                            query = """
                                UPDATE tasks 
                                SET task_status = ?,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?
                            """
                            params = (task_status, task_id)
                            self._execute_with_logging(cursor, query, params)
                            
                            if cursor.rowcount == 0:
                                raise ValueError(f"Task {task_id} could not be updated")
                            
                            # Record in history
                            query = """
                                INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value)
                                VALUES (?, ?, 'status_changed', 'task_status', ?, ?)
                            """
                            params = (task_id, agent_id, old_status, task_status)
                            self._execute_with_logging(cursor, query, params)
                            
                            updated.append(task_id)
                        except Exception as e:
                            conn.rollback()
                            logger.error(f"Bulk update status failed for task {task_id}: {e}")
                            raise
                    
                    conn.commit()
                    logger.info(f"Bulk updated status for {len(updated)} tasks by agent {agent_id}")
                    return {
                        "success": True,
                        "updated": len(updated),
                        "failed": len(failed),
                        "task_ids": updated,
                        "failed_task_ids": failed
                    }
                except Exception:
                    conn.rollback()
                    raise
            else:
                # Best-effort mode: update as many as possible
                for task_id in task_ids:
                    try:
                        # Get current status
                        query = "SELECT task_status FROM tasks WHERE id = ?"
                        params = (task_id,)
                        self._execute_with_logging(cursor, query, params)
                        current = cursor.fetchone()
                        if not current:
                            failed.append(task_id)
                            continue
                        
                        old_status = current["task_status"]
                        
                        # Update status
                        query = """
                            UPDATE tasks 
                            SET task_status = ?,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """
                        params = (task_status, task_id)
                        self._execute_with_logging(cursor, query, params)
                        
                        if cursor.rowcount == 0:
                            failed.append(task_id)
                            continue
                        
                        # Record in history
                        query = """
                            INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value)
                            VALUES (?, ?, 'status_changed', 'task_status', ?, ?)
                        """
                        params = (task_id, agent_id, old_status, task_status)
                        self._execute_with_logging(cursor, query, params)
                        
                        updated.append(task_id)
                    except Exception as e:
                        logger.warning(f"Failed to update status for task {task_id}: {e}")
                        failed.append(task_id)
                
                conn.commit()
                logger.info(f"Bulk updated status for {len(updated)} tasks (failed: {len(failed)}) by agent {agent_id}")
                return {
                    "success": True,
                    "updated": len(updated),
                    "failed": len(failed),
                    "task_ids": updated,
                    "failed_task_ids": failed
                }
        finally:
            self.adapter.close(conn)
    
    def delete_tasks(
        self,
        task_ids: List[int],
        require_all: bool = False
    ) -> Dict[str, Any]:
        """
        Bulk delete multiple tasks.
        
        Args:
            task_ids: List of task IDs to delete
            require_all: If True, all tasks must succeed or none will be deleted (transaction)
        
        Returns:
            Dictionary with success status, deleted count, and failed task IDs
        
        Raises:
            ValueError: If task_ids is empty
        """
        if not task_ids:
            raise ValueError("task_ids cannot be empty")
        
        conn = self._get_connection()
        deleted = []
        failed = []
        
        try:
            cursor = conn.cursor()
            
            if require_all:
                # Transaction mode: all or nothing
                query = "BEGIN TRANSACTION"
                self._execute_with_logging(cursor, query, None)
                try:
                    for task_id in task_ids:
                        try:
                            # Verify task exists
                            query = "SELECT id FROM tasks WHERE id = ?"
                            params = (task_id,)
                            self._execute_with_logging(cursor, query, params)
                            if not cursor.fetchone():
                                raise ValueError(f"Task {task_id} not found")
                            
                            # Delete task (cascade will handle relationships, comments, etc.)
                            query = "DELETE FROM tasks WHERE id = ?"
                            params = (task_id,)
                            self._execute_with_logging(cursor, query, params)
                            
                            if cursor.rowcount == 0:
                                raise ValueError(f"Task {task_id} could not be deleted")
                            
                            deleted.append(task_id)
                        except Exception as e:
                            conn.rollback()
                            logger.error(f"Bulk delete failed for task {task_id}: {e}")
                            raise
                    
                    conn.commit()
                    logger.info(f"Bulk deleted {len(deleted)} tasks")
                    return {
                        "success": True,
                        "deleted": len(deleted),
                        "failed": len(failed),
                        "task_ids": deleted,
                        "failed_task_ids": failed
                    }
                except Exception:
                    conn.rollback()
                    raise
            else:
                # Best-effort mode: delete as many as possible
                for task_id in task_ids:
                    try:
                        # Verify task exists
                        query = "SELECT id FROM tasks WHERE id = ?"
                        params = (task_id,)
                        self._execute_with_logging(cursor, query, params)
                        if not cursor.fetchone():
                            failed.append(task_id)
                            continue
                        
                        # Delete task (cascade will handle relationships, comments, etc.)
                        query = "DELETE FROM tasks WHERE id = ?"
                        params = (task_id,)
                        self._execute_with_logging(cursor, query, params)
                        
                        if cursor.rowcount == 0:
                            failed.append(task_id)
                            continue
                        
                        deleted.append(task_id)
                    except Exception as e:
                        logger.warning(f"Failed to delete task {task_id}: {e}")
                        failed.append(task_id)
                
                conn.commit()
                logger.info(f"Bulk deleted {len(deleted)} tasks (failed: {len(failed)})")
                return {
                    "success": True,
                    "deleted": len(deleted),
                    "failed": len(failed),
                    "task_ids": deleted,
                    "failed_task_ids": failed
                }
        finally:
            self.adapter.close(conn)
    
    def unlock_tasks(
        self,
        task_ids: List[int],
        agent_id: str
    ) -> Dict[str, Any]:
        """
        Unlock multiple tasks atomically.
        
        Args:
            task_ids: List of task IDs to unlock
            agent_id: Agent ID performing the unlock
        
        Returns:
            Dictionary with success status and summary of unlocked tasks
        
        Raises:
            ValueError: If agent_id is missing
        """
        if not task_ids:
            return {
                "success": True,
                "unlocked_count": 0,
                "unlocked_task_ids": [],
                "failed_count": 0,
                "failed_task_ids": []
            }
        
        if not agent_id:
            raise ValueError("agent_id is required for bulk unlock")
        
        conn = self._get_connection()
        unlocked = []
        failed = []
        
        try:
            cursor = conn.cursor()
            
            for task_id in task_ids:
                try:
                    # Get current status
                    query = "SELECT assigned_agent, task_status FROM tasks WHERE id = ?"
                    params = (task_id,)
                    self._execute_with_logging(cursor, query, params)
                    current = cursor.fetchone()
                    
                    if not current:
                        failed.append({"task_id": task_id, "error": "Task not found"})
                        continue
                    
                    old_status = current["task_status"]
                    
                    # Unlock the task
                    query = """
                        UPDATE tasks 
                        SET task_status = 'available',
                            assigned_agent = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND task_status = 'in_progress'
                    """
                    params = (task_id,)
                    self._execute_with_logging(cursor, query, params)
                    
                    if cursor.rowcount > 0:
                        # Record in history
                        query = """
                            INSERT INTO change_history (task_id, agent_id, change_type, field_name, old_value, new_value)
                            VALUES (?, ?, 'unlocked', 'task_status', ?, 'available')
                        """
                        params = (task_id, agent_id, old_status)
                        self._execute_with_logging(cursor, query, params)
                        unlocked.append(task_id)
                    else:
                        failed.append({"task_id": task_id, "error": "Task not in_progress"})
                
                except Exception as e:
                    logger.error(f"Error unlocking task {task_id}: {e}", exc_info=True)
                    failed.append({"task_id": task_id, "error": str(e)})
            
            conn.commit()
            
            return {
                "success": True,
                "unlocked_count": len(unlocked),
                "unlocked_task_ids": unlocked,
                "failed_count": len(failed),
                "failed_task_ids": failed
            }
        except Exception as e:
            conn.rollback()
            logger.error(f"Bulk unlock failed: {e}", exc_info=True)
            raise
        finally:
            self.adapter.close(conn)
