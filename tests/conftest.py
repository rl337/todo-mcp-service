"""
Pytest configuration and shared fixtures for multi-tenancy tests.
Provides helper functions and fixtures that can be used across all test files.
"""
import pytest
import tempfile
import shutil
import os
from todorama.database import TodoDatabase


def create_test_organization(db, name="Test Organization"):
    """
    Helper function to create a test organization.
    Returns organization ID, or None if organizations table doesn't exist.
    """
    conn = db._get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO organizations (name, created_at, updated_at)
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name,))
        
        if db.db_type == "postgresql":
            cursor.execute("SELECT id FROM organizations WHERE name = ?", (name,))
            org_id = cursor.fetchone()[0]
        else:
            org_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        return org_id
    except Exception:
        # Organizations table may not exist yet
        conn.close()
        return None


def create_test_project_with_org(db, org_id=None, name="Test Project", local_path="/test/path"):
    """
    Helper function to create a test project, optionally with an organization.
    If org_id is None and organizations table exists, creates a default organization.
    Returns (project_id, org_id).
    """
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Check if organizations table exists and organization_id column exists in projects
    has_org_support = False
    try:
        if db.db_type == "sqlite":
            cursor.execute("PRAGMA table_info(projects)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}
        else:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'organization_id'
            """)
            has_org_support = cursor.fetchone() is not None
            if has_org_support:
                cursor.execute("PRAGMA table_info(projects)")
                columns = {row[1]: row[2] for row in cursor.fetchall()}
            else:
                columns = {}
        
        has_org_support = "organization_id" in columns
    except Exception:
        has_org_support = False
    
    # Create organization if needed and supported
    if has_org_support and org_id is None:
        org_id = create_test_organization(db)
    
    # Create project
    if has_org_support and org_id is not None:
        cursor.execute("""
            INSERT INTO projects (name, local_path, organization_id, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name, local_path, org_id))
    else:
        # Fall back to old method without organization_id
        cursor.execute("""
            INSERT INTO projects (name, local_path, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (name, local_path))
    
    if db.db_type == "postgresql":
        cursor.execute("SELECT id FROM projects WHERE name = ?", (name,))
        project_id = cursor.fetchone()[0]
    else:
        project_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    
    return project_id, org_id


@pytest.fixture
def org_fixture(temp_db):
    """
    Fixture that creates a test organization if multi-tenancy is supported.
    Returns organization ID or None.
    """
    db, _ = temp_db
    org_id = create_test_organization(db)
    yield org_id


@pytest.fixture
def project_with_org_fixture(temp_db, org_fixture):
    """
    Fixture that creates a test project with organization context.
    Works with or without multi-tenancy support.
    """
    db, _ = temp_db
    project_id, org_id = create_test_project_with_org(db, org_id=org_fixture)
    yield project_id, org_id
