"""
Repository for analytics and statistics operations.

This module extracts analytics-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import json
import logging
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta, timezone as dt_timezone
import time

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    """Repository for analytics and statistics operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_insert: Callable[[Any, str, tuple], int],
        execute_with_logging: Callable[[Any, str, tuple], Any]
    ):
        """
        Initialize AnalyticsRepository.
        
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
    
    def get_change_history(
        self,
        task_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get change history with optional filters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            
            if task_id:
                conditions.append("task_id = ?")
                params.append(task_id)
            if agent_id:
                conditions.append("agent_id = ?")
                params.append(agent_id)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            query = f"SELECT * FROM change_history {where_clause} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            self.adapter.close(conn)
    
    def get_activity_feed(
        self,
        task_id: Optional[int] = None,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get activity feed showing all task updates, completions, and relationship changes
        in chronological order.
        
        Args:
            task_id: Optional task ID to filter by (None for all tasks)
            agent_id: Optional agent ID to filter by
            start_date: Optional start date filter (ISO format string)
            end_date: Optional end date filter (ISO format string)
            limit: Maximum number of results to return
            
        Returns:
            List of activity entries in chronological order (oldest first)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            
            if task_id:
                conditions.append("ch.task_id = ?")
                params.append(task_id)
            if agent_id:
                conditions.append("ch.agent_id = ?")
                params.append(agent_id)
            if start_date:
                # Normalize date format for SQLite comparison
                try:
                    if start_date.endswith('Z'):
                        parsed_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    else:
                        # Handle both with and without timezone
                        if '+' in start_date or start_date.count('-') > 2:
                            # Has timezone info
                            parsed_date = datetime.fromisoformat(start_date)
                        else:
                            # No timezone, assume local
                            parsed_date = datetime.fromisoformat(start_date)
                    
                    # SQLite stores dates as strings in 'YYYY-MM-DD HH:MM:SS' format (UTC)
                    # Convert ISO format to SQLite format for comparison
                    # If the date has timezone info, convert to UTC; otherwise assume local time and convert to UTC
                    if parsed_date.tzinfo is not None:
                        # Convert to UTC
                        parsed_date = parsed_date.astimezone(dt_timezone.utc).replace(tzinfo=None)
                    else:
                        # No timezone info - assume it's local time and convert to UTC
                        # Get local timezone offset
                        local_offset = time.timezone if (time.daylight == 0) else time.altzone
                        local_tz = dt_timezone(timedelta(seconds=-local_offset))
                        parsed_date = parsed_date.replace(tzinfo=local_tz).astimezone(dt_timezone.utc).replace(tzinfo=None)
                    
                    # For start_date, subtract 2 hours to account for timezone and timing differences
                    adjusted_date = parsed_date - timedelta(hours=2)
                    normalized_date = adjusted_date.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("ch.created_at >= ?")
                    params.append(normalized_date)
                except (ValueError, AttributeError) as e:
                    # If parsing fails, use as-is (might work if already in correct format)
                    logger.warning(f"Failed to parse start_date '{start_date}': {e}, using as-is")
                    conditions.append("ch.created_at >= ?")
                    params.append(start_date)
            if end_date:
                # Normalize date format for SQLite comparison
                try:
                    if end_date.endswith('Z'):
                        parsed_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    else:
                        # Handle both with and without timezone
                        if '+' in end_date or end_date.count('-') > 2:
                            # Has timezone info
                            parsed_date = datetime.fromisoformat(end_date)
                        else:
                            # No timezone, assume local
                            parsed_date = datetime.fromisoformat(end_date)
                    
                    # SQLite stores dates as strings in 'YYYY-MM-DD HH:MM:SS' format (UTC)
                    # Convert ISO format to SQLite format for comparison
                    # If the date has timezone info, convert to UTC; otherwise assume local time and convert to UTC
                    if parsed_date.tzinfo is not None:
                        # Convert to UTC
                        parsed_date = parsed_date.astimezone(dt_timezone.utc).replace(tzinfo=None)
                    else:
                        # No timezone info - assume it's local time and convert to UTC
                        # Get local timezone offset
                        local_offset = time.timezone if (time.daylight == 0) else time.altzone
                        local_tz = dt_timezone(timedelta(seconds=-local_offset))
                        parsed_date = parsed_date.replace(tzinfo=local_tz).astimezone(dt_timezone.utc).replace(tzinfo=None)
                    
                    # For end_date, add 2 hours to account for timezone and timing differences
                    adjusted_date = parsed_date + timedelta(hours=2)
                    normalized_date = adjusted_date.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("ch.created_at <= ?")
                    params.append(normalized_date)
                except (ValueError, AttributeError) as e:
                    # If parsing fails, use as-is
                    logger.warning(f"Failed to parse end_date '{end_date}': {e}, using as-is")
                    conditions.append("ch.created_at <= ?")
                    params.append(end_date)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Query change_history with task title for context
            query = f"""
                SELECT 
                    ch.*,
                    t.title as task_title
                FROM change_history ch
                LEFT JOIN tasks t ON ch.task_id = t.id
                {where_clause}
                ORDER BY ch.created_at ASC
                LIMIT ?
            """
            params.append(limit)
            
            cursor.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            return results
        finally:
            self.adapter.close(conn)
    
    def get_agent_stats(
        self,
        agent_id: str,
        task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get statistics for an agent's performance."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get completed tasks count
            completed_query = """
                SELECT COUNT(*) as count FROM change_history
                WHERE agent_id = ? AND change_type = 'completed'
            """
            params = [agent_id]
            if task_type:
                completed_query = """
                    SELECT COUNT(*) as count FROM change_history ch
                    JOIN tasks t ON ch.task_id = t.id
                    WHERE ch.agent_id = ? AND ch.change_type = 'completed' AND t.task_type = ?
                """
                params.append(task_type)
            
            cursor.execute(completed_query, params)
            completed = cursor.fetchone()["count"]
            
            # Get verified tasks count
            verified_query = """
                SELECT COUNT(*) as count FROM change_history
                WHERE agent_id = ? AND change_type = 'verified'
            """
            verified_params = [agent_id]
            if task_type:
                verified_query = """
                    SELECT COUNT(*) as count FROM change_history ch
                    JOIN tasks t ON ch.task_id = t.id
                    WHERE ch.agent_id = ? AND ch.change_type = 'verified' AND t.task_type = ?
                """
                verified_params.append(task_type)
            
            cursor.execute(verified_query, verified_params)
            verified = cursor.fetchone()["count"]
            
            # Get success rate (completed and verified)
            cursor.execute("""
                SELECT COUNT(DISTINCT ch1.task_id) as count FROM change_history ch1
                JOIN change_history ch2 ON ch1.task_id = ch2.task_id
                WHERE ch1.agent_id = ? AND ch1.change_type = 'completed'
                    AND ch2.agent_id = ? AND ch2.change_type = 'verified'
            """, (agent_id, agent_id))
            success_count = cursor.fetchone()["count"]
            
            # Get average time delta for completed tasks
            avg_delta_query = """
                SELECT AVG(t.time_delta_hours) as avg_delta FROM tasks t
                JOIN change_history ch ON t.id = ch.task_id
                WHERE ch.agent_id = ? AND ch.change_type = 'completed'
                    AND t.time_delta_hours IS NOT NULL
            """
            avg_delta_params = [agent_id]
            if task_type:
                avg_delta_query = """
                    SELECT AVG(t.time_delta_hours) as avg_delta FROM tasks t
                    JOIN change_history ch ON t.id = ch.task_id
                    WHERE ch.agent_id = ? AND ch.change_type = 'completed'
                        AND t.task_type = ? AND t.time_delta_hours IS NOT NULL
                """
                avg_delta_params.append(task_type)
            
            cursor.execute(avg_delta_query, avg_delta_params)
            avg_delta_result = cursor.fetchone()
            avg_time_delta = float(avg_delta_result["avg_delta"]) if avg_delta_result["avg_delta"] is not None else None
            
            return {
                "agent_id": agent_id,
                "tasks_completed": completed,
                "tasks_verified": verified,
                "success_rate": (success_count / completed * 100) if completed > 0 else 0.0,
                "avg_time_delta": avg_time_delta,
                "task_type_filter": task_type
            }
        finally:
            self.adapter.close(conn)
    
    def get_completion_rates(
        self,
        project_id: Optional[int] = None,
        task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get completion rates for tasks."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Get total tasks
            cursor.execute(f"SELECT COUNT(*) as count FROM tasks{where_clause}", params)
            total_tasks = cursor.fetchone()["count"]
            
            # Get completed tasks
            completed_params = params + ["complete"]
            if where_clause:
                completed_query = f"SELECT COUNT(*) as count FROM tasks{where_clause} AND task_status = ?"
            else:
                completed_query = "SELECT COUNT(*) as count FROM tasks WHERE task_status = ?"
            cursor.execute(completed_query, completed_params)
            completed_tasks = cursor.fetchone()["count"]
            
            # Calculate percentage
            completion_percentage = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0
            
            # Get status breakdown
            status_params = params + []
            cursor.execute(
                f"""
                SELECT task_status, COUNT(*) as count 
                FROM tasks{where_clause}
                GROUP BY task_status
                """,
                status_params if where_clause else []
            )
            status_breakdown = {row["task_status"]: row["count"] for row in cursor.fetchall()}
            
            # Get type breakdown
            type_params = params + []
            cursor.execute(
                f"""
                SELECT task_type, COUNT(*) as count,
                       SUM(CASE WHEN task_status = 'complete' THEN 1 ELSE 0 END) as completed
                FROM tasks{where_clause}
                GROUP BY task_type
                """,
                type_params if where_clause else []
            )
            tasks_by_type = {}
            for row in cursor.fetchall():
                tasks_by_type[row["task_type"]] = {
                    "total": row["count"],
                    "completed": row["completed"],
                    "completion_percentage": (row["completed"] / row["count"] * 100) if row["count"] > 0 else 0.0
                }
            
            return {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "completion_percentage": round(completion_percentage, 2),
                "status_breakdown": status_breakdown,
                "tasks_by_type": tasks_by_type
            }
        finally:
            self.adapter.close(conn)
    
    def get_average_time_to_complete(
        self,
        project_id: Optional[int] = None,
        task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get average time to complete tasks (from created_at to completed_at)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            conditions = ["task_status = 'complete'", "completed_at IS NOT NULL", "created_at IS NOT NULL"]
            params = []
            
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
            
            where_clause = " WHERE " + " AND ".join(conditions)
            
            # Calculate average hours
            cursor.execute(
                f"""
                SELECT 
                    AVG((julianday(completed_at) - julianday(created_at)) * 24) as avg_hours,
                    COUNT(*) as completed_count,
                    MIN((julianday(completed_at) - julianday(created_at)) * 24) as min_hours,
                    MAX((julianday(completed_at) - julianday(created_at)) * 24) as max_hours
                FROM tasks
                {where_clause}
                """,
                params
            )
            result = cursor.fetchone()
            
            avg_hours = float(result["avg_hours"]) if result["avg_hours"] else None
            min_hours = float(result["min_hours"]) if result["min_hours"] else None
            max_hours = float(result["max_hours"]) if result["max_hours"] else None
            completed_count = result["completed_count"]
            
            return {
                "average_hours": round(avg_hours, 2) if avg_hours else None,
                "min_hours": round(min_hours, 2) if min_hours else None,
                "max_hours": round(max_hours, 2) if max_hours else None,
                "completed_count": completed_count
            }
        finally:
            self.adapter.close(conn)
    
    def get_bottlenecks(
        self,
        long_running_hours: float = 24.0,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Identify bottlenecks: long-running tasks and blocking tasks."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Find long-running in_progress tasks
            cursor.execute(
                """
                SELECT t.*, 
                       (julianday('now') - julianday(t.updated_at)) * 24 as hours_in_progress
                FROM tasks t
                WHERE t.task_status = 'in_progress'
                  AND (julianday('now') - julianday(t.updated_at)) * 24 > ?
                ORDER BY hours_in_progress DESC
                LIMIT ?
                """,
                (long_running_hours, limit)
            )
            long_running_tasks = [dict(row) for row in cursor.fetchall()]
            
            # Find tasks with blocking relationships
            cursor.execute(
                """
                SELECT DISTINCT t.*,
                       COUNT(DISTINCT tr2.id) as blocking_count
                FROM tasks t
                JOIN task_relationships tr1 ON t.id = tr1.child_task_id
                LEFT JOIN task_relationships tr2 ON t.id = tr2.child_task_id AND tr2.relationship_type = 'blocking'
                WHERE tr1.relationship_type = 'blocking'
                  AND t.task_status != 'complete'
                GROUP BY t.id
                ORDER BY blocking_count DESC, t.updated_at ASC
                LIMIT ?
                """,
                (limit,)
            )
            blocking_tasks = [dict(row) for row in cursor.fetchall()]
            
            # Find tasks blocked by incomplete tasks
            cursor.execute(
                """
                SELECT t.*, 
                       COUNT(DISTINCT tr.parent_task_id) as blockers_count
                FROM tasks t
                JOIN task_relationships tr ON t.id = tr.child_task_id
                JOIN tasks parent ON tr.parent_task_id = parent.id
                WHERE tr.relationship_type IN ('blocking', 'blocked_by')
                  AND parent.task_status != 'complete'
                  AND t.task_status != 'complete'
                GROUP BY t.id
                ORDER BY blockers_count DESC
                LIMIT ?
                """,
                (limit,)
            )
            blocked_tasks = [dict(row) for row in cursor.fetchall()]
            
            return {
                "long_running_tasks": long_running_tasks,
                "blocking_tasks": blocking_tasks,
                "blocked_tasks": blocked_tasks
            }
        finally:
            self.adapter.close(conn)
    
    def get_agent_comparisons(
        self,
        task_type: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Get performance comparisons for all agents."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get agent stats for all agents
            type_condition = "AND t.task_type = ?" if task_type else ""
            type_params = [task_type] if task_type else []
            
            cursor.execute(
                f"""
                SELECT 
                    ch.agent_id,
                    COUNT(DISTINCT CASE WHEN ch.change_type = 'completed' THEN ch.task_id END) as tasks_completed,
                    COUNT(DISTINCT CASE WHEN ch2.change_type = 'verified' THEN ch.task_id END) as tasks_verified,
                    AVG(CASE WHEN ch.change_type = 'completed' AND t.time_delta_hours IS NOT NULL 
                        THEN t.time_delta_hours END) as avg_time_delta,
                    AVG(CASE WHEN ch.change_type = 'completed' AND t.actual_hours IS NOT NULL 
                        THEN t.actual_hours END) as avg_actual_hours,
                    AVG(CASE WHEN ch.change_type = 'completed' AND t.estimated_hours IS NOT NULL 
                        THEN t.estimated_hours END) as avg_estimated_hours
                FROM change_history ch
                JOIN tasks t ON ch.task_id = t.id
                LEFT JOIN change_history ch2 ON ch.task_id = ch2.task_id AND ch2.change_type = 'verified'
                WHERE ch.change_type = 'completed'
                    {type_condition}
                GROUP BY ch.agent_id
                HAVING tasks_completed > 0
                ORDER BY tasks_completed DESC
                LIMIT ?
                """,
                type_params + [limit]
            )
            
            agents = []
            for row in cursor.fetchall():
                agent_data = {
                    "agent_id": row["agent_id"],
                    "tasks_completed": row["tasks_completed"],
                    "tasks_verified": row["tasks_verified"] or 0,
                    "avg_time_delta": round(float(row["avg_time_delta"]), 2) if row["avg_time_delta"] else None,
                    "avg_actual_hours": round(float(row["avg_actual_hours"]), 2) if row["avg_actual_hours"] else None,
                    "avg_estimated_hours": round(float(row["avg_estimated_hours"]), 2) if row["avg_estimated_hours"] else None
                }
                # Calculate success rate
                if agent_data["tasks_completed"] > 0:
                    agent_data["success_rate"] = round(
                        (agent_data["tasks_verified"] / agent_data["tasks_completed"]) * 100, 2
                    )
                else:
                    agent_data["success_rate"] = 0.0
                agents.append(agent_data)
            
            return {
                "agents": agents,
                "total_agents": len(agents),
                "task_type_filter": task_type
            }
        finally:
            self.adapter.close(conn)
    
    def record_agent_experience(
        self,
        agent_id: str,
        task_id: Optional[int] = None,
        outcome: str = "success",
        execution_time_hours: Optional[float] = None,
        failure_reason: Optional[str] = None,
        strategy_used: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Record an agent experience for learning and improvement.
        
        Args:
            agent_id: Agent identifier
            task_id: Optional task ID this experience relates to
            outcome: Outcome of the experience ('success', 'failure', 'partial')
            execution_time_hours: Time taken to complete (if applicable)
            failure_reason: Reason for failure (if outcome is 'failure')
            strategy_used: Strategy or approach used
            notes: Additional notes
            metadata: Additional structured metadata (JSON)
            
        Returns:
            Experience ID
        """
        if outcome not in ["success", "failure", "partial"]:
            raise ValueError(f"Invalid outcome: {outcome}. Must be one of: success, failure, partial")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            metadata_json = json.dumps(metadata) if metadata else None
            
            experience_id = self._execute_insert(cursor, """
                INSERT INTO agent_experiences (
                    agent_id, task_id, outcome, execution_time_hours,
                    failure_reason, strategy_used, notes, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (agent_id, task_id, outcome, execution_time_hours,
                  failure_reason, strategy_used, notes, metadata_json))
            
            conn.commit()
            logger.info(f"Recorded experience {experience_id} for agent {agent_id} (outcome: {outcome})")
            return experience_id
        finally:
            self.adapter.close(conn)
    
    def get_agent_experience(self, experience_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific agent experience by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM agent_experiences WHERE id = ?", (experience_id,))
            row = cursor.fetchone()
            if row:
                experience = dict(row)
                # Parse metadata JSON if present
                if experience.get("metadata"):
                    try:
                        experience["metadata"] = json.loads(experience["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        experience["metadata"] = {}
                return experience
            return None
        finally:
            self.adapter.close(conn)
    
    def query_agent_experiences(
        self,
        agent_id: Optional[str] = None,
        task_id: Optional[int] = None,
        outcome: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query agent experiences with filters.
        
        Args:
            agent_id: Filter by agent ID
            task_id: Filter by task ID
            outcome: Filter by outcome ('success', 'failure', 'partial')
            limit: Maximum number of results
            
        Returns:
            List of experience dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            
            if agent_id:
                conditions.append("agent_id = ?")
                params.append(agent_id)
            if task_id:
                conditions.append("task_id = ?")
                params.append(task_id)
            if outcome:
                if outcome not in ["success", "failure", "partial"]:
                    raise ValueError(f"Invalid outcome: {outcome}")
                conditions.append("outcome = ?")
                params.append(outcome)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            params.append(limit)
            
            cursor.execute(f"""
                SELECT * FROM agent_experiences
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """, params)
            
            experiences = []
            for row in cursor.fetchall():
                exp = dict(row)
                # Parse metadata JSON if present
                if exp.get("metadata"):
                    try:
                        exp["metadata"] = json.loads(exp["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        exp["metadata"] = {}
                experiences.append(exp)
            
            return experiences
        finally:
            self.adapter.close(conn)
    
    def get_agent_learning_stats(self, agent_id: str) -> Dict[str, Any]:
        """
        Get learning statistics for an agent based on their experiences.
        
        Args:
            agent_id: Agent identifier
            
        Returns:
            Dictionary with learning statistics
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get total experiences and outcomes
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_experiences,
                    COUNT(CASE WHEN outcome = 'success' THEN 1 END) as success_count,
                    COUNT(CASE WHEN outcome = 'failure' THEN 1 END) as failure_count,
                    COUNT(CASE WHEN outcome = 'partial' THEN 1 END) as partial_count,
                    AVG(execution_time_hours) as avg_execution_time,
                    MIN(execution_time_hours) as min_execution_time,
                    MAX(execution_time_hours) as max_execution_time
                FROM agent_experiences
                WHERE agent_id = ?
            """, (agent_id,))
            
            row = cursor.fetchone()
            if row and row["total_experiences"] and row["total_experiences"] > 0:
                total = row["total_experiences"]
                success_count = row["success_count"] or 0
                failure_count = row["failure_count"] or 0
                partial_count = row["partial_count"] or 0
                
                return {
                    "agent_id": agent_id,
                    "total_experiences": total,
                    "success_count": success_count,
                    "failure_count": failure_count,
                    "partial_count": partial_count,
                    "success_rate": success_count / total if total > 0 else 0.0,
                    "failure_rate": failure_count / total if total > 0 else 0.0,
                    "avg_execution_time": round(float(row["avg_execution_time"]), 2) if row["avg_execution_time"] else None,
                    "min_execution_time": round(float(row["min_execution_time"]), 2) if row["min_execution_time"] else None,
                    "max_execution_time": round(float(row["max_execution_time"]), 2) if row["max_execution_time"] else None,
                }
            else:
                # No experiences yet
                return {
                    "agent_id": agent_id,
                    "total_experiences": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "partial_count": 0,
                    "success_rate": 0.0,
                    "failure_rate": 0.0,
                    "avg_execution_time": None,
                    "min_execution_time": None,
                    "max_execution_time": None,
                }
        finally:
            self.adapter.close(conn)
    
    def get_visualization_data(
        self,
        project_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get data formatted for visualization/charts."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            conditions = []
            params = []
            
            if project_id:
                conditions.append("project_id = ?")
                params.append(project_id)
            
            if start_date:
                conditions.append("DATE(created_at) >= DATE(?)")
                params.append(start_date)
            
            if end_date:
                conditions.append("DATE(created_at) <= DATE(?)")
                params.append(end_date)
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Status distribution
            cursor.execute(
                f"""
                SELECT task_status, COUNT(*) as count
                FROM tasks
                {where_clause}
                GROUP BY task_status
                """,
                params if where_clause else []
            )
            status_distribution = {row["task_status"]: row["count"] for row in cursor.fetchall()}
            
            # Type distribution
            cursor.execute(
                f"""
                SELECT task_type, COUNT(*) as count
                FROM tasks
                {where_clause}
                GROUP BY task_type
                """,
                params if where_clause else []
            )
            type_distribution = {row["task_type"]: row["count"] for row in cursor.fetchall()}
            
            # Completion timeline (by day)
            timeline_conditions = ["completed_at IS NOT NULL"]
            timeline_params = []
            
            if project_id:
                timeline_conditions.append("project_id = ?")
                timeline_params.append(project_id)
            
            if start_date:
                timeline_conditions.append("DATE(completed_at) >= DATE(?)")
                timeline_params.append(start_date)
            
            if end_date:
                timeline_conditions.append("DATE(completed_at) <= DATE(?)")
                timeline_params.append(end_date)
            
            timeline_where = " WHERE " + " AND ".join(timeline_conditions)
            
            cursor.execute(
                f"""
                SELECT DATE(completed_at) as date, COUNT(*) as count
                FROM tasks
                {timeline_where}
                GROUP BY DATE(completed_at)
                ORDER BY date ASC
                """,
                timeline_params
            )
            completion_timeline = [
                {"date": row["date"], "count": row["count"]}
                for row in cursor.fetchall()
            ]
            
            # Priority distribution
            cursor.execute(
                f"""
                SELECT priority, COUNT(*) as count
                FROM tasks
                {where_clause}
                GROUP BY priority
                """,
                params if where_clause else []
            )
            priority_distribution = {row["priority"]: row["count"] for row in cursor.fetchall()}
            
            return {
                "status_distribution": status_distribution,
                "type_distribution": type_distribution,
                "priority_distribution": priority_distribution,
                "completion_timeline": completion_timeline
            }
        finally:
            self.adapter.close(conn)
    
    def get_task_statistics(
        self,
        project_id: Optional[int] = None,
        task_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated statistics about tasks.
        
        Args:
            project_id: Optional project filter
            task_type: Optional task type filter
            start_date: Optional start date filter (ISO format)
            end_date: Optional end date filter (ISO format)
            
        Returns:
            Dictionary with statistics including counts by status, type, project, and completion rate
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Build WHERE clause
            conditions = []
            params = []
            
            if project_id is not None:
                conditions.append("project_id = ?")
                params.append(project_id)
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
            if start_date:
                conditions.append("created_at >= ?")
                params.append(start_date)
            if end_date:
                conditions.append("created_at <= ?")
                params.append(end_date)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Total count
            cursor.execute(f"SELECT COUNT(*) FROM tasks {where_clause}", params)
            total = cursor.fetchone()[0]
            
            # Counts by status
            status_counts = {}
            for status in ["available", "in_progress", "complete", "blocked", "cancelled"]:
                status_params = params + [status]
                if conditions:
                    status_where = f"{where_clause} AND task_status = ?"
                else:
                    status_where = "WHERE task_status = ?"
                cursor.execute(
                    f"SELECT COUNT(*) FROM tasks {status_where}",
                    status_params
                )
                status_counts[status] = cursor.fetchone()[0]
            
            # Counts by task_type
            type_counts = {}
            for task_type_val in ["concrete", "abstract", "epic"]:
                type_params = params + [task_type_val]
                if conditions:
                    type_where = f"{where_clause} AND task_type = ?"
                else:
                    type_where = "WHERE task_type = ?"
                cursor.execute(
                    f"SELECT COUNT(*) FROM tasks {type_where}",
                    type_params
                )
                type_counts[task_type_val] = cursor.fetchone()[0]
            
            # Counts by project (if not filtering by project)
            project_counts = {}
            if project_id is None:
                cursor.execute("SELECT project_id, COUNT(*) FROM tasks GROUP BY project_id")
                for row in cursor.fetchall():
                    proj_id = row[0]
                    count = row[1]
                    project_counts[proj_id] = count
            
            # Completion rate
            completion_rate = 0.0
            if total > 0:
                completion_rate = (status_counts.get("complete", 0) / total) * 100
            
            return {
                "total": total,
                "by_status": status_counts,
                "by_type": type_counts,
                "by_project": project_counts if project_id is None else {project_id: total},
                "completion_rate": round(completion_rate, 2)
            }
        finally:
            conn.close()
    
    def get_recent_completions(
        self,
        limit: int = 10,
        project_id: Optional[int] = None,
        hours: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recently completed tasks sorted by completion time.
        
        Args:
            limit: Maximum number of tasks to return
            project_id: Optional project filter
            hours: Optional filter for completions within last N hours
            
        Returns:
            List of task dictionaries (lightweight summary format)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            conditions = ["task_status = 'complete'", "completed_at IS NOT NULL"]
            params = []
            
            if project_id is not None:
                conditions.append("project_id = ?")
                params.append(project_id)
            
            if hours is not None:
                if self.db_type == "sqlite":
                    conditions.append(f"completed_at >= datetime('now', '-{hours} hours')")
                else:
                    conditions.append("completed_at >= NOW() - INTERVAL ? HOUR")
                    params.append(hours)
            
            where_clause = "WHERE " + " AND ".join(conditions)
            
            query = f"""
                SELECT id, title, task_status, assigned_agent, project_id, 
                       created_at, updated_at, completed_at
                FROM tasks
                {where_clause}
                ORDER BY completed_at DESC
                LIMIT ?
            """
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def get_task_summaries(
        self,
        project_id: Optional[int] = None,
        task_type: Optional[str] = None,
        task_status: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get lightweight task summaries (essential fields only).
        
        Args:
            project_id: Optional project filter
            task_type: Optional task type filter
            task_status: Optional status filter
            assigned_agent: Optional agent filter
            priority: Optional priority filter
            limit: Maximum number of results
            
        Returns:
            List of task summary dictionaries with only essential fields
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            conditions = []
            params = []
            
            if project_id is not None:
                conditions.append("project_id = ?")
                params.append(project_id)
            if task_type:
                conditions.append("task_type = ?")
                params.append(task_type)
            if task_status:
                conditions.append("task_status = ?")
                params.append(task_status)
            if assigned_agent:
                conditions.append("assigned_agent = ?")
                params.append(assigned_agent)
            if priority:
                conditions.append("priority = ?")
                params.append(priority)
            
            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            query = f"""
                SELECT id, title, task_type, task_status, assigned_agent, 
                       project_id, priority, created_at, updated_at, completed_at
                FROM tasks
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """
            params.append(limit)
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            self.adapter.close(conn)
