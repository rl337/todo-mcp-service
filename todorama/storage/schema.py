"""
Schema management for database initialization.

This module handles database schema creation and initialization,
extracted from the monolithic TodoDatabase class for better maintainability.
"""
import sqlite3
import logging
from typing import Callable, Any

from todorama.db_adapter import BaseDatabaseAdapter

logger = logging.getLogger(__name__)


class SchemaManager:
    """Manages database schema initialization and creation."""
    
    def __init__(
        self,
        db_type: str,
        adapter: BaseDatabaseAdapter,
        get_connection: Callable[[], Any],
        normalize_sql: Callable[[str], str],
        execute_with_logging: Callable[[Any, str, tuple], Any]
    ):
        """
        Initialize SchemaManager.
        
        Args:
            db_type: Database type ('sqlite' or 'postgresql')
            adapter: Database adapter instance
            get_connection: Function to get database connection
            normalize_sql: Function to normalize SQL queries
            execute_with_logging: Function to execute queries with logging
        """
        self.db_type = db_type
        self.adapter = adapter
        self._get_connection = get_connection
        self._normalize_sql = normalize_sql
        self._execute_with_logging = execute_with_logging
    
    def initialize_schema(self):
        """
        Initialize the complete database schema.
        
        This method orchestrates the creation of all tables, indexes, and
        full-text search setup. It delegates to specialized methods for
        each logical group of tables.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Create core tables (order matters due to foreign keys)
            self._create_organizations_schema(cursor)
            self._create_projects_schema(cursor)
            self._create_tasks_schema(cursor)
            self._create_relationships_schema(cursor)
            self._create_change_history_schema(cursor)
            self._create_tags_schema(cursor)
            self._create_templates_schema(cursor)
            self._create_webhooks_schema(cursor)
            self._create_versions_schema(cursor)
            self._create_attachments_schema(cursor)
            self._create_comments_schema(cursor)
            self._create_api_keys_schema(cursor)
            self._create_blocked_agents_schema(cursor)
            self._create_audit_logs_schema(cursor)
            self._create_users_schema(cursor)
            self._create_recurring_tasks_schema(cursor)
            self._create_agent_experiences_schema(cursor)
            self._create_multi_tenancy_schema(cursor)
            
            # Create indexes
            self._create_indexes(cursor)
            
            # Setup full-text search
            self._setup_fulltext_search(cursor)
            
            conn.commit()
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            self.adapter.close(conn)
    
    def _create_organizations_schema(self, cursor):
        """Create organizations table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_projects_schema(self, cursor):
        """Create projects table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                origin_url TEXT,
                local_path TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
        # Note: organization_id added via Alembic migrations
    
    def _create_tasks_schema(self, cursor):
        """Create tasks table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT NOT NULL,
                task_type TEXT NOT NULL CHECK(task_type IN ('concrete', 'abstract', 'epic')),
                task_instruction TEXT NOT NULL,
                verification_instruction TEXT NOT NULL,
                task_status TEXT NOT NULL DEFAULT 'available' 
                    CHECK(task_status IN ('available', 'in_progress', 'complete', 'blocked', 'cancelled')),
                verification_status TEXT NOT NULL DEFAULT 'unverified'
                    CHECK(verification_status IN ('unverified', 'verified')),
                assigned_agent TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            )
        """)
        self._execute_with_logging(cursor, query)
        # Note: Additional columns (priority, due_date, etc.) added via Alembic migrations
    
    def _create_relationships_schema(self, cursor):
        """Create task relationships table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS task_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_task_id INTEGER NOT NULL,
                child_task_id INTEGER NOT NULL,
                relationship_type TEXT NOT NULL
                    CHECK(relationship_type IN ('subtask', 'blocking', 'blocked_by', 'followup', 'related')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (child_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                UNIQUE(parent_task_id, child_task_id, relationship_type)
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_change_history_schema(self, cursor):
        """
        Create change history table with migration support for SQLite.
        
        SQLite doesn't support ALTER TABLE to modify CHECK constraints,
        so we need to recreate the table if the constraint needs updating.
        """
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS change_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                change_type TEXT NOT NULL
                    CHECK(change_type IN ('created', 'locked', 'unlocked', 'updated', 'completed', 'verified', 'status_changed', 'relationship_added', 'progress', 'note', 'blocker', 'question', 'finding')),
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # Migration: Fix change_history CHECK constraint if it doesn't include update types
        if self.db_type == "sqlite":
            self._migrate_change_history_constraint(cursor)
    
    def _migrate_change_history_constraint(self, cursor):
        """
        Migrate change_history table to support update types (progress, note, blocker, question, finding).
        
        This is needed for SQLite databases that were created before these change types were added.
        """
        try:
            # Test if the constraint allows 'progress' type by checking the schema
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='change_history'")
            schema_row = cursor.fetchone()
            if schema_row and schema_row[0] and "'progress'" not in schema_row[0]:
                # Table exists but doesn't have the new constraint - need to migrate
                raise sqlite3.IntegrityError("Migration needed")
            
            # Test by trying to insert (table might have been created with old constraint)
            cursor.execute("""
                INSERT INTO change_history (task_id, agent_id, change_type, notes)
                VALUES (-1, 'test', 'progress', 'test')
            """)
            cursor.execute("DELETE FROM change_history WHERE task_id = -1")
        except sqlite3.IntegrityError:
            # Constraint doesn't allow 'progress', need to migrate
            logger.info("Migrating change_history table to support update types (progress, note, blocker, question, finding)")
            
            # Backup existing data
            cursor.execute("SELECT * FROM change_history")
            old_data = cursor.fetchall()
            
            # Drop indexes first
            cursor.execute("DROP INDEX IF EXISTS idx_change_history_task")
            cursor.execute("DROP INDEX IF EXISTS idx_change_history_agent")
            cursor.execute("DROP INDEX IF EXISTS idx_change_history_created")
            
            # Drop old table (this auto-commits in SQLite)
            cursor.execute("DROP TABLE change_history")
            
            # Recreate with updated constraint
            query = self._normalize_sql("""
                CREATE TABLE change_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    agent_id TEXT NOT NULL,
                    change_type TEXT NOT NULL
                        CHECK(change_type IN ('created', 'locked', 'unlocked', 'updated', 'completed', 'verified', 'status_changed', 'relationship_added', 'progress', 'note', 'blocker', 'question', 'finding')),
                    field_name TEXT,
                    old_value TEXT,
                    new_value TEXT,
                    notes TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                )
            """)
            self._execute_with_logging(cursor, query)
            
            # Recreate indexes
            self._execute_with_logging(cursor, "CREATE INDEX IF NOT EXISTS idx_change_history_task ON change_history(task_id)")
            self._execute_with_logging(cursor, "CREATE INDEX IF NOT EXISTS idx_change_history_agent ON change_history(agent_id)")
            self._execute_with_logging(cursor, "CREATE INDEX IF NOT EXISTS idx_change_history_created ON change_history(created_at)")
            
            # Restore data (skip rows that would violate new constraint - shouldn't be any)
            if old_data:
                cursor.executemany("""
                    INSERT INTO change_history (id, task_id, agent_id, change_type, field_name, old_value, new_value, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, old_data)
                # Reset sequence to avoid ID conflicts
                max_id = max(row[0] for row in old_data if row[0] is not None)
                cursor.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'change_history'", (max_id,))
            
            logger.info(f"Migrated change_history table, restored {len(old_data)} rows")
        except Exception as e:
            if "Migration needed" not in str(e):
                logger.error(f"Error during change_history migration: {e}", exc_info=True)
                raise
    
    def _create_tags_schema(self, cursor):
        """Create tags and task_tags tables."""
        # Tags table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # Task tags junction table (many-to-many)
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS task_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                UNIQUE(task_id, tag_id)
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_templates_schema(self, cursor):
        """Create task templates table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS task_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                task_type TEXT NOT NULL CHECK(task_type IN ('concrete', 'abstract', 'epic')),
                task_instruction TEXT NOT NULL,
                verification_instruction TEXT NOT NULL,
                priority TEXT DEFAULT 'medium' 
                    CHECK(priority IN ('low', 'medium', 'high', 'critical')),
                estimated_hours REAL,
                notes TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_webhooks_schema(self, cursor):
        """Create webhooks and webhook_deliveries tables."""
        # Webhooks table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                events TEXT NOT NULL,
                secret TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                retry_count INTEGER NOT NULL DEFAULT 3,
                timeout_seconds INTEGER NOT NULL DEFAULT 10,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # Webhook delivery history table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'success', 'failed')),
                response_code INTEGER,
                response_body TEXT,
                attempt_number INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                delivered_at TIMESTAMP,
                FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_versions_schema(self, cursor):
        """Create task versions table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS task_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                version_number INTEGER NOT NULL,
                title TEXT,
                task_type TEXT,
                task_instruction TEXT,
                verification_instruction TEXT,
                task_status TEXT,
                verification_status TEXT,
                priority TEXT,
                assigned_agent TEXT,
                notes TEXT,
                estimated_hours REAL,
                actual_hours REAL,
                time_delta_hours REAL,
                due_date TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                UNIQUE(task_id, version_number)
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_attachments_schema(self, cursor):
        """Create file attachments table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS file_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                description TEXT,
                uploaded_by TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_comments_schema(self, cursor):
        """Create task comments table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                agent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                parent_comment_id INTEGER,
                mentions TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_comment_id) REFERENCES task_comments(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_api_keys_schema(self, cursor):
        """Create API keys table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
        # Note: is_admin and organization_id added via Alembic migrations
    
    def _create_blocked_agents_schema(self, cursor):
        """Create blocked agents table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS blocked_agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL UNIQUE,
                reason TEXT,
                blocked_by TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                unblocked_at TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_audit_logs_schema(self, cursor):
        """Create audit logs table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                actor TEXT NOT NULL,
                actor_type TEXT NOT NULL CHECK(actor_type IN ('api_key', 'user', 'system')),
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_users_schema(self, cursor):
        """Create users and user_sessions tables."""
        # Users table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_login_at TIMESTAMP
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # User sessions table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_recurring_tasks_schema(self, cursor):
        """Create recurring tasks table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS recurring_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                recurrence_type TEXT NOT NULL CHECK(recurrence_type IN ('daily', 'weekly', 'monthly')),
                recurrence_config TEXT NOT NULL,
                next_occurrence TIMESTAMP NOT NULL,
                last_occurrence_created TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_agent_experiences_schema(self, cursor):
        """Create agent experiences table."""
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS agent_experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                task_id INTEGER,
                outcome TEXT NOT NULL CHECK(outcome IN ('success', 'failure', 'partial')),
                execution_time_hours REAL,
                failure_reason TEXT,
                strategy_used TEXT,
                notes TEXT,
                metadata TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_multi_tenancy_schema(self, cursor):
        """
        Create multi-tenancy tables (teams, roles, organization_members, team_members).
        
        Note: organizations table is created separately in _create_organizations_schema
        to ensure it's created before projects/tasks that reference it.
        """
        # Teams table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # Roles table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER,
                name TEXT NOT NULL,
                permissions TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # Organization members table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS organization_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role_id INTEGER,
                joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL,
                UNIQUE(organization_id, user_id)
            )
        """)
        self._execute_with_logging(cursor, query)
        
        # Team members table
        query = self._normalize_sql("""
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role_id INTEGER,
                joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET NULL,
                UNIQUE(team_id, user_id)
            )
        """)
        self._execute_with_logging(cursor, query)
    
    def _create_indexes(self, cursor):
        """Create all database indexes for performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(task_status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_agent)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)",
            # Note: idx_tasks_priority, idx_tasks_due_date created by Alembic migrations
            "CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)",
            "CREATE INDEX IF NOT EXISTS idx_relationships_parent ON task_relationships(parent_task_id)",
            "CREATE INDEX IF NOT EXISTS idx_relationships_child ON task_relationships(child_task_id)",
            "CREATE INDEX IF NOT EXISTS idx_change_history_task ON change_history(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_change_history_agent ON change_history(agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_change_history_created ON change_history(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_task_versions_task ON task_versions(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_versions_number ON task_versions(task_id, version_number)",
            "CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)",
            "CREATE INDEX IF NOT EXISTS idx_task_tags_task ON task_tags(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_tags_tag ON task_tags(tag_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_templates_name ON task_templates(name)",
            "CREATE INDEX IF NOT EXISTS idx_task_templates_type ON task_templates(task_type)",
            "CREATE INDEX IF NOT EXISTS idx_webhooks_project ON webhooks(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_webhooks_enabled ON webhooks(enabled)",
            "CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id)",
            "CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status)",
            "CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created ON webhook_deliveries(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_file_attachments_task ON file_attachments(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_file_attachments_created ON file_attachments(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_comments_parent ON task_comments(parent_comment_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_comments_agent ON task_comments(agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_comments_created ON task_comments(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)",
            "CREATE INDEX IF NOT EXISTS idx_api_keys_enabled ON api_keys(enabled)",
            # Note: idx_api_keys_admin, idx_api_keys_organization created by Alembic migrations
            "CREATE INDEX IF NOT EXISTS idx_blocked_agents_agent_id ON blocked_agents(agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor)",
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)",
            "CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)",
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_recurring_tasks_task ON recurring_tasks(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_recurring_tasks_next ON recurring_tasks(next_occurrence)",
            "CREATE INDEX IF NOT EXISTS idx_recurring_tasks_active ON recurring_tasks(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_agent_experiences_agent ON agent_experiences(agent_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_experiences_task ON agent_experiences(task_id)",
            "CREATE INDEX IF NOT EXISTS idx_agent_experiences_outcome ON agent_experiences(outcome)",
            "CREATE INDEX IF NOT EXISTS idx_agent_experiences_created ON agent_experiences(created_at)",
            # Composite indexes
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_type ON tasks(task_status, task_type)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, task_status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_project_status_type ON tasks(project_id, task_status, task_type)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(task_status, priority)",
            "CREATE INDEX IF NOT EXISTS idx_relationships_parent_type ON task_relationships(parent_task_id, relationship_type)",
            "CREATE INDEX IF NOT EXISTS idx_relationships_child_type ON task_relationships(child_task_id, relationship_type)",
            "CREATE INDEX IF NOT EXISTS idx_task_tags_task_tag ON task_tags(task_id, tag_id)",
            # Multi-tenancy indexes
            "CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug)",
            "CREATE INDEX IF NOT EXISTS idx_teams_organization ON teams(organization_id)",
            "CREATE INDEX IF NOT EXISTS idx_roles_organization ON roles(organization_id)",
            "CREATE INDEX IF NOT EXISTS idx_organization_members_org ON organization_members(organization_id)",
            "CREATE INDEX IF NOT EXISTS idx_organization_members_user ON organization_members(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_organization_members_role ON organization_members(role_id)",
            "CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)",
            "CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_team_members_role ON team_members(role_id)",
        ]
        
        # PostgreSQL doesn't support DESC in CREATE INDEX, need separate handling
        if self.db_type == "postgresql":
            indexes.append("CREATE INDEX IF NOT EXISTS idx_tasks_created_status ON tasks(created_at DESC, task_status)")
        else:
            indexes.append("CREATE INDEX IF NOT EXISTS idx_tasks_created_status ON tasks(created_at DESC, task_status)")
        
        for index_query in indexes:
            self._execute_with_logging(cursor, index_query)
    
    def _setup_fulltext_search(self, cursor):
        """Setup full-text search for tasks."""
        if self.db_type == "sqlite":
            # FTS5 virtual table for SQLite
            try:
                self._execute_with_logging(cursor, """
                    CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
                        title,
                        task_instruction,
                        notes,
                        content='tasks',
                        content_rowid='id'
                    )
                """)
                # Rebuild FTS5 index if needed
                try:
                    self._execute_with_logging(cursor, "SELECT COUNT(*) FROM tasks_fts")
                    count = cursor.fetchone()[0] if hasattr(cursor.fetchone(), '__getitem__') else cursor.fetchone()['count']
                    if count == 0:
                        self._execute_with_logging(cursor, "SELECT COUNT(*) FROM tasks")
                        task_count = cursor.fetchone()[0] if hasattr(cursor.fetchone(), '__getitem__') else cursor.fetchone()['count']
                        if task_count > 0:
                            self._execute_with_logging(cursor, "INSERT INTO tasks_fts(tasks_fts) VALUES('rebuild')")
                except Exception:
                    pass
            except Exception:
                logger.warning("FTS5 not available, full-text search will use fallback")
        else:
            # PostgreSQL full-text search
            if self.adapter.supports_fulltext_search():
                self.adapter.create_fulltext_index(cursor, "tasks", ["title", "task_instruction", "notes"])
