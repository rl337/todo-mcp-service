"""
Repository for recurring task operations.

This module extracts recurring task-related database operations from TodoDatabase
to improve separation of concerns and maintainability.
"""
import json
import logging
from datetime import datetime, timedelta
import calendar
from typing import Optional, List, Dict, Any, Callable

logger = logging.getLogger(__name__)


class RecurringRepository:
    """Repository for recurring task operations."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        adapter: Any,
        execute_insert: Callable[[Any, str, tuple], int],
        execute_with_logging: Callable[[Any, str, tuple], Any],
        get_task: Callable[[int], Optional[Dict[str, Any]]],
        create_task: Callable[..., int]
    ):
        """
        Initialize RecurringRepository.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            get_connection: Function to get database connection
            adapter: Database adapter (for closing connections)
            execute_insert: Function to execute INSERT queries and return ID
            execute_with_logging: Function to execute queries with logging
            get_task: Function to get a task by ID
            create_task: Function to create a new task
        """
        self.db_type = db_type
        self._get_connection = get_connection
        self.adapter = adapter
        self._execute_insert = execute_insert
        self._execute_with_logging = execute_with_logging
        self._get_task = get_task
        self._create_task = create_task
    
    def _parse_recurring_task(self, row: Any) -> Dict[str, Any]:
        """
        Parse a recurring task row from database.
        
        Args:
            row: Database row
        
        Returns:
            Parsed recurring task dictionary
        """
        config = json.loads(row["recurrence_config"]) if row.get("recurrence_config") else {}
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "recurrence_type": row["recurrence_type"],
            "recurrence_config": config,
            "next_occurrence": row["next_occurrence"],
            "last_occurrence_created": row.get("last_occurrence_created"),
            "is_active": row["is_active"],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at")
        }
    
    def create(
        self,
        task_id: int,
        recurrence_type: str,
        recurrence_config: Dict[str, Any],
        next_occurrence: datetime
    ) -> int:
        """
        Create a recurring task pattern.
        
        Args:
            task_id: ID of the base task to recur
            recurrence_type: 'daily', 'weekly', or 'monthly'
            recurrence_config: Dictionary with recurrence-specific config
                - For weekly: {'day_of_week': 0-6} (0=Sunday)
                - For monthly: {'day_of_month': 1-31}
            next_occurrence: When to create the next instance
        
        Returns:
            Recurring task ID
        
        Raises:
            ValueError: If recurrence_type is invalid or task not found
        """
        if recurrence_type not in ["daily", "weekly", "monthly"]:
            raise ValueError(f"Invalid recurrence_type: {recurrence_type}. Must be daily, weekly, or monthly")
        
        # Verify task exists
        task = self._get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Store config as JSON string
            config_json = json.dumps(recurrence_config)
            
            recurring_id = self._execute_insert(cursor, """
                INSERT INTO recurring_tasks (
                    task_id, recurrence_type, recurrence_config, 
                    next_occurrence, is_active
                ) VALUES (?, ?, ?, ?, 1)
            """, (task_id, recurrence_type, config_json, next_occurrence))
            
            conn.commit()
            logger.info(f"Created recurring task {recurring_id} for task {task_id}")
            return recurring_id
        finally:
            self.adapter.close(conn)
    
    def get_by_id(self, recurring_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a recurring task by ID.
        
        Args:
            recurring_id: Recurring task ID
        
        Returns:
            Recurring task dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT id, task_id, recurrence_type, recurrence_config,
                       next_occurrence, last_occurrence_created, is_active,
                       created_at, updated_at
                FROM recurring_tasks
                WHERE id = ?
            """
            params = (recurring_id,)
            self._execute_with_logging(cursor, query, params)
            row = cursor.fetchone()
            if row:
                return self._parse_recurring_task(dict(row))
            return None
        finally:
            self.adapter.close(conn)
    
    def list(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """
        List all recurring tasks.
        
        Args:
            active_only: If True, only return active recurring tasks
        
        Returns:
            List of recurring task dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if active_only:
                query = """
                    SELECT id, task_id, recurrence_type, recurrence_config,
                           next_occurrence, last_occurrence_created, is_active,
                           created_at, updated_at
                    FROM recurring_tasks
                    WHERE is_active = 1
                    ORDER BY next_occurrence ASC
                """
            else:
                query = """
                    SELECT id, task_id, recurrence_type, recurrence_config,
                           next_occurrence, last_occurrence_created, is_active,
                           created_at, updated_at
                    FROM recurring_tasks
                    ORDER BY next_occurrence ASC
                """
            params = None
            self._execute_with_logging(cursor, query, params)
            
            results = []
            for row in cursor.fetchall():
                results.append(self._parse_recurring_task(dict(row)))
            return results
        finally:
            self.adapter.close(conn)
    
    def get_due(self) -> List[Dict[str, Any]]:
        """
        Get all recurring tasks that are due for instance creation
        (next_occurrence <= now and is_active = 1).
        
        Returns:
            List of recurring task dictionaries
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT id, task_id, recurrence_type, recurrence_config,
                       next_occurrence, last_occurrence_created, is_active,
                       created_at, updated_at
                FROM recurring_tasks
                WHERE is_active = 1 AND next_occurrence <= CURRENT_TIMESTAMP
                ORDER BY next_occurrence ASC
            """
            params = None
            self._execute_with_logging(cursor, query, params)
            
            results = []
            for row in cursor.fetchall():
                results.append(self._parse_recurring_task(dict(row)))
            return results
        finally:
            self.adapter.close(conn)
    
    def create_instance(self, recurring_id: int) -> int:
        """
        Create a new task instance from a recurring task pattern.
        Updates next_occurrence based on recurrence type.
        
        Args:
            recurring_id: Recurring task ID
        
        Returns:
            New task instance ID
        
        Raises:
            ValueError: If recurring task not found, not active, or base task not found
        """
        recurring = self.get_by_id(recurring_id)
        if not recurring:
            raise ValueError(f"Recurring task {recurring_id} not found")
        
        if recurring["is_active"] != 1:
            raise ValueError(f"Recurring task {recurring_id} is not active")
        
        # Get base task
        base_task = self._get_task(recurring["task_id"])
        if not base_task:
            raise ValueError(f"Base task {recurring['task_id']} not found")
        
        # Create new task instance with same properties as base task
        new_task_id = self._create_task(
            title=base_task["title"],
            task_type=base_task["task_type"],
            task_instruction=base_task["task_instruction"],
            verification_instruction=base_task["verification_instruction"],
            agent_id="system",  # System-created instances
            project_id=base_task.get("project_id"),
            notes=base_task.get("notes"),
            priority=base_task.get("priority", "medium"),
            estimated_hours=base_task.get("estimated_hours")
        )
        
        # Calculate next occurrence
        current_next = recurring["next_occurrence"]
        if isinstance(current_next, str):
            # Parse ISO format datetime string
            current_next = datetime.fromisoformat(current_next.replace('Z', '+00:00'))
        
        if recurring["recurrence_type"] == "daily":
            next_occurrence = current_next + timedelta(days=1)
        elif recurring["recurrence_type"] == "weekly":
            # Add 7 days
            next_occurrence = current_next + timedelta(days=7)
        elif recurring["recurrence_type"] == "monthly":
            # Add approximately one month
            if current_next.month == 12:
                next_occurrence = current_next.replace(year=current_next.year + 1, month=1)
            else:
                next_occurrence = current_next.replace(month=current_next.month + 1)
            
            # Handle day_of_month config if specified
            config = recurring.get("recurrence_config", {})
            if "day_of_month" in config:
                day_of_month = config["day_of_month"]
                # Clamp to valid days in the target month
                last_day = calendar.monthrange(next_occurrence.year, next_occurrence.month)[1]
                day_of_month = min(day_of_month, last_day)
                next_occurrence = next_occurrence.replace(day=day_of_month)
        else:
            raise ValueError(f"Unknown recurrence_type: {recurring['recurrence_type']}")
        
        # Update recurring task
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                UPDATE recurring_tasks
                SET next_occurrence = ?,
                    last_occurrence_created = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (next_occurrence, recurring_id)
            self._execute_with_logging(cursor, query, params)
            conn.commit()
            logger.info(f"Created recurring instance {new_task_id} from recurring task {recurring_id}")
        finally:
            self.adapter.close(conn)
        
        return new_task_id
    
    def update(
        self,
        recurring_id: int,
        recurrence_type: Optional[str] = None,
        recurrence_config: Optional[Dict[str, Any]] = None,
        next_occurrence: Optional[datetime] = None
    ) -> None:
        """
        Update a recurring task.
        
        Args:
            recurring_id: Recurring task ID
            recurrence_type: Optional new recurrence type
            recurrence_config: Optional new recurrence config
            next_occurrence: Optional new next occurrence date
        
        Raises:
            ValueError: If recurring task not found or invalid recurrence_type
        """
        recurring = self.get_by_id(recurring_id)
        if not recurring:
            raise ValueError(f"Recurring task {recurring_id} not found")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if recurrence_type:
                if recurrence_type not in ["daily", "weekly", "monthly"]:
                    raise ValueError(f"Invalid recurrence_type: {recurrence_type}")
                updates.append("recurrence_type = ?")
                params.append(recurrence_type)
            
            if recurrence_config is not None:
                config_json = json.dumps(recurrence_config)
                updates.append("recurrence_config = ?")
                params.append(config_json)
            
            if next_occurrence:
                updates.append("next_occurrence = ?")
                params.append(next_occurrence)
            
            if not updates:
                return  # No updates to make
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(recurring_id)
            
            query = f"""
                UPDATE recurring_tasks
                SET {', '.join(updates)}
                WHERE id = ?
            """
            self._execute_with_logging(cursor, query, tuple(params))
            conn.commit()
            logger.info(f"Updated recurring task {recurring_id}")
        finally:
            self.adapter.close(conn)
    
    def deactivate(self, recurring_id: int) -> None:
        """
        Deactivate a recurring task (stop creating new instances).
        
        Args:
            recurring_id: Recurring task ID
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = """
                UPDATE recurring_tasks
                SET is_active = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (recurring_id,)
            self._execute_with_logging(cursor, query, params)
            conn.commit()
            logger.info(f"Deactivated recurring task {recurring_id}")
        finally:
            self.adapter.close(conn)
    
    def process_due(self) -> List[int]:
        """
        Process all due recurring tasks and create instances.
        This should be called periodically (e.g., via cron job).
        
        Returns:
            List of newly created task instance IDs
        """
        due_tasks = self.get_due()
        created_task_ids = []
        
        for recurring in due_tasks:
            try:
                instance_id = self.create_instance(recurring["id"])
                created_task_ids.append(instance_id)
                logger.info(f"Processed recurring task {recurring['id']}, created instance {instance_id}")
            except Exception as e:
                logger.error(f"Failed to process recurring task {recurring['id']}: {e}", exc_info=True)
        
        return created_task_ids
