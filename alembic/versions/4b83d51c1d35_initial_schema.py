"""initial_schema

Revision ID: 4b83d51c1d35
Revises: 
Create Date: 2025-11-12 09:08:24.541318

Initial schema migration for todorama.
This migration creates all tables with their current structure including
all columns that were added via historical ad-hoc migrations.

Note: This represents the current state of the schema. Historical migrations
for individual column additions are created as separate migration scripts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b83d51c1d35'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create all tables with current structure."""
    # Organizations table (must be created before projects/tasks that reference it)
    op.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug)")
    
    # Projects table (base schema - organization_id added in later migration)
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)")
    
    # Tasks table (base schema - migrated columns added in later migrations)
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(task_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_agent)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_type ON tasks(task_status, task_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, task_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_status_type ON tasks(project_id, task_status, task_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_status ON tasks(created_at DESC, task_status)")
    
    # Task relationships table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_relationships_parent ON task_relationships(parent_task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_relationships_child ON task_relationships(child_task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_relationships_parent_type ON task_relationships(parent_task_id, relationship_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_relationships_child_type ON task_relationships(child_task_id, relationship_type)")
    
    # Change history table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_history_task ON change_history(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_history_agent ON change_history(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_change_history_created ON change_history(created_at)")
    
    # Tags table
    op.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
    
    # Task tags junction table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_tags_task ON task_tags(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_tags_tag ON task_tags(tag_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_tags_task_tag ON task_tags(task_id, tag_id)")
    
    # Task templates table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_templates_name ON task_templates(name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_templates_type ON task_templates(task_type)")
    
    # Webhooks table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_project ON webhooks(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhooks_enabled ON webhooks(enabled)")
    
    # Webhook deliveries table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook ON webhook_deliveries(webhook_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created ON webhook_deliveries(created_at)")
    
    # Task versions table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_versions_task ON task_versions(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_versions_number ON task_versions(task_id, version_number)")
    
    # File attachments table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_file_attachments_task ON file_attachments(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_file_attachments_created ON file_attachments(created_at)")
    
    # Task comments table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_parent ON task_comments(parent_comment_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_agent ON task_comments(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_created ON task_comments(created_at)")
    
    # API keys table (base schema - is_admin and organization_id added in later migrations)
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_enabled ON api_keys(enabled)")
    
    # Blocked agents table
    op.execute("""
        CREATE TABLE IF NOT EXISTS blocked_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL UNIQUE,
            reason TEXT,
            blocked_by TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            unblocked_at TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_blocked_agents_agent_id ON blocked_agents(agent_id)")
    
    # Audit logs table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_actor ON audit_logs(actor)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at)")
    
    # Users table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    
    # User sessions table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(session_token)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)")
    
    # Recurring tasks table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_task ON recurring_tasks(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_next ON recurring_tasks(next_occurrence)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_recurring_tasks_active ON recurring_tasks(is_active)")
    
    # Agent experiences table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_experiences_agent ON agent_experiences(agent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_experiences_task ON agent_experiences(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_experiences_outcome ON agent_experiences(outcome)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_experiences_created ON agent_experiences(created_at)")
    
    # Teams table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_teams_organization ON teams(organization_id)")
    
    # Roles table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_roles_organization ON roles(organization_id)")
    
    # Organization members table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_organization_members_org ON organization_members(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_organization_members_user ON organization_members(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_organization_members_role ON organization_members(role_id)")
    
    # Team members table
    op.execute("""
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
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_team ON team_members(team_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_user ON team_members(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_team_members_role ON team_members(role_id)")
    
    # Full-text search (SQLite FTS5 - PostgreSQL handled separately)
    # Note: FTS5 virtual tables are SQLite-specific
    try:
        op.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS tasks_fts USING fts5(
                title,
                task_instruction,
                notes,
                content='tasks',
                content_rowid='id'
            )
        """)
    except Exception:
        # FTS5 may not be available or may already exist
        pass


def downgrade() -> None:
    """Downgrade schema - drop all tables."""
    # Drop in reverse order of dependencies
    op.execute("DROP TABLE IF EXISTS tasks_fts")
    op.execute("DROP TABLE IF EXISTS team_members")
    op.execute("DROP TABLE IF EXISTS organization_members")
    op.execute("DROP TABLE IF EXISTS roles")
    op.execute("DROP TABLE IF EXISTS teams")
    op.execute("DROP TABLE IF EXISTS organizations")
    op.execute("DROP TABLE IF EXISTS agent_experiences")
    op.execute("DROP TABLE IF EXISTS recurring_tasks")
    op.execute("DROP TABLE IF EXISTS user_sessions")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS blocked_agents")
    op.execute("DROP TABLE IF EXISTS api_keys")
    op.execute("DROP TABLE IF EXISTS task_comments")
    op.execute("DROP TABLE IF EXISTS file_attachments")
    op.execute("DROP TABLE IF EXISTS task_versions")
    op.execute("DROP TABLE IF EXISTS webhook_deliveries")
    op.execute("DROP TABLE IF EXISTS webhooks")
    op.execute("DROP TABLE IF EXISTS task_templates")
    op.execute("DROP TABLE IF EXISTS task_tags")
    op.execute("DROP TABLE IF EXISTS tags")
    op.execute("DROP TABLE IF EXISTS change_history")
    op.execute("DROP TABLE IF EXISTS task_relationships")
    op.execute("DROP TABLE IF EXISTS tasks")
    op.execute("DROP TABLE IF EXISTS projects")
