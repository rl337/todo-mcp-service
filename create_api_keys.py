#!/usr/bin/env python3
"""Create API keys and save to api_keys.json using the API."""
import json
import os
import requests
from pathlib import Path

API_KEYS_FILE = Path("api_keys.json")
API_BASE = "http://localhost:8000/mcp/todo-mcp-service/api"

def create_admin_key_via_db():
    """Create admin key by directly accessing the database."""
    import sqlite3
    import secrets
    import hashlib
    from todorama.config import get_database_path, ensure_database_directory
    
    # Get unified database path (same as service uses)
    db_path = get_database_path()
    
    # Ensure directory exists
    ensure_database_directory(db_path)
    
    # Connect directly - service has already initialized schema
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get first project ID
        cursor.execute("SELECT id, name FROM projects LIMIT 1")
        project_row = cursor.fetchone()
        if not project_row:
            raise ValueError("No projects found. Please create a project first.")
        
        project_id = project_row[0]
        
        # Generate API key
        api_key = f"admin_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_prefix = api_key[:8]
        
        # Create the API key with is_admin=1
        cursor.execute("""
            INSERT INTO api_keys (project_id, key_hash, key_prefix, name, enabled, is_admin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, key_hash, key_prefix, "Admin Key (System)", 1, 1))
        
        key_id = cursor.lastrowid
        
        conn.commit()
        
        print(f"✅ Admin key created (ID: {key_id})")
        return api_key
    finally:
        conn.close()

def create_project_keys_via_db(admin_key):
    """Create project keys by directly accessing the database."""
    import sqlite3
    import secrets
    import hashlib
    from todorama.config import get_database_path, ensure_database_directory
    
    # Get unified database path (same as service uses)
    db_path = get_database_path()
    
    # Ensure directory exists
    ensure_database_directory(db_path)
    
    # Connect directly - service has already initialized schema
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Get all projects
        cursor.execute("SELECT id, name FROM projects")
        projects = cursor.fetchall()
        
        project_keys = {}
        
        for project_id, project_name in projects:
            # Check if key already exists
            cursor.execute("SELECT id FROM api_keys WHERE project_id = ? AND enabled = 1", (project_id,))
            existing = cursor.fetchone()
            
            if existing:
                print(f"⏭️  Project {project_id} ({project_name}) already has a key (ID: {existing[0]})")
                continue
            
            # Generate API key
            api_key = f"project_{project_id}_{secrets.token_urlsafe(24)}"
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            key_prefix = api_key[:8]
            
            cursor.execute("""
                INSERT INTO api_keys (project_id, key_hash, key_prefix, name, enabled)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, key_hash, key_prefix, f"Project Key for {project_name}", 1))
            
            key_id = cursor.lastrowid
            
            project_keys[str(project_id)] = {
                "key_id": key_id,
                "api_key": api_key,
                "project_id": project_id,
                "name": f"Project Key for {project_name}",
                "key_prefix": key_prefix
            }
            print(f"✅ Created key for project {project_id} ({project_name})")
        
        conn.commit()
        return project_keys
    finally:
        conn.close()

def main():
    print("=" * 60)
    print("Creating API Keys")
    print("=" * 60)
    print()
    
    # Check if api_keys.json already exists
    if API_KEYS_FILE.exists():
        # Check if it's just a placeholder
        try:
            with open(API_KEYS_FILE, 'r') as f:
                existing = json.load(f)
                if existing.get("admin_key") == "admin_PLACEHOLDER_REPLACE_WITH_REAL_KEY":
                    print(f"⚠️  {API_KEYS_FILE} exists but contains placeholder - will overwrite")
                else:
                    print(f"⚠️  {API_KEYS_FILE} already exists with real keys")
                    # In non-interactive mode, skip if real keys exist
                    import sys
                    if not sys.stdin.isatty():
                        print("Skipping (non-interactive mode). Use --force to overwrite.")
                        return
                    response = input("Overwrite? (y/N): ").strip().lower()
                    if response != 'y':
                        print("Cancelled.")
                        return
        except:
            # If we can't read it, ask to overwrite
            import sys
            if not sys.stdin.isatty():
                print(f"⚠️  {API_KEYS_FILE} exists but unreadable - skipping (non-interactive mode)")
                return
            response = input("Overwrite? (y/N): ").strip().lower()
            if response != 'y':
                print("Cancelled.")
                return
    
    api_keys = {
        "admin_key": None,
        "project_keys": {}
    }
    
    # Create admin key
    print("Creating admin key...")
    try:
        admin_key = create_admin_key_via_db()
        api_keys["admin_key"] = admin_key
        print(f"   Admin key: {admin_key[:30]}...")
    except Exception as e:
        print(f"❌ Failed to create admin key: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print()
    
    # Create project keys
    print("Creating project keys...")
    try:
        project_keys = create_project_keys_via_db(admin_key)
        api_keys["project_keys"] = project_keys
    except Exception as e:
        print(f"❌ Failed to create project keys: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print()
    
    # Save to file
    try:
        with open(API_KEYS_FILE, 'w') as f:
            json.dump(api_keys, f, indent=2)
        os.chmod(API_KEYS_FILE, 0o600)
        print(f"✅ Saved API keys to {API_KEYS_FILE}")
        print(f"   File permissions: 600 (read/write for owner only)")
    except Exception as e:
        print(f"❌ Failed to save API keys: {e}")
        return
    
    print()
    print("=" * 60)
    print("✅ Complete!")
    print("=" * 60)
    print(f"Admin key: {api_keys['admin_key'][:30]}...")
    print(f"Project keys: {len(api_keys['project_keys'])} projects")
    print()
    print("⚠️  IMPORTANT: Keep this file secure and never commit it to git!")

if __name__ == "__main__":
    main()
