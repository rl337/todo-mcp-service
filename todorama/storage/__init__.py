"""
Storage abstraction layer.
Provides a clean interface for data persistence that can be swapped out.
"""
from .interface import StorageInterface
from .sqlite_storage import SQLiteStorage
from .repositories import TaskRepository, ProjectRepository, OrganizationRepository

__all__ = [
    'StorageInterface',
    'SQLiteStorage',
    'TaskRepository',
    'ProjectRepository',
    'OrganizationRepository',
]










