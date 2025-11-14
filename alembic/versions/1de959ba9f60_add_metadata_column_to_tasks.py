"""add_metadata_column_to_tasks

Revision ID: 1de959ba9f60
Revises: 951e5f2c4fd7
Create Date: 2025-11-12 09:10:31.734340

Add metadata column to tasks table (for storing GitHub URLs and other metadata).
This migration is conditional - it checks if the column exists before adding it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '1de959ba9f60'
down_revision: Union[str, Sequence[str], None] = '951e5f2c4fd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add metadata column to tasks table if it doesn't exist."""
    conn = op.get_bind()
    
    if not _column_exists(conn, 'tasks', 'metadata'):
        op.execute("ALTER TABLE tasks ADD COLUMN metadata TEXT")


def downgrade() -> None:
    """Remove metadata column from tasks table."""
    # Note: SQLite doesn't support DROP COLUMN directly
    # Column removal would require table recreation
    pass
