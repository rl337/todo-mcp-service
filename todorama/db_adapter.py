"""
Database adapter abstraction layer for supporting multiple database backends.
"""
import os
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple, List
from enum import Enum

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """Database type enumeration."""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class BaseDatabaseAdapter(ABC):
    """Abstract base class for database adapters."""
    
    def __init__(self, connection_string: str):
        """
        Initialize database adapter.
        
        Args:
            connection_string: Database connection string (path for SQLite, URI for PostgreSQL)
        """
        self.connection_string = connection_string
    
    @abstractmethod
    def connect(self):
        """Get a database connection."""
        pass
    
    @abstractmethod
    def close(self, conn):
        """Close a database connection."""
        pass
    
    @abstractmethod
    def execute(self, cursor, query: str, params: Tuple = None):
        """Execute a query with parameters."""
        pass
    
    @abstractmethod
    def get_last_insert_id(self, cursor) -> int:
        """Get the last inserted row ID."""
        pass
    
    @abstractmethod
    def normalize_query(self, query: str) -> str:
        """Normalize SQL query for this database backend."""
        pass
    
    @abstractmethod
    def get_pk_type(self) -> str:
        """Get primary key type definition."""
        pass
    
    @abstractmethod
    def supports_fulltext_search(self) -> bool:
        """Check if this database supports full-text search."""
        pass
    
    @abstractmethod
    def create_fulltext_index(self, cursor, table_name: str, columns: List[str]):
        """Create full-text search index."""
        pass
    
    @abstractmethod
    def format_fulltext_query(self, query: str, columns: List[str]) -> str:
        """Format a full-text search query."""
        pass


class SQLiteAdapter(BaseDatabaseAdapter):
    """SQLite database adapter."""
    
    def connect(self):
        import sqlite3
        conn = sqlite3.connect(self.connection_string)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def close(self, conn):
        conn.close()
    
    def execute(self, cursor, query: str, params: Tuple = None):
        if params:
            return cursor.execute(query, params)
        else:
            return cursor.execute(query)
    
    def get_last_insert_id(self, cursor) -> int:
        return cursor.lastrowid
    
    def normalize_query(self, query: str) -> str:
        # SQLite uses ? placeholders and AUTOINCREMENT, which is already the default
        return query
    
    def get_pk_type(self) -> str:
        return "INTEGER PRIMARY KEY AUTOINCREMENT"
    
    def supports_fulltext_search(self) -> bool:
        return True  # FTS5
    
    def create_fulltext_index(self, cursor, table_name: str, columns: List[str]):
        """Create FTS5 virtual table for SQLite."""
        columns_str = ", ".join(columns)
        fts_query = f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {table_name}_fts USING fts5(
                {columns_str},
                content='{table_name}',
                content_rowid='id'
            )
        """
        cursor.execute(fts_query)
    
    def format_fulltext_query(self, query: str, columns: List[str]) -> str:
        """Format FTS5 query."""
        # FTS5 uses MATCH operator
        return f"{columns[0]}_fts MATCH ?"


class PostgreSQLAdapter(BaseDatabaseAdapter):
    """PostgreSQL database adapter."""
    
    def connect(self):
        try:
            import psycopg2
            from psycopg2.extras import RealDictRow
            import psycopg2.extensions
            
            # Parse connection string (can be URI or keyword arguments)
            conn = psycopg2.connect(self.connection_string)
            
            # Set row factory to return dict-like objects
            def dict_row_factory(cursor):
                return RealDictRow
            
            # Use RealDictCursor for dict-like rows
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.close()
            
            # Enable foreign keys (PostgreSQL has them enabled by default)
            conn.set_session(autocommit=False)
            
            return conn
        except ImportError:
            raise ImportError("psycopg2-binary is required for PostgreSQL support. Install it with: pip install psycopg2-binary")
    
    def close(self, conn):
        conn.close()
    
    def execute(self, cursor, query: str, params: Tuple = None):
        # Convert ? placeholders to %s for PostgreSQL
        normalized_query = query.replace("?", "%s")
        if params:
            return cursor.execute(normalized_query, params)
        else:
            return cursor.execute(normalized_query)
    
    def get_last_insert_id(self, cursor) -> int:
        # For PostgreSQL, we need to use RETURNING clause
        # If query didn't have RETURNING, we can't get the ID this way
        # The caller should use RETURNING id in the INSERT statement
        result = cursor.fetchone()
        if result:
            return result['id'] if hasattr(result, 'keys') else result[0]
        return cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
    
    def normalize_query(self, query: str) -> str:
        # Replace ? with %s for PostgreSQL
        # Replace AUTOINCREMENT with SERIAL
        # Replace INTEGER PRIMARY KEY AUTOINCREMENT with SERIAL PRIMARY KEY
        normalized = query.replace("?", "%s")
        normalized = normalized.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        normalized = normalized.replace("AUTOINCREMENT", "")
        # Replace INTEGER with BIGINT for IDs to match SERIAL behavior
        normalized = normalized.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
        return normalized
    
    def get_pk_type(self) -> str:
        return "SERIAL PRIMARY KEY"
    
    def supports_fulltext_search(self) -> bool:
        return True  # PostgreSQL has full-text search
    
    def create_fulltext_index(self, cursor, table_name: str, columns: List[str]):
        """Create PostgreSQL full-text search index using tsvector."""
        try:
            # Add tsvector column if it doesn't exist
            cursor.execute(f"""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = '{table_name}' AND column_name = 'fts_vector'
            """)
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN fts_vector tsvector")
            
            # Create index on tsvector
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_fts 
                ON {table_name} USING gin(fts_vector)
            """)
            
            # Create or replace trigger function
            cursor.execute(f"""
                CREATE OR REPLACE FUNCTION {table_name}_fts_trigger() RETURNS trigger AS $$
                BEGIN
                    NEW.fts_vector := 
                        to_tsvector('english', COALESCE(NEW.{columns[0]}, '')) ||
                        to_tsvector('english', COALESCE(NEW.{columns[1] if len(columns) > 1 else columns[0]}, '')) ||
                        to_tsvector('english', COALESCE(NEW.{columns[2] if len(columns) > 2 else columns[0]}, ''));
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            # Create trigger to update tsvector
            cursor.execute(f"""
                DROP TRIGGER IF EXISTS {table_name}_fts_update ON {table_name};
                CREATE TRIGGER {table_name}_fts_update
                BEFORE INSERT OR UPDATE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION {table_name}_fts_trigger();
            """)
        except Exception as e:
            logger.warning(f"Failed to create PostgreSQL full-text search index: {e}")
    
    def format_fulltext_query(self, query: str, columns: List[str]) -> str:
        """Format PostgreSQL full-text search query using tsvector."""
        # PostgreSQL uses to_tsquery for search
        return f"fts_vector @@ to_tsquery('english', %s)"


def get_database_adapter(connection_string: Optional[str] = None) -> BaseDatabaseAdapter:
    """
    Factory function to get the appropriate database adapter.
    
    Args:
        connection_string: Database connection string. If None, uses environment variables.
        
    Returns:
        Database adapter instance
    """
    db_type = os.getenv("DB_TYPE", "sqlite").lower()
    
    if connection_string is None:
        if db_type == "postgresql":
            # PostgreSQL connection string from environment
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = os.getenv("DB_NAME", "todos")
            db_user = os.getenv("DB_USER", "postgres")
            db_password = os.getenv("DB_PASSWORD", "")
            
            if db_password:
                connection_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user} password={db_password}"
            else:
                connection_string = f"host={db_host} port={db_port} dbname={db_name} user={db_user}"
        else:
            # SQLite connection string (file path)
            from todorama.config import get_database_path
            connection_string = get_database_path()
    
    if db_type == "postgresql":
        return PostgreSQLAdapter(connection_string)
    else:
        return SQLiteAdapter(connection_string)
