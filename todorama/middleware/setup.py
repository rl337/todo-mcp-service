"""
Middleware setup and configuration.
"""
from todorama.adapters.http_framework import HTTPFrameworkAdapter
from todorama.monitoring import MetricsMiddleware
from todorama.rate_limiting import RateLimitMiddleware
from todorama.security_headers import SecurityHeadersMiddleware

http_adapter = HTTPFrameworkAdapter()
FastAPI = http_adapter.FastAPI
StaticFiles = http_adapter.StaticFiles


def setup_middleware(app):
    """Set up all middleware for the FastAPI application."""
    # Add monitoring middleware (must be added before routes)
    app.add_middleware(MetricsMiddleware)
    
    # Add rate limiting middleware (after metrics, before routes)
    app.add_middleware(RateLimitMiddleware)
    
    # Add security headers middleware (adds security headers to all responses)
    app.add_middleware(SecurityHeadersMiddleware)

