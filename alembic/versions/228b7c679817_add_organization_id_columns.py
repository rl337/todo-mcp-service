"""add_organization_id_columns

Revision ID: 228b7c679817
Revises: 1de959ba9f60
Create Date: 2025-11-12 09:10:32.742723

Add organization_id columns to projects, tasks, and api_keys tables for multi-tenancy support.
This migration is conditional - it checks if columns exist before adding them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '228b7c679817'
down_revision: Union[str, Sequence[str], None] = '1de959ba9f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add organization_id columns to projects, tasks, and api_keys tables if they don't exist."""
    conn = op.get_bind()
    is_postgresql = conn.dialect.name == 'postgresql'
    
    # Add organization_id to projects table
    if not _column_exists(conn, 'projects', 'organization_id'):
        op.execute("ALTER TABLE projects ADD COLUMN organization_id INTEGER")
        op.execute("CREATE INDEX IF NOT EXISTS idx_projects_organization ON projects(organization_id)")
        if is_postgresql:
            try:
                op.execute("""
                    ALTER TABLE projects 
                    ADD CONSTRAINT fk_projects_organization 
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
                """)
            except Exception:
                # Constraint may already exist
                pass
    
    # Add organization_id to tasks table
    if not _column_exists(conn, 'tasks', 'organization_id'):
        op.execute("ALTER TABLE tasks ADD COLUMN organization_id INTEGER")
        op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_organization ON tasks(organization_id)")
        if is_postgresql:
            try:
                op.execute("""
                    ALTER TABLE tasks 
                    ADD CONSTRAINT fk_tasks_organization 
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE SET NULL
                """)
            except Exception:
                # Constraint may already exist
                pass
    
    # Add organization_id to api_keys table
    if not _column_exists(conn, 'api_keys', 'organization_id'):
        op.execute("ALTER TABLE api_keys ADD COLUMN organization_id INTEGER")
        op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_organization ON api_keys(organization_id)")
        if is_postgresql:
            try:
                op.execute("""
                    ALTER TABLE api_keys 
                    ADD CONSTRAINT fk_api_keys_organization 
                    FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
                """)
            except Exception:
                # Constraint may already exist
                pass


def downgrade() -> None:
    """Remove organization_id columns from projects, tasks, and api_keys tables."""
    conn = op.get_bind()
    is_postgresql = conn.dialect.name == 'postgresql'
    
    # Remove foreign key constraints (PostgreSQL only)
    if is_postgresql:
        try:
            op.execute("ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS fk_api_keys_organization")
            op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS fk_tasks_organization")
            op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS fk_projects_organization")
        except Exception:
            pass
    
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_api_keys_organization")
    op.execute("DROP INDEX IF EXISTS idx_tasks_organization")
    op.execute("DROP INDEX IF EXISTS idx_projects_organization")
    
    # Note: SQLite doesn't support DROP COLUMN directly
    # Column removal would require table recreation
