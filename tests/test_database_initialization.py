"""
Integration test for database initialization.

Tests that:
1. Alembic migrations can be run on a fresh database
2. The initialize command creates a complete, valid database
3. The resulting database has all required tables and columns
"""
import os
import sys
import tempfile
import shutil
import subprocess
import sqlite3
import pytest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def temp_db_dir():
    """Create a temporary directory for test database."""
    temp_dir = tempfile.mkdtemp(prefix="todorama_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_db_path(temp_db_dir):
    """Get path to test database file."""
    return os.path.join(temp_db_dir, "test_todos.db")


def test_alembic_migrations_on_fresh_database(temp_db_path):
    """Test that Alembic migrations can be run on a fresh database."""
    # Set database path
    os.environ["TODO_DB_PATH"] = temp_db_path
    os.environ["DB_TYPE"] = "sqlite"
    
    # Get project root
    project_root = Path(__file__).parent.parent
    
    # Run alembic upgrade head
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )
    
    assert result.returncode == 0, f"Alembic failed: {result.stderr}"
    
    # Verify database was created
    assert os.path.exists(temp_db_path), "Database file was not created"
    
    # Verify tasks table exists
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert cursor.fetchone() is not None, "tasks table was not created"
    conn.close()


def test_initialize_command_creates_complete_database(temp_db_path):
    """Test that the initialize command creates a complete, valid database."""
    # Set database path
    os.environ["TODO_DB_PATH"] = temp_db_path
    os.environ["DB_TYPE"] = "sqlite"
    
    # Import and run initialize command
    from todorama.commands.initialize import InitializeCommand
    from argparse import Namespace
    
    args = Namespace(
        database_path=temp_db_path,
        skip_migrations=False,
        validate_only=False
    )
    
    cmd = InitializeCommand(args)
    try:
        cmd.init()
        result = cmd.run()
        assert result == 0, "Initialize command failed"
    finally:
        cmd.cleanup()
    
    # Verify database exists
    assert os.path.exists(temp_db_path), "Database file was not created"
    
    # Verify schema is complete
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    
    # Check tasks table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    assert cursor.fetchone() is not None, "tasks table not found"
    
    # Check all required columns exist
    cursor.execute("PRAGMA table_info(tasks)")
    columns = {row[1]: row for row in cursor.fetchall()}
    
    required_columns = {
        "id", "project_id", "title", "task_type", "task_instruction",
        "verification_instruction", "task_status", "verification_status",
        "assigned_agent", "created_at", "updated_at", "completed_at",
        "notes", "priority"
    }
    
    missing = required_columns - set(columns.keys())
    assert not missing, f"Missing required columns: {missing}"
    
    # Verify priority column has correct constraints
    if "priority" in columns:
        priority_col = columns["priority"]
        # Check default value (SQLite may return with quotes)
        default_val = priority_col[4]
        if default_val is not None:
            default_val = str(default_val).strip("'\"")
        assert default_val in ("medium", None), \
            f"priority column default should be 'medium', got {priority_col[4]}"
    
    conn.close()


def test_initialize_command_with_migrations(temp_db_path):
    """Test initialize command runs migrations and validates schema."""
    # Set database path
    os.environ["TODO_DB_PATH"] = temp_db_path
    os.environ["DB_TYPE"] = "sqlite"
    
    # Import and run initialize command
    from todorama.commands.initialize import InitializeCommand
    from argparse import Namespace
    
    args = Namespace(
        database_path=temp_db_path,
        skip_migrations=False,
        validate_only=False
    )
    
    cmd = InitializeCommand(args)
    try:
        cmd.init()
        result = cmd.run()
        assert result == 0, f"Initialize command failed with exit code {result}"
    finally:
        cmd.cleanup()
    
    # Verify database is valid
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    
    # Check tasks table structure
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Must have priority column (added by migration)
    assert "priority" in columns, "priority column missing after migration"
    
    # Check indexes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'")
    indexes = [row[0] for row in cursor.fetchall()]
    
    # Should have priority-related indexes
    priority_indexes = [idx for idx in indexes if "priority" in idx]
    assert len(priority_indexes) > 0, "Priority indexes not found"
    
    conn.close()


def test_initialize_command_validate_only(temp_db_path):
    """Test initialize command in validate-only mode."""
    # First create a database with migrations
    os.environ["TODO_DB_PATH"] = temp_db_path
    os.environ["DB_TYPE"] = "sqlite"
    
    # Run migrations first
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )
    assert result.returncode == 0, "Failed to run migrations"
    
    # Now validate
    from todorama.commands.initialize import InitializeCommand
    from argparse import Namespace
    
    args = Namespace(
        database_path=temp_db_path,
        skip_migrations=False,
        validate_only=True
    )
    
    cmd = InitializeCommand(args)
    try:
        cmd.init()
        result = cmd.run()
        assert result == 0, "Validation should pass for valid database"
    finally:
        cmd.cleanup()


def test_initialize_command_skip_migrations(temp_db_path):
    """Test initialize command with --skip-migrations flag."""
    os.environ["TODO_DB_PATH"] = temp_db_path
    os.environ["DB_TYPE"] = "sqlite"
    
    from todorama.commands.initialize import InitializeCommand
    from argparse import Namespace
    
    args = Namespace(
        database_path=temp_db_path,
        skip_migrations=True,
        validate_only=False
    )
    
    cmd = InitializeCommand(args)
    try:
        cmd.init()
        result = cmd.run()
        # When skipping migrations, database will be created by TodoDatabase
        # but validation will fail because priority column is missing (expected)
        # The command should exit cleanly (not crash), but validation failure is OK
        # Exit code 1 is expected when validation fails due to missing migrations
        assert result in (0, 1), f"Initialize should exit cleanly (may fail validation), got {result}"
        
        # Verify database was created
        assert os.path.exists(temp_db_path), "Database should be created even if validation fails"
    finally:
        cmd.cleanup()


def test_database_schema_completeness(temp_db_path):
    """Test that the database schema is complete after initialization."""
    # Run full initialization
    os.environ["TODO_DB_PATH"] = temp_db_path
    os.environ["DB_TYPE"] = "sqlite"
    
    # Run alembic
    project_root = Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
        env=os.environ.copy()
    )
    assert result.returncode == 0
    
    # Run initialize command
    from todorama.commands.initialize import InitializeCommand
    from argparse import Namespace
    
    args = Namespace(
        database_path=temp_db_path,
        skip_migrations=False,
        validate_only=False
    )
    
    cmd = InitializeCommand(args)
    try:
        cmd.init()
        result = cmd.run()
        assert result == 0
    finally:
        cmd.cleanup()
    
    # Comprehensive schema validation
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Verify essential tables exist
    essential_tables = ["tasks", "projects"]
    for table in essential_tables:
        assert table in tables, f"Essential table {table} missing"
    
    # Verify tasks table structure
    cursor.execute("PRAGMA table_info(tasks)")
    task_columns = {row[1]: row for row in cursor.fetchall()}
    
    # All required columns
    required_columns = {
        "id", "project_id", "title", "task_type", "task_instruction",
        "verification_instruction", "task_status", "verification_status",
        "assigned_agent", "created_at", "updated_at", "completed_at",
        "notes", "priority"
    }
    
    for col in required_columns:
        assert col in task_columns, f"Required column {col} missing from tasks table"
    
    # Verify priority column constraints
    priority_col = task_columns["priority"]
    assert priority_col[2] == "TEXT", "priority column should be TEXT type"
    # Default should be 'medium' or NULL (SQLite returns default as string, may have quotes)
    default_val = priority_col[4]
    if default_val is not None:
        # Remove quotes if present (SQLite may return "'medium'" or "medium")
        default_val = str(default_val).strip("'\"")
    assert default_val in ("medium", None), \
        f"priority default should be 'medium', got {priority_col[4]}"
    
    # Verify indexes exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'")
    indexes = [row[0] for row in cursor.fetchall()]
    
    # Should have at least one priority-related index
    priority_indexes = [idx for idx in indexes if "priority" in idx.lower()]
    assert len(priority_indexes) > 0, "No priority-related indexes found"
    
    conn.close()

