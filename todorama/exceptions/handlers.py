"""
Exception handlers for the application.
"""
import sqlite3
import logging
from typing import Any
from todorama.adapters.http_framework import HTTPFrameworkAdapter
from fastapi.exceptions import RequestValidationError
from todorama.monitoring import get_request_id
from todorama.exceptions.errors import (
    ServiceError,
    NotFoundError,
    ValidationError,
    to_http_exception,
    to_mcp_error_response
)

# Initialize adapter
http_adapter = HTTPFrameworkAdapter()
Request = http_adapter.Request
JSONResponse = http_adapter.JSONResponse
HTTPException = http_adapter.HTTPException

logger = logging.getLogger(__name__)


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for unhandled exceptions.
    """
    request_id = get_request_id() or '-'
    logger.error(
        f"Unhandled exception in {request.method} {request.url.path}: {str(exc)}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "exception_type": type(exc).__name__,
        }
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again or contact support if the issue persists.",
            "path": request.url.path,
            "method": request.method,
            "request_id": request_id
        }
    )


async def sqlite_exception_handler(request: Request, exc: sqlite3.Error) -> JSONResponse:
    """
    Handler for SQLite database errors.
    Returns 200 OK with success: False for MCP endpoints to make errors visible to agents.
    """
    request_id = get_request_id() or '-'
    error_detail = str(exc)
    error_type = type(exc).__name__
    
    logger.error(
        f"Database error in {request.method} {request.url.path}: {error_detail}",
        exc_info=True,
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": error_type,
        }
    )
    
    # For MCP endpoints, return 200 OK with success: False
    # This makes errors visible to agents using MCP
    if request.url.path.startswith("/mcp/"):
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "error": f"Database error in {request.url.path}: {error_detail}",
                "error_type": type(exc).__name__,
                "error_details": error_detail,
                "path": request.url.path,
                "request_id": request_id
            }
        )
    else:
        # For non-MCP endpoints, use standard error format
        return JSONResponse(
            status_code=500,
            content={
                "error": "Database error",
                "detail": "A database operation failed. Please try again or contact support if the issue persists.",
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id
            }
        )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Handle request validation errors with clear messages.
    """
    request_id = get_request_id() or '-'
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]
        errors.append(f"{field}: {msg}")
    
    logger.warning(
        f"Validation error in {request.method} {request.url.path}: {', '.join(errors)}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "errors": errors,
        }
    )
    response = JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "detail": "One or more fields failed validation",
            "errors": errors,
            "path": request.url.path,
            "method": request.method,
            "request_id": request_id
        }
    )
    # Add request ID to headers if available
    if request_id != '-':
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = request_id
    return response


async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """
    Handler for standard ServiceError exceptions.
    
    Converts ServiceError to appropriate HTTP response:
    - For MCP endpoints: Returns 200 OK with success: False and error details
    - For other endpoints: Returns appropriate HTTP status code with error details
    """
    request_id = get_request_id() or '-'
    
    # Set request_id on exception if not already set
    if not exc.request_id:
        exc.request_id = request_id
    
    # Log the error
    log_level = logging.WARNING if isinstance(exc, (NotFoundError, ValidationError)) else logging.ERROR
    logger.log(
        log_level,
        f"Service error in {request.method} {request.url.path}: {exc.message}",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": exc.__class__.__name__,
            "error_message": exc.message,
        }
    )
    
    # For MCP endpoints, return 200 OK with success: False
    if request.url.path.startswith("/mcp/"):
        error_response = to_mcp_error_response(exc)
        return JSONResponse(
            status_code=200,
            content=error_response
        )
    else:
        # For non-MCP endpoints, convert to HTTPException and return appropriate status
        http_exc = to_http_exception(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail
        )


def setup_exception_handlers(app):
    """
    Register exception handlers with the FastAPI app.
    
    Note: ServiceError handler must be registered before the generic Exception handler
    to ensure ServiceError exceptions are caught first.
    """
    # Register ServiceError handler first (more specific)
    app.add_exception_handler(ServiceError, service_error_handler)
    # Then register generic handlers
    app.add_exception_handler(Exception, global_exception_handler)
    app.add_exception_handler(sqlite3.Error, sqlite_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

