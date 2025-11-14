"""
Exception handlers and standard exceptions for the application.
"""
from todorama.exceptions.errors import (
    ServiceError,
    NotFoundError,
    ValidationError,
    DuplicateError,
    DatabaseError,
    TaskNotFoundError,
    ProjectNotFoundError,
    OrganizationNotFoundError,
    TagNotFoundError,
    TemplateNotFoundError,
    to_http_exception,
    to_mcp_error_response,
)

__all__ = [
    "ServiceError",
    "NotFoundError",
    "ValidationError",
    "DuplicateError",
    "DatabaseError",
    "TaskNotFoundError",
    "ProjectNotFoundError",
    "OrganizationNotFoundError",
    "TagNotFoundError",
    "TemplateNotFoundError",
    "to_http_exception",
    "to_mcp_error_response",
]
