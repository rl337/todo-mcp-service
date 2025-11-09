"""
Migrate command - Migrate data from SQLite to PostgreSQL.
"""
import os
import sqlite3
import logging
from todorama.__main__ import Command

logger = logging.getLogger(__name__)


class MigrateCommand(Command):
    """Command to migrate data from SQLite to PostgreSQL."""
    
    @classmethod
    def add_arguments(cls, parser):
        """Add migrate-specific arguments."""
        parser.add_argument(
            "sqlite_db",
            help="Path to SQLite database file"
        )
        parser.add_argument(
            "postgresql_conn",
            help="PostgreSQL connection string (e.g., 'host=localhost port=5432 dbname=todos user=postgres password=pass')"
        )
    
    def init(self):
        """Initialize the migrate command."""
        super().init()
        
        # Validate SQLite database exists
        if not os.path.exists(self.args.sqlite_db):
            raise FileNotFoundError(f"SQLite database not found: {self.args.sqlite_db}")
        
        logger.info(f"Migration initialized: {self.args.sqlite_db} -> PostgreSQL")
    
    def run(self) -> int:
        """Run the migration."""
        try:
            self._migrate_sqlite_to_postgresql(
                self.args.sqlite_db,
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

