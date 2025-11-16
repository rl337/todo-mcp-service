"""
Key management command - Issue, invalidate, and manage API keys for the TODO service.

Supports:
- issue: Create new API keys (--admin or --project flag)
- invalidate: Revoke API keys
- list: List all API keys
- save: Save keys to api_keys.json file
"""
import os
import sys
import json
import secrets
import hashlib
import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any, List
from todorama.__main__ import Command
from todorama.database import TodoDatabase

logger = logging.getLogger(__name__)


class KeyManagementCommand(Command):
    """Command to manage API keys for the TODO service."""
    
    API_KEYS_FILE = Path("api_keys.json")
    
    @classmethod
    def get_name(cls) -> str:
        """Get the command name (used in CLI)."""
        return "key-management"
    
    @classmethod
    def add_arguments(cls, parser):
        """Add key management arguments."""
        subparsers = parser.add_subparsers(
            dest="action",
            help="Action to perform",
            metavar="ACTION",
            required=True
        )
        
        # issue subcommand
        issue_parser = subparsers.add_parser(
            "issue",
            help="Issue (create) a new API key"
        )
        issue_parser.add_argument(
            "--admin",
            action="store_true",
            help="Issue an admin API key (works across all projects)"
        )
        issue_parser.add_argument(
            "--project",
            type=int,
            metavar="PROJECT_ID",
            help="Issue a project-scoped API key for the specified project"
        )
        issue_parser.add_argument(
            "--project-all",
            action="store_true",
            help="Issue API keys for all projects"
        )
        issue_parser.add_argument(
            "--name",
            help="Name for the API key (default: auto-generated)"
        )
        issue_parser.add_argument(
            "--save",
            action="store_true",
            help="Save the key(s) to api_keys.json"
        )
        issue_parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=True,
            help="Skip projects that already have keys when using --project-all (default: True)"
        )
        
        # invalidate subcommand
        invalidate_parser = subparsers.add_parser(
            "invalidate",
            help="Invalidate (revoke) an API key"
        )
        invalidate_parser.add_argument(
            "--key-id",
            type=int,
            metavar="KEY_ID",
            help="ID of the key to invalidate"
        )
        invalidate_parser.add_argument(
            "--key-prefix",
            metavar="PREFIX",
            help="Prefix of the key to invalidate (first 8 characters)"
        )
        invalidate_parser.add_argument(
            "--project",
            type=int,
            metavar="PROJECT_ID",
            help="Invalidate all keys for a specific project"
        )
        invalidate_parser.add_argument(
            "--all",
            action="store_true",
            help="Invalidate all keys (use with caution!)"
        )
        invalidate_parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm invalidation (required for --all or --project)"
        )
        
        # list subcommand
        list_parser = subparsers.add_parser(
            "list",
            help="List all API keys"
        )
        list_parser.add_argument(
            "--format",
            choices=["json", "table"],
            default="table",
            help="Output format (default: table)"
        )
        list_parser.add_argument(
            "--project",
            type=int,
            metavar="PROJECT_ID",
            help="List keys for a specific project only"
        )
        list_parser.add_argument(
            "--admin-only",
            action="store_true",
            help="List only admin keys"
        )
        
        # save subcommand
        save_parser = subparsers.add_parser(
            "save",
            help="Save current keys to api_keys.json"
        )
        save_parser.add_argument(
            "--admin-key",
            help="Admin API key to save (or use TODO_ADMIN_KEY env var)"
        )
    
    def init(self):
        """Initialize the key management command."""
        super().init()
        
        if not hasattr(self.args, 'action') or not self.args.action:
            logger.error("Action required. Use: issue, invalidate, list, or save")
            return
        
        self.action = self.args.action
        logger.debug(f"Key management command initialized: {self.action}")
    
    def run(self) -> int:
        """Run the key management command."""
        try:
            if self.action == "issue":
                return self._issue_key()
            elif self.action == "invalidate":
                return self._invalidate_key()
            elif self.action == "list":
                return self._list_keys()
            elif self.action == "save":
                return self._save_keys()
            else:
                logger.error(f"Unknown action: {self.action}")
                return 1
        except Exception as e:
            logger.exception(f"Key management command failed: {e}")
            return 1
    
    def _get_db(self) -> TodoDatabase:
        """Get database instance (initializes schema if needed)."""
        return TodoDatabase()
    
    def _get_db_path(self) -> Path:
        """Get the database path."""
        from todorama.config import get_database_path
        return Path(get_database_path())
    
    def _hash_api_key(self, key: str) -> str:
        """Hash an API key using SHA-256."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _issue_key(self) -> int:
        """Issue (create) a new API key."""
        # Determine scope
        if self.args.admin:
            return self._issue_admin_key()
        elif self.args.project:
            return self._issue_project_key(self.args.project)
        elif self.args.project_all:
            return self._issue_all_project_keys()
        else:
            logger.error("Must specify --admin, --project PROJECT_ID, or --project-all")
            return 1
    
    def _issue_admin_key(self) -> int:
        """Generate an admin API key."""
        # Use TodoDatabase to ensure schema is initialized
        db = self._get_db()
        
        try:
            # Generate a new API key
            api_key = f"admin_{secrets.token_urlsafe(32)}"
            key_hash = self._hash_api_key(api_key)
            key_prefix = api_key[:8]
            
            # Get project ID (use first project if not specified)
            cursor.execute("SELECT id, name FROM projects LIMIT 1")
            project_row = cursor.fetchone()
            if not project_row:
                logger.error("No projects found. Please create a project first.")
                return 1
            
            project_id = project_row[0]
            project_name = project_row[1]
            
            # Create the API key
            name = self.args.name or "Admin Key (System)"
            cursor.execute("""
                INSERT INTO api_keys (project_id, key_hash, key_prefix, name, enabled)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, key_hash, key_prefix, name, 1))
            
            key_id = cursor.lastrowid
            
            # Make it admin
            cursor.execute("""
                INSERT OR IGNORE INTO api_key_admin (api_key_id)
                VALUES (?)
            """, (key_id,))
            
            conn.commit()
            
            print("=" * 60)
            print("✅ Admin API key created!")
            print("=" * 60)
            print(f"Key ID: {key_id}")
            print(f"Project ID: {project_id} ({project_name})")
            print(f"API Key: {api_key}")
            print()
            print("⚠️  IMPORTANT: Save this key immediately - it cannot be retrieved later!")
            
            # Save if requested
            if self.args.save:
                self._save_admin_key_to_file(api_key)
            
            return 0
            
        except sqlite3.OperationalError as e:
            logger.error(f"Database error: {e}")
            logger.error("The database schema may not be initialized. Please start the service first.")
            return 1
        finally:
            conn.close()
    
    def _load_admin_key(self) -> Optional[str]:
        """Load admin key from various sources."""
        # Try command-line argument
        if hasattr(self.args, 'admin_key') and self.args.admin_key:
            return self.args.admin_key
        
        # Try environment variable
        admin_key = os.getenv("TODO_ADMIN_KEY")
        if admin_key:
            return admin_key
        
        # Try loading from api_keys.json
        if self.API_KEYS_FILE.exists():
            try:
                with open(self.API_KEYS_FILE, 'r') as f:
                    data = json.load(f)
                    if "admin_key" in data:
                        return data["admin_key"]
            except Exception as e:
                logger.debug(f"Could not load admin key from file: {e}")
        
        return None
    
    def _issue_project_key(self, project_id: int) -> int:
        """Issue an API key for a specific project."""
        db_path = self._get_db_path()
        
        if not db_path.exists():
            logger.error(f"Database not found: {db_path}")
            return 1
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        try:
            # Verify project exists
            cursor.execute("SELECT id, name FROM projects WHERE id = ?", (project_id,))
            project = cursor.fetchone()
            if not project:
                logger.error(f"Project {project_id} not found")
                return 1
            
            project_name = project[1]
            
            # Check if key already exists
            cursor.execute("SELECT id FROM api_keys WHERE project_id = ? AND enabled = 1", (project_id,))
            existing = cursor.fetchone()
            if existing and self.args.skip_existing:
                logger.info(f"Project {project_id} ({project_name}) already has an active key (ID: {existing[0]})")
                return 0
            
            # Generate key
            api_key = f"project_{project_id}_{secrets.token_urlsafe(24)}"
            key_hash = self._hash_api_key(api_key)
            key_prefix = api_key[:8]
            
            # Create the API key
            name = self.args.name or f"{project_name} API Key"
            cursor.execute("""
                INSERT INTO api_keys (project_id, key_hash, key_prefix, name, enabled)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, key_hash, key_prefix, name, 1))
            
            key_id = cursor.lastrowid
            conn.commit()
            
            print("=" * 60)
            print("✅ Project API key issued!")
            print("=" * 60)
            print(f"Key ID: {key_id}")
            print(f"Project ID: {project_id} ({project_name})")
            print(f"API Key: {api_key}")
            print()
            print("⚠️  IMPORTANT: Save this key immediately - it cannot be retrieved later!")
            
            # Save if requested
            if self.args.save:
                self._save_project_key_to_file(project_id, {
                    "project_id": project_id,
                    "project_name": project_name,
                    "key_id": key_id,
                    "api_key": api_key,
                    "key_prefix": key_prefix,
                    "name": name
                })
            
            return 0
            
        except Exception as e:
            logger.error(f"Error issuing project key: {e}")
            conn.rollback()
            return 1
        finally:
            conn.close()
    
    def _issue_all_project_keys(self) -> int:
        """Issue API keys for all projects."""
        import requests
        
        # Load admin key
        admin_key = self._load_admin_key()
        if not admin_key:
            logger.error("Admin key not found.")
            logger.error("Provide via: --admin-key, TODO_ADMIN_KEY env var, or api_keys.json")
            return 1
        
        API_BASE = os.getenv("TODO_SERVICE_URL", "http://localhost:8000/mcp/todo-mcp-service").rstrip("/")
        if not API_BASE.startswith("http"):
            API_BASE = f"http://{API_BASE}"
        API_BASE = f"{API_BASE}/api"
        
        # Check service health
        try:
            response = requests.get(f"{API_BASE.replace('/api', '')}/health", timeout=2)
            if response.status_code != 200:
                logger.warning("Service health check failed, but continuing...")
        except Exception as e:
            logger.warning(f"Service may not be running: {e}")
        
        # Get all projects
        try:
            response = requests.post(
                f"{API_BASE}/Project/list",
                headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
                timeout=5
            )
            if response.status_code != 200:
                logger.error(f"Failed to list projects: {response.status_code}")
                logger.error(response.text)
                return 1
            
            projects = response.json()
            if not isinstance(projects, list):
                logger.error("Invalid response from Project/list")
                return 1
        except Exception as e:
            logger.error(f"Error listing projects: {e}")
            return 1
        
        if not projects:
            logger.error("No projects found")
            return 1
        
        logger.info(f"Found {len(projects)} project(s)")
        
        # Load existing keys
        existing_keys = {}
        if self.API_KEYS_FILE.exists() and self.args.skip_existing:
            try:
                with open(self.API_KEYS_FILE, 'r') as f:
                    existing_data = json.load(f)
                    existing_keys = existing_data.get("project_keys", {})
            except Exception:
                pass
        
        # Issue keys for each project
        project_keys = {}
        issued_count = 0
        
        for project in projects:
            project_id = project.get("id")
            project_name = project.get("name", f"Project {project_id}")
            
            # Check if key already exists
            if project_id in existing_keys and self.args.skip_existing:
                logger.info(f"⏭️  Skipping project {project_id} ({project_name}) - key already exists")
                project_keys[project_id] = existing_keys[project_id]
                continue
            
            logger.info(f"Issuing API key for project {project_id} ({project_name})...")
            
            # Try to create via API
            key_data = self._create_project_key_via_api(API_BASE, admin_key, project_id, project_name)
            
            if not key_data:
                # Fall back to database method
                key_data = self._create_project_key_via_db(project_id, project_name)
            
            if key_data:
                project_keys[project_id] = {
                    "project_id": project_id,
                    "project_name": project_name,
                    "key_id": key_data.get("key_id"),
                    "api_key": key_data.get("api_key"),
                    "key_prefix": key_data.get("key_prefix"),
                    "name": key_data.get("name")
                }
                issued_count += 1
                logger.info(f"   ✅ Issued: {key_data.get('key_prefix', 'N/A')}...")
            else:
                logger.error(f"   ❌ Failed to issue key")
        
        # Save keys if requested
        if self.args.save:
            self._save_keys_to_file(admin_key, project_keys)
        
        print()
        print("=" * 60)
        print("✅ Complete!")
        print("=" * 60)
        print(f"Issued API keys for {issued_count} project(s)")
        if self.args.skip_existing:
            print(f"Skipped {len(project_keys) - issued_count} project(s) with existing keys")
        
        return 0
    
    def _create_project_key_via_api(self, api_base: str, admin_key: str, project_id: int, project_name: str) -> Optional[Dict[str, Any]]:
        """Create a project key via API."""
        import requests
        
        try:
            # Try command router endpoint
            response = requests.post(
                f"{api_base}/Project/create_api_key",
                headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
                json={"project_id": project_id, "name": f"{project_name} API Key"},
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                return response.json()
            
            # Try alternative endpoint
            base_url = api_base.replace("/api", "")
            response = requests.post(
                f"{base_url}/projects/{project_id}/api-keys",
                headers={"X-API-Key": admin_key, "Content-Type": "application/json"},
                json={"name": f"{project_name} API Key"},
                timeout=5
            )
            
            if response.status_code in [200, 201]:
                return response.json()
            
            logger.debug(f"API method failed: {response.status_code} - {response.text[:200]}")
            return None
            
        except Exception as e:
            logger.debug(f"API method error: {e}")
            return None
    
    def _create_project_key_via_db(self, project_id: int, project_name: str) -> Optional[Dict[str, Any]]:
        """Create a project key directly via database."""
        db_path = self._get_db_path()
        
        if not db_path.exists():
            return None
        
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        try:
            # Generate key
            api_key = f"project_{project_id}_{secrets.token_urlsafe(24)}"
            key_hash = self._hash_api_key(api_key)
            key_prefix = api_key[:8]
            
            # Create the API key
            cursor.execute("""
                INSERT INTO api_keys (project_id, key_hash, key_prefix, name, enabled)
                VALUES (?, ?, ?, ?, ?)
            """, (project_id, key_hash, key_prefix, f"{project_name} API Key", 1))
            
            key_id = cursor.lastrowid
            conn.commit()
            
            return {
                "key_id": key_id,
                "api_key": api_key,
                "key_prefix": key_prefix,
                "name": f"{project_name} API Key"
            }
            
        except Exception as e:
            logger.debug(f"Database method error: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def _list_keys(self) -> int:
        """List all API keys."""
        db_path = self._get_db_path()
        
        if not db_path.exists():
            logger.error(f"Database not found: {db_path}")
            return 1
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    ak.id,
                    ak.project_id,
                    p.name as project_name,
                    ak.key_prefix,
                    ak.name,
                    ak.enabled,
                    CASE WHEN aka.api_key_id IS NOT NULL THEN 1 ELSE 0 END as is_admin
                FROM api_keys ak
                LEFT JOIN projects p ON ak.project_id = p.id
                LEFT JOIN api_key_admin aka ON ak.id = aka.api_key_id
                ORDER BY ak.id
            """)
            
            keys = cursor.fetchall()
            
            if self.args.format == "json":
                keys_list = []
                for key in keys:
                    keys_list.append({
                        "id": key["id"],
                        "project_id": key["project_id"],
                        "project_name": key["project_name"],
                        "key_prefix": key["key_prefix"],
                        "name": key["name"],
                        "enabled": bool(key["enabled"]),
                        "is_admin": bool(key["is_admin"])
                    })
                print(json.dumps(keys_list, indent=2))
            else:
                print(f"\n{'ID':<6} {'Project':<20} {'Prefix':<12} {'Name':<30} {'Admin':<8} {'Enabled':<8}")
                print("-" * 90)
                for key in keys:
                    print(f"{key['id']:<6} {str(key['project_name'] or 'N/A'):<20} {key['key_prefix']:<12} {key['name']:<30} {'Yes' if key['is_admin'] else 'No':<8} {'Yes' if key['enabled'] else 'No':<8}")
                print(f"\nTotal: {len(keys)} key(s)")
            
            return 0
            
        except Exception as e:
            logger.error(f"Error listing keys: {e}")
            return 1
        finally:
            conn.close()
    
    def _save_keys(self) -> int:
        """Save keys to api_keys.json."""
        admin_key = self._load_admin_key()
        if not admin_key:
            logger.error("Admin key not found. Cannot save keys.")
            return 1
        
        # Get project keys from database
        project_keys = self._get_project_keys_from_db()
        
        self._save_keys_to_file(admin_key, project_keys)
        return 0
    
    def _get_project_keys_from_db(self) -> Dict[int, Dict[str, Any]]:
        """Get project keys from database."""
        db_path = self._get_db_path()
        project_keys = {}
        
        if not db_path.exists():
            return project_keys
        
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT 
                    ak.id as key_id,
                    ak.project_id,
                    p.name as project_name,
                    ak.key_prefix,
                    ak.name,
                    CASE WHEN aka.api_key_id IS NOT NULL THEN 1 ELSE 0 END as is_admin
                FROM api_keys ak
                LEFT JOIN projects p ON ak.project_id = p.id
                LEFT JOIN api_key_admin aka ON ak.id = aka.api_key_id
                WHERE ak.enabled = 1
            """)
            
            for key in cursor.fetchall():
                project_id = key["project_id"]
                project_keys[project_id] = {
                    "project_id": project_id,
                    "project_name": key["project_name"],
                    "key_id": key["key_id"],
                    "key_prefix": key["key_prefix"],
                    "name": key["name"],
                    "is_admin": bool(key["is_admin"])
                }
        finally:
            conn.close()
        
        return project_keys
    
    def _save_admin_key_to_file(self, admin_key: str):
        """Save admin key to api_keys.json."""
        data = {}
        if self.API_KEYS_FILE.exists():
            try:
                with open(self.API_KEYS_FILE, 'r') as f:
                    data = json.load(f)
            except Exception:
                pass
        
        data["admin_key"] = admin_key
        
        with open(self.API_KEYS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Set restrictive permissions
        os.chmod(self.API_KEYS_FILE, 0o600)
        logger.info(f"✅ Admin key saved to {self.API_KEYS_FILE}")
    
    def _save_keys_to_file(self, admin_key: str, project_keys: Dict[int, Dict[str, Any]]):
        """Save all keys to api_keys.json."""
        data = {
            "admin_key": admin_key,
            "project_keys": project_keys,
            "generated_at": str(Path(__file__).stat().st_mtime)
        }
        
        with open(self.API_KEYS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        # Set restrictive permissions
        os.chmod(self.API_KEYS_FILE, 0o600)
        logger.info(f"✅ API keys saved to {self.API_KEYS_FILE} (permissions: 600)")
        logger.info("⚠️  IMPORTANT: This file should NEVER be committed to git!")
    

