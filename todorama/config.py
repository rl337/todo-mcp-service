"""
Unified configuration for database paths and other settings.

This module provides a single source of truth for database path resolution
that works consistently across:
- Service (running in container or locally)
- CLI utilities
- Scripts and tools

The database path resolution:
1. Checks TODO_DB_PATH environment variable first
2. Falls back to a consistent default location
3. Ensures the directory exists
4. Works for both local development and containerized deployments

This module uses Pydantic Settings for type-safe configuration management
with support for .env files and environment variable overrides.
"""
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default database path - works for both local and container
# In containers, this should be mounted from a volume
# In local dev, this is relative to the project root
DEFAULT_DB_PATH = "data/todos.db"

# Container default (used when running in container)
CONTAINER_DB_PATH = "/app/data/todos.db"


def _is_container() -> bool:
    """Check if we're running in a container."""
    # Check for common container indicators
    if os.path.exists("/.dockerenv"):
        return True
    if os.path.exists("/proc/1/cgroup"):
        try:
            with open("/proc/1/cgroup", "r") as f:
                content = f.read()
                if "docker" in content or "containerd" in content or "kubepods" in content:
                    return True
        except:
            pass
    return False


class Settings(BaseSettings):
    """Application settings for Todorama.
    
    All configuration values can be set via environment variables or .env file.
    Defaults are provided for development convenience.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================================================
    # Standardized Database Configuration
    # ============================================================================
    # Database path is resolved via field_validator to handle TODO_DB_PATH
    # environment variable, container detection, and default paths
    database_path: str = ""  # Will be resolved by validator

    db_pool_size: int = 5  # Connection pool size (for future PostgreSQL support)
    db_max_overflow: int = 10  # Max overflow connections
    db_pool_timeout: int = 30  # Connection timeout
    sql_echo: bool = False  # SQL query logging

    # ============================================================================
    # Standardized Logging Configuration
    # ============================================================================
    log_level: str = "INFO"
    log_format: str = "json"

    # ============================================================================
    # Standardized Environment Configuration
    # ============================================================================
    environment: str = "development"
    debug: bool = False

    @field_validator("database_path", mode="before")
    @classmethod
    def resolve_database_path(cls, v: Optional[str]) -> str:
        """
        Resolve database path with unified resolution logic.
        
        Resolution order:
        1. TODO_DB_PATH environment variable (highest priority, backward compatibility)
        2. Value from .env file or Settings field (if provided)
        3. Container path if running in container
        4. Local development path
        
        Args:
            v: Value from field or None
            
        Returns:
            Absolute path to the database file
        """
        # Check environment variable first (backward compatibility with TODO_DB_PATH)
        env_path = os.getenv("TODO_DB_PATH")
        if env_path:
            return os.path.abspath(env_path)
        
        # If value was provided via .env or Settings field, use it
        if v:
            return os.path.abspath(v)
        
        # Determine default based on environment
        if _is_container():
            default_path = CONTAINER_DB_PATH
        else:
            # For local development, use project-relative path
            # Get project root (assume we're in todorama/ or a subdirectory)
            # This is a fallback - in practice, the path should be set via env var or .env
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent  # Go up from todorama/config.py to project root
            default_path = str(project_root / DEFAULT_DB_PATH)
        
        return os.path.abspath(default_path)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    return Settings()


def get_database_path() -> str:
    """
    Get the database path with unified resolution.
    
    This function is maintained for backward compatibility with existing code.
    It delegates to the Pydantic Settings configuration.
    
    Resolution order:
    1. TODO_DB_PATH environment variable (highest priority)
    2. Container path if running in container
    3. Local development path
    
    Returns:
        Absolute path to the database file
    """
    settings = get_settings()
    return settings.database_path


def ensure_database_directory(db_path: Optional[str] = None) -> None:
    """
    Ensure the database directory exists.
    
    Args:
        db_path: Path to the database file. If None, uses get_database_path().
    """
    if db_path is None:
        db_path = get_database_path()
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
