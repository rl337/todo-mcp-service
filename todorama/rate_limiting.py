"""
Rate limiting middleware for the TODO service.

Implements sliding window rate limiting algorithm with support for:
- Global rate limits
- Per-endpoint rate limits
- Per-agent rate limits
- Configurable via environment variables
"""
import os
import time
import logging
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple
from threading import Lock

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Logger
logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Sliding window rate limiter implementation."""
    
    def __init__(self, max_requests: int, window_seconds: int):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed in the window
            window_seconds: Size of the time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()
        self.lock = Lock()
    
    def is_allowed(self, current_time: Optional[float] = None) -> Tuple[bool, int]:
        """
        Check if request is allowed and return retry-after seconds.
        
        Args:
            current_time: Current timestamp (for testing)
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        if current_time is None:
            current_time = time.time()
        
        with self.lock:
            # Remove requests outside the window
            cutoff_time = current_time - self.window_seconds
            while self.requests and self.requests[0] < cutoff_time:
                self.requests.popleft()
            
            # Check if limit exceeded
            if len(self.requests) >= self.max_requests:
                # Calculate retry-after: time until oldest request expires
                oldest_request = self.requests[0]
                retry_after = int(self.window_seconds - (current_time - oldest_request)) + 1
                return False, max(1, retry_after)
            
            # Add current request
            self.requests.append(current_time)
            remaining = self.max_requests - len(self.requests)
            return True, remaining


class TokenBucketRateLimiter:
    """Token bucket rate limiter implementation.
    
    Token bucket algorithm allows burst traffic up to bucket capacity,
    and refills tokens at a steady rate. This is ideal for per-user
    rate limiting as it allows natural traffic bursts.
    """
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket rate limiter.
        
        Args:
            capacity: Maximum number of tokens (burst size)
            refill_rate: Tokens added per second (refill rate)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = float(capacity)  # Start with full bucket
        self.last_refill = time.time()
        self.lock = Lock()
    
    def is_allowed(self, current_time: Optional[float] = None, tokens_needed: int = 1) -> Tuple[bool, float]:
        """
        Check if request is allowed and return time until next token available.
        
        Args:
            current_time: Current timestamp (for testing)
            tokens_needed: Number of tokens required (default: 1)
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        if current_time is None:
            current_time = time.time()
        
        with self.lock:
            # Refill tokens based on elapsed time
            elapsed = current_time - self.last_refill
            if elapsed > 0:
                # Add tokens at refill rate
                tokens_to_add = elapsed * self.refill_rate
                self.tokens = min(self.capacity, self.tokens + tokens_to_add)
                self.last_refill = current_time
            
            # Check if we have enough tokens
            if self.tokens >= tokens_needed:
                # Consume tokens
                self.tokens -= tokens_needed
                remaining = float(self.tokens)  # Return as float for type consistency
                return True, remaining
            else:
                # Calculate time until next token is available
                tokens_needed_after_refill = tokens_needed - self.tokens
                if self.refill_rate > 0:
                    retry_after = tokens_needed_after_refill / self.refill_rate
                else:
                    retry_after = float('inf')
                return False, max(0.0, retry_after)


class RateLimitManager:
    """Manages rate limiters for different scopes (global, endpoint, agent)."""
    
    def __init__(self):
        """Initialize rate limit manager with configuration from environment."""
        # Default limits (can be overridden by environment variables)
        self.global_max_requests = int(os.getenv("RATE_LIMIT_GLOBAL_MAX", "100"))
        self.global_window_seconds = int(os.getenv("RATE_LIMIT_GLOBAL_WINDOW", "60"))
        
        self.endpoint_max_requests = int(os.getenv("RATE_LIMIT_ENDPOINT_MAX", "200"))
        self.endpoint_window_seconds = int(os.getenv("RATE_LIMIT_ENDPOINT_WINDOW", "60"))
        
        self.agent_max_requests = int(os.getenv("RATE_LIMIT_AGENT_MAX", "50"))
        self.agent_window_seconds = int(os.getenv("RATE_LIMIT_AGENT_WINDOW", "60"))
        
        # Per-user rate limits (for authenticated users) - using token bucket algorithm
        self.user_max_requests = int(os.getenv("RATE_LIMIT_USER_MAX", "100"))
        self.user_window_seconds = int(os.getenv("RATE_LIMIT_USER_WINDOW", "60"))
        # Token bucket: capacity = max_requests, refill_rate = max_requests / window_seconds
        self.user_bucket_capacity = self.user_max_requests
        self.user_refill_rate = float(self.user_max_requests) / float(self.user_window_seconds)
        
        # Per-endpoint overrides (format: "ENDPOINT_PATH:max:window")
        # Example: "RATE_LIMIT_ENDPOINT_OVERRIDES=/health:500:60,/mcp/sse:10:60"
        endpoint_overrides = os.getenv("RATE_LIMIT_ENDPOINT_OVERRIDES", "")
        self.endpoint_overrides: Dict[str, Tuple[int, int]] = {}
        if endpoint_overrides:
            for override in endpoint_overrides.split(","):
                parts = override.strip().split(":")
                if len(parts) == 3:
                    endpoint_path, max_req, window = parts
                    self.endpoint_overrides[endpoint_path] = (int(max_req), int(window))
        
        # Per-agent overrides (format: "AGENT_ID:max:window")
        agent_overrides = os.getenv("RATE_LIMIT_AGENT_OVERRIDES", "")
        self.agent_overrides: Dict[str, Tuple[int, int]] = {}
        if agent_overrides:
            for override in agent_overrides.split(","):
                parts = override.strip().split(":")
                if len(parts) == 3:
                    agent_id, max_req, window = parts
                    self.agent_overrides[agent_id] = (int(max_req), int(window))
        
        # Per-user overrides (format: "USER_ID:max:window")
        user_overrides = os.getenv("RATE_LIMIT_USER_OVERRIDES", "")
        self.user_overrides: Dict[str, Tuple[int, int]] = {}
        if user_overrides:
            for override in user_overrides.split(","):
                parts = override.strip().split(":")
                if len(parts) == 3:
                    user_id, max_req, window = parts
                    self.user_overrides[user_id] = (int(max_req), int(window))
        
        # Rate limiters: keyed by scope identifier
        self.global_limiter = SlidingWindowRateLimiter(
            self.global_max_requests,
            self.global_window_seconds
        )
        self.endpoint_limiters: Dict[str, SlidingWindowRateLimiter] = defaultdict(
            lambda: SlidingWindowRateLimiter(
                self.endpoint_max_requests,
                self.endpoint_window_seconds
            )
        )
        self.agent_limiters: Dict[str, SlidingWindowRateLimiter] = defaultdict(
            lambda: SlidingWindowRateLimiter(
                self.agent_max_requests,
                self.agent_window_seconds
            )
        )
        # Use token bucket for per-user rate limiting
        self.user_limiters: Dict[str, TokenBucketRateLimiter] = defaultdict(
            lambda: TokenBucketRateLimiter(
                self.user_bucket_capacity,
                self.user_refill_rate
            )
        )
        
        logger.info(
            "Rate limiting initialized",
            extra={
                "global_limit": f"{self.global_max_requests}/{self.global_window_seconds}s (sliding window)",
                "endpoint_limit": f"{self.endpoint_max_requests}/{self.endpoint_window_seconds}s (sliding window)",
                "agent_limit": f"{self.agent_max_requests}/{self.agent_window_seconds}s (sliding window)",
                "user_limit": f"{self.user_bucket_capacity} capacity, {self.user_refill_rate:.2f} tokens/s (token bucket)",
                "endpoint_overrides": len(self.endpoint_overrides),
                "agent_overrides": len(self.agent_overrides),
                "user_overrides": len(self.user_overrides),
            }
        )
    
    def _get_endpoint_limiter(self, endpoint_path: str) -> SlidingWindowRateLimiter:
        """Get or create rate limiter for an endpoint."""
        # Check for override
        if endpoint_path in self.endpoint_overrides:
            max_req, window = self.endpoint_overrides[endpoint_path]
            # Create or update limiter with override values
            if endpoint_path not in self.endpoint_limiters:
                self.endpoint_limiters[endpoint_path] = SlidingWindowRateLimiter(max_req, window)
            return self.endpoint_limiters[endpoint_path]
        
        return self.endpoint_limiters[endpoint_path]
    
    def _get_agent_limiter(self, agent_id: str) -> SlidingWindowRateLimiter:
        """Get or create rate limiter for an agent."""
        # Check for override
        if agent_id in self.agent_overrides:
            max_req, window = self.agent_overrides[agent_id]
            # Create or update limiter with override values
            if agent_id not in self.agent_limiters:
                self.agent_limiters[agent_id] = SlidingWindowRateLimiter(max_req, window)
            return self.agent_limiters[agent_id]
        
        return self.agent_limiters[agent_id]
    
    def _get_user_limiter(self, user_id: str) -> TokenBucketRateLimiter:
        """Get or create rate limiter for a user (using token bucket algorithm)."""
        # Check for override
        if user_id in self.user_overrides:
            max_req, window = self.user_overrides[user_id]
            # Convert to token bucket parameters
            capacity = max_req
            refill_rate = float(max_req) / float(window)
            # Create or update limiter with override values
            if user_id not in self.user_limiters:
                self.user_limiters[user_id] = TokenBucketRateLimiter(capacity, refill_rate)
            return self.user_limiters[user_id]
        
        return self.user_limiters[user_id]
    
    def _extract_agent_id(self, request: Request) -> Optional[str]:
        """Extract agent ID from request (from query params or headers)."""
        # Try to get from query params
        agent_id = request.query_params.get("agent_id")
        if agent_id:
            return agent_id
        
        # Try to get from headers
        agent_id = request.headers.get("X-Agent-ID")
        if agent_id:
            return agent_id
        
        # Note: For POST requests, agent_id is often in the JSON body
        # but we can't read it in middleware without consuming the stream
        # So we rely on headers and query params for per-agent rate limiting
        # Per-endpoint and global limits still apply
        
        return None
    
    def _extract_user_id(self, request: Request) -> Optional[str]:
        """Extract user ID from request state (set by authentication middleware)."""
        # User ID is set in request.state by verify_session_token or verify_user_auth
        user_id = getattr(request.state, "user_id", None)
        if user_id:
            return str(user_id)
        return None
    
    def _normalize_endpoint_path(self, path: str) -> str:
        """Normalize endpoint path for rate limiting (remove IDs, etc.)."""
        import re
        # Replace UUIDs
        path = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '{id}',
            path,
            flags=re.IGNORECASE
        )
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        return path
    
    def check_rate_limit(
        self,
        request: Request,
        agent_id: Optional[str] = None
    ) -> Tuple[bool, Optional[int], Dict[str, int]]:
        """
        Check if request should be rate limited.
        
        Args:
            request: FastAPI request object
            agent_id: Optional agent ID (extracted if not provided)
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset
        """
        current_time = time.time()
        endpoint_path = self._normalize_endpoint_path(request.url.path)
        
        # Extract agent ID if not provided
        if agent_id is None:
            agent_id = self._extract_agent_id(request)
        
        # Check global limit
        global_allowed, global_info = self.global_limiter.is_allowed(current_time)
        if not global_allowed:
            logger.warning(
                "Global rate limit exceeded",
                extra={
                    "endpoint": endpoint_path,
                    "agent_id": agent_id,
                    "retry_after": global_info,
                }
            )
            return False, global_info, {
                "limit": self.global_max_requests,
                "remaining": 0,
                "reset": int(current_time) + global_info,
            }
        
        # Check endpoint limit
        endpoint_limiter = self._get_endpoint_limiter(endpoint_path)
        endpoint_allowed, endpoint_info = endpoint_limiter.is_allowed(current_time)
        if not endpoint_allowed:
            logger.warning(
                "Endpoint rate limit exceeded",
                extra={
                    "endpoint": endpoint_path,
                    "agent_id": agent_id,
                    "retry_after": endpoint_info,
                }
            )
            return False, endpoint_info, {
                "limit": endpoint_limiter.max_requests,
                "remaining": 0,
                "reset": int(current_time) + endpoint_info,
            }
        
        # Check agent limit (if agent ID available)
        if agent_id:
            agent_limiter = self._get_agent_limiter(agent_id)
            agent_allowed, agent_info = agent_limiter.is_allowed(current_time)
            if not agent_allowed:
                logger.warning(
                    "Agent rate limit exceeded",
                    extra={
                        "endpoint": endpoint_path,
                        "agent_id": agent_id,
                        "retry_after": agent_info,
                    }
                )
                return False, agent_info, {
                    "limit": agent_limiter.max_requests,
                    "remaining": 0,
                    "reset": int(current_time) + agent_info,
                }
        
        # Check user limit (if user ID available from authentication) - uses token bucket
        user_id = self._extract_user_id(request)
        user_limiter = None
        user_remaining_tokens = None
        if user_id:
            user_limiter = self._get_user_limiter(user_id)
            user_allowed, user_info = user_limiter.is_allowed(current_time)
            if not user_allowed:
                # user_info is float retry_after for token bucket
                retry_after_seconds = max(1, int(user_info) + 1)  # Round up to next second
                logger.warning(
                    "User rate limit exceeded (token bucket)",
                    extra={
                        "endpoint": endpoint_path,
                        "user_id": user_id,
                        "agent_id": agent_id,
                        "retry_after": retry_after_seconds,
                        "bucket_capacity": user_limiter.capacity,
                        "refill_rate": user_limiter.refill_rate,
                    }
                )
                return False, retry_after_seconds, {
                    "limit": user_limiter.capacity,
                    "remaining": 0,
                    "reset": int(current_time) + retry_after_seconds,
                }
            else:
                # user_info contains remaining tokens (float) when allowed
                user_remaining_tokens = float(user_info)
        
        # All checks passed
        # Calculate remaining from the most restrictive limit
        global_remaining = self.global_max_requests - len(self.global_limiter.requests)
        endpoint_remaining = endpoint_limiter.max_requests - len(endpoint_limiter.requests)
        
        # Determine the most restrictive limit
        limit = min(self.global_max_requests, endpoint_limiter.max_requests)
        remaining = min(global_remaining, endpoint_remaining)
        
        # Consider agent limit if applicable
        if agent_id:
            agent_remaining = agent_limiter.max_requests - len(agent_limiter.requests)
            limit = min(limit, agent_limiter.max_requests)
            remaining = min(remaining, agent_remaining)
        
        # Consider user limit if applicable (token bucket)
        if user_id and user_limiter is not None and user_remaining_tokens is not None:
            # user_remaining_tokens was set above when checking user limit
            user_limit_val = user_limiter.capacity
            limit = min(limit, user_limit_val)
            remaining = min(remaining, int(user_remaining_tokens))
        
        return True, None, {
            "limit": limit,
            "remaining": max(0, remaining),
            "reset": int(current_time) + self.global_window_seconds,
        }


# Global rate limit manager instance
_rate_limit_manager: Optional[RateLimitManager] = None


def get_rate_limit_manager() -> RateLimitManager:
    """Get or create the global rate limit manager."""
    global _rate_limit_manager
    if _rate_limit_manager is None:
        _rate_limit_manager = RateLimitManager()
    return _rate_limit_manager


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting API requests."""
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Get rate limit manager
        manager = get_rate_limit_manager()
        
        # Check rate limit (agent_id extracted from headers/query params)
        is_allowed, retry_after, rate_limit_info = manager.check_rate_limit(
            request,
            agent_id=None  # Will be extracted in check_rate_limit
        )
        
        if not is_allowed:
            # Return 429 Too Many Requests with clear error message
            retry_after_int = int(retry_after)
            error_detail = (
                f"You have exceeded the rate limit for this service. "
                f"Please wait {retry_after_int} second{'s' if retry_after_int != 1 else ''} before making another request. "
                f"The rate limit is {rate_limit_info['limit']} requests per time period."
            )
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "detail": error_detail,
                    "retry_after": retry_after_int,
                    "limit": rate_limit_info["limit"],
                    "remaining": rate_limit_info["remaining"],
                    "reset_at": rate_limit_info["reset"],
                    "path": request.url.path,
                    "method": request.method,
                },
                headers={
                    "Retry-After": str(retry_after_int),
                    "X-RateLimit-Limit": str(rate_limit_info["limit"]),
                    "X-RateLimit-Remaining": str(rate_limit_info["remaining"]),
                    "X-RateLimit-Reset": str(rate_limit_info["reset"]),
                }
            )
            return response
        
        # Request allowed, proceed
        response = await call_next(request)
        
        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(rate_limit_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(rate_limit_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(rate_limit_info["reset"])
        
        return response
