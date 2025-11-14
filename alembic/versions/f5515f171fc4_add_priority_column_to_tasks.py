"""add_priority_column_to_tasks

Revision ID: f5515f171fc4
Revises: 4b83d51c1d35
Create Date: 2025-11-12 09:10:29.614249

Add priority column to tasks table.
This migration is conditional - it checks if the column exists before adding it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'f5515f171fc4'
down_revision: Union[str, Sequence[str], None] = '4b83d51c1d35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add priority column to tasks table if it doesn't exist."""
    conn = op.get_bind()
    
    if not _column_exists(conn, 'tasks', 'priority'):
        # SQLite
        if conn.dialect.name == 'sqlite':
            op.execute("""
                ALTER TABLE tasks 
                ADD COLUMN priority TEXT DEFAULT 'medium' 
                CHECK(priority IN ('low', 'medium', 'high', 'critical'))
            """)
        else:
            # PostgreSQL
            op.execute("ALTER TABLE tasks ADD COLUMN priority TEXT DEFAULT 'medium'")
            op.execute("""
                ALTER TABLE tasks 
                ADD CONSTRAINT tasks_priority_check 
                CHECK(priority IN ('low', 'medium', 'high', 'critical'))
            """)
        
        # Update existing tasks to have medium priority
        op.execute("UPDATE tasks SET priority = 'medium' WHERE priority IS NULL")
        
        # Create index
        op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)")
        op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(task_status, priority)")


def downgrade() -> None:
    """Remove priority column from tasks table."""
    # Note: SQLite doesn't support DROP COLUMN directly
    # This would require recreating the table, which is complex
    # For now, we'll leave the column but document that downgrade is not fully supported
    op.execute("DROP INDEX IF EXISTS idx_tasks_status_priority")
    op.execute("DROP INDEX IF EXISTS idx_tasks_priority")
    # Column removal would require table recreation in SQLite
