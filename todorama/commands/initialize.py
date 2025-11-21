"""
Initialize command - Initialize database and run migrations without starting the server.
"""
import os
import sys
import logging
import subprocess
from pathlib import Path
from todorama.__main__ import Command
from todorama.config import get_database_path, ensure_database_directory
from todorama.database import TodoDatabase

logger = logging.getLogger(__name__)


class InitializeCommand(Command):
    """Command to initialize the database and run migrations without starting the server."""
    
    @classmethod
    def get_name(cls) -> str:
        """Override to return 'init' instead of 'initialize'."""
        return "init"
    
    @classmethod
    def get_description(cls) -> str:
        """Get command description."""
        return "Initialize database, run migrations, and validate schema (does not start server)"
    
    @classmethod
    def add_arguments(cls, parser):
        """Add initialize-specific arguments."""
        parser.add_argument(
            "--database-path",
            type=str,
            default=None,
            help="Path to database file (overrides TODO_DB_PATH and config defaults)"
        )
        parser.add_argument(
            "--skip-migrations",
            action="store_true",
            help="Skip running Alembic migrations (only create database if missing)"
        )
        parser.add_argument(
            "--validate-only",
            action="store_true",
            help="Only validate existing database schema, don't create or migrate"
        )
    
    def init(self):
        """Initialize the initialize command."""
        super().init()
        
        # Determine database path
        if self.args.database_path:
            self.db_path = os.path.abspath(self.args.database_path)
            # Set environment variable so other code uses this path
            os.environ["TODO_DB_PATH"] = self.db_path
        else:
            self.db_path = get_database_path()
        
        logger.info(f"Database path: {self.db_path}")
    
    def run(self) -> int:
        """Run database initialization."""
        try:
            # Ensure database directory exists
            if not self.args.validate_only:
                ensure_database_directory(self.db_path)
                logger.info(f"Database directory ensured: {os.path.dirname(self.db_path)}")
            
            # Check if database exists
            db_exists = os.path.exists(self.db_path)
            
            if self.args.validate_only:
                if not db_exists:
                    logger.error(f"Database does not exist: {self.db_path}")
                    return 1
                logger.info("Validating existing database schema...")
                return self._validate_schema()
            
            # Run Alembic migrations if not skipped
            if not self.args.skip_migrations:
                logger.info("Running Alembic migrations...")
                migration_result = self._run_migrations()
                if migration_result != 0:
                    logger.error("Migrations failed")
                    return migration_result
                logger.info("✅ Migrations completed successfully")
            else:
                logger.info("Skipping migrations (--skip-migrations flag set)")
            
            # Initialize database connection (creates schema if needed)
            logger.info("Initializing database connection...")
            try:
                db = TodoDatabase(self.db_path)
                logger.info("✅ Database connection initialized")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}", exc_info=True)
                return 1
            
            # Validate schema
            logger.info("Validating database schema...")
            validation_result = self._validate_schema()
            if validation_result != 0:
                return validation_result
            
            logger.info("✅ Database initialization complete")
            return 0
            
        except Exception as e:
            logger.exception(f"Initialization failed: {e}")
            return 1
    
    def _run_migrations(self) -> int:
        """Run Alembic migrations."""
        try:
            # Get project root (parent of todorama package)
            project_root = Path(__file__).parent.parent.parent
            
            # Set database path for Alembic
            os.environ["TODO_DB_PATH"] = self.db_path
            
            # Run alembic upgrade head
            alembic_cmd = [
                sys.executable, "-m", "alembic",
                "upgrade", "head"
            ]
            
            logger.debug(f"Running: {' '.join(alembic_cmd)}")
            result = subprocess.run(
                alembic_cmd,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                env=os.environ.copy()
            )
            
            if result.returncode != 0:
                logger.error(f"Alembic migration failed:")
                logger.error(f"stdout: {result.stdout}")
                logger.error(f"stderr: {result.stderr}")
                return result.returncode
            
            if result.stdout:
                logger.debug(f"Alembic output: {result.stdout}")
            
            return 0
            
        except FileNotFoundError:
            logger.error("Alembic not found. Make sure it's installed in the environment.")
            return 1
        except Exception as e:
            logger.exception(f"Error running migrations: {e}")
            return 1
    
    def _validate_schema(self) -> int:
        """Validate that the database schema is complete."""
        try:
            import sqlite3
            
            if not os.path.exists(self.db_path):
                logger.error(f"Database file does not exist: {self.db_path}")
                return 1
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            logger.info(f"Found {len(tables)} tables: {', '.join(tables)}")
            
            # Validate tasks table has all required columns
            if "tasks" not in tables:
                logger.error("tasks table not found")
                conn.close()
                return 1
            
            cursor.execute("PRAGMA table_info(tasks)")
            columns = {row[1]: row for row in cursor.fetchall()}
            
            # Required columns based on current schema
            required_columns = {
                "id", "project_id", "title", "task_type", "task_instruction",
                "verification_instruction", "task_status", "verification_status",
                "assigned_agent", "created_at", "updated_at", "completed_at",
                "notes", "priority"  # priority was added in migration
            }
            
            missing_columns = required_columns - set(columns.keys())
            if missing_columns:
                logger.error(f"Missing required columns in tasks table: {missing_columns}")
                conn.close()
                return 1
            
            logger.info(f"✅ tasks table has all {len(required_columns)} required columns")
            
            # Check for priority column specifically (recent addition)
            if "priority" in columns:
                priority_col = columns["priority"]
                logger.info(f"✅ priority column exists (type: {priority_col[2]}, default: {priority_col[4]})")
            else:
                logger.warning("⚠️  priority column missing (may need migration)")
            
            # Check for indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tasks'")
            indexes = [row[0] for row in cursor.fetchall()]
            logger.info(f"Found {len(indexes)} indexes on tasks table")
            
            # Check for priority-related indexes
            priority_indexes = [idx for idx in indexes if "priority" in idx]
            if priority_indexes:
                logger.info(f"✅ Priority indexes found: {', '.join(priority_indexes)}")
            
            conn.close()
            logger.info("✅ Schema validation passed")
            return 0
            
        except Exception as e:
            logger.exception(f"Schema validation failed: {e}")
            return 1
    
    def cleanup(self):
        """Clean up initialize command resources."""
        super().cleanup()
        logger.debug("Initialize command cleaned up")

