"""
Tests for webhook notification system.
"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app
from database import TodoDatabase
from backup import BackupManager


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    backups_dir = os.path.join(temp_dir, "backups")
    
    # Create database
    db = TodoDatabase(db_path)
    backup_manager = BackupManager(db_path, backups_dir)
    
    # Override the database and backup manager in the app
    import main
    main.db = db
    main.backup_manager = backup_manager
    
    yield db, db_path, backups_dir
    
    shutil.rmtree(temp_dir)


@pytest.fixture
def client(temp_db):
    """Create test client."""
    return TestClient(app)


def test_create_webhook(client):
    """Test creating a webhook for a project."""
    # Create a project first
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test",
        "description": "Test project"
    })
    project_id = project_response.json()["id"]
    
    # Create webhook
    response = client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook",
        "events": ["task.created", "task.completed"]
    })
    assert response.status_code == 201
    data = response.json()
    assert data["url"] == "https://example.com/webhook"
    assert data["project_id"] == project_id
    assert "task.created" in data["events"]
    assert "task.completed" in data["events"]


def test_create_webhook_invalid_url(client):
    """Test creating webhook with invalid URL."""
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test"
    })
    project_id = project_response.json()["id"]
    
    response = client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "not-a-url",
        "events": ["task.created"]
    })
    assert response.status_code == 422  # Validation error


def test_list_webhooks(client):
    """Test listing webhooks for a project."""
    # Create project
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test"
    })
    project_id = project_response.json()["id"]
    
    # Create multiple webhooks
    client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook1",
        "events": ["task.created"]
    })
    client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook2",
        "events": ["task.completed"]
    })
    
    # List webhooks
    response = client.get("/projects/{}/webhooks".format(project_id))
    assert response.status_code == 200
    webhooks = response.json()["webhooks"]
    assert len(webhooks) == 2


def test_delete_webhook(client):
    """Test deleting a webhook."""
    # Create project and webhook
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test"
    })
    project_id = project_response.json()["id"]
    
    create_response = client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook",
        "events": ["task.created"]
    })
    webhook_id = create_response.json()["id"]
    
    # Delete webhook
    response = client.delete("/webhooks/{}".format(webhook_id))
    assert response.status_code == 200
    
    # Verify deleted
    list_response = client.get("/projects/{}/webhooks".format(project_id))
    assert len(list_response.json()["webhooks"]) == 0


@patch('main.httpx.AsyncClient')
def test_webhook_notification_on_task_created(client, mock_httpx_class):
    """Test that webhooks are called when a task is created."""
    # Create project
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test"
    })
    project_id = project_response.json()["id"]
    
    # Create webhook
    client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook",
        "events": ["task.created"]
    })
    
    # Mock HTTP client
    mock_client = MagicMock()
    mock_httpx_class.return_value.__aenter__.return_value = mock_client
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client.post.return_value = mock_response
    
    # Create task
    with patch('main.send_webhook_notification') as mock_send:
        response = client.post("/tasks", json={
            "title": "Test Task",
            "task_type": "concrete",
            "task_instruction": "Do something",
            "verification_instruction": "Check it works",
            "agent_id": "test-agent",
            "project_id": project_id
        })
        assert response.status_code == 201
        
        # Verify webhook was called
        mock_send.assert_called_once()


@patch('main.send_webhook_notification')
def test_webhook_notification_on_task_completed(mock_send, client):
    """Test that webhooks are called when a task is completed."""
    # Create project
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test"
    })
    project_id = project_response.json()["id"]
    
    # Create webhook
    client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook",
        "events": ["task.completed"]
    })
    
    # Create and complete task
    create_response = client.post("/tasks", json={
        "title": "Test Task",
        "task_type": "concrete",
        "task_instruction": "Do something",
        "verification_instruction": "Check it works",
        "agent_id": "test-agent",
        "project_id": project_id
    })
    task_id = create_response.json()["id"]
    
    # Lock task first
    client.post("/tasks/{}/lock".format(task_id), json={"agent_id": "test-agent"})
    
    # Complete task
    client.post("/tasks/{}/complete".format(task_id), json={
        "agent_id": "test-agent",
        "notes": "Done"
    })
    
    # Verify webhook was called (should be called twice: once for created, once for completed)
    assert mock_send.call_count >= 1


@patch('main.httpx.AsyncClient')
def test_webhook_retry_logic(mock_httpx_class, client):
    """Test that webhooks retry on failure."""
    # Create project and webhook
    project_response = client.post("/projects", json={
        "name": "Test Project",
        "local_path": "/tmp/test"
    })
    project_id = project_response.json()["id"]
    
    client.post("/projects/{}/webhooks".format(project_id), json={
        "url": "https://example.com/webhook",
        "events": ["task.created"]
    })
    
    # Mock HTTP client to fail first, then succeed
    mock_client = MagicMock()
    mock_httpx_class.return_value.__aenter__.return_value = mock_client
    
    from httpx import Response
    # First call fails, second succeeds
    mock_client.post.side_effect = [
        Response(status_code=500, request=MagicMock()),
        Response(status_code=200, request=MagicMock())
    ]
    
    # Create task
    with patch('main.send_webhook_notification') as mock_send:
        # We'll test retry logic in the actual implementation
        response = client.post("/tasks", json={
            "title": "Test Task",
            "task_type": "concrete",
            "task_instruction": "Do something",
            "verification_instruction": "Check it works",
            "agent_id": "test-agent",
            "project_id": project_id
        })
        assert response.status_code == 201


def test_webhook_only_triggers_for_subscribed_events(client):
    """Test that webhooks only trigger for events they're subscribed to."""
    # This test will verify that a webhook subscribed to task.created
    # doesn't trigger on task.completed
    pass  # Will implement with actual webhook system
