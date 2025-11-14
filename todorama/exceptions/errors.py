"""
Standard Exception Hierarchy for Todorama MCP Service

This module provides a standardized exception hierarchy for consistent error handling
across the todorama service. All exceptions inherit from ServiceError and can be
converted to HTTPException (for FastAPI) or MCP error responses.

See docs/EXCEPTION_STANDARD.md for complete documentation.
"""
from typing import Any


# ============================================================================
# Base Exception Class
# ============================================================================

class ServiceError(Exception):
    """Base exception for all MCP service errors.
    
    All service-specific exceptions should inherit from this class.
    This provides a common base for exception handling and conversion.
    
    Attributes:
        message: Human-readable error message
        request_id: Optional request ID for tracing
        context: Dictionary of additional context
        original_error: Optional original exception that caused this error
    """
    
    def __init__(
        self,
        message: str,
        *,
        request_id: str | None = None,
        context: dict[str, Any] | None = None,
        original_error: Exception | None = None
    ):
        """Initialize service error.
        
        Args:
            message: Human-readable error message
            request_id: Optional request ID for tracing
            context: Optional dictionary of additional context
            original_error: Optional original exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.request_id = request_id
        self.context = context or {}
        self.original_error = original_error
    
    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for serialization.
        
        Returns:
            Dictionary representation of the exception
        """
        result = {
            "error_type": self.__class__.__name__,
            "message": self.message,
        }
        if self.request_id:
            result["request_id"] = self.request_id
        if self.context:
            result["context"] = self.context
        if self.original_error:
            result["original_error"] = {
                "type": type(self.original_error).__name__,
                "message": str(self.original_error)
            }
        return result


# ============================================================================
# Common Exception Types
# ============================================================================

class NotFoundError(ServiceError):
    """Raised when a requested resource is not found.
    
    Attributes:
        resource_type: Type of resource (e.g., "Task", "Project", "Organization")
        resource_id: ID of the resource that was not found
    """
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str | int,
        *,
        message: str | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None
    ):
        """Initialize not found error.
        
        Args:
            resource_type: Type of resource (e.g., "Task", "Project", "Organization")
            resource_id: ID of the resource that was not found
            message: Optional custom error message (auto-generated if not provided)
            request_id: Optional request ID for tracing
            context: Optional additional context
        """
        if message is None:
            message = f"{resource_type} with ID '{resource_id}' not found"
        
        super().__init__(message, request_id=request_id, context=context)
        self.resource_type = resource_type
        self.resource_id = str(resource_id)
        self.context.setdefault("resource_type", resource_type)
        self.context.setdefault("resource_id", str(resource_id))


class ValidationError(ServiceError):
    """Raised when input validation fails.
    
    Attributes:
        field: Optional field name that failed validation
        value: Optional value that failed validation
    """
    
    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None
    ):
        """Initialize validation error.
        
        Args:
            message: Error message describing the validation failure
            field: Optional field name that failed validation
            value: Optional value that failed validation
            request_id: Optional request ID for tracing
            context: Optional additional context
        """
        super().__init__(message, request_id=request_id, context=context)
        self.field = field
        self.value = value
        if field is not None:
            self.context.setdefault("field", field)
        if value is not None:
            self.context.setdefault("value", str(value))


class DuplicateError(ServiceError):
    """Raised when attempting to create a duplicate resource.
    
    Attributes:
        resource_type: Type of resource (e.g., "Task", "Project", "Organization")
        field: Field that has duplicate value
        value: Duplicate value
    """
    
    def __init__(
        self,
        resource_type: str,
        field: str,
        value: str,
        *,
        message: str | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None
    ):
        """Initialize duplicate error.
        
        Args:
            resource_type: Type of resource (e.g., "Task", "Project", "Organization")
            field: Field that has duplicate value
            value: Duplicate value
            message: Optional custom error message (auto-generated if not provided)
            request_id: Optional request ID for tracing
            context: Optional additional context
        """
        if message is None:
            message = f"{resource_type} with {field} '{value}' already exists"
        
        super().__init__(message, request_id=request_id, context=context)
        self.resource_type = resource_type
        self.field = field
        self.value = value
        self.context.setdefault("resource_type", resource_type)
        self.context.setdefault("field", field)
        self.context.setdefault("value", value)


class DatabaseError(ServiceError):
    """Raised when a database operation fails.
    
    Attributes:
        operation: Optional database operation that failed (e.g., "INSERT", "SELECT")
        original_error: Optional original database exception
    """
    
    def __init__(
        self,
        message: str,
        *,
        original_error: Exception | None = None,
        operation: str | None = None,
        request_id: str | None = None,
        context: dict[str, Any] | None = None
    ):
        """Initialize database error.
        
        Args:
            message: Error message describing the database failure
            original_error: Optional original database exception
            operation: Optional database operation that failed (e.g., "INSERT", "SELECT")
            request_id: Optional request ID for tracing
            context: Optional additional context
        """
        super().__init__(message, request_id=request_id, context=context, original_error=original_error)
        self.operation = operation
        if operation is not None:
            self.context.setdefault("operation", operation)


# ============================================================================
# Service-Specific Exceptions
# ============================================================================

class TaskNotFoundError(NotFoundError):
    """Raised when a task is not found."""
    
    def __init__(self, task_id: str | int, **kwargs):
        super().__init__("Task", task_id, **kwargs)
        self.task_id = task_id  # Convenience attribute


class ProjectNotFoundError(NotFoundError):
    """Raised when a project is not found."""
    
    def __init__(self, project_id: str | int, **kwargs):
        super().__init__("Project", project_id, **kwargs)
        self.project_id = project_id  # Convenience attribute


class OrganizationNotFoundError(NotFoundError):
    """Raised when an organization is not found."""
    
    def __init__(self, organization_id: str | int, **kwargs):
        super().__init__("Organization", organization_id, **kwargs)
        self.organization_id = organization_id  # Convenience attribute


class TagNotFoundError(NotFoundError):
    """Raised when a tag is not found."""
    
    def __init__(self, tag_id: str | int, **kwargs):
        super().__init__("Tag", tag_id, **kwargs)
        self.tag_id = tag_id  # Convenience attribute


class TemplateNotFoundError(NotFoundError):
    """Raised when a template is not found."""
    
    def __init__(self, template_id: str | int, **kwargs):
        super().__init__("Template", template_id, **kwargs)
        self.template_id = template_id  # Convenience attribute


# ============================================================================
# Helper Functions for FastAPI Integration
# ============================================================================

def to_http_exception(
    exc: ServiceError,
    *,
    default_status_code: int = 500,
    include_context: bool = True
):
    """Convert ServiceError to FastAPI HTTPException.
    
    Args:
        exc: Service error to convert
        default_status_code: Default status code if mapping not found
        include_context: Whether to include exception context in response
    
    Returns:
        HTTPException with appropriate status code and detail
    """
    from todorama.adapters.http_framework import HTTPFrameworkAdapter
    http_adapter = HTTPFrameworkAdapter()
    HTTPException = http_adapter.HTTPException
    
    # Map exception types to HTTP status codes
    status_code_map = {
        NotFoundError: 404,
        ValidationError: 422,
        DuplicateError: 409,
        DatabaseError: 500,
    }
    
    status_code = status_code_map.get(type(exc), default_status_code)
    
    # Build response detail
    detail = {
        "error": exc.__class__.__name__,
        "message": exc.message,
    }
    
    if include_context and exc.context:
        detail["context"] = exc.context
    
    if exc.request_id:
        detail["request_id"] = exc.request_id
    
    return HTTPException(status_code=status_code, detail=detail)


# ============================================================================
# Helper Functions for MCP Integration
# ============================================================================

def to_mcp_error_response(exc: ServiceError) -> dict[str, Any]:
    """Convert ServiceError to MCP error response format.
    
    MCP endpoints return 200 OK with success: False and error details.
    This function creates the error response dictionary.
    
    Args:
        exc: Service error to convert
    
    Returns:
        Dictionary with success: False and error details
    """
    # Map exception types to MCP error codes
    error_code_map = {
        NotFoundError: -32001,  # Custom: Not Found
        ValidationError: -32602,  # Invalid Params
        DuplicateError: -32002,  # Custom: Duplicate
        DatabaseError: -32603,  # Internal Error
    }
    
    error_code = error_code_map.get(type(exc), -32603)
    
    # Build error response
    response = {
        "success": False,
        "error": {
            "code": error_code,
            "message": exc.message,
            "error_type": exc.__class__.__name__,
        }
    }
    
    if exc.context:
        response["error"]["context"] = exc.context
    
    if exc.request_id:
        response["error"]["request_id"] = exc.request_id
    
    return response


# ============================================================================
# Exports
# ============================================================================

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
