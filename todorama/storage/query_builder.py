"""
Query builder for task queries and searches.

This module extracts complex query building logic from TodoDatabase
to reduce complexity and improve maintainability.
"""
import sqlite3
import logging
from typing import Optional, List, Dict, Any, Tuple, Callable

logger = logging.getLogger(__name__)


class TaskQueryBuilder:
    """Builds SQL queries for task filtering and searching."""
    
    def __init__(
        self,
        db_type: str,
        get_connection: Callable[[], Any],
        normalize_sql: Callable[[str], str],
        execute_with_logging: Callable[[Any, str, Tuple], Any]
    ):
        """
        Initialize TaskQueryBuilder.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            get_connection: Function to get database connection
            normalize_sql: Function to normalize SQL queries
            execute_with_logging: Function to execute queries with logging
        """
        self.db_type = db_type
        self._get_connection = get_connection
        self._normalize_sql = normalize_sql
        self._execute_with_logging = execute_with_logging
    
    def build_conditions(
        self,
        task_type: Optional[str] = None,
        task_status: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        project_id: Optional[int] = None,
        priority: Optional[str] = None,
        has_due_date: Optional[bool] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        updated_after: Optional[str] = None,
        updated_before: Optional[str] = None,
        completed_after: Optional[str] = None,
        completed_before: Optional[str] = None,
        search: Optional[str] = None,
        organization_id: Optional[int] = None
    ) -> Tuple[List[str], List[Any]]:
        """
        Build WHERE clause conditions from filters.
        
        Returns:
            Tuple of (conditions list, params list)
        """
        conditions = []
        params = []
        
        if task_type:
            conditions.append("t.task_type = ?")
            params.append(task_type)
        
        # Handle task_status filter
        # Special handling for 'blocked' and 'needs_verification' will be done in build_query
        filter_task_status = task_status
        if task_status == "blocked":
            # Don't add task_status filter yet - will be handled in build_query
            pass
        elif task_status == "needs_verification":
            # needs_verification is a computed state: complete + unverified
            conditions.append("t.task_status = 'complete' AND t.verification_status = 'unverified'")
        elif task_status:
            conditions.append("t.task_status = ?")
            params.append(task_status)
        
        if assigned_agent:
            conditions.append("t.assigned_agent = ?")
            params.append(assigned_agent)
        
        if project_id is not None:
            conditions.append("t.project_id = ?")
            params.append(project_id)
        
        # Tenant isolation: filter by organization_id
        if organization_id is not None:
            conditions.append("t.organization_id = ?")
            params.append(organization_id)
        
        if priority:
            conditions.append("t.priority = ?")
            params.append(priority)
        
        # Handle due_date filtering
        if has_due_date is not None:
            if has_due_date:
                conditions.append("t.due_date IS NOT NULL")
            else:
                conditions.append("t.due_date IS NULL")
        
        # Handle date range filtering
        if created_after:
            conditions.append("t.created_at >= ?")
            params.append(created_after)
        if created_before:
            conditions.append("t.created_at <= ?")
            params.append(created_before)
        if updated_after:
            conditions.append("t.updated_at >= ?")
            params.append(updated_after)
        if updated_before:
            conditions.append("t.updated_at <= ?")
            params.append(updated_before)
        if completed_after:
            conditions.append("t.completed_at >= ?")
            params.append(completed_after)
        if completed_before:
            conditions.append("t.completed_at <= ?")
            params.append(completed_before)
        
        # Handle text search (case-insensitive search in title and task_instruction)
        if search:
            search_term = f"%{search.lower()}%"
            # SQLite LIKE is case-insensitive by default, but use LOWER for consistency
            conditions.append("(LOWER(t.title) LIKE ? OR LOWER(t.task_instruction) LIKE ?)")
            params.append(search_term)
            params.append(search_term)
        
        return conditions, params, filter_task_status
    
    def apply_tag_filters(
        self,
        tag_id: Optional[int] = None,
        tag_ids: Optional[List[int]] = None
    ) -> Tuple[str, str, List[Any]]:
        """
        Build tag filtering JOIN and GROUP BY clauses.
        
        Returns:
            Tuple of (join_clause, group_by_clause, params)
        """
        join_clause = ""
        group_by_clause = ""
        params = []
        
        if tag_id:
            join_clause = "INNER JOIN task_tags tt ON t.id = tt.task_id"
            params.append(tag_id)
        elif tag_ids:
            # Multiple tags: task must have all specified tags
            join_clause = "INNER JOIN task_tags tt ON t.id = tt.task_id"
            placeholders = ",".join("?" * len(tag_ids))
            params.extend(tag_ids)
            # Group by to ensure we get tasks that have all tags
            group_by_clause = "GROUP BY t.id HAVING COUNT(DISTINCT tt.tag_id) = ?"
            params.append(len(tag_ids))
        
        return join_clause, group_by_clause, params
    
    def build_order_by(self, order_by: Optional[str] = None) -> str:
        """
        Build ORDER BY clause.
        
        Args:
            order_by: Ordering option ('priority', 'priority_asc', or None for default)
        
        Returns:
            ORDER BY clause string
        """
        # Default ordering by created_at DESC
        if order_by == "priority":
            # Order by priority: critical > high > medium > low
            return """ORDER BY 
                CASE t.priority 
                    WHEN 'critical' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0
                END DESC, t.created_at DESC"""
        elif order_by == "priority_asc":
            # Order by priority ascending: low > medium > high > critical
            return """ORDER BY 
                CASE t.priority 
                    WHEN 'critical' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    WHEN 'low' THEN 1
                    ELSE 0
                END ASC, t.created_at DESC"""
        else:
            return "ORDER BY t.created_at DESC"
    
    def apply_pagination(self, limit: int) -> Tuple[str, List[Any]]:
        """
        Apply pagination (LIMIT clause).
        
        Args:
            limit: Maximum number of results
        
        Returns:
            Tuple of (limit_clause, params)
        """
        return "LIMIT ?", [limit]
    
    def find_blocked_parent_ids(self, cursor: Any) -> set:
        """
        Find all task IDs that have blocked subtasks (recursively).
        
        This is used for the special 'blocked' status filter that includes
        tasks with blocked subtasks, not just tasks with status='blocked'.
        
        Args:
            cursor: Database cursor
        
        Returns:
            Set of task IDs that have blocked subtasks
        """
        # First, find direct parents of blocked tasks
        cursor.execute("""
            SELECT DISTINCT tr.parent_task_id as id
            FROM task_relationships tr
            JOIN tasks t_child ON tr.child_task_id = t_child.id
            WHERE tr.relationship_type = 'subtask' 
                AND t_child.task_status = 'blocked'
        """)
        all_blocked_parent_ids = {row[0] for row in cursor.fetchall()}
        
        # Recursively find grandparents, etc. with blocked descendants
        new_parents = all_blocked_parent_ids
        while new_parents:
            placeholders = ",".join("?" * len(new_parents))
            cursor.execute(f"""
                SELECT DISTINCT tr.parent_task_id as id
                FROM task_relationships tr
                WHERE tr.relationship_type = 'subtask' 
                    AND tr.child_task_id IN ({placeholders})
                    AND tr.parent_task_id IS NOT NULL
            """, list(new_parents))
            next_level = {row[0] for row in cursor.fetchall() if row[0] is not None}
            next_level -= all_blocked_parent_ids  # Only new ones
            new_parents = next_level
            all_blocked_parent_ids.update(next_level)
        
        return all_blocked_parent_ids
    
    def apply_blocked_status_filter(
        self,
        conditions: List[str],
        params: List[Any],
        cursor: Any,
        filter_task_status: Optional[str]
    ) -> Tuple[List[str], List[Any]]:
        """
        Apply special 'blocked' status filter that includes tasks with blocked subtasks.
        
        Args:
            conditions: Existing WHERE conditions
            params: Existing query parameters
            cursor: Database cursor (for finding blocked parents)
            filter_task_status: Task status filter value
        
        Returns:
            Updated (conditions, params) tuple
        """
        if filter_task_status == "blocked":
            all_blocked_parent_ids = self.find_blocked_parent_ids(cursor)
            
            # Add condition: task_status = 'blocked' OR id in (blocked parent ids)
            if all_blocked_parent_ids:
                parent_placeholders = ",".join("?" * len(all_blocked_parent_ids))
                conditions.append(f"(t.task_status = 'blocked' OR t.id IN ({parent_placeholders}))")
                params.extend(all_blocked_parent_ids)
            else:
                conditions.append("t.task_status = 'blocked'")
        
        return conditions, params
    
    def build_query(
        self,
        conditions: List[str],
        params: List[Any],
        join_clause: str,
        group_by_clause: str,
        order_clause: str,
        limit_clause: str,
        limit_params: List[Any]
    ) -> Tuple[str, List[Any]]:
        """
        Assemble complete SELECT query.
        
        Args:
            conditions: WHERE conditions
            params: Query parameters
            join_clause: JOIN clause (for tags)
            group_by_clause: GROUP BY clause (for multiple tags)
            order_clause: ORDER BY clause
            limit_clause: LIMIT clause
            limit_params: Parameters for LIMIT
        
        Returns:
            Tuple of (query string, params list)
        """
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        # Combine all parts
        all_params = params + limit_params
        query = f"SELECT DISTINCT t.* FROM tasks t {join_clause} {where_clause} {group_by_clause} {order_clause} {limit_clause}"
        
        return query, all_params
    
    def build_search_query(
        self,
        query: str,
        limit: int,
        organization_id: Optional[int] = None
    ) -> Tuple[str, List[Any], bool]:
        """
        Build full-text search query.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            organization_id: Optional organization ID for tenant isolation
        
        Returns:
            Tuple of (query_sql, params, use_fts5) where use_fts5 indicates if FTS5 was used
        """
        search_query = query.strip() if query else ""
        
        # If query is empty, return all tasks (fallback to regular query)
        if not search_query:
            if organization_id is not None:
                query_sql = self._normalize_sql("""
                    SELECT * FROM tasks
                    WHERE organization_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """)
                return query_sql, [organization_id, limit], False
            else:
                query_sql = self._normalize_sql("""
                    SELECT * FROM tasks
                    ORDER BY created_at DESC
                    LIMIT ?
                """)
                return query_sql, [limit], False
        
        # Use different full-text search based on database backend
        if self.db_type == "postgresql":
            # PostgreSQL uses tsvector with GIN index
            # Use to_tsquery for proper query parsing
            tsquery = " & ".join(search_query.split())  # Join words with & to require all terms
            
            if organization_id is not None:
                query_sql = """
                    SELECT *
                    FROM tasks
                    WHERE fts_vector @@ to_tsquery('english', %s)
                        AND organization_id = %s
                    ORDER BY ts_rank(fts_vector, to_tsquery('english', %s)) DESC, created_at DESC
                    LIMIT %s
                """
                return query_sql, [tsquery, organization_id, tsquery, limit], False
            else:
                query_sql = """
                    SELECT *
                    FROM tasks
                    WHERE fts_vector @@ to_tsquery('english', %s)
                    ORDER BY ts_rank(fts_vector, to_tsquery('english', %s)) DESC, created_at DESC
                    LIMIT %s
                """
                return query_sql, [tsquery, tsquery, limit], False
        else:
            # SQLite uses FTS5
            if organization_id is not None:
                query_sql = """
                    SELECT t.*
                    FROM tasks t
                    JOIN tasks_fts ON t.id = tasks_fts.rowid
                    WHERE tasks_fts MATCH ? AND t.organization_id = ?
                    ORDER BY bm25(tasks_fts) ASC, t.created_at DESC
                    LIMIT ?
                """
                return query_sql, [search_query, organization_id, limit], True
            else:
                query_sql = """
                    SELECT t.*
                    FROM tasks t
                    JOIN tasks_fts ON t.id = tasks_fts.rowid
                    WHERE tasks_fts MATCH ?
                    ORDER BY bm25(tasks_fts) ASC, t.created_at DESC
                    LIMIT ?
                """
                return query_sql, [search_query, limit], True
    
    def normalize_search_terms(self, query: str) -> str:
        """
        Normalize and escape search terms.
        
        Args:
            query: Raw search query
        
        Returns:
            Normalized search query
        """
        return query.strip()
    
    def build_like_fallback_query(
        self,
        query: str,
        limit: int,
        organization_id: Optional[int] = None
    ) -> Tuple[str, List[Any]]:
        """
        Build LIKE fallback query for when FTS5 is unavailable.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            organization_id: Optional organization ID
        
        Returns:
            Tuple of (query_sql, params)
        """
        keywords = query.strip().split()
        
        if not keywords:
            # Empty query, return empty results
            if organization_id is not None:
                query_sql = "SELECT * FROM tasks WHERE organization_id = ? LIMIT ?"
                return query_sql, [organization_id, limit]
            else:
                query_sql = "SELECT * FROM tasks WHERE 1=0 LIMIT ?"
                return query_sql, [limit]
        
        # Build LIKE conditions for each keyword (all keywords must match)
        like_conditions = []
        params = []
        for keyword in keywords:
            pattern = f"%{keyword}%"
            like_conditions.append("(title LIKE ? OR task_instruction LIKE ? OR notes LIKE ?)")
            params.extend([pattern, pattern, pattern])
        
        # Add organization_id filter if provided
        if organization_id is not None:
            like_conditions.append("organization_id = ?")
            params.append(organization_id)
        
        query_sql = f"""
            SELECT DISTINCT * FROM tasks
            WHERE {' AND '.join(like_conditions)}
            ORDER BY created_at DESC
            LIMIT ?
        """
        params.append(limit)
        
        return query_sql, params
    
    def execute_search(
        self,
        cursor: Any,
        query: str,
        limit: int,
        organization_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute search query with proper backend handling.
        
        Args:
            cursor: Database cursor
            query: Search query string
            limit: Maximum number of results
            organization_id: Optional organization ID
        
        Returns:
            List of task dictionaries
        """
        search_query = self.normalize_search_terms(query)
        
        # Try FTS5/tsvector first
        try:
            query_sql, params, use_fts5 = self.build_search_query(search_query, limit, organization_id)
            
            if use_fts5 and self.db_type == "sqlite":
                # Try FTS5 for SQLite
                try:
                    self._execute_with_logging(cursor, query_sql, tuple(params))
                    fts_results = cursor.fetchall()
                    if fts_results:
                        # FTS5 worked and returned results
                        return [dict(row) for row in fts_results]
                    else:
                        # FTS5 returned empty - fall back to LIKE
                        logger.warning("FTS5 returned no results, falling back to LIKE")
                except sqlite3.OperationalError:
                    # FTS5 not available - fall back to LIKE
                    logger.warning("FTS5 search failed, falling back to LIKE")
            else:
                # PostgreSQL or non-FTS5 SQLite
                self._execute_with_logging(cursor, query_sql, tuple(params))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning(f"Full-text search failed, falling back to LIKE: {e}")
        
        # Fallback to LIKE search
        like_query, like_params = self.build_like_fallback_query(search_query, limit, organization_id)
        try:
            self._execute_with_logging(cursor, like_query, tuple(like_params))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as fallback_error:
            logger.error(f"LIKE search also failed: {fallback_error}")
            return []
