"""add_due_date_column_to_tasks

Revision ID: 951e5f2c4fd7
Revises: b0e1f6bbbfc9
Create Date: 2025-11-12 09:10:30.845260

Add due_date column to tasks table.
This migration is conditional - it checks if the column exists before adding it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '951e5f2c4fd7'
down_revision: Union[str, Sequence[str], None] = 'b0e1f6bbbfc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add due_date column to tasks table if it doesn't exist."""
    conn = op.get_bind()
    
    if not _column_exists(conn, 'tasks', 'due_date'):
        op.execute("ALTER TABLE tasks ADD COLUMN due_date TIMESTAMP")
        # Add index for due_date queries
        op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date)")


def downgrade() -> None:
    """Remove due_date column from tasks table."""
    op.execute("DROP INDEX IF EXISTS idx_tasks_due_date")
    # Note: SQLite doesn't support DROP COLUMN directly
    # Column removal would require table recreation
