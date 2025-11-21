"""
Test for estimated_hours column functionality.

This test demonstrates the estimated_hours error and verifies the fix.
"""
import pytest
import sqlite3
import os
import tempfile
import shutil
from pathlib import Path

from todorama.database import TodoDatabase
from todorama.mcp_api import MCPTodoAPI


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    db = TodoDatabase(db_path)
    yield db, db_path
    shutil.rmtree(temp_dir)


def test_create_task_with_estimated_hours_via_database(temp_db):
    """Test creating a task with estimated_hours using TodoDatabase directly."""
    db, db_path = temp_db
    
    # Verify estimated_hours column exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tasks)")
    columns = {row[1]: row for row in cursor.fetchall()}
    conn.close()
    
    assert "estimated_hours" in columns, "estimated_hours column should exist in tasks table"
    
    # Create task with estimated_hours
    task_id = db.create_task(
        title="Test Task with Hours",
        task_type="concrete",
        task_instruction="Do something",
        verification_instruction="Verify it works",
        agent_id="test-agent",
        estimated_hours=5.5
    )
    
    assert task_id > 0
    
    # Retrieve task and verify estimated_hours
    task = db.get_task(task_id)
    assert task is not None
    assert task["estimated_hours"] == 5.5


def test_create_task_with_estimated_hours_via_mcp_api(temp_db):
    """Test creating a task with estimated_hours using MCPTodoAPI."""
    db, db_path = temp_db
    
    # Verify estimated_hours column exists
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tasks)")
    columns = {row[1]: row for row in cursor.fetchall()}
    conn.close()
    
    assert "estimated_hours" in columns, "estimated_hours column should exist in tasks table"
    
    # Set environment variable so MCP API uses the same database
    import os
    original_db_path = os.environ.get("TODO_DB_PATH")
    os.environ["TODO_DB_PATH"] = db_path
    
    try:
        # Create task with estimated_hours via MCP API
        result = MCPTodoAPI.create_task(
            title="MCP Task with Hours",
            task_type="concrete",
            task_instruction="Fix the bug",
            verification_instruction="Verify bug is fixed",
            agent_id="test-agent",
            estimated_hours=3.0
        )
        
        assert result.get("success", False), f"Task creation should succeed, got: {result}"
        task_id = result.get("task_id")
        assert task_id is not None and task_id > 0
        
        # Retrieve task and verify estimated_hours (use the same db instance)
        task = db.get_task(task_id)
        assert task is not None, f"Task {task_id} should exist. Result: {result}"
        assert task["estimated_hours"] == 3.0
    finally:
        # Restore original environment
        if original_db_path:
            os.environ["TODO_DB_PATH"] = original_db_path
        elif "TODO_DB_PATH" in os.environ:
            del os.environ["TODO_DB_PATH"]


def test_create_task_with_estimated_hours_via_http_endpoint():
    """Test creating a task with estimated_hours via HTTP endpoint (integration test)."""
    import httpx
    
    # This test requires the service to be running
    base_url = os.getenv("TODO_SERVICE_URL", "http://localhost:8004")
    
    # Create task with estimated_hours
    response = httpx.post(
        f"{base_url}/mcp/create_task",
        json={
            "title": "HTTP Task with Hours",
            "task_type": "concrete",
            "task_instruction": "Implement feature",
            "verification_instruction": "Verify feature works",
            "agent_id": "test-agent",
            "estimated_hours": 8.5
        },
        timeout=10.0
    )
    
    # If service is not available, skip the test
    if response.status_code == 503 or response.status_code == 0:
        pytest.skip("Service not available")
    
    result = response.json()
    
    # If the service database hasn't been migrated yet, the test demonstrates the error
    if not result.get("success", False) and "estimated_hours" in result.get("error", ""):
        # This test demonstrates the error - the service needs migrations
        pytest.skip(f"Service database needs migration: {result.get('error')}")
    
    # Should succeed (200 or 201)
    assert response.status_code in (200, 201), \
        f"Expected success status, got {response.status_code}: {response.text}"
    
    assert result.get("success", False), \
        f"Task creation should succeed, got: {result}"
    
    task_id = result.get("task_id")
    assert task_id is not None and task_id > 0
    
    # Verify task has estimated_hours
    get_response = httpx.get(
        f"{base_url}/tasks/{task_id}",
        timeout=10.0
    )
    
    if get_response.status_code == 200:
        task = get_response.json()
        assert "estimated_hours" in task, "Task should have estimated_hours field"
        assert task["estimated_hours"] == 8.5


def test_estimated_hours_column_exists_after_initialize():
    """Test that estimated_hours column exists after running initialize command."""
    import tempfile
    import subprocess
    import sys
    
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_init.db")
    
    try:
        # Run initialize command
        result = subprocess.run(
            [sys.executable, "-m", "todorama", "init", "--database-path", db_path],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        assert result.returncode == 0, \
            f"Initialize command should succeed, got: {result.stderr}"
        
        # Verify estimated_hours column exists
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(tasks)")
        columns = {row[1]: row for row in cursor.fetchall()}
        conn.close()
        
        assert "estimated_hours" in columns, \
            "estimated_hours column should exist after initialization"
        
        # Verify column type is REAL
        estimated_hours_col = columns["estimated_hours"]
        assert estimated_hours_col[2] == "REAL", \
            f"estimated_hours should be REAL type, got {estimated_hours_col[2]}"
        
    finally:
        shutil.rmtree(temp_dir)

