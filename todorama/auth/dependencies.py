"""
Authentication and authorization dependencies for FastAPI.
"""
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
import logging

from todorama.adapters.http_framework import HTTPFrameworkAdapter
from todorama.adapters.validation import ValidationAdapter
from todorama.auth.permissions import (
    has_permission, get_user_permissions_from_roles, ADMIN
)
from todorama.services.role_service import RoleService

logger = logging.getLogger(__name__)

# Initialize adapters
http_adapter = HTTPFrameworkAdapter()
HTTPException = http_adapter.HTTPException
Request = http_adapter.Request
HTTPAuthorizationCredentials = http_adapter.HTTPAuthorizationCredentials
Depends = http_adapter.Depends


async def verify_api_key(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = None,
    db=None  # Will be injected from dependencies - use global db if None for backward compatibility
) -> Dict[str, Any]:
    """
    Verify API key from request headers.
    Supports both X-API-Key header and Authorization: Bearer token.
    
    Returns:
        Dictionary with 'key_id' and 'project_id' if authenticated
    Raises:
        HTTPException 401 if authentication fails
    """
    if db is None:
        # For backward compatibility with main.py, try to use global db
        # Otherwise use service container
        try:
            import main
            db = main.db
        except (AttributeError, ImportError):
            from todorama.dependencies.services import get_db
            db = get_db()
    
    api_key = None
    
    # Try X-API-Key header first
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        api_key = api_key_header
    
    # Try Authorization: Bearer token
    if not api_key and authorization:
        api_key = authorization.credentials
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-Key header or Authorization: Bearer token."
        )
    
    # Hash the key and look it up
    key_hash = db._hash_api_key(api_key)
    key_info = db.get_api_key_by_hash(key_hash)
    
    if not key_info:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    if key_info["enabled"] != 1:
        raise HTTPException(
            status_code=401,
            detail="API key has been revoked"
        )
    
    # Update last used timestamp
    db.update_api_key_last_used(key_info["id"])
    
    # Extract organization_id from API key
    organization_id = key_info.get("organization_id")
    
    # Store in request state for use in endpoints
    request.state.project_id = key_info["project_id"]
    request.state.key_id = key_info["id"]
    request.state.organization_id = organization_id
    
    # Get admin status
    is_admin = db.is_api_key_admin(key_info["id"])
    request.state.is_admin = is_admin
    
    return {
        "key_id": key_info["id"],
        "project_id": key_info["project_id"],
        "organization_id": organization_id,
        "is_admin": is_admin
    }


async def verify_admin_api_key(
    request: Request,
    auth: Dict[str, Any] = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Verify that the API key has admin privileges.
    
    Returns:
        Same as verify_api_key if admin, else raises 403
    Raises:
        HTTPException 403 if not admin
    """
    if not auth.get("is_admin", False):
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required"
        )
    return auth


async def verify_session_token(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = None,
    db=None  # Will be injected from dependencies
) -> Dict[str, Any]:
    """
    Verify session token from Authorization: Bearer token.
    
    Returns:
        Dictionary with 'user_id', 'session_id', and 'session_token' if authenticated
    Raises:
        HTTPException 401 if authentication fails
    """
    if db is None:
        try:
            import main
            db = main.db
        except (AttributeError, ImportError):
            from todorama.dependencies.services import get_db
            db = get_db()
    
    token = None
    
    # Get token from Authorization header
    if authorization:
        token = authorization.credentials
    else:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Session token required. Provide Authorization: Bearer token."
        )
    
    # Look up session
    session = db.get_session_by_token(token)
    
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session token"
        )
    
    # Store in request state
    request.state.user_id = session["user_id"]
    request.state.session_id = session["id"]
    request.state.session_token = token
    
    # Get organization_id from session if available
    organization_id = session.get("organization_id")
    if organization_id:
        request.state.organization_id = organization_id
    
    return {
        "user_id": session["user_id"],
        "session_id": session["id"],
        "session_token": token,
        "organization_id": organization_id,
        "auth_type": "session"
    }


async def verify_user_auth(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = None,
    db=None  # Will be injected from dependencies
) -> Dict[str, Any]:
    """
    Verify either API key or session token authentication.
    Tries session token first, then API key.
    
    Returns:
        Dictionary with authentication info
    """
    if db is None:
        try:
            import main
            db = main.db
        except (AttributeError, ImportError):
            from todorama.dependencies.services import get_db
            db = get_db()
    
    # Try session token first
    token = None
    if authorization:
        token = authorization.credentials
    else:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
    
    if token:
        # Try as session token first
        session = db.get_session_by_token(token)
        if session:
            request.state.user_id = session["user_id"]
            request.state.session_id = session["id"]
            organization_id = session.get("organization_id")
            if organization_id:
                request.state.organization_id = organization_id
            return {
                "user_id": session["user_id"],
                "session_id": session["id"],
                "organization_id": organization_id,
                "auth_type": "session"
            }
    
    # Try API key if no session token found
    api_key = None
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        api_key = api_key_header
    
    if api_key:
        # Hash the key and look it up
        key_hash = db._hash_api_key(api_key)
        key_info = db.get_api_key_by_hash(key_hash)
        
        if key_info and key_info["enabled"] == 1:
            db.update_api_key_last_used(key_info["id"])
            request.state.project_id = key_info["project_id"]
            request.state.key_id = key_info["id"]
            organization_id = key_info.get("organization_id")
            if organization_id:
                request.state.organization_id = organization_id
            return {
                "key_id": key_info["id"],
                "project_id": key_info["project_id"],
                "organization_id": organization_id,
                "auth_type": "api_key"
            }
    
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide X-API-Key header or Authorization: Bearer token."
    )


async def optional_api_key(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = None,
    db=None  # Will be injected from dependencies
) -> Optional[Dict[str, Any]]:
    """
    Optional API key verification.
    Returns None if no API key provided (instead of raising error).
    """
    if db is None:
        try:
            import main
            db = main.db
        except (AttributeError, ImportError):
            from todorama.dependencies.services import get_db
            db = get_db()
    
    try:
        return await verify_api_key(request, authorization, db)
    except HTTPException:
        return None


async def get_current_organization(
    request: Request,
    auth: Optional[Dict[str, Any]] = None,
    db=None
) -> Optional[int]:
    """
    Get the current organization ID from request state, API key, or session.
    
    This dependency extracts organization_id from:
    1. Request state (set by verify_api_key or verify_session_token)
    2. API key's organization_id
    3. Session's organization_id
    
    Returns:
        Organization ID if available, None otherwise
    """
    if db is None:
        try:
            import main
            db = main.db
        except (AttributeError, ImportError):
            from todorama.dependencies.services import get_db
            db = get_db()
    
    # Try to get from request state (set by verify_api_key or verify_session_token)
    if hasattr(request.state, 'organization_id') and request.state.organization_id is not None:
        return request.state.organization_id
    
    # If auth dict provided, try to get from it
    if auth:
        org_id = auth.get("organization_id")
        if org_id is not None:
            return org_id
        
        # For session-based auth, get from session's organization_id
        if auth.get("auth_type") == "session":
            user_id = auth.get("user_id")
            if user_id:
                # Get user's organizations (first one as default)
                orgs = db.list_organizations(user_id=user_id)
                if orgs:
                    return orgs[0]["id"]
    
    return None


async def require_organization(
    request: Request,
    organization_id: Optional[int] = Depends(get_current_organization),
    db=None
) -> int:
    """
    Dependency that requires an organization context to exist.
    
    Raises:
        HTTPException 403 if no organization context is available
    """
    if organization_id is None:
        raise HTTPException(
            status_code=403,
            detail="Organization context required. Please ensure you're authenticated with an API key or session that has an organization."
        )
    return organization_id


def get_user_roles(
    user_id: int,
    organization_id: Optional[int] = None,
    team_id: Optional[int] = None,
    db=None
) -> List[Dict[str, Any]]:
    """
    Get user's roles in an organization or team.
    
    Args:
        user_id: User ID
        organization_id: Optional organization ID
        team_id: Optional team ID
        db: Database instance
        
    Returns:
        List of role dictionaries
    """
    if db is None:
        try:
            import main
            db = main.db
        except (AttributeError, ImportError):
            from todorama.dependencies.services import get_db
            db = get_db()
    
    role_service = RoleService(db)
    return role_service.get_user_roles(user_id, organization_id, team_id)


def require_permission(permission: str):
    """
    Dependency factory that creates a permission checker.
    
    Usage:
        @router.post("/tasks")
        async def create_task(
            request: Request,
            auth: Dict = Depends(verify_user_auth),
            _: None = Depends(require_permission("TASK_CREATE"))
        ):
            ...
    
    Args:
        permission: Required permission string
        
    Returns:
        Dependency function that checks permission
    """
    async def check_permission(
        request: Request,
        auth: Dict[str, Any] = Depends(verify_user_auth),
        db=None
    ) -> None:
        """
        Check if user has the required permission.
        Raises HTTPException 403 if permission denied.
        """
        if db is None:
            try:
                import main
                db = main.db
            except (AttributeError, ImportError):
                from todorama.dependencies.services import get_db
                db = get_db()
        
        # Admin API keys bypass permission checks
        if auth.get("is_admin", False):
            return None
        
        # Get user ID from auth
        user_id = auth.get("user_id")
        if not user_id:
            # For API key auth, we need to check if it's admin or get organization context
            # For now, if no user_id, check admin status
            if not auth.get("is_admin", False):
                raise HTTPException(
                    status_code=403,
                    detail=f"Permission denied: {permission} required"
                )
            return None
        
        # Get organization context
        organization_id = None
        if hasattr(request.state, 'organization_id'):
            organization_id = request.state.organization_id
        else:
            # Try to get from user's default organization
            orgs = db.list_organizations(user_id=user_id)
            if orgs:
                organization_id = orgs[0]["id"]
        
        if not organization_id:
            raise HTTPException(
                status_code=403,
                detail="Organization context required for permission check"
            )
        
        # Get user roles
        roles = get_user_roles(user_id, organization_id=organization_id, db=db)
        
        # Extract permissions from roles
        user_permissions = get_user_permissions_from_roles(roles)
        
        # Check permission
        if not has_permission(user_permissions, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied: {permission} required"
            )
        
        return None
    
    return check_permission

