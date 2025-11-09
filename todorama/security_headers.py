"""
Security headers middleware for the TODO service.

Implements security headers to protect against common web vulnerabilities:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY (configurable)
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security (HSTS): Only on HTTPS
- Content-Security-Policy: Basic CSP
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: Restrictive permissions
- Cross-Origin-Opener-Policy: same-origin
- Cross-Origin-Embedder-Policy: require-corp (optional)
- Cross-Origin-Resource-Policy: same-origin

All headers are configurable via environment variables.
"""
import os
import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Logger
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding security headers to all responses."""
    
    def __init__(self, app):
        """Initialize security headers middleware with configuration."""
        super().__init__(app)
        
        # X-Content-Type-Options: Prevent MIME type sniffing
        self.content_type_options = os.getenv(
            "SECURITY_HEADER_X_CONTENT_TYPE_OPTIONS",
            "nosniff"
        )
        
        # X-Frame-Options: Prevent clickjacking
        # Options: DENY, SAMEORIGIN, ALLOW-FROM (deprecated)
        self.frame_options = os.getenv(
            "SECURITY_HEADER_X_FRAME_OPTIONS",
            "DENY"
        )
        
        # X-XSS-Protection: Legacy XSS protection (for older browsers)
        # Note: Modern browsers don't use this, but it doesn't hurt
        self.xss_protection = os.getenv(
            "SECURITY_HEADER_X_XSS_PROTECTION",
            "1; mode=block"
        )
        
        # Strict-Transport-Security (HSTS)
        # Only set if HTTPS is enabled and SECURITY_HSTS_ENABLED is true
        self.hsts_enabled = os.getenv("SECURITY_HSTS_ENABLED", "false").lower() == "true"
        self.hsts_max_age = int(os.getenv("SECURITY_HSTS_MAX_AGE", "31536000"))  # 1 year default
        self.hsts_include_subdomains = (
            os.getenv("SECURITY_HSTS_INCLUDE_SUBDOMAINS", "true").lower() == "true"
        )
        self.hsts_preload = (
            os.getenv("SECURITY_HSTS_PRELOAD", "false").lower() == "true"
        )
        
        # Content-Security-Policy
        # Default: Restrictive policy, can be customized
        self.csp = os.getenv(
            "SECURITY_HEADER_CSP",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-ancestors 'none';"
        )
        
        # Referrer-Policy
        # Options: no-referrer, no-referrer-when-downgrade, origin, origin-when-cross-origin,
        # same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
        self.referrer_policy = os.getenv(
            "SECURITY_HEADER_REFERRER_POLICY",
            "strict-origin-when-cross-origin"
        )
        
        # Permissions-Policy (formerly Feature-Policy)
        # Restrictive default policy
        self.permissions_policy = os.getenv(
            "SECURITY_HEADER_PERMISSIONS_POLICY",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()"
        )
        
        # Cross-Origin-Opener-Policy
        # Options: same-origin, same-origin-allow-popups, unsafe-none
        self.coop = os.getenv(
            "SECURITY_HEADER_CROSS_ORIGIN_OPENER_POLICY",
            "same-origin"
        )
        
        # Cross-Origin-Embedder-Policy (optional, can break some integrations)
        # Only set if explicitly enabled
        self.coep_enabled = os.getenv("SECURITY_HEADER_COEP_ENABLED", "false").lower() == "true"
        self.coep = os.getenv(
            "SECURITY_HEADER_CROSS_ORIGIN_EMBEDDER_POLICY",
            "require-corp"
        )
        
        # Cross-Origin-Resource-Policy
        # Options: same-origin, same-site, cross-origin
        self.corp = os.getenv(
            "SECURITY_HEADER_CROSS_ORIGIN_RESOURCE_POLICY",
            "same-origin"
        )
        
        logger.info(
            "Security headers middleware initialized",
            extra={
                "x_content_type_options": self.content_type_options,
                "x_frame_options": self.frame_options,
                "hsts_enabled": self.hsts_enabled,
                "csp_configured": bool(self.csp),
                "referrer_policy": self.referrer_policy,
                "coep_enabled": self.coep_enabled,
            }
        )
    
    def _build_hsts_header(self) -> Optional[str]:
        """Build HSTS header value if enabled."""
        if not self.hsts_enabled:
            return None
        
        parts = [f"max-age={self.hsts_max_age}"]
        
        if self.hsts_include_subdomains:
            parts.append("includeSubDomains")
        
        if self.hsts_preload:
            parts.append("preload")
        
        return "; ".join(parts)
    
    def _is_https(self, request: Request) -> bool:
        """Check if request is over HTTPS."""
        # Check X-Forwarded-Proto header (for reverse proxies)
        forwarded_proto = request.headers.get("X-Forwarded-Proto", "").lower()
        if forwarded_proto == "https":
            return True
        
        # Check scheme from URL
        return request.url.scheme == "https"
    
    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers to response."""
        # Process request first
        response = await call_next(request)
        
        # Add security headers
        if isinstance(response, Response):
            # X-Content-Type-Options
            response.headers["X-Content-Type-Options"] = self.content_type_options
            
            # X-Frame-Options
            response.headers["X-Frame-Options"] = self.frame_options
            
            # X-XSS-Protection
            response.headers["X-XSS-Protection"] = self.xss_protection
            
            # Strict-Transport-Security (only on HTTPS)
            if self.hsts_enabled and self._is_https(request):
                hsts_header = self._build_hsts_header()
                if hsts_header:
                    response.headers["Strict-Transport-Security"] = hsts_header
            
            # Content-Security-Policy
            if self.csp:
                response.headers["Content-Security-Policy"] = self.csp
            
            # Referrer-Policy
            response.headers["Referrer-Policy"] = self.referrer_policy
            
            # Permissions-Policy
            if self.permissions_policy:
                response.headers["Permissions-Policy"] = self.permissions_policy
            
            # Cross-Origin-Opener-Policy
            response.headers["Cross-Origin-Opener-Policy"] = self.coop
            
            # Cross-Origin-Embedder-Policy (optional)
            if self.coep_enabled:
                response.headers["Cross-Origin-Embedder-Policy"] = self.coep
            
            # Cross-Origin-Resource-Policy
            response.headers["Cross-Origin-Resource-Policy"] = self.corp
        
        return response
