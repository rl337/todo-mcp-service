"""add_is_admin_column_to_api_keys

Revision ID: 87fa4b07319e
Revises: 228b7c679817
Create Date: 2025-11-12 09:10:33.656317

Add is_admin column to api_keys table.
This migration is conditional - it checks if the column exists before adding it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '87fa4b07319e'
down_revision: Union[str, Sequence[str], None] = '228b7c679817'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    """Add is_admin column to api_keys table if it doesn't exist."""
    conn = op.get_bind()
    
    if not _column_exists(conn, 'api_keys', 'is_admin'):
        op.execute("ALTER TABLE api_keys ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        # Create index
        op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_admin ON api_keys(is_admin)")


def downgrade() -> None:
    """Remove is_admin column from api_keys table."""
    op.execute("DROP INDEX IF EXISTS idx_api_keys_admin")
    # Note: SQLite doesn't support DROP COLUMN directly
    # Column removal would require table recreation
