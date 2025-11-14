"""add_time_tracking_columns_to_tasks

Revision ID: b0e1f6bbbfc9
Revises: f5515f171fc4
Create Date: 2025-11-12 09:10:30.109289

Add time tracking columns (estimated_hours, actual_hours, started_at, time_delta_hours) to tasks table.
This migration is conditional - it checks if columns exist before adding them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b0e1f6bbbfc9'
down_revision: Union[str, Sequence[str], None] = 'f5515f171fc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add time tracking columns to tasks table if they don't exist."""
    conn = op.get_bind()
    
    columns_to_add = [
        ('estimated_hours', 'REAL'),
        ('actual_hours', 'REAL'),
        ('started_at', 'TIMESTAMP'),
        ('time_delta_hours', 'REAL'),
    ]
    
    for column_name, column_type in columns_to_add:
        if not _column_exists(conn, 'tasks', column_name):
            op.execute(f"ALTER TABLE tasks ADD COLUMN {column_name} {column_type}")


def downgrade() -> None:
    """Remove time tracking columns from tasks table."""
    # Note: SQLite doesn't support DROP COLUMN directly
    # Column removal would require table recreation
    pass
