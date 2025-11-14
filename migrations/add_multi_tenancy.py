#!/usr/bin/env python3
"""
Migration script to add multi-tenancy to existing data.

This script:
1. Creates a default organization for existing data
2. Assigns all existing projects to default organization
3. Assigns all existing tasks to default organization (via project or directly)
4. Creates default roles (admin, member, viewer)
5. Assigns all existing users to default organization with appropriate roles
6. Migrates existing API keys to default organization

Supports both SQLite and PostgreSQL databases.

Usage:
    python -m todorama.commands.migrate add_multi_tenancy [--rollback]
"""
import os
import sys
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add parent directory to path to import todorama
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from todorama.database import TodoDatabase
from todorama.db_adapter import get_database_adapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiTenancyMigration:
    """Migration to add multi-tenancy to existing data."""
    
    def __init__(self, db: TodoDatabase):
        """Initialize migration with database connection."""
        self.db = db
        self.db_type = db.db_type
        self.adapter = db.adapter
        self.rollback_data: Dict[str, Any] = {}
        self.stats: Dict[str, int] = {
            'organizations_created': 0,
            'projects_migrated': 0,
            'tasks_migrated': 0,
            'roles_created': 0,
            'users_migrated': 0,
            'api_keys_migrated': 0
        }
    
    def _get_connection(self):
        """Get database connection."""
        return self.db._get_connection()
    
    def _execute_query(self, cursor, query: str, params: tuple = None):
        """Execute query with logging."""
        return self.db._execute_with_logging(cursor, query, params)
    
    def _normalize_sql(self, query: str) -> str:
        """Normalize SQL for database type."""
        return self.db._normalize_sql(query)
    
    def _generate_slug(self, name: str) -> str:
        """Generate slug from name."""
        return self.db._generate_slug(name)
    
    def create_default_organization(self) -> int:
        """Create default organization for existing data."""
        logger.info("Creating default organization...")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Check if default organization already exists
            cursor.execute("SELECT id FROM organizations WHERE slug = ?", ("default",))
            existing = cursor.fetchone()
            if existing:
                org_id = existing[0] if isinstance(existing, tuple) else existing['id']
                logger.info(f"Default organization already exists with ID: {org_id}")
                return org_id
            
            # Create default organization
            slug = "default"
            name = "Default Organization"
            description = "Default organization for existing data migrated to multi-tenancy"
            
            cursor.execute("""
                INSERT INTO organizations (name, slug, description)
                VALUES (?, ?, ?)
            """, (name, slug, description))
            
            if self.db_type == "sqlite":
                org_id = cursor.lastrowid
            else:
                cursor.execute("SELECT LASTVAL()")
                org_id = cursor.fetchone()[0]
            
            conn.commit()
            logger.info(f"Created default organization with ID: {org_id}")
            self.stats['organizations_created'] = 1
            
            # Store for rollback
            self.rollback_data['default_org_id'] = org_id
            
            return org_id
        finally:
            self.adapter.close(conn)
    
    def create_default_roles(self, organization_id: int) -> Dict[str, int]:
        """Create default roles (admin, member, viewer) for the organization."""
        logger.info("Creating default roles...")
        
        roles = {
            'admin': {
                'name': 'Admin',
                'permissions': json.dumps({
                    'tasks': ['create', 'read', 'update', 'delete'],
                    'projects': ['create', 'read', 'update', 'delete'],
                    'organizations': ['create', 'read', 'update', 'delete'],
                    'users': ['create', 'read', 'update', 'delete'],
                    'api_keys': ['create', 'read', 'update', 'delete']
                })
            },
            'member': {
                'name': 'Member',
                'permissions': json.dumps({
                    'tasks': ['create', 'read', 'update'],
                    'projects': ['create', 'read', 'update'],
                    'organizations': ['read'],
                    'users': ['read'],
                    'api_keys': ['create', 'read', 'update']
                })
            },
            'viewer': {
                'name': 'Viewer',
                'permissions': json.dumps({
                    'tasks': ['read'],
                    'projects': ['read'],
                    'organizations': ['read'],
                    'users': ['read'],
                    'api_keys': ['read']
                })
            }
        }
        
        role_ids = {}
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            for role_key, role_data in roles.items():
                # Check if role already exists
                cursor.execute("""
                    SELECT id FROM roles 
                    WHERE organization_id = ? AND name = ?
                """, (organization_id, role_data['name']))
                existing = cursor.fetchone()
                
                if existing:
                    role_id = existing[0] if isinstance(existing, tuple) else existing['id']
                    logger.info(f"Role '{role_data['name']}' already exists with ID: {role_id}")
                else:
                    cursor.execute("""
                        INSERT INTO roles (organization_id, name, permissions)
                        VALUES (?, ?, ?)
                    """, (organization_id, role_data['name'], role_data['permissions']))
                    
                    if self.db_type == "sqlite":
                        role_id = cursor.lastrowid
                    else:
                        cursor.execute("SELECT LASTVAL()")
                        role_id = cursor.fetchone()[0]
                    
                    logger.info(f"Created role '{role_data['name']}' with ID: {role_id}")
                    self.stats['roles_created'] += 1
                
                role_ids[role_key] = role_id
            
            conn.commit()
            logger.info(f"Created {len(role_ids)} default roles")
            
            # Store for rollback
            self.rollback_data['default_roles'] = role_ids
            
            return role_ids
        finally:
            self.adapter.close(conn)
    
    def migrate_projects(self, organization_id: int):
        """Assign all existing projects to the default organization."""
        logger.info("Migrating projects to default organization...")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all projects without organization_id
            cursor.execute("""
                SELECT id FROM projects 
                WHERE organization_id IS NULL
            """)
            projects = cursor.fetchall()
            
            if not projects:
                logger.info("No projects to migrate")
                return
            
            # Update projects
            project_ids = [p[0] if isinstance(p, tuple) else p['id'] for p in projects]
            placeholders = ','.join(['?' for _ in project_ids])
            
            query = self._normalize_sql(f"""
                UPDATE projects 
                SET organization_id = ?
                WHERE id IN ({placeholders})
            """)
            
            cursor.execute(query, (organization_id,) + tuple(project_ids))
            conn.commit()
            
            migrated_count = cursor.rowcount
            logger.info(f"Migrated {migrated_count} projects to organization {organization_id}")
            self.stats['projects_migrated'] = migrated_count
            
            # Store for rollback
            self.rollback_data['migrated_project_ids'] = project_ids
            
        finally:
            self.adapter.close(conn)
    
    def migrate_tasks(self, organization_id: int):
        """Assign all existing tasks to the default organization (via project or directly)."""
        logger.info("Migrating tasks to default organization...")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # First, update tasks that have a project_id (get organization_id from project)
            cursor.execute("""
                UPDATE tasks 
                SET organization_id = (
                    SELECT organization_id FROM projects 
                    WHERE projects.id = tasks.project_id
                )
                WHERE project_id IS NOT NULL 
                AND organization_id IS NULL
                AND EXISTS (
                    SELECT 1 FROM projects 
                    WHERE projects.id = tasks.project_id 
                    AND projects.organization_id IS NOT NULL
                )
            """)
            tasks_via_project = cursor.rowcount
            
            # Then, update tasks without project_id or with project_id but no organization
            cursor.execute("""
                UPDATE tasks 
                SET organization_id = ?
                WHERE organization_id IS NULL
            """, (organization_id,))
            tasks_direct = cursor.rowcount
            
            conn.commit()
            
            total_migrated = tasks_via_project + tasks_direct
            logger.info(f"Migrated {total_migrated} tasks to organization {organization_id} "
                       f"({tasks_via_project} via project, {tasks_direct} directly)")
            self.stats['tasks_migrated'] = total_migrated
            
        finally:
            self.adapter.close(conn)
    
    def migrate_users(self, organization_id: int, role_ids: Dict[str, int]):
        """Assign all existing users to the default organization with appropriate roles."""
        logger.info("Migrating users to default organization...")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all users
            cursor.execute("SELECT id FROM users")
            users = cursor.fetchall()
            
            if not users:
                logger.info("No users to migrate")
                return
            
            user_ids = [u[0] if isinstance(u, tuple) else u['id'] for u in users]
            migrated_count = 0
            
            # Assign each user to the organization
            # Use 'member' role as default for existing users
            default_role_id = role_ids.get('member')
            
            for user_id in user_ids:
                # Check if user is already a member
                cursor.execute("""
                    SELECT id FROM organization_members 
                    WHERE organization_id = ? AND user_id = ?
                """, (organization_id, user_id))
                existing = cursor.fetchone()
                
                if existing:
                    logger.debug(f"User {user_id} is already a member of organization {organization_id}")
                    continue
                
                # Add user as member
                cursor.execute("""
                    INSERT INTO organization_members (organization_id, user_id, role_id)
                    VALUES (?, ?, ?)
                """, (organization_id, user_id, default_role_id))
                migrated_count += 1
            
            conn.commit()
            
            logger.info(f"Migrated {migrated_count} users to organization {organization_id}")
            self.stats['users_migrated'] = migrated_count
            
            # Store for rollback
            self.rollback_data['migrated_user_ids'] = user_ids
            
        finally:
            self.adapter.close(conn)
    
    def migrate_api_keys(self, organization_id: int):
        """Migrate existing API keys to the default organization."""
        logger.info("Migrating API keys to default organization...")
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get all API keys without organization_id
            cursor.execute("""
                SELECT id FROM api_keys 
                WHERE organization_id IS NULL
            """)
            api_keys = cursor.fetchall()
            
            if not api_keys:
                logger.info("No API keys to migrate")
                return
            
            # Update API keys
            api_key_ids = [k[0] if isinstance(k, tuple) else k['id'] for k in api_keys]
            placeholders = ','.join(['?' for _ in api_key_ids])
            
            query = self._normalize_sql(f"""
                UPDATE api_keys 
                SET organization_id = ?
                WHERE id IN ({placeholders})
            """)
            
            cursor.execute(query, (organization_id,) + tuple(api_key_ids))
            conn.commit()
            
            migrated_count = cursor.rowcount
            logger.info(f"Migrated {migrated_count} API keys to organization {organization_id}")
            self.stats['api_keys_migrated'] = migrated_count
            
            # Store for rollback
            self.rollback_data['migrated_api_key_ids'] = api_key_ids
            
        finally:
            self.adapter.close(conn)
    
    def validate_migration(self, organization_id: int) -> Dict[str, Any]:
        """Validate that migration was successful."""
        logger.info("Validating migration...")
        
        conn = self._get_connection()
        validation_results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'statistics': {}
        }
        
        try:
            cursor = conn.cursor()
            
            # Check projects
            cursor.execute("""
                SELECT COUNT(*) as count FROM projects 
                WHERE organization_id IS NULL
            """)
            result = cursor.fetchone()
            if isinstance(result, dict):
                projects_without_org = result.get('count', result.get('COUNT(*)', 0))
            else:
                projects_without_org = result[0] if result else 0
            if projects_without_org > 0:
                validation_results['errors'].append(
                    f"{projects_without_org} projects still have NULL organization_id"
                )
                validation_results['valid'] = False
            validation_results['statistics']['projects_with_org'] = (
                self.stats['projects_migrated'] - projects_without_org
            )
            
            # Check tasks
            cursor.execute("""
                SELECT COUNT(*) as count FROM tasks 
                WHERE organization_id IS NULL
            """)
            result = cursor.fetchone()
            if isinstance(result, dict):
                tasks_without_org = result.get('count', result.get('COUNT(*)', 0))
            else:
                tasks_without_org = result[0] if result else 0
            if tasks_without_org > 0:
                validation_results['warnings'].append(
                    f"{tasks_without_org} tasks still have NULL organization_id "
                    "(this may be acceptable if they're orphaned)"
                )
            validation_results['statistics']['tasks_with_org'] = (
                self.stats['tasks_migrated'] - tasks_without_org
            )
            
            # Check API keys
            cursor.execute("""
                SELECT COUNT(*) as count FROM api_keys 
                WHERE organization_id IS NULL
            """)
            result = cursor.fetchone()
            if isinstance(result, dict):
                api_keys_without_org = result.get('count', result.get('COUNT(*)', 0))
            else:
                api_keys_without_org = result[0] if result else 0
            if api_keys_without_org > 0:
                validation_results['errors'].append(
                    f"{api_keys_without_org} API keys still have NULL organization_id"
                )
                validation_results['valid'] = False
            validation_results['statistics']['api_keys_with_org'] = (
                self.stats['api_keys_migrated'] - api_keys_without_org
            )
            
            # Check organization members
            cursor.execute("""
                SELECT COUNT(*) as count FROM organization_members 
                WHERE organization_id = ?
            """, (organization_id,))
            result = cursor.fetchone()
            if isinstance(result, dict):
                members_count = result.get('count', result.get('COUNT(*)', 0))
            else:
                members_count = result[0] if result else 0
            validation_results['statistics']['organization_members'] = members_count
            
            # Check roles
            cursor.execute("""
                SELECT COUNT(*) as count FROM roles 
                WHERE organization_id = ?
            """, (organization_id,))
            result = cursor.fetchone()
            if isinstance(result, dict):
                roles_count = result.get('count', result.get('COUNT(*)', 0))
            else:
                roles_count = result[0] if result else 0
            validation_results['statistics']['roles'] = roles_count
            
        finally:
            self.adapter.close(conn)
        
        return validation_results
    
    def save_rollback_data(self, filepath: str = "migration_rollback.json"):
        """Save rollback data to file."""
        rollback_data = {
            'timestamp': datetime.now().isoformat(),
            'migration_type': 'add_multi_tenancy',
            'data': self.rollback_data,
            'stats': self.stats
        }
        
        with open(filepath, 'w') as f:
            json.dump(rollback_data, f, indent=2)
        
        logger.info(f"Rollback data saved to {filepath}")
    
    def load_rollback_data(self, filepath: str = "migration_rollback.json") -> bool:
        """Load rollback data from file."""
        if not os.path.exists(filepath):
            logger.error(f"Rollback file not found: {filepath}")
            return False
        
        with open(filepath, 'r') as f:
            rollback_data = json.load(f)
        
        self.rollback_data = rollback_data.get('data', {})
        self.stats = rollback_data.get('stats', {})
        logger.info(f"Rollback data loaded from {filepath}")
        return True
    
    def rollback(self, filepath: str = "migration_rollback.json"):
        """Rollback the migration."""
        logger.info("Starting rollback...")
        
        if not self.load_rollback_data(filepath):
            return False
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Rollback API keys
            if 'migrated_api_key_ids' in self.rollback_data:
                api_key_ids = self.rollback_data['migrated_api_key_ids']
                if api_key_ids:
                    placeholders = ','.join(['?' for _ in api_key_ids])
                    query = self._normalize_sql(f"""
                        UPDATE api_keys 
                        SET organization_id = NULL
                        WHERE id IN ({placeholders})
                    """)
                    cursor.execute(query, tuple(api_key_ids))
                    logger.info(f"Rolled back {len(api_key_ids)} API keys")
            
            # Rollback tasks
            if 'migrated_project_ids' in self.rollback_data:
                # Tasks will be rolled back when projects are rolled back
                pass
            
            # Rollback projects
            if 'migrated_project_ids' in self.rollback_data:
                project_ids = self.rollback_data['migrated_project_ids']
                if project_ids:
                    placeholders = ','.join(['?' for _ in project_ids])
                    query = self._normalize_sql(f"""
                        UPDATE projects 
                        SET organization_id = NULL
                        WHERE id IN ({placeholders})
                    """)
                    cursor.execute(query, tuple(project_ids))
                    logger.info(f"Rolled back {len(project_ids)} projects")
            
            # Rollback organization members
            if 'migrated_user_ids' in self.rollback_data and 'default_org_id' in self.rollback_data:
                user_ids = self.rollback_data['migrated_user_ids']
                org_id = self.rollback_data['default_org_id']
                if user_ids:
                    placeholders = ','.join(['?' for _ in user_ids])
                    query = self._normalize_sql(f"""
                        DELETE FROM organization_members 
                        WHERE organization_id = ? AND user_id IN ({placeholders})
                    """)
                    cursor.execute(query, (org_id,) + tuple(user_ids))
                    logger.info(f"Rolled back {len(user_ids)} organization members")
            
            # Rollback roles (delete default roles)
            if 'default_roles' in self.rollback_data and 'default_org_id' in self.rollback_data:
                role_ids = list(self.rollback_data['default_roles'].values())
                if role_ids:
                    placeholders = ','.join(['?' for _ in role_ids])
                    query = self._normalize_sql(f"""
                        DELETE FROM roles 
                        WHERE id IN ({placeholders})
                    """)
                    cursor.execute(query, tuple(role_ids))
                    logger.info(f"Rolled back {len(role_ids)} roles")
            
            # Rollback organization (delete default organization)
            if 'default_org_id' in self.rollback_data:
                org_id = self.rollback_data['default_org_id']
                query = self._normalize_sql("""
                    DELETE FROM organizations 
                    WHERE id = ?
                """)
                cursor.execute(query, (org_id,))
                logger.info(f"Rolled back default organization {org_id}")
            
            conn.commit()
            logger.info("Rollback completed successfully")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Rollback failed: {e}", exc_info=True)
            return False
        finally:
            self.adapter.close(conn)
    
    def run(self) -> bool:
        """Run the migration."""
        logger.info("=" * 60)
        logger.info("Starting multi-tenancy migration")
        logger.info("=" * 60)
        
        try:
            # Step 1: Create default organization
            organization_id = self.create_default_organization()
            
            # Step 2: Create default roles
            role_ids = self.create_default_roles(organization_id)
            
            # Step 3: Migrate projects
            self.migrate_projects(organization_id)
            
            # Step 4: Migrate tasks
            self.migrate_tasks(organization_id)
            
            # Step 5: Migrate users
            self.migrate_users(organization_id, role_ids)
            
            # Step 6: Migrate API keys
            self.migrate_api_keys(organization_id)
            
            # Step 7: Validate migration
            validation = self.validate_migration(organization_id)
            
            # Step 8: Save rollback data
            self.save_rollback_data()
            
            # Report results
            logger.info("=" * 60)
            logger.info("Migration completed!")
            logger.info("=" * 60)
            logger.info("Statistics:")
            for key, value in self.stats.items():
                logger.info(f"  {key}: {value}")
            
            logger.info("\nValidation results:")
            logger.info(f"  Valid: {validation['valid']}")
            if validation['errors']:
                logger.error("  Errors:")
                for error in validation['errors']:
                    logger.error(f"    - {error}")
            if validation['warnings']:
                logger.warning("  Warnings:")
                for warning in validation['warnings']:
                    logger.warning(f"    - {warning}")
            logger.info("  Statistics:")
            for key, value in validation['statistics'].items():
                logger.info(f"    {key}: {value}")
            
            if not validation['valid']:
                logger.error("Migration completed with errors. Please review and fix.")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            return False


def main():
    """Main entry point for migration script."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Add multi-tenancy to existing data"
    )
    parser.add_argument(
        '--rollback',
        action='store_true',
        help='Rollback the migration instead of running it'
    )
    parser.add_argument(
        '--rollback-file',
        default='migration_rollback.json',
        help='Path to rollback data file (default: migration_rollback.json)'
    )
    
    args = parser.parse_args()
    
    # Initialize database
    db = TodoDatabase()
    
    # Create migration instance
    migration = MultiTenancyMigration(db)
    
    if args.rollback:
        success = migration.rollback(args.rollback_file)
        sys.exit(0 if success else 1)
    else:
        success = migration.run()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
