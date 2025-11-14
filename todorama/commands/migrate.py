"""
Migrate command - Migrate data from SQLite to PostgreSQL or add multi-tenancy.
"""
import os
import sys
import sqlite3
import logging
from todorama.__main__ import Command

logger = logging.getLogger(__name__)


class MigrateCommand(Command):
    """Command to migrate data from SQLite to PostgreSQL or add multi-tenancy."""
    
    @classmethod
    def add_arguments(cls, parser):
        """Add migrate-specific arguments."""
        # Support subcommands: add_multi_tenancy
        parser.add_argument(
            "subcommand_or_sqlite_db",
            nargs="?",
            help="Subcommand (add_multi_tenancy) or path to SQLite database file"
        )
        parser.add_argument(
            "postgresql_conn",
            nargs="?",
            help="PostgreSQL connection string (e.g., 'host=localhost port=5432 dbname=todos user=postgres password=pass')"
        )
        parser.add_argument(
            "--rollback",
            action="store_true",
            help="Rollback the migration (for add_multi_tenancy)"
        )
        parser.add_argument(
            "--rollback-file",
            default="migration_rollback.json",
            help="Path to rollback data file (default: migration_rollback.json)"
        )
    
    def init(self):
        """Initialize the migrate command."""
        super().init()
        
        # Check if this is a subcommand
        subcommand = self.args.subcommand_or_sqlite_db
        
        if subcommand == "add_multi_tenancy":
            # This is the add_multi_tenancy subcommand
            self.subcommand = "add_multi_tenancy"
            logger.info("Initialized add_multi_tenancy migration")
        else:
            # This is the legacy SQLite to PostgreSQL migration
            self.subcommand = None
            if not subcommand:
                raise ValueError("Missing required argument: sqlite_db or subcommand")
            if not os.path.exists(subcommand):
                raise FileNotFoundError(f"SQLite database not found: {subcommand}")
            if not self.args.postgresql_conn:
                raise ValueError("Missing required argument: postgresql_conn")
            logger.info(f"Migration initialized: {subcommand} -> PostgreSQL")
    
    def run(self) -> int:
        """Run the migration."""
        try:
            if self.subcommand == "add_multi_tenancy":
                return self._run_add_multi_tenancy()
            else:
                return self._run_sqlite_to_postgresql()
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            return 1
    
    def _run_add_multi_tenancy(self) -> int:
        """Run the add_multi_tenancy migration."""
        # Get the project root directory (parent of todorama package)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        migrations_path = os.path.join(project_root, "migrations")
        
        if not os.path.exists(migrations_path):
            logger.error(f"Migration directory not found: {migrations_path}")
            return 1
        
        # Add project root to path to import migrations
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # Import the migration module
        from migrations.add_multi_tenancy import MultiTenancyMigration
        from todorama.database import TodoDatabase
        
        # Initialize database
        db = TodoDatabase()
        
        # Create migration instance
        migration = MultiTenancyMigration(db)
        
        if self.args.rollback:
            success = migration.rollback(self.args.rollback_file)
            return 0 if success else 1
        else:
            success = migration.run()
            return 0 if success else 1
    
    def _run_sqlite_to_postgresql(self) -> int:
        """Run the SQLite to PostgreSQL migration."""
        try:
            self._migrate_sqlite_to_postgresql(
                self.args.subcommand_or_sqlite_db,
                self.args.postgresql_conn
            )
            logger.info("Migration completed successfully!")
            return 0
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            return 1
    
    def _migrate_sqlite_to_postgresql(self, sqlite_path: str, postgresql_conn_string: str):
        """
        Migrate data from SQLite to PostgreSQL.
        
        Args:
            sqlite_path: Path to SQLite database file
            postgresql_conn_string: PostgreSQL connection string
        """
        logger.info(f"Starting migration from {sqlite_path} to PostgreSQL")
        
        # Connect to SQLite source
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cursor = sqlite_conn.cursor()
        
        try:
            # Import here to avoid circular dependencies
            from todorama.database import TodoDatabase
            
            # Create PostgreSQL database instance
            os.environ["DB_TYPE"] = "postgresql"
            pg_db = TodoDatabase(postgresql_conn_string)
            
            # Test PostgreSQL connection
            pg_conn = pg_db._get_connection()
            pg_cursor = pg_conn.cursor()
            pg_cursor.execute("SELECT 1")
            pg_conn.commit()
            pg_db.adapter.close(pg_conn)
            logger.info("PostgreSQL connection successful")
            
            # Get all tables from SQLite
            sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [row[0] for row in sqlite_cursor.fetchall()]
            
            logger.info(f"Found {len(tables)} tables to migrate: {', '.join(tables)}")
            
            # Migrate data table by table
            for table in tables:
                if table == "tasks_fts":
                    logger.info(f"Skipping {table} (full-text search table, will be recreated)")
                    continue
                
                logger.info(f"Migrating table: {table}")
                
                # Get all rows from SQLite
                sqlite_cursor.execute(f"SELECT * FROM {table}")
                rows = sqlite_cursor.fetchall()
                
                if not rows:
                    logger.info(f"  Table {table} is empty, skipping")
                    continue
                
                # Get column names
                columns = [description[0] for description in sqlite_cursor.description]
                
                # Insert into PostgreSQL
                pg_conn = pg_db._get_connection()
                pg_cursor = pg_conn.cursor()
                
                try:
                    placeholders = ", ".join(["%s" for _ in columns])
                    column_names = ", ".join(columns)
                    
                    for row in rows:
                        values = tuple(row[col] for col in columns)
                        query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
                        pg_db._execute_with_logging(pg_cursor, query, values)
                    
                    pg_conn.commit()
                    logger.info(f"  Migrated {len(rows)} rows from {table}")
                except Exception as e:
                    pg_conn.rollback()
                    logger.error(f"  Error migrating {table}: {e}")
                    raise
                finally:
                    pg_db.adapter.close(pg_conn)
        
        finally:
            sqlite_conn.close()
    
    def cleanup(self):
        """Clean up migration resources."""
        super().cleanup()
        logger.debug("Migration command cleaned up")

