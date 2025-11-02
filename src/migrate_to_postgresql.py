#!/usr/bin/env python3
"""
Migration script to migrate data from SQLite to PostgreSQL.

Usage:
    python3 migrate_to_postgresql.py <sqlite_db_path> <postgresql_connection_string>

Example:
    python3 migrate_to_postgresql.py /app/data/todos.db "host=localhost port=5432 dbname=todos user=postgres password=mypassword"
"""
import sys
import os
import sqlite3
import argparse
import logging

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import TodoDatabase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def migrate_sqlite_to_postgresql(sqlite_path: str, postgresql_conn_string: str):
    """
    Migrate data from SQLite to PostgreSQL.
    
    Args:
        sqlite_path: Path to SQLite database file
        postgresql_conn_string: PostgreSQL connection string
    """
    logger.info(f"Starting migration from {sqlite_path} to PostgreSQL")
    
    # Connect to SQLite source
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")
    
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()
    
    try:
        # Create PostgreSQL database instance
        os.environ["DB_TYPE"] = "postgresql"
        # Temporarily set connection string
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
        
        logger.info("Migration completed successfully!")
        
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite database to PostgreSQL")
    parser.add_argument("sqlite_db", help="Path to SQLite database file")
    parser.add_argument("postgresql_conn", help="PostgreSQL connection string (e.g., 'host=localhost port=5432 dbname=todos user=postgres password=pass')")
    
    args = parser.parse_args()
    
    try:
        migrate_sqlite_to_postgresql(args.sqlite_db, args.postgresql_conn)
        sys.exit(0)
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)
